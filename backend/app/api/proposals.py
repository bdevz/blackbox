from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import Proposal, RFP, get_db

router = APIRouter()


class ProposalUpdate(BaseModel):
    solution_section: str | None = None
    compliance_section: str | None = None
    cost_section: dict | None = None
    human_review_scores: dict | None = None


class OutcomeUpdate(BaseModel):
    outcome: str


@router.get("")
def list_proposals(skip: int = 0, limit: int = 50, status: str = None, db: Session = Depends(get_db)):
    query = db.query(Proposal).order_by(Proposal.created_at.desc())
    if status:
        query = query.filter(Proposal.status == status)
    return query.offset(skip).limit(limit).all()


@router.get("/{proposal_id}")
def get_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    return proposal


@router.post("/{rfp_id}/generate")
def generate_proposal(rfp_id: UUID, db: Session = Depends(get_db)):
    rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
    if not rfp:
        raise HTTPException(404, "RFP not found")
    proposal = Proposal(rfp_id=rfp.id, status="queued")
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    # TODO: queue LangGraph pipeline as Celery task
    return {"id": str(proposal.id), "status": "queued"}


@router.patch("/{proposal_id}")
def update_proposal(proposal_id: UUID, update: ProposalUpdate, db: Session = Depends(get_db)):
    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(proposal, field, value)
    db.commit()
    return {"status": "updated"}


@router.post("/{proposal_id}/submit")
def submit_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    proposal.status = "submitted"
    db.commit()
    return {"status": "submitted"}


@router.patch("/{proposal_id}/outcome")
def update_outcome(proposal_id: UUID, update: OutcomeUpdate, db: Session = Depends(get_db)):
    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    proposal.outcome = update.outcome
    db.commit()
    return {"status": "updated", "outcome": update.outcome}
