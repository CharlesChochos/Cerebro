-- Migration 020: Storm tracking, conflict progression, disease spread animation
-- Extends existing disease_outbreaks (from 006) with spread animation fields

-- Add spread animation columns to existing disease_outbreaks table
ALTER TABLE disease_outbreaks ADD COLUMN r_naught REAL DEFAULT 2.5;
ALTER TABLE disease_outbreaks ADD COLUMN mortality_rate REAL DEFAULT 0.01;
ALTER TABLE disease_outbreaks ADD COLUMN spread_radius_km REAL DEFAULT 10;

-- Spread animation point data (time-stepped circles)
CREATE TABLE IF NOT EXISTS disease_spread_points (
    id TEXT PRIMARY KEY,
    outbreak_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    cases INTEGER DEFAULT 0,
    day_offset INTEGER DEFAULT 0,
    radius_km REAL DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS storm_tracks (
    id TEXT PRIMARY KEY,
    storm_name TEXT NOT NULL,
    storm_type TEXT DEFAULT 'hurricane',
    category INTEGER DEFAULT 1,
    max_wind_kts INTEGER,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS storm_track_points (
    id TEXT PRIMARY KEY,
    storm_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timestamp TEXT NOT NULL,
    wind_kts INTEGER,
    pressure_mb INTEGER,
    is_forecast INTEGER DEFAULT 0,
    uncertainty_radius_km REAL DEFAULT 50,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conflict_progressions (
    id TEXT PRIMARY KEY,
    conflict_name TEXT NOT NULL,
    region TEXT,
    start_date TEXT NOT NULL,
    status TEXT DEFAULT 'ongoing',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conflict_progression_steps (
    id TEXT PRIMARY KEY,
    progression_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    narration TEXT,
    center_lat REAL NOT NULL,
    center_lng REAL NOT NULL,
    zoom REAL DEFAULT 6,
    bearing REAL DEFAULT 0,
    pitch REAL DEFAULT 45,
    event_date TEXT,
    markers_json TEXT,
    lines_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_disease_spread_outbreak ON disease_spread_points(outbreak_id);
CREATE INDEX IF NOT EXISTS idx_storm_track_points_storm ON storm_track_points(storm_id);
CREATE INDEX IF NOT EXISTS idx_conflict_steps_progression ON conflict_progression_steps(progression_id);
