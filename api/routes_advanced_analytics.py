"""
Advanced analytics API — historical analogs, cascade models,
narrative divergence, contrarian signals, narrative arcs.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from intelligence.historical_analogs import (
    run_analog_search, list_analog_matches, get_analog_match, HISTORICAL_ANALOGS,
)
from intelligence.cascade_model import (
    run_cascade_model, list_cascades, get_cascade, CASCADE_RULES,
)
from intelligence.narrative_divergence import (
    run_divergence_analysis, list_divergence_analyses, get_divergence_analysis,
)
from detection.contrarian_signals import (
    run_contrarian_scan, list_contrarian_signals, get_contrarian_signal,
)
from detection.narrative_arcs import (
    run_arc_tracker, list_narrative_arcs, get_narrative_arc,
)

router = APIRouter(prefix="/api", tags=["advanced-analytics"])


# ─── Historical Analogs ────────────────────────────────────────

class AnalogRequest(BaseModel):
    event_id: str | None = None
    region: str | None = None
    category: str | None = None
    top_n: int = 5


@router.post("/analogs/search")
def search_historical_analogs(req: AnalogRequest):
    """Search for historical analogs matching a current situation."""
    if not req.event_id and not req.region and not req.category:
        raise HTTPException(status_code=400, detail="Provide event_id, region, or category")
    conn = get_db()
    result = run_analog_search(conn, req.event_id, req.region, req.category, req.top_n)
    return result


@router.get("/analogs")
def list_analogs(
    category: str | None = None,
    limit: int = Query(default=20, le=100),
):
    """List stored historical analog matches."""
    conn = get_db()
    analogs = list_analog_matches(conn, category, limit)
    return {"total": len(analogs), "analogs": analogs}


@router.get("/analogs/catalog")
def get_analog_catalog():
    """Get the full catalog of known historical analogs."""
    return {"total": len(HISTORICAL_ANALOGS), "analogs": HISTORICAL_ANALOGS}


@router.get("/analogs/{analog_id}")
def get_analog(analog_id: str):
    """Get a specific stored analog match."""
    conn = get_db()
    analog = get_analog_match(conn, analog_id)
    if not analog:
        raise HTTPException(status_code=404, detail="Analog match not found")
    return analog


# ─── Second-Order Cascade Models ──────────────────────────────

class CascadeRequest(BaseModel):
    event_id: str | None = None
    trigger_description: str | None = None
    region: str | None = None
    category: str | None = None


@router.post("/cascades/model")
def create_cascade_model(req: CascadeRequest):
    """Model second-order cascade effects from a trigger event."""
    if not req.event_id and not req.trigger_description:
        raise HTTPException(status_code=400, detail="Provide event_id or trigger_description")
    conn = get_db()
    result = run_cascade_model(conn, req.event_id, req.trigger_description,
                                req.region, req.category)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/cascades")
def list_cascade_models(
    status: str | None = None,
    limit: int = Query(default=20, le=100),
):
    """List stored cascade models."""
    conn = get_db()
    cascades = list_cascades(conn, status, limit)
    return {"total": len(cascades), "cascades": cascades}


@router.get("/cascades/rules")
def get_cascade_rules():
    """Get all known cascade rules used for modeling."""
    return {"total": len(CASCADE_RULES), "rules": CASCADE_RULES}


@router.get("/cascades/{cascade_id}")
def get_cascade_model(cascade_id: str):
    """Get a specific cascade model."""
    conn = get_db()
    cascade = get_cascade(conn, cascade_id)
    if not cascade:
        raise HTTPException(status_code=404, detail="Cascade model not found")
    return cascade


# ─── Cross-Language Narrative Divergence ──────────────────────

class DivergenceRequest(BaseModel):
    topic: str
    region: str | None = None
    country_code: str | None = None
    days: int = 7


@router.post("/divergence/analyze")
def analyze_narrative_divergence(req: DivergenceRequest):
    """Analyze cross-source narrative divergence for a topic."""
    conn = get_db()
    result = run_divergence_analysis(conn, req.topic, req.region, req.country_code, req.days)
    return result


@router.get("/divergence")
def list_divergences(limit: int = Query(default=20, le=100)):
    """List stored narrative divergence analyses."""
    conn = get_db()
    analyses = list_divergence_analyses(conn, limit)
    return {"total": len(analyses), "analyses": analyses}


@router.get("/divergence/{analysis_id}")
def get_divergence(analysis_id: str):
    """Get a specific narrative divergence analysis."""
    conn = get_db()
    analysis = get_divergence_analysis(conn, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


# ─── Contrarian Signal Detector ───────────────────────────────

@router.post("/contrarian/scan")
def scan_contrarian(
    country_code: str | None = None,
    region: str | None = None,
):
    """Scan for contrarian signals that contradict dominant trends."""
    conn = get_db()
    result = run_contrarian_scan(conn, country_code, region)
    return result


@router.get("/contrarian")
def list_contrarians(
    signal_type: str | None = None,
    limit: int = Query(default=20, le=100),
):
    """List stored contrarian signals."""
    conn = get_db()
    signals = list_contrarian_signals(conn, signal_type, limit)
    return {"total": len(signals), "signals": signals}


@router.get("/contrarian/{signal_id}")
def get_contrarian(signal_id: str):
    """Get a specific contrarian signal."""
    conn = get_db()
    signal = get_contrarian_signal(conn, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Contrarian signal not found")
    return signal


# ─── Narrative Arc Tracker ────────────────────────────────────

class ArcRequest(BaseModel):
    topic: str
    region: str | None = None
    country_code: str | None = None


@router.post("/arcs/track")
def track_arc(req: ArcRequest):
    """Track a narrative arc — analyze its current phase and intensity."""
    conn = get_db()
    result = run_arc_tracker(conn, req.topic, req.region, req.country_code)
    return result


@router.get("/arcs")
def list_arcs(
    phase: str | None = None,
    limit: int = Query(default=20, le=100),
):
    """List tracked narrative arcs."""
    conn = get_db()
    arcs = list_narrative_arcs(conn, phase, limit)
    return {"total": len(arcs), "arcs": arcs}


@router.get("/arcs/{arc_id}")
def get_arc(arc_id: str):
    """Get a specific narrative arc."""
    conn = get_db()
    arc = get_narrative_arc(conn, arc_id)
    if not arc:
        raise HTTPException(status_code=404, detail="Narrative arc not found")
    return arc
