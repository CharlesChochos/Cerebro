-- 014: Intelligence tradecraft — key assumptions, I&W framework, association matrix,
-- threat assessment matrix, IC source ratings (A-F / 1-6).

CREATE TABLE IF NOT EXISTS key_assumptions (
    id              TEXT PRIMARY KEY,
    assessment_id   TEXT,                       -- links to the assessment being evaluated
    assumption_text TEXT NOT NULL,
    confidence      TEXT DEFAULT 'moderate',     -- low / moderate / high
    evidence_for    TEXT,                        -- JSON array of supporting evidence
    evidence_against TEXT,                       -- JSON array of contradicting evidence
    status          TEXT DEFAULT 'untested',     -- untested / confirmed / challenged / disproven
    impact_if_wrong TEXT DEFAULT 'moderate',     -- low / moderate / high / critical
    analyst         TEXT,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assumptions_assessment ON key_assumptions(assessment_id);
CREATE INDEX IF NOT EXISTS idx_assumptions_status ON key_assumptions(status);

CREATE TABLE IF NOT EXISTS iw_frameworks (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    threat_type     TEXT,                        -- military / political / economic / cyber / terrorism
    region          TEXT,
    country_code    TEXT,
    status          TEXT DEFAULT 'active',       -- active / triggered / expired / archived
    threshold_pct   REAL DEFAULT 60.0,           -- % of indicators needed to trigger warning
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_iw_status ON iw_frameworks(status);
CREATE INDEX IF NOT EXISTS idx_iw_threat_type ON iw_frameworks(threat_type);

CREATE TABLE IF NOT EXISTS iw_indicators (
    id              TEXT PRIMARY KEY,
    framework_id    TEXT NOT NULL REFERENCES iw_frameworks(id),
    indicator_text  TEXT NOT NULL,
    category        TEXT,                        -- diplomatic / military / economic / information / social
    weight          REAL DEFAULT 1.0,            -- relative importance
    status          TEXT DEFAULT 'not_observed',  -- not_observed / possible / observed / confirmed
    observed_at     TEXT,
    evidence        TEXT,                        -- JSON evidence details
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_iw_ind_framework ON iw_indicators(framework_id);
CREATE INDEX IF NOT EXISTS idx_iw_ind_status ON iw_indicators(status);

CREATE TABLE IF NOT EXISTS association_matrix (
    id                TEXT PRIMARY KEY,
    entity_a_type     TEXT NOT NULL,              -- event / entity / source / country
    entity_a_id       TEXT NOT NULL,
    entity_a_label    TEXT,
    entity_b_type     TEXT NOT NULL,
    entity_b_id       TEXT NOT NULL,
    entity_b_label    TEXT,
    relationship_type TEXT NOT NULL,              -- linked / co-located / co-temporal / financial / command / communication
    strength          REAL DEFAULT 0.5,           -- 0.0 to 1.0
    confidence        TEXT DEFAULT 'moderate',    -- low / moderate / high
    evidence          TEXT,                       -- JSON evidence basis
    bidirectional     INTEGER DEFAULT 1,          -- 1 = A↔B, 0 = A→B
    analyst           TEXT,
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assoc_entity_a ON association_matrix(entity_a_type, entity_a_id);
CREATE INDEX IF NOT EXISTS idx_assoc_entity_b ON association_matrix(entity_b_type, entity_b_id);
CREATE INDEX IF NOT EXISTS idx_assoc_relationship ON association_matrix(relationship_type);

CREATE TABLE IF NOT EXISTS threat_assessments (
    id                TEXT PRIMARY KEY,
    threat_name       TEXT NOT NULL,
    threat_type       TEXT,                       -- state / non-state / cyber / natural / economic
    description       TEXT,
    capability_score  REAL DEFAULT 0,             -- 0-100
    intent_score      REAL DEFAULT 0,             -- 0-100
    opportunity_score REAL DEFAULT 0,             -- 0-100
    vulnerability_score REAL DEFAULT 50,          -- 0-100  (defender perspective)
    overall_score     REAL DEFAULT 0,             -- computed composite
    region            TEXT,
    country_code      TEXT,
    timeframe         TEXT DEFAULT 'near-term',   -- near-term / mid-term / long-term
    status            TEXT DEFAULT 'active',       -- active / mitigated / expired
    analyst           TEXT,
    evidence          TEXT,                        -- JSON evidence
    mitigations       TEXT,                        -- JSON mitigation actions
    created_at        TEXT DEFAULT (datetime('now')),
    updated_at        TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_threat_type ON threat_assessments(threat_type);
CREATE INDEX IF NOT EXISTS idx_threat_status ON threat_assessments(status);
CREATE INDEX IF NOT EXISTS idx_threat_region ON threat_assessments(region);

CREATE TABLE IF NOT EXISTS source_ratings (
    id                TEXT PRIMARY KEY,
    source_name       TEXT NOT NULL,
    source_type       TEXT,                       -- humint / sigint / osint / geoint / masint / techint
    reliability       TEXT NOT NULL DEFAULT 'C',  -- A (completely reliable) to F (cannot be judged)
    information_quality INTEGER NOT NULL DEFAULT 3, -- 1 (confirmed) to 6 (cannot be judged)
    composite_score   REAL,                       -- computed from reliability + quality
    rating_basis      TEXT,                       -- JSON: why this rating
    track_record      TEXT,                       -- JSON: historical accuracy
    last_report_date  TEXT,
    report_count      INTEGER DEFAULT 0,
    analyst           TEXT,
    notes             TEXT,
    created_at        TEXT DEFAULT (datetime('now')),
    updated_at        TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_source_name ON source_ratings(source_name);
CREATE INDEX IF NOT EXISTS idx_source_reliability ON source_ratings(reliability);
CREATE INDEX IF NOT EXISTS idx_source_type ON source_ratings(source_type);
