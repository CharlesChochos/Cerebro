"""
Composite risk scoring engine.

Computes 0-100 risk scores per region/country/topic by aggregating:
- Average severity of recent events
- Average confidence (source reliability)
- Corroboration count (how many distinct sources report the same region/topic)
- Event velocity (rate relative to baseline)
- Time decay (older events contribute less)

Risk = weighted combination with normalization.
"""
import json
import logging
import math
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Weights for composite score
WEIGHTS = {
    "severity": 0.35,
    "corroboration": 0.25,
    "velocity": 0.20,
    "confidence": 0.10,
    "recency": 0.10,
}

# Decay half-life in hours
DECAY_HALF_LIFE = 48.0


def compute_decay(hours_old: float, half_life: float = DECAY_HALF_LIFE) -> float:
    """Exponential decay factor (1.0 = fresh, approaches 0)."""
    if hours_old <= 0:
        return 1.0
    return math.pow(0.5, hours_old / half_life)


def classify_trend(current_velocity: float, baseline: float) -> str:
    """Classify trend based on velocity ratio."""
    if baseline <= 0:
        return "stable"
    ratio = current_velocity / baseline
    if ratio >= 3.0:
        return "spike"
    if ratio >= 1.5:
        return "rising"
    if ratio <= 0.5:
        return "falling"
    return "stable"


def compute_risk_for_scope(conn, scope_type: str, scope_value: str, hours: int = 48) -> dict:
    """
    Compute composite risk score for a specific scope.

    Returns dict with score, components, and metadata.
    """
    # Map scope to query column
    if scope_type == "region":
        where_clause = "region = ?"
    elif scope_type == "country":
        where_clause = "country_code = ?"
    elif scope_type == "topic":
        where_clause = "category = ?"
    else:
        return {"score": 0, "error": f"unknown scope_type: {scope_type}"}

    # Fetch recent events for this scope
    rows = conn.execute(
        f"""SELECT severity, confidence, source, timestamp
            FROM events
            WHERE {where_clause}
              AND julianday('now') - julianday(timestamp) <= ?
            ORDER BY timestamp DESC""",
        (scope_value, hours / 24.0),
    ).fetchall()

    if not rows:
        return {
            "score": 0,
            "components": {"severity_avg": 0, "confidence_avg": 0, "corroboration": 0, "velocity": 0, "recency": 0},
            "event_count": 0,
            "source_count": 0,
            "trend": "stable",
        }

    events = [dict(r) for r in rows]
    now = datetime.now(timezone.utc)

    # 1. Decay-weighted severity average
    total_weight = 0.0
    weighted_severity = 0.0
    weighted_confidence = 0.0
    for e in events:
        try:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            hours_old = (now - ts).total_seconds() / 3600
        except (ValueError, TypeError):
            hours_old = 24
        decay = compute_decay(hours_old)
        weighted_severity += e.get("severity", 0) * decay
        weighted_confidence += e.get("confidence", 0.5) * decay
        total_weight += decay

    severity_avg = weighted_severity / total_weight if total_weight > 0 else 0
    confidence_avg = weighted_confidence / total_weight if total_weight > 0 else 0

    # 2. Corroboration — distinct sources
    sources = set(e.get("source", "") for e in events)
    source_count = len(sources)
    # Normalize: 1 source = 20, 2 = 50, 3+ = 75, 5+ = 100
    corroboration = min(100, source_count * 25)

    # 3. Velocity — current rate vs 7-day baseline
    # Current: events in last `hours`; Baseline: events in prior 7 days / 7
    baseline_rows = conn.execute(
        f"""SELECT COUNT(*) as cnt FROM events
            WHERE {where_clause}
              AND julianday('now') - julianday(timestamp) BETWEEN ? AND ?""",
        (scope_value, hours / 24.0, 7.0),
    ).fetchone()
    baseline_daily = (baseline_rows["cnt"] / 7.0) if baseline_rows else 0
    current_daily = len(events) / (hours / 24.0) if hours > 0 else 0

    velocity_ratio = (current_daily / baseline_daily) if baseline_daily > 0 else 1.0
    # Normalize: ratio 1.0 = 30, 2.0 = 60, 3.0+ = 90+
    velocity_score = min(100, velocity_ratio * 30)

    # 4. Recency — how recent is the most recent event
    most_recent = events[0]  # already ordered DESC
    try:
        recent_ts = datetime.fromisoformat(most_recent["timestamp"].replace("Z", "+00:00"))
        recency_hours = (now - recent_ts).total_seconds() / 3600
    except (ValueError, TypeError):
        recency_hours = 24
    recency_score = max(0, 100 - recency_hours * 4)  # 100 if fresh, 0 if >25h old

    # 5. Composite score
    composite = (
        WEIGHTS["severity"] * severity_avg
        + WEIGHTS["corroboration"] * corroboration
        + WEIGHTS["velocity"] * velocity_score
        + WEIGHTS["confidence"] * (confidence_avg * 100)
        + WEIGHTS["recency"] * recency_score
    )
    composite = max(0, min(100, round(composite, 1)))

    trend = classify_trend(current_daily, baseline_daily)

    return {
        "score": composite,
        "components": {
            "severity_avg": round(severity_avg, 1),
            "confidence_avg": round(confidence_avg, 2),
            "corroboration": corroboration,
            "velocity": round(velocity_score, 1),
            "recency": round(recency_score, 1),
        },
        "event_count": len(events),
        "source_count": source_count,
        "trend": trend,
        "velocity_ratio": round(velocity_ratio, 2),
    }


def update_all_risk_scores(conn, hours: int = 48) -> dict:
    """
    Recompute risk scores for all active regions, countries, and topics.
    Returns stats dict.
    """
    updated = 0

    # Get active scopes
    scopes = []

    # Regions
    regions = conn.execute(
        """SELECT DISTINCT region FROM events
           WHERE region IS NOT NULL
             AND julianday('now') - julianday(timestamp) <= ?""",
        (hours / 24.0,),
    ).fetchall()
    scopes.extend([("region", r["region"]) for r in regions])

    # Countries
    countries = conn.execute(
        """SELECT DISTINCT country_code FROM events
           WHERE country_code IS NOT NULL
             AND julianday('now') - julianday(timestamp) <= ?""",
        (hours / 24.0,),
    ).fetchall()
    scopes.extend([("country", c["country_code"]) for c in countries])

    # Topics (categories)
    categories = conn.execute(
        """SELECT DISTINCT category FROM events
           WHERE category IS NOT NULL
             AND julianday('now') - julianday(timestamp) <= ?""",
        (hours / 24.0,),
    ).fetchall()
    scopes.extend([("topic", c["category"]) for c in categories])

    for scope_type, scope_value in scopes:
        result = compute_risk_for_scope(conn, scope_type, scope_value, hours)
        if result.get("score", 0) == 0 and result.get("event_count", 0) == 0:
            continue

        conn.execute(
            """INSERT INTO risk_scores (id, scope_type, scope_value, score, components,
                                         event_count, source_count, trend, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
               ON CONFLICT(scope_type, scope_value) DO UPDATE SET
                 score = excluded.score,
                 components = excluded.components,
                 event_count = excluded.event_count,
                 source_count = excluded.source_count,
                 trend = excluded.trend,
                 updated_at = excluded.updated_at""",
            (
                str(uuid.uuid4()),
                scope_type, scope_value,
                result["score"], json.dumps(result["components"]),
                result["event_count"], result["source_count"],
                result["trend"],
            ),
        )
        updated += 1

    conn.commit()
    stats = {"scopes_updated": updated, "regions": len(regions), "countries": len(countries), "categories": len(categories)}
    logger.info("Risk scores updated: %s", stats)
    return stats
