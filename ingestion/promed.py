"""
ProMED-mail early warning ingestion connector.

Fetches disease outbreak alerts from ProMED-mail via RSS.
ProMED is the global gold standard for early disease detection.
No API key required — public RSS feed.
Source: https://promedmail.org/
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import feedparser

logger = logging.getLogger(__name__)

PROMED_FEED = "https://promedmail.org/feed/"

# ProMED often covers the same diseases as WHO but earlier
DISEASE_KEYWORDS = {
    "ebola": 90, "marburg": 90, "avian influenza": 80, "h5n1": 80,
    "anthrax": 85, "plague": 85, "cholera": 70, "mpox": 60,
    "dengue": 55, "measles": 55, "polio": 70, "rabies": 50,
    "nipah": 85, "mers": 75, "covid": 65, "lassa": 75,
    "yellow fever": 65, "typhoid": 55, "meningitis": 60,
    "rift valley fever": 65, "crimean-congo": 70, "hantavirus": 65,
    "undiagnosed": 70,  # ProMED often reports mystery illnesses
}


def estimate_severity(title: str, summary: str) -> int:
    """Estimate severity from disease keywords."""
    text = (title + " " + (summary or "")).lower()
    for disease, sev in DISEASE_KEYWORDS.items():
        if disease in text:
            return sev
    return 50


def extract_disease(title: str) -> str:
    """Extract disease from ProMED title."""
    text = title.lower()
    for disease in DISEASE_KEYWORDS:
        if disease in text:
            return disease.title()
    return "Unspecified"


def fetch_promed() -> list[dict]:
    """Fetch ProMED-mail RSS feed."""
    try:
        feed = feedparser.parse(PROMED_FEED)
        if feed.bozo and not feed.entries:
            logger.warning("ProMED feed parse error: %s", feed.bozo_exception)
            return []
        return feed.entries
    except Exception as e:
        logger.error("ProMED feed error: %s", e)
        return []


def ingest(conn) -> dict:
    """Fetch ProMED alerts and store as events + disease_outbreaks."""
    entries = fetch_promed()
    inserted = 0
    skipped = 0
    errors = 0

    for entry in entries:
        title = entry.get("title", "").strip()
        if not title:
            continue

        link = entry.get("link", "")
        summary = entry.get("summary", entry.get("description", ""))
        published = entry.get("published", "")

        try:
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                ts = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            else:
                ts = datetime.now(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)

        source_id = f"promed-{link}" if link else f"promed-{title[:80]}"
        disease = extract_disease(title)
        severity = estimate_severity(title, summary)

        # ProMED titles often have format: "DISEASE - COUNTRY: (REGION)"
        region = None
        if " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                region = parts[-1].strip().split(":")[0].strip()

        event_id = str(uuid.uuid4())
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, source_id, timestamp, title, summary, raw_payload,
                    region, category, severity, confidence, entities_json, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, "promed", source_id,
                    ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    title[:500], (summary or "")[:2000],
                    json.dumps({"feed_entry": title, "link": link}),
                    region, "health", severity, 0.80,
                    json.dumps([{"name": disease, "type": "disease", "role": "subject"}]),
                    link,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
                conn.execute(
                    """INSERT OR IGNORE INTO disease_outbreaks
                       (id, source, disease, title, summary, region,
                        status, severity, source_url, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, "promed", disease, title[:500], (summary or "")[:2000],
                        region, "active", severity, link,
                        ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    ),
                )
            else:
                skipped += 1
        except Exception as e:
            logger.error("Error inserting ProMED event: %s", e)
            errors += 1

    conn.commit()
    stats = {"source": "promed", "fetched": len(entries), "inserted": inserted, "skipped": skipped, "errors": errors}
    logger.info("ProMED ingestion: %s", stats)
    return stats
