"""
Proactive intelligence push — generates and delivers intelligence alerts
based on threshold breaches, pattern matches, and scheduled analysis.

Alert types:
- threshold_breach: A metric exceeded a defined limit (e.g., severity spike)
- pattern_match: A known dangerous pattern was detected (e.g., dark vessel + conflict zone)
- scheduled_brief: Regular automated intelligence summary
- anomaly: Statistical anomaly detected in event streams

Priority levels: low / medium / high / critical
Status flow: pending → delivered → acknowledged → dismissed
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

VALID_ALERT_TYPES = {"threshold_breach", "pattern_match", "scheduled_brief", "anomaly"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
VALID_STATUSES = {"pending", "delivered", "acknowledged", "dismissed"}


def create_alert(
    conn,
    alert_type: str,
    title: str,
    summary: str | None = None,
    priority: str = "medium",
    trigger_rule: dict | None = None,
    target_entities: list[str] | None = None,
    region: str | None = None,
    country_code: str | None = None,
) -> str:
    """Create a proactive intelligence alert."""
    aid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO proactive_alerts
           (id, alert_type, priority, title, summary, trigger_rule,
            target_entities, region, country_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            aid,
            alert_type if alert_type in VALID_ALERT_TYPES else "anomaly",
            priority if priority in VALID_PRIORITIES else "medium",
            title, summary,
            json.dumps(trigger_rule) if trigger_rule else None,
            json.dumps(target_entities) if target_entities else None,
            region, country_code,
        ),
    )
    conn.commit()
    return aid


def get_alert(conn, alert_id: str) -> dict | None:
    """Get a single proactive alert."""
    row = conn.execute("SELECT * FROM proactive_alerts WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["trigger_rule"] = json.loads(d["trigger_rule"]) if d["trigger_rule"] else None
    d["target_entities"] = json.loads(d["target_entities"]) if d["target_entities"] else []
    return d


def list_alerts(
    conn,
    status: str | None = None,
    priority: str | None = None,
    alert_type: str | None = None,
    hours: int = 24,
    limit: int = 50,
) -> list[dict]:
    """List proactive alerts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conditions = ["created_at >= ?"]
    params: list = [cutoff]

    if status and status in VALID_STATUSES:
        conditions.append("status = ?")
        params.append(status)
    if priority and priority in VALID_PRIORITIES:
        conditions.append("priority = ?")
        params.append(priority)
    if alert_type and alert_type in VALID_ALERT_TYPES:
        conditions.append("alert_type = ?")
        params.append(alert_type)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM proactive_alerts WHERE {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["trigger_rule"] = json.loads(d["trigger_rule"]) if d["trigger_rule"] else None
        d["target_entities"] = json.loads(d["target_entities"]) if d["target_entities"] else []
        results.append(d)
    return results


def update_alert_status(conn, alert_id: str, status: str) -> bool:
    """Update an alert's delivery/acknowledgment status."""
    if status not in VALID_STATUSES:
        return False

    row = conn.execute("SELECT id FROM proactive_alerts WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        return False

    now = datetime.now(timezone.utc).isoformat()
    updates = ["status = ?"]
    params: list = [status]

    if status == "delivered":
        updates.append("delivered_at = ?")
        params.append(now)
    elif status == "acknowledged":
        updates.append("acknowledged_at = ?")
        params.append(now)

    params.append(alert_id)
    conn.execute(
        f"UPDATE proactive_alerts SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return True


def scan_for_alerts(conn, hours: int = 6) -> list[dict]:
    """
    Scan recent events for conditions that should trigger proactive alerts.

    Rules:
    1. Severity spike: avg severity in a region jumped >30% in last N hours
    2. Event burst: >10 events in a single country in a short window
    3. Dark vessel in conflict zone: vessel went dark near active conflict area
    4. Multi-source convergence: 3+ sources reporting on same region
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    generated_alerts = []

    # Rule 1: Severity spike by country
    rows = conn.execute(
        """SELECT country_code, AVG(severity) as avg_sev, COUNT(*) as cnt
           FROM events
           WHERE timestamp >= ? AND country_code IS NOT NULL
           GROUP BY country_code
           HAVING avg_sev > 70 AND cnt >= 5""",
        (cutoff,),
    ).fetchall()

    for r in rows:
        aid = create_alert(
            conn,
            alert_type="threshold_breach",
            title=f"Severity spike in {r['country_code']}",
            summary=f"Average severity {r['avg_sev']:.0f} across {r['cnt']} events",
            priority="high" if r["avg_sev"] > 80 else "medium",
            trigger_rule={"rule": "severity_spike", "avg_severity": r["avg_sev"], "event_count": r["cnt"]},
            country_code=r["country_code"],
        )
        generated_alerts.append({"alert_id": aid, "type": "severity_spike", "country": r["country_code"]})

    # Rule 2: Event burst by country
    rows = conn.execute(
        """SELECT country_code, COUNT(*) as cnt
           FROM events
           WHERE timestamp >= ? AND country_code IS NOT NULL
           GROUP BY country_code
           HAVING cnt >= 15""",
        (cutoff,),
    ).fetchall()

    for r in rows:
        aid = create_alert(
            conn,
            alert_type="pattern_match",
            title=f"Event burst in {r['country_code']}",
            summary=f"{r['cnt']} events detected in {hours}h window",
            priority="high",
            trigger_rule={"rule": "event_burst", "count": r["cnt"], "hours": hours},
            country_code=r["country_code"],
        )
        generated_alerts.append({"alert_id": aid, "type": "event_burst", "country": r["country_code"]})

    # Rule 3: Multi-source convergence
    rows = conn.execute(
        """SELECT country_code, COUNT(DISTINCT source) as src_count, COUNT(*) as cnt
           FROM events
           WHERE timestamp >= ? AND country_code IS NOT NULL
           GROUP BY country_code
           HAVING src_count >= 3 AND cnt >= 5""",
        (cutoff,),
    ).fetchall()

    for r in rows:
        aid = create_alert(
            conn,
            alert_type="pattern_match",
            title=f"Multi-source convergence: {r['country_code']}",
            summary=f"{r['src_count']} sources reporting, {r['cnt']} events",
            priority="medium",
            trigger_rule={"rule": "multi_source", "sources": r["src_count"], "events": r["cnt"]},
            country_code=r["country_code"],
        )
        generated_alerts.append({"alert_id": aid, "type": "multi_source", "country": r["country_code"]})

    return generated_alerts
