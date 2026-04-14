"""
Entity Intelligence API routes — dossiers, link analysis, ACH, workspaces, sanctions.
Phase 9: God's Eye + Palantir-inspired entity analysis.
"""
import json
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db

router = APIRouter(prefix="/api", tags=["entity-intel"])


# ── Omnisearch ─────────────────────────────────────────────────────────────


@router.get("/entity-search")
def entity_omnisearch(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search across all data layers for entity intelligence."""
    from intelligence.dossier import omnisearch
    conn = get_db()
    return omnisearch(conn, q, limit=limit)


# ── Dossiers ───────────────────────────────────────────────────────────────


@router.get("/entities/{entity_id}/dossier")
def get_entity_dossier(entity_id: str):
    """Get or generate a comprehensive entity dossier."""
    from intelligence.dossier import generate_dossier
    conn = get_db()

    # Check for cached dossier first
    cached = conn.execute(
        """SELECT * FROM entity_dossiers
           WHERE entity_id = ? ORDER BY updated_at DESC LIMIT 1""",
        (entity_id,),
    ).fetchone()

    if cached:
        result = dict(cached)
        for field in ("key_facts", "timeline_events"):
            if result.get(field) and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        return result

    # Generate new dossier
    dossier = generate_dossier(conn, entity_id)
    if dossier.get("error") == "entity_not_found":
        raise HTTPException(status_code=404, detail="Entity not found")
    return dossier


@router.post("/entities/{entity_id}/dossier/refresh")
def refresh_entity_dossier(entity_id: str):
    """Force regeneration of an entity dossier."""
    from intelligence.dossier import generate_dossier
    conn = get_db()

    entity = conn.execute("SELECT id FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return generate_dossier(conn, entity_id)


# ── Link Analysis ──────────────────────────────────────────────────────────


@router.get("/entities/{entity_id}/graph")
def get_entity_graph(
    entity_id: str,
    depth: int = Query(default=2, ge=1, le=4),
    max_nodes: int = Query(default=50, ge=5, le=200),
):
    """Get link analysis graph centered on an entity."""
    from intelligence.dossier import get_link_graph
    conn = get_db()

    entity = conn.execute("SELECT id FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return get_link_graph(conn, entity_id, max_depth=depth, max_nodes=max_nodes)


@router.get("/entities/path/{source_id}/{target_id}")
def find_entity_path(
    source_id: str,
    target_id: str,
    max_depth: int = Query(default=5, ge=1, le=10),
):
    """Find shortest path between two entities in the knowledge graph."""
    from intelligence.dossier import find_shortest_path
    conn = get_db()

    for eid, label in [(source_id, "Source"), (target_id, "Target")]:
        if not conn.execute("SELECT id FROM entities WHERE id = ?", (eid,)).fetchone():
            raise HTTPException(status_code=404, detail=f"{label} entity not found")

    return find_shortest_path(conn, source_id, target_id, max_depth=max_depth)


# ── Tracked Entities ───────────────────────────────────────────────────────


@router.get("/tracked-entities")
def list_tracked_entities(
    priority: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List entities under active intelligence monitoring."""
    conn = get_db()
    conditions = []
    params: list = []

    if priority:
        conditions.append("te.priority = ?")
        params.append(priority)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT te.*, e.name, e.entity_type, e.event_count, e.aliases
            FROM tracked_entities te
            JOIN entities e ON e.id = te.entity_id
            {where}
            ORDER BY
                CASE te.priority
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 3
                END,
                e.event_count DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    tracked = []
    for r in rows:
        t = dict(r)
        for field in ("tags", "aliases"):
            if t.get(field) and isinstance(t[field], str):
                try:
                    t[field] = json.loads(t[field])
                except json.JSONDecodeError:
                    pass
        tracked.append(t)

    return {"tracked_entities": tracked}


class TrackEntityRequest(BaseModel):
    entity_id: str
    priority: str = "normal"
    notes: str | None = None
    tags: list[str] | None = None


@router.post("/tracked-entities")
def track_entity(req: TrackEntityRequest):
    """Add an entity to active tracking."""
    conn = get_db()

    entity = conn.execute("SELECT id FROM entities WHERE id = ?", (req.entity_id,)).fetchone()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Check if already tracked
    existing = conn.execute(
        "SELECT id FROM tracked_entities WHERE entity_id = ?", (req.entity_id,)
    ).fetchone()
    if existing:
        # Update priority
        conn.execute(
            """UPDATE tracked_entities SET priority = ?, notes = ?, tags = ?
               WHERE entity_id = ?""",
            (req.priority, req.notes, json.dumps(req.tags) if req.tags else None, req.entity_id),
        )
        conn.commit()
        return {"tracked_id": existing["id"], "updated": True}

    tracked_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO tracked_entities (id, entity_id, priority, notes, tags)
           VALUES (?, ?, ?, ?, ?)""",
        (tracked_id, req.entity_id, req.priority, req.notes,
         json.dumps(req.tags) if req.tags else None),
    )
    conn.commit()
    return {"tracked_id": tracked_id, "created": True}


@router.delete("/tracked-entities/{entity_id}")
def untrack_entity(entity_id: str):
    """Remove an entity from active tracking."""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM tracked_entities WHERE entity_id = ?", (entity_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entity not tracked")

    conn.execute("DELETE FROM tracked_entities WHERE entity_id = ?", (entity_id,))
    conn.commit()
    return {"removed": entity_id}


# ── ACH Frameworks ─────────────────────────────────────────────────────────


class ACHCreateRequest(BaseModel):
    title: str
    question: str
    hypotheses: list[str]
    evidence: list[str]
    workspace_id: str | None = None


@router.post("/ach")
def create_ach(req: ACHCreateRequest):
    """Create an ACH framework with auto-filled matrix."""
    from intelligence.ach import create_ach_framework
    conn = get_db()

    if len(req.hypotheses) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 hypotheses")
    if len(req.evidence) < 1:
        raise HTTPException(status_code=400, detail="Need at least 1 evidence item")

    return create_ach_framework(
        conn, req.title, req.question, req.hypotheses, req.evidence, req.workspace_id
    )


@router.get("/ach")
def list_ach_frameworks(
    limit: int = Query(default=20, ge=1, le=100),
):
    """List all ACH frameworks."""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, workspace_id, title, description, model_used, created_at, updated_at
           FROM ach_frameworks ORDER BY updated_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return {"frameworks": [dict(r) for r in rows]}


@router.get("/ach/{framework_id}")
def get_ach_framework(framework_id: str):
    """Get a specific ACH framework with full matrix."""
    from intelligence.ach import score_ach_matrix
    conn = get_db()

    row = conn.execute(
        "SELECT * FROM ach_frameworks WHERE id = ?", (framework_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="ACH framework not found")

    result = dict(row)
    for field in ("hypotheses", "evidence", "matrix"):
        if result.get(field) and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except json.JSONDecodeError:
                pass

    # Add scores
    if isinstance(result.get("matrix"), list) and isinstance(result.get("hypotheses"), list):
        result["scores"] = score_ach_matrix(result["matrix"], result["hypotheses"])

    return result


class ACHCellUpdate(BaseModel):
    evidence_idx: int
    hypothesis_idx: int
    value: str


@router.patch("/ach/{framework_id}/cell")
def update_ach_cell(framework_id: str, req: ACHCellUpdate):
    """Update a single cell in the ACH matrix (analyst override)."""
    from intelligence.ach import update_ach_cell as do_update
    conn = get_db()

    row = conn.execute(
        "SELECT id FROM ach_frameworks WHERE id = ?", (framework_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="ACH framework not found")

    result = do_update(conn, framework_id, req.evidence_idx, req.hypothesis_idx, req.value)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Workspaces ─────────────────────────────────────────────────────────────


class WorkspaceCreateRequest(BaseModel):
    title: str
    description: str | None = None
    workspace_type: str = "notebook"
    pinned_events: list[str] | None = None
    pinned_entities: list[str] | None = None


@router.post("/workspaces")
def create_workspace(req: WorkspaceCreateRequest):
    """Create an analysis workspace."""
    conn = get_db()
    ws_id = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO analysis_workspaces
           (id, title, description, workspace_type, content, pinned_events, pinned_entities)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            ws_id, req.title, req.description, req.workspace_type,
            json.dumps({"notes": []}),
            json.dumps(req.pinned_events or []),
            json.dumps(req.pinned_entities or []),
        ),
    )
    conn.commit()
    return {"workspace_id": ws_id, "title": req.title}


@router.get("/workspaces")
def list_workspaces(
    workspace_type: str | None = None,
    status: str = "active",
    limit: int = Query(default=30, ge=1, le=100),
):
    """List analysis workspaces."""
    conn = get_db()
    conditions = ["status = ?"]
    params: list = [status]

    if workspace_type:
        conditions.append("workspace_type = ?")
        params.append(workspace_type)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT id, title, description, workspace_type, status, created_at, updated_at
            FROM analysis_workspaces WHERE {where}
            ORDER BY updated_at DESC LIMIT ?""",
        params + [limit],
    ).fetchall()
    return {"workspaces": [dict(r) for r in rows]}


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: str):
    """Get workspace detail with full content."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM analysis_workspaces WHERE id = ?", (workspace_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    result = dict(row)
    for field in ("content", "pinned_events", "pinned_entities"):
        if result.get(field) and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except json.JSONDecodeError:
                pass

    # Get associated ACH frameworks
    frameworks = conn.execute(
        """SELECT id, title, model_used, created_at
           FROM ach_frameworks WHERE workspace_id = ?
           ORDER BY created_at DESC""",
        (workspace_id,),
    ).fetchall()
    result["ach_frameworks"] = [dict(f) for f in frameworks]

    return result


class WorkspaceNoteRequest(BaseModel):
    text: str


@router.post("/workspaces/{workspace_id}/notes")
def add_workspace_note(workspace_id: str, req: WorkspaceNoteRequest):
    """Add a note to a workspace."""
    conn = get_db()
    row = conn.execute(
        "SELECT content FROM analysis_workspaces WHERE id = ?", (workspace_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    content = json.loads(row["content"]) if row["content"] else {"notes": []}
    if "notes" not in content:
        content["notes"] = []

    content["notes"].append({
        "id": str(uuid.uuid4()),
        "text": req.text,
        "created_at": "now",
    })

    conn.execute(
        """UPDATE analysis_workspaces
           SET content = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
           WHERE id = ?""",
        (json.dumps(content), workspace_id),
    )
    conn.commit()
    return {"added": True, "note_count": len(content["notes"])}


# ── Sanctions ──────────────────────────────────────────────────────────────


@router.get("/sanctions/hits")
def list_sanctions_hits(
    entity_id: str | None = None,
    reviewed: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List sanctions evasion detections."""
    from detection.sanctions import get_sanctions_hits
    conn = get_db()
    hits = get_sanctions_hits(conn, entity_id=entity_id, reviewed=reviewed)
    return {"hits": hits[:limit], "total": len(hits)}


@router.post("/sanctions/scan")
def run_sanctions_scan():
    """Run a full sanctions evasion scan."""
    from detection.sanctions import run_sanctions_scan as do_scan
    conn = get_db()
    return do_scan(conn)


@router.get("/sanctions/watchlist")
def list_sanctions_watchlist(
    entity_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List sanctions watchlist entries."""
    conn = get_db()
    conditions = []
    params: list = []

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT * FROM sanctions_watchlist {where}
            ORDER BY added_at DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    entries = []
    for r in rows:
        e = dict(r)
        for field in ("aliases", "details"):
            if e.get(field) and isinstance(e[field], str):
                try:
                    e[field] = json.loads(e[field])
                except json.JSONDecodeError:
                    pass
        entries.append(e)

    return {"watchlist": entries}


@router.post("/sanctions/hits/{hit_id}/review")
def review_sanctions_hit(hit_id: str):
    """Mark a sanctions hit as reviewed."""
    conn = get_db()
    row = conn.execute("SELECT id FROM sanctions_hits WHERE id = ?", (hit_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sanctions hit not found")

    conn.execute("UPDATE sanctions_hits SET reviewed = 1 WHERE id = ?", (hit_id,))
    conn.commit()
    return {"reviewed": hit_id}
