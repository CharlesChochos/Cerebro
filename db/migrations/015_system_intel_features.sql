-- 015: Ambient narration, proactive intelligence push, system self-awareness,
-- historical replay, commodity dependency mapping, capital flight detection.

-- Proactive intelligence push — scheduled/triggered alerts
CREATE TABLE IF NOT EXISTS proactive_alerts (
    id              TEXT PRIMARY KEY,
    alert_type      TEXT NOT NULL,              -- threshold_breach / pattern_match / scheduled_brief / anomaly
    priority        TEXT DEFAULT 'medium',      -- low / medium / high / critical
    title           TEXT NOT NULL,
    summary         TEXT,
    trigger_rule    TEXT,                       -- JSON: what triggered this alert
    target_entities TEXT,                       -- JSON: entity IDs this alert relates to
    region          TEXT,
    country_code    TEXT,
    status          TEXT DEFAULT 'pending',     -- pending / delivered / acknowledged / dismissed
    delivered_at    TEXT,
    acknowledged_at TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_proactive_status ON proactive_alerts(status);
CREATE INDEX IF NOT EXISTS idx_proactive_type ON proactive_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_proactive_priority ON proactive_alerts(priority);

-- System self-awareness — component health tracking
CREATE TABLE IF NOT EXISTS system_components (
    id              TEXT PRIMARY KEY,
    component_name  TEXT NOT NULL UNIQUE,
    component_type  TEXT,                       -- ingestion / processing / intelligence / api / database
    status          TEXT DEFAULT 'unknown',     -- healthy / degraded / down / unknown
    last_heartbeat  TEXT,
    last_error      TEXT,
    metrics         TEXT,                       -- JSON: component-specific metrics
    config          TEXT,                       -- JSON: component config
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_syscomp_status ON system_components(status);

-- Historical replay — time-indexed snapshots
CREATE TABLE IF NOT EXISTS replay_snapshots (
    id              TEXT PRIMARY KEY,
    snapshot_time   TEXT NOT NULL,              -- the point-in-time this represents
    snapshot_type   TEXT DEFAULT 'auto',        -- auto / manual / milestone
    label           TEXT,
    event_count     INTEGER DEFAULT 0,
    entity_count    INTEGER DEFAULT 0,
    summary_stats   TEXT,                       -- JSON: counts by category, region, etc.
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_replay_time ON replay_snapshots(snapshot_time);

-- Commodity dependency mapping
CREATE TABLE IF NOT EXISTS commodity_dependencies (
    id              TEXT PRIMARY KEY,
    country_code    TEXT NOT NULL,
    commodity_name  TEXT NOT NULL,
    commodity_code  TEXT,                       -- HS2 or custom code
    dependency_type TEXT DEFAULT 'import',      -- import / export / transit
    share_pct       REAL,                       -- % of country's total trade
    volume_usd      REAL,                       -- annual trade volume in USD
    top_partners    TEXT,                       -- JSON: list of trade partner country codes
    risk_level      TEXT DEFAULT 'normal',      -- normal / elevated / high / critical
    risk_factors    TEXT,                       -- JSON: what makes this dependency risky
    last_updated    TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_commodity_country ON commodity_dependencies(country_code);
CREATE INDEX IF NOT EXISTS idx_commodity_name ON commodity_dependencies(commodity_name);
CREATE INDEX IF NOT EXISTS idx_commodity_risk ON commodity_dependencies(risk_level);

-- Capital flight detection
CREATE TABLE IF NOT EXISTS capital_flight_signals (
    id              TEXT PRIMARY KEY,
    country_code    TEXT NOT NULL,
    signal_type     TEXT NOT NULL,              -- currency_drop / reserve_decline / bond_spread / outflow_spike / fx_control
    severity        REAL DEFAULT 50,            -- 0-100
    indicator_value REAL,                       -- the measured value
    baseline_value  REAL,                       -- historical baseline
    change_pct      REAL,                       -- % change from baseline
    description     TEXT,
    evidence        TEXT,                       -- JSON: supporting data
    detected_at     TEXT DEFAULT (datetime('now')),
    status          TEXT DEFAULT 'active'       -- active / confirmed / resolved / false_positive
);

CREATE INDEX IF NOT EXISTS idx_capflight_country ON capital_flight_signals(country_code);
CREATE INDEX IF NOT EXISTS idx_capflight_type ON capital_flight_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_capflight_severity ON capital_flight_signals(severity);
