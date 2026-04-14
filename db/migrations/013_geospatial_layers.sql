-- Migration 013: Geospatial layers — maritime zones, elevation profiles,
-- vegetation indices, predictive positioning, data lineage.

-- =============================================================
-- MARITIME_ZONES — shipping lanes, EEZ, sensitive areas
-- =============================================================
CREATE TABLE IF NOT EXISTS maritime_zones (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    zone_type TEXT NOT NULL,            -- eez, shipping_lane, chokepoint, restricted, anchorage
    country_code TEXT,
    polygon_json TEXT NOT NULL,          -- GeoJSON polygon/multipolygon
    bbox_west REAL,
    bbox_south REAL,
    bbox_east REAL,
    bbox_north REAL,
    description TEXT,
    risk_level TEXT DEFAULT 'normal',    -- normal, elevated, high, critical
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_maritime_zones_type ON maritime_zones(zone_type);
CREATE INDEX IF NOT EXISTS idx_maritime_zones_bbox ON maritime_zones(bbox_west, bbox_south, bbox_east, bbox_north);

-- =============================================================
-- ELEVATION_PROFILES — stored elevation path data
-- =============================================================
CREATE TABLE IF NOT EXISTS elevation_profiles (
    id TEXT PRIMARY KEY,
    name TEXT,
    points_json TEXT NOT NULL,           -- JSON [[lat,lng,elevation_m], ...]
    total_distance_km REAL,
    min_elevation_m REAL,
    max_elevation_m REAL,
    elevation_gain_m REAL,
    elevation_loss_m REAL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- =============================================================
-- VEGETATION_READINGS — NDVI and vegetation index data
-- =============================================================
CREATE TABLE IF NOT EXISTS vegetation_readings (
    id TEXT PRIMARY KEY,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    country_code TEXT,
    region TEXT,
    ndvi REAL,                           -- Normalized Difference Vegetation Index (-1 to 1)
    baseline_ndvi REAL,
    change_pct REAL,
    classification TEXT,                  -- lush, normal, stressed, barren, water
    capture_date TEXT,
    source TEXT DEFAULT 'modis',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_vegetation_capture ON vegetation_readings(capture_date);
CREATE INDEX IF NOT EXISTS idx_vegetation_country ON vegetation_readings(country_code);

-- =============================================================
-- PREDICTIVE_POSITIONS — predicted future event/entity locations
-- =============================================================
CREATE TABLE IF NOT EXISTS predictive_positions (
    id TEXT PRIMARY KEY,
    prediction_type TEXT NOT NULL,        -- event_hotspot, entity_movement, vessel_destination, escalation_zone
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    radius_km REAL DEFAULT 50,
    probability REAL DEFAULT 0.5,
    category TEXT,
    country_code TEXT,
    region TEXT,
    description TEXT,
    basis TEXT DEFAULT '[]',              -- JSON: event_ids or evidence used
    time_horizon_hours INTEGER DEFAULT 72,
    expires_at TEXT,
    realized INTEGER DEFAULT 0,           -- was this prediction confirmed?
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_predictive_type ON predictive_positions(prediction_type);
CREATE INDEX IF NOT EXISTS idx_predictive_expires ON predictive_positions(expires_at);

-- =============================================================
-- DATA_LINEAGE — audit trail for all data items
-- =============================================================
CREATE TABLE IF NOT EXISTS data_lineage (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,            -- event, entity, brief, alert, fusion_signal, prediction
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,                 -- created, updated, enriched, classified, fused, audited, exported
    actor TEXT NOT NULL,                  -- system component: ingestion, classifier, fuser, grounding, api, user
    details TEXT DEFAULT '{}',            -- JSON: what changed, parameters used
    parent_lineage_id TEXT,               -- FK to previous lineage entry (chain)
    source_ids TEXT DEFAULT '[]',         -- JSON: upstream entity IDs that contributed
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_lineage_entity ON data_lineage(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_lineage_action ON data_lineage(action);
CREATE INDEX IF NOT EXISTS idx_lineage_actor ON data_lineage(actor);
CREATE INDEX IF NOT EXISTS idx_lineage_created ON data_lineage(created_at);

-- Seed maritime chokepoints and sensitive zones
INSERT OR IGNORE INTO maritime_zones (id, name, zone_type, description, risk_level, polygon_json, bbox_west, bbox_south, bbox_east, bbox_north)
VALUES
    ('mz-hormuz', 'Strait of Hormuz', 'chokepoint',
     '21% of global oil transit. Critical chokepoint between Persian Gulf and Gulf of Oman.', 'high',
     '[[56.0,26.0],[56.5,26.0],[56.5,27.0],[56.0,27.0],[56.0,26.0]]',
     56.0, 26.0, 56.5, 27.0),
    ('mz-malacca', 'Strait of Malacca', 'chokepoint',
     'Busiest shipping lane globally. 25% of all traded goods transit here.', 'elevated',
     '[[99.5,1.0],[104.5,1.0],[104.5,4.0],[99.5,4.0],[99.5,1.0]]',
     99.5, 1.0, 104.5, 4.0),
    ('mz-suez', 'Suez Canal Zone', 'chokepoint',
     'Critical trade route connecting Mediterranean and Red Sea. 12% of global trade.', 'elevated',
     '[[32.0,29.5],[33.0,29.5],[33.0,31.5],[32.0,31.5],[32.0,29.5]]',
     32.0, 29.5, 33.0, 31.5),
    ('mz-bab', 'Bab el-Mandeb', 'chokepoint',
     'Gateway between Red Sea and Gulf of Aden. Houthi attacks make this critical.', 'critical',
     '[[42.5,12.0],[44.0,12.0],[44.0,13.5],[42.5,13.5],[42.5,12.0]]',
     42.5, 12.0, 44.0, 13.5),
    ('mz-taiwan', 'Taiwan Strait', 'chokepoint',
     'Strategic waterway between Taiwan and mainland China. High military tension.', 'high',
     '[[118.0,23.0],[120.5,23.0],[120.5,26.0],[118.0,26.0],[118.0,23.0]]',
     118.0, 23.0, 120.5, 26.0),
    ('mz-panama', 'Panama Canal Zone', 'chokepoint',
     'Connects Atlantic and Pacific. 5% of global trade. Drought causing transit delays.', 'elevated',
     '[[-80.0,8.8],[-79.4,8.8],[-79.4,9.5],[-80.0,9.5],[-80.0,8.8]]',
     -80.0, 8.8, -79.4, 9.5),
    ('mz-gibraltar', 'Strait of Gibraltar', 'chokepoint',
     'Gateway between Atlantic and Mediterranean. NATO monitoring zone.', 'normal',
     '[[-6.0,35.5],[-5.0,35.5],[-5.0,36.5],[-6.0,36.5],[-6.0,35.5]]',
     -6.0, 35.5, -5.0, 36.5),
    ('mz-scs', 'South China Sea', 'restricted',
     'Disputed waters with overlapping territorial claims. Heavy military presence.', 'high',
     '[[105.0,5.0],[120.0,5.0],[120.0,22.0],[105.0,22.0],[105.0,5.0]]',
     105.0, 5.0, 120.0, 22.0),
    ('mz-black-sea', 'Black Sea Zone', 'restricted',
     'Active conflict zone. Russian naval blockade and mine risk.', 'critical',
     '[[27.0,40.5],[42.0,40.5],[42.0,47.0],[27.0,47.0],[27.0,40.5]]',
     27.0, 40.5, 42.0, 47.0),
    ('mz-guinea', 'Gulf of Guinea', 'restricted',
     'Highest piracy risk globally. Major oil production and shipping zone.', 'high',
     '[[-5.0,0.0],[10.0,0.0],[10.0,7.0],[-5.0,7.0],[-5.0,0.0]]',
     -5.0, 0.0, 10.0, 7.0),
    ('mz-arctic-ne', 'Northern Sea Route', 'shipping_lane',
     'Arctic shipping route along Russian coast. Seasonal ice coverage.', 'elevated',
     '[[30.0,68.0],[180.0,68.0],[180.0,80.0],[30.0,80.0],[30.0,68.0]]',
     30.0, 68.0, 180.0, 80.0),
    ('mz-persian-gulf', 'Persian Gulf', 'restricted',
     'Major oil production zone. Heavy naval presence. Iran-US tensions.', 'high',
     '[[48.0,24.0],[56.5,24.0],[56.5,30.5],[48.0,30.5],[48.0,24.0]]',
     48.0, 24.0, 56.5, 30.5);
