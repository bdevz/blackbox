import asyncio
import logging

from celery import Celery
from sqlalchemy.orm import joinedload

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery("blackbox", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

from app.workers.beat_schedule import CELERY_BEAT_SCHEDULE
celery_app.conf.beat_schedule = CELERY_BEAT_SCHEDULE


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
        logger.info("[TASK] Invoking LangGraph pipeline — proposal=%s", proposal_id)
        result = asyncio.run(proposal_graph.ainvoke(initial_state))
        logger.info("[TASK] Pipeline finished — final_status=%s, keys=%s",
                    result.get("status"), list(result.keys()))

        # Log what we got back before saving
        qual = result.get("qualification")
        sol = result.get("solution", {})
        comp = result.get("compliance", {})
        cost = result.get("cost")
        rev = result.get("review")

        logger.info("[TASK] Saving to DB — proposal=%s", proposal_id)
        logger.info("[TASK]   qualification_result: %s", "PRESENT" if qual else "MISSING")
        logger.info("[TASK]   solution_section (approach): %d chars",
                    len(sol.get("approach", "")) if sol else 0)
        logger.info("[TASK]   compliance_section (narrative): %d chars",
                    len(comp.get("narrative", "")) if comp else 0)
        logger.info("[TASK]   cost_section: %s", "PRESENT" if cost else "MISSING")
        logger.info("[TASK]   review_result: recommendation=%s, quality_score=%s",
                    rev.get("recommendation") if rev else None,
                    rev.get("quality_score") if rev else None)

        proposal.qualification_result = qual
        proposal.solution_section = sol.get("approach", "") if sol else ""
        proposal.compliance_section = comp.get("narrative", "") if comp else ""
        proposal.cost_section = cost
        proposal.review_result = rev
        proposal.status = "draft"

        # Assemble document
        try:
            from app.assembly.assembler import assemble_proposal
            from app.models.database import CompanyKnowledge

            boilerplate_rows = db.query(CompanyKnowledge).filter(CompanyKnowledge.type == "boilerplate").all()
            boilerplate = {r.key: r.value for r in boilerplate_rows}
            rfp = proposal.rfp

            proposal.assembled_document = assemble_proposal(
                rfp_title=rfp.title if rfp else "Untitled RFP",
                agency_name=rfp.agency_name if rfp else "Unknown Agency",
                deadline=str(rfp.deadline) if rfp and rfp.deadline else None,
                qualification=result.get("qualification", {}),
                solution_section=result.get("solution", {}).get("approach", ""),
                compliance_section=result.get("compliance", {}).get("narrative", ""),
                cost_section=result.get("cost", {}),
                review_result=result.get("review"),
                boilerplate=boilerplate,
            )
        except Exception as assembly_err:
            logger.warning("[TASK] Assembly failed for proposal %s: %s", proposal_id, assembly_err)

        db.commit()
        logger.info("[TASK] DB commit SUCCESS — proposal=%s status=draft", proposal_id)

        # Index proposal into Pinecone immediately after draft is saved
        try:
            from app.services.rag_indexer import index_proposal
            asyncio.run(index_proposal(proposal_id, db))
        except Exception as idx_err:
            logger.warning("[TASK] Pinecone indexing failed for proposal %s: %s", proposal_id, idx_err)

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

        # Index RFP into Pinecone immediately after ingestion
        try:
            from app.services.rag_indexer import index_rfp
            asyncio.run(index_rfp(rfp_id, db))
        except Exception as idx_err:
            logger.warning("[TASK] Pinecone indexing failed for RFP %s: %s", rfp_id, idx_err)

        return {"rfp_id": rfp_id, "status": "ingested", "title": brief.get("title")}

    except Exception as e:
        db.rollback()
        return {"rfp_id": rfp_id, "status": "error", "error": str(e)}
    finally:
        db.close()


@celery_app.task
def fetch_highergov_rfps_task(captured_date: str = None):
    """Periodic task: fetch, filter, and score RFPs from HigherGov."""
    from app.integrations.highergov import fetch_and_filter
    return asyncio.run(fetch_and_filter(captured_date=captured_date))


@celery_app.task
def sync_hubspot_outcomes_task():
    """Periodic task: sync outcomes from HubSpot."""
    from app.integrations.hubspot_sync import sync_outcomes
    return sync_outcomes()


@celery_app.task
def embed_winning_proposals_task():
    """Periodic task: embed winning proposals for similarity search.

    Runs the legacy Voyage+pgvector pipeline AND indexes to Pinecone.
    """
    from app.integrations.embedding_pipeline import embed_winning_proposals
    pgvector_result = embed_winning_proposals()

    # Also index any won/lost proposals not yet in Pinecone
    try:
        from app.models.database import SessionLocal, Proposal
        from app.services.rag_indexer import index_proposal

        db = SessionLocal()
        try:
            proposals = (
                db.query(Proposal)
                .filter(Proposal.outcome.in_(["won", "lost"]))
                .filter(Proposal.solution_section.isnot(None))
                .all()
            )
            indexed = 0
            for p in proposals:
                try:
                    count = asyncio.run(index_proposal(str(p.id), db))
                    indexed += count
                except Exception:
                    pass
        finally:
            db.close()

        return {**pgvector_result, "pinecone_vectors": indexed}
    except Exception as e:
        return {**pgvector_result, "pinecone_error": str(e)}


@celery_app.task
def run_coda_etl_task():
    """Periodic task: extract data from Coda."""
    import os
    import subprocess
    cwd = "/app" if os.path.exists("/app/etl") else "."
    result = subprocess.run(
        ["python", "etl/coda_extract.py", "extract", "--load-db"],
        capture_output=True, text=True, timeout=300, cwd=cwd,
    )
    return {"stdout": result.stdout[-500:], "stderr": result.stderr[-500:], "returncode": result.returncode}


@celery_app.task
def run_hubspot_etl_task():
    """Periodic task: extract data from HubSpot."""
    import os
    import subprocess
    cwd = "/app" if os.path.exists("/app/etl") else "."
    result = subprocess.run(
        ["python", "etl/hubspot_extract.py", "extract", "--load-db"],
        capture_output=True, text=True, timeout=300, cwd=cwd,
    )
    return {"stdout": result.stdout[-500:], "stderr": result.stderr[-500:], "returncode": result.returncode}


@celery_app.task
def run_slack_etl_task():
    """Periodic task: extract data from Slack."""
    import os
    import subprocess
    cwd = "/app" if os.path.exists("/app/etl") else "."
    result = subprocess.run(
        ["python", "etl/slack_extract.py", "extract", "--load-db"],
        capture_output=True, text=True, timeout=300, cwd=cwd,
    )
    return {"stdout": result.stdout[-500:], "stderr": result.stderr[-500:], "returncode": result.returncode}
