"""
Geospatial Advanced API routes — geofences, measurements, weapons, KML, trajectories.
Phase 10: Advanced geospatial features.
"""
import json
import uuid

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from api.main import get_db

router = APIRouter(prefix="/api", tags=["geospatial"])


# ── Geofences ──────────────────────────────────────────────────────────────


class GeofenceCreateRequest(BaseModel):
    name: str
    polygon: list[list[float]]  # [[lng, lat], ...]
    description: str = ""
    category: str = "custom"
    alert_on_entry: bool = True
    alert_severity_min: float = 0


@router.post("/geofences")
def create_geofence(req: GeofenceCreateRequest):
    """Create a geofence monitoring polygon."""
    from detection.geofence import create_geofence as do_create
    conn = get_db()
    result = do_create(
        conn, req.name, req.polygon, req.description,
        req.category, req.alert_on_entry, req.alert_severity_min,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/geofences")
def list_geofences(active: bool = True, limit: int = Query(default=50, ge=1, le=200)):
    """List geofences."""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, name, description, category, active, event_count,
                  bbox_west, bbox_south, bbox_east, bbox_north,
                  alert_on_entry, alert_severity_min, created_at
           FROM geofences WHERE active = ?
           ORDER BY created_at DESC LIMIT ?""",
        (1 if active else 0, limit),
    ).fetchall()
    return {"geofences": [dict(r) for r in rows]}


@router.get("/geofences/{geofence_id}")
def get_geofence(geofence_id: str):
    """Get geofence detail with polygon and events."""
    from detection.geofence import get_events_in_geofence
    conn = get_db()
    row = conn.execute("SELECT * FROM geofences WHERE id = ?", (geofence_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Geofence not found")

    result = dict(row)
    if result.get("polygon_json"):
        try:
            result["polygon"] = json.loads(result["polygon_json"])
        except json.JSONDecodeError:
            pass
    result["events"] = get_events_in_geofence(conn, geofence_id, limit=30)
    return result


@router.delete("/geofences/{geofence_id}")
def delete_geofence(geofence_id: str):
    """Deactivate a geofence."""
    conn = get_db()
    row = conn.execute("SELECT id FROM geofences WHERE id = ?", (geofence_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Geofence not found")
    conn.execute("UPDATE geofences SET active = 0 WHERE id = ?", (geofence_id,))
    conn.commit()
    return {"deactivated": geofence_id}


@router.post("/geofences/scan")
def scan_geofences(hours: int = 24):
    """Scan recent events against all active geofences."""
    from detection.geofence import scan_events_against_geofences
    conn = get_db()
    return scan_events_against_geofences(conn, hours=hours)


# ── Measurements ───────────────────────────────────────────────────────────


class MeasureDistanceRequest(BaseModel):
    points: list[list[float]]  # [[lat, lng], ...]


@router.post("/measure/distance")
def measure_distance(req: MeasureDistanceRequest):
    """Calculate distance along a polyline in kilometers."""
    from geo.measure import polyline_distance, initial_bearing
    if len(req.points) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 points")

    total = polyline_distance(req.points)
    bearing = initial_bearing(
        req.points[0][0], req.points[0][1],
        req.points[-1][0], req.points[-1][1],
    )

    # Segment distances
    segments = []
    for i in range(len(req.points) - 1):
        from geo.measure import haversine_distance
        d = haversine_distance(
            req.points[i][0], req.points[i][1],
            req.points[i + 1][0], req.points[i + 1][1],
        )
        segments.append({"from": req.points[i], "to": req.points[i + 1], "distance_km": round(d, 3)})

    return {
        "total_distance_km": round(total, 3),
        "initial_bearing_deg": round(bearing, 1),
        "segments": segments,
        "point_count": len(req.points),
    }


class MeasureAreaRequest(BaseModel):
    polygon: list[list[float]]  # [[lat, lng], ...]


@router.post("/measure/area")
def measure_area(req: MeasureAreaRequest):
    """Calculate area of a polygon in square kilometers."""
    from geo.measure import polygon_area_km2, polyline_distance
    if len(req.polygon) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 points for area")

    area = polygon_area_km2(req.polygon)
    perimeter = polyline_distance(req.polygon + [req.polygon[0]])

    return {
        "area_km2": round(area, 3),
        "perimeter_km": round(perimeter, 3),
        "point_count": len(req.polygon),
    }


class SaveMeasurementRequest(BaseModel):
    name: str
    profile_type: str  # distance, area, elevation
    points: list[list[float]]


@router.post("/measurements")
def save_measurement(req: SaveMeasurementRequest):
    """Save a measurement profile."""
    from geo.measure import save_measurement as do_save
    conn = get_db()
    return do_save(conn, req.name, req.profile_type, req.points)


@router.get("/measurements")
def list_measurements(limit: int = Query(default=30, ge=1, le=100)):
    """List saved measurements."""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, name, profile_type, total_distance_km, total_area_km2, created_at
           FROM measurement_profiles ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return {"measurements": [dict(r) for r in rows]}


# ── Weapons Systems & Range Rings ──────────────────────────────────────────


@router.get("/weapons")
def list_weapons_systems(
    system_type: str | None = None,
    country_code: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List weapons systems."""
    conn = get_db()
    conditions: list[str] = []
    params: list = []

    if system_type:
        conditions.append("system_type = ?")
        params.append(system_type)
    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT * FROM weapons_systems {where}
            ORDER BY max_range_km DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    systems = []
    for r in rows:
        s = dict(r)
        if s.get("metadata") and isinstance(s["metadata"], str):
            try:
                s["metadata"] = json.loads(s["metadata"])
            except json.JSONDecodeError:
                pass
        systems.append(s)

    return {"weapons_systems": systems}


@router.get("/weapons/{system_id}/range-rings")
def get_range_rings(
    system_id: str,
    lat: float = Query(..., description="Center latitude"),
    lng: float = Query(..., description="Center longitude"),
):
    """Generate range ring GeoJSON for a weapons system at a given position."""
    from geo.measure import generate_range_rings
    conn = get_db()

    system = conn.execute(
        "SELECT * FROM weapons_systems WHERE id = ?", (system_id,)
    ).fetchone()
    if not system:
        raise HTTPException(status_code=404, detail="Weapons system not found")

    s = dict(system)
    ranges = [s["max_range_km"]]
    if s["min_range_km"] and s["min_range_km"] > 0:
        ranges.insert(0, s["min_range_km"])
    # Add 50% range ring
    ranges.insert(-1, s["max_range_km"] * 0.5)

    features = generate_range_rings(lat, lng, sorted(set(ranges)))

    return {
        "type": "FeatureCollection",
        "features": features,
        "system": {
            "name": s["name"],
            "type": s["system_type"],
            "max_range_km": s["max_range_km"],
        },
    }


# ── Deployments ────────────────────────────────────────────────────────────


class DeploymentCreateRequest(BaseModel):
    system_id: str
    lat: float
    lng: float
    name: str | None = None
    country_code: str | None = None
    confidence: float = 0.5
    source: str | None = None


@router.post("/deployments")
def create_deployment(req: DeploymentCreateRequest):
    """Record a weapons system deployment."""
    conn = get_db()

    system = conn.execute("SELECT id FROM weapons_systems WHERE id = ?", (req.system_id,)).fetchone()
    if not system:
        raise HTTPException(status_code=404, detail="Weapons system not found")

    dep_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO weapons_deployments
           (id, system_id, name, lat, lng, country_code, confidence, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (dep_id, req.system_id, req.name, req.lat, req.lng,
         req.country_code, req.confidence, req.source),
    )
    conn.commit()
    return {"deployment_id": dep_id}


@router.get("/deployments")
def list_deployments(
    system_id: str | None = None,
    status: str = "active",
    limit: int = Query(default=50, ge=1, le=200),
):
    """List weapons deployments with system info."""
    conn = get_db()
    conditions = ["wd.status = ?"]
    params: list = [status]

    if system_id:
        conditions.append("wd.system_id = ?")
        params.append(system_id)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT wd.*, ws.name as system_name, ws.system_type, ws.max_range_km
            FROM weapons_deployments wd
            JOIN weapons_systems ws ON ws.id = wd.system_id
            WHERE {where}
            ORDER BY wd.last_confirmed DESC LIMIT ?""",
        params + [limit],
    ).fetchall()
    return {"deployments": [dict(r) for r in rows]}


# ── Trajectories ───────────────────────────────────────────────────────────


class TrajectoryRequest(BaseModel):
    launch_lat: float
    launch_lng: float
    target_lat: float
    target_lng: float
    trajectory_type: str = "ballistic"  # ballistic or cruise
    max_altitude_km: float = 100
    num_points: int = 50


@router.post("/trajectory")
def compute_trajectory(req: TrajectoryRequest):
    """Compute a missile trajectory arc between two points."""
    from geo.measure import ballistic_trajectory_arc, cruise_missile_trajectory, haversine_distance

    distance = haversine_distance(req.launch_lat, req.launch_lng, req.target_lat, req.target_lng)

    if req.trajectory_type == "cruise":
        points = cruise_missile_trajectory(
            req.launch_lat, req.launch_lng,
            req.target_lat, req.target_lng,
            num_points=min(req.num_points, 200),
        )
    else:
        points = ballistic_trajectory_arc(
            req.launch_lat, req.launch_lng,
            req.target_lat, req.target_lng,
            max_altitude_km=req.max_altitude_km,
            num_points=min(req.num_points, 200),
        )

    return {
        "trajectory_type": req.trajectory_type,
        "distance_km": round(distance, 1),
        "max_altitude_km": req.max_altitude_km if req.trajectory_type == "ballistic" else 0.05,
        "points": points,
    }


# ── KML Export ─────────────────────────────────────────────────────────────


@router.get("/export/events.kml")
def export_events_kml(
    category: str | None = None,
    severity_min: float | None = None,
    hours: int | None = None,
):
    """Export events as KML file."""
    from geo.kml import export_events_kml as do_export
    conn = get_db()
    kml = do_export(conn, category=category, severity_min=severity_min, hours=hours)
    return Response(content=kml, media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": "attachment; filename=cerebro_events.kml"})


@router.get("/export/geofences.kml")
def export_geofences_kml():
    """Export geofences as KML file."""
    from geo.kml import export_geofences_kml as do_export
    conn = get_db()
    kml = do_export(conn)
    return Response(content=kml, media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": "attachment; filename=cerebro_geofences.kml"})


@router.get("/export/deployments.kml")
def export_deployments_kml():
    """Export weapons deployments as KML file."""
    from geo.kml import export_deployments_kml as do_export
    conn = get_db()
    kml = do_export(conn)
    return Response(content=kml, media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": "attachment; filename=cerebro_deployments.kml"})


@router.get("/export/events.kmz")
def export_events_kmz(
    category: str | None = None,
    severity_min: float | None = None,
    hours: int | None = None,
):
    """Export events as KMZ (zipped KML) file."""
    from geo.kml import export_events_kml as do_export, generate_kmz
    conn = get_db()
    kml = do_export(conn, category=category, severity_min=severity_min, hours=hours)
    kmz = generate_kmz(kml)
    return Response(content=kmz, media_type="application/vnd.google-earth.kmz",
                    headers={"Content-Disposition": "attachment; filename=cerebro_events.kmz"})
