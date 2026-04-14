"""
Geofencing engine — point-in-polygon detection for event monitoring.

Uses ray casting algorithm for pure-Python point-in-polygon test.
Pre-filters with bounding box checks for performance.
"""
import json
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


def point_in_polygon(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    """
    Ray casting algorithm for point-in-polygon test.

    polygon: list of [lng, lat] pairs (GeoJSON order).
    Returns True if point is inside the polygon.
    """
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]  # lng, lat
        xj, yj = polygon[j][0], polygon[j][1]

        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


def compute_bbox(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    """Compute bounding box (west, south, east, north) from polygon coordinates."""
    lngs = [p[0] for p in polygon]
    lats = [p[1] for p in polygon]
    return min(lngs), min(lats), max(lngs), max(lats)


def point_in_bbox(lat: float, lng: float, west: float, south: float, east: float, north: float) -> bool:
    """Fast bounding box check before expensive polygon test."""
    return south <= lat <= north and west <= lng <= east


def create_geofence(
    conn,
    name: str,
    polygon_coords: list[list[float]],
    description: str = "",
    category: str = "custom",
    alert_on_entry: bool = True,
    alert_severity_min: float = 0,
) -> dict:
    """
    Create a new geofence from polygon coordinates.
    polygon_coords: list of [lng, lat] pairs (GeoJSON order).
    """
    if len(polygon_coords) < 3:
        return {"error": "Polygon must have at least 3 points"}

    # Ensure polygon is closed
    if polygon_coords[0] != polygon_coords[-1]:
        polygon_coords.append(polygon_coords[0])

    # Build GeoJSON
    geojson = {
        "type": "Polygon",
        "coordinates": [polygon_coords],
    }

    # Compute bounding box
    west, south, east, north = compute_bbox(polygon_coords)

    fence_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO geofences
           (id, name, description, polygon_json, bbox_west, bbox_south, bbox_east, bbox_north,
            category, alert_on_entry, alert_severity_min)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fence_id, name, description, json.dumps(geojson),
         west, south, east, north, category,
         1 if alert_on_entry else 0, alert_severity_min),
    )
    conn.commit()

    return {
        "geofence_id": fence_id,
        "name": name,
        "bbox": {"west": west, "south": south, "east": east, "north": north},
    }


def check_event_in_geofences(conn, event_id: str, lat: float, lng: float, severity: float = 0) -> list[dict]:
    """
    Check if an event falls inside any active geofences.
    Returns list of triggered geofences.
    """
    if lat is None or lng is None:
        return []

    # Get active geofences, pre-filter with bbox
    fences = conn.execute(
        """SELECT id, name, polygon_json, bbox_west, bbox_south, bbox_east, bbox_north,
                  alert_on_entry, alert_severity_min
           FROM geofences
           WHERE active = 1
             AND bbox_west <= ? AND bbox_east >= ?
             AND bbox_south <= ? AND bbox_north >= ?""",
        (lng, lng, lat, lat),
    ).fetchall()

    triggered = []
    for fence in fences:
        f = dict(fence)

        # Skip if severity below threshold
        if severity < f["alert_severity_min"]:
            continue

        # Parse polygon and do precise check
        try:
            geojson = json.loads(f["polygon_json"])
            polygon = geojson["coordinates"][0]
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

        if point_in_polygon(lat, lng, polygon):
            # Record the event
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO geofence_events (id, geofence_id, event_id)
                       VALUES (?, ?, ?)""",
                    (str(uuid.uuid4()), f["id"], event_id),
                )
                conn.execute(
                    "UPDATE geofences SET event_count = event_count + 1 WHERE id = ?",
                    (f["id"],),
                )
            except Exception as e:
                logger.warning("Failed to record geofence event: %s", e)

            triggered.append({
                "geofence_id": f["id"],
                "geofence_name": f["name"],
                "alert_on_entry": bool(f["alert_on_entry"]),
            })

    if triggered:
        conn.commit()

    return triggered


def scan_events_against_geofences(conn, hours: int = 24) -> dict:
    """
    Scan recent events against all active geofences.
    Returns stats on how many events triggered fences.
    """
    events = conn.execute(
        """SELECT id, latitude, longitude, severity
           FROM events
           WHERE latitude IS NOT NULL AND longitude IS NOT NULL
             AND julianday('now') - julianday(timestamp) <= ?
             AND id NOT IN (SELECT event_id FROM geofence_events)""",
        (hours / 24.0,),
    ).fetchall()

    total_triggers = 0
    for event in events:
        e = dict(event)
        triggers = check_event_in_geofences(
            conn, e["id"], e["latitude"], e["longitude"], e.get("severity", 0)
        )
        total_triggers += len(triggers)

    return {"events_scanned": len(events), "triggers": total_triggers}


def get_events_in_geofence(conn, geofence_id: str, limit: int = 50) -> list[dict]:
    """Get all events that are inside a specific geofence."""
    rows = conn.execute(
        """SELECT e.id, e.source, e.title, e.category, e.severity, e.latitude, e.longitude,
                  e.timestamp, ge.entered_at
           FROM geofence_events ge
           JOIN events e ON e.id = ge.event_id
           WHERE ge.geofence_id = ?
           ORDER BY ge.entered_at DESC LIMIT ?""",
        (geofence_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
