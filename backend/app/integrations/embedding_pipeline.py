"""Auto-embed winning proposals for similarity search."""

import logging

from app.config import settings
from app.models.database import SessionLocal, Proposal, ProposalEmbedding

logger = logging.getLogger(__name__)


def embed_winning_proposals() -> dict:
    """Find won proposals without embeddings and embed them."""
    if not settings.voyage_api_key:
        logger.warning("VOYAGE_API_KEY not set, skipping embedding")
        return {"embedded": 0, "skipped": 0, "errors": 0, "message": "No API key"}

    db = SessionLocal()
    summary = {"embedded": 0, "skipped": 0, "errors": 0}

    try:
        embedded_ids = db.query(ProposalEmbedding.proposal_id).distinct().subquery()

        proposals = (
            db.query(Proposal)
            .filter(
                Proposal.outcome == "won",
                Proposal.solution_section.isnot(None),
                Proposal.solution_section != "",
                ~Proposal.id.in_(db.query(embedded_ids.c.proposal_id)),
            )
            .all()
        )

        if not proposals:
            logger.info("No winning proposals to embed")
            return summary

        import voyageai
        vo = voyageai.Client(api_key=settings.voyage_api_key)

        batch_size = 10
        for i in range(0, len(proposals), batch_size):
            batch = proposals[i : i + batch_size]
            texts = [p.solution_section for p in batch]

            try:
                result = vo.embed(texts, model=settings.voyage_model)

                for proposal, embedding in zip(batch, result.embeddings):
                    pe = ProposalEmbedding(
                        proposal_id=proposal.id,
                        embedding=embedding,
                        section="solution",
                    )
                    db.add(pe)
                    summary["embedded"] += 1

                db.commit()

            except Exception as e:
                logger.error(f"Embedding batch failed: {e}")
                summary["errors"] += 1
                db.rollback()

        return summary

    finally:
        db.close()
