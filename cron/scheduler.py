"""
In-process auto-ingestion scheduler.

Runs alongside the FastAPI server (started from its lifespan). Fires each
source at its natural cadence without needing an external cron/systemd.

Each source runs in a `run_in_executor` so its blocking HTTP/DB work doesn't
stall the FastAPI event loop.

Enable/disable with env var CEREBRO_AUTO_INGEST=true|false (default true in
dev, so data freshens without any extra setup).

Tune cadences with CEREBRO_INGEST_SECONDS_<SOURCE> if needed, e.g.
CEREBRO_INGEST_SECONDS_OPENSKY=30 to poll flights every 30s.
"""
import asyncio
import importlib
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# (source_name, module_path, function_name, default_interval_seconds)
SCHEDULE: list[tuple[str, str, str, int]] = [
    # Fast tier — movement data that changes every minute
    ("opensky",       "ingestion.opensky",       "ingest",  60),   # live flights
    # (aisstream is a persistent WebSocket worker — started separately via
    #  `python -m ingestion.aisstream`, not periodically scheduled)
    # Medium tier — news + fires
    ("gdelt",         "ingestion.gdelt",         "ingest", 900),   # 15 min
    ("rss",           "ingestion.rss",           "ingest", 600),   # 10 min
    ("viirs",         "ingestion.viirs",         "ingest", 1800),  # 30 min
    # Slow tier — macro/financial + weekly-ish datasets
    ("yahoo_finance", "ingestion.yahoo_finance", "ingest", 3600),  # 1 hour
    ("fred",          "ingestion.fred",          "ingest", 21600), # 6 hours
    ("worldbank",     "ingestion.worldbank",     "ingest", 86400), # 24 hours
    ("acled",         "ingestion.acled",         "ingest", 21600), # 6 hours
]


def _env_seconds(source: str, default: int) -> int:
    """Read CEREBRO_INGEST_SECONDS_<SOURCE> override or fall back to default."""
    val = os.getenv(f"CEREBRO_INGEST_SECONDS_{source.upper()}")
    try:
        return max(30, int(val)) if val else default
    except ValueError:
        return default


def _run_source_blocking(source: str, module_path: str, func: str) -> dict:
    """Blocking call executed off the event loop via run_in_executor."""
    # Each source manages its own DB connection to avoid contention with the API's
    # long-lived connection (SQLite writers serialize; separate connections are safe).
    from db.connection import get_connection
    conn = get_connection()
    try:
        module = importlib.import_module(module_path)
        fn = getattr(module, func, None)
        if fn is None:
            return {"source": source, "error": f"missing {func}()"}
        return fn(conn) or {"source": source}
    except Exception as e:  # pragma: no cover — best-effort logging
        return {"source": source, "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


# One shared lock across every source coroutine — SQLite serializes writers
# at the file level anyway, and running ingesters in parallel just produces
# "database is locked" errors. Queueing them gives clean single-writer semantics.
_ingest_lock = asyncio.Lock()


async def _source_loop(name: str, module_path: str, func: str, interval: int):
    """One coroutine per source — sleeps `interval` then runs the ingest function."""
    # Small stagger so we don't hammer everything on first tick
    await asyncio.sleep((hash(name) % 30) + 5)
    loop = asyncio.get_running_loop()
    while True:
        try:
            async with _ingest_lock:
                started = datetime.now(timezone.utc)
                stats = await loop.run_in_executor(None, _run_source_blocking, name, module_path, func)
                dur = (datetime.now(timezone.utc) - started).total_seconds()
                if stats.get("error"):
                    logger.warning("[scheduler] %s failed in %.1fs: %s", name, dur, stats["error"])
                else:
                    logger.info(
                        "[scheduler] %s ok in %.1fs — fetched=%s inserted=%s",
                        name, dur, stats.get("fetched", "?"), stats.get("inserted", "?"),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover
            logger.exception("[scheduler] %s crashed: %s", name, e)
        await asyncio.sleep(interval)


def start_scheduler() -> list[asyncio.Task]:
    """Kick off every source's loop as a background task. Returns them for cancellation."""
    if os.getenv("CEREBRO_AUTO_INGEST", "true").lower() in ("0", "false", "no", "off"):
        logger.info("[scheduler] auto-ingest disabled via CEREBRO_AUTO_INGEST")
        return []

    tasks: list[asyncio.Task] = []
    for name, module_path, func, default_interval in SCHEDULE:
        interval = _env_seconds(name, default_interval)
        task = asyncio.create_task(_source_loop(name, module_path, func, interval))
        tasks.append(task)
        logger.info("[scheduler] started %s every %ds", name, interval)
    return tasks


async def stop_scheduler(tasks: list[asyncio.Task]) -> None:
    """Cancel and await all background tasks on shutdown."""
    for t in tasks:
        t.cancel()
    for t in tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
