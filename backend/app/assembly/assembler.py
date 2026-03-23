"""Assemble proposal sections into a unified markdown document."""

import json
from datetime import datetime


def assemble_proposal(
    rfp_title: str,
    agency_name: str,
    deadline: str,
    qualification: dict,
    solution_section: str,
    compliance_section: str,
    cost_section: dict,
    review_result: dict = None,
    boilerplate: dict = None,
) -> str:
    """Stitch proposal sections into a single markdown document."""
    sections = []
    sections.append(_build_cover_letter(rfp_title, agency_name, deadline, boilerplate))
    sections.append(_build_toc())
    sections.append(_build_executive_summary(qualification, rfp_title, agency_name))
    sections.append(f"# 2. Technical Approach\n\n{solution_section}")
    sections.append(f"# 3. Compliance\n\n{compliance_section}")
    sections.append(_build_cost_section(cost_section))
    sections.append(_build_appendices(boilerplate))
    return "\n\n---\n\n".join(sections)


def _build_cover_letter(rfp_title, agency_name, deadline, boilerplate=None):
    transmittal = ""
    if boilerplate and "transmittal" in boilerplate:
        t = boilerplate["transmittal"]
        transmittal = t.get("text", str(t)) if isinstance(t, dict) else str(t)

    date_str = datetime.now().strftime("%B %d, %Y")
    deadline_str = deadline or "as specified"

    return f"""# Cover Letter

**Date:** {date_str}

**To:** Procurement Office, {agency_name}

**Re:** {rfp_title}

Dear Procurement Officer,

ConsultAdd, Inc. is pleased to submit this proposal in response to the above-referenced Request for Proposal. We have carefully reviewed the requirements and are confident in our ability to deliver exceptional results.

{transmittal}

ConsultAdd is a 600-person enterprise technology firm with 350+ specialized field consultants deployed nationwide. With 15+ years of experience and 200+ successful government projects, we bring deep SLED expertise backed by ISO 27001, SOC 2 Type II, and CMMC Level I certifications.

We confirm our proposal remains valid through the deadline of {deadline_str} and look forward to the opportunity to serve {agency_name}.

Respectfully submitted,

**ConsultAdd, Inc.**"""


def _build_toc():
    return """# Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Technical Approach](#2-technical-approach)
3. [Compliance](#3-compliance)
4. [Cost Proposal](#4-cost-proposal)
5. [Appendices](#5-appendices)"""


def _build_executive_summary(qualification, rfp_title, agency_name):
    if not qualification:
        return "# 1. Executive Summary\n\n*Qualification data not available.*"

    confidence = qualification.get("confidence", 0)
    reasons = qualification.get("reasons", [])
    recommendation = qualification.get("recommendation", "go")
    reasons_md = "\n".join(f"- {r}" for r in reasons) if reasons else "- Meets all requirements"

    return f"""# 1. Executive Summary

ConsultAdd is pleased to present our proposal for **{rfp_title}** for **{agency_name}**.

**Qualification Assessment:** {recommendation.upper()} (Confidence: {confidence:.0%})

**Key Strengths:**
{reasons_md}"""


def _build_cost_section(cost_section):
    if not cost_section:
        return "# 4. Cost Proposal\n\n*Cost data not available.*"

    parts = ["# 4. Cost Proposal"]

    labor = cost_section.get("labor_costs", {})
    roles = labor.get("roles", [])
    if roles:
        parts.append("\n## Labor Costs\n")
        parts.append("| Role | Rate ($/hr) | Hours | Headcount | Total |")
        parts.append("|------|------------|-------|-----------|-------|")
        for r in roles:
            parts.append(
                f"| {r.get('title', 'N/A')} | ${r.get('rate', 0):,.2f} "
                f"| {r.get('hours', 0):,} | {r.get('headcount', 1)} "
                f"| ${r.get('total', 0):,.2f} |"
            )
        parts.append(f"\n**Labor Subtotal:** ${labor.get('subtotal', 0):,.2f}")

    other = cost_section.get("other_costs", [])
    if other:
        parts.append("\n## Other Costs\n")
        parts.append("| Item | Amount |")
        parts.append("|------|--------|")
        for item in other:
            parts.append(f"| {item.get('item', 'N/A')} | ${item.get('amount', 0):,.2f} |")

    total = cost_section.get("total", 0)
    parts.append(f"\n## Total Project Cost: ${total:,.2f}")

    narrative = cost_section.get("narrative", "")
    if narrative:
        parts.append(f"\n## Cost Justification\n\n{narrative}")

    return "\n".join(parts)


def _build_appendices(boilerplate=None):
    parts = ["# 5. Appendices"]

    if boilerplate:
        for key_variants, label in [
            (["eeo", "eeo-statement"], "Appendix A: Equal Employment Opportunity Statement"),
            (["non-collusion", "non_collusion"], "Appendix B: Non-Collusion Affidavit"),
        ]:
            for k in key_variants:
                if k in boilerplate:
                    text = boilerplate[k]
                    if isinstance(text, dict):
                        text = text.get("text", str(text))
                    parts.append(f"\n## {label}\n\n{text}")
                    break

    if len(parts) == 1:
        parts.append("\n*No appendices available.*")

    return "\n".join(parts)
