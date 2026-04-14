-- Cerebro Core Schema
-- Migration 001: Events, Entities, Alerts, and supporting tables

-- =============================================================
-- EVENTS — the central table for all ingested intelligence data
-- =============================================================
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,               -- e.g. 'gdelt', 'acled', 'rss'
    source_id TEXT,                      -- original ID from the source
    timestamp TEXT NOT NULL,             -- ISO 8601 UTC
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    category TEXT,                       -- military, economic, health, political, environmental
    severity REAL DEFAULT 0,            -- 0-100
    confidence REAL DEFAULT 0,          -- 0-1.0
    title TEXT NOT NULL,
    summary TEXT,
    raw_payload TEXT,                    -- JSON blob from source
    latitude REAL,
    longitude REAL,
    country_code TEXT,                   -- ISO 3166-1 alpha-2
    region TEXT,
    entities_json TEXT,                  -- JSON array of extracted entities
    source_url TEXT,
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_country ON events(country_code);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);

-- Full-text search on events
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    title,
    summary,
    content='events',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync with events table
CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, summary)
    VALUES ('delete', old.rowid, old.title, old.summary);
    INSERT INTO events_fts(rowid, title, summary)
    VALUES (new.rowid, new.title, new.summary);
END;


-- =============================================================
-- ENTITIES — knowledge graph nodes
-- =============================================================
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,           -- person, organization, vessel, location, weapon_system
    aliases TEXT,                         -- JSON array of alternate names
    metadata TEXT,                        -- JSON blob of extra attributes
    first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    event_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);


-- =============================================================
-- ENTITY_RELATIONS — knowledge graph edges
-- =============================================================
CREATE TABLE IF NOT EXISTS entity_relations (
    id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL REFERENCES entities(id),
    target_entity_id TEXT NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL,          -- e.g. 'employs', 'located_in', 'allied_with'
    confidence REAL DEFAULT 0.5,
    first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source_event_id TEXT REFERENCES events(id)
);

CREATE INDEX IF NOT EXISTS idx_entity_relations_source ON entity_relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_relations_target ON entity_relations(target_entity_id);


-- =============================================================
-- ALERTS — generated alerts with decay tracking
-- =============================================================
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    event_id TEXT REFERENCES events(id),
    alert_type TEXT NOT NULL,             -- threshold, anomaly, pattern, fusion
    severity REAL NOT NULL,               -- 0-100
    confidence REAL NOT NULL,             -- 0-1.0
    title TEXT NOT NULL,
    description TEXT,
    region TEXT,
    country_code TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at TEXT,
    acknowledged INTEGER DEFAULT 0,
    corroboration_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);


-- =============================================================
-- SOURCE_RELIABILITY — per-source accuracy tracking
-- =============================================================
CREATE TABLE IF NOT EXISTS source_reliability (
    source TEXT PRIMARY KEY,
    total_events INTEGER DEFAULT 0,
    confirmed_events INTEGER DEFAULT 0,
    accuracy REAL DEFAULT 0.5,            -- confirmed/total
    last_ingestion TEXT,
    avg_latency_seconds REAL,
    status TEXT DEFAULT 'active'          -- active, degraded, offline
);


-- =============================================================
-- SYSTEM_LOG — ambient narration feed
-- =============================================================
CREATE TABLE IF NOT EXISTS system_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    component TEXT NOT NULL,              -- ingestion, processing, intelligence, api
    level TEXT NOT NULL DEFAULT 'info',   -- debug, info, warning, error
    message TEXT NOT NULL,
    metadata TEXT                         -- JSON blob of extra context
);

CREATE INDEX IF NOT EXISTS idx_system_log_timestamp ON system_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_system_log_component ON system_log(component);


-- =============================================================
-- AUDIT_LOG — data lineage and provenance
-- =============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    action TEXT NOT NULL,                 -- created, updated, deleted, classified, fused
    entity_type TEXT NOT NULL,            -- event, entity, alert, brief
    entity_id TEXT NOT NULL,
    details TEXT                          -- JSON blob describing the change
);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
