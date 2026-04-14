"""
Confidence decay — exponential fade on events without corroboration.

Events lose confidence over time if not corroborated by additional sources.
This implements the confidence decay from the build plan (Section 7.1).
"""
import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Half-life in hours — confidence halves every N hours without corroboration
HALF_LIFE_HOURS = 48.0  # 2 days


def compute_decay(original_confidence: float, hours_elapsed: float) -> float:
    """Compute decayed confidence using exponential decay."""
    if hours_elapsed <= 0:
        return original_confidence
    decay_rate = math.log(2) / HALF_LIFE_HOURS
    decayed = original_confidence * math.exp(-decay_rate * hours_elapsed)
    return round(max(0.01, decayed), 4)


def apply_decay(conn, min_age_hours: float = 6.0) -> dict:
    """
    Apply confidence decay to events older than min_age_hours
    that haven't been corroborated (confidence not manually boosted).
    """
    now = datetime.now(timezone.utc)
    cutoff = now.isoformat()

    # Find events that are old enough to decay
    rows = conn.execute(
        """SELECT id, confidence, timestamp
           FROM events
           WHERE confidence > 0.05
           AND julianday(?) - julianday(timestamp) > ?""",
        (cutoff, min_age_hours / 24.0),
    ).fetchall()

    updated = 0
    for row in rows:
        event_time = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        hours = (now - event_time).total_seconds() / 3600.0
        new_confidence = compute_decay(row["confidence"], hours)

        if abs(new_confidence - row["confidence"]) > 0.01:
            conn.execute(
                "UPDATE events SET confidence = ? WHERE id = ?",
                (new_confidence, row["id"]),
            )
            updated += 1

    conn.commit()
    stats = {"evaluated": len(rows), "updated": updated}
    logger.info("Confidence decay: %s", stats)
    return stats
