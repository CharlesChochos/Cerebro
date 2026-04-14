"""
Phase 15 API routes — photo pins, EXIF extraction, event enrichment,
and enrichment statistics.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from detection.photo_pins import (
    add_photo_pin, get_photo_pin, list_photo_pins,
    get_photo_pin_geojson, find_mismatches,
)
from detection.exif_extraction import extract_exif, check_location_mismatch
from geo.enrichment import (
    enrich_event, batch_enrich, get_enrichment, get_enrichment_stats,
)

router = APIRouter(prefix="/api", tags=["phase15-enrichment"])


# ─── Photo Pins ──────────────────────────────────────────────

class PhotoPinRequest(BaseModel):
    source_url: str
    latitude: float
    longitude: float
    title: str | None = None
    caption: str | None = None
    event_id: str | None = None
    country_code: str | None = None
    image_url: str | None = None


@router.post("/photo-pins")
def api_add_photo_pin(req: PhotoPinRequest):
    conn = get_db()
    result = add_photo_pin(conn, **req.model_dump())
    return {"pin_id": result["id"], "exif_mismatch": result["exif_mismatch"],
            "mismatch_km": result["mismatch_km"]}


@router.get("/photo-pins")
def api_list_photo_pins(
    event_id: str | None = None,
    country_code: str | None = None,
    mismatch_only: bool = False,
    limit: int = Query(100, le=500),
):
    conn = get_db()
    pins = list_photo_pins(conn, event_id=event_id,
                           country_code=country_code,
                           mismatch_only=mismatch_only, limit=limit)
    return {"pins": pins, "total": len(pins)}


@router.get("/photo-pins/geojson")
def api_photo_pin_geojson(mismatch_only: bool = False):
    conn = get_db()
    return get_photo_pin_geojson(conn, mismatch_only=mismatch_only)


@router.get("/photo-pins/mismatches")
def api_find_mismatches(limit: int = Query(50, le=200)):
    conn = get_db()
    mismatches = find_mismatches(conn, limit=limit)
    return {"mismatches": mismatches, "total": len(mismatches)}


@router.get("/photo-pins/{pin_id}")
def api_get_photo_pin(pin_id: str):
    conn = get_db()
    pin = get_photo_pin(conn, pin_id)
    if not pin:
        raise HTTPException(404, "Photo pin not found")
    return pin


# ─── EXIF Extraction ────────────────────────────────────────

class ExifCheckRequest(BaseModel):
    claimed_lat: float
    claimed_lng: float
    exif_lat: float
    exif_lng: float
    threshold_km: float = 50.0


@router.post("/exif/check-mismatch")
def api_check_exif_mismatch(req: ExifCheckRequest):
    return check_location_mismatch(
        req.claimed_lat, req.claimed_lng,
        req.exif_lat, req.exif_lng,
        req.threshold_km)


# ─── Event Enrichment ───────────────────────────────────────

@router.post("/enrichment/enrich/{event_id}")
def api_enrich_event(event_id: str):
    conn = get_db()
    event = conn.execute(
        "SELECT id, latitude, longitude FROM events WHERE id = ?",
        (event_id,)).fetchone()
    if not event:
        raise HTTPException(404, "Event not found")
    if event["latitude"] is None or event["longitude"] is None:
        raise HTTPException(400, "Event has no coordinates")
    result = enrich_event(conn, event_id, event["latitude"], event["longitude"])
    return result


@router.post("/enrichment/batch")
def api_batch_enrich(limit: int = Query(100, le=1000)):
    conn = get_db()
    count = batch_enrich(conn, limit=limit)
    return {"enriched": count}


@router.get("/enrichment/stats")
def api_enrichment_stats():
    conn = get_db()
    return get_enrichment_stats(conn)


@router.get("/enrichment/{event_id}")
def api_get_enrichment(event_id: str):
    conn = get_db()
    enrichment = get_enrichment(conn, event_id)
    if not enrichment:
        raise HTTPException(404, "Enrichment not found")
    return enrichment
