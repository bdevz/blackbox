"""HigherGov SLED RFP integration — fetches, filters, and scores opportunities."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from anthropic import AsyncAnthropic

from app.agents.qualification import CONSULTADD_CONTEXT
from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.highergov.com/api-external/opportunity/"

# IT professional services NAICS codes relevant to ConsultAdd
NAICS_CODES = [
    {"code": "541511", "label": "Custom Computer Programming Services"},
    {"code": "541512", "label": "Computer Systems Design Services"},
    {"code": "541513", "label": "Computer Facilities Management Services"},
    {"code": "541519", "label": "Other Computer Related Services"},
    {"code": "518210", "label": "Data Processing, Hosting, and Related Services"},
    {"code": "541611", "label": "Administrative & General Management Consulting"},
]

# Tier 2 thresholds
MIN_HOURS_UNTIL_DUE = 24  # At least 24h — 3 PM IST start means US ET deadlines same-day are too tight
MAX_DAYS_UNTIL_DUE = 15  # Only RFPs due within the next 2 weeks
MAX_ESTIMATED_VALUE = 2_000_000  # $2M ceiling — anything above is likely too big


def passes_tier2_filter(opp: dict, existing_keys: set[str]) -> bool:
    """Deterministic filter — reject obviously irrelevant opportunities."""

    # Duplicate check
    if opp.get("opp_key") in existing_keys:
        return False

    # No description and no AI summary — can't evaluate
    if not (opp.get("description_text") or "").strip() and not opp.get("ai_summary"):
        return False

    # Sole source — can't bid
    if opp.get("sole_source_flag"):
        return False

    # Product, not service
    if opp.get("product_service") == "P":
        return False

    # Due date checks — only want RFPs due within 24h to 15 days
    # Team starts at 3 PM IST (9:30 AM UTC), most US deadlines are ET (UTC-4/5)
    # So a same-day 5 PM ET deadline = only ~3.5h of work time — too tight
    due = opp.get("due_date")
    if due:
        try:
            due_dt = datetime.strptime(due, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_until = (due_dt - now).total_seconds() / 3600
            if hours_until < 0:
                return False  # Already expired
            if hours_until < MIN_HOURS_UNTIL_DUE:
                return False  # Less than 24h — can't prepare a quality proposal
            if (due_dt - now).days > MAX_DAYS_UNTIL_DUE:
                return False  # Too far out — focus on what's urgent
        except ValueError:
            pass  # Unparseable date — don't reject

    # Value too high
    val_low = opp.get("val_est_low")
    if val_low is not None:
        try:
            if float(val_low) > MAX_ESTIMATED_VALUE:
                return False
        except (ValueError, TypeError):
            pass

    return True


def score_relevance_prompt(opp: dict) -> tuple[str, str]:
    """Build Haiku prompt to score opportunity relevance for ConsultAdd."""

    system = f"""You are an RFP relevance scorer for ConsultAdd.

{CONSULTADD_CONTEXT}

Score this government opportunity on three dimensions:
1. service_fit (0-40): Does this match ConsultAdd's IT services? (MSP, cloud, cyber, data analytics, modernization, ERP, staffing, accessibility)
2. size_fit (0-30): Is the estimated value in ConsultAdd's sweet spot ($100K-$500K ideal, $50K-$2M acceptable)?
3. capability_fit (0-30): Does ConsultAdd have the certs, past performance, and team to win this?

Respond with ONLY valid JSON:
{{
  "service_fit": 0-40,
  "size_fit": 0-30,
  "capability_fit": 0-30,
  "total": 0-100,
  "reasoning": "one sentence"
}}

Score generously for IT professional services. Score 0 for construction, janitorial, medical, legal, or non-IT work that slipped through NAICS filters."""

    desc = opp.get("ai_summary") or opp.get("description_text", "")
    naics = opp.get("naics_code", {}).get("naics_code", "unknown")
    agency = opp.get("agency", {})
    val_low = opp.get("val_est_low", "unknown")
    val_high = opp.get("val_est_high", "unknown")

    user = f"""## Opportunity
Title: {opp.get('title', 'Untitled')}
NAICS: {naics}
Agency: {agency.get('agency_name', 'Unknown')} ({agency.get('agency_type', 'Unknown')})
State: {opp.get('pop_state', 'Unknown')}
Estimated Value: ${val_low} - ${val_high}

## Description
{desc[:3000]}"""

    return system, user


class HigherGovClient:
    """Client for the HigherGov external API."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.highergov_api_key

    async def fetch_page(
        self, naics_code: str, captured_date: str, page: int = 1, limit: int = 100
    ) -> tuple[list[dict], int]:
        """Fetch one page of opportunities for a NAICS code and date."""
        params = {
            "api_key": self.api_key,
            "format": "json",
            "captured_date": captured_date,
            "naics_code": naics_code,
            "limit": limit,
            "page_number": page,
        }
        resp = httpx.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        total_pages = data.get("meta", {}).get("pagination", {}).get("pages", 1)
        return results, total_pages

    async def fetch_all_for_date(self, captured_date: str) -> list[dict]:
        """Fetch all IT SLED opportunities captured on a given date."""
        all_opps = []
        for naics_entry in NAICS_CODES:
            code = naics_entry["code"]
            page = 1
            while True:
                try:
                    results, total_pages = await self.fetch_page(code, captured_date, page)
                    all_opps.extend(results)
                    logger.info(f"NAICS {code} page {page}/{total_pages}: {len(results)} opps")
                    if page >= total_pages:
                        break
                    page += 1
                except Exception as e:
                    logger.error(f"Error fetching NAICS {code} page {page}: {e}")
                    break
        return all_opps


async def score_opportunities(opps: list[dict]) -> list[dict]:
    """Run Tier 3 LLM relevance scoring on a batch of opportunities."""
    if not settings.anthropic_api_key:
        logger.warning("No Anthropic API key — skipping Tier 3 scoring")
        return [{"opp": opp, "score": 50, "reasoning": "no API key"} for opp in opps]

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    scored = []

    for opp in opps:
        try:
            system, user = score_relevance_prompt(opp)
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                temperature=0.1,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, count=1)
            raw = re.sub(r"\n?```\s*$", "", raw)
            # Extract first JSON object if there's trailing text
            start = raw.find("{")
            if start != -1:
                depth = 0
                for i in range(start, len(raw)):
                    if raw[i] == "{":
                        depth += 1
                    elif raw[i] == "}":
                        depth -= 1
                        if depth == 0:
                            raw = raw[start:i + 1]
                            break
            result = json.loads(raw)
            scored.append({
                "opp": opp,
                "score": result.get("total", 0),
                "service_fit": result.get("service_fit", 0),
                "size_fit": result.get("size_fit", 0),
                "capability_fit": result.get("capability_fit", 0),
                "reasoning": result.get("reasoning", ""),
            })
        except Exception as e:
            logger.warning(f"Scoring failed for {opp.get('title')}: {e}")
            scored.append({"opp": opp, "score": 0, "reasoning": f"error: {e}"})

    return scored


async def fetch_and_filter(
    captured_date: str = None,
    relevance_threshold: int = 60,
    auto_qualify_threshold: int = 80,
) -> dict:
    """Full pipeline: fetch → Tier 2 filter → Tier 3 score → ingest.

    Returns summary dict with counts.
    """
    from app.models.database import SessionLocal, RFP

    if captured_date is None:
        captured_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    db = SessionLocal()
    try:
        # Get existing external IDs to dedup
        existing_keys = set(
            row[0] for row in db.query(RFP.external_id).filter(RFP.external_id.isnot(None)).all()
        )

        # Tier 1: Fetch from API (filtered by NAICS codes)
        client = HigherGovClient()
        all_opps = await client.fetch_all_for_date(captured_date)
        logger.info(f"Tier 1 (API): {len(all_opps)} opportunities fetched for {captured_date}")

        # Tier 2: Deterministic filter
        tier2_passed = [opp for opp in all_opps if passes_tier2_filter(opp, existing_keys)]
        logger.info(f"Tier 2 (deterministic): {len(tier2_passed)}/{len(all_opps)} passed")

        # Tier 3: LLM relevance scoring
        scored = await score_opportunities(tier2_passed)
        relevant = [s for s in scored if s["score"] >= relevance_threshold]
        logger.info(f"Tier 3 (LLM): {len(relevant)}/{len(tier2_passed)} scored >= {relevance_threshold}")

        # Ingest into DB
        ingested = 0
        auto_qualified = 0
        for item in relevant:
            opp = item["opp"]
            try:
                val_low = float(opp["val_est_low"]) if opp.get("val_est_low") else None
                val_high = float(opp["val_est_high"]) if opp.get("val_est_high") else None
                estimated_value = val_high or val_low

                rfp = RFP(
                    source="highergov",
                    external_id=opp.get("opp_key"),
                    title=opp.get("title", "Untitled"),
                    agency_name=opp.get("agency", {}).get("agency_name"),
                    agency_state=opp.get("pop_state"),
                    category=opp.get("naics_code", {}).get("naics_code"),
                    estimated_value=estimated_value,
                    raw_document_url=opp.get("source_path"),
                    qualification_score=item["score"] / 100.0,
                    meta={
                        "highergov_path": opp.get("path"),
                        "document_path": opp.get("document_path"),
                        "naics_code": opp.get("naics_code", {}).get("naics_code"),
                        "relevance_score": item["score"],
                        "service_fit": item.get("service_fit"),
                        "size_fit": item.get("size_fit"),
                        "capability_fit": item.get("capability_fit"),
                        "reasoning": item.get("reasoning"),
                        "source_id": opp.get("source_id"),
                        "opp_type": opp.get("opp_type", {}).get("description"),
                        "contact_email": (opp.get("primary_contact_email") or {}).get("contact_email"),
                    },
                )

                if opp.get("due_date"):
                    try:
                        rfp.deadline = datetime.strptime(opp["due_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

                # Build extracted brief from API data
                desc = opp.get("ai_summary") or opp.get("description_text", "")
                rfp.extracted_brief = {
                    "title": opp.get("title"),
                    "agency": opp.get("agency", {}).get("agency_name"),
                    "state": opp.get("pop_state"),
                    "category": opp.get("naics_code", {}).get("naics_code"),
                    "deadline": opp.get("due_date"),
                    "estimated_value": estimated_value,
                    "requirements": [],
                    "scope": desc[:2000],
                    "evaluation_criteria": {},
                }
                rfp.ingested_at = datetime.now(timezone.utc)

                db.add(rfp)
                db.flush()
                ingested += 1

                if item["score"] >= auto_qualify_threshold:
                    auto_qualified += 1

            except Exception as e:
                logger.warning(f"Failed to ingest {opp.get('title')}: {e}")
                db.rollback()
                continue

        db.commit()

        summary = {
            "captured_date": captured_date,
            "tier1_fetched": len(all_opps),
            "tier2_passed": len(tier2_passed),
            "tier3_relevant": len(relevant),
            "ingested": ingested,
            "auto_qualify_candidates": auto_qualified,
        }
        logger.info(f"HigherGov sync complete: {summary}")
        return summary

    finally:
        db.close()
