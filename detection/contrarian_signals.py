"""
Contrarian signal detector — find events and patterns that contradict dominant trends.

In intelligence analysis, the most valuable signals are often the ones that go *against*
the prevailing narrative. A single de-escalation event during a military buildup, or an
economic recovery signal amid a crisis, can be a leading indicator that the consensus
view is wrong.

This module detects four types of contrarian signals:
1. **Trend reversal**: Severity trajectory flips direction
2. **Outlier events**: Individual events that contradict the category's trend
3. **Counter-narrative**: Events whose content diverges from the dominant framing
4. **Anomaly**: Unusual category/severity combinations for a region
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

CONTRARIAN_PROMPT = """You are a senior intelligence analyst. Your job is to evaluate
whether a potential contrarian signal is genuinely significant or just noise.

DOMINANT TREND:
{dominant_trend}

CONTRARIAN SIGNAL:
{contrarian_evidence}

CONTEXT:
Category: {category}
Region: {region}
Recent events (last 7 days): {recent_count}
Average severity: {avg_severity:.0f}/100

Assess the significance of this contrarian signal:

Respond with a JSON object:
{{
  "is_significant": true/false,
  "strength": 0.0 to 1.0,
  "analysis": "1-2 sentence assessment of why this matters or doesn't",
  "implications": ["implication 1", "implication 2"],
  "recommended_action": "what analysts should do about this signal"
}}

Respond ONLY with the JSON object.
"""


def get_severity_trend(conn, category: str, country_code: str | None = None,
                        region: str | None = None, days: int = 30) -> dict:
    """
    Compute the severity trend for a category over a time period.

    Returns: average severity in first half vs. second half, plus direction.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    midpoint = (datetime.now(timezone.utc) - timedelta(days=days // 2)).isoformat()

    conditions = ["category = ?", "timestamp >= ?"]
    params = [category, cutoff]

    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)
    if region:
        conditions.append("region = ?")
        params.append(region)

    where = " AND ".join(conditions)

    # First half
    first_half = conn.execute(
        f"SELECT AVG(severity) as avg_sev, COUNT(*) as cnt FROM events WHERE {where} AND timestamp < ?",
        params + [midpoint],
    ).fetchone()

    # Second half
    second_half = conn.execute(
        f"SELECT AVG(severity) as avg_sev, COUNT(*) as cnt FROM events WHERE {where} AND timestamp >= ?",
        params + [midpoint],
    ).fetchone()

    first_avg = first_half["avg_sev"] or 0
    second_avg = second_half["avg_sev"] or 0
    first_count = first_half["cnt"] or 0
    second_count = second_half["cnt"] or 0

    if first_avg == 0 and second_avg == 0:
        direction = "flat"
    elif second_avg > first_avg * 1.15:
        direction = "escalating"
    elif second_avg < first_avg * 0.85:
        direction = "de-escalating"
    else:
        direction = "stable"

    return {
        "category": category,
        "first_half_avg": round(first_avg, 1),
        "second_half_avg": round(second_avg, 1),
        "first_half_count": first_count,
        "second_half_count": second_count,
        "direction": direction,
        "total_events": first_count + second_count,
    }


def detect_trend_reversals(conn, country_code: str | None = None,
                            region: str | None = None) -> list[dict]:
    """
    Detect categories where the short-term trend (7d) contradicts the
    medium-term trend (30d).
    """
    categories = ["military", "political", "economic", "health", "environmental"]
    signals = []

    for cat in categories:
        medium = get_severity_trend(conn, cat, country_code, region, days=30)
        short = get_severity_trend(conn, cat, country_code, region, days=7)

        # Contrarian: medium-term escalating but short-term de-escalating (or vice versa)
        is_reversal = (
            (medium["direction"] == "escalating" and short["direction"] == "de-escalating") or
            (medium["direction"] == "de-escalating" and short["direction"] == "escalating")
        )

        if is_reversal and medium["total_events"] >= 3:
            strength = abs(short["second_half_avg"] - medium["second_half_avg"]) / max(medium["second_half_avg"], 1)
            signals.append({
                "signal_type": "trend_reversal",
                "category": cat,
                "region": region,
                "country_code": country_code,
                "dominant_trend": f"{cat} has been {medium['direction']} over 30 days "
                                  f"(avg severity {medium['first_half_avg']:.0f}→{medium['second_half_avg']:.0f})",
                "contrarian_evidence": f"But the last 7 days show {short['direction']} "
                                       f"(avg severity {short['first_half_avg']:.0f}→{short['second_half_avg']:.0f})",
                "strength": round(min(strength, 1.0), 3),
                "event_ids": [],
            })

    return signals


def detect_severity_outliers(conn, country_code: str | None = None,
                              region: str | None = None, days: int = 7) -> list[dict]:
    """
    Find individual events whose severity significantly diverges from their
    category's recent average.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cutoff_30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    conditions_base = []
    params_base = []
    if country_code:
        conditions_base.append("country_code = ?")
        params_base.append(country_code)
    if region:
        conditions_base.append("region = ?")
        params_base.append(region)

    extra_where = (" AND " + " AND ".join(conditions_base)) if conditions_base else ""

    # Get category averages over 30 days
    avgs = conn.execute(
        f"""SELECT category, AVG(severity) as avg_sev, COUNT(*) as cnt
            FROM events WHERE timestamp >= ? {extra_where}
            AND category IS NOT NULL
            GROUP BY category HAVING cnt >= 5""",
        [cutoff_30] + params_base,
    ).fetchall()

    cat_avg = {r["category"]: r["avg_sev"] for r in avgs}
    signals = []

    # Find recent events that deviate strongly
    recent = conn.execute(
        f"""SELECT id, title, category, severity, source, timestamp
            FROM events WHERE timestamp >= ? {extra_where}
            AND category IS NOT NULL
            ORDER BY timestamp DESC LIMIT 100""",
        [cutoff] + params_base,
    ).fetchall()

    for evt in recent:
        cat = evt["category"]
        if cat not in cat_avg:
            continue
        avg = cat_avg[cat]
        if avg == 0:
            continue

        deviation = abs(evt["severity"] - avg) / avg

        # Contrarian if event is significantly lower severity during an escalation,
        # or higher during de-escalation
        if deviation >= 0.5:
            direction = "lower" if evt["severity"] < avg else "higher"
            signals.append({
                "signal_type": "outlier",
                "category": cat,
                "region": region,
                "country_code": country_code,
                "dominant_trend": f"{cat} average severity is {avg:.0f}/100 over 30 days",
                "contrarian_evidence": f"Event [{evt['id']}] has severity {evt['severity']}/100 "
                                       f"({direction} than average): {evt['title']}",
                "strength": round(min(deviation, 1.0), 3),
                "event_ids": [evt["id"]],
            })

    # Return only the strongest outliers
    signals.sort(key=lambda s: s["strength"], reverse=True)
    return signals[:10]


def detect_category_anomalies(conn, country_code: str | None = None,
                               region: str | None = None, days: int = 7) -> list[dict]:
    """
    Detect when a category has an unusual event count relative to its baseline.
    E.g., suddenly many health events in a region that usually has military events.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cutoff_30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    conditions_base = []
    params_base = []
    if country_code:
        conditions_base.append("country_code = ?")
        params_base.append(country_code)
    if region:
        conditions_base.append("region = ?")
        params_base.append(region)

    extra_where = (" AND " + " AND ".join(conditions_base)) if conditions_base else ""

    # Baseline: daily average per category over 30 days
    baseline = conn.execute(
        f"""SELECT category, COUNT(*) * 1.0 / 30 as daily_avg
            FROM events WHERE timestamp >= ? {extra_where}
            AND category IS NOT NULL
            GROUP BY category""",
        [cutoff_30] + params_base,
    ).fetchall()
    baseline_map = {r["category"]: r["daily_avg"] for r in baseline}

    # Recent: daily average per category over last N days
    recent = conn.execute(
        f"""SELECT category, COUNT(*) * 1.0 / ? as daily_avg
            FROM events WHERE timestamp >= ? {extra_where}
            AND category IS NOT NULL
            GROUP BY category""",
        [days, cutoff] + params_base,
    ).fetchall()

    signals = []
    for r in recent:
        cat = r["category"]
        recent_avg = r["daily_avg"]
        base_avg = baseline_map.get(cat, 0)

        if base_avg == 0:
            continue

        ratio = recent_avg / base_avg
        if ratio >= 2.0 or ratio <= 0.3:
            direction = "surge" if ratio >= 2.0 else "drop"
            signals.append({
                "signal_type": "anomaly",
                "category": cat,
                "region": region,
                "country_code": country_code,
                "dominant_trend": f"{cat} baseline is {base_avg:.1f} events/day over 30 days",
                "contrarian_evidence": f"Recent {days} days show {recent_avg:.1f} events/day "
                                       f"({direction}: {ratio:.1f}x baseline)",
                "strength": round(min(abs(ratio - 1.0) / 2.0, 1.0), 3),
                "event_ids": [],
            })

    return signals


def scan_contrarian_signals(conn, country_code: str | None = None,
                             region: str | None = None) -> list[dict]:
    """
    Run all contrarian signal detectors and return combined results.
    """
    signals = []
    signals.extend(detect_trend_reversals(conn, country_code, region))
    signals.extend(detect_severity_outliers(conn, country_code, region))
    signals.extend(detect_category_anomalies(conn, country_code, region))

    # Sort by strength
    signals.sort(key=lambda s: s["strength"], reverse=True)
    return signals


def store_contrarian_signal(conn, signal: dict) -> str:
    """Store a contrarian signal in the database."""
    sid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO contrarian_signals
           (id, signal_type, category, region, country_code,
            description, dominant_trend, contrarian_evidence,
            strength, event_ids, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sid, signal["signal_type"], signal.get("category"),
            signal.get("region"), signal.get("country_code"),
            f"{signal['signal_type']}: {signal.get('category', 'unknown')}",
            signal["dominant_trend"], signal["contrarian_evidence"],
            signal["strength"],
            json.dumps(signal.get("event_ids", [])),
            signal.get("model_used"),
        ),
    )
    conn.commit()
    return sid


def run_contrarian_scan(conn, country_code: str | None = None,
                         region: str | None = None) -> dict:
    """Full contrarian scan: detect + store significant signals."""
    signals = scan_contrarian_signals(conn, country_code, region)

    # Store signals with strength >= 0.3
    stored_ids = []
    for s in signals:
        if s["strength"] >= 0.3:
            sid = store_contrarian_signal(conn, s)
            stored_ids.append(sid)

    by_type = defaultdict(int)
    for s in signals:
        by_type[s["signal_type"]] += 1

    return {
        "total_signals": len(signals),
        "stored": len(stored_ids),
        "by_type": dict(by_type),
        "signals": signals,
        "country_code": country_code,
        "region": region,
    }


def list_contrarian_signals(conn, signal_type: str | None = None,
                              limit: int = 20) -> list[dict]:
    """List stored contrarian signals."""
    query = "SELECT * FROM contrarian_signals"
    params = []
    if signal_type:
        query += " WHERE signal_type = ?"
        params.append(signal_type)
    query += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["event_ids"] = json.loads(d["event_ids"]) if d["event_ids"] else []
        results.append(d)
    return results


def get_contrarian_signal(conn, signal_id: str) -> dict | None:
    """Get a single contrarian signal."""
    row = conn.execute(
        "SELECT * FROM contrarian_signals WHERE id = ?", (signal_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["event_ids"] = json.loads(d["event_ids"]) if d["event_ids"] else []
    return d
