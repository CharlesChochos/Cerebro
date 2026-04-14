"""
Intelligence brief generation using Claude Opus.

Produces structured intelligence briefings:
- Daily briefs: top events, emerging patterns, watch items
- Weekly summaries: trends, escalations, de-escalations
- Flash briefs: triggered by critical events (severity >= 85)
- Regional briefs: focused on a specific geographic area

Every claim grounded to source events via event_ids.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"  # Sonnet for cost efficiency; upgrade to Opus when budget allows

DAILY_BRIEF_PROMPT = """You are the lead intelligence analyst at a global monitoring center.
Produce a DAILY INTELLIGENCE BRIEF based on the events below.

EVENTS (last {hours} hours):
{events_text}

FUSION SIGNALS (cross-domain patterns detected):
{fusion_text}

ACTIVE ENTITIES:
{entities_text}

FORMAT your brief in Markdown with these sections:

## Executive Summary
One paragraph: the single most important development today and why decision-makers should care.

## Critical Developments
For each critical item (severity >= 70):
- **[EVENT_ID]** Title — 2-sentence analysis with implications
- List the specific event IDs supporting each claim in parentheses

## Emerging Patterns
Cross-domain correlations and trends building over time.
Reference fusion signal IDs where applicable.

## Regional Hotspots
Geographic areas showing elevated activity. Group by region.

## Watch Items
Events that aren't critical yet but could escalate within 24-72 hours.

## Predictions
Make 2-4 specific, testable predictions with:
- prediction: what you expect to happen
- confidence: 0.0-1.0
- timeframe: "24h", "48h", "7d", or "30d"
- reasoning: one sentence explaining why

CRITICAL RULES:
1. Every factual claim MUST reference specific event IDs in parentheses
2. Do NOT invent events or details not in the source data
3. Severity assessments must be justified
4. Distinguish between confirmed facts and analytical judgments

After the brief, provide a JSON block with metadata:
```json
{{
  "event_ids_referenced": [...],
  "entity_ids_referenced": [...],
  "predictions": [
    {{"prediction": "...", "confidence": 0.X, "timeframe": "...", "category": "..."}}
  ]
}}
```
"""

FLASH_BRIEF_PROMPT = """You are a senior intelligence analyst issuing a FLASH BRIEF.

A critical event has been detected:
{event_text}

RELATED EVENTS (same region/category, last 48h):
{related_text}

KNOWN ENTITIES INVOLVED:
{entities_text}

Produce a concise flash brief (under 500 words) covering:
1. **What happened** — facts only, cite event IDs
2. **Immediate implications** — who is affected and how
3. **Escalation risk** — could this get worse? What would trigger escalation?
4. **Recommended watch items** — what to monitor in the next 24h

After the brief, provide a JSON metadata block:
```json
{{
  "event_ids_referenced": [...],
  "entity_ids_referenced": [...],
  "predictions": [
    {{"prediction": "...", "confidence": 0.X, "timeframe": "24h", "category": "..."}}
  ]
}}
```
"""


def gather_events_for_brief(conn, hours: int = 24, limit: int = 80) -> list[dict]:
    """Gather events for brief generation, ordered by severity."""
    rows = conn.execute(
        """SELECT id, source, title, summary, category, severity, confidence,
                  country_code, region, timestamp
           FROM events
           WHERE julianday('now') - julianday(timestamp) <= ?
           ORDER BY severity DESC, timestamp DESC
           LIMIT ?""",
        (hours / 24.0, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def gather_fusion_signals(conn, hours: int = 24) -> list[dict]:
    """Gather recent fusion signals for context."""
    rows = conn.execute(
        """SELECT id, signal_type, title, description, severity, confidence,
                  event_ids, entity_ids, grounding_score
           FROM fusion_signals
           WHERE julianday('now') - julianday(created_at) <= ?
           ORDER BY severity DESC
           LIMIT 20""",
        (hours / 24.0,),
    ).fetchall()
    return [dict(r) for r in rows]


def gather_entities(conn, limit: int = 30) -> list[dict]:
    """Get most active entities."""
    rows = conn.execute(
        """SELECT id, name, entity_type, event_count
           FROM entities
           ORDER BY event_count DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def gather_related_events(conn, event: dict, hours: int = 48) -> list[dict]:
    """Gather events related to a specific event (same region or category)."""
    rows = conn.execute(
        """SELECT id, source, title, summary, category, severity, confidence,
                  country_code, region, timestamp
           FROM events
           WHERE id != ?
             AND julianday('now') - julianday(timestamp) <= ?
             AND (region = ? OR category = ? OR country_code = ?)
           ORDER BY severity DESC
           LIMIT 30""",
        (event["id"], hours / 24.0, event.get("region"), event.get("category"), event.get("country_code")),
    ).fetchall()
    return [dict(r) for r in rows]


def format_events(events: list[dict]) -> str:
    """Format events for prompt injection."""
    lines = []
    for e in events:
        lines.append(
            f"[{e['id']}] ({e['source']}) {e.get('category','?')} sev={e['severity']} "
            f"cc={e.get('country_code','?')} — {e['title']}"
        )
        if e.get("summary"):
            lines.append(f"    {e['summary'][:250]}")
    return "\n".join(lines) if lines else "(no events)"


def format_fusion(signals: list[dict]) -> str:
    """Format fusion signals for prompt injection."""
    lines = []
    for s in signals:
        lines.append(
            f"[{s['id']}] {s['signal_type']} sev={s['severity']} conf={s['confidence']} "
            f"grounding={s.get('grounding_score', '?')} — {s['title']}"
        )
        if s.get("description"):
            lines.append(f"    {s['description'][:200]}")
    return "\n".join(lines) if lines else "(no fusion signals detected)"


def format_entities(entities: list[dict]) -> str:
    """Format entities for prompt injection."""
    return "\n".join(
        f"[{e['id']}] {e['name']} ({e['entity_type']}) — {e['event_count']} events"
        for e in entities
    ) if entities else "(no entities)"


def extract_metadata_block(content: str) -> tuple[str, dict]:
    """
    Extract the JSON metadata block from the end of a brief.
    Returns (brief_text, metadata_dict).
    """
    metadata = {"event_ids_referenced": [], "entity_ids_referenced": [], "predictions": []}

    # Look for ```json ... ``` block at the end
    json_start = content.rfind("```json")
    if json_start == -1:
        return content, metadata

    json_end = content.rfind("```", json_start + 7)
    if json_end == -1:
        return content, metadata

    json_text = content[json_start + 7:json_end].strip()
    brief_text = content[:json_start].strip()

    try:
        parsed = json.loads(json_text)
        if isinstance(parsed, dict):
            metadata = {
                "event_ids_referenced": parsed.get("event_ids_referenced", []),
                "entity_ids_referenced": parsed.get("entity_ids_referenced", []),
                "predictions": parsed.get("predictions", []),
            }
    except json.JSONDecodeError:
        logger.warning("Failed to parse brief metadata JSON block")

    return brief_text, metadata


def compute_grounding_score(referenced_ids: list, valid_ids: set) -> float:
    """Compute fraction of referenced event IDs that exist in source data."""
    if not referenced_ids:
        return 0.0
    valid = sum(1 for eid in referenced_ids if eid in valid_ids)
    return round(valid / len(referenced_ids), 2)


def store_predictions(conn, brief_id: str, predictions: list[dict]):
    """Store testable predictions from a brief."""
    for pred in predictions:
        conn.execute(
            """INSERT INTO predictions (id, brief_id, prediction, confidence, timeframe, category)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                brief_id,
                pred.get("prediction", ""),
                pred.get("confidence", 0.5),
                pred.get("timeframe", "24h"),
                pred.get("category", "unknown"),
            ),
        )


def generate_daily_brief(conn, hours: int = 24) -> dict:
    """
    Generate a daily intelligence brief.

    Returns stats dict with brief_id, grounding_score, token usage.
    """
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping brief generation")
        return {"error": "no_api_key"}

    events = gather_events_for_brief(conn, hours=hours)
    if len(events) < 3:
        logger.info("Not enough events for daily brief (%d)", len(events))
        return {"briefs": 0, "reason": "insufficient_events"}

    fusion_signals = gather_fusion_signals(conn, hours=hours)
    entities = gather_entities(conn)
    valid_event_ids = {e["id"] for e in events}

    prompt = DAILY_BRIEF_PROMPT.format(
        hours=hours,
        events_text=format_events(events),
        fusion_text=format_fusion(fusion_signals),
        entities_text=format_entities(entities),
    )

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()
    except anthropic.APIError as e:
        logger.error("Brief generation API error: %s", e)
        return {"error": str(e)}

    # Parse brief and metadata
    brief_text, metadata = extract_metadata_block(content)

    # Compute grounding score
    grounding = compute_grounding_score(
        metadata.get("event_ids_referenced", []), valid_event_ids
    )

    # Extract executive summary (first section after ## Executive Summary)
    summary = ""
    lines = brief_text.split("\n")
    in_summary = False
    summary_lines = []
    for line in lines:
        if "## Executive Summary" in line:
            in_summary = True
            continue
        if in_summary and line.startswith("## "):
            break
        if in_summary and line.strip():
            summary_lines.append(line.strip())
    summary = " ".join(summary_lines)[:500]

    # Store the brief
    brief_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO briefs
           (id, brief_type, title, content, summary, event_ids, entity_ids,
            grounding_score, model_used, token_count, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            brief_id,
            "daily",
            f"Daily Intelligence Brief — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            brief_text,
            summary,
            json.dumps(metadata.get("event_ids_referenced", [])),
            json.dumps(metadata.get("entity_ids_referenced", [])),
            grounding,
            MODEL,
            message.usage.input_tokens + message.usage.output_tokens,
            json.dumps({
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "events_analyzed": len(events),
                "fusion_signals": len(fusion_signals),
            }),
        ),
    )

    # Store predictions
    store_predictions(conn, brief_id, metadata.get("predictions", []))

    conn.commit()

    stats = {
        "brief_id": brief_id,
        "brief_type": "daily",
        "events_analyzed": len(events),
        "grounding_score": grounding,
        "predictions_stored": len(metadata.get("predictions", [])),
        "model": MODEL,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    logger.info("Daily brief generated: %s", stats)
    return stats


def generate_flash_brief(conn, event_id: str) -> dict:
    """
    Generate a flash brief for a critical event.

    Returns stats dict with brief_id, grounding_score, token usage.
    """
    if not CLAUDE_API_KEY:
        return {"error": "no_api_key"}

    row = conn.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if not row:
        return {"error": "event_not_found"}

    event = dict(row)
    related = gather_related_events(conn, event)
    entities = gather_entities(conn, limit=15)
    valid_event_ids = {event["id"]} | {e["id"] for e in related}

    prompt = FLASH_BRIEF_PROMPT.format(
        event_text=format_events([event]),
        related_text=format_events(related),
        entities_text=format_entities(entities),
    )

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()
    except anthropic.APIError as e:
        logger.error("Flash brief API error: %s", e)
        return {"error": str(e)}

    brief_text, metadata = extract_metadata_block(content)
    grounding = compute_grounding_score(
        metadata.get("event_ids_referenced", []), valid_event_ids
    )

    brief_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO briefs
           (id, brief_type, title, content, summary, event_ids, entity_ids,
            grounding_score, model_used, token_count, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            brief_id,
            "flash",
            f"FLASH: {event['title'][:60]}",
            brief_text,
            brief_text[:500],
            json.dumps(metadata.get("event_ids_referenced", [])),
            json.dumps(metadata.get("entity_ids_referenced", [])),
            grounding,
            MODEL,
            message.usage.input_tokens + message.usage.output_tokens,
            json.dumps({
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "trigger_event": event_id,
            }),
        ),
    )

    store_predictions(conn, brief_id, metadata.get("predictions", []))
    conn.commit()

    return {
        "brief_id": brief_id,
        "brief_type": "flash",
        "trigger_event": event_id,
        "grounding_score": grounding,
        "model": MODEL,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
