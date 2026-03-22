from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import RFP, Proposal, AgentRun, get_db

router = APIRouter()


@router.get("/pipeline")
def pipeline_health(db: Session = Depends(get_db)):
    counts = {}
    for status in ["queued", "generating", "draft", "reviewing", "submitted"]:
        counts[status] = db.query(Proposal).filter(Proposal.status == status).count()
    return counts


@router.get("/agents")
def agent_performance(db: Session = Depends(get_db)):
    results = db.query(
        AgentRun.agent_type,
        func.avg(AgentRun.duration_ms).label("avg_duration_ms"),
        func.count(AgentRun.id).label("total_runs"),
        func.sum(func.cast(AgentRun.status == "error", db.bind.dialect.name == "postgresql" and "integer" or "int")).label("errors"),
    ).group_by(AgentRun.agent_type).all()
    return [{"agent": r.agent_type, "avg_duration_ms": float(r.avg_duration_ms or 0), "total_runs": r.total_runs} for r in results]


@router.get("/costs")
def cost_tracking(db: Session = Depends(get_db)):
    results = db.query(
        func.sum(AgentRun.input_tokens).label("total_input"),
        func.sum(AgentRun.output_tokens).label("total_output"),
        func.count(AgentRun.id).label("total_calls"),
    ).first()
    input_t = results.total_input or 0
    output_t = results.total_output or 0
    estimated_cost = (input_t * 0.000015) + (output_t * 0.000075)
    return {"input_tokens": input_t, "output_tokens": output_t, "total_calls": results.total_calls, "estimated_cost_usd": round(estimated_cost, 2)}


@router.get("/outcomes")
def outcome_tracker(db: Session = Depends(get_db)):
    counts = {}
    for outcome in ["pending", "won", "lost", "interview", "no_response"]:
        counts[outcome] = db.query(Proposal).filter(Proposal.outcome == outcome).count()
    total = sum(counts.values())
    win_rate = (counts.get("won", 0) / total * 100) if total > 0 else 0
    return {"counts": counts, "total": total, "win_rate_pct": round(win_rate, 1)}


@router.get("/deadlines")
def deadline_radar(db: Session = Depends(get_db)):
    rfps = db.query(RFP).filter(RFP.deadline.isnot(None)).order_by(RFP.deadline).limit(50).all()
    return [{"id": str(r.id), "title": r.title, "agency": r.agency_name, "deadline": r.deadline, "state": r.agency_state} for r in rfps]
