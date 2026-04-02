#!/usr/bin/env python3
"""
Kahunas Hybrid Extractor v6.1
Uses API for checkin list + Playwright scraping for full Q&A data.

API Endpoint: POST https://api.kahunas.io/api/v2/checkin/list
Authentication: Bearer token (web_auth_token from Kahunas dashboard)

This hybrid approach combines:
- API speed: Get checkin list in 1 request
- Playwright reliability: Scrape full Q&A from each checkin detail page
"""

import json
import re
import sys
import time
import os
from datetime import datetime
from pathlib import Path

# Try to import requests, fall back to urllib if not available
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.parse
    import urllib.error
    HAS_REQUESTS = False


class KahunasHybridExtractor:
    """Extract fitness data using API + Playwright hybrid approach."""
    
    BASE_URL = 'https://api.kahunas.io/api/v2'
    LIST_ENDPOINT = f'{BASE_URL}/checkin/list'
    LOGIN_URL = 'https://kahunas.io/login'
    DASHBOARD_URL = 'https://kahunas.io/dashboard'
    CHECKIN_URL_TEMPLATE = 'https://kahunas.io/client/checkin/view/{uuid}'
    
    def __init__(self, token: str, email: str = None, password: str = None):
        self.token = token
        self.email = email
        self.password = password
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    def _make_api_request(self, payload: dict, cookies: dict = None) -> dict:
        """Make POST request to Kahunas API with optional cookie auth."""
        if HAS_REQUESTS:
            resp = requests.post(self.LIST_ENDPOINT, json=payload, headers=self.headers, 
                                cookies=cookies, timeout=30)
            resp.raise_for_status()
            return resp.json()
        else:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                self.LIST_ENDPOINT, 
                data=data, 
                headers=self.headers,
                method='POST'
            )
            # Add cookies if provided
            if cookies:
                req.add_header('Cookie', f"ci_session={cookies.get('ci_session', '')}")
            
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
    
    def _get_cookie_auth(self) -> dict:
        """Get authentication cookie from Playwright browser."""
        if not self.browser:
            return None
        
        try:
            cookies = self.context.cookies()
            # Find ci_session cookie
            for c in cookies:
                if c['name'] == 'ci_session':
                    return {'ci_session': c['value']}
            return None
        except:
            return None
    
    def get_all_checkins(self) -> list:
        """Fetch all checkins (up to 29) from the API using cookie auth."""
        all_checkins = []
        page = 1
        
        # Get cookie auth from browser
        cookies = self._get_cookie_auth()
        if not cookies:
            print("   WARNING: No session cookie found")
        
        while True:
            result = self._make_api_request({'page': page, 'per_page': 20}, cookies=cookies)
            data = result.get('data')
            
            if data is None:
                print("   API returned no data - may need to refresh session")
                break
            
            checkins = data.get('checkins', [])
            
            if not checkins:
                break
                
            all_checkins.extend(checkins)
            
            if page >= data.get('last_page', 1):
                break
            page += 1
        
        return all_checkins
    
    def init_playwright(self):
        """Initialize Playwright for browser automation."""
        try:
            from playwright.sync_api import sync_playwright
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.context = self.browser.new_context(viewport={'width': 1920, 'height': 1080})
            self.page = self.context.new_page()
            return True
        except Exception as e:
            print(f"   Playwright not available: {e}")
            return False
    
    def close_playwright(self):
        """Close Playwright browser."""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def login_to_kahunas(self):
        """Login to Kahunas using email/password."""
        if not self.email or not self.password:
            raise ValueError("Email and password are required for login")
        
        try:
            self.page.goto(self.LOGIN_URL, wait_until='domcontentloaded', timeout=30000)
            time.sleep(2)
            
            # Fill login form using name attributes (more reliable)
            self.page.fill('input[name="identity"]', self.email)
            self.page.fill('input[name="password"]', self.password)
            
            time.sleep(1)
            
            # Submit using Enter key (more reliable than clicking)
            self.page.press('input[name="password"]', 'Enter')
            
            time.sleep(5)
            
            # Wait for dashboard URL
            self.page.wait_for_url('**/dashboard', timeout=20000)
            
            print("   Logged in via form")
            return True
            
        except Exception as e:
            print(f"   Form login error: {e}")
            return False
    
    def login_with_token(self):
        """Try to login using token from localStorage."""
        try:
            self.page.goto(self.DASHBOARD_URL, wait_until='domcontentloaded')
            time.sleep(1)
            
            self.page.evaluate(f"""
                localStorage.setItem('web_auth_token', '{self.token}');
            """)
            self.page.reload()
            time.sleep(2)
            
            if 'login' not in self.page.url.lower():
                print("   Logged in via token")
                return True
            else:
                print("   Token injection failed")
                return False
        except Exception as e:
            print(f"   Token login failed: {e}")
            return False
    
    def extract_checkin_detail(self, uuid: str) -> dict:
        """Scrape a single checkin detail page for full Q&A data."""
        detail = {
            'checkin': {'qa_pairs': []},
            'nutrition_plan': {'qa_pairs': []},
            'workout_program': {'qa_pairs': []},
            'logs': {'qa_pairs': []},
            'weight': {}
        }
        
        try:
            url = self.CHECKIN_URL_TEMPLATE.format(uuid=uuid)
            self.page.goto(url, wait_until='domcontentloaded')
            time.sleep(1.5)
            
            # Extract weight from page header FIRST (before clicking any tabs)
            detail['weight'] = self._extract_weight_from_page()
            
            # Extract Checkin tab
            detail['checkin'] = self._extract_current_tab()
            
            # Click Nutrition Plan tab
            if self._click_tab('nutrition_plan'):
                detail['nutrition_plan'] = self._extract_current_tab()
            
            # Click Workout Program tab
            if self._click_tab('workout_plan'):
                detail['workout_program'] = self._extract_current_tab()
            
            # Click Logs tab
            if self._click_tab('logs'):
                detail['logs'] = self._extract_current_tab()
            
        except Exception as e:
            print(f"   Error scraping {uuid}: {e}")
        
        return detail
    
    def _click_tab(self, tab_key: str) -> bool:
        """Click on a tab button using multiple strategies."""
        # Map tab keys to their button text/selectors
        strategies = {
            'nutrition_plan': {
                'selectors': [
                    '#client-diet_plan-view-button',
                    '[data-action="diet_plan"]',
                    '.j-diet-plan-tab',
                    'button:has-text("Nutrition")',
                    'a:has-text("Nutrition Plan")',
                    '[data-tab="diet_plan"]',
                ],
                'keywords': ['nutrition', 'diet', 'food']
            },
            'workout_plan': {
                'selectors': [
                    '#client-workout_plan-view-button',
                    '[data-action="workout_plan"]',
                    '.j-workout-plan-tab',
                    'button:has-text("Workout")',
                    'a:has-text("Workout Program")',
                    '[data-tab="workout_plan"]',
                ],
                'keywords': ['workout', 'training', 'exercise']
            },
            'logs': {
                'selectors': [
                    '#client-logs-view-button',
                    '.j-logs-tab',
                    '[data-action="logs"]',
                    'button:has-text("Log")',
                    'a:has-text("Log")',
                    '[data-tab="logs"]',
                ],
                'keywords': ['log', 'note']
            },
        }
        
        tab_config = strategies.get(tab_key, {})
        selectors = tab_config.get('selectors', [])
        keywords = tab_config.get('keywords', [])
        
        # Try selectors first
        for selector in selectors:
            try:
                elements = self.page.query_selector_all(selector)
                for element in elements:
                    if element.is_visible():
                        element.click()
                        time.sleep(1.5)
                        return True
            except:
                continue
        
        # Fallback: search by text content
        try:
            buttons = self.page.query_selector_all('button, a, [role="tab"], .nav-item, .tab-item')
            for btn in buttons:
                text = btn.inner_text().lower()
                if any(k in text for k in keywords):
                    if btn.is_visible():
                        btn.click()
                        time.sleep(1.5)
                        return True
        except:
            pass
        
        return False
    
    def _extract_weight_from_page(self) -> dict:
        """Extract start/current weight from the page header."""
        js_code = """
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
        try:
            return self.page.evaluate(js_code)
        except:
            return {'startWeight': None, 'currentWeight': None}
    
    def _extract_current_tab(self) -> dict:
        """Extract all Q&A from the current tab using tab-separated parsing."""
        js_code = """
        (function() {
            const result = { qa_pairs: [], raw_text: '' };
            
            // Get raw text
            result.raw_text = document.body.innerText.substring(0, 15000);
            
            // Method 1: Parse tab-separated Q&A pairs from body text
            // Each pair is: question[tab]answer[newline]
            const text = document.body.innerText;
            const lines = text.split('\\n');
            
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                // Check if line contains tab (Q\tA format)
                if (line.includes('\\t')) {
                    const parts = line.split('\\t');
                    if (parts.length >= 2) {
                        const question = parts[0].replace(/\\s+/g, ' ').trim();
                        const answer = parts.slice(1).join('\\t').replace(/\\s+/g, ' ').trim();
                        if (question.length > 3 && answer.length > 0 && answer.length < 2000) {
                            result.qa_pairs.push({
                                question: question,
                                answer: answer,
                                source: 'tab_separated'
                            });
                        }
                    }
                }
            }
            
            // Method 2: Look for key-value pairs in form-like structures
            // Scan for patterns like "Question text: Answer" where question is on one line
            for (let i = 0; i < lines.length - 1; i++) {
                const current = lines[i].trim();
                const next = lines[i + 1].trim();
                
                // Skip if current already matched as tab-separated
                const alreadyMatched = result.qa_pairs.some(q => 
                    q.source === 'tab_separated' && q.question === current);
                
                if (!alreadyMatched && current.length > 5 && current.length < 150 && 
                    next.length > 0 && next.length < 500 &&
                    current.endsWith('?')) {
                    result.qa_pairs.push({
                        question: current,
                        answer: next,
                        source: 'question_answer'
                    });
                }
            }
            
            // Method 3: Check for table rows with single td (often contains answer)
            document.querySelectorAll('table tbody tr').forEach(function(row) {
                const cells = row.querySelectorAll('td');
                const th = row.querySelector('th');
                
                if (cells.length === 1 && th) {
                    const question = th.textContent.replace(/\\s+/g, ' ').trim();
                    const answer = cells[0].textContent.replace(/\\s+/g, ' ').trim();
                    if (question && answer && answer.length < 1000) {
                        result.qa_pairs.push({
                            question: question,
                            answer: answer,
                            source: 'table_single_cell'
                        });
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
        
        try:
            return self.page.evaluate(js_code)
        except Exception as e:
            return {'qa_pairs': [], 'raw_text': '', 'error': str(e)}
    
    def extract_all_data(self) -> dict:
        """Extract all checkin data using hybrid API + scraping approach."""
        timestamp = datetime.now().isoformat()
        
        result = {
            'meta': {
                'extracted_at': timestamp,
                'source': 'kahunas.io API v2 + Playwright scraping',
                'extraction_version': '6.1',
                'extraction_method': 'hybrid_api_playwright',
                'endpoint': self.LIST_ENDPOINT,
                'data_categories': ['checkin', 'nutrition_plan', 'workout_program', 'logs'],
                'trend_focus': 'last_10_checkins',
                'note': 'API provides checkin list, Playwright scrapes full Q&A from detail pages'
            },
            'statistics': {
                'total_checkins_api': 0,
                'total_checkins_extracted': 0,
                'tabs_scraped': 0,
            },
            'checkins': [],
            'checkins_complete': [],  # Alias for compatibility with report generator
            'user_profile': {}  # Will be populated from first checkin data
        }
        
        # Alias for compatibility
        result['checkins_complete'] = result['checkins']
        
        # Step 1: Initialize Playwright FIRST to get fresh auth
        print('Step 1: Initializing browser and logging in...')
        if not self.init_playwright():
            print('   ERROR: Playwright not available')
            return result
        
        try:
            if not self.login_to_kahunas():
                print('   ERROR: Login failed')
                return result
            
            # Get fresh token from browser's window object (not localStorage)
            fresh_token = self.page.evaluate("() => { return window.web_auth_token; }")
            
            if fresh_token:
                self.token = fresh_token
                self.headers['Authorization'] = f'Bearer {self.token}'
                print(f'   Got fresh token from browser (length: {len(fresh_token)})')
            else:
                print('   WARNING: Could not get token from browser window')
        except Exception as e:
            print(f'   Error during login: {e}')
            return result
        
        # Step 2: Get checkin list from API using fresh token
        print('\nStep 2: Fetching checkin list from API...')
        all_checkins = self.get_all_checkins()
        result['statistics']['total_checkins_api'] = len(all_checkins)
        print(f'   Found {len(all_checkins)} checkins in Kahunas system')
        
        # Limit to last 10 for trend analysis
        MAX_CHECKINS = 10
        checkins_to_extract = all_checkins[:MAX_CHECKINS]
        print(f'   Will extract last {len(checkins_to_extract)} checkins')
        
        # Step 3: Scrape full Q&A data for each checkin
        print('\nStep 3: Scraping full Q&A data for each checkin...')
        print('-' * 60)
        
        for i, checkin in enumerate(checkins_to_extract):
            checkin_num = checkin.get('checkin_no', i + 1)
            date = checkin.get('date', 'Unknown')
            uuid = checkin.get('uuid', '')
            
            print(f"[{i+1}/{len(checkins_to_extract)}] Checkin #{checkin_num} - {date}")
            
            # Parse API fields
            parsed = self._parse_api_fields(checkin)
            
            # Scrape full detail if we have UUID
            detail = {}
            if uuid:
                detail = self.extract_checkin_detail(uuid)
                parsed['tabs'] = detail
                
                # Extract user_profile from first checkin - weights from page DOM
                if i == 0:
                    fields_list = checkin.get('fields', [])
                    weight_data = detail.get('weight', {})
                    
                    # Helper to find field value by name in the fields list
                    def get_field_value(fields, field_name, default=''):
                        for f in fields:
                            if f.get('name') == field_name:
                                return f.get('value', default)
                        return default
                    
                    # Extract name from raw_text (contains "Name\nEmail\nPhone" pattern)
                    raw_text = detail.get('checkin', {}).get('raw_text', '') or \
                               detail.get('nutrition_plan', {}).get('raw_text', '') or ''
                    
                    name = 'Client'
                    email = ''
                    if raw_text:
                        lines = raw_text.split('\n')
                        if len(lines) >= 2:
                            # First line is usually name, second is email
                            name = lines[0].strip()
                            email = lines[1].strip() if '@' in lines[1] else ''
                    
                    result['user_profile'] = {
                        'name': name,
                        'email': email,
                        'start_weight_kg': float(weight_data.get('startWeight') or 0),
                        'current_weight_kg': float(weight_data.get('currentWeight') or 0),
                        'age': get_field_value(fields_list, 'age', ''),
                        'package': get_field_value(fields_list, 'package', ''),
                        'checkin_day': get_field_value(fields_list, 'checkin_day', ''),
                    }
                
                # Count Q&A pairs
                total_qa = sum(len(detail.get(tab, {}).get('qa_pairs', [])) 
                               for tab in ['checkin', 'nutrition_plan', 'workout_program', 'logs'])
                print(f"           Scraped {total_qa} Q&A pairs from detail page")
                result['statistics']['tabs_scraped'] += 1
            else:
                parsed['tabs'] = {
                    'checkin': {'qa_pairs': []},
                    'nutrition_plan': {'qa_pairs': []},
                    'workout_program': {'qa_pairs': []},
                    'logs': {'qa_pairs': []}
                }
            
            result['checkins'].append(parsed)
            result['statistics']['total_checkins_extracted'] += 1
            
            # Print key findings
            if parsed.get('waist'):
                print(f"           Waist: {parsed['waist']} cm")
            
            # Check for injury notes
            injury_tab = parsed.get('tabs', {}).get('checkin', {}).get('qa_pairs', [])
            for qa in injury_tab:
                if 'injury' in qa.get('question', '').lower() or 'tennis' in qa.get('answer', '').lower():
                    print(f"           Injury note: {qa.get('answer', '')[:50]}...")
                    break
            
            time.sleep(0.5)  # Rate limiting
        
        # Close browser when done
        self.close_playwright()
        
        return result
    
    def _parse_api_fields(self, checkin: dict) -> dict:
        """Parse fields from API response."""
        parsed = {
            'checkin_no': checkin.get('checkin_no'),
            'checkin_name': checkin.get('checkin_name'),
            'date': checkin.get('date'),
            'day': checkin.get('checkin_day'),
            'uuid': checkin.get('uuid'),
            'date_utc': checkin.get('date_utc'),
            'waist': None,
            'weight': None,
            'nutrition_compliance': None,
            'nutrition_notes': None,
            'alcohol': None,
            'fluids': None,
            'stimulants': None,
            'hunger_level': None,
            'appetite': None,
            'stress': None,
            'motivation': None,
            'injuries': None,
            'resting_hr': None,
            'all_fields': checkin.get('fields', [])
        }
        
        for field in checkin.get('fields', []):
            label = field.get('label', '').lower()
            value = field.get('value', '')
            
            if 'waist' in label:
                parsed['waist'] = value
            elif 'weight' in label:
                parsed['weight'] = value
            elif 'nutrition plan' in label or 'managing with' in label:
                parsed['nutrition_compliance'] = value
            elif 'untracked' in label or 'not on plan' in label:
                parsed['nutrition_notes'] = value
            elif 'alcohol' in label:
                parsed['alcohol'] = value
            elif 'fluids' in label or 'litres' in label:
                parsed['fluids'] = value
            elif 'stimulant' in label or 'coffee' in label:
                parsed['stimulants'] = value
            elif 'hunger' in label and 'level' in label:
                parsed['hunger_level'] = value
            elif 'appetite' in label:
                parsed['appetite'] = value
            elif 'stress' in label:
                parsed['stress'] = value
            elif 'motivation' in label:
                parsed['motivation'] = value
            elif 'injury' in label or 'niggle' in label:
                parsed['injuries'] = value
            elif 'resting heart rate' in label:
                parsed['resting_hr'] = value
        
        return parsed
    
    def _extract_api_only(self, checkins: list, result: dict) -> dict:
        """Fallback: Extract only API data without Playwright scraping."""
        print('\nFallback: Extracting API-only data...')
        
        for checkin in checkins:
            parsed = self._parse_api_fields(checkin)
            parsed['tabs'] = {
                'checkin': {'qa_pairs': [], 'source': 'api_fallback'},
                'nutrition_plan': {'qa_pairs': [], 'source': 'api_fallback'},
                'workout_program': {'qa_pairs': [], 'source': 'api_fallback'},
                'logs': {'qa_pairs': [], 'source': 'api_fallback'}
            }
            result['checkins'].append(parsed)
            result['statistics']['total_checkins_extracted'] += 1
        
        return result


def main():
    """Main extraction function."""
    print('=' * 70)
    print('KAHUNAS HYBRID EXTRACTOR v6.1')
    print('API (checkin list) + Playwright (full Q&A detail scraping)')
    print('=' * 70)
    
    # Parse arguments
    token = None
    email = None
    password = None
    
    args = sys.argv[1:]
    if args:
        token = args[0]
        if len(args) > 2:
            email = args[1]
            password = args[2]
    else:
        # Try to read from environment or config
        env_path = Path.home() / '.hermes' / '.env'
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith('KAHUNAS_TOKEN='):
                        token = line.split('=', 1)[1].strip()
                    elif line.startswith('KAHUNAS_EMAIL='):
                        email = line.split('=', 1)[1].strip()
                    elif line.startswith('KAHUNAS_PASSWORD='):
                        password = line.split('=', 1)[1].strip()
    
    # If no token provided, we'll get one via Playwright login
    # Password is required for Playwright login
    if not password:
        password = os.environ.get('KAHUNAS_COACH_PASSWORD', '')
    if not email:
        email = os.environ.get('KAHUNAS_COACH_EMAIL', '')
    
    try:
        extractor = KahunasHybridExtractor(token, email, password)
        result = extractor.extract_all_data()
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = Path.home() / 'kahunas_api_data' / f'kahunas_hybrid_{timestamp}.json'
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print()
        print('=' * 70)
        print('EXTRACTION COMPLETE')
        print('=' * 70)
        print(f"Total checkins in system: {result['statistics']['total_checkins_api']}")
        print(f"Checkins extracted: {result['statistics']['total_checkins_extracted']}")
        print(f"Detail pages scraped: {result['statistics']['tabs_scraped']}")
        print(f"Saved to: {output_file}")
        
        # Count total Q&A pairs
        total_qa = 0
        for c in result['checkins']:
            for tab in ['checkin', 'nutrition_plan', 'workout_program', 'logs']:
                total_qa += len(c.get('tabs', {}).get(tab, {}).get('qa_pairs', []))
        print(f"Total Q&A pairs: {total_qa}")
        
        return result
        
    except Exception as e:
        print(f'ERROR: {str(e)}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()