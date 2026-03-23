import json

from app.agents.base import BaseAgent
from app.agents.qualification import CONSULTADD_CONTEXT
from app.models.database import CompanyKnowledge


class ComplianceAgent(BaseAgent):
    agent_type = "comply"
    model = "claude-opus-4-6"
    temperature = 0.2
    max_tokens = 8192

    def inject_context(self, context: dict, db=None) -> dict:
        if db is None:
            return context

        rows = (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.type.in_(["cert", "certification", "boilerplate"]))
            .all()
        )
        certs = []
        boilerplate = []
        for r in rows:
            entry = {"type": r.type, "key": r.key, "value": r.value}
            if r.type == "boilerplate":
                boilerplate.append(entry)
            else:
                certs.append(entry)

        context["certifications"] = certs
        context["boilerplate"] = boilerplate
        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a government RFP compliance specialist for ConsultAdd.

{CONSULTADD_CONTEXT}

Your job: write the compliance narrative and produce a forms checklist.

Rules:
- NEVER fabricate certifications. If a required cert is missing, flag it explicitly:
  "ConsultAdd does not currently hold X. Acquisition timeline: Y."
- Use boilerplate text VERBATIM where available (EEO, non-collusion, transmittal).
- For each required form, indicate status: "have", "need", or "na".
- ALL work is performed by US-based resources. Never mention offshore, India, or overseas delivery.
- Present ConsultAdd as a US-headquartered firm with nationwide consultant deployment.

Respond with ONLY valid JSON (no markdown fences):
{{
  "narrative": "markdown string — full compliance narrative",
  "forms_checklist": [
    {{"form": "Form Name", "status": "have"|"need"|"na"}}
  ],
  "certifications_cited": ["Cert1", "Cert2"],
  "flags": ["any concerns or missing items"],
  "confidence": 0.0-1.0
}}"""

        rfp_brief = context.get("rfp_brief", {})
        qualification = context.get("qualification", {})
        certs = context.get("certifications", [])
        boilerplate = context.get("boilerplate", [])

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Qualification Assessment
{json.dumps(qualification, indent=2)}

## ConsultAdd's Certifications
{json.dumps(certs, indent=2) if certs else "No certification data available."}

## Available Boilerplate Text
{json.dumps(boilerplate, indent=2) if boilerplate else "No boilerplate available."}

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
