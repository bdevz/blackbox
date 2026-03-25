# Blackbox

AI-powered RFP proposal generation platform for ConsultAdd Public Services. Ingests government RFPs, qualifies them, generates complete proposals using orchestrated AI agents, and exports production-ready documents.

## What It Does

```
HigherGov/Upload → Ingest → Qualify → [Solution || Compliance] → Cost → Review → Revise → Reconcile → Assemble → PDF/DOCX
```

1. **Ingests RFPs** from HigherGov API (automated daily) or manual upload (PDF/DOCX/TXT)
2. **Qualifies** each RFP against ConsultAdd's capabilities, certifications, and win history (50+ past wins)
3. **Generates** technical approach, compliance narrative, and cost proposal using 5 specialist AI agents
4. **Reviews** for contradictions, offshore contamination, and playbook violations
5. **Assembles** into a production-ready proposal document with cover letter, TOC, and appendices
6. **Exports** as PDF or DOCX

Built on a winning playbook reverse-engineered from 13 actual winning proposals.

## Architecture

```
Frontend (React + Vite)     →  Backend API (FastAPI)
                                    ↓
                            Celery Worker + Beat
                                    ↓
                            LangGraph Orchestrator
                              ↓     ↓     ↓
                          Qualify  Solution  Compliance
                                    ↓
                                  Cost
                                    ↓
                                 Review → Revision Loop → Reconcile
                                    ↓
                               Assembler → PDF/DOCX

PostgreSQL + pgvector  |  Redis  |  Anthropic API (Claude Opus 4.6)
```

| Component | Stack |
|-----------|-------|
| Backend | FastAPI + SQLAlchemy + Celery + Redis |
| Agents | LangGraph orchestrator + 7 specialist agents (qualify, solution, comply, cost, review, reconcile, ingest) |
| Database | PostgreSQL 16 + pgvector |
| Frontend | React 18 + Vite + Tailwind + Shadcn/ui |
| Export | WeasyPrint (PDF) + python-docx (DOCX) |
| Integrations | HigherGov API, HubSpot CRM, Slack, Coda |

## Quick Start

### Prerequisites

- Docker Desktop
- Node.js 18+ (for frontend dev)
- Python 3.12+ (for local backend dev)

### 1. Clone and configure

```bash
git clone https://github.com/bdevz/blackbox.git
cd blackbox
cp .env.example .env
```

Edit `.env` with your API keys:

```env
ANTHROPIC_API_KEY=sk-ant-...        # Required — powers all AI agents
HUBSPOT_API_KEY=pat-na2-...         # Optional — enables HubSpot deal sync
HIGHERGOV_API_KEY=...               # Optional — enables automated RFP ingestion
SLACK_BOT_TOKEN=xoxb-...            # Optional — enables Slack integration
VOYAGE_API_KEY=...                  # Optional — enables similar proposal search
```

### 2. Start the stack

```bash
docker compose up -d
```

This starts 5 services:

| Service | Port | Description |
|---------|------|-------------|
| `backend` | 8000 | FastAPI API server |
| `worker` | — | Celery task worker |
| `beat` | — | Celery Beat scheduler (HubSpot sync, HigherGov fetch) |
| `postgres` | 5432 | PostgreSQL + pgvector |
| `redis` | 6379 | Celery broker + result backend |

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend at http://localhost:5173, API at http://localhost:8000.

### 4. Verify

```bash
curl http://localhost:8000/api/health
# {"status": "ok", "service": "blackbox"}
```

### 5. Upload your first RFP

```bash
curl -X POST http://localhost:8000/api/rfps/upload \
  -F "file=@my-rfp.pdf"
```

Then generate a proposal:

```bash
curl -X POST http://localhost:8000/api/proposals/{rfp_id}/generate
```

## Project Structure

```
blackbox/
├── backend/
│   ├── app/
│   │   ├── agents/              # AI agent system
│   │   │   ├── playbook.py      # ConsultAdd Winning Playbook (14 patterns, company profile, staff roster)
│   │   │   ├── base.py          # BaseAgent — abstract class all agents inherit
│   │   │   ├── orchestrator.py  # LangGraph pipeline: qualify → [solution || compliance] → cost → review
│   │   │   ├── qualification.py # GO/NO-GO decision agent (Opus)
│   │   │   ├── solution.py      # Technical approach writer (Opus)
│   │   │   ├── compliance.py    # Compliance narrative + forms checklist (Opus)
│   │   │   ├── cost.py          # Cost proposal with deterministic calculation + narrative (Opus)
│   │   │   ├── review.py        # QA reviewer — checks contradictions + playbook violations (Opus)
│   │   │   ├── reconcile.py     # Cross-section consistency fixer (runs after review)
│   │   │   └── ingestion.py     # RFP document parser (Haiku)
│   │   ├── api/                 # FastAPI routes
│   │   │   ├── rfps.py          # RFP CRUD + upload + ingest-url
│   │   │   ├── proposals.py     # Proposal CRUD + generate + assemble + export
│   │   │   ├── dashboard.py     # Pipeline health, agent stats, win analysis
│   │   │   └── company.py       # Company knowledge CRUD
│   │   ├── assembly/            # Document output
│   │   │   ├── assembler.py     # Stitches sections into markdown with cover letter + TOC
│   │   │   ├── pdf_renderer.py  # Markdown → HTML → PDF (WeasyPrint)
│   │   │   └── docx_renderer.py # Markdown → DOCX (python-docx)
│   │   ├── integrations/        # External service connectors
│   │   │   ├── highergov.py     # HigherGov RFP API — 3-tier filter (NAICS → rules → Haiku scoring)
│   │   │   ├── hubspot_sync.py  # HubSpot deal outcome sync
│   │   │   └── embedding_pipeline.py  # Voyage embeddings for similar proposal search
│   │   ├── analytics/           # Reporting
│   │   │   ├── agent_analytics.py    # Per-agent cost/performance tracking
│   │   │   └── outcome_analysis.py   # Win rate analysis by category/state
│   │   ├── workers/
│   │   │   ├── tasks.py         # Celery tasks (generate, ingest, sync, embed, ETL)
│   │   │   └── beat_schedule.py # Scheduled tasks (HubSpot every 60s, HigherGov daily)
│   │   ├── models/database.py   # SQLAlchemy models (RFP, Proposal, AgentRun, etc.)
│   │   ├── config.py            # Pydantic settings from .env
│   │   └── main.py              # FastAPI app factory
│   ├── tests/                   # 160+ unit tests
│   ├── scripts/                 # Utility scripts (seed data, embed proposals)
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, RFP list, Proposal detail
│   │   ├── components/          # Layout, UI components (Shadcn/ui)
│   │   └── lib/api.ts           # API client
│   ├── package.json
│   └── vite.config.ts
├── etl/                         # Data extraction scripts (Coda, HubSpot, Slack)
├── docker-compose.yml
├── CLAUDE.md                    # AI agent instructions
└── .env.example
```

## Agent Pipeline

### Execution Order

```
QUALIFY → [SOLUTION || COMPLIANCE] → COST → REVIEW → RECONCILE → ASSEMBLE
```

Solution and Compliance run in parallel via `asyncio.gather`. If Review finds issues, a revision loop re-runs affected agents (max 2 passes).

### Agent Details

| Agent | Model | Max Tokens | Purpose |
|-------|-------|------------|---------|
| **Qualify** | Opus | 4,096 | GO/NO-GO decision based on certs, win history, scope fit |
| **Solution** | Opus | 16,000 | Technical approach with named staff, deliverables, timeline |
| **Compliance** | Opus | 12,000 | Regulation citations, forms checklist, MBE/DBE statement |
| **Cost** | Opus | 12,000 | Deterministic calculation + narrative justification |
| **Review** | Opus | 12,000 | QA — contradictions, playbook violations, offshore check |
| **Reconcile** | Opus | 16,000 | Cross-section consistency fix (rates, names, versions) |
| **Ingest** | Haiku | 2,048 | Parse uploaded RFP into structured brief |

### The Winning Playbook

All agents are guided by `playbook.py` — 14 patterns reverse-engineered from 13 actual winning proposals:

1. **Agency-first opening** — lead with their mission, not ours
2. **Mirror RFP structure** — section numbers match 1:1
3. **Never mention India/offshore** — US-only framing
4. **Name specific people** — from a real 12-person staff roster
5. **Construct local presence** — Industrious satellite offices nationwide
6. **Price 30-50% under ceiling** — aggressive but justified
7. **Quantify everything** — "94.7% SLA" not "good performance"
8. **Pre-research the agency** — cite their systems, plans, audits
9. **Exceed SLA minimums** — and show the data
10. **Lead with MBE** — where diversity is scored
11. **Value-added services at $0** — executive oversight, DR simulations
12. **Deliverable output boxes** — visual anchors for evaluators
13. **Cite regulations by number** — "HIPAA 45 CFR §164.308"
14. **Seed follow-on work** — position for multi-year partnership

## API Reference

### RFPs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/rfps` | List all RFPs |
| `GET` | `/api/rfps/{id}` | Get RFP details |
| `POST` | `/api/rfps/upload` | Upload RFP document (PDF/DOCX/TXT) |
| `POST` | `/api/rfps/ingest-url` | Ingest RFP from URL |

### Proposals

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/proposals` | List all proposals |
| `GET` | `/api/proposals/{id}` | Get proposal details |
| `POST` | `/api/proposals/{rfp_id}/generate` | Generate proposal for an RFP |
| `POST` | `/api/proposals/{id}/assemble` | Assemble into document |
| `GET` | `/api/proposals/{id}/export/pdf` | Download as PDF |
| `GET` | `/api/proposals/{id}/export/docx` | Download as DOCX |
| `PATCH` | `/api/proposals/{id}` | Update proposal |
| `PATCH` | `/api/proposals/{id}/outcome` | Record win/loss |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dashboard/pipeline` | Pipeline health (queued/generating/draft counts) |
| `GET` | `/api/dashboard/agents` | Agent performance stats |
| `GET` | `/api/dashboard/agents/detailed` | Per-agent cost and timing |
| `GET` | `/api/dashboard/costs` | Token usage and estimated API costs |
| `GET` | `/api/dashboard/outcomes` | Win/loss/pending counts |
| `GET` | `/api/dashboard/win-analysis` | Win rate by category and state |
| `GET` | `/api/dashboard/deadlines` | Upcoming RFP deadlines |

Full OpenAPI docs at http://localhost:8000/docs.

## Development

### Run backend locally (without Docker)

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload
```

### Run tests

```bash
cd backend
python -m pytest tests/ -v --ignore=tests/test_integration.py
```

### Key files to understand first

1. **`backend/app/agents/playbook.py`** — The brain. Company profile, winning patterns, staff roster, agent rules. Start here.
2. **`backend/app/agents/orchestrator.py`** — The pipeline. LangGraph state machine that chains all agents.
3. **`backend/app/agents/base.py`** — BaseAgent abstract class. All agents inherit `run()`, `build_prompt()`, `validate_output()`.
4. **`backend/app/workers/tasks.py`** — Celery tasks that invoke the pipeline asynchronously.
5. **`backend/app/models/database.py`** — All SQLAlchemy models (RFP, Proposal, AgentRun, CompanyKnowledge, etc.)

### Adding a new agent

1. Create `backend/app/agents/my_agent.py` inheriting from `BaseAgent`
2. Implement `build_prompt()` (return system + user prompts) and `validate_output()` (parse JSON)
3. Add it as a node in `orchestrator.py`'s `build_graph()`
4. Write tests in `backend/tests/test_my_agent.py`

### Modifying the playbook

Edit `backend/app/agents/playbook.py`. Changes affect all agents immediately. Key sections:

- `CONSULTADD_PROFILE` — Company data, certs, references, staff roster
- `WINNING_PLAYBOOK` — 14 patterns
- `SOLUTION_RULES`, `COMPLIANCE_RULES`, `COST_RULES`, etc. — Agent-specific rules
- `CANONICAL_CITATIONS` — Version-locked regulation references

## Data Model

```
RFP (rfps)
├── extracted_brief: jsonb       # Parsed RFP structure
├── title, agency_name, state
├── estimated_value, deadline
└── source: "manual" | "highergov" | "coda"

Proposal (proposals)
├── rfp_id → RFP
├── qualification_result: jsonb  # GO/NO-GO + reasons
├── solution_section: text       # Technical approach markdown
├── compliance_section: text     # Compliance narrative markdown
├── cost_section: jsonb          # Roles, rates, totals, narrative
├── review_result: jsonb         # Quality score + contradictions
├── assembled_document: text     # Final stitched markdown
├── status: queued → generating → draft → reviewing → submitted
└── outcome: pending → won | lost | interview | no_response

AgentRun (agent_runs)
├── proposal_id → Proposal
├── agent_type, model_used
├── input_tokens, output_tokens, duration_ms
└── status: "ok" | "error"

CompanyKnowledge (company_knowledge)
├── type: "cert" | "capability" | "ratecard" | "boilerplate"
├── key: identifier
└── value: jsonb
```

## Integrations

### HigherGov (RFP sourcing)

Automated daily fetch of SLED IT opportunities. 3-tier filter:
1. **NAICS code filter** — IT services codes only (541511, 541512, etc.)
2. **Rules filter** — deadline 24h–15d out, value < $2M, not sole-source, has description
3. **Haiku relevance scorer** — scores service fit, size fit, capability fit (threshold: 60+)

### HubSpot (deal sync)

Celery Beat syncs deal outcomes every 60 seconds. Maps deal stages to proposal outcomes (won/lost/interview).

### Slack (award history)

Reads `#rfp-awarded` and `#general` channels for historical win data and proposal documents.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for all agents |
| `HUBSPOT_API_KEY` | No | HubSpot access token for deal sync |
| `HIGHERGOV_API_KEY` | No | HigherGov API key for RFP sourcing |
| `SLACK_BOT_TOKEN` | No | Slack bot token for channel reading |
| `VOYAGE_API_KEY` | No | Voyage AI key for embeddings |
| `DATABASE_URL` | Auto | PostgreSQL connection (set by Docker) |
| `REDIS_URL` | Auto | Redis connection (set by Docker) |

## License

Proprietary. ConsultAdd Inc.
