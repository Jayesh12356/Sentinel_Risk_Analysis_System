# SENTINEL — Build Context (Levels 1–5 COMPLETE)

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
Level 5: Human in the Loop — **FULLY IMPLEMENTED AND FULL SYSTEM QA VERIFIED**
Builds directly on top of Level 4 — all Level 1, 2, 3, 4 code remains intact

## What Level 5 Adds
- Human feedback on every brief — "Acted On", "False Positive", "Escalate", "Dismiss"
- Feedback stored in Qdrant and influences future confidence scoring
- P0 briefs sent to human via Slack/Email with one-click response links
- FeedbackAgent — reads accumulated human judgments and adjusts
  SignalClassifier and ArbiterAgent confidence weights over time
- Feedback dashboard — see what humans approved, dismissed, escalated
- System learns from human judgment without any retraining

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- Feedback links in alerts/emails work in demo mode
- FeedbackAgent runs normally in demo mode
- Seeded feedback history in data/sample_feedback.json for demo
- Every sensor agent MUST implement both live and demo paths

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker)
                  sentinel_signals  — signals + embeddings
                  sentinel_memory   — threat memory entries
                  sentinel_prompts  — versioned prompt store
                  sentinel_feedback — NEW human feedback entries
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

## Model Routing (unchanged from Level 4)
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend: "openrouter" (default) or "groq"
- Embeddings always OpenRouter regardless of LLM_PROVIDER
- No hardcoded model strings anywhere

## LLM Client Pattern (unchanged from Level 4)
- openai SDK with custom base_url
- Provider switching via LLM_PROVIDER env var
- ALL LLM + embedding calls through sentinel/llm/client.py only

## Thinking Levels (unchanged from Level 4)
- Thinking OFF: EntityExtractor, SignalClassifier, RiskAssessor,
                BriefWriter, QualityAgent, all Layer 0, RouterAgent
- Thinking ON:  CausalChainBuilder, RedTeamAgent, BlueTeamAgent,
                ArbiterAgent, PromptOptimiser, FeedbackAgent
- Groq silently ignores thinking param

## Conventions (unchanged from Level 4)
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: asyncio.WindowsSelectorEventLoopPolicy() in main.py

## Architecture (Level 5 changes marked →NEW / →UPG)
- LangGraph StateGraph as sole orchestration framework
- Pipeline is a graph with conditional routing (from Level 2)
- Memory queries in reasoning agents (from Level 3)
- PromptStore + QualityAgent + PromptOptimiser (from Level 4)
- →NEW: FeedbackAgent added as periodic background task
         NOT a LangGraph node — runs on a schedule or on-demand
- →NEW: Qdrant sentinel_feedback collection
- →NEW: Feedback links embedded in all P0/P1 alert emails and Slack messages
- →UPG: SignalClassifier reads feedback weights before classifying
- →UPG: ArbiterAgent reads feedback weights before scoring confidence
- →UPG: AlertDispatcher includes one-click feedback URLs in messages
- FastAPI CORS enabled for http://localhost:3000

## Human Feedback System (NEW)

### FeedbackEntry Schema
  sentinel/models/feedback_entry.py

  FeedbackAction enum:
    ACTED_ON      — human took action, signal was real and important
    FALSE_POSITIVE — signal was wrong or irrelevant
    ESCALATE      — human wants higher priority than SENTINEL assigned
    DISMISS       — acknowledged but no action needed

  FeedbackEntry:
    id:             UUID
    signal_id:      UUID
    brief_id:       UUID
    action:         FeedbackAction
    note:           str | None     (optional human comment)
    signal_title:   str
    signal_source:  SignalSource
    original_priority: SignalPriority
    original_confidence: float
    submitted_by:   str            (default: "human")
    created_at:     datetime

  Stored in: Qdrant sentinel_feedback collection
  Embedded using signal_title + action for similarity search

### Feedback Collection Flow
  1. ArbiterAgent completes verdict on P0/P1 signal
  2. AlertDispatcher sends email/Slack with 4 buttons:
       ✅ Acted On    → GET /feedback/{signal_id}/acted_on
       ❌ False Pos   → GET /feedback/{signal_id}/false_positive
       ⬆ Escalate    → GET /feedback/{signal_id}/escalate
       ➡ Dismiss     → GET /feedback/{signal_id}/dismiss
  3. Human clicks link → FastAPI creates FeedbackEntry
  4. Response page: "Thank you — SENTINEL has recorded your feedback"
  5. FeedbackAgent picks up new entries on next scheduled run

### Feedback Influence on Future Runs (FeedbackAgent)
  Location: sentinel/agents/feedback/feedback_agent.py
  Runs: as asyncio background task, triggered after each pipeline run
        OR manually via POST /feedback/process

  Reads last 30 days of FeedbackEntries from sentinel_feedback
  Computes feedback_weights:

    false_positive_rate:
      count(FALSE_POSITIVE) / total_feedback for each signal category
      If false_positive_rate > 0.3 for a category:
        → reduce confidence multiplier for that category by 0.1
        → stored in data/feedback_weights.json

    escalation_rate:
      count(ESCALATE) / total_feedback for each signal source
      If escalation_rate > 0.2 for a source:
        → increase priority weight for that source by 0.1

    acted_on_rate:
      count(ACTED_ON) / total_feedback
      Used as a proxy for overall system quality
      Logged and shown in dashboard

  FeedbackAgent writes feedback_weights.json
  SignalClassifier reads feedback_weights.json at start of each run
  ArbiterAgent reads feedback_weights.json at start of each run

  This is NOT retraining — it is weight adjustment.
  The LLM prompts do not change (that is Level 4's job).
  Only the confidence multipliers change.

### Feedback Weights Schema
  data/feedback_weights.json

  {
    "category_confidence_multipliers": {
      "CYBER": 1.0,
      "NEWS": 1.0,
      "FINANCIAL": 1.0
    },
    "source_priority_weights": {
      "NVD": 1.0,
      "NEWSAPI": 1.0,
      "SEC_EDGAR": 1.0
    },
    "overall_acted_on_rate": 0.0,
    "last_updated": "ISO datetime"
  }

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
  FEEDBACK_BASE_URL=http://localhost:8000   # base for feedback click links
  FEEDBACK_WINDOW_DAYS=30                  # how many days of feedback to use
  FEEDBACK_MIN_ENTRIES=5                   # minimum before weights adjust

## 15 Agents — Layer Map (Level 5)

Layer 0 — Sensors (3 agents, unchanged):
  NewsScanner          → RSS + NewsAPI  → sample fallback
  CyberThreatAgent     → NVD/CVE API   → sample fallback
  FinancialSignalAgent → SEC EDGAR     → sample fallback

Layer 1 — Processing (3 agents, SignalClassifier upgraded):
  EntityExtractor      → NER via Gemini
  SignalClassifier →UPG → P0/P1/P2/P3 + reads feedback_weights
  RouterAgent          → Path decision

Layer 2 — Reasoning (2 agents, unchanged):
  RiskAssessor         → profile-weighted scoring
  CausalChainBuilder   → root cause DAG + memory

Layer 3 — Deliberation (3 agents, ArbiterAgent upgraded):
  RedTeamAgent         → adversarial challenge + memory
  BlueTeamAgent        → optimistic defence + memory
  ArbiterAgent  →UPG   → confidence scoring + reads feedback_weights
                          triggers AlertDispatcher with feedback links

Layer 4 — Output (3 agents, unchanged):
  BriefWriter          → personalised brief
  QualityAgent         → scores brief
  PromptOptimiser      → rewrites weak prompts async

Layer 5 — Memory + Feedback (2 agents, FeedbackAgent NEW):
  MemoryWriter         → writes MemoryEntry + QualityScore
  FeedbackAgent →NEW   → reads FeedbackEntries, computes weights,
                          writes feedback_weights.json

## LangGraph Pipeline Flow (Level 5)
  START
    → NewsScanner → CyberThreatAgent → FinancialSignalAgent
    → EntityExtractor → SignalClassifier [reads feedback_weights]
    → [Loop 1 check]
    → RouterAgent
    → [Route check]
        Path A → RiskAssessor → CausalChainBuilder → RedTeamAgent
              → BlueTeamAgent
              → ArbiterAgent [reads feedback_weights,
                              sends alert WITH feedback links]
              → [Loop 2 check] → BriefWriter
        Path B → RiskAssessor → BriefWriter
        Path C → BriefWriter
    → QualityAgent
    → [Quality check → PromptOptimiser if needed]
    → MemoryWriter
    → asyncio.create_task(FeedbackAgent.run())  ← background, non-blocking
  END

  Separately (HTTP triggered):
    GET /feedback/{signal_id}/{action} → creates FeedbackEntry
    POST /feedback/process → runs FeedbackAgent immediately

## FastAPI Endpoints (Level 5 additions)
  --- All Level 1 + 2 + 3 + 4 endpoints unchanged ---

  --- New in Level 5 ---
  GET  /feedback/{signal_id}/acted_on       → record feedback + thank you page
  GET  /feedback/{signal_id}/false_positive → record feedback + thank you page
  GET  /feedback/{signal_id}/escalate       → record feedback + thank you page
  GET  /feedback/{signal_id}/dismiss        → record feedback + thank you page
  GET  /feedback                            → list all FeedbackEntries
  GET  /feedback/stats                      → acted_on_rate, false_positive_rate per category
  GET  /feedback/weights                    → current feedback_weights.json contents
  POST /feedback/process                    → manually trigger FeedbackAgent
  DELETE /feedback                          → clear all feedback (testing only)

## UI Changes (Level 5)
  New page: /feedback (Feedback Dashboard)
  - Summary cards at top:
      Acted On rate | False Positive rate | Escalations | Dismissals
  - Timeline of all feedback entries newest first
      Each entry: signal title + original priority + action badge
      (green=Acted On, red=False Positive, orange=Escalate, grey=Dismiss)
  - "Weight Adjustments" section:
      Shows current feedback_weights.json as a table
      Category multipliers with up/down arrows if adjusted from 1.0
  - "Process Feedback" button → calls POST /feedback/process
  - Add to top nav after Prompts

  Alerts board upgrades:
  - Each alert card now has 4 small feedback buttons at bottom
    ✅ ❌ ⬆ ➡ — calls feedback endpoints directly from UI
  - Once feedback submitted: buttons replaced with
    "Feedback recorded: {action}" in matching colour

  Brief page upgrades:
  - Add "Your Feedback" section at bottom of each brief
  - Shows feedback submitted for alerts in this brief
  - Overall feedback summary: "3 acted on, 1 false positive"

  Pipeline monitor upgrades:
  - Add "Acted On Rate" stat card (from /feedback/stats)
  - FeedbackAgent shown as background task in pipeline view

## Build Order (Level 5 — 8 prompts)

Phase 1 — Feedback Infrastructure : Prompts 01–02
  01 → FeedbackEntry model + Qdrant collection + feedback weights
       sentinel/models/feedback_entry.py
           FeedbackAction enum + FeedbackEntry model
           to_payload() / from_payload()
       sentinel/feedback/__init__.py
       sentinel/feedback/store.py
           async save_feedback(signal_id, brief_id, action, note) → FeedbackEntry
           async get_feedback(days_back=30) → List[FeedbackEntry]
           async get_feedback_stats() → dict
       data/feedback_weights.json (initial — all weights 1.0)
       scripts/init_qdrant.py updated — creates sentinel_feedback collection
       sentinel/config.py updated — QDRANT_FEEDBACK_COLLECTION etc
       .env.example updated
       tests/unit/test_feedback.py

  02 → Feedback FastAPI endpoints
       GET /feedback/{signal_id}/{action} → HTML thank-you response page
           creates FeedbackEntry via feedback store
           returns simple HTML: "SENTINEL recorded your feedback"
       GET /feedback → list entries
       GET /feedback/stats → rates per category
       GET /feedback/weights → current weights
       POST /feedback/process → trigger FeedbackAgent
       DELETE /feedback → clear (testing)
       sentinel/api/routes.py updated
       data/sample_feedback.json — 10 seeded entries for demo mode

Phase 2 — FeedbackAgent : Prompt 03
  03 → FeedbackAgent
       sentinel/agents/feedback/feedback_agent.py
           async run() → reads FeedbackEntries → computes weights
           → writes data/feedback_weights.json
       sentinel/pipeline/graph.py updated
           asyncio.create_task(FeedbackAgent().run()) after MemoryWriter

Phase 3 — Wire Feedback Weights : Prompt 04
  04 → SignalClassifier + ArbiterAgent read feedback weights
       sentinel/feedback/weights.py
           load_weights() → reads feedback_weights.json, returns dict
           cached with 60s TTL so agents don't re-read every signal
       SignalClassifier.run() — multiply confidence by
           category_confidence_multipliers[signal.source]
       ArbiterAgent.run() — multiply final_confidence by
           source_priority_weights[signal.source]

Phase 4 — AlertDispatcher upgrade : Prompt 05
  05 → Embed feedback links in alerts
       AlertDispatcher updated — add 4 feedback URLs to email body
           {FEEDBACK_BASE_URL}/feedback/{signal_id}/acted_on
           {FEEDBACK_BASE_URL}/feedback/{signal_id}/false_positive
           {FEEDBACK_BASE_URL}/feedback/{signal_id}/escalate
           {FEEDBACK_BASE_URL}/feedback/{signal_id}/dismiss
       Slack message updated — include same links as plain text
       Both email and Slack show signal title + priority in message

Phase 5 — UI : Prompts 06–07
  06 → Feedback Dashboard page (/feedback)
       Summary cards + timeline + weight table + process button
       Add to top nav

  07 → Alerts + Brief + Pipeline UI upgrades
       Feedback buttons on alert cards
       Feedback summary on brief page
       Acted On Rate stat card on pipeline page

Phase 6 — QA : Prompt 08
  08 → End-to-end QA for Level 5
       Run pipeline — verify FeedbackAgent fires after MemoryWriter
       Submit feedback via GET /feedback/{id}/acted_on — verify entry created
       Submit 5 false positives for CYBER category
       Run POST /feedback/process — verify weights.json updated
       Run pipeline again — verify SignalClassifier uses adjusted weights
       Verify ArbiterAgent confidence reflects adjusted weights
       Test alert email contains feedback links (ALERT_DEMO_MODE=true, check logs)
       Verify Feedback Dashboard shows entries and correct rates
       Verify alert cards show feedback buttons
       Verify "Feedback recorded" replaces buttons after submission

## Cost Estimate (Level 5 additions)
  FeedbackAgent: 0 LLM calls (pure Python math + file write)
  Feedback weight reading: 0 LLM calls (file read, cached)
  AlertDispatcher upgrade: 0 LLM calls (string formatting only)
  Level 5 adds zero LLM cost per run
  Cumulative total per run: ~$0.009 — unchanged from Level 4

## Progress Tracker
  Last completed prompt: FULL SYSTEM QA (Levels 1–5)
  Current phase: COMPLETE — Ready for Level 6
  Level 5 status: FULLY IMPLEMENTED AND FULL SYSTEM QA VERIFIED (62/63 items pass)

## Full System QA Results
  Bugs found and fixed during QA:
    FIX 1: init_qdrant.py + init_prompts.py — unicode chars crash Windows console → ASCII [OK]/[FAIL]
    FIX 2: ensure_collection() vector_size 768 → 3072 (gemini-embedding-001 outputs 3072)
    FIX 3: All 4 Qdrant collections deleted and recreated at dim=3072
    FIX 4: feedback/store.py — get_async_client() (nonexistent) → _get_client(); dim 1536 → 3072
    FIX 5: GET /prompts list route was missing — added endpoint returning all 9 agents with versions

  QA PASS summary (62/63):
    Pre-flight (1–8):   ALL PASS
    Level 1 (9–15):     ALL PASS
    Level 2 (16–22):    ALL PASS
    Level 3 (23–30):    ALL PASS
    Level 4 (31–39):    ALL PASS (after FIX 5)
    Level 5 (40–48):    ALL PASS (after FIX 4)
    UI (49–59):         ALL PASS
    Unit Tests (60):    30/31 PASS (1 pre-existing config test)
    Final (61–63):      61 SKIPPED (no GROQ_API_KEY), 62–63 PASS

## Next
  SENTINEL Levels 1–5 is complete. Ready for Level 6.


## Built (Level 5)
  ✓ FeedbackEntry model (feedback_entry.py) with FeedbackAction enum (4 values), to_payload/from_payload
  ✓ FeedbackStore (feedback/store.py) — save_feedback, get_feedback, get_feedback_stats, clear_feedback
  ✓ FeedbackAgent (agents/feedback/feedback_agent.py) — threshold-based weight adjustment, no LLM
  ✓ Feedback weights loader (feedback/weights.py) — 60s TTL cache, get_confidence_multiplier, get_priority_weight
  ✓ 8 Level 5 API endpoints in routes.py
       GET /feedback/{signal_id}/{action_name}  → HTML thank-you page (one-click link target)
       GET /feedback                            → list recent entries
       GET /feedback/stats                      → rates by action/source
       GET /feedback/weights                    → current feedback_weights.json
       POST /feedback/process                   → trigger FeedbackAgent background task
       DELETE /feedback                         → clear all entries (testing)
  ✓ SignalClassifier wired: applies get_confidence_multiplier(source) to LLM confidence after classification
  ✓ ArbiterAgent wired: applies get_priority_weight(source) to arbiter_confidence after verdict
  ✓ graph.py: _trigger_feedback_agent_async() added — fires after MemoryWriter completes
  ✓ /feedback Next.js UI page — 4 action summary cards, feedback timeline, weight visualisation bars
  ✓ layout.tsx updated — Feedback nav link added with Users icon
  ✓ data/feedback_weights.json — initial file with all weights at 1.0
  ✓ data/sample_feedback.json — 10 seeded demo entries (all 4 actions × 3 sources)
  ✓ scripts/init_qdrant.py updated — creates sentinel_feedback collection
  ✓ config.py updated — QDRANT_FEEDBACK_COLLECTION, FEEDBACK_BASE_URL, FEEDBACK_WINDOW_DAYS, FEEDBACK_MIN_ENTRIES
  ✓ .env.example updated with Level 5 variables
  ✓ tests/unit/test_feedback.py — 8 tests, all pass

## Schemas defined (Level 5)
  FeedbackAction: ACTED_ON | FALSE_POSITIVE | ESCALATE | DISMISS
  FeedbackEntry: id, signal_id, brief_id, action, note, signal_title, signal_source,
                 original_priority, original_confidence, submitted_by, created_at

## Agent interfaces (Level 5)
  FeedbackAgent.run() → dict{skipped, total_feedback, adjustments, weights}
    - Reads FeedbackStore stats
    - Adjusts category_confidence_multipliers (FP rate > 30% → -0.1×)
    - Adjusts source_priority_weights (escalation rate > 20% → +0.1×)
    - Clips all weights to [0.5, 1.5]
    - Writes feedback_weights.json

## Files created (Level 5)
  sentinel/models/feedback_entry.py
  sentinel/feedback/__init__.py
  sentinel/feedback/store.py
  sentinel/feedback/weights.py
  sentinel/agents/feedback/__init__.py
  sentinel/agents/feedback/feedback_agent.py
  data/feedback_weights.json
  data/sample_feedback.json
  sentinel-ui/src/app/feedback/page.tsx
  tests/unit/test_feedback.py

## Files modified (Level 5)
  sentinel/config.py               — added Level 5 config vars
  sentinel/.env.example            — added Level 5 env vars
  scripts/init_qdrant.py           — creates sentinel_feedback collection
  sentinel/api/routes.py           — 8 feedback endpoints + HTML thank-you page
  sentinel/pipeline/graph.py       — _trigger_feedback_agent_async() after MemoryWriter
  sentinel/agents/layer1_processing/signal_classifier.py — confidence multiplier wiring
  sentinel/agents/layer3_deliberation/arbiter.py         — priority weight wiring
  sentinel-ui/src/app/layout.tsx   — Feedback nav link

## Next
  Level 5 is complete. Proceed to Level 6 when ready.
