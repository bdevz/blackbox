# Wave 2: Specialist Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 5 specialist agents (Qualify, Solution, Compliance, Cost, Review) and wire them into the LangGraph orchestrator with parallel Solution+Compliance fan-out.

**Architecture:** Smart agents with thin orchestrator. Each agent inherits `BaseAgent`, owns its DB context injection, prompt construction, and output validation. Orchestrator nodes are 3-5 line wrappers. Solution and Compliance run concurrently via `asyncio.gather` in a single fan-out node.

**Tech Stack:** Python 3.11+, FastAPI, Anthropic AsyncAnthropic SDK, Voyage embeddings, LangGraph, SQLAlchemy, Celery, PostgreSQL + pgvector

**Spec:** `docs/superpowers/specs/2026-03-22-wave2-agents-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Edit | `backend/app/agents/base.py` | Switch to AsyncAnthropic, add max_tokens class attr |
| Edit | `backend/app/config.py` | Add voyage_model, voyage_api_key |
| Edit | `backend/app/models/database.py` | Add `failed` to ProposalStatus, fix Vector dim |
| Edit | `backend/pyproject.toml` | Add voyageai, pytest deps |
| Create | `backend/app/agents/qualification.py` | QualificationAgent |
| Create | `backend/app/agents/solution.py` | SolutionAgent |
| Create | `backend/app/agents/compliance.py` | ComplianceAgent |
| Create | `backend/app/agents/cost.py` | CostAgent + calculate_costs() |
| Create | `backend/app/agents/review.py` | ReviewAgent |
| Edit | `backend/app/agents/orchestrator.py` | Async nodes, parallel fan-out, proposal_id |
| Edit | `backend/app/agents/__init__.py` | Export all agents |
| Edit | `backend/app/workers/tasks.py` | Wire orchestrator into Celery task |
| Create | `backend/tests/conftest.py` | Shared fixtures |
| Create | `backend/tests/test_qualification.py` | QualificationAgent unit tests |
| Create | `backend/tests/test_solution.py` | SolutionAgent unit tests |
| Create | `backend/tests/test_compliance.py` | ComplianceAgent unit tests |
| Create | `backend/tests/test_cost.py` | CostAgent unit tests + calculate_costs() |
| Create | `backend/tests/test_review.py` | ReviewAgent unit tests |
| Create | `backend/tests/test_orchestrator.py` | Orchestrator integration tests |

---

### Task 1: Foundation — BaseAgent, Config, Schema, Dependencies

**Files:**
- Modify: `backend/app/agents/base.py:7,28,33,57-59`
- Modify: `backend/app/config.py:19-20`
- Modify: `backend/app/models/database.py:27-34,150`
- Modify: `backend/pyproject.toml:6-32`

- [ ] **Step 1: Update pyproject.toml — add voyageai and test deps**

Add `voyageai` and `pytest` to dependencies in `backend/pyproject.toml`:

```toml
[project]
name = "blackbox"
version = "0.1.0"
description = "AI-powered RFP proposal generation platform"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0",
    "alembic>=1.14",
    "psycopg2-binary>=2.9",
    "pgvector>=0.3",
    "celery[redis]>=5.4",
    "redis>=5.0",
    "httpx>=0.28",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "python-dotenv>=1.0",
    "python-multipart>=0.0.18",
    "langchain>=0.3",
    "langgraph>=0.2",
    "langchain-anthropic>=0.3",
    "anthropic>=0.42",
    "voyageai>=0.3",
    "sse-starlette>=2.0",
    "pymupdf>=1.25",
    "pytesseract>=0.3",
    "python-docx>=1.1",
    "openpyxl>=3.1",
    "slack-bolt>=1.21",
    "slack-sdk>=3.34",
    "weasyprint>=63",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Update config.py — add Voyage settings**

Add two fields to `Settings` class in `backend/app/config.py`, after `s3_endpoint`:

```python
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3-large"
```

- [ ] **Step 3: Update database.py — add `failed` status and fix Vector dimension**

In `backend/app/models/database.py`, add `failed` to `ProposalStatus` enum:

```python
class ProposalStatus(str, PyEnum):
    queued = "queued"
    generating = "generating"
    draft = "draft"
    reviewing = "reviewing"
    submitted = "submitted"
    won = "won"
    lost = "lost"
    failed = "failed"
```

Change `ProposalEmbedding.embedding` from `Vector(1536)` to `Vector(1024)`:

```python
    embedding = Column(Vector(1024))
```

- [ ] **Step 4: Update base.py — AsyncAnthropic + max_tokens attr**

Replace the full content of `backend/app/agents/base.py`:

```python
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from app.config import settings
from app.models.database import SessionLocal, AgentRun


@dataclass
class AgentResult:
    output: dict
    confidence: float
    model: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class BaseAgent(ABC):
    agent_type: str = "base"
    model: str = "claude-sonnet-4-20250514"
    max_retries: int = 2
    max_tokens: int = 4096
    temperature: float = 0.3

    def __init__(self, model: str = None):
        if model:
            self.model = model
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    @abstractmethod
    def build_prompt(self, context: dict) -> tuple[str, str]:
        """Return (system_prompt, user_prompt)."""
        ...

    @abstractmethod
    def validate_output(self, raw: str) -> dict:
        """Parse and validate LLM output. Raise ValueError if invalid."""
        ...

    def inject_context(self, context: dict, db=None) -> dict:
        """Override to inject agent-specific data from DB."""
        return context

    async def run(self, context: dict, proposal_id: str = None) -> AgentResult:
        db = SessionLocal()
        try:
            context = self.inject_context(context, db)
            system_prompt, user_prompt = self.build_prompt(context)
            prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]

            start = time.monotonic()
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            raw_text = response.content[0].text
            output = self.validate_output(raw_text)

            result = AgentResult(
                output=output,
                confidence=output.get("confidence", 0.0),
                model=self.model,
                prompt_hash=prompt_hash,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                duration_ms=duration_ms,
            )

            if proposal_id:
                run = AgentRun(
                    proposal_id=proposal_id,
                    agent_type=self.agent_type,
                    model_used=self.model,
                    prompt_hash=prompt_hash,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    duration_ms=duration_ms,
                    status="ok",
                )
                db.add(run)
                db.commit()

            return result

        except Exception as e:
            if proposal_id:
                run = AgentRun(
                    proposal_id=proposal_id,
                    agent_type=self.agent_type,
                    model_used=self.model,
                    prompt_hash="error",
                    status="error",
                    error_message=str(e),
                )
                db.add(run)
                db.commit()
            raise
        finally:
            db.close()

    async def retry(self, context: dict, error: str, proposal_id: str = None) -> AgentResult:
        context["_retry_error"] = error
        context["_retry_instruction"] = f"Previous attempt failed: {error}. Adjust your approach."
        return await self.run(context, proposal_id)
```

Key changes: `Anthropic` → `AsyncAnthropic`, `self.client.messages.create` → `await self.client.messages.create`, `max_tokens=4096` → `max_tokens=self.max_tokens`, added `max_tokens: int = 4096` class attribute.

- [ ] **Step 5: Commit foundation changes**

```bash
git add backend/pyproject.toml backend/app/config.py backend/app/models/database.py backend/app/agents/base.py
git commit -m "feat: foundation for Wave 2 — AsyncAnthropic, max_tokens attr, Voyage config, failed status"
```

---

### Task 2: QualificationAgent + Tests

**Files:**
- Create: `backend/app/agents/qualification.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_qualification.py`

- [ ] **Step 1: Create shared test fixtures**

Create `backend/tests/conftest.py`:

```python
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
```

- [ ] **Step 2: Write QualificationAgent failing tests**

Create `backend/tests/test_qualification.py`:

```python
import json

import pytest

from app.agents.qualification import QualificationAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = QualificationAgent.__new__(QualificationAgent)

    def test_valid_output(self, sample_qualification_output):
        raw = json.dumps(sample_qualification_output)
        result = self.agent.validate_output(raw)
        assert result["qualified"] is True
        assert result["confidence"] == 0.85
        assert result["recommendation"] == "go"
        assert len(result["reasons"]) == 3
        assert isinstance(result["missing"], list)

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_qualified_field(self):
        raw = json.dumps({"confidence": 0.5, "reasons": [], "missing": [], "recommendation": "go"})
        with pytest.raises(ValueError, match="qualified"):
            self.agent.validate_output(raw)

    def test_missing_recommendation_field(self):
        raw = json.dumps({"qualified": True, "confidence": 0.5, "reasons": [], "missing": []})
        with pytest.raises(ValueError, match="recommendation"):
            self.agent.validate_output(raw)

    def test_invalid_recommendation_value(self):
        raw = json.dumps({
            "qualified": True, "confidence": 0.5, "reasons": [], "missing": [],
            "recommendation": "maybe",
        })
        with pytest.raises(ValueError, match="recommendation"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "qualified": True, "confidence": 1.5, "reasons": [], "missing": [],
            "recommendation": "go",
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)

    def test_nogo_output(self):
        raw = json.dumps({
            "qualified": False, "confidence": 0.9, "reasons": ["Missing certs"],
            "missing": ["SOC 2 Type II"], "recommendation": "no-go",
        })
        result = self.agent.validate_output(raw)
        assert result["qualified"] is False
        assert result["missing"] == ["SOC 2 Type II"]


class TestBuildPrompt:
    def setup_method(self):
        self.agent = QualificationAgent.__new__(QualificationAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief):
        context = {"rfp_brief": sample_rfp_brief}
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief):
        context = {"rfp_brief": sample_rfp_brief}
        system, _ = self.agent.build_prompt(context)
        assert "qualification" in system.lower()
        assert "ConsultAdd" in system

    def test_user_prompt_includes_rfp_brief(self, sample_rfp_brief):
        context = {"rfp_brief": sample_rfp_brief}
        _, user = self.agent.build_prompt(context)
        assert sample_rfp_brief["title"] in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert QualificationAgent.agent_type == "qualify"

    def test_model(self):
        assert QualificationAgent.model == "claude-haiku-4-5-20251001"

    def test_temperature(self):
        assert QualificationAgent.temperature == 0.1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_qualification.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.qualification'`

- [ ] **Step 4: Implement QualificationAgent**

Create `backend/app/agents/qualification.py`:

```python
import json

from app.agents.base import BaseAgent
from app.models.database import SessionLocal, CompanyKnowledge


CONSULTADD_CONTEXT = """ConsultAdd is a 30-person IT consulting company based in India.
- Targets state and local government RFPs only (no federal)
- Wins on competitive cost, not boutique quality
- Current win rate: 3-4% (volume strategy — more at-bats = more wins)
- Goal: 10x proposal volume (100 → 1,000 RFPs/month) with same headcount"""


class QualificationAgent(BaseAgent):
    agent_type = "qualify"
    model = "claude-haiku-4-5-20251001"
    temperature = 0.1

    def inject_context(self, context: dict, db=None) -> dict:
        if db is None:
            return context
        rows = (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.type.in_(["cert", "certification", "capability"]))
            .all()
        )
        context["company_qualifications"] = [
            {"type": r.type, "key": r.key, "value": r.value} for r in rows
        ]
        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a government RFP qualification classifier for ConsultAdd.

{CONSULTADD_CONTEXT}

Your job: determine whether ConsultAdd should bid on this RFP.

Process:
1. DETERMINISTIC CHECKS FIRST — match required certifications, state registrations, revenue thresholds, years in business, and category against ConsultAdd's actual qualifications.
2. LLM JUDGMENT SECOND — assess soft factors like scope fit, team capacity, and competitive positioning.
3. Flag anything missing but potentially acquirable before the deadline.

Respond with ONLY valid JSON (no markdown fences):
{{
  "qualified": true/false,
  "confidence": 0.0-1.0,
  "reasons": ["reason1", "reason2"],
  "missing": ["missing_item1"],
  "recommendation": "go" | "no-go" | "conditional"
}}"""

        quals = context.get("company_qualifications", [])
        quals_text = json.dumps(quals, indent=2) if quals else "No qualification data available."

        rfp_brief = context.get("rfp_brief", {})
        rfp_text = json.dumps(rfp_brief, indent=2)

        user = f"""## RFP Brief
{rfp_text}

## ConsultAdd's Current Qualifications
{quals_text}

Evaluate whether ConsultAdd should bid on this RFP."""

        return system, user

    def validate_output(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON output from qualification agent")

        required = ["qualified", "confidence", "reasons", "missing", "recommendation"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["qualified"], bool):
            raise ValueError("'qualified' must be a boolean")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        if not isinstance(data["reasons"], list):
            raise ValueError("'reasons' must be a list")

        if not isinstance(data["missing"], list):
            raise ValueError("'missing' must be a list")

        valid_recs = {"go", "no-go", "conditional"}
        if data["recommendation"] not in valid_recs:
            raise ValueError(f"'recommendation' must be one of {valid_recs}")

        return data
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_qualification.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_qualification.py backend/app/agents/qualification.py
git commit -m "feat: add QualificationAgent with unit tests"
```

---

### Task 3: SolutionAgent + Tests

**Files:**
- Create: `backend/app/agents/solution.py`
- Create: `backend/tests/test_solution.py`

- [ ] **Step 1: Write SolutionAgent failing tests**

Create `backend/tests/test_solution.py`:

```python
import json

import pytest

from app.agents.solution import SolutionAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = SolutionAgent.__new__(SolutionAgent)

    def test_valid_output(self, sample_solution_output):
        raw = json.dumps(sample_solution_output)
        result = self.agent.validate_output(raw)
        assert "approach" in result
        assert isinstance(result["staffing"], list)
        assert len(result["staffing"]) == 5
        assert result["staffing"][0]["role"] == "Project Manager"

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_approach(self):
        raw = json.dumps({
            "staffing_plan": "x", "staffing": [], "timeline": "x",
            "technology_stack": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="approach"):
            self.agent.validate_output(raw)

    def test_missing_staffing_array(self):
        raw = json.dumps({
            "approach": "x", "staffing_plan": "x", "timeline": "x",
            "technology_stack": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="staffing"):
            self.agent.validate_output(raw)

    def test_staffing_entry_missing_role(self):
        raw = json.dumps({
            "approach": "x", "staffing_plan": "x",
            "staffing": [{"hours": 100, "headcount": 1}],
            "timeline": "x", "technology_stack": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="role"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "approach": "x", "staffing_plan": "x", "staffing": [],
            "timeline": "x", "technology_stack": [], "confidence": -0.1,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)


class TestBuildPrompt:
    def setup_method(self):
        self.agent = SolutionAgent.__new__(SolutionAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
        }
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        system, _ = self.agent.build_prompt(context)
        assert "technical" in system.lower()
        assert "ConsultAdd" in system

    def test_user_prompt_includes_rfp_and_qualification(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        _, user = self.agent.build_prompt(context)
        assert sample_rfp_brief["title"] in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert SolutionAgent.agent_type == "solution"

    def test_model(self):
        assert SolutionAgent.model == "claude-opus-4-6"

    def test_temperature(self):
        assert SolutionAgent.temperature == 0.4

    def test_max_tokens(self):
        assert SolutionAgent.max_tokens == 8192
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_solution.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SolutionAgent**

Create `backend/app/agents/solution.py`:

```python
import json
import logging

from app.agents.base import BaseAgent
from app.config import settings
from app.models.database import SessionLocal, CompanyKnowledge, ProposalEmbedding

logger = logging.getLogger(__name__)

CONSULTADD_CONTEXT = """ConsultAdd is a 30-person IT consulting company based in India.
- Targets state and local government RFPs only (no federal)
- Wins on competitive cost, not boutique quality
- Current win rate: 3-4% (volume strategy — more at-bats = more wins)
- Goal: 10x proposal volume (100 → 1,000 RFPs/month) with same headcount"""


class SolutionAgent(BaseAgent):
    agent_type = "solution"
    model = "claude-opus-4-6"
    temperature = 0.4
    max_tokens = 8192

    def _find_similar_proposals(self, rfp_brief: dict, db) -> list[dict]:
        """Query pgvector for similar past proposals using Voyage embeddings."""
        try:
            import voyageai

            vo = voyageai.Client(api_key=settings.voyage_api_key)
            brief_text = json.dumps(rfp_brief)
            embedding_result = vo.embed([brief_text], model=settings.voyage_model)
            query_vector = embedding_result.embeddings[0]

            results = (
                db.query(ProposalEmbedding)
                .order_by(ProposalEmbedding.embedding.cosine_distance(query_vector))
                .limit(3)
                .all()
            )
            return [
                {"section": r.section, "proposal_id": str(r.proposal_id)}
                for r in results
            ]
        except Exception as e:
            logger.warning(f"Similar proposal lookup failed (expected if no embeddings exist): {e}")
            return []

    def inject_context(self, context: dict, db=None) -> dict:
        if db is None:
            return context

        rows = (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.type.in_(["capability", "reference", "ratecard"]))
            .all()
        )
        context["company_knowledge"] = [
            {"type": r.type, "key": r.key, "value": r.value} for r in rows
        ]

        rfp_brief = context.get("rfp_brief", {})
        context["similar_proposals"] = self._find_similar_proposals(rfp_brief, db)

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a technical proposal writer for ConsultAdd.

{CONSULTADD_CONTEXT}

Your job: write the technical solution section of an RFP response.

Rules:
- Ground EVERYTHING in ConsultAdd's actual capabilities and past wins.
- NEVER claim capabilities ConsultAdd does not have.
- Reference specific past projects when available.
- Include a structured staffing array for downstream cost calculation.

Respond with ONLY valid JSON (no markdown fences):
{{
  "approach": "markdown string — full technical approach",
  "staffing_plan": "narrative staffing description",
  "staffing": [
    {{"role": "Title", "hours": 960, "headcount": 1}}  // hours = per-person hours
  ],
  "timeline": "implementation timeline description",
  "technology_stack": ["Tech1", "Tech2"],
  "confidence": 0.0-1.0
}}"""

        rfp_brief = context.get("rfp_brief", {})
        qualification = context.get("qualification", {})
        knowledge = context.get("company_knowledge", [])
        similar = context.get("similar_proposals", [])

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Qualification Assessment
{json.dumps(qualification, indent=2)}

## ConsultAdd Capabilities & References
{json.dumps(knowledge, indent=2)}

## Similar Past Proposals
{json.dumps(similar, indent=2) if similar else "No similar proposals found."}

Write the technical solution for this RFP."""

        return system, user

    def validate_output(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON output from solution agent")

        required = ["approach", "staffing_plan", "staffing", "timeline", "technology_stack", "confidence"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["approach"], str) or not data["approach"].strip():
            raise ValueError("'approach' must be a non-empty string")

        if not isinstance(data["staffing"], list):
            raise ValueError("'staffing' must be a list")

        for i, entry in enumerate(data["staffing"]):
            if not isinstance(entry, dict):
                raise ValueError(f"staffing[{i}] must be a dict")
            for key in ["role", "hours", "headcount"]:
                if key not in entry:
                    raise ValueError(f"staffing[{i}] missing required field: {key}")

        if not isinstance(data["technology_stack"], list):
            raise ValueError("'technology_stack' must be a list")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_solution.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/solution.py backend/tests/test_solution.py
git commit -m "feat: add SolutionAgent with pgvector similarity search and unit tests"
```

---

### Task 4: ComplianceAgent + Tests

**Files:**
- Create: `backend/app/agents/compliance.py`
- Create: `backend/tests/test_compliance.py`

- [ ] **Step 1: Write ComplianceAgent failing tests**

Create `backend/tests/test_compliance.py`:

```python
import json

import pytest

from app.agents.compliance import ComplianceAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = ComplianceAgent.__new__(ComplianceAgent)

    def test_valid_output(self, sample_compliance_output):
        raw = json.dumps(sample_compliance_output)
        result = self.agent.validate_output(raw)
        assert "narrative" in result
        assert len(result["forms_checklist"]) == 4
        assert result["forms_checklist"][0]["status"] in ("have", "need", "na")

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_narrative(self):
        raw = json.dumps({
            "forms_checklist": [], "certifications_cited": [],
            "flags": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="narrative"):
            self.agent.validate_output(raw)

    def test_invalid_form_status(self):
        raw = json.dumps({
            "narrative": "x",
            "forms_checklist": [{"form": "W-9", "status": "maybe"}],
            "certifications_cited": [], "flags": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="status"):
            self.agent.validate_output(raw)

    def test_missing_forms_checklist(self):
        raw = json.dumps({
            "narrative": "x", "certifications_cited": [],
            "flags": [], "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="forms_checklist"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "narrative": "x", "forms_checklist": [],
            "certifications_cited": [], "flags": [], "confidence": 2.0,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)


class TestBuildPrompt:
    def setup_method(self):
        self.agent = ComplianceAgent.__new__(ComplianceAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        system, _ = self.agent.build_prompt(context)
        assert "compliance" in system.lower()
        assert "ConsultAdd" in system

    def test_user_prompt_includes_rfp(self, sample_rfp_brief, sample_qualification_output):
        context = {"rfp_brief": sample_rfp_brief, "qualification": sample_qualification_output}
        _, user = self.agent.build_prompt(context)
        assert sample_rfp_brief["title"] in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert ComplianceAgent.agent_type == "comply"

    def test_model(self):
        assert ComplianceAgent.model == "claude-opus-4-6"

    def test_temperature(self):
        assert ComplianceAgent.temperature == 0.2

    def test_max_tokens(self):
        assert ComplianceAgent.max_tokens == 8192
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_compliance.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ComplianceAgent**

Create `backend/app/agents/compliance.py`:

```python
import json

from app.agents.base import BaseAgent
from app.models.database import CompanyKnowledge


CONSULTADD_CONTEXT = """ConsultAdd is a 30-person IT consulting company based in India.
- Targets state and local government RFPs only (no federal)
- Wins on competitive cost, not boutique quality
- Current win rate: 3-4% (volume strategy — more at-bats = more wins)
- Goal: 10x proposal volume (100 → 1,000 RFPs/month) with same headcount"""


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_compliance.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/compliance.py backend/tests/test_compliance.py
git commit -m "feat: add ComplianceAgent with boilerplate injection and unit tests"
```

---

### Task 5: CostAgent + Tests

**Files:**
- Create: `backend/app/agents/cost.py`
- Create: `backend/tests/test_cost.py`

- [ ] **Step 1: Write CostAgent failing tests**

Create `backend/tests/test_cost.py`:

```python
import json

import pytest

from app.agents.cost import CostAgent


class TestCalculateCosts:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_basic_calculation(self, sample_solution_output, sample_company_knowledge):
        rate_card = next(
            k["value"] for k in sample_company_knowledge if k["type"] == "ratecard"
        )
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card["rates"],
        )
        assert result["labor_costs"]["subtotal"] == 441600.0
        pm = result["labor_costs"]["roles"][0]
        assert pm["title"] == "Project Manager"
        assert pm["rate"] == 95.0
        assert pm["hours"] == 960
        assert pm["total"] == 91200.0
        assert result["missing_rates"] == []

    def test_missing_role_in_rate_card(self):
        result = CostAgent.__new__(CostAgent).calculate_costs(
            staffing=[{"role": "Data Scientist", "hours": 500, "headcount": 1}],
            rate_card={"Developer": {"hourly": 55}},
        )
        assert "Data Scientist" in result["missing_rates"]
        ds_role = result["labor_costs"]["roles"][0]
        assert ds_role["rate"] == 0
        assert ds_role["total"] == 0

    def test_empty_staffing(self):
        result = CostAgent.__new__(CostAgent).calculate_costs(
            staffing=[],
            rate_card={"Developer": {"hourly": 55}},
        )
        assert result["labor_costs"]["subtotal"] == 0
        assert result["labor_costs"]["roles"] == []

    def test_margin_applied(self, sample_solution_output, sample_company_knowledge):
        rate_card = next(
            k["value"] for k in sample_company_knowledge if k["type"] == "ratecard"
        )
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card["rates"],
            margin=0.15,
        )
        expected_with_margin = 441600.0 * 1.15
        assert abs(result["total_with_margin"] - expected_with_margin) < 0.01


class TestValidateOutput:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_valid_output(self, sample_cost_output):
        raw = json.dumps(sample_cost_output)
        result = self.agent.validate_output(raw)
        assert result["total"] == 489600.0
        assert len(result["labor_costs"]["roles"]) == 5

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_labor_costs(self):
        raw = json.dumps({
            "other_costs": [], "total": 0, "narrative": "x", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="labor_costs"):
            self.agent.validate_output(raw)

    def test_missing_total(self):
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [], "narrative": "x", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="total"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [], "total": 0, "narrative": "x", "confidence": 1.5,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)

    def test_rejects_divergent_subtotal(self):
        agent = CostAgent.__new__(CostAgent)
        agent._computed_costs = {"labor_costs": {"subtotal": 100000.0}}
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 200000.0},
            "other_costs": [], "total": 200000.0, "narrative": "x", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="diverges"):
            agent.validate_output(raw)

    def test_accepts_matching_subtotal(self):
        agent = CostAgent.__new__(CostAgent)
        agent._computed_costs = {"labor_costs": {"subtotal": 441600.0}}
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 441600.0},
            "other_costs": [], "total": 489600.0, "narrative": "x", "confidence": 0.5,
        })
        result = agent.validate_output(raw)
        assert result["labor_costs"]["subtotal"] == 441600.0


class TestBuildPrompt:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_returns_tuple_of_strings(self, sample_rfp_brief, sample_solution_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "solution": sample_solution_output,
            "computed_costs": {
                "labor_costs": {"roles": [], "subtotal": 0},
                "missing_rates": [],
                "total_with_margin": 0,
            },
        }
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(self, sample_rfp_brief, sample_solution_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "solution": sample_solution_output,
            "computed_costs": {"labor_costs": {"roles": [], "subtotal": 0}, "missing_rates": [], "total_with_margin": 0},
        }
        system, _ = self.agent.build_prompt(context)
        assert "cost" in system.lower()
        assert "ConsultAdd" in system


class TestAgentAttributes:
    def test_agent_type(self):
        assert CostAgent.agent_type == "cost"

    def test_model(self):
        assert CostAgent.model == "claude-sonnet-4-6"

    def test_temperature(self):
        assert CostAgent.temperature == 0.2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_cost.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CostAgent**

Create `backend/app/agents/cost.py`:

```python
import json

from app.agents.base import BaseAgent
from app.models.database import CompanyKnowledge


CONSULTADD_CONTEXT = """ConsultAdd is a 30-person IT consulting company based in India.
- Targets state and local government RFPs only (no federal)
- Wins on competitive cost, not boutique quality
- Cost is why ConsultAdd wins — competitive India-based pricing is the edge
- Current win rate: 3-4% (volume strategy — more at-bats = more wins)
- Goal: 10x proposal volume (100 → 1,000 RFPs/month) with same headcount"""

DEFAULT_MARGIN = 0.15


class CostAgent(BaseAgent):
    agent_type = "cost"
    model = "claude-sonnet-4-6"
    temperature = 0.2

    def calculate_costs(
        self,
        staffing: list[dict],
        rate_card: dict,
        margin: float = DEFAULT_MARGIN,
    ) -> dict:
        """Deterministic cost calculation: rate * hours * headcount. No LLM involved."""
        roles = []
        missing_rates = []
        subtotal = 0.0

        for entry in staffing:
            role = entry["role"]
            hours = entry["hours"]
            headcount = entry.get("headcount", 1)

            rate_info = rate_card.get(role)
            if rate_info is None:
                missing_rates.append(role)
                hourly_rate = 0.0
            else:
                hourly_rate = float(rate_info.get("hourly", rate_info) if isinstance(rate_info, dict) else rate_info)

            total = hourly_rate * hours * headcount
            subtotal += total
            roles.append({
                "title": role,
                "rate": hourly_rate,
                "hours": hours,
                "headcount": headcount,
                "total": total,
            })

        return {
            "labor_costs": {"roles": roles, "subtotal": subtotal},
            "missing_rates": missing_rates,
            "total_with_margin": subtotal * (1 + margin),
        }

    def inject_context(self, context: dict, db=None) -> dict:
        if db is None:
            return context

        rows = (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.type.in_(["ratecard", "rate"]))
            .all()
        )

        rate_card = {}
        for r in rows:
            if r.type == "ratecard" and isinstance(r.value, dict):
                rate_card.update(r.value.get("rates", {}))
            elif r.type == "rate" and isinstance(r.value, dict):
                rate_card[r.key] = r.value

        context["rate_card"] = rate_card

        solution = context.get("solution", {})
        staffing = solution.get("staffing", [])
        computed = self.calculate_costs(
            staffing=staffing,
            rate_card=rate_card,
        )
        context["computed_costs"] = computed
        # Store on self for validate_output to cross-check LLM numbers
        self._computed_costs = computed

        return context

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = f"""You are a cost proposal assembler for ConsultAdd.

{CONSULTADD_CONTEXT}

Your job: write ONLY the cost justification narrative. The numbers have already been calculated deterministically — do NOT change them.

You will receive:
1. The RFP brief
2. The solution's staffing plan
3. Pre-computed cost breakdown (use these exact numbers)

Write a compelling narrative that justifies the pricing. Emphasize ConsultAdd's cost advantage from India-based delivery.

Respond with ONLY valid JSON (no markdown fences):
{{
  "labor_costs": {{
    "roles": [
      {{"title": "Role", "rate": 95.0, "hours": 960, "total": 91200.0}}
    ],
    "subtotal": 441600.0
  }},
  "other_costs": [
    {{"item": "Description", "amount": 5000.0}}
  ],
  "total": 446600.0,
  "narrative": "markdown string — cost justification",
  "confidence": 0.0-1.0
}}

IMPORTANT: The labor_costs roles, rates, hours, totals, and subtotal MUST match the pre-computed values exactly. You may add other_costs for non-labor items."""

        rfp_brief = context.get("rfp_brief", {})
        solution = context.get("solution", {})
        computed = context.get("computed_costs", {})

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Solution Staffing Plan
{json.dumps(solution.get("staffing", []), indent=2)}

## Pre-Computed Cost Breakdown (USE THESE EXACT NUMBERS)
{json.dumps(computed, indent=2)}

Write the cost justification narrative. Use the pre-computed numbers exactly."""

        return system, user

    def validate_output(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON output from cost agent")

        required = ["labor_costs", "other_costs", "total", "narrative", "confidence"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        lc = data["labor_costs"]
        if not isinstance(lc, dict) or "roles" not in lc or "subtotal" not in lc:
            raise ValueError("'labor_costs' must have 'roles' and 'subtotal'")

        if not isinstance(lc["roles"], list):
            raise ValueError("'labor_costs.roles' must be a list")

        for i, role in enumerate(lc["roles"]):
            for key in ["title", "rate", "hours", "total"]:
                if key not in role:
                    raise ValueError(f"labor_costs.roles[{i}] missing '{key}'")

        if not isinstance(data["other_costs"], list):
            raise ValueError("'other_costs' must be a list")

        if not isinstance(data["total"], (int, float)):
            raise ValueError("'total' must be a number")

        if not isinstance(data["narrative"], str) or not data["narrative"].strip():
            raise ValueError("'narrative' must be a non-empty string")

        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("'confidence' must be a float between 0 and 1")

        # Cross-check LLM numbers against deterministic calculation
        computed = getattr(self, "_computed_costs", None)
        if computed is not None:
            expected_subtotal = computed["labor_costs"]["subtotal"]
            if abs(lc["subtotal"] - expected_subtotal) > 0.01:
                raise ValueError(
                    f"LLM labor subtotal ({lc['subtotal']}) diverges from "
                    f"computed value ({expected_subtotal})"
                )

        return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_cost.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/cost.py backend/tests/test_cost.py
git commit -m "feat: add CostAgent with deterministic cost calculation and unit tests"
```

---

### Task 6: ReviewAgent + Tests

**Files:**
- Create: `backend/app/agents/review.py`
- Create: `backend/tests/test_review.py`

- [ ] **Step 1: Write ReviewAgent failing tests**

Create `backend/tests/test_review.py`:

```python
import json

import pytest

from app.agents.review import ReviewAgent


class TestValidateOutput:
    def setup_method(self):
        self.agent = ReviewAgent.__new__(ReviewAgent)

    def test_valid_output(self):
        raw = json.dumps({
            "contradictions": [
                {"sections": ["solution", "cost"], "issue": "Staffing count mismatch", "severity": "high"}
            ],
            "missing_sections": [],
            "formatting_issues": ["Inconsistent header levels"],
            "quality_score": 0.75,
            "recommendation": "needs_revision",
            "confidence": 0.85,
        })
        result = self.agent.validate_output(raw)
        assert len(result["contradictions"]) == 1
        assert result["recommendation"] == "needs_revision"

    def test_clean_review(self):
        raw = json.dumps({
            "contradictions": [],
            "missing_sections": [],
            "formatting_issues": [],
            "quality_score": 0.92,
            "recommendation": "ready",
            "confidence": 0.90,
        })
        result = self.agent.validate_output(raw)
        assert result["recommendation"] == "ready"

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            self.agent.validate_output("not json")

    def test_missing_contradictions(self):
        raw = json.dumps({
            "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "ready", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="contradictions"):
            self.agent.validate_output(raw)

    def test_invalid_recommendation(self):
        raw = json.dumps({
            "contradictions": [], "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "maybe", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="recommendation"):
            self.agent.validate_output(raw)

    def test_invalid_severity(self):
        raw = json.dumps({
            "contradictions": [
                {"sections": ["a", "b"], "issue": "x", "severity": "critical"}
            ],
            "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "ready", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="severity"):
            self.agent.validate_output(raw)

    def test_quality_score_out_of_range(self):
        raw = json.dumps({
            "contradictions": [], "missing_sections": [], "formatting_issues": [],
            "quality_score": 1.5, "recommendation": "ready", "confidence": 0.5,
        })
        with pytest.raises(ValueError, match="quality_score"):
            self.agent.validate_output(raw)

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "contradictions": [], "missing_sections": [], "formatting_issues": [],
            "quality_score": 0.5, "recommendation": "ready", "confidence": -0.1,
        })
        with pytest.raises(ValueError, match="confidence"):
            self.agent.validate_output(raw)


class TestBuildPrompt:
    def setup_method(self):
        self.agent = ReviewAgent.__new__(ReviewAgent)

    def test_returns_tuple_of_strings(
        self, sample_rfp_brief, sample_qualification_output,
        sample_solution_output, sample_compliance_output, sample_cost_output,
    ):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
        }
        system, user = self.agent.build_prompt(context)
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str) and len(user) > 0

    def test_system_prompt_contains_key_terms(
        self, sample_rfp_brief, sample_qualification_output,
        sample_solution_output, sample_compliance_output, sample_cost_output,
    ):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
        }
        system, _ = self.agent.build_prompt(context)
        assert "review" in system.lower() or "QA" in system

    def test_user_prompt_includes_all_sections(
        self, sample_rfp_brief, sample_qualification_output,
        sample_solution_output, sample_compliance_output, sample_cost_output,
    ):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
        }
        _, user = self.agent.build_prompt(context)
        assert "Qualification" in user
        assert "Solution" in user
        assert "Compliance" in user
        assert "Cost" in user


class TestAgentAttributes:
    def test_agent_type(self):
        assert ReviewAgent.agent_type == "review"

    def test_model(self):
        assert ReviewAgent.model == "claude-sonnet-4-6"

    def test_temperature(self):
        assert ReviewAgent.temperature == 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_review.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ReviewAgent**

Create `backend/app/agents/review.py`:

```python
import json

from app.agents.base import BaseAgent


class ReviewAgent(BaseAgent):
    agent_type = "review"
    model = "claude-sonnet-4-6"
    temperature = 0.1

    def build_prompt(self, context: dict) -> tuple[str, str]:
        system = """You are a proposal QA reviewer. Your job is to find contradictions, missing sections, and formatting issues across a complete RFP proposal.

Check specifically for:
1. STAFFING CONSISTENCY — does the solution's staffing count match the cost section's roles?
2. TIMELINE CONSISTENCY — are dates and durations consistent across sections?
3. CONTRADICTIONS — do any sections make claims that contradict other sections?
4. RFP COVERAGE — are all RFP requirements addressed somewhere in the proposal?
5. FORMATTING — consistent header levels, no broken references, professional tone.

Be specific and actionable. Each issue should have enough detail for a human to fix it.

Respond with ONLY valid JSON (no markdown fences):
{
  "contradictions": [
    {"sections": ["section1", "section2"], "issue": "description", "severity": "high"|"medium"|"low"}
  ],
  "missing_sections": ["section that should exist but doesn't"],
  "formatting_issues": ["specific formatting problem"],
  "quality_score": 0.0-1.0,
  "recommendation": "ready" | "needs_revision" | "major_issues",
  "confidence": 0.0-1.0
}"""

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_review.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/review.py backend/tests/test_review.py
git commit -m "feat: add ReviewAgent with cross-section QA and unit tests"
```

---

### Task 7: Orchestrator + Worker Wiring

**Files:**
- Modify: `backend/app/agents/orchestrator.py` (full rewrite)
- Modify: `backend/app/agents/__init__.py`
- Modify: `backend/app/workers/tasks.py`
- Create: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: Write orchestrator test**

Create `backend/tests/test_orchestrator.py`:

```python
"""Orchestrator structure tests — no LLM calls, verifies graph wiring."""

from app.agents.orchestrator import ProposalState, proposal_graph, should_continue


class TestShouldContinue:
    def test_qualified_continues(self):
        state = {"qualification": {"qualified": True}}
        assert should_continue(state) == "continue"

    def test_not_qualified_ends(self):
        state = {"qualification": {"qualified": False}}
        assert should_continue(state) == "end"

    def test_missing_qualification_continues(self):
        state = {}
        assert should_continue(state) == "continue"

    def test_conditional_continues(self):
        state = {"qualification": {"qualified": True, "recommendation": "conditional"}}
        assert should_continue(state) == "continue"


class TestProposalState:
    def test_has_proposal_id_field(self):
        state: ProposalState = {"proposal_id": "test-123"}
        assert state["proposal_id"] == "test-123"

    def test_has_errors_field(self):
        state: ProposalState = {"errors": ["missing cert"]}
        assert state["errors"] == ["missing cert"]


class TestGraphStructure:
    def test_graph_compiles(self):
        assert proposal_graph is not None

    def test_graph_has_expected_nodes(self):
        node_names = set(proposal_graph.get_graph().nodes.keys())
        expected = {"__start__", "__end__", "qualify", "solution_comply", "cost", "review"}
        assert expected.issubset(node_names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL — old orchestrator has `solution` and `comply` nodes, not `solution_comply`

- [ ] **Step 3: Update __init__.py exports**

Replace `backend/app/agents/__init__.py`:

```python
from app.agents.qualification import QualificationAgent
from app.agents.solution import SolutionAgent
from app.agents.compliance import ComplianceAgent
from app.agents.cost import CostAgent
from app.agents.review import ReviewAgent

__all__ = [
    "QualificationAgent",
    "SolutionAgent",
    "ComplianceAgent",
    "CostAgent",
    "ReviewAgent",
]
```

- [ ] **Step 4: Rewrite orchestrator.py**

Replace full content of `backend/app/agents/orchestrator.py`:

```python
"""LangGraph orchestrator — runs the full proposal generation pipeline."""

import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.qualification import QualificationAgent
from app.agents.solution import SolutionAgent
from app.agents.compliance import ComplianceAgent
from app.agents.cost import CostAgent
from app.agents.review import ReviewAgent


class ProposalState(TypedDict, total=False):
    rfp_id: str
    rfp_brief: dict
    proposal_id: str
    qualification: dict
    solution: dict
    compliance: dict
    cost: dict
    review: dict
    status: str
    errors: list


async def qualify_node(state: ProposalState) -> ProposalState:
    agent = QualificationAgent()
    result = await agent.run(
        {"rfp_brief": state["rfp_brief"]},
        proposal_id=state.get("proposal_id"),
    )
    update = {"qualification": result.output, "status": "qualified"}
    if not result.output.get("qualified", True):
        update["errors"] = result.output.get("missing", [])
        update["status"] = "disqualified"
    return update


async def solution_comply_node(state: ProposalState) -> ProposalState:
    sol_agent = SolutionAgent()
    comp_agent = ComplianceAgent()
    sol_result, comp_result = await asyncio.gather(
        sol_agent.run(
            {"rfp_brief": state["rfp_brief"], "qualification": state["qualification"]},
            proposal_id=state.get("proposal_id"),
        ),
        comp_agent.run(
            {"rfp_brief": state["rfp_brief"], "qualification": state["qualification"]},
            proposal_id=state.get("proposal_id"),
        ),
    )
    return {
        "solution": sol_result.output,
        "compliance": comp_result.output,
        "status": "solution_compliance",
    }


async def cost_node(state: ProposalState) -> ProposalState:
    agent = CostAgent()
    result = await agent.run(
        {"rfp_brief": state["rfp_brief"], "solution": state["solution"]},
        proposal_id=state.get("proposal_id"),
    )
    return {"cost": result.output, "status": "costing"}


async def review_node(state: ProposalState) -> ProposalState:
    agent = ReviewAgent()
    result = await agent.run(
        {
            "rfp_brief": state["rfp_brief"],
            "qualification": state["qualification"],
            "solution": state["solution"],
            "compliance": state["compliance"],
            "cost": state["cost"],
        },
        proposal_id=state.get("proposal_id"),
    )
    return {"review": result.output, "status": "review"}


def should_continue(state: ProposalState) -> str:
    qual = state.get("qualification", {})
    if not qual.get("qualified", True):
        return "end"
    return "continue"


def build_graph():
    graph = StateGraph(ProposalState)

    graph.add_node("qualify", qualify_node)
    graph.add_node("solution_comply", solution_comply_node)
    graph.add_node("cost", cost_node)
    graph.add_node("review", review_node)

    graph.set_entry_point("qualify")

    graph.add_conditional_edges(
        "qualify", should_continue,
        {"continue": "solution_comply", "end": END},
    )
    graph.add_edge("solution_comply", "cost")
    graph.add_edge("cost", "review")
    graph.add_edge("review", END)

    return graph.compile()


proposal_graph = build_graph()
```

- [ ] **Step 5: Update workers/tasks.py**

Replace full content of `backend/app/workers/tasks.py`:

```python
import asyncio

from celery import Celery
from sqlalchemy.orm import joinedload

from app.config import settings

celery_app = Celery("blackbox", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, max_retries=2)
def generate_proposal_task(self, proposal_id: str):
    """Run the full LangGraph pipeline for a proposal."""
    from app.agents.orchestrator import proposal_graph
    from app.models.database import SessionLocal, Proposal

    db = SessionLocal()
    try:
        proposal = (
            db.query(Proposal)
            .options(joinedload(Proposal.rfp))
            .filter(Proposal.id == proposal_id)
            .first()
        )
        if not proposal:
            return {"error": "Proposal not found"}

        proposal.status = "generating"
        db.commit()

        initial_state = {
            "rfp_id": str(proposal.rfp_id),
            "rfp_brief": proposal.rfp.extracted_brief,
            "proposal_id": str(proposal.id),
        }
        result = asyncio.run(proposal_graph.ainvoke(initial_state))

        proposal.qualification_result = result.get("qualification")
        proposal.solution_section = result.get("solution", {}).get("approach", "")
        proposal.compliance_section = result.get("compliance", {}).get("narrative", "")
        proposal.cost_section = result.get("cost")
        proposal.review_result = result.get("review")
        proposal.status = "draft"
        db.commit()

        return {"proposal_id": proposal_id, "status": "draft"}

    except Exception as e:
        db.rollback()
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if proposal:
            if self.request.retries >= self.max_retries:
                proposal.status = "failed"
            else:
                proposal.status = "queued"
            db.commit()
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


@celery_app.task
def ingest_rfp_task(rfp_id: str, file_url: str = None):
    """Parse and ingest an RFP document."""
    # TODO: invoke ingestion pipeline
    return {"rfp_id": rfp_id, "status": "ingested"}
```

- [ ] **Step 6: Run orchestrator tests**

Run: `cd backend && python -m pytest tests/test_orchestrator.py -v`
Expected: All PASS

- [ ] **Step 7: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests across all files PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/orchestrator.py backend/app/agents/__init__.py backend/app/workers/tasks.py backend/tests/test_orchestrator.py
git commit -m "feat: wire agents into orchestrator with parallel fan-out and Celery task"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify imports work end-to-end**

Run: `cd backend && python -c "from app.agents import QualificationAgent, SolutionAgent, ComplianceAgent, CostAgent, ReviewAgent; from app.agents.orchestrator import proposal_graph; print('All imports OK'); print(f'Graph nodes: {set(proposal_graph.get_graph().nodes.keys())}')"`

Expected output:
```
All imports OK
Graph nodes: {'__start__', '__end__', 'qualify', 'solution_comply', 'cost', 'review'}
```

- [ ] **Step 3: Commit any fixes, then final commit message**

If all green, no action needed. If any fixes were required, commit them:

```bash
git add -u
git commit -m "fix: address test failures from final verification"
```
