"""
Election monitoring — tracks elections worldwide, assesses risk of
irregularities, violence, or disputed outcomes.
"""
import json
import uuid
from datetime import datetime, timezone

VALID_TYPES = {"presidential", "parliamentary", "referendum", "local"}
VALID_STATUSES = {"upcoming", "active", "completed", "disputed"}
VALID_RISK = {"normal", "elevated", "high", "critical"}


def create_election(conn, country_code: str, election_type: str,
                    election_date: str | None = None, candidates: list[str] | None = None,
                    risk_level: str = "normal", risk_factors: list[str] | None = None,
                    region: str | None = None, analyst: str | None = None) -> str:
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO election_monitors
           (id, country_code, election_type, election_date, candidates,
            risk_level, risk_factors, region, analyst)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, country_code,
         election_type if election_type in VALID_TYPES else "presidential",
         election_date, json.dumps(candidates or []),
         risk_level if risk_level in VALID_RISK else "normal",
         json.dumps(risk_factors or []), region, analyst),
    )
    conn.commit()
    return eid


def get_election(conn, eid: str) -> dict | None:
    row = conn.execute("SELECT * FROM election_monitors WHERE id = ?", (eid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    for f in ("candidates", "risk_factors", "irregularities"):
        d[f] = json.loads(d[f]) if d[f] else []
    return d


def list_elections(conn, country_code: str | None = None, status: str | None = None,
                   limit: int = 50) -> list[dict]:
    conditions, params = [], []
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)
    if status and status in VALID_STATUSES:
        conditions.append("status = ?"); params.append(status)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM election_monitors{where} ORDER BY election_date DESC LIMIT ?",
        params + [limit]).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        for f in ("candidates", "risk_factors", "irregularities"):
            d[f] = json.loads(d[f]) if d[f] else []
        results.append(d)
    return results


def update_election(conn, eid: str, status: str | None = None,
                    irregularities: list[str] | None = None,
                    turnout_pct: float | None = None,
                    result_summary: str | None = None,
                    risk_level: str | None = None) -> bool:
    row = conn.execute("SELECT * FROM election_monitors WHERE id = ?", (eid,)).fetchone()
    if not row:
        return False
    updates, params = ["updated_at = ?"], [datetime.now(timezone.utc).isoformat()]
    if status and status in VALID_STATUSES:
        updates.append("status = ?"); params.append(status)
    if irregularities:
        existing = json.loads(row["irregularities"]) if row["irregularities"] else []
        updates.append("irregularities = ?"); params.append(json.dumps(existing + irregularities))
    if turnout_pct is not None:
        updates.append("turnout_pct = ?"); params.append(turnout_pct)
    if result_summary:
        updates.append("result_summary = ?"); params.append(result_summary)
    if risk_level and risk_level in VALID_RISK:
        updates.append("risk_level = ?"); params.append(risk_level)
    params.append(eid)
    conn.execute(f"UPDATE election_monitors SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    return True
