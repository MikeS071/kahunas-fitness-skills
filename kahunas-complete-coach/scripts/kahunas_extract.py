#!/home/hermes/venv-playwright/bin/python3
"""
Kahunas Extraction Module v6.0
Common extraction logic for Kahunas.io coach accounts.
Uses API for checkin list + Playwright scraping for full Q&A data.

This module provides:
- login_and_get_token(): Browser login, returns (playwright, context, page, token)
- get_active_clients(): Fetch all active clients via API
- filter_clients_by_uuid(): Partial UUID matching (e.g. '9b61b431' matches '9b61b431-...')
- has_new_checkin(): Check if client has new checkins since last extraction
- extract_client_checkins(): Extract full Q&A for specified clients
- save_client_data(): Save extracted data to file

Usage:
    python3 kahunas_extract.py --coach samantha --clients 9b61b431  # specific client
    python3 kahunas_extract.py --coach samantha --daily            # new checkins only
    python3 kahunas_extract.py --coach samantha                    # all active
"""

import json
import sys
import os
import time
import re
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================

SKILL_DIR = Path.home() / ".hermes/skills/fitness/kahunas-complete-coach"
COACHES_DIR = SKILL_DIR / "coaches"

BASE_URL = 'https://api.kahunas.io/api/v2'
CHECKIN_LIST_URL = f'{BASE_URL}/checkin/list'
CLIENTS_API_URL = f'{BASE_URL}/coach/clients'

# Default data directory
DEFAULT_DATA_DIR = Path.home() / "kahunas_api_data"


# ============================================================================
# CONFIG LOADING
# ============================================================================

def load_coach_config(coach_name: str) -> dict:
    """Load coach configuration from coaches/<name>.json"""
    config_file = COACHES_DIR / f"{coach_name}.json"
    if not config_file.exists():
        raise FileNotFoundError(f"Coach config not found: {config_file}")
    with open(config_file) as f:
        return json.load(f)


def get_data_dirs(coach_config: dict = None) -> Tuple[Path, Path, Path, Path]:
    """Get data directories. Returns (clients_dir, reports_dir, logs_dir, base_dir)"""
    if coach_config and coach_config.get('data_dir'):
        base = Path(coach_config['data_dir'])
    else:
        base = DEFAULT_DATA_DIR
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


# ============================================================================
# PARTIAL UUID MATCHING (FIXED)
# ============================================================================

def filter_clients_by_uuid(clients: List[dict], partial_uuids: List[str]) -> List[dict]:
    """
    Filter clients by partial UUID matching.
    
    Args:
        clients: List of client dicts with 'uuid' key
        partial_uuids: List of partial UUID strings (e.g. ['9b61b431'])
    
    Returns:
        Filtered list of clients whose uuid starts with any of the partial_uuids
    
    Example:
        '9b61b431' matches '9b61b431-a1b2-c3d4-...' (the full UUID)
    """
    if not partial_uuids:
        return clients
    
    filtered = []
    for client_uuid in partial_uuids:
        uuid_lower = client_uuid.lower().strip()
        for client in clients:
            if client.get('uuid', '').lower().startswith(uuid_lower):
                filtered.append(client)
    return filtered


# ============================================================================
# DATE PARSING (FIXED)
# ============================================================================

def parse_checkin_date(s: str) -> Optional[date]:
    """
    Parse checkin date string to date object.
    
    Supports formats: "03 Apr, 2026", "2026-04-03", "03/04/2026"
    """
    for fmt in ["%d %b, %Y", "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ============================================================================
# NEW CHECKIN DETECTION (FIXED)
# ============================================================================

def get_latest_client_file(uuid: str, clients_dir: Path) -> Optional[Path]:
    """Get the most recent client data file for a given UUID."""
    pattern = f"*_{uuid[:8]}_*.json"
    files = list(clients_dir.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def has_new_checkin(client_uuid: str, api_checkins: List[dict], clients_dir: Path) -> bool:
    """
    Check if there are new checkins since last extraction.
    
    Compares most-recent stored checkin date against most-recent API checkin date.
    Uses checkin number as secondary signal when dates are equal.
    """
    latest_file = get_latest_client_file(client_uuid, clients_dir)
    if not latest_file:
        return True  # Never extracted, treat as new

    try:
        with open(latest_file) as f:
            stored = json.load(f)

        stored_checkins = stored.get('checkins_complete', [])
        if not stored_checkins:
            return True

        # Get the most recent stored checkin
        stored_most_recent = stored_checkins[0]
        stored_date = parse_checkin_date(stored_most_recent.get('date', ''))
        stored_no = stored_most_recent.get('checkin_no', 0)

        # Get the most recent API checkin
        if not api_checkins:
            return False

        api_most_recent = api_checkins[0]  # API returns newest-first
        api_date = parse_checkin_date(api_most_recent.get('date', ''))
        api_no = api_most_recent.get('checkin_no', 0)

        if not stored_date or not api_date:
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


# ============================================================================
# LOGIN & AUTHENTICATION
# ============================================================================

def login_and_get_token(email: str, password: str) -> Tuple:
    """
    Perform browser login and return auth token.
    
    Returns: (playwright, context, page, token)
    
    Uses Playwright to:
    1. Navigate to Kahunas login
    2. Fill credentials and submit
    3. Wait for dashboard redirect
    4. Extract web_auth_token from page
    
    Raises:
        ValueError: If login fails or token not found
    """
    from playwright.sync_api import sync_playwright
    
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
        page.wait_for_selector('input[type="password"]', timeout=15000)
        
        # Step 2: Fill credentials
        page.fill('input[type="text"], input[type="email"]', email)
        page.fill('input[type="password"]', password)
        
        # Step 3: Click submit and wait for navigation
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
        
        # Step 5: Wait for auth token to be set
        page.wait_for_load_state('networkidle', timeout=15000)
        page.wait_for_timeout(5000)  # Extra buffer for JS token initialization
        
        # Step 6: Get auth token
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
                const tokenMatch = cookies.match(/web_auth_token[^;]*=([^;]+)/);
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


# ============================================================================
# CLIENT LIST
# ============================================================================

def get_active_clients(token: str, deactivated_emails: set = None) -> Tuple[List[dict], List[dict]]:
    """
    Get all active clients via API.
    
    Active = has checkins AND not deactivated.
    Deactivated clients are identified by email from coach config.
    
    Returns:
        Tuple of (active_clients, no_checkin_clients)
    """
    if deactivated_emails is None:
        deactivated_emails = set()
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    all_api_clients = []
    
    # Fetch all pages from API
    for page_num in range(1, 10):
        api_url = f'{CLIENTS_API_URL}?per_page=100&page={page_num}'
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
            
            if len(all_api_clients) >= total:
                break
                
        except Exception as e:
            print(f"   Page {page_num} error: {e}")
            break
    
    # Determine active clients (has checkins + not deactivated)
    active_clients = []
    no_checkin_clients = []
    
    for c in all_api_clients:
        try:
            data = json.dumps({'client_uuid': c['uuid']}).encode()
            req = urllib.request.Request(CHECKIN_LIST_URL, data=data)
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
                    no_checkin_clients.append(c)  # Treat as no-checkin for filtering
                    continue
                
                active_clients.append(c)
            else:
                c['checkin_count'] = 0
                no_checkin_clients.append(c)
                
        except Exception:
            c['checkin_count'] = 0
            no_checkin_clients.append(c)
    
    return active_clients, no_checkin_clients


# ============================================================================
# CHECKIN EXTRACTION
# ============================================================================

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


def click_tab(page, tab_key: str) -> bool:
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


def extract_checkin_detail(page, uuid: str) -> dict:
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
            if click_tab(page, tab_key):
                time.sleep(0.5)
                try:
                    tab_name = tab_key.replace('_plan', '_program').replace('_', '_')
                    detail[tab_name if tab_name != 'logs' else 'logs'] = page.evaluate(EXTRACT_TAB_JS)
                except:
                    pass
    
    except Exception:
        pass
    
    return detail


def extract_client_checkins(
    pw, context, page, token: str,
    clients: List[dict],
    clients_dir: Path,
    max_checkins: int = 3
) -> List[Tuple[dict, Path]]:
    """
    Extract full Q&A data for specified clients.
    
    Args:
        pw, context, page: Playwright objects from login_and_get_token()
        token: Auth token
        clients: List of client dicts with 'uuid', 'name', 'email'
        clients_dir: Directory to save extracted data
        max_checkins: Max checkins to extract per client (default 3)
    
    Returns:
        List of (client_data_dict, saved_filepath) tuples
    """
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    results = []
    date_str = datetime.now().strftime("%Y%m%d")
    
    for i, client in enumerate(clients):
        print(f"\n  [{i+1}/{len(clients)}] {client['name']}...", end="")
        
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
        
        # Scrape full Q&A for each checkin
        checkins_to_scrape = checkins[:max_checkins]
        scraped_checkins = []
        client_data = None
        
        for j, checkin in enumerate(checkins_to_scrape):
            uuid = checkin.get('uuid')
            if not uuid:
                continue
            
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
            detail = extract_checkin_detail(page, uuid)
            parsed['tabs'] = detail
            
            # Extract user_profile from first checkin
            if j == 0:
                weight_data = detail.get('weight', {})
                client_data = {
                    'meta': {
                        'extracted_at': datetime.now().isoformat(),
                        'source': 'kahunas_extract_v6.0',
                        'client_uuid': client['uuid'],
                        'client_name': client['name'],
                        'client_email': client['email'],
                        'coach_email': None,  # Set by caller if needed
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
            
            scraped_checkins.append(parsed)
            
            # Count Q&A pairs
            total_qa = sum(
                len(detail.get(tab, {}).get('qa_pairs', []))
                for tab in ['checkin', 'nutrition_plan', 'workout_program', 'logs']
            )
            print(f" {total_qa} Q&A")
            
            time.sleep(0.3)
        
        # Store scraped checkins
        if client_data:
            client_data['checkins_complete'] = scraped_checkins
        else:
            client_data = {
                'meta': {
                    'extracted_at': datetime.now().isoformat(),
                    'source': 'kahunas_extract_v6.0',
                    'client_uuid': client['uuid'],
                    'client_name': client['name'],
                    'client_email': client['email'],
                    'coach_email': None,
                    'checkin_count': len(checkins)
                },
                'user_profile': {},
                'checkins_complete': scraped_checkins,
                'scores': {}
            }
        
        # Save client file
        name_safe = client['name'].replace(' ', '_').replace('/', '-')
        filename = f"client_{name_safe}_{client['uuid'][:8]}_{date_str}.json"
        filepath = clients_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(client_data, f, indent=2)
        
        results.append((client_data, filepath))
    
    return results


def save_master_file(clients_data: List[dict], clients_dir: Path, coach_email: str = None) -> Path:
    """Save a master file containing all extracted client data."""
    master = {
        'meta': {
            'extracted_at': datetime.now().isoformat(),
            'total_clients': len(clients_data),
            'coach_email': coach_email
        },
        'clients': clients_data
    }
    
    master_file = clients_dir / f"all_clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(master_file, 'w') as f:
        json.dump(master, f, indent=2)
    
    return master_file


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Kahunas Extraction - Extract client checkin data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract specific client by partial UUID
  python3 kahunas_extract.py --coach samantha --clients 9b61b431
  
  # Extract all active clients
  python3 kahunas_extract.py --coach samantha
  
  # Extract only clients with new checkins
  python3 kahunas_extract.py --coach samantha --daily
  
  # Extract multiple specific clients
  python3 kahunas_extract.py --coach samantha --clients 9b61b431,a1b2c3d4
"""
    )
    parser.add_argument('--coach', type=str, help='Coach name (loads from coaches/<name>.json)')
    parser.add_argument('--clients', type=str, help='Comma-separated partial UUIDs to process')
    parser.add_argument('--daily', action='store_true', help='Only extract clients with new checkins')
    parser.add_argument('--max-checkins', type=int, default=3, help='Max checkins per client (default: 3)')
    parser.add_argument('--output-dir', type=str, help='Override output directory')
    return parser.parse_args()


def main():
    args = parse_args()
    
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
    
    # Load coach config
    coach_config = None
    coach_email = None
    if args.coach:
        coach_config = load_coach_config(args.coach)
        coach_email = coach_config.get('kahunas', {}).get('coach_email')
    
    # Get data directories
    clients_dir, reports_dir, logs_dir, base_dir = get_data_dirs(coach_config)
    if args.output_dir:
        base_dir = Path(args.output_dir)
        clients_dir = base_dir / "clients"
    base_dir.mkdir(parents=True, exist_ok=True)
    clients_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("KAHUNAS EXTRACTION v6.0")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.clients:
        print(f"Mode: SPECIFIC CLIENTS ({args.clients})")
    elif args.daily:
        print(f"Mode: DAILY (new checkins only)")
    else:
        print(f"Mode: ALL ACTIVE CLIENTS")
    print(f"Output: {clients_dir}")
    print("=" * 60)
    
    # Get credentials
    if coach_config:
        email = coach_config['kahunas']['coach_email']
        password = coach_config['kahunas']['coach_password']
    else:
        email = get_env_var("KAHUNAS_COACH_EMAIL")
        password = get_env_var("KAHUNAS_COACH_PASSWORD")
        if not email or not password:
            print("ERROR: Must provide --coach or set KAHUNAS_COACH_EMAIL/KAHUNAS_COACH_PASSWORD")
            sys.exit(1)
    
    # Login
    print("\n[1/4] Logging in...")
    try:
        pw, context, page, token = login_and_get_token(email, password)
        print("   Logged in")
    except Exception as e:
        print(f"   FATAL: Login failed: {e}")
        sys.exit(1)
    
    try:
        # Get clients
        deactivated_emails = set()
        if coach_config:
            deactivated_emails = set(coach_config.get('kahunas', {}).get('deactivated_clients', []))
        
        print("\n[2/4] Fetching client list...")
        active_clients, no_checkin_clients = get_active_clients(token, deactivated_emails)
        
        print(f"   Active clients: {len(active_clients)}")
        print(f"   No checkins: {len(no_checkin_clients)}")
        
        if no_checkin_clients:
            print(f"   (No checkins: {', '.join(c['name'] for c in no_checkin_clients[:5])}{'...' if len(no_checkin_clients) > 5 else ''})")
        
        if not active_clients:
            print("FATAL: No active clients found")
            sys.exit(1)
        
        # Filter by specific clients (FIXED: partial UUID matching)
        if args.clients:
            partial_uuids = [u.strip() for u in args.clients.split(',')]
            active_clients = filter_clients_by_uuid(active_clients, partial_uuids)
            print(f"   Filtered to {len(active_clients)} client(s) by UUID")
        
        if not active_clients:
            print("FATAL: No clients match the filter")
            sys.exit(1)
        
        # Filter by daily mode
        if args.daily:
            print("\n   [DAILY MODE] Checking for new checkins...")
            filtered = []
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            for c in active_clients:
                try:
                    data = json.dumps({'client_uuid': c['uuid']}).encode()
                    req = urllib.request.Request(CHECKIN_LIST_URL, data=data)
                    for k, v in headers.items():
                        req.add_header(k, v)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        result = json.loads(resp.read())
                        api_checkins = result.get('data', {}).get('checkins', [])
                    if has_new_checkin(c['uuid'], api_checkins, clients_dir):
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
        
        # Extract checkins
        print(f"\n[3/4] Extracting checkins for {len(active_clients)} client(s)...")
        results = extract_client_checkins(
            pw, context, page, token,
            active_clients, clients_dir,
            max_checkins=args.max_checkins
        )
        
        # Save master file
        print(f"\n[4/4] Saving master file...")
        clients_data = [r[0] for r in results]
        for r in clients_data:
            r['meta']['coach_email'] = coach_email
        master_file = save_master_file(clients_data, clients_dir, coach_email)
        
        print(f"\n{'='*60}")
        print(f"SUCCESS: Extracted {len(results)} client(s)")
        print(f"Data saved to: {clients_dir}")
        print(f"Master file: {master_file.name}")
        print(f"{'='*60}")
        
    finally:
        # Clean up browser
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
