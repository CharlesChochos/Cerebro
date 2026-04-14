-- Migration 009: Geospatial Advanced Features
-- Phase 10: Geofencing, weapons systems, measurement profiles

-- =============================================================
-- GEOFENCES — user-defined monitoring polygons
-- =============================================================
CREATE TABLE IF NOT EXISTS geofences (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    polygon_json TEXT NOT NULL,              -- GeoJSON Polygon geometry
    bbox_west REAL,                          -- Pre-computed bounding box for fast filtering
    bbox_south REAL,
    bbox_east REAL,
    bbox_north REAL,
    category TEXT,                            -- military, economic, environmental, custom
    alert_on_entry INTEGER DEFAULT 1,        -- Fire alert when event enters fence
    alert_severity_min REAL DEFAULT 0,       -- Only alert if event severity >= threshold
    active INTEGER DEFAULT 1,
    event_count INTEGER DEFAULT 0,           -- Cached count of events inside
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_geofences_active ON geofences(active);
CREATE INDEX IF NOT EXISTS idx_geofences_bbox ON geofences(bbox_west, bbox_south, bbox_east, bbox_north);

-- =============================================================
-- GEOFENCE_EVENTS — events that triggered a geofence
-- =============================================================
CREATE TABLE IF NOT EXISTS geofence_events (
    id TEXT PRIMARY KEY,
    geofence_id TEXT NOT NULL REFERENCES geofences(id),
    event_id TEXT NOT NULL REFERENCES events(id),
    entered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(geofence_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_geofence_events_fence ON geofence_events(geofence_id);

-- =============================================================
-- WEAPONS_SYSTEMS — known weapons with range data for range rings
-- =============================================================
CREATE TABLE IF NOT EXISTS weapons_systems (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    system_type TEXT NOT NULL,                -- sam, cruise_missile, ballistic_missile, artillery, radar
    country_code TEXT,
    min_range_km REAL DEFAULT 0,
    max_range_km REAL NOT NULL,
    altitude_max_km REAL,                    -- Maximum engagement altitude
    speed_mach REAL,                         -- Speed in Mach
    warhead_type TEXT,                       -- conventional, nuclear, chemical
    description TEXT,
    metadata TEXT                             -- JSON blob for extra specs
);

-- Seed common weapons systems for range ring visualization
INSERT OR IGNORE INTO weapons_systems (id, name, system_type, country_code, min_range_km, max_range_km, altitude_max_km, speed_mach, description)
VALUES
    ('ws-s400', 'S-400 Triumf', 'sam', 'RU', 2, 400, 30, 14.0, 'Russian long-range SAM system'),
    ('ws-s300', 'S-300PMU-2', 'sam', 'RU', 3, 200, 27, 8.0, 'Russian medium/long-range SAM'),
    ('ws-patriot', 'MIM-104 Patriot PAC-3', 'sam', 'US', 3, 160, 24, 5.0, 'US medium-range SAM system'),
    ('ws-thaad', 'THAAD', 'sam', 'US', 50, 200, 150, 8.0, 'US terminal high-altitude defense'),
    ('ws-iron-dome', 'Iron Dome', 'sam', 'IL', 4, 70, 10, 2.5, 'Israeli short-range defense'),
    ('ws-kalibr', 'Kalibr 3M-54', 'cruise_missile', 'RU', 50, 2500, 0.015, 0.8, 'Russian sea-launched cruise missile'),
    ('ws-tomahawk', 'BGM-109 Tomahawk', 'cruise_missile', 'US', 100, 2500, 0.03, 0.75, 'US sea/land-launched cruise missile'),
    ('ws-iskander', 'Iskander-M 9K720', 'ballistic_missile', 'RU', 50, 500, 50, 6.0, 'Russian short-range ballistic missile'),
    ('ws-df21d', 'DF-21D', 'ballistic_missile', 'CN', 500, 1500, 100, 10.0, 'Chinese anti-ship ballistic missile'),
    ('ws-himars', 'M142 HIMARS', 'artillery', 'US', 15, 300, 0, 3.0, 'US precision rocket artillery (GMLRS/ATACMS)');

-- =============================================================
-- WEAPONS_DEPLOYMENTS — known positions of weapons systems
-- =============================================================
CREATE TABLE IF NOT EXISTS weapons_deployments (
    id TEXT PRIMARY KEY,
    system_id TEXT NOT NULL REFERENCES weapons_systems(id),
    name TEXT,                                -- Deployment site name
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    country_code TEXT,
    status TEXT DEFAULT 'active',             -- active, suspected, destroyed, relocated
    confidence REAL DEFAULT 0.5,
    source TEXT,                              -- Where this intel came from
    first_detected TEXT,
    last_confirmed TEXT,
    metadata TEXT                             -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_deployments_system ON weapons_deployments(system_id);
CREATE INDEX IF NOT EXISTS idx_deployments_status ON weapons_deployments(status);

-- =============================================================
-- MEASUREMENT_PROFILES — saved measurement paths/areas
-- =============================================================
CREATE TABLE IF NOT EXISTS measurement_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    profile_type TEXT NOT NULL,               -- distance, area, elevation
    points_json TEXT NOT NULL,                -- JSON array of [lat, lng] or [lat, lng, elevation]
    total_distance_km REAL,
    total_area_km2 REAL,
    metadata TEXT,                             -- JSON blob for elevation data etc.
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
