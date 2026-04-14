"""
Ambient narration — system activity ticker that surfaces real-time
operational activity from the system_log table.

Provides:
- Recent activity feed (last N entries, filterable by component/level)
- Activity summary (counts by component and level over a time window)
- Log entry creation helper (used by all modules to record activity)
- Narration stream: human-readable descriptions of system activity
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

VALID_LEVELS = {"debug", "info", "warning", "error"}
VALID_COMPONENTS = {"ingestion", "processing", "intelligence", "api", "detection", "system"}


def log_activity(
    conn,
    component: str,
    message: str,
    level: str = "info",
    metadata: dict | None = None,
) -> int:
    """Record a system activity log entry. Returns the log row ID."""
    cursor = conn.execute(
        """INSERT INTO system_log (component, level, message, metadata)
           VALUES (?, ?, ?, ?)""",
        (
            component if component in VALID_COMPONENTS else "system",
            level if level in VALID_LEVELS else "info",
            message,
            json.dumps(metadata) if metadata else None,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_activity_feed(
    conn,
    component: str | None = None,
    level: str | None = None,
    minutes: int = 60,
    limit: int = 50,
) -> list[dict]:
    """Get recent system activity log entries."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    conditions = ["timestamp >= ?"]
    params: list = [cutoff]

    if component and component in VALID_COMPONENTS:
        conditions.append("component = ?")
        params.append(component)
    if level and level in VALID_LEVELS:
        conditions.append("level = ?")
        params.append(level)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM system_log WHERE {where} ORDER BY timestamp DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else None
        results.append(d)
    return results


def get_activity_summary(conn, minutes: int = 60) -> dict:
    """Get a summary of system activity over a time window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    total = conn.execute(
        "SELECT COUNT(*) as c FROM system_log WHERE timestamp >= ?", (cutoff,)
    ).fetchone()["c"]

    by_component: dict[str, int] = {}
    rows = conn.execute(
        "SELECT component, COUNT(*) as c FROM system_log WHERE timestamp >= ? GROUP BY component",
        (cutoff,),
    ).fetchall()
    for r in rows:
        by_component[r["component"]] = r["c"]

    by_level: dict[str, int] = {}
    rows = conn.execute(
        "SELECT level, COUNT(*) as c FROM system_log WHERE timestamp >= ? GROUP BY level",
        (cutoff,),
    ).fetchall()
    for r in rows:
        by_level[r["level"]] = r["c"]

    return {
        "window_minutes": minutes,
        "total_entries": total,
        "by_component": by_component,
        "by_level": by_level,
        "errors": by_level.get("error", 0),
        "warnings": by_level.get("warning", 0),
    }


def generate_narration(conn, limit: int = 10) -> list[dict]:
    """
    Generate human-readable narration entries from recent system activity.
    Transforms raw log entries into ticker-friendly messages.
    """
    NARRATION_TEMPLATES = {
        "ingestion": "📡 {message}",
        "processing": "⚙️ {message}",
        "intelligence": "🧠 {message}",
        "detection": "🔍 {message}",
        "api": "🌐 {message}",
        "system": "💻 {message}",
    }

    LEVEL_ICONS = {
        "error": "🔴",
        "warning": "🟡",
        "info": "🟢",
        "debug": "⚪",
    }

    entries = get_activity_feed(conn, minutes=120, limit=limit)

    narrations = []
    for e in entries:
        icon = LEVEL_ICONS.get(e["level"], "⚪")
        template = NARRATION_TEMPLATES.get(e["component"], "📋 {message}")
        text = template.format(message=e["message"])

        narrations.append({
            "id": e["id"],
            "timestamp": e["timestamp"],
            "level": e["level"],
            "icon": icon,
            "text": f"{icon} {text}",
            "component": e["component"],
            "metadata": e["metadata"],
        })

    return narrations
