import base64
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.models.database import RFP, get_db

router = APIRouter()


@router.get("")
def list_rfps(skip: int = 0, limit: int = 50, status: str = None, db: Session = Depends(get_db)):
    query = db.query(RFP).order_by(RFP.created_at.desc())
    if status:
        query = query.filter(RFP.meta["status"].astext == status)
    return query.offset(skip).limit(limit).all()


@router.get("/{rfp_id}")
def get_rfp(rfp_id: UUID, db: Session = Depends(get_db)):
    rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
    if not rfp:
        raise HTTPException(404, "RFP not found")
    return rfp


@router.post("/upload")
async def upload_rfp(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    rfp = RFP(
        title=file.filename or "Untitled",
        source="manual",
        meta={"filename": file.filename, "size": len(content)},
    )
    db.add(rfp)
    db.commit()
    db.refresh(rfp)

    from app.workers.tasks import ingest_rfp_task
    ingest_rfp_task.delay(
        str(rfp.id),
        file_content_b64=base64.b64encode(content).decode(),
        filename=file.filename,
    )

    return {"id": str(rfp.id), "status": "queued", "filename": file.filename}


@router.post("/ingest-url")
def ingest_url(url: str, db: Session = Depends(get_db)):
    rfp = RFP(title=url, source="manual", meta={"url": url})
    rfp.raw_document_url = url
    db.add(rfp)
    db.commit()
    db.refresh(rfp)

    from app.workers.tasks import ingest_rfp_task
    ingest_rfp_task.delay(str(rfp.id), file_url=url)

    return {"id": str(rfp.id), "status": "queued", "url": url}


@router.post("/fetch-highergov")
def fetch_highergov(captured_date: str = None, db: Session = Depends(get_db)):
    """Trigger HigherGov RFP fetch. Defaults to yesterday if no date given."""
    from app.workers.tasks import fetch_highergov_rfps_task
    task = fetch_highergov_rfps_task.delay(captured_date=captured_date)
    return {"task_id": task.id, "status": "queued", "captured_date": captured_date or "yesterday"}


@router.get("/highergov/stats")
def highergov_stats(db: Session = Depends(get_db)):
    """Show HigherGov ingestion stats."""
    from sqlalchemy import func
    total = db.query(func.count(RFP.id)).filter(RFP.source == "highergov").scalar()
    by_state = (
        db.query(RFP.agency_state, func.count(RFP.id))
        .filter(RFP.source == "highergov")
        .group_by(RFP.agency_state)
        .order_by(func.count(RFP.id).desc())
        .limit(10)
        .all()
    )
    by_category = (
        db.query(RFP.category, func.count(RFP.id))
        .filter(RFP.source == "highergov")
        .group_by(RFP.category)
        .order_by(func.count(RFP.id).desc())
        .all()
    )
    return {
        "total_ingested": total,
        "by_state": [{"state": s, "count": c} for s, c in by_state],
        "by_naics": [{"naics": n, "count": c} for n, c in by_category],
    }
