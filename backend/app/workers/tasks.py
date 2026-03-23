import asyncio

from celery import Celery
from sqlalchemy.orm import joinedload

from app.config import settings

celery_app = Celery("blackbox", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, max_retries=2)
def generate_proposal_task(self, proposal_id: str):
    """Run the full LangGraph pipeline for a proposal."""
    from app.agents.orchestrator import proposal_graph
    from app.models.database import SessionLocal, Proposal

    db = SessionLocal()
    try:
        proposal = (
            db.query(Proposal)
            .options(joinedload(Proposal.rfp))
            .filter(Proposal.id == proposal_id)
            .first()
        )
        if not proposal:
            return {"error": "Proposal not found"}

        proposal.status = "generating"
        db.commit()

        initial_state = {
            "rfp_id": str(proposal.rfp_id),
            "rfp_brief": proposal.rfp.extracted_brief,
            "proposal_id": str(proposal.id),
        }
        result = asyncio.run(proposal_graph.ainvoke(initial_state))

        proposal.qualification_result = result.get("qualification")
        proposal.solution_section = result.get("solution", {}).get("approach", "")
        proposal.compliance_section = result.get("compliance", {}).get("narrative", "")
        proposal.cost_section = result.get("cost")
        proposal.review_result = result.get("review")
        proposal.status = "draft"
        db.commit()

        return {"proposal_id": proposal_id, "status": "draft"}

    except Exception as e:
        db.rollback()
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if proposal:
            if self.request.retries >= self.max_retries:
                proposal.status = "failed"
            else:
                proposal.status = "queued"
            db.commit()
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


@celery_app.task
def ingest_rfp_task(rfp_id: str, file_url: str = None):
    """Parse and ingest an RFP document."""
    # TODO: invoke ingestion pipeline
    return {"rfp_id": rfp_id, "status": "ingested"}
