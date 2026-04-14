-- Migration 005: Natural language query — conversation sessions

-- =============================================================
-- CONVERSATION_SESSIONS — multi-turn query sessions
-- =============================================================
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id TEXT PRIMARY KEY,
    title TEXT,                            -- auto-generated from first question
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated ON conversation_sessions(updated_at);

-- =============================================================
-- CONVERSATION_TURNS — individual Q&A pairs within a session
-- =============================================================
CREATE TABLE IF NOT EXISTS conversation_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    event_ids TEXT,                         -- JSON array of referenced event IDs
    entity_ids TEXT,                        -- JSON array of referenced entity IDs
    grounding_score REAL,                  -- 0-1.0
    suggested_questions TEXT,              -- JSON array of 3 follow-up suggestions
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id, turn_number);
