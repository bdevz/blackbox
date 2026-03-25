"""RAG indexer — chunks, embeds, and dual-writes to Pinecone (primary) + pgvector (legacy).

Indexing triggers (all immediate, no batching):
  index_proposal(proposal_id)       — called when proposal reaches draft/won/lost
  index_rfp(rfp_id)                 — called when an RFP is ingested
  index_company_knowledge(id)       — called when a knowledge row is upserted
  index_all_company_knowledge()     — bulk re-index (ETL or initial setup)

Pinecone is the primary store (1536-dim OpenAI embeddings).
pgvector retains its 1024-dim Voyage embeddings for backward compatibility;
new OpenAI vectors are NOT written there (dimension mismatch: 1536 vs 1024).
A future migration can unify both to 1536-dim if desired.
"""
import json
import logging
from datetime import datetime, timezone

from app.models.database import (
    CompanyKnowledge,
    Proposal,
    ProposalEmbedding,
    RFP,
    SessionLocal,
)
from app.services import embedding as emb_service
from app.services import pinecone_store as pc_store
from app.services.chunker import chunk_knowledge_entry, chunk_proposal_section, chunk_rfp

logger = logging.getLogger(__name__)


# ── Proposal indexing ─────────────────────────────────────────────────────────

async def index_proposal(proposal_id: str, db=None) -> int:
    """Index all sections of a proposal into Pinecone.

    Indexes: solution, compliance, cost (narrative), and assembled_document (full).
    Metadata includes outcome, agency, category, quality_score for filtered retrieval.
    Returns total number of vectors upserted.
    """
    close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if not proposal:
            logger.warning(f"Proposal {proposal_id} not found — skipping index")
            return 0

        rfp = db.query(RFP).filter(RFP.id == proposal.rfp_id).first()
        year = datetime.now(timezone.utc).year
        if rfp and rfp.created_at:
            year = rfp.created_at.year

        base_meta = {
            "proposal_id": str(proposal.id),
            "rfp_id": str(proposal.rfp_id),
            "outcome": proposal.outcome or "pending",
            "agency_name": (rfp.agency_name or "") if rfp else "",
            "agency_state": (rfp.agency_state or "") if rfp else "",
            "rfp_category": (rfp.category or "") if rfp else "",
            "estimated_value": float(rfp.estimated_value) if rfp and rfp.estimated_value else 0.0,
            "year": year,
            "quality_score": _extract_quality_score(proposal),
        }

        sections: list[tuple[str, str]] = []
        if proposal.solution_section:
            sections.append(("solution", proposal.solution_section))
        if proposal.compliance_section:
            sections.append(("compliance", proposal.compliance_section))
        if proposal.cost_section:
            sections.append(("cost", _cost_to_text(proposal.cost_section)))
        if proposal.assembled_document:
            sections.append(("full", proposal.assembled_document))

        total_upserted = 0

        for section_name, section_text in sections:
            chunks = chunk_proposal_section(
                text=section_text,
                section=section_name,
                proposal_id=str(proposal.id),
                extra_meta=base_meta,
            )
            if not chunks:
                continue

            vectors = await emb_service.embed([c.text for c in chunks])
            if not vectors or len(vectors) != len(chunks):
                continue

            pc_vectors = [
                {
                    "id": f"{proposal.id}_{section_name}_{i}",
                    "values": vec,
                    # Store first 1000 chars of chunk text for retrieval preview
                    "metadata": {**chunk.metadata, "text": chunk.text[:1000]},
                }
                for i, (chunk, vec) in enumerate(zip(chunks, vectors))
            ]
            if pc_store.upsert(pc_vectors, namespace=pc_store.NS_PROPOSALS):
                total_upserted += len(pc_vectors)

        if total_upserted:
            logger.info(f"Indexed proposal {proposal_id}: {total_upserted} vectors across {len(sections)} sections")

        return total_upserted

    finally:
        if close_db:
            db.close()


# ── RFP indexing ──────────────────────────────────────────────────────────────

async def index_rfp(rfp_id: str, db=None) -> int:
    """Index an RFP document into Pinecone NS_RFPS namespace."""
    close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
        if not rfp:
            return 0

        # Build indexable text from title + extracted brief
        brief = rfp.extracted_brief or {}
        rfp_text = f"# {rfp.title}\n\n{json.dumps(brief, indent=2)}"
        year = rfp.created_at.year if rfp.created_at else datetime.now(timezone.utc).year

        base_meta = {
            "rfp_id": str(rfp.id),
            "agency_name": rfp.agency_name or "",
            "agency_state": rfp.agency_state or "",
            "category": rfp.category or "",
            "estimated_value": float(rfp.estimated_value) if rfp.estimated_value else 0.0,
            "year": year,
            "source": rfp.source or "manual",
        }

        chunks = chunk_rfp(rfp_text, str(rfp.id), extra_meta=base_meta)
        if not chunks:
            return 0

        vectors = await emb_service.embed([c.text for c in chunks])
        if not vectors:
            return 0

        pc_vectors = [
            {
                "id": f"rfp_{rfp.id}_{i}",
                "values": vec,
                "metadata": {**chunk.metadata, "text": chunk.text[:1000]},
            }
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]

        # Remove stale vectors for this RFP before re-indexing
        pc_store.delete_by_filter(pc_store.NS_RFPS, {"rfp_id": {"$eq": str(rfp.id)}})
        pc_store.upsert(pc_vectors, namespace=pc_store.NS_RFPS)
        logger.info(f"Indexed RFP {rfp_id}: {len(pc_vectors)} vectors")
        return len(pc_vectors)

    finally:
        if close_db:
            db.close()


# ── Company knowledge indexing ────────────────────────────────────────────────

async def index_company_knowledge(knowledge_id: str, db=None) -> int:
    """Index a single CompanyKnowledge row into Pinecone NS_COMPANY_KNOWLEDGE."""
    close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        row = db.query(CompanyKnowledge).filter(CompanyKnowledge.id == knowledge_id).first()
        if not row:
            return 0

        value = row.value
        text = f"{row.key}: {json.dumps(value)}" if isinstance(value, dict) else f"{row.key}: {value}"

        meta = {
            "knowledge_id": str(row.id),
            "type": row.type,
            "key": row.key,
            "relevant_for_agents": _agents_for_type(row.type),
            "expires_at": row.expires_at.isoformat() if row.expires_at else "",
        }

        chunks = chunk_knowledge_entry(text, str(row.id), extra_meta=meta)
        if not chunks:
            return 0

        vectors = await emb_service.embed([c.text for c in chunks])
        if not vectors:
            return 0

        pc_vectors = [
            {
                "id": f"ck_{row.id}_{i}",
                "values": vec,
                "metadata": {**chunk.metadata, "text": chunk.text[:1000]},
            }
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]

        # Re-index: remove old vectors for this knowledge entry first
        pc_store.delete_by_filter(
            pc_store.NS_COMPANY_KNOWLEDGE,
            {"knowledge_id": {"$eq": str(row.id)}},
        )
        pc_store.upsert(pc_vectors, namespace=pc_store.NS_COMPANY_KNOWLEDGE)
        return len(pc_vectors)

    finally:
        if close_db:
            db.close()


async def index_all_company_knowledge(db=None) -> int:
    """Bulk re-index all CompanyKnowledge rows — use for initial setup or ETL refresh."""
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        rows = db.query(CompanyKnowledge).all()
        total = 0
        for row in rows:
            total += await index_company_knowledge(str(row.id), db)
        logger.info(f"Bulk indexed {total} company knowledge vectors from {len(rows)} rows")
        return total
    finally:
        if close_db:
            db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_quality_score(proposal: Proposal) -> float:
    if not proposal.review_result:
        return 0.0
    if isinstance(proposal.review_result, dict):
        return float(proposal.review_result.get("quality_score", 0.0))
    return 0.0


def _cost_to_text(cost_section) -> str:
    """Convert cost section (JSONB dict) to plain text for embedding."""
    if not isinstance(cost_section, dict):
        return str(cost_section)
    parts = []
    if cost_section.get("narrative"):
        parts.append(cost_section["narrative"])
    if cost_section.get("executive_oversight"):
        parts.append(cost_section["executive_oversight"])
    exclusions = cost_section.get("exclusions", [])
    if exclusions:
        parts.append("Exclusions: " + "; ".join(exclusions))
    return "\n\n".join(parts)


def _agents_for_type(knowledge_type: str) -> list[str]:
    """Map a KnowledgeType to the agent types that should retrieve it."""
    mapping: dict[str, list[str]] = {
        "cert": ["qualify", "comply"],
        "certification": ["qualify", "comply"],
        "capability": ["qualify", "solution"],
        "reference": ["solution"],
        "boilerplate": ["comply"],
        "ratecard": ["cost", "solution"],
        "rate": ["cost"],
        "slack_thread": ["qualify", "solution"],
    }
    return mapping.get(knowledge_type, [])
