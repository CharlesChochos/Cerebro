"""
Geospatial layers API — maritime zones, elevation profiles, vegetation indices,
predictive positioning, data lineage, smart clustering, and density heatmaps.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from geo.elevation import (
    compute_elevation_profile, store_elevation_profile,
    get_elevation_profile, list_elevation_profiles,
)
from geo.maritime import (
    list_maritime_zones, get_maritime_zone, create_maritime_zone,
    find_zones_for_point, get_zones_geojson,
)
from detection.vegetation import (
    store_reading as store_veg_reading,
    get_readings as get_veg_readings,
    scan_vegetation_anomalies,
    get_vegetation_geojson,
)
from detection.predictive_positioning import (
    run_predictive_scan, list_predictions, get_predictions_geojson,
    detect_hotspots, detect_escalation_zones,
)
from intelligence.data_lineage import (
    record_lineage, get_lineage_chain, get_lineage_entry,
    list_lineage, get_lineage_stats, trace_sources,
)

router = APIRouter(prefix="/api", tags=["geo-layers"])


# ─── Maritime Zones ───────────────────────────────────────────

@router.get("/maritime/zones")
def get_maritime_zones(
    zone_type: str | None = None,
    risk_level: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """List maritime zones (chokepoints, shipping lanes, restricted areas)."""
    conn = get_db()
    zones = list_maritime_zones(conn, zone_type, risk_level, limit)
    return {"total": len(zones), "zones": zones}


@router.get("/maritime/zones/geojson")
def get_maritime_geojson(zone_type: str | None = None):
    """Get maritime zones as GeoJSON for map rendering."""
    conn = get_db()
    return get_zones_geojson(conn, zone_type)


@router.get("/maritime/zones/{zone_id}")
def get_zone(zone_id: str):
    """Get a specific maritime zone."""
    conn = get_db()
    zone = get_maritime_zone(conn, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


class MaritimeZoneRequest(BaseModel):
    name: str
    zone_type: str
    polygon: list[list[float]]
    description: str | None = None
    risk_level: str = "normal"
    country_code: str | None = None


@router.post("/maritime/zones")
def create_zone(req: MaritimeZoneRequest):
    """Create a new maritime zone."""
    if len(req.polygon) < 3:
        raise HTTPException(status_code=400, detail="Polygon needs >= 3 points")
    conn = get_db()
    zid = create_maritime_zone(
        conn, req.name, req.zone_type, req.polygon,
        req.description, req.risk_level, req.country_code,
    )
    return {"zone_id": zid}


@router.get("/maritime/lookup")
def lookup_point(lat: float, lng: float):
    """Find which maritime zones contain a given point."""
    conn = get_db()
    zones = find_zones_for_point(conn, lat, lng)
    return {"lat": lat, "lng": lng, "zones": zones}


# ─── Elevation Profiles ──────────────────────────────────────

class ElevationRequest(BaseModel):
    points: list[list[float]]  # [[lat, lng], ...]
    num_samples: int = 50
    name: str | None = None


@router.post("/elevation/profile")
def create_elevation_profile(req: ElevationRequest):
    """Compute elevation profile along a path."""
    if len(req.points) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 points")
    conn = get_db()
    profile = compute_elevation_profile(req.points, req.num_samples)
    if "error" in profile:
        raise HTTPException(status_code=400, detail=profile["error"])
    pid = store_elevation_profile(conn, profile, req.name)
    profile["profile_id"] = pid
    return profile


@router.get("/elevation/profiles")
def list_profiles(limit: int = Query(default=20, le=100)):
    """List stored elevation profiles."""
    conn = get_db()
    profiles = list_elevation_profiles(conn, limit)
    return {"total": len(profiles), "profiles": profiles}


@router.get("/elevation/profiles/{profile_id}")
def get_profile(profile_id: str):
    """Get a specific elevation profile with full point data."""
    conn = get_db()
    profile = get_elevation_profile(conn, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


# ─── Vegetation Indices ──────────────────────────────────────

class VegetationReadingRequest(BaseModel):
    lat: float
    lng: float
    ndvi: float
    baseline_ndvi: float = 0.3
    capture_date: str | None = None
    country_code: str | None = None
    region: str | None = None


@router.post("/vegetation/readings")
def add_vegetation_reading(req: VegetationReadingRequest):
    """Add a vegetation index reading."""
    conn = get_db()
    rid = store_veg_reading(
        conn, req.lat, req.lng, req.ndvi, req.baseline_ndvi,
        req.capture_date, req.country_code, req.region,
    )
    return {"reading_id": rid}


@router.get("/vegetation/readings")
def get_vegetation_readings(
    country_code: str | None = None,
    classification: str | None = None,
    days: int = Query(default=30, le=365),
    limit: int = Query(default=100, le=500),
):
    """List vegetation readings."""
    conn = get_db()
    readings = get_veg_readings(conn, country_code, classification, days, limit)
    return {"total": len(readings), "readings": readings}


@router.get("/vegetation/geojson")
def vegetation_geojson(country_code: str | None = None, days: int = 30):
    """Get vegetation readings as GeoJSON for map layer."""
    conn = get_db()
    return get_vegetation_geojson(conn, country_code, days)


@router.get("/vegetation/anomalies")
def vegetation_anomalies(threshold: float = -20.0, days: int = 30):
    """Scan for vegetation stress anomalies."""
    conn = get_db()
    anomalies = scan_vegetation_anomalies(conn, threshold, days)
    return {"total": len(anomalies), "anomalies": anomalies}


# ─── Predictive Positioning ──────────────────────────────────

@router.post("/predictive/scan")
def run_prediction_scan(
    category: str | None = None,
    country_code: str | None = None,
):
    """Run predictive positioning scan — detect hotspots and escalation zones."""
    conn = get_db()
    result = run_predictive_scan(conn, category, country_code)
    return result


@router.get("/predictive/positions")
def get_prediction_list(
    prediction_type: str | None = None,
    active_only: bool = True,
    limit: int = Query(default=20, le=100),
):
    """List predictive positions."""
    conn = get_db()
    predictions = list_predictions(conn, prediction_type, active_only, limit)
    return {"total": len(predictions), "predictions": predictions}


@router.get("/predictive/geojson")
def predictions_geojson(prediction_type: str | None = None):
    """Get predictions as GeoJSON for map layer."""
    conn = get_db()
    return get_predictions_geojson(conn, prediction_type)


@router.get("/predictive/hotspots")
def get_hotspots(
    category: str | None = None,
    country_code: str | None = None,
    days: int = Query(default=14, le=90),
):
    """Get current event hotspots."""
    conn = get_db()
    hotspots = detect_hotspots(conn, category, country_code, days)
    return {"total": len(hotspots), "hotspots": hotspots}


@router.get("/predictive/escalation-zones")
def get_escalation_zones(days: int = Query(default=14, le=90)):
    """Get detected escalation zones."""
    conn = get_db()
    zones = detect_escalation_zones(conn, days)
    return {"total": len(zones), "zones": zones}


# ─── Smart Clustering ────────────────────────────────────────

@router.get("/clusters/density")
def get_cluster_density(
    category: str | None = None,
    country_code: str | None = None,
    days: int = Query(default=7, le=90),
    grid_size: float = Query(default=2.0, ge=0.5, le=10.0),
):
    """Get event density grid for smart clustering visualization."""
    conn = get_db()
    from detection.predictive_positioning import compute_event_density
    from datetime import datetime, timezone, timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions = ["timestamp >= ?", "latitude IS NOT NULL"]
    params: list = [cutoff]

    if category:
        conditions.append("category = ?")
        params.append(category)
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = " AND ".join(conditions)
    events = conn.execute(
        f"SELECT id, latitude as lat, longitude as lng, severity, category FROM events WHERE {where}",
        params,
    ).fetchall()

    cells = compute_event_density([dict(e) for e in events], grid_size)
    return {"total_cells": len(cells), "grid_size_deg": grid_size, "cells": cells}


# ─── Event Density Heatmap Data ──────────────────────────────

@router.get("/heatmap/data")
def get_heatmap_data(
    category: str | None = None,
    days: int = Query(default=7, le=90),
    limit: int = Query(default=5000, le=10000),
):
    """Get event data optimized for heatmap rendering (lat, lng, severity)."""
    conn = get_db()
    from datetime import datetime, timezone, timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions = ["timestamp >= ?", "latitude IS NOT NULL"]
    params: list = [cutoff]

    if category:
        conditions.append("category = ?")
        params.append(category)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT latitude as lat, longitude as lng, severity, category FROM events WHERE {where} LIMIT ?",
        params + [limit],
    ).fetchall()

    points = [{"lat": r["lat"], "lng": r["lng"], "severity": r["severity"],
               "category": r["category"]} for r in rows]
    return {"total": len(points), "points": points}


# ─── Data Lineage / Audit Trail ──────────────────────────────

class LineageRequest(BaseModel):
    entity_type: str
    entity_id: str
    action: str
    actor: str
    details: dict | None = None
    source_ids: list[str] | None = None
    parent_lineage_id: str | None = None


@router.post("/lineage")
def create_lineage(req: LineageRequest):
    """Record a data lineage entry."""
    conn = get_db()
    lid = record_lineage(
        conn, req.entity_type, req.entity_id, req.action, req.actor,
        req.details, req.source_ids, req.parent_lineage_id,
    )
    return {"lineage_id": lid}


@router.get("/lineage")
def get_lineage_list(
    entity_type: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    hours: int = Query(default=24, le=720),
    limit: int = Query(default=50, le=200),
):
    """List recent lineage entries."""
    conn = get_db()
    entries = list_lineage(conn, entity_type, action, actor, hours, limit)
    return {"total": len(entries), "entries": entries}


@router.get("/lineage/stats")
def lineage_stats(hours: int = Query(default=24, le=720)):
    """Get lineage statistics for the audit dashboard."""
    conn = get_db()
    return get_lineage_stats(conn, hours)


@router.get("/lineage/entry/{lineage_id}")
def get_single_lineage(lineage_id: str):
    """Get a single lineage entry by ID."""
    conn = get_db()
    entry = get_lineage_entry(conn, lineage_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Lineage entry not found")
    return entry


@router.get("/lineage/trace/{entity_type}/{entity_id}")
def trace_entity_sources(entity_type: str, entity_id: str):
    """Trace the full source tree for a data item."""
    conn = get_db()
    tree = trace_sources(conn, entity_type, entity_id)
    return tree


@router.get("/lineage/{entity_type}/{entity_id}")
def get_entity_lineage(entity_type: str, entity_id: str):
    """Get the full lineage chain for a data item."""
    conn = get_db()
    chain = get_lineage_chain(conn, entity_type, entity_id)
    return {"entity_type": entity_type, "entity_id": entity_id,
            "total": len(chain), "chain": chain}
