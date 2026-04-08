# SENTINEL — Build Context (Level 2)

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
Level 2: Company DNA + Dynamic Routing
Builds directly on top of Level 1 — all Level 1 code remains intact

## What Level 2 Adds
- CompanyProfile — who you are, what you run, who your suppliers are
- RouterAgent — LLM decides pipeline path per signal (graph not line)
- Personalised risk scoring — signals weighted by YOUR exposure
- Company Profile UI — edit your profile from the dashboard
- New FastAPI endpoints for company profile CRUD

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- --demo-mode loads from data/sample_signals/ instead of live APIs
- Gemini still runs in demo mode (only live APIs are mocked)
- This guarantees demo never fails due to external API outage
- Every sensor agent MUST implement both live and demo paths
- Demo company profile loaded from data/company_profile.json if no DB entry

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker)
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
- Profile storage: JSON file (data/company_profile.json) — no new DB needed

## Model Routing
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend: "openrouter" (default) or "groq"
- Embeddings always OpenRouter regardless of LLM_PROVIDER
- No hardcoded model strings anywhere
- RouterAgent uses LLM to decide pipeline path — uses SENTINEL_PRIMARY_MODEL

## LLM Client Pattern (unchanged from Level 1)
- openai SDK with custom base_url
- Provider switching via LLM_PROVIDER env var
- OpenRouter headers: {"HTTP-Referer": "sentinel", "X-Title": "SENTINEL"}
- ALL LLM + embedding calls through sentinel/llm/client.py only

## Thinking Levels (unchanged from Level 1)
- Thinking OFF: EntityExtractor, SignalClassifier, RiskAssessor,
                BriefWriter, all Layer 0, RouterAgent
- Thinking ON:  CausalChainBuilder, RedTeamAgent, BlueTeamAgent, ArbiterAgent
- Groq silently ignores thinking param

## Conventions (unchanged from Level 1)
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: asyncio.WindowsSelectorEventLoopPolicy() in main.py

## Architecture (Level 2 changes marked with →NEW)
- LangGraph StateGraph as sole orchestration framework
- →NEW: Pipeline is now a graph with conditional routing, not a fixed line
- →NEW: RouterAgent added after SignalClassifier as a LangGraph conditional node
- →NEW: Three pipeline paths determined by RouterAgent per signal
- Red/Blue/Arbiter remain sequential LangGraph nodes
- Qdrant for all vector storage and semantic search
- FastAPI for all external endpoints
- pydantic-settings for all config
- tenacity for all retries (3 attempts, exponential 2–60s)
- FastAPI CORS enabled for http://localhost:3000

## CompanyProfile Schema (NEW)
  sentinel/models/company_profile.py

  CompanyProfile:
    id:               str (default: "default")
    name:             str
    industry:         str
    regions:          List[str]     (e.g. ["EU", "US", "APAC"])
    tech_stack:       List[str]     (e.g. ["AWS", "Apache", "Kubernetes"])
    suppliers:        List[str]     (e.g. ["TSMC", "Azure", "Salesforce"])
    competitors:      List[str]
    regulatory_scope: List[str]     (e.g. ["GDPR", "SOC2", "HIPAA"])
    keywords:         List[str]     (custom watch terms)
    updated_at:       datetime

  Stored in: data/company_profile.json (flat file, no extra DB)
  Loaded by: sentinel/profile/manager.py on startup and cached

## RouterAgent (NEW — Layer 1.5)
  Location: sentinel/agents/layer1_processing/router.py
  Position: Inserted into LangGraph AFTER SignalClassifier

  Routing logic (LLM reads signal + company profile and decides):

  Path A — FULL pipeline (default for P0/P1 signals relevant to company)
    → RiskAssessor → CausalChainBuilder → RedTeam → BlueTeam
    → Arbiter → BriefWriter

  Path B — FAST pipeline (P2 signals OR signals with low company relevance)
    → RiskAssessor → BriefWriter
    (skips CausalChain + deliberation to save time and cost)

  Path C — LOG ONLY (P3 signals OR signals with zero company relevance)
    → BriefWriter directly
    (skips everything — just log and store)

  RouterAgent output: RouteDecision Pydantic model
    signal_id:         UUID
    path:              Enum(FULL, FAST, LOG_ONLY)
    relevance_score:   float (0.0–1.0, how relevant to company profile)
    relevance_reason:  str
    company_matches:   List[str] (which profile fields matched)

## Personalised Risk Scoring (Level 2 upgrade to RiskAssessor)
  RiskAssessor now receives CompanyProfile alongside signal + report.
  Exposure score is no longer generic — it is calculated as:

  base_exposure = generic industry exposure (0.0–1.0)
  profile_boost = 0.0

  For each match between signal entities and company profile:
    tech_stack match  → +0.20
    supplier match    → +0.25
    region match      → +0.15
    regulatory match  → +0.20
    keyword match     → +0.10

  final_exposure = min(base_exposure + profile_boost, 1.0)
  risk_score = impact × probability × final_exposure × 10

  This means a CVE affecting Apache goes from generic P1
  to P0 if "Apache" is in the company's tech_stack.

## Required .env Variables
  OPENROUTER_API_KEY=
  NEWSAPI_KEY=
  SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
  SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
  QDRANT_URL=http://localhost:6333
  QDRANT_COLLECTION=sentinel_signals
  DEMO_MODE=false
  LOG_LEVEL=INFO
  LLM_PROVIDER=openrouter
  GROQ_API_KEY=
  GROQ_MODEL=llama-3.3-70b-versatile
  COMPANY_PROFILE_PATH=data/company_profile.json

## 12 Agents — Layer Map (Level 2)

Layer 0 — Sensors (3 agents, unchanged):
  NewsScanner          → RSS + NewsAPI  → sample fallback
  CyberThreatAgent     → NVD/CVE API   → sample fallback
  FinancialSignalAgent → SEC EDGAR     → sample fallback

Layer 1 — Processing (3 agents, RouterAgent added):
  EntityExtractor      → NER via Gemini
  SignalClassifier     → P0/P1/P2/P3 via Gemini
  RouterAgent  →NEW    → Path decision via Gemini + CompanyProfile

Layer 2 — Reasoning (2 agents, RiskAssessor upgraded):
  RiskAssessor →UPG    → Impact × Probability × Exposure (profile-weighted)
  CausalChainBuilder   → Root cause + downstream effects

Layer 3 — Deliberation (3 agents, unchanged):
  RedTeamAgent         → Adversarial challenge via Gemini
  BlueTeamAgent        → Optimistic defence via Gemini
  ArbiterAgent         → Confidence score + verdict

Layer 4 — Output (1 agent, unchanged):
  BriefWriter          → Full executive intelligence brief

## LangGraph Pipeline Flow (Level 2)
  START
    → NewsScanner
    → CyberThreatAgent
    → FinancialSignalAgent
    → EntityExtractor
    → SignalClassifier
    → [Loop 1 check] → if confidence < 0.5 → back to EntityExtractor
    → RouterAgent  ← NEW
    → [Route check]
        Path A (FULL)     → RiskAssessor → CausalChainBuilder
                              → RedTeamAgent → BlueTeamAgent → ArbiterAgent
                              → [Loop 2 check] → BriefWriter
        Path B (FAST)     → RiskAssessor → BriefWriter
        Path C (LOG_ONLY) → BriefWriter
  END

## FastAPI Endpoints (Level 2 additions)
  --- All Level 1 endpoints unchanged ---
  GET  /health
  POST /ingest
  GET  /alerts
  GET  /alerts/{id}
  GET  /briefs
  GET  /briefs/latest
  GET  /briefs/{id}
  GET  /pipeline/status

  --- New in Level 2 ---
  GET  /company/profile          → return current CompanyProfile
  PUT  /company/profile          → update CompanyProfile (full replace)
  GET  /company/profile/matches  → return signals that matched profile
                                   (useful for showing "why this alert")

## UI Changes (Level 2)
  New page: /company (Company Profile editor)
  - Form with fields for all CompanyProfile fields
  - Tags input for tech_stack, suppliers, regions, regulatory_scope, keywords
  - Save button calls PUT /company/profile
  - Last updated timestamp shown
  - Add to top nav between Briefs and right side

  Alerts board upgrades:
  - Each alert card now shows "Company Match" badge if relevance_score > 0.6
  - Matched fields shown as small tags on card
    e.g. "Apache" tag if tech_stack matched
  - relevance_score shown as second progress bar (green) below confidence bar

  Brief page upgrades:
  - Add "Company Exposure" section at top of brief
  - Shows which profile fields triggered higher scoring
  - Shows personalised risk score vs generic score side by side

## Build Order (Level 2 — 8 prompts)

Phase 1 — Company Profile Foundation : Prompts 01–02
  01 → CompanyProfile Pydantic model + profile manager
       sentinel/models/company_profile.py
       sentinel/profile/manager.py (load, save, get_active_profile)
       data/company_profile.json (demo profile — tech company on AWS/Apache)
       FastAPI endpoints: GET/PUT /company/profile

  02 → RouterAgent
       sentinel/agents/layer1_processing/router.py
       RouteDecision Pydantic model
       LangGraph conditional edges for Path A/B/C
       Update sentinel/pipeline/graph.py to wire new routing logic

Phase 2 — Personalised Scoring : Prompt 03
  03 → Upgrade RiskAssessor with profile-weighted exposure
       Load CompanyProfile in RiskAssessor.run()
       Calculate profile_boost from entity matches
       Add company_matches and relevance_score to RiskReport
       Update sentinel/models/risk_report.py with new fields

Phase 3 — New API Endpoint : Prompt 04
  04 → GET /company/profile/matches endpoint
       Returns all signals/reports where company_matches is non-empty
       Sorted by relevance_score descending

Phase 4 — UI : Prompts 05–07
  05 → Company Profile page (/company)
       Form + tags input + save + last updated timestamp
       Add to top nav

  06 → Alerts board upgrade
       Company Match badge + matched field tags
       Second green progress bar for relevance_score

  07 → Brief page upgrade
       Company Exposure section
       Personalised vs generic score comparison

Phase 5 — QA : Prompt 08
  08 → End-to-end QA for Level 2
       Verify RouterAgent routes correctly (Path A/B/C all fire)
       Verify profile matching boosts scores correctly
       Verify Company Profile page saves and reloads
       Verify /company/profile/matches returns correct signals
       Run full pipeline in demo mode — check all 3 paths trigger

## Cost Estimate (Level 2 additions)
  RouterAgent: ~1 LLM call per signal = 10 extra calls per run
  Personalised scoring: no extra LLM calls (pure Python math)
  Level 2 total per run: ~19 LLM calls vs ~9 in Level 1
  Extra cost per run: ~$0.003
  Still well under $30 OpenRouter budget

## Progress Tracker
  Last completed prompt: 08 (End-to-End QA)
  Current phase: ✅ Level 2 COMPLETE

## Built
  (Level 1 complete — see Level 1 CONTEXT.md for full list)
  Level 2 additions (backend):
  - sentinel/models/company_profile.py — CompanyProfile Pydantic model
  - sentinel/profile/__init__.py + sentinel/profile/manager.py — load/save/cache
  - data/company_profile.json — demo profile: "Meridian Technologies"
  - sentinel/config.py — added COMPANY_PROFILE_PATH
  - sentinel/models/route_decision.py — RoutePath enum + RouteDecision model
  - sentinel/agents/layer1_processing/router.py — RouterAgent with LLM + fallback (fixed signal.content)
  - sentinel/pipeline/state.py — added route_decisions
  - sentinel/pipeline/graph.py — 12 nodes, 3-path routing
  - sentinel/models/risk_report.py — added company_matches + relevance_score
  - sentinel/agents/layer2_reasoning/risk_assessor.py — profile-weighted exposure (fixed getattr fallback)
  - sentinel/api/routes.py — company profile endpoints + _risk_reports store + company match data in alerts
  - .env.example — added COMPANY_PROFILE_PATH
  - tests/unit/test_company_profile.py — 7 tests — ALL PASS

  Level 2 additions (frontend):
  - sentinel-ui/src/lib/api.ts — CompanyProfile, ProfileMatch, Alert (+ company_matches, relevance_score) interfaces + API functions
  - sentinel-ui/src/app/layout.tsx — "Company" nav, 12 agents badge
  - sentinel-ui/src/app/company/page.tsx — Company Profile editor (TagInput, 4 sections, sticky save bar)
  - sentinel-ui/src/app/alerts/page.tsx — Company Match badge + field tags + relevance bar
  - sentinel-ui/src/app/briefs/page.tsx — Company Exposure section with profile match details

## QA Results (Prompt 08)
  Pipeline: completed | 10 signals | 10 reports | 0 errors
  Company Profile: loads "Meridian Technologies" with tech_stack, suppliers, regions
  Alerts: 9/10 alerts have company_matches with relevance_score
  Profile Matches: endpoint returns matched signals sorted by relevance desc
  Briefs: 1 brief generated with P0 priority, 10 alerts
  Bugs fixed during QA:
    - router.py: signal.description → signal.content (Signal model has no description field)
    - risk_assessor.py: signal.description → getattr(signal, 'description', '') fallback

## Next
→ Level 2 complete. Ready for Level 3 planning or deployment.








