"""
AIS dark pattern detection — flags vessels that go dark.

Vessels that stop transmitting AIS are flagged as potential anomalies.
Higher severity is assigned when vessels go dark near:
- Known conflict zones
- Sanctioned waters
- Chokepoints (Strait of Hormuz, Malacca, Bab-el-Mandeb, etc.)

This is a key SIGINT indicator for sanctions evasion, smuggling, and military operations.
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Minimum hours silent before flagging as "dark"
DARK_THRESHOLD_HOURS = 4.0

# Sensitive regions — vessels going dark near these get higher severity
# Format: (name, south_lat, north_lat, west_lng, east_lng, severity_boost)
SENSITIVE_REGIONS = [
    ("Strait of Hormuz", 25.0, 27.5, 54.0, 57.5, 30),
    ("Strait of Malacca", -2.0, 6.0, 98.0, 105.0, 20),
    ("Bab-el-Mandeb", 11.5, 13.5, 42.5, 44.5, 30),
    ("Suez Canal", 29.5, 31.5, 32.0, 33.0, 25),
    ("South China Sea", 5.0, 22.0, 108.0, 121.0, 20),
    ("Black Sea", 40.5, 47.0, 27.5, 42.0, 25),
    ("Eastern Mediterranean", 32.0, 37.0, 29.0, 36.0, 20),
    ("Persian Gulf", 24.0, 30.0, 48.0, 56.5, 25),
    ("Gulf of Guinea", -2.0, 7.0, -5.0, 10.0, 25),
    ("Korean Peninsula", 33.0, 42.0, 124.0, 132.0, 20),
    ("Taiwan Strait", 22.0, 26.0, 117.0, 121.0, 25),
    ("Arctic Northeast Passage", 68.0, 80.0, 30.0, 180.0, 15),
]


def get_region_for_position(lat: float | None, lng: float | None) -> tuple[str | None, int]:
    """Check if a position falls within a sensitive region. Returns (region_name, severity_boost)."""
    if lat is None or lng is None:
        return None, 0

    for name, south, north, west, east, boost in SENSITIVE_REGIONS:
        if south <= lat <= north and west <= lng <= east:
            return name, boost

    return None, 0


def detect_dark_vessels(conn, threshold_hours: float = DARK_THRESHOLD_HOURS) -> dict:
    """
    Scan vessels table for those that have gone dark (no AIS update recently).

    Steps:
    1. Find vessels whose last_seen is older than threshold_hours
    2. Mark them with dark_since if not already marked
    3. Create ais_dark_events entries for new dark patterns
    4. Resolve dark events for vessels that reappeared
    """
    now = datetime.now(timezone.utc)
    stats = {
        "vessels_scanned": 0,
        "new_dark": 0,
        "still_dark": 0,
        "resolved": 0,
    }

    # Step 1: Find vessels that haven't transmitted recently
    dark_candidates = conn.execute(
        """SELECT mmsi, name, latitude, longitude, last_seen, dark_since
           FROM vessels
           WHERE julianday(?) - julianday(last_seen) > ?
           AND latitude IS NOT NULL AND longitude IS NOT NULL""",
        (now.isoformat(), threshold_hours / 24.0),
    ).fetchall()

    stats["vessels_scanned"] = len(dark_candidates)

    for row in dark_candidates:
        vessel = dict(row)
        mmsi = vessel["mmsi"]

        if vessel["dark_since"]:
            # Already marked dark — check if we need to update the dark event
            stats["still_dark"] += 1
            continue

        # New dark vessel — mark it
        conn.execute(
            "UPDATE vessels SET dark_since = ? WHERE mmsi = ?",
            (vessel["last_seen"], mmsi),
        )

        # Calculate dark duration
        last_seen_dt = datetime.fromisoformat(vessel["last_seen"].replace("Z", "+00:00"))
        dark_hours = (now - last_seen_dt).total_seconds() / 3600.0

        # Check sensitive region
        region, severity_boost = get_region_for_position(
            vessel["latitude"], vessel["longitude"]
        )

        # Base severity: 40 + boost for region + boost for duration
        severity = min(100, 40 + severity_boost + min(30, dark_hours * 2))

        # Create dark event
        conn.execute(
            """INSERT INTO ais_dark_events
               (id, mmsi, vessel_name, last_known_lat, last_known_lng,
                last_known_time, dark_duration_hours, region, severity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), mmsi, vessel["name"],
                vessel["latitude"], vessel["longitude"],
                vessel["last_seen"], round(dark_hours, 1),
                region, round(severity, 1),
            ),
        )
        stats["new_dark"] += 1

    # Step 2: Resolve dark events for vessels that reappeared
    reappeared = conn.execute(
        """SELECT de.id, de.mmsi, v.latitude, v.longitude, v.last_seen
           FROM ais_dark_events de
           JOIN vessels v ON v.mmsi = de.mmsi
           WHERE de.resolved = 0
           AND v.dark_since IS NULL""",
    ).fetchall()

    for row in reappeared:
        r = dict(row)
        conn.execute(
            """UPDATE ais_dark_events
               SET resolved = 1, resolved_at = ?, resolved_lat = ?, resolved_lng = ?
               WHERE id = ?""",
            (r["last_seen"], r["latitude"], r["longitude"], r["id"]),
        )
        stats["resolved"] += 1

    conn.commit()
    logger.info("AIS dark detection: %s", stats)
    return stats
