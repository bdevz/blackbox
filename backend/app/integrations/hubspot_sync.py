"""Sync proposal outcomes from HubSpot deal stages."""

import logging

import httpx

from app.config import settings
from app.models.database import SessionLocal, RFP, Proposal

logger = logging.getLogger(__name__)

STAGE_OUTCOME_MAP = {
    "closedwon": "won",
    "closedlost": "lost",
    "contractsent": "interview",
    "qualifiedtobuy": "pending",
    "presentationscheduled": "interview",
    "decisionmakerboughtin": "interview",
}


def sync_outcomes() -> dict:
    """Fetch HubSpot deals and update proposal outcomes."""
    if not settings.hubspot_api_key:
        logger.warning("HUBSPOT_API_KEY not set, skipping sync")
        return {"synced": 0, "skipped": 0, "errors": 0, "message": "No API key"}

    db = SessionLocal()
    summary = {"synced": 0, "won": 0, "lost": 0, "skipped": 0, "errors": 0}

    try:
        deals = _fetch_deals()

        for deal in deals:
            try:
                deal_id = deal.get("id")
                properties = deal.get("properties", {})
                stage = properties.get("dealstage", "").lower()

                outcome = STAGE_OUTCOME_MAP.get(stage)
                if not outcome:
                    summary["skipped"] += 1
                    continue

                rfp = db.query(RFP).filter(RFP.external_id == str(deal_id)).first()
                if not rfp:
                    summary["skipped"] += 1
                    continue

                proposal = (
                    db.query(Proposal)
                    .filter(Proposal.rfp_id == rfp.id)
                    .order_by(Proposal.created_at.desc())
                    .first()
                )
                if not proposal:
                    summary["skipped"] += 1
                    continue

                if proposal.outcome == outcome:
                    summary["skipped"] += 1
                    continue

                proposal.outcome = outcome
                db.commit()

                summary["synced"] += 1
                if outcome == "won":
                    summary["won"] += 1
                elif outcome == "lost":
                    summary["lost"] += 1

            except Exception as e:
                logger.error(f"Error processing deal {deal.get('id')}: {e}")
                summary["errors"] += 1
                db.rollback()

        return summary

    finally:
        db.close()


def _fetch_deals() -> list[dict]:
    """Fetch deals from HubSpot CRM API."""
    url = "https://api.hubapi.com/crm/v3/objects/deals"
    headers = {"Authorization": f"Bearer {settings.hubspot_api_key}"}
    params = {
        "limit": 100,
        "properties": "dealstage,dealname,amount,closedate,pipeline",
    }

    all_deals = []
    after = None

    while True:
        if after:
            params["after"] = after

        resp = httpx.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        all_deals.extend(data.get("results", []))

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")
        if not after:
            break

    return all_deals
