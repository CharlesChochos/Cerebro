"""
Conflict frontline tracking — stores and retrieves territorial control
geometries for animated frontline visualization.
"""
import json
import uuid


def add_frontline(conn, conflict_name: str, date: str,
                  geometry_json: str | dict,
                  country_code: str | None = None,
                  side_a: str | None = None,
                  side_b: str | None = None,
                  status: str = "active",
                  source: str | None = None) -> str:
    fid = str(uuid.uuid4())
    geo = json.dumps(geometry_json) if isinstance(geometry_json, dict) else geometry_json
    conn.execute(
        """INSERT INTO conflict_frontlines
           (id, conflict_name, country_code, date, geometry_json,
            side_a, side_b, status, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fid, conflict_name, country_code, date, geo,
         side_a, side_b, status, source),
    )
    conn.commit()
    return fid


def get_frontline(conn, frontline_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM conflict_frontlines WHERE id = ?",
                       (frontline_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["geometry"] = json.loads(d["geometry_json"])
    return d


def list_frontlines(conn, conflict_name: str | None = None,
                    country_code: str | None = None,
                    status: str | None = None,
                    limit: int = 50) -> list[dict]:
    conditions, params = [], []
    if conflict_name:
        conditions.append("conflict_name = ?"); params.append(conflict_name)
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)
    if status:
        conditions.append("status = ?"); params.append(status)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM conflict_frontlines{where} ORDER BY date DESC LIMIT ?",
        params + [limit]).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["geometry"] = json.loads(d["geometry_json"])
        results.append(d)
    return results


def get_frontline_animation(conn, conflict_name: str,
                            limit: int = 365) -> dict:
    """Get chronologically ordered frontline snapshots for animation."""
    rows = conn.execute(
        """SELECT * FROM conflict_frontlines
           WHERE conflict_name = ?
           ORDER BY date ASC LIMIT ?""",
        (conflict_name, limit)).fetchall()

    frames = []
    for r in rows:
        d = dict(r)
        frames.append({
            "date": d["date"],
            "geometry": json.loads(d["geometry_json"]),
            "side_a": d["side_a"],
            "side_b": d["side_b"],
            "status": d["status"],
        })
    return {
        "conflict_name": conflict_name,
        "frame_count": len(frames),
        "frames": frames,
    }


def get_frontlines_geojson(conn, conflict_name: str | None = None,
                           date: str | None = None) -> dict:
    """Return latest frontlines as GeoJSON FeatureCollection."""
    conditions, params = [], []
    if conflict_name:
        conditions.append("conflict_name = ?"); params.append(conflict_name)
    if date:
        conditions.append("date = ?"); params.append(date)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # Get latest date per conflict if no specific date
    if not date:
        rows = conn.execute(
            f"""SELECT f1.* FROM conflict_frontlines f1
                INNER JOIN (
                    SELECT conflict_name, MAX(date) as max_date
                    FROM conflict_frontlines
                    {where}
                    GROUP BY conflict_name
                ) f2 ON f1.conflict_name = f2.conflict_name AND f1.date = f2.max_date
                LIMIT 100""",
            params).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM conflict_frontlines{where} LIMIT 100",
            params).fetchall()

    STATUS_COLORS = {
        "active": "#ef4444",
        "frozen": "#60a5fa",
        "ceasefire": "#22c55e",
    }

    features = []
    for r in rows:
        d = dict(r)
        geo = json.loads(d["geometry_json"])
        features.append({
            "type": "Feature",
            "geometry": geo,
            "properties": {
                "id": d["id"],
                "conflict_name": d["conflict_name"],
                "date": d["date"],
                "side_a": d["side_a"],
                "side_b": d["side_b"],
                "status": d["status"],
                "color": STATUS_COLORS.get(d["status"], "#ef4444"),
            },
        })
    return {"type": "FeatureCollection", "features": features}
