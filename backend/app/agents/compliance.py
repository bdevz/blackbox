import json
import logging

from app.agents.base import BaseAgent
from app.agents.playbook import CONSULTADD_PROFILE, COMPLIANCE_RULES, CANONICAL_CITATIONS
from app.config import settings
from app.models.database import CompanyKnowledge

logger = logging.getLogger(__name__)


class ComplianceAgent(BaseAgent):
    agent_type = "comply"
    model = settings.claude_model
    temperature = 0.2
    max_tokens = 12000

    async def inject_context(self, context: dict, db=None) -> dict:
        # ── SQL: structured cert/boilerplate lookup ──
        if db is not None:
            rows = (
                db.query(CompanyKnowledge)
                .filter(CompanyKnowledge.type.in_(["cert", "certification", "boilerplate"]))
                .all()
            )
            certs, boilerplate = [], []
            for r in rows:
                entry = {"type": r.type, "key": r.key, "value": r.value}
                (boilerplate if r.type == "boilerplate" else certs).append(entry)
            context["certifications"] = certs
            context["boilerplate"] = boilerplate

        # ── RAG: similar winning compliance sections + certs knowledge base ──
        rag_ctx = context.pop("rag_context", {})
        if rag_ctx:
            context["rag_results"] = rag_ctx
        else:
            try:
                from app.services.rag_retriever import retrieve_for_agent
                rfp_text = json.dumps(context.get("rfp_brief", {}))
                context["rag_results"] = await retrieve_for_agent("comply", rfp_text)
            except Exception as e:
                logger.warning(f"ComplianceAgent RAG retrieval failed: {e}")
                context["rag_results"] = {}

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a government RFP compliance specialist for ConsultAdd Public Services.
You write compliance sections that WIN government contracts. Trained on 13 winning proposals.

{CONSULTADD_PROFILE}

{COMPLIANCE_RULES}

{CANONICAL_CITATIONS}

Your job: write the compliance narrative and produce a forms checklist.

Rules:
- CITE every regulation by NAME and NUMBER — never "applicable regulations."
- Use certification stacking order: SOC 2 Type II → ISO 27001 → domain-specific → MBE/DBE → GSA.
- NEVER fabricate certifications. If a required cert is missing, flag it explicitly.
- Use boilerplate text VERBATIM where available (EEO, non-collusion, transmittal).
- For each required form, indicate status: "have", "need", or "na".
- ALL work is performed by US-based resources. NEVER mention offshore, India, or overseas.
- Data residency: "All data hosted within the United States, managed by U.S. persons."
- Present compliance as a TABLE: Compliance Area | Standard | Credential | Activity.
- Lead with MBE/diversity where it is scored or required.

Respond with ONLY valid JSON (no markdown fences):
{{
  "narrative": "markdown string — full compliance narrative with regulation citations",
  "forms_checklist": [
    {{"form": "Form Name", "status": "have"|"need"|"na"}}
  ],
  "certifications_cited": ["Cert1", "Cert2"],
  "compliance_table": [
    {{"area": "HIPAA", "standard": "45 CFR Part 164", "credential": "HIPAA-aligned SOPs", "activity": "Encryption, access controls, breach notification"}}
  ],
  "diversity_statement": "MBE/DBE compliance narrative if applicable",
  "data_residency_statement": "US data hosting statement",
  "flags": ["any concerns or missing items"],
  "confidence": 0.0-1.0
}}"""

        from app.services.rag_retriever import format_rag_context_for_prompt

        rfp_brief = context.get("rfp_brief", {})
        qualification = context.get("qualification", {})
        certs = context.get("certifications", [])
        boilerplate = context.get("boilerplate", [])
        rag_section = format_rag_context_for_prompt(
            context.get("rag_results", {}), agent_type="comply"
        )

        solution = context.get("solution", {})
        staffing_plan = solution.get("staffing_plan", "") if solution else ""
        staffing = solution.get("staffing", []) if solution else []

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Qualification Assessment
{json.dumps(qualification, indent=2)}

## Solution Staffing Plan (MIRROR THIS — use the same team names and roles)
{staffing_plan if staffing_plan else "Not yet available."}

## Solution Staffing Array
{json.dumps(staffing, indent=2) if staffing else "Not yet available."}

IMPORTANT: If a staffing plan is provided above, your compliance narrative MUST reference
the same team members by name and role. Do NOT create a different team or different role titles.
Use the exact same names, certifications, and titles from the solution section.

## ConsultAdd's Certifications
{json.dumps(certs, indent=2) if certs else "No certification data available."}

## Available Boilerplate Text
{json.dumps(boilerplate, indent=2) if boilerplate else "No boilerplate available."}
{rag_section}
Write the compliance narrative for this RFP."""

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
            raise ValueError("Invalid JSON output from compliance agent")

        required = ["narrative", "forms_checklist", "certifications_cited", "flags", "confidence"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["narrative"], str) or not data["narrative"].strip():
            raise ValueError("'narrative' must be a non-empty string")

        if not isinstance(data["forms_checklist"], list):
            raise ValueError("'forms_checklist' must be a list")

        valid_statuses = {"have", "need", "na"}
        for i, entry in enumerate(data["forms_checklist"]):
            if not isinstance(entry, dict):
                raise ValueError(f"forms_checklist[{i}] must be a dict")
            if "form" not in entry or "status" not in entry:
                raise ValueError(f"forms_checklist[{i}] must have 'form' and 'status'")
            if entry["status"] not in valid_statuses:
                raise ValueError(f"forms_checklist[{i}] status must be one of {valid_statuses}")

        if not isinstance(data["certifications_cited"], list):
            raise ValueError("'certifications_cited' must be a list")

        if not isinstance(data["flags"], list):
            raise ValueError("'flags' must be a list")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        return data
