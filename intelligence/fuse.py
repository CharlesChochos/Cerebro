"""
Cross-domain intelligence fusion using Claude Sonnet.

Connects events across sources to detect higher-order patterns:
- Vessel dark + conflict zone + commodity spike = sanctions evasion
- Military buildup + diplomatic breakdown + troop movement = escalation
- Currency crash + bank run + sovereign debt spike = economic crisis

Every fusion signal must map back to specific source events (grounding).
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

FUSION_PROMPT = """You are a senior intelligence analyst performing cross-domain fusion.

Given the following recent events from multiple sources, identify any cross-domain correlations
or patterns that suggest a larger intelligence signal. Focus on:

1. **Sanctions evasion**: vessel dark patterns + conflict zones + commodity movements
2. **Military escalation**: troop movements + diplomatic failures + arms procurement
3. **Economic crisis**: currency movements + sovereign debt + trade disruptions
4. **Health emergencies**: disease outbreaks + travel patterns + supply chain impacts
5. **Geopolitical shifts**: alliance changes + territorial disputes + resource competition

EVENTS:
{events_text}

ENTITIES IN PLAY:
{entities_text}

For each fusion signal you detect, provide:
- signal_type: one of [sanctions_evasion, military_escalation, economic_crisis, health_emergency, geopolitical_shift, supply_chain_disruption]
- title: concise signal name (under 80 chars)
- description: 2-3 sentence explanation of the correlation and why it matters
- severity: 0-100
- confidence: 0.0-1.0
- event_ids: array of the specific event IDs that support this signal
- entity_ids: array of entity IDs involved (if any)

CRITICAL: Only report signals where you have 2+ events from different sources corroborating.
Every claim MUST reference specific event_ids. Do NOT fabricate connections.

Respond ONLY with a JSON array of signal objects. If no significant signals found, return [].
"""


def gather_recent_events(conn, hours: int = 24, limit: int = 100) -> list[dict]:
    """Gather recent events across all sources for fusion analysis."""
    rows = conn.execute(
        """SELECT id, source, title, summary, category, severity, confidence,
                  country_code, region, timestamp
           FROM events
           WHERE julianday('now') - julianday(timestamp) <= ?
           AND severity >= 30
           ORDER BY severity DESC, timestamp DESC
           LIMIT ?""",
        (hours / 24.0, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def gather_active_entities(conn, limit: int = 30) -> list[dict]:
    """Get most active entities for context."""
    rows = conn.execute(
        """SELECT id, name, entity_type, event_count
           FROM entities
           ORDER BY event_count DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def format_events_for_prompt(events: list[dict]) -> str:
    """Format events into text for the fusion prompt."""
    lines = []
    for e in events:
        lines.append(
            f"[{e['id']}] ({e['source']}) {e.get('category','?')} sev={e['severity']} "
            f"cc={e.get('country_code','?')} — {e['title']}"
        )
        if e.get("summary"):
            lines.append(f"    Summary: {e['summary'][:200]}")
    return "\n".join(lines)


def format_entities_for_prompt(entities: list[dict]) -> str:
    """Format entities into text for the fusion prompt."""
    return "\n".join(
        f"[{e['id']}] {e['name']} ({e['entity_type']}) — {e['event_count']} events"
        for e in entities
    )


def compute_grounding_score(signal: dict, valid_event_ids: set) -> float:
    """Compute what fraction of referenced event IDs actually exist in DB."""
    ref_ids = signal.get("event_ids", [])
    if not ref_ids:
        return 0.0
    valid = sum(1 for eid in ref_ids if eid in valid_event_ids)
    return round(valid / len(ref_ids), 2)


def run_fusion(conn, hours: int = 24) -> dict:
    """
    Run cross-domain fusion analysis on recent events.

    Returns stats dict with signals found and grounding scores.
    """
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping fusion")
        return {"error": "no_api_key"}

    events = gather_recent_events(conn, hours=hours)
    if len(events) < 5:
        logger.info("Not enough events for fusion (%d)", len(events))
        return {"signals": 0, "reason": "insufficient_events"}

    entities = gather_active_entities(conn)
    valid_event_ids = {e["id"] for e in events}

    prompt = FUSION_PROMPT.format(
        events_text=format_events_for_prompt(events),
        entities_text=format_entities_for_prompt(entities),
    )

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()
        signals = json.loads(content)

        if not isinstance(signals, list):
            signals = []

    except json.JSONDecodeError as e:
        logger.error("Fusion JSON parse error: %s", e)
        return {"error": "json_parse", "signals": 0}
    except anthropic.APIError as e:
        logger.error("Fusion API error: %s", e)
        return {"error": str(e), "signals": 0}

    stored = 0
    for sig in signals:
        grounding = compute_grounding_score(sig, valid_event_ids)

        # Only store signals with reasonable grounding
        if grounding < 0.3:
            logger.debug("Skipping poorly grounded signal: %s (%.0f%%)", sig.get("title"), grounding * 100)
            continue

        conn.execute(
            """INSERT INTO fusion_signals
               (id, signal_type, title, description, severity, confidence,
                event_ids, entity_ids, grounding_score, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                sig.get("signal_type", "unknown"),
                sig.get("title", "Untitled Signal"),
                sig.get("description", ""),
                sig.get("severity", 50),
                sig.get("confidence", 0.5),
                json.dumps(sig.get("event_ids", [])),
                json.dumps(sig.get("entity_ids", [])),
                grounding,
                MODEL,
            ),
        )
        stored += 1

    conn.commit()

    stats = {
        "events_analyzed": len(events),
        "entities_in_context": len(entities),
        "signals_detected": len(signals),
        "signals_stored": stored,
        "model": MODEL,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    logger.info("Fusion analysis: %s", stats)
    return stats
