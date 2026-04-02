# Blackbox Agent Configurations for Paperclip

## How to Use These Prompts

Each prompt file (CEO.md, INTAKE.md, SCOPING.md, RESEARCH.md, WRITING.md, QA.md) goes into the
`adapterConfig.promptTemplate` field when creating the agent via Paperclip's hire API.

Template variables available: `{{ agent.id }}`, `{{ agent.name }}`, `{{ agent.role }}`

## Agent Hierarchy

```
Board (you)
  └── CEO Agent
        ├── Intake Agent
        ├── Scoping Agent
        ├── Research Agent
        ├── Writing Agent
        └── QA Agent
```

## Agent Creation Payloads

### 1. CEO Agent

```json
{
  "name": "BlackboxCEO",
  "role": "ceo",
  "title": "Chief Executive Officer",
  "icon": "crown",
  "reportsTo": null,
  "capabilities": "Orchestrates the RFP proposal pipeline. Delegates to 5 specialist agents, makes go/no-go decisions based on qualification scores, monitors pipeline health and costs.",
  "adapterType": "claude_local",
  "adapterConfig": {
    "cwd": "/path/to/blackbox",
    "model": "claude-sonnet-4-5-20250929",
    "promptTemplate": "<contents of CEO.md>"
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": true,
      "intervalSec": 300,
      "wakeOnDemand": true
    }
  },
  "budgetMonthlyCents": 50000
}
```

### 2. Intake Agent

```json
{
  "name": "Intake",
  "role": "engineer",
  "title": "RFP Intake Specialist",
  "icon": "inbox",
  "reportsTo": "<ceo-agent-id>",
  "capabilities": "Parses RFP documents (PDF/DOCX) into structured JSON intake objects. Extracts agency, scope, deadline, evaluation criteria, format requirements.",
  "adapterType": "claude_local",
  "adapterConfig": {
    "cwd": "/path/to/blackbox",
    "model": "claude-haiku-4-5-20251001",
    "promptTemplate": "<contents of INTAKE.md>"
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": true,
      "intervalSec": 300,
      "wakeOnDemand": true
    }
  },
  "budgetMonthlyCents": 2000
}
```

### 3. Scoping Agent

```json
{
  "name": "Scoping",
  "role": "engineer",
  "title": "Proposal Strategy Analyst",
  "icon": "target",
  "reportsTo": "<ceo-agent-id>",
  "capabilities": "Analyzes RFP requirements and produces proposal strategy briefs: framework selection, section emphasis, past client matching, compliance mapping.",
  "adapterType": "claude_local",
  "adapterConfig": {
    "cwd": "/path/to/blackbox",
    "model": "claude-sonnet-4-5-20250929",
    "promptTemplate": "<contents of SCOPING.md>"
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": true,
      "intervalSec": 300,
      "wakeOnDemand": true
    }
  },
  "budgetMonthlyCents": 5000
}
```

### 4. Research Agent (Capture Intelligence)

```json
{
  "name": "Research",
  "role": "researcher",
  "title": "Capture Intelligence Lead",
  "icon": "search",
  "reportsTo": "<ceo-agent-id>",
  "capabilities": "Produces agency dossiers via web search and HigherGov. Scores opportunities 0-100 with GO/PURSUE/CONDITIONAL/PASS. The crown jewel of the pipeline.",
  "adapterType": "claude_local",
  "adapterConfig": {
    "cwd": "/path/to/blackbox",
    "model": "claude-sonnet-4-5-20250929",
    "promptTemplate": "<contents of RESEARCH.md>"
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": true,
      "intervalSec": 300,
      "wakeOnDemand": true
    }
  },
  "budgetMonthlyCents": 15000
}
```

### 5. Writing Agent

```json
{
  "name": "Writer",
  "role": "engineer",
  "title": "Senior Proposal Writer",
  "icon": "pen",
  "reportsTo": "<ceo-agent-id>",
  "capabilities": "Drafts full government proposals using ConsultAdd v3 methodology. Generates proprietary frameworks (LAUNCH, SHIELD, PULSE, etc.), implements spine effect, self-checks via Gate 1 and Gate 2.",
  "adapterType": "claude_local",
  "adapterConfig": {
    "cwd": "/path/to/blackbox",
    "model": "claude-opus-4-6",
    "promptTemplate": "<contents of WRITING.md>"
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": true,
      "intervalSec": 600,
      "wakeOnDemand": true
    }
  },
  "budgetMonthlyCents": 200000
}
```

### 6. QA Agent

```json
{
  "name": "QualityReview",
  "role": "engineer",
  "title": "Proposal Quality Assurance",
  "icon": "shield-check",
  "reportsTo": "<ceo-agent-id>",
  "capabilities": "Independent proposal review against RFP evaluation criteria. No access to Writing Agent prompt. Checks compliance, personalization, consistency, AI speak detection.",
  "adapterType": "claude_local",
  "adapterConfig": {
    "cwd": "/path/to/blackbox",
    "model": "claude-opus-4-6",
    "promptTemplate": "<contents of QA.md>"
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": true,
      "intervalSec": 300,
      "wakeOnDemand": true
    }
  },
  "budgetMonthlyCents": 50000
}
```

## Monthly Budget Summary

| Agent | Model | Budget | Rationale |
|-------|-------|--------|-----------|
| CEO | Sonnet | $500 | Orchestration only, low token usage |
| Intake | Haiku | $20 | Fast parsing, cheap per-call |
| Scoping | Sonnet | $50 | Analysis, moderate complexity |
| Research | Sonnet | $150 | Heavy search + synthesis |
| Writing | Opus | $2,000 | Highest quality needed, most tokens |
| QA | Opus | $500 | Independent review, thorough |
| **Total** | | **$3,270** | At 100 RFPs/month with ~50% PASS rate |

## Task Flow via Paperclip Issues

The CEO creates issues (tasks) and assigns them to agents. Each issue flows through:

```
todo -> [checkout] -> in_progress -> done
                   -> blocked (if stuck)
```

**Issue naming convention:**
- `[INTAKE] DC Water - IT App Dev Services - RFP-2025-001`
- `[SCOPE] DC Water - IT App Dev Services`
- `[RESEARCH] DC Water - IT App Dev Services`
- `[WRITE] DC Water - IT App Dev Services`
- `[QA] DC Water - IT App Dev Services`

**Parent-child structure:**
- Parent issue: "RFP: DC Water IT App Dev Services"
  - Child: [INTAKE] ...
  - Child: [SCOPE] ...
  - Child: [RESEARCH] ...
  - Child: [WRITE] ... (only if PURSUE+)
  - Child: [QA] ... (only if written)
