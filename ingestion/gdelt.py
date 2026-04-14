"""
GDELT Events 2.0 ingestion connector.

Uses the GDELT file-based export (updated every 15 minutes) which is
far more reliable than the DOC API. Downloads the latest CSV export,
parses CAMEO-coded events, and inserts into the events table.

Data: http://data.gdeltproject.org/gdeltv2/lastupdate.txt
Schema: http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf
"""
import csv
import io
import json
import logging
import uuid
import zipfile
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

GDELT_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

# CAMEO root codes mapped to Cerebro categories
# See: https://parusanalytics.com/eventdata/cameo.dir/CAMEO.Manual.1.1b3.pdf
CAMEO_CATEGORY_MAP = {
    "01": "political",      # Make public statement
    "02": "political",      # Appeal
    "03": "political",      # Express intent to cooperate
    "04": "political",      # Consult
    "05": "political",      # Engage in diplomatic cooperation
    "06": "political",      # Engage in material cooperation
    "07": "political",      # Provide aid
    "08": "political",      # Yield
    "09": "political",      # Investigate
    "10": "political",      # Demand
    "11": "political",      # Disapprove
    "12": "political",      # Reject
    "13": "political",      # Threaten
    "14": "military",       # Protest
    "15": "military",       # Exhibit force posture
    "16": "military",       # Reduce relations
    "17": "military",       # Coerce
    "18": "military",       # Assault
    "19": "military",       # Fight
    "20": "military",       # Use unconventional mass violence
}

# GDELT Events 2.0 CSV columns (57 columns)
# We use a subset of the most useful ones
COLUMN_NAMES = [
    "GlobalEventID", "Day", "MonthYear", "Year", "FractionDate",
    "Actor1Code", "Actor1Name", "Actor1CountryCode", "Actor1KnownGroupCode",
    "Actor1EthnicCode", "Actor1Religion1Code", "Actor1Religion2Code",
    "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
    "Actor2Code", "Actor2Name", "Actor2CountryCode", "Actor2KnownGroupCode",
    "Actor2EthnicCode", "Actor2Religion1Code", "Actor2Religion2Code",
    "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
    "IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode",
    "QuadClass", "GoldsteinScale", "NumMentions", "NumSources",
    "NumArticles", "AvgTone",
    "Actor1Geo_Type", "Actor1Geo_FullName", "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code", "Actor1Geo_ADM2Code",
    "Actor1Geo_Lat", "Actor1Geo_Long", "Actor1Geo_FeatureID",
    "Actor2Geo_Type", "Actor2Geo_FullName", "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code", "Actor2Geo_ADM2Code",
    "Actor2Geo_Lat", "Actor2Geo_Long", "Actor2Geo_FeatureID",
    "ActionGeo_Type", "ActionGeo_FullName", "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code", "ActionGeo_ADM2Code",
    "ActionGeo_Lat", "ActionGeo_Long", "ActionGeo_FeatureID",
    "DATEADDED", "SOURCEURL",
]


def _parse_row(row: dict) -> dict | None:
    """Convert a GDELT CSV row into a Cerebro event dict."""
    event_id = row.get("GlobalEventID", "")
    if not event_id:
        return None

    # Build title from actors and event
    actor1 = row.get("Actor1Name", "").strip() or row.get("Actor1Code", "").strip() or "Unknown"
    actor2 = row.get("Actor2Name", "").strip() or row.get("Actor2Code", "").strip() or "Unknown"
    event_code = row.get("EventCode", "")
    root_code = row.get("EventRootCode", "")

    title = f"{actor1} → {actor2} (CAMEO {event_code})"

    # Timestamp from DATEADDED (format: YYYYMMDDHHMMSS)
    date_added = row.get("DATEADDED", "")
    try:
        dt = datetime.strptime(date_added[:14], "%Y%m%d%H%M%S")
        timestamp = dt.replace(tzinfo=timezone.utc).isoformat()
    except (ValueError, IndexError):
        timestamp = datetime.now(timezone.utc).isoformat()

    # Location — prefer ActionGeo (where event happened)
    lat = None
    lon = None
    country_code = None
    region = None

    for prefix in ["ActionGeo", "Actor1Geo", "Actor2Geo"]:
        lat_str = row.get(f"{prefix}_Lat", "")
        lon_str = row.get(f"{prefix}_Long", "")
        if lat_str and lon_str:
            try:
                lat = float(lat_str)
                lon = float(lon_str)
                country_code = row.get(f"{prefix}_CountryCode", "")[:2] or None
                region = row.get(f"{prefix}_FullName", "") or None
                break
            except ValueError:
                continue

    # Category from CAMEO root code
    category = CAMEO_CATEGORY_MAP.get(root_code)

    # Goldstein scale (-10 to +10) → severity (0-100)
    # More negative = more conflictual = higher severity
    goldstein = row.get("GoldsteinScale", "")
    severity = 0
    try:
        g = float(goldstein)
        severity = max(0, min(100, ((-g + 10) / 20) * 100))
    except ValueError:
        pass

    # Confidence from number of sources/mentions
    num_sources = 0
    try:
        num_sources = int(row.get("NumSources", "0"))
    except ValueError:
        pass
    confidence = min(1.0, num_sources / 10.0)  # 10+ sources = full confidence

    # Summary
    tone = row.get("AvgTone", "")
    num_mentions = row.get("NumMentions", "0")
    num_articles = row.get("NumArticles", "0")
    quad_class = row.get("QuadClass", "")
    quad_labels = {"1": "Verbal Cooperation", "2": "Material Cooperation",
                   "3": "Verbal Conflict", "4": "Material Conflict"}
    quad_label = quad_labels.get(quad_class, f"Class {quad_class}")

    summary = (
        f"{quad_label} | Goldstein: {goldstein} | Tone: {tone} | "
        f"Mentions: {num_mentions} | Articles: {num_articles} | Sources: {num_sources}"
    )

    # Entities extracted from actors
    entities = []
    if actor1 and actor1 != "Unknown":
        entities.append({"name": actor1, "type": "actor", "role": "source"})
    if actor2 and actor2 != "Unknown":
        entities.append({"name": actor2, "type": "actor", "role": "target"})

    return {
        "id": str(uuid.uuid4()),
        "source": "gdelt",
        "source_id": f"gdelt-{event_id}",
        "timestamp": timestamp,
        "title": title[:500],
        "summary": summary,
        "raw_payload": json.dumps(row),
        "latitude": lat,
        "longitude": lon,
        "country_code": country_code,
        "region": region,
        "category": category,
        "severity": round(severity, 1),
        "confidence": round(confidence, 2),
        "entities_json": json.dumps(entities) if entities else None,
        "source_url": row.get("SOURCEURL", ""),
    }


def fetch_latest_export() -> list[dict]:
    """Download and parse the latest GDELT Events 2.0 CSV export."""
    # Get the latest update file URL
    try:
        resp = httpx.get(GDELT_LASTUPDATE_URL, timeout=15.0)
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("Failed to fetch GDELT lastupdate: %s", e)
        return []

    # Parse the first line to get the export CSV URL
    lines = resp.text.strip().split("\n")
    export_url = None
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and ".export.CSV.zip" in parts[2]:
            export_url = parts[2]
            break

    if not export_url:
        logger.error("Could not find export URL in lastupdate.txt")
        return []

    logger.info("Downloading GDELT export: %s", export_url)

    # Download the CSV zip
    try:
        resp = httpx.get(export_url, timeout=60.0)
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("Failed to download GDELT export: %s", e)
        return []

    # Extract CSV from zip
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = zf.namelist()[0]
            csv_data = zf.read(csv_name).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, IndexError) as e:
        logger.error("Failed to extract GDELT CSV: %s", e)
        return []

    # Parse CSV (tab-delimited, no header)
    rows = []
    reader = csv.reader(io.StringIO(csv_data), delimiter="\t")
    for raw_row in reader:
        if len(raw_row) >= len(COLUMN_NAMES):
            row_dict = dict(zip(COLUMN_NAMES, raw_row))
            rows.append(row_dict)
        elif len(raw_row) >= 40:
            # Pad with empty strings if slightly short
            padded = raw_row + [""] * (len(COLUMN_NAMES) - len(raw_row))
            row_dict = dict(zip(COLUMN_NAMES, padded))
            rows.append(row_dict)

    logger.info("Parsed %d events from GDELT export", len(rows))
    return rows


def ingest(conn, max_events: int | None = None) -> dict:
    """
    Fetch latest GDELT export and insert new events into the database.
    Returns stats dict with counts.
    """
    rows = fetch_latest_export()
    if max_events:
        rows = rows[:max_events]

    inserted = 0
    skipped = 0
    errors = 0

    for row in rows:
        event = _parse_row(row)
        if event is None:
            skipped += 1
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
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error("Error inserting GDELT event: %s", e)
            errors += 1

    conn.commit()

    stats = {
        "source": "gdelt",
        "fetched": len(rows),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("GDELT ingestion complete: %s", stats)
    return stats
