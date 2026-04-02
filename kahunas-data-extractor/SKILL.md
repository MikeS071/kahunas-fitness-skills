---
name: kahunas-data-extractor
description: Extract COMPLETE fitness data from Kahunas.io including Checkin, Nutrition Plan, Workout Program, and Logs tabs
version: 6.2.0

self_contained: true
virtualenv: venv-playwright/

trend_analysis:
  focus: "Last 10 checkins for trend/pattern analysis"
  rationale: "10 checkins provides statistically meaningful data for identifying trends, plateaus, and improvement opportunities while minimizing extraction time"
  benefits:
    - Establishes consistent review cadence (approx 10 weeks of data)
    - Enough data points to identify patterns vs one-off variations
    - Captures seasonal/cycle effects (menstrual, training blocks)
    - Reduces extraction time vs full history
    - Prioritizes recent data (more relevant for current goals)
trigger: 
  - When user asks to extract Kahunas data
  - When user wants to download Kahunas checkins with all tabs
  - When user mentions comprehensive data extraction from Kahunas
  - When user needs nutrition plan, workout, or logs data
  - When working with Kahunas.io API for all 4 sub-tabs
  - When user wants workout program exercises tracked for progression analysis

critical_requirement: |
  ALWAYS extract ALL 4 tabs for every checkin. The analysis reports
  depend on complete data from ALL tabs:
  1. checkin - Biometrics, measurements, waist, heart rate, ratings
  2. nutrition_plan - Compliance, alcohol, fluids, stimulants, hunger timing
  3. workout_program - Exercises, sets, reps, weights (needed for progression analysis)
  4. logs - Coach notes, feedback, client comments

  TREND ANALYSIS FOCUS: Extraction is limited to the LAST 10 CHECKINS
  (sorted newest-first) to provide meaningful trend data without
  the time overhead of extracting full history.

api_access:
  version: "6.1 (HYBRID - RECOMMENDED)"
  endpoint: "POST https://api.kahunas.io/api/v2/checkin/list"
  authentication: "Bearer token (web_auth_token)"
  pagination: |
    - total_checkins: 29 (Michal's account)
    - last_page: 2 (20 per page default)
    - Request body: {"page": 1, "per_page": 20}
  response: |
    Returns all 29 checkins with embedded field data (label/value pairs)
    Each checkin includes 11 BASIC fields only:
  api_limited_fields:
    - "Waist Circumference"
    - "Fluids (litres)"
    - "Hunger level (1-10)"
    - "Appetite (1-10)"
    - "Stress (1-10)"
    - "Motivation (1-10)"
    - "Mobility sessions"
    - "Fasted Blood Glucose"
    - "Systolic BP"
    - "Diastolic BP"
    - "Resting Heart Rate"
  missing_from_api: |
    The following data exists ONLY in the HTML detail pages (NOT in API):
    - Nutrition compliance notes (full text)
    - Injury details and descriptions
    - Workout struggles and exercise-specific feedback
    - Coach support notes
    - "What went well" / "What could be better" free text
    - Full Q&A user comments for all 4 tabs
  hybrid_approach: |
    To get COMPLETE data (API + full Q&A), use v6.1 HYBRID method:
    1. Playwright: Login to Kahunas and get fresh web_auth_token via page.evaluate
    2. API: Get checkin list with Bearer token authentication
    3. Playwright: Scrape full Q&A from each checkin detail page (4 tabs)
    
    Script: scripts/kahunas_api_extractor.py v6.1
    Usage: python3 kahunas_api_extractor.py [token] [email] [password]
    
    The script requires: email and password from environment variables (KAHUNAS_COACH_EMAIL, KAHUNAS_COACH_PASSWORD) or arguments
    
    IMPORTANT: 
    - Token MUST come from window.web_auth_token (JS evaluation), NOT localStorage
    - ci_session cookie alone does NOT work for API auth - need Bearer token
    - Must provide password for Playwright login to get fresh token
  advantages:
    - API: 100x faster than web scraping for basic metrics
    - Hybrid: Gets complete Q&A data while still using API for efficiency
    - Structured data directly (no HTML parsing for basic fields)
    - Falls back to API-only if Playwright fails

data_categories:
  - checkin: Biometrics, measurements, waist circumference, heart rate, ratings
  - nutrition_plan: Meal compliance, alcohol, fluids, gastric distress, stimulants
  - workout_program: Exercises, sets, reps, intensity (CRITICAL for progression tracking)
  - logs: Notes, coach feedback, comments

prerequisites:
  - Access to Kahunas.io dashboard
  - Valid auth token (web_auth_token from page source)
  - User UUID (from page source)
  - Browser DevTools access OR Python with Playwright

steps:
  1: |
    Run the hybrid extractor (API + Playwright):
    
    cd ~/.hermes/skills/fitness/kahunas-data-extractor
    ./venv-playwright/bin/python3 scripts/kahunas_api_extractor.py
    
    Output: kahunas_api_data/kahunas_hybrid_YYYYMMDD_HHMMSS.json

notes: |
  - The web_auth_token and userUuid are embedded in the page source
  - **v6.0 API METHOD** (RECOMMENDED): POST https://api.kahunas.io/api/v2/checkin/list
    - Requires Bearer token authentication
    - Returns all 29 checkins with embedded field data
    - Much faster than web scraping
    - Script: scripts/kahunas_api_extractor.py
  - HTML scraping works on the /dashboard page
  - Individual checkin details at /client/checkin/view/{UUID}
  - **v6.0: Focus on last 10 checkins** - sorted newest-first, provides ~10 weeks
    of data for meaningful trend analysis without full history extraction overhead
  DISCOVERED ENDPOINTS (from JavaScript analysis):
  - /client/checkin/view/{id} - Get full checkin details (HTML) - use for workout/logs tabs
  - /client/checkin/check_in_view/{id} - Same with different path
  - /client/checkin/compar_check_in/{id} - Compare with previous checkin
  
  PAGE STRUCTURE (Key Finding):
  - Checkin details are in HTML TABLE elements with row/columnheader structure
  - Q&A pairs: columnheader = question, cell = answer
  - Example: row("Waist Circumference (belly button height in cm) 88")
  - 4 sub-tabs on each checkin page: Checkin, Nutrition Plan, Workout Program, Logs
  
  TYPICAL FIELDS EXTRACTED:
  Checkin Tab: Waist circumference, hunger ratings (1-10), appetite, stress, motivation
  Nutrition Tab: compliance status, untracked meals, alcohol, fluids (L), gastric distress, stimulants (coffees), hunger timing
  Workout Tab: exercises, sets, reps, completion status
  Logs Tab: coach notes, client comments
  
  USER PROFILE INFO (from dashboard):
  - Name and email displayed in header
  - Package name (e.g., "Men's Physique Mentorship")
  - Start weight, current weight, age, check-in day

known_issues:
  - v5.2 methods (JS/Playwright) may have issues with Kahunas UI changes
  - v6.1 HYBRID is the recommended extraction method
  - API rate limiting not yet tested (be cautious with rapid successive calls)
  - v6.1 limits to last 10 checkins for trend analysis
  - CRITICAL: Token injection (localStorage) does NOT work - password login required for web scraping
  - For FULL Q&A data, must provide Kahunas password to enable Playwright detail scraping
  - WEIGHT DATA: Start/current weight is NOT in the API (all /user/* endpoints return 404). Must be scraped from checkin detail page DOM header using the _extract_weight_from_page() method.

v6.1_critical_findings:
  token_source: "window.web_auth_token (792-char JWT) - must use page.evaluate AFTER login, NOT localStorage"
  api_auth: "ci_session cookie does NOT work. ONLY Bearer token from window.web_auth_token works"
  tab_selectors: "Nutrition: #client-diet_plan-view-button | Workout: #client-workout_plan-view-button | Logs: .j-logs-tab"
  qa_parsing: "Tab-separated values in raw text (split by \t), NOT table-based parsing"
  user_profile_api: "GET https://api.kahunas.io/api/v2/user/profile returns 404 - weight/stated data NOT available via API"
  weight_extraction: "Weight must be scraped from page DOM header. Format: '85 kg' appears BEFORE 'Start Weight' label, '76.1 kg' appears between 'Start Weight' and 'Current Weight' labels. Use line-by-line parsing on innerText."
  output_keys: "checkins (primary), checkins_complete (alias), user_profile (scraped from checkin detail page DOM)"
  coach_scraping: "Checkin detail URLs work from coach's perspective: /client/checkin/view/{uuid} - no need for /coach/ prefix. Coach session cookies suffice for scraping."
  data_compatibility: "API-only checkins return 'fields' (label/value list), NOT 'tabs.checkin.qa_pairs'. Full Q&A scraping required for report_generator compatibility. multi_client_workflow v5.0 produces compatible output."

v5.2_field_discovery:
  login_selector: "Kahunas uses input[type='submit'][name='signin'] for login, NOT a button element"
  js_syntax_fix: "When passing JavaScript to page.evaluate(), use IIFE syntax: (function() { ... })()"
  data_parsing: "Checkin Q&A data uses tab-separated values; actual data starts after 'Submitted on:' marker"
  raw_text_sample: |
    Submitted on: Friday 27 Mar, 2026 01:05 PM
    Waist Circumference (belly button height in cm)    88
    How are you managing with the nutrition plan?    Not on plan this week
    ...
  regex_parsing: |
    # Extract key metrics from raw_text:
    import re
    waist = re.search(r'Waist Circumference.*?\t(\d+)', raw_text)
    nutrition = re.search(r'nutrition plan\?\t([^\t\n]+)', raw_text)

outputs:
  - kahunas_checkins_YYYY-MM-DD.json containing:
    - extracted_at timestamp
    - user_uuid
    - checkins_from_html (array of basic checkin info)
    - api_results (if successful)
    - source URL
---

## Quick Reference

### Finding Your Token
1. Go to Kahunas dashboard
2. Right-click → View Page Source
3. Search for `web_auth_token`
4. Copy the quoted value

### Finding Your UUID
- Same location in page source
- Search for `userUuid`

### API Endpoints Discovered
- `POST https://api.kahunas.io/api/v2/checkin/list` - ONLY working endpoint (2026-03-30)
- All other endpoints (/{uuid}, /detail/{uuid}, /view/{uuid}) return 404

### API vs HTML Data (CRITICAL)
| Data Type | API | HTML Detail Page |
|-----------|-----|------------------|
| Waist | ✓ | ✓ |
| Fluids | ✓ | ✓ |
| Hunger | ✓ | ✓ |
| Appetite | ✓ | ✓ |
| Stress | ✓ | ✓ |
| Motivation | ✓ | ✓ |
| Resting HR | ✓ | ✓ |
| Start/Current Weight | ✗ | ✓ (in page header, NOT in Q&A tab) |
| Nutrition notes (full) | ✗ | ✓ |
| Injury details | ✗ | ✓ |
| Coach feedback | ✗ | ✓ |
| Workout struggles | ✗ | ✓ |

### Output Format Example (v5.2 - ALL 4 Tabs Always Extracted, Last 10 Checkins)
```json
{
  "meta": {
    "extracted_at": "2025-03-27T15:30:00Z",
    "user": "Michal Szalinski",
    "user_id": "f848cd2b-43fa-417d-8686-5d15063b83eb",
    "version": "5.2",
    "extraction_version": "5.2",
    "trend_focus": "last_10_checkins",
    "data_categories": ["checkin", "nutrition_plan", "workout_program", "logs"]
  },
  "user_profile": {
    "package": "Men's Physique Mentorship 2024",
    "start_weight_kg": 85,
    "current_weight_kg": 76.6,
    "age": 54,
    "check_in_day": "Friday"
  },
  "checkins_complete": [
    {
      "checkin_id": "8525e176-6601-42f9-8d3c-ac4c9aaacb5e",
      "checkin_number": "29th",
      "date": "27 Mar, 2026",
      "tabs": {
        "checkin": {
          "qa_pairs": [
            {
              "question": "Waist Circumference (belly button height in cm)",
              "answer": "88",
              "source": "label"
            },
            {
              "question": "HUNGER levels (1 constantly full & bloated, 10 stomach always rumbling)",
              "answer": "5",
              "source": "label"
            }
          ]
        },
        "nutrition_plan": {
          "qa_pairs": [
            {
              "question": "How are you managing with the nutrition plan?",
              "answer": "Not on plan this week",
              "source": "label"
            },
            {
              "question": "How many litres of fluids (on average) are you consuming daily?",
              "answer": "4",
              "source": "label"
            }
          ]
        },
        "workout_program": {
          "qa_pairs": [
            {
              "question": "Bench Press",
              "answer": "4 sets x 8-10 reps @ 60kg",
              "source": "table"
            }
          ]
        },
        "logs": {
          "qa_pairs": [
            {
              "question": "Coach Notes",
              "answer": "Great week overall. Focus on elbow recovery.",
              "source": "text"
            }
          ]
        }
      }
    }
  ]
}
```

**IMPORTANT:** Each checkin should have ALL 4 tabs with qa_pairs arrays. If any tab shows
empty qa_pairs, re-run the extraction using the updated v5.2 script which uses multiple
fallback strategies to ensure complete data capture.

**v5.2 Enhancement:** Data is sorted by date (newest first) and limited to last 10 checkins
to enable meaningful trend analysis without full history extraction overhead.

## Troubleshooting

**v5.2 LOGIN FIX: Button click fails on Kahunas login**
→ Kahunas uses `input[type="submit"][name="signin"]` NOT a button element
→ Use: `page.locator('input[type="submit"][name="signin"]').click()`
→ Or: `page.evaluate("document.querySelector('input[type=submit][name=signin]').click()")`
→ Debug: list all inputs with `page.query_selector_all('input')` to see the actual form structure

**"web_auth_token not found"**
→ Make sure you're logged into the dashboard

**API returns 404**
→ Endpoints require browser session cookies
→ Use JavaScript method which includes credentials

**"Empty checkin list"**
→ Check if you're on the correct page (/dashboard)
→ Verify checkins exist in the "Latest check-ins" section

**Browser session expires during extraction**
→ The checkin detail pages require active session
→ Extract immediately after login or use browser console method

**Playwright not available in environment**
→ Use browser_* tools (browser_navigate, browser_click, browser_snapshot)
→ Or use the JavaScript console method which works in any browser

**WORKOUT_PROGRAM or LOGS tabs show empty qa_pairs**
→ This was a common issue in v5.0 - now fixed in v5.1
→ Re-run extraction with the updated script
→ The v5.1 scripts use MULTIPLE selector strategies as fallbacks
→ If issue persists:
   1. Check if those tabs exist on Kahunas for your account
   2. Some older checkins may not have workout/logs data
   3. Verify by manually clicking through the tabs on Kahunas

**Tabs not being clicked properly**
→ v5.2 now has 10+ fallback selectors per tab
→ If extraction still fails, Kahunas may have changed their UI
→ Report the issue with your browser console output

**JavaScript console injection fails (JS errors on page)**
→ If the page has JavaScript errors (e.g., "io is not defined", "Promise.allSettled is not a function")
→ The JavaScript console extraction method will NOT work
→ FALLBACK METHOD: Use browser_* tools for manual extraction:
   1. browser_navigate to checkin detail page
   2. browser_snapshot (full=true) to capture Checkin tab
   3. browser_click on Nutrition Plan tab → browser_snapshot
   4. browser_click on Workout Program tab → browser_snapshot
   5. browser_click on Log tab → browser_snapshot
   6. Manually parse the snapshot data into JSON
→ This was the method used successfully on 2026-03-30 when JS console method failed

---

## Next Steps: Analyze the Data

After extraction, use **kahunas-complete-coach** for comprehensive analysis:

```
Skill: kahunas-complete-coach
Purpose: Complete fitness analysis - personal optimization (ZOE/J3/RP) + professional coaching (17-step Clean Health)
Data Input: The JSON file generated by this extractor
Location: ~/.hermes/skills/fitness/kahunas-complete-coach/
```

### Quick Analysis Commands
```bash
# Complete unified analysis (both personal + professional)
python ~/.hermes/skills/fitness/kahunas-complete-coach/scripts/unified_orchestrator.py \
  --data your_extracted_data.json \
  --output-dir ./reports

# Personal optimization only (ZOE/J3/RP frameworks)
python ~/.hermes/skills/fitness/kahunas-complete-coach/scripts/analyze_checkins.py \
  --input your_extracted_data.json

# Professional client review only (Clean Health 17-step)
python ~/.hermes/skills/fitness/kahunas-complete-coach/scripts/client_analyzer.py \
  --input your_extracted_data.json
```
