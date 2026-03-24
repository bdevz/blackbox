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
    # Run solution FIRST so compliance can see the staffing plan
    sol_agent = SolutionAgent()
    sol_result = await sol_agent.run(
        {"rfp_brief": state["rfp_brief"], "qualification": state["qualification"]},
        proposal_id=state.get("proposal_id"),
    )

    # Pass solution output to compliance so it mirrors the same staffing/team
    comp_agent = ComplianceAgent()
    comp_result = await comp_agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "solution": sol_result.output,  # Compliance sees the solution
        },
        proposal_id=state.get("proposal_id"),
    )
    return {
        "solution": sol_result.output,
        "compliance": comp_result.output,
        "status": "solution_compliance",
    }


async def cost_node(state: ProposalState) -> ProposalState:
    agent = CostAgent()
    result = await agent.run(
        {
            "rfp_id": state.get("rfp_id"),
            "rfp_brief": state["rfp_brief"],
            "solution": state["solution"],
        },
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
    """Re-run all content agents with full review feedback for cross-section consistency.

    Key insight from proposal analysis: contradictions arise from agents not seeing
    each other's output. The revision node re-runs solution first, then passes the
    revised solution to compliance, then re-runs cost with the revised solution.
    This ensures cross-section consistency.
    """
    review = state.get("review", {})
    revision_count = state.get("revision_count", 0) + 1

    # Build comprehensive feedback from ALL review findings
    all_feedback_parts = []
    for c in review.get("contradictions", []):
        all_feedback_parts.append(f"[{c['severity'].upper()}] {c['issue']}")
    for m in review.get("missing_sections", []):
        all_feedback_parts.append(f"[MISSING] {m}")
    for v in review.get("playbook_violations", []):
        sev = v.get("severity", "medium").upper()
        all_feedback_parts.append(f"[{sev}] {v.get('pattern', '')}: {v.get('violation', '')} — FIX: {v.get('fix', '')}")
    for f in review.get("formatting_issues", []):
        all_feedback_parts.append(f"[FORMAT] {f}")
    all_feedback = "\n".join(all_feedback_parts)

    update: dict = {"revision_count": revision_count, "status": f"revision_{revision_count}"}

    # Step 1: Re-run solution with ALL review feedback
    sol_agent = SolutionAgent()
    sol_result = await sol_agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "review_feedback": all_feedback,
        },
        proposal_id=state.get("proposal_id"),
    )
    update["solution"] = sol_result.output

    # Step 2: Re-run compliance with revised solution + review feedback
    comp_agent = ComplianceAgent()
    comp_result = await comp_agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "solution": sol_result.output,  # Pass revised solution for consistency
            "review_feedback": all_feedback,
        },
        proposal_id=state.get("proposal_id"),
    )
    update["compliance"] = comp_result.output

    # Step 3: Re-run cost with revised solution
    cost_agent = CostAgent()
    cost_result = await cost_agent.run(
        {
            "rfp_id": state.get("rfp_id"),
            "rfp_brief": state["rfp_brief"],
            "solution": sol_result.output,  # Use revised solution staffing
            "review_feedback": all_feedback,
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
