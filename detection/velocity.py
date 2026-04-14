"""
Event velocity tracking — monitors event rate per scope.

Computes:
- Current rate (events per period) for each region/country/topic
- 7-day rolling baseline
- Velocity ratio (current / baseline)
- Auto-flags spikes at 3x baseline

Used for sparkline visualizations and velocity spike alerts.
"""
import json
import logging
import uuid

logger = logging.getLogger(__name__)

PERIODS = {
    "1h": 1.0 / 24.0,    # fraction of a day
    "6h": 6.0 / 24.0,
    "24h": 1.0,
}


def compute_velocity(conn, scope_type: str, scope_value: str, period: str) -> dict:
    """
    Compute event velocity for a specific scope and period.
    Returns dict with current count, baseline, and ratio.
    """
    period_days = PERIODS.get(period, 1.0)

    # Map scope_type to column
    col_map = {"region": "region", "country": "country_code", "topic": "category"}
    col = col_map.get(scope_type)
    if not col:
        return {"error": f"unknown scope_type: {scope_type}"}

    # Current period count
    current = conn.execute(
        f"""SELECT COUNT(*) as cnt, AVG(severity) as avg_sev
            FROM events
            WHERE {col} = ?
              AND julianday('now') - julianday(timestamp) <= ?""",
        (scope_value, period_days),
    ).fetchone()
    current_count = current["cnt"]
    avg_severity = current["avg_sev"] or 0

    # Baseline: same period over prior 7 days, averaged
    baseline = conn.execute(
        f"""SELECT COUNT(*) as cnt FROM events
            WHERE {col} = ?
              AND julianday('now') - julianday(timestamp) BETWEEN ? AND ?""",
        (scope_value, period_days, 7.0),
    ).fetchone()
    # Normalize: total in 7 days / (7 / period_days_equivalent)
    periods_in_7d = 7.0 / period_days if period_days > 0 else 1
    baseline_rate = baseline["cnt"] / periods_in_7d if periods_in_7d > 0 else 0

    ratio = current_count / baseline_rate if baseline_rate > 0 else 1.0

    return {
        "event_count": current_count,
        "avg_severity": round(avg_severity, 1),
        "baseline_rate": round(baseline_rate, 2),
        "velocity_ratio": round(ratio, 2),
        "is_spike": ratio >= 3.0,
    }


def update_all_velocities(conn) -> dict:
    """Recompute velocity for all active scopes and periods."""
    updated = 0

    # Get active scopes (recent events)
    scopes = []
    for col, scope_type in [("region", "region"), ("country_code", "country"), ("category", "topic")]:
        rows = conn.execute(
            f"""SELECT DISTINCT {col} as val FROM events
                WHERE {col} IS NOT NULL
                  AND julianday('now') - julianday(timestamp) <= 7""",
        ).fetchall()
        scopes.extend([(scope_type, r["val"]) for r in rows])

    for scope_type, scope_value in scopes:
        for period in PERIODS:
            result = compute_velocity(conn, scope_type, scope_value, period)
            if "error" in result:
                continue

            conn.execute(
                """INSERT INTO event_velocity
                   (id, scope_type, scope_value, period, event_count,
                    avg_severity, baseline_rate, velocity_ratio, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                   ON CONFLICT(scope_type, scope_value, period) DO UPDATE SET
                     event_count = excluded.event_count,
                     avg_severity = excluded.avg_severity,
                     baseline_rate = excluded.baseline_rate,
                     velocity_ratio = excluded.velocity_ratio,
                     computed_at = excluded.computed_at""",
                (
                    str(uuid.uuid4()),
                    scope_type, scope_value, period,
                    result["event_count"], result["avg_severity"],
                    result["baseline_rate"], result["velocity_ratio"],
                ),
            )
            updated += 1

    conn.commit()
    spikes = conn.execute(
        "SELECT COUNT(*) as cnt FROM event_velocity WHERE velocity_ratio >= 3.0"
    ).fetchone()

    stats = {"velocities_updated": updated, "spikes_detected": spikes["cnt"]}
    logger.info("Velocity tracking: %s", stats)
    return stats
