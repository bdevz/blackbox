#!/usr/bin/env python3
"""Coda extraction ETL for Blackbox — pulls RFP data from the RFP Tracker doc."""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx
from dotenv import load_dotenv

load_dotenv()

CODA_BASE = "https://coda.io/apis/v1"
DOC_ID = os.getenv("CODA_DOC_ID", "dSt8mkiTmO7")
API_TOKEN = os.getenv("CODA_API_TOKEN", "")
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "coda_extract.json"
PAGE_LIMIT = 200
MAX_RETRIES = 3


def headers():
    return {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}


async def api_get(client: httpx.AsyncClient, path: str, params: dict = None) -> dict:
    url = f"{CODA_BASE}{path}"
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


async def list_tables(client: httpx.AsyncClient) -> list[dict]:
    data = await api_get(client, f"/docs/{DOC_ID}/tables")
    return data.get("items", [])


async def list_columns(client: httpx.AsyncClient, table_id: str) -> list[dict]:
    data = await api_get(client, f"/docs/{DOC_ID}/tables/{table_id}/columns")
    return data.get("items", [])


async def list_rows(client: httpx.AsyncClient, table_id: str) -> list[dict]:
    all_rows = []
    page_token = None
    while True:
        params = {"limit": PAGE_LIMIT, "useColumnNames": True}
        if page_token:
            params["pageToken"] = page_token
        data = await api_get(client, f"/docs/{DOC_ID}/tables/{table_id}/rows", params)
        items = data.get("items", [])
        all_rows.extend(items)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        click.echo(f"    Fetched {len(all_rows)} rows so far...")
    return all_rows


def classify_table(name: str, columns: list[str]) -> str:
    name_lower = name.lower()
    col_set = {c.lower() for c in columns}
    if any(k in name_lower for k in ["rfp", "rfx", "proposal", "solicitation", "bid"]):
        return "rfp"
    if any(k in name_lower for k in ["rate", "pricing", "cost"]):
        return "rate_card"
    if any(k in name_lower for k in ["cert", "license", "registration", "credential"]):
        return "certification"
    if any(k in name_lower for k in ["template", "boilerplate"]):
        return "boilerplate"
    if any(k in name_lower for k in ["interview"]):
        return "interview"
    if any(k in col_set for k in ["agency", "deadline", "state", "contract value"]):
        return "rfp"
    return "other"


async def extract_all():
    if not API_TOKEN:
        raise click.ClickException("CODA_API_TOKEN not set")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {"extracted_at": datetime.now(timezone.utc).isoformat(), "doc_id": DOC_ID, "tables": []}
    stats = {"tables": 0, "rows": 0, "rfp_rows": 0, "errors": 0}

    async with httpx.AsyncClient(timeout=30) as client:
        tables = await list_tables(client)
        click.echo(f"Found {len(tables)} tables in doc {DOC_ID}\n")

        for table in tables:
            tid = table["id"]
            tname = table.get("name", tid)
            stats["tables"] += 1

            try:
                columns = await list_columns(client, tid)
                col_names = [c.get("name", c["id"]) for c in columns]
                classification = classify_table(tname, col_names)

                click.echo(f"Table: {tname} ({classification})")
                click.echo(f"  Columns: {', '.join(col_names[:8])}{'...' if len(col_names) > 8 else ''}")

                rows = await list_rows(client, tid)
                click.echo(f"  Rows: {len(rows)}")

                row_data = []
                for row in rows:
                    values = row.get("values", {})
                    row_data.append({"id": row.get("id"), "name": row.get("name", ""), "values": values})

                stats["rows"] += len(rows)
                if classification == "rfp":
                    stats["rfp_rows"] += len(rows)

                result["tables"].append({
                    "id": tid,
                    "name": tname,
                    "classification": classification,
                    "columns": col_names,
                    "row_count": len(rows),
                    "rows": row_data,
                })
            except Exception as e:
                click.echo(f"  ERROR: {e}")
                stats["errors"] += 1

            click.echo()

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)

    click.echo("=" * 50)
    click.echo(f"Extraction complete:")
    click.echo(f"  Tables processed: {stats['tables']}")
    click.echo(f"  Total rows: {stats['rows']}")
    click.echo(f"  RFP rows: {stats['rfp_rows']}")
    click.echo(f"  Errors: {stats['errors']}")
    click.echo(f"  Output: {OUTPUT_FILE}")
    return result


def load_to_db(data: dict, db_url: str = None):
    """Load extracted Coda data into PostgreSQL. Call after extract."""
    from sqlalchemy import create_engine, text

    db_url = db_url or os.getenv("DATABASE_URL", "postgresql://blackbox:blackbox@localhost:5432/blackbox")
    engine = create_engine(db_url)

    rfp_count = 0
    knowledge_count = 0

    with engine.begin() as conn:
        for table in data.get("tables", []):
            classification = table.get("classification", "other")

            if classification == "rfp":
                for row in table.get("rows", []):
                    values = row.get("values", {})
                    conn.execute(text("""
                        INSERT INTO rfps (id, source, external_id, title, agency_name, agency_state,
                            metadata, created_at)
                        VALUES (gen_random_uuid(), 'coda', :ext_id, :title, :agency, :state,
                            :metadata::jsonb, NOW())
                        ON CONFLICT (external_id) DO UPDATE SET metadata = :metadata::jsonb
                    """), {
                        "ext_id": row.get("id", ""),
                        "title": values.get("Name", values.get("Title", values.get("RFP Name", row.get("name", "")))),
                        "agency": values.get("Agency", values.get("Agency Name", "")),
                        "state": values.get("State", values.get("Location", "")),
                        "metadata": json.dumps(values, default=str),
                    })
                    rfp_count += 1

            elif classification in ("rate_card", "certification", "boilerplate"):
                for row in table.get("rows", []):
                    values = row.get("values", {})
                    conn.execute(text("""
                        INSERT INTO company_knowledge (id, type, key, value, updated_at)
                        VALUES (gen_random_uuid(), :type, :key, :value::jsonb, NOW())
                        ON CONFLICT (type, key) DO UPDATE SET value = :value::jsonb, updated_at = NOW()
                    """), {
                        "type": classification.replace("_", ""),
                        "key": row.get("name", row.get("id", "")),
                        "value": json.dumps(values, default=str),
                    })
                    knowledge_count += 1

    click.echo(f"Loaded to DB: {rfp_count} RFPs, {knowledge_count} knowledge items")


@click.group()
def cli():
    """Blackbox Coda ETL — extract RFP data from Coda."""
    pass


@cli.command()
def tables():
    """List all tables in the Coda doc."""
    async def _run():
        if not API_TOKEN:
            raise click.ClickException("CODA_API_TOKEN not set")
        async with httpx.AsyncClient(timeout=30) as client:
            tbls = await list_tables(client)
            for t in tbls:
                cols = await list_columns(client, t["id"])
                col_names = [c.get("name", c["id"]) for c in cols]
                classification = classify_table(t.get("name", ""), col_names)
                click.echo(f"  {t.get('name', t['id'])} [{classification}] — {len(col_names)} columns")
    asyncio.run(_run())


@cli.command()
@click.option("--load-db", is_flag=True, help="Load extracted data into PostgreSQL")
def extract(load_db):
    """Extract all data from the Coda doc."""
    data = asyncio.run(extract_all())
    if load_db:
        load_to_db(data)


@cli.command()
@click.option("--db-url", default=None, help="PostgreSQL connection string")
def sync(db_url):
    """Incremental sync — extract and load to DB."""
    data = asyncio.run(extract_all())
    load_to_db(data, db_url)


if __name__ == "__main__":
    cli()
