"""
Intelligence layer API routes — briefs, world state, fusion signals, red team.
"""
import json

from fastapi import APIRouter, HTTPException, Query

from api.main import get_db

router = APIRouter(prefix="/api", tags=["intelligence"])


# ── Briefs ──────────────────────────────────────────────────────────────────


@router.get("/briefs")
def list_briefs(
    brief_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List intelligence briefs, newest first."""
    conn = get_db()
    query = "SELECT id, brief_type, title, summary, grounding_score, model_used, token_count, created_at FROM briefs"
    params: list = []
    if brief_type:
        query += " WHERE brief_type = ?"
        params.append(brief_type)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    total_query = "SELECT COUNT(*) FROM briefs"
    if brief_type:
        total_query += " WHERE brief_type = ?"
        total = conn.execute(total_query, [brief_type]).fetchone()[0]
    else:
        total = conn.execute(total_query).fetchone()[0]

    return {
        "briefs": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/briefs/{brief_id}")
def get_brief(brief_id: str):
    """Get a full intelligence brief with its predictions and red team analysis."""
    conn = get_db()
    row = conn.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Brief not found")

    brief = dict(row)
    # Parse JSON fields
    for field in ("event_ids", "entity_ids", "metadata"):
        if brief.get(field) and isinstance(brief[field], str):
            try:
                brief[field] = json.loads(brief[field])
            except json.JSONDecodeError:
                pass

    # Attach predictions
    predictions = conn.execute(
        "SELECT * FROM predictions WHERE brief_id = ? ORDER BY confidence DESC",
        (brief_id,),
    ).fetchall()
    brief["predictions"] = [dict(p) for p in predictions]

    # Attach red team analysis if any
    red_team = conn.execute(
        "SELECT * FROM red_team_analyses WHERE target_type = 'brief' AND target_id = ?",
        (brief_id,),
    ).fetchall()
    brief["red_team"] = []
    for rt in red_team:
        rt_dict = dict(rt)
        for field in ("counterarguments", "alternative_hypotheses"):
            if rt_dict.get(field) and isinstance(rt_dict[field], str):
                try:
                    rt_dict[field] = json.loads(rt_dict[field])
                except json.JSONDecodeError:
                    pass
        brief["red_team"].append(rt_dict)

    return brief


# ── World State ─────────────────────────────────────────────────────────────


@router.get("/worldstate")
def get_world_state():
    """Get the most recent world state document."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM world_state ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if not row:
        return {"world_state": None, "message": "No world state generated yet"}
    return {"world_state": dict(row)}


@router.get("/worldstate/history")
def world_state_history(
    limit: int = Query(default=7, ge=1, le=30),
):
    """Get historical world state documents."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, date, token_count, events_summarized, model_used, created_at FROM world_state ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"history": [dict(r) for r in rows]}


@router.get("/worldstate/{state_id}")
def get_world_state_by_id(state_id: str):
    """Get a specific world state document by ID."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM world_state WHERE id = ?", (state_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="World state not found")
    return dict(row)


# ── Fusion Signals ──────────────────────────────────────────────────────────


@router.get("/fusion")
def list_fusion_signals(
    signal_type: str | None = None,
    min_severity: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List cross-domain fusion signals."""
    conn = get_db()
    conditions = ["severity >= ?"]
    params: list = [min_severity]

    if signal_type:
        conditions.append("signal_type = ?")
        params.append(signal_type)

    where = " AND ".join(conditions)
    query = f"SELECT * FROM fusion_signals WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()

    signals = []
    for r in rows:
        sig = dict(r)
        for field in ("event_ids", "entity_ids", "metadata"):
            if sig.get(field) and isinstance(sig[field], str):
                try:
                    sig[field] = json.loads(sig[field])
                except json.JSONDecodeError:
                    pass
        signals.append(sig)

    return {"signals": signals, "limit": limit, "offset": offset}


# ── Predictions ─────────────────────────────────────────────────────────────


@router.get("/predictions")
def list_predictions(
    outcome: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    """List predictions, optionally filtered by outcome."""
    conn = get_db()
    query = "SELECT * FROM predictions"
    params: list = []

    if outcome == "pending":
        query += " WHERE outcome IS NULL"
    elif outcome in ("correct", "incorrect"):
        query += " WHERE outcome = ?"
        params.append(outcome)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return {"predictions": [dict(r) for r in rows]}


# ── Red Team ────────────────────────────────────────────────────────────────


@router.get("/redteam/{target_type}/{target_id}")
def get_red_team(target_type: str, target_id: str):
    """Get red team analyses for a specific target."""
    conn = get_db()
    if target_type not in ("event", "brief", "fusion_signal"):
        raise HTTPException(status_code=400, detail="Invalid target_type")

    rows = conn.execute(
        "SELECT * FROM red_team_analyses WHERE target_type = ? AND target_id = ? ORDER BY created_at DESC",
        (target_type, target_id),
    ).fetchall()

    analyses = []
    for r in rows:
        a = dict(r)
        for field in ("counterarguments", "alternative_hypotheses"):
            if a.get(field) and isinstance(a[field], str):
                try:
                    a[field] = json.loads(a[field])
                except json.JSONDecodeError:
                    pass
        analyses.append(a)

    return {"analyses": analyses, "target_type": target_type, "target_id": target_id}
