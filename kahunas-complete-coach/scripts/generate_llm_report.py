#!/usr/bin/env python3
"""
LLM-Powered Personalized Report Generator v2.0
===============================================
Uses CHFI 17-step methodology + LLM to generate truly personalized
fitness coaching reports unique to each client's data.

This script ONLY generates markdown reports. Email sending and HTML conversion
is handled by email_utils.py.

Usage:
    python3 generate_llm_report.py --input <client_json> --output <report_md>
"""

import json
import argparse
import os
from datetime import datetime
from pathlib import Path

# ============================================================================
# CHFI 17-STEP METHODOLOGY KNOWLEDGE BASE
# ============================================================================

CHFI_KNOWLEDGE = """
## CHFI 17-STEP CLIENT REVIEW METHODOLOGY

### Target Values
- Body Composition: Fat loss = -1%/week, Growth = +0.5%/week, Maintenance = ±0.2%/week
- Sleep: 7-9 hours, quality ≥7/10, consistent bedtime ±30min
- Hydration: 1mL per calorie consumed (typically 3-4L/day)
- Protein: 2.2g per kg target bodyweight
- Training: 2x/week per muscle group, 6-8 sets per session
- Mobility: 7x/week (daily)

### Alert Priority System
🔴 URGENT (Immediate Action): Waist >1cm increase, Stress >7/10, Injury reported, Sleep <6hr
🟠 HIGH (This Week): Weight stable 2-3 weeks, Mobility <2x/week, Motivation <7/10, Compliance <80%
🟡 MEDIUM (Next Week): Steps <8000, Hydration <3L, Sleep quality 5-6/10
🟢 MAINTENANCE: On-target metrics, positive trends

### Fatigue Markers (3+ elevated = consider deload)
- RPE/stress level, Gym performance trend, Strength maintenance
- Muscle pump quality, Heart rate variability, Training motivation
- Mood stability, Appetite consistency, GI function
- Sleep quality, Illness/injury, Libido/menses

### Common Patterns & Root Causes
1. High Stress + Off-Plan Eating = Environmental trigger → Pre-plan meals for stress
2. Long Workouts + Low Motivation = Accumulating fatigue → Implement deload
3. Poor Sleep + High Hunger = Leptin/ghrelin disruption → Sleep hygiene + pre-bed protein
4. Weight Stable + High Stress = Cortisol water retention → Stress management focus
5. Early Morning Hunger (6am) = Overnight hypoglycemia → 25-30g casein before bed

### Training Modifications (3-week plateau)
1. Load increase 2.5-5%
2. Rep increase (add 1-2 reps)
3. Set increase (add 1 working set)
4. Rest reduction (10-15 seconds)

### Nutrition Adjustment Triggers
- Fat Loss Stall (2+ weeks): Reduce carbs 25-50g OR fats 10-15g
- Growth Stall (2+ weeks): Add 100-200 calories, increase carbs primarily

### Meal Timing (PNC2)
- Breakfast: Within 2 hours of waking
- Lunch: Before 1pm (ideally)
- Dinner: No later than 2 hours before bed
- 50% of calories 8+ hours before melatonin onset

### Injury Management Protocol
1. Reduce to pain-free range
2. Substitute pain-causing exercises
3. Increase volume on unaffected areas
4. Add rehab/prehab work
"""

SYSTEM_PROMPT = """You are an expert fitness coach using the Clean Health Fitness Institute (CHFI) 17-step methodology.

Generate a concise, punchy weekly fitness review for ONE client based ONLY on their actual data.

## STRICT Output Rules:
1. MAXIMUM 450 words total - be brutal about cutting fluff
2. Use clean markdown tables (max 4 columns)
3. Every sentence must reference specific client data or CHFI principles
4. No generic advice - must connect to THEIR numbers
5. Commentary is 2-3 sentences MAX per section

## Report Structure:

```
# WEEKLY FITNESS REVIEW
**Client:** [NAME] | **Checkin:** [DATE]

## 1. WEIGHT / WAIST
| Metric | Value | Target | Status |
[2-3 sentence analysis - cite THEIR numbers]

## 2. TRAINING & PROGRESSION
| Exercise | Status | Notes |
[Analyze: sessions completed, motivation, any plateaued exercises 3+ weeks,
strained exercises, progression trends. If no workout data - say so.]

## 3. FATIGUE / RECOVERY
[List key fatigue markers with 🔴/🟠/🟢 status]
**Key issue:** [One sentence - MAIN problem]
[1-2 sentence recommendation]

## 4. NUTRITION
| Metric | Current | Target |
[2-3 sentence analysis - cite THEIR actual foods]

## 5. GOALS FOR NEXT WEEK
🔴 [URGENT - max 2 items]
🟠 [HIGH - max 2 items]
🟢 [Keep doing - max 2 items]
```

## CHFI Training Progression Rules:
- **Plateau trigger:** Same weight/reps for 3+ weeks → increase load 2.5-5%, add 1-2 reps, or add 1 set
- **Fatigue signs:** Long workouts + low motivation + declining performance → deload
- **Injury protocol:** Reduce to pain-free range, substitute exercises, increase unaffected areas

## Priority Definitions:
🔴 URGENT: Injury, <6hr sleep, >7/10 stress, 0% compliance
🟠 HIGH: Plateau 3+ weeks, Motivation <7/10, Compliance <80%
🟢 MAINTENANCE: On track, positive trends

Generate now. Be concise. Be specific. Be useful.
"""


def load_data(filepath):
    """Load JSON data from file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def extract_qa_text(checkins, max_checkins=3):
    """Extract Q&A pairs from last N checkins as readable text."""
    lines = []
    for i, checkin in enumerate(checkins[:max_checkins]):
        checkin_num = checkin.get('checkin_no', i+1)
        date = checkin.get('date', 'Unknown date')
        lines.append(f"\n=== CHECKIN #{checkin_num} ({date}) ===\n")

        # Get tabs
        tabs = checkin.get('tabs', {})

        # Checkin Q&A
        checkin_qa = tabs.get('checkin', {}).get('qa_pairs', [])
        if checkin_qa:
            lines.append("\n--- CHECKIN RESPONSES ---\n")
            for qa in checkin_qa:
                q = qa.get('question', '').strip()
                a = qa.get('answer', '').strip()
                if q and a and len(a) < 500:
                    lines.append(f"Q: {q}\nA: {a}\n")

        # Workout program exercises (parse from raw_text)
        workout_raw = tabs.get('workout_program', {}).get('raw_text', '')
        if workout_raw and ('Sets:' in workout_raw or 'Reps:' in workout_raw):
            lines.append("\n--- WORKOUT PROGRAM ---\n")
            # Parse exercise blocks
            current_exercise = None
            for line in workout_raw.split('\n'):
                line = line.strip()
                # Exercise name line (no label, just the name)
                if line and not line.startswith(('A:', 'B:', 'C:', 'D:', 'E:', 'F:', 'Sets:', 'Reps:', 'RIR:', 'REST:', 'Notes:', 'Time:', 'Heart', 'Workout')):
                    if len(line) > 3 and len(line) < 60:
                        current_exercise = line
                        lines.append(f"\nExercise: {line}\n")
                elif line.startswith('Sets:'):
                    sets = line.replace('Sets:', '').strip()
                    lines.append(f"  Sets: {sets}\n")
                elif line.startswith('Reps:'):
                    reps = line.replace('Reps:', '').strip()
                    lines.append(f"  Reps: {reps}\n")
                elif line.startswith('RIR:'):
                    rir = line.replace('RIR:', '').strip()
                    if rir:
                        lines.append(f"  RIR: {rir}\n")

        # Logs
        logs_qa = tabs.get('logs', {}).get('qa_pairs', [])
        if logs_qa:
            lines.append("\n--- LOGS ---\n")
            for qa in logs_qa:
                q = qa.get('question', '').strip()
                a = qa.get('answer', '').strip()
                if q and a and len(a) < 500:
                    lines.append(f"Q: {q}\nA: {a}\n")

    return ''.join(lines)


def load_env():
    """Load .env file if present (for cron job context)."""
    env_file = Path.home() / ".hermes/.env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    import os
                    if key not in os.environ:
                        os.environ[key] = val

def call_llm(prompt, model="anthropic/claude-opus-4.6"):
    """Call OpenRouter API for LLM analysis."""
    import urllib.request
    
    # Load .env for cron context (env vars may not be inherited from parent process)
    load_env()
    
    api_key=os.environ.get('OPENROUTER_API_KEY', '')
    if not api_key:
        return "[LLM unavailable: No API key]"
    
    endpoint = "https://openrouter.ai/api/v1/chat/completions"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1500
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'HTTP-Referer': 'https://hermes.ai',
                'X-Title': 'Fitness Report Generator'
            }
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            choices = result.get('choices', [])
            if choices:
                return choices[0].get('message', {}).get('content', '')
            return "[LLM: No response content]"
    except Exception as e:
        return f"[LLM call failed: {e}]"


def generate_personalized_report(data, client_name_override=None):
    """Generate a truly personalized report using LLM analysis."""
    
    meta = data.get('meta', {})
    user_profile = data.get('user_profile', {})
    checkins = data.get('checkins_complete', [])
    
    client_name = client_name_override or user_profile.get('name', meta.get('client_name', 'Client'))
    start_weight = user_profile.get('start_weight_kg', 0)
    current_weight = user_profile.get('current_weight_kg', 0)
    
    # Extract Q&A context
    qa_context = extract_qa_text(checkins)
    
    # Build the full prompt with client data
    prompt = f"""## CLIENT DATA
Name: {client_name}
Start Weight: {start_weight}kg
Current Weight: {current_weight}kg
Checkin Count: {meta.get('checkin_count', len(checkins))}

## CLIENT Q&A DATA (from recent checkins)
{qa_context}

## CHFI KNOWLEDGE BASE
{CHFI_KNOWLEDGE}

Now generate the personalized weekly fitness review report for {client_name}.
"""
    
    # Call LLM for analysis
    print("Analyzing client data with LLM...")
    llm_report = call_llm(prompt)
    
    if llm_report.startswith("[LLM call failed"):
        # Fallback to basic structure with extracted data
        print("LLM unavailable, generating with extracted data...")
        return generate_fallback_report(data, client_name)
    
    return llm_report


def generate_fallback_report(data, client_name):
    """Generate a basic report when LLM is unavailable."""
    meta = data.get('meta', {})
    user_profile = data.get('user_profile', {})
    checkins = data.get('checkins_complete', [])
    
    start_weight = user_profile.get('start_weight_kg', 0)
    current_weight = user_profile.get('current_weight_kg', 0)
    weight_change = current_weight - start_weight
    
    # Extract key info from first checkin
    first_checkin = checkins[0] if checkins else {}
    tabs = first_checkin.get('tabs', {})
    checkin_qa = tabs.get('checkin', {}).get('qa_pairs', [])
    
    # Parse key values
    motivation = "Not reported"
    stress = "Not reported"
    sleep = "Not reported"
    injury = "None reported"
    compliance = "Not reported"
    
    for qa in checkin_qa:
        q = qa.get('question', '').lower()
        a = qa.get('answer', '').strip()
        if 'motivat' in q:
            motivation = a
        elif 'stress' in q:
            stress = a
        elif 'sleep' in q:
            sleep = a
        elif 'injury' in q or 'hurt' in q or 'pain' in q:
            if a and a != '-':
                injury = a
    
    report = f"""# WEEKLY FITNESS REVIEW
**Client:** {client_name} | **Checkin:** {first_checkin.get('date', datetime.now().strftime('%d %b, %Y'))} | **Generated:** {datetime.now().strftime('%Y-%m-%d')}

## 1. WEIGHT / WAIST CHANGE

| Metric | Value |
|--------|-------|
| Current Weight | {current_weight} kg |
| Start Weight | {start_weight} kg |
| Total Change | {weight_change:+.1f} kg |

**Analysis:** {"Weight loss" if weight_change < 0 else "Weight gain" if weight_change > 0 else "Weight maintained"} of {abs(weight_change):.1f}kg.

## 2. TRAINING PERFORMANCE

| Metric | Status |
|--------|--------|
| Motivation | {motivation} |
| Sessions Completed | {len(checkins)} checkins |

## 3. FATIGUE / RECOVERY STATUS

| Metric | Value |
|--------|-------|
| Stress | {stress} |
| Sleep | {sleep} |
| Injury Status | {injury} |

## 4. NUTRITION & ADJUSTMENTS

Compliance information pending detailed review.

## 5. GOALS FOR NEXT WEEK

- Review training program based on current status
- Monitor recovery and adjust intensity accordingly

---
*Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Generate LLM-powered personalized fitness report (markdown only - no email sending)"
    )
    parser.add_argument('--input', '-i', required=True, help='Input JSON data file')
    parser.add_argument('--output', '-o', help='Output markdown file')
    parser.add_argument('--client', '-c', help='Client name override')
    parser.add_argument('--no-llm', action='store_true', help='Skip LLM, use fallback')
    
    args = parser.parse_args()
    
    print(f"Loading data from: {args.input}")
    data = load_data(args.input)
    
    client_name = args.client or data.get('user_profile', {}).get('name', 'Client')
    
    print(f"Generating personalized report for {client_name}...")
    
    if args.no_llm:
        report = generate_fallback_report(data, client_name)
    else:
        report = generate_personalized_report(data, args.client)
    
    # Save output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(report)
        print(f"Report saved to: {output_path}")
    else:
        # Print to console if no output file specified
        print("\n" + "="*60)
        print(report)
        print("="*60)


if __name__ == '__main__':
    main()
