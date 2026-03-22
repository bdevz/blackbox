#!/usr/bin/env python3
"""Slack extraction ETL for Blackbox — pulls RFP discussions and award announcements."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
CHANNELS = {
    "interview-team": os.getenv("SLACK_INTERVIEW_CHANNEL", "C088YP1M732"),
    "general": os.getenv("SLACK_GENERAL_CHANNEL", "C07AYH29X4L"),
}
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "slack_extract.json"
RFP_KEYWORDS = {"rfp", "rfx", "proposal", "won", "award", "contract", "bid", "solicitation", "submitted", "deadline"}
RATE_LIMIT_PAUSE = 1.2


def get_client() -> WebClient:
    if not BOT_TOKEN:
        raise click.ClickException("SLACK_BOT_TOKEN not set")
    return WebClient(token=BOT_TOKEN)


def rate_limit_wait():
    time.sleep(RATE_LIMIT_PAUSE)


def resolve_users(client: WebClient, user_ids: set[str]) -> dict[str, str]:
    cache = {}
    for uid in user_ids:
        if uid in cache:
            continue
        try:
            resp = client.users_info(user=uid)
            profile = resp.get("user", {}).get("profile", {})
            cache[uid] = profile.get("display_name") or profile.get("real_name") or uid
            rate_limit_wait()
        except SlackApiError:
            cache[uid] = uid
    return cache


def fetch_channel_history(client: WebClient, channel_id: str, channel_name: str) -> list[dict]:
    all_messages = []
    cursor = None
    page = 0

    while True:
        try:
            kwargs = {"channel": channel_id, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.conversations_history(**kwargs)
            messages = resp.get("messages", [])
            all_messages.extend(messages)
            page += 1
            click.echo(f"  Page {page}: {len(messages)} messages (total: {len(all_messages)})")

            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
            rate_limit_wait()
        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                retry_after = int(e.response.headers.get("Retry-After", 5))
                click.echo(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            raise

    return all_messages


def fetch_thread_replies(client: WebClient, channel_id: str, thread_ts: str) -> list[dict]:
    try:
        resp = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=200)
        rate_limit_wait()
        replies = resp.get("messages", [])
        return replies[1:] if len(replies) > 1 else []
    except SlackApiError:
        return []


def is_rfp_related(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in RFP_KEYWORDS)


def extract_channel(client: WebClient, channel_id: str, channel_name: str, filter_keywords: bool = False) -> dict:
    click.echo(f"\nExtracting #{channel_name} ({channel_id})...")
    messages = fetch_channel_history(client, channel_id, channel_name)
    click.echo(f"  Total messages: {len(messages)}")

    user_ids = set()
    for msg in messages:
        if msg.get("user"):
            user_ids.add(msg["user"])

    click.echo(f"  Resolving {len(user_ids)} users...")
    user_map = resolve_users(client, user_ids)

    threads = []
    threaded_count = 0
    skipped = 0

    for msg in messages:
        text = msg.get("text", "")

        if filter_keywords and not is_rfp_related(text):
            skipped += 1
            continue

        thread_ts = msg.get("thread_ts") or msg.get("ts")
        reply_count = msg.get("reply_count", 0)

        replies = []
        if reply_count > 0 and msg.get("ts") == thread_ts:
            replies = fetch_thread_replies(client, channel_id, thread_ts)
            threaded_count += 1
            for r in replies:
                if r.get("user") and r["user"] not in user_map:
                    user_ids.add(r["user"])

        reactions = []
        for reaction in msg.get("reactions", []):
            reactions.append({"name": reaction["name"], "count": reaction["count"]})

        files = []
        for f in msg.get("files", []):
            files.append({"name": f.get("name", ""), "type": f.get("filetype", ""), "url": f.get("url_private", "")})

        threads.append({
            "ts": msg.get("ts"),
            "user": user_map.get(msg.get("user", ""), msg.get("user", "")),
            "text": text,
            "date": datetime.fromtimestamp(float(msg.get("ts", 0)), tz=timezone.utc).isoformat(),
            "reactions": reactions,
            "files": files,
            "reply_count": reply_count,
            "replies": [{
                "user": user_map.get(r.get("user", ""), r.get("user", "")),
                "text": r.get("text", ""),
                "date": datetime.fromtimestamp(float(r.get("ts", 0)), tz=timezone.utc).isoformat(),
            } for r in replies],
        })

    click.echo(f"  Threads with replies: {threaded_count}")
    if filter_keywords:
        click.echo(f"  Skipped (not RFP-related): {skipped}")
    click.echo(f"  Extracted threads: {len(threads)}")

    return {
        "channel_id": channel_id,
        "channel_name": channel_name,
        "message_count": len(messages),
        "extracted_threads": len(threads),
        "threads": threads,
    }


def extract_all_channels():
    client = get_client()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = {"extracted_at": datetime.now(timezone.utc).isoformat(), "channels": []}

    for name, cid in CHANNELS.items():
        filter_kw = (name == "general")
        channel_data = extract_channel(client, cid, name, filter_keywords=filter_kw)
        result["channels"].append(channel_data)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)

    click.echo("\n" + "=" * 50)
    total = sum(c["extracted_threads"] for c in result["channels"])
    click.echo(f"Extraction complete:")
    for c in result["channels"]:
        click.echo(f"  #{c['channel_name']}: {c['extracted_threads']} threads from {c['message_count']} messages")
    click.echo(f"  Total threads: {total}")
    click.echo(f"  Output: {OUTPUT_FILE}")
    return result


def load_to_db(data: dict, db_url: str = None):
    from sqlalchemy import create_engine, text

    db_url = db_url or os.getenv("DATABASE_URL", "postgresql://blackbox:blackbox@localhost:5432/blackbox")
    engine = create_engine(db_url)
    count = 0

    with engine.begin() as conn:
        for channel in data.get("channels", []):
            for thread in channel.get("threads", []):
                full_text = thread.get("text", "")
                for reply in thread.get("replies", []):
                    full_text += f"\n{reply.get('user', '')}: {reply.get('text', '')}"

                conn.execute(text("""
                    INSERT INTO company_knowledge (id, type, key, value, updated_at)
                    VALUES (gen_random_uuid(), 'slack_thread', :key, :value::jsonb, NOW())
                    ON CONFLICT (type, key) DO UPDATE SET value = :value::jsonb, updated_at = NOW()
                """), {
                    "key": f"{channel['channel_name']}-{thread.get('ts', '')}",
                    "value": json.dumps({
                        "channel": channel["channel_name"],
                        "date": thread.get("date"),
                        "user": thread.get("user"),
                        "text": full_text,
                        "reactions": thread.get("reactions", []),
                        "reply_count": thread.get("reply_count", 0),
                    }, default=str),
                })
                count += 1

    click.echo(f"Loaded {count} Slack threads to DB")


@click.group()
def cli():
    """Blackbox Slack ETL — extract RFP discussions from Slack."""
    pass


@cli.command()
def channels():
    """List accessible Slack channels."""
    client = get_client()
    try:
        resp = client.conversations_list(types="public_channel,private_channel", limit=200)
        for ch in resp.get("channels", []):
            marker = " ***" if ch["id"] in CHANNELS.values() else ""
            click.echo(f"  #{ch.get('name', '?')} ({ch['id']}) — {ch.get('num_members', '?')} members{marker}")
    except SlackApiError as e:
        click.echo(f"Error: {e.response.get('error', str(e))}")


@cli.command()
@click.option("--channel", default=None, help="Extract single channel by ID")
@click.option("--load-db", is_flag=True, help="Load extracted data into PostgreSQL")
def extract(channel, load_db):
    """Extract RFP discussions from configured Slack channels."""
    if channel:
        client = get_client()
        name = next((n for n, cid in CHANNELS.items() if cid == channel), channel)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        data = {"extracted_at": datetime.now(timezone.utc).isoformat(),
                "channels": [extract_channel(client, channel, name)]}
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    else:
        data = extract_all_channels()
    if load_db:
        load_to_db(data)


if __name__ == "__main__":
    cli()
