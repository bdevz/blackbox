"""Orchestrator structure tests — no LLM calls, verifies graph wiring."""

from app.agents.orchestrator import ProposalState, proposal_graph, should_continue


class TestShouldContinue:
    def test_qualified_continues(self):
        state = {"qualification": {"qualified": True}}
        assert should_continue(state) == "continue"

    def test_not_qualified_ends(self):
        state = {"qualification": {"qualified": False}}
        assert should_continue(state) == "end"

    def test_missing_qualification_continues(self):
        state = {}
        assert should_continue(state) == "continue"

    def test_conditional_continues(self):
        state = {"qualification": {"qualified": True, "recommendation": "conditional"}}
        assert should_continue(state) == "continue"


class TestProposalState:
    def test_has_proposal_id_field(self):
        state: ProposalState = {"proposal_id": "test-123"}
        assert state["proposal_id"] == "test-123"

    def test_has_errors_field(self):
        state: ProposalState = {"errors": ["missing cert"]}
        assert state["errors"] == ["missing cert"]


class TestGraphStructure:
    def test_graph_compiles(self):
        assert proposal_graph is not None

    def test_graph_has_expected_nodes(self):
        node_names = set(proposal_graph.get_graph().nodes.keys())
        expected = {"__start__", "__end__", "qualify", "solution_comply", "cost", "review"}
        assert expected.issubset(node_names)
