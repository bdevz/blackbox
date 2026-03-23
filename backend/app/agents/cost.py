import json

from app.agents.base import BaseAgent
from app.models.database import CompanyKnowledge


CONSULTADD_CONTEXT = """ConsultAdd is a 30-person IT consulting company based in India.
- Targets state and local government RFPs only (no federal)
- Wins on competitive cost, not boutique quality
- Cost is why ConsultAdd wins — competitive India-based pricing is the edge
- Current win rate: 3-4% (volume strategy — more at-bats = more wins)
- Goal: 10x proposal volume (100 → 1,000 RFPs/month) with same headcount"""

DEFAULT_MARGIN = 0.15


class CostAgent(BaseAgent):
    agent_type = "cost"
    model = "claude-sonnet-4-6"
    temperature = 0.2

    def calculate_costs(
        self,
        staffing: list[dict],
        rate_card: dict,
        margin: float = DEFAULT_MARGIN,
        estimated_value: float = None,
        competitor_avg: float = None,
    ) -> dict:
        """Deterministic cost calculation with price-to-win adjustments."""
        roles = []
        missing_rates = []
        subtotal = 0.0

        for entry in staffing:
            role = entry["role"]
            hours = entry["hours"]
            headcount = entry.get("headcount", 1)

            rate_info = rate_card.get(role)
            if rate_info is None:
                missing_rates.append(role)
                hourly_rate = 0.0
            else:
                hourly_rate = float(rate_info.get("hourly", rate_info) if isinstance(rate_info, dict) else rate_info)

            total = hourly_rate * hours * headcount
            subtotal += total
            roles.append({
                "title": role,
                "rate": hourly_rate,
                "hours": hours,
                "headcount": headcount,
                "total": total,
            })

        # Price-to-win: adjust margin if competitor data available
        effective_margin = margin
        if competitor_avg is not None and subtotal > 0:
            if subtotal * (1 + margin) > competitor_avg:
                effective_margin = max((competitor_avg / subtotal) - 1, 0.05)

        result = {
            "labor_costs": {"roles": roles, "subtotal": subtotal},
            "missing_rates": missing_rates,
            "total_with_margin": subtotal * (1 + effective_margin),
        }

        # Price-to-win: flag over-budget and compute value-engineered alternative
        if estimated_value is not None and subtotal * (1 + effective_margin) > estimated_value * 1.1:
            result["over_budget"] = True
            target = estimated_value * 0.95
            scale = target / (subtotal * (1 + effective_margin)) if subtotal > 0 else 1.0
            ve_roles = []
            ve_subtotal = 0.0
            for r in roles:
                ve_hours = int(r["hours"] * scale)
                ve_total = r["rate"] * ve_hours * r.get("headcount", 1)
                ve_subtotal += ve_total
                ve_roles.append({**r, "hours": ve_hours, "total": ve_total})
            result["value_engineered"] = {
                "labor_costs": {"roles": ve_roles, "subtotal": ve_subtotal},
                "total_with_margin": ve_subtotal * (1 + effective_margin),
            }
        else:
            result["over_budget"] = False

        return result

    def inject_context(self, context: dict, db=None) -> dict:
        if db is None:
            return context

        rows = (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.type.in_(["ratecard", "rate"]))
            .all()
        )

        rate_card = {}
        for r in rows:
            if r.type == "ratecard" and isinstance(r.value, dict):
                rate_card.update(r.value.get("rates", {}))
            elif r.type == "rate" and isinstance(r.value, dict):
                rate_card[r.key] = r.value

        context["rate_card"] = rate_card

        # Extract estimated_value from RFP brief
        rfp_brief = context.get("rfp_brief", {})
        estimated_value = rfp_brief.get("estimated_value")
        context["estimated_value"] = float(estimated_value) if estimated_value else None

        # Fetch competitor intel
        from app.models.database import CompetitorIntel
        rfp_id = context.get("rfp_id") or rfp_brief.get("rfp_id")
        competitor_avg = None
        if rfp_id:
            competitors = db.query(CompetitorIntel).filter(
                CompetitorIntel.rfp_id == rfp_id
            ).all()
            if competitors:
                values = [float(c.past_contract_value) for c in competitors if c.past_contract_value]
                competitor_avg = sum(values) / len(values) if values else None
                context["competitor_intel"] = [
                    {"name": c.competitor_name, "value": float(c.past_contract_value) if c.past_contract_value else None}
                    for c in competitors
                ]

        solution = context.get("solution", {})
        staffing = solution.get("staffing", [])
        computed = self.calculate_costs(
            staffing=staffing,
            rate_card=rate_card,
            estimated_value=context["estimated_value"],
            competitor_avg=competitor_avg,
        )
        context["computed_costs"] = computed
        self._computed_costs = computed

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a cost proposal assembler for ConsultAdd.

{CONSULTADD_CONTEXT}

Your job: write ONLY the cost justification narrative. The numbers have already been calculated deterministically — do NOT change them.

You will receive:
1. The RFP brief
2. The solution's staffing plan
3. Pre-computed cost breakdown (use these exact numbers)

Write a compelling narrative that justifies the pricing. Emphasize ConsultAdd's cost advantage from India-based delivery.

Respond with ONLY valid JSON (no markdown fences):
{{
  "labor_costs": {{
    "roles": [
      {{"title": "Role", "rate": 95.0, "hours": 960, "total": 91200.0}}
    ],
    "subtotal": 441600.0
  }},
  "other_costs": [
    {{"item": "Description", "amount": 5000.0}}
  ],
  "total": 446600.0,
  "narrative": "markdown string — cost justification",
  "confidence": 0.0-1.0
}}

IMPORTANT: The labor_costs roles, rates, hours, totals, and subtotal MUST match the pre-computed values exactly. You may add other_costs for non-labor items."""

        rfp_brief = context.get("rfp_brief", {})
        solution = context.get("solution", {})
        computed = context.get("computed_costs", {})
        estimated_value = context.get("estimated_value")
        competitor_intel = context.get("competitor_intel", [])

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Solution Staffing Plan
{json.dumps(solution.get("staffing", []), indent=2)}

## Pre-Computed Cost Breakdown (USE THESE EXACT NUMBERS)
{json.dumps(computed, indent=2)}"""

        if estimated_value:
            user += f"""

## Budget Context
Estimated RFP value: ${estimated_value:,.2f}
{"WARNING: Our pricing exceeds the estimated value. Justify competitiveness or highlight value-engineering trade-offs." if computed.get("over_budget") else "Our pricing is within the estimated budget."}"""

        if competitor_intel:
            user += f"""

## Competitor Intelligence
{json.dumps(competitor_intel, indent=2)}
Position our pricing as competitive against these competitors."""

        user += """

Write the cost justification narrative. Use the pre-computed numbers exactly."""

        review_feedback = context.get("review_feedback")
        if review_feedback:
            user += f"""

## QA Reviewer Feedback (FIX THESE ISSUES)
The QA reviewer found these issues with your previous output. You MUST fix them:
{review_feedback}"""

        return system, user

    def validate_output(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON output from cost agent")

        required = ["labor_costs", "other_costs", "total", "narrative", "confidence"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        lc = data["labor_costs"]
        if not isinstance(lc, dict) or "roles" not in lc or "subtotal" not in lc:
            raise ValueError("'labor_costs' must have 'roles' and 'subtotal'")

        if not isinstance(lc["roles"], list):
            raise ValueError("'labor_costs.roles' must be a list")

        for i, role in enumerate(lc["roles"]):
            for key in ["title", "rate", "hours", "total"]:
                if key not in role:
                    raise ValueError(f"labor_costs.roles[{i}] missing '{key}'")

        if not isinstance(data["other_costs"], list):
            raise ValueError("'other_costs' must be a list")

        if not isinstance(data["total"], (int, float)):
            raise ValueError("'total' must be a number")

        if not isinstance(data["narrative"], str) or not data["narrative"].strip():
            raise ValueError("'narrative' must be a non-empty string")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        # Cross-check LLM numbers against deterministic calculation
        computed = getattr(self, "_computed_costs", None)
        if computed is not None:
            expected_subtotal = computed["labor_costs"]["subtotal"]
            if abs(lc["subtotal"] - expected_subtotal) > 0.01:
                raise ValueError(
                    f"LLM labor subtotal ({lc['subtotal']}) diverges from "
                    f"computed value ({expected_subtotal})"
                )

        return data
