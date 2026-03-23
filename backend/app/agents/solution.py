import json
import logging

from app.agents.base import BaseAgent
from app.agents.playbook import CONSULTADD_PROFILE, WINNING_PLAYBOOK, SOLUTION_RULES
from app.config import settings
from app.models.database import CompanyKnowledge, ProposalEmbedding

logger = logging.getLogger(__name__)


class SolutionAgent(BaseAgent):
    agent_type = "solution"
    model = "claude-opus-4-6"
    temperature = 0.4
    max_tokens = 8192

    def _find_similar_proposals(self, rfp_brief: dict, db) -> list[dict]:
        """Query pgvector for similar past proposals using Voyage embeddings."""
        try:
            import voyageai

            vo = voyageai.Client(api_key=settings.voyage_api_key)
            brief_text = json.dumps(rfp_brief)
            embedding_result = vo.embed([brief_text], model=settings.voyage_model)
            query_vector = embedding_result.embeddings[0]

            results = (
                db.query(ProposalEmbedding)
                .order_by(ProposalEmbedding.embedding.cosine_distance(query_vector))
                .limit(3)
                .all()
            )
            return [
                {"section": r.section, "proposal_id": str(r.proposal_id)}
                for r in results
            ]
        except Exception as e:
            logger.warning(f"Similar proposal lookup failed (expected if no embeddings exist): {e}")
            return []

    def inject_context(self, context: dict, db=None) -> dict:
        if db is None:
            return context

        rows = (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.type.in_(["capability", "reference", "ratecard"]))
            .all()
        )
        context["company_knowledge"] = [
            {"type": r.type, "key": r.key, "value": r.value} for r in rows
        ]

        rfp_brief = context.get("rfp_brief", {})
        context["similar_proposals"] = self._find_similar_proposals(rfp_brief, db)

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a technical proposal writer for ConsultAdd Public Services.
You write proposals that WIN government contracts. You have been trained on 13 winning proposals.

{CONSULTADD_PROFILE}

{SOLUTION_RULES}

{WINNING_PLAYBOOK}

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

        rfp_brief = context.get("rfp_brief", {})
        qualification = context.get("qualification", {})
        knowledge = context.get("company_knowledge", [])
        similar = context.get("similar_proposals", [])

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Qualification Assessment
{json.dumps(qualification, indent=2)}

## ConsultAdd Capabilities & References
{json.dumps(knowledge, indent=2)}

## Similar Past Proposals
{json.dumps(similar, indent=2) if similar else "No similar proposals found."}

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
