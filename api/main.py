"""
Cerebro API Server — FastAPI application.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import FRONTEND_URL
from db.connection import get_connection
from db.migrate import run_migrations

# Module-level connection, initialized on startup
_db_conn = None


def get_db():
    """Return the shared database connection."""
    return _db_conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations on startup, close DB on shutdown."""
    global _db_conn
    _db_conn = get_connection()
    applied = run_migrations(_db_conn)
    if applied:
        _db_conn.execute(
            "INSERT INTO system_log (component, level, message, metadata) VALUES (?, ?, ?, ?)",
            ("api", "info", f"Applied {len(applied)} migration(s)", str(applied)),
        )
        _db_conn.commit()

    _db_conn.execute(
        "INSERT INTO system_log (component, level, message) VALUES (?, ?, ?)",
        ("api", "info", "Cerebro API server started"),
    )
    _db_conn.commit()

    yield

    if _db_conn:
        _db_conn.close()


app = FastAPI(
    title="Cerebro",
    description="Global Intelligence Monitoring System API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
from api.routes_events import router as events_router
from api.routes_entities import router as entities_router
from api.routes_sources import router as sources_router
from api.routes_geo import router as geo_router
from api.routes_vessels import router as vessels_router
from api.routes_intel import router as intel_router
from api.routes_query import router as query_router
from api.routes_specint import router as specint_router
from api.routes_risk import router as risk_router
from api.routes_entity_intel import router as entity_intel_router
from api.routes_geospatial import router as geospatial_router
from api.routes_output import router as output_router
from api.routes_ai_features import router as ai_features_router
from api.routes_advanced_analytics import router as advanced_analytics_router
from api.routes_geo_layers import router as geo_layers_router
from api.routes_intel_tradecraft import router as intel_tradecraft_router
from api.routes_system_intel import router as system_intel_router
from api.routes_domain_tracking import router as domain_tracking_router
from api.routes_phase13 import router as phase13_router
from api.routes_phase14 import router as phase14_router
from api.routes_phase15 import router as phase15_router
from api.routes_phase16 import router as phase16_router
# Register specific-path routers BEFORE parametric ones
# so /api/events/geo beats /api/events/{id} and /api/vessels/dark beats /api/vessels/{mmsi}
# Entity intel routes with /entities/{id}/dossier etc. go BEFORE the base entities router
# Geospatial routes with /export/*.kml go before any parametric routes
app.include_router(geo_router)
app.include_router(vessels_router)
app.include_router(intel_router)
app.include_router(query_router)
app.include_router(specint_router)
app.include_router(risk_router)
app.include_router(entity_intel_router)
app.include_router(geospatial_router)
app.include_router(output_router)
app.include_router(ai_features_router)
app.include_router(advanced_analytics_router)
app.include_router(geo_layers_router)
app.include_router(intel_tradecraft_router)
app.include_router(system_intel_router)
app.include_router(domain_tracking_router)
app.include_router(phase13_router)
app.include_router(phase14_router)
app.include_router(phase15_router)
app.include_router(phase16_router)
app.include_router(events_router)
app.include_router(entities_router)
app.include_router(sources_router)


@app.get("/health")
def health_check():
    """Health check endpoint — verifies DB connection and returns system status."""
    conn = get_db()
    try:
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        alert_count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

        # Verify FTS5
        conn.execute("SELECT * FROM events_fts LIMIT 0")
        fts_ok = True
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

    return {
        "status": "healthy",
        "database": "connected",
        "fts5": "ok" if fts_ok else "error",
        "spatialite": "loaded",
        "counts": {
            "events": event_count,
            "entities": entity_count,
            "alerts": alert_count,
        },
    }
