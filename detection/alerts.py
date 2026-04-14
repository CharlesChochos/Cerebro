"""
Alert system — automated notifications on threshold crossings.

Alert types:
- threshold: risk score exceeds configured threshold
- velocity_spike: event rate exceeds 3x baseline
- anomaly: nightlight drop, AIS dark pattern, etc.
- prediction_miss: predicted event didn't happen or unexpected event occurred

Features:
- Deduplication via cooldown periods per scope
- Alert acknowledgment tracking
- Configurable per-region/topic thresholds
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def check_cooldown(conn, config_id: str, scope_type: str, scope_value: str, cooldown_minutes: int) -> bool:
    """Check if an alert was recently fired for this config+scope (dedup)."""
    row = conn.execute(
        """SELECT MAX(created_at) as last_alert
           FROM alert_history
           WHERE config_id = ?
             AND scope_type = ?
             AND (scope_value = ? OR scope_value IS NULL)""",
        (config_id, scope_type, scope_value),
    ).fetchone()

    if not row or not row["last_alert"]:
        return False  # No previous alert, no cooldown

    try:
        last = datetime.fromisoformat(row["last_alert"].replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
        return elapsed < cooldown_minutes
    except (ValueError, TypeError):
        return False


def fire_alert(conn, config_id: str | None, alert_type: str, title: str,
               description: str, severity: float,
               scope_type: str | None = None, scope_value: str | None = None,
               event_ids: list | None = None) -> str | None:
    """
    Fire an alert after cooldown check.
    Returns alert_id if fired, None if suppressed by cooldown.
    """
    # Check cooldown
    if config_id and scope_type:
        config = conn.execute(
            "SELECT cooldown_minutes FROM alert_configs WHERE id = ?", (config_id,)
        ).fetchone()
        cooldown = config["cooldown_minutes"] if config else 60

        if check_cooldown(conn, config_id, scope_type, scope_value or "", cooldown):
            logger.debug("Alert suppressed by cooldown: %s", title)
            return None

    alert_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO alert_history
           (id, config_id, alert_type, title, description, severity,
            scope_type, scope_value, event_ids)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            alert_id, config_id, alert_type, title, description, severity,
            scope_type, scope_value, json.dumps(event_ids or []),
        ),
    )
    logger.info("Alert fired: [%s] %s (sev=%.0f)", alert_type, title, severity)
    return alert_id


def evaluate_threshold_alerts(conn) -> list[str]:
    """
    Check all enabled alert configs against current risk scores.
    Fire alerts where thresholds are exceeded.
    Returns list of alert IDs fired.
    """
    configs = conn.execute(
        "SELECT * FROM alert_configs WHERE enabled = 1"
    ).fetchall()

    fired = []
    for config in configs:
        cfg = dict(config)

        if cfg["scope_type"] == "global":
            # Check all risk scores against this global config
            high_risk = conn.execute(
                "SELECT * FROM risk_scores WHERE score >= ? ORDER BY score DESC LIMIT 5",
                (cfg["min_risk_score"],),
            ).fetchall()
        else:
            high_risk = conn.execute(
                "SELECT * FROM risk_scores WHERE scope_type = ? AND score >= ? ORDER BY score DESC",
                (cfg["scope_type"], cfg["min_risk_score"]),
            ).fetchall()

        for risk in high_risk:
            r = dict(risk)
            alert_id = fire_alert(
                conn,
                config_id=cfg["id"],
                alert_type="threshold",
                title=f"Risk threshold: {r['scope_value']} ({r['scope_type']}) at {r['score']:.0f}",
                description=(
                    f"Risk score for {r['scope_value']} reached {r['score']:.0f}/100. "
                    f"Trend: {r['trend']}. Events: {r['event_count']} from {r['source_count']} sources."
                ),
                severity=r["score"],
                scope_type=r["scope_type"],
                scope_value=r["scope_value"],
            )
            if alert_id:
                fired.append(alert_id)

    conn.commit()
    return fired


def evaluate_velocity_alerts(conn, spike_threshold: float = 3.0) -> list[str]:
    """
    Fire alerts for event velocity spikes (3x+ baseline).
    Returns list of alert IDs fired.
    """
    spikes = conn.execute(
        """SELECT * FROM event_velocity
           WHERE velocity_ratio >= ?
           ORDER BY velocity_ratio DESC""",
        (spike_threshold,),
    ).fetchall()

    fired = []
    for spike in spikes:
        s = dict(spike)
        alert_id = fire_alert(
            conn,
            config_id="default-velocity",
            alert_type="velocity_spike",
            title=f"Velocity spike: {s['scope_value']} ({s['scope_type']}) at {s['velocity_ratio']:.1f}x baseline",
            description=(
                f"Event rate for {s['scope_value']} is {s['velocity_ratio']:.1f}x above "
                f"the 7-day baseline ({s['event_count']} events in {s['period']} vs "
                f"baseline of {s.get('baseline_rate', 0):.1f})."
            ),
            severity=min(100, s["velocity_ratio"] * 25),
            scope_type=s["scope_type"],
            scope_value=s["scope_value"],
        )
        if alert_id:
            fired.append(alert_id)

    conn.commit()
    return fired


def run_alert_evaluation(conn) -> dict:
    """Run all alert evaluations. Returns stats."""
    threshold_alerts = evaluate_threshold_alerts(conn)
    velocity_alerts = evaluate_velocity_alerts(conn)

    stats = {
        "threshold_alerts": len(threshold_alerts),
        "velocity_alerts": len(velocity_alerts),
        "total_fired": len(threshold_alerts) + len(velocity_alerts),
    }
    logger.info("Alert evaluation: %s", stats)
    return stats
