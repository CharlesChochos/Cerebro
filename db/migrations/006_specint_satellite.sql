-- Migration 006: SPECINT sources + satellite imagery cache

-- =============================================================
-- SATELLITE_CACHE — cached satellite imagery metadata & tiles
-- =============================================================
CREATE TABLE IF NOT EXISTS satellite_cache (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,                  -- 'sentinel2', 'viirs', 'viirs_fires'
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    bbox_json TEXT,                         -- JSON bounding box [west, south, east, north]
    capture_date TEXT NOT NULL,             -- ISO 8601 date of satellite pass
    cloud_cover REAL,                      -- 0-100 percent
    image_url TEXT,                         -- URL or local path to cached image
    thumbnail_url TEXT,                     -- smaller preview
    resolution_m REAL,                     -- ground resolution in meters
    annotations TEXT,                       -- JSON: Claude Vision annotations
    annotation_model TEXT,                 -- model used for annotation
    metadata TEXT,                          -- JSON blob (band info, scene ID, etc.)
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_satellite_source ON satellite_cache(source);
CREATE INDEX IF NOT EXISTS idx_satellite_date ON satellite_cache(capture_date);
CREATE INDEX IF NOT EXISTS idx_satellite_coords ON satellite_cache(lat, lng);

-- =============================================================
-- NIGHTLIGHT_READINGS — VIIRS nighttime light intensity
-- =============================================================
CREATE TABLE IF NOT EXISTS nightlight_readings (
    id TEXT PRIMARY KEY,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    country_code TEXT,
    region TEXT,
    radiance REAL NOT NULL,                -- nanowatts/cm²/sr
    baseline_radiance REAL,                -- historical average for this location
    change_pct REAL,                       -- percent change from baseline
    capture_date TEXT NOT NULL,
    metadata TEXT,                          -- JSON blob
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_nightlight_date ON nightlight_readings(capture_date);
CREATE INDEX IF NOT EXISTS idx_nightlight_coords ON nightlight_readings(lat, lng);
CREATE INDEX IF NOT EXISTS idx_nightlight_country ON nightlight_readings(country_code);

-- =============================================================
-- FIRE_DETECTIONS — VIIRS active fire hotspots
-- =============================================================
CREATE TABLE IF NOT EXISTS fire_detections (
    id TEXT PRIMARY KEY,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    brightness REAL,                       -- Kelvin (VIIRS I-band)
    bright_ti4 REAL,                       -- VIIRS TI4 channel brightness
    bright_ti5 REAL,                       -- VIIRS TI5 channel brightness
    frp REAL,                              -- fire radiative power (MW)
    confidence TEXT,                        -- 'low', 'nominal', 'high'
    country_code TEXT,
    daynight TEXT,                          -- 'D' or 'N'
    capture_date TEXT NOT NULL,
    satellite TEXT DEFAULT 'NOAA-20',
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fire_date ON fire_detections(capture_date);
CREATE INDEX IF NOT EXISTS idx_fire_coords ON fire_detections(lat, lng);
CREATE INDEX IF NOT EXISTS idx_fire_confidence ON fire_detections(confidence);

-- =============================================================
-- DISEASE_OUTBREAKS — WHO/ProMED disease tracking
-- =============================================================
CREATE TABLE IF NOT EXISTS disease_outbreaks (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,                  -- 'who', 'promed'
    disease TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    country_code TEXT,
    region TEXT,
    lat REAL,
    lng REAL,
    case_count INTEGER,
    death_count INTEGER,
    status TEXT,                            -- 'active', 'resolved', 'monitoring'
    severity REAL DEFAULT 50,
    source_url TEXT,
    published_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_outbreak_disease ON disease_outbreaks(disease);
CREATE INDEX IF NOT EXISTS idx_outbreak_country ON disease_outbreaks(country_code);
CREATE INDEX IF NOT EXISTS idx_outbreak_date ON disease_outbreaks(published_at);

-- =============================================================
-- WEATHER_EVENTS — NOAA severe weather alerts
-- =============================================================
CREATE TABLE IF NOT EXISTS weather_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,              -- hurricane, tornado, flood, wildfire, etc.
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT,                          -- minor, moderate, severe, extreme
    urgency TEXT,                           -- immediate, expected, future
    lat REAL,
    lng REAL,
    area_desc TEXT,                         -- affected area description
    polygon_json TEXT,                      -- GeoJSON polygon of affected area
    country_code TEXT DEFAULT 'US',
    effective TEXT,                         -- when alert becomes effective
    expires TEXT,                           -- when alert expires
    source_url TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_weather_type ON weather_events(event_type);
CREATE INDEX IF NOT EXISTS idx_weather_severity ON weather_events(severity);
