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


def build_graph():
    graph = StateGraph(ProposalState)

    graph.add_node("qualify", qualify_node)
    graph.add_node("solution_comply", solution_comply_node)
    graph.add_node("cost", cost_node)
    graph.add_node("review", review_node)

    graph.set_entry_point("qualify")

    graph.add_conditional_edges(
        "qualify", should_continue,
        {"continue": "solution_comply", "end": END},
    )
    graph.add_edge("solution_comply", "cost")
    graph.add_edge("cost", "review")
    graph.add_edge("review", END)

    return graph.compile()


proposal_graph = build_graph()
