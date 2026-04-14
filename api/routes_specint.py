"""
SPECINT API routes — satellite imagery, fires, nightlights, disease outbreaks, weather.
"""
import json

from fastapi import APIRouter, HTTPException, Query

from api.main import get_db

router = APIRouter(prefix="/api", tags=["specint"])


# ── Satellite Imagery ───────────────────────────────────────────────────────


@router.get("/satellite")
def list_satellite_images(
    source: str | None = None,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lng: float | None = None,
    max_lng: float | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    """List cached satellite imagery with optional bbox and source filter."""
    conn = get_db()
    conditions = []
    params: list = []

    if source:
        conditions.append("source = ?")
        params.append(source)
    if min_lat is not None:
        conditions.append("lat >= ?")
        params.append(min_lat)
    if max_lat is not None:
        conditions.append("lat <= ?")
        params.append(max_lat)
    if min_lng is not None:
        conditions.append("lng >= ?")
        params.append(min_lng)
    if max_lng is not None:
        conditions.append("lng <= ?")
        params.append(max_lng)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT id, source, lat, lng, capture_date, cloud_cover,
                       thumbnail_url, resolution_m, annotations, created_at
                FROM satellite_cache {where}
                ORDER BY capture_date DESC LIMIT ?"""
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    images = []
    for r in rows:
        img = dict(r)
        if img.get("annotations") and isinstance(img["annotations"], str):
            try:
                img["annotations"] = json.loads(img["annotations"])
            except json.JSONDecodeError:
                pass
        images.append(img)

    return {"images": images}


# NOTE: /satellite/compare MUST come before /satellite/{image_id}
@router.get("/satellite/compare")
def compare_satellite_images(
    lat: float = Query(...),
    lng: float = Query(...),
    tolerance: float = Query(default=0.5),
    limit: int = Query(default=10, ge=2, le=20),
):
    """Get satellite images near a point for before/after comparison."""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, source, lat, lng, capture_date, cloud_cover,
                  thumbnail_url, resolution_m, annotations
           FROM satellite_cache
           WHERE lat BETWEEN ? AND ?
             AND lng BETWEEN ? AND ?
           ORDER BY capture_date DESC LIMIT ?""",
        (lat - tolerance, lat + tolerance, lng - tolerance, lng + tolerance, limit),
    ).fetchall()
    return {"images": [dict(r) for r in rows]}


@router.get("/satellite/{image_id}")
def get_satellite_image(image_id: str):
    """Get full satellite image metadata including annotations."""
    conn = get_db()
    row = conn.execute("SELECT * FROM satellite_cache WHERE id = ?", (image_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")
    result = dict(row)
    for field in ("annotations", "metadata", "bbox_json"):
        if result.get(field) and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except json.JSONDecodeError:
                pass
    return result


# ── Fire Detections ─────────────────────────────────────────────────────────


@router.get("/fires")
def list_fires(
    confidence: str | None = None,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lng: float | None = None,
    max_lng: float | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    """List active fire detections with optional bbox and confidence filter."""
    conn = get_db()
    conditions = []
    params: list = []

    if confidence:
        conditions.append("confidence = ?")
        params.append(confidence)
    if min_lat is not None:
        conditions.append("lat >= ?")
        params.append(min_lat)
    if max_lat is not None:
        conditions.append("lat <= ?")
        params.append(max_lat)
    if min_lng is not None:
        conditions.append("lng >= ?")
        params.append(min_lng)
    if max_lng is not None:
        conditions.append("lng <= ?")
        params.append(max_lng)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT id, lat, lng, brightness, frp, confidence, daynight,
                       capture_date, satellite
                FROM fire_detections {where}
                ORDER BY capture_date DESC LIMIT ?"""
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return {"fires": [dict(r) for r in rows], "count": len(rows)}


# ── Nightlight Readings ─────────────────────────────────────────────────────


@router.get("/nightlights")
def list_nightlights(
    min_change: float = Query(default=0, ge=0),
    country_code: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List nightlight readings, optionally filtered by change magnitude."""
    conn = get_db()
    conditions = ["ABS(change_pct) >= ?"]
    params: list = [min_change]

    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = " AND ".join(conditions)
    query = f"""SELECT id, lat, lng, country_code, region, radiance,
                       baseline_radiance, change_pct, capture_date
                FROM nightlight_readings
                WHERE {where}
                ORDER BY ABS(change_pct) DESC LIMIT ?"""
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return {"readings": [dict(r) for r in rows]}


# ── Disease Outbreaks ───────────────────────────────────────────────────────


@router.get("/outbreaks")
def list_outbreaks(
    disease: str | None = None,
    status: str | None = None,
    country_code: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    """List disease outbreaks with optional filters."""
    conn = get_db()
    conditions = []
    params: list = []

    if disease:
        conditions.append("disease LIKE ?")
        params.append(f"%{disease}%")
    if status:
        conditions.append("status = ?")
        params.append(status)
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT id, source, disease, title, summary, country_code, region,
                       case_count, death_count, status, severity, source_url, published_at
                FROM disease_outbreaks {where}
                ORDER BY published_at DESC LIMIT ?"""
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return {"outbreaks": [dict(r) for r in rows], "count": len(rows)}


# ── Weather Events ──────────────────────────────────────────────────────────


@router.get("/weather")
def list_weather_events(
    event_type: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    """List weather events/alerts."""
    conn = get_db()
    conditions = []
    params: list = []

    if event_type:
        conditions.append("event_type LIKE ?")
        params.append(f"%{event_type}%")
    if severity:
        conditions.append("severity = ?")
        params.append(severity)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT id, event_type, title, severity, urgency, lat, lng,
                       area_desc, effective, expires
                FROM weather_events {where}
                ORDER BY effective DESC LIMIT ?"""
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return {"weather_events": [dict(r) for r in rows], "count": len(rows)}
