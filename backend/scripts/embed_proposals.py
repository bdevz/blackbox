#!/usr/bin/env python
"""Embed existing proposals for pgvector similarity search.

Usage: cd backend && python -m scripts.embed_proposals
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import voyageai

from app.config import settings
from app.models.database import SessionLocal, Proposal, ProposalEmbedding


def embed():
    if not settings.voyage_api_key:
        print("VOYAGE_API_KEY not set — skipping embedding")
        return

    db = SessionLocal()
    try:
        # Find proposals with solution text but no embeddings
        already_embedded = (
            db.query(ProposalEmbedding.proposal_id)
            .filter(ProposalEmbedding.section == "solution")
            .subquery()
        )
        proposals = (
            db.query(Proposal)
            .filter(
                Proposal.solution_section.isnot(None),
                Proposal.solution_section != "",
                ~Proposal.id.in_(db.query(already_embedded.c.proposal_id)),
            )
            .all()
        )

        if not proposals:
            print("No proposals to embed")
            return

        print(f"Embedding {len(proposals)} proposals...")
        vo = voyageai.Client(api_key=settings.voyage_api_key)

        # Batch embed (Voyage supports batching)
        texts = [p.solution_section for p in proposals]
        # Voyage has a max batch size, process in chunks of 8
        batch_size = 8
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            result = vo.embed(batch, model=settings.voyage_model)
            all_embeddings.extend(result.embeddings)

        for proposal, embedding in zip(proposals, all_embeddings):
            pe = ProposalEmbedding(
                proposal_id=proposal.id,
                embedding=embedding,
                section="solution",
            )
            db.add(pe)

        db.commit()
        print(f"Embedded {len(proposals)} proposals successfully")
    finally:
        db.close()


if __name__ == "__main__":
    embed()
