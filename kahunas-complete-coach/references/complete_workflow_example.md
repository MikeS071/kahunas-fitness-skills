# Complete Workflow Example - Kahunas Client Analyzer

## Overview

This example demonstrates the complete 3-phase workflow for analyzing a client's checkin data
using the Clean Health Fitness Institute 17-step review process.

## Prerequisites

1. Kahunas.io access (dashboard login)
2. Client checkin data (can be extracted via kahunas-data-extractor)
3. Python 3.7+ installed

---

## Phase 1: Extract All Checkin Data

### Option A: Using the extraction script
```bash
# Run the full extraction to get all checkins
python /home/hermes/kahunas_full_extractor.py

# Or use the browser console script
# 1. Open https://kahunas.io/dashboard
# 3. Copy/paste kahunas_full_extractor.js
# 4. Press Enter
# 5. Download the generated JSON file
```

**Output:** Single JSON file with all checkins, photos, nutrition, training, and logs data.

---

## Phase 2: Run the Complete Analysis

### Using the workflow orchestrator:
```bash
# Complete workflow (Extract → Analyze → Recommend)
cd /home/hermes/.hermes/skills/fitness/kahunas-client-analyzer
python scripts/workflow_orchestrator.py \
  --data-file /home/hermes/kahunas_final_extraction_20250327.json \
  --output-dir ./reports
```

**Expected Output:**
```
================================================================================
PHASE 1: EXTRACTING DATA FROM KAHUNAS
================================================================================
✓ Data file found: kahunas_final_extraction_20250327.json

================================================================================
PHASE 2: RUNNING 17-STEP ANALYSIS
================================================================================
Running 17-step review process...
----------------------------------------
[1-2] Photo comparison & visual assessment...
[3] Menstrual cycle assessment...
[4] Waist circumference comparison...
[5] Rate of weight change...
[6] Sleep assessment...
[7] Stress markers...
[8] Daily consistency (steps, hydration)...
✓ Steps 1-8 complete

✓ Analysis saved: ./reports/analysis_20250327_174501.md

================================================================================
PHASE 3: GENERATING WEEKLY RECOMMENDATIONS
================================================================================
✓ Recommendations saved: ./reports/recommendations_20250327_174501.md
✓ Action items saved: ./reports/action_items_20250327_174501.json

================================================================================
WORKFLOW COMPLETE
================================================================================

Output files:
  📊 Analysis: ./reports/analysis_20250327_174501.md
  🎯 Recommendations: ./reports/recommendations_20250327_174501.md
  ✅ Action Items: ./reports/action_items_20250327_174501.json
```

---

## Phase 3: Example Analysis Output
## Phase 3: Example Analysis Output

### Sample Output for Michal Szalinski

```markdown
# WEEKLY FITNESS REVIEW
**Client:** Michal Szalinski | **Checkin:** 27 Mar, 2026 | **Generated:** 2026-03-30

## 1. WEIGHT / WAIST CHANGE

| Metric | Value |
|--------|-------|
| Current Weight | 76.6 kg |
| Start Weight | 85 kg |
| Total Change | 8.4 kg |
| Weekly Rate | 0.27 kg/week |
| Waist Circumference | 88.0 cm |

**Interpretation:** Weight loss of 8.4kg (0.27/week). ⚠️ Slower than target - review calories.

## 2. TRAINING PERFORMANCE

| Metric | Status |
|--------|--------|
| Motivation | 8/10 ✅ High |
| Workouts Longer | ⚠️ Yes |
| Pump Quality | Good Pumps |

**Hardest Workout:** Tennis elbow reduced strength in arm exercises
**Easiest Workout:** All - reduced weights for elbows

### Exercise Progression Review
*Requires workout_program tab extraction with weight/rep history*

## 3. FATIGUE / RECOVERY STATUS

| Metric | Value | Assessment |
|--------|-------|------------|
| Stress | 4/10 | ✅ Low |
| Recovery Between Sets | ⚠️ No |
| Sleep Quality | Not logged | - |
| Mobility Sessions | 1/week | ⚠️ Below target (7) |

🚨 **INJURY STATUS:** Both arms have tennis elbow issues. Need to go see a doctor.

**Immediate Actions Required:**
1. Schedule GP appointment this week
2. Switch to lower body specialization (6-8 weeks)
3. Begin daily forearm mobility routine (3x10min/day)

## 4. NUTRITION & ADJUSTMENTS

| Metric | Value |
|--------|-------|
| Compliance | Not on plan this week |
| Alcohol | None |
| Hydration | 4.0L |
| Caffeine | 3-4 coffees |
| Gastric Distress | ✅ None |
| Hunger Timing | 6am |

**Metabolic Health Notes:**
- Early morning hunger (6am) → add 20-30g slow-digesting protein before bed
- Hydration at 4L - excellent
- 3-4 coffees/day - consider caffeine cutoff at 2pm

## 5. GOALS FOR NEXT WEEK

### 🚨 URGENT (This Week)
- [ ] **Schedule GP appointment for bilateral tennis elbow** (This week)
- [ ] **Switch to lower body specialization (6-8 weeks)** (Immediately)
- [ ] **Begin daily forearm mobility routine (3x10min/day)** (Immediately)

### 🟠 HIGH Priority
- [ ] **Pre-plan work event meals (protein-first strategy)** (Next 2 weeks)
- [ ] **Add 20-30g casein/Greek yogurt 1 hour before bed** (This week)
- [ ] **Increase mobility to daily 10-min block** (This week)

### 🟡 Medium Priority
- [ ] Set caffeine cutoff at 2pm, consider reducing to 2-3 coffees
- [ ] Improve meal tracking compliance to 90%+

### 🟢 Maintain
- [ ] Continue alcohol abstinence
- [ ] Continue 4L daily hydration

### Targets for Next Checkin

| Area | Target | How to Measure |
|------|--------|----------------|
| Medical | GP appt booked | Appointment confirmed |
| Mobility | 7x/week (daily 10min) | Daily log |
| Nutrition tracking | 90%+ compliance | % meals logged |
| Pre-bed protein | 20-30g casein | Nightly compliance |
| Caffeine cutoff | None after 2pm | Afternoon monitoring |
| Waist | Maintain or reduce | Weekly measurement |

---
*Analysis: Clean Health 17-Step + ZOE/J3/RP frameworks*
```

- [ ] Compare side pose: waist tightness, posture
- [ ] Compare back pose: lat width, back definition
- [ ] Note lighting direction and intensity changes

### Step 3: Menstrual Cycle Assessment
**Applicable:** False

### Step 4: Waist Circumference
- **Current:** 88.0 cm
- **Previous:** 88.0 cm  
- **Change:** 0.0 cm (stable)

### Step 5: Rate of Weight Change
- **Current:** 76.6 kg
- **Trend:** Maintenance/stable phase

### Step 6: Sleep Assessment
- **Hours:** 7.0
- **Rating:** 7/10
- **Assessment:** ✓ Good quantity and quality

### Step 7: Stress Assessment
- **Rating:** 4/10
- **Assessment:** ✓ Low stress week

### Step 8: Daily Consistency
- **Steps:** 8,500 / 10,000 (85%)
- **Hydration:** 4.0 L (excellent)

---

## 🎯 Recommendations Summary

**High Priority:**
1. Schedule GP appointment for chronic tennis elbow
2. Switch to lower body specialization
3. Increase mobility to daily 10min

**Medium Priority:**
4. Pre-plan meals for work events
5. Increase steps to 10,000 daily

**Maintenance:**
6. Continue 4L daily hydration
7. Maintain alcohol abstinence
```

---

## Using Individual Components

```python
# Python API for custom analysis
from scripts.client_analyzer import ClientAnalyzer
import json

# Load data
with open('kahunas_data.json') as f:
    data = json.load(f)

# Initialize analyzer
analyzer = ClientAnalyzer(data, client_name="Michal Szalinski")

# Run specific steps
visual = analyzer.step_1_2_photo_visual_assessment()
waist = analyzer.step_4_waist_comparison()
stress = analyzer.step_7_stress_assessment()

# Access results
print(f"Waist change: {waist['change_cm']}cm")
print(f"Stress level: {stress['stress_rating']}/10")
```

---

## Files Generated

After running the complete workflow:

```
./reports/
├── analysis_YYYYMMDD_HHMMSS.md      # Full 17-step analysis
├── recommendations_YYYYMMDD_HHMMSS.md  # Weekly recommendations  
└── action_items_YYYYMMDD_HHMMSS.json   # Structured actions
```

---

## Methodology Credits

Based on official Clean Health Fitness Institute curriculum:
- 17-Step Review Process
- Fatigue-Recovery-Adaptation
- Performance Nutrition Coach Levels 1-3
- Performance Personal Trainer Levels 1-2

Copyright © CHFI IP Holdings Pty Ltd 2020-2021
