"""
Indications & Warning (I&W) Framework — monitors for specific observable
indicators that signal impending threats or significant developments.

Each I&W framework defines:
- A threat type and region to monitor
- A set of weighted indicators (diplomatic, military, economic, info, social)
- A threshold percentage of observed indicators needed to trigger a warning
- Status tracking: active → triggered → expired

The system evaluates frameworks by computing what percentage of weighted
indicators have been observed, and compares against the threshold.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VALID_STATUS = {"active", "triggered", "expired", "archived"}
VALID_INDICATOR_STATUS = {"not_observed", "possible", "observed", "confirmed"}
INDICATOR_STATUS_WEIGHT = {"not_observed": 0.0, "possible": 0.3, "observed": 0.7, "confirmed": 1.0}


def create_framework(
    conn,
    name: str,
    threat_type: str | None = None,
    description: str | None = None,
    region: str | None = None,
    country_code: str | None = None,
    threshold_pct: float = 60.0,
) -> str:
    """Create a new I&W framework."""
    fid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO iw_frameworks
           (id, name, description, threat_type, region, country_code, threshold_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (fid, name, description, threat_type, region, country_code, threshold_pct),
    )
    conn.commit()
    return fid


def get_framework(conn, framework_id: str) -> dict | None:
    """Get a framework with its indicators."""
    row = conn.execute("SELECT * FROM iw_frameworks WHERE id = ?", (framework_id,)).fetchone()
    if not row:
        return None
    d = dict(row)

    indicators = conn.execute(
        "SELECT * FROM iw_indicators WHERE framework_id = ? ORDER BY created_at",
        (framework_id,),
    ).fetchall()

    d["indicators"] = []
    for ind in indicators:
        ind_d = dict(ind)
        ind_d["evidence"] = json.loads(ind_d["evidence"]) if ind_d["evidence"] else None
        d["indicators"].append(ind_d)

    return d


def list_frameworks(
    conn,
    status: str | None = None,
    threat_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List I&W frameworks."""
    conditions = []
    params: list = []

    if status and status in VALID_STATUS:
        conditions.append("status = ?")
        params.append(status)
    if threat_type:
        conditions.append("threat_type = ?")
        params.append(threat_type)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM iw_frameworks{where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


def add_indicator(
    conn,
    framework_id: str,
    indicator_text: str,
    category: str | None = None,
    weight: float = 1.0,
) -> str:
    """Add an indicator to a framework."""
    iid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO iw_indicators
           (id, framework_id, indicator_text, category, weight)
           VALUES (?, ?, ?, ?, ?)""",
        (iid, framework_id, indicator_text, category, weight),
    )
    conn.commit()
    return iid


def update_indicator_status(
    conn,
    indicator_id: str,
    status: str,
    evidence: dict | None = None,
) -> bool:
    """Update an indicator's observation status."""
    if status not in VALID_INDICATOR_STATUS:
        return False

    row = conn.execute("SELECT id FROM iw_indicators WHERE id = ?", (indicator_id,)).fetchone()
    if not row:
        return False

    now = datetime.now(timezone.utc).isoformat()
    observed_at = now if status in ("observed", "confirmed") else None

    conn.execute(
        """UPDATE iw_indicators
           SET status = ?, observed_at = ?, evidence = ?, updated_at = ?
           WHERE id = ?""",
        (status, observed_at, json.dumps(evidence) if evidence else None, now, indicator_id),
    )
    conn.commit()
    return True


def evaluate_framework(conn, framework_id: str) -> dict:
    """
    Evaluate an I&W framework — compute the warning level based on observed indicators.

    Returns the weighted observation percentage and whether the threshold is exceeded.
    """
    fw = get_framework(conn, framework_id)
    if not fw:
        return {"error": "Framework not found"}

    indicators = fw["indicators"]
    if not indicators:
        return {
            "framework_id": framework_id,
            "name": fw["name"],
            "warning_level": 0.0,
            "threshold_pct": fw["threshold_pct"],
            "triggered": False,
            "total_indicators": 0,
            "indicators": [],
        }

    total_weight = sum(ind["weight"] for ind in indicators)
    observed_weight = 0.0

    indicator_details = []
    for ind in indicators:
        status_w = INDICATOR_STATUS_WEIGHT.get(ind["status"], 0.0)
        contribution = ind["weight"] * status_w
        observed_weight += contribution

        indicator_details.append({
            "id": ind["id"],
            "indicator_text": ind["indicator_text"],
            "category": ind["category"],
            "weight": ind["weight"],
            "status": ind["status"],
            "observed_at": ind["observed_at"],
            "contribution": round(contribution, 3),
        })

    warning_level = (observed_weight / total_weight * 100) if total_weight > 0 else 0
    triggered = warning_level >= fw["threshold_pct"]

    # Auto-update framework status if triggered
    if triggered and fw["status"] == "active":
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE iw_frameworks SET status = 'triggered', updated_at = ? WHERE id = ?",
            (now, framework_id),
        )
        conn.commit()

    return {
        "framework_id": framework_id,
        "name": fw["name"],
        "threat_type": fw["threat_type"],
        "region": fw["region"],
        "warning_level": round(warning_level, 1),
        "threshold_pct": fw["threshold_pct"],
        "triggered": triggered,
        "total_indicators": len(indicators),
        "observed": sum(1 for i in indicators if i["status"] in ("observed", "confirmed")),
        "possible": sum(1 for i in indicators if i["status"] == "possible"),
        "indicators": indicator_details,
    }
