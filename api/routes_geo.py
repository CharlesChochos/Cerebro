"""
Geo API routes — bounding box queries, saved views.
Uses SpatiaLite for spatial queries on events with lat/lng.
"""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.main import get_db

router = APIRouter(prefix="/api", tags=["geo"])


@router.get("/events/geo")
def get_events_geo(
    west: float = Query(..., ge=-180, le=180, description="West bound longitude"),
    south: float = Query(..., ge=-90, le=90, description="South bound latitude"),
    east: float = Query(..., ge=-180, le=180, description="East bound longitude"),
    north: float = Query(..., ge=-90, le=90, description="North bound latitude"),
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    severity_min: Optional[float] = Query(None, ge=0, le=100),
    time_start: Optional[str] = Query(None, description="ISO 8601 start time"),
    time_end: Optional[str] = Query(None, description="ISO 8601 end time"),
    limit: int = Query(2000, ge=1, le=5000),
):
    """
    Get events within a bounding box for map rendering.
    Uses SpatiaLite MbrWithin for efficient spatial filtering.
    Returns lightweight GeoJSON-like features for marker rendering.
    """
    conn = get_db()

    conditions = [
        "e.latitude IS NOT NULL",
        "e.longitude IS NOT NULL",
    ]
    params: list = []

    # SpatiaLite bounding box: MbrWithin(point, BuildMbr(west, south, east, north))
    conditions.append(
        "MbrWithin(MakePoint(e.longitude, e.latitude, 4326), BuildMbr(?, ?, ?, ?, 4326))"
    )
    params.extend([west, south, east, north])

    if category:
        conditions.append("e.category = ?")
        params.append(category)
    if source:
        conditions.append("e.source = ?")
        params.append(source)
    if severity_min is not None:
        conditions.append("e.severity >= ?")
        params.append(severity_min)
    if time_start:
        conditions.append("e.timestamp >= ?")
        params.append(time_start)
    if time_end:
        conditions.append("e.timestamp <= ?")
        params.append(time_end)

    where = " AND ".join(conditions)

    rows = conn.execute(
        f"""SELECT e.id, e.latitude, e.longitude, e.title, e.category,
                   e.severity, e.confidence, e.source, e.timestamp,
                   e.country_code
            FROM events e
            WHERE {where}
            ORDER BY e.severity DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    features = []
    for row in rows:
        features.append({
            "id": row["id"],
            "lat": row["latitude"],
            "lng": row["longitude"],
            "title": row["title"],
            "category": row["category"],
            "severity": row["severity"],
            "confidence": row["confidence"],
            "source": row["source"],
            "timestamp": row["timestamp"],
            "country_code": row["country_code"],
        })

    return {"total": len(features), "features": features}


# ─── Saved Views CRUD ───


@router.get("/views")
def list_views():
    """List all saved map views."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM saved_views ORDER BY updated_at DESC"
    ).fetchall()
    views = []
    for row in rows:
        v = dict(row)
        for field in ("layers", "filters"):
            if v.get(field):
                try:
                    v[field] = json.loads(v[field])
                except json.JSONDecodeError:
                    v[field] = None
        views.append(v)
    return {"views": views}


@router.post("/views")
def create_view(body: dict):
    """Save a new map view."""
    conn = get_db()
    view_id = str(uuid.uuid4())
    name = body.get("name", "Untitled View")
    conn.execute(
        """INSERT INTO saved_views
           (id, name, description, center_lat, center_lng, zoom, bearing, pitch, layers, filters)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            view_id,
            name,
            body.get("description", ""),
            body.get("center_lat", 0),
            body.get("center_lng", 0),
            body.get("zoom", 2.0),
            body.get("bearing", 0.0),
            body.get("pitch", 0.0),
            json.dumps(body.get("layers", [])),
            json.dumps(body.get("filters", {})),
        ),
    )
    conn.commit()
    return {"id": view_id, "name": name}


@router.get("/views/{view_id}")
def get_view(view_id: str):
    """Get a saved view by ID."""
    conn = get_db()
    row = conn.execute("SELECT * FROM saved_views WHERE id = ?", (view_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="View not found")
    v = dict(row)
    for field in ("layers", "filters"):
        if v.get(field):
            try:
                v[field] = json.loads(v[field])
            except json.JSONDecodeError:
                v[field] = None
    return v


@router.delete("/views/{view_id}")
def delete_view(view_id: str):
    """Delete a saved view."""
    conn = get_db()
    row = conn.execute("SELECT id FROM saved_views WHERE id = ?", (view_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="View not found")
    conn.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
    conn.commit()
    return {"deleted": view_id}
