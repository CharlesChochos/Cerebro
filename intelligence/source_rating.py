"""
IC Source Rating System (Admiralty / NATO STANAG 2022) — rates intelligence
sources on two independent dimensions:

Reliability (A–F):
  A = Completely reliable
  B = Usually reliable
  C = Fairly reliable
  D = Not usually reliable
  E = Unreliable
  F = Cannot be judged

Information Quality (1–6):
  1 = Confirmed by other sources
  2 = Probably true
  3 = Possibly true
  4 = Doubtful
  5 = Improbable
  6 = Cannot be judged

Composite score maps the two dimensions to a 0-100 numeric value for
sorting and threshold alerting.

Example: "B2" = Usually reliable source, probably true information → high quality
         "D5" = Not usually reliable, improbable information → low quality
"""
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

RELIABILITY_GRADES = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "F": 0}
QUALITY_GRADES = {1: 5, 2: 4, 3: 3, 4: 2, 5: 1, 6: 0}
RELIABILITY_LABELS = {
    "A": "Completely reliable",
    "B": "Usually reliable",
    "C": "Fairly reliable",
    "D": "Not usually reliable",
    "E": "Unreliable",
    "F": "Cannot be judged",
}
QUALITY_LABELS = {
    1: "Confirmed by other sources",
    2: "Probably true",
    3: "Possibly true",
    4: "Doubtful",
    5: "Improbable",
    6: "Cannot be judged",
}

VALID_SOURCE_TYPES = {"humint", "sigint", "osint", "geoint", "masint", "techint"}


def compute_composite_score(reliability: str, information_quality: int) -> float:
    """
    Compute a 0-100 composite score from the two-dimensional rating.

    Both dimensions contribute equally. F/6 (cannot be judged) contributes 0.
    """
    rel_score = RELIABILITY_GRADES.get(reliability.upper(), 0)
    qual_score = QUALITY_GRADES.get(information_quality, 0)
    # Each dimension is 0-5, total 0-10, scaled to 0-100
    return round((rel_score + qual_score) / 10.0 * 100, 1)


def format_rating(reliability: str, information_quality: int) -> str:
    """Format as the standard IC rating string, e.g. 'B2'."""
    return f"{reliability.upper()}{information_quality}"


def classify_rating(composite: float) -> str:
    """Classify composite score into quality tier."""
    if composite >= 80:
        return "excellent"
    elif composite >= 60:
        return "good"
    elif composite >= 40:
        return "adequate"
    elif composite >= 20:
        return "poor"
    return "unreliable"


def rate_source(
    conn,
    source_name: str,
    reliability: str,
    information_quality: int,
    source_type: str | None = None,
    rating_basis: list[str] | None = None,
    analyst: str | None = None,
    notes: str | None = None,
) -> dict:
    """Create or update a source rating."""
    reliability = reliability.upper()
    if reliability not in RELIABILITY_GRADES:
        reliability = "F"
    if information_quality not in QUALITY_GRADES:
        information_quality = 6

    composite = compute_composite_score(reliability, information_quality)
    rid = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO source_ratings
           (id, source_name, source_type, reliability, information_quality,
            composite_score, rating_basis, analyst, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rid, source_name,
            source_type if source_type in VALID_SOURCE_TYPES else None,
            reliability, information_quality, composite,
            json.dumps(rating_basis or []),
            analyst, notes,
        ),
    )
    conn.commit()

    return {
        "rating_id": rid,
        "rating": format_rating(reliability, information_quality),
        "composite_score": composite,
        "quality_tier": classify_rating(composite),
        "reliability_label": RELIABILITY_LABELS[reliability],
        "quality_label": QUALITY_LABELS[information_quality],
    }


def get_rating(conn, rating_id: str) -> dict | None:
    """Get a single source rating."""
    row = conn.execute("SELECT * FROM source_ratings WHERE id = ?", (rating_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["rating_basis"] = json.loads(d["rating_basis"]) if d["rating_basis"] else []
    d["track_record"] = json.loads(d["track_record"]) if d["track_record"] else None
    d["rating"] = format_rating(d["reliability"], d["information_quality"])
    d["quality_tier"] = classify_rating(d["composite_score"])
    d["reliability_label"] = RELIABILITY_LABELS.get(d["reliability"], "Unknown")
    d["quality_label"] = QUALITY_LABELS.get(d["information_quality"], "Unknown")
    return d


def list_ratings(
    conn,
    source_type: str | None = None,
    min_composite: float | None = None,
    reliability: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List source ratings with optional filters."""
    conditions = []
    params: list = []

    if source_type and source_type in VALID_SOURCE_TYPES:
        conditions.append("source_type = ?")
        params.append(source_type)
    if min_composite is not None:
        conditions.append("composite_score >= ?")
        params.append(min_composite)
    if reliability:
        conditions.append("reliability = ?")
        params.append(reliability.upper())

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM source_ratings{where} ORDER BY composite_score DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["rating_basis"] = json.loads(d["rating_basis"]) if d["rating_basis"] else []
        d["track_record"] = json.loads(d["track_record"]) if d["track_record"] else None
        d["rating"] = format_rating(d["reliability"], d["information_quality"])
        d["quality_tier"] = classify_rating(d["composite_score"])
        results.append(d)
    return results


def get_ratings_for_source(conn, source_name: str) -> list[dict]:
    """Get all ratings for a specific source name (history)."""
    rows = conn.execute(
        "SELECT * FROM source_ratings WHERE source_name = ? ORDER BY created_at DESC",
        (source_name,),
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["rating_basis"] = json.loads(d["rating_basis"]) if d["rating_basis"] else []
        d["track_record"] = json.loads(d["track_record"]) if d["track_record"] else None
        d["rating"] = format_rating(d["reliability"], d["information_quality"])
        d["quality_tier"] = classify_rating(d["composite_score"])
        results.append(d)
    return results


def get_rating_stats(conn) -> dict:
    """Get summary statistics for all source ratings."""
    total = conn.execute("SELECT COUNT(*) as c FROM source_ratings").fetchone()["c"]

    by_reliability = {}
    rows = conn.execute(
        "SELECT reliability, COUNT(*) as c FROM source_ratings GROUP BY reliability"
    ).fetchall()
    for r in rows:
        by_reliability[r["reliability"]] = r["c"]

    by_type = {}
    rows = conn.execute(
        "SELECT source_type, COUNT(*) as c, AVG(composite_score) as avg_s "
        "FROM source_ratings WHERE source_type IS NOT NULL GROUP BY source_type"
    ).fetchall()
    for r in rows:
        by_type[r["source_type"]] = {
            "count": r["c"],
            "avg_composite": round(r["avg_s"], 1),
        }

    avg_composite = conn.execute("SELECT AVG(composite_score) as a FROM source_ratings").fetchone()["a"]

    return {
        "total_ratings": total,
        "avg_composite_score": round(avg_composite, 1) if avg_composite else 0,
        "by_reliability_grade": by_reliability,
        "by_source_type": by_type,
        "rating_scale": {
            "reliability": RELIABILITY_LABELS,
            "information_quality": QUALITY_LABELS,
        },
    }
