"""
Monitored locations — pulse beacon sites tracked for activity changes.

Each location has an alert level (normal → elevated → high → critical)
and a pulse_rate that drives the frontend beacon animation speed.
"""
import uuid
from datetime import datetime, timezone

# Seed: notable geopolitical monitoring points
SEED_LOCATIONS = [
    ("Camp Humphreys", 36.9627, 127.0312, "military_base", "KR",
     "normal", 2.0, 50, "Largest US overseas military base"),
    ("Natanz Nuclear Facility", 33.7245, 51.7269, "nuclear", "IR",
     "elevated", 1.5, 30, "Iranian uranium enrichment site"),
    ("Sevastopol Naval Base", 44.6167, 33.5254, "military_base", "UA",
     "high", 1.0, 40, "Major Black Sea fleet base"),
    ("Strait of Hormuz", 26.5667, 56.2500, "port", "OM",
     "elevated", 1.5, 80, "Critical oil transit chokepoint"),
    ("Suez Canal", 30.4550, 32.3500, "port", "EG",
     "normal", 2.0, 60, "Global shipping chokepoint"),
    ("US Embassy Baghdad", 33.2985, 44.3961, "embassy", "IQ",
     "elevated", 1.5, 10, "Largest US embassy compound"),
    ("Bagram Airfield", 34.9461, 69.2650, "airfield", "AF",
     "normal", 2.0, 20, "Former major coalition airbase"),
    ("Kaliningrad", 54.7104, 20.4522, "military_base", "RU",
     "elevated", 1.5, 40, "Russian Baltic exclave & military hub"),
    ("Tartus Naval Facility", 34.8861, 35.8867, "port", "SY",
     "high", 1.0, 30, "Russian naval base in Syria"),
    ("Guantanamo Bay", 19.9023, -75.0961, "military_base", "CU",
     "normal", 2.0, 30, "US naval station"),
    ("Yongbyon Nuclear Complex", 39.7953, 125.7553, "nuclear", "KP",
     "high", 1.0, 20, "North Korean nuclear facility"),
    ("Diego Garcia", -7.3133, 72.4111, "airfield", "IO",
     "normal", 2.0, 50, "US/UK military atoll base"),
]


def seed_locations(conn) -> int:
    count = 0
    for name, lat, lng, loc_type, cc, alert, pulse, radius, notes in SEED_LOCATIONS:
        lid = str(uuid.uuid4())
        try:
            conn.execute(
                """INSERT OR IGNORE INTO monitored_locations
                   (id, name, latitude, longitude, location_type, country_code,
                    alert_level, pulse_rate, radius_km, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (lid, name, lat, lng, loc_type, cc, alert, pulse, radius, notes),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    return count


def add_location(conn, name: str, latitude: float, longitude: float,
                 location_type: str = "general", country_code: str | None = None,
                 alert_level: str = "normal", pulse_rate: float = 2.0,
                 radius_km: float = 50, notes: str | None = None) -> str:
    valid_types = {"general", "military_base", "embassy", "port",
                   "border", "nuclear", "airfield"}
    if location_type not in valid_types:
        raise ValueError(f"Invalid location_type: {location_type}")

    valid_alerts = {"normal", "elevated", "high", "critical"}
    if alert_level not in valid_alerts:
        raise ValueError(f"Invalid alert_level: {alert_level}")

    lid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO monitored_locations
           (id, name, latitude, longitude, location_type, country_code,
            alert_level, pulse_rate, radius_km, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lid, name, latitude, longitude, location_type, country_code,
         alert_level, pulse_rate, radius_km, notes),
    )
    conn.commit()
    return lid


def get_location(conn, location_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM monitored_locations WHERE id = ?",
                       (location_id,)).fetchone()
    return dict(row) if row else None


def list_locations(conn, location_type: str | None = None,
                   alert_level: str | None = None,
                   country_code: str | None = None,
                   active_only: bool = True,
                   limit: int = 100) -> list[dict]:
    conditions, params = [], []
    if active_only:
        conditions.append("active = 1")
    if location_type:
        conditions.append("location_type = ?"); params.append(location_type)
    if alert_level:
        conditions.append("alert_level = ?"); params.append(alert_level)
    if country_code:
        conditions.append("country_code = ?"); params.append(country_code)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM monitored_locations{where} ORDER BY name LIMIT ?",
        params + [limit]).fetchall()
    return [dict(r) for r in rows]


def update_alert_level(conn, location_id: str, alert_level: str,
                       pulse_rate: float | None = None) -> bool:
    valid_alerts = {"normal", "elevated", "high", "critical"}
    if alert_level not in valid_alerts:
        raise ValueError(f"Invalid alert_level: {alert_level}")

    # Auto-adjust pulse rate based on alert level if not specified
    if pulse_rate is None:
        pulse_rate = {"normal": 2.0, "elevated": 1.5,
                      "high": 1.0, "critical": 0.5}[alert_level]

    conn.execute(
        """UPDATE monitored_locations
           SET alert_level = ?, pulse_rate = ?
           WHERE id = ?""",
        (alert_level, pulse_rate, location_id),
    )
    conn.commit()
    return conn.total_changes > 0


def record_event(conn, location_id: str) -> bool:
    """Increment 24h event counter for a location."""
    conn.execute(
        """UPDATE monitored_locations
           SET event_count_24h = event_count_24h + 1,
               last_event_at = datetime('now')
           WHERE id = ?""",
        (location_id,),
    )
    conn.commit()
    return conn.total_changes > 0


def get_beacon_geojson(conn, alert_level: str | None = None) -> dict:
    """Generate GeoJSON for pulse beacons with animation properties."""
    locations = list_locations(conn, alert_level=alert_level, limit=200)
    features = []

    alert_colors = {
        "normal": "#22c55e",
        "elevated": "#eab308",
        "high": "#f97316",
        "critical": "#ef4444",
    }

    for loc in locations:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [loc["longitude"], loc["latitude"]],
            },
            "properties": {
                "id": loc["id"],
                "name": loc["name"],
                "location_type": loc["location_type"],
                "country_code": loc["country_code"],
                "alert_level": loc["alert_level"],
                "pulse_rate": loc["pulse_rate"],
                "radius_km": loc["radius_km"],
                "event_count_24h": loc["event_count_24h"],
                "color": alert_colors.get(loc["alert_level"], "#94a3b8"),
            },
        })

    return {"type": "FeatureCollection", "features": features}
