"""
Ocean/maritime context layers — shipping lanes, EEZ, chokepoints, restricted zones.

Provides GeoJSON layers for maritime situational awareness on the globe.
Seeded zones come from the migration; this module handles CRUD and
spatial queries (which zones contain a given point).
"""
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

RISK_COLORS = {
    "normal": "#3b82f6",
    "elevated": "#eab308",
    "high": "#f97316",
    "critical": "#ef4444",
}

ZONE_TYPE_STYLES = {
    "chokepoint": {"fill_opacity": 0.15, "stroke_width": 2, "stroke_dash": None},
    "shipping_lane": {"fill_opacity": 0.08, "stroke_width": 1.5, "stroke_dash": [4, 4]},
    "restricted": {"fill_opacity": 0.12, "stroke_width": 2, "stroke_dash": [8, 4]},
    "eez": {"fill_opacity": 0.05, "stroke_width": 1, "stroke_dash": [2, 2]},
    "anchorage": {"fill_opacity": 0.2, "stroke_width": 1, "stroke_dash": None},
}


def list_maritime_zones(conn, zone_type: str | None = None,
                         risk_level: str | None = None,
                         limit: int = 50) -> list[dict]:
    """List maritime zones, optionally filtered."""
    query = "SELECT * FROM maritime_zones"
    conditions = []
    params = []

    if zone_type:
        conditions.append("zone_type = ?")
        params.append(zone_type)
    if risk_level:
        conditions.append("risk_level = ?")
        params.append(risk_level)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY risk_level DESC, name LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["polygon"] = json.loads(d["polygon_json"]) if d["polygon_json"] else []
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
        results.append(d)
    return results


def get_maritime_zone(conn, zone_id: str) -> dict | None:
    """Get a single maritime zone."""
    row = conn.execute(
        "SELECT * FROM maritime_zones WHERE id = ?", (zone_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["polygon"] = json.loads(d["polygon_json"]) if d["polygon_json"] else []
    d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
    return d


def create_maritime_zone(conn, name: str, zone_type: str,
                          polygon: list[list[float]],
                          description: str | None = None,
                          risk_level: str = "normal",
                          country_code: str | None = None) -> str:
    """Create a new maritime zone."""
    zid = str(uuid.uuid4())

    # Compute bounding box
    lngs = [p[0] for p in polygon]
    lats = [p[1] for p in polygon]
    bbox_west = min(lngs)
    bbox_south = min(lats)
    bbox_east = max(lngs)
    bbox_north = max(lats)

    conn.execute(
        """INSERT INTO maritime_zones
           (id, name, zone_type, polygon_json, bbox_west, bbox_south, bbox_east, bbox_north,
            description, risk_level, country_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            zid, name, zone_type, json.dumps(polygon),
            bbox_west, bbox_south, bbox_east, bbox_north,
            description, risk_level, country_code,
        ),
    )
    conn.commit()
    return zid


def point_in_polygon_simple(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test. Polygon is [[lng, lat], ...]."""
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


def find_zones_for_point(conn, lat: float, lng: float) -> list[dict]:
    """Find all maritime zones containing a given point."""
    # Pre-filter by bounding box
    rows = conn.execute(
        """SELECT * FROM maritime_zones
           WHERE bbox_west <= ? AND bbox_east >= ?
             AND bbox_south <= ? AND bbox_north >= ?""",
        (lng, lng, lat, lat),
    ).fetchall()

    matching = []
    for r in rows:
        polygon = json.loads(r["polygon_json"])
        if point_in_polygon_simple(lat, lng, polygon):
            d = dict(r)
            d["polygon"] = polygon
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
            matching.append(d)

    return matching


def get_zones_geojson(conn, zone_type: str | None = None) -> dict:
    """
    Get all maritime zones as a GeoJSON FeatureCollection for map rendering.
    """
    zones = list_maritime_zones(conn, zone_type, limit=100)

    features = []
    for z in zones:
        style = ZONE_TYPE_STYLES.get(z["zone_type"], ZONE_TYPE_STYLES["eez"])
        color = RISK_COLORS.get(z["risk_level"], "#3b82f6")

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [z["polygon"]],
            },
            "properties": {
                "id": z["id"],
                "name": z["name"],
                "zone_type": z["zone_type"],
                "risk_level": z["risk_level"],
                "description": z["description"],
                "color": color,
                "fill_opacity": style["fill_opacity"],
                "stroke_width": style["stroke_width"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }
