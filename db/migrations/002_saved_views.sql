-- Migration 002: Saved map views for bookmarking map state
CREATE TABLE IF NOT EXISTS saved_views (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    center_lat REAL NOT NULL,
    center_lng REAL NOT NULL,
    zoom REAL NOT NULL DEFAULT 2.0,
    bearing REAL NOT NULL DEFAULT 0.0,
    pitch REAL NOT NULL DEFAULT 0.0,
    layers TEXT,              -- JSON array of enabled layer names
    filters TEXT,             -- JSON blob of active filters (category, source, severity, etc.)
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_saved_views_name ON saved_views(name);
