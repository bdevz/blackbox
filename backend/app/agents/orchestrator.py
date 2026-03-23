"""LangGraph orchestrator — runs the full proposal generation pipeline."""

import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.qualification import QualificationAgent
from app.agents.solution import SolutionAgent
from app.agents.compliance import ComplianceAgent
from app.agents.cost import CostAgent
from app.agents.review import ReviewAgent


class ProposalState(TypedDict, total=False):
    rfp_id: str
    rfp_brief: dict
    proposal_id: str
    qualification: dict
    solution: dict
    compliance: dict
    cost: dict
    review: dict
    status: str
    errors: list
    revision_count: int
    review_feedback: dict


async def qualify_node(state: ProposalState) -> ProposalState:
    agent = QualificationAgent()
    result = await agent.run(
        {"rfp_brief": state["rfp_brief"]},
        proposal_id=state.get("proposal_id"),
    )
    update = {"qualification": result.output, "status": "qualified"}
    if not result.output.get("qualified", True):
        update["errors"] = result.output.get("missing", [])
        update["status"] = "disqualified"
    return update


async def solution_comply_node(state: ProposalState) -> ProposalState:
    sol_agent = SolutionAgent()
    comp_agent = ComplianceAgent()
    sol_result, comp_result = await asyncio.gather(
        sol_agent.run(
            {"rfp_brief": state["rfp_brief"], "qualification": state["qualification"]},
            proposal_id=state.get("proposal_id"),
        ),
        comp_agent.run(
            {"rfp_brief": state["rfp_brief"], "qualification": state["qualification"]},
            proposal_id=state.get("proposal_id"),
        ),
    )
    return {
        "solution": sol_result.output,
        "compliance": comp_result.output,
        "status": "solution_compliance",
    }


async def cost_node(state: ProposalState) -> ProposalState:
    agent = CostAgent()
    result = await agent.run(
        {"rfp_brief": state["rfp_brief"], "solution": state["solution"]},
        proposal_id=state.get("proposal_id"),
    )
    return {"cost": result.output, "status": "costing"}


async def review_node(state: ProposalState) -> ProposalState:
    agent = ReviewAgent()
    result = await agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "solution": state["solution"],
            "compliance": state["compliance"],
            "cost": state["cost"],
        },
        proposal_id=state.get("proposal_id"),
    )
    return {"review": result.output, "status": "review"}


def should_continue(state: ProposalState) -> str:
    qual = state.get("qualification", {})
    if not qual.get("qualified", True):
        return "end"
    return "continue"


def should_revise(state: ProposalState) -> str:
    review = state.get("review", {})
    recommendation = review.get("recommendation", "ready")
    revision_count = state.get("revision_count", 0)

    if recommendation == "ready" or revision_count >= 2:
        return "end"
    return "revise"


def _extract_affected_sections(review: dict) -> set[str]:
    """Extract which sections have contradictions from review output."""
    affected = set()
    for contradiction in review.get("contradictions", []):
        for section in contradiction.get("sections", []):
            affected.add(section)
    return affected


def _build_review_feedback(review: dict, section: str) -> str:
    """Build feedback string for a specific section from review contradictions."""
    issues = []
    for c in review.get("contradictions", []):
        if section in c.get("sections", []):
            issues.append(f"[{c['severity'].upper()}] {c['issue']}")
    for m in review.get("missing_sections", []):
        issues.append(f"Missing: {m}")
    return "\n".join(issues) if issues else ""


async def revision_node(state: ProposalState) -> ProposalState:
    """Re-run affected agents with review feedback. Always re-run cost after solution changes."""
    review = state.get("review", {})
    affected = _extract_affected_sections(review)
    revision_count = state.get("revision_count", 0) + 1

    update: dict = {"revision_count": revision_count, "status": f"revision_{revision_count}"}

    tasks = []
    task_keys = []

    if "solution" in affected:
        sol_agent = SolutionAgent()
        feedback = _build_review_feedback(review, "solution")
        tasks.append(sol_agent.run(
            {
                "rfp_brief": state["rfp_brief"],
                "qualification": state["qualification"],
                "review_feedback": feedback,
            },
            proposal_id=state.get("proposal_id"),
        ))
        task_keys.append("solution")

    if "compliance" in affected:
        comp_agent = ComplianceAgent()
        feedback = _build_review_feedback(review, "compliance")
        tasks.append(comp_agent.run(
            {
                "rfp_brief": state["rfp_brief"],
                "qualification": state["qualification"],
                "review_feedback": feedback,
            },
            proposal_id=state.get("proposal_id"),
        ))
        task_keys.append("compliance")

    if tasks:
        results = await asyncio.gather(*tasks)
        for key, result in zip(task_keys, results):
            update[key] = result.output

    # Always re-run cost if solution was revised (staffing may have changed)
    if "solution" in affected or "cost" in affected:
        cost_agent = CostAgent()
        solution = update.get("solution", state.get("solution", {}))
        cost_feedback = _build_review_feedback(review, "cost")
        cost_result = await cost_agent.run(
            {
                "rfp_id": state.get("rfp_id"),
                "rfp_brief": state["rfp_brief"],
                "solution": solution,
                "review_feedback": cost_feedback,
            },
            proposal_id=state.get("proposal_id"),
        )
        update["cost"] = cost_result.output

    return update


def build_graph():
    graph = StateGraph(ProposalState)

    graph.add_node("qualify", qualify_node)
    graph.add_node("solution_comply", solution_comply_node)
    graph.add_node("cost", cost_node)
    graph.add_node("review", review_node)
    graph.add_node("revision", revision_node)

    graph.set_entry_point("qualify")

    graph.add_conditional_edges(
        "qualify", should_continue,
        {"continue": "solution_comply", "end": END},
    )
    graph.add_edge("solution_comply", "cost")
    graph.add_edge("cost", "review")
    graph.add_conditional_edges(
        "review", should_revise,
        {"revise": "revision", "end": END},
    )
    graph.add_edge("revision", "cost")

    return graph.compile()


proposal_graph = build_graph()
