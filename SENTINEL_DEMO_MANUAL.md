# SENTINEL — Complete Demo & Rehearsal Manual

## Autonomous Multi-Agent Enterprise Risk Intelligence System
### Levels 1–10 · 22 AI Agents · 7 Processing Layers · Multi-Tenant Architecture

---

## How to Use This Manual

This manual is your single reference for setting up, running, and demonstrating the entire SENTINEL system. It is written so that **anyone** — even someone who has never seen the project — can follow every step and present a polished live demo.

**Structure:**
- **Part 1** — Startup: How to launch all services from scratch
- **Part 2** — System Overview: What the system does and how it works (read this to understand before demoing)
- **Part 3** — Functionality Walkthrough: Step-by-step verification of every feature, level by level
- **Part 4** — Live Demo Script: Exactly what to say and show during a presentation
- **Part 5** — Common Questions & Answers
- **Part 6** — Troubleshooting Guide
- **Part 7** — Quick Reference Card

---

## PART 1 — STARTUP

> **You must complete these steps every time before running SENTINEL.** All three services (Qdrant, Backend, Frontend) must be running simultaneously.

### Step 1: Start Qdrant (Vector Database)

Open **Terminal 1** and run:

```powershell
docker-compose up -d
```

Wait 5 seconds, then verify Qdrant is running:

```powershell
Invoke-RestMethod -Uri http://localhost:6333/collections
```

**What you should see:** A JSON response listing collections. If you see an error, Docker Desktop may not be running — open it first, wait 30 seconds, then retry.

### Step 2: Initialise the Database (First time only)

If this is your **first time** starting the system (or after a clean reset), run these seed scripts in order:

```powershell
python scripts/init_qdrant.py            # Creates all Qdrant collections
python scripts/init_prompts.py           # Seeds 9 agent prompts (version 1)
python scripts/init_tenants.py           # Creates 5 demo tenants
python scripts/seed_shared_patterns.py   # Seeds 6 shared intelligence patterns
python scripts/seed_forecast_history.py  # Seeds 120 historical entries for forecasting
```

**What you should see:** Each script prints a confirmation message. No errors should appear.

> **Note:** You do NOT need to re-run these scripts on subsequent startups unless you completely wipe your Qdrant data.

### Step 3: Start the Backend API Server

Open **Terminal 2** and run:

```powershell
cd "c:\Learnings\Projects\8sem project design"
uvicorn sentinel.main:app --reload --port 8000
```

**What you should see:** The terminal prints `INFO: Application startup complete` and shows the active LLM provider (OpenRouter or Groq) and demo mode status. The `--reload` flag means the server auto-restarts when you edit Python files.

### Step 4: Start the Frontend UI

Open **Terminal 3** and run:

```powershell
cd "c:\Learnings\Projects\8sem project design\sentinel-ui"
npm run dev
```

**What you should see:** Next.js compiles and prints `Ready on http://localhost:3000`. Open this URL in your browser.

### Step 5: Verify Everything Works

Open your browser to **http://localhost:3000**. You should see the SENTINEL dashboard with:
- A top navigation bar (Pipeline, Alerts, Briefs, Company, Memory, Prompts, Feedback, Forecasts, Actions, Negotiations, Shared Intel, Tenants, Governance)
- A version badge showing **v10.0 / 22 nodes**
- A tenant switcher dropdown in the header
- Stat cards showing zeros (no pipeline has run yet)

Also open **http://localhost:8000/docs** in another tab — this is the FastAPI Swagger UI where you can see and test all API endpoints.

---

## PART 2 — SYSTEM OVERVIEW

> **Read this section before demoing.** Understanding how SENTINEL works end-to-end will make your demo confident and clear.

### What is SENTINEL?

SENTINEL is an **autonomous multi-agent system** that continuously monitors external risk signals (cybersecurity threats, financial filings, geopolitical news), analyses them through a layered pipeline of specialised AI agents, and produces actionable intelligence briefs personalised to your company. Unlike a chatbot, SENTINEL runs **without being asked** — it monitors, classifies, debates, acts, and learns autonomously.

### The 10-Level Architecture

| Level | Name | What It Does |
|-------|------|--------------|
| **1** | Core Pipeline | 11 agents process signals through sensing → classification → reasoning → deliberation → output |
| **2** | Company DNA | Personalises risk scoring using your company profile (tech stack, suppliers, regulations) |
| **3** | Agent Memory | Every run is remembered. Agents use past analyses to detect recurring patterns and improve |
| **4** | Self-Improving Prompts | A QualityAgent scores each brief. If quality is below threshold, the system rewrites its own prompts |
| **5** | Human Feedback | Users rate alerts (Acted On / False Positive / Escalate / Dismiss). The system adjusts confidence weights |
| **6** | Multi-Tenant Federation | Multiple companies share the same system. Data is isolated, but threat patterns are shared anonymously |
| **7** | Predictive Intelligence | Forecasts which low-priority signals will escalate, using historical pattern analysis |
| **8** | Autonomous Actions | High-confidence threats trigger automatic responses (Jira tickets, PagerDuty alerts, Slack messages) |
| **9** | Negotiation Pipeline | When a supplier risk is detected, SENTINEL searches for alternatives, drafts outreach emails, and recommends replacements |
| **10** | Meta-Governance | A MetaAgent monitors the health of all other agents, runs A/B tests on prompts, and maintains an immutable governance log |

### The 7 Processing Layers

When you trigger the pipeline, signals pass through **7 layers** in sequence:

```
Layer 0: SENSORS
  NewsScanner → CyberThreatAgent → FinancialSignalAgent
  (Gathers raw signals from news, CVE databases, SEC filings)
         ↓
Layer 1: PROCESSING
  EntityExtractor → SignalClassifier
  (Extracts entities, assigns priority P0–P3)
  ↺ Loop 1: If confidence < 0.5, re-process
         ↓
Layer 1.5: ROUTING
  RouterAgent
  (Decides: FULL path / FAST path / LOG_ONLY path)
         ↓
Layer 2: REASONING
  RiskAssessor → CausalChainBuilder
  (Scores risk, builds cause-effect chains)
         ↓
Layer 3: DELIBERATION
  RedTeamAgent → BlueTeamAgent → ArbiterAgent
  (Adversarial debate: challenge → defend → verdict)
  ↺ Loop 2: If RedTeam wins, escalate and re-assess
         ↓
Layer 4: OUTPUT
  BriefWriter → QualityAgent → PromptOptimiser (async)
  (Generates brief, scores quality, self-improves)
         ↓
Layer 5: PERSISTENCE
  MemoryWriter → SharedPatternWriter → ForecastAgent → ActionPlanner
  (Stores results, shares patterns, makes predictions, plans actions)
```

### The 22 AI Agents

| # | Agent | Layer | Purpose |
|---|-------|-------|---------|
| 1 | NewsScanner | 0 | Collects geopolitical and industry news signals |
| 2 | CyberThreatAgent | 0 | Collects CVE vulnerabilities and cyber advisories |
| 3 | FinancialSignalAgent | 0 | Collects SEC filings, bankruptcy warnings, earnings |
| 4 | EntityExtractor | 1 | Extracts organisations, people, products, CVEs, locations |
| 5 | SignalClassifier | 1 | Assigns priority (P0–P3) and confidence score |
| 6 | RouterAgent | 1.5 | Routes signals to FULL, FAST, or LOG_ONLY processing path |
| 7 | RiskAssessor | 2 | Scores risk using `impact × probability × exposure × 10` |
| 8 | CausalChainBuilder | 2 | Builds DAG of cause → effect relationships (uses deep thinking) |
| 9 | RedTeamAgent | 3 | Adversarial: challenges the risk assessment, finds blind spots |
| 10 | BlueTeamAgent | 3 | Defensive: provides mitigating factors and defences |
| 11 | ArbiterAgent | 3 | Judges the debate, sets final confidence and verdict |
| 12 | BriefWriter | 4 | Generates the executive intelligence brief |
| 13 | QualityAgent | 4 | Scores the brief on 5 dimensions (specificity, evidence, clarity, actionability, completeness) |
| 14 | PromptOptimiser | 4 | Rewrites weak agent prompts when quality drops below 0.70 |
| 15 | MemoryWriter | 5 | Persists analysis results for future reference |
| 16 | SharedPatternWriter | 5 | Anonymises and shares threat patterns across tenants |
| 17 | ForecastAgent | 5 | Predicts which P2/P3 signals will escalate to P0/P1 |
| 18 | WeakSignalDetector | 5 | Flags emerging weak signals before they escalate (no LLM, pure heuristics) |
| 19 | ForecastOutcomeTracker | 5 | Validates past predictions against new data |
| 20 | ActionPlanner | 5 | Decides what autonomous actions to take (Jira, PagerDuty, Slack, etc.) |
| 21 | FeedbackAgent | 5 | Adjusts confidence weights based on human feedback |
| 22 | MetaAgent | 6 | Monitors all agents' health, debate balance, and action effectiveness |

### Demo Mode

When `DEMO_MODE=true` (set in `.env`), SENTINEL uses **pre-built sample data** instead of calling real external APIs:
- **Sensors** return 10 signals from JSON files (4 news + 3 cyber + 3 financial)
- **LLM calls are still real** — Gemini/Groq processes every signal through reasoning and debate
- **Alerts, Actions, Negotiations** are logged instead of sending real emails/Slack/Jira

This means you get a full, realistic demo without needing NewsAPI, NVD, or Jira credentials.

### The 5 Demo Tenants

| Tenant | Industry | Key Technologies | Regulations |
|--------|----------|-------------------|-------------|
| **default** (Meridian Technologies) | Technology / SaaS | Apache, Kubernetes, PostgreSQL | SOC2, GDPR |
| **techcorp** | Technology / SaaS | AWS, Apache, Kubernetes | SOC2, GDPR |
| **retailco** | Retail / E-commerce | Azure, Shopify | PCI-DSS |
| **financeinc** | Financial Services | Oracle, Kafka | SOX, FINRA |
| **healthco** | Healthcare | Epic, HL7 | HIPAA |

Each tenant has its own isolated data collections in Qdrant and its own company profile. Threat patterns are shared anonymously between tenants.

---

## PART 3 — FUNCTIONALITY WALKTHROUGH

> **Go through each level in order.** Each step tells you exactly what to do, where to look, and what you should see. Check the box once verified.

### LEVEL 1 — Core Pipeline (The Foundation)

**What this level proves:** The entire multi-agent pipeline runs end-to-end — 10 signals enter, an intelligence brief exits.

**Step 1.1 — Trigger the Pipeline**

```
In browser: http://localhost:3000 → Click "Run Pipeline" button
   OR
API call:   POST http://localhost:8000/ingest
```

- [ ] The UI shows a loading spinner and agent status pills turn yellow/green as each agent runs
- [ ] Terminal 2 (backend) shows log messages for each agent in sequence:
  `NewsScanner → CyberThreatAgent → FinancialSignalAgent → EntityExtractor → SignalClassifier → RouterAgent → RiskAssessor → CausalChainBuilder → RedTeamAgent → BlueTeamAgent → ArbiterAgent → BriefWriter → QualityAgent → MemoryWriter`

> **Wait approximately 3–5 minutes** for the pipeline to complete. Each LLM agent makes a real API call, so the total time depends on your LLM provider's speed.

**Step 1.2 — Verify Pipeline Output**

```
API: GET http://localhost:8000/pipeline/status
```

- [ ] Response shows `"status": "completed"` and `"signal_count": 10`
- [ ] The UI Pipeline page shows all stat cards populated: Signals (10), Reports, Quality Score, Memory entries, Forecasts, Actions

**Step 1.3 — Check the Intelligence Brief**

```
UI:  http://localhost:3000/briefs
API: GET http://localhost:8000/briefs/latest
```

- [ ] A full executive brief is displayed with:
  - Title and executive summary
  - Multiple sections (one per risk category)
  - Alert items with priority labels
  - Recommendations specific to your company's tech stack
- [ ] The brief is NOT empty or placeholder text

**Step 1.4 — Check Alerts**

```
UI:  http://localhost:3000/alerts
API: GET http://localhost:8000/alerts
```

- [ ] Alerts are displayed in 4 columns: P0 (Critical), P1 (High), P2 (Medium), P3 (Low)
- [ ] Each alert card shows a confidence bar, source, and recommended action
- [ ] At least 1 P0 alert exists (from demo data distribution: 2 P0, 3 P1, 3 P2, 2 P3)

---

### LEVEL 2 — Company DNA + Dynamic Routing

**What this level proves:** SENTINEL personalises risk analysis based on your company's specific profile — your tech stack, suppliers, regulations, and industry.

**Step 2.1 — View the Company Profile**

```
UI:  http://localhost:3000/company
API: GET http://localhost:8000/company/profile
```

- [ ] Profile shows company name (e.g., "Meridian Technologies"), industry, tech stack, suppliers, regions, and regulatory scope
- [ ] All fields are editable in the UI with a "Save" button

**Step 2.2 — Test Profile Editing**

- [ ] In the UI, add "Redis" to the tech_stack field → click Save
- [ ] Verify via API: `GET /company/profile` → tech_stack includes "Redis"
- [ ] Remove "Redis" and save again to restore original

**Step 2.3 — Verify Dynamic Routing**

During the pipeline run (Step 1.1), check Terminal 2 for routing decisions:

- [ ] You see `route.decision path=FULL` for P0/P1 signals (full pipeline with debate)
- [ ] You see `route.decision path=FAST` for P2 signals (skip deliberation)
- [ ] You see `route.decision path=LOG_ONLY` for P3 signals (minimal processing)

**Step 2.4 — Check Personalised Risk Scoring**

```
API: GET http://localhost:8000/company/profile/matches
```

- [ ] Returns a list of signals sorted by `relevance_score` (highest first)
- [ ] Signals mentioning your tech stack items (Apache, Kubernetes) score higher than generic signals

> **Why this matters:** A critical Apache vulnerability scores much higher for a company that actually uses Apache. Generic threats get deprioritised.

---

### LEVEL 3 — Agent Memory + Alerts

**What this level proves:** The system remembers past analyses and uses them to improve future ones. Alerts fire automatically for high-risk signals.

**Step 3.1 — Verify Memory Entries**

```
UI:  http://localhost:3000/memory
API: GET http://localhost:8000/memory/search?q=apache
```

- [ ] Memory entries exist (created during the pipeline run in Level 1)
- [ ] Searching for "apache" returns relevant past entries
- [ ] The Memory page in the UI shows a timeline of entries, newest first

**Step 3.2 — Check Memory Patterns**

```
API: GET http://localhost:8000/memory/patterns
```

- [ ] Returns grouped patterns showing recurring threat categories
- [ ] Each pattern shows an `occurrence_count` (how many times this type of threat has been seen)

**Step 3.3 — Run Pipeline a Second Time (Important!)**

- [ ] Run the pipeline again: click "Run Pipeline" in the UI or `POST /ingest`
- [ ] Wait for completion (~3-5 minutes)
- [ ] Check Terminal 2 for `memory_context` — agents now include past analyses in their reasoning
- [ ] Open `/briefs` → the latest brief should include a "Memory Context" section referencing past events

> **Key insight for demo:** The second run is where you prove the system **learns**. Agents reference "we've seen similar patterns before" — this happens automatically without retraining.

**Step 3.4 — Test Alert Dispatcher**

```
API: POST http://localhost:8000/alerts/test
```

- [ ] Terminal 2 shows an alert was logged (in demo mode, alerts are logged instead of emailed/Slacked)
- [ ] P0 signals with high relevance automatically trigger alerts during pipeline runs

**Step 3.5 — Verify Personalised Recommendations**

- [ ] Open the latest brief at `/briefs`
- [ ] Recommendations should reference your company's specific tech stack (e.g., "Update Apache to version X" instead of generic "patch your systems")
- [ ] If your company has regulatory scope (GDPR, SOC2), recommendations reference specific regulation articles

---

### LEVEL 4 — Self-Improving Prompts

**What this level proves:** The system evaluates the quality of its own output and automatically rewrites its internal prompts to improve.

**Step 4.1 — Check Prompt Store**

```
UI:  http://localhost:3000/prompts
API: GET http://localhost:8000/prompts/BriefWriter
```

- [ ] All 9 LLM agents are listed, each with a version number
- [ ] BriefWriter shows version 1 (or higher if PromptOptimiser has already run)
- [ ] Clicking an agent shows the full prompt text and version history

**Step 4.2 — Check Quality Score**

```
API: GET http://localhost:8000/quality
```

- [ ] Returns at least 1 QualityScore with 5 dimension scores:
  - **specificity** — Are recommendations specific to your company?
  - **evidence_depth** — Are claims backed by signal evidence?
  - **causal_clarity** — Is the causal chain logical?
  - **actionability** — Can a human act on this brief immediately?
  - **completeness** — Are all risk categories addressed?
- [ ] `overall` is a weighted average (weights: 0.25, 0.20, 0.20, 0.25, 0.10)
- [ ] `weak_agents` lists which agents contributed to low scores

**Step 4.3 — Trigger PromptOptimiser (if not already triggered)**

If `overall` quality score was below 0.70 (the threshold), the PromptOptimiser should have already fired automatically. To manually trigger:

```
API: POST http://localhost:8000/quality/optimise
```

- [ ] Response shows `"message": "Optimisation triggered"` with the weak agents list
- [ ] Wait 30-60 seconds for the background task to complete
- [ ] Check: `GET /prompts/BriefWriter` → version should increment (e.g., from 1 to 2)
- [ ] Check: `GET /prompts/BriefWriter/history` → shows both version 1 and version 2

> **Key insight for demo:** The system rewrote its own instructions to improve. No human edited any prompt. The next pipeline run will use the improved prompt.

**Step 4.4 — Rollback a Prompt (Optional Demo)**

```
API: POST http://localhost:8000/prompts/BriefWriter/rollback?target_version=1
```

- [ ] BriefWriter reverts to version 1
- [ ] This is a safety mechanism: if an optimised prompt performs worse, you can instantly revert

---

### LEVEL 5 — Human Feedback Loop

**What this level proves:** Humans can rate the system's output. Those ratings automatically adjust future confidence scoring.

**Step 5.1 — Submit Feedback on an Alert**

First, get a signal ID from any alert:
```
API: GET http://localhost:8000/alerts
```
Copy any `signal_id` from the response.

Then submit feedback by visiting this URL in your browser:
```
http://localhost:8000/feedback/{signal_id}/acted_on
```

- [ ] A thank-you HTML page is displayed
- [ ] The feedback entry is recorded in the system

You can also try:
- `http://localhost:8000/feedback/{signal_id}/false_positive` — marks the signal as a false alarm
- `http://localhost:8000/feedback/{signal_id}/escalate` — says the signal is more serious than rated
- `http://localhost:8000/feedback/{signal_id}/dismiss` — ignores the signal

**Step 5.2 — View Feedback**

```
UI:  http://localhost:3000/feedback
API: GET http://localhost:8000/feedback
```

- [ ] Shows all submitted feedback entries with timestamps and action types
- [ ] Summary cards show: Acted On rate, False Positive rate, Escalations, Dismissals

**Step 5.3 — View Feedback Statistics**

```
API: GET http://localhost:8000/feedback/stats
```

- [ ] Shows `acted_on_rate`, `false_positive_rate` per signal category
- [ ] These rates drive the confidence weight adjustments

**Step 5.4 — Process Feedback (Trigger Weight Adjustment)**

```
API: POST http://localhost:8000/feedback/process
```

- [ ] FeedbackAgent runs and computes new confidence weights
- [ ] If a category has 30%+ false positive rate → confidence multiplier is reduced
- [ ] If a source has 20%+ escalation rate → priority weight is increased
- [ ] Weights are clipped to [0.5, 1.5] range for safety
- [ ] Next pipeline run automatically uses the adjusted weights

**Step 5.5 — Feedback Buttons in UI**

- [ ] Open `/alerts` in the UI
- [ ] Each alert card has 4 feedback buttons: Acted On, False Positive, Escalate, Dismiss
- [ ] Clicking a button records feedback and replaces the buttons with a confirmation badge

---

### LEVEL 6 — Multi-Tenant Federation

**What this level proves:** Multiple companies can use the same SENTINEL instance. Their data is completely isolated, but threat intelligence is shared anonymously.

**Step 6.1 — View Tenants**

```
UI:  http://localhost:3000/tenants
API: GET http://localhost:8000/tenants
```

- [ ] At least 5 tenants listed: default, techcorp, retailco, financeinc, healthco
- [ ] Each tenant card shows the company name, industry, and signal count

**Step 6.2 — Run Pipeline for Different Tenants**

```
API: POST http://localhost:8000/ingest?tenant_id=techcorp
     (wait for completion)
API: POST http://localhost:8000/ingest?tenant_id=retailco
     (wait for completion)
```

- [ ] Each tenant gets different sample signals tailored to their industry
- [ ] TechCorp gets cyber-heavy signals (AWS, Kubernetes-related)
- [ ] RetailCo gets supply chain and PCI-DSS-related signals

**Step 6.3 — Verify Data Isolation**

```
API: GET http://localhost:8000/alerts?tenant_id=techcorp
API: GET http://localhost:8000/alerts?tenant_id=retailco
```

- [ ] TechCorp alerts are completely different from RetailCo alerts
- [ ] No cross-contamination — TechCorp's data never appears in RetailCo's responses

**Step 6.4 — Switch Tenants in the UI**

- [ ] Use the tenant switcher dropdown in the top navigation bar
- [ ] Switch to "techcorp" → all pages reload with TechCorp's data
- [ ] Switch to "retailco" → all pages reload with RetailCo's data
- [ ] The alerts, briefs, memory, and actions all change per tenant

**Step 6.5 — Check Shared Intelligence**

```
UI:  http://localhost:3000/shared
API: GET http://localhost:8000/shared/patterns
```

- [ ] Shared patterns exist with occurrence counts across tenants
- [ ] **No company names or tenant IDs appear** in shared data (anonymisation working)
- [ ] The headline stat shows "Protecting N companies — M shared patterns"
- [ ] The CausalChainBuilder uses these patterns in its reasoning (check the brief for cross-company references)

> **Key insight for demo:** "TechCorp experienced a ransomware attack. RetailCo now sees that pattern in their threat analysis — without knowing it was TechCorp. Privacy by design."

---

### LEVEL 7 — Predictive Risk Intelligence

**What this level proves:** SENTINEL predicts which low-priority signals will escalate, before they become critical.

**Step 7.1 — Check Active Forecasts**

```
UI:  http://localhost:3000/forecasts
API: GET http://localhost:8000/forecasts/active
```

- [ ] Pending forecasts exist for P2/P3 signals (P0/P1 are already critical, so they're not forecasted)
- [ ] Each forecast shows: probability (0.0–1.0), horizon (24h/48h/72h/7d), and reasoning

**Step 7.2 — Check Forecast Accuracy**

```
API: GET http://localhost:8000/forecasts/accuracy
```

- [ ] Shows accuracy metrics per category
- [ ] The ForecastAgent self-calibrates: if past accuracy < 0.5, it reduces confidence; if > 0.8, it increases

**Step 7.3 — Resolve Forecasts**

```
API: POST http://localhost:8000/forecasts/resolve
```

- [ ] The ForecastOutcomeTracker runs and evaluates past predictions:
  - **CORRECT**: A later signal matched the prediction
  - **EXPIRED**: Horizon passed, no match, probability was low → not necessarily wrong
  - **INCORRECT**: Horizon passed, no match, probability was high → forecast was wrong

**Step 7.4 — Forecast Badges in Alerts**

- [ ] Open `/alerts` in the UI
- [ ] P2/P3 alert cards show orange forecast badges like "Forecast: P0 in 72h"
- [ ] This tells the user: "This looks low-priority now, but our model predicts it will escalate"

**Step 7.5 — Predicted Threats in Briefs**

- [ ] Open `/briefs` → the latest brief includes a "Predicted Threats" section
- [ ] Shows forecasted escalations with probability bars

> **Key insight for demo:** "This P2 signal about a supply chain disruption? SENTINEL predicts it will escalate to P0 within 72 hours based on 120 historical data points."

---

### LEVEL 8 — Autonomous Actions

**What this level proves:** SENTINEL doesn't just report risks — it takes action. A confidence-gated system ensures the right level of automation vs. human oversight.

**Step 8.1 — Check Actions**

```
UI:  http://localhost:3000/actions
API: GET http://localhost:8000/actions
```

- [ ] Actions exist from the pipeline run
- [ ] Each action shows: type (JIRA_TICKET, PAGERDUTY_ALERT, EMAIL_DRAFT, WEBHOOK, SLACK_MESSAGE), status, and confidence

**Step 8.2 — Understand the Three Confidence Gates**

| Confidence | Status | What Happens |
|-----------|--------|--------------|
| **≥ 0.85** (HIGH) | AUTO_EXECUTED | Action is taken immediately without human approval |
| **0.60–0.84** (MODERATE) | PENDING_APPROVAL | Action waits for a human to approve or reject |
| **< 0.60** (LOW) | REPORT_ONLY | Action is logged as a recommendation only |

Special rules:
- P0 PagerDuty alerts are ALWAYS auto-executed (regardless of confidence)
- Email drafts ALWAYS require approval (never auto-sent)

**Step 8.3 — Approve or Reject a Pending Action**

```
UI:  Click "Approve" or "Reject" on any pending action card
API: POST http://localhost:8000/actions/{action_id}/approve
     POST http://localhost:8000/actions/{action_id}/reject
```

- [ ] Approved action → status changes to APPROVED and the action is executed (logged in demo mode)
- [ ] Rejected action → status changes to REJECTED, no execution

**Step 8.4 — Check Action Audit Log**

```
API: GET http://localhost:8000/actions/audit
```

- [ ] Full audit trail of every action: who triggered it, when, what happened
- [ ] This is the accountability layer — every autonomous decision is traceable

**Step 8.5 — View and Modify Action Registry**

```
UI:  Actions page → "Registry" tab
API: GET http://localhost:8000/actions/registry
```

- [ ] Shows toggleable switches for each action type (Jira, PagerDuty, Email, Webhook, Slack)
- [ ] Disabling an action type means the ActionPlanner will never plan that type

**Step 8.6 — Actions in the Brief**

- [ ] Open `/briefs` → the brief includes:
  - "Actions Taken" section (AUTO_EXECUTED actions)
  - "Pending Approval" section (actions waiting for human review)
  - "Recommendations" section (REPORT_ONLY actions)

---

### LEVEL 9 — Negotiation Pipeline

**What this level proves:** When a supplier risk is detected, SENTINEL autonomously searches for alternative suppliers, drafts professional outreach emails, monitors for replies, and recommends the best replacement.

**Step 9.1 — Run a Demo Negotiation**

```
API: GET http://localhost:8000/negotiations/demo
```

**Wait approximately 10-30 seconds.** The system runs a complete 6-step negotiation pipeline:

1. **SEARCHING** — Finds 3-5 alternative suppliers (from demo database)
2. **DRAFTING** — Writes professional outreach emails to each alternative
3. **SENDING** — Marks emails as sent (logged in demo mode)
4. **AWAITING_REPLY** — Waits for replies (uses mock replies in demo mode)
5. **SUMMARISING** — Analyses replies and compares alternatives
6. **COMPLETE** — Recommends the best supplier with reasoning

- [ ] Response shows `"status": "COMPLETE"`
- [ ] Response includes `alternatives_found`, `outreach_emails`, and `recommendation`

**Step 9.2 — Verify Session Storage**

```
API: GET http://localhost:8000/negotiations
```

- [ ] At least 1 negotiation session stored
- [ ] Session shows the full status progression

**Step 9.3 — View in the UI**

```
UI: http://localhost:3000/negotiations
```

- [ ] Status timeline visible: SEARCHING → DRAFTING → AWAITING REPLY → COMPLETE
- [ ] Alternative supplier cards show name, website, and relevance score
- [ ] Outreach email cards show subject, body, sent/reply status
- [ ] Recommendation section shows the recommended supplier with detailed reasoning

**Step 9.4 — Manual Trigger**

```
API: POST http://localhost:8000/negotiations/trigger?supplier_name=CloudVendor&risk_reason=Bankruptcy%20risk
```

- [ ] Creates a new negotiation session for the specified supplier
- [ ] Runs the full pipeline in the background

---

### LEVEL 10 — Meta-Governance

**What this level proves:** The system monitors itself — tracking agent health, debate fairness, action effectiveness — and maintains an immutable audit trail of every autonomous decision.

**Step 10.1 — Run Meta-Analysis**

```
UI:  http://localhost:3000/governance → Click "Run Analysis"
API: POST http://localhost:8000/meta/run
```

- [ ] MetaAgent analyses all agent performance data and produces a MetaReport
- [ ] Wait 30-60 seconds for the analysis to complete

**Step 10.2 — View System Health**

```
API: GET http://localhost:8000/meta/reports/latest
```

- [ ] MetaReport contains:
  - **overall_health**: A composite score from 0.0 to 1.0 (displayed as 0–100 in UI)
  - **agent_health**: Per-agent quality scores, error rates, and latency
  - **debate_balance**: Red Team vs Blue Team win rates (should be BALANCED)
  - **action_effectiveness**: Total actions, acted-on rate, auto-execute rate, rejection rate
  - **critical_issues**: LLM-generated list of issues and recommendations

**Step 10.3 — Governance Dashboard in UI**

```
UI: http://localhost:3000/governance
```

- [ ] Health gauge (SVG circular gauge, colour-coded: green = healthy, yellow = warning, red = critical)
- [ ] Agent Health Table: sortable, with expandable issues per agent
- [ ] Debate Balance: Red/Blue bars with BALANCED or DOMINANT badge
- [ ] Action Effectiveness: Total, acted-on rate, auto-exec rate
- [ ] A/B Tests: Active tests with progress bars

**Step 10.4 — Check Governance Log**

```
API: GET http://localhost:8000/governance/log
```

- [ ] Returns an immutable log of every autonomous decision:
  - ACTION_EXECUTED, PROMPT_CHANGED, WEIGHT_ADJUSTED, etc.
- [ ] Each entry records: agent_name, event_type, reasoning, confidence, and whether a human was involved
- [ ] Entries are **write-once** — they cannot be edited or deleted (audit trail integrity)

**Step 10.5 — Filter Governance Log**

```
API: GET http://localhost:8000/governance/log?event_type=ACTION_EXECUTED
```

- [ ] Only shows events of that specific type

**Step 10.6 — Human Override System**

```
API: POST http://localhost:8000/governance/overrides
     Body: {"scope": "GLOBAL", "reason": "Emergency pause"}
```

- [ ] Creates an override rule that blocks ALL autonomous actions system-wide
- [ ] While active, no actions are auto-executed — everything goes to PENDING_APPROVAL
- [ ] Overrides can target: a specific AGENT, ACTION_TYPE, TENANT, or GLOBAL

```
API: GET http://localhost:8000/governance/overrides
```

- [ ] Shows all active override rules

```
API: DELETE http://localhost:8000/governance/overrides/{override_id}
```

- [ ] Deactivates the override → autonomous actions resume

> **Key insight for demo:** "At any moment, a CISO can flip one switch and pause all autonomous actions globally. Full control, full accountability."

**Step 10.7 — A/B Testing (Advanced)**

When the PromptOptimiser creates a new prompt version, an A/B test automatically starts:
- Odd pipeline runs use variant A (the current prompt)
- Even pipeline runs use variant B (the challenger prompt)
- After a minimum number of runs, the winner is automatically selected and activated

```
API: GET http://localhost:8000/ab-tests
API: GET http://localhost:8000/ab-tests/active
```

- [ ] Shows A/B tests with quality metrics for each variant

---

## PART 4 — LIVE DEMO SCRIPT

> **Use this script when presenting SENTINEL to an audience.** Each step includes what to show and what to say. The demo takes approximately 10–15 minutes.

### Opening (30 seconds)

> "SENTINEL is an autonomous multi-agent risk intelligence system. It's not a chatbot — nobody asks it questions. It runs continuously, monitoring the threat landscape, personalising risk to your specific company, and taking action when confidence is high enough. I'll run the full pipeline live right now."

### Step 1 — Run the Pipeline (2 minutes)

**Show:** Pipeline page (http://localhost:3000) → Click "Run Pipeline"

**Show:** Terminal 2 — agents logging in real-time

> "Eleven AI agents are running right now. The first three are sensors — they scan external sources for news, cybersecurity advisories, and financial filings. Then classifiers assign priority. Then reasoning and a full adversarial debate. RedTeam challenges the assessment. BlueTeam defends it. An Arbiter decides. Finally, a brief is generated, scored for quality, and committed to memory."

Wait for pipeline to complete (or use a pre-run pipeline).

### Step 2 — Show the Brief (2 minutes)

**Show:** Briefs page (http://localhost:3000/briefs) → Click the latest brief

> "This is the output — an executive intelligence brief. Notice the recommendations are specific to our tech stack. It says 'update Apache to version X' — not generic 'patch your systems'. That's because SENTINEL knows our company profile."

**Point to:** Confidence gauge → "84% confidence after adversarial debate"

**Point to:** Causal chain DAG → "This is the cause-and-effect chain the system built"

**Point to:** Red vs Blue panels → "RedTeam said we're underestimating this risk. BlueTeam argued our existing controls mitigate it. The Arbiter sided with Blue."

### Step 3 — Show Alerts (1 minute)

**Show:** Alerts page (http://localhost:3000/alerts)

> "Every signal is classified P0 through P3. These orange forecast badges are predictions — SENTINEL says this P2 signal will escalate to P0 within 72 hours based on historical patterns. That's Level 7, predictive intelligence."

**Point to:** The feedback buttons → "Users can rate these: Acted On, False Positive, Escalate, Dismiss. Those ratings automatically adjust future confidence scoring."

### Step 4 — Show Company Profile (30 seconds)

**Show:** Company page (http://localhost:3000/company)

> "SENTINEL knows who we are. Our cloud stack, our suppliers, our regulatory scope. Signals that match this profile score higher. A critical Apache vulnerability matters a lot more to a company that actually uses Apache."

### Step 5 — Show Memory (1 minute)

**Show:** Memory page (http://localhost:3000/memory)

> "After every run, SENTINEL remembers. On the second run, agents reference patterns from the first: 'we've seen similar Apache vulnerabilities twice in the past 90 days — this is a recurring pattern.' The system gets smarter without retraining."

### Step 6 — Show Autonomous Actions (1 minute)

**Show:** Actions page (http://localhost:3000/actions)

> "Level 8 — SENTINEL doesn't just report, it acts. High-confidence P0 signals automatically page on-call engineers via PagerDuty. Medium-confidence signals wait here for your approval — one click to approve, one click to reject. Low-confidence signals are logged as recommendations only. This is confidence-gated autonomy."

**Demo:** Click Approve on a pending action.

### Step 7 — Show Multi-Tenant (1 minute)

**Show:** Tenant switcher dropdown → Switch to "techcorp"

> "Same system, different company. TechCorp's alerts, their profile, their brief. The data never crosses. Complete isolation."

**Show:** Shared Intelligence page (http://localhost:3000/shared)

> "But threat patterns pool anonymously. TechCorp experienced a ransomware attack. RetailCo now sees that pattern in their threat analysis — without knowing it was TechCorp. Privacy by design."

### Step 8 — Show Negotiation (1 minute)

**Show:** Negotiations page (http://localhost:3000/negotiations)

> "Level 9. A supplier was flagged as a bankruptcy risk. SENTINEL didn't just report it — it searched for alternative suppliers, drafted professional outreach emails, waited for replies, and recommended the best replacement. All autonomously."

**Point to:** The status timeline, email drafts, and recommendation.

### Step 9 — Show Self-Improvement (1 minute)

**Show:** Prompts page (http://localhost:3000/prompts)

> "The system improves its own instructions. After the last run, BriefWriter scored 61% quality. SENTINEL automatically rewrote its prompt to address the weaknesses. Now it's on version 2. No human changed anything."

### Step 10 — Show Governance (1 minute)

**Show:** Governance page (http://localhost:3000/governance)

> "Level 10 — meta-governance. The system monitors itself. You can see agent health, Red/Blue debate balance, action effectiveness, and a complete immutable audit log of every autonomous decision. If anything goes wrong, a CISO can hit one override switch and pause all autonomy globally."

### Closing (30 seconds)

> "What you've seen is a system that monitors external threats, personalises risk to your specific company, debates its own conclusions through adversarial AI, takes autonomous action where appropriate, learns from human feedback, improves its own prompts, predicts future escalations, negotiates supplier replacements, and governs itself — all from a single pipeline run. 22 agents, 10 architecture levels, fully automated, running on open-source infrastructure."

---

## PART 5 — COMMON QUESTIONS & ANSWERS

**Q: "How is this different from a RAG chatbot?"**
> A: "A chatbot responds to questions. SENTINEL runs continuously without being asked. It monitors, classifies, debates, and acts. No human prompts it — it prompts itself. It's an autonomous intelligence system, not a question-answering tool."

**Q: "What happens if an LLM call fails?"**
> A: "Every LLM call uses Tenacity retry with 3 attempts and exponential backoff. If all retries fail, the agent logs the error and returns safe defaults. Sensor agents fall back to demo data. The pipeline never crashes silently."

**Q: "How do you handle AI safety with autonomous actions?"**
> A: "Three mechanisms. First, a confidence gate: high confidence auto-executes, medium waits for approval, low reports only. Second, a global override switch that can pause all autonomy instantly. Third, an immutable governance log that records every autonomous decision with full reasoning — complete accountability."

**Q: "What does this cost to run?"**
> A: "Each full pipeline run costs approximately $0.017 in LLM calls via OpenRouter. All infrastructure — Qdrant, FastAPI, Next.js — is free and open source. The only recurring cost is the LLM API. You can switch to Groq for free-tier access."

**Q: "Is this production-ready?"**
> A: "The architecture is production-grade — fully async, type-safe (Pydantic throughout), containerised with Docker, and tested with 369 test cases. For actual production, you'd add API authentication, deploy Qdrant to a cloud instance, and replace demo data with live API keys (NewsAPI, NVD, SerpAPI)."

**Q: "How does the adversarial debate work?"**
> A: "Three agents. RedTeam tries to find blind spots and argues why the threat is worse than assessed. BlueTeam provides mitigating factors and existing defences. The Arbiter weighs both arguments and sets a final confidence score. If RedTeam wins, the signal's priority is escalated and re-assessed from scratch."

**Q: "Can it work with different LLM providers?"**
> A: "Yes. Set `LLM_PROVIDER=groq` in .env for Groq, or `LLM_PROVIDER=openrouter` for OpenRouter. Embeddings always use OpenRouter's Gemini embedding model regardless of which provider is selected for reasoning."

**Q: "What if a company doesn't want autonomy?"**
> A: "Set a GLOBAL override — all actions become PENDING_APPROVAL. Or disable specific action types in the Action Registry. Or set `ACTION_AUTO_THRESHOLD=1.0` so nothing ever auto-executes. Full control."

---

## PART 6 — TROUBLESHOOTING GUIDE

### Problem: Pipeline hangs or takes too long

**Diagnose:**
1. Check Qdrant is running: `Invoke-RestMethod http://localhost:6333/collections`
2. Check the LLM provider is responding: Look at Terminal 2 for `llm.complete` log entries
3. Check your API key is valid: OpenRouter dashboard or Groq console

**Fix:**
- Restart the backend: Press `Ctrl+C` in Terminal 2, then run `uvicorn sentinel.main:app --reload --port 8000` again
- If Qdrant is down: `docker-compose up -d`
- If the LLM key is expired: Update `.env` with a new key and restart the backend

### Problem: UI not loading or blank page

**Diagnose:**
1. Check the frontend is running: Look at Terminal 3 for Next.js output
2. Check CORS: Backend must be on port 8000, frontend on port 3000

**Fix:**
- Restart frontend: `cd sentinel-ui && npm run dev`
- Clear browser cache: `Ctrl+Shift+Delete` → clear cached files → reload

### Problem: No alerts showing after pipeline run

**Diagnose:**
1. Check pipeline completed: `GET http://localhost:8000/pipeline/status` → should show `"completed"`
2. Check the correct tenant: `GET http://localhost:8000/tenants` → verify active tenant matches UI

**Fix:**
- Run the pipeline again: `POST http://localhost:8000/ingest`
- Switch to the correct tenant using the dropdown in the UI

### Problem: Memory entries missing

**Diagnose:**
1. This is normal after the **first** run — memory entries are created but not yet used
2. Memory entries should appear after `POST /ingest` completes

**Fix:**
- Run the pipeline at least once: `POST http://localhost:8000/ingest`
- Check: `GET http://localhost:8000/memory/search?q=risk` → should return entries

### Problem: Actions showing 0

**Diagnose:**
1. Actions are only created for FULL path signals (P0/P1)
2. Check `data/tenants/default/action_registry.json` exists

**Fix:**
- Run the pipeline: `POST http://localhost:8000/ingest`
- Check: `GET http://localhost:8000/actions` → should show actions after the run

### Problem: Negotiations showing 0 sessions

**Diagnose:**
1. Negotiations are only created when you explicitly trigger one

**Fix:**
- Run demo negotiation: `GET http://localhost:8000/negotiations/demo`
- Or manually trigger: `POST http://localhost:8000/negotiations/trigger?supplier_name=TestSupplier&risk_reason=testing`

### Problem: PromptOptimiser not firing

**Diagnose:**
1. Check quality score is below threshold (0.70): `GET http://localhost:8000/quality`
2. Check `OPTIMISER_ENABLED=true` in `.env`

**Fix:**
- Manually trigger: `POST http://localhost:8000/quality/optimise`
- Wait 30-60 seconds, then check: `GET /prompts/BriefWriter` → version should increment

### Problem: Port already in use

**Fix:**
```powershell
# Kill process on port 8000
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# Kill process on port 3000
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## PART 7 — QUICK REFERENCE CARD

### URLs

| Service | URL |
|---------|-----|
| Frontend (UI) | http://localhost:3000 |
| Backend API docs | http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |

### Key API Endpoints

| Endpoint | Method | What It Does |
|----------|--------|-------------|
| `/ingest` | POST | Triggers full pipeline run |
| `/pipeline/status` | GET | Current pipeline status |
| `/alerts` | GET | All alerts by priority |
| `/briefs/latest` | GET | Most recent intelligence brief |
| `/company/profile` | GET | Current company profile |
| `/memory/search?q=term` | GET | Semantic memory search |
| `/quality` | GET | Quality scores |
| `/quality/optimise` | POST | Manually trigger prompt optimisation |
| `/prompts/{agent}` | GET | Agent prompt and version |
| `/feedback` | GET | All feedback entries |
| `/feedback/process` | POST | Trigger weight adjustment |
| `/forecasts/active` | GET | Pending predictions |
| `/forecasts/resolve` | POST | Resolve pending forecasts |
| `/actions` | GET | All autonomous actions |
| `/actions/pending` | GET | Actions awaiting approval |
| `/actions/{id}/approve` | POST | Approve an action |
| `/actions/{id}/reject` | POST | Reject an action |
| `/negotiations/demo` | GET | Run demo negotiation |
| `/negotiations` | GET | All negotiation sessions |
| `/tenants` | GET | All tenants |
| `/shared/patterns` | GET | Shared intelligence patterns |
| `/meta/run` | POST | Trigger meta-analysis |
| `/governance/log` | GET | Immutable governance log |
| `/governance/overrides` | GET/POST | Override rules |
| `/ab-tests` | GET | A/B test status |
| `/health` | GET | System health check |

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_MODE` | `true` | Use demo data instead of live APIs |
| `LLM_PROVIDER` | `openrouter` | LLM provider: `openrouter` or `groq` |
| `OPENROUTER_API_KEY` | — | Your OpenRouter API key |
| `GROQ_API_KEY` | — | Your Groq API key (if using Groq) |
| `QUALITY_THRESHOLD` | `0.70` | Below this, PromptOptimiser fires |
| `OPTIMISER_ENABLED` | `true` | Enable/disable prompt self-improvement |
| `META_ENABLED` | `true` | Enable/disable MetaAgent |
| `GOVERNANCE_ENABLED` | `true` | Enable/disable governance logging |
| `AB_TEST_ENABLED` | `true` | Enable/disable A/B testing |
| `FORECAST_MIN_PROBABILITY` | `0.40` | Minimum probability to store a forecast |
| `FORECAST_ALERT_THRESHOLD` | `0.80` | Probability threshold for predictive alerts |

### Quick Commands

```powershell
# Start everything
docker-compose up -d
uvicorn sentinel.main:app --reload --port 8000
cd sentinel-ui && npm run dev

# Run pipeline
Invoke-RestMethod -Uri http://localhost:8000/ingest -Method Post

# Check status
Invoke-RestMethod -Uri http://localhost:8000/pipeline/status

# Switch LLM provider to Groq (free)
# Edit .env: LLM_PROVIDER=groq
# Add GROQ_API_KEY=gsk_...
# Restart backend
```
