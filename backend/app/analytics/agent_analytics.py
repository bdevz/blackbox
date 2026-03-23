"""Agent performance analytics from AgentRun data."""

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.database import AgentRun


# Approximate per-token costs by agent model
MODEL_COSTS = {
    "qualify": {"input": 0.000001, "output": 0.000005},     # Haiku
    "solution": {"input": 0.000015, "output": 0.000075},    # Opus
    "comply": {"input": 0.000015, "output": 0.000075},      # Opus
    "cost": {"input": 0.000003, "output": 0.000015},        # Sonnet
    "review": {"input": 0.000003, "output": 0.000015},      # Sonnet
}


def get_agent_detailed_stats(db: Session) -> list[dict]:
    """Get detailed per-agent performance metrics."""
    results = (
        db.query(
            AgentRun.agent_type,
            func.count(AgentRun.id).label("total_runs"),
            func.avg(AgentRun.duration_ms).label("avg_duration_ms"),
            func.avg(AgentRun.input_tokens).label("avg_input_tokens"),
            func.avg(AgentRun.output_tokens).label("avg_output_tokens"),
            func.sum(AgentRun.input_tokens).label("total_input_tokens"),
            func.sum(AgentRun.output_tokens).label("total_output_tokens"),
            func.sum(case((AgentRun.status == "error", 1), else_=0)).label("error_count"),
        )
        .group_by(AgentRun.agent_type)
        .all()
    )

    stats = []
    for r in results:
        costs = MODEL_COSTS.get(r.agent_type, {"input": 0.000003, "output": 0.000015})
        total_cost = (
            (r.total_input_tokens or 0) * costs["input"]
            + (r.total_output_tokens or 0) * costs["output"]
        )

        stats.append({
            "agent_type": r.agent_type,
            "total_runs": r.total_runs,
            "avg_duration_ms": round(r.avg_duration_ms or 0),
            "avg_input_tokens": round(r.avg_input_tokens or 0),
            "avg_output_tokens": round(r.avg_output_tokens or 0),
            "error_count": r.error_count,
            "error_rate": round(r.error_count / r.total_runs, 4) if r.total_runs else 0,
            "total_cost_usd": round(total_cost, 4),
            "avg_cost_per_run": round(total_cost / r.total_runs, 4) if r.total_runs else 0,
        })

    return stats


def get_proposal_cost_breakdown(db: Session, proposal_id: str) -> dict:
    """Get per-agent cost breakdown for a specific proposal."""
    runs = db.query(AgentRun).filter(AgentRun.proposal_id == proposal_id).all()

    breakdown = []
    total = 0
    for run in runs:
        costs = MODEL_COSTS.get(run.agent_type, {"input": 0.000003, "output": 0.000015})
        run_cost = (
            (run.input_tokens or 0) * costs["input"]
            + (run.output_tokens or 0) * costs["output"]
        )
        total += run_cost
        breakdown.append({
            "agent_type": run.agent_type,
            "model": run.model_used,
            "duration_ms": run.duration_ms,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "cost_usd": round(run_cost, 4),
            "status": run.status,
        })

    return {"proposal_id": proposal_id, "runs": breakdown, "total_cost_usd": round(total, 4)}


def get_optimization_recommendations(db: Session) -> list[dict]:
    """Suggest model optimizations based on agent performance."""
    stats = get_agent_detailed_stats(db)
    recommendations = []

    for s in stats:
        if s["agent_type"] in ("solution", "comply") and s["error_rate"] == 0 and s["total_runs"] >= 5:
            recommendations.append({
                "agent_type": s["agent_type"],
                "current_model": "claude-opus-4-6",
                "suggested_model": "claude-sonnet-4-6",
                "reason": f"Zero errors across {s['total_runs']} runs. Sonnet may produce equivalent quality at ~80% cost savings.",
                "estimated_savings_per_run": round(s["avg_cost_per_run"] * 0.8, 4),
                "priority": "medium",
            })

        if s["error_rate"] > 0.1 and s["total_runs"] >= 3:
            recommendations.append({
                "agent_type": s["agent_type"],
                "reason": f"Error rate {s['error_rate']:.1%} across {s['total_runs']} runs. Consider prompt tuning or model upgrade.",
                "priority": "high",
            })

    return recommendations
