# Kahunas Fitness Coaching Automation

A production-ready automation pipeline for [Kahunas.io](https://kahunas.io) fitness coaching platform. Extract client check-in data, analyze trends using evidence-based methodologies (ZOE, J3 University, RP Strength, Clean Health Fitness Institute), generate personalized coaching reports, and deliver them via email.

## Overview

This repository contains **3 interconnected skills** that power a complete daily workflow:

| Skill | Purpose | Key Capabilities |
|-------|---------|------------------|
| **[kahunas-complete-coach](kahunas-complete-coach/)** | Main orchestrator | Multi-client workflow, LLM-powered report generation, HTML email delivery via Resend, CHFI 17-step methodology |
| **[kahunas-session-recovery](kahunas-session-recovery/)** | Resilience | Resume interrupted extractions, merge partial files, checkpoint recovery |
| **[kahunas-debug-resilience-patterns](kahunas-debug-resilience-patterns/)** | Debugging | Cron environment fixes, AJAX login patterns, Playwright cleanup, Telegram notifications |

## Quick Start

```bash
# Navigate to the skill you need
cd kahunas-complete-coach

# Run daily pipeline for a coach
python scripts/multi_client_workflow.py --coach samantha --daily --generate --email

# Or extract only (no report generation)
python scripts/kahunas_extract.py --coach samantha --daily

# Resend an existing report
python scripts/resend_report.py --coach samantha --report /path/to/report.md
```

## Architecture

```
kahunas-fitness-skills/
├── kahunas-complete-coach/         # Main orchestrator & reporting
│   ├── coaches/                     # Per-coach JSON configs (credentials)
│   ├── scripts/                     # Workflow scripts
│   │   ├── multi_client_workflow.py    # Full pipeline (extract + report + email)
│   │   ├── kahunas_extract.py           # Extraction module (shared logic)
│   │   ├── generate_llm_report.py      # LLM-powered report generation
│   │   ├── email_utils.py              # Resend API integration
│   │   └── resend_report.py             # Utility to resend reports
│   ├── source_materials/            # CHFI methodology docs
│   ├── references/                  # Quick reference guides
│   └── HOWTO.md                     # Setup & usage guide
│
├── kahunas-session-recovery/        # Recovery procedures
│   └── scripts/
│       └── merge_extractions.py    # Merge partial extractions
│
└── kahunas-debug-resilience-patterns/  # Debugging knowledge base
    └── SKILL.md                     # Patterns & solutions
```

## Python Environment

All scripts require Playwright. The shared Python environment is at:

```
~/venv-playwright/
```

This environment is shared across all skills and must have Playwright installed:

```bash
~/venv-playwright/bin/playwright install chromium
```

## Key Features

### Complete Data Extraction
- **All 4 Kahunas tabs** captured: Checkin, Nutrition Plan, Workout Program, Logs
- **Hybrid approach**: Fast API for metadata, Playwright for detailed Q&A
- **Multi-client support**: Handles all coach clients with broken web pagination

### Evidence-Based Analysis
- **ZOE**: Metabolic health tracking (gut health, food responses, glucose patterns)
- **J3 University**: Physique coaching methodology
- **RP Strength**: Training periodization and progression tracking
- **Clean Health Fitness Institute (CHFI)**: 17-step professional client review process

### Intelligent Reporting
- **LLM-powered**: Generates personalized weekly recommendations via OpenRouter
- **5-section structure**: Weight/Waist, Training Performance, Fatigue/Recovery, Nutrition, Goals
- **Plateau detection**: Identifies 3+ week stagnation in exercises → triggers video review requests
- **Injury prioritization**: Auto-flags injuries and suggests medical consultations

### Automated Delivery
- **HTML emails** via Resend API
- **Per-client reports** with personalized content
- **Telegram notifications** for workflow failures

## Prerequisites

- Python 3.8+
- Playwright (`~/venv-playwright/bin/pip install playwright && ~/venv-playwright/bin/playwright install chromium`)
- Kahunas.io account with API access
- [OpenRouter](https://openrouter.ai) API key (for LLM reports)
- [Resend](https://resend.com) API key (for email delivery)

## Configuration

Each coach has a `coaches/<name>.json` config file containing:
- Kahunas credentials (email/password)
- OpenRouter API key
- Resend API key (in `smtp.password` field)
- Deactivated/excluded client list

**No credentials are hardcoded** — all configuration read from per-coach JSON files.

## Data Privacy

Sensitive coach configuration files (containing credentials) are excluded from version control:

```gitignore
coaches/*.json
!coaches/EXAMPLE.json
```

## Support

- **Report generation & extraction**: See `kahunas-complete-coach/HOWTO.md`
- **Session recovery**: See `kahunas-session-recovery/SKILL.md`
- **Debugging**: See `kahunas-debug-resilience-patterns/SKILL.md`

---

Built with [Hermes Agent](https://github.com/nickarora/hermes-agent) — CLI AI agent framework.
