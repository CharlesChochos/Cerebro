"""
Nightlight economic proxy detection.

Uses VIIRS nighttime light intensity as a GDP/economic activity proxy.
Significant drops in nightlight radiance correlate with:
- Economic collapse (Venezuela 2018, Syria civil war)
- Power grid failures
- Natural disaster aftermath
- Conflict zone depopulation

Significant increases correlate with:
- Rapid urbanization
- Industrial buildup
- Military base expansion
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Thresholds for significant changes
DROP_THRESHOLD_PCT = -20.0     # 20% decrease = significant economic signal
SURGE_THRESHOLD_PCT = 30.0     # 30% increase = significant activity signal
CRITICAL_DROP_PCT = -40.0      # 40% decrease = critical (war/collapse level)


def compute_change(current: float, baseline: float) -> float:
    """Compute percent change from baseline."""
    if baseline <= 0:
        return 0.0
    return ((current - baseline) / baseline) * 100.0


def severity_from_change(change_pct: float) -> int:
    """Map nightlight change to severity score."""
    abs_change = abs(change_pct)
    if abs_change >= 50:
        return 90
    if abs_change >= 40:
        return 80
    if abs_change >= 30:
        return 65
    if abs_change >= 20:
        return 50
    if abs_change >= 10:
        return 30
    return 10


def classify_change(change_pct: float) -> str:
    """Classify the type of nightlight change."""
    if change_pct <= CRITICAL_DROP_PCT:
        return "critical_decline"
    if change_pct <= DROP_THRESHOLD_PCT:
        return "significant_decline"
    if change_pct >= SURGE_THRESHOLD_PCT:
        return "significant_surge"
    return "normal"


def detect_anomalies(conn, threshold_pct: float = 20.0) -> list[dict]:
    """
    Scan nightlight_readings for anomalous changes vs baseline.

    Returns list of detected anomalies with metadata.
    """
    rows = conn.execute(
        """SELECT id, lat, lng, country_code, region, radiance,
                  baseline_radiance, change_pct, capture_date
           FROM nightlight_readings
           WHERE baseline_radiance > 0
             AND ABS(change_pct) >= ?
           ORDER BY ABS(change_pct) DESC
           LIMIT 100""",
        (threshold_pct,),
    ).fetchall()

    anomalies = []
    for r in rows:
        reading = dict(r)
        change = reading.get("change_pct", 0)
        classification = classify_change(change)

        if classification == "normal":
            continue

        anomalies.append({
            "reading_id": reading["id"],
            "lat": reading["lat"],
            "lng": reading["lng"],
            "country_code": reading.get("country_code"),
            "region": reading.get("region"),
            "radiance": reading["radiance"],
            "baseline": reading["baseline_radiance"],
            "change_pct": round(change, 1),
            "classification": classification,
            "severity": severity_from_change(change),
            "capture_date": reading["capture_date"],
        })

    return anomalies


def generate_events_from_anomalies(conn, anomalies: list[dict]) -> int:
    """
    Create events from nightlight anomalies for the intelligence pipeline.
    Returns count of events inserted.
    """
    inserted = 0
    import json

    for a in anomalies:
        direction = "drop" if a["change_pct"] < 0 else "surge"
        title = (
            f"Nightlight {direction}: {abs(a['change_pct']):.0f}% change at "
            f"({a['lat']:.2f}, {a['lng']:.2f})"
        )
        if a.get("country_code"):
            title += f" ({a['country_code']})"

        source_id = f"nightlight-{a['lat']:.3f}-{a['lng']:.3f}-{a['capture_date']}"

        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, source_id, timestamp, title, summary, raw_payload,
                    latitude, longitude, country_code, region,
                    category, severity, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), "viirs_nightlights", source_id,
                    f"{a['capture_date']}T00:00:00+00:00",
                    title[:500],
                    f"VIIRS nightlight {a['classification']}: radiance changed from "
                    f"{a['baseline']:.1f} to {a['radiance']:.1f} ({a['change_pct']:+.1f}%)",
                    json.dumps(a),
                    a["lat"], a["lng"], a.get("country_code"), a.get("region"),
                    "economic", a["severity"], 0.70,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            logger.error("Error inserting nightlight event: %s", e)

    if inserted > 0:
        conn.commit()

    return inserted


def run_detection(conn) -> dict:
    """Run full nightlight anomaly detection pipeline."""
    anomalies = detect_anomalies(conn)
    events_created = generate_events_from_anomalies(conn, anomalies)

    stats = {
        "anomalies_detected": len(anomalies),
        "events_created": events_created,
        "critical": sum(1 for a in anomalies if a["classification"] == "critical_decline"),
        "significant_drops": sum(1 for a in anomalies if a["classification"] == "significant_decline"),
        "significant_surges": sum(1 for a in anomalies if a["classification"] == "significant_surge"),
    }
    logger.info("Nightlight detection: %s", stats)
    return stats
