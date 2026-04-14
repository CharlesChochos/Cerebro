"""
Event classification using Claude API (Haiku).

Classifies events into categories with severity and confidence scores.
Designed to be called on unclassified or GDELT-pre-classified events
to get richer, more accurate classification from Claude.
"""
import json
import logging

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

# Use Haiku for classification — cheapest and fast enough
MODEL = "claude-haiku-4-5-20251001"

CLASSIFICATION_PROMPT = """You are an intelligence analyst classifying global events.

Given the event below, provide:
1. **category**: exactly one of: military, economic, health, political, environmental
2. **severity**: integer 0-100 (0=routine, 50=notable, 75=significant, 90+=critical)
3. **confidence**: float 0.0-1.0 in your classification
4. **summary**: one-sentence intelligence summary (what happened, where, why it matters)

Event:
Title: {title}
Current Summary: {summary}
Source: {source}
Country: {country_code}
Existing Category: {category}

Respond ONLY with valid JSON, no other text:
{{"category": "...", "severity": N, "confidence": N.N, "summary": "..."}}"""


def classify_event(event: dict) -> dict | None:
    """
    Classify a single event using Claude Haiku.
    Returns dict with category, severity, confidence, summary or None on error.
    """
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY set — skipping classification")
        return None

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    prompt = CLASSIFICATION_PROMPT.format(
        title=event.get("title", ""),
        summary=event.get("summary", ""),
        source=event.get("source", ""),
        country_code=event.get("country_code", ""),
        category=event.get("category", "unknown"),
    )

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()

        # Parse JSON response
        result = json.loads(content)

        # Validate fields
        valid_categories = {"military", "economic", "health", "political", "environmental"}
        if result.get("category") not in valid_categories:
            logger.warning("Invalid category from Claude: %s", result.get("category"))
            return None

        severity = result.get("severity", 0)
        if not isinstance(severity, (int, float)) or severity < 0 or severity > 100:
            severity = max(0, min(100, int(severity)))

        confidence = result.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            confidence = max(0.0, min(1.0, float(confidence)))

        return {
            "category": result["category"],
            "severity": round(severity),
            "confidence": round(confidence, 2),
            "summary": result.get("summary", ""),
        }

    except json.JSONDecodeError as e:
        logger.error("Failed to parse Claude response as JSON: %s", e)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error: %s", e)
        return None


def classify_batch(conn, limit: int = 50) -> dict:
    """
    Classify unclassified or low-confidence events in the database.
    Returns stats dict.
    """
    # Find events that need classification:
    # - severity is 0 (unclassified by Claude)
    # - OR confidence is below 0.3 (low confidence from GDELT heuristic)
    rows = conn.execute(
        """SELECT id, title, summary, source, country_code, category
           FROM events
           WHERE severity = 0 OR confidence < 0.3
           ORDER BY ingested_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    classified = 0
    errors = 0

    for row in rows:
        event = dict(row)
        result = classify_event(event)
        if result is None:
            errors += 1
            continue

        conn.execute(
            """UPDATE events
               SET category = ?, severity = ?, confidence = ?, summary = ?
               WHERE id = ?""",
            (
                result["category"],
                result["severity"],
                result["confidence"],
                result["summary"],
                event["id"],
            ),
        )
        classified += 1

    conn.commit()

    stats = {
        "total_candidates": len(rows),
        "classified": classified,
        "errors": errors,
    }
    logger.info("Classification batch: %s", stats)
    return stats
