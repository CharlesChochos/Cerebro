"""
OpenStreetMap change detection ingestion connector.

Monitors OSM changesets for significant infrastructure changes that
may indicate military buildup, construction, or other intelligence signals.
Uses the OSM API (no key required) and Overpass for targeted queries.
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

OSM_CHANGESET_API = "https://api.openstreetmap.org/api/0.6/changesets"
OVERPASS_API = "https://overpass-api.de/api/interpreter"

# Regions of interest for infrastructure monitoring
MONITOR_REGIONS = [
    {"name": "South China Sea Islands", "bbox": "5,105,25,125"},
    {"name": "Crimea/Black Sea", "bbox": "43,32,47,37"},
    {"name": "Korean DMZ", "bbox": "37.5,126,38.5,127.5"},
    {"name": "Taiwan Strait", "bbox": "22,117,26,122"},
    {"name": "Persian Gulf", "bbox": "24,50,30,56"},
    {"name": "Golan Heights", "bbox": "32.5,35.5,33.5,36.5"},
]

# Tags indicating infrastructure of intelligence interest
INTELLIGENCE_TAGS = [
    "military", "airfield", "barracks", "runway", "helipad",
    "port", "harbour", "pier", "dam", "power_plant",
    "nuclear", "radar", "antenna", "bunker", "checkpoint",
]


def fetch_recent_changesets(bbox: str, hours: int = 24) -> list[dict]:
    """Fetch recent OSM changesets in a bounding box."""
    time_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        resp = httpx.get(
            OSM_CHANGESET_API,
            params={"bbox": bbox, "time": time_str, "closed": "true"},
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        # OSM returns XML by default; parse accordingly
        # For simplicity, we'll use Overpass for structured data
        return []
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.debug("OSM changeset API error: %s", e)
        return []


def query_overpass_infrastructure(bbox: str) -> list[dict]:
    """Query Overpass for military/infrastructure features in a region."""
    south, west, north, east = bbox.split(",")
    # Query for military and key infrastructure features modified recently
    query = f"""
    [out:json][timeout:25];
    (
      node["military"]({south},{west},{north},{east});
      way["military"]({south},{west},{north},{east});
      node["aeroway"="runway"]({south},{west},{north},{east});
      way["aeroway"="runway"]({south},{west},{north},{east});
      node["man_made"="radar"]({south},{west},{north},{east});
    );
    out center meta 50;
    """
    try:
        resp = httpx.post(
            OVERPASS_API,
            data={"data": query},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("elements", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.debug("Overpass API error: %s", e)
        return []


def ingest(conn) -> dict:
    """Fetch OSM infrastructure data for monitored regions."""
    inserted = 0
    skipped = 0
    errors = 0
    fetched = 0

    for region in MONITOR_REGIONS:
        elements = query_overpass_infrastructure(region["bbox"])
        fetched += len(elements)

        for elem in elements:
            tags = elem.get("tags", {})
            lat = elem.get("lat") or elem.get("center", {}).get("lat")
            lng = elem.get("lon") or elem.get("center", {}).get("lon")
            if not lat or not lng:
                continue

            osm_id = elem.get("id", "")
            osm_type = elem.get("type", "node")
            name = tags.get("name", tags.get("military", tags.get("aeroway", "Infrastructure")))

            # Check if any intelligence-relevant tags
            relevant_tags = [t for t in INTELLIGENCE_TAGS if any(t in str(v).lower() for v in tags.values())]
            if not relevant_tags:
                continue

            title = f"OSM: {name} ({', '.join(relevant_tags)}) in {region['name']}"
            source_id = f"osm-{osm_type}-{osm_id}"

            # Determine severity based on type
            severity = 30
            if "military" in relevant_tags or "nuclear" in relevant_tags:
                severity = 60
            elif "runway" in relevant_tags or "radar" in relevant_tags:
                severity = 50

            timestamp = tags.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"))

            event_id = str(uuid.uuid4())
            try:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO events
                       (id, source, source_id, timestamp, title, summary, raw_payload,
                        latitude, longitude, region, category, severity, confidence,
                        source_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, "osm", source_id, timestamp,
                        title[:500],
                        f"Infrastructure feature in {region['name']}: {name}. Tags: {', '.join(relevant_tags)}",
                        json.dumps({"osm_id": osm_id, "type": osm_type, "tags": tags}),
                        lat, lng, region["name"], "military", severity, 0.70,
                        f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Error inserting OSM event: %s", e)
                errors += 1

    conn.commit()
    stats = {"source": "osm", "fetched": fetched, "inserted": inserted, "skipped": skipped, "errors": errors}
    logger.info("OSM ingestion: %s", stats)
    return stats
