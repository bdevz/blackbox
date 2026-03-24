import json

import pytest

from app.agents.solution import SolutionAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = SolutionAgent.__new__(SolutionAgent)

    def test_valid_output(self, sample_solution_output):
        raw = json.dumps(sample_solution_output)
        result = self.agent.validate_output(raw)
        assert "approach" in result
        assert isinstance(result["staffing"], list)
        assert len(result["staffing"]) == 5
        assert result["staffing"][0]["role"] == "Project Manager"

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_approach(self):
        raw = json.dumps({
            "staffing_plan": "x", "staffing": [], "timeline": "x",
            "technology_stack": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="approach"):
            self.agent.validate_output(raw)

    def test_missing_staffing_array(self):
        raw = json.dumps({
            "approach": "x", "staffing_plan": "x", "timeline": "x",
            "technology_stack": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="staffing"):
            self.agent.validate_output(raw)

    def test_staffing_entry_missing_role(self):
        raw = json.dumps({
            "approach": "x", "staffing_plan": "x",
            "staffing": [{"hours": 100, "headcount": 1}],
            "timeline": "x", "technology_stack": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="role"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "approach": "x", "staffing_plan": "x", "staffing": [],
            "timeline": "x", "technology_stack": [], "confidence": -0.1,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)


class TestBuildPrompt:
    def setup_method(self):
        self.agent = SolutionAgent.__new__(SolutionAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
        }
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        system, _ = self.agent.build_prompt(context)
        assert "technical" in system.lower()
        assert "ConsultAdd" in system

    def test_user_prompt_includes_rfp_and_qualification(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        _, user = self.agent.build_prompt(context)
        assert sample_rfp_brief["title"] in user


class TestReviewFeedbackInPrompt:
    def setup_method(self):
        self.agent = SolutionAgent.__new__(SolutionAgent)

    def test_review_feedback_included_in_user_prompt(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "company_knowledge": [],
            "similar_proposals": [],
            "review_feedback": "[HIGH] Staffing count mismatch",
        }
        _, user = self.agent.build_prompt(context)
        assert "Staffing count mismatch" in user

    def test_no_review_feedback_no_section(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "company_knowledge": [],
            "similar_proposals": [],
        }
        _, user = self.agent.build_prompt(context)
        assert "QA reviewer found" not in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert SolutionAgent.agent_type == "solution"

    def test_model(self):
        assert SolutionAgent.model == "claude-opus-4-6"

    def test_temperature(self):
        assert SolutionAgent.temperature == 0.4

    def test_max_tokens(self):
        assert SolutionAgent.max_tokens == 16000
