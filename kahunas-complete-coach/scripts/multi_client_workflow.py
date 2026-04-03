#!/usr/bin/env python3
"""
Multi-Client Weekly Workflow v6.0 - Thin Orchestrator
=====================================================
Extracts data for clients using coach credentials, generates reports, sends emails.

This script is now a thin orchestrator that:
1. Calls kahunas_extract for data extraction
2. Calls generate_llm_report.py for report generation
3. Calls email_utils for sending reports

All extraction logic lives in kahunas_extract.py.

Usage:
    python3 multi_client_workflow.py --coach samantha --daily --generate --email

Options:
    --coach NAME     Coach name (loads from coaches/<name>.json)
    --daily          Only extract clients who have new checkins since last extraction
    --generate       Generate LLM reports after extraction
    --email          Send reports via email after generation
    --clients UUID   Comma-separated partial UUIDs to process (optional)
"""

import json
import sys
import os
import subprocess
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

# Import the common extraction module
import kahunas_extract
import email_utils

# ============================================================================
# CONFIGURATION
# ============================================================================

SKILL_DIR = Path.home() / ".hermes/skills/fitness/kahunas-complete-coach"
COACHES_DIR = SKILL_DIR / "coaches"


# ============================================================================
# HELPERS
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
    """Get data directories for a coach."""
    if coach_config.get('data_dir'):
        base = Path(coach_config['data_dir'])
    else:
        base = Path.home() / "kahunas_api_data"
    return base / "clients", base / "reports", base / "logs", base


def get_env_var(key: str, default: str = "") -> str:
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


def apply_coach_env(coach_config: dict):
    """Set environment variables from coach config."""
    os.environ['KAHUNAS_COACH_EMAIL'] = coach_config['kahunas']['coach_email']
    os.environ['KAHUNAS_COACH_PASSWORD'] = coach_config['kahunas']['coach_password']
    os.environ['OPENROUTER_API_KEY'] = coach_config['openrouter']['api_key']
    os.environ['SMTP_PASS'] = coach_config['smtp']['password']
    os.environ['RESEND_FROM_EMAIL'] = coach_config['smtp']['user']


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description='Multi-Client Kahunas Workflow')
    parser.add_argument('--coach', type=str, help='Coach name (loads from coaches/<name>.json)')
    parser.add_argument('--daily', action='store_true', help='Only extract clients with new checkins')
    parser.add_argument('--generate', action='store_true', help='Generate LLM reports after extraction')
    parser.add_argument('--email', action='store_true', help='Send reports via email')
    parser.add_argument('--clients', type=str, help='Comma-separated partial UUIDs to process')
    return parser.parse_args()


# ============================================================================
# HEALTH CHECK & NOTIFICATIONS
# ============================================================================

def check_kahunas_health(max_wait=5) -> tuple:
    """Pre-flight check: verify Kahunas.io is reachable."""
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
    """Send a Telegram message via bot API."""
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
        import urllib.parse
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


# ============================================================================
# REPORT GENERATION & EMAIL
# ============================================================================

def generate_llm_report(client_data_file: Path, client_name: str, reports_dir: Path) -> Optional[Path]:
    """Generate LLM report for a client."""
    script = SKILL_DIR / "scripts" / "generate_llm_report.py"
    
    # Find venv python
    venv_python = Path.home() / "venv-playwright/bin/python3"
    if not venv_python.exists():
        venv_python = sys.executable  # Fall back to current python
    
    output_file = reports_dir / f"{client_name.replace(' ', '_')}_LLM_{date.today().strftime('%Y%m%d')}.md"
    
    cmd = [str(venv_python), str(script), "--input", str(client_data_file), "--output", str(output_file)]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and output_file.exists():
            return output_file
        else:
            print(f"      Report generation failed: {result.stderr[:200] if result.stderr else 'unknown error'}")
    except subprocess.TimeoutExpired:
        print(f"      Report generation timed out")
    except Exception as e:
        print(f"      Report generation error: {e}")
    
    return None


def send_report_email(report_file: Path, client_name: str, recipient: str, 
                      checkin_date: str, smtp_cfg: dict, coach_name: str) -> bool:
    """Send report via email."""
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
        print(f"      Email Error: {msg}")
        return False


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def main():
    global CLIENTS_DATA_DIR, REPORTS_DIR
    
    # Load .env file
    env_file = Path.home() / ".hermes/.env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    if key not in os.environ:
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
        DATA_DIR = Path.home() / "kahunas_api_data"
        CLIENTS_DATA_DIR = DATA_DIR / "clients"
        REPORTS_DIR = DATA_DIR / "reports"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CLIENTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("MULTI-CLIENT WORKFLOW v6.0 (Thin Orchestrator)")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.daily:
        print("Mode: DAILY (only new checkins)")
    if args.generate:
        print("Mode: + GENERATE REPORTS")
    if args.email:
        print("Mode: + EMAIL REPORTS")
    print("=" * 60)
    
    coach_name = coach_config.get('name', 'Unknown') if coach_config else 'Legacy'
    
    # Pre-flight health check
    print("\n[0/4] Pre-flight health check...")
    reachable, health_error = check_kahunas_health(max_wait=5)
    if not reachable:
        print(f"   FATAL: {health_error}")
        print("   Skipping this run.")
        notify_failure(
            summary=f"Kahunas.io unreachable",
            details=health_error,
            coach_name=coach_name
        )
        sys.exit(0)
    print("   ✓ Kahunas.io is reachable")
    
    # Get credentials
    if coach_config:
        email = coach_config['kahunas']['coach_email']
        password = coach_config['kahunas']['coach_password']
    else:
        email = get_env_var("KAHUNAS_COACH_EMAIL")
        password = get_env_var("KAHUNAS_COACH_PASSWORD")
        if not email or not password:
            print("ERROR: Must provide credentials via --coach or env vars")
            sys.exit(1)
    
    try:
        # ====================================================================
        # STEP 1: Login
        # ====================================================================
        print("\n[1/4] Logging in...")
        try:
            pw, context, page, token = kahunas_extract.login_and_get_token(email, password)
            print("   Logged in")
            print("   Token obtained")
        except Exception as e:
            print(f"   FATAL: Login failed: {e}")
            notify_failure(
                summary=f"Login failed after 3 attempts",
                details=str(e),
                coach_name=coach_name
            )
            sys.exit(1)
        
        # ====================================================================
        # STEP 2: Get clients
        # ====================================================================
        print("\n[2/4] Fetching client list...")
        
        deactivated_emails = set()
        if coach_config:
            deactivated_emails = set(coach_config.get('kahunas', {}).get('deactivated_clients', []))
        
        active_clients, no_checkin_clients = kahunas_extract.get_active_clients(token, deactivated_emails)
        
        print(f"   Active clients: {len(active_clients)}")
        print(f"   No checkins (excluded): {len(no_checkin_clients)}")
        
        if no_checkin_clients:
            print(f"   (No checkins: {', '.join(c['name'] for c in no_checkin_clients)})")
        
        if deactivated_emails:
            deactivated_list = [c for c in active_clients if c.get('email', '').lower() in deactivated_emails]
            if deactivated_list:
                print(f"   (Deactivated: {', '.join(c['name'] for c in deactivated_list)})")
        
        if not active_clients:
            print("FATAL: No active clients found")
            sys.exit(1)
        
        # Filter by specific clients (FIXED: partial UUID matching)
        if args.clients:
            partial_uuids = [u.strip() for u in args.clients.split(',')]
            active_clients = kahunas_extract.filter_clients_by_uuid(active_clients, partial_uuids)
            print(f"   Filtered to specific clients: {len(active_clients)}")
        
        # Filter by daily mode (FIXED: proper date comparison)
        if args.daily:
            print("\n   [DAILY MODE] Checking for new checkins...")
            filtered = []
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            for c in active_clients:
                try:
                    data = json.dumps({'client_uuid': c['uuid']}).encode()
                    req = urllib.request.Request(kahunas_extract.CHECKIN_LIST_URL, data=data)
                    for k, v in headers.items():
                        req.add_header(k, v)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        result = json.loads(resp.read())
                        api_checkins = result.get('data', {}).get('checkins', [])
                    if kahunas_extract.has_new_checkin(c['uuid'], api_checkins, CLIENTS_DATA_DIR):
                        filtered.append(c)
                        print(f"      {c['name']}: NEW")
                    else:
                        print(f"      {c['name']}: no new checkins")
                except:
                    filtered.append(c)  # On error, include client
            active_clients = filtered
            print(f"\n   Clients with new checkins: {len(active_clients)}")
            
            if not active_clients:
                print("   No clients with new data. Exiting.")
                return
        
        if not active_clients:
            print("FATAL: No clients to process")
            sys.exit(1)
        
        # ====================================================================
        # STEP 3: Extract checkins
        # ====================================================================
        print(f"\n[3/4] Extracting checkins for {len(active_clients)} client(s)...")
        
        results = kahunas_extract.extract_client_checkins(
            pw, context, page, token,
            active_clients, CLIENTS_DATA_DIR,
            max_checkins=3
        )
        
        # Save master file
        clients_data = [r[0] for r in results]
        for r in clients_data:
            r['meta']['coach_email'] = email
        master_file = kahunas_extract.save_master_file(clients_data, CLIENTS_DATA_DIR, email)
        
        print(f"\n{'='*60}")
        print(f"SUCCESS: Extracted {len(results)} client(s)")
        print(f"Data saved to: {CLIENTS_DATA_DIR}")
        print(f"Master file: {master_file.name}")
        print(f"{'='*60}")
        
        # ====================================================================
        # STEP 4: Generate reports and send emails
        # ====================================================================
        if args.generate:
            print(f"\n[4/4] Generating LLM reports...")
            
            for client_data, client_file in results:
                client_name = client_data.get('meta', {}).get('client_name', 'Unknown')
                print(f"\n   {client_name}...")
                
                # Generate report
                report_file = generate_llm_report(client_file, client_name, REPORTS_DIR)
                
                if report_file:
                    print(f"      Report: {report_file.name}")
                    
                    # Send email
                    if args.email:
                        checkins = client_data.get('checkins_complete', [])
                        checkin_date = checkins[0].get('date', '') if checkins else ''
                        recipient = coach_config.get('report_recipient') if coach_config else get_env_var('REPORT_RECIPIENT')
                        smtp_cfg = coach_config.get('smtp', {}) if coach_config else {}
                        coach_name_for_email = coach_config.get('name', 'Your Coach') if coach_config else 'Your Coach'
                        
                        if send_report_email(report_file, client_name, recipient, checkin_date, smtp_cfg, coach_name_for_email):
                            print(f"      Email sent!")
                        else:
                            print(f"      Email FAILED")
                else:
                    print(f"      Report FAILED")
            
            print(f"\n{'='*60}")
            print("DONE: Extraction and reports complete")
            print(f"{'='*60}")
        else:
            print(f"\n[4/4] Skipping report generation (use --generate to enable)")
        
    except Exception as workflow_error:
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
        raise
        
    finally:
        # Clean up browser resources
        try:
            context.close()
        except:
            pass
        try:
            pw.stop()
        except:
            pass


if __name__ == "__main__":
    main()
