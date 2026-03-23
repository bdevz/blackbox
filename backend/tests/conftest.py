import pytest


@pytest.fixture
def sample_rfp_brief():
    return {
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


@pytest.fixture
def sample_company_knowledge():
    return [
        {"type": "cert", "key": "iso-27001", "value": {"name": "ISO 27001", "status": "active", "expires": "2027-01-01"}},
        {"type": "certification", "key": "cmmi-3", "value": {"name": "CMMI Level 3", "status": "active"}},
        {"type": "capability", "key": "cloud-migration", "value": {"name": "Cloud Migration", "years": 8, "projects": 45}},
        {"type": "capability", "key": "mainframe-modernization", "value": {"name": "Mainframe Modernization", "years": 5, "projects": 12}},
        {"type": "reference", "key": "ohio-dot", "value": {"client": "Ohio DOT", "project": "Network Upgrade", "year": 2025, "value": 1800000}},
        {"type": "ratecard", "key": "2026", "value": {
            "rates": {
                "Project Manager": {"hourly": 95, "daily": 760},
                "Senior Developer": {"hourly": 75, "daily": 600},
                "Developer": {"hourly": 55, "daily": 440},
                "QA Engineer": {"hourly": 50, "daily": 400},
                "Cloud Architect": {"hourly": 110, "daily": 880},
                "Business Analyst": {"hourly": 65, "daily": 520},
            }
        }},
        {"type": "boilerplate", "key": "eeo-statement", "value": {"text": "ConsultAdd is an Equal Opportunity Employer..."}},
        {"type": "boilerplate", "key": "non-collusion", "value": {"text": "The undersigned hereby certifies that this proposal is genuine and not collusive..."}},
    ]


@pytest.fixture
def sample_qualification_output():
    return {
        "qualified": True,
        "confidence": 0.85,
        "reasons": [
            "ISO 27001 certification active",
            "CMMI Level 3 certified",
            "8 years cloud migration experience exceeds 5-year minimum",
        ],
        "missing": [],
        "recommendation": "go",
    }


@pytest.fixture
def sample_solution_output():
    return {
        "approach": "## Technical Approach\n\nWe propose a phased migration...",
        "staffing_plan": "The project will be staffed with a dedicated team of 5...",
        "staffing": [
            {"role": "Project Manager", "hours": 960, "headcount": 1},
            {"role": "Cloud Architect", "hours": 480, "headcount": 1},
            {"role": "Senior Developer", "hours": 960, "headcount": 2},
            {"role": "Developer", "hours": 960, "headcount": 2},
            {"role": "QA Engineer", "hours": 960, "headcount": 1},
        ],
        "timeline": "12-month phased implementation...",
        "technology_stack": ["AWS", "Kubernetes", "Terraform", "Python", "PostgreSQL"],
        "confidence": 0.78,
    }


@pytest.fixture
def sample_compliance_output():
    return {
        "narrative": "## Compliance Narrative\n\nConsultAdd meets all mandatory requirements...",
        "forms_checklist": [
            {"form": "W-9", "status": "have"},
            {"form": "Ohio Vendor Registration", "status": "have"},
            {"form": "EEO Certificate", "status": "have"},
            {"form": "Non-Collusion Affidavit", "status": "need"},
        ],
        "certifications_cited": ["ISO 27001", "CMMI Level 3"],
        "flags": [],
        "confidence": 0.82,
    }


@pytest.fixture
def sample_cost_output():
    return {
        "labor_costs": {
            "roles": [
                {"title": "Project Manager", "rate": 95.0, "hours": 960, "headcount": 1, "total": 91200.0},
                {"title": "Cloud Architect", "rate": 110.0, "hours": 480, "headcount": 1, "total": 52800.0},
                {"title": "Senior Developer", "rate": 75.0, "hours": 960, "headcount": 2, "total": 144000.0},
                {"title": "Developer", "rate": 55.0, "hours": 960, "headcount": 2, "total": 105600.0},
                {"title": "QA Engineer", "rate": 50.0, "hours": 960, "headcount": 1, "total": 48000.0},
            ],
            "subtotal": 441600.0,
        },
        "other_costs": [
            {"item": "Cloud infrastructure (AWS)", "amount": 36000.0},
            {"item": "Licenses and tools", "amount": 12000.0},
        ],
        "total": 489600.0,
        "narrative": "## Cost Justification\n\nOur pricing reflects competitive India-based rates...",
        "confidence": 0.90,
    }


@pytest.fixture
def sample_review_output_needs_revision():
    return {
        "contradictions": [
            {
                "sections": ["solution", "cost"],
                "issue": "Staffing count mismatch: solution lists 7 people, cost has 5 roles",
                "severity": "high",
            },
            {
                "sections": ["solution", "compliance"],
                "issue": "Solution claims CMMI Level 5, compliance only cites Level 3",
                "severity": "medium",
            },
        ],
        "missing_sections": [],
        "formatting_issues": [],
        "quality_score": 0.52,
        "recommendation": "needs_revision",
        "confidence": 0.88,
    }


@pytest.fixture
def sample_review_output_ready():
    return {
        "contradictions": [],
        "missing_sections": [],
        "formatting_issues": [],
        "quality_score": 0.92,
        "recommendation": "ready",
        "confidence": 0.95,
    }


@pytest.fixture
def sample_competitor_intel():
    return [
        {
            "competitor_name": "Infosys",
            "past_contract_value": 2200000.0,
            "incumbent_years": 3,
        },
        {
            "competitor_name": "TCS",
            "past_contract_value": 1900000.0,
            "incumbent_years": 1,
        },
    ]
