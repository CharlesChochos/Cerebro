"""
Association Matrix — maps relationships between entities, events, countries,
and sources to uncover hidden connections and patterns.

Relationship types:
- linked: general association
- co-located: entities appeared at the same location
- co-temporal: entities appeared at the same time
- financial: financial relationship
- command: command/control hierarchy
- communication: communication link detected

The matrix is bidirectional by default (A↔B) but can be directional (A→B).
Strength is 0.0–1.0 and confidence is low/moderate/high.
"""
import json
import logging
import uuid
from collections import defaultdict

logger = logging.getLogger(__name__)

VALID_RELATIONSHIP_TYPES = {
    "linked", "co-located", "co-temporal", "financial", "command", "communication",
}
VALID_CONFIDENCE = {"low", "moderate", "high"}


def create_association(
    conn,
    entity_a_type: str,
    entity_a_id: str,
    entity_b_type: str,
    entity_b_id: str,
    relationship_type: str,
    strength: float = 0.5,
    confidence: str = "moderate",
    entity_a_label: str | None = None,
    entity_b_label: str | None = None,
    evidence: list[str] | None = None,
    bidirectional: bool = True,
    analyst: str | None = None,
) -> str:
    """Create an association between two entities."""
    aid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO association_matrix
           (id, entity_a_type, entity_a_id, entity_a_label,
            entity_b_type, entity_b_id, entity_b_label,
            relationship_type, strength, confidence, evidence,
            bidirectional, analyst)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            aid, entity_a_type, entity_a_id, entity_a_label,
            entity_b_type, entity_b_id, entity_b_label,
            relationship_type,
            max(0.0, min(1.0, strength)),
            confidence if confidence in VALID_CONFIDENCE else "moderate",
            json.dumps(evidence or []),
            1 if bidirectional else 0,
            analyst,
        ),
    )
    conn.commit()
    return aid


def get_association(conn, association_id: str) -> dict | None:
    """Get a single association."""
    row = conn.execute("SELECT * FROM association_matrix WHERE id = ?", (association_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
    d["bidirectional"] = bool(d["bidirectional"])
    return d


def find_associations(
    conn,
    entity_type: str | None = None,
    entity_id: str | None = None,
    relationship_type: str | None = None,
    min_strength: float = 0.0,
    limit: int = 100,
) -> list[dict]:
    """
    Find associations involving a specific entity or matching criteria.
    Searches both A and B sides for bidirectional associations.
    """
    conditions = []
    params: list = []

    if entity_type and entity_id:
        conditions.append(
            "((entity_a_type = ? AND entity_a_id = ?) OR "
            "(entity_b_type = ? AND entity_b_id = ? AND bidirectional = 1))"
        )
        params.extend([entity_type, entity_id, entity_type, entity_id])
    elif entity_type:
        conditions.append("(entity_a_type = ? OR (entity_b_type = ? AND bidirectional = 1))")
        params.extend([entity_type, entity_type])

    if relationship_type:
        conditions.append("relationship_type = ?")
        params.append(relationship_type)
    if min_strength > 0:
        conditions.append("strength >= ?")
        params.append(min_strength)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM association_matrix{where} ORDER BY strength DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
        d["bidirectional"] = bool(d["bidirectional"])
        results.append(d)
    return results


def list_associations(
    conn,
    relationship_type: str | None = None,
    min_strength: float = 0.0,
    limit: int = 100,
) -> list[dict]:
    """List all associations with optional filtering."""
    return find_associations(conn, relationship_type=relationship_type,
                             min_strength=min_strength, limit=limit)


def build_network_graph(conn, entity_type: str, entity_id: str, depth: int = 2) -> dict:
    """
    Build a network graph starting from an entity, traversing associations up to `depth` hops.

    Returns nodes and edges suitable for visualization.
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    visited = set()
    frontier = [(entity_type, entity_id, 0)]

    while frontier:
        etype, eid, d = frontier.pop(0)
        key = f"{etype}:{eid}"
        if key in visited or d > depth:
            continue
        visited.add(key)

        assocs = find_associations(conn, entity_type=etype, entity_id=eid, limit=50)

        for a in assocs:
            # Determine the "other" side
            if a["entity_a_type"] == etype and a["entity_a_id"] == eid:
                other_type = a["entity_b_type"]
                other_id = a["entity_b_id"]
                other_label = a["entity_b_label"]
                this_label = a["entity_a_label"]
            else:
                other_type = a["entity_a_type"]
                other_id = a["entity_a_id"]
                other_label = a["entity_a_label"]
                this_label = a["entity_b_label"]

            # Add this node
            if key not in nodes:
                nodes[key] = {
                    "type": etype, "id": eid,
                    "label": this_label or eid, "depth": d,
                }

            # Add other node
            other_key = f"{other_type}:{other_id}"
            if other_key not in nodes:
                nodes[other_key] = {
                    "type": other_type, "id": other_id,
                    "label": other_label or other_id, "depth": d + 1,
                }

            edges.append({
                "source": key,
                "target": other_key,
                "relationship": a["relationship_type"],
                "strength": a["strength"],
                "confidence": a["confidence"],
            })

            if d + 1 <= depth:
                frontier.append((other_type, other_id, d + 1))

    return {
        "root": {"type": entity_type, "id": entity_id},
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def get_matrix_stats(conn) -> dict:
    """Get summary statistics for the association matrix."""
    total = conn.execute("SELECT COUNT(*) as c FROM association_matrix").fetchone()["c"]

    by_type = {}
    rows = conn.execute(
        "SELECT relationship_type, COUNT(*) as c, AVG(strength) as avg_s "
        "FROM association_matrix GROUP BY relationship_type"
    ).fetchall()
    for r in rows:
        by_type[r["relationship_type"]] = {
            "count": r["c"],
            "avg_strength": round(r["avg_s"], 3),
        }

    return {
        "total_associations": total,
        "by_relationship_type": by_type,
    }
