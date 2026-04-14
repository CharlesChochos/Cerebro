"""
Intelligence tradecraft API — key assumptions check, I&W framework,
association matrix, threat assessment matrix, IC source ratings.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from intelligence.key_assumptions import (
    create_assumption, update_assumption_status, get_assumption,
    list_assumptions, evaluate_assumptions,
)
from intelligence.iw_framework import (
    create_framework, get_framework, list_frameworks,
    add_indicator, update_indicator_status, evaluate_framework,
)
from intelligence.association_matrix import (
    create_association, get_association, find_associations,
    list_associations, build_network_graph, get_matrix_stats,
)
from intelligence.threat_assessment import (
    create_assessment, get_assessment, list_assessments,
    update_assessment, get_threat_summary,
)
from intelligence.source_rating import (
    rate_source, get_rating, list_ratings, get_ratings_for_source,
    get_rating_stats,
)

router = APIRouter(prefix="/api", tags=["intel-tradecraft"])


# ─── Key Assumptions Check ──────────────────────────────────

class AssumptionRequest(BaseModel):
    assumption_text: str
    assessment_id: str | None = None
    confidence: str = "moderate"
    evidence_for: list[str] | None = None
    evidence_against: list[str] | None = None
    impact_if_wrong: str = "moderate"
    analyst: str | None = None
    notes: str | None = None


class AssumptionStatusUpdate(BaseModel):
    status: str
    evidence_for: list[str] | None = None
    evidence_against: list[str] | None = None
    confidence: str | None = None


@router.post("/assumptions")
def post_assumption(req: AssumptionRequest):
    """Record a key assumption."""
    conn = get_db()
    aid = create_assumption(
        conn, req.assumption_text, req.assessment_id, req.confidence,
        req.evidence_for, req.evidence_against, req.impact_if_wrong,
        req.analyst, req.notes,
    )
    return {"assumption_id": aid}


@router.get("/assumptions")
def get_assumptions(
    assessment_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """List key assumptions."""
    conn = get_db()
    items = list_assumptions(conn, assessment_id, status, limit)
    return {"total": len(items), "assumptions": items}


@router.get("/assumptions/evaluate/{assessment_id}")
def evaluate_assessment_assumptions(assessment_id: str):
    """Evaluate all assumptions for an assessment — identify weakest assumptions."""
    conn = get_db()
    return evaluate_assumptions(conn, assessment_id)


@router.get("/assumptions/{assumption_id}")
def get_single_assumption(assumption_id: str):
    """Get a single key assumption."""
    conn = get_db()
    item = get_assumption(conn, assumption_id)
    if not item:
        raise HTTPException(status_code=404, detail="Assumption not found")
    return item


@router.put("/assumptions/{assumption_id}")
def put_assumption_status(assumption_id: str, req: AssumptionStatusUpdate):
    """Update an assumption's status and evidence."""
    conn = get_db()
    ok = update_assumption_status(
        conn, assumption_id, req.status,
        req.evidence_for, req.evidence_against, req.confidence,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid status or assumption not found")
    return {"updated": True}


# ─── Indications & Warning Framework ────────────────────────

class IWFrameworkRequest(BaseModel):
    name: str
    threat_type: str | None = None
    description: str | None = None
    region: str | None = None
    country_code: str | None = None
    threshold_pct: float = 60.0


class IWIndicatorRequest(BaseModel):
    indicator_text: str
    category: str | None = None
    weight: float = 1.0


class IWIndicatorStatusUpdate(BaseModel):
    status: str
    evidence: dict | None = None


@router.post("/iw/frameworks")
def post_iw_framework(req: IWFrameworkRequest):
    """Create a new I&W framework."""
    conn = get_db()
    fid = create_framework(
        conn, req.name, req.threat_type, req.description,
        req.region, req.country_code, req.threshold_pct,
    )
    return {"framework_id": fid}


@router.get("/iw/frameworks")
def get_iw_frameworks(
    status: str | None = None,
    threat_type: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """List I&W frameworks."""
    conn = get_db()
    items = list_frameworks(conn, status, threat_type, limit)
    return {"total": len(items), "frameworks": items}


@router.get("/iw/frameworks/{framework_id}")
def get_iw_framework(framework_id: str):
    """Get a specific I&W framework with its indicators."""
    conn = get_db()
    item = get_framework(conn, framework_id)
    if not item:
        raise HTTPException(status_code=404, detail="Framework not found")
    return item


@router.get("/iw/frameworks/{framework_id}/evaluate")
def evaluate_iw_framework(framework_id: str):
    """Evaluate an I&W framework — compute warning level."""
    conn = get_db()
    result = evaluate_framework(conn, framework_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/iw/frameworks/{framework_id}/indicators")
def post_iw_indicator(framework_id: str, req: IWIndicatorRequest):
    """Add an indicator to an I&W framework."""
    conn = get_db()
    # Verify framework exists
    fw = get_framework(conn, framework_id)
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")
    iid = add_indicator(conn, framework_id, req.indicator_text, req.category, req.weight)
    return {"indicator_id": iid}


@router.put("/iw/indicators/{indicator_id}")
def put_iw_indicator_status(indicator_id: str, req: IWIndicatorStatusUpdate):
    """Update an indicator's observation status."""
    conn = get_db()
    ok = update_indicator_status(conn, indicator_id, req.status, req.evidence)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid status or indicator not found")
    return {"updated": True}


# ─── Association Matrix ─────────────────────────────────────

class AssociationRequest(BaseModel):
    entity_a_type: str
    entity_a_id: str
    entity_b_type: str
    entity_b_id: str
    relationship_type: str
    strength: float = 0.5
    confidence: str = "moderate"
    entity_a_label: str | None = None
    entity_b_label: str | None = None
    evidence: list[str] | None = None
    bidirectional: bool = True
    analyst: str | None = None


@router.post("/associations")
def post_association(req: AssociationRequest):
    """Create an association between two entities."""
    conn = get_db()
    aid = create_association(
        conn, req.entity_a_type, req.entity_a_id,
        req.entity_b_type, req.entity_b_id,
        req.relationship_type, req.strength, req.confidence,
        req.entity_a_label, req.entity_b_label,
        req.evidence, req.bidirectional, req.analyst,
    )
    return {"association_id": aid}


@router.get("/associations")
def get_associations(
    entity_type: str | None = None,
    entity_id: str | None = None,
    relationship_type: str | None = None,
    min_strength: float = 0.0,
    limit: int = Query(default=100, le=500),
):
    """List or search associations."""
    conn = get_db()
    if entity_type and entity_id:
        items = find_associations(conn, entity_type, entity_id, relationship_type, min_strength, limit)
    else:
        items = list_associations(conn, relationship_type, min_strength, limit)
    return {"total": len(items), "associations": items}


@router.get("/associations/stats")
def get_association_stats():
    """Get association matrix summary statistics."""
    conn = get_db()
    return get_matrix_stats(conn)


@router.get("/associations/network/{entity_type}/{entity_id}")
def get_association_network(entity_type: str, entity_id: str, depth: int = Query(default=2, le=4)):
    """Build a network graph from an entity, traversing associations."""
    conn = get_db()
    return build_network_graph(conn, entity_type, entity_id, depth)


@router.get("/associations/{association_id}")
def get_single_association(association_id: str):
    """Get a single association."""
    conn = get_db()
    item = get_association(conn, association_id)
    if not item:
        raise HTTPException(status_code=404, detail="Association not found")
    return item


# ─── Threat Assessment Matrix ───────────────────────────────

class ThreatAssessmentRequest(BaseModel):
    threat_name: str
    capability_score: float
    intent_score: float
    opportunity_score: float
    vulnerability_score: float = 50.0
    threat_type: str | None = None
    description: str | None = None
    region: str | None = None
    country_code: str | None = None
    timeframe: str = "near-term"
    analyst: str | None = None
    evidence: list[str] | None = None
    mitigations: list[str] | None = None


class ThreatUpdateRequest(BaseModel):
    capability_score: float | None = None
    intent_score: float | None = None
    opportunity_score: float | None = None
    vulnerability_score: float | None = None
    status: str | None = None


@router.post("/threats")
def post_threat(req: ThreatAssessmentRequest):
    """Create a new threat assessment."""
    conn = get_db()
    return create_assessment(
        conn, req.threat_name, req.capability_score, req.intent_score,
        req.opportunity_score, req.vulnerability_score, req.threat_type,
        req.description, req.region, req.country_code, req.timeframe,
        req.analyst, req.evidence, req.mitigations,
    )


@router.get("/threats")
def get_threats(
    threat_type: str | None = None,
    status: str | None = None,
    region: str | None = None,
    timeframe: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """List threat assessments."""
    conn = get_db()
    items = list_assessments(conn, threat_type, status, region, timeframe, limit)
    return {"total": len(items), "assessments": items}


@router.get("/threats/summary")
def get_threats_summary(region: str | None = None):
    """Get a summary of active threats."""
    conn = get_db()
    return get_threat_summary(conn, region)


@router.get("/threats/{assessment_id}")
def get_single_threat(assessment_id: str):
    """Get a single threat assessment."""
    conn = get_db()
    item = get_assessment(conn, assessment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return item


@router.put("/threats/{assessment_id}")
def put_threat(assessment_id: str, req: ThreatUpdateRequest):
    """Update threat dimension scores."""
    conn = get_db()
    result = update_assessment(
        conn, assessment_id, req.capability_score, req.intent_score,
        req.opportunity_score, req.vulnerability_score, req.status,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return result


# ─── IC Source Ratings ──────────────────────────────────────

class SourceRatingRequest(BaseModel):
    source_name: str
    reliability: str        # A-F
    information_quality: int  # 1-6
    source_type: str | None = None
    rating_basis: list[str] | None = None
    analyst: str | None = None
    notes: str | None = None


@router.post("/source-ratings")
def post_source_rating(req: SourceRatingRequest):
    """Rate an intelligence source using the IC A-F / 1-6 system."""
    conn = get_db()
    return rate_source(
        conn, req.source_name, req.reliability, req.information_quality,
        req.source_type, req.rating_basis, req.analyst, req.notes,
    )


@router.get("/source-ratings")
def get_source_ratings(
    source_type: str | None = None,
    min_composite: float | None = None,
    reliability: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """List source ratings."""
    conn = get_db()
    items = list_ratings(conn, source_type, min_composite, reliability, limit)
    return {"total": len(items), "ratings": items}


@router.get("/source-ratings/stats")
def source_rating_stats():
    """Get source rating summary statistics."""
    conn = get_db()
    return get_rating_stats(conn)


@router.get("/source-ratings/source/{source_name}")
def get_source_rating_history(source_name: str):
    """Get all ratings for a specific source (history)."""
    conn = get_db()
    items = get_ratings_for_source(conn, source_name)
    return {"source_name": source_name, "total": len(items), "ratings": items}


@router.get("/source-ratings/{rating_id}")
def get_single_source_rating(rating_id: str):
    """Get a single source rating."""
    conn = get_db()
    item = get_rating(conn, rating_id)
    if not item:
        raise HTTPException(status_code=404, detail="Rating not found")
    return item
