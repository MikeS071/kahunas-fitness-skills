# Kahunas Complete Coach - HOWTO

Self-contained skill for analyzing Kahunas.io checkin data and generating actionable weekly fitness reports using LLM-powered personalization.

## Quick Start

```bash
# Run daily workflow for a coach (extracts new checkins, generates reports, sends emails)
cd ~/.hermes/skills/fitness/kahunas-complete-coach
python3 scripts/multi_client_workflow.py --coach samantha --daily --generate --email
```

## Prerequisites

1. Create a coach config file: `coaches/<coach_name>.json`
2. See `coaches/EXAMPLE.json` for the template

## File Structure

```
kahunas-complete-coach/
├── coaches/                       # Coach configurations (one per coach)
│   ├── samantha.json             # Example: Samantha Selvam's config
│   └── EXAMPLE.json              # Template for new coaches
├── scripts/
│   ├── multi_client_workflow.py  # Main orchestrator (v5.0+)
│   └── generate_llm_report.py    # LLM-powered report generator
├── source_materials/              # Clean Health PDFs
├── references/                     # Supporting docs
├── SKILL.md                       # Technical documentation
└── HOWTO.md                       # This file
```

## Coach Configuration

Each coach has their own JSON config in `coaches/`. This contains:
- Kahunas credentials
- OpenRouter API key
- SMTP settings
- Report recipient
- Deactivated clients list

See `coaches/EXAMPLE.json` for the full template.

## Usage

### Single Coach Daily Workflow
```bash
python3 scripts/multi_client_workflow.py --coach samantha --daily --generate --email
```

Flags:
- `--coach <name>` - Load config from `coaches/<name>.json`
- `--daily` - Only process clients with new checkins since last run
- `--generate` - Generate LLM reports after extraction
- `--email` - Send reports via email

### Generate Report Only
```bash
python3 scripts/generate_llm_report.py \
  --input ~/kahunas_api_data/clients/client_Michal_xxx.json \
  --output ~/kahunas_api_data/reports/Michal_LLM.md \
  --checkin-date "31 Mar, 2026"
```

## What the Report Contains

The 5-section executive summary:

### 1. Weight / Waist Change
- Current weight, start weight, total change
- Weekly rate of change
- Trend assessment

### 2. Training Performance
- Motivation, pump quality, session duration
- Exercise progression tracking
- Plateau detection (3+ weeks = video review request)

### 3. Fatigue / Recovery Status
- Stress, sleep, mobility
- Injury tracking (with duration calculation)
- Recovery between sets assessment
- Immediate action items

### 4. Nutrition & Adjustments
- Compliance status
- Alcohol, hydration, stimulants
- Gastric distress
- Hunger timing analysis (ZOE metabolic insights)
- Off-plan reason processing

### 5. Goals for Next Week
- Prioritized action items (Urgent → Maintain)
- Targets with measurement criteria
- Based on Clean Health 17-step process

## Frameworks Used

- **ZOE**: Metabolic health insights (blood sugar, gut health, overnight hypoglycemia detection)
- **J3 University**: Training periodization, MEV/MRV, specialization cycles
- **RP Strength**: Evidence-based tracking, consistency over perfection
- **Clean Health 17-Step**: Professional client review protocol

## Adding a New Coach

1. Copy `coaches/EXAMPLE.json` to `coaches/<name>.json`
2. Fill in all credentials (Kahunas, OpenRouter, SMTP)
3. Run: `python3 scripts/multi_client_workflow.py --coach <name> --daily --generate --email`

## Cron Automation

```bash
# 10:30 AM daily - check for new checkins, generate and email reports
30 10 * * * cd ~/.hermes/skills/fitness/kahunas-complete-coach && python3 scripts/multi_client_workflow.py --coach samantha --daily --generate --email
```

## Data Requirements

The report generator expects JSON with:
- `checkins_complete[]`: Array of checkin objects
- `meta`: Extraction metadata (client name, UUID, timestamp)
- Each checkin has `tabs.checkin.qa_pairs`: Q&A array

## Packaging

To package this skill for a new Hermes instance:
1. Copy the entire `kahunas-complete-coach/` directory
2. Create `coaches/<name>.json` files with valid credentials
3. No external .env changes needed - all config is self-contained

## Troubleshooting

### Report shows "0 kg" for weight
- Ensure extraction ran with Playwright (not API-only)
- Weight comes from page DOM, not API

### Missing data sections
- Check extraction completed all checkins
- Verify Q&A pairs were captured (should see "21 Q&A pairs" per checkin)
- Ensure all 4 tabs were scraped
