import pytest
from app.assembly.assembler import assemble_proposal


SAMPLE_QUALIFICATION = {
    "qualified": True,
    "confidence": 0.85,
    "reasons": ["ISO 27001 certified", "8 years cloud experience"],
    "recommendation": "go",
}

SAMPLE_COST = {
    "labor_costs": {
        "roles": [
            {"title": "Project Manager", "rate": 95.0, "hours": 960, "headcount": 1, "total": 91200.0},
            {"title": "Developer", "rate": 55.0, "hours": 960, "headcount": 2, "total": 105600.0},
        ],
        "subtotal": 196800.0,
    },
    "other_costs": [{"item": "Cloud infra", "amount": 12000.0}],
    "total": 208800.0,
    "narrative": "Competitive India-based pricing.",
}

SAMPLE_BOILERPLATE = {
    "eeo-statement": {"text": "ConsultAdd is an Equal Opportunity Employer."},
    "non-collusion": {"text": "This proposal is genuine and not collusive."},
    "transmittal": {"text": "We hereby submit this proposal."},
}


class TestAssembleProposal:
    def test_returns_string(self):
        result = assemble_proposal(
            rfp_title="IT Modernization",
            agency_name="Ohio DAS",
            deadline="2026-05-15",
            qualification=SAMPLE_QUALIFICATION,
            solution_section="## Our Approach\nPhased migration.",
            compliance_section="## Compliance\nAll requirements met.",
            cost_section=SAMPLE_COST,
        )
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_all_sections(self):
        result = assemble_proposal(
            rfp_title="Test RFP",
            agency_name="Test Agency",
            deadline="2026-06-01",
            qualification=SAMPLE_QUALIFICATION,
            solution_section="Solution content",
            compliance_section="Compliance content",
            cost_section=SAMPLE_COST,
        )
        assert "Cover Letter" in result
        assert "Table of Contents" in result
        assert "Executive Summary" in result
        assert "Technical Approach" in result
        assert "Compliance" in result
        assert "Cost Proposal" in result
        assert "Appendices" in result

    def test_cover_letter_has_rfp_info(self):
        result = assemble_proposal(
            rfp_title="Cloud Migration RFP",
            agency_name="California DOT",
            deadline="2026-07-01",
            qualification={},
            solution_section="",
            compliance_section="",
            cost_section={},
        )
        assert "Cloud Migration RFP" in result
        assert "California DOT" in result

    def test_cost_table_rendered(self):
        result = assemble_proposal(
            rfp_title="Test",
            agency_name="Test",
            deadline=None,
            qualification={},
            solution_section="",
            compliance_section="",
            cost_section=SAMPLE_COST,
        )
        assert "Project Manager" in result
        assert "$91,200.00" in result
        assert "$196,800.00" in result

    def test_boilerplate_injected(self):
        result = assemble_proposal(
            rfp_title="Test",
            agency_name="Test",
            deadline=None,
            qualification={},
            solution_section="",
            compliance_section="",
            cost_section={},
            boilerplate=SAMPLE_BOILERPLATE,
        )
        assert "Equal Opportunity Employer" in result
        assert "genuine and not collusive" in result

    def test_empty_cost_section(self):
        result = assemble_proposal(
            rfp_title="Test",
            agency_name="Test",
            deadline=None,
            qualification={},
            solution_section="",
            compliance_section="",
            cost_section={},
        )
        assert "Cost data not available" in result

    def test_empty_qualification(self):
        result = assemble_proposal(
            rfp_title="Test",
            agency_name="Test",
            deadline=None,
            qualification={},
            solution_section="",
            compliance_section="",
            cost_section={},
        )
        assert "Qualification data not available" in result
