# Kahunas Data Extractor - HOWTO

Self-contained skill for extracting complete fitness checkin data from Kahunas.io.

## Quick Start

```bash
cd ~/.hermes/skills/fitness/kahunas-data-extractor
./venv-playwright/bin/python3 scripts/kahunas_api_extractor.py
```

This will:
1. Launch a headless browser and log into Kahunas.io
2. Extract the last 10 checkins using hybrid API + Playwright
3. Scrape all Q&A data from all 4 tabs (Checkin, Nutrition, Workout, Logs)
4. Save to `~/kahunas_api_data/kahunas_hybrid_YYYYMMDD_HHMMSS.json`

## Prerequisites

- Python 3.8+
- Playwright browser (included in venv)
- Kahunas.io login credentials

Credentials are read from `~/.hermes/.env`:
```
KAHUNAS_EMAIL=email
KAHUNAS_PASSWORD=password
```

## What Gets Extracted

### Data from API (fast)
- Checkin list (dates, numbers, UUIDs)
- Basic metrics (waist, fluids, hunger, appetite, stress, motivation, etc.)

### Data from Web Scraping (detailed)
- Start/Current weight (from page header)
- Full Q&A pairs from all tabs:
  - **Checkin Tab**: Waist, injuries, ratings, heart rate
  - **Nutrition Tab**: Compliance, untracked meals, alcohol, hydration, stimulants, hunger timing
  - **Workout Tab**: Exercises, sets, reps, weights
  - **Logs Tab**: Coach notes, client comments

## Output

```
kahunas_api_data/
  kahunas_hybrid_20260330_162059.json   # Raw extracted data
  reports/                               # Generated reports
    weekly_report_27Mar2026_client.md
```

## Report Generation

After extraction, generate a report:

```bash
cd ~/.hermes/skills/fitness/kahunas-complete-coach/scripts
python3 generate_full_report.py --input ~/kahunas_api_data/kahunas_hybrid_latest.json
```

## Troubleshooting

### "Playwright browser not found"
```bash
cd ~/.hermes/skills/fitness/kahunas-data-extractor/venv-playwright
./bin/playwright install chromium
```

### Login fails
- Check credentials in `~/.hermes/.env`
- Kahunas may have changed login flow - browser automation may need updating

### Extraction is slow
- Normal: ~2-3 minutes for 10 checkins
- Each checkin requires 4 tab clicks + page loads

## File Structure

```
kahunas-data-extractor/
├── scripts/
│   └── kahunas_api_extractor.py   # Main extraction script (v6.2)
├── venv-playwright/                # Self-contained Python environment
├── SKILL.md                        # Technical documentation
└── HOWTO.md                        # This file
```
