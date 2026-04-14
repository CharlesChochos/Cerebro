"""
Event context enrichment — auto-enriches events with geographic context
at ingest time: nearest city, admin region, terrain type, proximity
to borders and military installations.

Uses the existing reverse_geocoding module plus heuristic terrain
classification based on coordinates.
"""
import uuid
from geo.reverse_geocoding import reverse_geocode


# Simplified terrain classification based on latitude/longitude heuristics
# In production this would use land cover data (e.g., ESA WorldCover)
TERRAIN_ZONES = [
    # (lat_min, lat_max, lng_min, lng_max, terrain, pop_density)
    (23, 35, 20, 60, "desert", "low"),       # Sahara / Arabian
    (60, 75, -180, 180, "tundra", "low"),     # Arctic regions
    (-60, -90, -180, 180, "ice", "uninhabited"),
    (20, 30, 70, 90, "mountain", "medium"),   # Himalayas
    (35, 47, 5, 20, "mountain", "medium"),    # Alps
    (-5, 5, -80, -60, "jungle", "low"),       # Amazon
    (-5, 5, 20, 40, "jungle", "low"),         # Congo
    (25, 50, -130, -65, "mixed", "high"),     # Continental US
    (45, 60, -10, 40, "temperate", "high"),   # Western Europe
    (20, 40, 100, 125, "mixed", "high"),      # Eastern China
]

# Known borders (simplified — major ones for proximity check)
MAJOR_BORDERS = [
    # (name, lat, lng) — points along borders
    ("US-Mexico", 32.0, -110.0),
    ("India-Pakistan LoC", 34.0, 74.5),
    ("North-South Korea DMZ", 38.0, 127.0),
    ("Ukraine-Russia", 50.0, 38.0),
    ("Israel-Gaza", 31.4, 34.4),
    ("Israel-Lebanon", 33.1, 35.5),
    ("Turkey-Syria", 36.8, 38.0),
    ("China-India LAC", 34.5, 78.0),
    ("Finland-Russia", 62.0, 30.0),
    ("Poland-Belarus", 53.0, 23.5),
]

# Known military installations (simplified sample)
MILITARY_BASES = [
    ("Camp Humphreys", 36.96, 127.03),
    ("Ramstein AB", 49.44, 7.60),
    ("Diego Garcia", -7.31, 72.41),
    ("Pearl Harbor", 21.35, -157.95),
    ("Sevastopol Naval", 44.62, 33.53),
    ("Tartus Naval", 34.89, 35.89),
    ("Natanz Nuclear", 33.72, 51.73),
    ("Bagram Airfield", 34.95, 69.27),
    ("Guantanamo Bay", 19.90, -75.10),
    ("Incirlik AB", 37.00, 35.43),
]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _classify_terrain(lat: float, lng: float) -> tuple[str, str]:
    """Classify terrain type and population density from coordinates."""
    for lat_min, lat_max, lng_min, lng_max, terrain, pop in TERRAIN_ZONES:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return terrain, pop

    # Coastal heuristic — very simplified
    if abs(lat) < 60:
        return "temperate", "medium"
    return "unknown", "unknown"


def _nearest_border(lat: float, lng: float) -> float | None:
    """Find distance to nearest known border in km."""
    if not MAJOR_BORDERS:
        return None
    distances = [_haversine_km(lat, lng, b[1], b[2]) for b in MAJOR_BORDERS]
    return round(min(distances), 1)


def _nearest_military(lat: float, lng: float) -> float | None:
    """Find distance to nearest known military installation in km."""
    if not MILITARY_BASES:
        return None
    distances = [_haversine_km(lat, lng, b[1], b[2]) for b in MILITARY_BASES]
    return round(min(distances), 1)


def enrich_event(conn, event_id: str, latitude: float,
                 longitude: float) -> dict:
    """
    Enrich a single event with geographic context.
    Results are cached in the event_enrichments table.
    """
    # Check cache first
    existing = conn.execute(
        "SELECT * FROM event_enrichments WHERE event_id = ?",
        (event_id,)).fetchone()
    if existing:
        return dict(existing)

    # Reverse geocode for country/region
    geo = reverse_geocode(conn, latitude, longitude)
    country_name = geo.get("country_name", "") or ""
    admin_region = geo.get("state", "") or geo.get("admin_region", "") or ""
    nearest_city = geo.get("city", "") or geo.get("nearest_city", "") or ""

    # Terrain classification
    terrain_type, pop_density = _classify_terrain(latitude, longitude)

    # Proximity calculations
    nearest_border_km = _nearest_border(latitude, longitude)
    nearest_military_km = _nearest_military(latitude, longitude)

    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT OR IGNORE INTO event_enrichments
           (id, event_id, nearest_city, admin_region, country_name,
            terrain_type, population_density,
            nearest_border_km, nearest_military_km)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, event_id, nearest_city, admin_region, country_name,
         terrain_type, pop_density, nearest_border_km, nearest_military_km),
    )
    conn.commit()

    return {
        "id": eid,
        "event_id": event_id,
        "nearest_city": nearest_city,
        "admin_region": admin_region,
        "country_name": country_name,
        "terrain_type": terrain_type,
        "population_density": pop_density,
        "nearest_border_km": nearest_border_km,
        "nearest_military_km": nearest_military_km,
    }


def batch_enrich(conn, limit: int = 100) -> int:
    """
    Enrich events that haven't been enriched yet.
    Runs as a batch job after ingestion.
    """
    rows = conn.execute(
        """SELECT e.id, e.latitude, e.longitude
           FROM events e
           LEFT JOIN event_enrichments ee ON e.id = ee.event_id
           WHERE ee.id IS NULL
             AND e.latitude IS NOT NULL
             AND e.longitude IS NOT NULL
           LIMIT ?""",
        (limit,)).fetchall()

    count = 0
    for row in rows:
        try:
            enrich_event(conn, row["id"], row["latitude"], row["longitude"])
            count += 1
        except Exception:
            pass

    return count


def get_enrichment(conn, event_id: str) -> dict | None:
    """Get enrichment data for a specific event."""
    row = conn.execute(
        "SELECT * FROM event_enrichments WHERE event_id = ?",
        (event_id,)).fetchone()
    return dict(row) if row else None


def get_enrichment_stats(conn) -> dict:
    """Get stats on enrichment coverage."""
    total_events = conn.execute(
        "SELECT COUNT(*) FROM events WHERE latitude IS NOT NULL").fetchone()[0]
    enriched = conn.execute(
        "SELECT COUNT(*) FROM event_enrichments").fetchone()[0]
    near_border = conn.execute(
        "SELECT COUNT(*) FROM event_enrichments WHERE nearest_border_km < 50").fetchone()[0]
    near_military = conn.execute(
        "SELECT COUNT(*) FROM event_enrichments WHERE nearest_military_km < 100").fetchone()[0]

    return {
        "total_events_with_coords": total_events,
        "enriched": enriched,
        "coverage_pct": round(enriched / max(total_events, 1) * 100, 1),
        "near_border_50km": near_border,
        "near_military_100km": near_military,
    }
