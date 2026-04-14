"""
Phase 14 API routes — satellite orbits, monitored location beacons,
country extrusions, and immersive/holographic feature data endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from detection.satellite_orbits import (
    seed_satellites, add_satellite, get_satellite, get_by_norad,
    list_satellites, predict_passes, get_orbit_geojson,
)
from detection.monitored_locations import (
    seed_locations, add_location, get_location, list_locations,
    update_alert_level, record_event, get_beacon_geojson,
)
from detection.country_extrusions import (
    seed_extrusions, upsert_metric, get_metric, list_metrics,
    get_extrusion_data, get_rankings, compute_normalized,
)

router = APIRouter(prefix="/api", tags=["phase14-immersive"])


# ─── Satellite Orbits ────────────────────────────────────────

class SatelliteRequest(BaseModel):
    norad_id: int
    name: str
    category: str = "unknown"
    country_code: str | None = None
    tle_line1: str | None = None
    tle_line2: str | None = None
    inclination: float | None = None
    period_min: float | None = None
    apogee_km: float | None = None
    perigee_km: float | None = None
    launch_date: str | None = None


@router.post("/satellites/seed")
def api_seed_satellites():
    conn = get_db()
    count = seed_satellites(conn)
    return {"seeded": count}


@router.post("/satellites")
def api_add_satellite(req: SatelliteRequest):
    conn = get_db()
    sid = add_satellite(conn, **req.model_dump())
    return {"satellite_id": sid}


@router.get("/satellites")
def api_list_satellites(
    category: str | None = None,
    country_code: str | None = None,
    status: str = "active",
    limit: int = Query(100, le=1000),
):
    conn = get_db()
    sats = list_satellites(conn, category=category,
                           country_code=country_code, status=status, limit=limit)
    return {"satellites": sats, "total": len(sats)}


@router.get("/satellites/orbits/geojson")
def api_orbit_geojson(category: str | None = None):
    conn = get_db()
    return get_orbit_geojson(conn, category=category)


@router.get("/satellites/passes")
def api_predict_passes(
    norad_id: int = Query(...),
    lat: float = Query(...),
    lng: float = Query(...),
    hours: int = Query(24, le=72),
):
    conn = get_db()
    passes = predict_passes(conn, norad_id, lat, lng, hours)
    return {"passes": passes, "total": len(passes)}


@router.get("/satellites/norad/{norad_id}")
def api_get_by_norad(norad_id: int):
    conn = get_db()
    sat = get_by_norad(conn, norad_id)
    if not sat:
        raise HTTPException(404, "Satellite not found")
    return sat


@router.get("/satellites/{satellite_id}")
def api_get_satellite(satellite_id: str):
    conn = get_db()
    sat = get_satellite(conn, satellite_id)
    if not sat:
        raise HTTPException(404, "Satellite not found")
    return sat


# ─── Monitored Locations / Pulse Beacons ─────────────────────

class LocationRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    location_type: str = "general"
    country_code: str | None = None
    alert_level: str = "normal"
    pulse_rate: float = 2.0
    radius_km: float = 50
    notes: str | None = None


class AlertLevelUpdate(BaseModel):
    alert_level: str
    pulse_rate: float | None = None


@router.post("/beacons/seed")
def api_seed_locations():
    conn = get_db()
    count = seed_locations(conn)
    return {"seeded": count}


@router.post("/beacons")
def api_add_location(req: LocationRequest):
    conn = get_db()
    try:
        lid = add_location(conn, **req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"location_id": lid}


@router.get("/beacons")
def api_list_locations(
    location_type: str | None = None,
    alert_level: str | None = None,
    country_code: str | None = None,
    limit: int = Query(100, le=500),
):
    conn = get_db()
    locs = list_locations(conn, location_type=location_type,
                          alert_level=alert_level, country_code=country_code,
                          limit=limit)
    return {"locations": locs, "total": len(locs)}


@router.get("/beacons/geojson")
def api_beacon_geojson(alert_level: str | None = None):
    conn = get_db()
    return get_beacon_geojson(conn, alert_level=alert_level)


@router.put("/beacons/{location_id}/alert")
def api_update_alert(location_id: str, req: AlertLevelUpdate):
    conn = get_db()
    loc = get_location(conn, location_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    try:
        update_alert_level(conn, location_id, req.alert_level, req.pulse_rate)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"updated": True}


@router.post("/beacons/{location_id}/event")
def api_record_event(location_id: str):
    conn = get_db()
    loc = get_location(conn, location_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    record_event(conn, location_id)
    return {"recorded": True}


@router.get("/beacons/{location_id}")
def api_get_location(location_id: str):
    conn = get_db()
    loc = get_location(conn, location_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    return loc


# ─── Country Extrusions ─────────────────────────────────────

class ExtrusionRequest(BaseModel):
    country_code: str
    metric_name: str
    metric_value: float
    normalized: float | None = None
    period: str = "current"


@router.post("/extrusions/seed")
def api_seed_extrusions():
    conn = get_db()
    count = seed_extrusions(conn)
    return {"seeded": count}


@router.post("/extrusions")
def api_upsert_metric(req: ExtrusionRequest):
    conn = get_db()
    try:
        eid = upsert_metric(conn, **req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"extrusion_id": eid}


@router.get("/extrusions")
def api_list_metrics(
    metric_name: str | None = None,
    country_code: str | None = None,
    period: str = "current",
    limit: int = Query(200, le=500),
):
    conn = get_db()
    metrics = list_metrics(conn, metric_name=metric_name,
                           country_code=country_code, period=period, limit=limit)
    return {"metrics": metrics, "total": len(metrics)}


@router.get("/extrusions/data/{metric_name}")
def api_extrusion_data(metric_name: str, period: str = "current"):
    conn = get_db()
    data = get_extrusion_data(conn, metric_name, period)
    return {"metric": metric_name, "data": data, "total": len(data)}


@router.get("/extrusions/rankings/{metric_name}")
def api_rankings(metric_name: str, period: str = "current",
                 top_n: int = Query(20, le=100)):
    conn = get_db()
    ranked = get_rankings(conn, metric_name, period, top_n)
    return {"metric": metric_name, "rankings": ranked, "total": len(ranked)}


@router.post("/extrusions/normalize/{metric_name}")
def api_normalize(metric_name: str, period: str = "current"):
    conn = get_db()
    count = compute_normalized(conn, metric_name, period)
    return {"normalized": count}


@router.get("/extrusions/{country_code}/{metric_name}")
def api_get_metric(country_code: str, metric_name: str,
                   period: str = "current"):
    conn = get_db()
    m = get_metric(conn, country_code, metric_name, period)
    if not m:
        raise HTTPException(404, "Metric not found")
    return m
