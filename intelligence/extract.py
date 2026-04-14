"""
Entity extraction module.

Provides two modes:
1. Regex-based extraction (no API key needed) — extracts entities from
   structured GDELT data and event titles/summaries
2. Claude-based NER (requires API key) — richer extraction with relationships

The regex mode runs as a fallback when Claude is unavailable.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Common organization patterns
ORG_PATTERNS = [
    r"\b(NATO|UN|EU|WHO|IMF|OPEC|ASEAN|BRICS|G7|G20|ICC|ICJ|WTO)\b",
    r"\b(United Nations|European Union|African Union|Arab League)\b",
    r"\b(World Bank|Federal Reserve|ECB|Bank of England)\b",
    r"\b(Pentagon|Kremlin|White House|Downing Street)\b",
]

# Country name to code mapping (most referenced)
COUNTRY_NAMES = {
    "United States": "US", "Russia": "RU", "China": "CN", "Ukraine": "UA",
    "Israel": "IL", "Palestine": "PS", "Iran": "IR", "Iraq": "IQ",
    "Syria": "SY", "Turkey": "TR", "Saudi Arabia": "SA", "India": "IN",
    "Pakistan": "PK", "Afghanistan": "AF", "North Korea": "KP",
    "South Korea": "KR", "Japan": "JP", "Taiwan": "TW", "Germany": "DE",
    "France": "FR", "United Kingdom": "UK", "Brazil": "BR", "Mexico": "MX",
    "Nigeria": "NG", "South Africa": "ZA", "Egypt": "EG", "Ethiopia": "ET",
    "Yemen": "YE", "Libya": "LY", "Sudan": "SD", "Somalia": "SO",
    "Myanmar": "MM", "Venezuela": "VE", "Colombia": "CO", "Argentina": "AR",
}


def extract_entities_regex(title: str, summary: str = "", entities_json: str = "") -> list[dict]:
    """
    Extract entities using regex patterns from event text.
    Returns list of entity dicts with name, type, and confidence.
    """
    entities = {}
    text = f"{title} {summary}"

    # Extract from existing entities_json (GDELT actors)
    if entities_json:
        try:
            existing = json.loads(entities_json)
            for e in existing:
                name = e.get("name", "").strip()
                if name and len(name) > 2 and name != "Unknown":
                    key = name.lower()
                    if key not in entities:
                        entities[key] = {
                            "name": name,
                            "entity_type": "actor",
                            "confidence": 0.7,
                        }
        except (json.JSONDecodeError, TypeError):
            pass

    # Extract organizations
    for pattern in ORG_PATTERNS:
        for match in re.finditer(pattern, text):
            name = match.group(0)
            key = name.lower()
            if key not in entities:
                entities[key] = {
                    "name": name,
                    "entity_type": "organization",
                    "confidence": 0.9,
                }

    # Extract country names
    for country, code in COUNTRY_NAMES.items():
        if country.lower() in text.lower():
            key = country.lower()
            if key not in entities:
                entities[key] = {
                    "name": country,
                    "entity_type": "location",
                    "confidence": 0.85,
                    "metadata": {"country_code": code},
                }

    return list(entities.values())


def process_events(conn, limit: int = 200) -> dict:
    """
    Extract entities from events that haven't been processed yet.
    Inserts into entities + entity_relations tables.
    """
    # Find events with no entities extracted yet
    rows = conn.execute(
        """SELECT id, title, summary, entities_json, country_code
           FROM events
           WHERE id NOT IN (
               SELECT DISTINCT entity_id FROM audit_log
               WHERE action = 'entities_extracted' AND entity_type = 'event'
           )
           ORDER BY ingested_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    events_processed = 0
    entities_created = 0
    relations_created = 0

    for row in rows:
        event = dict(row)
        extracted = extract_entities_regex(
            event.get("title", ""),
            event.get("summary", ""),
            event.get("entities_json", ""),
        )

        event_entity_ids = []

        for ent in extracted:
            # Upsert entity
            existing = conn.execute(
                "SELECT id FROM entities WHERE name = ? AND entity_type = ?",
                (ent["name"], ent["entity_type"]),
            ).fetchone()

            if existing:
                entity_id = existing[0]
                conn.execute(
                    "UPDATE entities SET last_seen = ?, event_count = event_count + 1 WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), entity_id),
                )
            else:
                entity_id = str(uuid.uuid4())
                metadata = json.dumps(ent.get("metadata", {}))
                conn.execute(
                    """INSERT INTO entities (id, name, entity_type, metadata, event_count)
                       VALUES (?, ?, ?, ?, 1)""",
                    (entity_id, ent["name"], ent["entity_type"], metadata),
                )
                entities_created += 1

            event_entity_ids.append(entity_id)

        # Create relations between co-occurring entities in same event
        for i, id_a in enumerate(event_entity_ids):
            for id_b in event_entity_ids[i + 1:]:
                existing_rel = conn.execute(
                    """SELECT id FROM entity_relations
                       WHERE source_entity_id = ? AND target_entity_id = ?
                       AND source_event_id = ?""",
                    (id_a, id_b, event["id"]),
                ).fetchone()

                if not existing_rel:
                    conn.execute(
                        """INSERT INTO entity_relations
                           (id, source_entity_id, target_entity_id, relation_type,
                            confidence, source_event_id)
                           VALUES (?, ?, ?, 'co_occurs', 0.5, ?)""",
                        (str(uuid.uuid4()), id_a, id_b, event["id"]),
                    )
                    relations_created += 1

        # Mark event as processed
        conn.execute(
            "INSERT INTO audit_log (action, entity_type, entity_id, details) VALUES (?, ?, ?, ?)",
            ("entities_extracted", "event", event["id"], json.dumps({"count": len(extracted)})),
        )
        events_processed += 1

    conn.commit()

    stats = {
        "events_processed": events_processed,
        "entities_created": entities_created,
        "relations_created": relations_created,
    }
    logger.info("Entity extraction: %s", stats)
    return stats
