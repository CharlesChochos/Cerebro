"""
NOAA severe weather alerts ingestion connector.

Fetches active weather alerts from the NWS API.
No API key required — public data.
Source: https://api.weather.gov/alerts/active
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"

SEVERITY_MAP = {
    "Extreme": 95,
    "Severe": 80,
    "Moderate": 55,
    "Minor": 30,
    "Unknown": 40,
}

# Map NWS event types to Cerebro categories
EVENT_CATEGORY_MAP = {
    "Hurricane": "environmental",
    "Tornado": "environmental",
    "Tsunami": "environmental",
    "Earthquake": "environmental",
    "Flood": "environmental",
    "Wildfire": "environmental",
    "Blizzard": "environmental",
    "Winter Storm": "environmental",
    "Extreme Heat": "environmental",
    "Extreme Cold": "environmental",
}


def fetch_alerts(severity: str | None = None) -> list[dict]:
    """Fetch active NWS alerts. Optionally filter by severity."""
    params = {"status": "actual", "message_type": "alert"}
    if severity:
        params["severity"] = severity

    try:
        resp = httpx.get(
            NWS_ALERTS_URL,
            params=params,
            headers={"User-Agent": "Cerebro/1.0 (intelligence-monitor)"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("features", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("NWS API error: %s", e)
        return []


def extract_coords(feature: dict) -> tuple[float | None, float | None]:
    """Extract centroid from alert geometry or affected zones."""
    geom = feature.get("geometry")
    if geom and geom.get("type") == "Point":
        coords = geom["coordinates"]
        return coords[1], coords[0]  # GeoJSON is [lng, lat]
    if geom and geom.get("type") == "Polygon":
        coords = geom["coordinates"][0]
        lat = sum(c[1] for c in coords) / len(coords)
        lng = sum(c[0] for c in coords) / len(coords)
        return lat, lng
    return None, None


def extract_polygon_json(feature: dict) -> str | None:
    """Extract GeoJSON polygon for area visualization."""
    geom = feature.get("geometry")
    if geom and geom.get("type") in ("Polygon", "MultiPolygon"):
        return json.dumps(geom)
    return None


def ingest(conn) -> dict:
    """Fetch NOAA/NWS alerts and store as events + weather_events."""
    features = fetch_alerts()
    inserted = 0
    skipped = 0
    errors = 0

    for feature in features:
        props = feature.get("properties", {})
        title = props.get("headline", props.get("event", "Weather Alert"))
        if not title:
            continue

        alert_id = props.get("id", "")
        source_id = f"noaa-{alert_id}"
        event_type = props.get("event", "Unknown")
        severity_str = props.get("severity", "Unknown")
        severity = SEVERITY_MAP.get(severity_str, 40)
        urgency = props.get("urgency", "")
        description = props.get("description", "")
        area_desc = props.get("areaDesc", "")
        effective = props.get("effective", "")
        expires = props.get("expires", "")

        lat, lng = extract_coords(feature)
        polygon = extract_polygon_json(feature)

        # Parse timestamp
        sent = props.get("sent", "")
        try:
            ts = datetime.fromisoformat(sent.replace("Z", "+00:00")) if sent else datetime.now(timezone.utc)
        except ValueError:
            ts = datetime.now(timezone.utc)

        event_id = str(uuid.uuid4())
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, source_id, timestamp, title, summary, raw_payload,
                    latitude, longitude, country_code, region, category,
                    severity, confidence, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, "noaa", source_id,
                    ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    title[:500], description[:2000],
                    json.dumps({"event": event_type, "severity": severity_str, "urgency": urgency}),
                    lat, lng, "US", area_desc[:200] if area_desc else None,
                    "environmental", severity, 0.95,
                    f"https://api.weather.gov/alerts/{alert_id}" if alert_id else None,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
                # Also store in weather_events
                conn.execute(
                    """INSERT OR IGNORE INTO weather_events
                       (id, event_type, title, description, severity, urgency,
                        lat, lng, area_desc, polygon_json, effective, expires, source_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, event_type, title[:500], description[:2000],
                        severity_str, urgency, lat, lng, area_desc[:500],
                        polygon, effective, expires,
                        f"https://api.weather.gov/alerts/{alert_id}" if alert_id else None,
                    ),
                )
            else:
                skipped += 1
        except Exception as e:
            logger.error("Error inserting NOAA event: %s", e)
            errors += 1

    conn.commit()
    stats = {"source": "noaa", "fetched": len(features), "inserted": inserted, "skipped": skipped, "errors": errors}
    logger.info("NOAA ingestion: %s", stats)
    return stats
