"""
Master ingestion runner — runs all source connectors.

Run manually:   python -m cron.ingest_all
Selective:      python -m cron.ingest_all --sources gdelt,rss,yahoo_finance
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import get_connection
from db.migrate import run_migrations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Registry of all available sources
SOURCE_REGISTRY = {
    "gdelt": ("ingestion.gdelt", "ingest"),
    "rss": ("ingestion.rss", "ingest"),
    "yahoo_finance": ("ingestion.yahoo_finance", "ingest"),
    "worldbank": ("ingestion.worldbank", "ingest"),
    "fred": ("ingestion.fred", "ingest"),
    "acled": ("ingestion.acled", "ingest"),
}


def run_source(conn, source_name: str) -> dict | None:
    """Import and run a single source connector."""
    if source_name not in SOURCE_REGISTRY:
        logger.error("Unknown source: %s", source_name)
        return None

    module_path, func_name = SOURCE_REGISTRY[source_name]
    try:
        import importlib
        module = importlib.import_module(module_path)
        ingest_func = getattr(module, func_name)
        stats = ingest_func(conn)
        return stats
    except Exception as e:
        logger.error("Source %s failed: %s", source_name, e, exc_info=True)
        return {"source": source_name, "error": str(e)}


def run(sources: list[str] | None = None):
    """Execute ingestion for specified sources (or all)."""
    conn = get_connection()
    run_migrations(conn)

    sources_to_run = sources or list(SOURCE_REGISTRY.keys())
    all_stats = []

    conn.execute(
        "INSERT INTO system_log (component, level, message, metadata) VALUES (?, ?, ?, ?)",
        ("ingestion", "info", "Ingestion cycle started", json.dumps({"sources": sources_to_run})),
    )
    conn.commit()

    for source_name in sources_to_run:
        logger.info("=== Running %s ===", source_name)
        stats = run_source(conn, source_name)
        if stats:
            all_stats.append(stats)

            # Update source reliability
            inserted = stats.get("inserted", 0)
            if inserted > 0 or stats.get("fetched", 0) > 0:
                conn.execute(
                    """INSERT INTO source_reliability (source, total_events, last_ingestion, status)
                       VALUES (?, ?, ?, 'active')
                       ON CONFLICT(source) DO UPDATE SET
                           total_events = total_events + excluded.total_events,
                           last_ingestion = excluded.last_ingestion,
                           status = 'active'""",
                    (source_name, inserted, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()

    # Log completion
    total_inserted = sum(s.get("inserted", 0) for s in all_stats)
    total_fetched = sum(s.get("fetched", 0) for s in all_stats)

    conn.execute(
        "INSERT INTO system_log (component, level, message, metadata) VALUES (?, ?, ?, ?)",
        (
            "ingestion", "info",
            f"Ingestion cycle completed: {total_inserted} inserted from {total_fetched} fetched across {len(sources_to_run)} sources",
            json.dumps(all_stats),
        ),
    )
    conn.commit()
    conn.close()

    logger.info("=== SUMMARY ===")
    for s in all_stats:
        logger.info("  %s: fetched=%s inserted=%s skipped=%s errors=%s",
                     s.get("source", "?"), s.get("fetched", "?"),
                     s.get("inserted", "?"), s.get("skipped", "?"),
                     s.get("errors", "?"))
    logger.info("Total: %d inserted from %d fetched", total_inserted, total_fetched)

    return all_stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cerebro ingestion runner")
    parser.add_argument(
        "--sources", type=str, default=None,
        help="Comma-separated list of sources to run (default: all)"
    )
    args = parser.parse_args()
    sources = args.sources.split(",") if args.sources else None
    run(sources)
