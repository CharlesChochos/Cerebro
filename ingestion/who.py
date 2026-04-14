"""
WHO Disease Outbreak News ingestion connector.

Fetches disease outbreak reports from the WHO website via their RSS/Atom feed.
No API key required — public data.
Source: https://www.who.int/csr/don/en/
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import feedparser
import httpx

logger = logging.getLogger(__name__)

WHO_DON_FEED = "https://www.who.int/feeds/entity/don/en/rss.xml"
WHO_OUTBREAKS_API = "https://www.who.int/api/hubs/diseaseoutbreaknews"

# Map disease keywords to severity estimates
DISEASE_SEVERITY = {
    "ebola": 90, "marburg": 90, "plague": 85, "cholera": 70,
    "mpox": 60, "avian influenza": 75, "h5n1": 80, "h7n9": 80,
    "mers": 75, "sars": 80, "covid": 65, "dengue": 55,
    "yellow fever": 65, "polio": 70, "measles": 55, "diphtheria": 60,
    "anthrax": 85, "typhoid": 55, "meningitis": 60, "lassa fever": 75,
    "rift valley fever": 65, "zika": 55, "nipah": 85, "hendra": 80,
}


def estimate_severity(title: str, summary: str) -> int:
    """Estimate severity based on disease keywords."""
    text = (title + " " + (summary or "")).lower()
    for disease, sev in DISEASE_SEVERITY.items():
        if disease in text:
            return sev
    return 50  # default moderate severity


def extract_disease(title: str) -> str:
    """Extract disease name from title."""
    text = title.lower()
    for disease in DISEASE_SEVERITY:
        if disease in text:
            return disease.title()
    # Try to extract from common patterns
    if " - " in title:
        parts = title.split(" - ")
        return parts[0].strip()
    return "Unknown"


def fetch_who_feed() -> list[dict]:
    """Fetch WHO Disease Outbreak News via RSS feed."""
    try:
        feed = feedparser.parse(WHO_DON_FEED)
        if feed.bozo and not feed.entries:
            logger.warning("WHO feed parse error: %s", feed.bozo_exception)
            return []
        return feed.entries
    except Exception as e:
        logger.error("WHO feed fetch error: %s", e)
        return []


def fetch_who_api() -> list[dict]:
    """Fetch WHO DON via the JSON API (fallback)."""
    try:
        resp = httpx.get(WHO_OUTBREAKS_API, timeout=15.0, params={"$top": "30", "$orderby": "PublicationDate desc"})
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("WHO API error: %s", e)
        return []


def ingest(conn) -> dict:
    """Fetch WHO Disease Outbreak News and store as events + disease_outbreaks."""
    entries = fetch_who_feed()
    inserted = 0
    skipped = 0
    errors = 0

    for entry in entries:
        title = entry.get("title", "").strip()
        if not title:
            continue

        link = entry.get("link", "")
        summary = entry.get("summary", entry.get("description", ""))
        published = entry.get("published", entry.get("updated", ""))

        # Parse date
        try:
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                ts = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            else:
                ts = datetime.now(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)

        source_id = f"who-{link}" if link else f"who-{title[:80]}"
        disease = extract_disease(title)
        severity = estimate_severity(title, summary)

        # Extract country from title if possible (common pattern: "Disease - Country")
        country_code = None
        region = None
        if " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                region = parts[-1].strip()

        # Insert into events table
        event_id = str(uuid.uuid4())
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, source_id, timestamp, title, summary, raw_payload,
                    country_code, region, category, severity, confidence,
                    entities_json, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, "who", source_id,
                    ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    title[:500], (summary or "")[:2000],
                    json.dumps({"feed_entry": title, "link": link}),
                    country_code, region, "health", severity, 0.85,
                    json.dumps([{"name": disease, "type": "disease", "role": "subject"}]),
                    link,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1

                # Also insert into disease_outbreaks
                conn.execute(
                    """INSERT OR IGNORE INTO disease_outbreaks
                       (id, source, disease, title, summary, country_code, region,
                        status, severity, source_url, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, "who", disease, title[:500], (summary or "")[:2000],
                        country_code, region, "active", severity, link,
                        ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    ),
                )
            else:
                skipped += 1
        except Exception as e:
            logger.error("Error inserting WHO event: %s", e)
            errors += 1

    conn.commit()
    stats = {"source": "who", "fetched": len(entries), "inserted": inserted, "skipped": skipped, "errors": errors}
    logger.info("WHO ingestion: %s", stats)
    return stats
