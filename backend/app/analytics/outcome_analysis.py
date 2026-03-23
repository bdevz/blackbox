"""Win/loss analysis from proposal outcomes."""

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.database import Proposal, RFP


def get_win_analysis(db: Session) -> dict:
    """Comprehensive win/loss analysis."""
    by_category = (
        db.query(
            RFP.category,
            func.count(Proposal.id).label("total"),
            func.sum(case((Proposal.outcome == "won", 1), else_=0)).label("won"),
            func.sum(case((Proposal.outcome == "lost", 1), else_=0)).label("lost"),
        )
        .join(Proposal, Proposal.rfp_id == RFP.id)
        .filter(Proposal.outcome.in_(["won", "lost"]))
        .group_by(RFP.category)
        .all()
    )

    categories = [
        {
            "category": r.category or "Unknown",
            "total": r.total,
            "won": r.won,
            "lost": r.lost,
            "win_rate": round(r.won / r.total, 4) if r.total > 0 else 0,
        }
        for r in by_category
    ]

    by_state = (
        db.query(
            RFP.agency_state,
            func.count(Proposal.id).label("total"),
            func.sum(case((Proposal.outcome == "won", 1), else_=0)).label("won"),
        )
        .join(Proposal, Proposal.rfp_id == RFP.id)
        .filter(Proposal.outcome.in_(["won", "lost"]))
        .group_by(RFP.agency_state)
        .all()
    )

    states = [
        {
            "state": r.agency_state or "Unknown",
            "total": r.total,
            "won": r.won,
            "win_rate": round(r.won / r.total, 4) if r.total > 0 else 0,
        }
        for r in by_state
    ]

    overall = db.query(
        func.count(Proposal.id).label("total"),
        func.sum(case((Proposal.outcome == "won", 1), else_=0)).label("won"),
        func.sum(case((Proposal.outcome == "lost", 1), else_=0)).label("lost"),
    ).filter(Proposal.outcome.in_(["won", "lost"])).first()

    return {
        "overall": {
            "total": overall.total or 0,
            "won": overall.won or 0,
            "lost": overall.lost or 0,
            "win_rate": round((overall.won or 0) / overall.total, 4) if overall.total else 0,
        },
        "by_category": categories,
        "by_state": states,
    }
