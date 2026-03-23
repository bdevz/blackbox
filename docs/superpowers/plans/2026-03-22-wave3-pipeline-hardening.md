# Wave 3: Pipeline Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Blackbox proposal pipeline with revision loops, RFP document ingestion, price-to-win cost logic, and API rate limiting.

**Architecture:** Add a conditional revision loop after ReviewAgent that re-runs flagged agents (max 2 passes). Add a document parsing module that extracts structured briefs from PDF/DOCX uploads. Enhance CostAgent with estimated_value and competitor intelligence for competitive pricing. Add a module-level asyncio semaphore in BaseAgent to bound concurrent API calls.

**Tech Stack:** FastAPI, SQLAlchemy, AsyncAnthropic, LangGraph, PyMuPDF (fitz), python-docx, httpx, asyncio, pytest

---

## File Structure

### New Files
| File | Responsibility |
|------|----------------|
| `backend/app/agents/ingestion.py` | RFP document parser — extracts text from PDF/DOCX, sends to Claude Haiku for structured brief extraction |
| `backend/tests/test_ingestion.py` | Tests for text extraction and brief parsing |
| `backend/tests/test_rate_limit.py` | Tests for semaphore concurrency bounding |
| `backend/tests/test_revision.py` | Tests for revision loop routing and state |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app/agents/orchestrator.py` | Add `revision_count` to ProposalState, add `revision_node`, add `should_revise` conditional, loop edges |
| `backend/app/agents/solution.py` | Handle `review_feedback` in `build_prompt()` for revision passes |
| `backend/app/agents/compliance.py` | Handle `review_feedback` in `build_prompt()` for revision passes |
| `backend/app/agents/cost.py` | Handle `review_feedback` in `build_prompt()`, add price-to-win logic (`inject_context`, `calculate_costs`, `validate_output`) |
| `backend/app/agents/base.py` | Add module-level `asyncio.Semaphore`, wrap API call in `async with` |
| `backend/app/config.py` | Add `max_concurrent_api_calls: int = 4` |
| `backend/app/workers/tasks.py` | Wire `ingest_rfp_task` to ingestion module |
| `backend/app/api/rfps.py` | Queue ingestion task after upload, store file content, wire ingest-url |
| `backend/tests/conftest.py` | Add `sample_review_output`, `sample_competitor_intel` fixtures |
| `backend/tests/test_orchestrator.py` | Add tests for `should_revise`, `revision_node`, new graph edges |
| `backend/tests/test_cost.py` | Add price-to-win tests |

---

## Task 1: Rate Limiting — Semaphore in BaseAgent

**Files:**
- Modify: `backend/app/config.py:4-26`
- Modify: `backend/app/agents/base.py:1-10,86-100`
- Create: `backend/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing test for semaphore bounding**

```python
# backend/tests/test_rate_limit.py
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.base import BaseAgent, _api_semaphore


class TestRateLimiting:
    def test_semaphore_exists(self):
        """Module-level semaphore is created."""
        assert isinstance(_api_semaphore, asyncio.Semaphore)

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrent_calls(self):
        """No more than max_concurrent calls run simultaneously."""
        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def mock_create(**kwargs):
            nonlocal active, max_active
            async with lock:
                active += 1
                if active > max_active:
                    max_active = active
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1
            # Return a mock response
            resp = MagicMock()
            resp.content = [MagicMock(text='{"confidence": 0.5}')]
            resp.usage = MagicMock(input_tokens=10, output_tokens=10)
            return resp

        class DummyAgent(BaseAgent):
            agent_type = "test"
            def build_prompt(self, context):
                return "system", "user"
            def validate_output(self, raw):
                import json
                return json.loads(raw)

        with patch("app.agents.base._api_semaphore", asyncio.Semaphore(2)):
            agent = DummyAgent.__new__(DummyAgent)
            agent.model = "claude-sonnet-4-6"
            agent.max_tokens = 100
            agent.temperature = 0.1
            agent.client = MagicMock()
            agent.client.messages = MagicMock()
            agent.client.messages.create = mock_create

            with patch("app.agents.base.SessionLocal") as mock_session:
                mock_db = MagicMock()
                mock_session.return_value = mock_db

                tasks = [agent.run({"test": True}) for _ in range(6)]
                await asyncio.gather(*tasks)

        assert max_active <= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_rate_limit.py -v`
Expected: FAIL — `_api_semaphore` not importable

- [ ] **Step 3: Add `max_concurrent_api_calls` to config**

In `backend/app/config.py`, add after `voyage_model` (line 21):
```python
    max_concurrent_api_calls: int = 4
```

- [ ] **Step 4: Add semaphore to BaseAgent**

In `backend/app/agents/base.py`, add after imports (line 10):
```python
from app.config import settings  # already imported

_api_semaphore = asyncio.Semaphore(settings.max_concurrent_api_calls)
```

Add `import asyncio` to the imports section.

In `BaseAgent.run()`, wrap the API call (lines 94-100) with the semaphore:
```python
            async with _api_semaphore:
                start = time.monotonic()
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                duration_ms = int((time.monotonic() - start) * 1000)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_rate_limit.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/ -v --ignore=tests/test_integration.py`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/agents/base.py backend/tests/test_rate_limit.py
git commit -m "feat: add asyncio semaphore to BaseAgent for API rate limiting"
```

---

## Task 2: Revision Loop — Orchestrator Routing Logic

**Files:**
- Modify: `backend/app/agents/orchestrator.py`
- Create: `backend/tests/test_revision.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: Add `sample_review_output` fixture to conftest**

In `backend/tests/conftest.py`, add at the end:
```python
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
```

- [ ] **Step 2: Write failing tests for `should_revise` and ProposalState changes**

```python
# backend/tests/test_revision.py
from app.agents.orchestrator import ProposalState, should_revise


class TestShouldRevise:
    def test_ready_goes_to_end(self):
        state = {
            "review": {"recommendation": "ready"},
            "revision_count": 0,
        }
        assert should_revise(state) == "end"

    def test_needs_revision_routes_to_revise(self):
        state = {
            "review": {"recommendation": "needs_revision"},
            "revision_count": 0,
        }
        assert should_revise(state) == "revise"

    def test_major_issues_routes_to_revise(self):
        state = {
            "review": {"recommendation": "major_issues"},
            "revision_count": 0,
        }
        assert should_revise(state) == "revise"

    def test_max_revisions_goes_to_end(self):
        state = {
            "review": {"recommendation": "needs_revision"},
            "revision_count": 2,
        }
        assert should_revise(state) == "end"

    def test_revision_count_1_allows_one_more(self):
        state = {
            "review": {"recommendation": "needs_revision"},
            "revision_count": 1,
        }
        assert should_revise(state) == "revise"

    def test_missing_review_goes_to_end(self):
        state = {"revision_count": 0}
        assert should_revise(state) == "end"


class TestProposalStateRevisionFields:
    def test_has_revision_count(self):
        state: ProposalState = {"revision_count": 1}
        assert state["revision_count"] == 1

    def test_has_review_feedback(self):
        state: ProposalState = {"review_feedback": {"solution": "fix staffing"}}
        assert "solution" in state["review_feedback"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_revision.py -v`
Expected: FAIL — `should_revise` not importable, `revision_count` not in ProposalState

- [ ] **Step 4: Add `revision_count` and `review_feedback` to ProposalState**

In `backend/app/agents/orchestrator.py`, update `ProposalState` (lines 15-25):
```python
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
    revision_count: int
    review_feedback: dict
```

- [ ] **Step 5: Add `should_revise` function**

In `backend/app/agents/orchestrator.py`, add after `should_continue` (after line 89):
```python
def should_revise(state: ProposalState) -> str:
    review = state.get("review", {})
    recommendation = review.get("recommendation", "ready")
    revision_count = state.get("revision_count", 0)

    if recommendation == "ready" or revision_count >= 2:
        return "end"
    return "revise"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_revision.py -v`
Expected: PASS

- [ ] **Step 7: Write failing tests for revision_node**

Add to `backend/tests/test_revision.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.orchestrator import revision_node


class TestRevisionNode:
    @pytest.mark.asyncio
    async def test_extracts_feedback_for_affected_sections(
        self, sample_rfp_brief, sample_qualification_output, sample_solution_output,
        sample_compliance_output, sample_cost_output, sample_review_output_needs_revision,
    ):
        """revision_node should extract per-section feedback from review contradictions."""
        state = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
            "review": sample_review_output_needs_revision,
            "revision_count": 0,
        }

        mock_result = MagicMock()
        mock_result.output = sample_solution_output

        with patch("app.agents.orchestrator.SolutionAgent") as MockSol, \
             patch("app.agents.orchestrator.ComplianceAgent") as MockComp, \
             patch("app.agents.orchestrator.CostAgent") as MockCost:
            MockSol.return_value.run = AsyncMock(return_value=mock_result)
            mock_comp_result = MagicMock()
            mock_comp_result.output = sample_compliance_output
            MockComp.return_value.run = AsyncMock(return_value=mock_comp_result)
            mock_cost_result = MagicMock()
            mock_cost_result.output = sample_cost_output
            MockCost.return_value.run = AsyncMock(return_value=mock_cost_result)

            result = await revision_node(state)

        assert result["revision_count"] == 1
        assert "solution" in result
        assert "cost" in result

    @pytest.mark.asyncio
    async def test_increments_revision_count(
        self, sample_rfp_brief, sample_qualification_output, sample_solution_output,
        sample_compliance_output, sample_cost_output, sample_review_output_needs_revision,
    ):
        state = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "solution": sample_solution_output,
            "compliance": sample_compliance_output,
            "cost": sample_cost_output,
            "review": sample_review_output_needs_revision,
            "revision_count": 1,
        }

        mock_result = MagicMock()
        mock_result.output = sample_solution_output

        with patch("app.agents.orchestrator.SolutionAgent") as MockSol, \
             patch("app.agents.orchestrator.ComplianceAgent") as MockComp, \
             patch("app.agents.orchestrator.CostAgent") as MockCost:
            MockSol.return_value.run = AsyncMock(return_value=mock_result)
            mock_comp_result = MagicMock()
            mock_comp_result.output = sample_compliance_output
            MockComp.return_value.run = AsyncMock(return_value=mock_comp_result)
            mock_cost_result = MagicMock()
            mock_cost_result.output = sample_cost_output
            MockCost.return_value.run = AsyncMock(return_value=mock_cost_result)

            result = await revision_node(state)

        assert result["revision_count"] == 2
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_revision.py::TestRevisionNode -v`
Expected: FAIL — `revision_node` not importable

- [ ] **Step 9: Implement `revision_node`**

In `backend/app/agents/orchestrator.py`, add after `review_node` (after line 82):
```python
def _extract_affected_sections(review: dict) -> set[str]:
    """Extract which sections have contradictions from review output."""
    affected = set()
    for contradiction in review.get("contradictions", []):
        for section in contradiction.get("sections", []):
            affected.add(section)
    return affected


def _build_review_feedback(review: dict, section: str) -> str:
    """Build feedback string for a specific section from review contradictions."""
    issues = []
    for c in review.get("contradictions", []):
        if section in c.get("sections", []):
            issues.append(f"[{c['severity'].upper()}] {c['issue']}")
    for m in review.get("missing_sections", []):
        issues.append(f"Missing: {m}")
    return "\n".join(issues) if issues else ""


async def revision_node(state: ProposalState) -> ProposalState:
    """Re-run affected agents with review feedback. Always re-run cost after solution changes."""
    review = state.get("review", {})
    affected = _extract_affected_sections(review)
    revision_count = state.get("revision_count", 0) + 1

    update: dict = {"revision_count": revision_count, "status": f"revision_{revision_count}"}

    tasks = []
    task_keys = []

    if "solution" in affected:
        sol_agent = SolutionAgent()
        feedback = _build_review_feedback(review, "solution")
        tasks.append(sol_agent.run(
            {
                "rfp_brief": state["rfp_brief"],
                "qualification": state["qualification"],
                "review_feedback": feedback,
            },
            proposal_id=state.get("proposal_id"),
        ))
        task_keys.append("solution")

    if "compliance" in affected:
        comp_agent = ComplianceAgent()
        feedback = _build_review_feedback(review, "compliance")
        tasks.append(comp_agent.run(
            {
                "rfp_brief": state["rfp_brief"],
                "qualification": state["qualification"],
                "review_feedback": feedback,
            },
            proposal_id=state.get("proposal_id"),
        ))
        task_keys.append("compliance")

    if tasks:
        results = await asyncio.gather(*tasks)
        for key, result in zip(task_keys, results):
            update[key] = result.output

    # Always re-run cost if solution was revised (staffing may have changed)
    if "solution" in affected or "cost" in affected:
        cost_agent = CostAgent()
        solution = update.get("solution", state.get("solution", {}))
        cost_feedback = _build_review_feedback(review, "cost")
        cost_result = await cost_agent.run(
            {
                "rfp_id": state.get("rfp_id"),
                "rfp_brief": state["rfp_brief"],
                "solution": solution,
                "review_feedback": cost_feedback,
            },
            proposal_id=state.get("proposal_id"),
        )
        update["cost"] = cost_result.output

    return update
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_revision.py -v`
Expected: PASS

- [ ] **Step 11: Update graph wiring with revision loop**

In `backend/app/agents/orchestrator.py`, update `build_graph()`:
```python
def build_graph():
    graph = StateGraph(ProposalState)

    graph.add_node("qualify", qualify_node)
    graph.add_node("solution_comply", solution_comply_node)
    graph.add_node("cost", cost_node)
    graph.add_node("review", review_node)
    graph.add_node("revision", revision_node)

    graph.set_entry_point("qualify")

    graph.add_conditional_edges(
        "qualify", should_continue,
        {"continue": "solution_comply", "end": END},
    )
    graph.add_edge("solution_comply", "cost")
    graph.add_edge("cost", "review")
    graph.add_conditional_edges(
        "review", should_revise,
        {"revise": "revision", "end": END},
    )
    graph.add_edge("revision", "cost")

    return graph.compile()
```

Note: After revision, we always go to `cost` (which then goes to `review`). If solution was revised, cost needs recompute. If only compliance was revised, cost is a quick re-run with same data. This keeps the graph simple.

Wait — if only compliance was revised, cost doesn't need to re-run. But the graph edges are static. The simplest correct approach: revision → review (skip cost if cost wasn't affected). But LangGraph static edges don't support this easily.

Simpler: revision always → cost → review. Cost is cheap (Sonnet). The redundant call costs ~$0.01. Ship simplicity.

- [ ] **Step 12: Update orchestrator test for new graph nodes**

In `backend/tests/test_orchestrator.py`, update `TestGraphStructure.test_graph_has_expected_nodes`:
```python
    def test_graph_has_expected_nodes(self):
        node_names = set(proposal_graph.get_graph().nodes.keys())
        expected = {"__start__", "__end__", "qualify", "solution_comply", "cost", "review", "revision"}
        assert expected.issubset(node_names)
```

- [ ] **Step 13: Run full test suite**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/ -v --ignore=tests/test_integration.py`
Expected: All tests pass

- [ ] **Step 14: Commit**

```bash
git add backend/app/agents/orchestrator.py backend/tests/test_revision.py backend/tests/conftest.py backend/tests/test_orchestrator.py
git commit -m "feat: add revision loop to orchestrator — max 2 passes on flagged sections"
```

---

## Task 3: Review Feedback Handling in Agents

**Files:**
- Modify: `backend/app/agents/solution.py:65-108`
- Modify: `backend/app/agents/compliance.py:42-84`
- Modify: `backend/app/agents/cost.py:92-138`
- Modify: `backend/tests/test_solution.py`
- Modify: `backend/tests/test_compliance.py`
- Modify: `backend/tests/test_cost.py`

- [ ] **Step 1: Write failing tests for review_feedback in build_prompt**

Add to `backend/tests/test_solution.py`:
```python
class TestReviewFeedbackInPrompt:
    def setup_method(self):
        self.agent = SolutionAgent.__new__(SolutionAgent)

    def test_review_feedback_included_in_user_prompt(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "company_knowledge": [],
            "similar_proposals": [],
            "review_feedback": "[HIGH] Staffing count mismatch",
        }
        _, user = self.agent.build_prompt(context)
        assert "Staffing count mismatch" in user
        assert "reviewer" in user.lower() or "review" in user.lower()

    def test_no_review_feedback_no_section(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "company_knowledge": [],
            "similar_proposals": [],
        }
        _, user = self.agent.build_prompt(context)
        assert "QA reviewer found" not in user
```

Add to `backend/tests/test_compliance.py`:
```python
class TestReviewFeedbackInPrompt:
    def setup_method(self):
        self.agent = ComplianceAgent.__new__(ComplianceAgent)

    def test_review_feedback_included_in_user_prompt(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "certifications": [],
            "boilerplate": [],
            "review_feedback": "[MEDIUM] Claims CMMI Level 5, only have Level 3",
        }
        _, user = self.agent.build_prompt(context)
        assert "CMMI Level 5" in user

    def test_no_review_feedback_no_section(self, sample_rfp_brief, sample_qualification_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "qualification": sample_qualification_output,
            "certifications": [],
            "boilerplate": [],
        }
        _, user = self.agent.build_prompt(context)
        assert "QA reviewer found" not in user
```

Add to `backend/tests/test_cost.py`:
```python
class TestReviewFeedbackInPrompt:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_review_feedback_included_in_user_prompt(self, sample_rfp_brief, sample_solution_output):
        context = {
            "rfp_brief": sample_rfp_brief,
            "solution": sample_solution_output,
            "computed_costs": {"labor_costs": {"roles": [], "subtotal": 0}, "missing_rates": [], "total_with_margin": 0},
            "review_feedback": "[HIGH] Costs exceed budget by 40%",
        }
        _, user = self.agent.build_prompt(context)
        assert "Costs exceed budget" in user
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_solution.py::TestReviewFeedbackInPrompt tests/test_compliance.py::TestReviewFeedbackInPrompt tests/test_cost.py::TestReviewFeedbackInPrompt -v`
Expected: FAIL — "Staffing count mismatch" not in user prompt

- [ ] **Step 3: Add review feedback handling to SolutionAgent.build_prompt()**

In `backend/app/agents/solution.py`, at the end of `build_prompt()` (before `return system, user`), add:
```python
        review_feedback = context.get("review_feedback")
        if review_feedback:
            user += f"""

## QA Reviewer Feedback (FIX THESE ISSUES)
The QA reviewer found these issues with your previous output. You MUST fix them:
{review_feedback}"""
```

- [ ] **Step 4: Add review feedback handling to ComplianceAgent.build_prompt()**

In `backend/app/agents/compliance.py`, at the end of `build_prompt()` (before `return system, user`), add:
```python
        review_feedback = context.get("review_feedback")
        if review_feedback:
            user += f"""

## QA Reviewer Feedback (FIX THESE ISSUES)
The QA reviewer found these issues with your previous output. You MUST fix them:
{review_feedback}"""
```

- [ ] **Step 5: Add review feedback handling to CostAgent.build_prompt()**

In `backend/app/agents/cost.py`, at the end of `build_prompt()` (before `return system, user`), add:
```python
        review_feedback = context.get("review_feedback")
        if review_feedback:
            user += f"""

## QA Reviewer Feedback (FIX THESE ISSUES)
The QA reviewer found these issues with your previous output. You MUST fix them:
{review_feedback}"""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_solution.py tests/test_compliance.py tests/test_cost.py -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/solution.py backend/app/agents/compliance.py backend/app/agents/cost.py backend/tests/test_solution.py backend/tests/test_compliance.py backend/tests/test_cost.py
git commit -m "feat: handle review feedback in agent prompts for revision loop"
```

---

## Task 4: Price-to-Win Logic in CostAgent

**Files:**
- Modify: `backend/app/agents/cost.py:22-59,61-90,92-138,141-186`
- Modify: `backend/tests/test_cost.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Add competitor intel fixture to conftest**

In `backend/tests/conftest.py`, add at the end:
```python
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
```

- [ ] **Step 2: Write failing tests for price-to-win**

Add to `backend/tests/test_cost.py`:
```python
class TestPriceToWin:
    def setup_method(self):
        self.agent = CostAgent.__new__(CostAgent)

    def test_flags_over_budget(self, sample_solution_output):
        """When base cost > estimated_value * 1.1, flag as over_budget."""
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
            estimated_value=200000.0,  # way under base cost
        )
        assert result["over_budget"] is True
        assert "value_engineered" in result

    def test_not_over_budget_when_within_threshold(self, sample_solution_output):
        """When base cost <= estimated_value * 1.1, no over_budget flag."""
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
            estimated_value=5000000.0,  # well above base cost
        )
        assert result.get("over_budget", False) is False

    def test_no_estimated_value_skips_price_to_win(self, sample_solution_output):
        """Without estimated_value, skip price-to-win logic."""
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        result = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
        )
        assert result.get("over_budget", False) is False
        assert "value_engineered" not in result

    def test_competitor_intel_adjusts_margin(self, sample_solution_output):
        """When competitor pricing is lower, reduce margin."""
        rate_card = {
            "Project Manager": {"hourly": 95},
            "Cloud Architect": {"hourly": 110},
            "Senior Developer": {"hourly": 75},
            "Developer": {"hourly": 55},
            "QA Engineer": {"hourly": 50},
        }
        # Competitor at $450k means our $441.6k base + 15% margin = $507.8k is too high
        result_no_comp = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
        )
        result_with_comp = self.agent.calculate_costs(
            staffing=sample_solution_output["staffing"],
            rate_card=rate_card,
            competitor_avg=450000.0,
        )
        # With competitor pressure, margin should be reduced
        assert result_with_comp["total_with_margin"] <= result_no_comp["total_with_margin"]


class TestValidateOutputPriceToWin:
    def test_accepts_value_engineered_field(self):
        agent = CostAgent.__new__(CostAgent)
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [],
            "total": 0,
            "narrative": "x",
            "confidence": 0.5,
            "value_engineered": True,
            "pricing_strategy": "competitive",
        })
        result = agent.validate_output(raw)
        assert result["value_engineered"] is True
        assert result["pricing_strategy"] == "competitive"

    def test_accepts_without_optional_fields(self):
        agent = CostAgent.__new__(CostAgent)
        raw = json.dumps({
            "labor_costs": {"roles": [], "subtotal": 0},
            "other_costs": [],
            "total": 0,
            "narrative": "x",
            "confidence": 0.5,
        })
        result = agent.validate_output(raw)
        assert "value_engineered" not in result or result.get("value_engineered") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_cost.py::TestPriceToWin tests/test_cost.py::TestValidateOutputPriceToWin -v`
Expected: FAIL — `calculate_costs()` doesn't accept `estimated_value` or `competitor_avg` params

- [ ] **Step 4: Update `calculate_costs()` with price-to-win logic**

In `backend/app/agents/cost.py`, update `calculate_costs()` signature and body:
```python
    def calculate_costs(
        self,
        staffing: list[dict],
        rate_card: dict,
        margin: float = DEFAULT_MARGIN,
        estimated_value: float = None,
        competitor_avg: float = None,
    ) -> dict:
        """Deterministic cost calculation with price-to-win adjustments."""
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

        # Price-to-win: adjust margin if competitor data available
        effective_margin = margin
        if competitor_avg is not None and subtotal > 0:
            # If our base cost + margin > competitor avg, reduce margin to be competitive
            if subtotal * (1 + margin) > competitor_avg:
                # Set margin so total = competitor_avg (but floor at 5%)
                effective_margin = max((competitor_avg / subtotal) - 1, 0.05)

        result = {
            "labor_costs": {"roles": roles, "subtotal": subtotal},
            "missing_rates": missing_rates,
            "total_with_margin": subtotal * (1 + effective_margin),
        }

        # Price-to-win: flag over-budget and compute value-engineered alternative
        if estimated_value is not None and subtotal * (1 + effective_margin) > estimated_value * 1.1:
            result["over_budget"] = True
            # Value-engineer: reduce hours by scaling down to fit within budget
            target = estimated_value * 0.95  # Target 95% of budget
            scale = target / (subtotal * (1 + effective_margin)) if subtotal > 0 else 1.0
            ve_roles = []
            ve_subtotal = 0.0
            for r in roles:
                ve_hours = int(r["hours"] * scale)
                ve_total = r["rate"] * ve_hours * r.get("headcount", 1)
                ve_subtotal += ve_total
                ve_roles.append({**r, "hours": ve_hours, "total": ve_total})
            result["value_engineered"] = {
                "labor_costs": {"roles": ve_roles, "subtotal": ve_subtotal},
                "total_with_margin": ve_subtotal * (1 + effective_margin),
            }
        else:
            result["over_budget"] = False

        return result
```

- [ ] **Step 5: Update `inject_context()` to fetch estimated_value and competitor intel**

In `backend/app/agents/cost.py`, update `inject_context()`:
```python
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

        # Extract estimated_value from RFP brief
        rfp_brief = context.get("rfp_brief", {})
        estimated_value = rfp_brief.get("estimated_value")
        context["estimated_value"] = float(estimated_value) if estimated_value else None

        # Fetch competitor intel
        from app.models.database import CompetitorIntel
        rfp_id = context.get("rfp_id") or context.get("rfp_brief", {}).get("rfp_id")
        competitor_avg = None
        competitors = []
        if rfp_id:
            competitors = db.query(CompetitorIntel).filter(
                CompetitorIntel.rfp_id == rfp_id
            ).all()
            if competitors:
                values = [float(c.past_contract_value) for c in competitors if c.past_contract_value]
                competitor_avg = sum(values) / len(values) if values else None
                context["competitor_intel"] = [
                    {"name": c.competitor_name, "value": float(c.past_contract_value) if c.past_contract_value else None}
                    for c in competitors
                ]

        solution = context.get("solution", {})
        staffing = solution.get("staffing", [])
        computed = self.calculate_costs(
            staffing=staffing,
            rate_card=rate_card,
            estimated_value=context["estimated_value"],
            competitor_avg=competitor_avg,
        )
        context["computed_costs"] = computed
        self._computed_costs = computed

        return context
```

- [ ] **Step 6: Update `build_prompt()` to include estimated_value and competitor data**

In `backend/app/agents/cost.py`, update the user prompt section of `build_prompt()`:
```python
        estimated_value = context.get("estimated_value")
        competitor_intel = context.get("competitor_intel", [])

        user = f"""## RFP Brief
{json.dumps(rfp_brief, indent=2)}

## Solution Staffing Plan
{json.dumps(solution.get("staffing", []), indent=2)}

## Pre-Computed Cost Breakdown (USE THESE EXACT NUMBERS)
{json.dumps(computed, indent=2)}"""

        if estimated_value:
            user += f"""

## Budget Context
Estimated RFP value: ${estimated_value:,.2f}
{"WARNING: Our pricing exceeds the estimated value. Justify competitiveness or highlight value-engineering trade-offs." if computed.get("over_budget") else "Our pricing is within the estimated budget."}"""

        if competitor_intel:
            user += f"""

## Competitor Intelligence
{json.dumps(competitor_intel, indent=2)}
Position our pricing as competitive against these competitors."""

        user += """

Write the cost justification narrative. Use the pre-computed numbers exactly."""

        review_feedback = context.get("review_feedback")
        if review_feedback:
            user += f"""

## QA Reviewer Feedback (FIX THESE ISSUES)
The QA reviewer found these issues with your previous output. You MUST fix them:
{review_feedback}"""

        return system, user
```

- [ ] **Step 7: Update `validate_output()` to accept optional price-to-win fields**

In `backend/app/agents/cost.py`, at the end of `validate_output()` (before `return data`), the optional fields are already valid since we just return `data` — JSON with extra fields passes validation. No changes needed.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_cost.py -v`
Expected: All tests pass

- [ ] **Step 9: Run full test suite**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/ -v --ignore=tests/test_integration.py`
Expected: All tests pass

- [ ] **Step 10: Commit**

```bash
git add backend/app/agents/cost.py backend/tests/test_cost.py backend/tests/conftest.py
git commit -m "feat: add price-to-win logic to CostAgent — budget awareness and competitor margin adjustment"
```

---

## Task 5: RFP Document Ingestion — Parser Module

**Files:**
- Create: `backend/app/agents/ingestion.py`
- Create: `backend/tests/test_ingestion.py`

- [ ] **Step 1: Write failing tests for text extraction**

```python
# backend/tests/test_ingestion.py
import pytest

from app.agents.ingestion import extract_text, parse_brief


class TestExtractText:
    def test_plain_text(self):
        content = b"This is a plain text RFP document."
        result = extract_text(content, "rfp.txt")
        assert "plain text RFP" in result

    def test_pdf_extraction(self, tmp_path):
        """Create a minimal PDF and extract text."""
        import fitz  # PyMuPDF
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "RFP for IT Services\nAgency: Ohio DAS\nDeadline: 2026-05-15")
        doc.save(str(pdf_path))
        doc.close()

        content = pdf_path.read_bytes()
        result = extract_text(content, "test.pdf")
        assert "RFP for IT Services" in result
        assert "Ohio DAS" in result

    def test_docx_extraction(self, tmp_path):
        """Create a minimal DOCX and extract text."""
        from docx import Document
        doc = Document()
        doc.add_paragraph("RFP for Cloud Migration")
        doc.add_paragraph("State of California")
        docx_path = tmp_path / "test.docx"
        doc.save(str(docx_path))

        content = docx_path.read_bytes()
        result = extract_text(content, "test.docx")
        assert "Cloud Migration" in result
        assert "California" in result

    def test_unsupported_format_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            extract_text(b"data", "file.xlsx")

    def test_empty_content_raises(self):
        with pytest.raises(ValueError, match="empty"):
            extract_text(b"", "test.pdf")


class TestParseBrief:
    def test_returns_required_fields(self):
        """parse_brief should return a dict with all required brief fields."""
        # We test the structure, not LLM output (that's integration)
        from app.agents.ingestion import BRIEF_SCHEMA
        assert "title" in BRIEF_SCHEMA
        assert "agency" in BRIEF_SCHEMA
        assert "requirements" in BRIEF_SCHEMA

    def test_validate_brief_valid(self):
        from app.agents.ingestion import validate_brief
        brief = {
            "title": "IT Modernization",
            "agency": "Ohio DAS",
            "state": "Ohio",
            "category": "IT",
            "deadline": "2026-05-15",
            "estimated_value": 2500000,
            "requirements": ["5 years experience"],
            "scope": "Cloud migration",
            "evaluation_criteria": {"technical": 40, "cost": 30},
        }
        result = validate_brief(brief)
        assert result["title"] == "IT Modernization"

    def test_validate_brief_missing_title(self):
        from app.agents.ingestion import validate_brief
        brief = {"agency": "Ohio DAS"}
        with pytest.raises(ValueError, match="title"):
            validate_brief(brief)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_ingestion.py -v`
Expected: FAIL — `ingestion` module doesn't exist

- [ ] **Step 3: Implement ingestion module**

```python
# backend/app/agents/ingestion.py
"""RFP document parser — extracts text from PDF/DOCX, parses into structured brief."""

import io
import json
import logging

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

BRIEF_SCHEMA = {
    "title": "str — RFP title",
    "agency": "str — issuing agency name",
    "state": "str — US state",
    "category": "str — RFP category (e.g. IT Consulting)",
    "deadline": "str — submission deadline (YYYY-MM-DD)",
    "estimated_value": "float or null — estimated contract value in USD",
    "requirements": "list[str] — mandatory requirements",
    "scope": "str — scope of work description",
    "evaluation_criteria": "dict[str, int] — criteria name → weight",
}


def extract_text(content: bytes, filename: str) -> str:
    """Extract plain text from PDF, DOCX, or text file."""
    if not content:
        raise ValueError("Document content is empty")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()

    elif ext == "docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs)
        return text.strip()

    elif ext in ("txt", "text", "md"):
        return content.decode("utf-8", errors="replace").strip()

    else:
        raise ValueError(f"Unsupported file format: .{ext}")


def validate_brief(brief: dict) -> dict:
    """Validate that parsed brief has minimum required fields."""
    required = ["title", "agency"]
    for field in required:
        if field not in brief or not brief[field]:
            raise ValueError(f"Parsed brief missing required field: {field}")

    # Set defaults for optional fields
    brief.setdefault("state", "")
    brief.setdefault("category", "")
    brief.setdefault("deadline", None)
    brief.setdefault("estimated_value", None)
    brief.setdefault("requirements", [])
    brief.setdefault("scope", "")
    brief.setdefault("evaluation_criteria", {})

    return brief


async def parse_brief(text: str) -> dict:
    """Use Claude Haiku to parse raw document text into a structured brief."""
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    system = """You are an RFP document parser. Extract structured data from raw RFP document text.

Respond with ONLY valid JSON (no markdown fences):
{
  "title": "RFP title",
  "agency": "issuing agency name",
  "state": "US state (2-letter or full name)",
  "category": "category like IT Consulting, Construction, etc.",
  "deadline": "YYYY-MM-DD or null if not found",
  "estimated_value": 2500000.0 or null if not found,
  "requirements": ["requirement 1", "requirement 2"],
  "scope": "full scope of work description",
  "evaluation_criteria": {"criteria_name": weight_int}
}

Extract ONLY what is explicitly stated in the document. Do NOT infer or fabricate data.
If a field is not present in the document, use null or empty list/object."""

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": f"Parse this RFP document:\n\n{text[:50000]}"}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    import re
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, count=1)
    raw = re.sub(r"\n?```\s*$", "", raw)

    brief = json.loads(raw)
    return validate_brief(brief)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_ingestion.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/ingestion.py backend/tests/test_ingestion.py
git commit -m "feat: add RFP document ingestion module — PDF/DOCX text extraction and brief parsing"
```

---

## Task 6: Wire Ingestion to Worker and API

**Files:**
- Modify: `backend/app/workers/tasks.py:71-75`
- Modify: `backend/app/api/rfps.py:27-45`

- [ ] **Step 1: Write failing test for ingest_rfp_task**

Add to `backend/tests/test_ingestion.py`:
```python
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


class TestIngestRfpTask:
    def test_task_exists(self):
        from app.workers.tasks import ingest_rfp_task
        assert ingest_rfp_task is not None

    @patch("app.workers.tasks.parse_brief", new_callable=AsyncMock)
    @patch("app.workers.tasks.extract_text")
    def test_task_updates_rfp_with_parsed_brief(self, mock_extract, mock_parse):
        from app.workers.tasks import ingest_rfp_task
        from app.models.database import SessionLocal

        mock_extract.return_value = "RFP text content"
        mock_parse.return_value = {
            "title": "IT Modernization",
            "agency": "Ohio DAS",
            "state": "Ohio",
            "category": "IT",
            "deadline": "2026-05-15",
            "estimated_value": 2500000,
            "requirements": ["5 years experience"],
            "scope": "Cloud migration",
            "evaluation_criteria": {"technical": 40},
        }

        # Mock DB
        mock_rfp = MagicMock()
        mock_rfp.meta = {"filename": "test.pdf"}
        mock_rfp.raw_document_url = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_rfp

        with patch("app.workers.tasks.SessionLocal", return_value=mock_db):
            # The task should call extract_text and parse_brief
            # and update the RFP's extracted_brief
            import base64
            encoded = base64.b64encode(b"fake pdf bytes").decode()
            result = ingest_rfp_task("test-rfp-id", file_content_b64=encoded, filename="test.pdf")

        assert result["status"] == "ingested"
        mock_extract.assert_called_once()
        mock_parse.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_ingestion.py::TestIngestRfpTask -v`
Expected: FAIL — task is a stub

- [ ] **Step 3: Implement `ingest_rfp_task` in workers/tasks.py**

Replace the stub `ingest_rfp_task` in `backend/app/workers/tasks.py`:
```python
@celery_app.task
def ingest_rfp_task(rfp_id: str, file_content_b64: str = None, filename: str = None, file_url: str = None):
    """Parse and ingest an RFP document into a structured brief.

    Note: file_content_b64 is base64-encoded because Celery uses JSON serialization
    which cannot transport raw bytes.
    """
    import base64
    from datetime import datetime, timezone

    from app.agents.ingestion import extract_text, parse_brief
    from app.models.database import SessionLocal, RFP

    db = SessionLocal()
    try:
        rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
        if not rfp:
            return {"error": "RFP not found", "rfp_id": rfp_id}

        # Decode base64 content if provided
        content = base64.b64decode(file_content_b64) if file_content_b64 else None
        fname = filename or rfp.meta.get("filename", "document.txt") if rfp.meta else "document.txt"

        if content is None and (file_url or rfp.raw_document_url):
            import httpx
            url = file_url or rfp.raw_document_url
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            content = resp.content
            fname = url.rsplit("/", 1)[-1] if "/" in url else "document.pdf"

        if content is None:
            return {"error": "No document content available", "rfp_id": rfp_id}

        text = extract_text(content, fname)
        brief = asyncio.run(parse_brief(text))

        rfp.extracted_brief = brief
        rfp.title = brief.get("title", rfp.title)
        rfp.agency_name = brief.get("agency")
        rfp.agency_state = brief.get("state")
        rfp.category = brief.get("category")
        if brief.get("estimated_value"):
            rfp.estimated_value = brief["estimated_value"]
        rfp.ingested_at = datetime.now(timezone.utc)
        db.commit()

        return {"rfp_id": rfp_id, "status": "ingested", "title": brief.get("title")}

    except Exception as e:
        db.rollback()
        return {"rfp_id": rfp_id, "status": "error", "error": str(e)}
    finally:
        db.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/test_ingestion.py::TestIngestRfpTask -v`
Expected: PASS

- [ ] **Step 5: Update upload endpoint to store content and queue ingestion**

In `backend/app/api/rfps.py`, update the upload endpoint:
```python
@router.post("/upload")
async def upload_rfp(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    rfp = RFP(
        title=file.filename or "Untitled",
        source="manual",
        meta={"filename": file.filename, "size": len(content)},
    )
    db.add(rfp)
    db.commit()
    db.refresh(rfp)

    import base64
    from app.workers.tasks import ingest_rfp_task
    ingest_rfp_task.delay(str(rfp.id), file_content_b64=base64.b64encode(content).decode(), filename=file.filename)

    return {"id": str(rfp.id), "status": "queued", "filename": file.filename}
```

- [ ] **Step 6: Update ingest-url endpoint to queue ingestion**

In `backend/app/api/rfps.py`, update the ingest-url endpoint:
```python
@router.post("/ingest-url")
def ingest_url(url: str, db: Session = Depends(get_db)):
    rfp = RFP(title=url, source="manual", meta={"url": url})
    rfp.raw_document_url = url
    db.add(rfp)
    db.commit()
    db.refresh(rfp)

    from app.workers.tasks import ingest_rfp_task
    ingest_rfp_task.delay(str(rfp.id), file_url=url)

    return {"id": str(rfp.id), "status": "queued", "url": url}
```

- [ ] **Step 7: Run full test suite**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/ -v --ignore=tests/test_integration.py`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/workers/tasks.py backend/app/api/rfps.py
git commit -m "feat: wire RFP ingestion to Celery worker and API upload/ingest-url endpoints"
```

---

## Task 7: End-to-End Verification

**Files:**
- Modify: `backend/tests/test_integration.py` (optional)

- [ ] **Step 1: Run full unit test suite**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/ -v --ignore=tests/test_integration.py`
Expected: All tests pass (new + existing)

- [ ] **Step 2: Verify imports and module structure**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -c "from app.agents.orchestrator import proposal_graph, should_revise; from app.agents.ingestion import extract_text, parse_brief; from app.agents.base import _api_semaphore; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Verify graph structure includes revision node**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -c "from app.agents.orchestrator import proposal_graph; nodes = set(proposal_graph.get_graph().nodes.keys()); print('Nodes:', nodes); assert 'revision' in nodes; print('Graph OK')"`
Expected: `Nodes: {..., 'revision', ...}` and `Graph OK`

- [ ] **Step 4: Run full test suite one final time**

Run: `cd /Users/bb/conductor/workspaces/blackbox/edinburgh/backend && python -m pytest tests/ -v --ignore=tests/test_integration.py --tb=short`
Expected: All tests pass, no warnings

- [ ] **Step 5: Commit any remaining fixes**

Only if needed — skip if everything passes clean.
