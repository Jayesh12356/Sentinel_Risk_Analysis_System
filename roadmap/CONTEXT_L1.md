# SENTINEL — Build Context

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
11 agents · 2 feedback loops · 3 external data sources
Masters Final Project — solo build, demo-first priority

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- --demo-mode loads from data/sample_signals/ instead of live APIs
- Gemini still runs in demo mode (only live APIs are mocked)
- This guarantees demo never fails due to external API outage
- Every sensor agent MUST implement both live and demo paths

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker)
- Embeddings:     google/gemini-embedding-001 via OpenRouter
                  (OpenAI-compatible endpoint)
- API:            FastAPI
- Config:         pydantic-settings
- Logging:        structlog
- Python:         3.11+, async throughout
- OS:             Windows 11 (native)
- UI Framework:   Next.js 14 (App Router)
- UI Styling:     Tailwind CSS + shadcn/ui
- UI Data Flow:   react-flow (causal chain DAG)
- UI connects to: FastAPI on http://localhost:8000

## Eliminated (too risky for solo build)
- NO DSPy          (unstable APIs, not needed for demo)
- NO AutoGen       (replaced by LangGraph nodes)
- NO CrewAI        (replaced by LangGraph nodes)
- NO LlamaIndex    (replaced by direct Qdrant calls)
- NO live social sentiment API (Reddit/Glassdoor unreliable)
- NO live supply chain API (no free stable source)
- NO regulatory agent (complex parsing, unstable)
- NO feedback loops 3, 4, 5 (not needed for demo)
- NO MemoryConsolidator (DSPy dependency removed)
- NO CompetitorProfiler (nice to have, not core)
- NO OpportunityDetector (nice to have, not core)

## Model Routing
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend is used for completions: "openrouter" (default) or "groq"
- Groq uses GROQ_API_KEY + GROQ_MODEL; OpenRouter uses OPENROUTER_API_KEY + SENTINEL_PRIMARY_MODEL
- Embeddings always go through OpenRouter regardless of LLM_PROVIDER (Groq has no embeddings endpoint)
- No hardcoded model strings anywhere
- Always reference settings.SENTINEL_PRIMARY_MODEL / settings.GROQ_MODEL via client.py

## LLM Client Pattern (CRITICAL — affects Prompt 01)
- Use openai SDK with custom base_url — NOT google-generativeai SDK
- Provider switching via LLM_PROVIDER env var:
    if LLM_PROVIDER == "groq":  base_url = "https://api.groq.com/openai/v1"
    else (openrouter):          base_url = "https://openrouter.ai/api/v1"
- OpenRouter headers: {"HTTP-Referer": "sentinel", "X-Title": "SENTINEL"}
- Embeddings: always OpenRouter — client.embeddings.create(model=settings.SENTINEL_EMBEDDING_MODEL, input=text)
- ALL LLM + embedding calls go through sentinel/llm/client.py only — never direct SDK in agents
- Startup log: "llm.provider.active  provider=<provider>  model=<model>"

## Thinking Levels (Gemini 3 Flash — configurable per agent)
- Thinking OFF (fast + cheap) — default for most agents:
    EntityExtractor, SignalClassifier, RiskAssessor, BriefWriter, all Layer 0
- Thinking ON (deep reasoning) — pass extra_body={"thinking": {"type": "enabled", "budget_tokens": 8000}}:
    CausalChainBuilder, RedTeamAgent, BlueTeamAgent, ArbiterAgent
- LLM client.py must expose thinking: bool = False param that sets extra_body automatically
- When LLM_PROVIDER=groq: thinking param is silently ignored (Groq doesn't support extra_body thinking)

## Conventions
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: sentinel/main.py must set asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()) before uvicorn.run()

## Architecture (locked — do not change)
- LangGraph StateGraph as sole orchestration framework — pin langgraph>=0.2.0,<0.3.0
- All agents are LangGraph nodes in one pipeline
- Red/Blue/Arbiter are sequential LangGraph nodes (not AutoGen)
- Qdrant for all vector storage and semantic search
- FastAPI for all external endpoints
- pydantic-settings for all config
- tenacity for all retries (3 attempts, exponential 2–60s)
- FastAPI must have CORS enabled for http://localhost:3000

## Required .env Variables
  OPENROUTER_API_KEY=
  NEWSAPI_KEY=
  SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
  SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
  QDRANT_URL=http://localhost:6333
  QDRANT_COLLECTION=sentinel_signals
  DEMO_MODE=false
  LOG_LEVEL=INFO
  LLM_PROVIDER=openrouter          # "openrouter" or "groq"
  GROQ_API_KEY=
  GROQ_MODEL=llama-3.3-70b-versatile

## 11 Agents — Layer Map

Layer 0 — Sensors (3 agents):
  NewsScanner          → RSS + NewsAPI  → sample fallback
  CyberThreatAgent     → NVD/CVE API   → sample fallback
  FinancialSignalAgent → SEC EDGAR     → sample fallback

Layer 1 — Processing (2 agents):
  EntityExtractor      → NER via Gemini
  SignalClassifier     → P0/P1/P2/P3 via Gemini

Layer 2 — Reasoning (2 agents):
  RiskAssessor         → Impact × Probability × Exposure
  CausalChainBuilder   → Root cause + downstream effects

Layer 3 — Deliberation (3 agents):
  RedTeamAgent         → Adversarial challenge via Gemini
  BlueTeamAgent        → Optimistic defence via Gemini
  ArbiterAgent         → Confidence score + verdict

Layer 4 — Output (1 agent):
  BriefWriter          → Full executive intelligence brief

## 2 Feedback Loops
  Loop 1: Signal confidence < 0.5 → re-query Qdrant for
          more context → reprocess through SignalClassifier
  Loop 2: Red Team wins debate → escalate priority one level
          → re-run RiskAssessor with updated context

## Signal Priority Levels
  P0 = Critical → instant alert (logged + API response)
  P1 = High     → daily digest
  P2 = Medium   → weekly report
  P3 = Low      → logged only

## Confidence Score Thresholds
  0.85–1.00 = High     → act immediately
  0.60–0.84 = Moderate → review recommended
  0.40–0.59 = Low      → needs more data (triggers Loop 1)
  < 0.40    = Insufficient → escalate to human

## Data Schemas (Prompt 2)
  Signal      → sentinel/models/signal.py
  RiskReport  → sentinel/models/risk_report.py
  Brief       → sentinel/models/brief.py

## LangGraph Pipeline Flow
  START
    → NewsScanner
    → CyberThreatAgent
    → FinancialSignalAgent
    → EntityExtractor
    → SignalClassifier
    → [Loop 1 check] → if confidence < 0.5 → back to EntityExtractor
    → RiskAssessor
    → CausalChainBuilder
    → RedTeamAgent
    → BlueTeamAgent
    → ArbiterAgent
    → [Loop 2 check] → if Red Team wins → back to RiskAssessor
    → BriefWriter
  END

## FastAPI Endpoints (Prompt 17)
  GET  /health              → system status
  POST /ingest              → trigger manual ingestion
  GET  /alerts              → list all alerts by priority
  GET  /alerts/{id}         → single alert detail
  GET  /briefs              → list all briefs
  GET  /briefs/latest       → most recent brief
  GET  /briefs/{id}         → single brief detail
  GET  /pipeline/status     → current pipeline run status

## Build Order (18 prompts — 100% achievable solo)

Phase 1 — Foundation     : Prompts 01–04
  01 → Project scaffold + Docker + config + LLM client
  02 → Pydantic schemas (Signal, RiskReport, Brief)
  03 → BaseAgent + Qdrant client + embeddings
  04 → LangGraph pipeline skeleton + state definition

Phase 2 — Sensor Agents  : Prompts 05–07
  05 → NewsScanner (RSS + NewsAPI + demo fallback)
  06 → CyberThreatAgent (NVD API + demo fallback)
  07 → FinancialSignalAgent (SEC EDGAR + demo fallback)

Phase 3 — Processing     : Prompts 08–09
  08 → EntityExtractor (NER via Gemini)
  09 → SignalClassifier (P0–P3 via Gemini + Loop 1)

Phase 4 — Reasoning      : Prompts 10–11
  10 → RiskAssessor (scoring + evidence chain)
  11 → CausalChainBuilder (root cause DAG)

Phase 5 — Deliberation   : Prompts 12–14
  12 → RedTeamAgent (adversarial challenge)
  13 → BlueTeamAgent (optimistic defence)
  14 → ArbiterAgent (verdict + Loop 2)

Phase 6 — Output + API   : Prompts 15–17
  15 → BriefWriter (full executive report)
  16 → Sample data files (demo mode content)
  17 → FastAPI app + all routes

Phase 7 — Integration    : Prompt 18
  18 → Wire all nodes into LangGraph pipeline
       End-to-end test with demo mode
       Verify full flow: signal in → brief out

Phase 8 — UI             : Prompts 19–23
  19 → Next.js scaffold (App Router, Tailwind, shadcn/ui, react-flow)
       Lives in sentinel-ui/ at project root
       .env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
  20 → Pipeline monitor screen — live agent status, polls GET /pipeline/status every 2s
  21 → Alerts board screen — P0/P1/P2/P3 columns, cards from GET /alerts
  22 → Intelligence brief screen — causal chain react-flow DAG, debate summary, GET /briefs/latest
  23 → Polish — demo mode toggle calls POST /ingest, loading states, error handling

## Cost Estimate
  Gemini 3 Flash: $0.50/M input · $3.00/M output (via OpenRouter)
  Gemini Embedding 001: $0.15/M input
  Full build:  $8–15 realistic · $25 worst case
  Add $30 to OpenRouter — comfortable ceiling

## Built
- Last completed prompt: 23 (BUILD COMPLETE + LEVEL 1 QA PASSED)
- Project scaffold — pyproject.toml with pinned deps (no DSPy/AutoGen/CrewAI/LlamaIndex)
- Full directory structure with __init__.py stubs (agents layers 0–4, models, pipeline, db, llm)
- .env.example with all required variables
- sentinel/config.py — pydantic-settings BaseSettings with get_settings() lru_cache, _SettingsProxy for lazy module-level access, demo_mode property, LLM_PROVIDER/GROQ_API_KEY/GROQ_MODEL fields
- sentinel/llm/client.py — Provider-switchable AsyncOpenAI client (OpenRouter/Groq) with complete() and embed(), tenacity retry, structlog. Embeddings always use OpenRouter. Groq silently ignores thinking param. Startup log shows active provider.
- sentinel/main.py — FastAPI app via create_app(), --demo-mode CLI flag with cache_clear(), Windows event-loop policy, uvicorn entrypoint
- docker-compose.yml — Qdrant service on port 6333 with persistent volume
- Dockerfile — python:3.11-slim, installs from pyproject.toml
- tests/unit/test_config.py — Settings load + demo_mode default tests
- data/sample_signals/ directory for demo mode fallback data
- Pydantic schemas — Signal, RiskReport, Brief with all sub-models (Entity, RiskScore, CausalLink, DeliberationResult, BriefSection, AlertItem)
- BaseAgent abstract class — accepts demo_mode kwarg, structlog, llm_complete/llm_embed helpers, abstract run() for LangGraph nodes
- Qdrant vector store client — ensure_collection, upsert, search (auto-embed), search_by_vector, store_signal (embed+upsert)
- PipelineState TypedDict — signals, risk_reports, brief, loop counters, pipeline_status
- LangGraph StateGraph — 11 agent nodes, Loop 1 (confidence < 0.5) + Loop 2 (Red Team wins) conditional edges, MAX_SIGNALS_PER_RUN=10 guard, build_graph/compile_graph
- NewsScanner agent — RSS feeds via feedparser+httpx, NewsAPI via httpx, demo-mode JSON fallback, 4 sample articles (1 P0, 1 P2, 2 P3)
- CyberThreatAgent — NVD API v2.0 via httpx, CVSS/severity/CWE enrichment, demo-mode JSON fallback, 3 sample CVEs (1 P0, 1 P1, 1 P2)
- FinancialSignalAgent — SEC EDGAR EFTS API via httpx, monitors 8-K/10-K/10-Q, demo-mode JSON fallback, 3 sample filings (2 P1, 1 P2)
- EntityExtractor — NER via Gemini, structured JSON prompt, extracts ORG/PERSON/CVE/PRODUCT/LOCATION/EVENT/REGULATION/METRIC entities
- SignalClassifier — P0–P3 classification via Gemini, confidence scores, risk categories, Loop 1 counter increment
- RiskAssessor — risk scoring via Gemini (impact × probability × exposure), evidence gathering, RiskReport creation, Loop 2 re-run awareness
- CausalChainBuilder — root cause DAG via Gemini (thinking=ON), 3–6 CausalLink objects per report, identifies root cause
- RedTeamAgent — adversarial challenge via Gemini (thinking=ON), identifies blind spots, argues for priority escalation
- BlueTeamAgent — optimistic defence via Gemini (thinking=ON), counters Red Team, identifies mitigating factors
- ArbiterAgent — final verdict via Gemini (thinking=ON), weighs Red vs Blue, sets red_team_wins, escalates priority + increments loop2_count for Loop 2
- BriefWriter — executive brief generation via Gemini (thinking=OFF), aggregates signals + reports into Brief with sections, alerts, recommendations
- Sample data files — news.json (4 articles), cyber.json (3 CVEs), financial.json (3 filings) — 10 signals total (2 P0, 3 P1, 3 P2, 2 P3)
- FastAPI routes — 8 endpoints (health, ingest, alerts, alerts/{id}, briefs, briefs/latest, briefs/{id}, pipeline/status)
- CORS middleware — enabled for http://localhost:3000
- sentinel/main.py updated — includes API router, CORS, Windows event-loop policy
- LangGraph pipeline wired — all 11 agent nodes with demo_mode, MAX_SIGNALS_PER_RUN=10 guard in _entity_extractor wrapper
- sentinel-ui/ Next.js 14 scaffold — App Router, TypeScript, Tailwind CSS, shadcn/ui, reactflow, lucide-react
- UI .env.local — NEXT_PUBLIC_API_URL=http://localhost:8000
- UI API client — src/lib/api.ts with typed interfaces for all 8 endpoints
- UI layout — light theme (white/slate), horizontal top nav bar with lucide-react icons, Inter font, indigo (#6366f1) primary accents
- UI design — enterprise SaaS aesthetic (Linear/Vercel inspired), white cards with slate-200 borders and shadow-sm, no emojis anywhere
- Pipeline monitor screen — 4 white stat cards with colored icon accents, horizontal agent pipeline flow (pills: grey=idle, indigo=running, green=complete, red=error), prominent indigo Run Pipeline button, clean timestamps
- Alerts board screen — 4-column layout (P0/P1/P2/P3), colored left-border column headers (red/orange/yellow/slate), white alert cards with confidence progress bar at bottom, lucide-react empty states, auto-refresh 5s
- Intelligence brief screen — premium report layout, SVG confidence gauge (no library), react-flow DAG with indigo nodes and slate edges, Red Team vs Blue Team side-by-side panels with colored left borders, numbered recommendations with indigo accents, previous briefs as clean table
- UI polish — loading skeletons (slate-200 animate-pulse), responsive at 1280px/1440px, active nav highlighting
- QA Level 1 — all 19 checklist items passed (backend 11/11, frontend 7/7, tests 1/1)
- scripts/init_qdrant.py — creates sentinel_signals Qdrant collection
- pyproject.toml — fixed build-backend to setuptools.build_meta

## Schemas defined
- Signal (SignalPriority enum P0–P3, SignalSource enum, Entity sub-model)
- RiskReport (RiskScore, CausalLink, DeliberationResult sub-models)
- Brief (BriefSection, AlertItem sub-models)

## Agent interfaces
- BaseAgent (abstract) — agent_name, demo_mode, llm_complete(), llm_embed(), run(state) → state
- Qdrant client — ensure_collection(), upsert(), search(), search_by_vector(), store_signal()
- PipelineState — TypedDict with signals, risk_reports, brief, loop counters
- Pipeline graph — 11 nodes, 2 conditional loops, build_graph(), compile_graph()
- NewsScanner — run(state), _fetch_rss(), _fetch_newsapi(), _load_demo_data()
- CyberThreatAgent — run(state), _fetch_nvd(), _load_demo_data()
- FinancialSignalAgent — run(state), _fetch_edgar(), _load_demo_data()
- EntityExtractor — run(state), _extract_entities(signal), _parse_entities(raw)
- SignalClassifier — run(state), _classify_signal(signal), _parse_classification(raw)
- RiskAssessor — run(state), _assess_signal(signal), _parse_assessment(raw)
- CausalChainBuilder — run(state), _build_chain(signal, report), _parse_chain(raw)
- RedTeamAgent — run(state), _challenge(signal, report), _parse_challenge(raw)
- BlueTeamAgent — run(state), _defend(signal, report), _parse_defence(raw)
- ArbiterAgent — run(state), _arbitrate(signal, report), _parse_verdict(raw)
- BriefWriter — run(state), _generate_brief(signals, reports, data), _build_signal_data(), _parse_brief(raw)

## Files created
- pyproject.toml
- .env.example
- docker-compose.yml
- Dockerfile
- sentinel/__init__.py
- sentinel/config.py
- sentinel/main.py
- sentinel/llm/__init__.py
- sentinel/llm/client.py
- sentinel/models/__init__.py
- sentinel/agents/__init__.py
- sentinel/agents/layer0_sensors/__init__.py
- sentinel/agents/layer1_processing/__init__.py
- sentinel/agents/layer2_reasoning/__init__.py
- sentinel/agents/layer3_deliberation/__init__.py
- sentinel/agents/layer4_output/__init__.py
- sentinel/pipeline/__init__.py
- sentinel/db/__init__.py
- tests/__init__.py
- tests/unit/__init__.py
- tests/unit/test_config.py
- data/sample_signals/.gitkeep
- sentinel/models/signal.py
- sentinel/models/risk_report.py
- sentinel/models/brief.py
- sentinel/agents/base.py
- sentinel/db/qdrant_client.py
- sentinel/pipeline/state.py
- sentinel/pipeline/graph.py
- sentinel/agents/layer0_sensors/news_scanner.py
- data/sample_signals/news.json
- sentinel/agents/layer0_sensors/cyber_threat.py
- data/sample_signals/cyber.json
- sentinel/agents/layer0_sensors/financial_signal.py
- data/sample_signals/financial.json
- sentinel/agents/layer1_processing/entity_extractor.py
- sentinel/agents/layer1_processing/signal_classifier.py
- sentinel/agents/layer2_reasoning/risk_assessor.py
- sentinel/agents/layer2_reasoning/causal_chain.py
- sentinel/agents/layer3_deliberation/red_team.py
- sentinel/agents/layer3_deliberation/blue_team.py
- sentinel/agents/layer3_deliberation/arbiter.py
- sentinel/agents/layer4_output/brief_writer.py
- sentinel/api/__init__.py
- sentinel/api/routes.py
- sentinel-ui/.env.local
- sentinel-ui/src/lib/api.ts
- sentinel-ui/src/app/layout.tsx
- sentinel-ui/src/app/page.tsx
- sentinel-ui/src/app/alerts/page.tsx
- sentinel-ui/src/app/briefs/page.tsx
- sentinel-ui/src/app/loading.tsx
- sentinel-ui/src/app/alerts/loading.tsx
- sentinel-ui/src/app/briefs/loading.tsx
- scripts/init_qdrant.py

## Next
→ LEVEL 1 QA COMPLETE — All 19 checklist items pass.
   - To run: docker-compose up -d && python scripts/init_qdrant.py
   - Backend: python -m sentinel.main --demo-mode (http://localhost:8000)
   - Frontend: cd sentinel-ui && npm run dev (http://localhost:3000)
   - Trigger pipeline: POST http://localhost:8000/ingest
   - Pipeline completes in ~2.5 minutes with 10 demo signals