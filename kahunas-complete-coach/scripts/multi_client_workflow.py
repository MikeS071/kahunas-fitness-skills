#!/usr/bin/env python3
"""
# Multi-Client Weekly Workflow v5.1 - Full Q&A Scraping
# Features: Health check, retry with backoff, Telegram failure notifications
=====================================================
Extracts data for ALL ACTIVE clients using coach credentials.
Uses API for checkin list + Playwright scraping for full Q&A detail.
Compatible with generate_full_report.py output format.

Usage:
    python3 multi_client_workflow.py [coach_email] [coach_password]

Options:
    --daily          Only extract clients who have new checkins since last extraction
    --generate       Generate LLM reports after extraction
    --email          Send reports via email after generation
    --clients UUID   Comma-separated list of specific client UUIDs to process
"""

import json
import sys
import os
import time
import re
import argparse
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

import email_utils

# ============================================================================
# CONFIGURATION
# ============================================================================

SKILL_DIR = Path.home() / ".hermes/skills/fitness/kahunas-complete-coach"
COACHES_DIR = SKILL_DIR / "coaches"

BASE_URL = 'https://api.kahunas.io/api/v2'
CHECKIN_LIST_URL = f'{BASE_URL}/checkin/list'


# ============================================================================
# Helpers
# ============================================================================

def load_coach_config(coach_name: str) -> dict:
    """Load coach configuration from coaches/<name>.json"""
    config_file = COACHES_DIR / f"{coach_name}.json"
    if not config_file.exists():
        print(f"ERROR: Coach config not found: {config_file}")
        sys.exit(1)
    with open(config_file) as f:
        return json.load(f)

def get_coach_data_dirs(coach_config: dict) -> tuple:
    """Get data directories for a coach. Coach-specific if name provided, else default."""
    coach_name = coach_config.get('name', '').replace(' ', '_')
    if coach_config.get('data_dir'):
        base = Path(coach_config['data_dir'])
    else:
        base = Path.home() / "kahunas_api_data"
    return base / "clients", base / "reports", base / "logs", base

def apply_coach_env(coach_config: dict):
    """Set environment variables from coach config."""
    os.environ['KAHUNAS_COACH_EMAIL'] = coach_config['kahunas']['coach_email']
    os.environ['KAHUNAS_COACH_PASSWORD'] = coach_config['kahunas']['coach_password']
    os.environ['OPENROUTER_API_KEY'] = coach_config['openrouter']['api_key']
    os.environ['SMTP_PASS'] = coach_config['smtp']['password']
    os.environ['RESEND_FROM_EMAIL'] = coach_config['smtp']['user']

def parse_args():
    parser = argparse.ArgumentParser(description='Multi-Client Kahunas Workflow')
    parser.add_argument('--coach', type=str, help='Coach name (loads from coaches/<name>.json)')
    parser.add_argument('--daily', action='store_true', help='Only extract clients with new checkins')
    parser.add_argument('--generate', action='store_true', help='Generate LLM reports after extraction')
    parser.add_argument('--email', action='store_true', help='Send reports via email')
    parser.add_argument('--clients', type=str, help='Comma-separated client UUIDs to process')
    parser.add_argument('email_arg', nargs='?', help='Coach email (positional, legacy)')
    parser.add_argument('password_arg', nargs='?', help='Coach password (positional, legacy)')
    return parser.parse_args()

def get_latest_client_file(uuid: str) -> Optional[Path]:
    """Get the most recent client data file for a given UUID."""
    pattern = f"*_{uuid[:8]}_*.json"
    files = list(CLIENTS_DATA_DIR.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)

def get_latest_checkin_date(uuid: str) -> Optional[str]:
    """Get the most recent checkin date from existing client file."""
    latest_file = get_latest_client_file(uuid)
    if not latest_file:
        return None
    try:
        with open(latest_file) as f:
            data = json.load(f)
        checkins = data.get('checkins_complete', [])
        if checkins:
            return checkins[0].get('date')
    except:
        pass
    return None

def has_new_checkin(client_uuid: str, api_checkins: List[dict]) -> bool:
    """Check if there are any new checkins since last extraction.

    Hybrid approach: compares the most-recent stored checkin date against the
    most-recent API checkin date. Uses checkin number as secondary signal when
    dates are equal (higher checkin_no = newer submission).

    This approach works correctly even when:
    - Kahunas stores future-dated checkins (e.g. "03 Apr, 2026" on Apr 1)
    - Only the last 3 checkins are stored (not all 20 returned by API)
    """
    latest_file = get_latest_client_file(client_uuid)
    if not latest_file:
        return True  # Never extracted, treat as new

    def parse_date(s):
        for fmt in ["%d %b, %Y", "%Y-%m-%d", "%d/%m/%Y"]:
            try:
                return datetime.strptime(s.strip(), fmt).date()
            except:
                continue
        return None

    try:
        with open(latest_file) as f:
            stored = json.load(f)

        stored_checkins = stored.get('checkins_complete', [])
        if not stored_checkins:
            return True

        # Get the most recent stored checkin
        stored_most_recent = stored_checkins[0]  # Already sorted newest-first by extraction
        stored_date = parse_date(stored_most_recent.get('date', ''))
        stored_no = stored_most_recent.get('checkin_no', 0)

        # Get the most recent API checkin
        if not api_checkins:
            return False

        api_most_recent = api_checkins[0]  # API returns newest-first
        api_date = parse_date(api_most_recent.get('date', ''))
        api_no = api_most_recent.get('checkin_no', 0)

        if not stored_date or not api_date:
            # Fall back to checkin number comparison
            return api_no > stored_no

        # Primary: date comparison
        if api_date > stored_date:
            return True
        if api_date < stored_date:
            return False

        # Dates equal — use checkin number as tiebreaker
        return api_no > stored_no

    except Exception:
        return True  # On any error, treat as new to avoid missed checkins

def generate_llm_report(client_data_file: Path, client_name: str) -> Optional[Path]:
    """Generate LLM report for a client."""
    import subprocess
    script = SKILL_DIR / "scripts" / "generate_llm_report.py"
    checkins = []
    try:
        with open(client_data_file) as f:
            data = json.load(f)
        checkins = data.get('checkins_complete', [])
    except:
        pass
    output_file = REPORTS_DIR / f"{client_name.replace(' ', '_')}_LLM_{date.today().strftime('%Y%m%d')}.md"
    venv_python = Path.home() / ".hermes/skills/fitness/kahunas-data-extractor/venv-playwright/bin/python3"
    
    cmd = [str(venv_python), str(script), "--input", str(client_data_file), "--output", str(output_file)]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and output_file.exists():
            return output_file
    except:
        pass
    return None

def send_report_email(report_file: Path, client_name: str, recipient: str, checkin_date: str, smtp_cfg: dict = None, coach_name: str = None) -> bool:
    """Send report via email using email_utils.
    
    Args:
        report_file: Path to the .md report file
        client_name: Client's name for personalization
        recipient: Email address to send to
        checkin_date: Check-in date string for the email header
        smtp_cfg: SMTP/Resend configuration (passed to email_utils)
        coach_name: Coach's name for the email footer
        
    Returns:
        True if email sent successfully, False otherwise
    """
    success, msg = email_utils.send_email(
        report_md_path=str(report_file),
        client_name=client_name,
        recipient=recipient,
        checkin_date=checkin_date,
        coach_name=coach_name or "Your Coach",
        smtp_cfg=smtp_cfg or {}
    )
    if success:
        return True
    else:
        print(f"   Email Error: {msg}")
        return False


def get_env_var(key, default=""):
    """Get environment variable, checking .env file as fallback."""
    val = os.environ.get(key, default)
    if not val:
        env_file = Path.home() / ".hermes/.env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith(f"{key}="):
                        val = line.strip().split("=", 1)[1]
                        break
    return val


# ============================================================================
# Health Check, Retry Logic, and Failure Notification
# ============================================================================

def check_kahunas_health(max_wait=5) -> tuple:
    """
    Pre-flight check: verify Kahunas.io is reachable.
    Returns (reachable: bool, error_msg: str)
    """
    urls_to_check = [
        'https://kahunas.io',
        'https://app.kahunas.io',
        'https://api.kahunas.io/health'
    ]
    for url in urls_to_check:
        try:
            result = subprocess.run(
                ['curl', '--fail', '--max-time', str(max_wait), '-s', '-o', '/dev/null', '-w', '%{http_code}', url],
                capture_output=True, text=True, timeout=max_wait + 2
            )
            code = result.stdout.strip()
            if result.returncode == 0 and code not in ('000', '503', '502', '504'):
                return True, ""
        except:
            pass
    # Try one more time with connection check
    try:
        result = subprocess.run(
            ['curl', '--fail', '--max-time', str(max_wait), '-s', '-o', '/dev/null', '-w', '%{http_code}', 'https://kahunas.io/login'],
            capture_output=True, text=True, timeout=max_wait + 2
        )
        code = result.stdout.strip()
        if result.returncode == 0 and code not in ('000', '503', '502', '504'):
            return True, ""
        return False, f"Kahunas.io unreachable (HTTP {code})"
    except subprocess.TimeoutExpired:
        return False, "Kahunas.io connection timed out"
    except Exception as e:
        return False, f"Kahunas.io unreachable: {e}"


def send_telegram_message(message: str, bot_token: str = None, chat_id: str = None) -> bool:
    """Send a Telegram message via bot API. Returns True on success."""
    if not bot_token:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not chat_id:
        chat_id = os.environ.get('TELEGRAM_HOME_CHANNEL', '1556514337')
    
    if not bot_token:
        print(f"   [TELEGRAM] No bot token configured — skipping notification")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
        'disable_notification': False
    }
    
    try:
        import urllib.request
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
        with urllib.request.urlopen(req, timeout=10) as resp:
            response = resp.read().decode()
            if '"ok":true' in response:
                print(f"   [TELEGRAM] Notification sent successfully")
                return True
            else:
                print(f"   [TELEGRAM] API returned error: {response[:200]}")
                return False
    except Exception as e:
        print(f"   [TELEGRAM] Failed to send: {e}")
        return False


def notify_failure(summary: str, details: str = "", coach_name: str = "Unknown") -> None:
    """Send failure notification to Telegram."""
    import html
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')
    
    # Strip and escape content for Telegram HTML
    summary_esc = html.escape(summary[:200]) if summary else "Unknown error"
    details_esc = html.escape(details[:400]) if details else ""
    coach_esc = html.escape(coach_name) if coach_name else "Unknown"
    
    msg = (
        f"⚠️ <b>Kahunas Workflow Failed</b>\n\n"
        f"<b>Coach:</b> {coach_esc}\n"
        f"<b>Time:</b> {timestamp}\n"
        f"<b>Error:</b> {summary_esc}\n"
    )
    if details_esc:
        msg += f"\n<i>Details:</i> {details_esc}\n"
    
    msg += "\n<i>Workflow will retry at next scheduled run.</i>"
    
    send_telegram_message(msg)


def retry_with_backoff(fn, max_attempts=3, initial_delay=5, max_delay=60, 
                       error_hints=None, context=None) -> tuple:
    """
    Retry a function with exponential backoff.
    Returns (success: bool, result: any, error: str)
    
    Args:
        fn: callable to retry (no args)
        max_attempts: max retry count
        initial_delay: seconds before first retry
        max_delay: max delay between retries
        error_hints: dict of error patterns -> hint strings
        context: dict with additional context for notification
    """
    import traceback
    
    if error_hints is None:
        error_hints = {}
    if context is None:
        context = {}
    
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn()
            if attempt > 1:
                print(f"   ✓ Succeeded on attempt {attempt}")
            return True, result, ""
        except Exception as e:
            last_error = str(e)
            error_type = type(e).__name__
            
            # Find matching hint
            hint = ""
            for pattern, h in error_hints.items():
                if pattern.lower() in last_error.lower():
                    hint = h
                    break
            
            if attempt < max_attempts:
                delay = min(initial_delay * (2 ** (attempt - 1)), max_delay)
                print(f"   Attempt {attempt} failed: {error_type}: {last_error}")
                if hint:
                    print(f"   Hint: {hint}")
                print(f"   Retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"   Attempt {attempt} failed: {error_type}: {last_error}")
                if hint:
                    print(f"   Final error hint: {hint}")
    
    return False, None, last_error


# ============================================================================
# Main Extraction
# ============================================================================
def main():
    global CLIENTS_DATA_DIR, REPORTS_DIR
    
    # Load .env file for cron job context (cron has minimal env)
    env_file = Path.home() / ".hermes/.env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    if key not in os.environ:  # Don't override explicit env vars
                        os.environ[key] = val
    
    args = parse_args()
    
    # Load coach config if specified
    coach_config = None
    if args.coach:
        coach_config = load_coach_config(args.coach)
        apply_coach_env(coach_config)
        CLIENTS_DATA_DIR, REPORTS_DIR, LOGS_DIR, DATA_DIR = get_coach_data_dirs(coach_config)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CLIENTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Coach: {coach_config['name']}")
        print(f"Data dir: {DATA_DIR}")
    else:
        # Legacy mode - use default dirs
        DATA_DIR = Path.home() / "kahunas_api_data"
        CLIENTS_DATA_DIR = DATA_DIR / "clients"
        REPORTS_DIR = DATA_DIR / "reports"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CLIENTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("MULTI-CLIENT EXTRACTION v5.1 (API + Q&A Scraping)")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.daily:
        print("Mode: DAILY (only new checkins)")
    if args.generate:
        print("Mode: + GENERATE REPORTS")
    if args.email:
        print("Mode: + EMAIL REPORTS")
    print("=" * 60)
    
    # Get coach name for notifications
    coach_name = coach_config.get('name', 'Unknown') if coach_config else 'Legacy'
    
    # Pre-flight health check (Option 4)
    print("\n[0/6] Pre-flight health check...")
    reachable, health_error = check_kahunas_health(max_wait=5)
    if not reachable:
        print(f"   FATAL: {health_error}")
        print("   Skipping this run. Kahunas.io must be accessible before retry.")
        notify_failure(
            summary=f"Kahunas.io unreachable",
            details=health_error,
            coach_name=coach_name
        )
        sys.exit(0)  # Exit cleanly - not an error, just skip
    print("   ✓ Kahunas.io is reachable")
    
    # Credentials
    if args.email_arg and args.password_arg:
        email = args.email_arg
        password = args.password_arg
    else:
        email = get_env_var("KAHUNAS_COACH_EMAIL")
        password = get_env_var("KAHUNAS_COACH_PASSWORD")
        
        if not email or not password:
            print("ERROR: Must provide credentials via --coach or env vars")
            sys.exit(1)
    
    from playwright.sync_api import sync_playwright
    
    # Retry-able login function (Option 1: Retry with exponential backoff)
    def login_and_get_token():
        """Perform browser login and return auth token. Can be retried.
        
        Uses standard form click + navigation wait — reliable for AJAX form submissions.
        The server returns a 303 redirect after POST; Playwright follows it automatically.
        """
        pw = sync_playwright().start()
        context = pw.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page.set_default_timeout(60000)
        
        try:
            # Step 1: Load login page
            page.goto('https://kahunas.io/login', wait_until='domcontentloaded', timeout=20000)
            
            # Wait for form to be interactive (ensures JS has loaded)
            page.wait_for_selector('input[type="password"]', timeout=15000)
            
            # Step 2: Fill credentials
            page.fill('input[type="text"], input[type="email"]', email)
            page.fill('input[type="password"]', password)
            
            # Step 3: Click submit and wait for navigation
            # Kahunas returns 303 on successful login — Playwright follows redirects
            page.click('input[type="submit"][name="signin"]')
            
            # Wait up to 45s for URL to change away from /login
            start = time.time()
            while time.time() - start < 45:
                if 'dashboard' in page.url:
                    break
                time.sleep(0.5)
            
            # Step 4: Verify we're on dashboard
            if 'dashboard' not in page.url:
                error_text = page.evaluate("""
                    () => {
                        const el = document.querySelector('.alert-danger, .error-message, .text-red, .invalid-feedback');
                        return el ? el.innerText.trim() : 'No visible error message';
                    }
                """)
                raise ValueError(f"Login did not redirect to dashboard. Stayed at: {page.url}. Error: {error_text}")
            
            # Step 5: Wait for auth token to be set (it may be set by JS callbacks after dashboard loads)
            # Wait for network to settle, then give extra time for token initialization
            page.wait_for_load_state('networkidle', timeout=15000)
            page.wait_for_timeout(5000)  # Extra buffer for JS token initialization
            
            # Step 6: Get auth token - check multiple possible sources
            token = page.evaluate("""
                () => {
                    // Primary source
                    if (window.web_auth_token && window.web_auth_token.length > 10) {
                        return window.web_auth_token;
                    }
                    // Fallback: check localStorage/sessionStorage
                    for (const key of Object.keys(window.localStorage)) {
                        if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth')) {
                            const val = localStorage.getItem(key);
                            if (val && val.length > 10) return val;
                        }
                    }
                    for (const key of Object.keys(window.sessionStorage)) {
                        if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth')) {
                            const val = sessionStorage.getItem(key);
                            if (val && val.length > 10) return val;
                        }
                    }
                    // Check cookies
                    const cookies = document.cookie;
                    const tokenMatch = cookies.match(/web_auth_token=([^;]+)/);
                    if (tokenMatch && tokenMatch[1].length > 10) {
                        return tokenMatch[1];
                    }
                    return null;
                }
            """)
            
            if not token:
                raise ValueError("Dashboard loaded but web_auth_token is missing")
            
            return pw, context, page, token
            
        except Exception:
            # Always clean up resources before re-raising
            try:
                context.close()
            except:
                pass
            try:
                pw.stop()
            except:
                pass
            raise
    
    # Error hints for retry messages
    error_hints = {
        "TimeoutError": "Kahunas.io is responding slowly. Login redirect timed out.",
        "connection refused": "Kahunas.io is down or blocking requests. Check status.",
        "net::ERR": "Network error reaching Kahunas.io.",
        "Timeout 20000ms exceeded": "Login redirect timed out. Kahunas.io may be overloaded.",
        "Timeout 45000ms exceeded": "Login redirect timed out after 45s. Kahunas.io is very slow."
    }
    
    print("\n[1/6] Logging in (with automatic retry)...")
    
    success, login_result, login_error = retry_with_backoff(
        login_and_get_token,
        max_attempts=3,
        initial_delay=10,
        max_delay=60,
        error_hints=error_hints
    )
    
    if not success:
        print(f"FATAL: Login failed after 3 attempts: {login_error}")
        notify_failure(
            summary=f"Login failed after 3 attempts",
            details=login_error,
            coach_name=coach_name
        )
        sys.exit(1)
    
    pw, context, page, token = login_result
    print("   Logged in")
    print("   Token obtained")
    
    try:
        
        # Step 2: Get ALL clients via API (bypasses broken web pagination)
        print("\n[2/6] Fetching client list via API...")
        
        all_api_clients = []
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Fetch all pages from API
        for page_num in range(1, 10):
            api_url = f'https://api.kahunas.io/api/v2/coach/clients?per_page=100&page={page_num}'
            req = urllib.request.Request(api_url)
            for k, v in headers.items():
                req.add_header(k, v)
            
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                    
                clients_data = result.get('data', [])
                meta = result.get('meta', {})
                total = meta.get('total', 0)
                
                if not clients_data:
                    break
                    
                for c in clients_data:
                    all_api_clients.append({
                        'uuid': c.get('uuid'),
                        'name': f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                        'email': c.get('email', '')
                    })
                
                print(f"   Page {page_num}: {len(clients_data)} clients (total: {len(all_api_clients)})")
                
                if len(all_api_clients) >= total:
                    break
                    
            except Exception as e:
                print(f"   Page {page_num} error: {e}")
                break
        
        print(f"\n   Total clients from API: {len(all_api_clients)}")
        
        # Step 3: Determine active clients
        # Active = has checkins AND not in the known Deactivated list
        # (Kahunas API doesn't expose archive/paused status, so we use checkins as proxy)
        print("\n[3/6] Determining active clients...")
        
        # Deactivated clients from coach config (coach-specific)
        deactivated_emails = set(coach_config.get('kahunas', {}).get('deactivated_clients', [])) if coach_config else set()
        
        active_clients = []
        no_checkin_clients = []
        deactivated_api_clients = []
        
        for c in all_api_clients:
            try:
                data = json.dumps({'client_uuid': c['uuid']}).encode()
                req = urllib.request.Request('https://api.kahunas.io/api/v2/checkin/list', data=data)
                for k, v in headers.items():
                    req.add_header(k, v)
                
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                    checkins = result.get('data', {}).get('checkins', [])
                    
                if len(checkins) > 0:
                    c['checkin_count'] = len(checkins)
                    
                    # Skip if email matches known deactivated
                    email_lower = c.get('email', '').lower()
                    if email_lower in deactivated_emails:
                        deactivated_api_clients.append(c)
                        continue
                    
                    active_clients.append(c)
                else:
                    c['checkin_count'] = 0
                    no_checkin_clients.append(c)
                    
            except Exception as e:
                c['checkin_count'] = 0
                no_checkin_clients.append(c)
        
        print(f"   Active clients: {len(active_clients)}")
        print(f"   No checkins (excluded): {len(no_checkin_clients)}")
        print(f"   Deactivated (excluded): {len(deactivated_api_clients)}")
        
        if no_checkin_clients:
            print(f"   (No checkins: {', '.join(c['name'] for c in no_checkin_clients)})")
        
        if deactivated_api_clients:
            print(f"   (Deactivated: {', '.join(c['name'] for c in deactivated_api_clients)})")
        
        clients = active_clients
        print(f"\n   Total active clients to process: {len(clients)}")
        
        if not clients:
            print("FATAL: No active clients found")
            sys.exit(1)
        
        # Filter: specific clients only
        if args.clients:
            target_uuids = set(args.clients.split(','))
            clients = [c for c in clients if c['uuid'] in target_uuids]
            print(f"   Filtered to specific clients: {len(clients)}")
        
        # Filter: daily mode - only clients with new checkins
        if args.daily:
            print("\n   [DAILY MODE] Checking for new checkins...")
            filtered_clients = []
            for c in clients:
                # Skip deactivated clients (defense-in-depth; step 3 should already filter these)
                email_lower = c.get('email', '').lower()
                if email_lower in deactivated_emails:
                    print(f"      {c['name']}: deactivated (skipping)")
                    continue
                # Get checkin list via API to check dates
                try:
                    data = json.dumps({'client_uuid': c['uuid']}).encode()
                    req = urllib.request.Request(CHECKIN_LIST_URL, data=data)
                    for k, v in headers.items():
                        req.add_header(k, v)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        result = json.loads(resp.read())
                        api_checkins = result.get('data', {}).get('checkins', [])
                    if has_new_checkin(c['uuid'], api_checkins):
                        filtered_clients.append(c)
                        print(f"      {c['name']}: NEW")
                    else:
                        print(f"      {c['name']}: no new checkins")
                except:
                    filtered_clients.append(c)  # On error, include client
            clients = filtered_clients
            print(f"\n   Clients with new checkins: {len(clients)}")
            
            if not clients:
                print("   No clients with new data. Exiting.")
                pw.stop()
                return
        
        # Step 4: Extract full Q&A data for each client
        print(f"\n[4/6] Scraping checkin details for {len(clients)} clients...")
        
        # JavaScript for extracting Q&A from checkin detail page
        EXTRACT_TAB_JS = """
        (function() {
            const result = { qa_pairs: [], raw_text: '' };
            result.raw_text = document.body.innerText.substring(0, 15000);
            
            const lines = document.body.innerText.split('\\n');
            
            // Method 1: Tab-separated Q&A
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (line.includes('\\t')) {
                    const parts = line.split('\\t');
                    if (parts.length >= 2) {
                        const question = parts[0].replace(/\\s+/g, ' ').trim();
                        const answer = parts.slice(1).join('\\t').replace(/\\s+/g, ' ').trim();
                        if (question.length > 3 && answer.length > 0 && answer.length < 2000) {
                            result.qa_pairs.push({ question, answer, source: 'tab_separated' });
                        }
                    }
                }
            }
            
            // Method 2: Question-answer pairs
            for (let i = 0; i < lines.length - 1; i++) {
                const current = lines[i].trim();
                const next = lines[i + 1].trim();
                const alreadyMatched = result.qa_pairs.some(q => q.source === 'tab_separated' && q.question === current);
                if (!alreadyMatched && current.length > 5 && current.length < 150 &&
                    next.length > 0 && next.length < 500 && current.endsWith('?')) {
                    result.qa_pairs.push({ question: current, answer: next, source: 'question_answer' });
                }
            }
            
            // Method 3: Table rows
            document.querySelectorAll('table tbody tr').forEach(function(row) {
                const cells = row.querySelectorAll('td');
                const th = row.querySelector('th');
                if (cells.length === 1 && th) {
                    const question = th.textContent.replace(/\\s+/g, ' ').trim();
                    const answer = cells[0].textContent.replace(/\\s+/g, ' ').trim();
                    if (question && answer && answer.length < 1000) {
                        result.qa_pairs.push({ question, answer, source: 'table_single_cell' });
                    }
                }
            });
            
            // Deduplicate
            const seen = new Set();
            result.qa_pairs = result.qa_pairs.filter(qa => {
                const key = qa.question.substring(0, 50) + '|' + qa.answer.substring(0, 50);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
            
            return result;
        })()
        """
        
        EXTRACT_WEIGHT_JS = """
        (function() {
            const lines = document.body.innerText.split('\\n');
            let startWeight = null;
            let currentWeight = null;
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line === 'Start Weight' && i > 0) {
                    const prev = lines[i-1].trim();
                    const match = prev.match(/(\\d+\\.?\\d*)\\s*kg/);
                    if (match) startWeight = match[1];
                }
                if (line === 'Current Weight' && i > 0) {
                    const prev = lines[i-1].trim();
                    if (prev.match(/\\d+\\.?\\d*\\s*kg/)) {
                        const match = prev.match(/(\\d+\\.?\\d*)\\s*kg/);
                        if (match) currentWeight = match[1];
                    }
                }
            }
            return { startWeight, currentWeight };
        })()
        """
        
        def click_tab(tab_key):
            """Click on a tab using multiple strategies."""
            strategies = {
                'nutrition_plan': {
                    'selectors': [
                        '#client-diet_plan-view-button', '[data-action="diet_plan"]',
                        '.j-diet-plan-tab', 'button:has-text("Nutrition")',
                        'a:has-text("Nutrition Plan")', '[data-tab="diet_plan"]',
                    ],
                    'keywords': ['nutrition', 'diet', 'food']
                },
                'workout_plan': {
                    'selectors': [
                        '#client-workout_plan-view-button', '[data-action="workout_plan"]',
                        '.j-workout-plan-tab', 'button:has-text("Workout")',
                        'a:has-text("Workout Program")', '[data-tab="workout_plan"]',
                    ],
                    'keywords': ['workout', 'training', 'exercise']
                },
                'logs': {
                    'selectors': [
                        '#client-logs-view-button', '.j-logs-tab',
                        '[data-action="logs"]', 'button:has-text("Log")',
                        'a:has-text("Log")', '[data-tab="logs"]',
                    ],
                    'keywords': ['log', 'note']
                },
            }
            
            config = strategies.get(tab_key, {})
            selectors = config.get('selectors', [])
            keywords = config.get('keywords', [])
            
            for selector in selectors:
                try:
                    elements = page.query_selector_all(selector)
                    for elem in elements:
                        if elem.is_visible():
                            elem.click()
                            time.sleep(1)
                            return True
                except:
                    continue
            
            try:
                buttons = page.query_selector_all('button, a, [role="tab"], .nav-item, .tab-item')
                for btn in buttons:
                    text = btn.inner_text().lower()
                    if any(k in text for k in keywords):
                        if btn.is_visible():
                            btn.click()
                            time.sleep(1)
                            return True
            except:
                pass
            
            return False
        
        def extract_checkin_detail(uuid):
            """Scrape a single checkin detail page for full Q&A data."""
            detail = {
                'checkin': {'qa_pairs': []},
                'nutrition_plan': {'qa_pairs': []},
                'workout_program': {'qa_pairs': []},
                'logs': {'qa_pairs': []},
                'weight': {}
            }
            
            try:
                url = f'https://kahunas.io/client/checkin/view/{uuid}'
                page.goto(url, wait_until='domcontentloaded')
                time.sleep(1.5)
                
                # Extract weight
                try:
                    detail['weight'] = page.evaluate(EXTRACT_WEIGHT_JS)
                except:
                    pass
                
                # Extract Checkin tab
                try:
                    detail['checkin'] = page.evaluate(EXTRACT_TAB_JS)
                except:
                    pass
                
                # Click through other tabs
                for tab_key in ['nutrition_plan', 'workout_plan', 'logs']:
                    if click_tab(tab_key):
                        time.sleep(0.5)
                        try:
                            tab_name = tab_key.replace('_plan', '_program').replace('_', '_')
                            detail[tab_name if tab_name != 'logs' else 'logs'] = page.evaluate(EXTRACT_TAB_JS)
                        except:
                            pass
                
            except Exception as e:
                pass
            
            return detail
        
        # Limit checkins to extract per client (for speed)
        MAX_CHECKINS_PER_CLIENT = 3
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        all_client_data = []
        date_str = datetime.now().strftime("%Y%m%d")
        
        for i, client in enumerate(clients):
            print(f"\n   [{i+1}/{len(clients)}] {client['name']}...", end="")
            
            # Get checkin list via API
            checkins = []
            try:
                data = json.dumps({'client_uuid': client['uuid']}).encode()
                req = urllib.request.Request(CHECKIN_LIST_URL, data=data)
                for k, v in headers.items():
                    req.add_header(k, v)
                
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                    checkins = result.get('data', {}).get('checkins', [])
            except Exception as e:
                print(f" Error: {e}")
                continue
            
            print(f" {len(checkins)} checkins, scraping...")
            
            # Scrape full Q&A for each checkin (limit to last N)
            checkins_to_scrape = checkins[:MAX_CHECKINS_PER_CLIENT]
            scraped_checkins = []
            
            for j, checkin in enumerate(checkins_to_scrape):
                uuid = checkin.get('uuid')
                if not uuid:
                    continue
                
                # Progress indicator for checkin scraping
                print(f"      [{j+1}/{len(checkins_to_scrape)}]", end=" ")
                
                # Parse API fields
                parsed = {
                    'checkin_no': checkin.get('checkin_no'),
                    'checkin_name': checkin.get('checkin_name'),
                    'date': checkin.get('date'),
                    'day': checkin.get('checkin_day'),
                    'uuid': uuid,
                    'date_utc': checkin.get('date_utc'),
                    'waist': None,
                    'weight': None,
                    'all_fields': checkin.get('fields', [])
                }
                
                # Parse fields from API response
                for field in checkin.get('fields', []):
                    label = field.get('label', '').lower()
                    value = field.get('value', '')
                    if 'waist' in label:
                        parsed['waist'] = value
                    elif 'weight' in label:
                        parsed['weight'] = value
                
                # Scrape full detail page
                detail = {}
                if uuid:
                    detail = extract_checkin_detail(uuid)
                    parsed['tabs'] = detail
                    
                    # Extract user_profile from first checkin
                    if j == 0:
                        weight_data = detail.get('weight', {})
                        
                        # Use API-provided name/email directly (reliable)
                        # Don't parse from raw_text as page structure varies
                        client_data = {
                            'meta': {
                                'extracted_at': datetime.now().isoformat(),
                                'source': 'multi_client_workflow_v5.0',
                                'client_uuid': client['uuid'],
                                'client_name': client['name'],
                                'client_email': client['email'],
                                'coach_email': email,
                                'checkin_count': len(checkins)
                            },
                            'user_profile': {
                                'name': client['name'],
                                'email': client['email'],
                                'start_weight_kg': float(weight_data.get('startWeight') or 0),
                                'current_weight_kg': float(weight_data.get('currentWeight') or 0),
                            },
                            'checkins_complete': [],
                            'scores': {}
                        }
                else:
                    parsed['tabs'] = {
                        'checkin': {'qa_pairs': []},
                        'nutrition_plan': {'qa_pairs': []},
                        'workout_program': {'qa_pairs': []},
                        'logs': {'qa_pairs': []}
                    }
                
                scraped_checkins.append(parsed)
                
                # Count Q&A pairs
                total_qa = sum(
                    len(detail.get(tab, {}).get('qa_pairs', []))
                    for tab in ['checkin', 'nutrition_plan', 'workout_program', 'logs']
                )
                print(f" {total_qa} Q&A")
                
                time.sleep(0.3)
            
            # Store scraped checkins in client_data
            if 'client_data' in locals():
                client_data['checkins_complete'] = scraped_checkins
            else:
                client_data = {
                    'meta': {
                        'extracted_at': datetime.now().isoformat(),
                        'source': 'multi_client_workflow_v5.0',
                        'client_uuid': client['uuid'],
                        'client_name': client['name'],
                        'client_email': client['email'],
                        'coach_email': email,
                        'checkin_count': len(checkins)
                    },
                    'user_profile': {},
                    'checkins_complete': scraped_checkins,
                    'scores': {}
                }
            
            # Save client file
            name_safe = client['name'].replace(' ', '_').replace('/', '-')
            filename = f"client_{name_safe}_{client['uuid'][:8]}_{date_str}.json"
            
            with open(CLIENTS_DATA_DIR / filename, 'w') as f:
                json.dump(client_data, f, indent=2)
            
            all_client_data.append(client_data)
        
        # Step 5: Save master file
        print(f"\n[5/6] Saving master file...")
        master = {
            'meta': {
                'extracted_at': datetime.now().isoformat(),
                'total_clients': len(all_client_data),
                'coach_email': email
            },
            'clients': all_client_data
        }
        
        master_file = CLIENTS_DATA_DIR / f"all_clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(master_file, 'w') as f:
            json.dump(master, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"SUCCESS: Extracted {len(clients)} active clients")
        print(f"Data saved to: {CLIENTS_DATA_DIR}")
        print(f"Master file: {master_file.name}")
        print(f"{'='*60}")
        
        # Optional: Generate LLM reports
        if args.generate:
            print(f"\n[6/6] Generating LLM reports...")
            for client_data in all_client_data:
                client_name = client_data.get('meta', {}).get('client_name', 'Unknown')
                # Find the saved file
                uuid = client_data.get('meta', {}).get('client_uuid', '')[:8]
                pattern = f"*_{uuid}_*.json"
                files = list(CLIENTS_DATA_DIR.glob(pattern))
                if files:
                    latest = max(files, key=lambda f: f.stat().st_mtime)
                    report_file = generate_llm_report(latest, client_name)
                    if report_file:
                        print(f"   {client_name}: {report_file.name}")
                        # Optional: Send email on success
                        if args.email:
                            checkins = client_data.get('checkins_complete', [])
                            checkin_date = checkins[0].get('date', '') if checkins else ''
                            recipient = coach_config.get('report_recipient') if coach_config else get_env_var('REPORT_RECIPIENT')
                            smtp_cfg = coach_config.get('smtp', {}) if coach_config else {}
                            coach_name = coach_config.get('name', 'Your Coach') if coach_config else 'Your Coach'
                            if send_report_email(report_file, client_name, recipient, checkin_date, smtp_cfg, coach_name):
                                print(f"      Email sent!")
                            else:
                                print(f"      Email FAILED")
                    else:
                        print(f"   {client_name}: FAILED")
        
        if args.generate:
            print(f"\n{'='*60}")
            print("DONE: Extraction and reports complete")
            print(f"{'='*60}")
        
    except Exception as workflow_error:
        # Catch any unexpected error and notify before propagating
        import traceback
        error_details = traceback.format_exc()
        print(f"\n!!! WORKFLOW ERROR !!!")
        print(f"Error: {workflow_error}")
        print(f"Details: {error_details[:500]}")
        
        notify_failure(
            summary=str(workflow_error),
            details=error_details[:800],
            coach_name=coach_name
        )
        raise  # Re-raise so finally still runs but error propagates
    
    finally:
        # Clean up browser resources
        try:
            if 'context' in dir():
                context.close()
        except:
            pass
        try:
            if 'pw' in dir():
                pw.stop()
        except:
            pass


if __name__ == "__main__":
    main()
