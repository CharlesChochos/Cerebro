"""
Threat Assessment Matrix — evaluates threats along four dimensions:

1. Capability (0-100): Does the threat actor have the means?
2. Intent (0-100): Does the threat actor have the will?
3. Opportunity (0-100): Are conditions favorable for the threat?
4. Vulnerability (0-100): How exposed is the defender?

Overall score = weighted geometric mean of the four dimensions.
Higher score = higher threat level.

Threat levels:
- Critical (≥80): Immediate action required
- High (≥60): Urgent attention needed
- Moderate (≥40): Monitor closely
- Low (≥20): Routine monitoring
- Minimal (<20): No significant threat
"""
import json
import logging
import math
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VALID_THREAT_TYPES = {"state", "non-state", "cyber", "natural", "economic"}
VALID_TIMEFRAMES = {"near-term", "mid-term", "long-term"}
VALID_STATUS = {"active", "mitigated", "expired"}

# Weights for the composite score
DIMENSION_WEIGHTS = {
    "capability": 0.30,
    "intent": 0.30,
    "opportunity": 0.25,
    "vulnerability": 0.15,
}


def compute_overall_score(
    capability: float, intent: float, opportunity: float, vulnerability: float,
) -> float:
    """
    Compute composite threat score using a weighted geometric mean.

    Geometric mean ensures all dimensions matter — a zero in any dimension
    significantly reduces the overall score (you can't have a threat without
    both capability AND intent).
    """
    # Clamp to [1, 100] to avoid log(0) issues
    cap = max(1.0, min(100.0, capability))
    intn = max(1.0, min(100.0, intent))
    opp = max(1.0, min(100.0, opportunity))
    vuln = max(1.0, min(100.0, vulnerability))

    w = DIMENSION_WEIGHTS
    log_score = (
        w["capability"] * math.log(cap) +
        w["intent"] * math.log(intn) +
        w["opportunity"] * math.log(opp) +
        w["vulnerability"] * math.log(vuln)
    )
    return round(math.exp(log_score), 1)


def classify_threat_level(score: float) -> str:
    """Classify overall score into threat level."""
    if score >= 80:
        return "critical"
    elif score >= 60:
        return "high"
    elif score >= 40:
        return "moderate"
    elif score >= 20:
        return "low"
    return "minimal"


def create_assessment(
    conn,
    threat_name: str,
    capability_score: float,
    intent_score: float,
    opportunity_score: float,
    vulnerability_score: float = 50.0,
    threat_type: str | None = None,
    description: str | None = None,
    region: str | None = None,
    country_code: str | None = None,
    timeframe: str = "near-term",
    analyst: str | None = None,
    evidence: list[str] | None = None,
    mitigations: list[str] | None = None,
) -> dict:
    """Create a new threat assessment."""
    tid = str(uuid.uuid4())
    overall = compute_overall_score(
        capability_score, intent_score, opportunity_score, vulnerability_score,
    )

    conn.execute(
        """INSERT INTO threat_assessments
           (id, threat_name, threat_type, description,
            capability_score, intent_score, opportunity_score, vulnerability_score,
            overall_score, region, country_code, timeframe, analyst, evidence, mitigations)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tid, threat_name,
            threat_type if threat_type in VALID_THREAT_TYPES else None,
            description,
            capability_score, intent_score, opportunity_score, vulnerability_score,
            overall, region, country_code,
            timeframe if timeframe in VALID_TIMEFRAMES else "near-term",
            analyst,
            json.dumps(evidence or []),
            json.dumps(mitigations or []),
        ),
    )
    conn.commit()

    return {
        "assessment_id": tid,
        "overall_score": overall,
        "threat_level": classify_threat_level(overall),
    }


def get_assessment(conn, assessment_id: str) -> dict | None:
    """Get a single threat assessment."""
    row = conn.execute("SELECT * FROM threat_assessments WHERE id = ?", (assessment_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
    d["mitigations"] = json.loads(d["mitigations"]) if d["mitigations"] else []
    d["threat_level"] = classify_threat_level(d["overall_score"])
    return d


def list_assessments(
    conn,
    threat_type: str | None = None,
    status: str | None = None,
    region: str | None = None,
    timeframe: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List threat assessments with optional filters."""
    conditions = []
    params: list = []

    if threat_type:
        conditions.append("threat_type = ?")
        params.append(threat_type)
    if status and status in VALID_STATUS:
        conditions.append("status = ?")
        params.append(status)
    if region:
        conditions.append("region = ?")
        params.append(region)
    if timeframe and timeframe in VALID_TIMEFRAMES:
        conditions.append("timeframe = ?")
        params.append(timeframe)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM threat_assessments{where} ORDER BY overall_score DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
        d["mitigations"] = json.loads(d["mitigations"]) if d["mitigations"] else []
        d["threat_level"] = classify_threat_level(d["overall_score"])
        results.append(d)
    return results


def update_assessment(
    conn,
    assessment_id: str,
    capability_score: float | None = None,
    intent_score: float | None = None,
    opportunity_score: float | None = None,
    vulnerability_score: float | None = None,
    status: str | None = None,
) -> dict | None:
    """Update dimension scores and recompute overall threat level."""
    row = conn.execute("SELECT * FROM threat_assessments WHERE id = ?", (assessment_id,)).fetchone()
    if not row:
        return None

    cap = capability_score if capability_score is not None else row["capability_score"]
    intn = intent_score if intent_score is not None else row["intent_score"]
    opp = opportunity_score if opportunity_score is not None else row["opportunity_score"]
    vuln = vulnerability_score if vulnerability_score is not None else row["vulnerability_score"]

    overall = compute_overall_score(cap, intn, opp, vuln)
    now = datetime.now(timezone.utc).isoformat()

    updates = [
        "capability_score = ?", "intent_score = ?",
        "opportunity_score = ?", "vulnerability_score = ?",
        "overall_score = ?", "updated_at = ?",
    ]
    params: list = [cap, intn, opp, vuln, overall, now]

    if status and status in VALID_STATUS:
        updates.append("status = ?")
        params.append(status)

    params.append(assessment_id)
    conn.execute(
        f"UPDATE threat_assessments SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()

    return {
        "assessment_id": assessment_id,
        "overall_score": overall,
        "threat_level": classify_threat_level(overall),
    }


def get_threat_summary(conn, region: str | None = None) -> dict:
    """Get a summary of active threat assessments, optionally filtered by region."""
    conditions = ["status = 'active'"]
    params: list = []
    if region:
        conditions.append("region = ?")
        params.append(region)

    where = " WHERE " + " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM threat_assessments{where} ORDER BY overall_score DESC",
        params,
    ).fetchall()

    by_level = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "minimal": 0}
    by_type: dict[str, int] = {}

    for r in rows:
        level = classify_threat_level(r["overall_score"])
        by_level[level] += 1
        ttype = r["threat_type"] or "unspecified"
        by_type[ttype] = by_type.get(ttype, 0) + 1

    return {
        "total_active": len(rows),
        "region": region,
        "by_threat_level": by_level,
        "by_threat_type": by_type,
        "highest_threat": dict(rows[0]) if rows else None,
    }
