---
name: kahunas-complete-coach
description: Complete fitness analysis and coaching system combining personal optimization (ZOE/J3/RP Strength frameworks) with professional client coaching (Clean Health Fitness Institute 17-step process). Analyzes Kahunas.io checkin data for trends, correlations, metabolic health, training periodization, and generates actionable weekly recommendations.
version: 5.0.0

critical_discovery:
  api_vs_scrape: |
    CRITICAL: The Kahunas API (/api/v2/checkin/list) only returns `fields: [{label, value}]` 
    format - NOT the full Q&A pairs needed for report generation. To get qa_pairs, you MUST
    scrape the checkin detail page: https://kahunas.io/client/checkin/view/{uuid}
    
    The API returns basic checkin metadata but the actual question/answer text lives in the 
    DOM of the detail page. Use Playwright to scrape:
    - Checkin tab Q&A: Extract from DOM
    - Nutrition Plan tab: Click tab, then scrape
    - Workout Program tab: Click tab, then scrape  
    - Logs tab: Click tab, then scrape
    
    Also parse workout_program.raw_text for exercise details (Sets, Reps, RIR values).

  name_parsing_bug: |
    CRITICAL: Do NOT parse client names from raw_text page content. The first line of 
    many checkin pages is "1" (a page element), not the client name.
    
    CORRECT: Always use the API-provided values:
    - client['name'] from /api/v2/coach/clients endpoint
    - client['email'] from the same endpoint
    
    This bug affected ALL 19 client files and required patching.

  extraction_speed: |
    Multi-client extraction times out at ~600s. Set MAX_CHECKINS_PER_CLIENT=3 to complete
    in ~5 minutes. More checkins = longer extraction. 3 is sufficient for trend analysis.

  llm_report_generator: |
    The LLM-powered generate_llm_report.py:
    1. Loads CHFI 17-step methodology as knowledge base
    2. Passes ALL Q&A data to LLM (OpenRouter API)
    3. Produces truly personalized, client-specific reports
    4. Includes training progression analysis and plateau detection
    5. Enforces 450-word limit with concise formatting

  ajax_login: |
    CRITICAL (v5.1+): Kahunas login works via standard form POST with HTTP 303 redirect.
    The web_auth_token is set asynchronously AFTER dashboard loads — waiting for networkidle is MANDATORY.
    
    CORRECT approach (v5.1+):
    1. Load login page: page.goto + wait_for_selector for password field
    2. Fill email + password fields
    3. Click submit: page.click('input[type="submit"][name="signin"]')
    4. Poll page.url until 'dashboard' appears (max 45s, 0.5s intervals)
    5. CRITICAL: page.wait_for_load_state('networkidle') — token is NOT set on page load
    6. CRITICAL: Extra 5s wait after networkidle for JS to initialize token
    7. Read: page.evaluate("window.web_auth_token")
    
    The fetch() approach (page.evaluate with fetch()) does NOT work — use page.click() instead.
    
    See: kahunas-debug-resilience-patterns skill for full code.

  cron_env_gotcha: |
    CRITICAL: Cron jobs run in a minimal environment — .env files are NOT auto-loaded.
    Any script running via cron MUST load .env explicitly at start of main().
    
    Symptom: TELEGRAM_BOT_TOKEN is empty in cron even though it works interactively.
    Fix: Add .env loading at top of main() before any other code.
    
    ALSO: coaches/*.json credentials must be REAL — placeholder passwords like
    "REPLACE_WITH_REAL_PASSWORD" will silently fail (no error message on page).
    Always verify credentials work interactively first.

  mistune_v320_plugin_syntax: |
    CRITICAL (2 Apr 2026): mistune v3.2.0 changed plugin specification format.
    
    FAILING syntax (used in v3.0.x):
      md = mistune.create_markdown(plugins=['tables', 'strikethrough'])
      => ValueError: not enough values to unpack (expected 2, got 1)
    
    CORRECT v3.2.0 syntax:
      md = mistune.create_markdown(plugins=[
          'mistune.plugins.table.table',
          'mistune.plugins.formatting.strikethrough',
      ])
    
    The plugins are now specified as 'module_path.plugin_function' strings.
    Table plugin: 'mistune.plugins.table.table'
    Strikethrough plugin: 'mistune.plugins.formatting.strikethrough'
    
    Discovered when HTML emails showed raw markdown tables instead of rendered tables.

key_features:
  - Unified 5-section executive report format (not "lens-based")
  - Automatic exercise progression analysis from workout logs
  - 3-week plateau detection triggers video review request
  - Partial key matching for robust Q&A extraction
  - Proper markdown table formatting with consistent column widths
trigger:
  - When user wants complete checkin analysis
  - When user wants trend analysis from fitness data
  - When user needs weekly recommendations based on checkins
  - When working with Kahunas JSON data for insights
  - When creating fitness reports from tracking data
  - When implementing the 17-step review process
  - When analyzing physique photos, body comp, training, and nutrition data
  - When user asks to analyze Kahunas checkin data
  - When user needs ZOE/J3/RP framework insights
  - When generating specific weekly recommendations for a client

required_inputs:
  - All checkin data JSON (extracted from Kahunas via kahunas-data-extractor)
  - Client photos (current and previous week for visual comparison)
  - Training calendar data (optional but recommended)

workflow:
  step_1_extract:
    action: "Extract checkin data from Kahunas using hybrid API + Playwright"
    tool: "kahunas-data-extractor"
    script: "scripts/kahunas_api_extractor.py"
    output: "kahunas_api_data/kahunas_hybrid_YYYYMMDD_HHMMSS.json"
    notes: "Extracts last 10 checkins with full Q&A data from all tabs"
    
step_1b_multi_client_extract:
    action: "Extract data for ALL coach clients (active only)"
    script: "scripts/multi_client_workflow.py" (v5.0+)
    output: "kahunas_api_data/clients/client_<name>_<uuid_short>_YYYYMMDD.json"
    notes: |
      IMPORTANT - Extraction workflow (v5.0):

      1. LOGIN via Playwright, get token: page.evaluate("window.web_auth_token")

      2. GET ALL CLIENTS via API (web UI has broken pagination):
         GET https://api.kahunas.io/api/v2/coach/clients?per_page=100&page=1
         Response: {"data": [...], "meta": {"total": 25, "per_page": 20, "current_page": 1, "last_page": 2}}

      3. DETERMINE ACTIVE: API doesn't return status. Active = has checkins.

      4. FOR EACH CLIENT - HYBRID EXTRACTION:
         a) API call for checkin list (fast): POST /api/v2/checkin/list
         b) Playwright scraping for Q&A detail (required!):
            - API only returns fields:[{label,value}], NOT qa_pairs
            - Scrape: https://kahunas.io/client/checkin/view/{uuid}
            - Parse tabs: checkin, nutrition_plan, workout_program, logs
            - Parse workout_program.raw_text for Sets/Reps/RIR

      5. SETTINGS:
         - MAX_CHECKINS_PER_CLIENT=3 (10+ causes timeout)
         - Use API-provided client['name'] NOT raw_text parsing

      DEACTIVATED CLIENTS to exclude: Zanetta Hartley, Ramona Kastrup

      4. UUID DEDUPLICATION: Always check uuid not in seen_uuids before adding.

      5. SAFETY LIMIT: Set max_pages=5 to prevent infinite loops if bug recurs.

      6. STOP CONDITION: When new_clients_on_page == 0, break immediately.

      Example table row structure:
        Cell[0]: "CS | Catherine Smith | smithcatherine101@icloud.com"
        Cell[1]: "2026 Women's Physique & Health Coaching"
        Cell[2]: "24 Mar, 2026 06:52 PM | Tuesday"
        Cell[3]: "Tue"
        Cell[4]: "Ongoing" or "Offline Payment" or "Canceled"
        Cell[5]: "Active" or "Deactivated"
        Cell[6]: "Actions"

      ACTUAL COUNTS: The coach dashboard typically has:
      - 25 total clients (from API)
      - 21 with checkins (active by API definition)
      - 18 shown as "Active" in web UI stats bar
      - 6 shown as "Archived" in web UI stats bar
      - 2 shown as "Deactivated" in web UI

      The 21 vs 18 difference: API doesn't expose archive status, so clients
      with checkins but archived in UI are included. Use "has checkins" as
      the working definition of active.

      DISCREPANCY NOTE: If web scraping shows 15 but API shows 21, the API is
      correct. The pagination bug causes web scraping to miss ~6 clients.

    step_1c_multi_coach:
      action: "Multi-coach support via --coach flag"
      script: "scripts/multi_client_workflow.py --coach <name>"
      config_dir: "coaches/<name>.json"
      config_contains: |
        - kahunas.coach_email, kahunas.coach_password
        - openrouter.api_key
        - smtp.host, smtp.port, smtp.user, smtp.password
        - report_recipient
        - data_dir (optional, defaults to ~/kahunas_api_data)
        - schedule (optional cron schedule)

      usage: |
        # Run for specific coach (loads config from coaches/<name>.json)
        python3 scripts/multi_client_workflow.py --coach samantha --daily --generate --email

        # Legacy mode (uses env vars, no --coach flag)
        python3 scripts/multi_client_workflow.py --daily --generate --email

      adding_new_coach: |
        1. Create coaches/<coach_name>.json from EXAMPLE.json template
        2. Fill in all credentials and settings
        3. Add cron job with --coach <coach_name> flag
        4. No script changes needed

      packaging: |
        The coaches/ directory is self-contained. To package:
        - Copy entire kahunas-complete-coach/ skill directory
        - Each new Hermes instance needs its own coaches/*.json with valid credentials
        - All config is in the skill, not in .env

    
  step_2_report:
    action: "Generate personalized report (LLM-powered)"
    tool: "kahunas-complete-coach"
    script: "scripts/generate_llm_report.py"
    output: "kahunas_api_data/reports/<client>_LLM_YYYYMMDD.md"
    auto_save: true
    sections:
      - Weight / Waist Change
      - Training & Progression (includes plateau detection)
      - Fatigue / Recovery Status
      - Nutrition & Adjustments
      - Goals for Next Week
    notes: |
      LLM Report Generator (generate_llm_report.py) - v2.0 (Apr 2026):
      - Uses CHFI 17-step methodology as knowledge base
      - Passes ALL Q&A data to LLM for client-specific analysis
      - Produces 450-word concise, punchy reports
      - Includes training progression analysis and plateau detection
      - Uses OpenRouter API (from coach config)
      - Max 1500 tokens output
      - ONLY generates .md files (no email/HTML logic)
      - Email sending handled by email_utils.py (mistune + Resend API)

    step_2b_email:
      action: "Send report via email (uses email_utils)"
      script: "scripts/email_utils.py (shared module)"
      function: "email_utils.send_email()"
      notes: |
        email_utils.py (Apr 2026) - Single source of truth for email delivery:
        - Converts markdown → HTML using mistune v3.2.0
        - Post-processes HTML for email-friendly inline styles
        - Sends via Resend API (not SMTP)
        - Uses coach config smtp dict for API key
        
        Resend usage:
          smtp_cfg = coach_config.get('smtp', {})
          email_utils.send_email(
              report_md_path=str(report_file),
              client_name=client_name,
              recipient=recipient,
              checkin_date=checkin_date,
              coach_name=coach_name,
              smtp_cfg=smtp_cfg
          )

    step_2c_resend:
      action: "Resend an existing .md report"
      script: "scripts/resend_report.py"
      usage: "python3 resend_report.py --report X.md --coach samantha"
      notes: "Standalone utility to resend any stored .md report"

source_materials:
  # PDFs stored in source_materials/ subdirectory (self-contained)
  - review_process.pdf: "17-step review protocol from Clean Health"
  - Fatigue-Recover-Adapt-1.pdf: "Fatigue assessment and recovery strategies"
  - PNC1_Textbook1.1.pdf: "Nutrition coaching fundamentals"
  - PNC2_Student-Textbook.pdf: "Periodization & program design"
  - PNC3_Student-Textbook.pdf: "Advanced coaching methodologies"
  - PPT-Level-1-Textbook.pdf: "Personal trainer certification content"
  - PPT2-Textbook.pdf: "Advanced training principles"

methodology_sources:

  # ============================================================
  # PERSONAL OPTIMIZATION FRAMEWORKS (ZOE / J3 / RP Strength)
  # ============================================================
  
  - name: "ZOE"
    focus: "Metabolic health, gut microbiome, personalized nutrition"
    url: "https://zoe.com/learn"
    key_principles:
      - Blood sugar control and glucose variability
      - Gut health diversity and microbiome balance
      - Inflammatory responses to foods
      - Personalized nutrition over one-size-fits-all
      - Fiber diversity (30+ plants/week target)
      - Post-meal glucose peaks <140 mg/dL
      - Early hunger timing correlates with overnight hypoglycemia
    sample_insight: "Early hunger at 6am suggests inadequate evening protein affecting glucose stability"
    
  - name: "J3 University"
    focus: "Physique development, bodybuilding education, training pedagogy"
    url: "https://blog.j3university.com/"
    key_principles:
      - Progressive overload and volume landmarks
      - Mesocycle periodization (4-6 week blocks)
      - MEV (Minimum Effective Volume) and MRV (Maximum Recoverable Volume)
      - Specialization cycles for lagging body parts
      - Deload timing based on performance degradation
      - Mind-muscle connection and technique mastery
    sample_insight: "Motivation below 7/10 indicates approaching MRV → implement deload"
      
  - name: "RP Strength"
    focus: "Scientific periodization, diet templates, evidence-based tracking"
    url: "https://rpstrength.com/blogs/articles"
    guides: "https://rpstrength.com/collections/guides"
    key_principles:
      - Consistency beats perfection
      - Weekly averages matter more than daily fluctuations
      - Training volume periodization (resensitization phases)
      - Diet breaks and maintenance phases
      - Meal timing around training
      - Recovery markers (sleep, HRV, soreness)
      - Auto-regulation based on fatigue
    sample_insight: "80%+ compliance maintains progress trajectory; one week off ≠ ruin"

  # ============================================================
  # PROFESSIONAL COACHING FRAMEWORK (Clean Health 17-Step)
  # ============================================================

  - name: "Clean Health Fitness Institute"
    focus: "Professional client checkin review process"
    course: "Client Checkin Review Protocol"
    steps: 17
    key_concepts:

      fatigue_assessment:
        signs_of_high_fatigue:
          - Rate of perceived exertion/stress
          - Decreased gym performance
          - Decreased strength
          - Decreased muscle pump
          - Heart rate variability changes
          - Reduced training motivation
          - Mood changes
          - Appetite suppression
          - GI disruption
          - Sleep disruption
          - Illness
          - Injuries and stiffness
          - Loss of libido/menses
        overreaching_definition: "Temporary decline in performance, few days to reverse"
        overtraining_definition: "Chronic decline, weeks to months to reverse"
        
      recovery_strategies:
        during_workout:
          - Rest times management
          - Intra-workout nutrition
          - Volume autoregulation
        between_workouts:
          - Nutrition timing
          - Sleep quality/quantity
          - Relaxation techniques
        between_weeks:
          - Light sessions (deload)
          - Rest days
          
      training_programming:
        volume_guidelines:
          beginner: "2-3x/week whole body, 1-3 sets per exercise"
          intermediate: "6-8 quality sets per muscle group per session, 2x/week frequency"
          advanced: "Same as intermediate, more intensity techniques"
          
        intensity_zones:
          relative_strength: "<5 reps, 3-5 sets per muscle group"
          absolute_strength: "6-8 sets at 80%+, 8-12 sets total per muscle group"
          hypertrophy: "6-12 reps, 60-85% 1RM"
          
        loading_schemes:
          pyramid_sets: "60-70% 1RM for 10-12 reps → working up → back off"
          broad_pyramid: "10-12% intensity spread (6x8,6,4,4,6,8)"
          half_pyramid: "Increasing weight, decreasing reps (3x8,6,4,2)"
          reverse_pyramid: "Heaviest first (after warm-up)"
          
        rest_periods:
          compound_exercises: "3-4 minutes"
          isolation_exercises: "90-100 seconds"
          antagonist_pairing: "Can reduce to 60-75 seconds"
          
      nutrition_periodization:
        phase_rates:
          growth_phase: "0.5% bodyweight gain per week ideal"
          fat_loss_phase: "1% bodyweight loss per week ideal"
          
        adjustment_triggers:
          weight_stable_2_3_weeks: "Assess phase and adjust calories"
          post_fat_loss: "Stabilize for 6 weeks before increasing food"
          metabolic_adaptation: "Consider diet break if prolonged plateau"
          
        meal_timing:
          breakfast: "Within 2 hours of waking"
          lunch: "Before 1pm (ideally), max before 3pm"
          dinner: "No later than 2 hours before bedtime"
          calorie_distribution: "Up to 50% of calories 8+ hours before melatonin onset"
          
        hydration: "1mL per calorie consumed (2000 cal = 2000mL)"
        fiber: "14g per 1000 calories"
        
      body_composition:
        assessment_priority: "Weight and waist matter more than skinfolds in overweight"
        menstrual_cycle_impact: 
          fluid_retention: "Luteal phase"
          performance: "Follicular phase typically better"
          energy: "Low energy in late luteal/early follicular"
        visual_assessment:
          - Increase in body fat
          - Fluid retention
          - Muscle tone changes
          - Muscle separation
          - Lighting influence awareness

# =============================================================================
# ANALYSIS FRAMEWORKS
# =============================================================================

analysis_framework:

  # ---------------------------------------------------------------------------
  # Core Metrics (from both personal + professional frameworks)
  # ---------------------------------------------------------------------------
  
  core_metrics:
    - category: "biometrics"
      metrics:
        - waist_circumference_cm: "Visceral fat indicator, metabolic health"
        - resting_hr_bpm: "Cardiovascular fitness, recovery status"
        - weight_kg: "Long-term trend only, daily noise expected"
        - sleep_hours: "Recovery cornerstone"
         
    - category: "nutrition"
      metrics:
        - plan_compliance: "Adherence %, primary driver of results"
        - untracked_meals: "Variance source, social/event impact"
        - alcohol: "Recovery inhibitor, empty calories"
        - hydration_litres: "Performance and recovery essential"
        - gastric_distress: "Food intolerance, gut health indicator"
        - stimulant_intake: "Caffeine timing, sleep quality impact"
        - hunger_timing: "Meal distribution optimization"
        - fiber_diversity: "30+ plants/week target (ZOE)"
        - glucose_control: "Post-meal peaks <140 mg/dL"
        
    - category: "training"
      metrics:
        - motivation_rating: "1-10 scale, <7 = intervention needed"
        - session_duration: "Efficiency indicator, creeping duration = fatigue"
        - exercise_struggles: "Form issues, strength loss, pain"
        - injuries: "Medical priority, training modification"
        - recovery_between_sets: "Cardiovascular fitness indicator"
        - pump_quality: "Hydration, glycogen status, mind-muscle"
        - mobility_sessions: "Injury prevention, <3x/week = risk"
        - volume_progression: "MEV to MRV tracking"
        - deload_timing: "Based on performance degradation"
        
    - category: "lifestyle"
      metrics:
        - stress_level: "Cortisol impact, recovery thief"
        - hunger_rating: "Caloric adequacy signal"
        - appetite_rating: "Diet sustainability indicator"

  # ---------------------------------------------------------------------------
  # Trend Analysis Rules (thresholds and correlation patterns)
  # ---------------------------------------------------------------------------
  
  trend_analysis_rules:
    primary_thresholds:
      waist_increase_2weeks: 
        threshold: ">1cm/wk"
        action: "Review calories, cortisol, alcohol"
      motivation_below_7: 
        threshold: "<7/10"
        action: "Deload or program change needed"
      stress_above_7: 
        threshold: ">7/10"
        action: "Lifestyle intervention priority"
      mobility_below_2: 
        threshold: "<2x/week"
        action: "Injury prevention protocol"
      compliance_below_80: 
        threshold: "<80%"
        action: "Simplify plan or address barriers"
      injuries_reported: 
        threshold: "Any injury"
        action: "Medical consultation + training modification"
      weight_plateu_3weeks:
        threshold: "Stable 3+ weeks"
        action: "Assess phase, consider calories adjustment"
        
    correlation_patterns:
      high_stress + low_compliance: 
        interpretation: "Environmental trigger, not willpower"
        action: "Plan ahead for stressful periods"
      poor_sleep + high_hunger: 
        interpretation: "Leptin/ghrelin disruption"
        action: "Sleep hygiene protocol"
      long_workouts + low_motivation: 
        interpretation: "Accumulating fatigue"
        action: "Consider deload"
      poor_pump + low_hydration: 
        interpretation: "Fluid or carb status"
        action: "Increase hydration/carbs"
      gastric_distress + non_compliance: 
        interpretation: "Food intolerance suspected"
        action: "Elimination protocol"
      early_hunger + poor_sleep: 
        interpretation: "Overnight hypoglycemia (ZOE framework)"
        action: "Add slow-digesting protein before bed"

  # ---------------------------------------------------------------------------
  # 17-Step Review Process (Clean Health)
  # ---------------------------------------------------------------------------
  
  17_step_review_process:
    step_1:
      name: "Photo Comparison (Current vs Previous)"
      action: "Compare current week photos to previous week"
      key_points:
        - Look for visual changes in body composition
        - Note lighting differences that affect appearance
      aos_field: "progress_photos"
      
    step_2:
      name: "Visual Physique Assessment"
      action: "Assess all photos for compositional changes"
      assess_for:
        - increase_body_fat: "Visible softness, reduced definition"
        - fluid_retention: "Puffy appearance, reduced vascularity"
        - muscle_tone_increase: "Improved firmness, separation"
        - body_fat_decrease: "Increased definition, visible abs/veins"
        - muscle_separation: "Inter-muscular lines visible"
        - lighting_changes: "Note how light affects appearance"
      aos_field: "visual_assessment_notes"
      
    step_3:
      name: "Menstrual Cycle Phase Assessment"
      action: "Record menstrual cycle phase if applicable"
      impact_on:
        - gym_performance: "Typically follicular > luteal"
        - fluid_retention: "Luteal phase = water weight"
        - fatigue: "Late luteal/early follicular = lowest"
        - energy_perception: "Ovulation = peak for many"
      aos_field: "cycle_phase"
      
    step_4:
      name: "Waist Circumference Comparison"
      action: "Compare current to previous week"
      significance: "Visceral fat indicator, metabolic health marker"
      thresholds:
        increase_1cm: "Review calories, stress, alcohol"
        increase_2cm: "Immediate intervention needed"
      aos_fields: ["waist_circumference", "waist_previous"]
      
    step_5:
      name: "Rate of Weight Change Assessment"
      action: "Calculate weekly bodyweight change percentage"
      targets:
        growth_phase: "0.5% bodyweight gain per week"
        fat_loss_phase: "1% bodyweight loss per week"
      aos_fields: ["weight_current", "weight_previous"]
      
    step_6:
      name: "Sleep Quality & Quantity Assessment"
      action: "Review sleep hours and quality ratings"
      targets:
        quantity: "7-9 hours"
        quality: ">7/10 rating"
      aos_fields: ["sleep_hours", "sleep_quality"]
      
    step_7:
      name: "Subjective Stress Markers Assessment"
      action: "Review stress levels and life events"
      impact: "High stress = stagnant bodyweight for weeks"
      targets:
        stress_level: "<7/10"
        trend: "Not increasing week over week"
      aos_fields: ["stress_rating", "stress_events"]
      
    step_8:
      name: "Daily Consistency Assessment"
      action: "Review step count, hydration, energy consistency"
      targets:
        steps: "10,000 daily (unless specified otherwise)"
        hydration: "Consistent daily intake"
        energy_levels: "Stable across week"
      aos_fields: ["daily_steps", "daily_hydration", "daily_energy"]
      
    step_9:
      name: "Training Calendar Review"
      action: "Check completed training days and phase position"
      assess:
        - completed_sessions: "Count across the week"
        - phase_type: "Strength/Hypertrophy/Metabolic"
        - weeks_into_block: "Where in 6-week block"
        - adherence: "% sessions completed"
      aos_fields: ["training_sessions_completed", "current_phase", "weeks_in_block"]
      
    step_10:
      name: "Training Performance Assessment"
      action: "Review log book for volume progression"
      looking_for:
        - gradual_increases: "Volume trending up over weeks"
        - exercise_volume: "Total reps x weight"
        - plateau_detection: "Same weight/reps 3+ weeks"
      aos_fields: ["exercise_performance", "volume_data"]
      
    step_11:
      name: "Training Program Modification"
      action: "Decide if program changes needed"
      timing:
        standard: "Assess every 6 weeks"
        early_changes: "If injury reported or struggling"
      aos_field: "program_changes"
      
    step_12:
      name: "Nutritional Updates Assessment"
      action: "Check if food adjustments needed"
      triggers:
        weight_stable_2_3_weeks: 
          action: "Assess phase and adjust calories"
      aos_fields: ["calorie_intake", "macro_targets"]
      
    step_13:
      name: "Post-Fat Loss Stabilization Check"
      action: "Ensure appropriate timing for increases"
      protocol:
        just_finished_fat_loss: "Stabilize bodyweight for 6 weeks"
        rationale: "Prevents rapid fat regain"
      aos_field: "phase_transition_status"
      
    step_14:
      name: "Subjective Information Review"
      action: "Review all qualitative checkin data"
      categories:
        - stressful_events
        - hunger_levels
        - appetite
        - mobility
        - positives
        - improvements
      aos_fields: ["subjective_ratings", "client_notes"]
      
    step_15:
      name: "Previous Week Goals Assessment"
      action: "Check completion of prior week's targets"
      aos_field: "goals_completion"
      
    step_16:
      name: "Manual Review & Video Recording"
      action: "Synthesize all data and record video feedback"
      aos_field: "coach_video_notes"
      
    step_17:
      name: "Repeat Process"
      action: "Apply to all other checkins"

  # ---------------------------------------------------------------------------
  # Alert Priority System
  # ---------------------------------------------------------------------------
  
  alert_priority_system:
    urgent_red:
      medical_issues: ["Bilateral injuries", "Chronic pain >4 weeks", "Gastric distress ongoing"]
      required_action: "Medical consultation within 1 week"
      
    high_orange:
      compliance: ["<80% nutrition adherence", "Alcohol episodes", "Grip stress >7/10"]
      training: ["Mobility <2x/week", "Motivation <7/10"]
      biometric: ["Waist increase >1cm"]
      
    medium_yellow:
      lifestyle: ["Sleep <6 hours", "Hydration <3L"]
      training: ["Pump quality declining", "Workouts getting longer"]
      
    maintenance_green:
      positive_reinforcement: ["Compliance >90%", "Alcohol-free streak", "Maintained PRs"]

# =============================================================================
# OUTPUTS GENERATED
# =============================================================================

outputs_generated:
  
  comprehensive_analysis:
    filename: "client_analysis_YYYY-MM-DD.md"
    sections:
      # PART 1: PERSONAL OPTIMIZATION (ZOE/J3/RP)
      - Executive Summary with priority alerts
      - Biometric Trends with ZOE metabolic insights
      - Nutrition Analysis with compliance metrics
      - Training Assessment with J3 periodization notes
      - Lifestyle Factors with RP-style observations
      - Correlation Insights (combined frameworks)
      # PART 2: PROFESSIONAL COACH REVIEW (17-Step)
      - Body Composition Trends (steps 1-5)
      - Recovery & Lifestyle (steps 6-8)
      - Training Performance (steps 9-11)
      - Nutrition Assessment (steps 12-13)
      - Subjective Review (step 14)
      - Goals Review (step 15)
      - Recommendations (step 16)
      # PART 3: ACTION PLAN
      - Weekly Action Plan with priorities
      - Targets for Next Checkin
       
  weekly_recommendations:
    filename: "weekly_recommendations_YYYY-MM-DD.md"
    sections:
      - Quick summary
      - This week's priorities (urgent/high/medium)
      - ZOE-style recommendations (metabolic health)
      - J3-style recommendations (training/periodization)
      - RP-style recommendations (consistency)
      - Clean Health 17-step recommendations
      - Targets table
      - Action checklist
      
  action_items_json:
    filename: "action_items.json"
    structure:
      high_priority: []
      medium_priority: []
      low_priority: []
      completed: []

sample_output_structure:
  executive_summary: |
    ## Client: [Name] | Checkin: [#] | Date: [Date]
    
    **Overall Status:** [On Track / Needs Attention / Critical]
    
    **Key Wins:**
    - [List positive achievements]
    
    **Key Concerns:**
    - [List issues requiring attention]
    
  body_composition_section: |
    ### Body Composition Analysis
    
    **Visual Assessment:** [Photos reviewed, changes noted]
    **Waist Trend:** [Current] cm vs [Previous] cm ([Change])
    **Weight Change:** [Current] kg ([Change] kg, [%]%) 
    **Phase Rate:** [Expected] vs [Actual]
    
    *Interpretation:* [Metabolic adaptation? Water retention? Fat loss?]
    
  training_section: |
    ### Training Performance
    
    **Sessions Completed:** [X]/[Y] ([Z]%)
    **Phase:** [Type] | Week [N] of 6
    **Volume Progression:** [Trend]
    **Plateaus Detected:** [Exercises stuck 3+ weeks]
    
    *Modifications Recommended:* [Changes to program]

example_recommendations:
  real_example_1:
    context: "Michal Szalinski, 54, bilateral tennis elbow"
    zoe_insight: 
      finding: "Chronic tendon inflammation"
      mechanism: "Local inflammation; systemic inflammation delays healing"
      recommendation: "Increase omega-3 (2-3g EPA/DHA daily). Consider turmeric/curcumin."
    j3_insight:
      finding: "Upper body specialization interrupted"
      mechanism: "Overuse injury common in 50+ with arm-dominant work"
      recommendation:
        immediate: "Switch to lower body specialization cycle"
        duration: "6-8 weeks"
        exercises_add: ["Reverse wrist curls", "Hammer curls"]
        exercises_remove: ["Barbell curls", "Skullcrushers"]
    rp_insight:
      finding: "Off-plan this week"
      mechanism: "One week off ≠ ruin, pattern recognition matters"
      recommendation: "Identify specific barrier (work events), create pre-planned response"
      target: "Map 1 barrier + solution for next occurrence"
      
  real_example_2:
    context: "Early morning hunger at 6am"
    zoe_insight:
      finding: "Early hunger timing"
      mechanism: "May indicate overnight hypoglycemia or inadequate evening protein"
      recommendation: "Add 20-30g casein or slow-digesting protein 1 hour before bed"
      target: "Shift hunger timing to 8am+ over 2 weeks"
      metric: "Morning hunger timing survey"

correlation_insights_examples:
  stress_compliance:
    pattern: "High stress (8/10) + Off-plan eating"
    interpretation: "Environmental trigger, not willpower issue"
    zoe_angle: "Cortisol affects glucose control - stressful periods need pre-planning"
    j3_angle: "Stress is a training variable - reduce volume during high stress"
    rp_angle: "Consistency under stress requires simplification, not perfection"
    
  fatigue_accumulation:
    pattern: "Workouts taking longer + Motivation dropping (6/10)"
    interpretation: "Accumulating fatigue approaching MRV"
    zoe_angle: "HRV likely declining; prioritize sleep quality"
    j3_angle: "Time to deload: reduce volume 40-50%, maintain intensity"
    rp_angle: "Deload before forced to by injury/illness"

files_in_skill:
  scripts/:
    - analyze_checkins.py: "Full trend analysis across multiple weeks"
    - generate_weekly_recommendations.py: "Framework-based recommendations (ZOE/J3/RP)"
    - multi_client_workflow.py: "Extract data for ALL coach clients (v5.0 API + Q&A scraping)"
    - generate_llm_report.py: "LLM-powered personalized report"
    
  references/:
    - textbook_sources.md: "Key concepts extracted from source materials"
    - quick_reference.md: "17-step checklist for client review"
    - complete_workflow_example.md: "Full workflow documentation"
    
  examples/:
    - michal_sample_analysis.md: "Sample output for reference"
    - sample_checkin_data.json: "Sample input data from kahunas-data-extractor"
    
  source_materials/:
    - review_process.pdf: "17-step review protocol from Clean Health"
    - Fatigue-Recover-Adapt-1.pdf: "Fatigue assessment & recovery strategies"
    - PNC1_Textbook1.1.pdf: "Nutrition coaching fundamentals"
    - PNC2_Student-Textbook.pdf: "Periodization & program design"
    - PNC3_Student-Textbook.pdf: "Advanced coaching methodologies"
    - PPT-Level-1-Textbook.pdf: "Personal trainer certification content"
    - PPT2-Textbook.pdf: "Advanced training principles"

data_format:
  source: "kahunas-data-extractor v5.0 JSON output"
  expected_structure:
    - meta: "extraction metadata, timestamp, user info"
    - user_profile: "client package, weights, age, check-in day"
    - checkins_complete[]: "array of all checkins with tabs"
    - checkins_complete[].tabs.checkin.qa_pairs[]: "biometrics, ratings, injuries"
    - checkins_complete[].tabs.nutrition_plan.qa_pairs[]: "compliance, meals, alcohol, fluids"
    - checkins_complete[].tabs.workout_program.qa_pairs[]: "exercises, sets, reps"
    - checkins_complete[].tabs.logs.qa_pairs[]: "coach feedback, notes"
  key_metrics:
    - waist_circumference_cm: "Primary visceral fat indicator"
    - nutrition_compliance: "Text field - analyze for patterns"
    - alcohol: "Standard drinks per week"
    - hydration_litres: "Daily fluid intake"
    - stimulant_intake: "Caffeine/coffee count"
    - hunger_timing: "When most hungry (meal timing insight)"
    - injury_text: "Free text - parse for injury mentions"

usage:
  command_line: |
    # Complete workflow (Extract → Analyze → Recommend)
    python scripts/workflow_orchestrator.py \
      --data kahunas_complete_data.json \
      --output-dir ./reports
    
    # Quick personal analysis only
    python scripts/analyze_checkins.py \
      --input kahunas_data.json \
      --output personal_analysis.md
    
    # Professional client review only
    python scripts/client_analyzer.py \
      --input kahunas_data.json \
      --client-id CLIENT_ID \
      --output client_review.md
    
    # Generate recommendations
    python scripts/generate_weekly_recommendations.py \
      --input kahunas_data.json \
      --output recommendations.md

    # ★ LLM-POWERED PERSONALIZED REPORT (recommended)
    # Uses OpenRouter API from coach config
    python scripts/generate_llm_report.py \
      --input kahunas_data.json \
      --output personalized_review.md

  python_api: |
    from kahunas_client_analyzer import ClientAnalyzer
    
    analyzer = ClientAnalyzer(kahunas_data)
    
    # Run complete analysis (both personal + professional)
    analysis = analyzer.run_comprehensive_analysis()
    
    # Or run individual analyses
    personal_analysis = analyzer.run_personal_optimization()  # ZOE/J3/RP
    professional_review = analyzer.run_17_step_process()      # Clean Health
    
    # Generate recommendations
    recommendations = analyzer.generate_weekly_recommendations()
    
    # Save reports
    analyzer.save_analysis("client_analysis.md")
    analyzer.save_recommendations("recommendations.md")

note: |
  This skill combines THREE complementary frameworks for complete fitness analysis:
  
  1. ZOE (Metabolic Health): Blood sugar, gut health, inflammation, personalized nutrition
  2. J3 University (Training): Progressive overload, MEV/MRV, periodization, deload timing
  3. RP Strength (Consistency): 80% rule, weekly averages, auto-regulation, diet breaks
  4. Clean Health (Professional): 17-step systematic client review process
  
  The frameworks complement each other:
  - ZOE: What's happening metabolically and how to optimize nutrition timing/quality
  - J3: How to structure training given current state and limitations
  - RP: How to maintain consistency and progress long-term
  - Clean Health: Systematic review ensuring no factor is missed
  
  Always prioritize:
  1. Medical issues (injuries, severe gastric distress) over performance
  2. 2-4 week trends rather than single data points
  3. Frame recommendations positively - what TO do rather than what NOT to do
  4. Client health and safety over arbitrary targets

resources:
  - name: "ZOE"
    url: "https://zoe.com/learn"
  - name: "J3 University"
    url: "https://blog.j3university.com/"
  - name: "RP Strength Articles"
    url: "https://rpstrength.com/blogs/articles"
  - name: "RP Strength Guides"
    url: "https://rpstrength.com/collections/guides"
  - name: "Clean Health Fitness Institute"
    url: "https://cleanhealth.edu.au/"
---
---

## Implementation Notes (Technical Lessons Learned)

These notes document non-trivial solutions discovered through trial and error:

### 1. SMTP Email - Resend Uses "resend" as Username, Not Email
**Problem:** Email sending failed silently with `(535, b'Invalid username')` when using `smtp_cfg.get('user')` as the From address. Resend SMTP authentication requires:
- **Username:** `resend` (literal string, NOT an email address)
- **Password:** the full Resend API key starting with `re_`
- **From address:** must be a valid domain email like `navi@archonhq.ai`

**Root Cause:** `send_report_email()` used `smtp_cfg.get('user')` = `"resend"` as the From header, and bare `except:` swallowed all errors silently.

**Solution (v5.1+):**
```python
from_email = smtp_cfg.get('from_email', get_env_var('RESEND_FROM_EMAIL', 'navi@archonhq.ai'))
# NOT smtp_cfg.get('user') which is "resend" for auth only

except Exception as e:
    import traceback
    print(f"   SMTP Error: {e}")
    traceback.print_exc()
    return False
```

**Coach config (coaches/*.json):**
```json
{
  "smtp": {
    "host": "smtp.resend.com",
    "port": 587,
    "user": "resend",
    "password": "re_WndxHD1h_ArVrgCCB344WUj3Jc2x47HGP"
  }
}
```

### 2. Daily Checkin Detection - Hybrid Date + Checkin Number Approach
**Problem:** UUID-set comparison failed because stored files only hold 3 checkins (MAX_CHECKINS_PER_CLIENT=3) while API returns 20. Since 17 of 20 API UUIDs were not in the 3 stored, `has_new_checkin()` returned True for ALL clients every run.

**Root Cause:** Old approach compared entire UUID sets — any of 17 unseen UUIDs triggered "new".

**Solution (v5.1+):** Compare only the most-recent checkin date + checkin number:
```python
stored_most_recent = stored_checkins[0]  # Sorted newest-first
api_most_recent = api_checkins[0]        # API returns newest-first

if api_date > stored_date:
    return True   # New date = definitely new
if api_date < stored_date:
    return False  # API older than stored (Kahunas stores future dates)
if api_no > stored_no:
    return True   # Same date, higher checkin# = newer submission
return False
```

**Why this works:** Daily detection only needs "is there a checkin newer than last time?" Comparing the single most-recent checkin is sufficient and handles Kahunas' future-date quirk.

### 3. user_profile.name Parsing - Use API Name Directly
**Problem:** When extracting from Kahunas.io, `user_profile.name` sometimes returns page structure text (like "1") instead of the client's actual name. This causes reports to say "Client: 1" instead of "Client: Jane Hurt".

**Root Cause:** The raw_text from checkin detail pages starts with page UI elements, not the client name. Lines like "1" or "Dashboard" can appear first.

**Solution:** Use `client['name']` from the API's client list directly - it's reliable:
```python
# In multi_client_workflow.py, when building user_profile:
'user_profile': {
    'name': client['name'],  # From API client list, NOT from raw_text
    'email': client['email'],
    ...
}
```

### 2. LLM-Powered Reports for Truly Personalized Analysis
**Problem:** Rule-based reports produce generic, template-like output similar across clients. Each client's report should be unique based on their specific data and circumstances.

**Solution:** Use `generate_llm_report.py` which:
- Includes the CHFI 17-step methodology as the LLM system prompt
- Passes ALL of the client's Q&A data to the LLM for context
- Generates truly personalized sections with client-specific quotes and data points
- Uses OpenRouter API for LLM calls

```bash
# Generate LLM-powered personalized report
# Uses OpenRouter API from coach config
python scripts/generate_llm_report.py \
  --input /path/to/client_data.json \
  --output /path/to/report.md
```

**Key Prompt Elements:**
- CHFI knowledge base embedded in system prompt (target values, fatigue markers, patterns)
- Full Q&A extraction from last 3 checkins passed as user context
- Clear section structure: Weight → Training → Fatigue → Nutrition → Goals

**Example Output Difference:**
- Rule-based: "Injury reported. Schedule GP appointment." (generic)
- LLM-powered: "Smashed elbow and shoulder 3 weeks ago + cold + mindless eating = cascading downward spiral. Identifies Pattern #1: stress → avoidance cycle. Cites client's exact words: 'never really hungry, just eat mindlessly'."

**Files:** `scripts/generate_llm_report.py`

### 2. Q&A Key Matching - Use Partial Matching
**Problem:** Kahunas questions have long descriptive text in parentheses:
```
"Do you you feel recovered enough between heavy compound sets?
(heart rate and breathing has returned to pre-set baseline before the next set)"
```
Exact string matching fails constantly.

**Solution:** Use partial key matching:
```python
def get_checkin(key, default=''):
    if key in checkin_qa:
        return checkin_qa[key]
    key_lower = key.lower()
    for q, a in checkin_qa.items():
        if key_lower in q.lower():
            return a
    return default
```

### 2. Date Sorting - Parse Dates Properly
**Problem:** Dates like "7th Mar 2026" sort alphabetically (7th > 29th alphabetically).
This breaks chronological analysis of workout history.

**Solution:** Parse dates with ordinal suffix removal:
```python
def parse_date(date_str: str) -> datetime:
    import re
    clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
    return datetime.strptime(clean, '%d %b %Y')
```

### 3. Workout Logs Are Free Text - Parse with Regex
**Problem:** Workout logs stored as unstructured text in Q&A answer fields:
```
"43 min, Rating: 3/5, Bench: 12x59kg, RDL: 15x59kg, Leg Press: 10x32.5kg"
```

**Solution:** Use regex patterns to extract structured data:
```python
exercise_patterns = [
    (r'Bench[:\s]*(\d+)x(\d+(?:\.\d+)?)\s*kg', 'Bench Press'),
    (r'RDL[:\s]*(\d+)x(\d+(?:\.\d+)?)\s*kg', 'Romanian Deadlift'),
    (r'Leg Press[:\s]*(\d+)x(\d+(?:\.\d+)?)\s*kg', 'Leg Press'),
]
```

### 4. Table Formatting - Consistent Widths
**Problem:** Inline markdown tables render inconsistently without proper alignment.

**Solution:** Use a `format_table()` helper that:
- Calculates max column widths from content
- Caps widths at 45 chars for readability
- Generates proper `|---|` alignment rows

---

## Kahunas Complete Coaching System

### Overview

This unified skill provides comprehensive fitness analysis and coaching through two complementary lenses:

| Mode | Framework | Use Case |
|------|-----------|----------|
| **Personal Optimization** | ZOE + J3 + RP Strength | Self-coaching, personal fitness |
| **Professional Review** | Clean Health 17-Step | Client coaching, professional assessment |

### Quick Start

```bash
# 1. Extract data first
Skill: kahunas-data-extractor

# 2. Run complete analysis (both modes)
python scripts/workflow_orchestrator.py \
  --data kahunas_complete_data.json \
  --output-dir ./reports

# 3. Or run specific analyses
python scripts/analyze_checkins.py --input data.json --output personal.md
python scripts/client_analyzer.py --input data.json --output professional.md
```

### What You Get

1. **Comprehensive Analysis** - Trends, correlations, patterns across weeks
2. **ZOE/J3/RP Recommendations** - Metabolic, training, consistency insights
3. **17-Step Professional Review** - Systematic client assessment
4. **Actionable Checklist** - Prioritized todo items for next week
5. **Target Tracking** - Quantified goals for next checkin

### Example Output

See: `examples/michal_sample_analysis.md`

---

## Changelog

### v4.0.2 (2026-03-31)
- **Critical Fix:** Discovered the Kahunas web UI pagination is fundamentally broken
- **Solution:** Use API endpoint `GET /api.kahunas.io/api/v2/coach/clients?per_page=100&page=N` instead of web scraping
- **Why:** Web pagination shows same 12 rows on pages 2+ (client-side bug in DataTables), making scraping unreliable
- **API benefits:** Returns all 25 clients in 2 pages vs web scraping getting only 15 unique
- **Fixed:** Status filtering - use checkin count to determine active (API doesn't expose archive/paused status)
- **Known Deactivated:** Ramona Kastrup (rkastrup1@gmail.com), Zanetta Hartley (zee.hartley@gmail.com)
- **Target count:** 19 active clients (21 with checkins minus 2 deactivated)

### v4.0.3 (2026-03-31)
- **Critical Discovery:** API checkins return incomplete data!
- **Problem:** API `POST /api/v2/checkin/list` returns only `fields` (list of {label, value, name})
- **Report Generator Needs:** `tabs.checkin.qa_pairs` (Q&A format with question/answer keys)
- **Solution:** Full checkin detail requires Playwright scraping of `/client/checkin/view/{uuid}`
- **See:** `kahunas-data-extractor/scripts/kahunas_multi_client_extractor.py` `_extract_checkin_detail()` method
### v5.0.0 (2026-03-31)
- **Method:** Uses API for checkin list + Playwright scraping of each checkin detail page for Q&A
- **Checkin detail URL:** `/client/checkin/view/{uuid}` works from coach's logged-in session
- **Tabs extracted:** checkin, nutrition_plan, workout_program, logs (all 4 tabs)
- **Q&A format:** Each tab has `qa_pairs` array with {question, answer, source} objects
- **Data structure:** `checkins_complete[N].tabs.checkin.qa_pairs` matches report generator expectations
- **Performance:** Limited to 3 checkins per client for speed (19 clients × 3 = 57 pages ≈ 5 min)
- **Tested:** Jane Hurt report generated successfully with injury detection working correctly

### v4.0.1 (2026-03-31)
- **Fixed:** Pagination bug - added max_pages limit and `new_clients_on_page == 0` early exit
- **Fixed:** UUID deduplication - `uuid not in seen_uuids` check prevents duplicates
- **Verified:** 15 active clients is correct (not 24); 2 clients are Deactivated
- **Updated:** Table cell structure documented (Cell[5] = status, not -2)

### v4.0.0 (2026-03-30)
- **Added:** Multi-client extraction support for coach accounts
- **Added:** `multi_client_workflow.py` for batch processing all coach clients
- **Fixed:** Client name extraction - `user_profile.name` returns ID ("52") not actual name
- **Fixed:** Email generation now properly extracts client name from `raw_text` tabs
- **Enhanced:** Robust `extract_client_name()` function with multiple fallback sources

### v3.1.0 (2026-03-30)
- **Fixed:** Date parsing bug in exercise progression - dates like "7th Mar" sorted alphabetically instead of chronologically, causing plateau detection to fail
- **Enhanced:** `parse_date()` function properly handles ordinal suffixes
- **Enhanced:** Partial key matching for robust Q&A extraction
- **Enhanced:** Markdown table formatting with consistent column widths
