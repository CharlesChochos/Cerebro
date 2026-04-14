"""
NASA VIIRS ingestion connector — fire detection + nighttime lights.

FIRMS (Fire Information for Resource Management System):
  Active fire hotspots from VIIRS I-Band 375m.
  No API key required for CSV endpoint; optional NASA Earthdata key for higher limits.
  Source: https://firms.modaps.eosdis.nasa.gov/

Nighttime Lights:
  VIIRS DNB (Day/Night Band) composite data.
  Source: https://eogdata.mines.edu/products/vnl/
"""
import csv
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

FIRMS_API_KEY = os.getenv("NASA_FIRMS_KEY", "OPEN")  # "OPEN" for anonymous access
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov"
FIRMS_CSV_URL = f"{FIRMS_BASE}/api/area/csv/{FIRMS_API_KEY}/VIIRS_NOAA20_NRT/world/1"

# Country-code to name for fire context
FIRE_SEVERITY_THRESHOLDS = {
    "high": 80,
    "nominal": 50,
    "low": 30,
}


def fetch_active_fires(days: int = 1) -> list[dict]:
    """Fetch VIIRS active fire detections from FIRMS."""
    url = f"{FIRMS_BASE}/api/area/csv/{FIRMS_API_KEY}/VIIRS_NOAA20_NRT/world/{days}"
    try:
        resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        return list(reader)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("FIRMS API error: %s", e)
        return []
    except Exception as e:
        logger.error("FIRMS parse error: %s", e)
        return []


def parse_fire_record(row: dict) -> dict | None:
    """Parse a FIRMS CSV row into a fire detection record."""
    try:
        lat = float(row.get("latitude", 0))
        lng = float(row.get("longitude", 0))
        if lat == 0 and lng == 0:
            return None

        brightness = float(row.get("bright_ti4", 0)) if row.get("bright_ti4") else None
        bright_ti5 = float(row.get("bright_ti5", 0)) if row.get("bright_ti5") else None
        frp = float(row.get("frp", 0)) if row.get("frp") else None
        confidence = row.get("confidence", "nominal").lower()
        daynight = row.get("daynight", "")
        acq_date = row.get("acq_date", "")
        acq_time = row.get("acq_time", "0000")

        return {
            "lat": lat,
            "lng": lng,
            "brightness": brightness,
            "bright_ti4": brightness,
            "bright_ti5": bright_ti5,
            "frp": frp,
            "confidence": confidence,
            "daynight": daynight,
            "capture_date": f"{acq_date}T{acq_time[:2]}:{acq_time[2:]}:00+00:00" if acq_date else None,
            "satellite": row.get("satellite", "NOAA-20"),
        }
    except (ValueError, TypeError) as e:
        logger.debug("Fire record parse error: %s", e)
        return None


def ingest_fires(conn) -> dict:
    """Fetch and store VIIRS active fire detections."""
    rows = fetch_active_fires(days=1)
    inserted = 0
    skipped = 0
    errors = 0

    # Process a sample — full global data can be huge
    # Focus on high-confidence fires only to keep volume manageable
    high_conf = [r for r in rows if r.get("confidence", "").lower() in ("high", "h")]
    sample = high_conf[:500]  # Cap at 500 most relevant

    for row in sample:
        fire = parse_fire_record(row)
        if not fire or not fire["capture_date"]:
            continue

        fire_id = str(uuid.uuid4())
        source_id = f"viirs-fire-{fire['lat']:.3f}-{fire['lng']:.3f}-{fire['capture_date'][:10]}"

        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO fire_detections
                   (id, lat, lng, brightness, bright_ti4, bright_ti5, frp,
                    confidence, daynight, capture_date, satellite)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fire_id, fire["lat"], fire["lng"],
                    fire["brightness"], fire["bright_ti4"], fire["bright_ti5"],
                    fire["frp"], fire["confidence"], fire["daynight"],
                    fire["capture_date"][:10], fire["satellite"],
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error("Error inserting fire detection: %s", e)
            errors += 1

    conn.commit()
    stats = {
        "source": "viirs_fires",
        "fetched": len(rows),
        "high_confidence": len(high_conf),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("VIIRS fire ingestion: %s", stats)
    return stats


def ingest(conn) -> dict:
    """Main ingestion entry point — fires."""
    return ingest_fires(conn)
