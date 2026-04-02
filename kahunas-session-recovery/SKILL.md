---
name: kahunas-session-recovery
description: Resume interrupted Kahunas.io extraction sessions - handles browser crashes, session timeouts, and partial extractions. Companion to kahunas-data-extractor for long running extractions.
version: 1.0.0
trigger:
  - When Kahunas browser session closes during extraction
  - When extraction is interrupted and needs to resume
  - When partial JSON data exists and needs completing
  - When user wants to continue from last successful checkin
---

## Overview

When extracting all checkins from Kahunas.io, the browser session may close unexpectedly (session timeout, network issues, tab crash). This skill provides recovery procedures to resume from where extraction left off.

## Quick Recovery

```bash
# 1. Check what was already extracted
cat your_partial_file.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
checkins = data.get('checkins_complete', [])
print(f'Already extracted: {len(checkins)} checkins')
if checkins:
    last = checkins[-1]
    print(f'Last: {last.get(\"number\")} - {last.get(\"date\")}')
"

# 2. Re-open browser and go to Kahunas dashboard
# 3. Run resume script (see below)
# 4. Merge with: python merge_extractions.py --original partial.json --resume resume.json
```

## Determining Where Extraction Stopped

Check the `tabs` object in the last checkin of your partial file:

| tabs.checkin.qa_pairs | tabs.nutrition_plan.qa_pairs | tabs.workout_program.qa_pairs | tabs.logs.qa_pairs | Status |
|-----------------------|------------------------------|-------------------------------|--------------------| -------|
| has data | empty | empty | empty | Stopped at Nutrition tab |
| empty | empty | empty | empty | Stopped before tabs started |
| has data | has data | empty | empty | Stopped at Workout tab |
| has data | has data | has data | has data | **Complete!** |

## Resume Script (Browser Console)

```javascript
// Kahunas RESUME Script
// 1. Go to https://kahunas.io/dashboard
// 2. Open console (F12)
// 3. Set START_INDEX to resume point (0 = all, 5 = skip first 5)
// 4. Paste and press Enter

const START_INDEX = 0; // CHANGE THIS to resume point

const checkins = [];
document.querySelectorAll('a[href*="/checkin/view/"]').forEach(link => {
    const match = link.href.match(/\/checkin\/view\/([a-f0-9-]+)/i);
    if (match) {
        const row = link.closest('tr');
        const cells = row ? row.querySelectorAll('td') : [];
        checkins.push({
            id: match[1],
            number: link.textContent.trim(),
            day: cells[1]?.textContent?.trim() || '',
            date: cells[2]?.textContent?.trim() || '',
            url: link.href
        });
    }
});

console.log(`Found ${checkins.length} total checkins`);
console.log(`Will process from index ${START_INDEX} onwards`);

const toProcess = checkins.slice(START_INDEX);

(async () => {
    const results = [];
    for (let i = 0; i < toProcess.length; i++) {
        console.log(`[${i+1}/${toProcess.length}] Processing ${toProcess[i].number}...`);
        
        window.location.href = toProcess[i].url;
        await new Promise(r => setTimeout(r, 3000));
        
        // Extract Q&A from current tab
        const qaPairs = [];
        document.querySelectorAll('table tr').forEach(row => {
            const cells = row.querySelectorAll('td, th');
            if (cells.length >= 2) {
                const question = cells[0].textContent.trim();
                const answer = cells[1].textContent.trim();
                if (question && answer && question.length > 3) {
                    qaPairs.push({ question, answer });
                }
            }
        });
        
        results.push({
            id: toProcess[i].id,
            number: toProcess[i].number,
            date: toProcess[i].date,
            qa_pairs: qaPairs,
            extracted_tabs: ['checkin'] // Add more tabs if needed
        });
        
        await new Promise(r => setTimeout(r, 1500));
    }
    
    const blob = new Blob([JSON.stringify(results, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kahunas_resume_${Date.now()}.json`;
    a.click();
    
    console.log(`✓ Extracted ${results.length} checkins`);
    window.kahunasResumeData = results;
})();
```

## Merge Script

Save as `merge_extractions.py`:

```python
#!/usr/bin/env python3
"""Merge partial and resume Kahunas extractions"""
import json
from datetime import datetime

def merge_extractions(original_file, resume_file, output_file):
    with open(original_file) as f:
        original = json.load(f)
    
    with open(resume_file) as f:
        resume = json.load(f)
    
    existing_ids = {c.get('checkin_id') or c.get('id') 
                   for c in original.get('checkins_complete', [])}
    
    new_checkins = [c for c in resume 
                   if (c.get('checkin_id') or c.get('id')) not in existing_ids]
    
    original['checkins_complete'].extend(new_checkins)
    
    original['meta']['resumed_at'] = original['meta'].get('extracted_at')
    original['meta']['extracted_at'] = datetime.now().isoformat()
    original['meta']['resumed_count'] = len(new_checkins)
    
    with open(output_file, 'w') as f:
        json.dump(original, f, indent=2)
    
    print(f"✓ Added {len(new_checkins)} new checkins")
    print(f"✓ Total: {len(original['checkins_complete'])} checkins")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', required=True, help='Partial extraction JSON')
    parser.add_argument('--resume', required=True, help='Resume extraction JSON')
    parser.add_argument('--output', default='kahunas_merged.json')
    args = parser.parse_args()
    merge_extractions(args.original, args.resume, args.output)
```

Usage:
```bash
python3 merge_extractions.py \
    --original kahunas_partial.json \
    --resume kahunas_resume_123456.json \
    --output kahunas_complete.json
```

## Session Management Tips

**Preventive:**
- Set MAX_CHECKINS to 10-15 per batch
- Save intermediate JSON every 5 checkins
- Keep browser console open to monitor progress
- Avoid switching to other tabs/windows

**If Session Closes:**
1. Note the last successfully processed checkin number
2. Calculate START_INDEX (e.g., if last was #25, set START_INDEX = 24)
3. Re-run extraction from that point
4. Merge the results

## Error States

| Error | Cause | Recovery |
|-------|-------|----------|
| "Target page, context or browser has been closed" | Browser crashed | Re-navigate, resume from previous checkin |
| Empty checkin list (0 found) | Session expired | Re-login to Kahunas |
| All qa_pairs empty | Wrong page/tab | Navigate to correct checkin detail page |

## Related Skills

- `kahunas-data-extractor` - Primary extraction skill
- `kahunas-fitness-analyzer` - Analyze the complete data
- `kahunas-client-analyzer` - Comprehensive client analysis
