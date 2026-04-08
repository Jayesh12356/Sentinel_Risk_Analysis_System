# SENTINEL — Project Manual

**Autonomous Multi-Agent Enterprise Risk Intelligence System**
Masters Final Project — Solo Build

> 11 agents · 1 orchestration framework · 3 data sources · 100% demo-safe

---

## 1. Project Overview

SENTINEL is an autonomous multi-agent AI pipeline that monitors
external business signals, analyses them through a chain of
specialised agents, debates their significance using adversarial
reasoning, and produces actionable intelligence briefs for
enterprise decision-makers.

The system is not a chatbot. It is a fully automated pipeline
where data enters at one end and a structured intelligence report
exits at the other — with no human intervention required.

---

## 2. Problem Being Solved

Enterprise risk teams face four unsolved problems:

  Information overload
    Hundreds of news articles, CVEs, and filings arrive daily.
    Analysts cannot read everything.

  Slow response
    Human correlation of signals takes hours to days.
    Risks are discovered after impact, not before.

  Siloed monitoring
    A supplier bankruptcy and a port congestion alert arrive
    on different desks. No one connects them.

  No institutional memory
    Past incidents do not improve future analysis.

SENTINEL solves all four with an automated agent pipeline.

---

## 3. System Architecture

### Pipeline Flow (Single LangGraph StateGraph)

  External Sources
      ↓
  [Layer 0] Sensor Agents (3)
      NewsScanner → CyberThreatAgent → FinancialSignalAgent
      ↓
  [Layer 1] Processing Agents (2)
      EntityExtractor → SignalClassifier
      ↓ (Loop 1 if confidence < 0.5)
  [Layer 2] Reasoning Agents (2)
      RiskAssessor → CausalChainBuilder
      ↓
  [Layer 3] Deliberation Agents (3)
      RedTeamAgent → BlueTeamAgent → ArbiterAgent
      ↓ (Loop 2 if Red Team wins)
  [Layer 4] Output Agent (1)
      BriefWriter
      ↓
  Intelligence Brief → FastAPI → User

### Demo Mode

  All sensor agents have two operating modes:

  Live mode:  polls real external APIs
  Demo mode:  loads from data/sample_signals/

  Run with: python -m sentinel.main --demo-mode

  Demo mode guarantees the pipeline runs successfully
  regardless of external API availability. Gemini
  reasoning runs normally in both modes.

---

## 4. The 11 Agents

### Layer 0 — Sensor Agents

  NewsScanner
    Purpose:  Polls RSS feeds and NewsAPI for business events
    Sources:  RSS (feedparser), NewsAPI free tier
    Output:   List[Signal] with source=NEWS
    Demo:     Loads data/sample_signals/news_samples.json

  CyberThreatAgent
    Purpose:  Monitors CVE/NVD for critical vulnerabilities
    Sources:  NVD API (free, no key required)
    Output:   List[Signal] with source=CYBER
    Demo:     Loads data/sample_signals/cyber_samples.json

  FinancialSignalAgent
    Purpose:  Extracts risk signals from SEC filings
    Sources:  SEC EDGAR full-text search API (free)
    Output:   List[Signal] with source=FINANCIAL
    Demo:     Loads data/sample_signals/financial_samples.json

### Layer 1 — Processing Agents

  EntityExtractor
    Purpose:  Extracts companies, people, locations, products
              from signal text using Gemini NER
    Input:    List[Signal]
    Output:   List[Signal] with entities field populated

  SignalClassifier
    Purpose:  Assigns priority P0/P1/P2/P3 and confidence score
              Triggers Loop 1 if confidence < 0.5
    Input:    List[Signal] with entities
    Output:   List[Signal] with priority and confidence

### Layer 2 — Reasoning Agents

  RiskAssessor
    Purpose:  Scores risk using Impact × Probability × Exposure
              Produces evidence chain
    Input:    List[Signal] classified
    Output:   RiskReport with score, classification, evidence

  CausalChainBuilder
    Purpose:  Traces root cause and 2nd/3rd order effects
    Input:    RiskReport
    Output:   RiskReport with causal_chain populated

### Layer 3 — Deliberation Agents

  RedTeamAgent
    Purpose:  Challenges the risk assessment adversarially
              Finds contradictory evidence, worst-case scenarios
    Input:    RiskReport with causal chain
    Output:   DebatePosition with arguments and evidence

  BlueTeamAgent
    Purpose:  Defends optimistic interpretation
              Finds mitigating factors and precedents
    Input:    RiskReport + RedTeam position
    Output:   DebatePosition with counter-arguments

  ArbiterAgent
    Purpose:  Reads full debate, computes final confidence score
              Triggers Loop 2 if Red Team wins decisively
              Escalates to human if confidence < 0.40
    Input:    Both debate positions
    Output:   RiskReport with final_confidence and verdict

### Layer 4 — Output Agent

  BriefWriter
    Purpose:  Produces full executive intelligence brief
              Includes all evidence, citations, debate summary,
              causal chain, confidence score, recommended actions
    Input:    Final RiskReport
    Output:   Brief (structured Pydantic model + formatted text)

---

## 5. Data Schemas

### Signal
  id:            UUID
  source:        Enum(NEWS, CYBER, FINANCIAL)
  title:         str
  body:          str
  url:           str
  published_at:  datetime
  entities:      List[str]
  priority:      Enum(P0, P1, P2, P3) | None
  confidence:    float | None
  embedding:     List[float] | None
  created_at:    datetime

### RiskReport
  id:              UUID
  signal_ids:      List[UUID]
  risk_score:      float  (0.0–10.0)
  impact:          float  (0.0–1.0)
  probability:     float  (0.0–1.0)
  exposure:        float  (0.0–1.0)
  classification:  Enum(LOW, MEDIUM, HIGH, CRITICAL)
  evidence_chain:  List[str]
  causal_chain:    List[str]
  red_team_args:   List[str]
  blue_team_args:  List[str]
  final_confidence: float
  verdict:         str
  created_at:      datetime

### Brief
  id:              UUID
  report_id:       UUID
  title:           str
  affected_entity: str
  severity:        Enum(P0, P1, P2, P3)
  confidence:      float
  root_cause:      str
  causal_chain:    List[str]
  evidence:        List[str]
  debate_summary:  str
  recommendations: List[str]
  full_text:       str
  created_at:      datetime

---

## 6. Feedback Loops

### Loop 1 — Low Confidence Reprocessing
  Trigger:   SignalClassifier confidence < 0.5
  Action:    Query Qdrant for similar historical signals
             Append context to signal body
             Re-run EntityExtractor + SignalClassifier
  Max runs:  2 (prevents infinite loop)

### Loop 2 — Red Team Escalation
  Trigger:   ArbiterAgent determines Red Team wins decisively
             (red_team_score > blue_team_score by > 0.3)
  Action:    Escalate signal priority by one level
             Re-run RiskAssessor with Red Team arguments
             as additional context
  Max runs:  1

---

## 7. FastAPI Endpoints

  GET  /health
    Returns system status and pipeline state

  POST /ingest
    Body: { "demo_mode": bool, "query": str (optional) }
    Triggers full pipeline run
    Returns: { "run_id": UUID, "status": "started" }

  GET  /alerts
    Query params: priority (P0/P1/P2/P3), limit, offset
    Returns list of signals by priority

  GET  /alerts/{signal_id}
    Returns single signal with full detail

  GET  /briefs
    Query params: limit, offset
    Returns list of brief summaries

  GET  /briefs/latest
    Returns most recently generated brief

  GET  /briefs/{brief_id}
    Returns full brief with all fields

  GET  /pipeline/status
    Returns current pipeline run state and last run time

---

## 8. Project Folder Structure

  sentinel/
  ├── docker-compose.yml
  ├── Dockerfile
  ├── pyproject.toml
  ├── .env.example
  ├── CONTEXT.md
  ├── SENTINEL_PROJECT_MANUAL.md
  │
  ├── sentinel/
  │   ├── __init__.py
  │   ├── main.py
  │   ├── config.py
  │   │
  │   ├── llm/
  │   │   ├── __init__.py
  │   │   └── client.py
  │   │
  │   ├── agents/
  │   │   ├── __init__.py
  │   │   ├── base.py
  │   │   ├── layer0_sensors/
  │   │   │   ├── __init__.py
  │   │   │   ├── news_scanner.py
  │   │   │   ├── cyber_threat.py
  │   │   │   └── financial_signal.py
  │   │   ├── layer1_processing/
  │   │   │   ├── __init__.py
  │   │   │   ├── entity_extractor.py
  │   │   │   └── signal_classifier.py
  │   │   ├── layer2_reasoning/
  │   │   │   ├── __init__.py
  │   │   │   ├── risk_assessor.py
  │   │   │   └── causal_chain.py
  │   │   ├── layer3_deliberation/
  │   │   │   ├── __init__.py
  │   │   │   ├── red_team.py
  │   │   │   ├── blue_team.py
  │   │   │   └── arbiter.py
  │   │   └── layer4_output/
  │   │       ├── __init__.py
  │   │       └── brief_writer.py
  │   │
  │   ├── orchestration/
  │   │   ├── __init__.py
  │   │   ├── pipeline.py
  │   │   └── feedback_loops.py
  │   │
  │   ├── retrieval/
  │   │   ├── __init__.py
  │   │   ├── qdrant_client.py
  │   │   └── embeddings.py
  │   │
  │   ├── models/
  │   │   ├── __init__.py
  │   │   ├── signal.py
  │   │   ├── risk_report.py
  │   │   └── brief.py
  │   │
  │   ├── tools/
  │   │   ├── __init__.py
  │   │   ├── news_tools.py
  │   │   ├── cyber_tools.py
  │   │   └── financial_tools.py
  │   │
  │   └── api/
  │       ├── __init__.py
  │       ├── app.py
  │       └── routes/
  │           ├── __init__.py
  │           ├── alerts.py
  │           ├── briefs.py
  │           └── system.py
  │
  ├── scripts/
  │   ├── init_qdrant.py
  │   └── seed_data.py
  │
  ├── tests/
  │   ├── unit/
  │   ├── integration/
  │   └── e2e/
  │
  ├── prompts/
  │   ├── entity_extractor.txt
  │   ├── signal_classifier.txt
  │   ├── risk_assessor.txt
  │   ├── causal_chain.txt
  │   ├── red_team.txt
  │   ├── blue_team.txt
  │   ├── arbiter.txt
  │   └── brief_writer.txt
  │
  └── data/
      └── sample_signals/
          ├── news_samples.json
          ├── cyber_samples.json
          └── financial_samples.json

---

## 9. Technology Stack

  Component        Library              Version
  ─────────────────────────────────────────────
  Orchestration    langgraph            >=0.1.0
  LLM client       openai               >=1.30.0
  API              fastapi              >=0.110.0
  API server       uvicorn[standard]    >=0.29.0
  Vector DB        qdrant-client        >=1.9.0
  Config           pydantic-settings    >=2.0.0
  Validation       pydantic             >=2.6.0
  Logging          structlog            >=24.0.0
  HTTP client      httpx                >=0.27.0
  RSS parsing      feedparser           >=6.0.0
  Retry logic      tenacity             >=8.2.0
  Env loading      python-dotenv        >=1.0.0
  Testing          pytest               >=8.0.0
  Async testing    pytest-asyncio       >=0.23.0

  Deliberately excluded:
    dspy-ai     — unstable, not needed
    pyautogen   — replaced by LangGraph nodes
    crewai      — replaced by LangGraph nodes
    llama-index — replaced by direct Qdrant calls

---

## 10. Setup Instructions

  Step 1: Create .env from .env.example
    cp .env.example .env
    Add your OPENROUTER_API_KEY
    Add your NEWSAPI_KEY (free at newsapi.org)

  Step 2: Start Qdrant
    docker-compose up -d qdrant

  Step 3: Initialize Qdrant collections
    python scripts/init_qdrant.py

  Step 4: Seed sample data (for demo mode)
    python scripts/seed_data.py

  Step 5: Run in demo mode (guaranteed to work)
    python -m sentinel.main --demo-mode

  Step 6: Run with live APIs
    python -m sentinel.main

  Step 7: Access API docs
    http://localhost:8000/docs

---

## 11. Demo Script for Professor

  1. Show the architecture diagram (this document, section 3)

  2. Run: python -m sentinel.main --demo-mode
     Point out each agent logging as it runs

  3. Open: http://localhost:8000/docs
     Run GET /briefs/latest
     Show the full intelligence brief output

  4. Explain the two feedback loops using the logs

  5. Show GET /alerts?priority=P0 for critical signals

  Total demo time: 5–8 minutes
  Zero chance of failure — demo mode uses local data

---

## 12. Success Criteria

  Functional:
  ✓ 3 sensor agents ingest data (live or demo)
  ✓ Pipeline classifies signals P0–P3 automatically
  ✓ Risk score generated with evidence chain
  ✓ Red/Blue debate runs for every P0/P1 signal
  ✓ Arbiter produces confidence score 0.0–1.0
  ✓ Executive brief generated with all sections
  ✓ Both feedback loops trigger correctly
  ✓ FastAPI serves all endpoints < 500ms
  ✓ Demo mode runs with zero external dependencies

  Academic:
  ✓ Automated agentic pipeline (no human intervention)
  ✓ Multi-agent architecture with clear layer separation
  ✓ Adversarial reasoning (Red/Blue/Arbiter pattern)
  ✓ Retrieval-augmented generation (Qdrant)
  ✓ Feedback loops for self-correction
  ✓ Production-grade patterns (async, typed, tested)

---

*Version: 2.0 — Simplified for solo masters build*
*Certainty: 100% with demo mode enabled*