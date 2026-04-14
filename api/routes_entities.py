"""
Entities API routes — search, detail, relationships.
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.main import get_db

router = APIRouter(prefix="/api/entities", tags=["entities"])


@router.get("")
def list_entities(
    entity_type: Optional[str] = Query(None, description="Filter by type"),
    search: Optional[str] = Query(None, description="Search by name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("event_count", description="Sort: event_count, name, last_seen"),
):
    """List entities with filtering and search."""
    conn = get_db()
    conditions = []
    params = []

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if search:
        conditions.append("name LIKE ?")
        params.append(f"%{search}%")

    where = " AND ".join(conditions) if conditions else "1=1"

    allowed_sorts = {"event_count", "name", "last_seen", "first_seen"}
    if sort not in allowed_sorts:
        sort = "event_count"

    total = conn.execute(f"SELECT COUNT(*) FROM entities WHERE {where}", params).fetchone()[0]

    rows = conn.execute(
        f"""SELECT id, name, entity_type, aliases, metadata, first_seen, last_seen, event_count
            FROM entities WHERE {where}
            ORDER BY {sort} DESC
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    entities = []
    for row in rows:
        entity = dict(row)
        for field in ("aliases", "metadata"):
            if entity.get(field):
                try:
                    entity[field] = json.loads(entity[field])
                except json.JSONDecodeError:
                    entity[field] = None
        entities.append(entity)

    return {"total": total, "limit": limit, "offset": offset, "entities": entities}


@router.get("/{entity_id}")
def get_entity(entity_id: str):
    """Get entity detail with related events and connected entities."""
    conn = get_db()
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = dict(row)
    for field in ("aliases", "metadata"):
        if entity.get(field):
            try:
                entity[field] = json.loads(entity[field])
            except json.JSONDecodeError:
                entity[field] = None

    # Get connected entities via relations
    relations = conn.execute(
        """SELECT er.*, e.name, e.entity_type
           FROM entity_relations er
           JOIN entities e ON e.id = CASE
               WHEN er.source_entity_id = ? THEN er.target_entity_id
               ELSE er.source_entity_id
           END
           WHERE er.source_entity_id = ? OR er.target_entity_id = ?
           LIMIT 50""",
        (entity_id, entity_id, entity_id),
    ).fetchall()

    entity["relations"] = [dict(r) for r in relations]
    return entity
