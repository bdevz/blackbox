#!/usr/bin/env python
"""Seed CompanyKnowledge table with ConsultAdd data.

Usage: cd backend && python -m scripts.seed_knowledge
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.dialects.postgresql import insert
from app.models.database import SessionLocal, CompanyKnowledge

KNOWLEDGE = [
    # Certifications
    {"type": "cert", "key": "iso-27001", "value": {"name": "ISO 27001", "status": "active", "expires": "2027-01-01", "body": "BSI Group"}},
    {"type": "cert", "key": "ohio-registration", "value": {"name": "Ohio Business Registration", "status": "active", "state": "Ohio"}},
    {"type": "certification", "key": "cmmi-3", "value": {"name": "CMMI Level 3", "status": "active", "appraised": "2024-06-15"}},

    # Capabilities
    {"type": "capability", "key": "it-consulting", "value": {"name": "IT Consulting", "years": 12, "founded": 2014}},
    {"type": "capability", "key": "cloud-migration", "value": {"name": "Cloud Migration", "years": 8, "projects": 45}},
    {"type": "capability", "key": "mainframe-modernization", "value": {"name": "Mainframe Modernization", "years": 5, "projects": 12}},
    {"type": "capability", "key": "data-analytics", "value": {"name": "Data Analytics & BI", "years": 6, "projects": 30}},
    {"type": "capability", "key": "cybersecurity", "value": {"name": "Cybersecurity & Compliance", "years": 4, "projects": 18}},
    {"type": "capability", "key": "devops", "value": {"name": "DevOps & CI/CD", "years": 6, "projects": 35}},

    # References
    {"type": "reference", "key": "ohio-dot", "value": {"client": "Ohio DOT", "project": "Network Upgrade", "year": 2025, "value": 1800000, "contact": "procurement@dot.ohio.gov"}},
    {"type": "reference", "key": "indiana-fssa", "value": {"client": "Indiana FSSA", "project": "Eligibility System Modernization", "year": 2024, "value": 950000}},
    {"type": "reference", "key": "michigan-dtmb", "value": {"client": "Michigan DTMB", "project": "Cloud Infrastructure Migration", "year": 2024, "value": 1200000}},

    # Rate card
    {"type": "ratecard", "key": "2026", "value": {"rates": {
        "Project Manager": {"hourly": 95, "daily": 760},
        "Senior Developer": {"hourly": 75, "daily": 600},
        "Developer": {"hourly": 55, "daily": 440},
        "QA Engineer": {"hourly": 50, "daily": 400},
        "Cloud Architect": {"hourly": 110, "daily": 880},
        "Business Analyst": {"hourly": 65, "daily": 520},
        "Data Engineer": {"hourly": 80, "daily": 640},
        "DevOps Engineer": {"hourly": 85, "daily": 680},
        "Security Analyst": {"hourly": 90, "daily": 720},
        "Technical Writer": {"hourly": 45, "daily": 360},
    }}},

    # Boilerplate
    {"type": "boilerplate", "key": "eeo-statement", "value": {"text": "ConsultAdd is an Equal Opportunity Employer committed to fostering an inclusive environment. We do not discriminate on the basis of race, color, religion, sex, national origin, age, disability, veteran status, sexual orientation, gender identity, or any other legally protected characteristic."}},
    {"type": "boilerplate", "key": "non-collusion", "value": {"text": "The undersigned hereby certifies that this proposal is genuine and not collusive or made in the interest of any person not herein named, and that the proposer has not directly or indirectly induced or solicited any other proposer to submit a sham proposal, or any other person, firm, or corporation to refrain from proposing."}},
    {"type": "boilerplate", "key": "transmittal", "value": {"text": "ConsultAdd Inc. is pleased to submit this proposal in response to the referenced Request for Proposal. We have carefully reviewed all requirements and are confident in our ability to deliver the requested services within the specified timeline and budget. This proposal is valid for 120 days from the date of submission."}},
]


def seed():
    db = SessionLocal()
    try:
        for item in KNOWLEDGE:
            stmt = insert(CompanyKnowledge).values(
                type=item["type"],
                key=item["key"],
                value=item["value"],
            ).on_conflict_do_update(
                constraint="uq_knowledge_type_key",
                set_={"value": item["value"]},
            )
            db.execute(stmt)
        db.commit()
        print(f"Seeded {len(KNOWLEDGE)} knowledge items")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
