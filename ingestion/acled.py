"""
ACLED (Armed Conflict Location & Event Data) ingestion connector.

Requires free API key — register at https://developer.acleddata.com/
Weekly updates with conflict events including actors, fatalities, and geo.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

ACLED_API_URL = "https://api.acleddata.com/acled/read"
ACLED_API_KEY = os.getenv("ACLED_API_KEY", "")
ACLED_EMAIL = os.getenv("ACLED_EMAIL", "")

# ACLED event types mapped to severity ranges
EVENT_TYPE_SEVERITY = {
    "Battles": 85,
    "Violence against civilians": 90,
    "Explosions/Remote violence": 88,
    "Riots": 65,
    "Protests": 40,
    "Strategic developments": 50,
}


def fetch_events(days_back: int = 7, limit: int = 500) -> list[dict]:
    """Fetch recent conflict events from ACLED API."""
    if not ACLED_API_KEY or not ACLED_EMAIL:
        logger.warning(
            "ACLED credentials not set (ACLED_API_KEY, ACLED_EMAIL). "
            "Register free at https://developer.acleddata.com/"
        )
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = {
        "key": ACLED_API_KEY,
        "email": ACLED_EMAIL,
        "event_date": f"{since}|{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "event_date_where": "BETWEEN",
        "limit": str(limit),
    }

    try:
        resp = httpx.get(ACLED_API_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("data", [])
        logger.info("ACLED returned %d events", len(events))
        return events
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("ACLED API error: %s", e)
        return []


def ingest(conn, days_back: int = 7) -> dict:
    """Fetch ACLED data and insert as events."""
    if not ACLED_API_KEY:
        logger.warning("No ACLED_API_KEY set — skipping ACLED ingestion")
        return {"source": "acled", "fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "note": "no_api_key"}

    raw_events = fetch_events(days_back)
    inserted = 0
    skipped = 0
    errors = 0

    for raw in raw_events:
        event_type = raw.get("event_type", "")
        sub_event = raw.get("sub_event_type", "")
        actor1 = raw.get("actor1", "Unknown")
        actor2 = raw.get("actor2", "")
        fatalities = raw.get("fatalities", 0)
        country = raw.get("country", "")
        location = raw.get("location", "")
        event_date = raw.get("event_date", "")
        data_id = raw.get("data_id", "")

        title = f"{event_type}: {actor1}"
        if actor2:
            title += f" vs {actor2}"
        title += f" in {location}, {country}"
        if fatalities and int(fatalities) > 0:
            title += f" ({fatalities} fatalities)"

        severity = EVENT_TYPE_SEVERITY.get(event_type, 50)
        try:
            fat_count = int(fatalities)
            if fat_count > 0:
                severity = min(100, severity + fat_count * 2)
        except (ValueError, TypeError):
            pass

        lat = None
        lon = None
        try:
            lat = float(raw.get("latitude", 0))
            lon = float(raw.get("longitude", 0))
            if lat == 0 and lon == 0:
                lat = lon = None
        except (ValueError, TypeError):
            pass

        iso3 = raw.get("iso3", "")
        country_code = iso3[:2] if iso3 else None

        entities = []
        if actor1 and actor1 != "Unknown":
            entities.append({"name": actor1, "type": "actor", "role": "source"})
        if actor2:
            entities.append({"name": actor2, "type": "actor", "role": "target"})

        event = {
            "id": str(uuid.uuid4()),
            "source": "acled",
            "source_id": f"acled-{data_id}",
            "timestamp": f"{event_date}T00:00:00+00:00" if event_date else datetime.now(timezone.utc).isoformat(),
            "title": title[:500],
            "summary": f"{event_type} / {sub_event} | {location}, {country} | Fatalities: {fatalities} | Source: {raw.get('source', '')}",
            "raw_payload": json.dumps(raw),
            "latitude": lat,
            "longitude": lon,
            "country_code": country_code,
            "region": f"{location}, {country}",
            "category": "military",
            "severity": min(100, round(severity)),
            "confidence": 0.9,  # ACLED is well-curated
            "entities_json": json.dumps(entities) if entities else None,
            "source_url": f"https://acleddata.com/data-export-tool/",
        }

        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, source_id, timestamp, title, summary, raw_payload,
                    latitude, longitude, country_code, region, category,
                    severity, confidence, entities_json, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event["id"], event["source"], event["source_id"],
                    event["timestamp"], event["title"], event["summary"],
                    event["raw_payload"], event["latitude"], event["longitude"],
                    event["country_code"], event["region"], event["category"],
                    event["severity"], event["confidence"], event["entities_json"],
                    event["source_url"],
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error("Error inserting ACLED event: %s", e)
            errors += 1

    conn.commit()
    stats = {
        "source": "acled",
        "fetched": len(raw_events),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("ACLED ingestion: %s", stats)
    return stats
