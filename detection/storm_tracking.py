"""
Storm/weather tracking — generates animated storm track paths with
uncertainty cones for hurricanes, typhoons, cyclones, and tornadoes.
"""
import uuid
import math


def _offset_coords(lat: float, lng: float, bearing_deg: float, dist_km: float):
    R = 6371.0
    d = dist_km / R
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) +
                      math.cos(lat1) * math.sin(d) * math.cos(br))
    lng2 = lng1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(lat1),
                              math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lng2)


STORM_CATEGORY_COLORS = {
    1: "#3b82f6",   # blue
    2: "#22c55e",   # green
    3: "#eab308",   # yellow
    4: "#f97316",   # orange
    5: "#ef4444",   # red
}


def create_storm(conn, storm_name: str, storm_type: str = "hurricane",
                 category: int = 3, max_wind_kts: int = 120) -> dict:
    sid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO storm_tracks
           (id, storm_name, storm_type, category, max_wind_kts)
           VALUES (?, ?, ?, ?, ?)""",
        (sid, storm_name, storm_type, min(category, 5), max_wind_kts))
    conn.commit()
    return {"id": sid, "storm_name": storm_name, "storm_type": storm_type,
            "category": category}


def add_track_point(conn, storm_id: str, latitude: float, longitude: float,
                    timestamp: str, wind_kts: int = 100, pressure_mb: int = 960,
                    is_forecast: int = 0, uncertainty_radius_km: float = 50) -> dict:
    pid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO storm_track_points
           (id, storm_id, latitude, longitude, timestamp, wind_kts,
            pressure_mb, is_forecast, uncertainty_radius_km)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, storm_id, latitude, longitude, timestamp, wind_kts,
         pressure_mb, is_forecast, uncertainty_radius_km))
    conn.commit()
    return {"id": pid, "storm_id": storm_id}


def get_storm(conn, storm_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM storm_tracks WHERE id = ?",
                       (storm_id,)).fetchone()
    return dict(row) if row else None


def list_storms(conn, status: str = "active") -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM storm_tracks WHERE status = ? ORDER BY created_at DESC",
        (status,)).fetchall()
    return [dict(r) for r in rows]


def get_storm_track_geojson(conn, storm_id: str) -> dict:
    """Get GeoJSON: track line + uncertainty cone polygon + point markers."""
    points = conn.execute(
        """SELECT * FROM storm_track_points
           WHERE storm_id = ? ORDER BY timestamp""",
        (storm_id,)).fetchall()
    points = [dict(p) for p in points]

    if not points:
        return {"type": "FeatureCollection", "features": []}

    storm = get_storm(conn, storm_id)
    color = STORM_CATEGORY_COLORS.get(storm["category"] if storm else 3, "#eab308")

    features = []

    # Track line
    coords = [[p["longitude"], p["latitude"]] for p in points]
    features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "type": "track_line",
            "color": color,
            "storm_name": storm["storm_name"] if storm else "",
        },
    })

    # Forecast uncertainty cone
    forecast_pts = [p for p in points if p["is_forecast"]]
    if forecast_pts:
        # Build cone polygon: left side forward, right side backward
        left_coords = []
        right_coords = []
        for i, p in enumerate(forecast_pts):
            radius = p["uncertainty_radius_km"]
            lat, lng = p["latitude"], p["longitude"]
            # Perpendicular offsets
            if i < len(forecast_pts) - 1:
                next_p = forecast_pts[i + 1]
                bearing = math.degrees(math.atan2(
                    next_p["longitude"] - lng, next_p["latitude"] - lat))
            else:
                bearing = 0
            l_lat, l_lng = _offset_coords(lat, lng, bearing - 90, radius)
            r_lat, r_lng = _offset_coords(lat, lng, bearing + 90, radius)
            left_coords.append([l_lng, l_lat])
            right_coords.append([r_lng, r_lat])

        cone_coords = left_coords + list(reversed(right_coords))
        if cone_coords:
            cone_coords.append(cone_coords[0])  # close polygon
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [cone_coords]},
                "properties": {"type": "uncertainty_cone", "color": color},
            })

    # Point markers for each track position
    for p in points:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p["longitude"], p["latitude"]]},
            "properties": {
                "type": "track_point",
                "wind_kts": p["wind_kts"],
                "pressure_mb": p["pressure_mb"],
                "is_forecast": p["is_forecast"],
                "timestamp": p["timestamp"],
                "color": color,
            },
        })

    return {"type": "FeatureCollection", "features": features}


def seed_sample_storms(conn) -> int:
    """Seed sample storms with realistic track data."""
    existing = conn.execute("SELECT COUNT(*) FROM storm_tracks").fetchone()[0]
    if existing > 0:
        return 0

    # Hurricane in Gulf of Mexico
    s1 = create_storm(conn, "Hurricane Alpha", "hurricane", 4, 140)
    track1 = [
        (20.0, -86.0, "2025-09-10T06:00:00", 80, 985, 0, 30),
        (21.5, -87.5, "2025-09-10T12:00:00", 95, 975, 0, 35),
        (23.0, -89.0, "2025-09-11T00:00:00", 120, 955, 0, 40),
        (25.0, -90.0, "2025-09-11T12:00:00", 140, 935, 0, 45),
        (27.5, -90.5, "2025-09-12T00:00:00", 130, 945, 1, 80),
        (29.5, -90.0, "2025-09-12T12:00:00", 110, 960, 1, 120),
        (31.0, -89.0, "2025-09-13T00:00:00", 85, 975, 1, 180),
    ]
    for lat, lng, ts, w, p, fc, ur in track1:
        add_track_point(conn, s1["id"], lat, lng, ts, w, p, fc, ur)

    # Typhoon in Pacific
    s2 = create_storm(conn, "Typhoon Bravo", "typhoon", 5, 160)
    track2 = [
        (14.0, 135.0, "2025-10-01T00:00:00", 100, 970, 0, 40),
        (16.0, 133.0, "2025-10-01T12:00:00", 130, 945, 0, 45),
        (18.5, 131.0, "2025-10-02T00:00:00", 155, 920, 0, 50),
        (21.0, 129.0, "2025-10-02T12:00:00", 160, 910, 0, 55),
        (24.0, 128.0, "2025-10-03T00:00:00", 145, 930, 1, 90),
        (27.0, 128.5, "2025-10-03T12:00:00", 120, 950, 1, 140),
        (30.0, 130.0, "2025-10-04T00:00:00", 90, 970, 1, 200),
    ]
    for lat, lng, ts, w, p, fc, ur in track2:
        add_track_point(conn, s2["id"], lat, lng, ts, w, p, fc, ur)

    return 2
