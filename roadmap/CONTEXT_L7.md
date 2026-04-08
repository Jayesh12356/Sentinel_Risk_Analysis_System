# SENTINEL — Build Context (Level 7)

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
Level 7: Predictive Risk Intelligence
Builds directly on top of Level 6 — all Level 1–6 code remains intact

## What Level 7 Adds
- ForecastAgent — detects weak signals before they become P0 events
- Predicts "probability this becomes critical in 72 hours" per signal
- Pattern classifier trained on Qdrant historical data (no external ML)
- Weak signal detection — finds early warnings humans would miss
- Forecast dashboard — shows predicted threats before they arrive
- Forecast accuracy tracking — was the prediction right?
- SENTINEL shifts from reactive (what happened) to predictive (what will happen)

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- ForecastAgent runs normally in demo mode (uses LLM + Qdrant history)
- Seeded historical data designed to produce meaningful forecasts
- Demo forecast: low-severity CVE → predicts P0 exploit in 72h
- Every sensor agent MUST implement both live and demo paths

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker)
                  {tenant_id}_signals   — private signals
                  {tenant_id}_memory    — private memory
                  {tenant_id}_feedback  — private feedback
                  {tenant_id}_forecasts — NEW per-tenant forecast store
                  sentinel_prompts      — shared prompt store
                  sentinel_shared_patterns — shared threat patterns
- Embeddings:     google/gemini-embedding-001 via OpenRouter
- API:            FastAPI
- Config:         pydantic-settings
- Logging:        structlog
- Python:         3.11+, async throughout
- OS:             Windows 11 (native)
- UI Framework:   Next.js 14 (App Router)
- UI Styling:     Tailwind CSS + shadcn/ui
- UI Data Flow:   react-flow
- UI connects to: FastAPI on http://localhost:8000

## Model Routing (unchanged from Level 6)
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend: "openrouter" (default) or "groq"
- Embeddings always OpenRouter regardless of LLM_PROVIDER
- No hardcoded model strings anywhere

## LLM Client Pattern (unchanged from Level 6)
- openai SDK with custom base_url
- Provider switching via LLM_PROVIDER env var
- ALL LLM + embedding calls through sentinel/llm/client.py only

## Thinking Levels (Level 7 additions marked)
- Thinking OFF: EntityExtractor, SignalClassifier, RiskAssessor,
                BriefWriter, QualityAgent, all Layer 0, RouterAgent
- Thinking ON:  CausalChainBuilder, RedTeamAgent, BlueTeamAgent,
                ArbiterAgent, PromptOptimiser, FeedbackAgent,
                ForecastAgent (thinking=ON — predictions need deep reasoning)
- Groq silently ignores thinking param

## Conventions (unchanged from Level 6)
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: asyncio.WindowsSelectorEventLoopPolicy() in main.py

## Architecture (Level 7 changes marked →NEW / →UPG)
- LangGraph StateGraph as sole orchestration framework
- All Level 1–6 pipeline logic unchanged
- →NEW: ForecastAgent added AFTER SignalClassifier as LangGraph node
         Runs on every signal regardless of route path
         Does NOT block the main pipeline — result stored in state
- →NEW: {tenant_id}_forecasts Qdrant collection per tenant
- →NEW: ForecastOutcomeTracker — background task that checks if
         forecasts came true (compares forecast against later signals)
- →NEW: WeakSignalDetector — pre-pipeline step that flags
         signals with low priority but high escalation potential
- →UPG: BriefWriter receives forecast context — includes
         predicted threats in the "Coming Next" section of brief
- →UPG: AlertDispatcher fires predictive alerts for HIGH_PROBABILITY
         forecasts (probability > 0.80) even for P2/P3 signals
- FastAPI CORS enabled for http://localhost:3000

## Forecast System Design (NEW)

### ForecastEntry Schema
  sentinel/models/forecast_entry.py

  ForecastHorizon enum:
    H24   — predicted within 24 hours
    H48   — predicted within 48 hours
    H72   — predicted within 72 hours
    H7D   — predicted within 7 days

  ForecastOutcome enum:
    PENDING    — not yet resolved
    CORRECT    — prediction came true
    INCORRECT  — prediction did not come true
    EXPIRED    — horizon passed without resolution

  ForecastEntry:
    id:                UUID
    tenant_id:         str
    signal_id:         UUID          (the weak signal that triggered forecast)
    signal_title:      str
    current_priority:  SignalPriority (what it is NOW — P2 or P3)
    predicted_priority: SignalPriority (what it will become — P0 or P1)
    probability:       float         (0.0–1.0)
    horizon:           ForecastHorizon
    reasoning:         str           (why ForecastAgent thinks this will escalate)
    evidence:          List[str]     (historical patterns that support prediction)
    outcome:           ForecastOutcome (default PENDING)
    resolved_at:       datetime | None
    created_at:        datetime

  Stored in: Qdrant {tenant_id}_forecasts collection
  Embedded using signal_title + reasoning for similarity search

### ForecastAgent
  Location: sentinel/agents/layer1_processing/forecast_agent.py
  Position: LangGraph node AFTER SignalClassifier, runs on ALL signals

  For each signal, ForecastAgent:
    1. Queries {tenant_id}_memory for historically similar signals
       that ESCALATED in priority after initial classification
    2. Queries sentinel_shared_patterns for cross-company escalation patterns
    3. Queries {tenant_id}_forecasts for past forecast accuracy
       (what % of past forecasts came true — used to calibrate confidence)
    4. Asks Gemini (thinking=ON):
       "Given this P2 signal, historical escalation patterns,
        and cross-company intelligence, what is the probability
        this becomes P0/P1 within 72 hours?
        Provide probability (0.0–1.0), horizon (H24/H48/H72/H7D),
        and reasoning in JSON."
    5. Creates ForecastEntry and stores in {tenant_id}_forecasts
    6. If probability > FORECAST_ALERT_THRESHOLD:
       → fires predictive alert via AlertDispatcher immediately
       → subject: "[SENTINEL FORECAST] P0 predicted in 72h"

  ForecastAgent only creates forecasts for:
    - P2 or P3 signals (P0/P1 are already critical, no need to forecast)
    - Signals where probability > FORECAST_MIN_PROBABILITY (0.40)
    - Skip if no historical data yet (FORECAST_MIN_HISTORY=5 past signals)

### WeakSignalDetector
  Location: sentinel/forecast/weak_signal_detector.py
  Position: Runs before pipeline as a pre-filter

  Scans incoming signals for weak signal indicators:
    - Low CVSS score but rapidly increasing CVE references
    - Minor financial filing but from systemically important entity
    - Single news article but matching known escalation pattern
    - Cross-tenant pattern match on a currently low-priority signal

  Output: weak_signal_flags: Dict[signal_id, List[str]]
    Injected into PipelineState
    ForecastAgent reads these flags as additional context

### ForecastOutcomeTracker
  Location: sentinel/forecast/outcome_tracker.py
  Runs as: asyncio background task after each pipeline run

  For each PENDING forecast older than its horizon:
    1. Search {tenant_id}_signals for signals similar to the forecast
       that arrived AFTER the forecast was created
    2. If found with higher priority → mark outcome=CORRECT
    3. If horizon expired with no matching signal → mark outcome=INCORRECT
       or outcome=EXPIRED if probability was < 0.6

  Updates ForecastEntry in Qdrant with outcome + resolved_at
  Logs: "forecast.resolved id={id} outcome={outcome} accuracy={rate}"

### Forecast Accuracy Metrics
  ForecastAgent reads its own historical accuracy before making predictions.
  This creates a self-calibrating system:

  If past accuracy < 0.5:
    → reduce probability estimates by 0.1 (be more conservative)
  If past accuracy > 0.8:
    → increase probability estimates by 0.05 (trust the model more)

  accuracy = count(CORRECT) / count(CORRECT + INCORRECT)
  Stored per tenant in {tenant_id}_forecasts metadata

## Historical Pattern Analysis (NEW)
  Forecasts are only as good as the history they draw from.
  Level 7 includes a history seeder to bootstrap predictions.

  scripts/seed_forecast_history.py
    For each demo tenant, seeds 30 historical MemoryEntries
    spanning the last 90 days with realistic escalation patterns:
      - 5 CVEs that escalated from P2 → P0 within 48h
      - 3 financial signals that escalated P2 → P1 within 7d
      - 10 signals that stayed at their original priority (true negatives)
    These give ForecastAgent real patterns to learn from immediately.

## Required .env Variables
  OPENROUTER_API_KEY=
  NEWSAPI_KEY=
  SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
  SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
  QDRANT_URL=http://localhost:6333
  QDRANT_COLLECTION=sentinel_signals
  QDRANT_MEMORY_COLLECTION=sentinel_memory
  QDRANT_PROMPTS_COLLECTION=sentinel_prompts
  QDRANT_FEEDBACK_COLLECTION=sentinel_feedback
  QDRANT_SHARED_COLLECTION=sentinel_shared_patterns
  DEMO_MODE=false
  LOG_LEVEL=INFO
  LLM_PROVIDER=openrouter
  GROQ_API_KEY=
  GROQ_MODEL=llama-3.3-70b-versatile
  COMPANY_PROFILE_PATH=data/company_profile.json
  ALERT_DEMO_MODE=true
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=
  SMTP_PASSWORD=
  ALERT_EMAIL_TO=
  SLACK_WEBHOOK_URL=
  ALERTS_ENABLED=true
  QUALITY_THRESHOLD=0.70
  OPTIMISER_ENABLED=true
  OPTIMISER_MIN_RUNS=3
  FEEDBACK_BASE_URL=http://localhost:8000
  FEEDBACK_WINDOW_DAYS=30
  FEEDBACK_MIN_ENTRIES=5
  ACTIVE_TENANT=default
  TENANTS_DIR=data/tenants
  FORECAST_ENABLED=true                  # NEW master switch
  FORECAST_ALERT_THRESHOLD=0.80          # NEW fire alert if prob > this
  FORECAST_MIN_PROBABILITY=0.40          # NEW minimum to store forecast
  FORECAST_MIN_HISTORY=5                 # NEW min past signals before forecasting
  FORECAST_HORIZON_DEFAULT=H72           # NEW default forecast horizon

## 16 Agents — Layer Map (Level 7)

Layer 0 — Sensors (3 agents, unchanged):
  NewsScanner          → RSS + NewsAPI  → sample fallback
  CyberThreatAgent     → NVD/CVE API   → sample fallback
  FinancialSignalAgent → SEC EDGAR     → sample fallback

Layer 1 — Processing (4 agents, ForecastAgent added):
  EntityExtractor      → NER via Gemini
  SignalClassifier     → P0/P1/P2/P3 + reads feedback_weights
  ForecastAgent →NEW   → predicts escalation probability (thinking=ON)
  RouterAgent          → Path decision

Layer 2 — Reasoning (2 agents, unchanged):
  RiskAssessor         → profile-weighted scoring
  CausalChainBuilder   → root cause DAG + memory + shared patterns

Layer 3 — Deliberation (3 agents, unchanged):
  RedTeamAgent         → adversarial challenge + memory
  BlueTeamAgent        → optimistic defence + memory
  ArbiterAgent         → verdict + alerts + feedback weights

Layer 4 — Output (3 agents, BriefWriter upgraded):
  BriefWriter →UPG     → includes "Predicted Threats" section
  QualityAgent         → scores brief
  PromptOptimiser      → rewrites weak prompts async

Layer 5 — Memory + Feedback (2 agents, unchanged):
  MemoryWriter         → writes MemoryEntry + QualityScore
  FeedbackAgent        → reads feedback, adjusts weights

  New non-agent services:
  WeakSignalDetector   → pre-pipeline weak signal flagging
  ForecastOutcomeTracker → background outcome resolution

## LangGraph Pipeline Flow (Level 7)
  START
    → [WeakSignalDetector]              ← NEW pre-filter
    → [Load TenantContext]
    → [SharedPatternReader]
    → NewsScanner → CyberThreatAgent → FinancialSignalAgent
    → EntityExtractor
    → SignalClassifier [reads feedback_weights]
    → ForecastAgent [thinking=ON, stores ForecastEntry] ← NEW
    → [Loop 1 check]
    → RouterAgent
    → [Route check]
        Path A → RiskAssessor
              → CausalChainBuilder [+memory + shared + forecasts]
              → RedTeamAgent → BlueTeamAgent
              → ArbiterAgent [alerts + feedback links]
              → [Loop 2 check] → BriefWriter [+forecast section]
        Path B → RiskAssessor → BriefWriter [+forecast section]
        Path C → BriefWriter
    → QualityAgent → [PromptOptimiser if needed]
    → MemoryWriter
    → SharedPatternWriter
    → asyncio.create_task(ForecastOutcomeTracker.run())  ← NEW
    → asyncio.create_task(FeedbackAgent.run())
  END

## FastAPI Endpoints (Level 7 additions)
  --- All Level 1–6 endpoints unchanged ---

  --- New in Level 7 ---
  GET  /forecasts                        → list all forecasts (tenant-scoped)
  GET  /forecasts/active                 → pending forecasts only
  GET  /forecasts/{id}                   → single forecast detail
  GET  /forecasts/accuracy               → accuracy metrics per tenant
  GET  /forecasts/signal/{signal_id}     → forecast for a specific signal
  POST /forecasts/resolve                → manually trigger outcome tracker
  GET  /forecasts/history?days=30        → resolved forecasts with outcomes

## UI Changes (Level 7)
  New page: /forecasts (Predictive Intelligence)
  - Hero section: "SENTINEL sees {N} threats coming"
    Large number showing active high-probability forecasts
  - Forecast cards sorted by probability descending:
    Each card:
      Signal title (the weak signal)
      Current priority badge (P2/P3 — what it is now)
      Predicted priority badge (P0/P1 — what it will become)
      Probability bar (red fill, e.g. 85%)
      Horizon pill (e.g. "Within 72 hours")
      Reasoning excerpt (first 100 chars)
      Outcome badge (PENDING/CORRECT/INCORRECT/EXPIRED)
  - "Accuracy" tab — shows historical forecast accuracy per category
    Bar chart: CYBER 78% | NEWS 61% | FINANCIAL 72%
  - Add to top nav after Shared

  Brief page upgrades:
  - Add "Predicted Threats" section BEFORE recommendations
    Shows active high-probability forecasts relevant to this brief
    Framed as: "SENTINEL predicts these will escalate:"
    Each item: signal + probability + horizon

  Alerts board upgrades:
  - "Forecast: P0 in 72h" warning badge on P2/P3 cards
    where a high-probability forecast exists for that signal
  - Clicking badge opens forecast detail modal

  Pipeline monitor upgrades:
  - Add "Active Forecasts" stat card
  - Add "Forecast Accuracy" stat card (% correct of resolved)

## Build Order (Level 7 — 9 prompts)

Phase 1 — Forecast Infrastructure : Prompts 01–02
  01 → ForecastEntry model + Qdrant collection + outcome tracker
       sentinel/models/forecast_entry.py
           ForecastHorizon enum, ForecastOutcome enum, ForecastEntry model
           to_payload() / from_payload()
       sentinel/forecast/__init__.py
       sentinel/forecast/store.py
           async save_forecast(entry) → ForecastEntry
           async get_forecasts(tenant_id, pending_only) → List[ForecastEntry]
           async get_accuracy(tenant_id) → dict
           async update_outcome(id, outcome) → ForecastEntry
       sentinel/forecast/outcome_tracker.py
           async run(tenant_id) → resolves pending forecasts
       scripts/init_qdrant.py updated
           creates {tenant_id}_forecasts for all 4 demo tenants
       sentinel/config.py updated — 5 FORECAST_ vars
       .env.example updated
       tests/unit/test_forecast.py

  02 → WeakSignalDetector + history seeder
       sentinel/forecast/weak_signal_detector.py
           detect(signals, tenant_context) → Dict[UUID, List[str]]
           checks: CVE reference growth, entity importance,
                   cross-tenant pattern match, historical escalation match
       scripts/seed_forecast_history.py
           seeds 30 historical MemoryEntries per demo tenant
           spans 90 days with realistic escalation patterns

Phase 2 — ForecastAgent : Prompt 03
  03 → ForecastAgent LangGraph node
       sentinel/agents/layer1_processing/forecast_agent.py
           async run(state) → state
           queries memory + shared patterns + past accuracy
           calls Gemini thinking=ON for probability estimate
           stores ForecastEntry if probability > FORECAST_MIN_PROBABILITY
           fires predictive alert if probability > FORECAST_ALERT_THRESHOLD
       sentinel/pipeline/state.py updated — forecasts: List[ForecastEntry]
       sentinel/pipeline/graph.py updated
           ForecastAgent node after SignalClassifier
           WeakSignalDetector runs at pipeline start

Phase 3 — BriefWriter Upgrade : Prompt 04
  04 → BriefWriter "Predicted Threats" section
       BriefWriter.run() receives forecasts from state
       New section in brief: predicted threats with probability + horizon
       Only includes forecasts with probability > 0.60
       sentinel/models/brief.py updated — predicted_threats field
       sentinel/agents/layer4_output/brief_writer.py updated

Phase 4 — API Endpoints : Prompt 05
  05 → Forecast FastAPI endpoints
       GET /forecasts, GET /forecasts/active, GET /forecasts/{id}
       GET /forecasts/accuracy, GET /forecasts/signal/{signal_id}
       POST /forecasts/resolve, GET /forecasts/history
       sentinel/api/routes.py updated

Phase 5 — UI : Prompts 06–07
  06 → Forecasts page (/forecasts)
       Hero + forecast cards + accuracy tab
       Add to top nav

  07 → Alerts + Brief + Pipeline UI upgrades
       Forecast badge on alert cards
       Predicted Threats section in briefs
       Active Forecasts + Accuracy stat cards on pipeline page

Phase 6 — QA : Prompts 08–09
  08 → Seed and verify forecast history
       Run scripts/seed_forecast_history.py — verify 30 entries per tenant
       Run pipeline — verify ForecastAgent fires for P2/P3 signals
       Verify ForecastEntry created in {tenant_id}_forecasts
       Verify probability + reasoning populated
       Verify predictive alert logs when prob > threshold
       GET /forecasts/active — returns pending forecasts

  09 → Full QA for Level 7
       Run ForecastOutcomeTracker manually via POST /forecasts/resolve
       Verify PENDING forecasts resolve to CORRECT/INCORRECT/EXPIRED
       GET /forecasts/accuracy — returns accuracy metrics
       Verify "Predicted Threats" section appears in brief
       Verify "Forecast: P0 in 72h" badge on alert cards
       Verify Forecasts page loads with cards and accuracy tab
       Verify Active Forecasts stat card on pipeline page
       All 4 demo tenants have isolated forecast collections
       pytest tests/ — all tests pass

## Cost Estimate (Level 7 additions)
  ForecastAgent: 1 LLM call per P2/P3 signal (thinking=ON)
    ~5 P2/P3 signals per run × thinking = ~$0.005 per run
  WeakSignalDetector: 0 LLM calls (pure Python pattern matching)
  ForecastOutcomeTracker: 0 LLM calls (Qdrant search + comparison)
  Level 7 total per run: ~28 LLM calls
  Extra cost per run: ~$0.005
  Cumulative total per run: ~$0.014

## Progress Tracker
  Last completed prompt: 09 (Full Level 7 QA — PASSED)
  Current phase: ✅ Level 7 COMPLETE

  QA Status:
    [x] init_qdrant.py — forecast collections created for default, techcorp, retailco, financeinc
    [x] seed_forecast_history.py — 120 MemoryEntries seeded (30 per tenant)
    [x] pytest tests/unit/ — 53/53 passed
    [x] npx tsc --noEmit — ZERO TypeScript errors
    [x] Live API pipeline run — 10 signals, 10 reports, 20 forecasts generated
    [x] GET /forecasts/active, /forecasts/accuracy, /briefs/latest — all verified
    [x] POST /forecasts/resolve — outcome tracker ran successfully
    [x] UI: /forecasts page, alert badges, briefs predicted threats, pipeline stat cards — all verified

## Built
  (Level 1 complete — see Level 1 CONTEXT.md)
  (Level 2 complete — see Level 2 CONTEXT.md)
  (Level 3 complete — see Level 3 CONTEXT.md)
  (Level 4 complete — see Level 4 CONTEXT.md)
  (Level 5 complete — see Level 5 CONTEXT.md)
  (Level 6 complete — see Level 6 CONTEXT.md)

  Level 7 — Phase 1: Forecast Infrastructure (Prompts 01–02) ✅
    ForecastEntry Pydantic model (ForecastHorizon, ForecastOutcome enums)
    ForecastStore async helpers: save_forecast, get_forecasts, get_accuracy,
      update_outcome, get_forecast_by_signal
    ForecastOutcomeTracker: async run(tenant_id) resolves PENDING forecasts
      via Qdrant similarity search on {tenant_id}_signals
    WeakSignalDetector: pure-Python heuristic engine (5 detection patterns)
      checks urgency keywords, vulnerability patterns, CVE IDs, financial
      crisis keywords, weak-signal linguistic patterns
    scripts/init_qdrant.py updated — provisions {tenant_id}_forecasts for
      4 demo tenants (default, techcorp, retailco, financeinc)
    sentinel/config.py updated — 5 FORECAST_ config vars added
    scripts/seed_forecast_history.py — seeds 30 MemoryEntries per tenant
      (120 total) with realistic escalation patterns

  Level 7 — Phase 2: Pipeline Integration (Prompt 03) ✅
    ForecastAgent LangGraph node:
      reads state.signals (P2/P3 only), queries memory + shared patterns
      runs Gemini thinking=ON for probability estimate per signal
      self-calibrates using get_accuracy() for tenant historical rate
      stores ForecastEntry if probability > FORECAST_MIN_PROBABILITY
      fires predictive alert if probability > FORECAST_ALERT_THRESHOLD
    sentinel/pipeline/state.py updated — forecasts: List[ForecastEntry],
      weak_signal_flags: Dict[str, List[str]] fields added
    sentinel/pipeline/graph.py updated — 19 nodes total:
      WEAK_SIGNAL_DETECTOR node added at START of pipeline
      FORECAST_AGENT node added after SIGNAL_CLASSIFIER
      _weak_signal_detector() async wrapper initialises state fields
      _forecast_agent() async wrapper calls ForecastAgent.run()

  Level 7 — Phase 3: BriefWriter Upgrade (Prompt 04) ✅
    brief model: predicted_threats: List[dict], forecast_count: int added
    BriefWriter.run() reads state.forecasts from state
    BriefWriter._generate_brief() now accepts forecasts kwarg
    Builds predicted_threats list from ForecastEntry objects (prob > 0.60)
    Appends "⚡ Predicted Threats (AI Forecast)" BriefSection if any

  Level 7 — Phase 4: API Endpoints (Prompt 05) ✅
    7 FastAPI forecast endpoints added to routes.py:
      GET  /forecasts              — all forecasts for tenant
      GET  /forecasts/active       — PENDING only
      GET  /forecasts/accuracy     — accuracy metrics with by_category
      GET  /forecasts/history      — resolved forecasts by date range
      GET  /forecasts/signal/{id}  — per-signal forecast
      GET  /forecasts/{id}         — single forecast by ID
      POST /forecasts/resolve      — trigger ForecastOutcomeTracker

  Level 7 — Phase 5: UI — /forecasts page (Prompt 06) ✅
    layout.tsx: TrendingUp icon + Forecasts nav item added after Briefs
    /forecasts/page.tsx: complete Predictive Risk Intelligence dashboard
      Stats row (Active, Resolved, Accuracy Rate, High-Prob Alerts)
      Self-calibrating accuracy banner with by_category rates
      Active / History tab toggle
      ForecastCard: probability bar, priority badges, expandable reasoning
      Resolve Pending button (POST /forecasts/resolve)
      Empty states with seed instructions

  Level 7 — Phase 5: UI — Alerts + Brief + Pipeline upgrades (Prompt 07) ✅
    alerts/page.tsx: Level 7 forecast badge per P2/P3 alert card
      TrendingUp icon, orange badge, "Forecast: P0 in 72h · 78%"
      Fetches GET /forecasts/signal/{signal_id} after alerts load
      Shows badge only if probability ≥ 0.65 and outcome=PENDING
    briefs/page.tsx: Predicted Threats section
      Orange left-border card, TrendingUp icon, probability bar,
      priority escalation arrows (P2 → P1), reasoning 2-line max
      Conditionally shown if brief.predicted_threats.length > 0
    lib/api.ts: BriefDetail interface updated
      predicted_threats?: Array<{signal_title, current_priority,
        predicted_priority, probability, horizon, reasoning}>
      forecast_count?: number
    page.tsx: Pipeline stat row expanded from 5 to 7 cards
      grid-cols-7, TrendingUp+BarChart3 imports
      forecastStats state polling /forecasts/active + /forecasts/accuracy every 10s
      "Forecasts" card (Active count, indigo TrendingUp)
      "Accuracy" card (rate%, emerald BarChart3)

## Schemas defined
  ForecastEntry (sentinel/models/forecast_entry.py):
    id: str, tenant_id: str, signal_id: str, signal_title: str,
    signal_category: str, current_priority: str, predicted_priority: str,
    probability: float, horizon: ForecastHorizon, reasoning: str,
    evidence: List[str], outcome: ForecastOutcome, created_at: datetime,
    resolved_at: Optional[datetime], calibration_adjustment: float
    + to_payload(), from_payload(), embed_text() methods

  Brief (sentinel/models/brief.py) — updated additions:
    predicted_threats: List[dict]  # {signal_title, current_priority,
                                   #  predicted_priority, probability,
                                   #  horizon, reasoning}
    forecast_count: int

## Agent interfaces
  ForecastAgent.run(state: dict) → dict:
    state IN:  signals: List[Signal], weak_signal_flags: Dict[str, List[str]]
    state OUT: forecasts: List[ForecastEntry]

  WeakSignalDetector (pre-pipeline, no LLM):
    detect(signals: List[Signal]) → Dict[str, List[str]]
    (per-signal flag categories)

  ForecastOutcomeTracker:
    run(tenant_id: str) → dict{resolved, correct, incorrect, expired}

## Files created
  sentinel/models/forecast_entry.py     — ForecastEntry Pydantic model
  sentinel/forecast/__init__.py          — package init
  sentinel/forecast/store.py             — Qdrant forecast store (5 helpers)
  sentinel/forecast/outcome_tracker.py   — async outcome resolution
  sentinel/forecast/weak_signal_detector.py — heuristic pre-filter
  sentinel/agents/layer1_processing/forecast_agent.py — LangGraph node
  scripts/seed_forecast_history.py       — 30×4=120 MemoryEntry seeder
  sentinel-ui/src/app/forecasts/page.tsx — /forecasts Predictive Intelligence page

  Files modified:
  sentinel/config.py                    — 5 FORECAST_ config vars
  sentinel/pipeline/state.py            — forecasts + weak_signal_flags fields
  sentinel/pipeline/graph.py            — 19 nodes, WEAK_SIGNAL_DETECTOR + FORECAST_AGENT
  sentinel/models/brief.py              — predicted_threats + forecast_count fields
  sentinel/agents/layer4_output/brief_writer.py — predicted_threats injection
  sentinel/api/routes.py                — 7 forecast endpoints
  scripts/init_qdrant.py                — {tenant_id}_forecasts collections
  sentinel-ui/src/app/layout.tsx        — Forecasts nav item (TrendingUp icon)
  sentinel-ui/src/app/alerts/page.tsx   — forecast badge per P2/P3 alert card
  sentinel-ui/src/app/briefs/page.tsx   — Predicted Threats section
  sentinel-ui/src/lib/api.ts            — BriefDetail: predicted_threats + forecast_count
  sentinel-ui/src/app/page.tsx          — grid-cols-7, Active Forecasts + Accuracy stat cards

  Level 7 -- Phase 6: QA Bug Fixes (Prompt 09) DONE
    Bug 1: Frontend Tenant interface used tenant_id but backend returns id
      Fixed: api.ts, TenantSwitcher.tsx, tenants/page.tsx, routes.py
    Bug 2: Default tenant context was techcorp but pipeline uses default
      Fixed: tenant-context.tsx DEFAULT_TENANT changed to default
    Bug 3: default tenant missing from registry.json
      Fixed: Added default entry to data/tenants/registry.json

## Next
SENTINEL LEVEL 7 -- ALL SYSTEMS GO -- Prompt 09 QA PASSED

   All 15 QA checks passed:
    API:  1-9  PASS (pipeline, forecasts, accuracy, briefs, resolve, history, per-signal)
    UI:  10-15 PASS (main page, forecasts page 20 active, alert forecast badges,
                    predicted threats in briefs, 7 pipeline stat cards,
                    multi-tenant switcher fully working with 5 tenants)

   Level 7 build is finalized. System is demo-ready.
