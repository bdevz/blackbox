import json

import pytest

from app.agents.cost import CostAgent


class TestCalculateCosts:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_basic_calculation(self, sample_solution_output, sample_company_knowledge):
        rate_card = next(
            k["value"] for k in sample_company_knowledge if k["type"] == "ratecard"
        )
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card["rates"],
        )
        assert result["labor_costs"]["subtotal"] == 441600.0
        pm = result["labor_costs"]["roles"][0]
        assert pm["title"] == "Project Manager"
        assert pm["rate"] == 95.0
        assert pm["hours"] == 960
        assert pm["total"] == 91200.0
        assert result["missing_rates"] == []

    def test_missing_role_in_rate_card(self):
        result = CostAgent.__new__(CostAgent).calculate_costs(
            staffing=[{"role": "Data Scientist", "hours": 500, "headcount": 1}],
            rate_card={"Developer": {"hourly": 55}},
        )
        assert "Data Scientist" in result["missing_rates"]
        ds_role = result["labor_costs"]["roles"][0]
        assert ds_role["rate"] == 0
        assert ds_role["total"] == 0

    def test_empty_staffing(self):
        result = CostAgent.__new__(CostAgent).calculate_costs(
            staffing=[],
            rate_card={"Developer": {"hourly": 55}},
        )
        assert result["labor_costs"]["subtotal"] == 0
        assert result["labor_costs"]["roles"] == []

    def test_margin_applied(self, sample_solution_output, sample_company_knowledge):
        rate_card = next(
            k["value"] for k in sample_company_knowledge if k["type"] == "ratecard"
        )
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card["rates"],
            margin=0.15,
        )
        expected_with_margin = 441600.0 * 1.15
        assert abs(result["total_with_margin"] - expected_with_margin) < 0.01


class TestValidateOutput:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_valid_output(self, sample_cost_output):
        raw = json.dumps(sample_cost_output)
        result = self.agent.validate_output(raw)
        assert result["total"] == 489600.0
        assert len(result["labor_costs"]["roles"]) == 5

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_labor_costs(self):
        raw = json.dumps({
            "other_costs": [], "total": 0, "narrative": "x", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="labor_costs"):
            self.agent.validate_output(raw)

    def test_missing_total(self):
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [], "narrative": "x", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="total"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [], "total": 0, "narrative": "x", "confidence": 1.5,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)

    def test_rejects_divergent_subtotal(self):
        agent = CostAgent.__new__(CostAgent)
        agent._computed_costs = {"labor_costs": {"subtotal": 100000.0}}
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 200000.0},
            "other_costs": [], "total": 200000.0, "narrative": "x", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="diverges"):
            agent.validate_output(raw)

    def test_accepts_matching_subtotal(self):
        agent = CostAgent.__new__(CostAgent)
        agent._computed_costs = {"labor_costs": {"subtotal": 441600.0}}
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 441600.0},
            "other_costs": [], "total": 489600.0, "narrative": "x", "confidence": 0.5,
        })
        result = agent.validate_output(raw)
        assert result["labor_costs"]["subtotal"] == 441600.0


class TestBuildPrompt:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief, sample_solution_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "solution": sample_solution_output,
            "computed_costs": {
                "labor_costs": {"roles": [], "subtotal": 0},
                "missing_rates": [],
                "total_with_margin": 0,
            },
        }
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief, sample_solution_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "solution": sample_solution_output,
            "computed_costs": {"labor_costs": {"roles": [], "subtotal": 0}, "missing_rates": [], "total_with_margin": 0},
        }
        system, _ = self.agent.build_prompt(context)
        assert "cost" in system.lower()
        assert "ConsultAdd" in system


class TestReviewFeedbackInPrompt:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_review_feedback_included_in_user_prompt(self, sample_rfp_brief, sample_solution_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "solution": sample_solution_output,
            "computed_costs": {"labor_costs": {"roles": [], "subtotal": 0}, "missing_rates": [], "total_with_margin": 0},
            "review_feedback": "[HIGH] Costs exceed budget by 40%",
        }
        _, user = self.agent.build_prompt(context)
        assert "Costs exceed budget" in user

    def test_no_review_feedback_no_section(self, sample_rfp_brief, sample_solution_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "solution": sample_solution_output,
            "computed_costs": {"labor_costs": {"roles": [], "subtotal": 0}, "missing_rates": [], "total_with_margin": 0},
        }
        _, user = self.agent.build_prompt(context)
        assert "QA reviewer found" not in user


class TestPriceToWin:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_flags_over_budget(self, sample_solution_output):
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
            estimated_value=200000.0,
        )
        assert result["over_budget"] is True
        assert "value_engineered" in result

    def test_not_over_budget_when_within_threshold(self, sample_solution_output):
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
            estimated_value=5000000.0,
        )
        assert result.get("over_budget", False) is False

    def test_no_estimated_value_skips_price_to_win(self, sample_solution_output):
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
        )
        assert result.get("over_budget", False) is False
        assert "value_engineered" not in result

    def test_competitor_intel_adjusts_margin(self, sample_solution_output):
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        result_no_comp = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
        )
        result_with_comp = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
            competitor_avg=450000.0,
        )
        assert result_with_comp["total_with_margin"] <= result_no_comp["total_with_margin"]


class TestValidateOutputPriceToWin:
    def test_accepts_value_engineered_field(self):
        agent = CostAgent.__new__(CostAgent)
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [],
            "total": 0,
            "narrative": "x",
            "confidence": 0.5,
            "value_engineered": True,
            "pricing_strategy": "competitive",
        })
        result = agent.validate_output(raw)
        assert result["value_engineered"] is True
        assert result["pricing_strategy"] == "competitive"

    def test_accepts_without_optional_fields(self):
        agent = CostAgent.__new__(CostAgent)
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [],
            "total": 0,
            "narrative": "x",
            "confidence": 0.5,
        })
        result = agent.validate_output(raw)
        assert "value_engineered" not in result


class TestAgentAttributes:
    def test_agent_type(self):
        assert CostAgent.agent_type == "cost"

    def test_model(self):
        assert CostAgent.model == "claude-sonnet-4-6"

    def test_temperature(self):
        assert CostAgent.temperature == 0.2
