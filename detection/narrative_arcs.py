"""
Narrative arc tracker — track how storylines evolve through phases over time.

Every geopolitical narrative follows an arc: it emerges from initial events, escalates
as more actors engage, peaks during a crisis moment, and eventually declines. Tracking
which phase a narrative is in helps analysts anticipate what comes next.

Phases:
  emerging   → First signals, low event count, growing mentions
  escalating → Increasing frequency and severity, multiple sources
  peak       → Maximum intensity, highest severity, broadest coverage
  declining  → Decreasing frequency, lower severity, fading coverage
  dormant    → Minimal activity, narrative has subsided (may re-emerge)

The tracker uses rolling windows over event counts, severity, and source diversity
to classify the current phase and detect phase transitions.
"""
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

ARC_PROMPT = """You are a narrative intelligence analyst tracking how a geopolitical
storyline is evolving.

TOPIC: {topic}
REGION: {region}
CURRENT PHASE: {phase}
INTENSITY: {intensity:.2f}

RECENT EVENTS (newest first):
{events_text}

PHASE HISTORY:
{phase_history}

Provide an updated narrative arc assessment:

Respond with a JSON object:
{{
  "phase": "emerging|escalating|peak|declining|dormant",
  "intensity": 0.0 to 1.0,
  "summary": "2-3 sentence summary of the current narrative state",
  "key_developments": ["recent development 1", "development 2"],
  "forecast": "1-2 sentence forecast of where this narrative is heading",
  "sentiment": -1.0 to 1.0 (negative to positive)
}}

Respond ONLY with the JSON object.
"""


def get_topic_events(conn, topic: str, region: str | None = None,
                      country_code: str | None = None,
                      days: int = 30) -> list[dict]:
    """Get events matching a topic, ordered by timestamp."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    conditions = ["timestamp >= ?"]
    params = [cutoff]

    if region:
        conditions.append("region = ?")
        params.append(region)
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = " AND ".join(conditions)

    # Try FTS first
    try:
        events = conn.execute(
            f"""SELECT e.id, e.source, e.title, e.summary, e.category,
                       e.severity, e.country_code, e.timestamp
                FROM events e
                JOIN events_fts fts ON e.id = fts.rowid
                WHERE fts.events_fts MATCH ? AND {where}
                ORDER BY e.timestamp DESC LIMIT 100""",
            [topic] + params,
        ).fetchall()
    except Exception:
        events = conn.execute(
            f"""SELECT id, source, title, summary, category, severity,
                       country_code, timestamp
                FROM events
                WHERE (title LIKE ? OR summary LIKE ?) AND {where}
                ORDER BY timestamp DESC LIMIT 100""",
            [f"%{topic}%", f"%{topic}%"] + params,
        ).fetchall()

    return [dict(e) for e in events]


def compute_arc_metrics(events: list[dict], days: int = 30) -> dict:
    """
    Compute narrative arc metrics from event data.

    Returns intensity, phase classification, and supporting metrics.
    """
    if not events:
        return {
            "phase": "dormant",
            "intensity": 0.0,
            "event_count": 0,
            "avg_severity": 0,
            "source_count": 0,
            "recent_trend": "none",
        }

    now = datetime.now(timezone.utc)

    # Split events into time windows
    week1 = []  # most recent 7 days
    week2 = []  # 8-14 days ago
    older = []  # 15+ days ago

    for e in events:
        try:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            age = (now - ts).days
        except (ValueError, TypeError):
            age = days  # treat as old if timestamp is bad

        if age <= 7:
            week1.append(e)
        elif age <= 14:
            week2.append(e)
        else:
            older.append(e)

    total = len(events)
    avg_severity = sum(e.get("severity", 0) for e in events) / max(total, 1)
    sources = set(e.get("source", "unknown") for e in events)

    # Compute intensity: weighted combination of count, severity, and recency
    # More recent events contribute more to intensity
    recency_weight = len(week1) * 3 + len(week2) * 1.5 + len(older) * 0.5
    max_recency = total * 3  # theoretical max if all events were in week1

    count_factor = min(total / 20, 1.0)  # saturates at 20 events
    severity_factor = avg_severity / 100
    recency_factor = recency_weight / max_recency if max_recency > 0 else 0
    source_factor = min(len(sources) / 5, 1.0)  # saturates at 5 sources

    intensity = (count_factor * 0.3 + severity_factor * 0.3 +
                 recency_factor * 0.25 + source_factor * 0.15)
    intensity = round(min(intensity, 1.0), 3)

    # Determine recent trend
    w1_avg = sum(e.get("severity", 0) for e in week1) / max(len(week1), 1)
    w2_avg = sum(e.get("severity", 0) for e in week2) / max(len(week2), 1)

    if len(week1) == 0:
        trend = "declining"
    elif len(week2) == 0 and len(week1) > 0:
        trend = "emerging"
    elif w1_avg > w2_avg * 1.2 and len(week1) >= len(week2):
        trend = "escalating"
    elif w1_avg < w2_avg * 0.8:
        trend = "declining"
    else:
        trend = "stable"

    # Classify phase
    if total <= 2 or intensity < 0.15:
        if len(week1) > 0:
            phase = "emerging"
        else:
            phase = "dormant"
    elif trend == "escalating" and intensity >= 0.3:
        phase = "escalating"
    elif intensity >= 0.6 and trend in ("stable", "escalating"):
        phase = "peak"
    elif trend == "declining":
        if intensity >= 0.2:
            phase = "declining"
        else:
            phase = "dormant"
    elif trend == "emerging":
        phase = "emerging"
    else:
        phase = "escalating" if intensity >= 0.3 else "emerging"

    return {
        "phase": phase,
        "intensity": intensity,
        "event_count": total,
        "avg_severity": round(avg_severity, 1),
        "source_count": len(sources),
        "recent_trend": trend,
        "week1_count": len(week1),
        "week2_count": len(week2),
        "older_count": len(older),
    }


def track_narrative_arc(conn, topic: str,
                         region: str | None = None,
                         country_code: str | None = None,
                         days: int = 30) -> dict:
    """
    Track the arc of a narrative topic, computing its current phase and intensity.
    """
    events = get_topic_events(conn, topic, region, country_code, days)
    metrics = compute_arc_metrics(events, days)

    # Build key events (highest severity)
    key_events = sorted(events, key=lambda e: e.get("severity", 0), reverse=True)[:5]
    key_event_ids = [e["id"] for e in key_events]

    # Build related entities from events
    related_entities = set()
    for e in events:
        # Entities might be in entities_json or separate
        ej = e.get("entities_json")
        if ej:
            try:
                ents = json.loads(ej) if isinstance(ej, str) else ej
                for ent in ents:
                    if isinstance(ent, dict):
                        related_entities.add(ent.get("name", ""))
                    elif isinstance(ent, str):
                        related_entities.add(ent)
            except (json.JSONDecodeError, TypeError):
                pass
    related_entities.discard("")

    # Check for existing arc to track phase history
    existing = conn.execute(
        """SELECT id, phase_history, arc_phase, start_date, peak_date
           FROM narrative_arcs WHERE topic = ?
           AND (region = ? OR (region IS NULL AND ? IS NULL))
           ORDER BY updated_at DESC LIMIT 1""",
        (topic, region, region),
    ).fetchone()

    phase_history = []
    start_date = None
    peak_date = None
    arc_id = None

    if existing:
        arc_id = existing["id"]
        phase_history = json.loads(existing["phase_history"]) if existing["phase_history"] else []
        start_date = existing["start_date"]
        peak_date = existing["peak_date"]

        # Record phase transition if phase changed
        if existing["arc_phase"] != metrics["phase"]:
            phase_history.append({
                "from": existing["arc_phase"],
                "to": metrics["phase"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "intensity": metrics["intensity"],
            })
    else:
        start_date = events[-1]["timestamp"] if events else datetime.now(timezone.utc).isoformat()

    if metrics["phase"] == "peak" and not peak_date:
        peak_date = datetime.now(timezone.utc).isoformat()

    summary = None
    model_used = None
    sentiment = 0.0

    if CLAUDE_API_KEY and events:
        try:
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
            events_text = "\n".join(
                f"  [{e['id']}] ({e['source']}) sev={e['severity']} — {e['title']}"
                for e in events[:15]
            )
            history_text = json.dumps(phase_history[-5:]) if phase_history else "No prior transitions."
            prompt = ARC_PROMPT.format(
                topic=topic,
                region=region or "Global",
                phase=metrics["phase"],
                intensity=metrics["intensity"],
                events_text=events_text,
                phase_history=history_text,
            )
            message = client.messages.create(
                model=MODEL,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            content = message.content[0].text.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            claude_result = json.loads(content)
            metrics["phase"] = claude_result.get("phase", metrics["phase"])
            metrics["intensity"] = claude_result.get("intensity", metrics["intensity"])
            summary = claude_result.get("summary")
            sentiment = claude_result.get("sentiment", 0.0)
            model_used = MODEL
        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.warning("Claude arc analysis failed: %s", e)

    if not summary:
        summary = (f"Topic '{topic}' is in {metrics['phase']} phase with {metrics['event_count']} events "
                   f"across {metrics['source_count']} sources. Recent trend: {metrics['recent_trend']}.")

    return {
        "arc_id": arc_id,
        "topic": topic,
        "region": region,
        "country_code": country_code,
        "arc_phase": metrics["phase"],
        "intensity": metrics["intensity"],
        "event_count": metrics["event_count"],
        "avg_severity": metrics["avg_severity"],
        "source_count": metrics["source_count"],
        "recent_trend": metrics["recent_trend"],
        "start_date": start_date,
        "peak_date": peak_date,
        "phase_history": phase_history,
        "key_events": key_event_ids,
        "related_entities": list(related_entities)[:20],
        "sentiment": sentiment,
        "summary": summary,
        "model_used": model_used,
    }


def store_narrative_arc(conn, arc: dict) -> str:
    """Store or update a narrative arc."""
    arc_id = arc.get("arc_id")

    if arc_id:
        # Update existing
        conn.execute(
            """UPDATE narrative_arcs SET
                arc_phase = ?, intensity = ?, event_count = ?,
                phase_history = ?, key_events = ?, related_entities = ?,
                sentiment_trend = ?, summary = ?, model_used = ?,
                peak_date = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                arc["arc_phase"], arc["intensity"], arc["event_count"],
                json.dumps(arc["phase_history"]),
                json.dumps(arc["key_events"]),
                json.dumps(arc["related_entities"]),
                json.dumps([{"timestamp": datetime.now(timezone.utc).isoformat(),
                             "sentiment": arc.get("sentiment", 0.0)}]),
                arc.get("summary"),
                arc.get("model_used"),
                arc.get("peak_date"),
                arc_id,
            ),
        )
    else:
        arc_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO narrative_arcs
               (id, topic, region, country_code, arc_phase, intensity,
                start_date, peak_date, event_count, phase_history,
                key_events, sentiment_trend, related_entities, summary, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                arc_id, arc["topic"], arc.get("region"), arc.get("country_code"),
                arc["arc_phase"], arc["intensity"],
                arc.get("start_date"), arc.get("peak_date"),
                arc["event_count"],
                json.dumps(arc["phase_history"]),
                json.dumps(arc["key_events"]),
                json.dumps([{"timestamp": datetime.now(timezone.utc).isoformat(),
                             "sentiment": arc.get("sentiment", 0.0)}]),
                json.dumps(arc["related_entities"]),
                arc.get("summary"),
                arc.get("model_used"),
            ),
        )

    conn.commit()
    return arc_id


def run_arc_tracker(conn, topic: str,
                     region: str | None = None,
                     country_code: str | None = None) -> dict:
    """Full arc tracking pipeline: analyze + store/update."""
    arc = track_narrative_arc(conn, topic, region, country_code)
    arc_id = store_narrative_arc(conn, arc)
    arc["arc_id"] = arc_id
    return arc


def list_narrative_arcs(conn, phase: str | None = None, limit: int = 20) -> list[dict]:
    """List stored narrative arcs."""
    query = "SELECT * FROM narrative_arcs"
    params = []
    if phase:
        query += " WHERE arc_phase = ?"
        params.append(phase)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        for field in ("phase_history", "key_events", "sentiment_trend", "related_entities"):
            d[field] = json.loads(d[field]) if d[field] else []
        results.append(d)
    return results


def get_narrative_arc(conn, arc_id: str) -> dict | None:
    """Get a single narrative arc."""
    row = conn.execute(
        "SELECT * FROM narrative_arcs WHERE id = ?", (arc_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    for field in ("phase_history", "key_events", "sentiment_trend", "related_entities"):
        d[field] = json.loads(d[field]) if d[field] else []
    return d
