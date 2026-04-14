"""
Yahoo Finance ingestion connector via yfinance.

Monitors key global market indices, commodities, and currencies.
No API key required. 15-minute delayed quotes.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import yfinance as yf

logger = logging.getLogger(__name__)

# Key tickers to monitor — indices, commodities, currencies
WATCHLIST = {
    # Major indices
    "^GSPC": {"name": "S&P 500", "type": "index", "region": "US"},
    "^DJI": {"name": "Dow Jones", "type": "index", "region": "US"},
    "^IXIC": {"name": "NASDAQ", "type": "index", "region": "US"},
    "^FTSE": {"name": "FTSE 100", "type": "index", "region": "UK"},
    "^GDAXI": {"name": "DAX", "type": "index", "region": "DE"},
    "^N225": {"name": "Nikkei 225", "type": "index", "region": "JP"},
    "^HSI": {"name": "Hang Seng", "type": "index", "region": "HK"},
    "000001.SS": {"name": "Shanghai Composite", "type": "index", "region": "CN"},

    # Commodities
    "CL=F": {"name": "Crude Oil (WTI)", "type": "commodity", "region": "GLOBAL"},
    "BZ=F": {"name": "Brent Crude", "type": "commodity", "region": "GLOBAL"},
    "GC=F": {"name": "Gold", "type": "commodity", "region": "GLOBAL"},
    "SI=F": {"name": "Silver", "type": "commodity", "region": "GLOBAL"},
    "NG=F": {"name": "Natural Gas", "type": "commodity", "region": "GLOBAL"},
    "ZW=F": {"name": "Wheat", "type": "commodity", "region": "GLOBAL"},

    # Currencies (vs USD)
    "EURUSD=X": {"name": "EUR/USD", "type": "currency", "region": "GLOBAL"},
    "GBPUSD=X": {"name": "GBP/USD", "type": "currency", "region": "GLOBAL"},
    "JPY=X": {"name": "USD/JPY", "type": "currency", "region": "GLOBAL"},
    "CNY=X": {"name": "USD/CNY", "type": "currency", "region": "GLOBAL"},
    "RUBUSD=X": {"name": "RUB/USD", "type": "currency", "region": "GLOBAL"},

    # Crypto (as market sentiment indicator)
    "BTC-USD": {"name": "Bitcoin", "type": "crypto", "region": "GLOBAL"},

    # Volatility
    "^VIX": {"name": "VIX (Fear Index)", "type": "volatility", "region": "US"},
}

# Thresholds for generating events (% daily change)
THRESHOLDS = {
    "index": 1.5,       # 1.5% move in major index
    "commodity": 3.0,    # 3% move in commodity
    "currency": 1.0,     # 1% move in currency
    "crypto": 5.0,       # 5% move in crypto
    "volatility": 10.0,  # 10% move in VIX
}


def _severity_from_pct_change(pct: float, asset_type: str) -> float:
    """Map percentage change to severity 0-100 based on asset type."""
    threshold = THRESHOLDS.get(asset_type, 2.0)
    abs_pct = abs(pct)
    if abs_pct < threshold * 0.5:
        return 10.0
    elif abs_pct < threshold:
        return 30.0
    elif abs_pct < threshold * 2:
        return 60.0
    elif abs_pct < threshold * 3:
        return 80.0
    return 95.0


def fetch_quotes() -> list[dict]:
    """Fetch current quotes for all watchlist tickers."""
    events = []
    tickers_str = " ".join(WATCHLIST.keys())

    try:
        data = yf.download(tickers_str, period="2d", interval="1d", progress=False, threads=True)
    except Exception as e:
        logger.error("yfinance download failed: %s", e)
        return []

    if data.empty:
        logger.warning("yfinance returned empty data")
        return []

    for ticker, meta in WATCHLIST.items():
        try:
            # Get closing prices for last 2 days
            if len(WATCHLIST) > 1:
                close = data["Close"][ticker]
            else:
                close = data["Close"]

            if close.empty or len(close) < 2:
                continue

            prev_close = float(close.iloc[-2])
            curr_close = float(close.iloc[-1])

            if prev_close == 0:
                continue

            pct_change = ((curr_close - prev_close) / prev_close) * 100
            direction = "up" if pct_change > 0 else "down"

            title = f"{meta['name']} ({ticker}) {direction} {abs(pct_change):.1f}% to {curr_close:,.2f}"
            severity = _severity_from_pct_change(pct_change, meta["type"])

            events.append({
                "id": str(uuid.uuid4()),
                "source": "yahoo_finance",
                "source_id": f"yf-{ticker}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "summary": (
                    f"{meta['type'].title()} | {meta['name']} | "
                    f"Close: {curr_close:,.2f} | Change: {pct_change:+.2f}% | "
                    f"Prev: {prev_close:,.2f}"
                ),
                "raw_payload": json.dumps({
                    "ticker": ticker,
                    "name": meta["name"],
                    "type": meta["type"],
                    "region": meta["region"],
                    "close": curr_close,
                    "prev_close": prev_close,
                    "pct_change": round(pct_change, 4),
                }),
                "latitude": None,
                "longitude": None,
                "country_code": None,
                "region": meta["region"],
                "category": "economic",
                "severity": round(severity, 1),
                "confidence": 0.95,  # Market data is highly reliable
                "entities_json": json.dumps([
                    {"name": meta["name"], "type": "financial_instrument", "role": "subject"}
                ]),
                "source_url": f"https://finance.yahoo.com/quote/{ticker}",
            })
        except Exception as e:
            logger.error("Error processing ticker %s: %s", ticker, e)

    logger.info("Yahoo Finance: generated %d events from %d tickers", len(events), len(WATCHLIST))
    return events


def ingest(conn) -> dict:
    """Fetch market data and insert as events."""
    events = fetch_quotes()
    inserted = 0
    skipped = 0
    errors = 0

    for event in events:
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
            logger.error("Error inserting YF event: %s", e)
            errors += 1

    conn.commit()
    stats = {
        "source": "yahoo_finance",
        "fetched": len(events),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("Yahoo Finance ingestion: %s", stats)
    return stats
