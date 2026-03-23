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

    # Pattern 1: Open with the agency, not ConsultAdd
    # Pattern 2: Mirror RFP scope in the letter
    # Pattern 10: Include MBE status
    return f"""# Letter of Transmittal

**Consultadd Public Services**
175 Greenwich St, 38th Floor
New York, NY 10007

**Date:** {date_str}

**To:** Procurement Office, {agency_name}

**Re:** {rfp_title}

Dear Procurement Officer,

On behalf of Consultadd Public Services, a division of Consultadd Inc., we are pleased to submit our proposal in response to the above-referenced solicitation. We recognize the importance of this initiative to {agency_name} and are fully committed to delivering results that strengthen your organization's operational capabilities.

{transmittal}

We have carefully reviewed the entire solicitation package, including all instructions, scope requirements, deliverables, conditions, insurance requirements, and compliance provisions. Consultadd Public Services confirms full compliance with all terms and conditions as stated.

Consultadd is a certified Minority Business Enterprise (MBE) with over 15 years of experience and 250+ government contracts awarded. With 600+ IT professionals and 350+ specialized field consultants deployed nationwide, we bring deep state and local government expertise backed by SOC 2 Type II, ISO 27001, and CMMC Level I certifications. We are an AWS Advanced Partner, Microsoft Solutions Partner, and GSA MAS Schedule holder.

We confirm our proposal remains valid for a minimum period of 180 days and look forward to the opportunity to serve {agency_name}.

Respectfully submitted,

**Bharat Bhate**
Founder & President
Consultadd Inc.
bharat.b@consultadd.com"""


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
    strengths = [r for r in reasons if not r.lower().startswith("no ") and "missing" not in r.lower() and "lack" not in r.lower()]
    strengths_md = "\n".join(f"- {r}" for r in strengths) if strengths else "- Deep expertise in government IT services"

    # Pattern 1: Open with agency framing, not vendor positioning
    # Pattern 8: Reference the agency by name and context
    return f"""# 1. Executive Summary

## Understanding of {agency_name}'s Requirements

{agency_name} is undertaking an important initiative with **{rfp_title}**. Consultadd Public Services understands that {agency_name} seeks more than a traditional contractor — it is looking for a strategic partner that can provide expert leadership, proven methodology, and measurable outcomes.

## Why Consultadd Public Services

Consultadd Public Services is a certified Minority Business Enterprise (MBE) with over 15 years of experience and 250+ government contracts awarded across state, local, and federal agencies. Our team of 600+ IT professionals includes 350+ specialized field consultants deployed nationwide.

**Key Strengths for This Engagement:**
{strengths_md}

## Our Commitment

We do not view this as a transactional engagement. Our approach is grounded in partnership, transparency, and a commitment to exceeding expectations. {agency_name} will always have full visibility into our work through regular reporting, milestone reviews, and direct access to our leadership team.

All work will be performed by U.S.-based staff from our nationwide team. Executive oversight by Bharat Bhate (Founder & President) and our PMO Director is included at no additional cost."""


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
