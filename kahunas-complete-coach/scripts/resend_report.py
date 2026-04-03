#!/usr/bin/env python3
"""
Resend an existing markdown report via email.
Uses email_utils for HTML conversion and Resend API delivery.

Usage:
    python3 resend_report.py --report <report.md> --coach <coach_name>
    python3 resend_report.py --report <report.md> --coach <coach_name> --recipient <email>

Options:
    --report      Path to the existing .md report file
    --coach       Coach config name (looks for coaches/<coach_name>.json)
    --recipient   Override email recipient (default: from coach config)
    --checkin-date Override checkin date (default: extracted from report or today)
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

# Add scripts dir to path for email_utils import
import sys
SKILL_DIR = Path.home() / ".hermes/skills/fitness/kahunas-complete-coach"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import email_utils


def load_coach_config(coach_name: str) -> dict:
    """Load coach configuration from coaches/<name>.json"""
    coach_file = SKILL_DIR / "coaches" / f"{coach_name}.json"
    if not coach_file.exists():
        print(f"ERROR: Coach config not found: {coach_file}")
        print(f"Available configs in: {coach_file.parent}")
        return None
    with open(coach_file) as f:
        return json.load(f)


def extract_client_name(report_md: str) -> str:
    """Extract client name from report markdown."""
    match = re.search(r'\*\*Client:\*\*\s*(.+?)(?:\s*\|)', report_md)
    if match:
        return match.group(1).strip()
    return "Client"


def extract_checkin_date(report_md: str) -> str:
    """Extract checkin date from report markdown."""
    match = re.search(r'\*\*Checkin:\*\*\s*(.+?)(?:\s*\*)|\*\*Check-in:\*\*\s*(.+?)(?:\s*\|)', report_md)
    if match:
        return (match.group(1) or match.group(2)).strip()
    # Fallback: try to find any date-like string
    match = re.search(r'(\d{1,2}\s+\w+,?\s+\d{4})', report_md)
    if match:
        return match.group(1)
    return datetime.now().strftime('%d %b, %Y')


def main():
    parser = argparse.ArgumentParser(
        description="Resend an existing markdown fitness report via email"
    )
    parser.add_argument('--report', '-r', required=True, help='Path to the .md report file')
    parser.add_argument('--coach', '-c', required=True, help='Coach config name (e.g., samantha)')
    parser.add_argument('--recipient', help='Override email recipient')
    parser.add_argument('--checkin-date', help='Override checkin date for email header')
    parser.add_argument('--client-name', help='Override client name for email header')
    
    args = parser.parse_args()
    
    # Validate report file
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"ERROR: Report file not found: {report_path}")
        return 1
    
    # Load the report
    with open(report_path) as f:
        report_md = f.read()
    
    # Extract metadata from report
    client_name = args.client_name or extract_client_name(report_md)
    checkin_date = args.checkin_date or extract_checkin_date(report_md)
    
    # Load coach config
    coach_config = load_coach_config(args.coach)
    if not coach_config:
        return 1
    
    # Determine recipient
    recipient = args.recipient or coach_config.get('report_recipient')
    if not recipient:
        print("ERROR: No recipient specified and no report_recipient in coach config")
        return 1
    
    # Get SMTP/Resend config
    smtp_cfg = coach_config.get('smtp', {})
    coach_name = coach_config.get('name', 'Your Coach')
    
    print(f"Resending report:")
    print(f"  Client: {client_name}")
    print(f"  Checkin: {checkin_date}")
    print(f"  Recipient: {recipient}")
    print(f"  Report: {report_path}")
    print()
    
    # Send the email
    success, msg = email_utils.send_email(
        report_md_path=str(report_path),
        client_name=client_name,
        recipient=recipient,
        checkin_date=checkin_date,
        coach_name=coach_name,
        smtp_cfg=smtp_cfg
    )
    
    if success:
        print(f"✅ {msg}")
        return 0
    else:
        print(f"❌ {msg}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
