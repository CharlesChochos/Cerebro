"""
Migration / refugee flow tracking — monitors displacement patterns,
refugee routes, and humanitarian crisis indicators.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta

VALID_FLOW_TYPES = {"refugee", "idp", "economic", "climate", "conflict"}
VALID_STATUSES = {"active", "seasonal", "resolved", "emerging"}


def record_flow(conn, origin_country: str, flow_type: str = "refugee",
                dest_country: str | None = None,
                transit_countries: list[str] | None = None,
                estimated_count: int | None = None, severity: float = 50,
                route_description: str | None = None,
                push_factors: list[str] | None = None,
                pull_factors: list[str] | None = None) -> str:
    fid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO migration_flows
           (id, origin_country, dest_country, transit_countries, flow_type,
            estimated_count, severity, route_description, push_factors, pull_factors)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fid, origin_country, dest_country,
         json.dumps(transit_countries or []),
         flow_type if flow_type in VALID_FLOW_TYPES else "refugee",
         estimated_count, min(100, max(0, severity)), route_description,
         json.dumps(push_factors or []), json.dumps(pull_factors or [])),
    )
    conn.commit()
    return fid


def get_flow(conn, fid: str) -> dict | None:
    row = conn.execute("SELECT * FROM migration_flows WHERE id = ?", (fid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    for f in ("transit_countries", "push_factors", "pull_factors"):
        d[f] = json.loads(d[f]) if d[f] else []
    return d


def list_flows(conn, origin_country: str | None = None, dest_country: str | None = None,
               flow_type: str | None = None, status: str | None = None,
               limit: int = 50) -> list[dict]:
    conditions, params = [], []
    if origin_country:
        conditions.append("origin_country = ?"); params.append(origin_country)
    if dest_country:
        conditions.append("dest_country = ?"); params.append(dest_country)
    if flow_type and flow_type in VALID_FLOW_TYPES:
        conditions.append("flow_type = ?"); params.append(flow_type)
    if status and status in VALID_STATUSES:
        conditions.append("status = ?"); params.append(status)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM migration_flows{where} ORDER BY severity DESC LIMIT ?",
        params + [limit]).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        for f in ("transit_countries", "push_factors", "pull_factors"):
            d[f] = json.loads(d[f]) if d[f] else []
        results.append(d)
    return results


def update_flow(conn, fid: str, status: str | None = None,
                estimated_count: int | None = None,
                severity: float | None = None) -> bool:
    row = conn.execute("SELECT id FROM migration_flows WHERE id = ?", (fid,)).fetchone()
    if not row:
        return False
    updates, params = [], []
    if status and status in VALID_STATUSES:
        updates.append("status = ?"); params.append(status)
    if estimated_count is not None:
        updates.append("estimated_count = ?"); params.append(estimated_count)
    if severity is not None:
        updates.append("severity = ?"); params.append(min(100, max(0, severity)))
    if not updates:
        return True
    params.append(fid)
    conn.execute(f"UPDATE migration_flows SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    return True


def get_crisis_summary(conn) -> dict:
    """Summary of active migration crises."""
    active = list_flows(conn, status="active", limit=200)
    emerging = list_flows(conn, status="emerging", limit=200)
    all_flows = active + emerging
    by_origin = {}
    total_displaced = 0
    for f in all_flows:
        by_origin[f["origin_country"]] = by_origin.get(f["origin_country"], 0) + 1
        total_displaced += f["estimated_count"] or 0
    return {
        "active_flows": len(active), "emerging_flows": len(emerging),
        "total_estimated_displaced": total_displaced,
        "by_origin_country": by_origin,
        "highest_severity": round(max((f["severity"] for f in all_flows), default=0), 1),
    }
