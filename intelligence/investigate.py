"""
Autonomous deep dive investigation agent — Claude with tool_use.

When an anomaly triggers, this agent launches a multi-step investigation
using Claude's tool-calling capability.  It queries vessel history,
nearby events, news, commodity prices, satellite changes, and entity
networks to produce a comprehensive investigative report.

Flow:
  1.  User or system triggers investigate(conn, alert_or_event_id)
  2.  We assemble context (the triggering alert/event data)
  3.  Claude is called with a set of tools it can invoke
  4.  Each tool call is executed against the local database
  5.  Results are fed back to Claude for the next reasoning step
  6.  Loop terminates when Claude produces a final report (max 10 rounds)
  7.  The report is stored in the investigations table
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

INVESTIGATION_SYSTEM = """You are a senior intelligence analyst conducting an autonomous
investigation into an anomaly.  You have access to tools that query
Cerebro's databases.  Follow leads methodically:

1. Start by understanding the anomaly context.
2. Query related events nearby in space and time.
3. If vessels are involved, pull vessel history and check dark events.
4. Check for related entities and their networks.
5. Look at commodity / market signals if economically relevant.
6. Check satellite change records for the area.
7. Synthesize findings into a structured report.

Stay under 10 tool calls.  When you have enough evidence, produce your
final report as a JSON object with this exact schema:

{
  "title": "one-line investigation title",
  "summary": "2-3 paragraph executive summary",
  "key_findings": ["finding 1", "finding 2", ...],
  "risk_assessment": "low | medium | high | critical",
  "confidence": 0.0-1.0,
  "recommended_actions": ["action 1", "action 2", ...],
  "entities_of_interest": ["entity name 1", ...],
  "sources_consulted": ["source 1", ...]
}

Return ONLY this JSON when you are done — no surrounding text."""


# ─── Tool definitions for Claude ────────────────────────────

TOOLS = [
    {
        "name": "query_events_near",
        "description": (
            "Search for recent intelligence events near a geographic point. "
            "Returns events within the specified radius and time window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point"},
                "lng": {"type": "number", "description": "Longitude of center point"},
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometers (default 100)",
                    "default": 100,
                },
                "days": {
                    "type": "integer",
                    "description": "Look back N days (default 7)",
                    "default": 7,
                },
                "category": {
                    "type": "string",
                    "description": "Optional: filter by category (military, economic, health, political, environmental)",
                },
            },
            "required": ["lat", "lng"],
        },
    },
    {
        "name": "query_vessel_history",
        "description": (
            "Get recent track history and details for a vessel by MMSI. "
            "Returns position history, vessel type, flag, and any dark events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mmsi": {
                    "type": "string",
                    "description": "Maritime Mobile Service Identity number",
                },
            },
            "required": ["mmsi"],
        },
    },
    {
        "name": "query_entity_network",
        "description": (
            "Find all relationships for a named entity (person, organization, "
            "vessel, country).  Returns entity details and up to 2-hop connections."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity to look up",
                },
            },
            "required": ["entity_name"],
        },
    },
    {
        "name": "query_news",
        "description": (
            "Search recent news/event headlines matching a keyword, "
            "optionally filtered by region or category."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search term for headlines and summaries",
                },
                "region": {
                    "type": "string",
                    "description": "Optional country code or region name to filter by",
                },
                "days": {
                    "type": "integer",
                    "description": "Look back N days (default 7)",
                    "default": 7,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "query_commodity_prices",
        "description": (
            "Check recent commodity or financial data signals for a commodity "
            "or market indicator."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "commodity": {
                    "type": "string",
                    "description": "Commodity name (oil, gas, wheat, gold) or market indicator",
                },
                "days": {
                    "type": "integer",
                    "description": "Look back N days (default 30)",
                    "default": 30,
                },
            },
            "required": ["commodity"],
        },
    },
    {
        "name": "query_satellite_changes",
        "description": (
            "Check cached satellite imagery and change annotations "
            "for a geographic area."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude"},
                "lng": {"type": "number", "description": "Longitude"},
                "radius_km": {
                    "type": "number",
                    "description": "Search radius (default 50)",
                    "default": 50,
                },
            },
            "required": ["lat", "lng"],
        },
    },
]


# ─── Tool execution against local database ──────────────────

def _exec_query_events_near(conn, params: dict) -> str:
    lat = params["lat"]
    lng = params["lng"]
    radius_km = params.get("radius_km", 100)
    days = params.get("days", 7)
    category = params.get("category")

    # Bounding-box approximation: 1° ≈ 111 km
    delta = radius_km / 111.0
    query = """
        SELECT id, title, summary, source, category, severity, confidence,
               latitude, longitude, country_code, timestamp
        FROM events
        WHERE latitude BETWEEN ? AND ?
          AND longitude BETWEEN ? AND ?
          AND julianday('now') - julianday(timestamp) <= ?
    """
    args: list = [lat - delta, lat + delta, lng - delta, lng + delta, days]

    if category:
        query += " AND category = ?"
        args.append(category)

    query += " ORDER BY severity DESC LIMIT 20"
    rows = conn.execute(query, args).fetchall()
    events = [dict(r) for r in rows]
    return json.dumps(events, default=str)


def _exec_query_vessel_history(conn, params: dict) -> str:
    mmsi = params["mmsi"]

    # Vessel details from vessels table (current state)
    vessel = conn.execute(
        "SELECT * FROM vessels WHERE mmsi = ?", (mmsi,),
    ).fetchone()
    if not vessel:
        # Fallback: get latest from tracks
        vessel = conn.execute(
            "SELECT * FROM vessel_tracks WHERE mmsi = ? ORDER BY timestamp DESC LIMIT 1",
            (mmsi,),
        ).fetchone()

    # Recent track
    track = conn.execute(
        """SELECT latitude, longitude, speed, course, timestamp
           FROM vessel_tracks WHERE mmsi = ?
           ORDER BY timestamp DESC LIMIT 50""",
        (mmsi,),
    ).fetchall()

    # Dark events
    darks = conn.execute(
        """SELECT * FROM ais_dark_events
           WHERE mmsi = ? ORDER BY created_at DESC LIMIT 5""",
        (mmsi,),
    ).fetchall()

    return json.dumps({
        "vessel": dict(vessel) if vessel else None,
        "track_points": len(track),
        "recent_positions": [dict(r) for r in track[:10]],
        "dark_events": [dict(r) for r in darks],
    }, default=str)


def _exec_query_entity_network(conn, params: dict) -> str:
    name = params["entity_name"]

    # Find entity
    entities = conn.execute(
        "SELECT * FROM entities WHERE name LIKE ? LIMIT 5",
        (f"%{name}%",),
    ).fetchall()

    if not entities:
        return json.dumps({"entity": None, "message": f"No entity matching '{name}'"})

    entity = dict(entities[0])
    eid = entity["id"]

    # 1-hop relationships
    rels = conn.execute(
        """SELECT er.relation_type, er.confidence,
                  e2.name as related_name, e2.entity_type as related_type
           FROM entity_relations er
           JOIN entities e2 ON (
               CASE WHEN er.source_entity_id = ? THEN er.target_entity_id
                    ELSE er.source_entity_id END = e2.id
           )
           WHERE er.source_entity_id = ? OR er.target_entity_id = ?
           LIMIT 20""",
        (eid, eid, eid),
    ).fetchall()

    return json.dumps({
        "entity": entity,
        "all_matches": [dict(e) for e in entities],
        "relationships": [dict(r) for r in rels],
    }, default=str)


def _exec_query_news(conn, params: dict) -> str:
    keyword = params["keyword"]
    region = params.get("region")
    days = params.get("days", 7)

    query = """
        SELECT id, title, summary, source, category, severity, country_code, timestamp
        FROM events
        WHERE (title LIKE ? OR summary LIKE ?)
          AND julianday('now') - julianday(timestamp) <= ?
    """
    args: list = [f"%{keyword}%", f"%{keyword}%", days]

    if region:
        query += " AND (country_code = ? OR region LIKE ?)"
        args.extend([region, f"%{region}%"])

    query += " ORDER BY timestamp DESC LIMIT 15"
    rows = conn.execute(query, args).fetchall()
    return json.dumps([dict(r) for r in rows], default=str)


def _exec_query_commodity_prices(conn, params: dict) -> str:
    commodity = params["commodity"]
    days = params.get("days", 30)

    # Check financial events
    rows = conn.execute(
        """SELECT title, summary, source, severity, timestamp
           FROM events
           WHERE category = 'economic'
             AND (title LIKE ? OR summary LIKE ?)
             AND julianday('now') - julianday(timestamp) <= ?
           ORDER BY timestamp DESC LIMIT 10""",
        (f"%{commodity}%", f"%{commodity}%", days),
    ).fetchall()

    return json.dumps({
        "commodity": commodity,
        "related_events": [dict(r) for r in rows],
        "event_count": len(rows),
    }, default=str)


def _exec_query_satellite_changes(conn, params: dict) -> str:
    lat = params["lat"]
    lng = params["lng"]
    radius_km = params.get("radius_km", 50)
    delta = radius_km / 111.0

    rows = conn.execute(
        """SELECT id, source, capture_date, cloud_cover, annotations,
                  resolution_m, bbox_json
           FROM satellite_cache
           WHERE CAST(json_extract(bbox_json, '$[0]') AS REAL) <= ?
             AND CAST(json_extract(bbox_json, '$[2]') AS REAL) >= ?
             AND CAST(json_extract(bbox_json, '$[1]') AS REAL) <= ?
             AND CAST(json_extract(bbox_json, '$[3]') AS REAL) >= ?
           ORDER BY capture_date DESC LIMIT 10""",
        (lng + delta, lng - delta, lat + delta, lat - delta),
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        if d.get("annotations"):
            try:
                d["annotations"] = json.loads(d["annotations"])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)

    return json.dumps({
        "search_center": [lat, lng],
        "images_found": len(results),
        "satellite_records": results,
    }, default=str)


TOOL_DISPATCH = {
    "query_events_near": _exec_query_events_near,
    "query_vessel_history": _exec_query_vessel_history,
    "query_entity_network": _exec_query_entity_network,
    "query_news": _exec_query_news,
    "query_commodity_prices": _exec_query_commodity_prices,
    "query_satellite_changes": _exec_query_satellite_changes,
}


# ─── Main investigation loop ────────────────────────────────

def _build_trigger_context(conn, trigger_type: str, trigger_id: str) -> str:
    """Build context text describing what triggered this investigation."""
    if trigger_type == "event":
        row = conn.execute("SELECT * FROM events WHERE id = ?", (trigger_id,)).fetchone()
        if row:
            e = dict(row)
            return (
                f"ANOMALY TRIGGER: Event\n"
                f"Title: {e.get('title', 'N/A')}\n"
                f"Source: {e.get('source', 'N/A')}\n"
                f"Category: {e.get('category', 'N/A')}\n"
                f"Severity: {e.get('severity', 'N/A')}\n"
                f"Confidence: {e.get('confidence', 'N/A')}\n"
                f"Summary: {e.get('summary', 'N/A')}\n"
                f"Location: {e.get('latitude', '?')}, {e.get('longitude', '?')} "
                f"({e.get('country_code', '?')})\n"
                f"Timestamp: {e.get('timestamp', 'N/A')}"
            )

    elif trigger_type == "alert":
        row = conn.execute("SELECT * FROM alerts WHERE id = ?", (trigger_id,)).fetchone()
        if row:
            a = dict(row)
            return (
                f"ANOMALY TRIGGER: Alert\n"
                f"Type: {a.get('alert_type', 'N/A')}\n"
                f"Severity: {a.get('severity', 'N/A')}\n"
                f"Confidence: {a.get('confidence', 'N/A')}\n"
                f"Title: {a.get('title', 'N/A')}\n"
                f"Region: {a.get('region', 'N/A')}\n"
                f"Description: {a.get('description', 'N/A')}"
            )

    elif trigger_type == "vessel":
        row = conn.execute(
            "SELECT * FROM vessels WHERE mmsi = ?", (trigger_id,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM vessel_tracks WHERE mmsi = ? ORDER BY timestamp DESC LIMIT 1",
                (trigger_id,),
            ).fetchone()
        if row:
            v = dict(row)
            return (
                f"ANOMALY TRIGGER: Vessel anomaly\n"
                f"MMSI: {v.get('mmsi', 'N/A')}\n"
                f"Name: {v.get('name', v.get('vessel_name', 'N/A'))}\n"
                f"Type: {v.get('vessel_type', 'N/A')}\n"
                f"Flag: {v.get('flag', v.get('flag_state', 'N/A'))}\n"
                f"Last Position: {v.get('latitude', '?')}, {v.get('longitude', '?')}\n"
                f"Speed: {v.get('speed', '?')} kts\n"
                f"Course: {v.get('course', '?')}°"
            )

    elif trigger_type == "fusion":
        row = conn.execute(
            "SELECT * FROM fusion_signals WHERE id = ?", (trigger_id,)
        ).fetchone()
        if row:
            f = dict(row)
            return (
                f"ANOMALY TRIGGER: Fusion signal\n"
                f"Type: {f.get('signal_type', 'N/A')}\n"
                f"Title: {f.get('title', 'N/A')}\n"
                f"Severity: {f.get('severity', 'N/A')}\n"
                f"Description: {f.get('description', 'N/A')}"
            )

    return f"ANOMALY TRIGGER: {trigger_type} / {trigger_id} (details unavailable)"


def investigate(conn, trigger_type: str, trigger_id: str,
                max_rounds: int = 10) -> dict:
    """
    Launch an autonomous deep-dive investigation.

    Args:
        conn:         Database connection
        trigger_type: "event", "alert", "vessel", or "fusion"
        trigger_id:   ID of the triggering record
        max_rounds:   Maximum tool-calling rounds (default 10)

    Returns:
        Investigation result dict with report and metadata.
    """
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping investigation")
        return {"error": "no_api_key"}

    context = _build_trigger_context(conn, trigger_type, trigger_id)
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    messages = [{"role": "user", "content": f"Investigate this anomaly:\n\n{context}"}]

    total_input_tokens = 0
    total_output_tokens = 0
    tool_calls_made = 0
    tools_used = []

    for _round in range(max_rounds):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=INVESTIGATION_SYSTEM,
                tools=TOOLS,
                messages=messages,
            )
        except anthropic.APIError as e:
            logger.error("Investigation API error round %d: %s", _round, e)
            return {"error": str(e)}

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Check if Claude wants to use tools or is done
        if response.stop_reason == "end_turn":
            # Claude produced final output — extract the text
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            break

        # Process tool use blocks
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for block in assistant_content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_calls_made += 1
                tools_used.append(tool_name)

                handler = TOOL_DISPATCH.get(tool_name)
                if handler:
                    try:
                        result_str = handler(conn, tool_input)
                    except Exception as e:
                        logger.error("Tool %s error: %s", tool_name, e)
                        result_str = json.dumps({"error": str(e)})
                else:
                    result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
    else:
        # Exhausted rounds — ask Claude for final summary
        messages.append({
            "role": "user",
            "content": "You've used all available tool calls. Please provide your final investigation report now as the JSON schema specified.",
        })
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=INVESTIGATION_SYSTEM,
                messages=messages,
            )
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
        except anthropic.APIError as e:
            logger.error("Investigation final-round error: %s", e)
            final_text = json.dumps({
                "title": "Investigation incomplete",
                "summary": f"API error on final round: {e}",
                "key_findings": [],
                "risk_assessment": "medium",
                "confidence": 0.3,
                "recommended_actions": ["Retry investigation"],
                "entities_of_interest": [],
                "sources_consulted": tools_used,
            })

    # Parse the final report
    try:
        # Strip markdown fences if present
        clean = final_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        if clean.startswith("json"):
            clean = clean[4:].strip()
        report = json.loads(clean)
    except (json.JSONDecodeError, IndexError):
        report = {
            "title": "Investigation complete (unstructured)",
            "summary": final_text[:2000],
            "key_findings": [],
            "risk_assessment": "medium",
            "confidence": 0.5,
            "recommended_actions": [],
            "entities_of_interest": [],
            "sources_consulted": tools_used,
        }

    # Store the investigation
    inv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO investigations
           (id, trigger_type, trigger_id, title, summary, key_findings,
            risk_assessment, confidence, recommended_actions,
            entities_of_interest, sources_consulted, tool_calls_made,
            input_tokens, output_tokens, model_used, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            inv_id,
            trigger_type,
            trigger_id,
            report.get("title", ""),
            report.get("summary", ""),
            json.dumps(report.get("key_findings", [])),
            report.get("risk_assessment", "medium"),
            report.get("confidence", 0.5),
            json.dumps(report.get("recommended_actions", [])),
            json.dumps(report.get("entities_of_interest", [])),
            json.dumps(tools_used),
            tool_calls_made,
            total_input_tokens,
            total_output_tokens,
            MODEL,
            now,
        ),
    )
    conn.commit()

    result = {
        "investigation_id": inv_id,
        "trigger_type": trigger_type,
        "trigger_id": trigger_id,
        "report": report,
        "tool_calls_made": tool_calls_made,
        "tools_used": tools_used,
        "model": MODEL,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
    logger.info("Investigation complete: %s (tools=%d, tokens=%d+%d)",
                inv_id, tool_calls_made, total_input_tokens, total_output_tokens)
    return result


def get_investigation(conn, investigation_id: str) -> dict | None:
    """Retrieve a stored investigation by ID."""
    row = conn.execute(
        "SELECT * FROM investigations WHERE id = ?", (investigation_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    for field in ("key_findings", "recommended_actions",
                  "entities_of_interest", "sources_consulted"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def list_investigations(conn, limit: int = 20) -> list[dict]:
    """List recent investigations."""
    rows = conn.execute(
        """SELECT id, trigger_type, trigger_id, title, risk_assessment,
                  confidence, tool_calls_made, created_at
           FROM investigations ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def auto_investigate_anomalies(conn, severity_threshold: int = 90,
                                max_investigations: int = 3) -> list[dict]:
    """
    Auto-trigger investigations for recent high-severity events
    that haven't been investigated yet.
    """
    rows = conn.execute(
        """SELECT e.id FROM events e
           LEFT JOIN investigations i
             ON i.trigger_type = 'event' AND i.trigger_id = e.id
           WHERE e.severity >= ?
             AND i.id IS NULL
             AND julianday('now') - julianday(e.timestamp) <= 1
           ORDER BY e.severity DESC
           LIMIT ?""",
        (severity_threshold, max_investigations),
    ).fetchall()

    results = []
    for row in rows:
        result = investigate(conn, "event", row["id"])
        results.append(result)
    return results
