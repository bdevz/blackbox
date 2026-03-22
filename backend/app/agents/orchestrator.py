"""LangGraph orchestrator — runs the full proposal generation pipeline."""

from typing import TypedDict

from langgraph.graph import StateGraph, END


class ProposalState(TypedDict, total=False):
    rfp_id: str
    rfp_brief: dict
    qualification: dict
    solution: dict
    compliance: dict
    cost: dict
    review: dict
    status: str
    errors: list


def qualify_node(state: ProposalState) -> ProposalState:
    # TODO: invoke QualificationAgent
    return {"qualification": {"qualified": True, "confidence": 0.0}, "status": "qualifying"}


def solution_node(state: ProposalState) -> ProposalState:
    # TODO: invoke SolutionAgent
    return {"solution": {"approach": "", "confidence": 0.0}, "status": "solution"}


def comply_node(state: ProposalState) -> ProposalState:
    # TODO: invoke ComplianceAgent
    return {"compliance": {"narrative": "", "confidence": 0.0}, "status": "compliance"}


def cost_node(state: ProposalState) -> ProposalState:
    # TODO: invoke CostAgent
    return {"cost": {"total": 0, "confidence": 0.0}, "status": "costing"}


def review_node(state: ProposalState) -> ProposalState:
    # TODO: invoke ReviewAgent
    return {"review": {"contradictions": [], "quality": "pending"}, "status": "review"}


def should_continue(state: ProposalState) -> str:
    qual = state.get("qualification", {})
    if not qual.get("qualified", True):
        return "end"
    return "continue"


def build_graph() -> StateGraph:
    graph = StateGraph(ProposalState)

    graph.add_node("qualify", qualify_node)
    graph.add_node("solution", solution_node)
    graph.add_node("comply", comply_node)
    graph.add_node("cost", cost_node)
    graph.add_node("review", review_node)

    graph.set_entry_point("qualify")

    graph.add_conditional_edges("qualify", should_continue, {"continue": "solution", "end": END})
    # Solution and Comply run after qualify — LangGraph handles them sequentially
    # To parallelize: use a fan-out node (future optimization)
    graph.add_edge("solution", "comply")
    graph.add_edge("comply", "cost")
    graph.add_edge("cost", "review")
    graph.add_edge("review", END)

    return graph.compile()


proposal_graph = build_graph()
