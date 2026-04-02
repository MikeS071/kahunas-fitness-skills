# Kahunas Fitness Coaching Automation

A production-ready automation pipeline for [Kahunas.io](https://kahunas.io) fitness coaching platform. Extract client check-in data, analyze trends using evidence-based methodologies (ZOE, J3 University, RP Strength, Clean Health Fitness Institute), generate personalized coaching reports, and deliver them via email.

## Overview

This repository contains **4 interconnected skills** that power a complete daily workflow:

| Skill | Purpose | Key Capabilities |
|-------|---------|------------------|
| **[kahunas-complete-coach](kahunas-complete-coach/)** | Main orchestrator | Multi-client workflow, LLM-powered report generation, HTML email delivery via Resend, CHFI 17-step methodology |
| **[kahunas-data-extractor](kahunas-data-extractor/)** | Data extraction | Hybrid API + Playwright scraping, extracts all 4 tabs (Checkin, Nutrition Plan, Workout Program, Logs), pagination handling |
| **[kahunas-session-recovery](kahunas-session-recovery/)** | Resilience | Resume interrupted extractions, merge partial files, checkpoint recovery |
| **[kahunas-debug-resilience-patterns](kahunas-debug-resilience-patterns/)** | Debugging | Cron environment fixes, AJAX login patterns, Playwright cleanup, Telegram notifications |

## Quick Start

```bash
# Navigate to the skill you need
cd kahunas-complete-coach

# Run daily pipeline for a coach
python scripts/multi_client_workflow.py --coach samantha --daily --generate --email

# Resend an existing report
python scripts/resend_report.py --coach samantha --report /path/to/report.md
```

See individual skill `HOWTO.md` files for detailed setup instructions.

## Architecture

```
kahunas-fitness-skills/
├── kahunas-complete-coach/         # Main orchestrator & reporting
│   ├── coaches/                     # Per-coach JSON configs (credentials)
│   ├── scripts/                     # Workflow orchestration
│   │   ├── multi_client_workflow.py    # Main entry point
│   │   ├── generate_llm_report.py      # LLM-powered report generation
│   │   ├── email_utils.py              # Resend API integration
│   │   └── resend_report.py             # Utility to resend reports
│   ├── source_materials/            # CHFI methodology docs
│   ├── references/                  # Quick reference guides
│   └── HOWTO.md                     # Setup & usage guide
│
├── kahunas-data-extractor/          # Data extraction layer
│   ├── scripts/
│   │   ├── kahunas_api_extractor.py         # API-based extraction
│   │   ├── kahunas_comprehensive_extractor.py  # Playwright tab scraping
│   │   └── kahunas_multi_client_extractor.py  # Multi-client support
│   └── HOWTO.md                     # Extraction guide
│
├── kahunas-session-recovery/        # Recovery procedures
│   └── scripts/
│       └── merge_extractions.py    # Merge partial extractions
│
└── kahunas-debug-resilience-patterns/  # Debugging knowledge base
    └── SKILL.md                     # Patterns & solutions
```

## Key Features

### Complete Data Extraction
- **All 4 Kahunas tabs** captured: Checkin, Nutrition Plan, Workout Program, Logs
- **Hybrid approach**: Fast API for metadata, Playwright for detailed Q&A
- **Pagination handled**: Automatically finds and processes all pages

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
- Playwright (`pip install playwright && playwright install`)
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

- **Extraction issues**: See `kahunas-data-extractor/HOWTO.md`
- **Report generation**: See `kahunas-complete-coach/HOWTO.md`
- **Session recovery**: See `kahunas-session-recovery/SKILL.md`
- **Debugging**: See `kahunas-debug-resilience-patterns/SKILL.md`

---

Built with [Hermes Agent](https://github.com/nickarora/hermes-agent) — CLI AI agent framework.