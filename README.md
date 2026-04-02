# Kahunas Fitness Skills

Automation skills for [Kahunas.io](https://kahunas.io) fitness coaching platform. These skills power a daily pipeline that extracts client check-in data, generates personalized LLM coaching reports, and emails them to coaches.

## Skills

| Skill | Description |
|-------|-------------|
| `kahunas-complete-coach` | Main orchestrator — logs into Kahunas, fetches all clients, scrapes Q&A details, generates LLM reports via OpenRouter, sends HTML emails via Resend. Uses CHFI 17-step methodology. |
| `kahunas-data-extractor` | API + Playwright scraping hybrid for extracting check-in data from Kahunas.io. Handles pagination, token auth, and detail page scraping. |
| `kahunas-session-recovery` | Resume interrupted extraction sessions by replaying checkpointed client UUIDs and re-fetching failed pages. |
| `kahunas-debug-resilience-patterns` | Debugging patterns and resilience techniques for the Kahunas.io platform (playwright, API, session recovery). |

## Architecture

```
kahunas-complete-coach/
├── coaches/          # Per-coach JSON configs (credentials, deactivated clients)
├── scripts/
│   ├── multi_client_workflow.py   # Main orchestrator
│   ├── generate_llm_report.py     # LLM report generation
│   ├── email_utils.py             # Resend API + mistune HTML conversion
│   └── resend_report.py           # Utility to resend existing .md reports
├── source_materials/  # CHFI methodology docs, reference materials
├── examples/          # Sample inputs/outputs
└── HOWTO.md          # Setup and usage guide
```

## Quick Start

See `kahunas-complete-coach/HOWTO.md` for full setup instructions.

TL;DR:
```bash
# Daily pipeline
python scripts/multi_client_workflow.py --coach samantha --daily --generate --email

# Resend a report
python scripts/resend_report.py --coach samantha --report <path-to.md>
```

## Configuration

Each coach has a `coaches/<name>.json` config file containing:
- Kahunas credentials
- OpenRouter API key
- Resend API key (in `smtp.password` field)
- Deactivated client email list

No credentials are hardcoded — everything read from the coach config.
