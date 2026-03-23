import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from app.integrations.highergov import (
    NAICS_CODES,
    HigherGovClient,
    passes_tier2_filter,
    score_relevance_prompt,
)


class TestNAICSCodes:
    def test_contains_core_it_codes(self):
        codes = [c["code"] for c in NAICS_CODES]
        assert "541512" in codes  # Computer Systems Design
        assert "541511" in codes  # Custom Computer Programming
        assert "541519" in codes  # Other Computer Related Services

    def test_each_code_has_label(self):
        for entry in NAICS_CODES:
            assert "code" in entry
            assert "label" in entry
            assert len(entry["code"]) == 6


class TestTier2Filter:
    def _make_opp(self, **overrides):
        base = {
            "opp_key": "abc123",
            "title": "IT Managed Services",
            "description_text": "Need IT services",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d"),
            "val_est_low": "100000",
            "val_est_high": "500000",
            "sole_source_flag": False,
            "product_service": "S",
            "source_type": "sled",
            "ai_summary": None,
            "agency": {"agency_type": "SLED"},
        }
        base.update(overrides)
        return base

    def test_valid_opportunity_passes(self):
        assert passes_tier2_filter(self._make_opp(), set()) is True

    def test_expired_due_date_rejected(self):
        opp = self._make_opp(due_date="2020-01-01")
        assert passes_tier2_filter(opp, set()) is False

    def test_due_in_12_hours_rejected(self):
        """Less than 24h — can't start at 3 PM IST and hit a US ET deadline."""
        soon = (datetime.now(timezone.utc) + timedelta(hours=12)).strftime("%Y-%m-%d")
        opp = self._make_opp(due_date=soon)
        assert passes_tier2_filter(opp, set()) is False

    def test_due_in_2_days_passes(self):
        """2 days out is tight but workable."""
        two_days = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
        opp = self._make_opp(due_date=two_days)
        assert passes_tier2_filter(opp, set()) is True

    def test_due_date_too_far_out_rejected(self):
        """RFPs due more than 15 days out are not urgent enough."""
        far_out = (datetime.now(timezone.utc) + timedelta(days=45)).strftime("%Y-%m-%d")
        opp = self._make_opp(due_date=far_out)
        assert passes_tier2_filter(opp, set()) is False

    def test_due_date_within_window_passes(self):
        """RFPs due in 10 days should pass."""
        in_window = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
        opp = self._make_opp(due_date=in_window)
        assert passes_tier2_filter(opp, set()) is True

    def test_too_expensive_rejected(self):
        opp = self._make_opp(val_est_low="3000000")
        assert passes_tier2_filter(opp, set()) is False

    def test_sole_source_rejected(self):
        opp = self._make_opp(sole_source_flag=True)
        assert passes_tier2_filter(opp, set()) is False

    def test_duplicate_rejected(self):
        opp = self._make_opp(opp_key="dup123")
        assert passes_tier2_filter(opp, {"dup123"}) is False

    def test_no_description_rejected(self):
        opp = self._make_opp(description_text="", ai_summary=None)
        assert passes_tier2_filter(opp, set()) is False

    def test_ai_summary_substitutes_for_description(self):
        opp = self._make_opp(description_text="", ai_summary="IT managed services RFP")
        assert passes_tier2_filter(opp, set()) is True

    def test_none_due_date_passes(self):
        """Opportunities without a due date should not be filtered out."""
        opp = self._make_opp(due_date=None)
        assert passes_tier2_filter(opp, set()) is True

    def test_none_value_passes(self):
        """Opportunities without estimated value should not be filtered out."""
        opp = self._make_opp(val_est_low=None, val_est_high=None)
        assert passes_tier2_filter(opp, set()) is True

    def test_product_not_service_rejected(self):
        opp = self._make_opp(product_service="P")
        assert passes_tier2_filter(opp, set()) is False


class TestScoreRelevancePrompt:
    def test_prompt_contains_company_context(self):
        opp = {
            "title": "Cloud Migration Services",
            "description_text": "Need AWS cloud migration",
            "ai_summary": None,
            "naics_code": {"naics_code": "541512"},
            "agency": {"agency_name": "Ohio DAS", "agency_type": "SLED"},
            "pop_state": "OH",
            "val_est_low": "200000",
            "val_est_high": "400000",
        }
        system, user = score_relevance_prompt(opp)
        assert "ConsultAdd" in system
        assert "Cloud Migration" in user
        assert "541512" in user

    def test_prompt_asks_for_json(self):
        opp = {
            "title": "Test",
            "description_text": "Test desc",
            "ai_summary": None,
            "naics_code": {"naics_code": "541512"},
            "agency": {"agency_name": "Test Agency", "agency_type": "SLED"},
            "pop_state": "TX",
            "val_est_low": None,
            "val_est_high": None,
        }
        system, _ = score_relevance_prompt(opp)
        assert "service_fit" in system
        assert "size_fit" in system
        assert "capability_fit" in system


class TestHigherGovClient:
    def test_client_initializes_with_config(self):
        client = HigherGovClient(api_key="test-key")
        assert client.api_key == "test-key"

    @pytest.mark.asyncio
    async def test_fetch_page_calls_api(self):
        client = HigherGovClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{"title": "Test RFP"}],
            "meta": {"pagination": {"pages": 1, "count": 1}},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("app.integrations.highergov.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            results, total_pages = await client.fetch_page("541512", "2026-03-20", page=1)

        assert len(results) == 1
        assert results[0]["title"] == "Test RFP"
        assert total_pages == 1
