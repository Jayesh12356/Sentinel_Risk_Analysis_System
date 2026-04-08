# SENTINEL — Comprehensive Test Plan

> **System**: Autonomous Multi-Agent Enterprise Risk Intelligence System
> **Scope**: Levels 1–10, 22 agents, 7 layers, multi-tenant, full-stack
> **Date**: 2026-03-27

---

## Table of Contents

1. [Pre-Flight Checks](#1-pre-flight-checks)
2. [Level 1 — Core Pipeline](#2-level-1--core-pipeline)
3. [Level 2 — Company DNA + Dynamic Routing](#3-level-2--company-dna--dynamic-routing)
4. [Level 3 — Agent Memory + Alerts](#4-level-3--agent-memory--alerts)
5. [Level 4 — Self-Improving Prompts](#5-level-4--self-improving-prompts)
6. [Level 5 — Human Feedback Loop](#6-level-5--human-feedback-loop)
7. [Level 6 — Multi-Tenant Federation](#7-level-6--multi-tenant-federation)
8. [Level 7 — Predictive Risk Intelligence](#8-level-7--predictive-risk-intelligence)
9. [Level 8 — Autonomous Actions](#9-level-8--autonomous-actions)
10. [Level 9 — Negotiation Pipeline](#10-level-9--negotiation-pipeline)
11. [Level 10 — Meta-Governance](#11-level-10--meta-governance)
12. [Cross-Cutting Tests](#12-cross-cutting-tests)
13. [End-to-End Integration Tests](#13-end-to-end-integration-tests)
14. [UI / Frontend Tests](#14-ui--frontend-tests)
15. [Performance & Stress Tests](#15-performance--stress-tests)
16. [Security & Data Isolation Tests](#16-security--data-isolation-tests)
17. [Failure & Recovery Tests](#17-failure--recovery-tests)
18. [Demo Mode Validation](#18-demo-mode-validation)

---

## 1. Pre-Flight Checks

### 1.1 Infrastructure

| # | Test | Command / Method | Expected Result |
|---|------|------------------|-----------------|
| PF-01 | Docker Compose starts Qdrant | `docker-compose up -d` | Qdrant running on `localhost:6333` |
| PF-02 | Qdrant health check | `GET http://localhost:6333/healthz` | `200 OK` |
| PF-03 | Init Qdrant collections | `python scripts/init_qdrant.py` | All collections created (sentinel_signals, sentinel_memory, sentinel_prompts, sentinel_feedback, sentinel_shared_patterns, sentinel_meta, {tenant_id}_* for 5 tenants) |
| PF-04 | Init prompt versions | `python scripts/init_prompts.py` | 9 agent prompts seeded in sentinel_prompts |
| PF-05 | Init tenants | `python scripts/init_tenants.py` | 4 demo tenants created + default |
| PF-06 | Seed shared patterns | `python scripts/seed_shared_patterns.py` | 6 shared patterns seeded |
| PF-07 | Seed forecast history | `python scripts/seed_forecast_history.py` | 120 MemoryEntries seeded (30 per tenant) |
| PF-08 | Backend starts | `python -m uvicorn sentinel.main:app --host 0.0.0.0 --port 8000 --reload` | `Application startup complete`, no import errors |
| PF-09 | Health endpoint | `GET /health` | `{"status":"ok", ...}` |
| PF-10 | Frontend starts | `cd sentinel-ui && npm run dev` | Next.js on `localhost:3000`, no compile errors |
| PF-11 | TypeScript compilation | `npx tsc --noEmit` | 0 errors |
| PF-12 | Unit tests | `python -m pytest tests/unit/ -q` | 89/89 pass (or all pass) |
| PF-13 | .env loaded | Check structlog output | LLM provider, model, demo_mode logged at startup |

### 1.2 Configuration

| # | Test | Expected |
|---|------|----------|
| PF-14 | All .env variables present | Compare .env against .env.example — no missing keys |
| PF-15 | DEMO_MODE default | Defaults to `false` when not set |
| PF-16 | LLM_PROVIDER default | Defaults to `openrouter` |
| PF-17 | CORS configured | Requests from `localhost:3000` accepted |
| PF-18 | Windows event loop policy | `asyncio.WindowsSelectorEventLoopPolicy()` set in main.py |

---

## 2. Level 1 — Core Pipeline

### 2.1 Pydantic Models

| # | Test | Expected |
|---|------|----------|
| L1-01 | Signal model creation | Valid Signal with all fields, UUID auto-generated |
| L1-02 | SignalPriority enum | P0, P1, P2, P3 values valid |
| L1-03 | RiskReport model creation | RiskScore, CausalLink, DeliberationResult sub-models populated |
| L1-04 | Brief model creation | BriefSection, AlertItem sub-models populated |
| L1-05 | Model serialization round-trip | `model.model_dump()` → `Model(**data)` equality |

### 2.2 LLM Client

| # | Test | Expected |
|---|------|----------|
| L1-06 | OpenRouter provider init | `base_url = "https://openrouter.ai/api/v1"`, correct headers |
| L1-07 | Groq provider init | `base_url = "https://api.groq.com/openai/v1"` when `LLM_PROVIDER=groq` |
| L1-08 | `complete()` returns string | Valid non-empty response from LLM |
| L1-09 | `embed()` returns vector | Vector of dimension 3072 returned |
| L1-10 | Thinking param ON | `extra_body={"thinking": ...}` passed for thinking=True |
| L1-11 | Thinking param silently ignored on Groq | No error when thinking=True with Groq provider |
| L1-12 | Retry on failure | Tenacity retries 3 times with exponential backoff |
| L1-13 | Embeddings always use OpenRouter | Even when `LLM_PROVIDER=groq`, embeddings use OpenRouter |

### 2.3 Sensor Agents (Layer 0)

| # | Test | Expected |
|---|------|----------|
| L1-14 | NewsScanner demo mode | Returns 4 sample signals from `data/sample_signals/news.json` |
| L1-15 | CyberThreatAgent demo mode | Returns 3 sample CVEs from `data/sample_signals/cyber.json` |
| L1-16 | FinancialSignalAgent demo mode | Returns 3 sample filings from `data/sample_signals/financial.json` |
| L1-17 | Signal format | All demo signals conform to Signal Pydantic model |
| L1-18 | 10 total demo signals | 4 news + 3 cyber + 3 financial = 10 signals |
| L1-19 | Priority distribution | 2 P0, 3 P1, 3 P2, 2 P3 |
| L1-20 | NewsScanner live fallback | If RSS/NewsAPI fails, loads demo data (no crash) |
| L1-21 | CyberThreatAgent live fallback | If NVD API fails, loads demo data (no crash) |
| L1-22 | FinancialSignalAgent live fallback | If SEC EDGAR fails, loads demo data (no crash) |

### 2.4 Processing Agents (Layer 1)

| # | Test | Expected |
|---|------|----------|
| L1-23 | EntityExtractor NER | Extracts ORG, PERSON, CVE, PRODUCT, LOCATION entities |
| L1-24 | SignalClassifier assigns P0-P3 | Each signal gets a priority and confidence score |
| L1-25 | SignalClassifier confidence range | All confidence scores in [0.0, 1.0] |
| L1-26 | Loop 1 trigger | Signal with confidence < 0.5 loops back to EntityExtractor |
| L1-27 | Loop 1 counter increment | `loop1_count` increments on each loop, max guard prevents infinite loops |

### 2.5 Reasoning Agents (Layer 2)

| # | Test | Expected |
|---|------|----------|
| L1-28 | RiskAssessor scoring | `risk_score = impact × probability × exposure × 10` |
| L1-29 | RiskReport populated | All RiskReport fields filled (score, evidence, causal links) |
| L1-30 | CausalChainBuilder DAG | Returns 3-6 CausalLink objects per report |
| L1-31 | Root cause identified | At least one CausalLink marked as root cause |
| L1-32 | Thinking=ON for reasoning | CausalChainBuilder uses `thinking=True` |

### 2.6 Deliberation Agents (Layer 3)

| # | Test | Expected |
|---|------|----------|
| L1-33 | RedTeamAgent adversarial | Returns challenge text, blind spots, priority escalation argument |
| L1-34 | BlueTeamAgent defence | Returns defence text, mitigating factors |
| L1-35 | ArbiterAgent verdict | Sets `red_team_wins: bool`, `final_confidence: float` |
| L1-36 | Loop 2 trigger | If Red Team wins → priority escalated, loops back to RiskAssessor |
| L1-37 | Loop 2 counter | `loop2_count` increments, max guard prevents infinite loops |
| L1-38 | Thinking=ON for deliberation | All 3 agents use `thinking=True` |

### 2.7 Output Agent (Layer 4)

| # | Test | Expected |
|---|------|----------|
| L1-39 | BriefWriter generates Brief | Complete Brief model with sections, alerts, recommendations |
| L1-40 | Brief stored | Brief accessible via `GET /briefs/latest` |

### 2.8 Pipeline

| # | Test | Expected |
|---|------|----------|
| L1-41 | Full pipeline execution | `POST /ingest` → pipeline completes, brief generated |
| L1-42 | MAX_SIGNALS_PER_RUN guard | At most 10 signals processed per run |
| L1-43 | Pipeline status | `GET /pipeline/status` returns current/last run status |
| L1-44 | Graph structure | All 11 agent nodes wired with correct edges |

### 2.9 API Endpoints

| # | Test | Expected |
|---|------|----------|
| L1-45 | `GET /health` | Returns `{"status":"ok"}` |
| L1-46 | `POST /ingest` | Triggers pipeline, returns `202 Accepted` or run ID |
| L1-47 | `GET /alerts` | Returns list of alerts by priority |
| L1-48 | `GET /alerts/{id}` | Returns single alert detail |
| L1-49 | `GET /briefs` | Returns list of all briefs |
| L1-50 | `GET /briefs/latest` | Returns most recent brief |
| L1-51 | `GET /briefs/{id}` | Returns single brief |
| L1-52 | `GET /pipeline/status` | Returns pipeline status |

---

## 3. Level 2 — Company DNA + Dynamic Routing

### 3.1 Company Profile

| # | Test | Expected |
|---|------|----------|
| L2-01 | CompanyProfile model | Valid model with name, industry, regions, tech_stack, suppliers, etc. |
| L2-02 | Demo profile loads | "Meridian Technologies" profile loaded from JSON |
| L2-03 | `GET /company/profile` | Returns current profile |
| L2-04 | `PUT /company/profile` | Updates and persists profile |
| L2-05 | Profile persistence | Profile survives server restart (stored in JSON file) |

### 3.2 RouterAgent

| # | Test | Expected |
|---|------|----------|
| L2-06 | Path A (FULL) routing | P0/P1 with high company relevance → full pipeline |
| L2-07 | Path B (FAST) routing | P2 or low company relevance → RiskAssessor → BriefWriter only |
| L2-08 | Path C (LOG_ONLY) routing | P3 or zero relevance → BriefWriter directly |
| L2-09 | RouteDecision model | Contains path, relevance_score, relevance_reason, company_matches |
| L2-10 | All 3 paths fire in demo | With 10 demo signals, at least 1 signal takes each path |

### 3.3 Personalised Risk Scoring

| # | Test | Expected |
|---|------|----------|
| L2-11 | Tech stack match boost | Signal with "Apache" + company tech_stack ["Apache"] → +0.20 exposure |
| L2-12 | Supplier match boost | Signal mentioning company supplier → +0.25 exposure |
| L2-13 | Region match boost | Signal in company region → +0.15 |
| L2-14 | Final exposure capped at 1.0 | Multiple matches don't exceed 1.0 |
| L2-15 | `GET /company/profile/matches` | Returns signals sorted by relevance_score desc |

---

## 4. Level 3 — Agent Memory + Alerts

### 4.1 Memory System

| # | Test | Expected |
|---|------|----------|
| L3-01 | MemoryEntry creation | After pipeline run, MemoryEntry created per signal |
| L3-02 | MemoryEntry stored in Qdrant | Entries in sentinel_memory collection with embeddings |
| L3-03 | Memory semantic search | `GET /memory/search?q=apache` returns relevant past events |
| L3-04 | Memory patterns endpoint | `GET /memory/patterns` returns grouped recurring threats |
| L3-05 | Memory time filter | `days_back=90` filters correctly |
| L3-06 | `DELETE /memory` | Clears all memory entries |

### 4.2 Agent Memory Integration

| # | Test | Expected |
|---|------|----------|
| L3-07 | CausalChainBuilder uses memory | Prompt contains "PAST SIMILAR EVENTS" section |
| L3-08 | RedTeamAgent uses memory | Prompt contains past false positives from memory |
| L3-09 | BlueTeamAgent uses memory | Prompt contains past mitigations from memory |
| L3-10 | BriefWriter memory context | Brief includes "Memory Context" section |
| L3-11 | Recurring pattern detection | After 2+ runs with same signal, "recurring" flag set |
| L3-12 | Run twice then verify | Run pipeline twice → second run agents receive memory context |

### 4.3 Alert Dispatcher

| # | Test | Expected |
|---|------|----------|
| L3-13 | P0 alert fires | P0 signal with relevance_score > 0.7 triggers alert |
| L3-14 | Demo mode logging | `ALERT_DEMO_MODE=true` → structlog output, no real email/Slack |
| L3-15 | Alert format | Contains priority, source, confidence, risk_score, company matches |
| L3-16 | `POST /alerts/test` | Test alert endpoint works |
| L3-17 | Non-blocking alert | AlertDispatcher fires via asyncio.create_task(), doesn't block pipeline |

### 4.4 Personalised Remediation

| # | Test | Expected |
|---|------|----------|
| L3-18 | Stack-specific recommendations | Brief recommendations mention company tech_stack items |
| L3-19 | Regulatory references | Recommendations reference regulatory_scope items (e.g. "GDPR Article 33") |

---

## 5. Level 4 — Self-Improving Prompts

### 5.1 PromptStore

| # | Test | Expected |
|---|------|----------|
| L4-01 | Initial prompts seeded | 9 agent prompts in sentinel_prompts at version 1 |
| L4-02 | `get_active_prompt(agent)` | Returns active prompt text for given agent |
| L4-03 | Fallback to hardcoded | If PromptStore empty, agents use hardcoded defaults |
| L4-04 | `save_prompt_version()` | Creates new version, deactivates old |
| L4-05 | Prompt history | `get_prompt_history(agent)` returns all versions in order |
| L4-06 | Rollback | `rollback_prompt(agent, version)` restores previous version |

### 5.2 QualityAgent

| # | Test | Expected |
|---|------|----------|
| L4-07 | Scores brief on 5 dimensions | specificity, evidence_depth, causal_clarity, actionability, completeness |
| L4-08 | Weighted overall score | Correct weighted average (0.25, 0.20, 0.20, 0.25, 0.10) |
| L4-09 | Score range | All scores in [0.0, 1.0] |
| L4-10 | Identifies weak_agents | Returns list of agents whose output led to low scores |
| L4-11 | Pipeline position | QualityAgent runs AFTER BriefWriter, BEFORE MemoryWriter |

### 5.3 PromptOptimiser

| # | Test | Expected |
|---|------|----------|
| L4-12 | Triggers below threshold | Fires when `quality_score < QUALITY_THRESHOLD (0.70)` |
| L4-13 | OPTIMISER_MIN_RUNS guard | Doesn't fire until min runs reached |
| L4-14 | New prompt version created | PromptStore has new version after optimisation |
| L4-15 | Async execution | PromptOptimiser runs as background task, doesn't block pipeline |
| L4-16 | OPTIMISER_ENABLED=false | No optimisation when disabled |

### 5.4 API Endpoints

| # | Test | Expected |
|---|------|----------|
| L4-17 | `GET /prompts/{agent}` | Returns active prompt + version count |
| L4-18 | `GET /prompts/{agent}/history` | Returns full version history |
| L4-19 | `POST /prompts/{agent}/rollback` | Rolls back to specified version |
| L4-20 | `GET /quality` | Returns quality score records |
| L4-21 | `POST /quality/optimise` | Manually triggers optimisation |

---

## 6. Level 5 — Human Feedback Loop

### 6.1 Feedback Collection

| # | Test | Expected |
|---|------|----------|
| L5-01 | FeedbackEntry model | FeedbackAction enum: ACTED_ON, FALSE_POSITIVE, ESCALATE, DISMISS |
| L5-02 | `GET /feedback/{signal_id}/acted_on` | Creates FeedbackEntry, returns HTML thank-you page |
| L5-03 | `GET /feedback/{signal_id}/false_positive` | Creates FeedbackEntry with FALSE_POSITIVE action |
| L5-04 | `GET /feedback/{signal_id}/escalate` | Creates FeedbackEntry with ESCALATE action |
| L5-05 | `GET /feedback/{signal_id}/dismiss` | Creates FeedbackEntry with DISMISS action |
| L5-06 | FeedbackEntry stored in Qdrant | Entry in sentinel_feedback collection |
| L5-07 | `GET /feedback` | Lists all feedback entries |
| L5-08 | `GET /feedback/stats` | Returns acted_on_rate, false_positive_rate per category |
| L5-09 | `DELETE /feedback` | Clears all feedback entries |

### 6.2 FeedbackAgent

| # | Test | Expected |
|---|------|----------|
| L5-10 | Computes weights from feedback | Reads last 30 days of entries, calculates rates |
| L5-11 | High FP rate → lower confidence multiplier | 30%+ FP rate for category → multiplier reduced by 0.1 |
| L5-12 | High escalation rate → raise priority weight | 20%+ escalation for source → weight increased by 0.1 |
| L5-13 | Weight clipping | All weights clipped to [0.5, 1.5] |
| L5-14 | feedback_weights.json updated | File written by FeedbackAgent with new weights |
| L5-15 | FEEDBACK_MIN_ENTRIES guard | No weight adjustment until minimum entries reached |
| L5-16 | `POST /feedback/process` | Manually triggers FeedbackAgent |

### 6.3 Feedback Weight Integration

| # | Test | Expected |
|---|------|----------|
| L5-17 | SignalClassifier uses weights | Confidence multiplied by category_confidence_multipliers |
| L5-18 | ArbiterAgent uses weights | Final confidence adjusted by source_priority_weights |
| L5-19 | Weight cache TTL | Weights cached with 60s TTL, not re-read every signal |

---

## 7. Level 6 — Multi-Tenant Federation

### 7.1 Tenant Management

| # | Test | Expected |
|---|------|----------|
| L6-01 | 5 demo tenants exist | default, techcorp, retailco, financeinc, healthco |
| L6-02 | `GET /tenants` | Returns list of all tenants |
| L6-03 | `POST /tenants` | Creates new tenant + Qdrant collections |
| L6-04 | `DELETE /tenants/{id}` | Removes tenant from registry |
| L6-05 | Tenant Qdrant collections | {tenant_id}_signals, {tenant_id}_memory, {tenant_id}_feedback, {tenant_id}_forecasts, {tenant_id}_actions, {tenant_id}_negotiations per tenant |
| L6-06 | TenantContext injection | Pipeline state contains correct collection names for active tenant |

### 7.2 Data Isolation

| # | Test | Expected |
|---|------|----------|
| L6-07 | Run pipeline for techcorp | Signals stored in techcorp_signals only |
| L6-08 | Run pipeline for retailco | Signals stored in retailco_signals only |
| L6-09 | Cross-tenant isolation | techcorp data NOT in retailco collections |
| L6-10 | tenant_id query param | All L1-L5 endpoints accept `?tenant_id=` and scope correctly |

### 7.3 Shared Intelligence

| # | Test | Expected |
|---|------|----------|
| L6-11 | SharedPattern creation | After pipeline run, anonymised pattern written to sentinel_shared_patterns |
| L6-12 | Anonymisation | SharedPattern contains NO tenant_id or company_name |
| L6-13 | Pattern increment | Running same pattern across tenants → occurrence_count increases |
| L6-14 | SharedPatternReader | CausalChainBuilder prompt includes cross-company patterns |
| L6-15 | `GET /shared/patterns` | Returns anonymised patterns |
| L6-16 | `GET /shared/patterns/stats` | Returns cross-tenant statistics |

### 7.4 Demo Company Profiles

| # | Test | Expected |
|---|------|----------|
| L6-17 | TechCorp profile | Technology/SaaS, AWS, Apache, Kubernetes, SOC2, GDPR |
| L6-18 | RetailCo profile | Retail/E-commerce, Azure, Shopify, PCI-DSS |
| L6-19 | FinanceInc profile | Financial Services, Oracle, Kafka, SOX, FINRA |
| L6-20 | HealthCo profile | Healthcare, Epic, HL7, HIPAA |
| L6-21 | Per-tenant sample signals | 12 sample signal files (3 types × 4 tenants) |

---

## 8. Level 7 — Predictive Risk Intelligence

### 8.1 Forecast Infrastructure

| # | Test | Expected |
|---|------|----------|
| L7-01 | ForecastEntry model | ForecastHorizon (H24/H48/H72/H7D), ForecastOutcome (PENDING/CORRECT/INCORRECT/EXPIRED) |
| L7-02 | Forecast store operations | save_forecast, get_forecasts, update_outcome work |
| L7-03 | {tenant_id}_forecasts collection | Created for all demo tenants |

### 8.2 ForecastAgent

| # | Test | Expected |
|---|------|----------|
| L7-04 | Only forecasts P2/P3 signals | P0/P1 signals skipped (already critical) |
| L7-05 | Probability range | All probabilities in [0.0, 1.0] |
| L7-06 | FORECAST_MIN_PROBABILITY filter | Forecasts below 0.40 not stored |
| L7-07 | FORECAST_MIN_HISTORY guard | No forecasting if < 5 past signals |
| L7-08 | Self-calibration | Past accuracy < 0.5 → reduces probability by 0.1; > 0.8 → increases by 0.05 |
| L7-09 | Predictive alert | Probability > FORECAST_ALERT_THRESHOLD (0.80) → alert fired |
| L7-10 | ForecastEntry stored | Entry in {tenant_id}_forecasts after run |
| L7-11 | Thinking=ON | ForecastAgent uses deep reasoning |

### 8.3 WeakSignalDetector

| # | Test | Expected |
|---|------|----------|
| L7-12 | Pre-pipeline detection | Flags weak signals before main pipeline |
| L7-13 | Detection patterns | CVE refs growth, entity importance, cross-tenant match, escalation history |
| L7-14 | No LLM calls | Pure Python heuristic (0 LLM cost) |

### 8.4 ForecastOutcomeTracker

| # | Test | Expected |
|---|------|----------|
| L7-15 | CORRECT resolution | Later signal matches forecast → outcome=CORRECT |
| L7-16 | EXPIRED resolution | Horizon passed, no matching signal, probability < 0.6 → EXPIRED |
| L7-17 | INCORRECT resolution | Horizon passed, no match, probability ≥ 0.6 → INCORRECT |
| L7-18 | `POST /forecasts/resolve` | Manually triggers outcome tracker |
| L7-19 | Background execution | Runs as asyncio.create_task() after pipeline |

### 8.5 API Endpoints

| # | Test | Expected |
|---|------|----------|
| L7-20 | `GET /forecasts` | Returns all forecasts (tenant-scoped) |
| L7-21 | `GET /forecasts/active` | Returns PENDING only |
| L7-22 | `GET /forecasts/{id}` | Returns single forecast detail |
| L7-23 | `GET /forecasts/accuracy` | Returns accuracy metrics per tenant |
| L7-24 | `GET /forecasts/signal/{id}` | Returns forecast for specific signal |
| L7-25 | `GET /forecasts/history` | Returns resolved forecasts |

### 8.6 BriefWriter Upgrade

| # | Test | Expected |
|---|------|----------|
| L7-26 | Predicted Threats section | Brief contains predicted threats with probability > 0.60 |
| L7-27 | Forecast count in brief | `forecast_count` field populated |

---

## 9. Level 8 — Autonomous Actions

### 9.1 Action Infrastructure

| # | Test | Expected |
|---|------|----------|
| L8-01 | ActionType enum | JIRA_TICKET, PAGERDUTY_ALERT, EMAIL_DRAFT, WEBHOOK, SLACK_MESSAGE |
| L8-02 | ActionStatus enum | AUTO_EXECUTED, PENDING_APPROVAL, APPROVED, REJECTED, FAILED, REPORT_ONLY |
| L8-03 | ActionEntry model | All fields (id, tenant_id, signal_id, action_type, status, confidence, etc.) |
| L8-04 | ActionRegistry loads | Per-tenant action_registry.json loaded correctly |
| L8-05 | {tenant_id}_actions collection | Created for all 5 tenants |

### 9.2 Confidence-Gated Autonomy

| # | Test | Expected |
|---|------|----------|
| L8-06 | HIGH confidence (≥ 0.85) | Action auto-executed immediately |
| L8-07 | MODERATE confidence (0.60-0.84) | Action set to PENDING_APPROVAL |
| L8-08 | LOW confidence (< 0.60) | Action set to REPORT_ONLY |
| L8-09 | PagerDuty always auto for P0 | P0 PagerDuty alert → AUTO_EXECUTED regardless |
| L8-10 | Email drafts always pending | EMAIL_DRAFT → always PENDING_APPROVAL |

### 9.3 ActionEngine

| # | Test | Expected |
|---|------|----------|
| L8-11 | Demo mode logging | `ACTION_DEMO_MODE=true` → all integrations log, no real calls |
| L8-12 | Jira handler | `_execute_jira` creates ticket (or logs in demo) |
| L8-13 | PagerDuty handler | `_execute_pagerduty` creates incident (or logs) |
| L8-14 | Email draft handler | `_execute_email_draft` stores draft, does NOT send |
| L8-15 | Webhook handler | `_execute_webhook` posts to URL (or logs) |
| L8-16 | Slack handler | `_execute_slack` posts to webhook (or logs) |
| L8-17 | Failed action status | Integration error → status=FAILED, error logged |

### 9.4 ActionPlanner

| # | Test | Expected |
|---|------|----------|
| L8-18 | Plans actions for Path A | ActionPlanner fires after ArbiterAgent |
| L8-19 | Thinking=ON | Deep reasoning for action planning |
| L8-20 | Multiple actions per signal | Can plan JIRA + PAGERDUTY + SLACK for same P0 |
| L8-21 | Respects registry disabled | Disabled action types not planned |

### 9.5 API & Approval Flow

| # | Test | Expected |
|---|------|----------|
| L8-22 | `GET /actions` | Returns all actions (tenant-scoped) |
| L8-23 | `GET /actions/pending` | Returns PENDING_APPROVAL actions only |
| L8-24 | `POST /actions/{id}/approve` | Status → APPROVED, action executed |
| L8-25 | `POST /actions/{id}/reject` | Status → REJECTED, not executed |
| L8-26 | `GET /actions/audit` | Full audit log of all actions |
| L8-27 | `GET /actions/registry` | Current tenant action configuration |
| L8-28 | `PUT /actions/registry` | Updates action configuration |
| L8-29 | `GET /actions/signal/{id}` | Actions for specific signal |
| L8-30 | Double-approve guard | Approving already approved action → error or no-op |

### 9.6 BriefWriter Actions

| # | Test | Expected |
|---|------|----------|
| L8-31 | Actions Taken section | Brief shows AUTO_EXECUTED actions |
| L8-32 | Pending Approval section | Brief shows PENDING actions |
| L8-33 | Report Only section | Brief shows REPORT_ONLY as recommendations |

---

## 10. Level 9 — Negotiation Pipeline

### 10.1 Negotiation Models

| # | Test | Expected |
|---|------|----------|
| L9-01 | NegotiationStatus enum | SEARCHING, DRAFTING, AWAITING_REPLY, SUMMARISING, COMPLETE, FAILED, DEMO |
| L9-02 | AlternativeSupplier model | name, website, description, relevance_score, search_source |
| L9-03 | OutreachEmail model | supplier, subject, body, sent_at, reply fields |
| L9-04 | NegotiationSession model | Full session with alternatives, emails, recommendation |
| L9-05 | {tenant_id}_negotiations collection | Created for all tenants |

### 10.2 Trigger Conditions

| # | Test | Expected |
|---|------|----------|
| L9-06 | Supplier risk detection | ActionPlanner detects supplier in company_profile.suppliers at risk |
| L9-07 | INITIATE_NEGOTIATION action | ActionEntry created with correct type |
| L9-08 | Async negotiation start | NegotiationPipeline started via asyncio.create_task() |
| L9-09 | Risk score threshold | Only triggers when risk_score ≥ 7.0 AND P0/P1 |

### 10.3 WebSearchAgent

| # | Test | Expected |
|---|------|----------|
| L9-10 | Demo mode alternatives | Returns alternatives from `data/demo_alternatives.json` |
| L9-11 | 3-5 alternatives found | Returns between 3 and 5 AlternativeSupplier objects |
| L9-12 | SerpAPI fallback to DuckDuckGo | If SERPAPI_KEY empty, uses DuckDuckGo scraping |
| L9-13 | Query construction via LLM | Generates relevant search queries (thinking=OFF) |

### 10.4 OutreachDrafter

| # | Test | Expected |
|---|------|----------|
| L9-14 | Professional email draft | Subject + body generated for each alternative |
| L9-15 | Company context in email | Mentions company name, industry, risk reason |
| L9-16 | Thinking=ON | Deep reasoning for email drafting |

### 10.5 ReplyMonitor

| # | Test | Expected |
|---|------|----------|
| L9-17 | Demo mode replies | After delay, loads mock replies from `data/demo_replies.json` |
| L9-18 | Reply matching | Matches replies to correct OutreachEmail by subject/thread |
| L9-19 | Timeout handling | After NEGOTIATION_TIMEOUT_HOURS, proceeds with available replies |

### 10.6 NegotiationSummary

| # | Test | Expected |
|---|------|----------|
| L9-20 | Recommendation generated | Recommended supplier + reasoning from replies |
| L9-21 | Creates recommendation ActionEntry | PENDING_APPROVAL action for "Accept Recommendation" |
| L9-22 | Thinking=ON | Deep reasoning for supplier comparison |

### 10.7 NegotiationPipeline

| # | Test | Expected |
|---|------|----------|
| L9-23 | Full 6-node flow | SEARCH → DRAFT → SEND → MONITOR → SUMMARISE → COMPLETE |
| L9-24 | Status progression | Session status progresses SEARCHING→DRAFTING→...→COMPLETE |
| L9-25 | `GET /negotiations/demo` | Runs full demo negotiation with mock data |
| L9-26 | Session stored | NegotiationSession persisted in {tenant_id}_negotiations |

### 10.8 API Endpoints

| # | Test | Expected |
|---|------|----------|
| L9-27 | `GET /negotiations` | Lists all sessions (tenant-scoped) |
| L9-28 | `GET /negotiations/active` | Returns in-progress sessions |
| L9-29 | `GET /negotiations/{id}` | Full session detail |
| L9-30 | `GET /negotiations/{id}/emails` | Outreach emails for session |
| L9-31 | `POST /negotiations/{id}/send` | Approves and sends emails |
| L9-32 | `POST /negotiations/{id}/cancel` | Cancels mid-workflow |
| L9-33 | `GET /negotiations/{id}/summary` | Final recommendation |
| L9-34 | `POST /negotiations/trigger` | Manually triggers negotiation |

---

## 11. Level 10 — Meta-Governance

### 11.1 MetaAgent

| # | Test | Expected |
|---|------|----------|
| L10-01 | MetaReport model | Contains agent_health, debate_balance, action_effectiveness, overall_health |
| L10-02 | `POST /meta/run` | Triggers MetaAgent manually |
| L10-03 | Agent health collection | Per-agent quality scores, error rates, latency |
| L10-04 | Debate balance computation | Red vs Blue win rates, BALANCED/RED_DOMINANT/BLUE_DOMINANT status |
| L10-05 | Action effectiveness | total_actions, acted_on_rate, auto_execute_rate, rejection_rate |
| L10-06 | Overall health score | Composite 0.0-1.0 (or 0-100 in UI) |
| L10-07 | Critical issues identified | LLM analysis produces issues + recommendations |
| L10-08 | Auto-trigger after N runs | MetaAgent fires every META_RUN_INTERVAL_RUNS pipeline runs |
| L10-09 | META_ENABLED=false | No MetaAgent when disabled |

### 11.2 Remediation

| # | Test | Expected |
|---|------|----------|
| L10-10 | Debate imbalance fix | RedTeam win rate > 0.7 → PromptOptimiser rewrites BlueTeam prompt |
| L10-11 | High error rate alert | Agent error_rate > 0.1 → alert via AlertDispatcher |
| L10-12 | High rejection rate | rejection_rate > 0.5 → ACTION_AUTO_THRESHOLD lowered by 0.05 |

### 11.3 GovernanceLog

| # | Test | Expected |
|---|------|----------|
| L10-13 | GovernanceEntry model | event_type, agent_name, tenant_id, description, reasoning, confidence, human_involved |
| L10-14 | Immutable log | Entries are write-once, never updated or deleted |
| L10-15 | All autonomous decisions logged | ACTION_EXECUTED, PROMPT_CHANGED, WEIGHT_ADJUSTED, etc. |
| L10-16 | `GET /governance/log` | Returns paginated log entries |
| L10-17 | Filter by event_type | `GET /governance/log?event_type=ACTION_EXECUTED` filters correctly |
| L10-18 | GOVERNANCE_ENABLED=false | No logging when disabled |

### 11.4 HumanOverrideSystem

| # | Test | Expected |
|---|------|----------|
| L10-19 | Create override | `POST /governance/overrides` creates OverrideRule |
| L10-20 | Override scopes | AGENT, ACTION_TYPE, TENANT, GLOBAL scopes all work |
| L10-21 | Override blocks execution | ActionEngine check_override before execute → skip if active |
| L10-22 | Override logged | Skipped actions logged to GovernanceLog |
| L10-23 | Deactivate override | `DELETE /governance/overrides/{id}` deactivates rule |
| L10-24 | Execution resumes | After deactivation, agents run normally |
| L10-25 | GLOBAL override | Blocks ALL autonomous actions system-wide |
| L10-26 | Override persistence | Rules persisted in `data/override_rules.json` |

### 11.5 ABTestManager

| # | Test | Expected |
|---|------|----------|
| L10-27 | Start test | When PromptOptimiser saves new version → A/B test starts |
| L10-28 | Variant routing | Odd runs → variant A (current), even runs → variant B (challenger) |
| L10-29 | Quality tracking | quality_sum_a, quality_sum_b accumulated per run |
| L10-30 | Winner declaration | After AB_TEST_MIN_RUNS → winner automatically selected |
| L10-31 | Winner activated | Winning prompt becomes active version |
| L10-32 | Result logged | A/B test result logged to GovernanceLog |
| L10-33 | AB_TEST_ENABLED=false | No A/B testing when disabled |

### 11.6 AgentHealthEvent

| # | Test | Expected |
|---|------|----------|
| L10-34 | Events emitted | Every agent emits AgentHealthEvent after each run |
| L10-35 | Events written | HealthEventWriter writes events to sentinel_meta |
| L10-36 | Fields populated | agent_name, success, latency_ms, quality_score, error |

### 11.7 API Endpoints

| # | Test | Expected |
|---|------|----------|
| L10-37 | `GET /meta/reports` | Lists MetaReports |
| L10-38 | `GET /meta/reports/latest` | Most recent MetaReport |
| L10-39 | `GET /meta/health` | Current agent health scores |
| L10-40 | `GET /meta/debate-balance` | Red vs Blue win rates |
| L10-41 | `GET /meta/action-effectiveness` | Action acted-on rates |
| L10-42 | `GET /governance/overrides` | Active override rules |
| L10-43 | `GET /ab-tests` | Lists all A/B tests |
| L10-44 | `GET /ab-tests/active` | Currently running tests |

---

## 12. Cross-Cutting Tests

### 12.1 LLM & Embedding

| # | Test | Expected |
|---|------|----------|
| CC-01 | All LLM calls via client.py | No direct OpenAI SDK usage outside sentinel/llm/client.py |
| CC-02 | No hardcoded model strings | All agents use settings.SENTINEL_PRIMARY_MODEL |
| CC-03 | Groq provider works | Full pipeline completes with LLM_PROVIDER=groq |
| CC-04 | Embedding dimension 3072 | All Qdrant collections sized at 3072 for gemini-embedding-001 |

### 12.2 Logging

| # | Test | Expected |
|---|------|----------|
| CC-05 | No print() statements | `grep -r "print(" sentinel/` returns 0 results (excluding test files) |
| CC-06 | structlog throughout | All agents use structlog for logging |
| CC-07 | Errors logged before raising | Every except block logs via structlog |

### 12.3 Async

| # | Test | Expected |
|---|------|----------|
| CC-08 | All agent methods async | Every `run()` method is `async def` |
| CC-09 | Background tasks non-blocking | FeedbackAgent, ForecastOutcomeTracker, PromptOptimiser run via asyncio.create_task() |
| CC-10 | Windows compatibility | No asyncio event loop issues on Windows 11 |

### 12.4 Pydantic Enforcement

| # | Test | Expected |
|---|------|----------|
| CC-11 | No raw dicts between agents | All inter-agent data uses Pydantic models |
| CC-12 | Type hints everywhere | All function signatures have type hints |
| CC-13 | Model validation | Invalid data raises ValidationError |

### 12.5 Demo Mode

| # | Test | Expected |
|---|------|----------|
| CC-14 | DEMO_MODE=true fallback | All sensor agents return sample data |
| CC-15 | No external API calls in demo | No real HTTP calls to NewsAPI, NVD, EDGAR in demo |
| CC-16 | LLM still runs in demo | Gemini/Groq calls are real even in demo mode |
| CC-17 | AlertDispatcher demo | Logs instead of sending email/Slack |
| CC-18 | ActionEngine demo | Logs instead of calling Jira/PagerDuty/webhooks |
| CC-19 | ReplyMonitor demo | Uses mocked replies instead of IMAP polling |

---

## 13. End-to-End Integration Tests

### 13.1 Single-Tenant Full Pipeline

| # | Test | Expected |
|---|------|----------|
| E2E-01 | Full pipeline end-to-end | `POST /ingest` → 10 signals → 10 reports → 1 brief → memory entries → forecasts → actions |
| E2E-02 | Pipeline timing | Completes within 5 minutes in demo mode |
| E2E-03 | All agent nodes execute | structlog shows all 22 nodes running |
| E2E-04 | Brief quality scored | QualityScore present in pipeline result |
| E2E-05 | Memory entries written | MemoryWriter stores entries after run |
| E2E-06 | Shared patterns written | SharedPatternWriter creates/updates patterns |
| E2E-07 | FeedbackAgent triggered | Background task fires after pipeline |
| E2E-08 | ForecastOutcomeTracker triggered | Background task fires after pipeline |
| E2E-09 | GovernanceLog populated | Autonomous decisions logged |

### 13.2 Multi-Tenant Pipeline

| # | Test | Expected |
|---|------|----------|
| E2E-10 | Sequential tenant runs | Run pipeline for techcorp then retailco — both succeed |
| E2E-11 | Data isolation verified | techcorp signals not in retailco collections |
| E2E-12 | Shared intelligence cross-pollination | Patterns from techcorp run benefit retailco run |
| E2E-13 | Tenant-scoped API responses | `GET /alerts?tenant_id=techcorp` returns only techcorp alerts |

### 13.3 Feedback Loop Verification

| # | Test | Expected |
|---|------|----------|
| E2E-14 | Loop 1: low confidence | Signal with confidence < 0.5 → re-processed, loop counter increments |
| E2E-15 | Loop 2: Red Team wins | Red Team victory → priority escalated, re-runs RiskAssessor |
| E2E-16 | Prompt evolution | Low quality score → PromptOptimiser fires → new prompt version → next run uses it |
| E2E-17 | Feedback weight adjustment | Submit FALSE_POSITIVE feedback → weights change → next run uses adjusted weights |

### 13.4 Multi-Run Pipeline Evolution

| # | Test | Expected |
|---|------|----------|
| E2E-18 | Run 1: baseline | First run establishes baseline data |
| E2E-19 | Run 2: memory active | Second run agents receive memory context from run 1 |
| E2E-20 | Run 3: quality trend | Third run shows quality trend data |
| E2E-21 | Run 5: MetaAgent fires | Fifth run triggers MetaAgent (META_RUN_INTERVAL_RUNS=5) |
| E2E-22 | MetaReport generated | Health scores, debate balance, action effectiveness populated |

---

## 14. UI / Frontend Tests

### 14.1 Navigation

| # | Test | Expected |
|---|------|----------|
| UI-01 | Top navigation | All nav items: Pipeline, Alerts, Briefs, Company, Memory, Prompts, Feedback, Forecasts, Actions, Negotiations, Shared Intel, Tenants, Governance |
| UI-02 | Active nav highlighting | Current page nav item highlighted |
| UI-03 | Version badge | Shows v10.0 / 22 nodes |
| UI-04 | Tenant switcher | Dropdown in header, shows all tenants |
| UI-05 | Tenant switch effect | Switching tenant reloads all pages with new data |

### 14.2 Pipeline Monitor (/)

| # | Test | Expected |
|---|------|----------|
| UI-06 | Stat cards | All stat cards render: Signals, Reports, Quality Score, Memory, Forecasts, Accuracy, Actions |
| UI-07 | Run Pipeline button | Triggers `POST /ingest`, shows loading state |
| UI-08 | Agent pipeline pills | Show idle/running/complete/error states |
| UI-09 | Auto-refresh | Polls `/pipeline/status` every 2s during run |

### 14.3 Alerts Board (/alerts)

| # | Test | Expected |
|---|------|----------|
| UI-10 | 4-column layout | P0/P1/P2/P3 columns with colour-coded headers |
| UI-11 | Alert cards | Show confidence bar, company match badge, relevance bar |
| UI-12 | Forecast badge | P2/P3 cards show "Forecast: P0 in 72h" if applicable |
| UI-13 | Feedback buttons | 4 action buttons (Acted On, False Positive, Escalate, Dismiss) |
| UI-14 | Feedback recorded | After clicking, buttons replaced with confirmation badge |
| UI-15 | Auto-refresh | Re-fetches alerts every 5s |
| UI-16 | "Seen before" badge | Shows when memory has similar past events |

### 14.4 Briefs (/briefs)

| # | Test | Expected |
|---|------|----------|
| UI-17 | SVG confidence gauge | Renders correctly without library |
| UI-18 | React-flow DAG | Causal chain displays as indigo nodes with slate edges |
| UI-19 | Red vs Blue panels | Side-by-side with coloured borders |
| UI-20 | Predicted Threats section | Shows forecasted escalations with probability bars |
| UI-21 | Actions Taken/Pending sections | Show autonomous actions in brief |
| UI-22 | Memory Context section | Shows past events that informed analysis |
| UI-23 | Company Exposure section | Shows profile match details |
| UI-24 | "Optimised" badge | Shows if brief used optimised prompt (version > 1) |

### 14.5 Company Profile (/company)

| # | Test | Expected |
|---|------|----------|
| UI-25 | Profile form | All fields editable with tags input |
| UI-26 | Save | Calls `PUT /company/profile`, shows success |
| UI-27 | Last updated timestamp | Updates after save |

### 14.6 Memory (/memory)

| # | Test | Expected |
|---|------|----------|
| UI-28 | Timeline view | Entries shown newest first |
| UI-29 | Search | Live search calls `/memory/search` |
| UI-30 | Patterns tab | Grouped by entity with occurrence counts |

### 14.7 Prompts (/prompts)

| # | Test | Expected |
|---|------|----------|
| UI-31 | Agent list | All 9 LLM agents listed |
| UI-32 | Version history | Shows all versions with dates, scores |
| UI-33 | Active badge | Current active version marked |
| UI-34 | Rollback button | Works, reverts to selected version |
| UI-35 | Trigger Optimisation | Button triggers manual optimisation |

### 14.8 Feedback (/feedback)

| # | Test | Expected |
|---|------|----------|
| UI-36 | Summary cards | Acted On rate, FP rate, Escalations, Dismissals |
| UI-37 | Feedback timeline | All entries with action badges |
| UI-38 | Weight table | Shows current multipliers |
| UI-39 | Process Feedback button | Triggers FeedbackAgent |

### 14.9 Forecasts (/forecasts)

| # | Test | Expected |
|---|------|----------|
| UI-40 | Hero section | Shows active forecast count |
| UI-41 | Forecast cards | Probability bar, priority badges, expandable reasoning |
| UI-42 | Active/History tabs | Toggle between pending and resolved |
| UI-43 | Accuracy tab | Shows accuracy per category |
| UI-44 | Resolve Pending button | Triggers outcome tracker |

### 14.10 Actions (/actions)

| # | Test | Expected |
|---|------|----------|
| UI-45 | Pending Approval section | Shows pending actions with approve/reject |
| UI-46 | Approve button | Calls approve endpoint, action executed |
| UI-47 | Reject button | Calls reject endpoint, action marked rejected |
| UI-48 | Audit tab | Shows full action audit log |
| UI-49 | Registry tab | Shows toggles for each action type |

### 14.11 Negotiations (/negotiations)

| # | Test | Expected |
|---|------|----------|
| UI-50 | Status timeline | SEARCHING→DRAFTING→AWAITING→SUMMARISING→COMPLETE |
| UI-51 | Alternative supplier cards | Show name, website, relevance score |
| UI-52 | Email cards | Draft/Sent/Reply status for each outreach |
| UI-53 | Recommendation section | Recommended supplier with reasoning |
| UI-54 | History tab | Past completed negotiations |

### 14.12 Shared Intelligence (/shared)

| # | Test | Expected |
|---|------|----------|
| UI-55 | Headline stat | "Protecting N companies — M shared patterns" |
| UI-56 | Pattern cards | Type, affected industries, occurrence count, risk score |
| UI-57 | Search bar | Searches shared patterns |
| UI-58 | Privacy notice | "Privacy by Design" notice displayed |

### 14.13 Tenants (/tenants)

| # | Test | Expected |
|---|------|----------|
| UI-59 | Tenant cards | Name, industry, signal count, last run |
| UI-60 | Add Company | Form creates new tenant |
| UI-61 | Delete | Removes tenant with confirmation |

### 14.14 Governance (/governance)

| # | Test | Expected |
|---|------|----------|
| UI-62 | Health gauge | SVG circular gauge (0-100) with colour coding |
| UI-63 | Agent Health Table | Sortable, expandable issues per agent |
| UI-64 | Debate Balance | Red/Blue bars with BALANCED/DOMINANT badge |
| UI-65 | Action Effectiveness | Total, acted-on rate, auto-exec rate |
| UI-66 | A/B Tests | Active tests with progress bars |
| UI-67 | Governance Log | Colour-coded event badges, HUMAN/OVERRIDE tags |
| UI-68 | Override Controls | Create/deactivate overrides |
| UI-69 | Run Analysis button | Triggers MetaAgent, populates all sections |

---

## 15. Performance & Stress Tests

| # | Test | Expected |
|---|------|----------|
| PS-01 | Pipeline with 10 signals | Completes in < 5 minutes (demo mode) |
| PS-02 | Qdrant query latency | Semantic search < 200ms per query |
| PS-03 | Concurrent tenant runs | 2 tenant pipelines running simultaneously don't interfere |
| PS-04 | Memory growth | Memory entries don't grow unbounded (90-day window) |
| PS-05 | Background task cleanup | asyncio tasks complete and don't leak |
| PS-06 | API response times | All GET endpoints respond in < 500ms |
| PS-07 | Large governance log | Log with 1000+ entries paginates correctly |
| PS-08 | Multiple pipeline runs | 10 consecutive runs don't crash or leak memory |

---

## 16. Security & Data Isolation Tests

| # | Test | Expected |
|---|------|----------|
| SEC-01 | Tenant data isolation | Tenant A cannot access Tenant B's signals, memory, feedback |
| SEC-02 | Shared pattern anonymisation | No tenant_id or company_name in shared patterns |
| SEC-03 | Override protection | GLOBAL override blocks ALL autonomous actions |
| SEC-04 | Governance log immutability | Log entries cannot be modified or deleted via API |
| SEC-05 | CORS enforcement | Only localhost:3000 allowed, other origins rejected |
| SEC-06 | API key not exposed | OPENROUTER_API_KEY, GROQ_API_KEY not in API responses |
| SEC-07 | Override persistence | Override rules survive server restart |
| SEC-08 | Feedback weight bounds | Weights never go below 0.5 or above 1.5 |
| SEC-09 | No tenant crossover in searches | Qdrant queries always scoped to correct collection |

---

## 17. Failure & Recovery Tests

### 17.1 External Service Failures

| # | Test | Expected |
|---|------|----------|
| FR-01 | Qdrant down | Pipeline fails gracefully, logs error, no data loss |
| FR-02 | LLM API timeout | Tenacity retries 3 times, then fails gracefully |
| FR-03 | LLM returns malformed JSON | Agent parses gracefully, uses fallback/empty values |
| FR-04 | NewsAPI down (live mode) | Falls back to demo data automatically |
| FR-05 | NVD API down | Falls back to demo data |
| FR-06 | SEC EDGAR down | Falls back to demo data |
| FR-07 | SMTP connection fails | AlertDispatcher logs error, pipeline continues |
| FR-08 | Slack webhook fails | Log error, pipeline continues |
| FR-09 | SerpAPI down | WebSearchAgent falls back to DuckDuckGo |
| FR-10 | DuckDuckGo scraping fails | Falls back to demo alternatives |

### 17.2 Data Edge Cases

| # | Test | Expected |
|---|------|----------|
| FR-11 | Empty signal list | Pipeline handles 0 signals gracefully |
| FR-12 | All P3 signals | All signals route to LOG_ONLY path |
| FR-13 | All P0 signals | All signals route to FULL path |
| FR-14 | No company profile | RiskAssessor uses default exposure (no profile boost) |
| FR-15 | Empty memory | Agents work without memory context |
| FR-16 | No feedback entries | FeedbackAgent skips weight adjustment |
| FR-17 | No forecast history | ForecastAgent skips forecasting (FORECAST_MIN_HISTORY guard) |
| FR-18 | Empty prompt store | Agents fall back to hardcoded prompts |
| FR-19 | Invalid signal_id in feedback | Returns 404, no crash |
| FR-20 | Duplicate pipeline trigger | Second ingest while running is rejected or queued |

### 17.3 Recovery

| # | Test | Expected |
|---|------|----------|
| FR-21 | Server restart mid-pipeline | Pipeline state not corrupted, can re-run |
| FR-22 | Qdrant data survives restart | Docker volume persists data |
| FR-23 | Override rules survive restart | JSON file persisted on disk |
| FR-24 | Feedback weights survive restart | JSON file persisted |
| FR-25 | Tenant registry survives restart | JSON file persisted |

---

## 18. Demo Mode Validation

Full end-to-end demo walkthrough — validates the entire system works in demo mode without any real external APIs (except LLM).

| # | Test | Expected |
|---|------|----------|
| DM-01 | Start all services | Docker + backend + frontend all start without errors |
| DM-02 | Pipeline run (demo) | `POST /ingest` with DEMO_MODE=true → completes, 10 signals processed |
| DM-03 | Alerts populated | 10 alerts across P0-P3 columns |
| DM-04 | Brief generated | Executive brief with sections, alerts, recommendations |
| DM-05 | Company profile loaded | Meridian Technologies (or tenant profile) shown |
| DM-06 | Memory entries created | Memory page shows entries from pipeline run |
| DM-07 | Forecasts generated | P2/P3 signals get forecast entries |
| DM-08 | Quality scored | QualityScore attached to brief |
| DM-09 | Actions planned | ActionPlanner generates actions for P0/P1 signals |
| DM-10 | Governance log populated | Entries logged for autonomous decisions |
| DM-11 | MetaAgent report | "Run Analysis" on Governance page produces health report |
| DM-12 | Tenant switching | Switch between techcorp/retailco/financeinc/healthco — data changes |
| DM-13 | Shared intel populated | /shared shows cross-company patterns |
| DM-14 | Negotiation demo | `GET /negotiations/demo` runs full negotiation workflow |
| DM-15 | All pages render | Every UI page loads without error or blank sections |
| DM-16 | No external API calls | Verify no calls to NewsAPI, NVD, SEC EDGAR, Jira, PagerDuty, SMTP, Slack, SerpAPI |

---

## Test Execution Checklist

### Phase 1: Pre-Flight
- [ ] PF-01 through PF-18

### Phase 2: Unit Tests
- [ ] `python -m pytest tests/unit/ -q` — all pass
- [ ] `npx tsc --noEmit` — 0 errors

### Phase 3: Component Tests (by Level)
- [ ] L1-01 through L1-52
- [ ] L2-01 through L2-15
- [ ] L3-01 through L3-19
- [ ] L4-01 through L4-21
- [ ] L5-01 through L5-19
- [ ] L6-01 through L6-21
- [ ] L7-01 through L7-27
- [ ] L8-01 through L8-33
- [ ] L9-01 through L9-34
- [ ] L10-01 through L10-44

### Phase 4: Cross-Cutting
- [ ] CC-01 through CC-19

### Phase 5: End-to-End
- [ ] E2E-01 through E2E-22

### Phase 6: UI
- [ ] UI-01 through UI-69

### Phase 7: Performance
- [ ] PS-01 through PS-08

### Phase 8: Security
- [ ] SEC-01 through SEC-09

### Phase 9: Failure & Recovery
- [ ] FR-01 through FR-25

### Phase 10: Full Demo
- [ ] DM-01 through DM-16

---

**Total Test Cases: 369**

> All tests should pass before the system is considered production-ready.
> Priority order: Pre-Flight → Unit → Demo Mode → Component → E2E → UI → Security → Performance → Failure
