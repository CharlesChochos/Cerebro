"""
Natural language query API routes.
"""
import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None


@router.post("/query")
def post_query(req: QueryRequest):
    """
    Answer a natural language question about global intelligence.

    Optionally include a session_id for multi-turn conversation.
    """
    from intelligence.query import ask

    conn = get_db()

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if len(req.question) > 2000:
        raise HTTPException(status_code=400, detail="Question too long (max 2000 chars)")

    result = ask(conn, req.question, session_id=req.session_id)

    if "error" in result:
        if result["error"] == "no_api_key":
            raise HTTPException(status_code=503, detail="Claude API key not configured")
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/sessions")
def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List conversation sessions, most recent first."""
    conn = get_db()
    rows = conn.execute(
        """SELECT s.id, s.title, s.created_at, s.updated_at,
                  COUNT(t.id) as turn_count
           FROM conversation_sessions s
           LEFT JOIN conversation_turns t ON t.session_id = s.id
           GROUP BY s.id
           ORDER BY s.updated_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()

    total = conn.execute("SELECT COUNT(*) FROM conversation_sessions").fetchone()[0]

    return {
        "sessions": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Get a conversation session with all its turns."""
    conn = get_db()
    session = conn.execute(
        "SELECT * FROM conversation_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    turns = conn.execute(
        """SELECT id, turn_number, question, answer, event_ids, entity_ids,
                  grounding_score, suggested_questions, model_used,
                  input_tokens, output_tokens, created_at
           FROM conversation_turns
           WHERE session_id = ?
           ORDER BY turn_number ASC""",
        (session_id,),
    ).fetchall()

    turn_list = []
    for t in turns:
        td = dict(t)
        for field in ("event_ids", "entity_ids", "suggested_questions"):
            if td.get(field) and isinstance(td[field], str):
                try:
                    td[field] = json.loads(td[field])
                except json.JSONDecodeError:
                    pass
        turn_list.append(td)

    return {
        "session": dict(session),
        "turns": turn_list,
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete a conversation session and all its turns."""
    conn = get_db()
    session = conn.execute(
        "SELECT id FROM conversation_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    conn.execute("DELETE FROM conversation_turns WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM conversation_sessions WHERE id = ?", (session_id,))
    conn.commit()

    return {"deleted": session_id}
