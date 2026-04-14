"""
Phase 13 API routes — webcam feeds, trade flow arcs, conflict frontlines,
map annotations/drawing, street-level imagery, animation export.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from detection.webcam_feeds import (
    seed_webcams, add_webcam, get_webcam, list_webcams,
    find_webcams_near, get_webcam_geojson,
)
from detection.trade_flows import (
    seed_trade_flows, add_trade_flow, get_trade_flow,
    list_trade_flows, get_trade_flow_arcs,
)
from detection.conflict_frontlines import (
    add_frontline, get_frontline, list_frontlines,
    get_frontline_animation, get_frontlines_geojson,
)
from detection.map_annotations import (
    create_annotation, get_annotation, list_annotations,
    update_annotation, delete_annotation,
    get_annotations_geojson, list_layers,
)
from detection.street_imagery import (
    store_image, get_image, list_images,
    find_images_near, get_imagery_geojson,
)
from detection.animation_export import (
    create_export_job, get_export_job, list_export_jobs,
    update_export_status,
)

router = APIRouter(prefix="/api", tags=["phase13-animations"])


# ─── Webcam Feeds ──────────────────────────────────────────

class WebcamRequest(BaseModel):
    title: str
    latitude: float
    longitude: float
    country_code: str | None = None
    category: str = "weather"
    stream_url: str | None = None
    thumbnail_url: str | None = None
    provider: str = "windy"


@router.post("/webcams/seed")
def post_seed_webcams():
    conn = get_db()
    count = seed_webcams(conn)
    return {"seeded": count}


@router.post("/webcams")
def post_webcam(req: WebcamRequest):
    conn = get_db()
    wid = add_webcam(conn, req.title, req.latitude, req.longitude,
                     req.country_code, req.category,
                     req.stream_url, req.thumbnail_url, req.provider)
    return {"webcam_id": wid}


@router.get("/webcams")
def get_webcams(category: str | None = None,
                country_code: str | None = None,
                limit: int = Query(default=100, le=500)):
    conn = get_db()
    items = list_webcams(conn, category, country_code, limit=limit)
    return {"total": len(items), "webcams": items}


@router.get("/webcams/geojson")
def get_webcams_geojson(category: str | None = None,
                        country_code: str | None = None):
    conn = get_db()
    return get_webcam_geojson(conn, category, country_code)


@router.get("/webcams/near")
def get_webcams_near(lat: float = Query(...), lng: float = Query(...),
                     radius: float = Query(default=2.0, le=10.0),
                     limit: int = Query(default=20, le=100)):
    conn = get_db()
    items = find_webcams_near(conn, lat, lng, radius, limit)
    return {"total": len(items), "webcams": items}


@router.get("/webcams/{webcam_id}")
def get_single_webcam(webcam_id: str):
    conn = get_db()
    item = get_webcam(conn, webcam_id)
    if not item:
        raise HTTPException(status_code=404, detail="Webcam not found")
    return item


# ─── Trade Flow Arcs ──────────────────────────────────────

class TradeFlowRequest(BaseModel):
    origin_country: str
    dest_country: str
    commodity: str | None = None
    volume_usd: float | None = None
    volume_tons: float | None = None
    flow_type: str = "trade"
    year: int | None = None
    origin_lat: float | None = None
    origin_lng: float | None = None
    dest_lat: float | None = None
    dest_lng: float | None = None
    risk_level: str = "normal"


@router.post("/trade-flows/seed")
def post_seed_trade_flows():
    conn = get_db()
    count = seed_trade_flows(conn)
    return {"seeded": count}


@router.post("/trade-flows")
def post_trade_flow(req: TradeFlowRequest):
    conn = get_db()
    tid = add_trade_flow(conn, req.origin_country, req.dest_country,
                         req.commodity, req.volume_usd, req.volume_tons,
                         req.flow_type, req.year,
                         req.origin_lat, req.origin_lng,
                         req.dest_lat, req.dest_lng, req.risk_level)
    return {"flow_id": tid}


@router.get("/trade-flows")
def get_trade_flows(origin_country: str | None = None,
                    dest_country: str | None = None,
                    flow_type: str | None = None,
                    commodity: str | None = None,
                    limit: int = Query(default=100, le=500)):
    conn = get_db()
    items = list_trade_flows(conn, origin_country, dest_country,
                             flow_type, commodity, limit)
    return {"total": len(items), "flows": items}


@router.get("/trade-flows/arcs")
def get_trade_arcs(flow_type: str | None = None,
                   min_volume: float | None = None,
                   limit: int = Query(default=200, le=500)):
    conn = get_db()
    return get_trade_flow_arcs(conn, flow_type, min_volume, limit)


@router.get("/trade-flows/{flow_id}")
def get_single_trade_flow(flow_id: str):
    conn = get_db()
    item = get_trade_flow(conn, flow_id)
    if not item:
        raise HTTPException(status_code=404, detail="Trade flow not found")
    return item


# ─── Conflict Frontlines ──────────────────────────────────

class FrontlineRequest(BaseModel):
    conflict_name: str
    date: str
    geometry_json: dict
    country_code: str | None = None
    side_a: str | None = None
    side_b: str | None = None
    status: str = "active"
    source: str | None = None


@router.post("/frontlines")
def post_frontline(req: FrontlineRequest):
    conn = get_db()
    fid = add_frontline(conn, req.conflict_name, req.date,
                        req.geometry_json, req.country_code,
                        req.side_a, req.side_b, req.status, req.source)
    return {"frontline_id": fid}


@router.get("/frontlines")
def get_frontlines_list(conflict_name: str | None = None,
                        country_code: str | None = None,
                        status: str | None = None,
                        limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_frontlines(conn, conflict_name, country_code, status, limit)
    return {"total": len(items), "frontlines": items}


@router.get("/frontlines/geojson")
def get_frontlines_geo(conflict_name: str | None = None,
                       date: str | None = None):
    conn = get_db()
    return get_frontlines_geojson(conn, conflict_name, date)


@router.get("/frontlines/animate/{conflict_name}")
def get_frontline_anim(conflict_name: str,
                       limit: int = Query(default=365, le=1000)):
    conn = get_db()
    return get_frontline_animation(conn, conflict_name, limit)


@router.get("/frontlines/{frontline_id}")
def get_single_frontline(frontline_id: str):
    conn = get_db()
    item = get_frontline(conn, frontline_id)
    if not item:
        raise HTTPException(status_code=404, detail="Frontline not found")
    return item


# ─── Map Annotations / Drawing ────────────────────────────

class AnnotationRequest(BaseModel):
    annotation_type: str = "marker"
    geometry_json: dict
    properties_json: dict | None = None
    title: str | None = None
    description: str | None = None
    created_by: str | None = None
    layer_name: str = "default"


class AnnotationUpdateRequest(BaseModel):
    geometry_json: dict | None = None
    properties_json: dict | None = None
    title: str | None = None
    description: str | None = None
    visible: bool | None = None


@router.post("/annotations")
def post_annotation(req: AnnotationRequest):
    conn = get_db()
    aid = create_annotation(conn, req.annotation_type, req.geometry_json,
                            req.properties_json, req.title, req.description,
                            req.created_by, req.layer_name)
    return {"annotation_id": aid}


@router.get("/annotations")
def get_annotations_list(layer_name: str | None = None,
                         annotation_type: str | None = None,
                         created_by: str | None = None,
                         limit: int = Query(default=200, le=500)):
    conn = get_db()
    items = list_annotations(conn, layer_name, annotation_type, created_by, limit)
    return {"total": len(items), "annotations": items}


@router.get("/annotations/geojson")
def get_annotations_geo(layer_name: str | None = None):
    conn = get_db()
    return get_annotations_geojson(conn, layer_name)


@router.get("/annotations/layers")
def get_annotation_layers():
    conn = get_db()
    layers = list_layers(conn)
    return {"total": len(layers), "layers": layers}


@router.get("/annotations/{annotation_id}")
def get_single_annotation(annotation_id: str):
    conn = get_db()
    item = get_annotation(conn, annotation_id)
    if not item:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return item


@router.put("/annotations/{annotation_id}")
def put_annotation(annotation_id: str, req: AnnotationUpdateRequest):
    conn = get_db()
    ok = update_annotation(conn, annotation_id, req.geometry_json,
                           req.properties_json, req.title,
                           req.description, req.visible)
    if not ok:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"updated": True}


@router.delete("/annotations/{annotation_id}")
def del_annotation(annotation_id: str):
    conn = get_db()
    ok = delete_annotation(conn, annotation_id)
    return {"deleted": ok}


# ─── Street-Level Imagery (Mapillary) ─────────────────────

class StreetImageRequest(BaseModel):
    image_id: str
    latitude: float
    longitude: float
    compass_angle: float | None = None
    captured_at: str | None = None
    sequence_id: str | None = None
    thumbnail_url: str | None = None
    full_url: str | None = None
    linked_event_id: str | None = None
    provider: str = "mapillary"


@router.post("/street-imagery")
def post_street_image(req: StreetImageRequest):
    conn = get_db()
    sid = store_image(conn, req.image_id, req.latitude, req.longitude,
                      req.compass_angle, req.captured_at, req.sequence_id,
                      req.thumbnail_url, req.full_url,
                      req.linked_event_id, req.provider)
    return {"record_id": sid}


@router.get("/street-imagery")
def get_street_images(linked_event_id: str | None = None,
                      provider: str | None = None,
                      limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_images(conn, linked_event_id, provider, limit)
    return {"total": len(items), "images": items}


@router.get("/street-imagery/geojson")
def get_street_imagery_geo(lat: float | None = None,
                           lng: float | None = None,
                           radius: float = Query(default=1.0, le=5.0),
                           limit: int = Query(default=200, le=500)):
    conn = get_db()
    return get_imagery_geojson(conn, lat, lng, radius, limit)


@router.get("/street-imagery/near")
def get_street_imagery_near(lat: float = Query(...),
                            lng: float = Query(...),
                            radius: float = Query(default=0.05, le=1.0),
                            limit: int = Query(default=20, le=100)):
    conn = get_db()
    items = find_images_near(conn, lat, lng, radius, limit)
    return {"total": len(items), "images": items}


@router.get("/street-imagery/{record_id}")
def get_single_street_image(record_id: str):
    conn = get_db()
    item = get_image(conn, record_id)
    if not item:
        raise HTTPException(status_code=404, detail="Image not found")
    return item


# ─── Animation Export ──────────────────────────────────────

class AnimExportRequest(BaseModel):
    export_type: str = "gif"
    parameters: dict | None = None
    duration_secs: float | None = None
    frame_count: int | None = None


class AnimExportStatusUpdate(BaseModel):
    status: str
    output_path: str | None = None
    file_size: int | None = None
    error_message: str | None = None


@router.post("/exports/animation")
def post_export_animation(req: AnimExportRequest):
    conn = get_db()
    eid = create_export_job(conn, req.export_type, req.parameters,
                            req.duration_secs, req.frame_count)
    return {"job_id": eid}


@router.get("/exports/animation")
def get_export_jobs(status: str | None = None,
                    limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_export_jobs(conn, status, limit)
    return {"total": len(items), "jobs": items}


@router.get("/exports/animation/{job_id}")
def get_single_export_job(job_id: str):
    conn = get_db()
    item = get_export_job(conn, job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Export job not found")
    return item


@router.put("/exports/animation/{job_id}")
def put_export_status(job_id: str, req: AnimExportStatusUpdate):
    conn = get_db()
    ok = update_export_status(conn, job_id, req.status,
                              req.output_path, req.file_size, req.error_message)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid status or job not found")
    return {"updated": True}
