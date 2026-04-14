"""
UN Comtrade bilateral trade data ingestion connector.

Fetches international trade statistics to detect trade disruptions,
sanctions effects, and supply chain shifts.
No API key required for basic access (rate-limited).
Source: https://comtradeapi.un.org/
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

COMTRADE_API = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

# Key commodity codes to monitor (HS2 level)
COMMODITY_CODES = {
    "27": "Mineral fuels, oils",
    "71": "Precious stones & metals",
    "84": "Machinery & mechanical appliances",
    "85": "Electrical machinery & equipment",
    "72": "Iron & steel",
    "10": "Cereals (wheat, rice, corn)",
    "31": "Fertilizers",
    "26": "Ores, slag & ash",
    "28": "Inorganic chemicals",
    "90": "Optical & precision instruments",
}

# Key trade corridors to monitor
TRADE_CORRIDORS = [
    {"reporter": "156", "partner": "842", "label": "China → USA"},
    {"reporter": "842", "partner": "156", "label": "USA → China"},
    {"reporter": "276", "partner": "643", "label": "Germany → Russia"},
    {"reporter": "643", "partner": "156", "label": "Russia → China"},
    {"reporter": "356", "partner": "156", "label": "India → China"},
]


def fetch_trade_data(reporter_code: str, partner_code: str, period: str = "recent") -> list[dict]:
    """Fetch bilateral trade data from Comtrade."""
    try:
        params = {
            "reporterCode": reporter_code,
            "partnerCode": partner_code,
            "period": period,
            "flowCode": "M,X",  # imports and exports
        }
        resp = httpx.get(COMTRADE_API, params=params, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("Comtrade API error: %s", e)
        return []


def ingest(conn) -> dict:
    """Fetch Comtrade trade data for monitored corridors."""
    inserted = 0
    skipped = 0
    errors = 0
    fetched = 0

    for corridor in TRADE_CORRIDORS:
        records = fetch_trade_data(corridor["reporter"], corridor["partner"])
        fetched += len(records)

        for rec in records:
            trade_value = rec.get("primaryValue")
            if not trade_value:
                continue

            cmd_code = rec.get("cmdCode", "")
            cmd_desc = rec.get("cmdDesc", COMMODITY_CODES.get(cmd_code, "Unknown"))
            flow = rec.get("flowDesc", "Trade")
            period = rec.get("period", "")
            reporter = rec.get("reporterDesc", "")
            partner = rec.get("partnerDesc", "")

            title = f"Comtrade: {reporter} {flow} to {partner} — {cmd_desc} ${trade_value:,.0f} ({period})"
            source_id = f"comtrade-{corridor['reporter']}-{corridor['partner']}-{cmd_code}-{period}"

            event_id = str(uuid.uuid4())
            try:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO events
                       (id, source, source_id, timestamp, title, summary, raw_payload,
                        category, severity, confidence, entities_json, source_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, "comtrade", source_id,
                        f"{period}-01T00:00:00+00:00" if len(str(period)) == 7 else f"{period}T00:00:00+00:00",
                        title[:500],
                        f"{flow}: {reporter} → {partner}, {cmd_desc}, value ${trade_value:,.0f}",
                        json.dumps(rec),
                        "economic", 10, 0.95,
                        json.dumps([
                            {"name": reporter, "type": "location", "role": "reporter"},
                            {"name": partner, "type": "location", "role": "partner"},
                        ]),
                        "https://comtradeplus.un.org/",
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Error inserting Comtrade event: %s", e)
                errors += 1

    conn.commit()
    stats = {"source": "comtrade", "fetched": fetched, "inserted": inserted, "skipped": skipped, "errors": errors}
    logger.info("Comtrade ingestion: %s", stats)
    return stats
