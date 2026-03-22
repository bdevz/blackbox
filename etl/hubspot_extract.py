#!/usr/bin/env python3
"""HubSpot extraction ETL for Blackbox — pulls deal data from the RFX pipeline."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_BASE = "https://api.hubapi.com"
API_KEY = os.getenv("HUBSPOT_API_KEY", "")
PORTAL_ID = os.getenv("HUBSPOT_PORTAL_ID", "243046792")
PIPELINE_NAME = os.getenv("HUBSPOT_PIPELINE_NAME", "Sales Pipeline")
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "hubspot_extract.json"
MAX_RETRIES = 3

STAGE_MAP = {
    "closedwon": "won",
    "closed won": "won",
    "closedlost": "lost",
    "closed lost": "lost",
    "interview": "interview",
    "intent to award": "won",
    "intenttoaward": "won",
    "submitted": "pending",
    "qualified": "pending",
    "sourced": "pending",
    "rfx cancelled": "lost",
    "rfxcancelled": "lost",
    "not qualified": "lost",
    "notqualified": "lost",
    "terminated": "lost",
}


def headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


async def api_get(client: httpx.AsyncClient, path: str, params: dict = None) -> dict:
    url = f"{HUBSPOT_BASE}{path}"
    for attempt in range(MAX_RETRIES):
        resp = await client.get(url, headers=headers(), params=params or {})
        if resp.status_code == 429:
            wait = 2 ** (attempt + 1)
            click.echo(f"  Rate limited, waiting {wait}s...")
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise click.ClickException("Max retries exceeded on rate limit")


async def api_post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
    url = f"{HUBSPOT_BASE}{path}"
    for attempt in range(MAX_RETRIES):
        resp = await client.post(url, headers=headers(), json=body)
        if resp.status_code == 429:
            wait = 2 ** (attempt + 1)
            click.echo(f"  Rate limited, waiting {wait}s...")
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise click.ClickException("Max retries exceeded on rate limit")


async def get_pipelines(client: httpx.AsyncClient) -> list[dict]:
    data = await api_get(client, "/crm/v3/pipelines/deals")
    return data.get("results", [])


async def find_rfx_pipeline(client: httpx.AsyncClient) -> tuple[str, dict]:
    pipelines = await get_pipelines(client)
    for p in pipelines:
        if p.get("label", "").upper() == PIPELINE_NAME.upper():
            stages = {s["id"]: s.get("label", s["id"]) for s in p.get("stages", [])}
            return p["id"], stages
    labels = [p.get("label", p["id"]) for p in pipelines]
    raise click.ClickException(f"Pipeline '{PIPELINE_NAME}' not found. Available: {labels}")


async def get_deals(client: httpx.AsyncClient, pipeline_id: str) -> list[dict]:
    all_deals = []
    after = None
    properties = [
        "dealname", "amount", "dealstage", "closedate", "createdate",
        "pipeline", "hs_lastmodifieddate", "description",
    ]
    while True:
        body = {
            "filterGroups": [{"filters": [{"propertyName": "pipeline", "operator": "EQ", "value": pipeline_id}]}],
            "properties": properties,
            "limit": 100,
        }
        if after:
            body["after"] = after
        data = await api_post(client, "/crm/v3/objects/deals/search", body)
        results = data.get("results", [])
        all_deals.extend(results)
        paging = data.get("paging", {}).get("next")
        if paging:
            after = paging.get("after")
        else:
            break
        click.echo(f"  Fetched {len(all_deals)} deals so far...")
    return all_deals


async def get_deal_contacts(client: httpx.AsyncClient, deal_id: str) -> list[dict]:
    try:
        data = await api_get(client, f"/crm/v3/objects/deals/{deal_id}/associations/contacts")
        contacts = []
        for assoc in data.get("results", []):
            contact_id = assoc.get("id") or assoc.get("toObjectId")
            if contact_id:
                contact = await api_get(client, f"/crm/v3/objects/contacts/{contact_id}",
                    {"properties": "firstname,lastname,email,company,jobtitle,phone"})
                contacts.append(contact.get("properties", {}))
        return contacts
    except Exception:
        return []


def map_outcome(stage_id: str, stages: dict) -> str:
    stage_label = stages.get(stage_id, stage_id).lower().replace(" ", "")
    for key, outcome in STAGE_MAP.items():
        if key in stage_label:
            return outcome
    return "pending"


async def extract_all():
    if not API_KEY:
        raise click.ClickException("HUBSPOT_API_KEY not set")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"deals": 0, "contacts": 0, "won": 0, "lost": 0, "pending": 0, "errors": 0}

    async with httpx.AsyncClient(timeout=30) as client:
        pipeline_id, stages = await find_rfx_pipeline(client)
        click.echo(f"Found pipeline '{PIPELINE_NAME}' (ID: {pipeline_id})")
        click.echo(f"Stages: {json.dumps(stages, indent=2)}\n")

        deals = await get_deals(client, pipeline_id)
        click.echo(f"\nTotal deals: {len(deals)}\n")

        extracted_deals = []
        for i, deal in enumerate(deals):
            props = deal.get("properties", {})
            deal_id = deal.get("id")
            stage_id = props.get("dealstage", "")
            outcome = map_outcome(stage_id, stages)

            contacts = await get_deal_contacts(client, deal_id)
            stats["contacts"] += len(contacts)

            extracted = {
                "hubspot_id": deal_id,
                "name": props.get("dealname", ""),
                "amount": props.get("amount"),
                "stage": stages.get(stage_id, stage_id),
                "outcome": outcome,
                "close_date": props.get("closedate"),
                "create_date": props.get("createdate"),
                "description": props.get("description", ""),
                "contacts": contacts,
            }
            extracted_deals.append(extracted)
            stats["deals"] += 1
            stats[outcome] = stats.get(outcome, 0) + 1

            if (i + 1) % 20 == 0:
                click.echo(f"  Processed {i + 1}/{len(deals)} deals...")

    result = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": PIPELINE_NAME,
        "pipeline_id": pipeline_id,
        "stages": stages,
        "deals": extracted_deals,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)

    click.echo("\n" + "=" * 50)
    click.echo(f"Extraction complete:")
    click.echo(f"  Deals: {stats['deals']}")
    click.echo(f"  Contacts: {stats['contacts']}")
    click.echo(f"  Won: {stats.get('won', 0)}")
    click.echo(f"  Lost: {stats.get('lost', 0)}")
    click.echo(f"  Pending: {stats.get('pending', 0)}")
    click.echo(f"  Errors: {stats['errors']}")
    click.echo(f"  Output: {OUTPUT_FILE}")
    return result


def load_to_db(data: dict, db_url: str = None):
    from sqlalchemy import create_engine, text

    db_url = db_url or os.getenv("DATABASE_URL", "postgresql://blackbox:blackbox@localhost:5432/blackbox")
    engine = create_engine(db_url)
    count = 0

    with engine.begin() as conn:
        for deal in data.get("deals", []):
            conn.execute(text("""
                INSERT INTO rfps (id, source, external_id, title, estimated_value,
                    metadata, created_at)
                VALUES (gen_random_uuid(), 'hubspot', :ext_id, :title, :value,
                    :metadata::jsonb, NOW())
                ON CONFLICT (external_id) DO UPDATE SET
                    metadata = :metadata::jsonb,
                    estimated_value = :value
            """), {
                "ext_id": f"hs-{deal['hubspot_id']}",
                "title": deal.get("name", ""),
                "value": deal.get("amount"),
                "metadata": json.dumps(deal, default=str),
            })
            count += 1

    click.echo(f"Loaded {count} deals to DB")


@click.group()
def cli():
    """Blackbox HubSpot ETL — extract deal data from RFX pipeline."""
    pass


@cli.command()
def pipelines():
    """List all deal pipelines and their stages."""
    async def _run():
        if not API_KEY:
            raise click.ClickException("HUBSPOT_API_KEY not set")
        async with httpx.AsyncClient(timeout=30) as client:
            pipes = await get_pipelines(client)
            for p in pipes:
                is_rfx = " *** RFX ***" if p.get("label", "").upper() == PIPELINE_NAME.upper() else ""
                click.echo(f"\n{p.get('label', p['id'])}{is_rfx}")
                for s in p.get("stages", []):
                    click.echo(f"  {s.get('label', s['id'])} (order: {s.get('displayOrder', '?')})")
    asyncio.run(_run())


@cli.command()
def deals():
    """List deals in the RFX pipeline."""
    async def _run():
        if not API_KEY:
            raise click.ClickException("HUBSPOT_API_KEY not set")
        async with httpx.AsyncClient(timeout=30) as client:
            pid, stages = await find_rfx_pipeline(client)
            deal_list = await get_deals(client, pid)
            for d in deal_list:
                p = d.get("properties", {})
                stage = stages.get(p.get("dealstage", ""), "?")
                click.echo(f"  {p.get('dealname', '?')} | ${p.get('amount', '?')} | {stage}")
    asyncio.run(_run())


@cli.command()
@click.option("--load-db", is_flag=True, help="Load extracted data into PostgreSQL")
def extract(load_db):
    """Extract all deals from the RFX pipeline."""
    data = asyncio.run(extract_all())
    if load_db:
        load_to_db(data)


if __name__ == "__main__":
    cli()
