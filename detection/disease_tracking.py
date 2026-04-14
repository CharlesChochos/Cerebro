"""
Disease outbreak spread tracking and animation data.

Generates time-stepped concentric spread circles based on a simplified
SIR (Susceptible-Infected-Recovered) model with geographic propagation.

Uses the existing disease_outbreaks table (from migration 006) plus
spread animation columns added in migration 020.
"""
import uuid
import math


def _offset_coords(lat: float, lng: float, bearing_deg: float, dist_km: float):
    """Offset a point by distance along a bearing."""
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


def create_outbreak(conn, disease: str, lat: float, lng: float,
                    country_code: str = "", r_naught: float = 2.5,
                    mortality_rate: float = 0.01) -> dict:
    """Create a new disease outbreak and generate initial spread points."""
    oid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO disease_outbreaks
           (id, source, disease, title, summary, country_code,
            lat, lng, case_count, death_count, status, severity,
            published_at, r_naught, mortality_rate)
           VALUES (?, 'simulation', ?, ?, '', ?,
                   ?, ?, 1, 0, 'active', 50,
                   datetime('now'), ?, ?)""",
        (oid, disease, f"{disease} outbreak", country_code,
         lat, lng, r_naught, mortality_rate))

    # Generate spread points for 30 days
    _generate_spread(conn, oid, lat, lng, r_naught, days=30)
    conn.commit()

    return {
        "id": oid,
        "disease": disease,
        "lat": lat,
        "lng": lng,
        "r_naught": r_naught,
        "days_generated": 30,
    }


def _generate_spread(conn, outbreak_id: str, lat: float, lng: float,
                     r_naught: float, days: int = 30):
    """Generate spread points over time with geographic dispersion."""
    cases = 1
    radius_km = 5.0

    for day in range(days):
        cases = int(cases * (1 + (r_naught - 1) * 0.1 * max(0, 1 - cases / 100000)))
        cases = min(cases, 1000000)
        radius_km = min(radius_km * 1.12, 2000)

        pid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO disease_spread_points
               (id, outbreak_id, latitude, longitude, cases, day_offset, radius_km)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pid, outbreak_id, lat, lng, cases, day, round(radius_km, 1)))

        # Secondary spread after day 5
        if day > 5 and day % 3 == 0:
            bearing = (day * 47) % 360
            dist = radius_km * 0.4
            slat, slng = _offset_coords(lat, lng, bearing, dist)
            sid = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO disease_spread_points
                   (id, outbreak_id, latitude, longitude, cases, day_offset, radius_km)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sid, outbreak_id, slat, slng, int(cases * 0.2), day,
                 round(radius_km * 0.3, 1)))


def get_outbreak(conn, outbreak_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM disease_outbreaks WHERE id = ?",
        (outbreak_id,)).fetchone()
    return dict(row) if row else None


def list_outbreaks(conn, status: str = "active") -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM disease_outbreaks WHERE status = ? ORDER BY published_at DESC",
        (status,)).fetchall()
    return [dict(r) for r in rows]


def get_spread_geojson(conn, outbreak_id: str, day: int | None = None) -> dict:
    """Get GeoJSON for outbreak spread animation."""
    if day is not None:
        rows = conn.execute(
            """SELECT * FROM disease_spread_points
               WHERE outbreak_id = ? AND day_offset <= ?
               ORDER BY day_offset""",
            (outbreak_id, day)).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM disease_spread_points
               WHERE outbreak_id = ? ORDER BY day_offset""",
            (outbreak_id,)).fetchall()

    features = []
    for r in rows:
        r = dict(r)
        center_lat, center_lng = r["latitude"], r["longitude"]
        radius_km = r["radius_km"]
        coords = []
        for i in range(33):
            angle = (i % 32) * (360 / 32)
            plat, plng = _offset_coords(center_lat, center_lng, angle, radius_km)
            coords.append([plng, plat])

        opacity = max(0.1, 0.6 - r["day_offset"] * 0.015)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "day_offset": r["day_offset"],
                "cases": r["cases"],
                "radius_km": radius_km,
                "opacity": round(opacity, 2),
            },
        })

    return {"type": "FeatureCollection", "features": features}


def seed_sample_outbreaks(conn) -> int:
    """Seed sample outbreaks for demonstration."""
    existing = conn.execute(
        "SELECT COUNT(*) FROM disease_outbreaks WHERE source = 'simulation'"
    ).fetchone()[0]
    if existing > 0:
        return 0

    samples = [
        ("Respiratory Virus X", 23.1, 113.3, "CN", 3.2, 0.02),
        ("Hemorrhagic Fever Y", 6.5, 3.4, "NG", 1.8, 0.15),
        ("Influenza Strain Z", 35.7, 139.7, "JP", 2.0, 0.005),
    ]
    count = 0
    for name, lat, lng, cc, r0, mr in samples:
        create_outbreak(conn, name, lat, lng, cc, r0, mr)
        count += 1
    return count
