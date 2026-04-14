"""
Satellite orbit tracking — stores TLE (Two-Line Element) data and computes
simplified orbit pass predictions using Keplerian approximations.

Uses pure-Python orbital mechanics (no sgp4 dependency) for basic predictions.
"""
import json
import math
import uuid
from datetime import datetime, timezone, timedelta

# Seed: notable military/intelligence satellites
SEED_SATELLITES = [
    (25544, "ISS (ZARYA)", "science", "INT",
     "1 25544U 98067A   25100.50000000  .00016717  00000-0  10270-3 0  9005",
     "2 25544  51.6400 100.0000 0007000  50.0000 310.0000 15.50000000    05",
     51.64, 92.9, 420, 418, "1998-11-20"),
    (43013, "USA 276 (NROL-76)", "military", "US",
     None, None, 50.0, 95.0, 400, 390, "2017-05-01"),
    (39084, "YAOGAN 16A", "military", "CN",
     None, None, 63.4, 100.0, 1090, 1070, "2012-11-25"),
    (41862, "COSMO-SKYMED 2G FM1", "earth_obs", "IT",
     None, None, 97.9, 97.2, 620, 612, "2019-12-18"),
    (28654, "NOAA 18", "weather", "US",
     None, None, 99.0, 102.1, 854, 846, "2005-05-20"),
    (43226, "GLONASS-M 52", "navigation", "RU",
     None, None, 64.8, 676.0, 19140, 19100, "2018-06-17"),
    (37348, "TIANGONG", "science", "CN",
     None, None, 41.5, 91.5, 390, 385, "2021-04-29"),
    (49260, "STARLINK-3142", "comms", "US",
     None, None, 53.2, 95.6, 550, 540, "2021-11-13"),
    (27424, "ENVISAT", "earth_obs", "EU",
     None, None, 98.5, 100.6, 790, 785, "2002-03-01"),
    (25338, "LACROSSE 3", "military", "US",
     None, None, 57.0, 95.0, 680, 670, "1997-10-24"),
]


def seed_satellites(conn) -> int:
    count = 0
    for norad, name, cat, cc, tle1, tle2, inc, period, apo, peri, launch in SEED_SATELLITES:
        sid = str(uuid.uuid4())
        try:
            conn.execute(
                """INSERT OR IGNORE INTO satellite_orbits
                   (id, norad_id, name, category, country_code,
                    tle_line1, tle_line2, inclination, period_min,
                    apogee_km, perigee_km, launch_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sid, norad, name, cat, cc, tle1, tle2,
                 inc, period, apo, peri, launch),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    return count


def add_satellite(conn, norad_id: int, name: str,
                  category: str = "unknown", country_code: str | None = None,
                  tle_line1: str | None = None, tle_line2: str | None = None,
                  inclination: float | None = None, period_min: float | None = None,
                  apogee_km: float | None = None, perigee_km: float | None = None,
                  launch_date: str | None = None) -> str:
    sid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO satellite_orbits
           (id, norad_id, name, category, country_code,
            tle_line1, tle_line2, inclination, period_min,
            apogee_km, perigee_km, launch_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, norad_id, name, category, country_code,
         tle_line1, tle_line2, inclination, period_min,
         apogee_km, perigee_km, launch_date),
    )
    conn.commit()
    return sid


def get_satellite(conn, satellite_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM satellite_orbits WHERE id = ?",
                       (satellite_id,)).fetchone()
    return dict(row) if row else None


def get_by_norad(conn, norad_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM satellite_orbits WHERE norad_id = ?",
                       (norad_id,)).fetchone()
    return dict(row) if row else None


def list_satellites(conn, category: str | None = None,
                    country_code: str | None = None,
                    status: str = "active",
                    limit: int = 100) -> list[dict]:
    conditions, params = ["status = ?"], [status]
    if category:
        conditions.append("category = ?"); params.append(category)
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)

    where = " WHERE " + " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM satellite_orbits{where} ORDER BY name LIMIT ?",
        params + [limit]).fetchall()
    return [dict(r) for r in rows]


def predict_passes(conn, norad_id: int, observer_lat: float,
                   observer_lng: float, hours: int = 24) -> list[dict]:
    """
    Simplified pass prediction using Keplerian approximation.
    Returns approximate visible pass windows based on orbital period and inclination.
    """
    sat = get_by_norad(conn, norad_id)
    if not sat or not sat["period_min"] or not sat["inclination"]:
        return []

    period_sec = sat["period_min"] * 60
    inc = math.radians(sat["inclination"])
    altitude = ((sat["apogee_km"] or 400) + (sat["perigee_km"] or 400)) / 2

    # Approximate ground track: satellite covers ±inclination in latitude
    max_lat = sat["inclination"]
    if abs(observer_lat) > max_lat + 5:
        return []  # Observer too far from orbital plane

    passes = []
    now = datetime.now(timezone.utc)

    # Approximate: one orbit per period, visible when ground track is near observer
    orbits_in_window = int(hours * 3600 / period_sec) + 1

    for i in range(orbits_in_window):
        pass_time = now + timedelta(seconds=i * period_sec)
        # Simplified visibility check: every Nth pass is "visible"
        # based on observer longitude alignment (rough approximation)
        lng_offset = (i * 360 / (86400 / period_sec)) % 360
        effective_lng = (lng_offset - 180) % 360 - 180
        dist = abs(effective_lng - observer_lng)
        if dist > 180:
            dist = 360 - dist

        if dist < 30:  # Within ~30° longitude
            max_elev = max(5, 90 - dist * 2)  # Rough max elevation
            duration = max(60, int(600 * (1 - dist / 30)))  # Duration in seconds

            passes.append({
                "satellite_name": sat["name"],
                "norad_id": norad_id,
                "rise_time": pass_time.isoformat(),
                "set_time": (pass_time + timedelta(seconds=duration)).isoformat(),
                "max_elevation": round(max_elev, 1),
                "duration_sec": duration,
                "altitude_km": altitude,
            })

    return passes[:10]  # Limit to 10 passes


def get_orbit_geojson(conn, category: str | None = None) -> dict:
    """Generate approximate orbit ground tracks as GeoJSON."""
    sats = list_satellites(conn, category=category, limit=1000)
    features = []

    for sat in sats:
        if not sat["inclination"] or not sat["period_min"]:
            continue

        inc = sat["inclination"]
        period = sat["period_min"]
        # Generate simplified sinusoidal ground track
        coords = []
        for t in range(0, 360, 5):
            lng = (t - 180)
            lat = inc * math.sin(math.radians(t))
            coords.append([lng, lat])

        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "name": sat["name"],
                "norad_id": sat["norad_id"],
                "category": sat["category"],
                "country_code": sat["country_code"],
                "altitude_km": ((sat["apogee_km"] or 0) + (sat["perigee_km"] or 0)) / 2,
                "color": {
                    "military": "#ef4444", "comms": "#60a5fa",
                    "earth_obs": "#22c55e", "weather": "#eab308",
                    "navigation": "#a78bfa", "science": "#f97316",
                }.get(sat["category"], "#94a3b8"),
            },
        })

    return {"type": "FeatureCollection", "features": features}
