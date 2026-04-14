"""
Sanctions evasion detection — multi-hop graph traversal against watchlists.

Matches entities against SDN (Specially Designated Nationals) and other
sanctions lists via:
1. Direct name matching
2. Alias matching (fuzzy)
3. Multi-hop graph traversal through entity_relations

The multi-hop approach detects evasion through intermediaries:
  Sanctioned Org → Shell Company → Front Company → Your Vessel
"""
import json
import logging
import uuid

logger = logging.getLogger(__name__)

# Maximum hops for multi-hop detection
MAX_HOPS = 3

# Minimum confidence threshold for alias matching
ALIAS_CONFIDENCE = 0.6


def normalize_name(name: str) -> str:
    """Normalize entity name for comparison."""
    return name.lower().strip().replace(".", "").replace(",", "")


def check_direct_matches(conn) -> list[dict]:
    """
    Check for direct name matches between entities and sanctions watchlist.
    """
    hits = []

    watchlist = conn.execute(
        "SELECT id, name, aliases, entity_type, program FROM sanctions_watchlist"
    ).fetchall()

    for entry in watchlist:
        w = dict(entry)
        names_to_check = [w["name"]]

        # Parse aliases
        if w.get("aliases"):
            try:
                aliases = json.loads(w["aliases"])
                if isinstance(aliases, list):
                    names_to_check.extend(aliases)
            except (json.JSONDecodeError, TypeError):
                pass

        for name in names_to_check:
            norm_name = normalize_name(name)
            if not norm_name or len(norm_name) < 3:
                continue

            # Search entities by exact name or alias match
            rows = conn.execute(
                """SELECT id, name, entity_type, aliases
                   FROM entities
                   WHERE LOWER(name) = ? OR aliases LIKE ?""",
                (norm_name, f"%{name}%"),
            ).fetchall()

            for row in rows:
                entity = dict(row)
                match_type = "direct" if normalize_name(entity["name"]) == norm_name else "alias"
                confidence = 0.95 if match_type == "direct" else ALIAS_CONFIDENCE

                hits.append({
                    "entity_id": entity["id"],
                    "entity_name": entity["name"],
                    "watchlist_id": w["id"],
                    "watchlist_name": w["name"],
                    "match_type": match_type,
                    "match_confidence": confidence,
                    "program": w["program"],
                    "hop_path": json.dumps([entity["id"]]),
                })

    return hits


def check_multi_hop_matches(conn, max_hops: int = MAX_HOPS) -> list[dict]:
    """
    Multi-hop graph traversal: find entities connected to sanctioned entities
    through intermediaries in the entity_relations graph.
    """
    hits = []

    # First get all directly matched entity IDs
    direct_matches = conn.execute(
        """SELECT DISTINCT entity_id FROM sanctions_hits
           WHERE match_type IN ('direct', 'alias')"""
    ).fetchall()

    sanctioned_ids = {row["entity_id"] for row in direct_matches}

    if not sanctioned_ids:
        return hits

    # BFS from each sanctioned entity
    for start_id in sanctioned_ids:
        # Get the watchlist entry for context
        hit_row = conn.execute(
            """SELECT sh.watchlist_id, sw.name as watchlist_name, sw.program
               FROM sanctions_hits sh
               JOIN sanctions_watchlist sw ON sw.id = sh.watchlist_id
               WHERE sh.entity_id = ? LIMIT 1""",
            (start_id,),
        ).fetchone()

        if not hit_row:
            continue

        # BFS
        queue = [(start_id, [start_id], 0)]
        visited = {start_id}

        while queue:
            current, path, depth = queue.pop(0)

            if depth >= max_hops:
                continue

            # Get neighbors
            neighbors = conn.execute(
                """SELECT
                    CASE WHEN source_entity_id = ? THEN target_entity_id
                         ELSE source_entity_id END as neighbor_id,
                    confidence
                   FROM entity_relations
                   WHERE (source_entity_id = ? OR target_entity_id = ?)
                     AND confidence >= 0.3""",
                (current, current, current),
            ).fetchall()

            for nbr in neighbors:
                neighbor_id = nbr["neighbor_id"]

                if neighbor_id in visited or neighbor_id in sanctioned_ids:
                    continue

                visited.add(neighbor_id)
                new_path = path + [neighbor_id]

                # This is a multi-hop match
                # Confidence decays with each hop
                hop_confidence = round(0.9 ** len(new_path) * nbr["confidence"], 3)

                if hop_confidence >= 0.2:
                    hits.append({
                        "entity_id": neighbor_id,
                        "watchlist_id": hit_row["watchlist_id"],
                        "watchlist_name": hit_row["watchlist_name"],
                        "match_type": "multi_hop",
                        "match_confidence": hop_confidence,
                        "program": hit_row["program"],
                        "hop_path": json.dumps(new_path),
                        "hops": len(new_path) - 1,
                    })

                if depth + 1 < max_hops:
                    queue.append((neighbor_id, new_path, depth + 1))

    return hits


def run_sanctions_scan(conn) -> dict:
    """
    Full sanctions scan: direct matches + multi-hop detection.
    Stores results in sanctions_hits table.
    """
    # Step 1: Direct and alias matches
    direct_hits = check_direct_matches(conn)

    stored_direct = 0
    for hit in direct_hits:
        # Check for existing hit to avoid duplicates
        existing = conn.execute(
            """SELECT id FROM sanctions_hits
               WHERE entity_id = ? AND watchlist_id = ? AND match_type = ?""",
            (hit["entity_id"], hit["watchlist_id"], hit["match_type"]),
        ).fetchone()

        if not existing:
            conn.execute(
                """INSERT INTO sanctions_hits
                   (id, entity_id, watchlist_id, match_type, match_confidence,
                    hop_path, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), hit["entity_id"], hit["watchlist_id"],
                    hit["match_type"], hit["match_confidence"],
                    hit["hop_path"],
                    json.dumps({"program": hit["program"], "watchlist_name": hit["watchlist_name"]}),
                ),
            )
            stored_direct += 1

    conn.commit()

    # Step 2: Multi-hop matches (requires direct matches to exist first)
    multi_hits = check_multi_hop_matches(conn)

    stored_multi = 0
    for hit in multi_hits:
        existing = conn.execute(
            """SELECT id FROM sanctions_hits
               WHERE entity_id = ? AND watchlist_id = ? AND match_type = 'multi_hop'""",
            (hit["entity_id"], hit["watchlist_id"]),
        ).fetchone()

        if not existing:
            conn.execute(
                """INSERT INTO sanctions_hits
                   (id, entity_id, watchlist_id, match_type, match_confidence,
                    hop_path, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), hit["entity_id"], hit["watchlist_id"],
                    hit["match_type"], hit["match_confidence"],
                    hit["hop_path"],
                    json.dumps({
                        "program": hit["program"],
                        "watchlist_name": hit["watchlist_name"],
                        "hops": hit.get("hops", 0),
                    }),
                ),
            )
            stored_multi += 1

    conn.commit()

    stats = {
        "direct_matches": len(direct_hits),
        "multi_hop_matches": len(multi_hits),
        "stored_direct": stored_direct,
        "stored_multi_hop": stored_multi,
        "total_new": stored_direct + stored_multi,
    }
    logger.info("Sanctions scan: %s", stats)
    return stats


def get_sanctions_hits(conn, entity_id: str = None, reviewed: bool = None) -> list[dict]:
    """
    Get sanctions hits, optionally filtered by entity or review status.
    """
    conditions = []
    params = []

    if entity_id:
        conditions.append("sh.entity_id = ?")
        params.append(entity_id)
    if reviewed is not None:
        conditions.append("sh.reviewed = ?")
        params.append(1 if reviewed else 0)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = conn.execute(
        f"""SELECT sh.*, e.name as entity_name, e.entity_type,
                   sw.name as watchlist_name, sw.program
            FROM sanctions_hits sh
            JOIN entities e ON e.id = sh.entity_id
            JOIN sanctions_watchlist sw ON sw.id = sh.watchlist_id
            {where}
            ORDER BY sh.match_confidence DESC""",
        params,
    ).fetchall()

    hits = []
    for r in rows:
        h = dict(r)
        if h.get("hop_path") and isinstance(h["hop_path"], str):
            try:
                h["hop_path"] = json.loads(h["hop_path"])
            except json.JSONDecodeError:
                pass
        if h.get("details") and isinstance(h["details"], str):
            try:
                h["details"] = json.loads(h["details"])
            except json.JSONDecodeError:
                pass
        hits.append(h)

    return hits
