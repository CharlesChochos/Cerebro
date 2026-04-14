-- 018: Phase 14 — Immersive & holographic features support tables.

-- Satellite orbit tracking / pass prediction
CREATE TABLE IF NOT EXISTS satellite_orbits (
    id              TEXT PRIMARY KEY,
    norad_id        INTEGER NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT DEFAULT 'unknown',           -- military / comms / earth_obs / weather / navigation / science
    country_code    TEXT,
    tle_line1       TEXT,
    tle_line2       TEXT,
    inclination     REAL,
    period_min      REAL,
    apogee_km       REAL,
    perigee_km      REAL,
    launch_date     TEXT,
    status          TEXT DEFAULT 'active',
    updated_at      TEXT DEFAULT (datetime('now')),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_satellite_norad ON satellite_orbits(norad_id);
CREATE INDEX IF NOT EXISTS idx_satellite_category ON satellite_orbits(category);
CREATE INDEX IF NOT EXISTS idx_satellite_country ON satellite_orbits(country_code);

-- Monitored locations for pulse beacons
CREATE TABLE IF NOT EXISTS monitored_locations (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    location_type   TEXT DEFAULT 'general',           -- military_base / embassy / port / border / nuclear / airfield
    country_code    TEXT,
    alert_level     TEXT DEFAULT 'normal',            -- normal / elevated / high / critical
    pulse_rate      REAL DEFAULT 2.0,                -- seconds per pulse cycle
    radius_km       REAL DEFAULT 50,
    event_count_24h INTEGER DEFAULT 0,
    last_event_at   TEXT,
    notes           TEXT,
    active          INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_monitor_location ON monitored_locations(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_monitor_type ON monitored_locations(location_type);
CREATE INDEX IF NOT EXISTS idx_monitor_alert ON monitored_locations(alert_level);

-- Country extrusion data (3D visualization metrics)
CREATE TABLE IF NOT EXISTS country_extrusions (
    id              TEXT PRIMARY KEY,
    country_code    TEXT NOT NULL,
    metric_name     TEXT NOT NULL,                    -- event_count / risk_score / gdp / population / threat_level
    metric_value    REAL NOT NULL,
    normalized      REAL,                            -- 0.0-1.0 for visualization scaling
    period          TEXT DEFAULT 'current',
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_extrusion_unique ON country_extrusions(country_code, metric_name, period);
CREATE INDEX IF NOT EXISTS idx_extrusion_metric ON country_extrusions(metric_name);
