"""
Capital flight detection — identifies patterns of rapid capital outflow
from countries, signaling economic instability or crisis.

Signal types:
- currency_drop: Rapid currency depreciation (>5% in short period)
- reserve_decline: Central bank foreign reserves falling
- bond_spread: Sovereign bond spreads widening (risk premium increasing)
- outflow_spike: Abnormal capital outflow detected
- fx_control: Capital controls or forex restrictions imposed

Each signal has:
- Measured value vs baseline
- Severity (0-100) based on deviation magnitude
- Status: active / confirmed / resolved / false_positive
"""
import json
import logging
import math
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

VALID_SIGNAL_TYPES = {"currency_drop", "reserve_decline", "bond_spread", "outflow_spike", "fx_control"}
VALID_STATUSES = {"active", "confirmed", "resolved", "false_positive"}

# Severity thresholds for each signal type
SEVERITY_THRESHOLDS = {
    "currency_drop": {"moderate": -5, "high": -10, "critical": -20},
    "reserve_decline": {"moderate": -5, "high": -15, "critical": -30},
    "bond_spread": {"moderate": 100, "high": 300, "critical": 500},  # basis points
    "outflow_spike": {"moderate": 50, "high": 100, "critical": 200},  # % above baseline
    "fx_control": {"moderate": 0, "high": 0, "critical": 0},  # binary — controls imposed
}


def compute_severity(signal_type: str, change_pct: float) -> float:
    """Compute severity score (0-100) based on the change magnitude."""
    thresholds = SEVERITY_THRESHOLDS.get(signal_type)
    if not thresholds:
        return 50.0

    if signal_type == "fx_control":
        return 80.0  # Capital controls are always high severity

    abs_change = abs(change_pct)
    crit_thresh = abs(thresholds["critical"])
    high_thresh = abs(thresholds["high"])
    mod_thresh = abs(thresholds["moderate"])

    if abs_change >= crit_thresh:
        return min(100.0, 80 + (abs_change - crit_thresh) / crit_thresh * 20)
    elif abs_change >= high_thresh:
        return 60 + (abs_change - high_thresh) / (crit_thresh - high_thresh) * 20
    elif abs_change >= mod_thresh:
        return 30 + (abs_change - mod_thresh) / (high_thresh - mod_thresh) * 30
    else:
        return max(0, abs_change / mod_thresh * 30)


def record_signal(
    conn,
    country_code: str,
    signal_type: str,
    indicator_value: float,
    baseline_value: float,
    description: str | None = None,
    evidence: list[str] | None = None,
) -> dict:
    """Record a capital flight signal."""
    if baseline_value != 0:
        change_pct = ((indicator_value - baseline_value) / abs(baseline_value)) * 100
    else:
        change_pct = 0

    severity = compute_severity(signal_type, change_pct)
    sid = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO capital_flight_signals
           (id, country_code, signal_type, severity, indicator_value,
            baseline_value, change_pct, description, evidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sid, country_code,
            signal_type if signal_type in VALID_SIGNAL_TYPES else "outflow_spike",
            severity, indicator_value, baseline_value,
            round(change_pct, 2),
            description,
            json.dumps(evidence or []),
        ),
    )
    conn.commit()

    return {
        "signal_id": sid,
        "severity": round(severity, 1),
        "change_pct": round(change_pct, 2),
        "signal_type": signal_type,
    }


def get_signal(conn, signal_id: str) -> dict | None:
    """Get a single capital flight signal."""
    row = conn.execute("SELECT * FROM capital_flight_signals WHERE id = ?", (signal_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
    return d


def list_signals(
    conn,
    country_code: str | None = None,
    signal_type: str | None = None,
    status: str | None = None,
    min_severity: float = 0,
    days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """List capital flight signals."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions = ["detected_at >= ?"]
    params: list = [cutoff]

    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)
    if signal_type and signal_type in VALID_SIGNAL_TYPES:
        conditions.append("signal_type = ?")
        params.append(signal_type)
    if status and status in VALID_STATUSES:
        conditions.append("status = ?")
        params.append(status)
    if min_severity > 0:
        conditions.append("severity >= ?")
        params.append(min_severity)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM capital_flight_signals WHERE {where} ORDER BY severity DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
        results.append(d)
    return results


def update_signal_status(conn, signal_id: str, status: str) -> bool:
    """Update a signal's status."""
    if status not in VALID_STATUSES:
        return False
    row = conn.execute("SELECT id FROM capital_flight_signals WHERE id = ?", (signal_id,)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE capital_flight_signals SET status = ? WHERE id = ?", (status, signal_id))
    conn.commit()
    return True


def assess_country_flight_risk(conn, country_code: str, days: int = 90) -> dict:
    """
    Assess overall capital flight risk for a country based on recent signals.

    Composite score considers:
    - Number of active signals
    - Signal diversity (multiple types = higher risk)
    - Maximum severity
    - Recent trend (accelerating or decelerating)
    """
    signals = list_signals(conn, country_code=country_code, days=days, limit=200)
    active = [s for s in signals if s["status"] in ("active", "confirmed")]

    if not active:
        return {
            "country_code": country_code,
            "risk_level": "low",
            "composite_score": 0,
            "active_signals": 0,
            "signal_types": [],
            "signals": [],
        }

    # Signal diversity
    signal_types = list(set(s["signal_type"] for s in active))
    diversity_bonus = len(signal_types) * 10

    # Max and average severity
    max_sev = max(s["severity"] for s in active)
    avg_sev = sum(s["severity"] for s in active) / len(active)

    # Composite: weighted combination
    composite = min(100, avg_sev * 0.4 + max_sev * 0.3 + diversity_bonus + len(active) * 5)

    risk_level = "low"
    if composite >= 80:
        risk_level = "critical"
    elif composite >= 60:
        risk_level = "high"
    elif composite >= 40:
        risk_level = "elevated"
    elif composite >= 20:
        risk_level = "moderate"

    return {
        "country_code": country_code,
        "risk_level": risk_level,
        "composite_score": round(composite, 1),
        "active_signals": len(active),
        "signal_types": signal_types,
        "max_severity": round(max_sev, 1),
        "avg_severity": round(avg_sev, 1),
        "signals": active[:20],
    }


def scan_economic_events(conn, days: int = 7) -> list[dict]:
    """
    Scan recent economic events for patterns that suggest capital flight.
    Looks for economic events with high severity in specific countries.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = conn.execute(
        """SELECT country_code, AVG(severity) as avg_sev, COUNT(*) as cnt
           FROM events
           WHERE timestamp >= ? AND category = 'economic'
             AND country_code IS NOT NULL
           GROUP BY country_code
           HAVING avg_sev > 60 AND cnt >= 3""",
        (cutoff,),
    ).fetchall()

    detected = []
    for r in rows:
        severity = compute_severity("outflow_spike", r["avg_sev"])
        sid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO capital_flight_signals
               (id, country_code, signal_type, severity, indicator_value,
                baseline_value, change_pct, description)
               VALUES (?, ?, 'outflow_spike', ?, ?, 50, ?, ?)""",
            (
                sid, r["country_code"], severity, r["avg_sev"],
                round(r["avg_sev"] - 50, 2),
                f"Economic event cluster: {r['cnt']} events, avg severity {r['avg_sev']:.0f}",
            ),
        )
        detected.append({
            "signal_id": sid,
            "country_code": r["country_code"],
            "signal_type": "outflow_spike",
            "severity": round(severity, 1),
        })

    if detected:
        conn.commit()
    return detected
