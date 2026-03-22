# Blackbox Development

## Commands
```bash
docker compose up -d              # start full stack (postgres, redis, backend, worker)
docker compose logs -f backend    # follow backend logs
docker compose logs -f worker     # follow worker logs
cd backend && pip install -e .    # install backend deps locally
cd backend && uvicorn app.main:app --reload  # run backend locally
cd frontend && npm run dev        # frontend dev server
python etl/coda_extract.py extract          # extract Coda RFP data
python etl/hubspot_extract.py extract       # extract HubSpot deals
python etl/slack_extract.py extract         # extract Slack discussions
```

## Architecture
- **Backend:** FastAPI + SQLAlchemy + Celery + Redis
- **Agents:** LangGraph orchestrator + 5 specialist agents (qualify, solution, comply, cost, review)
- **Database:** PostgreSQL + pgvector
- **Frontend:** React + Vite + Shadcn/ui + Tailwind
- **ETL:** Coda (RFPs, rate cards), HubSpot (deals, outcomes), Slack (discussions)

## Agent execution order
QUALIFY → [SOLUTION || COMPLY] → COST → REVIEW

## Key files
- `backend/app/agents/orchestrator.py` — LangGraph pipeline definition
- `backend/app/agents/base.py` — BaseAgent class (all agents inherit from this)
- `backend/app/models/database.py` — SQLAlchemy models (all tables)
- `backend/app/config.py` — Environment settings
- `etl/` — Extraction scripts for Coda, HubSpot, Slack

## Tool IDs
- Coda doc: dSt8mkiTmO7
- Slack channels: C088YP1M732 (interview-team), C07AYH29X4L (general)
- HubSpot portal: 243046792, pipeline: RFX
