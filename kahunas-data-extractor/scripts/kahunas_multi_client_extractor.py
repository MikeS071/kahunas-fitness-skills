#!/usr/bin/env python3
"""
Kahunas Multi-Client Extractor v1.0
Extracts data for ALL clients when logged in as a coach.

Flow:
1. Login to Kahunas as coach at https://kahunas.io/coach/clients
2. Paginate through client list
3. For each client, extract their checkin data
4. Save each client's data to a separate JSON file
5. Generate individual reports and send to coach only

Usage:
    python3 kahunas_multi_client_extractor.py [coach_email] [coach_password]
    
Example:
    python3 kahunas_multi_client_extractor.py coach@example.com mypassword
"""

import json
import re
import sys
import time
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class KahunasMultiClientExtractor:
    """Extract fitness data for all coach clients."""
    
    BASE_URL = 'https://kahunas.io'
    LOGIN_URL = f'{BASE_URL}/login'
    COACH_CLIENTS_URL = f'{BASE_URL}/coach/clients'
    CLIENT_CHECKIN_URL_TEMPLATE = f'{BASE_URL}/client/checkin/view/{{uuid}}'
    
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.clients = []
        
    # ========================================================================
    # Browser Setup
    # ========================================================================
    
    def _init_browser(self):
        """Initialize Playwright browser."""
        from playwright.sync_api import sync_playwright
        
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(60000)
        
    def _close_browser(self):
        """Close browser and Playwright."""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def _get_auth_token(self) -> Optional[str]:
        """Get web_auth_token from page."""
        try:
            token = self.page.evaluate("window.web_auth_token")
            if token:
                return token
        except:
            pass
        return None
    
    def _get_user_uuid(self) -> Optional[str]:
        """Get userUuid from page."""
        try:
            uuid = self.page.evaluate("window.userUuid")
            if uuid:
                return uuid
        except:
            pass
        # Try to find in page source
        try:
            content = self.page.content()
            match = re.search(r'userUuid["\']?\s*[:=]\s*["\']?([a-f0-9-]{36})', content)
            if match:
                return match.group(1)
        except:
            pass
        return None
    
    # ========================================================================
    # Login
    # ========================================================================
    
    def login(self) -> bool:
        """Login to Kahunas as coach."""
        print(f"\n[LOGIN] Logging in as coach: {self.email}")
        
        try:
            self._init_browser()
            
            # Navigate to login
            self.page.goto(self.LOGIN_URL, wait_until='networkidle')
            time.sleep(2)
            
            # Fill login form
            self.page.fill('input[type="text"], input[type="email"]', self.email)
            self.page.fill('input[type="password"]', self.password)
            
            # Click submit - Kahunas uses input[type="submit"][name="signin"]
            self.page.click('input[type="submit"][name="signin"]')
            time.sleep(3)
            
            # Check if login succeeded
            if 'login' in self.page.url.lower():
                print("   ERROR: Login failed - still on login page")
                return False
            
            # Get auth token
            token = self._get_auth_token()
            if not token:
                print("   ERROR: Could not get auth token after login")
                return False
            
            print(f"   SUCCESS: Logged in, token obtained")
            return True
            
        except Exception as e:
            print(f"   ERROR: Login failed: {e}")
            return False
    
    # ========================================================================
    # Client List Extraction
    # ========================================================================
    
    def extract_client_list(self) -> List[Dict]:
        """Navigate to coach clients page and extract all clients."""
        print(f"\n[CLIENTS] Extracting client list from {self.COACH_CLIENTS_URL}")
        
        try:
            self.page.goto(self.COACH_CLIENTS_URL, wait_until='networkidle')
            time.sleep(3)
            
            clients = []
            page_num = 1
            
            while True:
                print(f"   Processing page {page_num}...")
                
                # Wait for client list to load
                self.page.wait_for_selector('table tbody tr, .client-list tr, [data-client-id]', timeout=10000)
                time.sleep(1)
                
                # Extract client rows - try multiple selectors
                client_rows = []
                try:
                    # Try table structure - look for rows with client links
                    client_rows = self.page.query_selector_all('table tbody tr')
                except:
                    pass
                
                if not client_rows:
                    try:
                        # Try div-based list
                        client_rows = self.page.query_selector_all('[data-client-id]')
                    except:
                        pass
                
                if not client_rows:
                    # Try to find any clickable client elements
                    client_rows = self.page.query_selector_all('.client-name, .client-item, .client-row')
                
                print(f"   Found {len(client_rows)} rows on page {page_num}")
                
                # Extract client info from each row
                for row in client_rows:
                    try:
                        client = self._extract_client_from_row(row)
                        if client and client.get('uuid'):
                            clients.append(client)
                    except Exception as e:
                        continue
                
                # Check for pagination - look for next button
                next_button = None
                try:
                    # Try multiple pagination selectors
                    selectors = [
                        '.pagination .next',
                        '.pagination .page-next', 
                        '[rel="next"]',
                        '.next-page',
                        'a[aria-label="Next"]',
                        'button:has-text("Next")',
                        '.pagination a:has-text(">")',
                        '.pagination a:has-text("»")',
                        '.page-item.next'
                    ]
                    for sel in selectors:
                        try:
                            next_button = self.page.query_selector(sel)
                            if next_button and next_button.is_enabled():
                                break
                        except:
                            continue
                except:
                    pass
                
                if next_button and next_button.is_enabled():
                    print(f"   Clicking next page button...")
                    next_button.click()
                    time.sleep(2)
                    page_num += 1
                else:
                    # Try to find page numbers and click the next one
                    try:
                        page_links = self.page.query_selector_all('.pagination a, .page-link')
                        for pl in page_links:
                            text = pl.inner_text().strip()
                            if text == str(page_num + 1) or text == '>':
                                pl.click()
                                time.sleep(2)
                                page_num += 1
                                next_button = True  # Force continue
                                break
                    except:
                        pass
                    
                    if not next_button or page_num == 1:
                        break
            
            print(f"   TOTAL: Found {len(clients)} clients")
            self.clients = clients
            return clients
            
        except Exception as e:
            print(f"   ERROR extracting client list: {e}")
            return []
    
    def _extract_client_from_row(self, row) -> Optional[Dict]:
        """Extract client info from a table row or element."""
        try:
            # The page structure has links like:
            # <a href="https://kahunas.io/coach/clients/view/UUID">Name</a>
            
            links = row.query_selector_all('a')
            
            uuid = None
            name = None
            email = None
            
            for link in links:
                href = link.get_attribute('href') or ''
                text = link.inner_text().strip()
                
                # Check if this is a client view link
                if '/coach/clients/view/' in href:
                    uuid_match = re.search(r'/([a-f0-9-]{36})', href)
                    if uuid_match:
                        uuid = uuid_match.group(1)
                    if text and len(text) > 1:
                        name = text
                elif '@' in text:
                    email = text
            
            # If name is still None, try to get from cell text
            if not name:
                cells = row.query_selector_all('td')
                for cell in cells:
                    text = cell.inner_text().strip()
                    if text and len(text) > 3 and not text.startswith('202') and '@' not in text:
                        if any(c.isalpha() for c in text) and 'Active' not in text and 'Deactivated' not in text:
                            name = text
                            break
            
            # Try to extract email from row text if not found in links
            if not email:
                row_text = row.inner_text()
                email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', row_text)
                if email_match:
                    email = email_match.group(1)
            
            if uuid:
                return {
                    'uuid': uuid,
                    'name': name or 'Unknown',
                    'email': email or '',
                    'extracted_at': datetime.now().isoformat()
                }
        except:
            pass
        
        return None
    
    # ========================================================================
    # Single Client Data Extraction
    # ========================================================================
    
    def extract_single_client_data(self, client: Dict) -> Dict:
        """Extract all checkin data for a single client using APIs."""
        uuid = client['uuid']
        name = client['name']
        print(f"\n[EXTRACTING] Client: {name} ({uuid[:8]}...)")
        
        try:
            # Get auth token
            token = self._get_auth_token()
            if not token:
                print(f"   WARNING: No token for client {name}")
                return self._empty_client_data(client)
            
            # Get checkins via API
            checkins = self._get_checkins_via_api(token, uuid)
            if not checkins:
                print(f"   No checkins found via API")
            
            # Get scores via health-data API
            scores = self._get_scores_via_api(token, uuid)
            
            # Get user profile from client view page
            profile = self._get_client_profile(uuid)
            
            print(f"   Found {len(checkins)} checkins, scores available: {bool(scores)}")
            
            return {
                'meta': {
                    'extracted_at': datetime.now().isoformat(),
                    'source': 'multi_client_extractor_v1.0',
                    'client_uuid': uuid,
                    'client_name': name,
                    'client_email': client.get('email', ''),
                    'coach_email': self.email
                },
                'user_profile': profile,
                'checkins_complete': checkins,
                'scores': scores
            }
            
        except Exception as e:
            print(f"   ERROR extracting client {name}: {e}")
            return self._empty_client_data(client)
    
    def _empty_client_data(self, client: Dict) -> Dict:
        """Return empty data structure for a client."""
        return {
            'meta': {
                'extracted_at': datetime.now().isoformat(),
                'client_uuid': client['uuid'],
                'client_name': client['name'],
                'error': 'Extraction failed'
            },
            'user_profile': {},
            'checkins_complete': [],
            'scores': {}
        }
    
    def _get_scores_via_api(self, token: str, client_uuid: str) -> Dict:
        """Get scores data via health-data API."""
        try:
            import urllib.request
            import json
            
            url = f'https://health-data.kahunas.io/fetch-data?user_id={client_uuid}&date=2026-03-30'
            req = urllib.request.Request(url)
            req.add_header('Authorization', f'Bearer {token}')
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result.get('body', {}).get('scores', {})
        except Exception as e:
            print(f"   Scores API error: {e}")
            return {}
    
    def _get_client_profile(self, client_uuid: str) -> Dict:
        """Navigate to client view and extract profile info."""
        profile = {}
        try:
            # Navigate to client view page
            client_url = f'{self.BASE_URL}/coach/clients/view/{client_uuid}'
            self.page.goto(client_url, wait_until='networkidle')
            time.sleep(2)
            
            # Extract key profile info from page
            text = self.page.inner_text('body')
            lines = text.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                # Look for profile fields
                if 'Start Weight' in line and i + 1 < len(lines):
                    weight_match = re.search(r'(\d+\.?\d*)\s*kg', lines[i + 1])
                    if weight_match:
                        profile['start_weight'] = float(weight_match.group(1))
                
                if 'Current Weight' in line and i + 1 < len(lines):
                    weight_match = re.search(r'(\d+\.?\d*)\s*kg', lines[i + 1])
                    if weight_match:
                        profile['current_weight'] = float(weight_match.group(1))
                
                if line == 'Age' and i + 1 < len(lines):
                    age_match = re.search(r'(\d+)', lines[i + 1])
                    if age_match:
                        profile['age'] = int(age_match.group(1))
                
                if 'Package' in line and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and 'kg' not in next_line and not next_line[0].isdigit():
                        profile['package'] = next_line
                
                if 'Check in day' in line or 'Check-in day' in line:
                    if i + 1 < len(lines):
                        profile['check_in_day'] = lines[i + 1].strip()
            
        except Exception as e:
            print(f"   Profile extraction error: {e}")
        
        return profile
    
    def _extract_checkins_from_page(self) -> List[Dict]:
        """Extract basic checkin list from current page."""
        checkins = []
        
        try:
            # Wait for checkin list
            self.page.wait_for_selector('.checkin-item, .checkin-row, tr[data-checkin-id]', timeout=5000)
            time.sleep(1)
            
            # Try multiple selectors
            rows = []
            try:
                rows = self.page.query_selector_all('.checkin-item, .checkin-row')
            except:
                pass
            
            if not rows:
                try:
                    rows = self.page.query_selector_all('tr[data-checkin-id]')
                except:
                    pass
            
            for row in rows:
                try:
                    # Extract checkin data
                    checkin_id = row.get_attribute('data-checkin-id') or row.get_attribute('data-uuid')
                    
                    # Try to find date
                    date_elem = row.query_selector('.date, .checkin-date, time')
                    date = date_elem.inner_text().strip() if date_elem else ''
                    
                    # Try to find UUID from link
                    link = row.query_selector('a[href*="checkin"]')
                    uuid = None
                    if link:
                        href = link.get_attribute('href')
                        uuid_match = re.search(r'/([a-f0-9]{32,36})', href)
                        if uuid_match:
                            uuid = uuid_match.group(1)
                    
                    if uuid or checkin_id:
                        checkins.append({
                            'uuid': uuid or checkin_id,
                            'checkin_id': checkin_id,
                            'date': date,
                            'tabs': {}
                        })
                except:
                    continue
                    
        except Exception as e:
            print(f"   Warning: Could not extract checkin list: {e}")
        
        return checkins
    
    def _get_checkins_via_api(self, token: str, client_uuid: str) -> List[Dict]:
        """Get checkin list via API for a specific client."""
        try:
            import urllib.request
            import json
            
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            # Use POST to /api/v2/checkin/list with client_uuid
            url = 'https://api.kahunas.io/api/v2/checkin/list'
            data = json.dumps({'client_uuid': client_uuid}).encode()
            
            req = urllib.request.Request(url, data=data)
            for k, v in headers.items():
                req.add_header(k, v)
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if result.get('message') == 'Check In List Successful':
                    return result.get('data', {}).get('checkins', [])
            
        except Exception as e:
            print(f"   API error: {e}")
        
        return []
    
    def _merge_checkin_data(self, page_checkins: List, api_checkins: List) -> List:
        """Merge page-extracted and API checkin data."""
        # For now, just return API checkins if available
        return api_checkins if api_checkins else page_checkins
    
    def _extract_checkin_detail(self, checkin: Dict) -> Dict:
        """Extract full Q&A data from a checkin detail page."""
        uuid = checkin.get('uuid')
        if not uuid:
            return checkin
        
        try:
            detail_url = f'{self.BASE_URL}/client/checkin/view/{uuid}'
            self.page.goto(detail_url, wait_until='networkidle')
            time.sleep(2)
            
            # Extract all 4 tabs
            tabs = {}
            
            # Checkin tab (default)
            tabs['checkin'] = self._extract_tab_qa('Checkin')
            
            # Try clicking through each tab
            tab_names = ['Nutrition Plan', 'Workout Program', 'Log']
            for tab_name in tab_names:
                tabs[tab_name.lower().replace(' ', '_')] = self._extract_tab_qa(tab_name)
            
            checkin['tabs'] = tabs
            
            # Extract weight from page header
            weight = self._extract_weight_from_page()
            if weight:
                checkin['weight'] = weight
            
        except Exception as e:
            checkin['tabs'] = {'error': str(e)}
        
        return checkin
    
    def _extract_tab_qa(self, tab_name: str) -> Dict:
        """Extract Q&A from a specific tab."""
        qa_pairs = []
        raw_text = ''
        
        try:
            # Try multiple selectors to click the tab
            tab_clicked = False
            selectors = [
                f'text="{tab_name}"',
                f'.tab-{tab_name.lower().replace(" ", "-")}',
                f'[data-tab="{tab_name}"]',
                f'.j-{tab_name.lower().replace(" ", "")}-tab'
            ]
            
            for selector in selectors:
                try:
                    tab_elem = self.page.query_selector(selector)
                    if tab_elem:
                        tab_elem.click()
                        tab_clicked = True
                        time.sleep(1)
                        break
                except:
                    continue
            
            # Get raw text
            try:
                raw_text = self.page.inner_text('body')
            except:
                pass
            
            # Parse Q&A pairs from raw text
            # Look for tab-separated question/answer patterns
            lines = raw_text.split('\n')
            current_question = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Question pattern: ends with ? or is a known label
                if line.endswith('?') or any(label in line for label in [
                    'Waist', 'Hunger', 'Appetite', 'Stress', 'Motivation',
                    'Fluids', 'Alcohol', 'Nutrition', 'Workout', 'Injury',
                    'Recovery', 'Pump', 'Easiest', 'Hardest', 'well', 'better'
                ]):
                    current_question = line
                elif current_question and line:
                    # This is the answer
                    qa_pairs.append({
                        'question': current_question,
                        'answer': line,
                        'source': 'tab_separated'
                    })
                    current_question = None
            
        except Exception as e:
            pass
        
        return {
            'qa_pairs': qa_pairs,
            'raw_text': raw_text[:5000]  # Limit raw text size
        }
    
    def _extract_weight_from_page(self) -> Optional[Dict]:
        """Extract weight data from checkin detail page header."""
        try:
            text = self.page.inner_text('body')
            lines = text.split('\n')
            
            start_weight = None
            current_weight = None
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                # Look for weight patterns
                if 'Start Weight' in line or 'start weight' in line.lower():
                    # Next line should have the weight
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        weight_match = re.search(r'(\d+\.?\d*)\s*kg', next_line, re.IGNORECASE)
                        if weight_match:
                            start_weight = float(weight_match.group(1))
                
                if 'Current Weight' in line or 'current weight' in line.lower():
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        weight_match = re.search(r'(\d+\.?\d*)\s*kg', next_line, re.IGNORECASE)
                        if weight_match:
                            current_weight = float(weight_match.group(1))
            
            if start_weight or current_weight:
                return {
                    'startWeight': start_weight,
                    'currentWeight': current_weight
                }
                
        except Exception as e:
            pass
        
        return None
    
    def _extract_user_profile_from_checkin(self, checkin: Dict) -> Dict:
        """Extract user profile from checkin data."""
        if not checkin:
            return {}
        
        # Try to get from raw_text in tabs
        tabs = checkin.get('tabs', {})
        for tab_name, tab_data in tabs.items():
            raw_text = tab_data.get('raw_text', '')
            if raw_text:
                profile = self._parse_profile_from_raw_text(raw_text)
                if profile:
                    return profile
        
        return {}
    
    def _parse_profile_from_raw_text(self, raw_text: str) -> Dict:
        """Parse user profile from raw text."""
        profile = {}
        lines = raw_text.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Package
            if 'Package' in line or 'Mentorship' in line or 'Transformation' in line:
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line[0].isdigit():
                        profile['package'] = next_line
            
            # Age
            if line == 'Age' or line.lower() == 'age':
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line.isdigit():
                        profile['age'] = int(next_line)
            
            # Check-in day
            if 'Check in day' in line or 'Check-in day' in line:
                if i + 1 < len(lines):
                    profile['check_in_day'] = lines[i + 1].strip()
        
        return profile
    
    # ========================================================================
    # Main Extraction
    # ========================================================================
    
    def extract_all_clients(self) -> List[Dict]:
        """Extract data for all clients."""
        print("=" * 60)
        print("KAHUNAS MULTI-CLIENT EXTRACTOR v1.0")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        if not self.login():
            print("FATAL: Login failed")
            return []
        
        # Extract client list
        clients = self.extract_client_list()
        
        if not clients:
            print("WARNING: No clients found")
            return []
        
        # Extract data for each client
        all_data = []
        for client in clients:
            data = self.extract_single_client_data(client)
            all_data.append(data)
            
            # Save individual client file
            name_safe = client['name'].replace(' ', '_').replace('/', '-')
            uuid_short = client['uuid'][:8]
            filename = f'client_{name_safe}_{uuid_short}_{datetime.now().strftime("%Y%m%d")}.json'
            
            output_dir = Path.home() / 'kahunas_api_data' / 'clients'
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / filename
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"   Saved: {output_path.name}")
            time.sleep(1)  # Rate limiting
        
        self._close_browser()
        
        # Save master list
        master_file = Path.home() / 'kahunas_api_data' / 'clients' / f'all_clients_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(master_file, 'w') as f:
            json.dump({
                'meta': {
                    'extracted_at': datetime.now().isoformat(),
                    'total_clients': len(all_data),
                    'coach_email': self.email
                },
                'clients': all_data
            }, f, indent=2)
        
        print(f"\n[MASTER] Saved: {master_file.name}")
        print("=" * 60)
        print(f"COMPLETE: Extracted {len(all_data)} clients")
        print("=" * 60)
        
        return all_data


# ========================================================================
# Main
# ========================================================================

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nERROR: Missing required arguments")
        print("Usage: python3 kahunas_multi_client_extractor.py [coach_email] [coach_password]")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    extractor = KahunasMultiClientExtractor(email, password)
    clients_data = extractor.extract_all_clients()
    
    if not clients_data:
        print("\nWARNING: No client data extracted")
        sys.exit(1)
    
    print(f"\nSUCCESS: Extracted {len(clients_data)} clients")
    sys.exit(0)


if __name__ == '__main__':
    main()
