"""
Webhook system — fires notifications to external endpoints with HMAC signing.

Supports event types: alert, risk_threshold, velocity_spike, new_brief, new_report.
Delivery is tracked in webhook_log with retry info.
"""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = 10  # seconds


def create_webhook(
    conn,
    name: str,
    url: str,
    event_types: list[str],
    secret: str | None = None,
    filters: dict | None = None,
) -> dict:
    """Register a new webhook endpoint."""
    wh_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO webhooks (id, name, url, secret, event_types, filters, active)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (wh_id, name, url, secret, json.dumps(event_types), json.dumps(filters or {})),
    )
    conn.commit()
    return {
        "id": wh_id,
        "name": name,
        "url": url,
        "event_types": event_types,
        "filters": filters or {},
        "active": True,
    }


def list_webhooks(conn, active_only: bool = True) -> list[dict]:
    """List all registered webhooks."""
    query = "SELECT * FROM webhooks"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["event_types"] = json.loads(d["event_types"]) if d["event_types"] else []
        d["filters"] = json.loads(d["filters"]) if d["filters"] else {}
        result.append(d)
    return result


def get_webhook(conn, webhook_id: str) -> dict | None:
    """Get a single webhook by ID."""
    row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["event_types"] = json.loads(d["event_types"]) if d["event_types"] else []
    d["filters"] = json.loads(d["filters"]) if d["filters"] else {}
    return d


def update_webhook(conn, webhook_id: str, **kwargs) -> dict | None:
    """Update webhook fields (name, url, secret, event_types, filters, active)."""
    wh = get_webhook(conn, webhook_id)
    if not wh:
        return None

    updatable = {"name", "url", "secret", "active"}
    sets = []
    params = []
    for key, val in kwargs.items():
        if key in updatable:
            sets.append(f"{key} = ?")
            params.append(val)
        elif key == "event_types":
            sets.append("event_types = ?")
            params.append(json.dumps(val))
        elif key == "filters":
            sets.append("filters = ?")
            params.append(json.dumps(val))

    if not sets:
        return wh

    params.append(webhook_id)
    conn.execute(f"UPDATE webhooks SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    return get_webhook(conn, webhook_id)


def delete_webhook(conn, webhook_id: str) -> bool:
    """Delete a webhook."""
    cursor = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    conn.commit()
    return cursor.rowcount > 0


def sign_payload(secret: str, payload: str) -> str:
    """Generate HMAC-SHA256 signature for a payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(secret: str, payload: str, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature."""
    expected = sign_payload(secret, payload)
    return hmac.compare_digest(expected, signature)


def _matches_filters(webhook_filters: dict, event_data: dict) -> bool:
    """Check if an event matches the webhook's filters."""
    if not webhook_filters:
        return True

    if "country_code" in webhook_filters and webhook_filters["country_code"]:
        if event_data.get("country_code") != webhook_filters["country_code"]:
            return False

    if "category" in webhook_filters and webhook_filters["category"]:
        if event_data.get("category") != webhook_filters["category"]:
            return False

    if "severity_min" in webhook_filters and webhook_filters["severity_min"]:
        if (event_data.get("severity") or 0) < webhook_filters["severity_min"]:
            return False

    return True


def fire_webhook(conn, webhook: dict, event_type: str, payload: dict) -> dict:
    """Fire a single webhook — send HTTP POST with optional HMAC signature."""
    log_id = str(uuid.uuid4())
    payload_str = json.dumps(payload, default=str)

    headers = {
        "Content-Type": "application/json",
        "X-Cerebro-Event": event_type,
        "X-Cerebro-Webhook-Id": webhook["id"],
        "X-Cerebro-Timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if webhook.get("secret"):
        sig = sign_payload(webhook["secret"], payload_str)
        headers["X-Cerebro-Signature"] = f"sha256={sig}"

    status_code = None
    response_body = None
    success = False

    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT) as client:
            resp = client.post(webhook["url"], content=payload_str, headers=headers)
            status_code = resp.status_code
            response_body = resp.text[:500]  # cap stored response
            success = 200 <= resp.status_code < 300
    except httpx.TimeoutException:
        response_body = "Timeout"
    except httpx.RequestError as e:
        response_body = str(e)[:500]

    # Log delivery
    conn.execute(
        """INSERT INTO webhook_log (id, webhook_id, event_type, payload, status_code, response_body, success)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (log_id, webhook["id"], event_type, payload_str, status_code, response_body, int(success)),
    )

    # Update webhook stats
    if success:
        conn.execute(
            "UPDATE webhooks SET last_fired = ?, fire_count = fire_count + 1 WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), webhook["id"]),
        )
    else:
        conn.execute(
            "UPDATE webhooks SET error_count = error_count + 1, last_error = ? WHERE id = ?",
            (response_body, webhook["id"]),
        )
    conn.commit()

    return {
        "log_id": log_id,
        "webhook_id": webhook["id"],
        "event_type": event_type,
        "status_code": status_code,
        "success": success,
        "response": response_body,
    }


def dispatch_event(conn, event_type: str, event_data: dict) -> list[dict]:
    """Dispatch an event to all matching active webhooks."""
    webhooks = list_webhooks(conn, active_only=True)
    results = []

    for wh in webhooks:
        if event_type not in wh["event_types"]:
            continue
        if not _matches_filters(wh.get("filters", {}), event_data):
            continue

        result = fire_webhook(conn, wh, event_type, event_data)
        results.append(result)

    return results


def get_webhook_logs(conn, webhook_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get webhook delivery logs."""
    if webhook_id:
        rows = conn.execute(
            "SELECT * FROM webhook_log WHERE webhook_id = ? ORDER BY fired_at DESC LIMIT ?",
            (webhook_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM webhook_log ORDER BY fired_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
