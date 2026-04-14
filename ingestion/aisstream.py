"""
AISstream.io WebSocket ingestion connector.

Connects to AISstream.io WebSocket for real-time AIS vessel positions.
Streams vessel position updates and stores them in vessels + vessel_tracks tables.

API docs: https://aisstream.io/documentation
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")
AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"

# AIS ship type codes → simplified categories
# Reference: https://coast.noaa.gov/data/marinecadastre/ais/VesselTypeCodes2018.pdf
VESSEL_TYPE_MAP = {
    range(20, 30): "wing_in_ground",
    range(30, 36): "fishing",
    range(36, 40): "special",
    range(40, 50): "high_speed",
    range(50, 60): "special",
    range(60, 70): "passenger",
    range(70, 80): "cargo",
    range(80, 90): "tanker",
    range(90, 100): "other",
}

# Military vessel indicators (name patterns, MMSI ranges)
MILITARY_MMSI_PREFIXES = {
    "338": "US Navy",
    "273": "Russian Navy",
    "412": "Chinese Navy",
    "235": "Royal Navy",
}

# Navigation status codes
NAV_STATUS = {
    0: "under_way_engine",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_maneuverability",
    4: "constrained_by_draught",
    5: "moored",
    6: "aground",
    7: "engaged_in_fishing",
    8: "under_way_sailing",
    15: "undefined",
}


def classify_vessel_type(ship_type_code: int, mmsi: str = "", name: str = "") -> str:
    """Classify vessel into simplified category from AIS ship type code."""
    # Check military indicators
    for prefix, _ in MILITARY_MMSI_PREFIXES.items():
        if mmsi.startswith(prefix):
            name_upper = (name or "").upper()
            if any(kw in name_upper for kw in ["NAVY", "USS ", "HMS ", "WARSHIP", "FRIGATE", "DESTROYER"]):
                return "military"

    for code_range, vessel_type in VESSEL_TYPE_MAP.items():
        if ship_type_code in code_range:
            return vessel_type

    return "other"


def parse_position_report(msg: dict) -> dict | None:
    """Parse an AISstream position report message into vessel data."""
    try:
        meta = msg.get("MetaData", {})
        position = msg.get("Message", {}).get("PositionReport", None)

        if not position and "StandardClassBPositionReport" in msg.get("Message", {}):
            position = msg["Message"]["StandardClassBPositionReport"]

        if not position:
            return None

        mmsi = str(meta.get("MMSI", ""))
        if not mmsi or len(mmsi) < 6:
            return None

        lat = position.get("Latitude", 0)
        lng = position.get("Longitude", 0)

        # Skip invalid coordinates
        if lat == 0 and lng == 0:
            return None
        if abs(lat) > 90 or abs(lng) > 180:
            return None

        ship_type = meta.get("ShipType", 0) or 0
        vessel_name = (meta.get("ShipName", "") or "").strip()

        return {
            "mmsi": mmsi,
            "name": vessel_name if vessel_name else None,
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
            "speed": position.get("Sog", None),
            "course": position.get("Cog", None),
            "heading": position.get("TrueHeading", None),
            "nav_status": NAV_STATUS.get(position.get("NavigationalStatus", 15), "undefined"),
            "vessel_type": classify_vessel_type(ship_type, mmsi, vessel_name),
            "timestamp": meta.get("time_utc", datetime.now(timezone.utc).isoformat()),
        }
    except Exception as e:
        logger.debug("Parse error: %s", e)
        return None


def parse_static_report(msg: dict) -> dict | None:
    """Parse ship static/voyage data (Class A) for vessel metadata."""
    try:
        meta = msg.get("MetaData", {})
        static = msg.get("Message", {}).get("ShipStaticData", None)
        if not static:
            return None

        mmsi = str(meta.get("MMSI", ""))
        if not mmsi:
            return None

        dim = static.get("Dimension", {})

        return {
            "mmsi": mmsi,
            "name": (static.get("Name", "") or "").strip() or None,
            "imo": str(static.get("ImoNumber", "")) if static.get("ImoNumber") else None,
            "callsign": (static.get("CallSign", "") or "").strip() or None,
            "destination": (static.get("Destination", "") or "").strip() or None,
            "length": (dim.get("A", 0) or 0) + (dim.get("B", 0) or 0) or None,
            "width": (dim.get("C", 0) or 0) + (dim.get("D", 0) or 0) or None,
            "draught": static.get("MaximumStaticDraught", None),
            "vessel_type": classify_vessel_type(
                static.get("Type", 0) or 0, mmsi, static.get("Name", "")
            ),
        }
    except Exception as e:
        logger.debug("Static parse error: %s", e)
        return None


def upsert_vessel(conn, data: dict):
    """Insert or update a vessel record."""
    existing = conn.execute("SELECT mmsi FROM vessels WHERE mmsi = ?", (data["mmsi"],)).fetchone()

    if existing:
        # Update position and metadata
        updates = []
        params = []
        for field in ("latitude", "longitude", "speed", "course", "heading",
                       "nav_status", "vessel_type"):
            if data.get(field) is not None:
                updates.append(f"{field} = ?")
                params.append(data[field])

        # Update optional static fields
        for field in ("name", "imo", "callsign", "destination", "length", "width", "draught"):
            if data.get(field) is not None:
                updates.append(f"{field} = ?")
                params.append(data[field])

        if updates:
            updates.append("last_seen = ?")
            params.append(data.get("timestamp", datetime.now(timezone.utc).isoformat()))
            updates.append("position_count = position_count + 1")
            updates.append("dark_since = NULL")  # Vessel is transmitting

            conn.execute(
                f"UPDATE vessels SET {', '.join(updates)} WHERE mmsi = ?",
                params + [data["mmsi"]],
            )
    else:
        ts = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        conn.execute(
            """INSERT INTO vessels
               (mmsi, name, imo, callsign, vessel_type, latitude, longitude,
                speed, course, heading, nav_status, destination, length, width, draught,
                first_seen, last_seen, position_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                data["mmsi"], data.get("name"), data.get("imo"), data.get("callsign"),
                data.get("vessel_type", "other"),
                data.get("latitude"), data.get("longitude"),
                data.get("speed"), data.get("course"), data.get("heading"),
                data.get("nav_status"), data.get("destination"),
                data.get("length"), data.get("width"), data.get("draught"),
                ts, ts,
            ),
        )


def store_track_point(conn, data: dict):
    """Store a vessel track position for trail visualization."""
    if data.get("latitude") is None or data.get("longitude") is None:
        return
    conn.execute(
        """INSERT INTO vessel_tracks
           (mmsi, latitude, longitude, speed, course, heading, timestamp, nav_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["mmsi"], data["latitude"], data["longitude"],
            data.get("speed"), data.get("course"), data.get("heading"),
            data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            data.get("nav_status"),
        ),
    )


async def stream_ais(conn, duration_seconds: int = 60, commit_every: int = 50) -> dict:
    """
    Connect to AISstream WebSocket and ingest vessel positions.

    Args:
        conn: SQLite database connection
        duration_seconds: How long to stream (0 = indefinite)
        commit_every: Commit to DB every N messages
    """
    try:
        import websockets
    except ImportError:
        logger.error("websockets package not installed. Run: pip install websockets")
        return {"error": "websockets not installed"}

    if not AISSTREAM_API_KEY:
        return {"error": "AISSTREAM_API_KEY not set"}

    stats = {
        "messages_received": 0,
        "vessels_updated": 0,
        "track_points": 0,
        "errors": 0,
        "duration_seconds": duration_seconds,
    }

    subscribe_msg = json.dumps({
        "APIKey": AISSTREAM_API_KEY,
        "BoundingBoxes": [
            [[-90, -180], [90, 180]],  # Global coverage
        ],
        "FiltersShipMMSI": [],
        "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport", "ShipStaticData"],
    })

    start_time = asyncio.get_event_loop().time()
    pending = 0

    try:
        async with websockets.connect(AISSTREAM_WS_URL) as ws:
            await ws.send(subscribe_msg)
            logger.info("Connected to AISstream WebSocket")

            async for raw_msg in ws:
                # Check duration
                if duration_seconds > 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= duration_seconds:
                        break

                try:
                    msg = json.loads(raw_msg)
                    msg_type = msg.get("MessageType", "")

                    if msg_type in ("PositionReport", "StandardClassBPositionReport"):
                        data = parse_position_report(msg)
                        if data:
                            upsert_vessel(conn, data)
                            store_track_point(conn, data)
                            stats["vessels_updated"] += 1
                            stats["track_points"] += 1
                            pending += 1

                    elif msg_type == "ShipStaticData":
                        data = parse_static_report(msg)
                        if data:
                            upsert_vessel(conn, data)
                            stats["vessels_updated"] += 1
                            pending += 1

                    stats["messages_received"] += 1

                    if pending >= commit_every:
                        conn.commit()
                        pending = 0

                except json.JSONDecodeError:
                    stats["errors"] += 1
                except Exception as e:
                    logger.debug("Message processing error: %s", e)
                    stats["errors"] += 1

        conn.commit()

    except Exception as e:
        logger.error("AISstream connection error: %s", e)
        stats["error"] = str(e)

    logger.info("AISstream ingestion: %s", stats)
    return stats


def ingest_sync(conn, duration_seconds: int = 60) -> dict:
    """Synchronous wrapper for the async AIS stream ingestion."""
    return asyncio.run(stream_ais(conn, duration_seconds=duration_seconds))
