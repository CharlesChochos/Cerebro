"""
Events API routes — list, detail, and search.
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.main import get_db

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def list_events(
    category: Optional[str] = Query(None, description="Filter by category"),
    country: Optional[str] = Query(None, description="Filter by country code"),
    severity_min: Optional[float] = Query(None, ge=0, le=100),
    severity_max: Optional[float] = Query(None, ge=0, le=100),
    source: Optional[str] = Query(None, description="Filter by source"),
    search: Optional[str] = Query(None, description="Full-text search query"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("timestamp", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
):
    """List events with filtering, search, and pagination."""
    conn = get_db()
    conditions = []
    params = []

    if category:
        conditions.append("e.category = ?")
        params.append(category)
    if country:
        conditions.append("e.country_code = ?")
        params.append(country.upper())
    if severity_min is not None:
        conditions.append("e.severity >= ?")
        params.append(severity_min)
    if severity_max is not None:
        conditions.append("e.severity <= ?")
        params.append(severity_max)
    if source:
        conditions.append("e.source = ?")
        params.append(source)

    # Full-text search via FTS5
    if search:
        conditions.append("e.rowid IN (SELECT rowid FROM events_fts WHERE events_fts MATCH ?)")
        params.append(search)

    where = " AND ".join(conditions) if conditions else "1=1"

    # Validate sort field
    allowed_sorts = {"timestamp", "severity", "confidence", "ingested_at", "category"}
    if sort not in allowed_sorts:
        sort = "timestamp"
    order_dir = "ASC" if order.lower() == "asc" else "DESC"

    # Get total count
    count_row = conn.execute(
        f"SELECT COUNT(*) FROM events e WHERE {where}", params
    ).fetchone()
    total = count_row[0]

    # Get page of results
    query = f"""
        SELECT e.id, e.source, e.source_id, e.timestamp, e.ingested_at,
               e.category, e.severity, e.confidence, e.title, e.summary,
               e.latitude, e.longitude, e.country_code, e.region,
               e.entities_json, e.source_url
        FROM events e
        WHERE {where}
        ORDER BY e.{sort} {order_dir}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()

    events = []
    for row in rows:
        event = dict(row)
        # Parse entities_json if present
        if event.get("entities_json"):
            try:
                event["entities"] = json.loads(event["entities_json"])
            except json.JSONDecodeError:
                event["entities"] = []
        else:
            event["entities"] = []
        del event["entities_json"]
        events.append(event)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events,
    }


@router.get("/{event_id}")
def get_event(event_id: str):
    """Get a single event by ID with full detail including raw payload."""
    conn = get_db()
    row = conn.execute(
        """SELECT id, source, source_id, timestamp, ingested_at,
                  category, severity, confidence, title, summary,
                  raw_payload, latitude, longitude, country_code, region,
                  entities_json, source_url
           FROM events WHERE id = ?""",
        (event_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    event = dict(row)

    # Parse JSON fields
    if event.get("raw_payload"):
        try:
            event["raw_payload"] = json.loads(event["raw_payload"])
        except json.JSONDecodeError:
            pass

    if event.get("entities_json"):
        try:
            event["entities"] = json.loads(event["entities_json"])
        except json.JSONDecodeError:
            event["entities"] = []
    else:
        event["entities"] = []
    del event["entities_json"]

    return event
