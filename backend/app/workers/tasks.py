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
                db.commit()
                raise
            proposal.status = "queued"
            db.commit()
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


@celery_app.task
def ingest_rfp_task(rfp_id: str, file_content_b64: str = None, filename: str = None, file_url: str = None):
    """Parse and ingest an RFP document into a structured brief.

    Note: file_content_b64 is base64-encoded because Celery uses JSON serialization
    which cannot transport raw bytes.
    """
    import base64
    from datetime import datetime, timezone

    from app.agents.ingestion import extract_text, parse_brief
    from app.models.database import SessionLocal, RFP

    db = SessionLocal()
    try:
        rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
        if not rfp:
            return {"error": "RFP not found", "rfp_id": rfp_id}

        # Decode base64 content if provided
        content = base64.b64decode(file_content_b64) if file_content_b64 else None
        fname = filename or (rfp.meta.get("filename", "document.txt") if rfp.meta else "document.txt")

        if content is None and (file_url or rfp.raw_document_url):
            import httpx
            url = file_url or rfp.raw_document_url
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            content = resp.content
            fname = url.rsplit("/", 1)[-1] if "/" in url else "document.pdf"

        if content is None:
            return {"error": "No document content available", "rfp_id": rfp_id}

        text = extract_text(content, fname)
        brief = asyncio.run(parse_brief(text))

        rfp.extracted_brief = brief
        rfp.title = brief.get("title", rfp.title)
        rfp.agency_name = brief.get("agency")
        rfp.agency_state = brief.get("state")
        rfp.category = brief.get("category")
        if brief.get("estimated_value"):
            rfp.estimated_value = brief["estimated_value"]
        rfp.ingested_at = datetime.now(timezone.utc)
        db.commit()

        return {"rfp_id": rfp_id, "status": "ingested", "title": brief.get("title")}

    except Exception as e:
        db.rollback()
        return {"rfp_id": rfp_id, "status": "error", "error": str(e)}
    finally:
        db.close()
