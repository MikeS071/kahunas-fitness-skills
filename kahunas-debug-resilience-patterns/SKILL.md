---
name: kahunas-debug-resilience-patterns
description: Debugging and resilience patterns discovered while building the Kahunas.io workflow reliability layer. Documents cron environment quirks, AJAX login handling, Playwright cleanup, and Telegram notification gotchas.
version: 1.0.0
category: fitness
created: 2026-04-01
---

# Kahunas Workflow — Debugging & Resilience Patterns

## 1. Cron Environment Doesn't Inherit `.env` Variables

**Problem:** `notify_failure()` silently failed during cron runs because `TELEGRAM_BOT_TOKEN` and other vars were empty.

**Why:** Cron jobs start in a minimal environment — `.env` files are not auto-loaded.

**Fix:** Load `.env` at the top of `main()` before any other code:
```python
env_file = Path.home() / ".hermes/.env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                if key not in os.environ:
                    os.environ[key] = val
```

**Lesson:** Any script that depends on env vars and runs via cron must explicitly load `.env`.

---

## 2. Kahunas Login: Click + URL Polling + Network Idle

**Problem:** Login `wait_for_url('**/dashboard')` timed out even though the login eventually succeeded.

**Evidence:**
- Kahunas uses a JavaScript submit handler that POSTs to `/login` and the server responds with HTTP 303 redirect
- `wait_for_url()` can miss the redirect if it fires before navigation completes
- `web_auth_token` is NOT set immediately on dashboard load — it's fetched via a subsequent async network request

**Correct approach (v5.1+):**
```python
import time

# Step 1: Load login page and wait for form
page.goto('https://kahunas.io/login', wait_until='domcontentloaded', timeout=20000)
page.wait_for_selector('input[type="password"]', timeout=15000)

# Step 2: Fill credentials
page.fill('input[type="text"], input[type="email"]', email)
page.fill('input[type="password"]', password)

# Step 3: Click submit — Kahunas returns 303 redirect on success
page.click('input[type="submit"][name="signin"]')

# Step 4: Poll URL until dashboard reached (max 45s)
start = time.time()
while time.time() - start < 45:
    if 'dashboard' in page.url:
        break
    time.sleep(0.5)

# Step 5: CRITICAL — Wait for network to settle BEFORE reading token
# web_auth_token is set asynchronously by JS AFTER page load
page.wait_for_load_state('networkidle', timeout=15000)
page.wait_for_timeout(5000)  # Extra buffer for JS token initialization

# Step 6: Read token (check multiple sources)
token = page.evaluate("""
    () => window.web_auth_token
    || window.authToken
    || localStorage.getItem('web_auth_token')
    || sessionStorage.getItem('web_auth_token')
    || document.cookie.match(/web_auth_token=([^;]+)/)?.[1]
""")
if not token:
    raise ValueError("Dashboard loaded but web_auth_token is missing")
```

**Lesson:** The `fetch()` approach (page.evaluate with fetch()) does NOT work — it doesn't preserve browser session context properly. Use `page.click()` for form submission, poll for URL change, and critically wait for `networkidle` before reading auth tokens set by async JS.

---

## 3. Playwright Resources Must Be Cleaned Up Before Retry

**Problem:** After a Playwright timeout, retrying immediately caused `"Playwright Sync API inside the asyncio loop"` errors.

**Why:** The previous browser's event loop wasn't fully torn down before `retry_with_backoff()` called `login_and_get_token()` again, creating a sync/async conflict.

**Fix:** Always clean up in the except block before re-raising:
```python
try:
    # ... Playwright operations ...
except Exception:
    try:
        context.close()
    except: pass
    try:
        pw.stop()
    except: pass
    raise  # Re-raise AFTER cleanup so retry loop can create fresh instance
```

**Lesson:** Playwright's sync API holds onto event loop resources. A failed attempt must fully clean up before retrying.

---

## 4. Telegram HTML Requires Proper Escaping

**Problem:** `notify_failure()` sent `"HTTP 400: Bad Request"` — the HTML in the message was malformed.

**Why:** Strings like `</details>` (invalid HTML entity), unescaped `<` in URLs, and control characters in error messages.

**Fix:**
```python
import html

def notify_failure(summary, details="", coach_name="Unknown"):
    summary_esc = html.escape(summary[:200]) if summary else "Unknown error"
    details_esc = html.escape(details[:400]) if details else ""
    coach_esc = html.escape(coach_name)
    
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
```

Also add visibility in `send_telegram_message`:
```python
if not bot_token:
    print(f"[TELEGRAM] No bot token configured — skipping notification")
    return False
# ... on failure:
print(f"[TELEGRAM] Failed to send: {e}")
```

**Lesson:** Always use `html.escape()` on user/environment content in HTML messages. Add print statements for debugging since cron output goes to files, not stdout.

---

## 5. Email Bug: Sent Only On Failure Instead of On Success

**Problem:** Email reports were never being sent despite `--email` flag being passed.

**Root Cause:** The email sending code was in the `else` (report generation FAILED) branch instead of the `if` (success) branch:
```python
# WRONG — email only sent when report_file is None (failure)
if report_file:
    print(f"   {client_name}: {report_file.name}")
else:
    print(f"   {client_name}: FAILED")
    if args.email:
        send_report_email(...)  # Only runs on failure!
```

**Fix:** Move email sending into the `if report_file:` success branch:
```python
# CORRECT — email sent when report generated successfully
if report_file:
    print(f"   {client_name}: {report_file.name}")
    if args.email:
        send_report_email(report_file, client_name, recipient, checkin_date, smtp_cfg)
        print(f"      Email sent!")
else:
    print(f"   {client_name}: FAILED")
```

**Lesson:** When adding post-processing logic (email, notifications), always verify it's in the correct branch. Use a simple smoke test: run with `--email` and confirm email is sent on success.

---

## 6. Health Check vs Browser Access Are Different

**Problem:** `check_kahunas_health()` (curl) passed, but Playwright login timed out.

**Why:**
- `curl https://kahunas.io` → HTTP 200, ~1s
- Browser login → times out at 45s

This can happen because:
1. Cloudflare or WAF blocks bot traffic at the browser level but not curl
2. The `/login` page loads but POST to `/login` hangs
3. CDN handles GET but origin server for POST is struggling

**Implication:** A passing health check doesn't guarantee the full login flow will work. The retry logic is essential for this gap.

---

## 7. Resend SMTP Uses `user: "resend"`, Not an Email Address

**Problem:** SMTP login to Resend fails with `535 Invalid username` when using an email as the username.

**Root Cause:** Resend's SMTP API expects `user: "resend"` (the string literal "resend"), not `user: "navihermes@gmail.com"` or `user: "navi@archonhq.ai"`.

**Verification:**
```python
import smtplib
# FAILS
smtplib.SMTP('smtp.resend.com', 587).login('navihermes@gmail.com', 're_WndxHD1h_...')
# → 535 Invalid username

# WORKS
smtplib.SMTP('smtp.resend.com', 587).starttls().login('resend', 're_WndxHD1h_...')
# → Authentication successful
```

**Correct coach config SMTP settings:**
```json
"smtp": {
  "host": "smtp.resend.com",
  "port": 587,
  "user": "resend",
  "password": "re_WndxHD1h_ArVrgCCB344WUj3Jc2x47HGP",
  "from_email": "navi@archonhq.ai"
}
```

**Lesson:** Resend SMTP authentication uses a fixed username `"resend"`. The `from_email` (sender identity) and `user` (authentication) are different values. Always test SMTP credentials independently before running the full workflow.

---

### 8b. `from_email` Bug in `send_report_email`

**Problem:** Email was being sent with `From: resend` (invalid), causing potential rejection even when SMTP login succeeded.

**Root Cause:** `send_report_email` used:
```python
from_email = smtp_cfg.get('user', get_env_var('RESEND_FROM_EMAIL', 'navi@archonhq.ai'))
# smtp_cfg['user'] = "resend"  →  from_email became "resend" ❌
```

The `smtp_cfg['user']` value (`"resend"`) was being used for `From:` header, not the actual sender email. The fix:
```python
from_email = smtp_cfg.get('from_email', get_env_var('RESEND_FROM_EMAIL', 'navi@archonhq.ai'))
# Now correctly uses: "navi@archonhq.ai" ✅
```

**Also:** `send_report_email` used bare `except:` which silently swallowed all errors. Always add proper exception logging:
```python
except Exception as e:
    import traceback
    print(f"   SMTP Error: {e}")
    traceback.print_exc()
    return False
```

**Lesson:** When `smtp_cfg['user']` and the email sender identity are different values (Resend: user=`resend`, from=`navi@archonhq.ai`), ensure `from_email` is a separate config key. Always log SMTP errors — a successful login doesn't guarantee the `From:` header is valid.

---

## 8. Daily Mode: Future-Dated Checkins Break New-Checkin Detection

**Problem:** `--daily` mode reports "no new checkins" even though a new checkin was just submitted.

**Root Cause:** Kahunas sometimes stores checkin dates in the future. For example:
- Checkin date stored as: `"03 Apr, 2026"`
- Today's date: `"01 Apr, 2026"`
- User submits new checkin today → date would be `"01 Apr, 2026"`

The `has_new_checkin()` function compares `new_checkin_date > stored_date`:
```
01 Apr, 2026 > 03 Apr, 2026 → FALSE
```
So the new checkin is NOT detected as newer than the already-stored future checkin.

**Why Kahunas uses future dates:** Likely because the client's subscription or coaching cycle is dated ahead, or it's the intended review date, not submission date.

**Debug approach:**
```bash
# 1. Run without --daily to force full extraction
python scripts/multi_client_workflow.py --coach samantha --generate --email

# 2. Inspect actual checkin dates in the saved JSON
python3 -c "
import json
with open('kahunas_api_data/clients/client_Michal__Szalinski_xxx.json') as f:
    data = json.load(f)
for c in data['checkins_complete'][:3]:
    print(f'#{c.get(\"checkin_no\")} date={c.get(\"date\")} uuid={c.get(\"uuid\")[:8]}')
"

# 3. Check API directly (if you can get a token)
curl -s -X POST https://api.kahunas.io/api/v2/checkin/list \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_uuid":"<uuid>","per_page":5}' | jq '.data.checkins[] | {no:.checkin_no, date:.date, created:.created_at}'
```

**Workaround for future-date issue:**
- Option A: In `has_new_checkin()`, also compare `created_at` (timestamp) in addition to the display `date`
- Option B: Force full extraction periodically (e.g., weekly) instead of relying solely on date comparison
- Option C: Use the checkin `uuid` to detect new submissions — if a UUID isn't in the stored file, it's new

**Detection code that should work (using uuid):**
```python
def has_new_checkin(client_uuid: str, api_checkins: List[dict]) -> bool:
    latest_file = get_latest_client_file(client_uuid)
    if not latest_file:
        return True

    with open(latest_file) as f:
        stored = json.load(f)
    stored_uuids = {c['uuid'] for c in stored.get('checkins_complete', [])}

    for checkin in api_checkins:
        if checkin.get('uuid') not in stored_uuids:
            return True  # New UUID found
    return False
```

**Lesson:** Date-based comparison is fragile when the system being queried returns future dates. UUID-based new detection is more robust than date comparison.

**Why:** 
- `curl https://kahunas.io` → HTTP 200, ~1s
- Browser login → times out at 45s

This can happen because:
1. Cloudflare or WAF blocks bot traffic at the browser level but not curl
2. The `/login` page loads but POST to `/login` hangs
3. CDN handles GET but origin server for POST is struggling

**Implication:** A passing health check doesn't guarantee the full login flow will work. The retry logic is essential for this gap.

---

## Verification Checklist

When debugging this workflow:
- [ ] Check `coaches/<name>.json` has REAL credentials, not placeholders (`REPLACE_WITH_KEY` = broken)
- [ ] Resend SMTP `user` must be `"resend"` (NOT an email). Test: `smtplib.SMTP('smtp.resend.com',587).starttls().login('resend','pass')`
- [ ] Verify cron env has `.env` vars: run script manually first
- [ ] Test Telegram independently: `curl -X POST "https://api.telegram.org/botTOKEN/sendMessage" -d "chat_id=ID&text=Test"`
- [ ] Test login independently via Playwright before running full workflow
- [ ] Check `~/.hermes/cron/output/<job_id>/` for output files when cron fails silently
- [ ] Smoke test: run with `--email` flag and verify email is sent on SUCCESS (not just failure)
- [ ] After fixing login, verify `web_auth_token` is actually captured (check workflow output says "Token obtained")
- [ ] If daily mode says "no new checkins", manually inspect stored JSON dates — checkins may be future-dated
- [ ] Test SMTP credentials directly: `python3 -c "import smtplib; smtplib.SMTP('smtp.resend.com',587).starttls().login('resend','pass')"`
- [ ] Verify `from_email` is set separately from `user` in `send_report_email` — `user="resend"` is for auth, `from_email` must be the actual sender address (e.g. `navi@archonhq.ai`)
- [ ] Verify OpenRouter API key works: `curl https://openrouter.ai/api/v1/models -H "Authorization: Bearer $KEY"`
- [ ] For OpenRouter key: check `~/.hermes/.env` → `OPENROUTER_API_KEY` (not the placeholder in coach config)
