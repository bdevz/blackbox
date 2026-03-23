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


class TestAgentAttributes:
    def test_agent_type(self):
        assert CostAgent.agent_type == "cost"

    def test_model(self):
        assert CostAgent.model == "claude-sonnet-4-6"

    def test_temperature(self):
        assert CostAgent.temperature == 0.2
