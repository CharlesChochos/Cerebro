"""
Vessels and Flights API routes — maritime/aviation tracking.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.main import get_db

router = APIRouter(prefix="/api", tags=["tracking"])


# ─── Vessels ───


@router.get("/vessels")
def list_vessels(
    vessel_type: Optional[str] = Query(None, description="Filter by type"),
    flag: Optional[str] = Query(None, description="Filter by flag country"),
    dark_only: bool = Query(False, description="Only show dark vessels"),
    west: Optional[float] = Query(None, ge=-180, le=180),
    south: Optional[float] = Query(None, ge=-90, le=90),
    east: Optional[float] = Query(None, ge=-180, le=180),
    north: Optional[float] = Query(None, ge=-90, le=90),
    limit: int = Query(1000, ge=1, le=5000),
):
    """List current vessel positions with optional filters."""
    conn = get_db()
    conditions = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params: list = []

    if vessel_type:
        conditions.append("vessel_type = ?")
        params.append(vessel_type)
    if flag:
        conditions.append("flag = ?")
        params.append(flag.upper())
    if dark_only:
        conditions.append("dark_since IS NOT NULL")

    # Bounding box filter
    if all(v is not None for v in [west, south, east, north]):
        conditions.append(
            "MbrWithin(MakePoint(longitude, latitude, 4326), BuildMbr(?, ?, ?, ?, 4326))"
        )
        params.extend([west, south, east, north])

    where = " AND ".join(conditions)

    rows = conn.execute(
        f"""SELECT mmsi, name, imo, callsign, vessel_type, flag,
                   latitude, longitude, speed, course, heading,
                   nav_status, destination, length, width,
                   last_seen, first_seen, position_count, dark_since
            FROM vessels
            WHERE {where}
            ORDER BY last_seen DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    return {"total": len(rows), "vessels": [dict(r) for r in rows]}


# ─── Dark Vessel Events (MUST come before /vessels/{mmsi}) ───


@router.get("/vessels/dark")
def list_dark_events(
    resolved: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List AIS dark (gap) events."""
    conn = get_db()
    conditions: list[str] = []
    params: list = []

    if resolved is not None:
        conditions.append("resolved = ?")
        params.append(1 if resolved else 0)

    where = " AND ".join(conditions) if conditions else "1=1"

    rows = conn.execute(
        f"""SELECT * FROM ais_dark_events
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    return {"total": len(rows), "dark_events": [dict(r) for r in rows]}


# ─── Vessel Detail ───


@router.get("/vessels/{mmsi}")
def get_vessel(mmsi: str):
    """Get vessel detail by MMSI."""
    conn = get_db()
    row = conn.execute("SELECT * FROM vessels WHERE mmsi = ?", (mmsi,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Vessel not found")
    return dict(row)


@router.get("/vessels/{mmsi}/track")
def get_vessel_track(
    mmsi: str,
    limit: int = Query(500, ge=1, le=5000),
    hours: Optional[float] = Query(24, description="Track history in hours"),
):
    """Get historical track for a vessel (for trail visualization)."""
    conn = get_db()

    # Verify vessel exists
    vessel = conn.execute("SELECT mmsi, name FROM vessels WHERE mmsi = ?", (mmsi,)).fetchone()
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")

    conditions = ["mmsi = ?"]
    params: list = [mmsi]

    if hours:
        conditions.append(
            "julianday('now') - julianday(timestamp) <= ?"
        )
        params.append(hours / 24.0)

    where = " AND ".join(conditions)

    rows = conn.execute(
        f"""SELECT latitude, longitude, speed, course, heading, timestamp, nav_status
            FROM vessel_tracks
            WHERE {where}
            ORDER BY timestamp ASC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    return {
        "mmsi": mmsi,
        "name": vessel["name"],
        "points": [dict(r) for r in rows],
    }


# ─── Flights ───


@router.get("/flights")
def list_flights(
    flight_type: Optional[str] = Query(None, description="civilian, military, cargo"),
    origin_country: Optional[str] = Query(None),
    west: Optional[float] = Query(None, ge=-180, le=180),
    south: Optional[float] = Query(None, ge=-90, le=90),
    east: Optional[float] = Query(None, ge=-180, le=180),
    north: Optional[float] = Query(None, ge=-90, le=90),
    limit: int = Query(2000, ge=1, le=10000),
):
    """List current flight positions with optional filters."""
    conn = get_db()
    conditions = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params: list = []

    if flight_type:
        conditions.append("flight_type = ?")
        params.append(flight_type)
    if origin_country:
        conditions.append("origin_country = ?")
        params.append(origin_country)

    # Bounding box
    if all(v is not None for v in [west, south, east, north]):
        conditions.append(
            "MbrWithin(MakePoint(longitude, latitude, 4326), BuildMbr(?, ?, ?, ?, 4326))"
        )
        params.extend([west, south, east, north])

    where = " AND ".join(conditions)

    rows = conn.execute(
        f"""SELECT icao24, callsign, origin_country, flight_type,
                   latitude, longitude, altitude, velocity, heading,
                   vertical_rate, on_ground, last_seen, position_count
            FROM flights
            WHERE {where}
            ORDER BY last_seen DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    return {"total": len(rows), "flights": [dict(r) for r in rows]}
