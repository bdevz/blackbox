import pytest
from unittest.mock import patch, MagicMock

from app.integrations.embedding_pipeline import embed_winning_proposals


class TestEmbedWinningProposals:
    @patch("app.integrations.embedding_pipeline.settings")
    def test_skips_when_no_api_key(self, mock_settings):
        mock_settings.voyage_api_key = ""
        result = embed_winning_proposals()
        assert result["embedded"] == 0
        assert "No API key" in result.get("message", "")

    @patch("app.integrations.embedding_pipeline.SessionLocal")
    @patch("app.integrations.embedding_pipeline.settings")
    def test_skips_when_no_proposals(self, mock_settings, mock_session_cls):
        mock_settings.voyage_api_key = "test-key"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.distinct.return_value.subquery.return_value = MagicMock()
        mock_session_cls.return_value = mock_db

        result = embed_winning_proposals()
        assert result["embedded"] == 0
