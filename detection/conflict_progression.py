"""
Conflict progression documentary mode — step-by-step narrated
conflict timelines with camera positions and map annotations.
"""
import uuid
import json


def create_progression(conn, conflict_name: str, region: str = "",
                       start_date: str = "") -> dict:
    pid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO conflict_progressions
           (id, conflict_name, region, start_date)
           VALUES (?, ?, ?, ?)""",
        (pid, conflict_name, region, start_date or "2025-01-01"))
    conn.commit()
    return {"id": pid, "conflict_name": conflict_name, "region": region}


def add_step(conn, progression_id: str, step_number: int, title: str,
             narration: str, center_lat: float, center_lng: float,
             zoom: float = 6, bearing: float = 0, pitch: float = 45,
             event_date: str = "", markers: list | None = None,
             lines: list | None = None) -> dict:
    sid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO conflict_progression_steps
           (id, progression_id, step_number, title, narration,
            center_lat, center_lng, zoom, bearing, pitch,
            event_date, markers_json, lines_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, progression_id, step_number, title, narration,
         center_lat, center_lng, zoom, bearing, pitch, event_date,
         json.dumps(markers or []), json.dumps(lines or [])))
    conn.commit()
    return {"id": sid, "step_number": step_number, "title": title}


def get_progression(conn, progression_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM conflict_progressions WHERE id = ?",
        (progression_id,)).fetchone()
    return dict(row) if row else None


def list_progressions(conn, status: str = "ongoing") -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM conflict_progressions WHERE status = ? ORDER BY start_date DESC",
        (status,)).fetchall()
    return [dict(r) for r in rows]


def get_steps(conn, progression_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM conflict_progression_steps
           WHERE progression_id = ? ORDER BY step_number""",
        (progression_id,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["markers"] = json.loads(d.get("markers_json") or "[]")
        d["lines"] = json.loads(d.get("lines_json") or "[]")
        result.append(d)
    return result


def get_step_geojson(conn, progression_id: str, step_number: int) -> dict:
    """Get GeoJSON for a specific step's markers and lines."""
    row = conn.execute(
        """SELECT * FROM conflict_progression_steps
           WHERE progression_id = ? AND step_number = ?""",
        (progression_id, step_number)).fetchone()
    if not row:
        return {"type": "FeatureCollection", "features": []}

    d = dict(row)
    markers = json.loads(d.get("markers_json") or "[]")
    lines = json.loads(d.get("lines_json") or "[]")

    features = []
    for m in markers:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [m.get("lng", 0), m.get("lat", 0)]},
            "properties": {
                "label": m.get("label", ""),
                "color": m.get("color", "#ef4444"),
            },
        })
    for line_coords in lines:
        if len(line_coords) >= 2:
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": line_coords},
                "properties": {"type": "frontline", "color": "#ef4444"},
            })

    return {"type": "FeatureCollection", "features": features}


def seed_sample_progressions(conn) -> int:
    """Seed sample conflict progression for demo."""
    existing = conn.execute(
        "SELECT COUNT(*) FROM conflict_progressions").fetchone()[0]
    if existing > 0:
        return 0

    # Ukraine conflict progression
    prog = create_progression(conn, "Ukraine-Russia Conflict", "Eastern Europe", "2022-02-24")

    steps = [
        (1, "Initial Invasion", "Russian forces launch multi-axis invasion from north, east, and south.",
         50.4, 30.5, 6, 0, 45, "2022-02-24",
         [{"lat": 51.5, "lng": 31.3, "label": "Chernihiv axis", "color": "#ef4444"},
          {"lat": 50.4, "lng": 30.5, "label": "Kyiv", "color": "#3b82f6"},
          {"lat": 46.5, "lng": 36.8, "label": "Southern front", "color": "#ef4444"}],
         [[[30.5, 51.8], [30.5, 50.8]], [[36.0, 47.0], [35.5, 46.5]]]),

        (2, "Battle of Kyiv", "Fierce resistance halts Russian advance on the capital.",
         50.4, 30.5, 8, -20, 50, "2022-03-15",
         [{"lat": 50.5, "lng": 30.2, "label": "Irpin", "color": "#eab308"},
          {"lat": 50.6, "lng": 30.5, "label": "Bucha", "color": "#ef4444"},
          {"lat": 51.3, "lng": 30.1, "label": "Hostomel Airport", "color": "#ef4444"}],
         []),

        (3, "Northern Withdrawal", "Russia withdraws from northern Ukraine, refocuses on Donbas.",
         49.0, 37.0, 7, 10, 40, "2022-04-02",
         [{"lat": 49.0, "lng": 37.5, "label": "Donbas focus", "color": "#ef4444"},
          {"lat": 47.1, "lng": 37.5, "label": "Mariupol siege", "color": "#ef4444"}],
         [[[36.0, 49.5], [38.0, 49.0], [39.0, 48.5]]]),

        (4, "Kherson Counter-Offensive", "Ukrainian forces recapture Kherson.",
         46.6, 32.6, 8, 30, 50, "2022-11-11",
         [{"lat": 46.6, "lng": 32.6, "label": "Kherson liberated", "color": "#22c55e"},
          {"lat": 46.9, "lng": 33.4, "label": "Dnipro River line", "color": "#3b82f6"}],
         []),

        (5, "Ongoing Attritional Warfare", "Conflict settles into attritional phase along extended frontlines.",
         48.5, 37.5, 6, 0, 45, "2025-01-01",
         [{"lat": 48.5, "lng": 37.5, "label": "Active front", "color": "#ef4444"},
          {"lat": 47.8, "lng": 35.0, "label": "Zaporizhzhia line", "color": "#eab308"}],
         [[[35.0, 47.0], [36.5, 47.5], [38.0, 48.5], [39.0, 49.0]]]),
    ]

    for sn, title, narration, lat, lng, z, b, pi, date, markers, lines in steps:
        add_step(conn, prog["id"], sn, title, narration, lat, lng, z, b, pi, date,
                 markers, lines)

    return 1
