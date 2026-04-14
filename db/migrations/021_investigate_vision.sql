-- Migration 021: Autonomous investigation agent + satellite change detection
-- Tables for deep-dive investigations and satellite vision comparisons.

CREATE TABLE IF NOT EXISTS investigations (
    id                   TEXT PRIMARY KEY,
    trigger_type         TEXT NOT NULL,        -- event, alert, vessel, fusion
    trigger_id           TEXT NOT NULL,
    title                TEXT DEFAULT '',
    summary              TEXT DEFAULT '',
    key_findings         TEXT DEFAULT '[]',    -- JSON array
    risk_assessment      TEXT DEFAULT 'medium',
    confidence           REAL DEFAULT 0.5,
    recommended_actions  TEXT DEFAULT '[]',    -- JSON array
    entities_of_interest TEXT DEFAULT '[]',    -- JSON array
    sources_consulted    TEXT DEFAULT '[]',    -- JSON array of tool names
    tool_calls_made      INTEGER DEFAULT 0,
    input_tokens         INTEGER DEFAULT 0,
    output_tokens        INTEGER DEFAULT 0,
    model_used           TEXT DEFAULT '',
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_investigations_trigger
    ON investigations(trigger_type, trigger_id);
CREATE INDEX IF NOT EXISTS idx_investigations_created
    ON investigations(created_at DESC);

CREATE TABLE IF NOT EXISTS satellite_change_detections (
    id                      TEXT PRIMARY KEY,
    before_image_id         TEXT REFERENCES satellite_cache(id),
    after_image_id          TEXT REFERENCES satellite_cache(id),
    changes_json            TEXT DEFAULT '{}',   -- Full detection result
    strategic_significance  TEXT DEFAULT 'low',
    model_used              TEXT DEFAULT '',
    mode                    TEXT DEFAULT 'metadata',  -- vision or metadata
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_sat_change_created
    ON satellite_change_detections(created_at DESC);
