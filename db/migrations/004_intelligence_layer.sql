-- Migration 004: Intelligence layer — briefs, world state, predictions, fusion

-- =============================================================
-- BRIEFS — generated intelligence reports
-- =============================================================
CREATE TABLE IF NOT EXISTS briefs (
    id TEXT PRIMARY KEY,
    brief_type TEXT NOT NULL,            -- daily, weekly, flash, regional
    title TEXT NOT NULL,
    content TEXT NOT NULL,                -- markdown-formatted brief
    summary TEXT,                         -- one-paragraph executive summary
    region TEXT,                          -- optional regional focus
    event_ids TEXT,                       -- JSON array of source event IDs
    entity_ids TEXT,                      -- JSON array of referenced entity IDs
    grounding_score REAL,                -- 0-1.0, fraction of claims with source backing
    model_used TEXT,                      -- which Claude model generated this
    token_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    metadata TEXT                         -- JSON blob (prompt tokens, cost, etc.)
);

CREATE INDEX IF NOT EXISTS idx_briefs_type ON briefs(brief_type);
CREATE INDEX IF NOT EXISTS idx_briefs_created ON briefs(created_at);

-- =============================================================
-- WORLD_STATE — compressed institutional memory
-- =============================================================
CREATE TABLE IF NOT EXISTS world_state (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,                   -- date this state covers
    content TEXT NOT NULL,                -- compressed world state document
    token_count INTEGER,
    events_summarized INTEGER,            -- how many events were compressed
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_world_state_date ON world_state(date);

-- =============================================================
-- PREDICTIONS — testable intelligence predictions
-- =============================================================
CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY,
    brief_id TEXT REFERENCES briefs(id),
    prediction TEXT NOT NULL,
    confidence REAL NOT NULL,             -- 0-1.0
    timeframe TEXT,                       -- e.g. "24h", "7d", "30d"
    category TEXT,
    outcome TEXT,                         -- null until resolved, then "correct" or "incorrect"
    outcome_event_id TEXT,                -- event that confirmed/denied prediction
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_predictions_outcome ON predictions(outcome);
CREATE INDEX IF NOT EXISTS idx_predictions_brief ON predictions(brief_id);

-- =============================================================
-- FUSION_SIGNALS — cross-domain correlations detected
-- =============================================================
CREATE TABLE IF NOT EXISTS fusion_signals (
    id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,            -- sanctions_evasion, escalation, economic_crisis, etc.
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity REAL NOT NULL,
    confidence REAL NOT NULL,
    event_ids TEXT NOT NULL,              -- JSON array of correlated event IDs
    entity_ids TEXT,                      -- JSON array of involved entities
    grounding_score REAL,
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_fusion_type ON fusion_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_fusion_severity ON fusion_signals(severity);

-- =============================================================
-- RED_TEAM_ANALYSES — devil's advocate counterarguments
-- =============================================================
CREATE TABLE IF NOT EXISTS red_team_analyses (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,            -- event, brief, fusion_signal
    target_id TEXT NOT NULL,
    counterarguments TEXT NOT NULL,       -- JSON array of counterargument objects
    alternative_hypotheses TEXT,          -- JSON array
    confidence_adjustment REAL,           -- suggested adjustment to original confidence
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_red_team_target ON red_team_analyses(target_type, target_id);
