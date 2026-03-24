import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.orchestrator import ProposalState, should_revise, revision_node


class TestShouldRevise:
    def test_ready_goes_to_end(self):
        state = {"review": {"recommendation": "ready"}, "revision_count": 0}
        assert should_revise(state) == "end"

    def test_needs_revision_routes_to_revise(self):
        state = {"review": {"recommendation": "needs_revision"}, "revision_count": 0}
        assert should_revise(state) == "revise"

    def test_major_issues_routes_to_revise(self):
        state = {"review": {"recommendation": "major_issues"}, "revision_count": 0}
        assert should_revise(state) == "revise"

    def test_max_revisions_goes_to_end(self):
        state = {"review": {"recommendation": "needs_revision"}, "revision_count": 2}
        assert should_revise(state) == "end"

    def test_revision_count_1_allows_one_more(self):
        state = {"review": {"recommendation": "needs_revision"}, "revision_count": 1}
        assert should_revise(state) == "revise"

    def test_missing_review_goes_to_end(self):
        state = {"revision_count": 0}
        assert should_revise(state) == "end"


class TestProposalStateRevisionFields:
    def test_has_revision_count(self):
        state: ProposalState = {"revision_count": 1}
        assert state["revision_count"] == 1

    def test_has_review_feedback(self):
        state: ProposalState = {"review_feedback": {"solution": "fix staffing"}}
        assert "solution" in state["review_feedback"]


class TestRevisionNode:
    @pytest.mark.asyncio
    async def test_extracts_feedback_for_affected_sections(
        self, sample_rfp_brief, sample_qualification_output, sample_solution_output,
        sample_compliance_output, sample_cost_output, sample_review_output_needs_revision,
    ):
        state = {
            "rfp_brief": sample_rfp_brief,
            "rfp_id": "test-rfp-id",
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
            "review": sample_review_output_needs_revision,
            "revision_count": 0,
        }

        mock_result = MagicMock()
        mock_result.output = sample_solution_output

        with patch("app.agents.orchestrator.SolutionAgent") as MockSol, \
             patch("app.agents.orchestrator.ComplianceAgent") as MockComp, \
             patch("app.agents.orchestrator.CostAgent") as MockCost:
            MockSol.return_value.run = AsyncMock(return_value=mock_result)
            mock_comp_result = MagicMock()
            mock_comp_result.output = sample_compliance_output
            MockComp.return_value.run = AsyncMock(return_value=mock_comp_result)
            mock_cost_result = MagicMock()
            mock_cost_result.output = sample_cost_output
            MockCost.return_value.run = AsyncMock(return_value=mock_cost_result)

            result = await revision_node(state)

        assert result["revision_count"] == 1
        assert "solution" in result
        assert "cost" in result

    @pytest.mark.asyncio
    async def test_increments_revision_count(
        self, sample_rfp_brief, sample_qualification_output, sample_solution_output,
        sample_compliance_output, sample_cost_output, sample_review_output_needs_revision,
    ):
        state = {
            "rfp_brief": sample_rfp_brief,
            "rfp_id": "test-rfp-id",
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
            "review": sample_review_output_needs_revision,
            "revision_count": 1,
        }

        mock_result = MagicMock()
        mock_result.output = sample_solution_output

        with patch("app.agents.orchestrator.SolutionAgent") as MockSol, \
             patch("app.agents.orchestrator.ComplianceAgent") as MockComp, \
             patch("app.agents.orchestrator.CostAgent") as MockCost:
            MockSol.return_value.run = AsyncMock(return_value=mock_result)
            mock_comp_result = MagicMock()
            mock_comp_result.output = sample_compliance_output
            MockComp.return_value.run = AsyncMock(return_value=mock_comp_result)
            mock_cost_result = MagicMock()
            mock_cost_result.output = sample_cost_output
            MockCost.return_value.run = AsyncMock(return_value=mock_cost_result)

            result = await revision_node(state)

        assert result["revision_count"] == 2
