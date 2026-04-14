-- Migration 012: Advanced analytics — historical analogs, cascade models,
-- narrative divergence, contrarian signals, narrative arcs.

-- Historical analog matches: stores matched historical patterns for current events
CREATE TABLE IF NOT EXISTS historical_analogs (
    id TEXT PRIMARY KEY,
    source_event_id TEXT,                   -- current event being analyzed
    source_region TEXT,
    source_category TEXT,
    analog_title TEXT NOT NULL,             -- name of the historical analog
    analog_description TEXT,                -- what happened historically
    analog_year INTEGER,
    analog_region TEXT,
    similarity_score REAL DEFAULT 0.0,      -- 0.0-1.0 how close the match is
    outcome_description TEXT,               -- what the historical outcome was
    key_differences TEXT DEFAULT '[]',       -- JSON array of differences
    key_similarities TEXT DEFAULT '[]',      -- JSON array of similarities
    risk_factors TEXT DEFAULT '[]',          -- JSON array of risk factors
    model_used TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Second-order cascade models: stores predicted event cascades
CREATE TABLE IF NOT EXISTS cascade_models (
    id TEXT PRIMARY KEY,
    trigger_event_id TEXT,                  -- triggering event
    trigger_description TEXT NOT NULL,
    region TEXT,
    country_code TEXT,
    cascade_steps TEXT DEFAULT '[]',        -- JSON: ordered list of predicted cascade steps
    total_steps INTEGER DEFAULT 0,
    max_severity REAL DEFAULT 0.0,
    probability_chain REAL DEFAULT 0.0,     -- product of step probabilities
    time_horizon_days INTEGER DEFAULT 30,
    status TEXT DEFAULT 'predicted',        -- predicted, partially_realized, realized, expired
    model_used TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cross-language narrative divergence: tracks how narratives differ across sources
CREATE TABLE IF NOT EXISTS narrative_divergence (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,                    -- topic being tracked
    region TEXT,
    country_code TEXT,
    source_clusters TEXT DEFAULT '[]',      -- JSON: groups of sources with similar narratives
    divergence_score REAL DEFAULT 0.0,      -- 0.0-1.0 how much narratives differ
    dominant_narrative TEXT,                -- most common narrative
    contrasting_narratives TEXT DEFAULT '[]', -- JSON: list of divergent narratives
    event_ids TEXT DEFAULT '[]',            -- JSON: events analyzed
    propaganda_indicators TEXT DEFAULT '[]', -- JSON: potential propaganda markers
    model_used TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Contrarian signals: events or patterns that go against the dominant trend
CREATE TABLE IF NOT EXISTS contrarian_signals (
    id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,              -- trend_reversal, outlier, counter_narrative, anomaly
    category TEXT,
    region TEXT,
    country_code TEXT,
    description TEXT NOT NULL,
    dominant_trend TEXT,                    -- what the trend currently is
    contrarian_evidence TEXT,               -- what contradicts the trend
    strength REAL DEFAULT 0.0,              -- 0.0-1.0 signal strength
    event_ids TEXT DEFAULT '[]',            -- JSON: supporting event IDs
    analysis TEXT,                          -- analytical assessment
    model_used TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Narrative arcs: tracks how narratives evolve over time
CREATE TABLE IF NOT EXISTS narrative_arcs (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    region TEXT,
    country_code TEXT,
    arc_phase TEXT DEFAULT 'emerging',      -- emerging, escalating, peak, declining, dormant
    intensity REAL DEFAULT 0.0,             -- 0.0-1.0 current intensity
    start_date TIMESTAMP,
    peak_date TIMESTAMP,
    event_count INTEGER DEFAULT 0,
    phase_history TEXT DEFAULT '[]',        -- JSON: timestamped phase transitions
    key_events TEXT DEFAULT '[]',           -- JSON: pivotal event IDs
    sentiment_trend TEXT DEFAULT '[]',      -- JSON: sentiment over time
    related_entities TEXT DEFAULT '[]',     -- JSON: key entities involved
    summary TEXT,
    model_used TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_historical_analogs_source ON historical_analogs(source_event_id);
CREATE INDEX IF NOT EXISTS idx_historical_analogs_category ON historical_analogs(source_category);
CREATE INDEX IF NOT EXISTS idx_cascade_models_trigger ON cascade_models(trigger_event_id);
CREATE INDEX IF NOT EXISTS idx_cascade_models_status ON cascade_models(status);
CREATE INDEX IF NOT EXISTS idx_narrative_divergence_topic ON narrative_divergence(topic);
CREATE INDEX IF NOT EXISTS idx_contrarian_signals_type ON contrarian_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_contrarian_signals_category ON contrarian_signals(category);
CREATE INDEX IF NOT EXISTS idx_narrative_arcs_topic ON narrative_arcs(topic);
CREATE INDEX IF NOT EXISTS idx_narrative_arcs_phase ON narrative_arcs(arc_phase);
