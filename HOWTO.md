# Kahunas Fitness Coaching — User Manual

This system automates the daily workflow for fitness coaching on [Kahunas.io](https://kahunas.io):
extract client check-in data, analyze it using evidence-based methodologies, generate personalized
reports, and deliver them by email — all on a schedule.

---

## Table of Contents

1. [How the System Works](#1-how-the-system-works)
2. [Prerequisites & Setup](#2-prerequisites--setup)
3. [Adding a New Coach](#3-adding-a-new-coach)
4. [Common Tasks](#4-common-tasks)
5. [Understanding the Data Flow](#5-understanding-the-data-flow)
6. [Interpreting the Report](#6-interpreting-the-report)
7. [Scheduling Automatic Runs](#7-scheduling-automatic-runs)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. How the System Works

The system consists of **3 skills** that work together:

| Skill | What It Does |
|-------|--------------|
| `kahunas-complete-coach` | Main workflow: extracts data, generates reports, sends emails |
| `kahunas-session-recovery` | Recovers from interrupted or failed extractions |
| `kahunas-debug-resilience-patterns` | Debugging guide for fixing problems |

### The Daily Cycle

```
Every morning at 10:30 AM (automated):
  1. Login to Kahunas.io as the coach
  2. Check each client's check-ins since yesterday
  3. Extract full data for clients with new check-ins
  4. Generate an LLM-powered personalized report for each client
  5. Email the report to the client
  6. If anything fails → Telegram notification
```

---

## 2. Prerequisites & Setup

### Required Accounts

- **Kahunas.io** — Coach account with API access
- **OpenRouter** — For LLM report generation ([openrouter.ai](https://openrouter.ai))
- **Resend** — For sending emails ([resend.com](https://resend.com))
- **Telegram** (optional) — For failure notifications

### Python Environment

All scripts run in a shared Python environment at:

```
~/venv-playwright/
```

This environment has Playwright installed (required for browser automation).

To install or update:
```bash
cd ~/venv-playwright
./bin/playwright install chromium
```

### Configuration File

Each coach has a **JSON config file** that stores all credentials in one place.

Location: `~/.hermes/skills/fitness/kahunas-complete-coach/coaches/<name>.json`

Template: `coaches/EXAMPLE.json`

Required fields:
```json
{
  "name": "Coach Name",
  "email": "coach@example.com",
  "kahunas": {
    "coach_email": "coach@kahunas.io",
    "coach_password": "your-password",
    "deactivated_clients": []
  },
  "report_recipient": "coach@example.com",
  "openrouter": {
    "api_key": "sk-or-..."
  },
  "smtp": {
    "host": "smtp.resend.com",
    "port": 587,
    "user": "resend",
    "password": "re_...",
    "from_email": "coach@your-domain.com"
  }
}
```

**Important:** The `user` field for Resend must always be the literal string `"resend"`.
The `from_email` is the actual sender email address — these are different values.

---

## 3. Adding a New Coach

### Step 1: Create the Config File

```bash
cd ~/.hermes/skills/fitness/kahunas-complete-coach/coaches
cp EXAMPLE.json mycoach.json
```

Edit `mycoach.json` and fill in:
- Kahunas credentials (coach email + password)
- OpenRouter API key
- Resend SMTP credentials
- `report_recipient` (who receives the reports)
- `deactivated_clients` (list of client emails to exclude)

### Step 2: Test the Setup

```bash
cd ~/.hermes/skills/fitness/kahunas-complete-coach

# Test extraction (no reports, no email — just data)
~/venv-playwright/bin/python3 scripts/kahunas_extract.py --coach mycoach
```

### Step 3: Run the Full Pipeline

```bash
~/venv-playwright/bin/python3 scripts/multi_client_workflow.py \
  --coach mycoach --daily --generate --email
```

---

## 4. Common Tasks

### A. Run the Daily Workflow (Extract + Report + Email)

```bash
cd ~/.hermes/skills/fitness/kahunas-complete-coach

~/venv-playwright/bin/python3 scripts/multi_client_workflow.py \
  --coach samantha --daily --generate --email
```

Flags:
| Flag | What It Does |
|------|-------------|
| `--coach samantha` | Load credentials from `coaches/samantha.json` |
| `--daily` | Only process clients who have new check-ins since yesterday |
| `--generate` | Generate LLM-powered reports after extraction |
| `--email` | Send reports via email to the client |

**Without `--daily`**: extracts data for ALL active clients.
**Without `--generate`**: extracts data but skips report generation.
**Without `--email`**: generates reports but doesn't send them.

### B. Extract Data Only (No Reports)

```bash
~/venv-playwright/bin/python3 scripts/kahunas_extract.py --coach samantha
```

This logs in, extracts all client data, and saves JSON files to `~/kahunas_api_data/clients/`.
It does NOT generate reports or send emails.

### C. Extract for Specific Client(s)

```bash
# One client (by partial UUID — can use just the first 8 characters)
~/venv-playwright/bin/python3 scripts/kahunas_extract.py \
  --coach samantha --clients 9b61b431

# Multiple clients
~/venv-playwright/bin/python3 scripts/kahunas_extract.py \
  --coach samantha --clients 9b61b431,a1b2c3d4
```

The partial UUID matching is flexible — `9b61b431` will match `9b61b431-a1b2-c3d4-e5f6`.

### D. Force Full Re-Extraction (Ignore Daily Mode)

```bash
# Extracts ALL active clients, ignoring when data was last extracted
~/venv-playwright/bin/python3 scripts/kahunas_extract.py --coach samantha
```

This is useful for:
- Periodic full refresh (e.g., weekly)
- Troubleshooting data quality issues
- After Kahunas changes their website structure

### E. Generate a Report from Existing Data

```bash
~/venv-playwright/bin/python3 scripts/generate_llm_report.py \
  --input ~/kahunas_api_data/clients/client_Michal_xxx.json \
  --output ~/kahunas_api_data/reports/Michal_Report.md
```

### F. Resend an Existing Report

```bash
~/venv-playwright/bin/python3 scripts/resend_report.py \
  --report ~/kahunas_api_data/reports/Michal_Report.md \
  --coach samantha \
  --recipient client@email.com
```

This is useful when:
- A report was generated but email delivery failed
- You need to resend to a different address
- A client asks for a re-send

### G. Recover from an Interrupted Extraction

If an extraction was interrupted (browser crashed, network dropped):

```bash
# Check what was already saved
ls -lt ~/kahunas_api_data/clients/

# Re-run — the system will detect and skip already-extracted clients
~/venv-playwright/bin/python3 scripts/kahunas_extract.py --coach samantha --daily
```

If data was partially saved and you need to merge:
```bash
cd ~/.hermes/skills/fitness/kahunas-session-recovery/scripts
python3 merge_extractions.py \
  --original ~/kahunas_api_data/clients/partial_file.json \
  --resume ~/kahunas_api_data/clients/resume_file.json \
  --output ~/kahunas_api_data/clients/merged_file.json
```

---

## 5. Understanding the Data Flow

```
kahunas_extract.py
  │
  ├── Login (Playwright browser automation)
  ├── Get client list (Kahunas API)
  ├── Determine active clients (has check-ins, not deactivated)
  │
  ├── For each active client:
  │   ├── Fetch check-in list (API)
  │   └── Scrape full Q&A data (Playwright):
  │       ├── Checkin tab (body metrics, ratings)
  │       ├── Nutrition Plan tab (compliance, diet notes)
  │       ├── Workout Program tab (exercises, sets, reps)
  │       └── Logs tab (coach/client notes)
  │
  └── Save to: ~/kahunas_api_data/clients/client_<Name>_<UUID>_<Date>.json

        │
        ▼ (if --generate)

generate_llm_report.py
  │
  ├── Load 17-step CHFI methodology
  ├── Pass all Q&A data to LLM (via OpenRouter API)
  ├── Generate 5-section personalized report
  └── Save to: ~/kahunas_api_data/reports/<Name>_LLM_<Date>.md

        │
        ▼ (if --email)

email_utils.py (via multi_client_workflow.py)
  │
  ├── Convert markdown report → HTML email
  └── Send via Resend SMTP API
```

### Where Data Is Stored

| Type | Location |
|------|----------|
| Extracted client data (JSON) | `~/kahunas_api_data/clients/` |
| Generated reports (Markdown) | `~/kahunas_api_data/reports/` |
| Workflow logs | `~/.hermes/cron/output/` |
| Coach configurations | `~/.hermes/skills/fitness/kahunas-complete-coach/coaches/` |

### File Naming Convention

```
client_<Name>_<UUID-short>_<Date>.json
client_Eleni_Philo_9b61b431_20260403.json

<Name>_LLM_<Date>.md
Eleni_Philo_LLM_20260403.md
```

---

## 6. Interpreting the Report

Each generated report has 5 sections:

### Section 1: Weight / Waist Change
- Current weight vs. start weight
- Weekly rate of change (should be ~0.5–1% per week)
- Trend assessment: on track, gaining, or stalled

### Section 2: Training Performance
- Motivation rating (7/10 or higher = good)
- Pump quality and session duration
- Exercise progression tracking
- **Plateau alert**: If the same weight/reps for 3+ weeks → "Video Review Request"

### Section 3: Fatigue / Recovery Status
- Stress and sleep markers
- Mobility and injury tracking
- Recovery between sets
- Immediate action items if recovery is poor

### Section 4: Nutrition & Adjustments
- Compliance percentage
- Alcohol, hydration, stimulants analysis
- Hunger timing (ZOE metabolic insights: early hunger = overnight glucose instability)
- Off-plan reasons explained

### Section 5: Goals for Next Week
- Prioritized action items (Urgent → Maintain)
- Specific measurable targets
- Based on the Clean Health 17-step review process

---

## 7. Scheduling Automatic Runs

### Daily at 10:30 AM (Recommended)

```bash
# Edit crontab
crontab -e

# Add this line:
30 10 * * * cd ~/.hermes/skills/fitness/kahunas-complete-coach && ~/venv-playwright/bin/python3 scripts/multi_client_workflow.py --coach samantha --daily --generate --email
```

This runs every day, processes only clients with new check-ins, generates reports, and emails them.

### Every Friday at 11 AM (Weekly Summary)

```bash
0 11 * * 5 cd ~/.hermes/skills/fitness/kahunas-complete-coach && ~/venv-playwright/bin/python3 scripts/resend_report.py --coach samantha --report $(ls -t ~/kahunas_api_data/reports/*<ClientName>*_LLM_*.md | head -1) --recipient client@email.com
```

### Checking Cron Output

When cron jobs run, their output goes to:
```
~/.hermes/cron/output/<job_id>/
```

If something fails, check the log files there.

---

## 8. Troubleshooting

### "Login failed" or "Token not found"

**Cause:** Kahunas credentials are wrong, or the login flow changed.

**Fix:**
1. Verify credentials in `coaches/<name>.json`
2. Try logging into Kahunas.io manually in a browser
3. If Kahunas changed their login page, the automation may need updating

---

### "No clients with new check-ins" (but there should be)

**Cause:** The system compares check-in dates. If Kahunas stores future-dated check-ins, the date comparison may not detect new ones.

**Fix:**
```bash
# Force full re-extraction
~/venv-playwright/bin/python3 scripts/kahunas_extract.py --coach samantha
```

---

### Report shows "0 kg" or missing data

**Cause:** The extraction ran but the Playwright scraping missed the data.

**Fix:**
1. Re-run extraction with: `--max-checkins 3` (default)
2. Check that the saved JSON files have Q&A pairs: look for `"qa_pairs": [...]` in the JSON
3. If empty, Kahunas may have changed their page structure

---

### Email not sent

**Cause:** Resend SMTP credentials are wrong, or `from_email` is misconfigured.

**Fix:**
1. Verify `smtp.user` is exactly `"resend"` (not an email address)
2. Verify `smtp.from_email` is the actual sender email address
3. Test SMTP directly:
   ```bash
   python3 -c "import smtplib; smtplib.SMTP('smtp.resend.com',587).starttls().login('resend','your-password')"
   ```

---

### LLM Report Generation Failed

**Cause:** OpenRouter API key is missing, expired, or invalid.

**Fix:**
1. Check `openrouter.api_key` in `coaches/<name>.json`
2. Verify the key at [openrouter.ai](https://openrouter.ai)
3. Check that you have credits on your OpenRouter account

---

### Extraction Times Out

**Cause:** Network issues, Kahunas is slow, or browser crashed.

**Fix:**
1. Try again — the system has automatic retry logic
2. Check `~/.hermes/cron/output/` for error logs
3. If it keeps happening, the system will send a Telegram notification

---

### Workflow Failed — Telegram Notification Not Received

**Cause:** Bot token or chat ID is wrong, or Telegram blocked the message.

**Fix:**
1. Test Telegram directly:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
     -d "chat_id=<CHAT_ID>&text=Test"
   ```
2. Check that the bot has been messaged by the user first (bots can't initiate Telegram chats)

---

### Playwright Browser Not Found

```bash
cd ~/venv-playwright
./bin/playwright install chromium
```

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Full daily workflow | `python3 scripts/multi_client_workflow.py --coach samantha --daily --generate --email` |
| Extract data only | `python3 scripts/kahunas_extract.py --coach samantha` |
| Specific client | `python3 scripts/kahunas_extract.py --coach samantha --clients 9b61b431` |
| Generate report | `python3 scripts/generate_llm_report.py --input <file>.json --output <file>.md` |
| Resend report | `python3 scripts/resend_report.py --coach samantha --report <file>.md --recipient email` |
| Recover session | `python3 scripts/merge_extractions.py --original <a>.json --resume <b>.json --output <out>.json` |
| Install browser | `cd ~/venv-playwright && ./bin/playwright install chromium` |

---

## Getting Help

If something isn't working:

1. **Run the command manually** with full output and check for error messages
2. **Check the logs** in `~/.hermes/cron/output/<job_id>/`
3. **Try a test extraction** with a single client: `--clients <uuid>`
4. **Verify credentials** in `coaches/<name>.json`
5. **Test APIs independently** (Kahunas login in browser, Resend SMTP, OpenRouter key)

For technical details on how the system works, see the skill documentation:
- `~/.hermes/skills/fitness/kahunas-complete-coach/SKILL.md`
- `~/.hermes/skills/fitness/kahunas-debug-resilience-patterns/SKILL.md`
- `~/.hermes/skills/fitness/kahunas-session-recovery/SKILL.md`
