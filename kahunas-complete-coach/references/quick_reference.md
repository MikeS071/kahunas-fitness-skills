# Quick Reference - Kahunas Client Analyzer

## 17-Step Review Process At-A-Glance

| Step | Name | Key Metric | Alert Threshold | Action if Triggered |
|------|------|------------|-----------------|---------------------|
| 1 | Photo Comparison | Visual changes | Manual review required | Compare to previous week |
| 2 | Visual Assessment | Body fat, fluid, tone | >2% visual change | Adjust nutrition |
| 3 | Cycle Phase | N/A | Luteal phase | Expect water retention |
| 4 | Waist | cm | >1cm increase | Review calories, stress, alcohol |
| 5 | Weight Change | %/week | Off target by >0.5% | Adjust calories |
| 6 | Sleep | Hours + Quality | <7 hours or <7/10 | Sleep hygiene protocol |
| 7 | Stress | 1-10 rating | >7/10 | Stress management priority |
| 8 | Consistency | Steps, hydration | <80% target | Set daily reminders |
| 9 | Calendar | Sessions/wk | <planned sessions | Review barriers |
| 10 | Performance | Volume trend | Plateau 3+ weeks | Increase load/volume |
| 11 | Program Changes | 6-week block | Current week 6 | Assess modifications |
| 12 | Nutrition | Stable 2-3 wks | Weight unchanged | Adjust calories 5-10% |
| 13 | Post-Diet | 6-wk stabilization | Just finished cut | Maintain, don't increase |
| 14 | Subjective | Hunger, mood | Significant changes | Address root cause |
| 15 | Goal Review | Completion % | <80% completion | Reassess goals |
| 16 | Modifications | Training/diet | Action needed | Implement changes |
| 17 | Repeat | All checkins | Multiple clients | Systematic review |

## Target Values by Phase

### Body Composition
- **Fat Loss:** -1% bodyweight per week
- **Growth:** +0.5% bodyweight per week
- **Maintenance:** ±0.2% bodyweight

### Sleep
- **Quantity:** 7-9 hours
- **Quality:** ≥7/10
- **Consistency:** Same bedtime ±30min

### Daily Metrics
- **Steps:** 10,000 (unless specified otherwise)
- **Hydration:** 1mL per calorie consumed
- **Protein:** 2.2g per kg target bodyweight

### Training
- **Frequency:** 2x/week per muscle group
- **Volume:** 6-8 sets per muscle per session
- **Rest:** 3-4min compound, 90sec isolation

## Alert Priority System

### 🔴 URGENT (Immediate Action)
- Waist increase >1cm
- Stress >7/10
- Injury reported
- Sleep <6 hours

### 🟠 HIGH (This Week)
- Weight stable 2-3 weeks
- Mobility <2x/week
- Motivation <7/10
- Compliance <80%

### 🟡 MEDIUM (Next Week)
- Steps <8,000
- Hydration <3L
- Minor technique issues
- Sleep quality 5-6/10

### 🟢 MAINTENANCE
- On-target metrics
- Positive trends
- Good compliance

## Common Patterns & Solutions

### Pattern: High Stress + Off-Plan Eating
**Interpretation:** Environmental trigger, not willpower
**Solution:** Pre-plan meals for stressful periods

### Pattern: Long Workouts + Low Motivation
**Interpretation:** Accumulating fatigue (overreaching)
**Solution:** Implement deload week

### Pattern: Poor Sleep + High Hunger
**Interpretation:** Leptin/ghrelin disruption
**Solution:** Sleep hygiene protocol + pre-bed protein

### Pattern: Weight Stable + High Stress
**Interpretation:** Cortisol-induced water retention
**Solution:** Focus on stress management, not calorie cuts

### Pattern: Early Hunger (6am)
**Interpretation:** Overnight hypoglycemia
**Solution:** 25-30g casein protein before bed

## Fatigue Markers Checklist

Assess these weekly:
- [ ] RPE/stress level
- [ ] Gym performance trend
- [ ] Strength maintenance
- [ ] Muscle pump quality
- [ ] Heart rate variability
- [ ] Training motivation
- [ ] Mood stability
- [ ] Appetite consistency
- [ ] GI function
- [ ] Sleep quality
- [ ] Illness/injury
- [ ] Libido/menses

**3+ markers elevated = Consider deload**

## Meal Timing Guidelines

### Optimal (From PNC2)
- **Breakfast:** Within 2 hours of waking
- **Lunch:** Before 1pm (max before 3pm)
- **Dinner:** No later than 2 hours before bed
- **Calorie distribution:** 50% of calories 8+ hours before melatonin onset

### Pre-Workout
- **2-3 hours before:** 500-600mL water
- **10-20 min before:** 200-300mL water

## Common Modifications

### Training Plateau (>3 weeks)
1. Load increase 2.5-5%
2. Rep increase (add 1-2 reps)
3. Set increase (add 1 working set)
4. Rest reduction (10-15 seconds)

### Nutrition Adjustment
**Fat Loss Stall (2+ weeks):**
- Reduce carbs by 25-50g OR
- Reduce fats by 10-15g

**Growth Stall (2+ weeks):**
- Add 100-200 calories
- Increase carbs primarily

### Injury Management
1. Reduce to pain-free range
2. Substitute pain-causing exercises
3. Increase volume on unaffected areas
4. Add rehab prehab work

## Command Quick Reference

```bash
# Run complete workflow
python workflow_orchestrator.py --data-file data.json

# Run only analysis (skip extraction)
python workflow_orchestrator.py --data-file data.json --skip-extract

# Run analysis + recommendations
python workflow_orchestrator.py --data-file data.json --skip-recommend

# Python API
from client_analyzer import ClientAnalyzer
analyzer = ClientAnalyzer(data)
analysis = analyzer.run_17_step_process()
```

## File Locations

```
~/.hermes/skills/fitness/kahunas-client-analyzer/
├── SKILL.md                      # Full documentation
├── scripts/
│   ├── client_analyzer.py        # 17-step analysis engine
│   └── workflow_orchestrator.py  # Complete workflow
└── references/
    ├── textbook_sources.md       # CHFI methodology
    ├── complete_workflow_example.md  # Usage examples
    └── quick_reference.md        # This file
```

## Support

For questions on methodology:
- Review SKILL.md for full documentation
- Check examples in references/
- Refer to original CHFI textbooks in fitness_materials/
