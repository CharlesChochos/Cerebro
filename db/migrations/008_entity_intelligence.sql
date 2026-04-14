-- Migration 008: Entity Intelligence — dossiers, ACH, workspaces, sanctions
-- Phase 9: God's Eye + Palantir-inspired entity analysis

-- =============================================================
-- TRACKED_ENTITIES — entities under active intelligence monitoring
-- =============================================================
CREATE TABLE IF NOT EXISTS tracked_entities (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id),
    priority TEXT NOT NULL DEFAULT 'normal',      -- critical, high, normal, low
    notes TEXT,
    risk_score REAL DEFAULT 0,
    tags TEXT,                                     -- JSON array of tags
    tracked_since TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_activity TEXT,
    UNIQUE(entity_id)
);

CREATE INDEX IF NOT EXISTS idx_tracked_entities_priority ON tracked_entities(priority);

-- =============================================================
-- ENTITY_DOSSIERS — synthesized intelligence profiles
-- =============================================================
CREATE TABLE IF NOT EXISTS entity_dossiers (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id),
    summary TEXT NOT NULL,
    key_facts TEXT,                                -- JSON array of key facts
    risk_assessment TEXT,
    timeline_events TEXT,                          -- JSON array of timeline entries
    source_count INTEGER DEFAULT 0,
    event_count INTEGER DEFAULT 0,
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_entity_dossiers_entity ON entity_dossiers(entity_id);

-- =============================================================
-- ANALYSIS_WORKSPACES — notebook-style analysis containers
-- =============================================================
CREATE TABLE IF NOT EXISTS analysis_workspaces (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    workspace_type TEXT NOT NULL DEFAULT 'notebook',  -- notebook, ach, link_analysis
    status TEXT NOT NULL DEFAULT 'active',             -- active, archived
    content TEXT,                                       -- JSON blob of workspace state
    pinned_events TEXT,                                 -- JSON array of event IDs
    pinned_entities TEXT,                               -- JSON array of entity IDs
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_workspaces_type ON analysis_workspaces(workspace_type);
CREATE INDEX IF NOT EXISTS idx_workspaces_status ON analysis_workspaces(status);

-- =============================================================
-- ACH_FRAMEWORKS — Analysis of Competing Hypotheses matrices
-- =============================================================
CREATE TABLE IF NOT EXISTS ach_frameworks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT REFERENCES analysis_workspaces(id),
    title TEXT NOT NULL,
    description TEXT,
    hypotheses TEXT NOT NULL,                           -- JSON array of hypothesis strings
    evidence TEXT NOT NULL,                             -- JSON array of evidence items
    matrix TEXT NOT NULL,                               -- JSON 2D array: matrix[evidence_idx][hypothesis_idx] = C/I/N/NA
    conclusion TEXT,                                    -- Claude's analysis summary
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_ach_workspace ON ach_frameworks(workspace_id);

-- =============================================================
-- SANCTIONS_WATCHLIST — SDN list entries for evasion detection
-- =============================================================
CREATE TABLE IF NOT EXISTS sanctions_watchlist (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases TEXT,                                       -- JSON array of known aliases
    entity_type TEXT NOT NULL,                          -- person, organization, vessel
    program TEXT,                                       -- OFAC SDN, EU sanctions, UN sanctions
    country_code TEXT,
    details TEXT,                                       -- JSON blob
    added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_sanctions_name ON sanctions_watchlist(name);
CREATE INDEX IF NOT EXISTS idx_sanctions_type ON sanctions_watchlist(entity_type);

-- =============================================================
-- SANCTIONS_HITS — detected matches between entities and watchlist
-- =============================================================
CREATE TABLE IF NOT EXISTS sanctions_hits (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id),
    watchlist_id TEXT NOT NULL REFERENCES sanctions_watchlist(id),
    match_type TEXT NOT NULL,                           -- direct, alias, multi_hop
    match_confidence REAL NOT NULL DEFAULT 0.5,
    hop_path TEXT,                                      -- JSON array of entity IDs in the path
    details TEXT,
    detected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    reviewed INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sanctions_hits_entity ON sanctions_hits(entity_id);
CREATE INDEX IF NOT EXISTS idx_sanctions_hits_reviewed ON sanctions_hits(reviewed);

-- Seed some sample sanctions watchlist entries for testing
INSERT OR IGNORE INTO sanctions_watchlist (id, name, aliases, entity_type, program, country_code, details)
VALUES
    ('sdn-001', 'Test Sanctioned Org', '["TSO","TestSanc Corp"]', 'organization', 'OFAC SDN', 'IR', '{"reason":"WMD proliferation"}'),
    ('sdn-002', 'Dark Fleet Shipping', '["DF Maritime","Shadow Tankers Ltd"]', 'organization', 'OFAC SDN', 'RU', '{"reason":"Oil price cap evasion"}'),
    ('sdn-003', 'Test Sanctioned Person', '["T.S. Person"]', 'person', 'EU Sanctions', 'KP', '{"reason":"Nuclear program"}');
