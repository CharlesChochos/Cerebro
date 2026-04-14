"""
Key Assumptions Check (KAC) — structured analytic technique to identify,
evaluate, and challenge the assumptions underlying intelligence assessments.

Workflow:
1. Analyst lists assumptions for an assessment
2. Each assumption gets evidence-for and evidence-against
3. System rates confidence and impact-if-wrong
4. Assumptions can be marked confirmed / challenged / disproven
5. Summary shows which assumptions are weakest (most likely to be wrong)
"""
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VALID_CONFIDENCE = {"low", "moderate", "high"}
VALID_STATUS = {"untested", "confirmed", "challenged", "disproven"}
VALID_IMPACT = {"low", "moderate", "high", "critical"}


def create_assumption(
    conn,
    assumption_text: str,
    assessment_id: str | None = None,
    confidence: str = "moderate",
    evidence_for: list[str] | None = None,
    evidence_against: list[str] | None = None,
    impact_if_wrong: str = "moderate",
    analyst: str | None = None,
    notes: str | None = None,
) -> str:
    """Record a key assumption."""
    aid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO key_assumptions
           (id, assessment_id, assumption_text, confidence, evidence_for,
            evidence_against, status, impact_if_wrong, analyst, notes)
           VALUES (?, ?, ?, ?, ?, ?, 'untested', ?, ?, ?)""",
        (
            aid, assessment_id, assumption_text,
            confidence if confidence in VALID_CONFIDENCE else "moderate",
            json.dumps(evidence_for or []),
            json.dumps(evidence_against or []),
            impact_if_wrong if impact_if_wrong in VALID_IMPACT else "moderate",
            analyst, notes,
        ),
    )
    conn.commit()
    return aid


def update_assumption_status(
    conn, assumption_id: str, status: str,
    evidence_for: list[str] | None = None,
    evidence_against: list[str] | None = None,
    confidence: str | None = None,
) -> bool:
    """Update the status and evidence for an assumption."""
    if status not in VALID_STATUS:
        return False

    row = conn.execute("SELECT * FROM key_assumptions WHERE id = ?", (assumption_id,)).fetchone()
    if not row:
        return False

    updates = ["status = ?", "updated_at = ?"]
    params: list = [status, datetime.now(timezone.utc).isoformat()]

    if evidence_for is not None:
        existing = json.loads(row["evidence_for"]) if row["evidence_for"] else []
        updates.append("evidence_for = ?")
        params.append(json.dumps(existing + evidence_for))
    if evidence_against is not None:
        existing = json.loads(row["evidence_against"]) if row["evidence_against"] else []
        updates.append("evidence_against = ?")
        params.append(json.dumps(existing + evidence_against))
    if confidence and confidence in VALID_CONFIDENCE:
        updates.append("confidence = ?")
        params.append(confidence)

    params.append(assumption_id)
    conn.execute(
        f"UPDATE key_assumptions SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return True


def get_assumption(conn, assumption_id: str) -> dict | None:
    """Get a single assumption."""
    row = conn.execute("SELECT * FROM key_assumptions WHERE id = ?", (assumption_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["evidence_for"] = json.loads(d["evidence_for"]) if d["evidence_for"] else []
    d["evidence_against"] = json.loads(d["evidence_against"]) if d["evidence_against"] else []
    return d


def list_assumptions(
    conn,
    assessment_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List assumptions, optionally filtered by assessment or status."""
    conditions = []
    params: list = []

    if assessment_id:
        conditions.append("assessment_id = ?")
        params.append(assessment_id)
    if status and status in VALID_STATUS:
        conditions.append("status = ?")
        params.append(status)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM key_assumptions{where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["evidence_for"] = json.loads(d["evidence_for"]) if d["evidence_for"] else []
        d["evidence_against"] = json.loads(d["evidence_against"]) if d["evidence_against"] else []
        results.append(d)
    return results


def evaluate_assumptions(conn, assessment_id: str) -> dict:
    """
    Evaluate all assumptions for an assessment — identify which are weakest.

    Vulnerability scoring:
    - Untested + high impact = highest vulnerability
    - Challenged + high impact = very high
    - Low confidence + high impact = high
    """
    assumptions = list_assumptions(conn, assessment_id=assessment_id, limit=200)

    CONFIDENCE_WEIGHT = {"low": 0.3, "moderate": 0.6, "high": 0.9}
    IMPACT_WEIGHT = {"low": 0.25, "moderate": 0.5, "high": 0.75, "critical": 1.0}
    STATUS_PENALTY = {"untested": 0.8, "confirmed": 0.0, "challenged": 1.0, "disproven": 1.0}

    scored = []
    for a in assumptions:
        evidence_balance = len(a["evidence_for"]) - len(a["evidence_against"])
        conf_w = CONFIDENCE_WEIGHT.get(a["confidence"], 0.5)
        impact_w = IMPACT_WEIGHT.get(a["impact_if_wrong"], 0.5)
        status_p = STATUS_PENALTY.get(a["status"], 0.5)

        # Vulnerability: high when low confidence, high impact, few evidence_for
        vulnerability = (1.0 - conf_w) * impact_w * (1.0 + status_p) / 2.0
        if evidence_balance < 0:
            vulnerability *= 1.3  # more evidence against → more vulnerable

        scored.append({
            "id": a["id"],
            "assumption_text": a["assumption_text"],
            "status": a["status"],
            "confidence": a["confidence"],
            "impact_if_wrong": a["impact_if_wrong"],
            "evidence_for_count": len(a["evidence_for"]),
            "evidence_against_count": len(a["evidence_against"]),
            "vulnerability_score": round(min(vulnerability, 1.0), 3),
        })

    scored.sort(key=lambda x: x["vulnerability_score"], reverse=True)

    total = len(assumptions)
    challenged = sum(1 for a in assumptions if a["status"] in ("challenged", "disproven"))

    return {
        "assessment_id": assessment_id,
        "total_assumptions": total,
        "untested": sum(1 for a in assumptions if a["status"] == "untested"),
        "confirmed": sum(1 for a in assumptions if a["status"] == "confirmed"),
        "challenged": challenged,
        "disproven": sum(1 for a in assumptions if a["status"] == "disproven"),
        "overall_confidence": "low" if challenged > total * 0.3 else ("high" if challenged == 0 else "moderate"),
        "assumptions": scored,
    }
