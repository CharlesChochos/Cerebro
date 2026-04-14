"""
World state compression — institutional memory for Cerebro.

Each night, compresses the day's events + existing world state into a single
compact document (~3,000 tokens). This gives Claude context about "what's
happening in the world" without feeding it thousands of raw events.

The world state acts as a rolling memory:
- Previous world state + today's events → updated world state
- Keeps track of ongoing situations, active conflicts, economic trends
- Drops items that become stale or resolved
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

COMPRESS_PROMPT = """You are maintaining a compressed world state document for an intelligence monitoring system.

PREVIOUS WORLD STATE:
{previous_state}

NEW EVENTS (last {hours} hours, {event_count} events):
{events_text}

FUSION SIGNALS:
{fusion_text}

Your task: produce an UPDATED world state document that:
1. Incorporates significant new developments from the events above
2. Updates ongoing situations with new information
3. Removes or downgrades items that are stale (>72h with no updates) or resolved
4. Keeps the document under 3,000 tokens
5. Maintains a consistent structure

FORMAT:
## Active Conflicts & Security
- [Region/Situation]: current status, key developments, trend (escalating/stable/de-escalating)

## Economic & Financial
- [Market/Economy]: current state, recent changes, outlook

## Health & Environmental
- [Situation]: status, affected areas, trajectory

## Geopolitical Developments
- [Situation]: parties involved, current dynamics, implications

## Watch List
- Items not yet critical but requiring monitoring

## Key Metrics
- Global event count (24h): {event_count}
- Critical events (sev >= 80): {critical_count}
- Active fusion signals: {fusion_count}
- Top affected regions: {top_regions}

Keep each bullet concise (1-2 sentences max). Prioritize by severity and recency.
Do NOT include any JSON metadata blocks — just the Markdown document.
"""


def get_previous_state(conn) -> str:
    """Get the most recent world state document."""
    row = conn.execute(
        """SELECT content FROM world_state
           ORDER BY date DESC LIMIT 1"""
    ).fetchone()
    if row:
        return row["content"]
    return "(No previous world state — this is the first run.)"


def gather_events(conn, hours: int = 24) -> list[dict]:
    """Gather events for compression."""
    rows = conn.execute(
        """SELECT id, source, title, summary, category, severity,
                  country_code, region, timestamp
           FROM events
           WHERE julianday('now') - julianday(timestamp) <= ?
           ORDER BY severity DESC, timestamp DESC
           LIMIT 150""",
        (hours / 24.0,),
    ).fetchall()
    return [dict(r) for r in rows]


def gather_fusion_signals(conn, hours: int = 24) -> list[dict]:
    """Gather recent fusion signals."""
    rows = conn.execute(
        """SELECT signal_type, title, severity, confidence
           FROM fusion_signals
           WHERE julianday('now') - julianday(created_at) <= ?
           ORDER BY severity DESC
           LIMIT 10""",
        (hours / 24.0,),
    ).fetchall()
    return [dict(r) for r in rows]


def format_events(events: list[dict]) -> str:
    """Format events compactly for the compression prompt."""
    lines = []
    for e in events:
        lines.append(
            f"- ({e['source']}) {e.get('category','?')} sev={e['severity']} "
            f"cc={e.get('country_code','?')}: {e['title']}"
        )
    return "\n".join(lines) if lines else "(no events)"


def format_fusion(signals: list[dict]) -> str:
    """Format fusion signals compactly."""
    return "\n".join(
        f"- {s['signal_type']} sev={s['severity']}: {s['title']}"
        for s in signals
    ) if signals else "(none)"


def compute_top_regions(events: list[dict], n: int = 5) -> str:
    """Get the top regions by event count."""
    region_counts: dict[str, int] = {}
    for e in events:
        region = e.get("region") or e.get("country_code") or "unknown"
        region_counts[region] = region_counts.get(region, 0) + 1
    top = sorted(region_counts.items(), key=lambda x: x[1], reverse=True)[:n]
    return ", ".join(f"{r} ({c})" for r, c in top)


def compress_world_state(conn, hours: int = 24) -> dict:
    """
    Generate or update the compressed world state.

    Returns stats dict.
    """
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping world state compression")
        return {"error": "no_api_key"}

    events = gather_events(conn, hours=hours)
    if not events:
        logger.info("No events for world state compression")
        return {"compressed": False, "reason": "no_events"}

    fusion_signals = gather_fusion_signals(conn, hours=hours)
    previous_state = get_previous_state(conn)
    critical_count = sum(1 for e in events if e.get("severity", 0) >= 80)

    prompt = COMPRESS_PROMPT.format(
        previous_state=previous_state,
        hours=hours,
        event_count=len(events),
        events_text=format_events(events),
        fusion_text=format_fusion(fusion_signals),
        critical_count=critical_count,
        fusion_count=len(fusion_signals),
        top_regions=compute_top_regions(events),
    )

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()
    except anthropic.APIError as e:
        logger.error("World state compression API error: %s", e)
        return {"error": str(e)}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conn.execute(
        """INSERT INTO world_state (id, date, content, token_count, events_summarized, model_used)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            str(uuid.uuid4()),
            today,
            content,
            message.usage.input_tokens + message.usage.output_tokens,
            len(events),
            MODEL,
        ),
    )
    conn.commit()

    stats = {
        "date": today,
        "events_summarized": len(events),
        "fusion_signals": len(fusion_signals),
        "critical_events": critical_count,
        "model": MODEL,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    logger.info("World state compressed: %s", stats)
    return stats
