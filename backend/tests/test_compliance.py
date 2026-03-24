import json

import pytest

from app.agents.compliance import ComplianceAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = ComplianceAgent.__new__(ComplianceAgent)

    def test_valid_output(self, sample_compliance_output):
        raw = json.dumps(sample_compliance_output)
        result = self.agent.validate_output(raw)
        assert "narrative" in result
        assert len(result["forms_checklist"]) == 4
        assert result["forms_checklist"][0]["status"] in ("have", "need", "na")

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_narrative(self):
        raw = json.dumps({
            "forms_checklist": [], "certifications_cited": [],
            "flags": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="narrative"):
            self.agent.validate_output(raw)

    def test_invalid_form_status(self):
        raw = json.dumps({
            "narrative": "x",
            "forms_checklist": [{"form": "W-9", "status": "maybe"}],
            "certifications_cited": [], "flags": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="status"):
            self.agent.validate_output(raw)

    def test_missing_forms_checklist(self):
        raw = json.dumps({
            "narrative": "x", "certifications_cited": [],
            "flags": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="forms_checklist"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "narrative": "x", "forms_checklist": [],
            "certifications_cited": [], "flags": [], "confidence": 2.0,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)


class TestBuildPrompt:
    def setup_method(self):
        self.agent = ComplianceAgent.__new__(ComplianceAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        system, _ = self.agent.build_prompt(context)
        assert "compliance" in system.lower()
        assert "ConsultAdd" in system

    def test_user_prompt_includes_rfp(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        _, user = self.agent.build_prompt(context)
        assert sample_rfp_brief["title"] in user


class TestReviewFeedbackInPrompt:
    def setup_method(self):
        self.agent = ComplianceAgent.__new__(ComplianceAgent)

    def test_review_feedback_included_in_user_prompt(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "certifications": [],
            "boilerplate": [],
            "review_feedback": "[MEDIUM] Claims CMMI Level 5, only have Level 3",
        }
        _, user = self.agent.build_prompt(context)
        assert "CMMI Level 5" in user

    def test_no_review_feedback_no_section(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "certifications": [],
            "boilerplate": [],
        }
        _, user = self.agent.build_prompt(context)
        assert "QA reviewer found" not in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert ComplianceAgent.agent_type == "comply"

    def test_model(self):
        assert ComplianceAgent.model == "claude-sonnet-4-6"

    def test_temperature(self):
        assert ComplianceAgent.temperature == 0.2

    def test_max_tokens(self):
        assert ComplianceAgent.max_tokens == 8192
