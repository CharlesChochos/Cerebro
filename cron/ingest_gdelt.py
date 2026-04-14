"""
GDELT ingestion cron job.

Run manually:   python -m cron.ingest_gdelt
Run on schedule: use system crontab or APScheduler
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import get_connection
from db.migrate import run_migrations
from ingestion.gdelt import ingest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run():
    """Execute one GDELT ingestion cycle."""
    conn = get_connection()
    run_migrations(conn)

    # Log start
    conn.execute(
        "INSERT INTO system_log (component, level, message) VALUES (?, ?, ?)",
        ("ingestion", "info", "GDELT ingestion cycle started"),
    )
    conn.commit()

    try:
        stats = ingest(conn)

        # Log completion
        conn.execute(
            "INSERT INTO system_log (component, level, message, metadata) VALUES (?, ?, ?, ?)",
            ("ingestion", "info", "GDELT ingestion cycle completed", json.dumps(stats)),
        )

        # Update source reliability
        conn.execute(
            """INSERT INTO source_reliability (source, total_events, last_ingestion, status)
               VALUES ('gdelt', ?, ?, 'active')
               ON CONFLICT(source) DO UPDATE SET
                   total_events = total_events + excluded.total_events,
                   last_ingestion = excluded.last_ingestion,
                   status = 'active'""",
            (stats["inserted"], datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

        logger.info(
            "GDELT: fetched=%d inserted=%d skipped=%d errors=%d",
            stats["fetched"], stats["inserted"], stats["skipped"], stats["errors"],
        )
        return stats

    except Exception as e:
        logger.error("GDELT ingestion failed: %s", e)
        conn.execute(
            "INSERT INTO system_log (component, level, message, metadata) VALUES (?, ?, ?, ?)",
            ("ingestion", "error", f"GDELT ingestion failed: {e}", None),
        )
        conn.commit()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
