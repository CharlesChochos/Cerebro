"""
Advanced AI features API — multi-perspective, grounding firewall, leading indicators,
autonomous deep dive, satellite change detection.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from intelligence.perspectives import (
    run_multi_perspective,
    list_simulations,
    get_simulation,
)
from intelligence.grounding import (
    audit_text,
    sanitize_text,
    audit_brief,
    audit_fusion_signal,
    get_audit,
    list_audits,
)
from detection.leading_indicators import (
    run_indicator_scan,
    list_indicators,
    scan_indicators,
)
from intelligence.investigate import (
    investigate,
    get_investigation,
    list_investigations,
)
from detection.satellite_vision import (
    compare_images_vision,
    detect_changes_at_location,
    get_change_detection,
    list_change_detections,
)

router = APIRouter(prefix="/api", tags=["ai-features"])


# ─── Multi-Perspective Simulation ────────────────────────────

class PerspectiveRequest(BaseModel):
    event_id: str | None = None
    region: str | None = None
    actors: list[str] | None = None


@router.post("/perspectives")
def create_perspective_simulation(req: PerspectiveRequest):
    """Run a multi-perspective simulation on an event or region."""
    if not req.event_id and not req.region:
        raise HTTPException(status_code=400, detail="Provide event_id or region")
    conn = get_db()
    result = run_multi_perspective(conn, req.event_id, req.region, req.actors)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/perspectives")
def list_perspective_simulations(limit: int = Query(default=20, le=100)):
    """List multi-perspective simulations."""
    conn = get_db()
    sims = list_simulations(conn, limit)
    return {"total": len(sims), "simulations": sims}


@router.get("/perspectives/{sim_id}")
def get_perspective_simulation(sim_id: str):
    """Get a specific multi-perspective simulation."""
    conn = get_db()
    sim = get_simulation(conn, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim


# ─── Hallucination Firewall (Grounding) ──────────────────────

class GroundingAuditRequest(BaseModel):
    text: str
    target_type: str = "manual"
    target_id: str = ""


class SanitizeRequest(BaseModel):
    text: str


@router.post("/grounding/audit")
def run_grounding_audit(req: GroundingAuditRequest):
    """Audit a text for grounding — check all claims against evidence."""
    conn = get_db()
    result = audit_text(conn, req.text, req.target_type, req.target_id)
    return result


@router.post("/grounding/sanitize")
def run_sanitize(req: SanitizeRequest):
    """Sanitize text by flagging or removing ungrounded claims."""
    conn = get_db()
    result = sanitize_text(conn, req.text)
    return result


@router.post("/grounding/audit-brief/{brief_id}")
def run_brief_audit(brief_id: str):
    """Audit a specific brief for grounding."""
    conn = get_db()
    result = audit_brief(conn, brief_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/grounding/audit-fusion/{signal_id}")
def run_fusion_audit(signal_id: str):
    """Audit a specific fusion signal for grounding."""
    conn = get_db()
    result = audit_fusion_signal(conn, signal_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/grounding/audits")
def list_grounding_audits(
    target_type: str | None = None,
    limit: int = Query(default=20, le=100),
):
    """List grounding audits."""
    conn = get_db()
    audits = list_audits(conn, target_type, limit)
    return {"total": len(audits), "audits": audits}


@router.get("/grounding/audits/{audit_id}")
def get_grounding_audit(audit_id: str):
    """Get a specific grounding audit."""
    conn = get_db()
    audit = get_audit(conn, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


# ─── Leading Indicators ──────────────────────────────────────

@router.post("/indicators/scan")
def run_leading_indicator_scan(country_code: str | None = None):
    """Scan for leading indicator patterns, optionally filtered by country."""
    conn = get_db()
    result = run_indicator_scan(conn, country_code)
    return result


@router.get("/indicators")
def list_leading_indicators(
    status: str | None = None,
    limit: int = Query(default=20, le=100),
):
    """List detected leading indicators."""
    conn = get_db()
    indicators = list_indicators(conn, status, limit)
    return {"total": len(indicators), "indicators": indicators}


@router.get("/indicators/patterns")
def get_known_patterns():
    """List all known leading indicator patterns being monitored."""
    from detection.leading_indicators import KNOWN_PATTERNS
    return {"patterns": KNOWN_PATTERNS}


@router.get("/indicators/check")
def check_indicators_now(country_code: str | None = None):
    """Quick check: scan indicators without storing results."""
    conn = get_db()
    indicators = scan_indicators(conn, country_code)
    firing = [i for i in indicators if i["status"] == "firing"]
    return {
        "total_checked": len(indicators),
        "firing": len(firing),
        "firing_indicators": firing,
        "all_indicators": indicators,
    }


# ─── Autonomous Deep Dive Investigation ────────────────────────

class InvestigateRequest(BaseModel):
    trigger_type: str  # event, alert, vessel, fusion
    trigger_id: str


@router.post("/investigate")
def launch_investigation(req: InvestigateRequest):
    """Launch an autonomous deep-dive investigation into an anomaly."""
    valid_types = {"event", "alert", "vessel", "fusion"}
    if req.trigger_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"trigger_type must be one of: {', '.join(valid_types)}",
        )
    conn = get_db()
    result = investigate(conn, req.trigger_type, req.trigger_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/investigations")
def list_all_investigations(limit: int = Query(default=20, le=100)):
    """List recent autonomous investigations."""
    conn = get_db()
    items = list_investigations(conn, limit)
    return {"total": len(items), "investigations": items}


@router.get("/investigations/{investigation_id}")
def get_single_investigation(investigation_id: str):
    """Get full details of a specific investigation."""
    conn = get_db()
    inv = get_investigation(conn, investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv


# ─── Satellite Change Detection (Vision) ───────────────────────

class SatelliteCompareRequest(BaseModel):
    before_image_id: str
    after_image_id: str


class LocationDetectionRequest(BaseModel):
    lat: float
    lng: float
    radius_km: float = 50


@router.post("/vision/compare")
def compare_satellite_images(req: SatelliteCompareRequest):
    """Compare two satellite images for change detection using Claude Vision."""
    conn = get_db()
    result = compare_images_vision(conn, req.before_image_id, req.after_image_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/vision/detect-changes")
def detect_satellite_changes(req: LocationDetectionRequest):
    """Auto-detect satellite changes near a location."""
    conn = get_db()
    result = detect_changes_at_location(conn, req.lat, req.lng, req.radius_km)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/vision/detections")
def list_satellite_detections(limit: int = Query(default=20, le=100)):
    """List recent satellite change detections."""
    conn = get_db()
    items = list_change_detections(conn, limit)
    return {"total": len(items), "detections": items}


@router.get("/vision/detections/{detection_id}")
def get_satellite_detection(detection_id: str):
    """Get details of a specific satellite change detection."""
    conn = get_db()
    det = get_change_detection(conn, detection_id)
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")
    return det
