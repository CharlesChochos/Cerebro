"""
Natural language query engine for Cerebro.

Answers user questions in plain English using:
- Recent events from the database
- Entity graph for relationships
- Compressed world state for context
- Conversation history for multi-turn follow-up

Every answer must reference specific event IDs (grounding).
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from config.settings import CLAUDE_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are Cerebro, an advanced intelligence analysis assistant.
You answer questions about global events, geopolitical developments, and security situations
using ONLY the source data provided to you.

CRITICAL RULES:
1. Every factual claim MUST cite specific event IDs in square brackets like [evt-abc123]
2. NEVER invent or hallucinate events, entities, or facts not in the provided data
3. If you don't have enough information, say so honestly
4. Distinguish between confirmed facts (from events) and your analytical judgments
5. When referencing entities, use their exact names from the entity data
6. Keep answers focused and actionable — this is for intelligence professionals

CONTEXT DATA:
{context}

At the end of your response, provide a JSON metadata block:
```json
{{
  "event_ids_referenced": ["id1", "id2"],
  "entity_ids_referenced": ["eid1"],
  "suggested_questions": [
    "Follow-up question 1 based on the answer",
    "Follow-up question 2 exploring a related angle",
    "Follow-up question 3 going deeper on a key point"
  ]
}}
```

The suggested questions should be specific, contextual, and help the user explore
the intelligence landscape further. Make them concrete, not generic.
"""


def build_context(conn, question: str) -> tuple[str, set, set]:
    """
    Build context for answering a question.

    Uses keyword matching against FTS5 index plus recent high-severity events.
    Returns (context_text, valid_event_ids, valid_entity_ids).
    """
    sections = []
    valid_event_ids: set[str] = set()
    valid_entity_ids: set[str] = set()

    # 1. FTS5 search for events matching the question
    fts_events = _search_events_fts(conn, question)
    if fts_events:
        sections.append("## Events Matching Your Query")
        for e in fts_events:
            sections.append(_format_event(e))
            valid_event_ids.add(e["id"])

    # 2. Recent high-severity events (always included for context)
    recent = _get_recent_events(conn, hours=48, min_severity=50, limit=30)
    new_recent = [e for e in recent if e["id"] not in valid_event_ids]
    if new_recent:
        sections.append("\n## Recent High-Severity Events")
        for e in new_recent[:20]:
            sections.append(_format_event(e))
            valid_event_ids.add(e["id"])

    # 3. Entity graph
    entities = _get_entities(conn, limit=25)
    if entities:
        sections.append("\n## Key Entities")
        for ent in entities:
            sections.append(f"[{ent['id']}] {ent['name']} ({ent['entity_type']}) — {ent['event_count']} events")
            valid_entity_ids.add(ent["id"])

    # 4. World state (compressed institutional memory)
    world_state = _get_world_state(conn)
    if world_state:
        sections.append(f"\n## Current World State (as of {world_state['date']})")
        sections.append(world_state["content"])

    # 5. Active fusion signals
    fusion = _get_fusion_signals(conn)
    if fusion:
        sections.append("\n## Active Fusion Signals")
        for f in fusion:
            sections.append(
                f"- {f['signal_type']}: {f['title']} (sev={f['severity']}, "
                f"conf={f['confidence']}, grounding={f.get('grounding_score', '?')})"
            )

    return "\n".join(sections), valid_event_ids, valid_entity_ids


def _search_events_fts(conn, question: str, limit: int = 20) -> list[dict]:
    """Search events using FTS5 full-text index."""
    # Clean the question for FTS5 — extract meaningful keywords
    stop_words = {
        "what", "when", "where", "who", "why", "how", "is", "are", "was",
        "were", "the", "a", "an", "in", "on", "at", "to", "for", "of",
        "and", "or", "but", "not", "with", "about", "tell", "me", "show",
        "latest", "recent", "any", "there", "has", "have", "been", "do",
        "does", "did", "can", "could", "would", "should", "will",
        "happening", "going", "current", "update", "know",
    }
    # Strip punctuation before filtering
    words = [
        w.strip("?!.,;:'\"()-")
        for w in question.lower().split()
    ]
    words = [w for w in words if w.isalpha() and w not in stop_words and len(w) > 2]

    if not words:
        return []

    # Use OR to match any keyword
    fts_query = " OR ".join(words)

    try:
        rows = conn.execute(
            """SELECT e.id, e.source, e.title, e.summary, e.category, e.severity,
                      e.confidence, e.country_code, e.region, e.timestamp
               FROM events_fts fts
               JOIN events e ON e.id = fts.rowid
               WHERE events_fts MATCH ?
               ORDER BY e.severity DESC, e.timestamp DESC
               LIMIT ?""",
            (fts_query, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("FTS search failed (falling back to LIKE): %s", e)
        # Fallback to LIKE search
        return _search_events_like(conn, words, limit)


def _search_events_like(conn, words: list[str], limit: int = 20) -> list[dict]:
    """Fallback search using LIKE when FTS fails."""
    conditions = []
    params: list = []
    for w in words[:5]:
        conditions.append("(title LIKE ? OR summary LIKE ?)")
        params.extend([f"%{w}%", f"%{w}%"])

    if not conditions:
        return []

    where = " OR ".join(conditions)
    rows = conn.execute(
        f"""SELECT id, source, title, summary, category, severity,
                   confidence, country_code, region, timestamp
            FROM events
            WHERE {where}
            ORDER BY severity DESC, timestamp DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


def _get_recent_events(conn, hours: int = 48, min_severity: int = 50, limit: int = 30) -> list[dict]:
    """Get recent high-severity events."""
    rows = conn.execute(
        """SELECT id, source, title, summary, category, severity,
                  confidence, country_code, region, timestamp
           FROM events
           WHERE julianday('now') - julianday(timestamp) <= ?
             AND severity >= ?
           ORDER BY severity DESC, timestamp DESC
           LIMIT ?""",
        (hours / 24.0, min_severity, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_entities(conn, limit: int = 25) -> list[dict]:
    """Get top entities by event count."""
    rows = conn.execute(
        "SELECT id, name, entity_type, event_count FROM entities ORDER BY event_count DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_world_state(conn) -> dict | None:
    """Get the latest world state."""
    row = conn.execute(
        "SELECT date, content FROM world_state ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _get_fusion_signals(conn, limit: int = 10) -> list[dict]:
    """Get recent active fusion signals."""
    rows = conn.execute(
        """SELECT signal_type, title, severity, confidence, grounding_score
           FROM fusion_signals
           WHERE julianday('now') - julianday(created_at) <= 3
           ORDER BY severity DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _format_event(e: dict) -> str:
    """Format a single event for context injection."""
    line = (
        f"[{e['id']}] ({e['source']}) {e.get('category','?')} sev={e['severity']} "
        f"cc={e.get('country_code','?')} ts={e.get('timestamp','?')} — {e['title']}"
    )
    if e.get("summary"):
        line += f"\n    {e['summary'][:300]}"
    return line


def _build_conversation_messages(
    conn, session_id: str | None, question: str, context: str
) -> list[dict]:
    """
    Build the messages array for Claude, including conversation history.
    """
    messages = []

    # Load previous turns from this session
    if session_id:
        turns = conn.execute(
            """SELECT question, answer FROM conversation_turns
               WHERE session_id = ?
               ORDER BY turn_number ASC
               LIMIT 10""",
            (session_id,),
        ).fetchall()

        for turn in turns:
            messages.append({"role": "user", "content": turn["question"]})
            # Strip the JSON metadata block from previous answers
            answer = turn["answer"]
            json_start = answer.rfind("```json")
            if json_start != -1:
                answer = answer[:json_start].strip()
            messages.append({"role": "assistant", "content": answer})

    # Add the current question
    messages.append({"role": "user", "content": question})

    return messages


def extract_metadata(content: str) -> tuple[str, dict]:
    """Extract the JSON metadata block from the response."""
    metadata = {
        "event_ids_referenced": [],
        "entity_ids_referenced": [],
        "suggested_questions": [],
    }

    json_start = content.rfind("```json")
    if json_start == -1:
        return content, metadata

    json_end = content.rfind("```", json_start + 7)
    if json_end == -1:
        return content, metadata

    json_text = content[json_start + 7:json_end].strip()
    answer_text = content[:json_start].strip()

    try:
        parsed = json.loads(json_text)
        if isinstance(parsed, dict):
            metadata["event_ids_referenced"] = parsed.get("event_ids_referenced", [])
            metadata["entity_ids_referenced"] = parsed.get("entity_ids_referenced", [])
            metadata["suggested_questions"] = parsed.get("suggested_questions", [])[:3]
    except json.JSONDecodeError:
        logger.warning("Failed to parse query response metadata")

    return answer_text, metadata


def compute_grounding(referenced_ids: list, valid_ids: set) -> float:
    """Compute grounding score."""
    if not referenced_ids:
        return 0.0
    valid = sum(1 for eid in referenced_ids if eid in valid_ids)
    return round(valid / len(referenced_ids), 2)


def ask(conn, question: str, session_id: str | None = None) -> dict:
    """
    Answer a natural language question using the intelligence database.

    Args:
        conn: Database connection
        question: User's question in plain English
        session_id: Optional session ID for multi-turn conversation

    Returns dict with answer, metadata, grounding, and session info.
    """
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — cannot answer queries")
        return {"error": "no_api_key"}

    if not question.strip():
        return {"error": "empty_question"}

    # Build context from the database
    context, valid_event_ids, valid_entity_ids = build_context(conn, question)

    # Create or resume session
    if not session_id:
        session_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO conversation_sessions (id, title) VALUES (?, ?)",
            (session_id, question[:100]),
        )

    # Get current turn number
    turn_row = conn.execute(
        "SELECT COALESCE(MAX(turn_number), 0) as max_turn FROM conversation_turns WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    turn_number = turn_row["max_turn"] + 1

    # Build messages with conversation history
    system = SYSTEM_PROMPT.format(context=context)
    messages = _build_conversation_messages(conn, session_id, question, context)

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            system=system,
            messages=messages,
        )
        content = message.content[0].text.strip()
    except anthropic.APIError as e:
        logger.error("Query API error: %s", e)
        return {"error": str(e), "session_id": session_id}

    # Parse answer and metadata
    answer_text, metadata = extract_metadata(content)

    # Compute grounding scores
    event_grounding = compute_grounding(
        metadata["event_ids_referenced"], valid_event_ids
    )
    entity_grounding = compute_grounding(
        metadata["entity_ids_referenced"], valid_entity_ids
    )
    overall_grounding = (
        (event_grounding + entity_grounding) / 2
        if metadata["entity_ids_referenced"]
        else event_grounding
    )

    # Store the turn
    turn_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO conversation_turns
           (id, session_id, turn_number, question, answer, event_ids, entity_ids,
            grounding_score, suggested_questions, model_used, input_tokens, output_tokens)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            turn_id,
            session_id,
            turn_number,
            question,
            answer_text,
            json.dumps(metadata["event_ids_referenced"]),
            json.dumps(metadata["entity_ids_referenced"]),
            overall_grounding,
            json.dumps(metadata["suggested_questions"]),
            MODEL,
            message.usage.input_tokens,
            message.usage.output_tokens,
        ),
    )

    # Update session timestamp
    conn.execute(
        "UPDATE conversation_sessions SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
        (session_id,),
    )
    conn.commit()

    return {
        "answer": answer_text,
        "session_id": session_id,
        "turn_number": turn_number,
        "event_ids_referenced": metadata["event_ids_referenced"],
        "entity_ids_referenced": metadata["entity_ids_referenced"],
        "suggested_questions": metadata["suggested_questions"],
        "grounding_score": overall_grounding,
        "model": MODEL,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
