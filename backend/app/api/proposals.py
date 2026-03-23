import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.models.database import Proposal, RFP, CompanyKnowledge, get_db
from app.workers.tasks import generate_proposal_task

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
    generate_proposal_task.delay(str(proposal.id))
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


@router.get("/{proposal_id}/export/pdf")
def export_pdf(proposal_id: UUID, db: Session = Depends(get_db)):
    proposal = db.query(Proposal).options(joinedload(Proposal.rfp)).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if not proposal.assembled_document:
        raise HTTPException(400, "Proposal has not been assembled yet")

    from app.assembly.pdf_renderer import render_pdf
    title = proposal.rfp.title if proposal.rfp else "Proposal"
    pdf_bytes = render_pdf(proposal.assembled_document, title=title)
    agency = (proposal.rfp.agency_name or "agency").replace(" ", "_") if proposal.rfp else "agency"
    filename = f"{agency}_{proposal_id}_proposal.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{proposal_id}/export/docx")
def export_docx(proposal_id: UUID, db: Session = Depends(get_db)):
    proposal = db.query(Proposal).options(joinedload(Proposal.rfp)).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if not proposal.assembled_document:
        raise HTTPException(400, "Proposal has not been assembled yet")

    from app.assembly.docx_renderer import render_docx
    title = proposal.rfp.title if proposal.rfp else "Proposal"
    docx_bytes = render_docx(proposal.assembled_document, title=title)
    agency = (proposal.rfp.agency_name or "agency").replace(" ", "_") if proposal.rfp else "agency"
    filename = f"{agency}_{proposal_id}_proposal.docx"

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{proposal_id}/assemble")
def reassemble_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    proposal = db.query(Proposal).options(joinedload(Proposal.rfp)).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")

    from app.assembly.assembler import assemble_proposal

    boilerplate_rows = db.query(CompanyKnowledge).filter(CompanyKnowledge.type == "boilerplate").all()
    boilerplate = {r.key: r.value for r in boilerplate_rows}

    rfp = proposal.rfp
    assembled = assemble_proposal(
        rfp_title=rfp.title if rfp else "Untitled RFP",
        agency_name=rfp.agency_name if rfp else "Unknown Agency",
        deadline=str(rfp.deadline) if rfp and rfp.deadline else None,
        qualification=proposal.qualification_result or {},
        solution_section=proposal.solution_section or "",
        compliance_section=proposal.compliance_section or "",
        cost_section=proposal.cost_section or {},
        review_result=proposal.review_result,
        boilerplate=boilerplate,
    )
    proposal.assembled_document = assembled
    db.commit()

    return {"proposal_id": str(proposal_id), "status": "assembled", "length": len(assembled)}
