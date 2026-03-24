import json

import pytest

from app.agents.qualification import QualificationAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = QualificationAgent.__new__(QualificationAgent)

    def test_valid_output(self, sample_qualification_output):
        raw = json.dumps(sample_qualification_output)
        result = self.agent.validate_output(raw)
        assert result["qualified"] is True
        assert result["confidence"] == 0.85
        assert result["recommendation"] == "go"
        assert len(result["reasons"]) == 3
        assert isinstance(result["missing"], list)

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_qualified_field(self):
        raw = json.dumps({"confidence": 0.5, "reasons": [], "missing": [], "recommendation": "go"})
        with pytest.raises(ValueError, match="qualified"):
            self.agent.validate_output(raw)

    def test_missing_recommendation_field(self):
        raw = json.dumps({"qualified": True, "confidence": 0.5, "reasons": [], "missing": []})
        with pytest.raises(ValueError, match="recommendation"):
            self.agent.validate_output(raw)

    def test_invalid_recommendation_value(self):
        raw = json.dumps({
            "qualified": True, "confidence": 0.5, "reasons": [], "missing": [],
            "recommendation": "maybe",
        })
        with pytest.raises(ValueError, match="recommendation"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "qualified": True, "confidence": 1.5, "reasons": [], "missing": [],
            "recommendation": "go",
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)

    def test_nogo_output(self):
        raw = json.dumps({
            "qualified": False, "confidence": 0.9, "reasons": ["Missing certs"],
            "missing": ["SOC 2 Type II"], "recommendation": "no-go",
        })
        result = self.agent.validate_output(raw)
        assert result["qualified"] is False
        assert result["missing"] == ["SOC 2 Type II"]


class TestBuildPrompt:
    def setup_method(self):
        self.agent = QualificationAgent.__new__(QualificationAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief):
        context = {"rfp_brief": sample_rfp_brief}
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief):
        context = {"rfp_brief": sample_rfp_brief}
        system, _ = self.agent.build_prompt(context)
        assert "qualification" in system.lower()
        assert "ConsultAdd" in system

    def test_user_prompt_includes_rfp_brief(self, sample_rfp_brief):
        context = {"rfp_brief": sample_rfp_brief}
        _, user = self.agent.build_prompt(context)
        assert sample_rfp_brief["title"] in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert QualificationAgent.agent_type == "qualify"

    def test_model(self):
                assert QualificationAgent.model == "claude-opus-4-6"

    def test_temperature(self):
        assert QualificationAgent.temperature == 0.1
