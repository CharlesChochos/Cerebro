-- 016: Domain-specific tracking — elections, nuclear proliferation, migration/refugees,
-- cyber incidents, custom event tags, EXIF metadata, reverse geocoding cache.

CREATE TABLE IF NOT EXISTS election_monitors (
    id              TEXT PRIMARY KEY,
    country_code    TEXT NOT NULL,
    election_type   TEXT NOT NULL,              -- presidential / parliamentary / referendum / local
    election_date   TEXT,
    status          TEXT DEFAULT 'upcoming',     -- upcoming / active / completed / disputed
    candidates      TEXT,                       -- JSON array
    risk_level      TEXT DEFAULT 'normal',      -- normal / elevated / high / critical
    risk_factors    TEXT,                       -- JSON array
    irregularities  TEXT,                       -- JSON array of reported issues
    turnout_pct     REAL,
    result_summary  TEXT,
    region          TEXT,
    analyst         TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_election_country ON election_monitors(country_code);
CREATE INDEX IF NOT EXISTS idx_election_status ON election_monitors(status);
CREATE INDEX IF NOT EXISTS idx_election_date ON election_monitors(election_date);

CREATE TABLE IF NOT EXISTS nuclear_events (
    id              TEXT PRIMARY KEY,
    country_code    TEXT NOT NULL,
    event_type      TEXT NOT NULL,              -- test / enrichment / facility / treaty / missile / rhetoric
    severity        REAL DEFAULT 50,
    facility_name   TEXT,
    latitude        REAL,
    longitude       REAL,
    description     TEXT,
    evidence        TEXT,                       -- JSON array
    source_type     TEXT,                       -- satellite / seismic / humint / osint / diplomatic
    status          TEXT DEFAULT 'unconfirmed', -- unconfirmed / confirmed / denied / retracted
    detected_at     TEXT DEFAULT (datetime('now')),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_nuclear_country ON nuclear_events(country_code);
CREATE INDEX IF NOT EXISTS idx_nuclear_type ON nuclear_events(event_type);
CREATE INDEX IF NOT EXISTS idx_nuclear_severity ON nuclear_events(severity);

CREATE TABLE IF NOT EXISTS migration_flows (
    id              TEXT PRIMARY KEY,
    origin_country  TEXT NOT NULL,
    dest_country    TEXT,
    transit_countries TEXT,                     -- JSON array
    flow_type       TEXT DEFAULT 'refugee',     -- refugee / idp / economic / climate / conflict
    estimated_count INTEGER,
    severity        REAL DEFAULT 50,
    route_description TEXT,
    push_factors    TEXT,                       -- JSON array
    pull_factors    TEXT,                       -- JSON array
    status          TEXT DEFAULT 'active',      -- active / seasonal / resolved / emerging
    reported_at     TEXT DEFAULT (datetime('now')),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_migration_origin ON migration_flows(origin_country);
CREATE INDEX IF NOT EXISTS idx_migration_dest ON migration_flows(dest_country);
CREATE INDEX IF NOT EXISTS idx_migration_type ON migration_flows(flow_type);

CREATE TABLE IF NOT EXISTS cyber_incidents (
    id              TEXT PRIMARY KEY,
    incident_type   TEXT NOT NULL,              -- ransomware / apt / ddos / data_breach / supply_chain / zero_day
    severity        REAL DEFAULT 50,
    target_sector   TEXT,                       -- government / military / finance / energy / healthcare / tech
    target_country  TEXT,
    target_org      TEXT,
    attributed_to   TEXT,                       -- threat actor attribution
    attribution_confidence TEXT DEFAULT 'low',  -- low / moderate / high
    attack_vector   TEXT,
    iocs            TEXT,                       -- JSON: indicators of compromise
    impact          TEXT,
    status          TEXT DEFAULT 'active',      -- active / contained / resolved / investigating
    detected_at     TEXT DEFAULT (datetime('now')),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cyber_type ON cyber_incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_cyber_severity ON cyber_incidents(severity);
CREATE INDEX IF NOT EXISTS idx_cyber_target ON cyber_incidents(target_country);
CREATE INDEX IF NOT EXISTS idx_cyber_actor ON cyber_incidents(attributed_to);

CREATE TABLE IF NOT EXISTS event_tags (
    id              TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL,
    tag_name        TEXT NOT NULL,
    tag_category    TEXT DEFAULT 'custom',      -- custom / auto / priority / watchlist
    color           TEXT,
    created_by      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tag_event ON event_tags(event_id);
CREATE INDEX IF NOT EXISTS idx_tag_name ON event_tags(tag_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tag_unique ON event_tags(event_id, tag_name);

CREATE TABLE IF NOT EXISTS exif_metadata (
    id              TEXT PRIMARY KEY,
    source_url      TEXT,
    filename        TEXT,
    latitude        REAL,
    longitude       REAL,
    altitude        REAL,
    capture_date    TEXT,
    camera_make     TEXT,
    camera_model    TEXT,
    software        TEXT,
    image_width     INTEGER,
    image_height    INTEGER,
    gps_accuracy    REAL,
    raw_exif        TEXT,                       -- JSON: full EXIF dump
    linked_event_id TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_exif_event ON exif_metadata(linked_event_id);
CREATE INDEX IF NOT EXISTS idx_exif_location ON exif_metadata(latitude, longitude);

CREATE TABLE IF NOT EXISTS geocode_cache (
    id              TEXT PRIMARY KEY,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    display_name    TEXT,
    country_code    TEXT,
    country_name    TEXT,
    state           TEXT,
    city            TEXT,
    district        TEXT,
    postal_code     TEXT,
    resolution      TEXT DEFAULT 'approximate', -- exact / approximate / country_level
    provider        TEXT DEFAULT 'internal',
    raw_response    TEXT,                       -- JSON
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_geocode_coords ON geocode_cache(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_geocode_country ON geocode_cache(country_code);
