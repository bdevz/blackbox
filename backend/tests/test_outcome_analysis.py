import pytest
from unittest.mock import MagicMock

from app.analytics.outcome_analysis import get_win_analysis


class TestGetWinAnalysis:
    def test_returns_structure(self):
        mock_db = MagicMock()
        # Mock by_category query
        mock_db.query.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = []
        # Mock overall query
        mock_overall = MagicMock()
        mock_overall.total = 0
        mock_overall.won = 0
        mock_overall.lost = 0
        mock_db.query.return_value.filter.return_value.first.return_value = mock_overall

        result = get_win_analysis(mock_db)
        assert "overall" in result
        assert "by_category" in result
        assert "by_state" in result
        assert result["overall"]["total"] == 0
        assert result["overall"]["win_rate"] == 0
