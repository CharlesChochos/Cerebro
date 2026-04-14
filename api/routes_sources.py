"""
Sources API routes — source health and reliability dashboard.
"""
from fastapi import APIRouter

from api.main import get_db

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def list_sources():
    """Get health and reliability info for all data sources."""
    conn = get_db()

    # Source reliability table
    reliability = conn.execute(
        "SELECT * FROM source_reliability ORDER BY total_events DESC"
    ).fetchall()

    # Event counts by source
    counts = conn.execute(
        "SELECT source, COUNT(*) as count FROM events GROUP BY source ORDER BY count DESC"
    ).fetchall()
    count_map = {r["source"]: r["count"] for r in counts}

    # Category breakdown by source
    categories = conn.execute(
        """SELECT source, category, COUNT(*) as count
           FROM events GROUP BY source, category ORDER BY source, count DESC"""
    ).fetchall()
    cat_map: dict = {}
    for r in categories:
        src = r["source"]
        if src not in cat_map:
            cat_map[src] = {}
        cat_map[src][r["category"] or "unclassified"] = r["count"]

    sources = []
    for row in reliability:
        src = dict(row)
        src["event_count_in_db"] = count_map.get(src["source"], 0)
        src["categories"] = cat_map.get(src["source"], {})
        sources.append(src)

    return {"sources": sources}
