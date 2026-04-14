-- Migration 011: Advanced AI features
-- Multi-perspective simulation, hallucination firewall, leading indicators

-- =============================================================
-- MULTI_PERSPECTIVE — parallel actor interpretations of events
-- =============================================================
CREATE TABLE IF NOT EXISTS multi_perspective (
    id TEXT PRIMARY KEY,
    event_id TEXT,                            -- triggering event (nullable for region-level)
    region TEXT,
    scenario_title TEXT NOT NULL,
    actors TEXT NOT NULL,                     -- JSON array of actor names
    perspectives TEXT NOT NULL,               -- JSON array of {actor, interpretation, goals, likely_response, miscalculation_risk}
    divergence_score REAL,                    -- 0-1: how much perspectives diverge (higher = more dangerous)
    miscalculation_risk TEXT,                 -- overall assessment
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_multi_persp_event ON multi_perspective(event_id);
CREATE INDEX IF NOT EXISTS idx_multi_persp_region ON multi_perspective(region);

-- =============================================================
-- GROUNDING_AUDITS — hallucination firewall results
-- =============================================================
CREATE TABLE IF NOT EXISTS grounding_audits (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,                -- brief, fusion_signal, dossier
    target_id TEXT NOT NULL,
    total_claims INTEGER DEFAULT 0,
    grounded_claims INTEGER DEFAULT 0,
    ungrounded_claims INTEGER DEFAULT 0,
    grounding_score REAL,                     -- grounded / total
    flagged_claims TEXT,                      -- JSON array of {claim, reason, severity}
    sanitized_text TEXT,                      -- text with ungrounded claims removed/flagged
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_grounding_target ON grounding_audits(target_type, target_id);

-- =============================================================
-- LEADING_INDICATORS — detected cross-domain correlations
-- =============================================================
CREATE TABLE IF NOT EXISTS leading_indicators (
    id TEXT PRIMARY KEY,
    indicator_name TEXT NOT NULL,             -- e.g. "wheat_price → political_instability"
    leading_series TEXT NOT NULL,             -- category/metric that leads
    lagging_series TEXT NOT NULL,             -- category/metric that follows
    correlation REAL,                         -- Pearson r
    lag_days INTEGER,                         -- how far ahead the leader is
    current_status TEXT,                      -- firing, dormant, expired
    last_signal_value REAL,                   -- latest value of leading indicator
    threshold REAL,                           -- value that triggers "firing"
    description TEXT,                         -- Claude interpretation
    historical_accuracy REAL,                 -- how often this pattern has held
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_leading_status ON leading_indicators(current_status);
