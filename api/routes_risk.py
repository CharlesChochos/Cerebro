"""
Risk scores, alerts, velocity, and prediction scorecard API routes.
"""
import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.main import get_db

router = APIRouter(prefix="/api", tags=["risk"])


# ── Risk Scores ─────────────────────────────────────────────────────────────


@router.get("/risk")
def list_risk_scores(
    scope_type: str | None = None,
    min_score: float = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List risk scores, optionally filtered by scope type and minimum score."""
    conn = get_db()
    conditions = ["score >= ?"]
    params: list = [min_score]

    if scope_type:
        conditions.append("scope_type = ?")
        params.append(scope_type)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT id, scope_type, scope_value, score, components,
                   event_count, source_count, trend, updated_at
            FROM risk_scores WHERE {where}
            ORDER BY score DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    scores = []
    for r in rows:
        s = dict(r)
        if s.get("components") and isinstance(s["components"], str):
            try:
                s["components"] = json.loads(s["components"])
            except json.JSONDecodeError:
                pass
        scores.append(s)

    return {"scores": scores}


@router.get("/risk/{scope_type}/{scope_value}")
def get_risk_score(scope_type: str, scope_value: str):
    """Get risk score for a specific scope."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM risk_scores WHERE scope_type = ? AND scope_value = ?",
        (scope_type, scope_value),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Risk score not found")
    result = dict(row)
    if result.get("components") and isinstance(result["components"], str):
        try:
            result["components"] = json.loads(result["components"])
        except json.JSONDecodeError:
            pass
    return result


# ── Alerts ──────────────────────────────────────────────────────────────────


@router.get("/alerts")
def list_alerts(
    alert_type: str | None = None,
    acknowledged: bool | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    """List alerts, newest first."""
    conn = get_db()
    conditions = []
    params: list = []

    if alert_type:
        conditions.append("alert_type = ?")
        params.append(alert_type)
    if acknowledged is not None:
        conditions.append("acknowledged = ?")
        params.append(1 if acknowledged else 0)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT id, config_id, alert_type, title, description, severity,
                   scope_type, scope_value, event_ids, acknowledged, created_at
            FROM alert_history {where}
            ORDER BY created_at DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    alerts = []
    for r in rows:
        a = dict(r)
        if a.get("event_ids") and isinstance(a["event_ids"], str):
            try:
                a["event_ids"] = json.loads(a["event_ids"])
            except json.JSONDecodeError:
                pass
        alerts.append(a)

    unack_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM alert_history WHERE acknowledged = 0"
    ).fetchone()["cnt"]

    return {"alerts": alerts, "unacknowledged_count": unack_count}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    conn = get_db()
    row = conn.execute("SELECT id FROM alert_history WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    conn.execute(
        """UPDATE alert_history
           SET acknowledged = 1, acknowledged_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
           WHERE id = ?""",
        (alert_id,),
    )
    conn.commit()
    return {"acknowledged": alert_id}


class AlertConfigRequest(BaseModel):
    name: str
    scope_type: str
    scope_value: str | None = None
    min_severity: int = 70
    min_risk_score: int = 60
    categories: list[str] | None = None
    cooldown_minutes: int = 60


@router.post("/alerts/configure")
def configure_alert(req: AlertConfigRequest):
    """Create or update an alert configuration."""
    import uuid
    conn = get_db()
    config_id = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO alert_configs
           (id, name, scope_type, scope_value, min_severity, min_risk_score,
            categories, cooldown_minutes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            config_id, req.name, req.scope_type, req.scope_value,
            req.min_severity, req.min_risk_score,
            json.dumps(req.categories) if req.categories else None,
            req.cooldown_minutes,
        ),
    )
    conn.commit()
    return {"config_id": config_id, "name": req.name}


@router.get("/alerts/configs")
def list_alert_configs():
    """List all alert configurations."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM alert_configs ORDER BY created_at DESC").fetchall()
    configs = []
    for r in rows:
        c = dict(r)
        if c.get("categories") and isinstance(c["categories"], str):
            try:
                c["categories"] = json.loads(c["categories"])
            except json.JSONDecodeError:
                pass
        configs.append(c)
    return {"configs": configs}


# ── Velocity ────────────────────────────────────────────────────────────────


@router.get("/velocity")
def list_velocities(
    scope_type: str | None = None,
    period: str | None = None,
    spikes_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List event velocities with optional filters."""
    conn = get_db()
    conditions = []
    params: list = []

    if scope_type:
        conditions.append("scope_type = ?")
        params.append(scope_type)
    if period:
        conditions.append("period = ?")
        params.append(period)
    if spikes_only:
        conditions.append("velocity_ratio >= 3.0")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT * FROM event_velocity {where}
            ORDER BY velocity_ratio DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    return {"velocities": [dict(r) for r in rows]}


# ── Predictions Scorecard ───────────────────────────────────────────────────


@router.get("/predictions/scorecard")
def get_prediction_scorecard():
    """Get the full prediction accuracy scorecard."""
    from detection.predictions import compute_scorecard
    conn = get_db()
    return compute_scorecard(conn)


@router.get("/predictions/surprise")
def get_surprise_index(date: str | None = None):
    """Get the surprise index for a given date."""
    from detection.predictions import compute_surprise_index
    conn = get_db()
    return compute_surprise_index(conn, date)
