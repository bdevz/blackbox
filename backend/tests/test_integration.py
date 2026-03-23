"""End-to-end integration test — runs the full orchestrator pipeline against live API.

Requires ANTHROPIC_API_KEY in env. Mocks DB layer since postgres may not be running.
Run with: cd backend && python -m pytest tests/test_integration.py -v -s -m integration
"""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.orchestrator import proposal_graph, ProposalState


def _make_knowledge_row(type_, key, value):
    """Create a mock CompanyKnowledge row."""
    row = MagicMock()
    row.type = type_
    row.key = key
    row.value = value
    return row


COMPANY_KNOWLEDGE = [
    _make_knowledge_row("cert", "iso-27001", {"name": "ISO 27001", "status": "active", "expires": "2027-01-01"}),
    _make_knowledge_row("certification", "cmmi-3", {"name": "CMMI Level 3", "status": "active"}),
    _make_knowledge_row("cert", "ohio-registration", {"name": "Ohio Business Registration", "status": "active", "state": "Ohio"}),
    _make_knowledge_row("capability", "it-consulting", {"name": "IT Consulting", "years": 12, "founded": 2014}),
    _make_knowledge_row("capability", "cloud-migration", {"name": "Cloud Migration", "years": 8, "projects": 45}),
    _make_knowledge_row("capability", "mainframe-modernization", {"name": "Mainframe Modernization", "years": 5, "projects": 12}),
    _make_knowledge_row("reference", "ohio-dot", {"client": "Ohio DOT", "project": "Network Upgrade", "year": 2025, "value": 1800000}),
    _make_knowledge_row("ratecard", "2026", {"rates": {
        "Project Manager": {"hourly": 95, "daily": 760},
        "Senior Developer": {"hourly": 75, "daily": 600},
        "Developer": {"hourly": 55, "daily": 440},
        "QA Engineer": {"hourly": 50, "daily": 400},
        "Cloud Architect": {"hourly": 110, "daily": 880},
        "Business Analyst": {"hourly": 65, "daily": 520},
    }}),
    _make_knowledge_row("boilerplate", "eeo-statement", {"text": "ConsultAdd is an Equal Opportunity Employer..."}),
    _make_knowledge_row("boilerplate", "non-collusion", {"text": "The undersigned hereby certifies that this proposal is genuine and not collusive..."}),
]


def _mock_session():
    """Return a mock DB session with CompanyKnowledge data seeded."""
    session = MagicMock()

    def _filter_knowledge(*args, **kwargs):
        """Simulate .filter(CompanyKnowledge.type.in_(types))."""
        result = MagicMock()
        # Check if this is a type filter by inspecting the call
        # Return all knowledge rows — agents filter in Python if needed
        result.all.return_value = COMPANY_KNOWLEDGE
        result.order_by.return_value.limit.return_value.all.return_value = []
        return result

    session.query.return_value.filter.side_effect = _filter_knowledge
    return session


SAMPLE_RFP = {
    "title": "IT Infrastructure Modernization for State of Ohio",
    "agency": "Ohio Department of Administrative Services",
    "state": "Ohio",
    "category": "IT Consulting",
    "deadline": "2026-05-15",
    "estimated_value": 2500000,
    "requirements": [
        "Minimum 5 years IT consulting experience",
        "ISO 27001 certification required",
        "Must be registered to do business in Ohio",
        "CMMI Level 3 or equivalent",
        "Experience with state/local government clients",
    ],
    "scope": "Modernize legacy mainframe systems to cloud-native architecture",
    "evaluation_criteria": {
        "technical_approach": 40,
        "cost": 30,
        "past_performance": 20,
        "staffing": 10,
    },
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline():
    """Run the full orchestrator pipeline: qualify → [solution || comply] → cost → review."""

    mock_session = _mock_session()

    with patch("app.agents.base.SessionLocal", return_value=mock_session):
        initial_state: ProposalState = {
            "rfp_id": "test-rfp-001",
            "rfp_brief": SAMPLE_RFP,
            "proposal_id": "",
        }

        result = await proposal_graph.ainvoke(initial_state)

    # Qualification
    assert "qualification" in result, "Missing qualification output"
    qual = result["qualification"]
    assert isinstance(qual["qualified"], bool)
    assert 0 <= qual["confidence"] <= 1
    assert qual["recommendation"] in {"go", "no-go", "conditional"}
    print(f"\n--- QUALIFICATION ---")
    print(f"Qualified: {qual['qualified']} (confidence: {qual['confidence']})")
    print(f"Recommendation: {qual['recommendation']}")
    print(f"Reasons: {qual.get('reasons', [])}")

    if not qual["qualified"]:
        print("RFP disqualified — pipeline stopped after qualification.")
        assert result["status"] == "disqualified"
        return

    # Solution
    assert "solution" in result, "Missing solution output"
    sol = result["solution"]
    assert isinstance(sol["approach"], str) and len(sol["approach"]) > 50
    assert isinstance(sol["staffing"], list) and len(sol["staffing"]) > 0
    assert all("role" in s and "hours" in s for s in sol["staffing"])
    print(f"\n--- SOLUTION ---")
    print(f"Tech stack: {sol.get('technology_stack', [])}")
    print(f"Staffing: {len(sol['staffing'])} roles")
    print(f"Confidence: {sol['confidence']}")

    # Compliance
    assert "compliance" in result, "Missing compliance output"
    comp = result["compliance"]
    assert isinstance(comp["narrative"], str) and len(comp["narrative"]) > 50
    assert isinstance(comp["forms_checklist"], list)
    print(f"\n--- COMPLIANCE ---")
    print(f"Forms: {len(comp['forms_checklist'])} items")
    print(f"Certs cited: {comp.get('certifications_cited', [])}")
    print(f"Flags: {comp.get('flags', [])}")

    # Cost
    assert "cost" in result, "Missing cost output"
    cost = result["cost"]
    assert isinstance(cost["total"], (int, float)) and cost["total"] > 0
    assert isinstance(cost["labor_costs"], dict)
    print(f"\n--- COST ---")
    print(f"Total: ${cost['total']:,.2f}")
    print(f"Labor subtotal: ${cost['labor_costs'].get('subtotal', 0):,.2f}")

    # Review
    assert "review" in result, "Missing review output"
    rev = result["review"]
    assert rev["recommendation"] in {"ready", "needs_revision", "major_issues"}
    assert 0 <= rev["quality_score"] <= 1
    print(f"\n--- REVIEW ---")
    print(f"Quality: {rev['quality_score']}")
    print(f"Recommendation: {rev['recommendation']}")
    print(f"Contradictions: {len(rev.get('contradictions', []))}")
    print(f"Missing sections: {rev.get('missing_sections', [])}")

    print(f"\n=== PIPELINE COMPLETE (status: {result['status']}) ===")
