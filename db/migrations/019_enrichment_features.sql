-- 019: Enrichment features — photo pins, EXIF metadata, event context enrichment.

-- Photo pins from news imagery (geolocated photos extracted from articles)
CREATE TABLE IF NOT EXISTS photo_pins (
    id              TEXT PRIMARY KEY,
    event_id        TEXT,                               -- linked event (nullable)
    source_url      TEXT NOT NULL,                      -- original article/image URL
    image_url       TEXT,                               -- direct image URL if available
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    title           TEXT,
    caption         TEXT,
    country_code    TEXT,
    -- EXIF metadata (if extracted)
    exif_lat        REAL,                               -- GPS from EXIF
    exif_lng        REAL,                               -- GPS from EXIF
    exif_timestamp  TEXT,                               -- datetime from EXIF
    exif_camera     TEXT,                               -- camera model
    exif_mismatch   INTEGER DEFAULT 0,                  -- 1 if claimed location != EXIF GPS
    mismatch_km     REAL,                               -- distance between claimed and EXIF location
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_photo_pins_event ON photo_pins(event_id);
CREATE INDEX IF NOT EXISTS idx_photo_pins_loc ON photo_pins(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_photo_pins_mismatch ON photo_pins(exif_mismatch);

-- Event context enrichment cache (nearest city, terrain type, etc.)
CREATE TABLE IF NOT EXISTS event_enrichments (
    id              TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL UNIQUE,
    nearest_city    TEXT,
    admin_region    TEXT,
    country_name    TEXT,
    terrain_type    TEXT,                               -- urban / rural / coastal / mountain / desert
    population_density TEXT,                            -- high / medium / low / uninhabited
    nearest_border_km REAL,
    nearest_military_km REAL,
    elevation_m     REAL,
    enriched_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_enrichment_event ON event_enrichments(event_id);
