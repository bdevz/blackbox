"""LangGraph orchestrator — runs the full proposal generation pipeline."""

import asyncio
import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.qualification import QualificationAgent
from app.agents.solution import SolutionAgent
from app.agents.compliance import ComplianceAgent
from app.agents.cost import CostAgent
from app.agents.review import ReviewAgent
from app.agents.reconcile import ReconcileAgent

logger = logging.getLogger(__name__)


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
    # Shared RAG context pre-fetched before the pipeline starts.
    # Keys are agent types ("qualify", "solution", "comply", "cost");
    # values are the dicts returned by rag_retriever.retrieve_for_agent().
    rag_context: dict


async def prefetch_rag_node(state: ProposalState) -> ProposalState:
    """Pre-fetch RAG context for all agents in parallel before the pipeline starts.

    Embeds the RFP brief once and runs Pinecone queries for qualify/solution/comply/cost
    concurrently. Stores results in rag_context so every downstream agent has pre-warmed
    context without making individual embedding calls.

    Failures are caught per-agent so a Pinecone outage never blocks proposal generation.
    """
    from app.services import rag_retriever

    rfp_brief = state.get("rfp_brief", {})
    query_text = json.dumps(rfp_brief)

    agent_types = ["qualify", "solution", "comply", "cost"]
    tasks = [rag_retriever.retrieve_for_agent(a, query_text) for a in agent_types]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    rag_context: dict = {}
    for agent_type, result in zip(agent_types, raw_results):
        if isinstance(result, Exception):
            logger.warning(f"RAG prefetch failed for '{agent_type}': {result}")
            rag_context[agent_type] = {}
        else:
            rag_context[agent_type] = result

    return {"rag_context": rag_context, "status": "rag_prefetched"}


async def qualify_node(state: ProposalState) -> ProposalState:
    proposal_id = state.get("proposal_id", "?")
    logger.info("[ORCHESTRATOR] qualify_node START — proposal=%s", proposal_id)
    agent = QualificationAgent()
    result = await agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "rag_context": state.get("rag_context", {}).get("qualify", {}),
        },
        proposal_id=state.get("proposal_id"),
    )
    update = {"qualification": result.output, "status": "qualified"}
    if not result.output.get("qualified", True):
        update["errors"] = result.output.get("missing", [])
        update["status"] = "disqualified"
        logger.warning("[ORCHESTRATOR] qualify_node DISQUALIFIED — missing=%s", result.output.get("missing"))
    else:
        logger.info("[ORCHESTRATOR] qualify_node DONE — qualified=True, score=%s",
                    result.output.get("score"))
    return update


async def solution_comply_node(state: ProposalState) -> ProposalState:
    proposal_id = state.get("proposal_id", "?")
    logger.info("[ORCHESTRATOR] solution_comply_node START — proposal=%s", proposal_id)

    # Run solution FIRST so compliance can see the staffing plan
    sol_agent = SolutionAgent()
    sol_result = await sol_agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "rag_context": state.get("rag_context", {}).get("solution", {}),
        },
        proposal_id=state.get("proposal_id"),
    )
    logger.info("[ORCHESTRATOR] solution DONE — approach_len=%d chars, staff_count=%s",
                len(sol_result.output.get("approach", "")),
                len(sol_result.output.get("staffing_plan", [])) if isinstance(sol_result.output.get("staffing_plan"), list) else "?")

    # Pass solution output to compliance so it mirrors the same staffing/team
    comp_agent = ComplianceAgent()
    comp_result = await comp_agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "solution": sol_result.output,
            "rag_context": state.get("rag_context", {}).get("comply", {}),
        },
        proposal_id=state.get("proposal_id"),
    )
    logger.info("[ORCHESTRATOR] compliance DONE — narrative_len=%d chars, compliant=%s",
                len(comp_result.output.get("narrative", "")),
                comp_result.output.get("compliant"))
    return {
        "solution": sol_result.output,
        "compliance": comp_result.output,
        "status": "solution_compliance",
    }


async def cost_node(state: ProposalState) -> ProposalState:
    proposal_id = state.get("proposal_id", "?")
    logger.info("[ORCHESTRATOR] cost_node START — proposal=%s", proposal_id)
    agent = CostAgent()
    result = await agent.run(
        {
            "rfp_id": state.get("rfp_id"),
            "rfp_brief": state["rfp_brief"],
            "solution": state["solution"],
            "rag_context": state.get("rag_context", {}).get("cost", {}),
        },
        proposal_id=state.get("proposal_id"),
    )
    logger.info("[ORCHESTRATOR] cost_node DONE — total=%s, narrative_len=%d chars",
                result.output.get("total_cost") or result.output.get("total"),
                len(result.output.get("narrative", "")))
    return {"cost": result.output, "status": "costing"}


async def review_node(state: ProposalState) -> ProposalState:
    proposal_id = state.get("proposal_id", "?")
    logger.info("[ORCHESTRATOR] review_node START — proposal=%s, revision_count=%s",
                proposal_id, state.get("revision_count", 0))
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
    logger.info("[ORCHESTRATOR] review_node DONE — recommendation=%s, quality_score=%s, contradictions=%d, violations=%d",
                result.output.get("recommendation"),
                result.output.get("quality_score"),
                len(result.output.get("contradictions", [])),
                len(result.output.get("playbook_violations", [])))
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
        logger.info("[ORCHESTRATOR] should_revise → END (recommendation=%s, revision_count=%d)",
                    recommendation, revision_count)
        return "end"
    logger.info("[ORCHESTRATOR] should_revise → REVISE (recommendation=%s, revision_count=%d)",
                recommendation, revision_count)
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
    logger.info("[ORCHESTRATOR] revision_node START — revision #%d, proposal=%s",
                revision_count, state.get("proposal_id", "?"))

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

    rag_context = state.get("rag_context", {})

    # Step 1: Re-run solution with ALL review feedback
    sol_agent = SolutionAgent()
    sol_result = await sol_agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "review_feedback": all_feedback,
            "rag_context": rag_context.get("solution", {}),
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
            "solution": sol_result.output,
            "review_feedback": all_feedback,
            "rag_context": rag_context.get("comply", {}),
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
            "solution": sol_result.output,
            "review_feedback": all_feedback,
            "rag_context": rag_context.get("cost", {}),
        },
        proposal_id=state.get("proposal_id"),
    )
    update["cost"] = cost_result.output
    logger.info("[ORCHESTRATOR] revision_node DONE — revision #%d complete", revision_count)

    return update


async def reconcile_node(state: ProposalState) -> ProposalState:
    """Single-pass reconciliation that reads ALL sections together and fixes inconsistencies.

    Runs ONCE after the final review (outside the revision loop).
    Uses solution as source of truth for scope/staffing, cost for numbers,
    and canonical citations for standards.
    """
    review = state.get("review", {})

    # Only reconcile if review found issues
    contradictions = review.get("contradictions", [])
    violations = review.get("playbook_violations", [])
    high_issues = [c for c in contradictions if c.get("severity") in ("high", "critical")]
    high_violations = [v for v in violations if v.get("severity") in ("high", "critical")]

    logger.info("[ORCHESTRATOR] reconcile_node START — high_issues=%d, high_violations=%d, proposal=%s",
                len(high_issues), len(high_violations), state.get("proposal_id", "?"))

    if not high_issues and not high_violations:
        logger.info("[ORCHESTRATOR] reconcile_node SKIPPED — no high/critical issues")
        return {"status": "reconciled"}  # Nothing to fix

    agent = ReconcileAgent()
    result = await agent.run(
        {
            "rfp_brief": state.get("rfp_brief", {}),
            "solution": state.get("solution", {}),
            "compliance": state.get("compliance", {}),
            "cost": state.get("cost", {}),
            "review": review,
        },
        proposal_id=state.get("proposal_id"),
    )

    output = result.output
    update: dict = {"status": "reconciled"}

    # Apply patches to solution
    sol_patches = output.get("solution_patches", {})
    if sol_patches:
        solution = dict(state.get("solution", {}))
        for field in ("approach", "staffing_plan", "timeline"):
            if sol_patches.get(field):
                solution[field] = sol_patches[field]
        update["solution"] = solution

    # Apply patches to compliance
    comp_patches = output.get("compliance_patches", {})
    if comp_patches and comp_patches.get("narrative"):
        compliance = dict(state.get("compliance", {}))
        compliance["narrative"] = comp_patches["narrative"]
        update["compliance"] = compliance

    # Apply patches to cost
    cost_patches = output.get("cost_patches", {})
    if cost_patches and cost_patches.get("narrative"):
        cost = dict(state.get("cost", {}))
        cost["narrative"] = cost_patches["narrative"]
        update["cost"] = cost

    logger.info("[ORCHESTRATOR] reconcile_node DONE — sol_patches=%s, comp_patches=%s, cost_patches=%s",
                bool(sol_patches), bool(comp_patches and comp_patches.get("narrative")),
                bool(cost_patches and cost_patches.get("narrative")))
    return update


def build_graph():
    graph = StateGraph(ProposalState)

    graph.add_node("prefetch_rag", prefetch_rag_node)
    graph.add_node("qualify", qualify_node)
    graph.add_node("solution_comply", solution_comply_node)
    graph.add_node("cost", cost_node)
    graph.add_node("review", review_node)
    graph.add_node("revision", revision_node)
    graph.add_node("reconcile", reconcile_node)

    # RAG prefetch runs first, then qualify
    graph.set_entry_point("prefetch_rag")
    graph.add_edge("prefetch_rag", "qualify")

    graph.add_conditional_edges(
        "qualify", should_continue,
        {"continue": "solution_comply", "end": END},
    )
    graph.add_edge("solution_comply", "cost")
    graph.add_edge("cost", "review")
    graph.add_conditional_edges(
        "review", should_revise,
        {"revise": "revision", "end": "reconcile"},
    )
    # Revision goes back to review (revision already re-runs cost internally)
    graph.add_edge("revision", "review")
    # Reconcile is the final step before END
    graph.add_edge("reconcile", END)

    return graph.compile()


proposal_graph = build_graph()
