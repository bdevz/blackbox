from celery import Celery

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
    from app.models.database import SessionLocal, Proposal
    db = SessionLocal()
    try:
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if not proposal:
            return {"error": "Proposal not found"}
        proposal.status = "generating"
        db.commit()
        # TODO: invoke LangGraph orchestrator
        return {"proposal_id": proposal_id, "status": "generating"}
    finally:
        db.close()


@celery_app.task
def ingest_rfp_task(rfp_id: str, file_url: str = None):
    """Parse and ingest an RFP document."""
    # TODO: invoke ingestion pipeline
    return {"rfp_id": rfp_id, "status": "ingested"}
