"""
Nuclear proliferation tracking — monitors nuclear-related events including
tests, enrichment activities, facility construction, treaty violations,
missile tests, and escalatory rhetoric.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta

VALID_TYPES = {"test", "enrichment", "facility", "treaty", "missile", "rhetoric"}
VALID_STATUSES = {"unconfirmed", "confirmed", "denied", "retracted"}
VALID_SOURCE_TYPES = {"satellite", "seismic", "humint", "osint", "diplomatic"}

# Countries of proliferation concern
WATCHLIST_COUNTRIES = {"KP", "IR", "PK", "IN", "IL", "RU", "CN", "US", "GB", "FR"}


def record_event(conn, country_code: str, event_type: str, severity: float = 50,
                 facility_name: str | None = None, lat: float | None = None,
                 lng: float | None = None, description: str | None = None,
                 evidence: list[str] | None = None,
                 source_type: str | None = None) -> str:
    nid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO nuclear_events
           (id, country_code, event_type, severity, facility_name,
            latitude, longitude, description, evidence, source_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (nid, country_code,
         event_type if event_type in VALID_TYPES else "rhetoric",
         min(100, max(0, severity)), facility_name, lat, lng, description,
         json.dumps(evidence or []),
         source_type if source_type in VALID_SOURCE_TYPES else None),
    )
    conn.commit()
    return nid


def get_event(conn, nid: str) -> dict | None:
    row = conn.execute("SELECT * FROM nuclear_events WHERE id = ?", (nid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
    return d


def list_events(conn, country_code: str | None = None, event_type: str | None = None,
                status: str | None = None, days: int = 90, limit: int = 50) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions, params = ["created_at >= ?"], [cutoff]
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)
    if event_type and event_type in VALID_TYPES:
        conditions.append("event_type = ?"); params.append(event_type)
    if status and status in VALID_STATUSES:
        conditions.append("status = ?"); params.append(status)
    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM nuclear_events WHERE {where} ORDER BY severity DESC LIMIT ?",
        params + [limit]).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
        results.append(d)
    return results


def update_status(conn, nid: str, status: str) -> bool:
    if status not in VALID_STATUSES:
        return False
    row = conn.execute("SELECT id FROM nuclear_events WHERE id = ?", (nid,)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE nuclear_events SET status = ? WHERE id = ?", (status, nid))
    conn.commit()
    return True


def get_country_profile(conn, country_code: str, days: int = 365) -> dict:
    """Nuclear threat profile for a country."""
    events = list_events(conn, country_code=country_code, days=days, limit=200)
    if not events:
        return {"country_code": country_code, "total_events": 0,
                "threat_level": "none", "on_watchlist": country_code in WATCHLIST_COUNTRIES}
    by_type = {}
    for e in events:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
    max_sev = max(e["severity"] for e in events)
    avg_sev = sum(e["severity"] for e in events) / len(events)
    threat = "critical" if max_sev >= 85 else "high" if max_sev >= 65 else "elevated" if max_sev >= 45 else "low"
    return {
        "country_code": country_code, "total_events": len(events),
        "by_event_type": by_type, "max_severity": round(max_sev, 1),
        "avg_severity": round(avg_sev, 1), "threat_level": threat,
        "on_watchlist": country_code in WATCHLIST_COUNTRIES,
    }
