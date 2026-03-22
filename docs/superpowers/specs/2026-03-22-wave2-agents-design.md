# Wave 2: Specialist Agents Design

## Overview

Implement the 5 specialist agents for the Blackbox RFP proposal system and wire them into the LangGraph orchestrator. All scaffolding exists (Wave 1). This wave fills in the agent classes, enables parallel execution for Solution + Compliance, and connects the pipeline to the Celery worker task.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Solution + Compliance execution | Parallel fan-out | Independent agents; matches CLAUDE.md intent |
| Anthropic client | `AsyncAnthropic` | `BaseAgent.run()` is already `async def`; enables real concurrency |
| Cost calculation location | Inside `CostAgent` | One agent, one file; no premature abstraction |
| Embedding provider | Voyage (via `voyageai` package) | Anthropic-owned; single vendor |
| Agent responsibility | Smart agents, thin orchestrator | Matches existing `BaseAgent` design with `inject_context()` |

## BaseAgent Changes

Two changes to `backend/app/agents/base.py`:

1. **`AsyncAnthropic` client** — replace `Anthropic` with `AsyncAnthropic`. Change `self.client.messages.create(...)` to `await self.client.messages.create(...)`. No signature changes needed.

2. **`max_tokens` class attribute** — extract the hardcoded `4096` to a class attribute so subclasses can override (SolutionAgent and ComplianceAgent need `8192`).

## Orchestrator Changes

Three changes to `backend/app/agents/orchestrator.py`:

1. **Async node functions** — all nodes become `async def`, each 3-5 lines: instantiate agent, call `await agent.run()`, return updated state dict.

2. **Parallel fan-out** — replace sequential `solution → comply` with a single `solution_comply_node` that runs both agents via `asyncio.gather`:

```python
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
```

Graph becomes: `qualify → (conditional) → solution_comply → cost → review → END`

3. **Add `proposal_id: str` to `ProposalState`** — passed through to agent runs for logging.

## Agent Specifications

### QualificationAgent (`backend/app/agents/qualification.py`)

| Attribute | Value |
|-----------|-------|
| agent_type | `"qualify"` |
| model | `"claude-haiku-4-5-20251001"` |
| temperature | `0.1` |
| max_tokens | `4096` (default) |

**inject_context:** Query `CompanyKnowledge` for types `cert`, `certification`, `capability`. Add ConsultAdd's qualifications list to context.

**build_prompt:** System prompt: government RFP qualification classifier for ConsultAdd (30-person IT consulting company in India, state/local government RFPs). User prompt: `rfp_brief` + injected qualifications. Instructs deterministic checks first (cert match, state registration, revenue threshold, years in business, category), then LLM judgment on soft factors. Flag anything missing but acquirable before deadline.

**validate_output schema:**
```json
{
  "qualified": bool,
  "confidence": float,       // 0.0-1.0
  "reasons": [str],
  "missing": [str],
  "recommendation": "go" | "no-go" | "conditional"
}
```

### SolutionAgent (`backend/app/agents/solution.py`)

| Attribute | Value |
|-----------|-------|
| agent_type | `"solution"` |
| model | `"claude-opus-4-6"` |
| temperature | `0.4` |
| max_tokens | `8192` |

**inject_context:** Query `CompanyKnowledge` for types `capability`, `reference`, `ratecard`. Query `ProposalEmbedding` via pgvector cosine similarity — embed the RFP brief using Voyage (`voyage-3-large`), retrieve top-3 similar past proposals. Graceful fallback to empty list if no embeddings exist.

**build_prompt:** System prompt: technical proposal writer for ConsultAdd. User prompt: `rfp_brief` + `qualification` output + injected capabilities/references/rate cards + similar past proposals. Must ground claims in real capabilities. Reference specific past wins when available. Never claim capabilities ConsultAdd doesn't have.

**validate_output schema:**
```json
{
  "approach": str,            // markdown
  "staffing_plan": str,
  "timeline": str,
  "technology_stack": [str],
  "confidence": float         // 0.0-1.0
}
```

### ComplianceAgent (`backend/app/agents/compliance.py`)

| Attribute | Value |
|-----------|-------|
| agent_type | `"comply"` |
| model | `"claude-opus-4-6"` |
| temperature | `0.2` |
| max_tokens | `8192` |

**inject_context:** Query `CompanyKnowledge` for types `cert`, `certification`, `boilerplate`. Load standard boilerplate texts (EEO, non-collusion, transmittal letters).

**build_prompt:** System prompt: government RFP compliance specialist. User prompt: `rfp_brief` + `qualification` output + injected certs/boilerplate. Must never fabricate certifications. If a required cert is missing, flag it explicitly with acquisition timeline. Use boilerplate verbatim where available.

**validate_output schema:**
```json
{
  "narrative": str,           // markdown
  "forms_checklist": [
    {"form": str, "status": "have" | "need" | "na"}
  ],
  "certifications_cited": [str],
  "flags": [str],
  "confidence": float         // 0.0-1.0
}
```

### CostAgent (`backend/app/agents/cost.py`)

| Attribute | Value |
|-----------|-------|
| agent_type | `"cost"` |
| model | `"claude-sonnet-4-6"` |
| temperature | `0.2` |
| max_tokens | `4096` (default) |

**inject_context:** Query `CompanyKnowledge` for types `ratecard`, `rate`. Load hourly/daily rates by role.

**calculate_costs(context) -> dict:** Deterministic Python method called before `build_prompt()`. Parses staffing plan from `solution` output, looks up each role's rate from rate card, computes `rate * hours * headcount` per role, sums subtotals, adds margin. Flags any roles missing from rate card. Returns structured cost breakdown dict.

**build_prompt:** System prompt: cost proposal assembler. User prompt: `rfp_brief` + `solution` output + pre-computed cost breakdown. LLM writes the narrative justification only — does not compute numbers.

**validate_output schema:**
```json
{
  "labor_costs": {
    "roles": [
      {"title": str, "rate": float, "hours": int, "total": float}
    ],
    "subtotal": float
  },
  "other_costs": [{"item": str, "amount": float}],
  "total": float,
  "narrative": str,           // markdown
  "confidence": float         // 0.0-1.0
}
```

**Validation rule:** The numbers in LLM output must match the deterministic calculation. Reject if they diverge.

### ReviewAgent (`backend/app/agents/review.py`)

| Attribute | Value |
|-----------|-------|
| agent_type | `"review"` |
| model | `"claude-sonnet-4-6"` |
| temperature | `0.1` |
| max_tokens | `4096` (default) |

**inject_context:** No DB queries. Works entirely from other agents' outputs.

**build_prompt:** System prompt: proposal QA reviewer. User prompt: all 4 prior outputs (`qualification`, `solution`, `compliance`, `cost`). Checks: staffing counts match between solution and cost, timeline consistency, no contradicting claims, all RFP requirements addressed, formatting issues.

**validate_output schema:**
```json
{
  "contradictions": [
    {"sections": [str, str], "issue": str, "severity": "high" | "medium" | "low"}
  ],
  "missing_sections": [str],
  "formatting_issues": [str],
  "quality_score": float,     // 0.0-1.0
  "recommendation": "ready" | "needs_revision" | "major_issues",
  "confidence": float         // 0.0-1.0
}
```

## Worker Task Wiring

Update `generate_proposal_task` in `backend/app/workers/tasks.py`:

```python
import asyncio
from app.agents.orchestrator import proposal_graph

# Inside generate_proposal_task, after setting status to "generating":
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
```

On exception: set `proposal.status = "queued"`, let Celery retry (existing `max_retries=2`).

`asyncio.run()` bridges the sync Celery worker to the async orchestrator — each task gets its own event loop.

## Dependencies & Schema Changes

1. **Add `voyageai` to `backend/pyproject.toml`** — for SolutionAgent's embedding query.
2. **Update `ProposalEmbedding.embedding`** — change `Vector(1536)` to `Vector(1024)` to match Voyage's `voyage-3-large` output dimensions. Table is empty so this is a no-op migration.
3. **Add `voyage_model` to `backend/app/config.py`** — default `"voyage-3-large"`.

## ConsultAdd Context (for system prompts)

All agent system prompts should include this grounding context:
- IT consulting company, 30-person team in India
- State/local government RFPs only (no federal)
- Wins on competitive cost, not boutique quality
- Current win rate: 3-4% (volume strategy)
- Target: 10x proposal volume with same headcount

## Test Strategy

Test files in `backend/tests/`, one per agent:

**Unit tests (no API calls, no DB):**
- `validate_output()` with valid JSON, invalid JSON, missing fields, wrong types
- `build_prompt()` returns tuple of two non-empty strings with expected keywords
- CostAgent `calculate_costs()` with known inputs produces expected outputs; missing rate card role is flagged

**Integration tests (`pytest.mark.integration`, need `ANTHROPIC_API_KEY`):**
- Each agent's `run()` with a minimal mock RFP brief
- Orchestrator end-to-end: `proposal_graph.ainvoke()` with mock RFP brief

**Fixtures:** shared `conftest.py` with sample `rfp_brief` dict and sample `CompanyKnowledge` rows.

## File Manifest

| Action | File |
|--------|------|
| Edit | `backend/app/agents/base.py` |
| Edit | `backend/app/agents/orchestrator.py` |
| Edit | `backend/app/agents/__init__.py` |
| Edit | `backend/app/workers/tasks.py` |
| Edit | `backend/app/models/database.py` |
| Edit | `backend/app/config.py` |
| Edit | `backend/pyproject.toml` |
| Create | `backend/app/agents/qualification.py` |
| Create | `backend/app/agents/solution.py` |
| Create | `backend/app/agents/compliance.py` |
| Create | `backend/app/agents/cost.py` |
| Create | `backend/app/agents/review.py` |
| Create | `backend/tests/conftest.py` |
| Create | `backend/tests/test_qualification.py` |
| Create | `backend/tests/test_solution.py` |
| Create | `backend/tests/test_compliance.py` |
| Create | `backend/tests/test_cost.py` |
| Create | `backend/tests/test_review.py` |
| Create | `backend/tests/test_orchestrator.py` |
