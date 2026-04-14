"""
RSS feed fleet ingestion connector.

Monitors 50+ global news RSS feeds across multiple languages and regions.
No API key required. Feeds update in near real-time.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

logger = logging.getLogger(__name__)

# RSS feeds organized by region/type
FEEDS = {
    # === Major Wire Services ===
    "reuters_world": "https://feeds.reuters.com/Reuters/worldNews",
    "ap_topnews": "https://rsshub.app/apnews/topics/apf-topnews",
    "afp_en": "https://www.france24.com/en/rss",

    # === English-Language Global ===
    "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "guardian_world": "https://www.theguardian.com/world/rss",
    "nytimes_world": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "washpost_world": "https://feeds.washingtonpost.com/rss/world",
    "dw_en": "https://rss.dw.com/rdf/rss-en-world",
    "france24_en": "https://www.france24.com/en/rss",

    # === Conflict & Security ===
    "bbc_middleeast": "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "bbc_africa": "http://feeds.bbci.co.uk/news/world/africa/rss.xml",
    "bbc_asia": "http://feeds.bbci.co.uk/news/world/asia/rss.xml",
    "bbc_europe": "http://feeds.bbci.co.uk/news/world/europe/rss.xml",
    "bbc_latinamerica": "http://feeds.bbci.co.uk/news/world/latin_america/rss.xml",

    # === Financial & Economic ===
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "ft_world": "https://www.ft.com/rss/home/international",
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",
    "cnbc_world": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "economist": "https://www.economist.com/international/rss.xml",

    # === Science & Health ===
    "who_news": "https://www.who.int/rss-feeds/news-english.xml",
    "bbc_scienv": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "nature_news": "https://www.nature.com/nature.rss",

    # === Regional Perspectives ===
    "scmp": "https://www.scmp.com/rss/91/feed",  # South China Morning Post
    "japantimes": "https://www.japantimes.co.jp/feed/",
    "hindu": "https://www.thehindu.com/news/international/feeder/default.rss",
    "moscow_times": "https://www.themoscowtimes.com/rss/news",
    "kyiv_independent": "https://kyivindependent.com/feed/",
    "timesofisrael": "https://www.timesofisrael.com/feed/",
    "african_news": "https://www.africanews.com/feed/",

    # === Defense & Military ===
    "defense_one": "https://www.defenseone.com/rss/",
    "janes": "https://www.janes.com/feeds/news",
    "war_on_rocks": "https://warontherocks.com/feed/",

    # === Technology & Cyber ===
    "ars_security": "https://feeds.arstechnica.com/arstechnica/security",
    "therecord": "https://therecord.media/feed/",
    "bleepingcomputer": "https://www.bleepingcomputer.com/feed/",

    # === Energy & Environment ===
    "carbon_brief": "https://www.carbonbrief.org/feed/",
    "oilprice": "https://oilprice.com/rss/main",
    "climate_home": "https://www.climatechangenews.com/feed/",
}


def _generate_source_id(url: str, title: str) -> str:
    """Generate a deterministic source_id from URL + title to prevent duplicates."""
    content = f"{url}|{title}"
    return f"rss-{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def _parse_entry(entry: dict, feed_name: str) -> dict | None:
    """Convert a feedparser entry into a Cerebro event dict."""
    title = entry.get("title", "").strip()
    if not title:
        return None

    link = entry.get("link", "")
    summary = entry.get("summary", entry.get("description", ""))
    # Strip HTML tags from summary (basic)
    if summary:
        import re
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        summary = summary[:500]

    # Parse publish date
    published = entry.get("published", entry.get("updated", ""))
    try:
        if published:
            dt = parsedate_to_datetime(published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            timestamp = dt.isoformat()
        else:
            timestamp = datetime.now(timezone.utc).isoformat()
    except (ValueError, TypeError):
        timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "id": str(uuid.uuid4()),
        "source": "rss",
        "source_id": _generate_source_id(link, title),
        "timestamp": timestamp,
        "title": title[:500],
        "summary": f"[{feed_name}] {summary}" if summary else f"[{feed_name}]",
        "raw_payload": json.dumps({
            "feed": feed_name,
            "link": link,
            "published": published,
            "author": entry.get("author", ""),
            "tags": [t.get("term", "") for t in entry.get("tags", [])],
        }),
        "latitude": None,
        "longitude": None,
        "country_code": None,
        "region": None,
        "category": None,  # Will be classified by Claude
        "severity": 0,
        "confidence": 0,
        "entities_json": None,
        "source_url": link,
    }


def fetch_feed(feed_name: str, feed_url: str) -> list[dict]:
    """Fetch and parse a single RSS feed. Returns list of parsed entries."""
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            logger.warning("Feed %s returned bozo error: %s", feed_name, feed.bozo_exception)
            return []
        return feed.entries
    except Exception as e:
        logger.error("Failed to fetch feed %s: %s", feed_name, e)
        return []


def ingest(conn, feeds: dict | None = None, max_per_feed: int = 30) -> dict:
    """
    Fetch all RSS feeds and insert new events.
    Returns stats dict.
    """
    feeds = feeds or FEEDS
    total_fetched = 0
    total_inserted = 0
    total_skipped = 0
    total_errors = 0
    feeds_processed = 0
    feeds_failed = 0

    for feed_name, feed_url in feeds.items():
        entries = fetch_feed(feed_name, feed_url)
        if not entries:
            feeds_failed += 1
            continue

        feeds_processed += 1
        for entry in entries[:max_per_feed]:
            total_fetched += 1
            event = _parse_entry(entry, feed_name)
            if event is None:
                total_skipped += 1
                continue

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
                    total_inserted += 1
                else:
                    total_skipped += 1
            except Exception as e:
                logger.error("Error inserting RSS event from %s: %s", feed_name, e)
                total_errors += 1

    conn.commit()

    stats = {
        "source": "rss",
        "feeds_total": len(feeds),
        "feeds_processed": feeds_processed,
        "feeds_failed": feeds_failed,
        "fetched": total_fetched,
        "inserted": total_inserted,
        "skipped": total_skipped,
        "errors": total_errors,
    }
    logger.info("RSS ingestion complete: %s", stats)
    return stats
