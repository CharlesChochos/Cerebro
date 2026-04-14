"""
Cyber incident tracking — monitors ransomware, APTs, DDoS, data breaches,
supply chain attacks, and zero-day exploits.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta

VALID_TYPES = {"ransomware", "apt", "ddos", "data_breach", "supply_chain", "zero_day"}
VALID_SECTORS = {"government", "military", "finance", "energy", "healthcare", "tech"}
VALID_STATUSES = {"active", "contained", "resolved", "investigating"}
VALID_CONFIDENCE = {"low", "moderate", "high"}


def record_incident(conn, incident_type: str, severity: float = 50,
                    target_sector: str | None = None, target_country: str | None = None,
                    target_org: str | None = None, attributed_to: str | None = None,
                    attribution_confidence: str = "low",
                    attack_vector: str | None = None,
                    iocs: dict | None = None, impact: str | None = None) -> str:
    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO cyber_incidents
           (id, incident_type, severity, target_sector, target_country,
            target_org, attributed_to, attribution_confidence, attack_vector,
            iocs, impact)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid,
         incident_type if incident_type in VALID_TYPES else "data_breach",
         min(100, max(0, severity)),
         target_sector if target_sector in VALID_SECTORS else None,
         target_country, target_org, attributed_to,
         attribution_confidence if attribution_confidence in VALID_CONFIDENCE else "low",
         attack_vector, json.dumps(iocs) if iocs else None, impact),
    )
    conn.commit()
    return cid


def get_incident(conn, cid: str) -> dict | None:
    row = conn.execute("SELECT * FROM cyber_incidents WHERE id = ?", (cid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["iocs"] = json.loads(d["iocs"]) if d["iocs"] else None
    return d


def list_incidents(conn, incident_type: str | None = None, target_country: str | None = None,
                   attributed_to: str | None = None, status: str | None = None,
                   days: int = 90, limit: int = 50) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions, params = ["created_at >= ?"], [cutoff]
    if incident_type and incident_type in VALID_TYPES:
        conditions.append("incident_type = ?"); params.append(incident_type)
    if target_country:
        conditions.append("target_country = ?"); params.append(target_country)
    if attributed_to:
        conditions.append("attributed_to LIKE ?"); params.append(f"%{attributed_to}%")
    if status and status in VALID_STATUSES:
        conditions.append("status = ?"); params.append(status)
    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM cyber_incidents WHERE {where} ORDER BY severity DESC LIMIT ?",
        params + [limit]).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["iocs"] = json.loads(d["iocs"]) if d["iocs"] else None
        results.append(d)
    return results


def update_incident(conn, cid: str, status: str | None = None,
                    attributed_to: str | None = None,
                    attribution_confidence: str | None = None) -> bool:
    row = conn.execute("SELECT id FROM cyber_incidents WHERE id = ?", (cid,)).fetchone()
    if not row:
        return False
    updates, params = [], []
    if status and status in VALID_STATUSES:
        updates.append("status = ?"); params.append(status)
    if attributed_to:
        updates.append("attributed_to = ?"); params.append(attributed_to)
    if attribution_confidence and attribution_confidence in VALID_CONFIDENCE:
        updates.append("attribution_confidence = ?"); params.append(attribution_confidence)
    if not updates:
        return True
    params.append(cid)
    conn.execute(f"UPDATE cyber_incidents SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    return True


def get_threat_landscape(conn, days: int = 30) -> dict:
    """Cyber threat landscape summary."""
    incidents = list_incidents(conn, days=days, limit=500)
    by_type, by_sector, by_actor = {}, {}, {}
    for i in incidents:
        by_type[i["incident_type"]] = by_type.get(i["incident_type"], 0) + 1
        if i["target_sector"]:
            by_sector[i["target_sector"]] = by_sector.get(i["target_sector"], 0) + 1
        if i["attributed_to"]:
            by_actor[i["attributed_to"]] = by_actor.get(i["attributed_to"], 0) + 1
    active = [i for i in incidents if i["status"] in ("active", "investigating")]
    return {
        "total_incidents": len(incidents), "active": len(active),
        "by_incident_type": by_type, "by_target_sector": by_sector,
        "by_threat_actor": by_actor,
        "avg_severity": round(sum(i["severity"] for i in incidents) / max(len(incidents), 1), 1),
    }
