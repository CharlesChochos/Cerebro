"""
Custom event tagging — allows analysts to tag events with custom labels
for organization, filtering, and cross-referencing.
"""
import uuid

VALID_CATEGORIES = {"custom", "auto", "priority", "watchlist"}

TAG_COLORS = {
    "priority": "#ef4444", "watchlist": "#f97316",
    "custom": "#3b82f6", "auto": "#6b7280",
}


def add_tag(conn, event_id: str, tag_name: str,
            tag_category: str = "custom", color: str | None = None,
            created_by: str | None = None) -> str:
    tid = str(uuid.uuid4())
    final_color = color or TAG_COLORS.get(tag_category, "#3b82f6")
    conn.execute(
        """INSERT OR IGNORE INTO event_tags
           (id, event_id, tag_name, tag_category, color, created_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tid, event_id, tag_name.strip().lower(),
         tag_category if tag_category in VALID_CATEGORIES else "custom",
         final_color, created_by),
    )
    conn.commit()
    return tid


def remove_tag(conn, event_id: str, tag_name: str) -> bool:
    result = conn.execute(
        "DELETE FROM event_tags WHERE event_id = ? AND tag_name = ?",
        (event_id, tag_name.strip().lower()),
    )
    conn.commit()
    return result.rowcount > 0


def get_event_tags(conn, event_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM event_tags WHERE event_id = ? ORDER BY created_at",
        (event_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def find_events_by_tag(conn, tag_name: str, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """SELECT et.*, e.title, e.category, e.severity, e.timestamp
           FROM event_tags et
           LEFT JOIN events e ON et.event_id = e.id
           WHERE et.tag_name = ?
           ORDER BY et.created_at DESC LIMIT ?""",
        (tag_name.strip().lower(), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_all_tags(conn, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """SELECT tag_name, tag_category, color, COUNT(*) as event_count
           FROM event_tags GROUP BY tag_name, tag_category, color
           ORDER BY event_count DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def bulk_tag(conn, event_ids: list[str], tag_name: str,
             tag_category: str = "custom", created_by: str | None = None) -> int:
    """Tag multiple events at once."""
    count = 0
    tag = tag_name.strip().lower()
    color = TAG_COLORS.get(tag_category, "#3b82f6")
    for eid in event_ids:
        tid = str(uuid.uuid4())
        try:
            conn.execute(
                """INSERT OR IGNORE INTO event_tags
                   (id, event_id, tag_name, tag_category, color, created_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tid, eid, tag, tag_category, color, created_by),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    return count
