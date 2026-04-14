"""
Domain tracking API — elections, nuclear proliferation, migration/refugees,
cyber incidents, custom tagging, EXIF extraction, reverse geocoding, PDF export.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from api.main import get_db
from detection.election_monitor import (
    create_election, get_election, list_elections, update_election,
)
from detection.nuclear_proliferation import (
    record_event as record_nuclear_event, get_event as get_nuclear_event,
    list_events as list_nuclear_events, update_status as update_nuclear_status,
    get_country_profile as get_nuclear_profile,
)
from detection.migration_tracking import (
    record_flow, get_flow, list_flows, update_flow, get_crisis_summary,
)
from detection.cyber_incidents import (
    record_incident, get_incident, list_incidents, update_incident,
    get_threat_landscape,
)
from intelligence.event_tagging import (
    add_tag, remove_tag, get_event_tags, find_events_by_tag,
    list_all_tags, bulk_tag,
)
from geo.exif_extraction import parse_exif_from_dict, store_exif, get_exif, list_exif, find_exif_near
from geo.reverse_geocoding import reverse_geocode, batch_reverse_geocode, get_geocode_stats
from intelligence.pdf_export import export_events_pdf, export_brief_pdf

router = APIRouter(prefix="/api", tags=["domain-tracking"])


# ─── Election Monitoring ────────────────────────────────────

class ElectionRequest(BaseModel):
    country_code: str
    election_type: str
    election_date: str | None = None
    candidates: list[str] | None = None
    risk_level: str = "normal"
    risk_factors: list[str] | None = None
    region: str | None = None
    analyst: str | None = None


class ElectionUpdateRequest(BaseModel):
    status: str | None = None
    irregularities: list[str] | None = None
    turnout_pct: float | None = None
    result_summary: str | None = None
    risk_level: str | None = None


@router.post("/elections")
def post_election(req: ElectionRequest):
    conn = get_db()
    eid = create_election(conn, req.country_code, req.election_type, req.election_date,
                          req.candidates, req.risk_level, req.risk_factors, req.region, req.analyst)
    return {"election_id": eid}


@router.get("/elections")
def get_elections(country_code: str | None = None, status: str | None = None,
                  limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_elections(conn, country_code, status, limit)
    return {"total": len(items), "elections": items}


@router.get("/elections/{election_id}")
def get_single_election(election_id: str):
    conn = get_db()
    item = get_election(conn, election_id)
    if not item:
        raise HTTPException(status_code=404, detail="Election not found")
    return item


@router.put("/elections/{election_id}")
def put_election(election_id: str, req: ElectionUpdateRequest):
    conn = get_db()
    ok = update_election(conn, election_id, req.status, req.irregularities,
                         req.turnout_pct, req.result_summary, req.risk_level)
    if not ok:
        raise HTTPException(status_code=404, detail="Election not found")
    return {"updated": True}


# ─── Nuclear Proliferation ──────────────────────────────────

class NuclearEventRequest(BaseModel):
    country_code: str
    event_type: str
    severity: float = 50
    facility_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    description: str | None = None
    evidence: list[str] | None = None
    source_type: str | None = None


@router.post("/nuclear")
def post_nuclear_event(req: NuclearEventRequest):
    conn = get_db()
    nid = record_nuclear_event(conn, req.country_code, req.event_type, req.severity,
                               req.facility_name, req.lat, req.lng, req.description,
                               req.evidence, req.source_type)
    return {"event_id": nid}


@router.get("/nuclear")
def get_nuclear_events(country_code: str | None = None, event_type: str | None = None,
                       status: str | None = None, days: int = Query(default=90, le=365),
                       limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_nuclear_events(conn, country_code, event_type, status, days, limit)
    return {"total": len(items), "events": items}


@router.get("/nuclear/profile/{country_code}")
def get_nuclear_country_profile(country_code: str, days: int = Query(default=365, le=3650)):
    conn = get_db()
    return get_nuclear_profile(conn, country_code, days)


@router.get("/nuclear/{event_id}")
def get_single_nuclear_event(event_id: str):
    conn = get_db()
    item = get_nuclear_event(conn, event_id)
    if not item:
        raise HTTPException(status_code=404, detail="Event not found")
    return item


@router.put("/nuclear/{event_id}/status")
def put_nuclear_status(event_id: str, status: str):
    conn = get_db()
    ok = update_nuclear_status(conn, event_id, status)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid status or event not found")
    return {"updated": True}


# ─── Migration / Refugee Tracking ───────────────────────────

class MigrationFlowRequest(BaseModel):
    origin_country: str
    flow_type: str = "refugee"
    dest_country: str | None = None
    transit_countries: list[str] | None = None
    estimated_count: int | None = None
    severity: float = 50
    route_description: str | None = None
    push_factors: list[str] | None = None
    pull_factors: list[str] | None = None


class MigrationUpdateRequest(BaseModel):
    status: str | None = None
    estimated_count: int | None = None
    severity: float | None = None


@router.post("/migration")
def post_migration_flow(req: MigrationFlowRequest):
    conn = get_db()
    fid = record_flow(conn, req.origin_country, req.flow_type, req.dest_country,
                      req.transit_countries, req.estimated_count, req.severity,
                      req.route_description, req.push_factors, req.pull_factors)
    return {"flow_id": fid}


@router.get("/migration")
def get_migration_flows(origin_country: str | None = None, dest_country: str | None = None,
                        flow_type: str | None = None, status: str | None = None,
                        limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_flows(conn, origin_country, dest_country, flow_type, status, limit)
    return {"total": len(items), "flows": items}


@router.get("/migration/crisis")
def get_migration_crisis_summary():
    conn = get_db()
    return get_crisis_summary(conn)


@router.get("/migration/{flow_id}")
def get_single_flow(flow_id: str):
    conn = get_db()
    item = get_flow(conn, flow_id)
    if not item:
        raise HTTPException(status_code=404, detail="Flow not found")
    return item


@router.put("/migration/{flow_id}")
def put_migration_flow(flow_id: str, req: MigrationUpdateRequest):
    conn = get_db()
    ok = update_flow(conn, flow_id, req.status, req.estimated_count, req.severity)
    if not ok:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"updated": True}


# ─── Cyber Incident Tracking ───────────────────────────────

class CyberIncidentRequest(BaseModel):
    incident_type: str
    severity: float = 50
    target_sector: str | None = None
    target_country: str | None = None
    target_org: str | None = None
    attributed_to: str | None = None
    attribution_confidence: str = "low"
    attack_vector: str | None = None
    iocs: dict | None = None
    impact: str | None = None


class CyberUpdateRequest(BaseModel):
    status: str | None = None
    attributed_to: str | None = None
    attribution_confidence: str | None = None


@router.post("/cyber")
def post_cyber_incident(req: CyberIncidentRequest):
    conn = get_db()
    cid = record_incident(conn, req.incident_type, req.severity, req.target_sector,
                          req.target_country, req.target_org, req.attributed_to,
                          req.attribution_confidence, req.attack_vector, req.iocs, req.impact)
    return {"incident_id": cid}


@router.get("/cyber")
def get_cyber_incidents(incident_type: str | None = None, target_country: str | None = None,
                        attributed_to: str | None = None, status: str | None = None,
                        days: int = Query(default=90, le=365),
                        limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_incidents(conn, incident_type, target_country, attributed_to, status, days, limit)
    return {"total": len(items), "incidents": items}


@router.get("/cyber/landscape")
def get_cyber_landscape(days: int = Query(default=30, le=365)):
    conn = get_db()
    return get_threat_landscape(conn, days)


@router.get("/cyber/{incident_id}")
def get_single_cyber_incident(incident_id: str):
    conn = get_db()
    item = get_incident(conn, incident_id)
    if not item:
        raise HTTPException(status_code=404, detail="Incident not found")
    return item


@router.put("/cyber/{incident_id}")
def put_cyber_incident(incident_id: str, req: CyberUpdateRequest):
    conn = get_db()
    ok = update_incident(conn, incident_id, req.status, req.attributed_to, req.attribution_confidence)
    if not ok:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"updated": True}


# ─── Custom Event Tagging ──────────────────────────────────

class TagRequest(BaseModel):
    event_id: str
    tag_name: str
    tag_category: str = "custom"
    color: str | None = None
    created_by: str | None = None


class BulkTagRequest(BaseModel):
    event_ids: list[str]
    tag_name: str
    tag_category: str = "custom"
    created_by: str | None = None


@router.post("/tags")
def post_tag(req: TagRequest):
    conn = get_db()
    tid = add_tag(conn, req.event_id, req.tag_name, req.tag_category, req.color, req.created_by)
    return {"tag_id": tid}


@router.post("/tags/bulk")
def post_bulk_tag(req: BulkTagRequest):
    conn = get_db()
    count = bulk_tag(conn, req.event_ids, req.tag_name, req.tag_category, req.created_by)
    return {"tagged": count}


@router.delete("/tags/{event_id}/{tag_name}")
def delete_tag(event_id: str, tag_name: str):
    conn = get_db()
    ok = remove_tag(conn, event_id, tag_name)
    return {"removed": ok}


@router.get("/tags")
def get_all_tags(limit: int = Query(default=100, le=500)):
    conn = get_db()
    items = list_all_tags(conn, limit)
    return {"total": len(items), "tags": items}


@router.get("/tags/events/{tag_name}")
def get_tagged_events(tag_name: str, limit: int = Query(default=100, le=500)):
    conn = get_db()
    items = find_events_by_tag(conn, tag_name, limit)
    return {"total": len(items), "tag": tag_name, "events": items}


@router.get("/tags/event/{event_id}")
def get_tags_for_event(event_id: str):
    conn = get_db()
    items = get_event_tags(conn, event_id)
    return {"total": len(items), "tags": items}


# ─── EXIF Extraction ───────────────────────────────────────

class ExifRequest(BaseModel):
    exif_data: dict
    source_url: str | None = None
    filename: str | None = None
    linked_event_id: str | None = None


@router.post("/exif")
def post_exif(req: ExifRequest):
    conn = get_db()
    parsed = parse_exif_from_dict(req.exif_data)
    eid = store_exif(conn, parsed, req.source_url, req.filename, req.linked_event_id)
    return {"exif_id": eid, "parsed": parsed}


@router.get("/exif")
def get_exif_list(linked_event_id: str | None = None, limit: int = Query(default=50, le=200)):
    conn = get_db()
    items = list_exif(conn, linked_event_id, limit)
    return {"total": len(items), "metadata": items}


@router.get("/exif/near")
def get_exif_near_point(lat: float = Query(...), lng: float = Query(...),
                        radius: float = Query(default=0.1, le=5.0),
                        limit: int = Query(default=20, le=100)):
    conn = get_db()
    items = find_exif_near(conn, lat, lng, radius, limit)
    return {"total": len(items), "metadata": items}


@router.get("/exif/{exif_id}")
def get_single_exif(exif_id: str):
    conn = get_db()
    item = get_exif(conn, exif_id)
    if not item:
        raise HTTPException(status_code=404, detail="EXIF record not found")
    return item


# ─── Reverse Geocoding ─────────────────────────────────────

class BatchGeocodeRequest(BaseModel):
    coordinates: list[list[float]]  # [[lat, lng], ...]


@router.get("/geocode/reverse")
def get_reverse_geocode(lat: float = Query(...), lng: float = Query(...)):
    conn = get_db()
    return reverse_geocode(conn, lat, lng)


@router.post("/geocode/batch")
def post_batch_geocode(req: BatchGeocodeRequest):
    conn = get_db()
    coords = [(c[0], c[1]) for c in req.coordinates if len(c) >= 2]
    results = batch_reverse_geocode(conn, coords)
    return {"total": len(results), "results": results}


@router.get("/geocode/stats")
def get_geocode_cache_stats():
    conn = get_db()
    return get_geocode_stats(conn)


# ─── PDF Export ─────────────────────────────────────────────

class PDFExportRequest(BaseModel):
    event_ids: list[str] | None = None
    category: str | None = None
    country_code: str | None = None
    limit: int = 50
    title: str = "Cerebro Intelligence Report"


@router.post("/export/pdf")
def post_export_pdf(req: PDFExportRequest):
    conn = get_db()
    pdf_bytes = export_events_pdf(conn, req.event_ids, req.category,
                                  req.country_code, req.limit, req.title)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cerebro_report.pdf"},
    )


@router.get("/export/pdf/brief/{brief_id}")
def get_export_brief_pdf(brief_id: str):
    conn = get_db()
    pdf_bytes = export_brief_pdf(conn, brief_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Brief not found")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=brief_{brief_id}.pdf"},
    )
