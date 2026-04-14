"""
Entity Intelligence — omnisearch, dossier generation, link analysis.

Cross-references all 18 data layers to build comprehensive entity profiles.
Uses Claude Sonnet for dossier synthesis when available.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

DOSSIER_PROMPT = """You are a senior intelligence analyst compiling an entity dossier.

ENTITY: {entity_name} (type: {entity_type})

CROSS-SOURCE INTELLIGENCE:
{intel_text}

KNOWN RELATIONSHIPS:
{relations_text}

Compile a comprehensive intelligence dossier. Provide:
1. **summary**: 2-3 paragraph executive summary of who/what this entity is and their significance
2. **key_facts**: Array of 5-10 key intelligence facts (strings)
3. **risk_assessment**: 1-2 paragraphs assessing the threat/risk level and reasoning
4. **timeline**: Array of objects with "date", "event", and "source" keys for the entity's activity timeline

Respond ONLY with a JSON object containing these four keys. Base everything strictly on the provided intelligence — do NOT fabricate facts.
"""


def omnisearch(conn, query: str, limit: int = 20) -> dict:
    """
    Search across all data layers for entity-relevant intelligence.
    Returns categorized results from each source.
    """
    results = {}
    like_query = f"%{query}%"

    # 1. Entities table
    rows = conn.execute(
        """SELECT id, name, entity_type, aliases, metadata, event_count, first_seen, last_seen
           FROM entities WHERE name LIKE ? OR aliases LIKE ?
           ORDER BY event_count DESC LIMIT ?""",
        (like_query, like_query, limit),
    ).fetchall()
    results["entities"] = [dict(r) for r in rows]

    # 2. Events referencing this entity
    rows = conn.execute(
        """SELECT id, source, title, category, severity, confidence, country_code,
                  region, timestamp
           FROM events WHERE title LIKE ? OR summary LIKE ? OR entities_json LIKE ?
           ORDER BY timestamp DESC LIMIT ?""",
        (like_query, like_query, like_query, limit),
    ).fetchall()
    results["events"] = [dict(r) for r in rows]

    # 3. Fusion signals
    try:
        rows = conn.execute(
            """SELECT id, signal_type, title, description, severity, confidence, created_at
               FROM fusion_signals WHERE title LIKE ? OR description LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like_query, like_query, limit),
        ).fetchall()
        results["fusion_signals"] = [dict(r) for r in rows]
    except Exception:
        results["fusion_signals"] = []

    # 4. Briefs mentioning entity
    try:
        rows = conn.execute(
            """SELECT id, brief_type, title, created_at
               FROM briefs WHERE title LIKE ? OR content LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like_query, like_query, limit),
        ).fetchall()
        results["briefs"] = [dict(r) for r in rows]
    except Exception:
        results["briefs"] = []

    # 5. Vessels (if entity could be a vessel)
    try:
        rows = conn.execute(
            """SELECT mmsi, name, vessel_type, flag_country, last_lat, last_lng, is_dark
               FROM vessels WHERE name LIKE ? OR mmsi LIKE ?
               LIMIT ?""",
            (like_query, like_query, limit),
        ).fetchall()
        results["vessels"] = [dict(r) for r in rows]
    except Exception:
        results["vessels"] = []

    # 6. Disease outbreaks
    try:
        rows = conn.execute(
            """SELECT id, disease, title, country_code, status, severity, published_at
               FROM disease_outbreaks WHERE title LIKE ? OR disease LIKE ?
               ORDER BY published_at DESC LIMIT ?""",
            (like_query, like_query, limit),
        ).fetchall()
        results["outbreaks"] = [dict(r) for r in rows]
    except Exception:
        results["outbreaks"] = []

    # 7. Red team analyses
    try:
        rows = conn.execute(
            """SELECT id, target_type, target_id, overall_assessment, created_at
               FROM red_team_analyses WHERE overall_assessment LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like_query, limit),
        ).fetchall()
        results["red_team"] = [dict(r) for r in rows]
    except Exception:
        results["red_team"] = []

    # 8. Sanctions watchlist
    try:
        rows = conn.execute(
            """SELECT id, name, entity_type, program, country_code
               FROM sanctions_watchlist WHERE name LIKE ? OR aliases LIKE ?
               LIMIT ?""",
            (like_query, like_query, limit),
        ).fetchall()
        results["sanctions_matches"] = [dict(r) for r in rows]
    except Exception:
        results["sanctions_matches"] = []

    # Count total results across all layers
    total = sum(len(v) for v in results.values())
    results["total_hits"] = total
    results["query"] = query

    return results


def gather_entity_intel(conn, entity_id: str) -> dict:
    """
    Gather all intelligence about a specific entity across data layers.
    """
    entity = conn.execute(
        "SELECT * FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    if not entity:
        return {"error": "entity_not_found"}

    entity = dict(entity)
    name = entity["name"]

    # Get related events via entity name search
    events = conn.execute(
        """SELECT id, source, title, category, severity, country_code, timestamp
           FROM events WHERE title LIKE ? OR entities_json LIKE ?
           ORDER BY timestamp DESC LIMIT 30""",
        (f"%{name}%", f"%{name}%"),
    ).fetchall()

    # Get entity relations
    relations = conn.execute(
        """SELECT er.relation_type, er.confidence,
                  CASE WHEN er.source_entity_id = ? THEN e2.name ELSE e1.name END as related_name,
                  CASE WHEN er.source_entity_id = ? THEN e2.entity_type ELSE e1.entity_type END as related_type,
                  CASE WHEN er.source_entity_id = ? THEN er.target_entity_id ELSE er.source_entity_id END as related_id
           FROM entity_relations er
           JOIN entities e1 ON e1.id = er.source_entity_id
           JOIN entities e2 ON e2.id = er.target_entity_id
           WHERE er.source_entity_id = ? OR er.target_entity_id = ?
           ORDER BY er.confidence DESC LIMIT 30""",
        (entity_id, entity_id, entity_id, entity_id, entity_id),
    ).fetchall()

    # Get fusion signals mentioning entity
    try:
        fusion = conn.execute(
            """SELECT id, signal_type, title, severity, confidence, created_at
               FROM fusion_signals WHERE title LIKE ? OR description LIKE ?
               ORDER BY created_at DESC LIMIT 10""",
            (f"%{name}%", f"%{name}%"),
        ).fetchall()
    except Exception:
        fusion = []

    # Check sanctions
    try:
        sanctions = conn.execute(
            """SELECT id, name, program, country_code
               FROM sanctions_watchlist WHERE name LIKE ? OR aliases LIKE ?""",
            (f"%{name}%", f"%{name}%"),
        ).fetchall()
    except Exception:
        sanctions = []

    return {
        "entity": entity,
        "events": [dict(r) for r in events],
        "relations": [dict(r) for r in relations],
        "fusion_signals": [dict(r) for r in fusion],
        "sanctions_matches": [dict(r) for r in sanctions],
    }


def format_intel_for_prompt(intel: dict) -> str:
    """Format gathered intelligence for the dossier prompt."""
    lines = []

    if intel.get("events"):
        lines.append("=== EVENTS ===")
        for e in intel["events"][:20]:
            lines.append(
                f"  [{e['source']}] {e['timestamp'][:10]} | {e['title']} "
                f"(sev={e['severity']}, cc={e.get('country_code', '?')})"
            )

    if intel.get("fusion_signals"):
        lines.append("\n=== FUSION SIGNALS ===")
        for f in intel["fusion_signals"]:
            lines.append(f"  [{f['signal_type']}] {f['title']} (sev={f['severity']})")

    if intel.get("sanctions_matches"):
        lines.append("\n=== SANCTIONS WATCHLIST MATCHES ===")
        for s in intel["sanctions_matches"]:
            lines.append(f"  {s['name']} ({s['program']}) — {s.get('country_code', '?')}")

    return "\n".join(lines) if lines else "No intelligence gathered."


def format_relations_for_prompt(relations: list[dict]) -> str:
    """Format entity relations for the dossier prompt."""
    if not relations:
        return "No known relationships."
    lines = []
    for r in relations:
        lines.append(
            f"  {r['related_name']} ({r['related_type']}) — "
            f"{r['relation_type']} (conf={r['confidence']})"
        )
    return "\n".join(lines)


def generate_dossier(conn, entity_id: str) -> dict:
    """
    Generate a comprehensive intelligence dossier for an entity.
    Uses Claude Sonnet if available, otherwise returns structured raw data.
    """
    intel = gather_entity_intel(conn, entity_id)
    if intel.get("error"):
        return intel

    entity = intel["entity"]
    entity_name = entity["name"]
    entity_type = entity["entity_type"]

    # Build raw dossier (always available, even without API key)
    raw_dossier = {
        "entity_id": entity_id,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "event_count": len(intel["events"]),
        "source_count": len(set(e["source"] for e in intel["events"])),
        "relation_count": len(intel["relations"]),
        "sanctions_flags": len(intel["sanctions_matches"]),
        "events": intel["events"][:10],
        "relations": intel["relations"][:10],
        "fusion_signals": intel["fusion_signals"],
        "sanctions_matches": intel["sanctions_matches"],
    }

    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — returning raw dossier")
        raw_dossier["model_used"] = None
        raw_dossier["summary"] = f"Entity profile for {entity_name} ({entity_type}). {len(intel['events'])} related events from {raw_dossier['source_count']} sources."
        raw_dossier["key_facts"] = []
        raw_dossier["risk_assessment"] = "Automated risk assessment requires Claude API key."
        raw_dossier["timeline_events"] = [
            {"date": e["timestamp"][:10], "event": e["title"], "source": e["source"]}
            for e in intel["events"][:10]
        ]
        return raw_dossier

    # Generate with Claude
    prompt = DOSSIER_PROMPT.format(
        entity_name=entity_name,
        entity_type=entity_type,
        intel_text=format_intel_for_prompt(intel),
        relations_text=format_relations_for_prompt(intel["relations"]),
    )

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()

        # Parse JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        dossier_data = json.loads(content)

        # Store dossier
        dossier_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO entity_dossiers
               (id, entity_id, summary, key_facts, risk_assessment,
                timeline_events, source_count, event_count, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dossier_id, entity_id,
                dossier_data.get("summary", ""),
                json.dumps(dossier_data.get("key_facts", [])),
                dossier_data.get("risk_assessment", ""),
                json.dumps(dossier_data.get("timeline", [])),
                raw_dossier["source_count"],
                raw_dossier["event_count"],
                MODEL,
            ),
        )
        conn.commit()

        raw_dossier.update({
            "dossier_id": dossier_id,
            "summary": dossier_data.get("summary", ""),
            "key_facts": dossier_data.get("key_facts", []),
            "risk_assessment": dossier_data.get("risk_assessment", ""),
            "timeline_events": dossier_data.get("timeline", []),
            "model_used": MODEL,
        })

    except (json.JSONDecodeError, anthropic.APIError) as e:
        logger.error("Dossier generation error: %s", e)
        raw_dossier["error"] = str(e)

    return raw_dossier


def get_link_graph(conn, entity_id: str, max_depth: int = 2, max_nodes: int = 50) -> dict:
    """
    Build a link analysis graph centered on an entity.
    Returns nodes and edges for D3.js force-directed visualization.

    max_depth: how many hops from center entity
    max_nodes: cap to prevent explosion
    """
    nodes = {}
    edges = []
    visited = set()

    def _expand(eid: str, depth: int):
        if depth > max_depth or eid in visited or len(nodes) >= max_nodes:
            return
        visited.add(eid)

        # Get this entity
        row = conn.execute(
            "SELECT id, name, entity_type, event_count FROM entities WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return

        entity = dict(row)
        nodes[eid] = {
            "id": eid,
            "name": entity["name"],
            "type": entity["entity_type"],
            "event_count": entity["event_count"],
            "depth": depth,
        }

        # Get relations
        rels = conn.execute(
            """SELECT er.id, er.source_entity_id, er.target_entity_id,
                      er.relation_type, er.confidence
               FROM entity_relations er
               WHERE er.source_entity_id = ? OR er.target_entity_id = ?
               ORDER BY er.confidence DESC LIMIT 20""",
            (eid, eid),
        ).fetchall()

        for rel in rels:
            r = dict(rel)
            other_id = r["target_entity_id"] if r["source_entity_id"] == eid else r["source_entity_id"]

            edges.append({
                "id": r["id"],
                "source": r["source_entity_id"],
                "target": r["target_entity_id"],
                "relation": r["relation_type"],
                "confidence": r["confidence"],
            })

            if len(nodes) < max_nodes:
                _expand(other_id, depth + 1)

    _expand(entity_id, 0)

    return {
        "center_entity": entity_id,
        "nodes": list(nodes.values()),
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def find_shortest_path(conn, source_id: str, target_id: str, max_depth: int = 5) -> dict:
    """
    BFS shortest path between two entities in the knowledge graph.
    Returns the path as list of entity IDs and the relations traversed.
    """
    if source_id == target_id:
        return {"path": [source_id], "relations": [], "hops": 0}

    queue = [(source_id, [source_id], [])]
    visited = {source_id}

    while queue:
        current, path, rels = queue.pop(0)

        if len(path) > max_depth + 1:
            break

        # Get neighbors
        rows = conn.execute(
            """SELECT
                CASE WHEN source_entity_id = ? THEN target_entity_id
                     ELSE source_entity_id END as neighbor_id,
                relation_type
               FROM entity_relations
               WHERE source_entity_id = ? OR target_entity_id = ?""",
            (current, current, current),
        ).fetchall()

        for row in rows:
            neighbor = row["neighbor_id"]
            relation = row["relation_type"]

            if neighbor == target_id:
                return {
                    "path": path + [neighbor],
                    "relations": rels + [relation],
                    "hops": len(path),
                }

            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor], rels + [relation]))

    return {"path": [], "relations": [], "hops": -1, "error": "no_path_found"}
