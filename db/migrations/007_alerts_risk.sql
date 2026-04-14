-- Migration 007: Alerts, risk scores, anomaly detection, velocity tracking

-- =============================================================
-- RISK_SCORES — composite risk per region/topic
-- =============================================================
CREATE TABLE IF NOT EXISTS risk_scores (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,              -- 'region', 'country', 'topic', 'entity'
    scope_value TEXT NOT NULL,             -- e.g. 'Middle East', 'US', 'military', 'NATO'
    score REAL NOT NULL,                   -- 0-100 composite risk
    components TEXT NOT NULL,              -- JSON: {severity_avg, confidence_avg, corroboration, velocity, decay_factor}
    event_count INTEGER DEFAULT 0,
    source_count INTEGER DEFAULT 0,        -- distinct sources contributing
    trend TEXT DEFAULT 'stable',           -- 'rising', 'falling', 'stable', 'spike'
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(scope_type, scope_value)
);

CREATE INDEX IF NOT EXISTS idx_risk_scope ON risk_scores(scope_type, scope_value);
CREATE INDEX IF NOT EXISTS idx_risk_score ON risk_scores(score DESC);

-- =============================================================
-- ALERT_CONFIGS — user-configurable alert thresholds
-- =============================================================
CREATE TABLE IF NOT EXISTS alert_configs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scope_type TEXT NOT NULL,              -- 'region', 'country', 'topic', 'global'
    scope_value TEXT,                       -- null for global
    min_severity INTEGER DEFAULT 70,
    min_risk_score INTEGER DEFAULT 60,
    categories TEXT,                        -- JSON array of categories, null = all
    enabled INTEGER DEFAULT 1,
    cooldown_minutes INTEGER DEFAULT 60,   -- min time between alerts for same scope
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- =============================================================
-- ALERT_HISTORY — fired alerts with dedup tracking
-- =============================================================
CREATE TABLE IF NOT EXISTS alert_history (
    id TEXT PRIMARY KEY,
    config_id TEXT REFERENCES alert_configs(id),
    alert_type TEXT NOT NULL,              -- 'threshold', 'velocity_spike', 'anomaly', 'prediction_miss'
    title TEXT NOT NULL,
    description TEXT,
    severity REAL NOT NULL,
    scope_type TEXT,
    scope_value TEXT,
    event_ids TEXT,                         -- JSON array of triggering events
    acknowledged INTEGER DEFAULT 0,
    acknowledged_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_alert_history_type ON alert_history(alert_type);
CREATE INDEX IF NOT EXISTS idx_alert_history_created ON alert_history(created_at);
CREATE INDEX IF NOT EXISTS idx_alert_history_ack ON alert_history(acknowledged);

-- =============================================================
-- EVENT_VELOCITY — rolling event rate tracking per scope
-- =============================================================
CREATE TABLE IF NOT EXISTS event_velocity (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    scope_value TEXT NOT NULL,
    period TEXT NOT NULL,                   -- '1h', '6h', '24h'
    event_count INTEGER NOT NULL,
    avg_severity REAL,
    baseline_rate REAL,                    -- rolling 7-day average for this period
    velocity_ratio REAL,                   -- current / baseline
    computed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(scope_type, scope_value, period)
);

CREATE INDEX IF NOT EXISTS idx_velocity_scope ON event_velocity(scope_type, scope_value);
CREATE INDEX IF NOT EXISTS idx_velocity_ratio ON event_velocity(velocity_ratio DESC);

-- =============================================================
-- SURPRISE_INDEX — morning prediction vs evening reality gap
-- =============================================================
CREATE TABLE IF NOT EXISTS surprise_index (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    prediction_id TEXT REFERENCES predictions(id),
    predicted_outcome TEXT,
    actual_outcome TEXT,
    surprise_score REAL,                   -- 0-100, how unexpected the day was
    components TEXT,                        -- JSON breakdown
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_surprise_date ON surprise_index(date);

-- Seed default global alert configs
INSERT OR IGNORE INTO alert_configs (id, name, scope_type, scope_value, min_severity, min_risk_score, cooldown_minutes)
VALUES
    ('default-critical', 'Critical Events', 'global', NULL, 85, 80, 30),
    ('default-high', 'High Severity Events', 'global', NULL, 70, 60, 60),
    ('default-velocity', 'Velocity Spikes', 'global', NULL, 50, 40, 120);
