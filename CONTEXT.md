# SENTINEL — Build Context (Level 10)

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
Level 10: SENTINEL Watching SENTINEL
Builds directly on top of Level 9 — all Level 1–9 code remains intact

## What Level 10 Adds
- MetaAgent — monitors the entire pipeline for quality and drift
- Pipeline health scoring — tracks which agents underperform repeatedly
- Debate balance detection — flags if RedTeam always wins (Blue prompts weak)
- Action effectiveness tracking — flags if recommendations never get acted on
- Silent A/B testing — runs old vs new prompts in parallel, picks the winner
- Governance dashboard — full audit trail, confidence gates, human override
- Self-audit reports — weekly system health summary
- This is SENTINEL having opinions about itself and acting on them

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- MetaAgent runs normally in demo mode (uses existing pipeline data)
- Seeded audit history for demo health dashboard
- A/B test results seeded to show optimisation working
- Every sensor agent MUST implement both live and demo paths

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker)
                  sentinel_meta — NEW system-wide meta audit collection
                  all previous collections unchanged
- Embeddings:     google/gemini-embedding-001 via OpenRouter
- API:            FastAPI
- Config:         pydantic-settings
- Logging:        structlog
- Python:         3.11+, async throughout
- OS:             Windows 11 (native)
- UI Framework:   Next.js 14 (App Router)
- UI Styling:     Tailwind CSS + shadcn/ui
- UI connects to: FastAPI on http://localhost:8000

## Model Routing (unchanged from Level 9)
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend: "openrouter" (default) or "groq"
- Embeddings always OpenRouter regardless of LLM_PROVIDER
- No hardcoded model strings anywhere

## LLM Client Pattern (unchanged from Level 9)
- openai SDK with custom base_url
- Provider switching via LLM_PROVIDER env var
- ALL LLM + embedding calls through sentinel/llm/client.py only

## Thinking Levels (Level 10 additions marked)
- Thinking OFF: EntityExtractor, SignalClassifier, RiskAssessor,
                BriefWriter, QualityAgent, all Layer 0, RouterAgent,
                WebSearchAgent, ReplyMonitor, MetaAgent (fast analysis)
- Thinking ON:  CausalChainBuilder, RedTeamAgent, BlueTeamAgent,
                ArbiterAgent, PromptOptimiser, FeedbackAgent,
                ForecastAgent, ActionPlanner, NegotiationAgent,
                OutreachDrafter, ABTestEvaluator (thinking=ON)
- Groq silently ignores thinking param

## Conventions (unchanged from Level 9)
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: asyncio.WindowsSelectorEventLoopPolicy() in main.py

## Architecture (Level 10 changes marked NEW / UPG)
- LangGraph StateGraph as sole orchestration framework
- All Level 1-9 pipeline logic unchanged
- NEW: MetaAgent runs as scheduled background task (not LangGraph node)
       Fires after every 5 pipeline runs OR on-demand via API
       Reads all historical data across Qdrant collections
       Produces MetaReport with health scores per agent
- NEW: ABTestManager — runs two pipeline variants in parallel
       Variant A: current active prompts
       Variant B: challenger prompts from PromptOptimiser
       Compares quality scores, picks winner automatically
- NEW: GovernanceLog — immutable append-only audit trail
       Every autonomous decision logged with reasoning + confidence
       Stored in sentinel_meta Qdrant collection
- NEW: HumanOverrideSystem — any autonomous action can be halted
       Override registered in GovernanceLog
       Future similar actions require approval until override cleared
- UPG: All agents emit AgentHealthEvent after each run
       MetaAgent aggregates these into pipeline health scores
- FastAPI CORS enabled for http://localhost:3000

## Meta System Design (NEW)

### MetaReport Schema
  sentinel/models/meta_report.py

  AgentHealthScore:
    agent_name:          str
    run_count:           int
    avg_quality_score:   float
    error_rate:          float
    avg_latency_ms:      float
    trend:               str     (IMPROVING / STABLE / DEGRADING)
    issues:              List[str]

  DebateBalance:
    red_team_win_rate:   float   (should be ~0.4-0.6 for healthy debate)
    blue_team_win_rate:  float
    balance_status:      str     (BALANCED / RED_DOMINANT / BLUE_DOMINANT)
    recommendation:      str

  ActionEffectiveness:
    total_actions:       int
    acted_on_rate:       float   (from FeedbackAgent)
    auto_execute_rate:   float
    approval_rate:       float   (of PENDING actions how many approved)
    rejection_rate:      float
    effectiveness_score: float   (composite 0.0-1.0)

  MetaReport:
    id:                  UUID
    period_start:        datetime
    period_end:          datetime
    runs_analysed:       int
    agent_health:        List[AgentHealthScore]
    debate_balance:      DebateBalance
    action_effectiveness: ActionEffectiveness
    forecast_accuracy:   float
    overall_health:      float   (0.0-1.0 composite)
    critical_issues:     List[str]
    recommendations:     List[str]
    created_at:          datetime

  Stored in: sentinel_meta Qdrant collection

### MetaAgent
  Location: sentinel/meta/meta_agent.py
  Runs: background task, every META_RUN_INTERVAL_RUNS pipeline runs
        OR manually via POST /meta/run

  Step 1 - Collect data (no LLM):
    Read last N pipeline runs from all Qdrant collections
    Compute AgentHealthScore per agent from quality scores + errors
    Compute DebateBalance from arbiter verdicts
    Compute ActionEffectiveness from feedback + action data
    Read ForecastAccuracy from forecast store

  Step 2 - Analyse issues (Gemini thinking=OFF, fast):
    "Given these health metrics, identify critical issues
     and generate 3-5 specific recommendations."
    Returns critical_issues + recommendations as JSON

  Step 3 - Store MetaReport in sentinel_meta

  Step 4 - Trigger remediation for critical issues:
    If debate unbalanced (RedTeam win rate > 0.7):
      -> request PromptOptimiser to rewrite BlueTeam prompt specifically
    If agent error_rate > 0.1:
      -> log alert via AlertDispatcher
    If action rejection_rate > 0.5:
      -> lower ACTION_AUTO_THRESHOLD by 0.05 (be more conservative)

### ABTestManager
  Location: sentinel/meta/ab_test.py

  Manages silent A/B tests between current and challenger prompts.

  ABTestConfig:
    agent_name:      str
    variant_a:       str   (current active prompt version)
    variant_b:       str   (challenger prompt version)
    start_time:      datetime
    run_count_a:     int
    run_count_b:     int
    quality_sum_a:   float
    quality_sum_b:   float
    status:          str   (RUNNING / COMPLETE / WINNER_A / WINNER_B)
    winner:          str | None

  How it works:
    1. PromptOptimiser creates a new prompt version for agent X
    2. Instead of immediately activating it, ABTestManager starts a test
    3. For next 10 pipeline runs:
       odd runs use variant_a (current)
       even runs use variant_b (challenger)
    4. After 10 runs, compare average quality scores
    5. Winner automatically becomes active prompt
    6. Loser archived in PromptStore with test result metadata
    7. ABTestManager logs result to GovernanceLog

  AB_TEST_ENABLED=true (configurable)
  AB_TEST_MIN_RUNS=10 (minimum runs before declaring winner)

### GovernanceLog
  Location: sentinel/meta/governance.py

  Immutable append-only log of every autonomous decision.
  Every entry is write-once — never updated, never deleted.

  GovernanceEntry:
    id:              UUID
    event_type:      str   (ACTION_EXECUTED, PROMPT_CHANGED,
                            WEIGHT_ADJUSTED, NEGOTIATION_STARTED,
                            OVERRIDE_APPLIED, AB_TEST_RESULT,
                            META_REPORT_GENERATED)
    agent_name:      str
    tenant_id:       str
    description:     str
    reasoning:       str
    confidence:      float | None
    human_involved:  bool
    override:        bool
    created_at:      datetime

  Stored in: sentinel_meta Qdrant collection (separate payload type)
  Never deleted — this is the permanent audit trail

### HumanOverrideSystem
  Location: sentinel/meta/override.py

  Allows a human to halt any class of autonomous behaviour.

  OverrideRule:
    id:              UUID
    scope:           str   (AGENT / ACTION_TYPE / TENANT / GLOBAL)
    target:          str   (e.g. "ActionPlanner", "JIRA_TICKET", "techcorp")
    reason:          str
    applied_by:      str
    active:          bool
    created_at:      datetime
    expires_at:      datetime | None

  Stored in: data/override_rules.json (flat file, checked at runtime)

  When an agent or action is about to execute:
    check_override(scope, target) -> bool
    If override active -> log to GovernanceLog + skip execution
    + notify via AlertDispatcher

  UI: toggle overrides on/off from Governance dashboard

### AgentHealthEvent
  Every agent emits after each run:
  sentinel/meta/health_event.py

  AgentHealthEvent:
    agent_name:    str
    tenant_id:     str
    run_id:        str
    success:       bool
    latency_ms:    float
    quality_score: float | None
    error:         str | None
    created_at:    datetime

  Collected in PipelineState as health_events: List[AgentHealthEvent]
  Written to sentinel_meta after pipeline completes

## Required .env Variables
  (all previous variables unchanged)
  META_RUN_INTERVAL_RUNS=5        # run MetaAgent every N pipeline runs
  META_ENABLED=true               # master switch for MetaAgent
  AB_TEST_ENABLED=true            # enable A/B testing for prompts
  AB_TEST_MIN_RUNS=10             # runs before declaring A/B winner
  GOVERNANCE_ENABLED=true         # enable immutable governance log
  OVERRIDE_RULES_PATH=data/override_rules.json

## 22 Agents - Layer Map (Level 10)

Layer 0 - Sensors (3 agents, unchanged):
  NewsScanner, CyberThreatAgent, FinancialSignalAgent

Layer 1 - Processing (4 agents, unchanged):
  EntityExtractor, SignalClassifier, ForecastAgent, RouterAgent

Layer 2 - Reasoning (2 agents, unchanged):
  RiskAssessor, CausalChainBuilder

Layer 3 - Deliberation (4 agents, unchanged):
  RedTeamAgent, BlueTeamAgent, ArbiterAgent, ActionPlanner

Layer 4 - Output (3 agents, unchanged):
  BriefWriter, QualityAgent, PromptOptimiser UPG

Layer 5 - Memory + Feedback (2 agents, unchanged):
  MemoryWriter UPG, FeedbackAgent

Layer 6 - Negotiation (5 agents, unchanged):
  NegotiationAgent, WebSearchAgent, OutreachDrafter,
  ReplyMonitor, NegotiationSummary

Layer 7 - Meta + Governance (NEW):
  MetaAgent    NEW - pipeline health monitor (thinking=OFF)
  ABTestEvaluator NEW - evaluates A/B test results (thinking=ON)
  GovernanceLogger NEW - immutable audit log writer
  OverrideChecker NEW - checks override rules before execution

## LangGraph Pipeline Flow (Level 10)
  Main pipeline: UNCHANGED from Level 9
  Each agent now emits AgentHealthEvent to PipelineState

  After pipeline END:
    -> MemoryWriter (unchanged)
    -> HealthEventWriter (writes AgentHealthEvents to sentinel_meta)
    -> GovernanceLogger (logs all autonomous decisions this run)
    -> increment run counter
    -> if run_count % META_RUN_INTERVAL_RUNS == 0:
         asyncio.create_task(MetaAgent.run())
    -> asyncio.create_task(ForecastOutcomeTracker.run())
    -> asyncio.create_task(FeedbackAgent.run())

  ABTestManager wraps PromptStore.get_active_prompt():
    if AB_TEST_ENABLED and test running for this agent:
      return variant based on run parity (odd=A, even=B)
    else:
      return normal active prompt

## FastAPI Endpoints (Level 10 additions)
  All Level 1-9 endpoints unchanged

  New in Level 10:
  GET  /meta/reports                  - list MetaReports
  GET  /meta/reports/latest           - most recent MetaReport
  GET  /meta/reports/{id}             - full report detail
  POST /meta/run                      - trigger MetaAgent immediately
  GET  /meta/health                   - current agent health scores
  GET  /meta/debate-balance           - red vs blue win rates
  GET  /meta/action-effectiveness     - action acted-on rates
  GET  /governance/log                - full GovernanceLog paginated
  GET  /governance/log?event_type=    - filtered by event type
  GET  /governance/overrides          - active override rules
  POST /governance/overrides          - create new override rule
  DELETE /governance/overrides/{id}   - deactivate override rule
  GET  /ab-tests                      - list all A/B tests
  GET  /ab-tests/active               - currently running tests
  GET  /ab-tests/{id}                 - single test detail

## UI Changes (Level 10)

  New page: /governance (Governance Dashboard) — TOP PRIORITY PAGE
  This is the showpiece page for the demo.

  Section 1 — System Health Overview:
    Large health score gauge (0-100) with colour coding
    Red = critical, Orange = degraded, Green = healthy
    Last analysed timestamp + "Run Analysis" button

  Section 2 — Agent Health Table:
    Row per agent, columns:
    Agent name | Run count | Avg quality | Error rate | Trend arrow | Status
    Red row if error_rate > 0.1 or quality < 0.6
    Clicking row expands issues list

  Section 3 — Debate Balance:
    Side-by-side bar: RedTeam win rate vs BlueTeam win rate
    Status badge: BALANCED / RED_DOMINANT / BLUE_DOMINANT
    If unbalanced: "SENTINEL is rewriting BlueTeam prompt" notification

  Section 4 — Action Effectiveness:
    Doughnut chart: Auto-executed vs Approved vs Rejected vs Report-Only
    Acted-on rate as large number with trend arrow
    If rejection rate high: "Lowering auto-threshold" notification

  Section 5 — A/B Tests:
    Active test cards showing variant A vs B quality scores
    Progress bar (out of MIN_RUNS)
    Winner badge when test completes

  Section 6 — Governance Log:
    Scrollable timeline of all GovernanceEntries
    Filter by event type, agent, date range
    Each entry: icon + description + confidence + human_involved badge

  Section 7 — Override Controls:
    Active overrides shown as cards with toggle switches
    "Add Override" form: scope + target + reason + expiry
    Warning: "Global override active — all autonomous actions paused"

  Add to top nav as last item with shield icon

  Pipeline monitor upgrades:
  - Add "System Health" stat card (MetaAgent overall_health score)
  - Add "Active Overrides" stat card (red if > 0)

  All pages:
  - If GLOBAL override active: red banner at top of every page
    "⚠ Manual Override Active — Autonomous actions paused"

## Build Order (Level 10 - 10 prompts)

Phase 1 - Meta Infrastructure : Prompts 01-02
  01 - MetaReport model + GovernanceEntry + sentinel_meta collection
       sentinel/models/meta_report.py
           AgentHealthScore, DebateBalance, ActionEffectiveness,
           MetaReport Pydantic models
       sentinel/models/governance_entry.py
           GovernanceEntry Pydantic model
       sentinel/meta/__init__.py
       sentinel/meta/governance.py
           async log_event(event_type, agent, tenant, description,
                          reasoning, confidence, human_involved) -> GovernanceEntry
           async get_log(limit, event_type) -> List[GovernanceEntry]
       scripts/init_qdrant.py updated
           creates sentinel_meta collection
       sentinel/config.py updated - 6 META_ vars
       .env.example updated
       tests/unit/test_meta.py

  02 - AgentHealthEvent + OverrideSystem
       sentinel/meta/health_event.py
           AgentHealthEvent Pydantic model
           async write_health_events(events) -> None
       sentinel/meta/override.py
           OverrideRule Pydantic model
           async check_override(scope, target) -> bool
           async create_override(rule) -> OverrideRule
           async deactivate_override(id) -> OverrideRule
           async list_overrides(active_only) -> List[OverrideRule]
       data/override_rules.json - empty list initially
       All agents updated to emit health events to PipelineState
       sentinel/pipeline/state.py - health_events field added
       sentinel/pipeline/graph.py - HealthEventWriter node at END

Phase 2 - MetaAgent : Prompt 03
  03 - MetaAgent implementation
       sentinel/meta/meta_agent.py
           async run(tenant_id) -> MetaReport
           _collect_agent_health() -> List[AgentHealthScore]
           _compute_debate_balance() -> DebateBalance
           _compute_action_effectiveness() -> ActionEffectiveness
           _analyse_issues(metrics) -> tuple[List[str], List[str]]
           _trigger_remediation(report) -> None
       sentinel/pipeline/graph.py updated
           run counter tracked in persistent state
           MetaAgent fires every META_RUN_INTERVAL_RUNS runs

Phase 3 - ABTestManager : Prompt 04
  04 - ABTestManager
       sentinel/meta/ab_test.py
           ABTestConfig Pydantic model
           ABTestManager class:
               start_test(agent_name, variant_a, variant_b) -> ABTestConfig
               get_prompt_for_run(agent_name, run_parity) -> str
               record_result(agent_name, variant, quality_score) -> None
               evaluate_test(agent_name) -> ABTestConfig (declares winner)
       sentinel/optimiser/prompt_store.py updated
           save_prompt_version() now calls ABTestManager.start_test()
           instead of immediately activating new prompt
       ABTestEvaluator node fires after ABTestManager.evaluate_test()
           logs result to GovernanceLog

Phase 4 - Governance Integration : Prompt 05
  05 - Wire GovernanceLogger into all autonomous decision points
       Every AUTO_EXECUTED action -> log to GovernanceLog
       Every prompt optimisation -> log to GovernanceLog
       Every weight adjustment -> log to GovernanceLog
       Every negotiation started -> log to GovernanceLog
       Every A/B test result -> log to GovernanceLog
       Every override applied -> log to GovernanceLog
       GovernanceLogger wrapper in sentinel/meta/governance.py
       Add override checks in:
           ActionEngine.execute() -> check before executing
           PromptOptimiser.run() -> check before rewriting
           NegotiationPipeline.run() -> check before starting

Phase 5 - API Endpoints : Prompt 06
  06 - Meta + Governance + A/B Test FastAPI endpoints
       All endpoints listed above
       sentinel/api/routes.py updated

Phase 6 - Governance Dashboard UI : Prompts 07-08
  07 - Governance Dashboard page (/governance) — main build
       All 7 sections listed above:
       Health gauge + Agent table + Debate balance + Action effectiveness
       A/B tests + Governance log + Override controls
       Add to top nav with shield icon

  08 - Pipeline + all-pages upgrades
       System Health + Active Overrides stat cards
       Global override banner on all pages
       Red row highlighting in agent table

Phase 7 - QA : Prompts 09-10
  09 - Meta system QA
       Run 5+ pipeline runs to trigger MetaAgent
       GET /meta/reports/latest — full report generated
       GET /meta/health — agent health scores populated
       GET /meta/debate-balance — win rates computed
       Verify PromptOptimiser triggers A/B test instead of direct activation
       Wait for 10 runs (or set AB_TEST_MIN_RUNS=2 for test)
       GET /ab-tests — test declared winner
       Winner activated as new prompt version
       POST /governance/overrides — create override for ActionPlanner
       Run pipeline — verify ActionPlanner skips with override active
       GET /governance/log — override event logged
       DELETE /governance/overrides/{id} — deactivate override
       Run pipeline — verify ActionPlanner resumes

  10 - Full final QA for Level 10
       GET /governance/log — entries from all 9 levels of autonomous events
       Governance Dashboard UI — all 7 sections populated with data
       Override toggle works from UI
       A/B test progress visible in UI
       System Health gauge shows correct score
       Global override banner appears when override active
       pytest tests/ — all tests pass
       npx tsc --noEmit — zero TypeScript errors
       Final confirmation: SENTINEL LEVEL 10 — ALL SYSTEMS GO

## Cost Estimate (Level 10 additions)
  MetaAgent: 1 LLM call per meta run (thinking=OFF) = ~$0.001
  ABTestEvaluator: 1 LLM call per test (thinking=ON) = rare
  GovernanceLogger: 0 LLM calls (pure write operations)
  OverrideChecker: 0 LLM calls (file read)
  Level 10 total per run: ~32 LLM calls
  Meta overhead: ~$0.001 every 5 runs = ~$0.0002 per run amortised
  Cumulative total per run: ~$0.017 essentially unchanged

## Progress Tracker
  Last completed prompt: 10
  Current phase: COMPLETE — Level 10 QA passed

## Built
  (Level 1 complete)
  (Level 2 complete)
  (Level 3 complete)
  (Level 4 complete)
  (Level 5 complete)
  (Level 6 complete)
  (Level 7 complete)
  (Level 8 complete)
  (Level 9 complete)
  (Level 10 complete)
  - MetaReport + AgentHealthScore + DebateBalance + ActionEffectiveness models
  - GovernanceEntry model (immutable audit log)
  - GovernanceLog store (Qdrant sentinel_meta + in-memory fallback)
  - AgentHealthEvent + write_health_events
  - HumanOverrideSystem (check/create/deactivate/list, JSON persistence)
  - MetaAgent (health collection, debate balance, action effectiveness, LLM analysis, remediation)
  - ABTestManager (start/record/evaluate/get with JSON persistence)
  - META_WRITER node in pipeline graph (health events, governance log, MetaAgent trigger)
  - ActionEngine updated: override check + governance logging before/after execution
  - 15 API endpoints (meta reports, health, debate, actions, governance log, overrides CRUD, A/B tests)
  - 12 frontend API functions + 8 TypeScript interfaces
  - Governance Dashboard UI at /governance with 7 sections
  - Navigation updated with ShieldCheck icon for Governance
  - Version badge: v10.0, 22 nodes
  - Config: 6 new environment variables (META_RUN_INTERVAL_RUNS, META_ENABLED, AB_TEST_ENABLED, AB_TEST_MIN_RUNS, GOVERNANCE_ENABLED, OVERRIDE_RULES_PATH)

## Schemas defined
  MetaReport, AgentHealthScore, DebateBalance, ActionEffectiveness
  GovernanceEntry (immutable audit entry)
  AgentHealthEvent (per-agent telemetry)
  OverrideRule (override rules)
  ABTestConfig (A/B test management)

## Agent interfaces
  MetaAgent.run(tenant_id) -> MetaReport
  GovernanceLog.log_event() / get_log()
  OverrideSystem.check_override() / create_override() / deactivate_override() / list_overrides()
  ABTestManager.start_test() / get_prompt_for_run() / record_result() / evaluate_test()
  write_health_events(events) -> None

## Files created
  sentinel/models/meta_report.py
  sentinel/models/governance_entry.py
  sentinel/meta/__init__.py
  sentinel/meta/governance.py
  sentinel/meta/health_event.py
  sentinel/meta/override.py
  sentinel/meta/meta_agent.py
  sentinel/meta/ab_test.py
  data/override_rules.json
  tests/unit/test_meta.py
  sentinel-ui/src/app/governance/page.tsx

## Files modified
  sentinel/config.py (+6 Level 10 env vars)
  .env.example (+8 Level 10 vars)
  scripts/init_qdrant.py (+sentinel_meta collection)
  sentinel/pipeline/state.py (+health_events, +run_counter)
  sentinel/pipeline/graph.py (+META_WRITER node, 21->22 nodes)
  sentinel/actions/engine.py (+override check, +governance logging)
  sentinel/api/routes.py (+15 Level 10 endpoints)
  sentinel-ui/src/lib/api.ts (+8 interfaces, +12 API functions)
  sentinel-ui/src/app/layout.tsx (+Governance nav, v10.0 badge)

## Next
  LEVEL 10 COMPLETE — ALL SYSTEMS GO
  89/89 Python tests pass
  0 TypeScript errors
  Governance Dashboard verified in browser
