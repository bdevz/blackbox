import json

from app.agents.base import BaseAgent
from app.models.database import CompanyKnowledge


CONSULTADD_CONTEXT = """ConsultAdd is a 600-person enterprise technology firm (300 US, 300 India).
Headquarters: 175 Greenwich St, 38th Floor, New York, NY.
15+ years in business. 200+ successful government projects delivered. 98% on-time/on-budget.
350+ specialized field consultants deployed nationwide.

Services:
- IT Managed Services (MSP), IT Consulting, IT Staffing
- Cloud Migration & Services (AWS, Azure) with FedRAMP compliance
- Cybersecurity & Managed Security Services (FISMA, NIST)
- Data Analytics & Data Migration
- Legacy Modernization & Application Development
- Enterprise System Implementation (Oracle, SAP, Microsoft ERP, Salesforce)
- Digital Accessibility Services

Certifications & Compliance:
- ISO 27001, SOC 2 Type II, CMMC Level I
- GSA Schedule holder
- CMAS (California cooperative purchasing)
- USPAACC certified

Technology Partnerships:
- AWS Advanced Partner, Microsoft Partner, Oracle Partner
- Salesforce Partner, IBM Silver Partner

Past Performance (state & local):
- Ohio Department of Natural Resources, New Jersey state agencies
- Orange County, Macomb County, Social Security Administration
- Multiple state DOT, DAS, and university systems

Sweet spot: $100K–$500K SLED contracts in IT professional services.
Competitive advantage: India delivery center for cost efficiency + 350 US consultants for on-site work."""


class QualificationAgent(BaseAgent):
    agent_type = "qualify"
    model = "claude-haiku-4-5-20251001"
    temperature = 0.1

    def inject_context(self, context: dict, db=None) -> dict:
        if db is None:
            return context
        rows = (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.type.in_(["cert", "certification", "capability"]))
            .all()
        )
        context["company_qualifications"] = [
            {"type": r.type, "key": r.key, "value": r.value} for r in rows
        ]
        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a government RFP qualification classifier for ConsultAdd.

{CONSULTADD_CONTEXT}

Your job: determine whether ConsultAdd should bid on this RFP.

Process:
1. DETERMINISTIC CHECKS FIRST — match required certifications, state registrations, revenue thresholds, years in business, and category against ConsultAdd's actual qualifications.
2. LLM JUDGMENT SECOND — assess soft factors like scope fit, team capacity, and competitive positioning.
3. Flag anything missing but potentially acquirable before the deadline.

Respond with ONLY valid JSON (no markdown fences):
{{
  "qualified": true/false,
  "confidence": 0.0-1.0,
  "reasons": ["reason1", "reason2"],
  "missing": ["missing_item1"],
  "recommendation": "go" | "no-go" | "conditional"
}}"""

        quals = context.get("company_qualifications", [])
        quals_text = json.dumps(quals, indent=2) if quals else "No qualification data available."

        rfp_brief = context.get("rfp_brief", {})
        rfp_text = json.dumps(rfp_brief, indent=2)

        user = f"""## RFP Brief
{rfp_text}

## ConsultAdd's Current Qualifications
{quals_text}

Evaluate whether ConsultAdd should bid on this RFP."""

        return system, user

    def validate_output(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON output from qualification agent")

        required = ["qualified", "confidence", "reasons", "missing", "recommendation"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["qualified"], bool):
            raise ValueError("'qualified' must be a boolean")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        if not isinstance(data["reasons"], list):
            raise ValueError("'reasons' must be a list")

        if not isinstance(data["missing"], list):
            raise ValueError("'missing' must be a list")

        valid_recs = {"go", "no-go", "conditional"}
        if data["recommendation"] not in valid_recs:
            raise ValueError(f"'recommendation' must be one of {valid_recs}")

        return data
