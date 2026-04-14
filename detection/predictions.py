"""
Prediction scorecard — tracks prediction accuracy and calibration.

Features:
- Resolution: checks if predictions came true
- Calibration: are 70% confident predictions correct 70% of the time?
- Surprise index: morning predictions vs evening reality gap
"""
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TIMEFRAME_HOURS = {
    "24h": 24,
    "48h": 48,
    "7d": 168,
    "30d": 720,
}


def check_expired_predictions(conn) -> dict:
    """
    Check predictions that have passed their timeframe without resolution.
    Mark as 'incorrect' if not confirmed by events.
    """
    resolved = 0

    # Get unresolved predictions
    rows = conn.execute(
        """SELECT id, prediction, confidence, timeframe, category, created_at
           FROM predictions
           WHERE outcome IS NULL"""
    ).fetchall()

    for row in rows:
        pred = dict(row)
        hours_limit = TIMEFRAME_HOURS.get(pred["timeframe"], 24)

        try:
            created = datetime.fromisoformat(pred["created_at"].replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        except (ValueError, TypeError):
            continue

        if elapsed > hours_limit:
            # Prediction window expired — mark as incorrect (unconfirmed)
            conn.execute(
                """UPDATE predictions SET outcome = 'expired', resolved_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                   WHERE id = ?""",
                (pred["id"],),
            )
            resolved += 1

    if resolved > 0:
        conn.commit()

    return {"expired_predictions": resolved}


def compute_calibration(conn) -> dict:
    """
    Compute prediction calibration — are confidence levels accurate?

    Returns calibration buckets: {bucket: {total, correct, accuracy}}.
    """
    buckets = {}
    for low, high, label in [
        (0.0, 0.3, "0-30%"),
        (0.3, 0.5, "30-50%"),
        (0.5, 0.7, "50-70%"),
        (0.7, 0.9, "70-90%"),
        (0.9, 1.01, "90-100%"),
    ]:
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN outcome = 'correct' THEN 1 ELSE 0 END) as correct
               FROM predictions
               WHERE outcome IS NOT NULL
                 AND confidence >= ? AND confidence < ?""",
            (low, high),
        ).fetchone()

        total = row["total"]
        correct = row["correct"] or 0
        accuracy = correct / total if total > 0 else None

        buckets[label] = {
            "total": total,
            "correct": correct,
            "accuracy": round(accuracy, 2) if accuracy is not None else None,
            "expected_range": f"{low*100:.0f}-{high*100:.0f}%",
        }

    return buckets


def compute_scorecard(conn) -> dict:
    """
    Compute full prediction scorecard stats.
    """
    total = conn.execute("SELECT COUNT(*) as cnt FROM predictions").fetchone()["cnt"]
    resolved = conn.execute(
        "SELECT COUNT(*) as cnt FROM predictions WHERE outcome IS NOT NULL"
    ).fetchone()["cnt"]
    correct = conn.execute(
        "SELECT COUNT(*) as cnt FROM predictions WHERE outcome = 'correct'"
    ).fetchone()["cnt"]
    incorrect = conn.execute(
        "SELECT COUNT(*) as cnt FROM predictions WHERE outcome = 'incorrect'"
    ).fetchone()["cnt"]
    expired = conn.execute(
        "SELECT COUNT(*) as cnt FROM predictions WHERE outcome = 'expired'"
    ).fetchone()["cnt"]
    pending = total - resolved

    accuracy = correct / resolved if resolved > 0 else None
    calibration = compute_calibration(conn)

    return {
        "total_predictions": total,
        "resolved": resolved,
        "pending": pending,
        "correct": correct,
        "incorrect": incorrect,
        "expired": expired,
        "accuracy": round(accuracy, 3) if accuracy is not None else None,
        "calibration": calibration,
    }


def compute_surprise_index(conn, date: str | None = None) -> dict:
    """
    Compute the surprise index for a given date.
    Measures gap between what was predicted and what actually happened.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Get predictions made before this date with 24h timeframe
    predictions = conn.execute(
        """SELECT id, prediction, confidence, category
           FROM predictions
           WHERE timeframe = '24h'
             AND date(created_at) = ?""",
        (date,),
    ).fetchall()

    if not predictions:
        return {"date": date, "surprise_score": 0, "reason": "no_predictions"}

    # Get high-severity events for this date
    events = conn.execute(
        """SELECT category, severity, title
           FROM events
           WHERE date(timestamp) = ?
             AND severity >= 60
           ORDER BY severity DESC LIMIT 20""",
        (date,),
    ).fetchall()

    # Simple surprise metric: how many predictions were wrong?
    pred_count = len(predictions)
    correct = conn.execute(
        """SELECT COUNT(*) as cnt FROM predictions
           WHERE timeframe = '24h'
             AND date(created_at) = ?
             AND outcome = 'correct'""",
        (date,),
    ).fetchone()["cnt"]

    # Also factor in unexpected high-severity events
    unexpected_count = len([e for e in events if dict(e)["severity"] >= 80])

    miss_rate = 1 - (correct / pred_count) if pred_count > 0 else 0
    surprise_score = min(100, round(miss_rate * 60 + unexpected_count * 10, 1))

    return {
        "date": date,
        "surprise_score": surprise_score,
        "predictions_made": pred_count,
        "predictions_correct": correct,
        "unexpected_events": unexpected_count,
        "miss_rate": round(miss_rate, 2),
    }
