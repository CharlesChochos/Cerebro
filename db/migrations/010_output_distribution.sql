-- Migration 010: Output, Distribution & External Interfaces
-- Phase 11: Country profiles, webhooks, widgets, reports

-- =============================================================
-- COUNTRY_PROFILES — auto-generated weekly risk profiles
-- =============================================================
CREATE TABLE IF NOT EXISTS country_profiles (
    id TEXT PRIMARY KEY,
    country_code TEXT NOT NULL,
    country_name TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    risk_score REAL,
    risk_trend TEXT,                          -- rising, stable, falling
    event_count INTEGER DEFAULT 0,
    top_categories TEXT,                      -- JSON array of {category, count}
    executive_summary TEXT,
    key_events TEXT,                          -- JSON array of event summaries
    predictions TEXT,                         -- JSON array of predictions
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_country_profiles_code ON country_profiles(country_code);
CREATE INDEX IF NOT EXISTS idx_country_profiles_period ON country_profiles(period_end);

-- =============================================================
-- WEEKLY_REPORTS — "week in review" trend reports
-- =============================================================
CREATE TABLE IF NOT EXISTS weekly_reports (
    id TEXT PRIMARY KEY,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    title TEXT NOT NULL,
    executive_summary TEXT,
    global_risk_score REAL,
    trending_topics TEXT,                     -- JSON array
    key_events TEXT,                          -- JSON array
    predictions_review TEXT,                  -- JSON: how last week's predictions performed
    outlook TEXT,                             -- Next week outlook
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_weekly_reports_week ON weekly_reports(week_end);

-- =============================================================
-- WEBHOOKS — external notification endpoints
-- =============================================================
CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    secret TEXT,                               -- HMAC signing secret
    event_types TEXT NOT NULL,                 -- JSON array: ["alert", "risk_threshold", "velocity_spike", "new_brief"]
    filters TEXT,                              -- JSON: {country_code, category, severity_min}
    active INTEGER DEFAULT 1,
    last_fired TEXT,
    fire_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_webhooks_active ON webhooks(active);

-- =============================================================
-- WEBHOOK_LOG — delivery tracking
-- =============================================================
CREATE TABLE IF NOT EXISTS webhook_log (
    id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL REFERENCES webhooks(id),
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,                     -- JSON payload sent
    status_code INTEGER,
    response_body TEXT,
    success INTEGER DEFAULT 0,
    fired_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_webhook_log_webhook ON webhook_log(webhook_id);

-- =============================================================
-- EMBED_TOKENS — time-limited tokens for embeddable widgets
-- =============================================================
CREATE TABLE IF NOT EXISTS embed_tokens (
    id TEXT PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    widget_type TEXT NOT NULL,                 -- risk_score, event_feed, alert_ticker
    scope TEXT,                                -- JSON: {country_code, category, entity_id}
    expires_at TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    access_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_embed_tokens_token ON embed_tokens(token);
CREATE INDEX IF NOT EXISTS idx_embed_tokens_active ON embed_tokens(active);
