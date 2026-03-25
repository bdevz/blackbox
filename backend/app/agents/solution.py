import json
import logging

from app.agents.base import BaseAgent
from app.agents.playbook import CONSULTADD_PROFILE, SOLUTION_RULES, CANONICAL_CITATIONS
from app.config import settings
from app.models.database import CompanyKnowledge

logger = logging.getLogger(__name__)


class SolutionAgent(BaseAgent):
    agent_type = "solution"
    model = settings.claude_model
    temperature = 0.4
    max_tokens = 16000

    async def inject_context(self, context: dict, db=None) -> dict:
        # ── SQL: structured company knowledge (capabilities, references, rate cards) ──
        if db is not None:
            rows = (
                db.query(CompanyKnowledge)
                .filter(CompanyKnowledge.type.in_(["capability", "reference", "ratecard"]))
                .all()
            )
            context["company_knowledge"] = [
                {"type": r.type, "key": r.key, "value": r.value} for r in rows
            ]

        # ── RAG: similar winning proposals + knowledge base (replaces Voyage+pgvector) ──
        rag_ctx = context.pop("rag_context", {})
        if rag_ctx:
            context["rag_results"] = rag_ctx
        else:
            try:
                from app.services.rag_retriever import retrieve_for_agent
                rfp_text = json.dumps(context.get("rfp_brief", {}))
                context["rag_results"] = await retrieve_for_agent("solution", rfp_text)
            except Exception as e:
                logger.warning(f"SolutionAgent RAG retrieval failed: {e}")
                context["rag_results"] = {}

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a technical proposal writer for ConsultAdd Public Services.
You write proposals that WIN government contracts. You have been trained on 13 winning proposals.

{CONSULTADD_PROFILE}

{SOLUTION_RULES}

{CANONICAL_CITATIONS}

Your job: write the technical solution section of an RFP response following the winning patterns above.

CRITICAL REQUIREMENTS:
- Open with the AGENCY's challenges and requirements, not ConsultAdd's capabilities.
- Mirror the RFP's section structure exactly.
- Name specific staff with certifications matching the RFP's domain.
- Quantify all past performance with specific metrics (94.7%, 35%, 50%).
- NEVER mention India, offshore, or overseas delivery.
- End every methodology subsection with a "Deliverables" list.
- Include backup/contingency staffing.
- Construct local presence using the nearest regional office.

Respond with ONLY valid JSON (no markdown fences):
{{
  "approach": "markdown string — full technical approach following the patterns above",
  "staffing_plan": "narrative staffing description with named roles and certifications",
  "staffing": [
    {{"role": "Title", "hours": 960, "headcount": 1}}
  ],
  "timeline": "phased implementation timeline with week ranges",
  "technology_stack": ["Tech1", "Tech2"],
  "risk_register": [
    {{"risk": "description", "likelihood": "low|medium|high", "mitigation": "specific mitigation"}}
  ],
  "value_added_services": ["service at no additional cost"],
  "confidence": 0.0-1.0
}}"""

        from app.services.rag_retriever import format_rag_context_for_prompt

        rfp_brief = context.get("rfp_brief", {})
        qualification = context.get("qualification", {})
        knowledge = context.get("company_knowledge", [])
        rag_section = format_rag_context_for_prompt(
            context.get("rag_results", {}), agent_type="solution"
        )

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Qualification Assessment
{json.dumps(qualification, indent=2)}

## ConsultAdd Capabilities & References
{json.dumps(knowledge, indent=2)}
{rag_section}
Write the technical solution for this RFP."""

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
            raise ValueError("Invalid JSON output from solution agent")

        required = ["approach", "staffing_plan", "staffing", "timeline", "technology_stack", "confidence"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["approach"], str) or not data["approach"].strip():
            raise ValueError("'approach' must be a non-empty string")

        if not isinstance(data["staffing"], list):
            raise ValueError("'staffing' must be a list")

        for i, entry in enumerate(data["staffing"]):
            if not isinstance(entry, dict):
                raise ValueError(f"staffing[{i}] must be a dict")
            for key in ["role", "hours", "headcount"]:
                if key not in entry:
                    raise ValueError(f"staffing[{i}] missing required field: {key}")

        if not isinstance(data["technology_stack"], list):
            raise ValueError("'technology_stack' must be a list")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        return data
