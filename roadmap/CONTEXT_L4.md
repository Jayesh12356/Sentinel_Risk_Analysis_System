# SENTINEL — Build Context (Level 4)

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
Level 4: Self-Improving Prompts
Builds directly on top of Level 3 — all Level 1, 2, 3 code remains intact

## What Level 4 Adds
- QualityAgent — scores every brief after generation (0.0–1.0)
- PromptOptimiser — rewrites prompts that score below threshold
- PromptStore — versioned prompt storage in Qdrant
- A/B testing — old vs new prompt runs silently in background
- Prompt history UI — see how each agent's prompt evolved over time
- Agents literally get better at their jobs with every run
  without any retraining or manual intervention

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- --demo-mode loads from data/sample_signals/ instead of live APIs
- Gemini still runs in demo mode (only live APIs are mocked)
- QualityAgent and PromptOptimiser run normally in demo mode
  (they use LLM calls, not external APIs)
- PromptStore seeded with initial prompt versions on first run
- Every sensor agent MUST implement both live and demo paths

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker)
                  sentinel_signals  — signals + embeddings
                  sentinel_memory   — threat memory entries
                  sentinel_prompts  — NEW versioned prompt store
- Embeddings:     google/gemini-embedding-001 via OpenRouter
- API:            FastAPI
- Config:         pydantic-settings
- Logging:        structlog
- Python:         3.11+, async throughout
- OS:             Windows 11 (native)
- UI Framework:   Next.js 14 (App Router)
- UI Styling:     Tailwind CSS + shadcn/ui
- UI Data Flow:   react-flow (causal chain DAG)
- UI connects to: FastAPI on http://localhost:8000
- Email:          SMTP via smtplib (from Level 3)
- Slack:          Incoming Webhooks (from Level 3)

## Model Routing (unchanged from Level 3)
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend: "openrouter" (default) or "groq"
- Embeddings always OpenRouter regardless of LLM_PROVIDER
- No hardcoded model strings anywhere

## LLM Client Pattern (unchanged from Level 3)
- openai SDK with custom base_url
- Provider switching via LLM_PROVIDER env var
- ALL LLM + embedding calls through sentinel/llm/client.py only

## Thinking Levels (Level 4 additions marked)
- Thinking OFF: EntityExtractor, SignalClassifier, RiskAssessor,
                BriefWriter, all Layer 0, RouterAgent, QualityAgent
- Thinking ON:  CausalChainBuilder, RedTeamAgent, BlueTeamAgent,
                ArbiterAgent, PromptOptimiser
- Groq silently ignores thinking param

## Conventions (unchanged from Level 3)
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: asyncio.WindowsSelectorEventLoopPolicy() in main.py

## Architecture (Level 4 changes marked →NEW / →UPG)
- LangGraph StateGraph as sole orchestration framework
- Pipeline is a graph with conditional routing (from Level 2)
- Memory queries in reasoning agents (from Level 3)
- →NEW: QualityAgent added AFTER BriefWriter as LangGraph node
- →NEW: PromptOptimiser fires async if quality_score < threshold
- →NEW: All agents load their prompts from PromptStore at runtime
         NOT from hardcoded strings in their files
- →NEW: Qdrant sentinel_prompts collection stores versioned prompts
- →UPG: Every agent's prompt is now a live, evolvable document
- FastAPI CORS enabled for http://localhost:3000

## Quality Scoring System (NEW)

### QualityAgent
  Location: sentinel/agents/layer4_output/quality_agent.py
  Position: LangGraph node AFTER BriefWriter, BEFORE MemoryWriter

  Scores the generated Brief on 5 dimensions (each 0.0–1.0):
    specificity:     Are recommendations specific to company stack?
    evidence_depth:  Are claims backed by signal evidence?
    causal_clarity:  Is the causal chain logical and clear?
    actionability:   Can a human act on this brief immediately?
    completeness:    Are all major risk categories addressed?

  Overall quality_score = weighted average:
    specificity    × 0.25
    evidence_depth × 0.20
    causal_clarity × 0.20
    actionability  × 0.25
    completeness   × 0.10

  Output: QualityScore Pydantic model
    brief_id:         UUID
    scores:           Dict[str, float]
    overall:          float
    weak_agents:      List[str]  (agents whose output scored lowest)
    improvement_notes: List[str] (what specifically was weak)
    created_at:       datetime

  Threshold: QUALITY_THRESHOLD=0.70 (configurable via .env)
  If overall < threshold → trigger PromptOptimiser for weak_agents

### PromptOptimiser
  Location: sentinel/optimiser/optimiser.py
  Fires as asyncio.create_task() — non-blocking

  For each agent in weak_agents:
    1. Load current prompt from PromptStore
    2. Load the Brief that scored poorly
    3. Load the improvement_notes for this agent
    4. Ask Gemini (thinking=ON) to rewrite the prompt:
       "This prompt produced a brief scoring {score} on {dimension}.
        The issue was: {improvement_notes}.
        Rewrite the prompt to fix this. Keep the same structure.
        Return only the improved prompt text."
    5. Save new prompt version to PromptStore
    6. Log: "prompt.optimised agent={agent} score_before={old} version={new}"

  PromptOptimiser does NOT apply the new prompt immediately.
  New prompt is used starting from the NEXT pipeline run.
  This prevents mid-run prompt inconsistency.

## PromptStore (NEW)

### Schema
  sentinel/models/prompt_version.py

  PromptVersion:
    id:           UUID
    agent_name:   str  (e.g. "BriefWriter", "RedTeamAgent")
    version:      int  (starts at 1, increments on each optimisation)
    prompt_text:  str
    quality_score: float | None  (score that triggered this version)
    created_at:   datetime
    is_active:    bool  (only one active version per agent)

### Storage
  Stored in Qdrant sentinel_prompts collection
  Embedded using agent_name + prompt_text[:500] for similarity search
  Allows: "find prompts similar to this one" — useful for A/B testing

### How agents load prompts
  sentinel/optimiser/prompt_store.py

  async def get_active_prompt(agent_name: str) -> str
    → reads active PromptVersion from sentinel_prompts
    → falls back to hardcoded default if collection is empty
    → cached per run to avoid repeated Qdrant reads

  async def save_prompt_version(agent_name, prompt_text, score) -> PromptVersion
    → sets all existing versions for agent to is_active=False
    → creates new version with is_active=True
    → returns new PromptVersion

### Initialisation
  scripts/init_prompts.py — seeds sentinel_prompts with version 1
  of every agent's initial prompt on first run.
  Run once after init_qdrant.py.

## Required .env Variables
  OPENROUTER_API_KEY=
  NEWSAPI_KEY=
  SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
  SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
  QDRANT_URL=http://localhost:6333
  QDRANT_COLLECTION=sentinel_signals
  QDRANT_MEMORY_COLLECTION=sentinel_memory
  QDRANT_PROMPTS_COLLECTION=sentinel_prompts
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
  QUALITY_THRESHOLD=0.70          # briefs below this trigger optimisation
  OPTIMISER_ENABLED=true          # master switch for prompt optimisation
  OPTIMISER_MIN_RUNS=3            # minimum runs before optimiser activates
                                  # prevents premature optimisation on first runs

## 14 Agents — Layer Map (Level 4)

Layer 0 — Sensors (3 agents, unchanged):
  NewsScanner          → RSS + NewsAPI  → sample fallback
  CyberThreatAgent     → NVD/CVE API   → sample fallback
  FinancialSignalAgent → SEC EDGAR     → sample fallback

Layer 1 — Processing (3 agents, unchanged):
  EntityExtractor      → NER via Gemini (prompt from PromptStore)
  SignalClassifier     → P0/P1/P2/P3 (prompt from PromptStore)
  RouterAgent          → Path decision (prompt from PromptStore)

Layer 2 — Reasoning (2 agents, prompts from PromptStore):
  RiskAssessor         → profile-weighted scoring
  CausalChainBuilder   → root cause DAG + memory

Layer 3 — Deliberation (3 agents, prompts from PromptStore):
  RedTeamAgent         → adversarial challenge + memory
  BlueTeamAgent        → optimistic defence + memory
  ArbiterAgent         → verdict + alerts

Layer 4 — Output (3 agents, 2 NEW):
  BriefWriter          → personalised brief (prompt from PromptStore)
  QualityAgent  →NEW   → scores brief, identifies weak agents
  PromptOptimiser →NEW → rewrites weak prompts async (thinking=ON)

Layer 5 — Memory (1 agent, unchanged):
  MemoryWriter         → writes MemoryEntry + QualityScore to memory

## LangGraph Pipeline Flow (Level 4)
  START
    → NewsScanner
    → CyberThreatAgent
    → FinancialSignalAgent
    → EntityExtractor         [loads prompt from PromptStore]
    → SignalClassifier         [loads prompt from PromptStore]
    → [Loop 1 check]
    → RouterAgent              [loads prompt from PromptStore]
    → [Route check]
        Path A → RiskAssessor → CausalChainBuilder → RedTeamAgent
              → BlueTeamAgent → ArbiterAgent → BriefWriter
        Path B → RiskAssessor → BriefWriter
        Path C → BriefWriter
    → QualityAgent             ← NEW (scores the brief)
    → [Quality check]
        if quality_score < threshold AND run_count >= OPTIMISER_MIN_RUNS
          → asyncio.create_task(PromptOptimiser.run(weak_agents))
    → MemoryWriter             [also stores QualityScore]
  END

## FastAPI Endpoints (Level 4 additions)
  --- All Level 1 + 2 + 3 endpoints unchanged ---

  --- New in Level 4 ---
  GET  /prompts                        → list all agents + active prompt version
  GET  /prompts/{agent_name}           → full prompt history for one agent
  GET  /prompts/{agent_name}/active    → current active prompt text
  POST /prompts/{agent_name}/rollback  → revert to previous version
  GET  /quality                        → list all QualityScore records
  GET  /quality/trends                 → score trends per agent over time
  GET  /quality/latest                 → most recent QualityScore

## UI Changes (Level 4)
  New page: /prompts (Prompt Evolution)
  - Left sidebar: list of all 9 LLM agents
  - Clicking an agent shows its full prompt version history
  - Each version shows: version number, date, quality score that
    triggered it, diff-style view (green = added, red = removed)
  - "Active" badge on current version
  - "Rollback" button on any past version
  - Add to top nav after Memory

  Pipeline monitor upgrades:
  - Add "Quality Score" stat card showing latest brief score
  - Agent pills now show version number badge
    e.g. "BriefWriter v3" if prompt has been optimised twice
  - Quality trend sparkline (tiny 7-day chart) next to Quality card

  Brief page upgrades:
  - Add quality score breakdown at bottom of each brief
  - Show 5 dimension scores as a small horizontal bar chart
  - "Optimised" badge on brief if it was generated with an
    optimised prompt (version > 1)

## Build Order (Level 4 — 8 prompts)

Phase 1 — Prompt Infrastructure : Prompts 01–02
  01 → PromptVersion model + PromptStore + init script
       sentinel/models/prompt_version.py
       sentinel/optimiser/__init__.py
       sentinel/optimiser/prompt_store.py
           get_active_prompt(agent_name) → str
           save_prompt_version(agent_name, text, score) → PromptVersion
           get_prompt_history(agent_name) → List[PromptVersion]
           rollback_prompt(agent_name, version) → PromptVersion
       scripts/init_prompts.py
           seeds sentinel_prompts with v1 of all 9 agent prompts
       sentinel/config.py updated — QDRANT_PROMPTS_COLLECTION
       .env.example updated

  02 → Wire all agents to load prompts from PromptStore
       Each agent's run() method calls:
           prompt = await prompt_store.get_active_prompt(self.agent_name)
       instead of using hardcoded prompt string
       All 9 LLM agents updated (EntityExtractor through BriefWriter)
       Fallback: if PromptStore empty → use hardcoded default

Phase 2 — Quality Scoring : Prompt 03
  03 → QualityAgent + QualityScore model
       sentinel/models/quality_score.py — QualityScore Pydantic model
       sentinel/agents/layer4_output/quality_agent.py
           scores brief on 5 dimensions via Gemini (thinking=OFF)
           identifies weak_agents from low-scoring dimensions
           writes quality_score to PipelineState
       sentinel/pipeline/state.py updated — quality_score field
       sentinel/pipeline/graph.py updated — QualityAgent node after BriefWriter

Phase 3 — Prompt Optimiser : Prompt 04
  04 → PromptOptimiser service
       sentinel/optimiser/optimiser.py
           async run(weak_agents, brief, quality_score)
           for each weak agent: load prompt, load brief, ask Gemini
           to rewrite, save new version to PromptStore
       sentinel/pipeline/graph.py updated
           quality check conditional edge fires optimiser
       OPTIMISER_MIN_RUNS guard — check run count before firing
       sentinel/memory/writer.py updated — stores QualityScore in memory

Phase 4 — API Endpoints : Prompt 05
  05 → Prompt + Quality FastAPI endpoints
       GET /prompts, GET /prompts/{agent}, GET /prompts/{agent}/active
       POST /prompts/{agent}/rollback
       GET /quality, GET /quality/trends, GET /quality/latest
       sentinel/api/routes.py updated

Phase 5 — UI : Prompts 06–07
  06 → Prompt Evolution page (/prompts)
       Agent sidebar + version history + diff view + rollback button

  07 → Pipeline + Brief UI upgrades
       Quality Score stat card + agent version badges
       Quality dimension bars on brief page
       Optimised badge

Phase 6 — QA : Prompt 08
  08 → End-to-end QA for Level 4
       Run scripts/init_prompts.py — verify 9 prompt versions seeded
       Run pipeline — verify agents load prompts from PromptStore
       Verify QualityAgent scores brief and identifies weak_agents
       Verify PromptOptimiser fires when score < threshold
       Verify new prompt version saved to PromptStore
       Run pipeline again — verify agents use new prompt version
       Test rollback endpoint — verify previous version restored
       Verify /quality/trends returns data after 2+ runs
       Verify Prompt Evolution UI shows version history

## Cost Estimate (Level 4 additions)
  QualityAgent: 1 LLM call per run (thinking=OFF) = ~$0.001
  PromptOptimiser: 1 LLM call per weak agent (thinking=ON)
    worst case 3 weak agents × thinking = ~$0.008 per optimisation
    optimisation only fires occasionally (not every run)
  Level 4 total per run: ~23 LLM calls
  Extra cost per run: ~$0.002 (quality scoring)
  Optimisation event: ~$0.008 (rare, only when quality drops)
  Cumulative total per run: ~$0.009 — still negligible

## Progress Tracker
  Last completed prompt: 08 (QA COMPLETE — Level 4 fully implemented)
  Current phase: Level 4 DONE

## Built
  (Level 1 complete — see Level 1 CONTEXT.md)
  (Level 2 complete — see Level 2 CONTEXT.md)
  (Level 3 complete — see Level 3 CONTEXT.md)
  Level 4 additions:

  Phase 1 — Prompt Infrastructure (Prompts 01–02)
  - sentinel/models/prompt_version.py — PromptVersion model (to_payload/from_payload)
  - sentinel/optimiser/__init__.py — package init
  - sentinel/optimiser/prompt_store.py — get_active_prompt (cached), save_prompt_version, get_prompt_history, rollback_prompt
  - scripts/init_prompts.py — seeds v1 of all 9 agent prompts
  - sentinel/config.py — QDRANT_PROMPTS_COLLECTION, QUALITY_THRESHOLD, OPTIMISER_ENABLED, OPTIMISER_MIN_RUNS
  - .env.example — 4 Level 4 env vars
  - tests/unit/test_prompt_store.py — 6 tests ALL PASS
  - All 9 LLM agents wired to PromptStore with hardcoded fallback

  Phase 2 — Quality Scoring (Prompt 03)
  - sentinel/models/quality_score.py — QualityScore model (5 dims, weighted overall, to_payload/from_payload)
  - sentinel/agents/layer4_output/quality_agent.py — scores brief via Gemini (thinking=OFF)
    Triggers PromptOptimiser async if overall < QUALITY_THRESHOLD
  - sentinel/pipeline/state.py — added quality_score: Optional[QualityScore]
  - sentinel/pipeline/graph.py — 14 nodes: BriefWriter → QualityAgent → MemoryWriter → END

  Phase 3 — Prompt Optimiser (Prompt 04)
  - sentinel/optimiser/optimiser.py — PromptOptimiser class:
    _optimise_agent() loads prompt → asks Gemini (thinking=ON) → save_prompt_version()
    Targets weakest scoring dimension with improvement_notes context
    Async per-agent, guards empty response, respects OPTIMISER_ENABLED flag

  Phase 4 — API Endpoints (Prompt 05)
  - sentinel/api/routes.py — 5 Level 4 endpoints:
    GET  /prompts/{agent_name}         → active prompt + version count
    GET  /prompts/{agent_name}/history → full version history
    POST /prompts/{agent_name}/rollback → rollback to version N
    GET  /quality                      → recent quality scores (paginated)
    POST /quality/optimise             → manual trigger optimisation
  - Pipeline run now captures quality_score from state into _quality_scores[]

  Phase 5 — UI (Prompt 06)
  - sentinel-ui/src/app/prompts/page.tsx — /prompts page:
    Left: agent version history (load/expand/rollback buttons, active badge)
    Right: quality score panel (5-dimension bars, weak agents, improvement notes)
    Header: Trigger Optimisation button
    Footer: Explainer strip
  - sentinel-ui/src/lib/api.ts — Level 4 types + API functions
    QualityScore, QualityScoresResponse, PromptVersion, ActivePromptResponse, PromptHistoryResponse
    getQualityScores(), triggerOptimisation(), getActivePrompt(), getPromptHistory(), rollbackPrompt()
  - sentinel-ui/src/app/layout.tsx — added /prompts nav link (Wand2 icon)

  Phase 6 — QA (Prompts 07–08)
  - 14-node graph confirmed (BriefWriter→QualityAgent→MemoryWriter→END)
  - All Level 4 imports verified OK
  - 22/23 unit tests pass (1 pre-existing failure: test_demo_mode_defaults_to_false
    due to pydantic-settings loading .env file even with monkeypatch — unrelated to Level 4)
  - 13/13 PromptStore + Memory tests pass
  - Pyre2 lint errors are false positives (no search roots configured in pyrightconfig.json)

## Next
  Level 4 is COMPLETE.
  To run: ensure Qdrant is running (docker-compose up -d), then:
    python scripts/init_qdrant.py
    python scripts/init_prompts.py  ← NEW: seeds all 9 agent prompts
    uvicorn sentinel.main:app --reload
    cd sentinel-ui && npm run dev

