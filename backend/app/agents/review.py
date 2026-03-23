import json

from app.agents.base import BaseAgent
from app.agents.playbook import REVIEW_RULES


class ReviewAgent(BaseAgent):
    agent_type = "review"
    model = "claude-sonnet-4-6"
    temperature = 0.1

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a proposal QA reviewer for ConsultAdd Public Services.
You enforce the winning patterns from 13 analyzed proposals. Your review determines
whether this proposal would win against competitors.

{REVIEW_RULES}

ADDITIONAL CHECKS:
1. STAFFING CONSISTENCY — does solution staffing match cost section roles?
2. TIMELINE CONSISTENCY — are dates and durations consistent?
3. CONTRADICTIONS — do any sections contradict each other?
4. RFP COVERAGE — are all RFP requirements addressed?
5. FORMATTING — consistent headers, professional tone.

SEVERITY LEVELS:
- CRITICAL: Offshore mention, staffing/cost mismatch, missing required sections → auto-fail
- HIGH: Generic language, no named staff, no quantified metrics → needs revision
- MEDIUM: Missing value-adds, weak local presence, vague regulations → improvement needed
- LOW: Formatting, minor language issues → polish

Be specific and actionable. Each issue must have enough detail to fix.

Respond with ONLY valid JSON (no markdown fences):
{{
  "contradictions": [
    {{"sections": ["section1", "section2"], "issue": "description", "severity": "high"|"medium"|"low"}}
  ],
  "missing_sections": ["section that should exist but doesn't"],
  "formatting_issues": ["specific formatting problem"],
  "playbook_violations": [
    {{"pattern": "Pattern N name", "violation": "what's wrong", "fix": "how to fix it", "severity": "critical"|"high"|"medium"|"low"}}
  ],
  "quality_score": 0.0-1.0,
  "recommendation": "ready" | "needs_revision" | "major_issues",
  "confidence": 0.0-1.0
}}"""

        rfp_brief = context.get("rfp_brief", {})
        qualification = context.get("qualification", {})
        solution = context.get("solution", {})
        compliance = context.get("compliance", {})
        cost = context.get("cost", {})

        user = f"""## Original RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Qualification Assessment
{json.dumps(qualification, indent=2)}

## Solution Section
{json.dumps(solution, indent=2)}

## Compliance Section
{json.dumps(compliance, indent=2)}

## Cost Section
{json.dumps(cost, indent=2)}

Review this proposal for contradictions, missing sections, and formatting issues."""

        return system, user

    def validate_output(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON output from review agent")

        required = ["contradictions", "missing_sections", "formatting_issues",
                     "quality_score", "recommendation", "confidence"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["contradictions"], list):
            raise ValueError("'contradictions' must be a list")

        valid_severities = {"high", "medium", "low"}
        for i, c in enumerate(data["contradictions"]):
            if not isinstance(c, dict):
                raise ValueError(f"contradictions[{i}] must be a dict")
            for key in ["sections", "issue", "severity"]:
                if key not in c:
                    raise ValueError(f"contradictions[{i}] missing '{key}'")
            if c["severity"] not in valid_severities:
                raise ValueError(f"contradictions[{i}] severity must be one of {valid_severities}")

        if not isinstance(data["missing_sections"], list):
            raise ValueError("'missing_sections' must be a list")

        if not isinstance(data["formatting_issues"], list):
            raise ValueError("'formatting_issues' must be a list")

        if not isinstance(data["quality_score"], (int, float)) or not 0 <= data["quality_score"] <= 1:
            raise ValueError("'quality_score' must be a float between 0 and 1")

        valid_recs = {"ready", "needs_revision", "major_issues"}
        if data["recommendation"] not in valid_recs:
            raise ValueError(f"'recommendation' must be one of {valid_recs}")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        return data
