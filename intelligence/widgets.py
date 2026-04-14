"""
Embeddable widget token system — time-limited tokens for public widget access.

Tokens grant read-only access to specific widget types (risk_score, event_feed,
alert_ticker) scoped to country/category/entity. Expired or deactivated tokens
are rejected at the API layer.
"""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta

TOKEN_LENGTH = 32  # 256-bit random token


def generate_token() -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(TOKEN_LENGTH)


def create_embed_token(
    conn,
    widget_type: str,
    scope: dict | None = None,
    hours_valid: int = 168,  # 1 week default
) -> dict:
    """Create a new embeddable widget token."""
    token_id = str(uuid.uuid4())
    token = generate_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours_valid)).isoformat()

    conn.execute(
        """INSERT INTO embed_tokens (id, token, widget_type, scope, expires_at, active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (token_id, token, widget_type, json.dumps(scope or {}), expires_at),
    )
    conn.commit()

    return {
        "id": token_id,
        "token": token,
        "widget_type": widget_type,
        "scope": scope or {},
        "expires_at": expires_at,
        "active": True,
    }


def validate_token(conn, token: str) -> dict | None:
    """Validate a token — returns token data if valid, None if invalid/expired."""
    row = conn.execute(
        "SELECT * FROM embed_tokens WHERE token = ? AND active = 1",
        (token,),
    ).fetchone()

    if not row:
        return None

    d = dict(row)

    # Check expiry
    expires_at = datetime.fromisoformat(d["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        return None

    # Increment access count
    conn.execute(
        "UPDATE embed_tokens SET access_count = access_count + 1 WHERE id = ?",
        (d["id"],),
    )
    conn.commit()

    d["scope"] = json.loads(d["scope"]) if d["scope"] else {}
    return d


def list_tokens(conn, active_only: bool = True) -> list[dict]:
    """List embed tokens."""
    query = "SELECT * FROM embed_tokens"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY created_at DESC"

    rows = conn.execute(query).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["scope"] = json.loads(d["scope"]) if d["scope"] else {}
        result.append(d)
    return result


def revoke_token(conn, token_id: str) -> bool:
    """Deactivate a token."""
    cursor = conn.execute(
        "UPDATE embed_tokens SET active = 0 WHERE id = ?",
        (token_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_widget_data(conn, token_data: dict) -> dict:
    """Fetch widget data based on token type and scope."""
    widget_type = token_data["widget_type"]
    scope = token_data.get("scope", {})

    if widget_type == "risk_score":
        return _get_risk_score_widget(conn, scope)
    elif widget_type == "event_feed":
        return _get_event_feed_widget(conn, scope)
    elif widget_type == "alert_ticker":
        return _get_alert_ticker_widget(conn, scope)
    else:
        return {"error": f"Unknown widget type: {widget_type}"}


def _get_risk_score_widget(conn, scope: dict) -> dict:
    """Risk score widget data."""
    if scope.get("country_code"):
        row = conn.execute(
            """SELECT score, trend, updated_at FROM risk_scores
               WHERE scope_type = 'country' AND scope_value = ?
               ORDER BY updated_at DESC LIMIT 1""",
            (scope["country_code"],),
        ).fetchone()
        if row:
            return {
                "widget_type": "risk_score",
                "scope": scope,
                "score": row["score"],
                "trend": row["trend"],
                "updated_at": row["updated_at"],
            }

    # Global fallback
    row = conn.execute(
        """SELECT AVG(score) as avg_score FROM risk_scores
           WHERE scope_type = 'country'"""
    ).fetchone()
    return {
        "widget_type": "risk_score",
        "scope": scope,
        "score": round(row["avg_score"] or 0, 1),
        "trend": "stable",
    }


def _get_event_feed_widget(conn, scope: dict) -> dict:
    """Event feed widget — recent events."""
    query = "SELECT id, title, category, severity, country_code, timestamp FROM events"
    params = []
    conditions = []

    if scope.get("country_code"):
        conditions.append("country_code = ?")
        params.append(scope["country_code"])
    if scope.get("category"):
        conditions.append("category = ?")
        params.append(scope["category"])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp DESC LIMIT 20"

    rows = conn.execute(query, params).fetchall()
    return {
        "widget_type": "event_feed",
        "scope": scope,
        "events": [dict(r) for r in rows],
        "count": len(rows),
    }


def _get_alert_ticker_widget(conn, scope: dict) -> dict:
    """Alert ticker widget — active alerts."""
    query = "SELECT id, title, severity, alert_type, created_at FROM alerts WHERE acknowledged = 0"
    params = []

    if scope.get("country_code"):
        query += " AND country_code = ?"
        params.append(scope["country_code"])

    query += " ORDER BY severity DESC LIMIT 10"
    rows = conn.execute(query, params).fetchall()
    return {
        "widget_type": "alert_ticker",
        "scope": scope,
        "alerts": [dict(r) for r in rows],
        "count": len(rows),
    }
