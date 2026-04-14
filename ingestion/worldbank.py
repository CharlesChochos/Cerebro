"""
World Bank Open Data ingestion connector.

Fetches macro indicators for 190+ countries.
No API key required. Data updates monthly/quarterly.
API docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

WB_API_BASE = "https://api.worldbank.org/v2"

# Key indicators to monitor
INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": {"name": "GDP Growth (annual %)", "category": "economic"},
    "FP.CPI.TOTL.ZG": {"name": "Inflation (CPI, annual %)", "category": "economic"},
    "SL.UEM.TOTL.ZS": {"name": "Unemployment Rate (%)", "category": "economic"},
    "BN.CAB.XOKA.GD.ZS": {"name": "Current Account Balance (% GDP)", "category": "economic"},
    "GC.DOD.TOTL.GD.ZS": {"name": "Government Debt (% GDP)", "category": "economic"},
    "SP.POP.GROW": {"name": "Population Growth (annual %)", "category": "health"},
    "SH.DYN.MORT": {"name": "Under-5 Mortality Rate (per 1,000)", "category": "health"},
    "EG.USE.PCAP.KG.OE": {"name": "Energy Use (kg oil equiv per capita)", "category": "environmental"},
}

# Focus countries (G20 + key hotspots)
COUNTRIES = [
    "USA", "CHN", "JPN", "DEU", "GBR", "FRA", "IND", "ITA", "BRA", "CAN",
    "RUS", "KOR", "AUS", "MEX", "IDN", "TUR", "SAU", "ARG", "ZAF", "NGA",
    "EGY", "IRN", "UKR", "POL", "THA", "VNM", "COL", "PAK", "PHL",
]


def fetch_indicator(indicator_code: str, countries: str = "all", mrv: int = 2) -> list[dict]:
    """
    Fetch most recent values for an indicator.
    mrv = most recent values (number of data points per country).
    """
    url = f"{WB_API_BASE}/country/{countries}/indicator/{indicator_code}"
    params = {
        "format": "json",
        "per_page": "500",
        "mrv": str(mrv),
    }

    try:
        resp = httpx.get(url, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("World Bank API error for %s: %s", indicator_code, e)
        return []
    except Exception:
        logger.error("Failed to parse World Bank response for %s", indicator_code)
        return []

    # WB API returns [metadata, data_array]
    if not isinstance(data, list) or len(data) < 2:
        return []

    return data[1] or []


def ingest(conn, countries: list[str] | None = None) -> dict:
    """Fetch World Bank indicators and insert as events."""
    country_str = ";".join(countries or COUNTRIES)
    inserted = 0
    skipped = 0
    errors = 0
    fetched = 0

    for code, meta in INDICATORS.items():
        records = fetch_indicator(code, country_str, mrv=1)
        for record in records:
            if record is None or record.get("value") is None:
                continue

            fetched += 1
            country_name = record.get("country", {}).get("value", "Unknown")
            country_id = record.get("country", {}).get("id", "")
            year = record.get("date", "")
            value = record.get("value")

            title = f"{country_name}: {meta['name']} = {value:.2f} ({year})"
            source_id = f"wb-{code}-{country_id}-{year}"

            event = {
                "id": str(uuid.uuid4()),
                "source": "worldbank",
                "source_id": source_id,
                "timestamp": f"{year}-01-01T00:00:00+00:00" if year else datetime.now(timezone.utc).isoformat(),
                "title": title[:500],
                "summary": f"{meta['name']} for {country_name} in {year}: {value:.2f}",
                "raw_payload": json.dumps(record),
                "latitude": None,
                "longitude": None,
                "country_code": country_id[:2] if country_id else None,
                "region": country_name,
                "category": meta["category"],
                "severity": 10,  # Baseline macro data, not an alert
                "confidence": 0.99,  # Official statistics
                "entities_json": json.dumps([
                    {"name": country_name, "type": "location", "role": "subject"},
                    {"name": meta["name"], "type": "indicator", "role": "measure"},
                ]),
                "source_url": f"https://data.worldbank.org/indicator/{code}?locations={country_id}",
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
                logger.error("Error inserting WB event: %s", e)
                errors += 1

    conn.commit()
    stats = {
        "source": "worldbank",
        "fetched": fetched,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("World Bank ingestion: %s", stats)
    return stats
