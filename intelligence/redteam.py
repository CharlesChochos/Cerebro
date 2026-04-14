"""
Red team analysis — devil's advocate counterarguments.

Automatically triggered for:
- High-severity events (>= 85)
- High-confidence fusion signals (>= 0.8)
- Intelligence briefs

Challenges assumptions, proposes alternative hypotheses, and suggests
confidence adjustments. Prevents groupthink and confirmation bias.
"""
import json
import logging
import uuid

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

RED_TEAM_PROMPT = """You are a senior intelligence analyst assigned to RED TEAM duty.
Your job is to challenge the analysis below and find weaknesses.

TARGET TYPE: {target_type}
TARGET:
{target_text}

SUPPORTING EVIDENCE:
{evidence_text}

Your tasks:

1. **Counterarguments**: For each major claim, provide a credible counterargument.
   Consider: source reliability, information gaps, potential disinformation,
   alternative interpretations, historical precedent for false positives.

2. **Alternative Hypotheses**: Propose 2-3 alternative explanations for the
   observed pattern that are consistent with the same evidence.

3. **Confidence Assessment**: Should the original confidence be adjusted?
   Consider information quality, source diversity, and analytical rigor.

4. **Blind Spots**: What information is MISSING that would be needed to
   confirm or deny this analysis? What sources haven't been checked?

Respond with a JSON object:
{{
  "counterarguments": [
    {{"claim": "original claim being challenged", "counter": "why it might be wrong", "severity": "low|medium|high"}}
  ],
  "alternative_hypotheses": [
    {{"hypothesis": "alternative explanation", "plausibility": 0.0-1.0, "evidence_for": "what supports this alternative"}}
  ],
  "confidence_adjustment": -0.X to +0.X,
  "adjustment_reasoning": "why confidence should change",
  "blind_spots": ["missing information 1", "missing information 2"],
  "overall_assessment": "one paragraph summary of red team findings"
}}
"""


def format_event_for_redteam(conn, event_id: str) -> tuple[str, str]:
    """Format an event and its evidence for red team analysis."""
    row = conn.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if not row:
        return "", ""

    event = dict(row)
    target = (
        f"Event: {event['title']}\n"
        f"Source: {event['source']}\n"
        f"Category: {event.get('category', '?')}\n"
        f"Severity: {event.get('severity', '?')}\n"
        f"Confidence: {event.get('confidence', '?')}\n"
        f"Summary: {event.get('summary', 'N/A')}\n"
        f"Country: {event.get('country_code', '?')}\n"
        f"Timestamp: {event.get('timestamp', '?')}"
    )

    # Gather corroborating events from same region/category
    related = conn.execute(
        """SELECT source, title, severity, timestamp
           FROM events
           WHERE id != ? AND (region = ? OR category = ?)
           AND julianday('now') - julianday(timestamp) <= 3
           ORDER BY severity DESC LIMIT 10""",
        (event_id, event.get("region"), event.get("category")),
    ).fetchall()

    evidence_lines = [
        f"- ({r['source']}) sev={r['severity']}: {r['title']}" for r in related
    ]
    evidence = "\n".join(evidence_lines) if evidence_lines else "(no corroborating events found)"

    return target, evidence


def format_brief_for_redteam(conn, brief_id: str) -> tuple[str, str]:
    """Format a brief for red team analysis."""
    row = conn.execute(
        "SELECT * FROM briefs WHERE id = ?", (brief_id,)
    ).fetchone()
    if not row:
        return "", ""

    brief = dict(row)
    target = (
        f"Brief Type: {brief['brief_type']}\n"
        f"Title: {brief['title']}\n"
        f"Grounding Score: {brief.get('grounding_score', '?')}\n\n"
        f"{brief['content'][:2000]}"
    )

    evidence = f"Grounding score: {brief.get('grounding_score', 'N/A')}"
    event_ids = json.loads(brief.get("event_ids", "[]"))
    if event_ids:
        events = conn.execute(
            f"SELECT source, title, severity FROM events WHERE id IN ({','.join('?' * len(event_ids))})",
            event_ids,
        ).fetchall()
        evidence += "\nReferenced events:\n" + "\n".join(
            f"- ({e['source']}) sev={e['severity']}: {e['title']}" for e in events
        )

    return target, evidence


def format_fusion_for_redteam(conn, signal_id: str) -> tuple[str, str]:
    """Format a fusion signal for red team analysis."""
    row = conn.execute(
        "SELECT * FROM fusion_signals WHERE id = ?", (signal_id,)
    ).fetchone()
    if not row:
        return "", ""

    sig = dict(row)
    target = (
        f"Signal Type: {sig['signal_type']}\n"
        f"Title: {sig['title']}\n"
        f"Severity: {sig['severity']}\n"
        f"Confidence: {sig['confidence']}\n"
        f"Grounding Score: {sig.get('grounding_score', '?')}\n\n"
        f"{sig['description']}"
    )

    event_ids = json.loads(sig.get("event_ids", "[]"))
    if event_ids:
        events = conn.execute(
            f"SELECT source, title, severity, category FROM events WHERE id IN ({','.join('?' * len(event_ids))})",
            event_ids,
        ).fetchall()
        evidence = "Correlated events:\n" + "\n".join(
            f"- ({e['source']}) {e['category']} sev={e['severity']}: {e['title']}" for e in events
        )
    else:
        evidence = "(no source events referenced)"

    return target, evidence


def run_red_team(conn, target_type: str, target_id: str) -> dict:
    """
    Run red team analysis on an event, brief, or fusion signal.

    Args:
        target_type: "event", "brief", or "fusion_signal"
        target_id: ID of the target

    Returns stats dict with analysis results.
    """
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping red team")
        return {"error": "no_api_key"}

    formatters = {
        "event": format_event_for_redteam,
        "brief": format_brief_for_redteam,
        "fusion_signal": format_fusion_for_redteam,
    }

    formatter = formatters.get(target_type)
    if not formatter:
        return {"error": f"unknown target_type: {target_type}"}

    target_text, evidence_text = formatter(conn, target_id)
    if not target_text:
        return {"error": f"{target_type} not found: {target_id}"}

    prompt = RED_TEAM_PROMPT.format(
        target_type=target_type,
        target_text=target_text,
        evidence_text=evidence_text,
    )

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()
        analysis = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("Red team JSON parse error: %s", e)
        return {"error": "json_parse"}
    except anthropic.APIError as e:
        logger.error("Red team API error: %s", e)
        return {"error": str(e)}

    # Store the analysis
    conn.execute(
        """INSERT INTO red_team_analyses
           (id, target_type, target_id, counterarguments, alternative_hypotheses,
            confidence_adjustment, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            str(uuid.uuid4()),
            target_type,
            target_id,
            json.dumps(analysis.get("counterarguments", [])),
            json.dumps(analysis.get("alternative_hypotheses", [])),
            analysis.get("confidence_adjustment", 0.0),
            MODEL,
        ),
    )
    conn.commit()

    stats = {
        "target_type": target_type,
        "target_id": target_id,
        "counterarguments": len(analysis.get("counterarguments", [])),
        "alternative_hypotheses": len(analysis.get("alternative_hypotheses", [])),
        "confidence_adjustment": analysis.get("confidence_adjustment", 0),
        "overall_assessment": analysis.get("overall_assessment", ""),
        "model": MODEL,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    logger.info("Red team analysis: %s", stats)
    return stats


def auto_red_team_events(conn, severity_threshold: int = 85) -> list[dict]:
    """
    Auto-trigger red team on recent high-severity events that
    haven't been analyzed yet.
    """
    rows = conn.execute(
        """SELECT e.id FROM events e
           LEFT JOIN red_team_analyses r
             ON r.target_type = 'event' AND r.target_id = e.id
           WHERE e.severity >= ?
             AND r.id IS NULL
             AND julianday('now') - julianday(e.timestamp) <= 1
           ORDER BY e.severity DESC
           LIMIT 5""",
        (severity_threshold,),
    ).fetchall()

    results = []
    for row in rows:
        result = run_red_team(conn, "event", row["id"])
        results.append(result)

    return results


def auto_red_team_fusion(conn, confidence_threshold: float = 0.8) -> list[dict]:
    """
    Auto-trigger red team on high-confidence fusion signals
    that haven't been analyzed yet.
    """
    rows = conn.execute(
        """SELECT f.id FROM fusion_signals f
           LEFT JOIN red_team_analyses r
             ON r.target_type = 'fusion_signal' AND r.target_id = f.id
           WHERE f.confidence >= ?
             AND r.id IS NULL
             AND julianday('now') - julianday(f.created_at) <= 1
           ORDER BY f.severity DESC
           LIMIT 3""",
        (confidence_threshold,),
    ).fetchall()

    results = []
    for row in rows:
        result = run_red_team(conn, "fusion_signal", row["id"])
        results.append(result)

    return results
