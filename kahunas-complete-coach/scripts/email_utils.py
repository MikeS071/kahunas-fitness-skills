#!/usr/bin/env python3
"""
Email utilities for Kahunas Complete Coach.
Single source of truth for markdown → HTML conversion and email sending.

Uses:
- mistune for robust markdown → HTML conversion
- Resend API for reliable email delivery
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

import mistune
import requests


def markdown_to_html(md_text: str) -> str:
    """
    Convert markdown to HTML using mistune.
    
    Args:
        md_text: Raw markdown string
        
    Returns:
        HTML string with proper table/list/header formatting
    """
    md = mistune.create_markdown(
        plugins=[
            'mistune.plugins.table.table',
            'mistune.plugins.formatting.strikethrough',
        ]
    )
    
    # Convert markdown to HTML
    html = md(md_text)
    
    # Post-process: wrap bare table cells in proper styling
    html = _post_process_html(html)
    
    return html


def _post_process_html(html: str) -> str:
    """
    Post-process mistune output for email-friendly formatting.
    Adds inline styles to tables and ensures email client compatibility.
    """
    # Add table wrapper styles
    html = re.sub(
        r'<table>',
        '<table style="border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px;">',
        html
    )
    
    # Style table headers
    def style_th(match):
        return f'<th style="border: 1px solid #ddd; padding: 8px 10px; text-align: left; background: #f8f8f8; font-weight: bold;">{match.group(1)}</th>'
    html = re.sub(r'<th>(.*?)</th>', style_th, html)
    
    # Style table cells
    def style_td(match):
        content = match.group(1)
        # Don't double-wrap if already processed
        if 'style=' in content:
            return match.group(0)
        return f'<td style="border: 1px solid #ddd; padding: 6px 10px;">{content}</td>'
    html = re.sub(r'<td>(.*?)</td>', style_td, html)
    
    # Style headers
    html = re.sub(
        r'<h2>(.*?)</h2>',
        r'<h2 style="color: #222; font-size: 16px; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin-top: 20px;">\1</h2>',
        html
    )
    html = re.sub(
        r'<h3>(.*?)</h3>',
        r'<h3 style="color: #444; font-size: 14px; margin-top: 14px;">\1</h3>',
        html
    )
    
    # Style horizontal rules
    html = re.sub(
        r'<hr>',
        r'<hr style="border: none; border-top: 1px solid #eee; margin: 16px 0;">',
        html
    )
    
    # Style paragraphs
    html = re.sub(
        r'<p>(.*?)</p>',
        r'<p style="margin: 8px 0; line-height: 1.5;">\1</p>',
        html
    )
    
    # Style lists
    html = re.sub(
        r'<ul>',
        '<ul style="margin: 8px 0; padding-left: 20px;">',
        html
    )
    html = re.sub(
        r'<li>(.*?)</li>',
        r'<li style="margin: 4px 0;">\1</li>',
        html
    )
    
    return html


def build_html_email(
    html_body: str,
    client_name: str,
    checkin_date: str,
    coach_name: str = "Your Coach"
) -> str:
    """
    Wrap HTML body in complete email template.
    
    Args:
        html_body: The converted HTML content (just the report body)
        client_name: Client's name for the header
        checkin_date: Check-in date string
        coach_name: Coach's name for the footer
        
    Returns:
        Complete HTML email ready to send
    """
    html_email = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 650px; margin: 0 auto; padding: 20px; background: #fff;">
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 24px; border-radius: 12px 12px 0 0;">
        <h1 style="margin: 0; font-size: 22px;">Weekly Fitness Review</h1>
        <p style="margin: 8px 0 0; opacity: 0.9; font-size: 14px;">{client_name} | Check-in {checkin_date}</p>
    </div>
    <div style="background: #fff; padding: 24px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 12px 12px;">
        {html_body}
    </div>
    <div style="text-align: center; padding: 16px; color: #888; font-size: 12px;">
        Generated {datetime.now().strftime('%d %b, %Y')} | CHFI 17-Step Framework | Coach: {coach_name}
    </div>
</body>
</html>"""
    return html_email


def build_plain_text(report_md: str) -> str:
    """
    Convert markdown to plain text for email.
    
    Args:
        report_md: Raw markdown string
        
    Returns:
        Plain text version with markdown stripped
    """
    # Remove bold markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', report_md)
    # Remove headers markers
    text = re.sub(r'^#{1,6} ', '', text, flags=re.MULTILINE)
    # Clean up HR
    text = re.sub(r'^---$', '', text, flags=re.MULTILINE)
    return text.strip()


def send_email(
    report_md_path: str,
    client_name: str,
    recipient: str,
    checkin_date: str,
    coach_name: str = "Your Coach",
    smtp_cfg: dict = None
) -> tuple[bool, str]:
    """
    Send a fitness report as a properly formatted HTML email.
    
    This is the main entry point for email sending. It:
    1. Loads the markdown report from disk
    2. Converts markdown → HTML using mistune
    3. Wraps in email template
    4. Sends via Resend API
    
    Args:
        report_md_path: Path to the .md report file
        client_name: Client's name for personalization
        recipient: Email address to send to
        checkin_date: Check-in date string for the email header
        coach_name: Coach's name for the email footer
        smtp_cfg: SMTP/Resend configuration dict with keys:
            - api_key: Resend API key (or password for SMTP auth)
            - host: SMTP host (unused for API, kept for compat)
            - port: SMTP port (unused for API, kept for compat)
            - user: SMTP user (unused for API, kept for compat)
            - from_email: Sender email address
            
    Returns:
        Tuple of (success: bool, message: str)
    """
    if smtp_cfg is None:
        smtp_cfg = {}
    
    # Load the markdown report
    try:
        report_md_path = Path(report_md_path)
        with open(report_md_path) as f:
            report_md = f.read()
    except FileNotFoundError:
        return False, f"Report file not found: {report_md_path}"
    except Exception as e:
        return False, f"Failed to read report file: {e}"
    
    # Convert markdown to HTML
    try:
        html_body = markdown_to_html(report_md)
    except Exception as e:
        return False, f"Failed to convert markdown to HTML: {e}"
    
    # Validate HTML conversion worked
    if '<table' not in html_body and '<h2' not in html_body:
        return False, f"HTML conversion produced no table or header tags - conversion may have failed"
    
    # Build full email HTML
    html_email = build_html_email(html_body, client_name, checkin_date, coach_name)
    
    # Build plain text version
    plain_text = build_plain_text(report_md)
    
    # Get Resend configuration
    api_key = smtp_cfg.get('password') or smtp_cfg.get('api_key') or os.environ.get('RESEND_API_KEY', '')
    from_email = smtp_cfg.get('from_email') or os.environ.get('RESEND_FROM_EMAIL', 'navi@archonhq.ai')
    
    if not api_key:
        return False, "Resend API key not configured"
    
    # Send via Resend API
    subject = f"Your Weekly Fitness Review - {client_name}"
    
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'from': from_email,
                'to': [recipient],
                'subject': subject,
                'html': html_email,
                'text': plain_text,
            },
            timeout=30,
        )
        
        if response.status_code == 200 or response.status_code == 201:
            return True, f"Email sent to {recipient}"
        else:
            error_detail = response.json().get('message', response.text)
            return False, f"Resend API error ({response.status_code}): {error_detail}"
            
    except requests.exceptions.Timeout:
        return False, "Resend API request timed out"
    except requests.exceptions.RequestException as e:
        return False, f"Resend API request failed: {e}"


def get_env_var(key: str, default: str = "") -> str:
    """Get environment variable with optional default."""
    return os.environ.get(key, default)
