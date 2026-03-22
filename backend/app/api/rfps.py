from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.models.database import RFP, get_db

router = APIRouter()


@router.get("")
def list_rfps(skip: int = 0, limit: int = 50, status: str = None, db: Session = Depends(get_db)):
    query = db.query(RFP).order_by(RFP.created_at.desc())
    if status:
        query = query.filter(RFP.metadata["status"].astext == status)
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
    rfp = RFP(title=file.filename or "Untitled", source="manual", metadata={"filename": file.filename, "size": len(content)})
    db.add(rfp)
    db.commit()
    db.refresh(rfp)
    # TODO: queue ingestion pipeline task
    return {"id": str(rfp.id), "status": "queued", "filename": file.filename}


@router.post("/ingest-url")
def ingest_url(url: str, db: Session = Depends(get_db)):
    rfp = RFP(title=url, source="manual", metadata={"url": url})
    db.add(rfp)
    db.commit()
    db.refresh(rfp)
    # TODO: queue URL scraping task
    return {"id": str(rfp.id), "status": "queued", "url": url}
