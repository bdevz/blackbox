"""Reconciliation agent — fixes cross-section inconsistencies in a single pass.

This agent reads ALL proposal sections together and produces corrected versions
where numbers, names, citations, timelines, and counts are consistent across
solution, compliance, and cost sections.

This runs ONCE after the final review, outside the revision loop.
"""

import json

from app.agents.base import BaseAgent
from app.agents.playbook import CANONICAL_CITATIONS
from app.config import settings


class ReconcileAgent(BaseAgent):
    agent_type = "reconcile"
    model = settings.claude_model
    temperature = 0.1
    max_tokens = 16000

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a proposal reconciliation specialist. Your ONLY job is to fix
cross-section inconsistencies in a government proposal. You receive the complete
proposal (solution, compliance, cost) plus the review agent's findings.

{CANONICAL_CITATIONS}

YOUR TASK:
1. Read the review's contradictions and playbook violations
2. For each inconsistency, determine the CORRECT value by:
   - Using the solution section as the source of truth for scope, staffing, timeline
   - Using the cost section as the source of truth for rates and totals
   - Using the canonical citations above for regulation/standard versions
3. Output corrected versions of ONLY the fields that need fixing

RULES:
- Do NOT rewrite sections. Only output the specific corrections.
- Do NOT change the substance — only fix inconsistencies.
- Do NOT add new content. Only reconcile what exists.
- If the solution says 40 users in pilot and cost says 80, pick the solution's number.
- If solution says $169K and cost says $184K, pick the cost's number (it's computed).
- If FIPS 140-2 appears in solution and FIPS 140-3 in compliance, use FIPS 140-3 (canonical).
- NEVER introduce India, offshore, or overseas references.

Respond with ONLY valid JSON (no markdown fences):
{{
  "corrections": [
    {{
      "section": "solution"|"compliance"|"cost",
      "field": "the field or text to fix",
      "old_value": "what it currently says",
      "new_value": "what it should say",
      "reason": "why this is the correct value"
    }}
  ],
  "solution_patches": {{
    "approach": "ONLY if approach text needs fixes — provide the FULL corrected approach text, or null if no changes needed",
    "staffing_plan": "corrected staffing_plan or null",
    "timeline": "corrected timeline or null"
  }},
  "compliance_patches": {{
    "narrative": "FULL corrected compliance narrative, or null if no changes needed"
  }},
  "cost_patches": {{
    "narrative": "FULL corrected cost narrative, or null if no changes needed"
  }},
  "remaining_issues": ["issues that cannot be fixed automatically — need human review"],
  "confidence": 0.0-1.0
}}

IMPORTANT: For patched fields, output the COMPLETE corrected text, not just the diff.
If a section needs no changes, set its patch to null."""

        solution = context.get("solution", {})
        compliance = context.get("compliance", {})
        cost = context.get("cost", {})
        review = context.get("review", {})

        # Build the contradiction summary
        issues = []
        for c in review.get("contradictions", []):
            issues.append(f"[{c.get('severity', 'medium').upper()}] {c.get('issue', '')}")
        for v in review.get("playbook_violations", []):
            if v.get("severity") in ("critical", "high"):
                issues.append(f"[PLAYBOOK-{v.get('severity', '').upper()}] {v.get('pattern', '')}: {v.get('violation', '')}")

        user = f"""## REVIEW FINDINGS TO RECONCILE
{chr(10).join(issues)}

## SOLUTION SECTION
Approach ({len(solution.get('approach', ''))} chars):
{solution.get('approach', '')[:8000]}

Staffing Plan:
{solution.get('staffing_plan', '')}

Staffing Array:
{json.dumps(solution.get('staffing', []), indent=2)}

Timeline:
{solution.get('timeline', '')}

## COMPLIANCE SECTION
{(compliance.get('narrative', '') or '')[:6000]}

## COST SECTION
Labor:
{json.dumps(cost.get('labor_costs', {}), indent=2)}

Total: {cost.get('total', 0)}

Narrative ({len(cost.get('narrative', '') or '')} chars):
{(cost.get('narrative', '') or '')[:6000]}

Fix ALL cross-section inconsistencies. Use solution for scope/staffing, cost for numbers, canonical citations for standards."""

        return system, user

    def validate_output(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON output from reconciliation agent")

        if "corrections" not in data:
            raise ValueError("Missing 'corrections' field")

        if not isinstance(data["corrections"], list):
            raise ValueError("'corrections' must be a list")

        if not isinstance(data.get("confidence", 0), (int, float)):
            raise ValueError("'confidence' must be a number")

        return data
