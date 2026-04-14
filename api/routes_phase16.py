"""
API routes — Phase 16: Disease outbreaks, storm tracking,
conflict progression documentary mode.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.main import get_db

router = APIRouter()


# ─── Disease Outbreak endpoints ───────────────────────────

class OutbreakCreate(BaseModel):
    disease: str
    lat: float
    lng: float
    country_code: str = ""
    r_naught: float = 2.5
    mortality_rate: float = 0.01


@router.post("/api/disease-outbreaks")
def create_outbreak(body: OutbreakCreate):
    from detection.disease_tracking import create_outbreak as _create
    conn = get_db()
    result = _create(conn, body.disease, body.lat, body.lng,
                     body.country_code, body.r_naught, body.mortality_rate)
    return result


@router.get("/api/disease-outbreaks")
def list_outbreaks(status: str = "active"):
    from detection.disease_tracking import list_outbreaks as _list
    conn = get_db()
    items = _list(conn, status)
    return {"outbreaks": items, "total": len(items)}


@router.get("/api/disease-outbreaks/{outbreak_id}")
def get_outbreak(outbreak_id: str):
    from detection.disease_tracking import get_outbreak as _get
    conn = get_db()
    result = _get(conn, outbreak_id)
    if not result:
        raise HTTPException(status_code=404, detail="Outbreak not found")
    return result


@router.get("/api/disease-outbreaks/{outbreak_id}/spread")
def get_spread(outbreak_id: str, day: Optional[int] = None):
    from detection.disease_tracking import get_spread_geojson, get_outbreak
    conn = get_db()
    ob = get_outbreak(conn, outbreak_id)
    if not ob:
        raise HTTPException(status_code=404, detail="Outbreak not found")
    return get_spread_geojson(conn, outbreak_id, day)


@router.post("/api/disease-outbreaks/seed")
def seed_outbreaks():
    from detection.disease_tracking import seed_sample_outbreaks
    conn = get_db()
    count = seed_sample_outbreaks(conn)
    return {"seeded": count}


# ─── Storm Tracking endpoints ─────────────────────────────

class StormCreate(BaseModel):
    storm_name: str
    storm_type: str = "hurricane"
    category: int = 3
    max_wind_kts: int = 120


class TrackPointCreate(BaseModel):
    latitude: float
    longitude: float
    timestamp: str
    wind_kts: int = 100
    pressure_mb: int = 960
    is_forecast: int = 0
    uncertainty_radius_km: float = 50


@router.post("/api/storms")
def create_storm(body: StormCreate):
    from detection.storm_tracking import create_storm as _create
    conn = get_db()
    return _create(conn, body.storm_name, body.storm_type, body.category,
                   body.max_wind_kts)


@router.get("/api/storms")
def list_storms(status: str = "active"):
    from detection.storm_tracking import list_storms as _list
    conn = get_db()
    items = _list(conn, status)
    return {"storms": items, "total": len(items)}


@router.get("/api/storms/{storm_id}")
def get_storm(storm_id: str):
    from detection.storm_tracking import get_storm as _get
    conn = get_db()
    result = _get(conn, storm_id)
    if not result:
        raise HTTPException(status_code=404, detail="Storm not found")
    return result


@router.get("/api/storms/{storm_id}/track")
def get_storm_track(storm_id: str):
    from detection.storm_tracking import get_storm_track_geojson, get_storm
    conn = get_db()
    s = get_storm(conn, storm_id)
    if not s:
        raise HTTPException(status_code=404, detail="Storm not found")
    return get_storm_track_geojson(conn, storm_id)


@router.post("/api/storms/seed")
def seed_storms():
    from detection.storm_tracking import seed_sample_storms
    conn = get_db()
    count = seed_sample_storms(conn)
    return {"seeded": count}


# ─── Conflict Progression endpoints ──────────────────────

class ProgressionCreate(BaseModel):
    conflict_name: str
    region: str = ""
    start_date: str = ""


class StepCreate(BaseModel):
    step_number: int
    title: str
    narration: str
    center_lat: float
    center_lng: float
    zoom: float = 6
    bearing: float = 0
    pitch: float = 45
    event_date: str = ""
    markers: list = []
    lines: list = []


@router.post("/api/conflict-progressions")
def create_progression(body: ProgressionCreate):
    from detection.conflict_progression import create_progression as _create
    conn = get_db()
    return _create(conn, body.conflict_name, body.region, body.start_date)


@router.get("/api/conflict-progressions")
def list_progressions(status: str = "ongoing"):
    from detection.conflict_progression import list_progressions as _list
    conn = get_db()
    items = _list(conn, status)
    return {"progressions": items, "total": len(items)}


@router.get("/api/conflict-progressions/{prog_id}")
def get_progression(prog_id: str):
    from detection.conflict_progression import get_progression as _get
    conn = get_db()
    result = _get(conn, prog_id)
    if not result:
        raise HTTPException(status_code=404, detail="Progression not found")
    return result


@router.get("/api/conflict-progressions/{prog_id}/steps")
def get_steps(prog_id: str):
    from detection.conflict_progression import get_steps, get_progression
    conn = get_db()
    p = get_progression(conn, prog_id)
    if not p:
        raise HTTPException(status_code=404, detail="Progression not found")
    steps = get_steps(conn, prog_id)
    return {"progression": p, "steps": steps}


@router.get("/api/conflict-progressions/{prog_id}/steps/{step_num}/geojson")
def get_step_geojson(prog_id: str, step_num: int):
    from detection.conflict_progression import get_step_geojson as _get_geo
    conn = get_db()
    return _get_geo(conn, prog_id, step_num)


@router.post("/api/conflict-progressions/seed")
def seed_progressions():
    from detection.conflict_progression import seed_sample_progressions
    conn = get_db()
    count = seed_sample_progressions(conn)
    return {"seeded": count}


# ─── Radar/Sensor Coverage endpoints ─────────────────────

@router.get("/api/radar/coverage")
def get_radar_coverage(radar_type: Optional[str] = None):
    from detection.radar_coverage import get_radar_coverage_geojson
    return get_radar_coverage_geojson(radar_type)


@router.get("/api/radar/types")
def get_radar_types():
    from detection.radar_coverage import list_radar_types
    return {"types": list_radar_types()}


# ─── Drone/UAV Activity endpoints ────────────────────────

@router.get("/api/drones/activity")
def get_drone_activity(category: Optional[str] = None,
                       status: Optional[str] = None):
    from detection.drone_tracking import get_drone_activity_geojson
    return get_drone_activity_geojson(category, status)


@router.get("/api/drones/categories")
def get_drone_categories():
    from detection.drone_tracking import list_drone_categories
    return {"categories": list_drone_categories()}


@router.get("/api/drones/operators")
def get_drone_operators():
    from detection.drone_tracking import list_drone_operators
    return {"operators": list_drone_operators()}
