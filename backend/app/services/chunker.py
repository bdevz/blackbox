"""Semantic + structural chunking for proposal documents, RFP text, and knowledge entries.

Strategy:
  1. Structural split  — split at markdown headings, numbered sections, paragraph breaks
  2. Merge small       — join adjacent tiny segments below the min threshold
  3. Split large       — break oversized segments at sentence boundaries with overlap
"""
import re
from dataclasses import dataclass, field

# Approximate: 1 token ≈ 4 characters
MAX_CHUNK_TOKENS = 500   # ~2000 chars per chunk
MIN_CHUNK_TOKENS = 50    # ~200 chars — below this we merge with neighbour
OVERLAP_SENTENCES = 2    # sentences carried over for context continuity


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    chunk_index: int = 0
    total_chunks: int = 1


# ── Utilities ─────────────────────────────────────────────────────────────────

def _token_estimate(text: str) -> int:
    return len(text) // 4


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving sentence-ending punctuation."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if s.strip()]


# ── Chunking pipeline ─────────────────────────────────────────────────────────

def _split_structural(text: str) -> list[str]:
    """Split at structural boundaries: markdown headings, numbered sections, blank lines."""
    # Split before headings (# ## ###) and at double newlines (paragraph breaks)
    # Also split before numbered section markers like "1.", "2.3.", "Section 4"
    pattern = r"(?=\n#{1,3} |\n\d+\.[\d.]* |\n\n)"
    raw = re.split(pattern, text, flags=re.MULTILINE)
    return [seg.strip() for seg in raw if seg.strip()]


def _merge_small(segments: list[str]) -> list[str]:
    """Merge adjacent segments that are too small to be useful on their own."""
    merged: list[str] = []
    buffer = ""

    for seg in segments:
        if _token_estimate(buffer) + _token_estimate(seg) < MIN_CHUNK_TOKENS * 3:
            buffer = (buffer + "\n\n" + seg).strip() if buffer else seg
        else:
            if buffer:
                merged.append(buffer)
            buffer = seg

    if buffer:
        merged.append(buffer)

    return merged


def _split_large(segment: str) -> list[str]:
    """Split an oversized segment at sentence boundaries, carrying overlap forward."""
    if _token_estimate(segment) <= MAX_CHUNK_TOKENS:
        return [segment]

    sentences = _split_sentences(segment)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = _token_estimate(sent)
        if current_tokens + sent_tokens > MAX_CHUNK_TOKENS and current:
            chunks.append(" ".join(current))
            # Carry last N sentences for context continuity (overlap)
            overlap = current[-OVERLAP_SENTENCES:] if len(current) >= OVERLAP_SENTENCES else current[:]
            current = overlap
            current_tokens = sum(_token_estimate(s) for s in current)
        current.append(sent)
        current_tokens += sent_tokens

    if current:
        chunks.append(" ".join(current))

    return chunks


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_text(text: str, base_metadata: dict | None = None) -> list[Chunk]:
    """Full semantic + structural chunking pipeline.

    Steps:
      1. Split at structural markers (headings, numbered sections, paragraph breaks)
      2. Merge undersized adjacent segments
      3. Split oversized segments at sentence boundaries with overlap
      4. Attach metadata to each chunk
    """
    if not text or not text.strip():
        return []

    base_metadata = base_metadata or {}

    segments = _split_structural(text)
    segments = _merge_small(segments)

    final_texts: list[str] = []
    for seg in segments:
        final_texts.extend(_split_large(seg))

    total = len(final_texts)
    return [
        Chunk(
            text=chunk,
            metadata={**base_metadata, "chunk_index": i, "total_chunks": total},
            chunk_index=i,
            total_chunks=total,
        )
        for i, chunk in enumerate(final_texts)
        if chunk.strip()
    ]


def chunk_proposal_section(
    text: str,
    section: str,
    proposal_id: str,
    extra_meta: dict | None = None,
) -> list[Chunk]:
    """Chunk a single proposal section (solution / compliance / cost / full)."""
    meta = {
        "proposal_id": proposal_id,
        "section": section,
        **(extra_meta or {}),
    }
    return chunk_text(text, meta)


def chunk_rfp(rfp_text: str, rfp_id: str, extra_meta: dict | None = None) -> list[Chunk]:
    """Chunk an RFP document."""
    meta = {"rfp_id": rfp_id, **(extra_meta or {})}
    return chunk_text(rfp_text, meta)


def chunk_knowledge_entry(text: str, knowledge_id: str, extra_meta: dict | None = None) -> list[Chunk]:
    """Chunk a company knowledge entry."""
    meta = {"knowledge_id": knowledge_id, **(extra_meta or {})}
    return chunk_text(text, meta)
