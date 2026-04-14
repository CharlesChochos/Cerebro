"""
EIA (US Energy Information Administration) ingestion connector.

Fetches energy market data: oil prices, gas inventories, production stats.
Free API key required: https://www.eia.gov/opendata/register.php
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

EIA_API_BASE = "https://api.eia.gov/v2"
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

# Key energy series to monitor
SERIES = {
    "PET.RWTC.D": {
        "name": "WTI Crude Oil Spot Price",
        "route": "petroleum/pri/spt/data/",
        "params": {"frequency": "daily", "data[0]": "value", "facets[series][]": "RWTC", "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "5"},
        "unit": "$/barrel",
    },
    "NG.RNGWHHD.D": {
        "name": "Henry Hub Natural Gas Spot Price",
        "route": "natural-gas/pri/fut/data/",
        "params": {"frequency": "daily", "data[0]": "value", "facets[series][]": "RNGWHHD", "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "5"},
        "unit": "$/MMBtu",
    },
    "PET.WCESTUS1.W": {
        "name": "US Crude Oil Commercial Stocks",
        "route": "petroleum/stoc/wstk/data/",
        "params": {"frequency": "weekly", "data[0]": "value", "facets[series][]": "WCESTUS1", "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "5"},
        "unit": "thousand barrels",
    },
    "ELEC.GEN.ALL-US-99.M": {
        "name": "US Total Electricity Generation",
        "route": "electricity/electric-power-operational-data/data/",
        "params": {"frequency": "monthly", "data[0]": "generation", "facets[sectorid][]": "99", "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "3"},
        "unit": "thousand MWh",
    },
}


def fetch_series(series_id: str, meta: dict) -> list[dict]:
    """Fetch EIA data series."""
    if not EIA_API_KEY:
        return []

    url = f"{EIA_API_BASE}/{meta['route']}"
    params = {**meta["params"], "api_key": EIA_API_KEY}

    try:
        resp = httpx.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", {}).get("data", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("EIA API error for %s: %s", series_id, e)
        return []


def ingest(conn) -> dict:
    """Fetch EIA energy data and insert as events."""
    if not EIA_API_KEY:
        logger.warning("No EIA_API_KEY set — skipping EIA ingestion")
        return {"source": "eia", "fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "note": "no_api_key"}

    inserted = 0
    skipped = 0
    errors = 0
    fetched = 0

    for series_id, meta in SERIES.items():
        observations = fetch_series(series_id, meta)

        for obs in observations:
            value = obs.get("value")
            if value is None:
                continue

            fetched += 1
            period = obs.get("period", "")

            try:
                value_float = float(value)
            except (ValueError, TypeError):
                continue

            title = f"EIA: {meta['name']} = {value_float:,.2f} {meta['unit']} ({period})"
            source_id = f"eia-{series_id}-{period}"

            event_id = str(uuid.uuid4())
            try:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO events
                       (id, source, source_id, timestamp, title, summary, raw_payload,
                        country_code, region, category, severity, confidence,
                        entities_json, source_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, "eia", source_id,
                        f"{period}T00:00:00+00:00" if len(period) >= 10 else f"{period}-01T00:00:00+00:00",
                        title[:500],
                        f"{meta['name']}: {value_float:,.2f} {meta['unit']}",
                        json.dumps({"series_id": series_id, "value": value_float, "period": period}),
                        "US", "United States", "economic", 15, 0.99,
                        json.dumps([{"name": meta["name"], "type": "indicator", "role": "subject"}]),
                        f"https://www.eia.gov/opendata/browser/",
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Error inserting EIA event: %s", e)
                errors += 1

    conn.commit()
    stats = {"source": "eia", "fetched": fetched, "inserted": inserted, "skipped": skipped, "errors": errors}
    logger.info("EIA ingestion: %s", stats)
    return stats
