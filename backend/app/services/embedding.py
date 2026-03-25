"""OpenAI embedding service — wraps text-embedding-3-small (1536-dim) for all RAG operations."""
import logging
from typing import Union

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed(texts: Union[str, list[str]], batch_size: int = 100) -> list[list[float]]:
    """Embed one or more texts using OpenAI text-embedding-3-small.

    Returns a list of 1536-dimensional vectors, one per input text.
    Batches requests to stay within API limits.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping embedding")
        return []

    if isinstance(texts, str):
        texts = [texts]

    if not texts:
        return []

    client = _get_client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = [t for t in texts[i : i + batch_size] if t and t.strip()]
        if not batch:
            continue
        try:
            response = await client.embeddings.create(
                model=settings.openai_embedding_model,
                input=batch,
            )
            # Sort by index to preserve order (OpenAI may reorder)
            batch_embeddings = [
                item.embedding
                for item in sorted(response.data, key=lambda x: x.index)
            ]
            all_embeddings.extend(batch_embeddings)
        except Exception as e:
            logger.error(f"Embedding batch {i // batch_size} failed: {e}")
            raise

    return all_embeddings


async def embed_one(text: str) -> list[float] | None:
    """Embed a single text string. Returns None if embedding fails or key not set."""
    if not text or not text.strip():
        return None
    try:
        results = await embed([text])
        return results[0] if results else None
    except Exception as e:
        logger.warning(f"embed_one failed: {e}")
        return None
