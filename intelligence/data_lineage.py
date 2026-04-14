"""
Data lineage / audit trail — track provenance and transformation of all data items.

Every piece of intelligence in Cerebro has a chain of custody:
  ingestion → classification → enrichment → fusion → grounding → output

This module records each transformation step, enabling analysts to:
1. Trace any conclusion back to its raw source data
2. Audit AI-generated content for quality
3. Detect where errors were introduced in the pipeline
4. Comply with data governance requirements
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def record_lineage(conn, entity_type: str, entity_id: str,
                    action: str, actor: str,
                    details: dict | None = None,
                    source_ids: list[str] | None = None,
                    parent_lineage_id: str | None = None) -> str:
    """
    Record a lineage entry for a data item.

    Args:
        entity_type: event, entity, brief, alert, fusion_signal, prediction
        entity_id: ID of the data item
        action: created, updated, enriched, classified, fused, audited, exported
        actor: system component that performed the action
        details: dict of what changed
        source_ids: upstream entity IDs that contributed
        parent_lineage_id: previous lineage entry in the chain
    """
    lid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO data_lineage
           (id, entity_type, entity_id, action, actor,
            details, source_ids, parent_lineage_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            lid, entity_type, entity_id, action, actor,
            json.dumps(details or {}),
            json.dumps(source_ids or []),
            parent_lineage_id,
        ),
    )
    conn.commit()
    return lid


def get_lineage_chain(conn, entity_type: str, entity_id: str) -> list[dict]:
    """
    Get the full lineage chain for a data item.
    Returns entries in chronological order.
    """
    rows = conn.execute(
        """SELECT * FROM data_lineage
           WHERE entity_type = ? AND entity_id = ?
           ORDER BY created_at ASC""",
        (entity_type, entity_id),
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"]) if d["details"] else {}
        d["source_ids"] = json.loads(d["source_ids"]) if d["source_ids"] else []
        results.append(d)
    return results


def get_lineage_entry(conn, lineage_id: str) -> dict | None:
    """Get a single lineage entry."""
    row = conn.execute(
        "SELECT * FROM data_lineage WHERE id = ?", (lineage_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["details"] = json.loads(d["details"]) if d["details"] else {}
    d["source_ids"] = json.loads(d["source_ids"]) if d["source_ids"] else []
    return d


def list_lineage(conn, entity_type: str | None = None,
                  action: str | None = None,
                  actor: str | None = None,
                  hours: int = 24,
                  limit: int = 50) -> list[dict]:
    """List recent lineage entries with optional filters."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = "SELECT * FROM data_lineage WHERE created_at >= ?"
    params: list = [cutoff]

    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    if action:
        query += " AND action = ?"
        params.append(action)
    if actor:
        query += " AND actor = ?"
        params.append(actor)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"]) if d["details"] else {}
        d["source_ids"] = json.loads(d["source_ids"]) if d["source_ids"] else []
        results.append(d)
    return results


def get_lineage_stats(conn, hours: int = 24) -> dict:
    """Get lineage statistics for the dashboard."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM data_lineage WHERE created_at >= ?",
        (cutoff,),
    ).fetchone()["cnt"]

    by_action = conn.execute(
        """SELECT action, COUNT(*) as cnt FROM data_lineage
           WHERE created_at >= ? GROUP BY action ORDER BY cnt DESC""",
        (cutoff,),
    ).fetchall()

    by_actor = conn.execute(
        """SELECT actor, COUNT(*) as cnt FROM data_lineage
           WHERE created_at >= ? GROUP BY actor ORDER BY cnt DESC""",
        (cutoff,),
    ).fetchall()

    by_type = conn.execute(
        """SELECT entity_type, COUNT(*) as cnt FROM data_lineage
           WHERE created_at >= ? GROUP BY entity_type ORDER BY cnt DESC""",
        (cutoff,),
    ).fetchall()

    return {
        "total_entries": total,
        "period_hours": hours,
        "by_action": {r["action"]: r["cnt"] for r in by_action},
        "by_actor": {r["actor"]: r["cnt"] for r in by_actor},
        "by_entity_type": {r["entity_type"]: r["cnt"] for r in by_type},
    }


def trace_sources(conn, entity_type: str, entity_id: str,
                   max_depth: int = 10) -> dict:
    """
    Trace the full source tree for a data item — follow source_ids recursively.
    Returns a tree of all upstream data items that contributed.
    """
    visited = set()
    tree = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "lineage": [],
        "sources": [],
    }

    def _trace(etype: str, eid: str, depth: int) -> dict:
        key = f"{etype}:{eid}"
        if key in visited or depth > max_depth:
            return {"entity_type": etype, "entity_id": eid, "depth": depth, "sources": []}
        visited.add(key)

        chain = get_lineage_chain(conn, etype, eid)
        source_ids = set()
        for entry in chain:
            for sid in entry.get("source_ids", []):
                source_ids.add(sid)

        child_traces = []
        for sid in source_ids:
            # Try to identify the type from the ID prefix pattern
            child_type = "event"  # default assumption
            if sid.startswith("ent-"):
                child_type = "entity"
            elif sid.startswith("brief-"):
                child_type = "brief"
            elif sid.startswith("alert-"):
                child_type = "alert"
            elif sid.startswith("fusion-"):
                child_type = "fusion_signal"

            child_traces.append(_trace(child_type, sid, depth + 1))

        return {
            "entity_type": etype,
            "entity_id": eid,
            "lineage_count": len(chain),
            "depth": depth,
            "sources": child_traces,
        }

    return _trace(entity_type, entity_id, 0)
