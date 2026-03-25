import json
import logging

from app.agents.base import BaseAgent
from app.agents.playbook import CONSULTADD_PROFILE, QUALIFICATION_RULES
from app.config import settings
from app.models.database import CompanyKnowledge

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (other agents import from here)
CONSULTADD_CONTEXT = CONSULTADD_PROFILE


class QualificationAgent(BaseAgent):
    agent_type = "qualify"
    model = settings.claude_model
    temperature = 0.1

    async def inject_context(self, context: dict, db=None) -> dict:
        # ── SQL: structured cert/capability lookup (deterministic matching) ──
        if db is not None:
            rows = (
                db.query(CompanyKnowledge)
                .filter(CompanyKnowledge.type.in_(["cert", "certification", "capability"]))
                .all()
            )
            context["company_qualifications"] = [
                {"type": r.type, "key": r.key, "value": r.value} for r in rows
            ]

        # ── RAG: semantic retrieval from pre-fetched context or live query ──
        rag_ctx = context.pop("rag_context", {})
        if rag_ctx:
            context["rag_results"] = rag_ctx
        else:
            # Fallback: live retrieval if prefetch wasn't run
            try:
                from app.services.rag_retriever import retrieve_for_agent
                rfp_text = json.dumps(context.get("rfp_brief", {}))
                context["rag_results"] = await retrieve_for_agent("qualify", rfp_text)
            except Exception as e:
                logger.warning(f"QualificationAgent RAG retrieval failed: {e}")
                context["rag_results"] = {}

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a government RFP qualification classifier for ConsultAdd.

{CONSULTADD_PROFILE}

{QUALIFICATION_RULES}

Your job: determine whether ConsultAdd should bid on this RFP.

Process:
1. DETERMINISTIC CHECKS FIRST — match required certifications, state registrations, revenue thresholds, years in business, and category against ConsultAdd's actual qualifications above.
2. WIN HISTORY CHECK — ConsultAdd has won 50+ awards across MSP, cybersecurity, SharePoint, cloud, data, ERP, and IT consulting for cities, counties, schools, universities, transit, housing, airports, and state agencies in 15+ states. Check if this RFP matches any winning category.
3. LLM JUDGMENT — assess scope fit, team capacity, competitive positioning, and pricing viability.
4. Flag anything missing but potentially acquirable before the deadline.

Respond with ONLY valid JSON (no markdown fences):
{{
  "qualified": true/false,
  "confidence": 0.0-1.0,
  "reasons": ["reason1", "reason2"],
  "missing": ["missing_item1"],
  "recommendation": "go" | "no-go" | "conditional"
}}"""

        from app.services.rag_retriever import format_rag_context_for_prompt

        quals = context.get("company_qualifications", [])
        quals_text = json.dumps(quals, indent=2) if quals else "No qualification data available."

        rfp_brief = context.get("rfp_brief", {})
        rfp_text = json.dumps(rfp_brief, indent=2)

        rag_section = format_rag_context_for_prompt(
            context.get("rag_results", {}), agent_type="qualify"
        )

        user = f"""## RFP Brief
{rfp_text}

## ConsultAdd's Current Qualifications
{quals_text}
{rag_section}
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
