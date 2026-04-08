# SENTINEL - Autonomous Multi-Agent Risk Intelligence System

SENTINEL is an enterprise-grade, autonomous multi-agent platform for detecting, reasoning about, and responding to strategic risk signals across news, cyber, and financial domains.

It combines a layered AI architecture, memory-backed reasoning, tenant-aware context, autonomous action planning, negotiation workflows, and governance controls into one end-to-end decision intelligence system.

## Highlights

- 22 AI agents across 10 maturity levels and 7 processing layers
- Multi-signal ingestion: news, cyber threats, financial indicators
- Layered reasoning: extraction, classification, risk scoring, deliberation
- Autonomous actions and negotiation pipeline for downstream execution support
- Multi-tenant architecture with tenant-specific profiles and action registries
- Feedback and self-improvement loops for prompt and outcome quality
- Governance and observability with quality scoring and health/meta reporting

## System Architecture

SENTINEL runs as a unified pipeline (LangGraph `StateGraph`) with staged responsibilities:

- Layer 0: Sensor agents ingest raw signals
- Layer 1: Processing agents extract entities, classify, and route
- Layer 2: Reasoning agents build causal chains and assess risk
- Layer 3: Deliberation agents challenge and refine strategy (red/blue/arbiter)
- Layer 4: Output agents generate executive-ready briefs and quality checks
- Support layers: memory, forecasting, feedback, action execution, negotiation, governance

For full implementation detail, see:

- `SENTINEL_PROJECT_MANUAL.md`
- `SENTINEL_DEMO_MANUAL.md`

## Core Capabilities

- **Risk Pipeline**: Signal -> analysis -> brief generation
- **Dynamic Routing**: Company profile-driven routing and context adaptation
- **Memory & Alerts**: Historical retrieval plus alerting on critical conditions
- **Forecasting**: Weak-signal detection and outcome tracking
- **Autonomous Actions**: Action recommendations and tenant registry integration
- **Negotiation Intelligence**: Outreach drafting, reply monitoring, and summaries
- **Meta-Governance**: Quality checks, override controls, and system health events

## Tech Stack

- **Backend**: Python, FastAPI
- **Orchestration**: LangGraph / LangChain patterns
- **Vector Store**: Qdrant
- **Frontend**: React UI (`sentinel-ui`)
- **Data**: JSON-based tenant profiles, action registries, sample signal stores

## Repository Structure

```text
sentinel_risk_analysis_system/
|- sentinel/                 # Core backend modules, agents, pipeline, models
|- sentinel-ui/              # Frontend application (kept as separate nested repo)
|- data/                     # Tenant configs, registries, sample/demo data
|- scripts/                  # Bootstrap and seed scripts
|- tests/                    # Unit tests
|- roadmap/                  # Level-wise implementation context docs
|- SENTINEL_PROJECT_MANUAL.md
|- SENTINEL_DEMO_MANUAL.md
|- docker-compose.yml
|- pyproject.toml
```

## Quick Start

### 1) Start Qdrant

```bash
docker compose up -d
```

### 2) Initialize data stores (first run)

```bash
python scripts/init_qdrant.py
python scripts/init_tenants.py
python scripts/init_prompts.py
```

### 3) Run backend API

```bash
uvicorn sentinel.main:app --reload --port 8000
```

### 4) Run frontend UI

```bash
cd sentinel-ui
npm install
npm run dev
```

### 5) Verify

- Backend health: `http://127.0.0.1:8000/health`
- API docs: `http://127.0.0.1:8000/docs`
- UI: `http://127.0.0.1:3000`

## Demo Flow (Recommended)

1. Trigger pipeline for a demo tenant
2. Inspect generated brief and risk scores
3. Review alerts, memory entries, and routing rationale
4. Show autonomous action suggestions
5. Demonstrate negotiation workflow output
6. Present feedback/self-improvement and governance outputs

A complete rehearsal script and troubleshooting guide are available in `SENTINEL_DEMO_MANUAL.md`.

## Key API Endpoints

- `GET /health`
- `POST /run`
- `GET /brief/latest`
- `GET /alerts`
- `GET /memory`
- `GET /tenants`
- `POST /feedback`
- `GET /meta/health`

Use `http://127.0.0.1:8000/docs` for the full interactive OpenAPI specification.

## Configuration

Runtime settings are loaded from `.env`.

- Keep `.env` private and never commit secrets
- Use `.env.example` as the template for local setup
- Switch providers/keys via environment variables as documented in the demo manual

## Documentation

- `SENTINEL_PROJECT_MANUAL.md` - architecture, agents, schemas, endpoints, setup
- `SENTINEL_DEMO_MANUAL.md` - startup, walkthrough, live demo script, troubleshooting
- `CONTEXT.md` and `roadmap/` - level-wise build context and progression notes

## Status

This repository contains a full demo-capable implementation with production-style modularity, testing, and documentation designed for academic demo, experimentation, and extensible enterprise prototyping.
