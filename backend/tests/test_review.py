import json

import pytest

from app.agents.review import ReviewAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = ReviewAgent.__new__(ReviewAgent)

    def test_valid_output(self):
        raw = json.dumps({
            "contradictions": [
                {"sections": ["solution", "cost"], "issue": "Staffing count mismatch", "severity": "high"}
            ],
            "missing_sections": [],
            "formatting_issues": ["Inconsistent header levels"],
            "quality_score": 0.75,
            "recommendation": "needs_revision",
            "confidence": 0.85,
        })
        result = self.agent.validate_output(raw)
        assert len(result["contradictions"]) == 1
        assert result["recommendation"] == "needs_revision"

    def test_clean_review(self):
        raw = json.dumps({
            "contradictions": [],
            "missing_sections": [],
            "formatting_issues": [],
            "quality_score": 0.92,
            "recommendation": "ready",
            "confidence": 0.90,
        })
        result = self.agent.validate_output(raw)
        assert result["recommendation"] == "ready"

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_contradictions(self):
        raw = json.dumps({
            "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "ready", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="contradictions"):
            self.agent.validate_output(raw)

    def test_invalid_recommendation(self):
        raw = json.dumps({
            "contradictions": [], "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "maybe", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="recommendation"):
            self.agent.validate_output(raw)

    def test_invalid_severity(self):
        raw = json.dumps({
            "contradictions": [
                {"sections": ["a", "b"], "issue": "x", "severity": "catastrophic"}
            ],
            "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "ready", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="severity"):
            self.agent.validate_output(raw)

    def test_quality_score_out_of_range(self):
        raw = json.dumps({
            "contradictions": [], "missing_sections": [], "formatting_issues": [],
            "quality_score": 1.5, "recommendation": "ready", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="quality_score"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "contradictions": [], "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "ready", "confidence": -0.1,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)


class TestBuildPrompt:
    def setup_method(self):
        self.agent = ReviewAgent.__new__(ReviewAgent)

    def test_returns_tuple_of_strings(
        self, sample_rfp_brief, sample_qualification_output,
        sample_solution_output, sample_compliance_output, sample_cost_output,
    ):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
        }
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(
        self, sample_rfp_brief, sample_qualification_output,
        sample_solution_output, sample_compliance_output, sample_cost_output,
    ):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
        }
        system, _ = self.agent.build_prompt(context)
        assert "review" in system.lower() or "QA" in system

    def test_user_prompt_includes_all_sections(
        self, sample_rfp_brief, sample_qualification_output,
        sample_solution_output, sample_compliance_output, sample_cost_output,
    ):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
        }
        _, user = self.agent.build_prompt(context)
        assert "Qualification" in user
        assert "Solution" in user
        assert "Compliance" in user
        assert "Cost" in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert ReviewAgent.agent_type == "review"

    def test_model(self):
                assert ReviewAgent.model == "claude-opus-4-6"

    def test_temperature(self):
        assert ReviewAgent.temperature == 0.1
