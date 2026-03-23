import pytest
from unittest.mock import MagicMock

from app.analytics.agent_analytics import (
    get_agent_detailed_stats,
    get_proposal_cost_breakdown,
    get_optimization_recommendations,
    MODEL_COSTS,
)


class TestModelCosts:
    def test_has_all_agent_types(self):
        assert "qualify" in MODEL_COSTS
        assert "solution" in MODEL_COSTS
        assert "comply" in MODEL_COSTS
        assert "cost" in MODEL_COSTS
        assert "review" in MODEL_COSTS

    def test_opus_costs_more_than_haiku(self):
        assert MODEL_COSTS["solution"]["output"] > MODEL_COSTS["qualify"]["output"]


class TestGetAgentDetailedStats:
    def test_returns_list(self):
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.agent_type = "qualify"
        mock_row.total_runs = 10
        mock_row.avg_duration_ms = 500.0
        mock_row.avg_input_tokens = 100.0
        mock_row.avg_output_tokens = 200.0
        mock_row.total_input_tokens = 1000
        mock_row.total_output_tokens = 2000
        mock_row.error_count = 1
        mock_db.query.return_value.group_by.return_value.all.return_value = [mock_row]

        result = get_agent_detailed_stats(mock_db)
        assert len(result) == 1
        assert result[0]["agent_type"] == "qualify"
        assert result[0]["total_runs"] == 10
        assert result[0]["error_rate"] == 0.1


class TestGetProposalCostBreakdown:
    def test_returns_breakdown(self):
        mock_db = MagicMock()
        mock_run = MagicMock()
        mock_run.agent_type = "qualify"
        mock_run.model_used = "claude-haiku-4-5-20251001"
        mock_run.duration_ms = 500
        mock_run.input_tokens = 100
        mock_run.output_tokens = 200
        mock_run.status = "ok"
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_run]

        result = get_proposal_cost_breakdown(mock_db, "test-id")
        assert result["proposal_id"] == "test-id"
        assert len(result["runs"]) == 1
        assert result["total_cost_usd"] > 0


class TestGetOptimizationRecommendations:
    def test_recommends_downgrade_for_zero_error_opus(self):
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.agent_type = "solution"
        mock_row.total_runs = 10
        mock_row.avg_duration_ms = 5000.0
        mock_row.avg_input_tokens = 500.0
        mock_row.avg_output_tokens = 2000.0
        mock_row.total_input_tokens = 5000
        mock_row.total_output_tokens = 20000
        mock_row.error_count = 0
        mock_db.query.return_value.group_by.return_value.all.return_value = [mock_row]

        result = get_optimization_recommendations(mock_db)
        assert len(result) >= 1
        assert result[0]["agent_type"] == "solution"
        assert result[0]["suggested_model"] == "claude-sonnet-4-6"
