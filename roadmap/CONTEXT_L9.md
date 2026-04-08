# SENTINEL — Build Context (Level 9)

## Project
Autonomous Multi-Agent Enterprise Risk Intelligence System
Level 9: SENTINEL Negotiates
Builds directly on top of Level 8 — all Level 1–8 code remains intact

## What Level 9 Adds
- SENTINEL doesn't just identify risk — it begins resolving it
- NegotiationAgent — when supplier risk detected, finds alternatives
- WebSearchAgent — searches web for alternative suppliers, partners, vendors
- OutreachDrafter — drafts professional outreach emails to alternatives
- ReplyMonitor — polls inbox for replies and summarises offers
- NegotiationSummary — recommends best option with reasoning
- Negotiation UI — full workflow visible in dashboard
- Multi-agent autonomous business process management

## Demo Mode
- ALL external API calls have a --demo-mode fallback
- WebSearchAgent uses mock search results in demo mode
- OutreachDrafter generates real drafts via LLM in demo mode
- ReplyMonitor uses seeded mock replies in demo mode
- Full negotiation workflow visible without real email sending
- Every sensor agent MUST implement both live and demo paths

## Stack
- LLM:            google/gemini-3-flash-preview via OpenRouter (default)
                  OR llama-3.3-70b-versatile via Groq (switchable via LLM_PROVIDER)
- Orchestration:  LangGraph ONLY (no AutoGen, no CrewAI)
- Vector DB:      Qdrant (Docker)
                  {tenant_id}_negotiations — NEW per-tenant negotiation store
                  all previous collections unchanged
- Embeddings:     google/gemini-embedding-001 via OpenRouter
- Web Search:     SerpAPI free tier (100 searches/month) OR
                  DuckDuckGo scraping via httpx (no key needed, fallback)
- Email:          SMTP via smtplib (from Level 3) for outreach sending
- API:            FastAPI
- Config:         pydantic-settings
- Logging:        structlog
- Python:         3.11+, async throughout
- OS:             Windows 11 (native)
- UI Framework:   Next.js 14 (App Router)
- UI Styling:     Tailwind CSS + shadcn/ui
- UI connects to: FastAPI on http://localhost:8000

## Model Routing (unchanged from Level 8)
- SENTINEL_PRIMARY_MODEL=google/gemini-3-flash-preview
- SENTINEL_EMBEDDING_MODEL=google/gemini-embedding-001
- LLM_PROVIDER controls which backend: "openrouter" (default) or "groq"
- Embeddings always OpenRouter regardless of LLM_PROVIDER
- No hardcoded model strings anywhere

## LLM Client Pattern (unchanged from Level 8)
- openai SDK with custom base_url
- Provider switching via LLM_PROVIDER env var
- ALL LLM + embedding calls through sentinel/llm/client.py only

## Thinking Levels (Level 9 additions marked)
- Thinking OFF: EntityExtractor, SignalClassifier, RiskAssessor,
                BriefWriter, QualityAgent, all Layer 0, RouterAgent,
                WebSearchAgent, ReplyMonitor
- Thinking ON:  CausalChainBuilder, RedTeamAgent, BlueTeamAgent,
                ArbiterAgent, PromptOptimiser, FeedbackAgent,
                ForecastAgent, ActionPlanner,
                NegotiationAgent (thinking=ON — complex multi-step reasoning)
                OutreachDrafter (thinking=ON — professional email drafting)
- Groq silently ignores thinking param

## Conventions (unchanged from Level 8)
- ALL agent methods are async
- ALL inter-agent data uses Pydantic models (no raw dicts)
- ALL LLM calls go through sentinel/llm/client.py only
- ALL external API calls wrapped in try/except with demo fallback
- ALL errors logged via structlog before raising
- Type hints on every function signature
- No print() anywhere — structlog only
- No hardcoded strings — always use settings or constants
- Windows 11: asyncio.WindowsSelectorEventLoopPolicy() in main.py

## Architecture (Level 9 changes marked NEW / UPG)
- LangGraph StateGraph as sole orchestration framework
- All Level 1-8 pipeline logic unchanged
- NEW: NegotiationPipeline — separate LangGraph StateGraph
       triggered when ActionPlanner identifies SUPPLIER_RISK action type
       runs INDEPENDENTLY from main pipeline as asyncio.create_task()
- NEW: NegotiationAgent — orchestrates the full negotiation workflow
- NEW: WebSearchAgent — finds alternative suppliers via web search
- NEW: OutreachDrafter — writes professional outreach emails
- NEW: ReplyMonitor — polls IMAP inbox for replies (background task)
- NEW: NegotiationSummary — synthesises replies into recommendation
- UPG: ActionPlanner — new action type INITIATE_NEGOTIATION
       fires when signal involves supplier bankruptcy/disruption
- UPG: ActionRegistry — INITIATE_NEGOTIATION action type added
- FastAPI CORS enabled for http://localhost:3000

## Negotiation System Design (NEW)

### When Negotiation Triggers
  ActionPlanner detects SUPPLIER_RISK signals:
    - Supplier mentioned in company_profile.suppliers
    - Signal involves: bankruptcy, acquisition, disruption, sanction
    - Risk score >= 7.0 AND priority P0 or P1
  ActionPlanner creates ActionEntry with action_type=INITIATE_NEGOTIATION
  ActionEngine fires NegotiationPipeline as asyncio.create_task()

### NegotiationSession Schema
  sentinel/models/negotiation.py

  NegotiationStatus enum:
    SEARCHING      - finding alternatives
    DRAFTING       - writing outreach emails
    AWAITING_REPLY - emails sent, waiting for responses
    SUMMARISING    - analysing replies
    COMPLETE       - recommendation ready
    FAILED         - negotiation failed or timed out
    DEMO           - demo mode with mock data

  AlternativeSupplier:
    name:            str
    website:         str
    description:     str
    relevance_score: float    (0.0-1.0, how well they match)
    search_source:   str      (where it was found)

  OutreachEmail:
    supplier:        AlternativeSupplier
    subject:         str
    body:            str
    sent_at:         datetime | None
    reply_received:  bool
    reply_body:      str | None
    reply_at:        datetime | None

  NegotiationSession:
    id:                  UUID
    tenant_id:           str
    signal_id:           UUID
    action_id:           UUID
    original_supplier:   str      (the at-risk supplier)
    risk_reason:         str      (why they are at risk)
    alternatives_found:  List[AlternativeSupplier]
    outreach_emails:     List[OutreachEmail]
    recommendation:      str | None  (final recommended supplier)
    recommendation_reasoning: str | None
    status:              NegotiationStatus
    created_at:          datetime
    completed_at:        datetime | None

  Stored in: Qdrant {tenant_id}_negotiations collection

### NegotiationPipeline (NEW separate LangGraph graph)
  Location: sentinel/negotiation/pipeline.py

  Separate StateGraph from main pipeline.
  Nodes:
    SEARCH     - WebSearchAgent finds 3-5 alternatives
    DRAFT      - OutreachDrafter writes emails for each alternative
    SEND       - sends emails via SMTP (or logs in demo mode)
    MONITOR    - ReplyMonitor polls inbox for replies (with timeout)
    SUMMARISE  - NegotiationSummary synthesises replies
    COMPLETE   - stores final NegotiationSession

  Flow:
    START -> SEARCH -> DRAFT -> SEND -> MONITOR -> SUMMARISE -> COMPLETE -> END

  Timeout: NEGOTIATION_TIMEOUT_HOURS (default 24)
  After timeout: generates summary from any replies received so far

### WebSearchAgent
  Location: sentinel/negotiation/web_search.py

  Searches for alternative suppliers using:
    Primary: SerpAPI (if SERPAPI_KEY configured)
    Fallback: DuckDuckGo via httpx scraping (no key needed)
    Demo: returns mock alternatives from data/demo_alternatives.json

  Query construction (Gemini, thinking=OFF):
    "Given supplier {name} in industry {industry},
     generate 3 search queries to find alternatives"

  Returns List[AlternativeSupplier] (top 3-5 results)

### OutreachDrafter
  Location: sentinel/negotiation/outreach_drafter.py

  For each AlternativeSupplier, drafts a professional outreach email.
  Uses Gemini (thinking=ON):
    "Draft a professional email to {supplier_name} from {company_name}
     expressing interest in their services as an alternative to {original}.
     Context: {risk_reason}. Company stack: {tech_stack}.
     Keep it concise, professional, and specific."

  Output: OutreachEmail with subject + body populated
  Human must approve before sending (NEGOTIATION_AUTO_SEND=false default)

### ReplyMonitor
  Location: sentinel/negotiation/reply_monitor.py

  Background async task that polls IMAP inbox:
    - Checks for replies to sent outreach emails
    - Matches replies by email thread / subject line
    - Updates OutreachEmail.reply_received + reply_body
    - Runs every REPLY_POLL_INTERVAL_MINUTES (default 30)

  Demo mode:
    - After 30 seconds, loads mock replies from data/demo_replies.json
    - Simulates 2 replies received out of 3 emails sent

### NegotiationSummary
  Location: sentinel/negotiation/summary.py

  Reads all OutreachEmail.reply_body values.
  Asks Gemini (thinking=ON):
    "We contacted {N} alternative suppliers.
     {M} replied. Here are their responses: {replies}.
     Recommend the best option considering: price signals, capability,
     speed of response, and our requirements: {company_profile}.
     Provide: recommended_supplier, reasoning, next_steps."

  Updates NegotiationSession.recommendation + reasoning
  Creates ActionEntry for the recommendation (PENDING_APPROVAL)

## Required .env Variables
  (all previous variables unchanged)
  SERPAPI_KEY=                          # optional, DuckDuckGo fallback if empty
  NEGOTIATION_ENABLED=true              # master switch
  NEGOTIATION_AUTO_SEND=false           # false = human approves emails before send
  NEGOTIATION_TIMEOUT_HOURS=24          # max time to wait for replies
  REPLY_POLL_INTERVAL_MINUTES=30        # how often to check inbox for replies
  NEGOTIATION_MAX_ALTERNATIVES=5        # max suppliers to contact

## 21 Agents - Layer Map (Level 9)

Layer 0 - Sensors (3 agents, unchanged):
  NewsScanner, CyberThreatAgent, FinancialSignalAgent

Layer 1 - Processing (4 agents, unchanged):
  EntityExtractor, SignalClassifier, ForecastAgent, RouterAgent

Layer 2 - Reasoning (2 agents, unchanged):
  RiskAssessor, CausalChainBuilder

Layer 3 - Deliberation (4 agents, unchanged):
  RedTeamAgent, BlueTeamAgent, ArbiterAgent, ActionPlanner UPG

Layer 4 - Output (3 agents, unchanged):
  BriefWriter, QualityAgent, PromptOptimiser

Layer 5 - Memory + Feedback (2 agents, unchanged):
  MemoryWriter, FeedbackAgent

Layer 6 - Negotiation (4 agents, NEW):
  NegotiationAgent  NEW - orchestrates negotiation workflow (thinking=ON)
  WebSearchAgent    NEW - finds alternative suppliers
  OutreachDrafter   NEW - drafts professional emails (thinking=ON)
  ReplyMonitor      NEW - polls inbox for replies (background)
  NegotiationSummary NEW - synthesises replies into recommendation (thinking=ON)

## LangGraph Pipeline Flow (Level 9)
  Main pipeline: UNCHANGED from Level 8

  New NegotiationPipeline (separate graph, fires async):
  START
    -> SEARCH (WebSearchAgent)
    -> DRAFT (OutreachDrafter)
    -> SEND (ActionEngine email)
    -> MONITOR (ReplyMonitor polls, timeout=NEGOTIATION_TIMEOUT_HOURS)
    -> SUMMARISE (NegotiationSummary)
    -> COMPLETE (store NegotiationSession)
  END

  Trigger: ActionEngine receives INITIATE_NEGOTIATION action type
           -> asyncio.create_task(NegotiationPipeline.run(session))

## FastAPI Endpoints (Level 9 additions)
  All Level 1-8 endpoints unchanged

  New in Level 9:
  GET  /negotiations                       - list all sessions tenant-scoped
  GET  /negotiations/active                - in-progress sessions
  GET  /negotiations/{id}                  - full session detail
  GET  /negotiations/{id}/emails           - outreach emails for session
  POST /negotiations/{id}/send             - approve + send outreach emails
  POST /negotiations/{id}/cancel           - cancel negotiation
  GET  /negotiations/{id}/summary          - final recommendation
  POST /negotiations/trigger               - manually trigger negotiation
  GET  /negotiations/demo                  - run demo negotiation with mock data

## UI Changes (Level 9)

  New page: /negotiations (Negotiation Centre)
  - Active negotiation card at top if in progress
    Shows: original supplier, status pill, progress timeline
    SEARCHING -> DRAFTING -> AWAITING REPLY -> SUMMARISING -> COMPLETE
  - Alternatives section: cards for each found supplier
    Name, website, relevance score, description
  - Outreach emails section: one card per email
    Supplier name, subject preview, status (Draft/Sent/Reply Received)
    "View Draft" expands full email text
    "Approve & Send" button (if NEGOTIATION_AUTO_SEND=false)
  - Replies section: shows received replies with supplier name
  - Recommendation section (appears when complete):
    Recommended supplier card with green border
    Reasoning paragraph
    "Accept Recommendation" action button
  - History tab: past completed negotiations
  - Add to top nav after Actions

  Brief page upgrades:
  - If negotiation triggered from this brief's signal:
    Add "Negotiation in Progress" banner with link to /negotiations
    Shows current negotiation status inline

  Action Centre upgrades:
  - INITIATE_NEGOTIATION action type shown with handshake icon
  - Clicking opens negotiation detail inline

## Build Order (Level 9 - 9 prompts)

Phase 1 - Negotiation Infrastructure : Prompts 01-02
  01 - NegotiationSession model + Qdrant collection
       sentinel/models/negotiation.py
           NegotiationStatus enum, AlternativeSupplier model,
           OutreachEmail model, NegotiationSession model
           to_payload() / from_payload()
       sentinel/negotiation/__init__.py
       sentinel/negotiation/store.py
           async save_session(session) -> NegotiationSession
           async get_sessions(tenant_id) -> List[NegotiationSession]
           async update_session(id, updates) -> NegotiationSession
       scripts/init_qdrant.py updated
           creates {tenant_id}_negotiations for all 5 tenants
       sentinel/config.py updated - 5 NEGOTIATION_ vars
       .env.example updated
       tests/unit/test_negotiation.py

  02 - ActionRegistry + ActionEngine update for INITIATE_NEGOTIATION
       ActionType enum updated - add INITIATE_NEGOTIATION
       ActionEngine._execute_negotiation() added
           creates NegotiationSession
           fires NegotiationPipeline as asyncio.create_task()
       ActionPlanner updated - detects SUPPLIER_RISK conditions
       data/tenants/*/action_registry.json updated
           INITIATE_NEGOTIATION: enabled=true, auto_execute=false
       data/demo_alternatives.json - 5 mock alternative suppliers
       data/demo_replies.json - 3 mock supplier replies

Phase 2 - Negotiation Agents : Prompts 03-05
  03 - WebSearchAgent
       sentinel/negotiation/web_search.py
           async search(supplier, industry, company_profile) -> List[AlternativeSupplier]
           _search_serpapi() - SerpAPI integration
           _search_duckduckgo() - httpx fallback scraping
           _load_demo_alternatives() - demo fallback
           _generate_queries() - LLM query construction (thinking=OFF)

  04 - OutreachDrafter
       sentinel/negotiation/outreach_drafter.py
           async draft(supplier, company_profile, risk_reason) -> OutreachEmail
           uses Gemini thinking=ON
           professional email template with company context

  05 - ReplyMonitor + NegotiationSummary
       sentinel/negotiation/reply_monitor.py
           async poll(session_id, tenant_id) -> List[OutreachEmail]
           IMAP polling with timeout
           demo mode: load from data/demo_replies.json after 30s delay
       sentinel/negotiation/summary.py
           async summarise(session) -> NegotiationSession
           uses Gemini thinking=ON
           returns recommendation + reasoning

Phase 3 - NegotiationPipeline : Prompt 06
  06 - NegotiationPipeline LangGraph graph
       sentinel/negotiation/pipeline.py
           NegotiationState TypedDict
           build_negotiation_graph() -> CompiledGraph
           SEARCH -> DRAFT -> SEND -> MONITOR -> SUMMARISE -> COMPLETE
           Timeout handling for MONITOR node

Phase 4 - API Endpoints + UI : Prompts 07-08
  07 - Negotiation FastAPI endpoints
       All 9 endpoints listed above
       sentinel/api/routes.py updated

  08 - Negotiation Centre UI (/negotiations)
       Status timeline + alternatives + emails + replies + recommendation
       Add to top nav
       Brief + Action Centre upgrades

Phase 5 - QA : Prompt 09
  09 - Full QA for Level 9
       Run demo negotiation via GET /negotiations/demo
       Verify NegotiationSession created with DEMO status
       Verify alternatives found (3-5 suppliers)
       Verify outreach emails drafted with company context
       Verify mock replies loaded in demo mode
       Verify recommendation generated
       Verify Negotiation Centre UI shows full workflow
       Verify status timeline progresses correctly
       Test POST /negotiations/{id}/cancel mid-workflow
       pytest tests/ - all tests pass
       npx tsc --noEmit - zero TypeScript errors

## Cost Estimate (Level 9 additions)
  WebSearchAgent query construction: 1 LLM call per negotiation (thinking=OFF)
  OutreachDrafter: 1 LLM call per alternative (3-5 alternatives) (thinking=ON)
  NegotiationSummary: 1 LLM call per negotiation (thinking=ON)
  Total per negotiation: ~6-7 LLM calls (thinking=ON for 2)
  Negotiations only fire for P0/P1 supplier risk signals (rare)
  Estimated 1-2 negotiations per week in production
  Extra cost per negotiation: ~$0.008
  Cumulative per pipeline run: ~$0.017 unchanged (negotiation is separate)

## Progress Tracker
  Last completed prompt: 09 (Full QA — Level 9 complete)
  Current phase: Level 9 COMPLETE

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
  - Prompt 01: NegotiationSession model + store + config + demo data + tests
  - Prompt 02: ActionType.INITIATE_NEGOTIATION + ActionEngine handler + ActionPlanner supplier risk detection + 5 registry updates
  - Prompt 03: WebSearchAgent (SerpAPI + DuckDuckGo fallback + demo mode)
  - Prompt 04: OutreachDrafter (Gemini thinking=ON + template fallback)
  - Prompt 05: ReplyMonitor (IMAP + demo mode) + NegotiationSummary (thinking=ON)
  - Prompt 06: NegotiationPipeline LangGraph graph (6 nodes: SEARCH→DRAFT→SEND→MONITOR→SUMMARISE→COMPLETE)
  - Prompt 07: 9 negotiation API endpoints in routes.py
  - Prompt 08: Negotiation Centre UI (/negotiations) with status timeline, supplier cards, email cards, recommendation
  - Prompt 09: Full QA — 76/76 tests pass, TypeScript 0 errors, UI verified in browser

## Schemas defined
  NegotiationStatus enum (7 values)
  AlternativeSupplier (name, website, description, relevance_score, search_source)
  OutreachEmail (supplier, subject, body, sent_at, reply_received, reply_body, reply_at)
  NegotiationSession (id, tenant_id, signal_id, action_id, original_supplier, risk_reason, alternatives_found, outreach_emails, recommendation, recommendation_reasoning, status, created_at, completed_at)
  NegotiationState TypedDict (session, company_profile, error)

## Agent interfaces
  WebSearchAgent.search(original_supplier, industry, company_profile, max_results) → List[AlternativeSupplier]
  OutreachDrafter.draft(supplier, company_name, company_profile, risk_reason, original_supplier) → OutreachEmail
  OutreachDrafter.draft_batch(suppliers, ...) → List[OutreachEmail]
  ReplyMonitor.poll(session, timeout_seconds) → List[OutreachEmail]
  NegotiationSummary.summarise(session, company_profile) → NegotiationSession
  NegotiationSummary.create_recommendation_action(session) → ActionEntry
  ActionPlanner._detect_supplier_risk(signal, report, reasoning_context) → dict | None
  ActionEngine._execute_negotiation(action) → dict

## Files created
  sentinel/models/negotiation.py — NegotiationSession, AlternativeSupplier, OutreachEmail models
  sentinel/negotiation/__init__.py — package init
  sentinel/negotiation/store.py — Qdrant + in-memory session persistence
  sentinel/negotiation/web_search.py — WebSearchAgent (SerpAPI + DDG + demo)
  sentinel/negotiation/outreach_drafter.py — OutreachDrafter (Gemini thinking=ON)
  sentinel/negotiation/reply_monitor.py — ReplyMonitor (IMAP + demo mode)
  sentinel/negotiation/summary.py — NegotiationSummary (thinking=ON recommendation)
  sentinel/negotiation/pipeline.py — NegotiationPipeline LangGraph (6 nodes)
  data/demo_alternatives.json — 5 mock alternative suppliers
  data/demo_replies.json — 3 mock supplier replies
  tests/unit/test_negotiation.py — 12 unit tests for Level 9
  sentinel-ui/src/app/negotiations/page.tsx — Negotiation Centre UI

## Files modified
  sentinel/config.py — 6 new negotiation config vars
  .env.example — Level 9 env vars added
  scripts/init_qdrant.py — {tenant_id}_negotiations collections
  sentinel/models/action_entry.py — INITIATE_NEGOTIATION enum value
  sentinel/actions/engine.py — _execute_negotiation handler + dispatch entry
  sentinel/agents/layer3_deliberation/action_planner.py — supplier risk detection + INITIATE_NEGOTIATION planning
  data/tenants/{default,techcorp,retailco,financeinc,healthco}/action_registry.json — INITIATE_NEGOTIATION enabled
  sentinel/api/routes.py — 9 negotiation endpoints
  sentinel-ui/src/lib/api.ts — 3 interfaces + 9 API functions
  sentinel-ui/src/app/layout.tsx — Handshake nav item + v9.0/21 nodes
  tests/unit/test_actions.py — updated ActionType assertion

## Next
  Level 9 COMPLETE — all prompts built, QA passed
  76/76 Python tests pass, TypeScript 0 errors
  Negotiation Centre UI verified in browser
