"""
OpenSky Network REST API ingestion connector.

Fetches current aircraft positions from the OpenSky Network.
Free API — no authentication required for anonymous access (10-second updates).
Rate limit: ~100 requests/day for anonymous, 4000/day for registered.

API docs: https://openskynetwork.github.io/opensky-api/rest.html
"""
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

OPENSKY_BASE = "https://opensky-network.org/api"

# Military callsign prefixes (common patterns)
MILITARY_CALLSIGNS = {
    "RCH", "REACH",   # US Air Force (cargo)
    "RRR",             # US Air Force (tanker)
    "DUKE", "JAKE",    # US Navy
    "CNV",             # US Navy
    "CASA",            # Spanish Air Force
    "RAF", "ASCOT",    # Royal Air Force
    "GAF", "GERM",     # German Air Force
    "FAF", "COTAM",    # French Air Force
    "IAM",             # Italian Air Force
    "PLF",             # Polish Air Force
    "SUI",             # Swiss Air Force
    "RFR",             # Russian Air Force
    "CFC", "DRAGON",   # Canadian Forces
    "AUST",            # Australian Air Force
    "SPAR",            # US VIP transport
    "EXEC",            # US Executive transport
    "SAM",             # Special Air Mission (Air Force One support)
    "EVAC",            # Medical evacuation
    "NATO",            # NATO
}

# Cargo airline ICAO codes
CARGO_OPERATORS = {
    "FDX",  # FedEx
    "UPS",  # UPS
    "GTI",  # Atlas Air
    "CLX",  # Cargolux
    "ADB",  # Antonov Design Bureau
    "VDA",  # Volga-Dnepr
    "ABW",  # AirBridgeCargo
    "GEC",  # Lufthansa Cargo
    "SQC",  # Singapore Airlines Cargo
    "CAO",  # Air China Cargo
    "KAL",  # Korean Air Cargo (shares code)
    "ETD",  # Etihad Cargo
    "MPH",  # Martinair (KLM Cargo)
}


def classify_flight_type(callsign: str, origin_country: str = "") -> str:
    """Classify an aircraft as civilian, military, or cargo from callsign patterns."""
    cs = (callsign or "").strip().upper()

    if not cs:
        return "unknown"

    # Check military prefixes
    for prefix in MILITARY_CALLSIGNS:
        if cs.startswith(prefix):
            return "military"

    # Check cargo operators (first 3 chars = ICAO airline code)
    airline_code = cs[:3]
    if airline_code in CARGO_OPERATORS:
        return "cargo"

    return "civilian"


def fetch_flights(bbox: tuple | None = None) -> list[dict]:
    """
    Fetch current aircraft states from OpenSky Network.

    Args:
        bbox: Optional (south, north, west, east) bounding box.
              If None, fetches all states (may be rate limited).

    Returns:
        List of parsed flight dicts.
    """
    params = {}
    if bbox:
        south, north, west, east = bbox
        params = {
            "lamin": south,
            "lamax": north,
            "lomin": west,
            "lomax": east,
        }

    try:
        resp = httpx.get(
            f"{OPENSKY_BASE}/states/all",
            params=params if params else None,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("OpenSky HTTP error: %s", e)
        return []
    except Exception as e:
        logger.error("OpenSky fetch error: %s", e)
        return []

    states = data.get("states", [])
    if not states:
        return []

    flights = []
    for state in states:
        # OpenSky state vector format:
        # [0] icao24, [1] callsign, [2] origin_country, [3] time_position,
        # [4] last_contact, [5] longitude, [6] latitude, [7] baro_altitude,
        # [8] on_ground, [9] velocity, [10] true_track, [11] vertical_rate,
        # [12] sensors, [13] geo_altitude, [14] squawk, [15] spi, [16] position_source

        if len(state) < 12:
            continue

        icao24 = state[0]
        callsign = (state[1] or "").strip()
        origin_country = state[2] or ""
        lat = state[6]
        lng = state[5]

        # Skip entries without position
        if lat is None or lng is None:
            continue

        flight = {
            "icao24": icao24,
            "callsign": callsign if callsign else None,
            "origin_country": origin_country,
            "flight_type": classify_flight_type(callsign, origin_country),
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
            "altitude": state[7],       # barometric altitude (meters)
            "velocity": state[9],       # m/s
            "heading": state[10],       # true track (degrees)
            "vertical_rate": state[11],
            "on_ground": 1 if state[8] else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        flights.append(flight)

    logger.info("OpenSky: fetched %d flights", len(flights))
    return flights


def ingest(conn, bbox: tuple | None = None) -> dict:
    """
    Fetch and store current flight positions.

    Args:
        conn: SQLite database connection.
        bbox: Optional bounding box (south, north, west, east).
    """
    flights = fetch_flights(bbox=bbox)

    inserted = 0
    updated = 0

    for f in flights:
        existing = conn.execute(
            "SELECT icao24 FROM flights WHERE icao24 = ?", (f["icao24"],)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE flights SET
                   callsign = COALESCE(?, callsign),
                   origin_country = COALESCE(?, origin_country),
                   flight_type = ?,
                   latitude = ?, longitude = ?, altitude = ?,
                   velocity = ?, heading = ?, vertical_rate = ?,
                   on_ground = ?, last_seen = ?,
                   position_count = position_count + 1
                   WHERE icao24 = ?""",
                (
                    f["callsign"], f["origin_country"], f["flight_type"],
                    f["latitude"], f["longitude"], f["altitude"],
                    f["velocity"], f["heading"], f["vertical_rate"],
                    f["on_ground"], f["timestamp"],
                    f["icao24"],
                ),
            )
            updated += 1
        else:
            conn.execute(
                """INSERT INTO flights
                   (icao24, callsign, origin_country, flight_type,
                    latitude, longitude, altitude, velocity, heading,
                    vertical_rate, on_ground, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f["icao24"], f["callsign"], f["origin_country"], f["flight_type"],
                    f["latitude"], f["longitude"], f["altitude"],
                    f["velocity"], f["heading"], f["vertical_rate"],
                    f["on_ground"], f["timestamp"], f["timestamp"],
                ),
            )
            inserted += 1

    conn.commit()

    stats = {"fetched": len(flights), "inserted": inserted, "updated": updated}
    logger.info("OpenSky ingestion: %s", stats)
    return stats
