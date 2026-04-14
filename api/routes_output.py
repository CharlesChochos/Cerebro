"""
Phase 11 API — Output, Distribution & External Interfaces.

Country profiles, weekly reports, webhooks, embed widgets.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db
from intelligence.reports import generate_country_profile, generate_weekly_report
from intelligence.webhooks import (
    create_webhook,
    list_webhooks,
    get_webhook,
    update_webhook,
    delete_webhook,
    dispatch_event,
    get_webhook_logs,
)
from intelligence.widgets import (
    create_embed_token,
    validate_token,
    list_tokens,
    revoke_token,
    get_widget_data,
)

router = APIRouter(prefix="/api", tags=["output"])


# ─── Country Profiles ────────────────────────────────────────

class CountryProfileRequest(BaseModel):
    country_code: str
    country_name: str
    days: int = 7


@router.post("/reports/country-profile")
def create_country_profile(req: CountryProfileRequest):
    """Generate a country risk profile."""
    conn = get_db()
    profile = generate_country_profile(conn, req.country_code, req.country_name, req.days)
    return profile


@router.get("/reports/country-profiles")
def list_country_profiles(
    country_code: str | None = None,
    limit: int = Query(default=20, le=100),
):
    """List generated country profiles."""
    conn = get_db()
    query = "SELECT * FROM country_profiles"
    params = []
    if country_code:
        query += " WHERE country_code = ?"
        params.append(country_code)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return {
        "total": len(rows),
        "profiles": [dict(r) for r in rows],
    }


@router.get("/reports/country-profiles/{profile_id}")
def get_country_profile(profile_id: str):
    """Get a specific country profile."""
    conn = get_db()
    row = conn.execute("SELECT * FROM country_profiles WHERE id = ?", (profile_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return dict(row)


# ─── Weekly Reports ──────────────────────────────────────────

@router.post("/reports/weekly")
def create_weekly_report():
    """Generate a new weekly report."""
    conn = get_db()
    report = generate_weekly_report(conn)
    return report


@router.get("/reports/weekly")
def list_weekly_reports(limit: int = Query(default=10, le=50)):
    """List generated weekly reports."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM weekly_reports ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {
        "total": len(rows),
        "reports": [dict(r) for r in rows],
    }


@router.get("/reports/weekly/{report_id}")
def get_weekly_report(report_id: str):
    """Get a specific weekly report."""
    conn = get_db()
    row = conn.execute("SELECT * FROM weekly_reports WHERE id = ?", (report_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return dict(row)


# ─── Webhooks ────────────────────────────────────────────────

class WebhookCreateRequest(BaseModel):
    name: str
    url: str
    event_types: list[str]
    secret: str | None = None
    filters: dict | None = None


class WebhookUpdateRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    secret: str | None = None
    event_types: list[str] | None = None
    filters: dict | None = None
    active: bool | None = None


class WebhookTestRequest(BaseModel):
    event_type: str = "test"
    payload: dict | None = None


@router.post("/webhooks")
def create_webhook_endpoint(req: WebhookCreateRequest):
    """Register a new webhook."""
    conn = get_db()
    wh = create_webhook(
        conn, req.name, req.url, req.event_types, req.secret, req.filters,
    )
    return wh


@router.get("/webhooks")
def list_webhooks_endpoint(active_only: bool = True):
    """List webhooks."""
    conn = get_db()
    hooks = list_webhooks(conn, active_only)
    return {"total": len(hooks), "webhooks": hooks}


@router.get("/webhooks/{webhook_id}")
def get_webhook_endpoint(webhook_id: str):
    """Get a webhook by ID."""
    conn = get_db()
    wh = get_webhook(conn, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return wh


@router.patch("/webhooks/{webhook_id}")
def update_webhook_endpoint(webhook_id: str, req: WebhookUpdateRequest):
    """Update a webhook."""
    conn = get_db()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    wh = update_webhook(conn, webhook_id, **updates)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return wh


@router.delete("/webhooks/{webhook_id}")
def delete_webhook_endpoint(webhook_id: str):
    """Delete a webhook."""
    conn = get_db()
    if not delete_webhook(conn, webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": True}


@router.post("/webhooks/{webhook_id}/test")
def test_webhook_endpoint(webhook_id: str, req: WebhookTestRequest):
    """Send a test payload to a webhook."""
    conn = get_db()
    wh = get_webhook(conn, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    from intelligence.webhooks import fire_webhook
    payload = req.payload or {"test": True, "message": "Cerebro webhook test"}
    result = fire_webhook(conn, wh, req.event_type, payload)
    return result


@router.get("/webhooks/{webhook_id}/logs")
def get_webhook_logs_endpoint(webhook_id: str, limit: int = Query(default=50, le=200)):
    """Get delivery logs for a webhook."""
    conn = get_db()
    logs = get_webhook_logs(conn, webhook_id, limit)
    return {"total": len(logs), "logs": logs}


@router.post("/webhooks/dispatch")
def dispatch_event_endpoint(event_type: str, payload: dict):
    """Manually dispatch an event to all matching webhooks."""
    conn = get_db()
    results = dispatch_event(conn, event_type, payload)
    return {"dispatched": len(results), "results": results}


# ─── Embed Widgets ───────────────────────────────────────────

class EmbedTokenRequest(BaseModel):
    widget_type: str  # risk_score, event_feed, alert_ticker
    scope: dict | None = None
    hours_valid: int = 168


@router.post("/widgets/tokens")
def create_widget_token(req: EmbedTokenRequest):
    """Create an embeddable widget token."""
    conn = get_db()
    valid_types = {"risk_score", "event_feed", "alert_ticker"}
    if req.widget_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid widget type. Must be one of: {valid_types}")
    token = create_embed_token(conn, req.widget_type, req.scope, req.hours_valid)
    return token


@router.get("/widgets/tokens")
def list_widget_tokens(active_only: bool = True):
    """List embed tokens."""
    conn = get_db()
    tokens = list_tokens(conn, active_only)
    return {"total": len(tokens), "tokens": tokens}


@router.delete("/widgets/tokens/{token_id}")
def revoke_widget_token(token_id: str):
    """Revoke an embed token."""
    conn = get_db()
    if not revoke_token(conn, token_id):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"revoked": True}


@router.get("/widgets/embed")
def get_widget_embed(token: str):
    """Get widget data using an embed token."""
    conn = get_db()
    token_data = validate_token(conn, token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    data = get_widget_data(conn, token_data)
    return data
