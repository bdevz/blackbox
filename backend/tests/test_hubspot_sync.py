import pytest
from unittest.mock import patch, MagicMock

from app.integrations.hubspot_sync import sync_outcomes, STAGE_OUTCOME_MAP


class TestStageOutcomeMap:
    def test_closedwon_maps_to_won(self):
        assert STAGE_OUTCOME_MAP["closedwon"] == "won"

    def test_closedlost_maps_to_lost(self):
        assert STAGE_OUTCOME_MAP["closedlost"] == "lost"

    def test_contractsent_maps_to_interview(self):
        assert STAGE_OUTCOME_MAP["contractsent"] == "interview"


class TestSyncOutcomes:
    @patch("app.integrations.hubspot_sync.settings")
    def test_skips_when_no_api_key(self, mock_settings):
        mock_settings.hubspot_api_key = ""
        result = sync_outcomes()
        assert result["synced"] == 0
        assert "No API key" in result.get("message", "")

    @patch("app.integrations.hubspot_sync._fetch_deals")
    @patch("app.integrations.hubspot_sync.SessionLocal")
    @patch("app.integrations.hubspot_sync.settings")
    def test_syncs_won_deal(self, mock_settings, mock_session_cls, mock_fetch):
        mock_settings.hubspot_api_key = "test-key"

        mock_fetch.return_value = [
            {"id": "deal-123", "properties": {"dealstage": "closedwon"}},
        ]

        mock_rfp = MagicMock()
        mock_rfp.id = "rfp-uuid"
        mock_proposal = MagicMock()
        mock_proposal.outcome = "pending"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_rfp
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_proposal
        mock_session_cls.return_value = mock_db

        result = sync_outcomes()
        assert result["synced"] == 1
        assert result["won"] == 1
        assert mock_proposal.outcome == "won"

    @patch("app.integrations.hubspot_sync._fetch_deals")
    @patch("app.integrations.hubspot_sync.SessionLocal")
    @patch("app.integrations.hubspot_sync.settings")
    def test_skips_deal_without_rfp(self, mock_settings, mock_session_cls, mock_fetch):
        mock_settings.hubspot_api_key = "test-key"

        mock_fetch.return_value = [
            {"id": "deal-999", "properties": {"dealstage": "closedwon"}},
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_session_cls.return_value = mock_db

        result = sync_outcomes()
        assert result["skipped"] >= 1
        assert result["synced"] == 0

    @patch("app.integrations.hubspot_sync._fetch_deals")
    @patch("app.integrations.hubspot_sync.SessionLocal")
    @patch("app.integrations.hubspot_sync.settings")
    def test_skips_already_synced(self, mock_settings, mock_session_cls, mock_fetch):
        mock_settings.hubspot_api_key = "test-key"

        mock_fetch.return_value = [
            {"id": "deal-123", "properties": {"dealstage": "closedwon"}},
        ]

        mock_rfp = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.outcome = "won"  # Already synced

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_rfp
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_proposal
        mock_session_cls.return_value = mock_db

        result = sync_outcomes()
        assert result["skipped"] >= 1
        assert result["synced"] == 0
