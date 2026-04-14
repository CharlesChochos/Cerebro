-- 017: Phase 13 — Animations, video features, street-level imagery support tables.

-- Public webcam feeds (Windy.com, traffic cams, weather cams)
CREATE TABLE IF NOT EXISTS webcam_feeds (
    id              TEXT PRIMARY KEY,
    provider        TEXT NOT NULL DEFAULT 'windy',  -- windy / dot / custom
    title           TEXT,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    country_code    TEXT,
    category        TEXT DEFAULT 'weather',          -- weather / traffic / landscape / port / border
    stream_url      TEXT,
    thumbnail_url   TEXT,
    status          TEXT DEFAULT 'active',            -- active / offline / maintenance
    last_checked    TEXT DEFAULT (datetime('now')),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_webcam_location ON webcam_feeds(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_webcam_category ON webcam_feeds(category);
CREATE INDEX IF NOT EXISTS idx_webcam_country ON webcam_feeds(country_code);

-- Trade flow data (for arc layer visualization)
CREATE TABLE IF NOT EXISTS trade_flows (
    id              TEXT PRIMARY KEY,
    origin_country  TEXT NOT NULL,
    dest_country    TEXT NOT NULL,
    commodity       TEXT,
    volume_usd      REAL,
    volume_tons     REAL,
    flow_type       TEXT DEFAULT 'trade',             -- trade / arms / aid / energy / migration
    year            INTEGER,
    origin_lat      REAL,
    origin_lng      REAL,
    dest_lat        REAL,
    dest_lng        REAL,
    risk_level      TEXT DEFAULT 'normal',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trade_origin ON trade_flows(origin_country);
CREATE INDEX IF NOT EXISTS idx_trade_dest ON trade_flows(dest_country);
CREATE INDEX IF NOT EXISTS idx_trade_type ON trade_flows(flow_type);

-- Conflict frontline geometries
CREATE TABLE IF NOT EXISTS conflict_frontlines (
    id              TEXT PRIMARY KEY,
    conflict_name   TEXT NOT NULL,
    country_code    TEXT,
    date            TEXT NOT NULL,
    geometry_json   TEXT NOT NULL,                    -- GeoJSON geometry
    side_a          TEXT,
    side_b          TEXT,
    status          TEXT DEFAULT 'active',            -- active / frozen / ceasefire
    source          TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_frontline_conflict ON conflict_frontlines(conflict_name);
CREATE INDEX IF NOT EXISTS idx_frontline_date ON conflict_frontlines(date);
CREATE INDEX IF NOT EXISTS idx_frontline_country ON conflict_frontlines(country_code);

-- Map annotations / drawings
CREATE TABLE IF NOT EXISTS map_annotations (
    id              TEXT PRIMARY KEY,
    annotation_type TEXT NOT NULL DEFAULT 'marker',   -- marker / line / polygon / circle / freehand / text
    geometry_json   TEXT NOT NULL,                    -- GeoJSON
    properties_json TEXT,                             -- styling, color, labels
    title           TEXT,
    description     TEXT,
    created_by      TEXT,
    layer_name      TEXT DEFAULT 'default',
    visible         INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_annotation_layer ON map_annotations(layer_name);
CREATE INDEX IF NOT EXISTS idx_annotation_type ON map_annotations(annotation_type);

-- Mapillary street-level imagery cache
CREATE TABLE IF NOT EXISTS street_imagery (
    id              TEXT PRIMARY KEY,
    provider        TEXT DEFAULT 'mapillary',
    image_id        TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    compass_angle   REAL,
    captured_at     TEXT,
    sequence_id     TEXT,
    thumbnail_url   TEXT,
    full_url        TEXT,
    linked_event_id TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_street_location ON street_imagery(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_street_event ON street_imagery(linked_event_id);

-- Animation export jobs
CREATE TABLE IF NOT EXISTS animation_exports (
    id              TEXT PRIMARY KEY,
    export_type     TEXT NOT NULL DEFAULT 'gif',      -- gif / mp4 / webm
    status          TEXT DEFAULT 'pending',           -- pending / rendering / completed / failed
    parameters_json TEXT,                             -- center, zoom, duration, fps, etc.
    frame_count     INTEGER,
    duration_secs   REAL,
    file_size       INTEGER,
    output_path     TEXT,
    error_message   TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT
);
