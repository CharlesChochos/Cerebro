"""
Historical replay / time machine — view the intelligence landscape as it
existed at any past point in time.

Features:
- Create snapshots of system state at a point in time
- Query events as they existed up to a specific timestamp
- Timeline navigation: list snapshots for date range browsing
- Replay summary: category/region breakdown at a given time
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def create_snapshot(
    conn,
    snapshot_time: str | None = None,
    snapshot_type: str = "auto",
    label: str | None = None,
) -> dict:
    """
    Create a snapshot of the system state at a given time.
    If no time provided, snapshots the current moment.
    """
    ts = snapshot_time or datetime.now(timezone.utc).isoformat()
    sid = str(uuid.uuid4())

    # Count events up to this time
    event_count = conn.execute(
        "SELECT COUNT(*) as c FROM events WHERE timestamp <= ?", (ts,)
    ).fetchone()["c"]

    entity_count = conn.execute(
        "SELECT COUNT(*) as c FROM entities WHERE first_seen <= ?", (ts,)
    ).fetchone()["c"]

    # Category breakdown
    by_category = {}
    rows = conn.execute(
        "SELECT category, COUNT(*) as c FROM events WHERE timestamp <= ? AND category IS NOT NULL GROUP BY category",
        (ts,),
    ).fetchall()
    for r in rows:
        by_category[r["category"]] = r["c"]

    # Region breakdown
    by_region = {}
    rows = conn.execute(
        "SELECT region, COUNT(*) as c FROM events WHERE timestamp <= ? AND region IS NOT NULL GROUP BY region",
        (ts,),
    ).fetchall()
    for r in rows:
        by_region[r["region"]] = r["c"]

    # Severity distribution
    severity_avg = conn.execute(
        "SELECT AVG(severity) as avg_s FROM events WHERE timestamp <= ?", (ts,)
    ).fetchone()["avg_s"]

    summary_stats = {
        "by_category": by_category,
        "by_region": by_region,
        "avg_severity": round(severity_avg, 1) if severity_avg else 0,
    }

    conn.execute(
        """INSERT INTO replay_snapshots
           (id, snapshot_time, snapshot_type, label, event_count, entity_count, summary_stats)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (sid, ts, snapshot_type, label, event_count, entity_count, json.dumps(summary_stats)),
    )
    conn.commit()

    return {
        "snapshot_id": sid,
        "snapshot_time": ts,
        "event_count": event_count,
        "entity_count": entity_count,
        "summary_stats": summary_stats,
    }


def get_snapshot(conn, snapshot_id: str) -> dict | None:
    """Get a specific snapshot."""
    row = conn.execute("SELECT * FROM replay_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["summary_stats"] = json.loads(d["summary_stats"]) if d["summary_stats"] else {}
    return d


def list_snapshots(
    conn,
    start_date: str | None = None,
    end_date: str | None = None,
    snapshot_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List snapshots within a date range."""
    conditions = []
    params: list = []

    if start_date:
        conditions.append("snapshot_time >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("snapshot_time <= ?")
        params.append(end_date)
    if snapshot_type:
        conditions.append("snapshot_type = ?")
        params.append(snapshot_type)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM replay_snapshots{where} ORDER BY snapshot_time DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["summary_stats"] = json.loads(d["summary_stats"]) if d["summary_stats"] else {}
        results.append(d)
    return results


def replay_events(
    conn,
    at_time: str,
    category: str | None = None,
    region: str | None = None,
    country_code: str | None = None,
    limit: int = 100,
) -> dict:
    """
    Replay events as they existed at a specific point in time.
    Returns events that had occurred by `at_time`.
    """
    conditions = ["timestamp <= ?"]
    params: list = [at_time]

    if category:
        conditions.append("category = ?")
        params.append(category)
    if region:
        conditions.append("region = ?")
        params.append(region)
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = " AND ".join(conditions)

    # Get the events
    rows = conn.execute(
        f"""SELECT id, title, category, severity, source, country_code, region,
               latitude, longitude, timestamp
           FROM events WHERE {where}
           ORDER BY timestamp DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    events = [dict(r) for r in rows]

    # Summary at that point in time
    total = conn.execute(
        f"SELECT COUNT(*) as c FROM events WHERE {where}", params
    ).fetchone()["c"]

    avg_sev = conn.execute(
        f"SELECT AVG(severity) as a FROM events WHERE {where}", params
    ).fetchone()["a"]

    return {
        "replay_time": at_time,
        "total_events": total,
        "avg_severity": round(avg_sev, 1) if avg_sev else 0,
        "returned": len(events),
        "events": events,
    }


def get_timeline(conn, days: int = 30, interval_hours: int = 24) -> list[dict]:
    """
    Generate a timeline of event counts at regular intervals over a period.
    Useful for time-series visualization of how the situation evolved.
    """
    now = datetime.now(timezone.utc)
    timeline = []

    steps = (days * 24) // interval_hours
    for i in range(steps, -1, -1):
        ts = (now - timedelta(hours=i * interval_hours)).isoformat()
        count = conn.execute(
            "SELECT COUNT(*) as c FROM events WHERE timestamp <= ?", (ts,)
        ).fetchone()["c"]

        timeline.append({
            "time": ts,
            "cumulative_events": count,
        })

    return timeline
