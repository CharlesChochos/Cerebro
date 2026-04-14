"""
FRED (Federal Reserve Economic Data) ingestion connector.

Fetches key US economic indicators from the St. Louis Fed.
API key is optional but recommended for higher rate limits.
Register free at: https://fred.stlouisfed.org/docs/api/api_key.html
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Key economic series to monitor
SERIES = {
    "UNRATE": {"name": "US Unemployment Rate", "unit": "%", "frequency": "monthly"},
    "CPIAUCSL": {"name": "US Consumer Price Index", "unit": "index", "frequency": "monthly"},
    "FEDFUNDS": {"name": "Federal Funds Rate", "unit": "%", "frequency": "monthly"},
    "GDP": {"name": "US GDP", "unit": "billions USD", "frequency": "quarterly"},
    "DGS10": {"name": "10-Year Treasury Yield", "unit": "%", "frequency": "daily"},
    "DGS2": {"name": "2-Year Treasury Yield", "unit": "%", "frequency": "daily"},
    "T10Y2Y": {"name": "10Y-2Y Yield Spread", "unit": "%", "frequency": "daily"},
    "DEXUSEU": {"name": "USD/EUR Exchange Rate", "unit": "USD per EUR", "frequency": "daily"},
    "DCOILWTICO": {"name": "WTI Crude Oil Price", "unit": "USD/barrel", "frequency": "daily"},
    "UMCSENT": {"name": "Consumer Sentiment (UMich)", "unit": "index", "frequency": "monthly"},
    "VIXCLS": {"name": "VIX Volatility Index", "unit": "index", "frequency": "daily"},
    "BAMLH0A0HYM2": {"name": "High Yield Bond Spread", "unit": "%", "frequency": "daily"},
    "M2SL": {"name": "M2 Money Supply", "unit": "billions USD", "frequency": "monthly"},
    "ICSA": {"name": "Initial Jobless Claims", "unit": "thousands", "frequency": "weekly"},
}


def fetch_series(series_id: str, limit: int = 5) -> list[dict]:
    """Fetch recent observations for a FRED series."""
    if not FRED_API_KEY:
        logger.debug("No FRED_API_KEY set — skipping %s", series_id)
        return []

    url = f"{FRED_API_BASE}/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(limit),
    }

    try:
        resp = httpx.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("observations", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("FRED API error for %s: %s", series_id, e)
        return []


def ingest(conn) -> dict:
    """Fetch FRED data and insert as events."""
    if not FRED_API_KEY:
        logger.warning("No FRED_API_KEY set — skipping FRED ingestion. Get one free at https://fred.stlouisfed.org/docs/api/api_key.html")
        return {"source": "fred", "fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "note": "no_api_key"}

    inserted = 0
    skipped = 0
    errors = 0
    fetched = 0

    for series_id, meta in SERIES.items():
        observations = fetch_series(series_id, limit=2)

        for obs in observations:
            value_str = obs.get("value", ".")
            if value_str == ".":
                continue  # Missing data point

            fetched += 1
            date = obs.get("date", "")
            try:
                value = float(value_str)
            except ValueError:
                continue

            title = f"FRED: {meta['name']} = {value:,.2f} {meta['unit']} ({date})"
            source_id = f"fred-{series_id}-{date}"

            event = {
                "id": str(uuid.uuid4()),
                "source": "fred",
                "source_id": source_id,
                "timestamp": f"{date}T00:00:00+00:00",
                "title": title[:500],
                "summary": f"{meta['name']} ({meta['frequency']}) as of {date}: {value:,.2f} {meta['unit']}",
                "raw_payload": json.dumps({
                    "series_id": series_id,
                    "name": meta["name"],
                    "value": value,
                    "unit": meta["unit"],
                    "date": date,
                    "frequency": meta["frequency"],
                }),
                "latitude": None,
                "longitude": None,
                "country_code": "US",
                "region": "United States",
                "category": "economic",
                "severity": 10,
                "confidence": 0.99,
                "entities_json": json.dumps([
                    {"name": meta["name"], "type": "indicator", "role": "subject"}
                ]),
                "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
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
                logger.error("Error inserting FRED event: %s", e)
                errors += 1

    conn.commit()
    stats = {
        "source": "fred",
        "fetched": fetched,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("FRED ingestion: %s", stats)
    return stats
