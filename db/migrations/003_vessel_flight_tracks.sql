-- Migration 003: Vessel and flight tracking tables for SIGINT

-- =============================================================
-- VESSELS — current state of tracked vessels
-- =============================================================
CREATE TABLE IF NOT EXISTS vessels (
    mmsi TEXT PRIMARY KEY,              -- Maritime Mobile Service Identity (9 digits)
    name TEXT,
    imo TEXT,                            -- IMO number
    callsign TEXT,
    vessel_type TEXT,                    -- cargo, tanker, military, fishing, passenger, other
    flag TEXT,                           -- Country flag code
    length REAL,
    width REAL,
    draught REAL,
    destination TEXT,
    latitude REAL,
    longitude REAL,
    speed REAL,                          -- Speed over ground (knots)
    course REAL,                         -- Course over ground (degrees)
    heading REAL,                        -- True heading (degrees)
    nav_status TEXT,                     -- navigational status
    last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    position_count INTEGER DEFAULT 1,
    dark_since TEXT,                     -- timestamp when vessel went dark (NULL = currently transmitting)
    metadata TEXT                        -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_vessels_type ON vessels(vessel_type);
CREATE INDEX IF NOT EXISTS idx_vessels_flag ON vessels(flag);
CREATE INDEX IF NOT EXISTS idx_vessels_dark ON vessels(dark_since);

-- =============================================================
-- VESSEL_TRACKS — AIS position history for trail visualization
-- =============================================================
CREATE TABLE IF NOT EXISTS vessel_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mmsi TEXT NOT NULL REFERENCES vessels(mmsi),
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    speed REAL,
    course REAL,
    heading REAL,
    timestamp TEXT NOT NULL,
    nav_status TEXT
);

CREATE INDEX IF NOT EXISTS idx_vessel_tracks_mmsi ON vessel_tracks(mmsi);
CREATE INDEX IF NOT EXISTS idx_vessel_tracks_time ON vessel_tracks(timestamp);

-- =============================================================
-- FLIGHTS — current state of tracked aircraft
-- =============================================================
CREATE TABLE IF NOT EXISTS flights (
    icao24 TEXT PRIMARY KEY,             -- ICAO 24-bit transponder address
    callsign TEXT,
    origin_country TEXT,
    flight_type TEXT,                    -- civilian, military, cargo, unknown
    latitude REAL,
    longitude REAL,
    altitude REAL,                       -- barometric altitude (meters)
    velocity REAL,                       -- m/s
    heading REAL,                        -- degrees
    vertical_rate REAL,                  -- m/s
    on_ground INTEGER DEFAULT 0,
    last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    position_count INTEGER DEFAULT 1,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_flights_type ON flights(flight_type);
CREATE INDEX IF NOT EXISTS idx_flights_country ON flights(origin_country);

-- =============================================================
-- AIS_DARK_EVENTS — flagged AIS gap anomalies
-- =============================================================
CREATE TABLE IF NOT EXISTS ais_dark_events (
    id TEXT PRIMARY KEY,
    mmsi TEXT NOT NULL REFERENCES vessels(mmsi),
    vessel_name TEXT,
    last_known_lat REAL,
    last_known_lng REAL,
    last_known_time TEXT NOT NULL,
    dark_duration_hours REAL,
    region TEXT,
    severity REAL DEFAULT 50,            -- higher if near conflict zone / sanctioned area
    resolved INTEGER DEFAULT 0,          -- 1 if vessel reappeared
    resolved_at TEXT,
    resolved_lat REAL,
    resolved_lng REAL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_ais_dark_mmsi ON ais_dark_events(mmsi);
CREATE INDEX IF NOT EXISTS idx_ais_dark_resolved ON ais_dark_events(resolved);
