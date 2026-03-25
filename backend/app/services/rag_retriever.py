"""RAG retriever — Pinecone queries with per-agent namespace + metadata filter presets.

Each agent type has a preset that defines:
  - Which namespaces to query
  - What metadata filters to apply (e.g. outcome=won, type=cert)
  - How many results to return per namespace

Usage in agents:
    results = await retrieve_for_agent("solution", rfp_brief_text)
    # results is a dict: {namespace: [{"text", "score", "metadata"}]}

Usage for direct proposal similarity:
    similar = await retrieve_similar_proposals(rfp_brief_text, section="solution")
"""
import logging

from app.services import embedding as emb_service
from app.services import pinecone_store as pc_store

logger = logging.getLogger(__name__)


# ── Per-agent retrieval presets ───────────────────────────────────────────────
# Format: {namespace: (filter_dict, top_k)}
# Empty filter dict {} means no metadata filter applied.

_AGENT_PRESETS: dict[str, dict[str, tuple[dict, int]]] = {
    "qualify": {
        pc_store.NS_COMPANY_KNOWLEDGE: (
            {"type": {"$in": ["cert", "certification", "capability"]}},
            6,
        ),
        pc_store.NS_RFPS: (
            {},  # Similar RFPs (any outcome for context)
            3,
        ),
    },
    "solution": {
        pc_store.NS_PROPOSALS: (
            {"section": {"$eq": "solution"}, "outcome": {"$eq": "won"}},
            3,
        ),
        pc_store.NS_COMPANY_KNOWLEDGE: (
            {"type": {"$in": ["capability", "reference", "ratecard"]}},
            6,
        ),
    },
    "comply": {
        pc_store.NS_PROPOSALS: (
            {"section": {"$eq": "compliance"}, "outcome": {"$eq": "won"}},
            3,
        ),
        pc_store.NS_COMPANY_KNOWLEDGE: (
            {"type": {"$in": ["cert", "certification", "boilerplate"]}},
            6,
        ),
    },
    "cost": {
        pc_store.NS_COMPETITOR_INTEL: (
            {},
            5,
        ),
        pc_store.NS_COMPANY_KNOWLEDGE: (
            {"type": {"$in": ["ratecard", "rate"]}},
            4,
        ),
        pc_store.NS_PROPOSALS: (
            {"section": {"$eq": "cost"}, "outcome": {"$eq": "won"}},
            2,
        ),
    },
    "review": {
        pc_store.NS_PROPOSALS: (
            {"outcome": {"$eq": "won"}, "quality_score": {"$gte": 0.85}},
            3,
        ),
    },
}


# ── Main retrieval API ────────────────────────────────────────────────────────

async def retrieve_for_agent(
    agent_type: str,
    query_text: str,
    extra_filters: dict | None = None,
) -> dict[str, list[dict]]:
    """Retrieve RAG context for a specific agent.

    Embeds query_text and runs all namespace queries defined in the agent's preset.
    Returns {namespace: [{"text": str, "score": float, "metadata": dict}]}.

    extra_filters are merged into every namespace's filter (useful for agency-specific
    narrowing, e.g. {"agency_state": {"$eq": "TX"}}).
    """
    if not query_text or not query_text.strip():
        return {}

    preset = _AGENT_PRESETS.get(agent_type)
    if not preset:
        logger.debug(f"No RAG preset configured for agent_type='{agent_type}'")
        return {}

    query_vector = await emb_service.embed_one(query_text)
    if query_vector is None:
        logger.warning(f"Could not embed query for {agent_type} — RAG skipped")
        return {}

    results: dict[str, list[dict]] = {}

    for namespace, (base_filter, top_k) in preset.items():
        merged_filter = {**base_filter, **(extra_filters or {})}
        matches = pc_store.query(
            vector=query_vector,
            namespace=namespace,
            top_k=top_k,
            filter=merged_filter if merged_filter else None,
        )
        results[namespace] = [
            {
                "text": m["metadata"].get("text", ""),
                "score": round(m["score"], 4),
                "metadata": {k: v for k, v in m["metadata"].items() if k != "text"},
            }
            for m in matches
        ]

    return results


async def retrieve_similar_proposals(
    query_text: str,
    section: str = "solution",
    outcome_filter: str | None = "won",
    top_k: int = 3,
) -> list[dict]:
    """Convenience helper: find similar proposal sections.

    Replaces the Voyage + pgvector approach previously used in SolutionAgent.
    Returns list of {"section", "proposal_id", "score", "text", "agency", "outcome"}.
    """
    query_vector = await emb_service.embed_one(query_text)
    if query_vector is None:
        return []

    pc_filter: dict = {"section": {"$eq": section}}
    if outcome_filter:
        pc_filter["outcome"] = {"$eq": outcome_filter}

    matches = pc_store.query(
        vector=query_vector,
        namespace=pc_store.NS_PROPOSALS,
        top_k=top_k,
        filter=pc_filter,
    )

    return [
        {
            "section": m["metadata"].get("section", section),
            "proposal_id": m["metadata"].get("proposal_id", ""),
            "score": round(m["score"], 4),
            "text": m["metadata"].get("text", ""),
            "agency": m["metadata"].get("agency_name", ""),
            "outcome": m["metadata"].get("outcome", ""),
        }
        for m in matches
    ]


# ── Prompt formatting helper ──────────────────────────────────────────────────

def format_rag_context_for_prompt(
    rag_results: dict[str, list[dict]],
    agent_type: str,
    max_snippets: int = 3,
) -> str:
    """Format RAG results into a clean prompt section.

    Produces a markdown block ready to inject into agent prompts.
    Skips empty namespaces. Limits to max_snippets total to control token usage.
    """
    if not rag_results:
        return ""

    _NS_LABELS = {
        pc_store.NS_PROPOSALS: "Similar Winning Proposals",
        pc_store.NS_RFPS: "Similar Past RFPs",
        pc_store.NS_COMPANY_KNOWLEDGE: "ConsultAdd Knowledge Base",
        pc_store.NS_COMPETITOR_INTEL: "Competitor Intelligence",
        pc_store.NS_SLACK_THREADS: "Internal Discussions",
    }

    lines: list[str] = ["## RAG Context (retrieved from knowledge base)"]
    snippet_count = 0

    for namespace, matches in rag_results.items():
        if not matches or snippet_count >= max_snippets:
            break
        label = _NS_LABELS.get(namespace, namespace)
        lines.append(f"\n### {label}")
        for m in matches:
            if snippet_count >= max_snippets:
                break
            meta = m.get("metadata", {})
            score = m.get("score", 0)
            text = m.get("text", "").strip()
            if not text:
                continue

            # Build a concise header line from available metadata
            header_parts = [f"Score: {score:.2f}"]
            if meta.get("agency_name"):
                header_parts.append(f"Agency: {meta['agency_name']}")
            if meta.get("outcome"):
                header_parts.append(f"Outcome: {meta['outcome']}")
            if meta.get("type"):
                header_parts.append(f"Type: {meta['type']}")
            if meta.get("section"):
                header_parts.append(f"Section: {meta['section']}")

            lines.append(f"[{' | '.join(header_parts)}]")
            # Truncate long snippets
            snippet = text[:600] + ("..." if len(text) > 600 else "")
            lines.append(f'"{snippet}"')
            lines.append("")
            snippet_count += 1

    return "\n".join(lines) if snippet_count > 0 else ""
