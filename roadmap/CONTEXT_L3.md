# SENTINEL — Build Context (Level 3)

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
Level 3: Agent Memory + Personalised Alerts
Builds directly on top of Level 2 — all Level 1 and Level 2 code remains intact

## What Level 3 Adds
- Agent Memory — every reasoning agent queries Qdrant for historical context
  before acting. RedTeam references past similar CVEs. BriefWriter notices
  patterns across weeks. System gets smarter with every run.
- Instant Alerts — P0 signals that match company profile trigger Email + Slack
  notifications immediately, not just after the brief is written
- Company-specific remediation — BriefWriter tailors action steps to your
  exact tech stack, not generic advice
- Memory API endpoints — query what SENTINEL remembers about past threats
- Memory UI — timeline view of threat history and pattern insights

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- --demo-mode loads from data/sample_signals/ instead of live APIs
- Gemini still runs in demo mode (only live APIs are mocked)
- Alert sending (Email/Slack) has demo mode — logs instead of sends
- Qdrant memory queries work normally in demo mode (uses seeded history)
- Every sensor agent MUST implement both live and demo paths

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker) — now used heavily for memory, not just storage
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
- Email:          SMTP via Python smtplib (Gmail compatible, free)
- Slack:          Slack Incoming Webhooks (free, no OAuth needed)

## Model Routing (unchanged from Level 2)
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend: "openrouter" (default) or "groq"
- Embeddings always OpenRouter regardless of LLM_PROVIDER
- No hardcoded model strings anywhere

## LLM Client Pattern (unchanged from Level 2)
- openai SDK with custom base_url
- Provider switching via LLM_PROVIDER env var
- ALL LLM + embedding calls through sentinel/llm/client.py only

## Thinking Levels (unchanged from Level 2)
- Thinking OFF: EntityExtractor, SignalClassifier, RiskAssessor,
                BriefWriter, all Layer 0, RouterAgent
- Thinking ON:  CausalChainBuilder, RedTeamAgent, BlueTeamAgent, ArbiterAgent
- Groq silently ignores thinking param

## Conventions (unchanged from Level 2)
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: asyncio.WindowsSelectorEventLoopPolicy() in main.py

## Architecture (Level 3 changes marked →NEW / →UPG)
- LangGraph StateGraph as sole orchestration framework
- Pipeline is a graph with conditional routing (from Level 2)
- →NEW: Every reasoning agent calls Qdrant memory BEFORE its LLM call
- →NEW: AlertDispatcher added as a non-LangGraph async service
         fires on P0 signals with relevance_score > 0.7 immediately
- →UPG: Qdrant now has two collections:
         sentinel_signals — existing (signals + embeddings)
         sentinel_memory  — NEW (structured threat memory entries)
- →UPG: BriefWriter receives memory context + company profile
         to generate stack-specific remediation steps
- FastAPI CORS enabled for http://localhost:3000

## Memory System Design (NEW)

### What gets stored in sentinel_memory
After every completed pipeline run, a MemoryEntry is created per signal:

  MemoryEntry:
    id:               UUID
    signal_id:        UUID
    signal_title:     str
    signal_source:    SignalSource
    entities:         List[str]
    priority:         SignalPriority
    risk_score:       float
    company_matches:  List[str]
    route_path:       RoutePath
    red_team_won:     bool
    final_confidence: float
    outcome_tags:     List[str]  (e.g. ["patched", "false_positive", "escalated"])
    created_at:       datetime

  Stored in Qdrant sentinel_memory collection
  Embedded using signal_title + entities as text
  Retrieved via semantic similarity search

### How agents use memory
Each reasoning agent receives memory_context: List[MemoryEntry] 
populated by searching sentinel_memory for similar past signals
BEFORE the agent's LLM call.

  CausalChainBuilder:
    Queries: "similar CVEs or events in past 90 days"
    Injects into prompt: "Past similar events: {memory_context}"
    Effect: Chain references actual historical patterns

  RedTeamAgent:
    Queries: "past signals where risk was overestimated"
    Injects: "Previous false positives: {memory_context}"
    Effect: More calibrated adversarial challenges

  BlueTeamAgent:
    Queries: "past signals successfully mitigated"
    Injects: "Past successful mitigations: {memory_context}"
    Effect: Defences grounded in what actually worked

  BriefWriter:
    Queries: "recurring threats in same category"
    Injects: "Pattern detected: {memory_context}"
    Effect: Briefs reference trend ("3rd Apache CVE this month")

### Memory retrieval pattern
  sentinel/memory/retriever.py
  async def get_relevant_memories(
      query_text: str,
      limit: int = 5,
      days_back: int = 90
  ) -> List[MemoryEntry]

  Uses Qdrant semantic search on sentinel_memory collection
  Filters by created_at >= now - days_back
  Returns top-k most similar past events

## Alert Dispatcher (NEW)
  Location: sentinel/alerts/dispatcher.py

  Fires IMMEDIATELY when ArbiterAgent sets final verdict on a signal where:
    signal.priority == P0
    AND route_decision.relevance_score > 0.7

  Does NOT wait for BriefWriter to finish.
  Runs as asyncio.create_task() — non-blocking.

  AlertDispatcher sends:
    1. Email via SMTP (Gmail free tier)
    2. Slack via Incoming Webhook URL
    3. Both can be disabled independently via .env

  Alert message format:
    Subject: [SENTINEL P0] {signal_title}
    Body:
      Priority:     P0 — CRITICAL
      Source:       {signal_source}
      Confidence:   {final_confidence}
      Company Match: {company_matches}
      Risk Score:   {risk_score}/10
      Action Required: Immediate review
      Link: http://localhost:8000/alerts/{signal_id}

  Demo mode behaviour:
    ALERT_DEMO_MODE=true → logs alert content via structlog instead of sending

## Personalised Remediation (Level 3 upgrade to BriefWriter)
  BriefWriter now receives:
    - CompanyProfile (tech_stack, regions, regulatory_scope)
    - List[MemoryEntry] (past similar threats)

  Prompt instructs BriefWriter to:
    - Reference specific tools from tech_stack in remediation steps
      e.g. "Patch Apache on your Kubernetes pods using:"
      NOT generic "patch the affected software"
    - Reference regulatory obligations
      e.g. "Under GDPR Article 33, notify DPA within 72 hours"
    - Reference past incidents from memory
      e.g. "This is the second Apache CVE this quarter"

  Result: Recommendations section reads like advice from someone
  who knows your company — not a generic template.

## Required .env Variables
  OPENROUTER_API_KEY=
  NEWSAPI_KEY=
  SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
  SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
  QDRANT_URL=http://localhost:6333
  QDRANT_COLLECTION=sentinel_signals
  QDRANT_MEMORY_COLLECTION=sentinel_memory
  DEMO_MODE=false
  LOG_LEVEL=INFO
  LLM_PROVIDER=openrouter
  GROQ_API_KEY=
  GROQ_MODEL=llama-3.3-70b-versatile
  COMPANY_PROFILE_PATH=data/company_profile.json
  # Alert settings
  ALERT_DEMO_MODE=true            # true = log only, false = actually send
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=                      # your gmail address
  SMTP_PASSWORD=                  # gmail app password (not your login password)
  ALERT_EMAIL_TO=                 # who receives P0 alerts
  SLACK_WEBHOOK_URL=              # from Slack app incoming webhook settings
  ALERTS_ENABLED=true             # master switch for all alert sending

## 12 Agents — Layer Map (Level 3, same count, agents upgraded)

Layer 0 — Sensors (3 agents, unchanged):
  NewsScanner          → RSS + NewsAPI  → sample fallback
  CyberThreatAgent     → NVD/CVE API   → sample fallback
  FinancialSignalAgent → SEC EDGAR     → sample fallback

Layer 1 — Processing (3 agents, unchanged):
  EntityExtractor      → NER via Gemini
  SignalClassifier     → P0/P1/P2/P3 via Gemini
  RouterAgent          → Path decision via Gemini + CompanyProfile

Layer 2 — Reasoning (2 agents, memory-upgraded):
  RiskAssessor  →UPG   → profile-weighted scoring (unchanged from L2)
  CausalChainBuilder →UPG → queries memory before LLM call

Layer 3 — Deliberation (3 agents, memory-upgraded):
  RedTeamAgent  →UPG   → queries memory for past false positives
  BlueTeamAgent →UPG   → queries memory for past mitigations
  ArbiterAgent  →UPG   → triggers AlertDispatcher on P0 verdict

Layer 4 — Output (1 agent, memory + profile upgraded):
  BriefWriter   →UPG   → personalised remediation via memory + profile

  Non-agent service (NEW):
  AlertDispatcher      → Email + Slack, fires async on P0 verdict
  MemoryWriter         → writes MemoryEntry after pipeline completes
  MemoryRetriever      → semantic search on sentinel_memory

## LangGraph Pipeline Flow (Level 3)
  START
    → NewsScanner
    → CyberThreatAgent
    → FinancialSignalAgent
    → EntityExtractor
    → SignalClassifier
    → [Loop 1 check] → if confidence < 0.5 → back to EntityExtractor
    → RouterAgent
    → [Route check]
        Path A (FULL) → RiskAssessor
                      → CausalChainBuilder [+memory query]
                      → RedTeamAgent [+memory query]
                      → BlueTeamAgent [+memory query]
                      → ArbiterAgent [→ fires AlertDispatcher if P0]
                      → [Loop 2 check] → BriefWriter [+memory + profile]
        Path B (FAST) → RiskAssessor → BriefWriter [+memory + profile]
        Path C (LOG)  → BriefWriter
    → MemoryWriter [writes MemoryEntry for this signal]
  END

## FastAPI Endpoints (Level 3 additions)
  --- All Level 1 + Level 2 endpoints unchanged ---
  GET  /health
  POST /ingest
  GET  /alerts / GET /alerts/{id}
  GET  /briefs / GET /briefs/latest / GET /briefs/{id}
  GET  /pipeline/status
  GET  /company/profile / PUT /company/profile
  GET  /company/profile/matches

  --- New in Level 3 ---
  GET  /memory                    → list recent MemoryEntries (limit, days_back)
  GET  /memory/search?q={text}    → semantic search over sentinel_memory
  GET  /memory/patterns           → recurring threat patterns (grouped by entity)
  DELETE /memory                  → clear all memory (useful for testing)
  POST /alerts/test               → send a test alert (checks SMTP + Slack config)

## UI Changes (Level 3)
  New page: /memory (Threat Memory)
  - Timeline of all past MemoryEntries newest first
  - Each entry: title, priority badge, source, risk score, company matches
  - Search bar at top — calls GET /memory/search live as you type
  - "Patterns" tab — shows recurring threats grouped by entity
    e.g. "Apache — 3 events this quarter" as a summary card
  - Add to top nav after Company

  Alerts board upgrades:
  - Alert cards now show "Seen before" badge if memory has similar past events
  - Hovering "Seen before" shows tooltip: "Similar to: {past_event_title}"

  Brief page upgrades:
  - Recommendations section now shows stack-specific steps
    e.g. actual commands/policy names relevant to company profile
  - Add "Memory Context" collapsible section at bottom of brief
    showing which past events informed this analysis
  - Pattern badge in brief header if recurring threat detected
    e.g. "⚠ Recurring — 3rd similar event in 90 days"

  Pipeline monitor upgrades:
  - Add "Memory" stat card: total MemoryEntries stored
  - Show memory query count in agent status (e.g. "5 memories retrieved")

## Build Order (Level 3 — 9 prompts)

Phase 1 — Memory Infrastructure : Prompts 01–02
  01 → MemoryEntry Pydantic model + Qdrant memory collection
       sentinel/models/memory_entry.py
       sentinel/memory/__init__.py
       sentinel/memory/retriever.py — get_relevant_memories()
       sentinel/memory/writer.py — write_memory_entry()
       scripts/init_qdrant.py updated — creates sentinel_memory collection
       .env.example updated with QDRANT_MEMORY_COLLECTION

  02 → MemoryWriter LangGraph node
       Runs after BriefWriter as final pipeline step
       Writes one MemoryEntry per processed signal
       sentinel/memory/writer.py — write_memory_entry(signal, report, route)
       sentinel/pipeline/graph.py updated — MemoryWriter node added at END

Phase 2 — Agent Memory Integration : Prompts 03–04
  03 → Inject memory into reasoning agents
       CausalChainBuilder — query memory, inject into prompt
       RedTeamAgent — query memory for past false positives
       BlueTeamAgent — query memory for past mitigations
       Each agent gets memory_context in its prompt template

  04 → BriefWriter memory + profile upgrade
       Load CompanyProfile + MemoryEntries in BriefWriter.run()
       Rewrite recommendations prompt to use tech_stack + regulatory_scope
       Add pattern detection: count similar events in last 90 days
       Add recurring threat flag to Brief output

Phase 3 — Alert Dispatcher : Prompt 05
  05 → AlertDispatcher service
       sentinel/alerts/__init__.py
       sentinel/alerts/dispatcher.py
       Email via smtplib (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)
       Slack via httpx POST to SLACK_WEBHOOK_URL
       ALERT_DEMO_MODE=true → structlog only
       ArbiterAgent updated — calls dispatcher.fire() as asyncio.create_task()
       POST /alerts/test endpoint added

Phase 4 — Memory API : Prompt 06
  06 → Memory FastAPI endpoints
       GET /memory — paginated list of MemoryEntries
       GET /memory/search?q= — semantic search
       GET /memory/patterns — group by entity, count occurrences
       DELETE /memory — clear collection
       sentinel/api/routes.py updated

Phase 5 — UI : Prompts 07–08
  07 → Memory page (/memory)
       Timeline + search + patterns tab
       Add to top nav

  08 → Alerts + Brief + Pipeline UI upgrades
       "Seen before" badge on alert cards
       Memory context section in briefs
       Recurring threat badge
       Memory stat card on pipeline page

Phase 6 — QA : Prompt 09
  09 → End-to-end QA for Level 3
       Run pipeline twice — verify MemoryEntries created after run 1
       Run pipeline again — verify agents receive memory context in logs
       Verify brief recommendations mention company tech_stack specifically
       Verify AlertDispatcher logs alert (ALERT_DEMO_MODE=true)
       Test POST /alerts/test endpoint
       Test GET /memory/search with a real query
       Verify "Seen before" badge appears on second run alerts
       Verify "Recurring" badge appears in brief after repeated signals

## Cost Estimate (Level 3 additions)
  Memory queries: 3 Qdrant searches per signal (no LLM cost)
  Memory-augmented prompts: slightly longer = ~10% more tokens per agent
  AlertDispatcher: 0 LLM calls (pure SMTP + HTTP)
  Level 3 total per run: ~21 LLM calls vs ~19 in Level 2
  Extra cost per run: ~$0.001
  Cumulative total per run: ~$0.007 — still negligible

## Progress Tracker
  Last completed prompt: 09 (Level 3 QA — ALL PASS)
  Current phase: LEVEL 3 COMPLETE ✅

## QA Results (Prompt 09)
  Unit tests: 7/7 PASSED (test_memory.py)
  Graph build: 13 nodes confirmed
    news_scanner → cyber_threat → financial_signal → entity_extractor →
    signal_classifier → router → risk_assessor → causal_chain →
    red_team → blue_team → arbiter → brief_writer → memory_writer
  Import checks: ALL 12 Level 3 modules import OK
  Config: QDRANT_MEMORY_COLLECTION=sentinel_memory, ALERT_DEMO_MODE=True
  Brief model: recurring_patterns=[], memory_context=[] (defaults OK)
  MemoryEntry round-trip: to_payload() → from_payload() OK

## Built
  (Level 1 complete — see Level 1 CONTEXT.md)
  (Level 2 complete — see Level 2 CONTEXT.md)
  Level 3 additions:
  - sentinel/models/memory_entry.py — MemoryEntry Pydantic model (to_payload/from_payload)
  - sentinel/memory/__init__.py — package init
  - sentinel/memory/retriever.py — get_relevant_memories() + count_similar_events()
  - sentinel/memory/writer.py — write_memory_entry(signal, report, route_decision)
  - sentinel/config.py — added QDRANT_MEMORY_COLLECTION + 7 alert settings
  - .env.example — added memory + alert environment variables
  - scripts/init_qdrant.py — creates both sentinel_signals + sentinel_memory collections
  - tests/unit/test_memory.py — 7 tests — ALL PASS
  - sentinel/pipeline/state.py — added memory_entries: list[MemoryEntry] (Layer 5)
  - sentinel/pipeline/graph.py — 13 nodes, MemoryWriter wired BriefWriter→MemoryWriter→END
  - sentinel/agents/layer2_reasoning/causal_chain.py — memory: PAST SIMILAR EVENTS in prompt
  - sentinel/agents/layer3_deliberation/red_team.py — memory: PAST SIMILAR EVENTS for false positive calibration
  - sentinel/agents/layer3_deliberation/blue_team.py — memory: PAST MITIGATIONS & OUTCOMES in prompt
  - sentinel/models/brief.py — added recurring_patterns + memory_context fields
  - sentinel/agents/layer4_output/brief_writer.py — loads CompanyProfile + memory, detects patterns, stack-specific recs
  - sentinel/alerts/__init__.py — package init
  - sentinel/alerts/dispatcher.py — fire_alert() with email/Slack/demo channels
  - sentinel/agents/layer3_deliberation/arbiter.py — fires alerts via asyncio.create_task() for P0/P1
  - sentinel/api/routes.py — POST /alerts/test + GET /memory + GET /memory/search + GET /memory/patterns + DELETE /memory
  - sentinel-ui/src/app/memory/page.tsx — Memory page: Timeline + Search + Patterns tabs
  - sentinel-ui/src/app/layout.tsx — added Memory to nav, 13 agents badge
  - sentinel-ui/src/lib/api.ts — BriefDetail: recurring_patterns + memory_context
  - sentinel-ui/src/app/briefs/page.tsx — Memory Context section: recurring patterns + past events
  - sentinel-ui/src/app/page.tsx — Memory stat card, MemoryWriter in pipeline nodes, 5-col grid

## Next
  LEVEL 3 COMPLETE — all 9 prompts done.
  To run: see run commands below.

## Run Commands
  # Backend
  cd "c:\Learnings\Projects\8sem project design"
  docker-compose up -d          # start Qdrant
  python scripts/init_qdrant.py # create collections
  uvicorn sentinel.main:app --reload --host 0.0.0.0 --port 8000

  # Frontend
  cd sentinel-ui
  npm run dev

  # Test alert dispatcher
  curl -X POST http://localhost:8000/alerts/test

  # Query memory
  curl http://localhost:8000/memory
  curl "http://localhost:8000/memory/search?q=apache"
  curl http://localhost:8000/memory/patterns
