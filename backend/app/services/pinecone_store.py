"""Pinecone vector store wrapper — namespace routing, upsert, query, delete.

Index config (serverless, free tier):
  - Dimension : 1536  (OpenAI text-embedding-3-small)
  - Metric    : cosine
  - Cloud     : aws / us-east-1  (configurable via settings)

Namespaces:
  proposals         — past proposal sections with outcome metadata
  rfps              — RFP documents/briefs
  company_knowledge — certs, capabilities, rate cards, boilerplate
  competitor_intel  — competitor pricing and positioning data
  slack_threads     — Slack discussion threads
"""
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ── Namespace constants ────────────────────────────────────────────────────────
NS_PROPOSALS = "proposals"
NS_RFPS = "rfps"
NS_COMPANY_KNOWLEDGE = "company_knowledge"
NS_COMPETITOR_INTEL = "competitor_intel"
NS_SLACK_THREADS = "slack_threads"

_index = None


def _get_index():
    """Lazy-initialize and cache the Pinecone index connection."""
    global _index
    if _index is not None:
        return _index

    if not settings.pinecone_api_key:
        logger.warning("PINECONE_API_KEY not set — all Pinecone operations will be no-ops")
        return None

    try:
        from pinecone import Pinecone, ServerlessSpec

        pc = Pinecone(api_key=settings.pinecone_api_key)
        index_name = settings.pinecone_index_name

        existing_names = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing_names:
            logger.info(f"Creating Pinecone index '{index_name}' (1536-dim cosine, serverless)")
            pc.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=settings.pinecone_cloud,
                    region=settings.pinecone_region,
                ),
            )

        _index = pc.Index(index_name)
        logger.info(f"Pinecone index '{index_name}' ready")
        return _index

    except Exception as e:
        logger.error(f"Pinecone initialization failed: {e}")
        return None


def reset_index_cache():
    """Force re-connection on next access (useful for tests)."""
    global _index
    _index = None


# ── Write operations ──────────────────────────────────────────────────────────

def upsert(vectors: list[dict], namespace: str) -> bool:
    """Upsert a batch of vectors into the given namespace.

    Each vector must be: {"id": str, "values": list[float], "metadata": dict}
    Automatically batches in groups of 100 (Pinecone limit).
    Returns True on success, False on failure/skip.
    """
    if not vectors:
        return True

    index = _get_index()
    if index is None:
        return False

    try:
        for i in range(0, len(vectors), 100):
            batch = vectors[i : i + 100]
            index.upsert(vectors=batch, namespace=namespace)
        logger.debug(f"Upserted {len(vectors)} vectors → ns={namespace}")
        return True
    except Exception as e:
        logger.error(f"Pinecone upsert failed (ns={namespace}): {e}")
        return False


def delete_by_filter(namespace: str, filter: dict) -> bool:
    """Delete all vectors matching a metadata filter in a namespace."""
    index = _get_index()
    if index is None:
        return False
    try:
        index.delete(filter=filter, namespace=namespace)
        return True
    except Exception as e:
        # 404 = namespace doesn't exist yet (first-time index) — not a real error
        err_str = str(e)
        if "404" in err_str or "Namespace not found" in err_str:
            logger.debug(f"Pinecone delete skipped (namespace '{namespace}' not yet created)")
        else:
            logger.error(f"Pinecone delete failed (ns={namespace}): {e}")
        return False


# ── Read operations ───────────────────────────────────────────────────────────

def query(
    vector: list[float],
    namespace: str,
    top_k: int = 5,
    filter: dict | None = None,
    include_metadata: bool = True,
) -> list[dict]:
    """Query nearest neighbours in a namespace.

    Returns list of {"id": str, "score": float, "metadata": dict}.
    Returns [] on failure or if Pinecone is not configured.
    """
    index = _get_index()
    if index is None:
        return []

    try:
        kwargs: dict[str, Any] = {
            "vector": vector,
            "top_k": top_k,
            "namespace": namespace,
            "include_metadata": include_metadata,
        }
        if filter:
            kwargs["filter"] = filter

        response = index.query(**kwargs)
        return [
            {
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata or {},
            }
            for match in response.matches
        ]
    except Exception as e:
        logger.error(f"Pinecone query failed (ns={namespace}): {e}")
        return []


def describe_index_stats() -> dict:
    """Return index stats (vector count per namespace) for monitoring."""
    index = _get_index()
    if index is None:
        return {}
    try:
        stats = index.describe_index_stats()
        return {
            "total_vector_count": stats.total_vector_count,
            "namespaces": {
                ns: {"vector_count": data.vector_count}
                for ns, data in (stats.namespaces or {}).items()
            },
        }
    except Exception as e:
        logger.error(f"Pinecone stats failed: {e}")
        return {}
