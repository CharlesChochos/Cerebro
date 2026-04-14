# Cerebro Implementation Plan

> **Guiding Rule:** No phase begins until the previous phase runs error-free. Each phase ends with a validation checklist. Each phase produces a usable system.

## Principles

1. **No phase begins until the previous phase runs error-free** -- every phase ends with a validation checklist
2. **Each phase produces a usable system** -- vertical slices, not horizontal layers
3. **Data flows before UI** -- ingestion and processing must work before we build dashboards for them
4. **Simple before smart** -- SQLite before DuckDB analytics, basic map before 3D globe, text before vision

---

## Phase 0 -- Project Scaffolding & Database Foundation

**Goal:** Bootable project with database, dev environment, and one API health endpoint.

### Steps

1. Initialize git repo, Python 3.12 venv, project folder structure:
   ```
   cerebro/
     ingestion/          # Feed connectors (one file per source)
     processing/         # Event normalization, entity resolution
     intelligence/       # Claude API integration layer
       classify.py       # Event classification (Haiku)
       extract.py        # NER + entity graph (Haiku/Sonnet)
       fuse.py           # Cross-domain fusion (Sonnet)
       brief.py          # Intelligence brief generation (Opus)
       investigate.py    # Autonomous deep dive agent (Sonnet)
       redteam.py        # Devil's advocate agent (Sonnet)
       worldstate.py     # Nightly world state compression (Opus)
     detection/          # Anomaly detection, AIS gaps, nightlights
     api/                # FastAPI server
     cron/               # Scheduled jobs (ingestion, fusion, briefs)
     db/                 # SQLite schema, migrations, DuckDB queries
     frontend/           # Next.js dashboard app
     config/             # API keys, source configs, prompt templates
   ```
2. Create SQLite database with core schema:
   - `events` table + FTS5 virtual table
   - `entities` + `entity_relations`
   - `alerts`, `source_reliability`
   - `system_log` (for ambient narration from day one)
   - `audit_log` (provenance tracking from day one)
   - SpatiaLite extension loaded for geo queries
3. Create migration system (simple numbered SQL files)
4. FastAPI server with `/health` endpoint that confirms DB connection
5. Basic config system (`config/` with env vars for API keys)
6. Next.js frontend project init (inside `frontend/`), deploy to Vercel free tier with a placeholder landing page

### Validation Checklist

- [ ] `python -m pytest tests/test_db.py` -- schema creates, FTS5 works, SpatiaLite geo query works
- [ ] `uvicorn api.main:app` starts, `/health` returns 200
- [ ] `vercel deploy` succeeds, landing page loads at public URL
- [ ] Git repo has clean commit history

### Why This First

Everything depends on the database schema and API server. If these have bugs, every subsequent phase inherits them.

---

## Phase 1 -- First Data Source End-to-End (GDELT)

**Goal:** One source ingesting, one Claude classification running, one API endpoint serving events, one frontend page displaying them.

### Steps

1. **Ingestion:** `ingestion/gdelt.py` -- fetch from GDELT REST API (15-min updates), normalize into `events` table schema
2. **Processing:** `processing/normalize.py` -- deduplicate, geocode, standardize timestamps
3. **Claude Classification:** `intelligence/classify.py` -- Haiku batch API call to classify events into categories + severity + confidence
4. **API Endpoints:**
   - `GET /api/events` -- paginated, filterable by category/severity/date/country
   - `GET /api/events/{id}` -- single event detail with raw payload
5. **Cron:** `cron/ingest_gdelt.py` -- scheduled every 15 minutes
6. **Frontend:** Basic event feed page -- table/list of recent events with category badges, severity color coding, timestamp, and source link
7. **System log:** Every ingestion run writes to `system_log` (ambient narration foundation)

### Validation Checklist

- [ ] GDELT ingestion runs, writes 50+ events to SQLite
- [ ] Claude classifies events, severity/confidence populated
- [ ] API returns events, filters work
- [ ] Frontend displays events with real data
- [ ] Cron runs on schedule without errors
- [ ] No duplicate events on re-ingestion

### Why This Order

This is the minimum viable intelligence pipeline. One source -> one processor -> one display. Every subsequent phase adds to this working loop.

---

## Phase 2 -- Core Data Sources (OSINT + FININT)

**Goal:** 8 of 18 sources flowing, entity extraction working, knowledge graph building.

### Steps

1. **Ingestion connectors** (one file per source):
   - `ingestion/acled.py` -- conflict events (weekly)
   - `ingestion/rss.py` -- RSS feed fleet (50+ feeds, real-time)
   - `ingestion/reddit.py` -- Reddit API (worldnews, geopolitics, economics)
   - `ingestion/telegram_feeds.py` -- public OSINT channels
   - `ingestion/yahoo_finance.py` -- market quotes via yfinance
   - `ingestion/fred.py` -- economic time series
   - `ingestion/worldbank.py` -- macro indicators
2. **Entity Extraction:** `intelligence/extract.py` -- Haiku/Sonnet NER extracting people, orgs, vessels, locations -> `entities` + `entity_relations` tables
3. **Source reliability tracking:** `source_reliability` table populated with accuracy scores per source
4. **Confidence decay:** Implement exponential confidence fade on events without corroboration
5. **API Endpoints:**
   - `GET /api/entities` -- search entities across types
   - `GET /api/entities/{id}` -- entity detail with related events
   - `GET /api/sources` -- source health/reliability dashboard
6. **Frontend:**
   - Event feed upgraded with multi-source filtering
   - Source reliability status page
   - Basic entity search

### Validation Checklist

- [ ] All 8 sources ingest without errors
- [ ] Entity extraction populates knowledge graph (entities + relations)
- [ ] Confidence decay observable over time
- [ ] Source reliability scores compute correctly
- [ ] No cross-source duplicate events for same real-world occurrence
- [ ] API performance acceptable (<500ms for event queries)

---

## Phase 3 -- Map Foundation & Geospatial

**Goal:** Interactive globe with events plotted, basic layers, clustering.

### Steps

1. **MapLibre GL integration** in Next.js frontend
   - Globe projection (3D globe mode -- the hero screenshot)
   - Category-colored event markers
   - Smart clustering that declutters on zoom
2. **Layered overlay system** -- each data source as a toggleable layer
3. **Event detail popups** -- click marker -> event card with title, summary, severity, source link
4. **Time range filter** -- slider to filter events by date range on the map
5. **Event density heatmap** -- heat gradient layer toggle
6. **API:** `GET /api/events/geo` -- bounding box query using SpatiaLite for viewport-limited fetches
7. **Saved views / bookmarks** -- serialize map state (center, zoom, layers, filters) to `saved_views` table

### Validation Checklist

- [ ] Globe renders with all current events plotted
- [ ] Layers toggle on/off per source
- [ ] Clustering works, declutters on zoom
- [ ] Heatmap layer renders
- [ ] Bounding box API returns only viewport events
- [ ] Saved views persist and restore correctly
- [ ] Performance: smooth at 1,000+ markers

### Why This Before More AI Features

The map is the primary interface for most intelligence outputs. Building it now means every subsequent feature has a visual home immediately.

---

## Phase 4 -- SIGINT Sources & Maritime/Aviation Tracking

**Goal:** Live vessel and aircraft tracking on the globe.

### Steps

1. **Ingestion:**
   - `ingestion/aisstream.py` -- WebSocket connection to AISstream.io for real-time vessel positions
   - `ingestion/opensky.py` -- OpenSky Network REST API for flight positions (10-sec updates)
2. **Database:** `vessel_tracks` table populated with AIS position history
3. **Map layers:**
   - Vessel markers (color-coded by type: cargo, tanker, military, fishing)
   - Aircraft markers (color-coded: civilian, military, cargo)
   - Ship wake / trail visualization (fading trails)
   - Flight path replay animation
4. **AIS dark pattern detection:** `detection/ais_gaps.py` -- flag vessels that go dark
5. **Vessel detail card** -- ship name, IMO, flag, dimensions, AIS history
6. **API:**
   - `GET /api/vessels` -- current positions, filterable
   - `GET /api/vessels/{mmsi}/track` -- historical track
   - `GET /api/flights` -- current flights

### Validation Checklist

- [ ] Vessels render on globe in real-time
- [ ] Aircraft render with type silhouettes
- [ ] Trails/wakes visible for moving vessels
- [ ] Dark pattern detection flags gaps correctly
- [ ] Vessel detail card displays complete info
- [ ] WebSocket connection resilient to disconnects

---

## Phase 5 -- Claude Intelligence Layer (Fusion, Briefs, World State)

**Goal:** Cross-domain intelligence fusion, automated briefs, and institutional memory.

### Steps

1. **Cross-domain fusion:** `intelligence/fuse.py` -- Sonnet connects events across sources (e.g., vessel dark + conflict zone + commodity spike = sanctions evasion signal)
2. **Intelligence brief generation:** `intelligence/brief.py` -- Opus generates daily/weekly briefs with explanation-first formatting
3. **World state compression:** `intelligence/worldstate.py` -- Nightly Opus job compresses day's events into ~3,000-token institutional memory document
4. **Red team / devil's advocate:** `intelligence/redteam.py` -- Auto-triggered for events with risk > 70, counterarguments displayed alongside
5. **Hallucination firewall:** Every Claude-generated claim must map to `source_event_id`. Compute and store grounding score
6. **Database:** `briefs` table, `world_state` table, `predictions` table
7. **API:**
   - `GET /api/briefs` -- list generated briefs
   - `GET /api/briefs/{id}` -- brief detail with grounding score and source links
   - `GET /api/worldstate` -- current compressed world state
8. **Frontend:**
   - Briefs page with formatted intelligence reports
   - Red team sidebar on high-risk events
   - Source provenance links on every claim

### Validation Checklist

- [ ] Fusion detects cross-source correlations
- [ ] Daily brief generates with proper sourcing
- [ ] World state compresses within token budget
- [ ] Red team fires on high-risk events
- [ ] Grounding score computed, hallucinations flagged
- [ ] Every claim traceable to raw event

---

## Phase 6 -- Natural Language Query Interface

**Goal:** Ask Cerebro questions in plain English, get sourced answers.

### Steps

1. **NL query engine:** `intelligence/query.py` -- Sonnet answers questions using events DB, entity graph, and world state as context
2. **Conversation memory:** `conversation_sessions` table for multi-turn follow-up
3. **Suggested next questions:** Claude generates 3 follow-up suggestions per response
4. **API:** `POST /api/query` -- accepts natural language question, returns sourced answer
5. **Frontend:**
   - Chat-style NL query interface
   - Source citations inline with answers
   - Suggested follow-up question chips
   - Conversation history sidebar

### Validation Checklist

- [ ] Answers reference specific events with source links
- [ ] Follow-up questions maintain context
- [ ] Response time < 5 seconds
- [ ] No hallucinated events (grounding check)
- [ ] Suggested questions are contextually relevant

---

## Phase 7 -- SPECINT Sources & Satellite Imagery

**Goal:** Health, energy, climate data flowing + satellite imagery with Claude Vision.

### Steps

1. **Ingestion (remaining 10 sources):**
   - `ingestion/who.py` -- WHO Disease Outbreak News
   - `ingestion/promed.py` -- ProMED-mail early warnings
   - `ingestion/eia.py` -- US Energy Information Administration
   - `ingestion/noaa.py` -- Weather and severe events
   - `ingestion/comtrade.py` -- UN Comtrade bilateral trade
   - `ingestion/sentinel.py` -- Copernicus Sentinel-2 imagery (10m optical)
   - `ingestion/viirs.py` -- NASA VIIRS nighttime lights + fire detection
   - `ingestion/osm.py` -- OpenStreetMap change detection
2. **Satellite processing:** Claude Vision (Sonnet) for change detection on Sentinel-2 imagery
3. **Nightlight economic proxy:** `detection/nightlights.py` -- VIIRS nightlight change as GDP proxy
4. **Map layers:**
   - Disease outbreak markers with affected area polygons
   - Fire detection hotspots (VIIRS active fires)
   - Nightlight change overlay
   - Weather/severe event polygons
5. **Satellite cache:** `satellite_cache` table for Sentinel-2 imagery
6. **Satellite swipe comparator:** Before/after with draggable divider
7. **Historical imagery timelapse:** Animated Sentinel-2 snapshots with Claude Vision annotations

### Validation Checklist

- [ ] All 18 core sources now ingesting (complete set)
- [ ] Satellite imagery fetched and cached
- [ ] Claude Vision annotates satellite changes
- [ ] Nightlight proxy correlates with known economic events
- [ ] Swipe comparator works in frontend
- [ ] Timelapse plays smoothly

---

## Phase 8 -- Alerts, Risk Scores & Anomaly Detection

**Goal:** Automated alerting system with risk scores and anomaly detection.

### Steps

1. **Risk scoring engine:** Composite 0-100 score per region/topic combining severity, confidence, corroboration count, and decay
2. **Alert system:** `alerts` table with thresholds, dedup, and decay tracking
3. **DuckDB analytics:** Set up DuckDB for time-series aggregations, anomaly baselines, and rolling correlations
4. **Leading indicator detection:** DuckDB rolling correlations + Claude causal evaluation
5. **Surprise index:** Morning predictions vs. evening reality gap scoring
6. **Event velocity tracking:** Sparklines with auto-flag at 3x baseline
7. **Prediction logging:** `predictions` table with resolution checks and calibration feedback
8. **Frontend:**
   - Risk dashboard with scores per region/topic
   - Alert feed with severity and explanation
   - Sparkline velocity indicators
   - Prediction scorecard page
9. **API:**
   - `GET /api/alerts` -- active alerts
   - `GET /api/risk` -- risk scores by region/topic
   - `POST /api/alerts/configure` -- user threshold settings

### Validation Checklist

- [ ] Risk scores compute and update with new events
- [ ] Alerts fire on threshold crossings
- [ ] DuckDB queries return within acceptable time
- [ ] Anomaly detection catches known patterns (test with historical data)
- [ ] Prediction scorecard computes calibration
- [ ] No alert storms (dedup working)

---

## Phase 9 -- Entity Intelligence (God's Eye + Palantir Features)

**Goal:** Deep entity tracking, dossiers, relationship graphs, and analysis workspaces.

### Steps

1. **Entity omnisearch** -- search across all 18 data layers, Claude synthesizes dossier
2. **Cross-source entity tracking** -- auto-chain when entity goes dark in one source
3. **Entity dossier pages** -- comprehensive profile: timeline, risk score, related entities, all source events
4. **Interactive link analysis graph** -- D3.js force-directed network with shortest-path detection
5. **ACH workspace** -- hypotheses x evidence matrix, Claude fills C/I/N ratings
6. **Notebook-style analysis workspace** -- freeform canvas with pinned events and notes
7. **Sanctions evasion detection** -- multi-hop graph traversal against SDN list
8. **Database:** `tracked_entities`, `analysis_workspaces`, `iw_frameworks` tables
9. **Frontend:**
   - Entity dossier page
   - Link analysis graph view
   - ACH matrix workspace
   - Analysis notebook (basic canvas)

### Validation Checklist

- [ ] Entity search returns results across all sources
- [ ] Dossier pages render with complete profile
- [ ] Link analysis graph interactive, shortest-path works
- [ ] ACH matrix populated by Claude
- [ ] Sanctions evasion flags known test cases
- [ ] Cross-source tracking chains correctly

---

## Phase 10 -- Geospatial Advanced Features

**Goal:** 3D terrain, geofencing, measurement tools, advanced map interactions.

### Steps

1. **Geofencing:** Draw polygon on map, monitor all events inside -- `geofences` table
2. **3D terrain rendering** -- Mapzen/AWS terrain tiles
3. **Measurement tools** -- distance/area via Turf.js
4. **Elevation profiles** along drawn paths
5. **KML/KMZ import and export**
6. **Weapons range rings** -- concentric translucent circles per system from `weapons_systems` table
7. **3D vessel models** -- Three.js ThreeBox plugin for MapLibre
8. **Aircraft silhouettes** -- SVG icons by ICAO type code
9. **Missile trajectory arcs** -- animated ballistic/cruise arcs

### Validation Checklist

- [ ] Geofence alerts work for events inside drawn polygon
- [ ] 3D terrain renders with acceptable performance
- [ ] Distance/area measurements accurate
- [ ] KML import/export round-trips correctly
- [ ] Range rings render for configured weapons systems
- [ ] 3D vessel models render on globe

---

## Phase 11 -- Output, Distribution & External Interfaces

**Goal:** Briefs as PDF, Telegram/Discord bot, webhooks, embeddable widgets.

### Steps

1. **Auto-generated country risk profiles** -- weekly PDF one-pagers -- `country_profiles` table
2. **Weekly trend report** -- Sunday "week in review" brief
3. **Telegram / Discord bot** -- NL query interface via bot
4. **Webhook API** -- `webhooks` table, POST JSON on threshold crossings
5. **Embeddable risk widgets** -- iframes with optional expiry tokens
6. **Command palette (Cmd+K)** -- fuzzy search via cmdk library
7. **Keyboard shortcuts** with help overlay
8. **Split-screen dual view**

### Validation Checklist

- [ ] PDF country profiles generate correctly
- [ ] Weekly report auto-generates
- [ ] Telegram bot responds to queries with sourced answers
- [ ] Webhooks fire on configured thresholds
- [ ] Embeddable widgets render in isolation
- [ ] Cmd+K palette searches events, entities, views, commands

---

## Phase 12 -- Domain-Specific Modules & Advanced Analytics

**Goal:** Specialized monitoring modules and deep analytics.

### Steps

1. **Election monitoring module** -- `upcoming_elections` table, pre-positioned monitoring
2. **Nuclear proliferation indicators**
3. **Migration/refugee flow tracking**
4. **Cyber incident tracking**
5. **Historical analog matching** -- "This looks 73% like Crimea 2014"
6. **Second-order cascade modeling** -- what-if sandbox
7. **Cross-language narrative divergence** -- TASS Russian vs. English
8. **Commodity dependency mapping** -- Sankey/chord diagrams from Comtrade
9. **Capital flight signal detection**
10. **Historical replay / time machine** -- rewind to any past date
11. **IC source ratings** -- A-F reliability x 1-6 credibility
12. **I&W frameworks** -- structured indicators per scenario

### Validation Checklist

- [ ] Election module pre-positions monitoring for upcoming elections
- [ ] Historical analogs return relevant matches with similarity scores
- [ ] Cascade model generates plausible second-order effects
- [ ] Narrative divergence detected in test cases
- [ ] Time machine replays past state correctly

---

## Phase 13 -- Animations, Video Features & Street-Level

**Goal:** Visual polish -- particle flows, situation replay, street-level imagery.

### Steps

1. **Event ripple animations** -- CSS keyframes on new events
2. **Particle flow for shipping/air traffic** -- deck.gl TripsLayer
3. **Trade flow arrows** -- deck.gl ArcLayer
4. **Interactive timeline scrubber** with event density -- D3.js brush
5. **Conflict frontline animation** -- Turf.js concave hull with territorial shifts
6. **Daily situation replay** -- 24hr playback with controls
7. **Map animation export** -- GIF/MP4 via html2canvas + MediaRecorder
8. **Ground-level imagery via Mapillary**
9. **Public webcam layer** -- Windy.com feeds
10. **Cinematic flythrough camera** -- smooth zoom-from-space-to-street
11. **Drawing / sketching tools** -- MapLibre Draw + freehand

### Validation Checklist

- [ ] Particle flows render smoothly at 60fps
- [ ] Timeline scrubber controls all map layers
- [ ] Situation replay plays 24hr period correctly
- [ ] Export produces valid GIF/MP4
- [ ] Street-level imagery loads on click
- [ ] Flythrough camera animates smoothly

---

## Phase 14 -- Immersive & Holographic Features

**Goal:** Iron Man HUD, 3D extrusions, VR/AR modes -- the wow factor.

### Steps

1. **Iron Man HUD overlay mode** -- tactical aesthetic toggle with scan-lines, translucent panels, targeting reticle
2. **3D extruded countries** -- proportional to risk/GDP/event count
3. **3D extruded bar charts on globe**
4. **Volumetric heatmap (3D)** -- glowing 3D event density volumes
5. **Globe projection morph** -- animated transitions between Mercator, globe, polar
6. **Glassmorphism panels** -- backdrop-filter: blur(20px)
7. **Pulse beacons** at monitored locations with variable rate by alert level
8. **WebXR / VR headset mode**
9. **AR phone camera overlay**
10. **Satellite orbit pass predictor** -- CelesTrak + sgp4

### Validation Checklist

- [ ] HUD mode toggles cleanly without breaking functionality
- [ ] 3D extrusions render correctly and are interactive
- [ ] VR mode works on Quest/Vision Pro
- [ ] AR mode works on mobile device
- [ ] Projection morph animates smoothly
- [ ] All features from earlier phases still work in all modes

---

## Phase Dependency Map

```
Phase 0: Scaffolding & DB
  |
Phase 1: First Source E2E (GDELT)
  |
Phase 2: Core Data Sources (8 sources + entities)
  |
  +---> Phase 3: Map Foundation
  |       |
  |       +---> Phase 4: SIGINT Tracking
  |       |       |
  |       |       +---> Phase 10: Advanced Geospatial
  |       |       |       |
  |       |       |       +---> Phase 13: Animations & Video
  |       |       |               |
  |       |       |               +---> Phase 14: Immersive
  |       |
  |       +---> Phase 7: SPECINT + Satellite (also needs Phase 5)
  |
  +---> Phase 5: Intelligence Layer (Fusion, Briefs)
          |
          +---> Phase 6: NL Query Interface
          |
          +---> Phase 7: SPECINT + Satellite (also needs Phase 3)
          |       |
          |       +---> Phase 8: Alerts & Risk Scores
          |               |
          |               +---> Phase 9: Entity Intelligence (also needs Phase 2, 3)
          |               |
          |               +---> Phase 11: Output & Distribution (also needs Phase 6)
          |               |
          |               +---> Phase 12: Domain Modules (also needs Phase 9)
```

## Summary Table

| Phase | Name | Depends On | Key Deliverable |
|-------|------|-----------|----------------|
| 0 | Scaffolding & DB | -- | Bootable project, schema, API, deployed frontend |
| 1 | First Source E2E | 0 | GDELT -> Claude -> API -> frontend (working pipeline) |
| 2 | Core Data Sources | 1 | 8 sources, entity extraction, knowledge graph |
| 3 | Map Foundation | 2 | Interactive globe with events, layers, clustering |
| 4 | SIGINT Tracking | 3 | Live vessel + aircraft on globe |
| 5 | Intelligence Layer | 2 | Fusion, briefs, world state, red team |
| 6 | NL Query | 5 | Chat interface with sourced answers |
| 7 | SPECINT + Satellite | 3, 5 | All 18 sources, satellite vision |
| 8 | Alerts & Risk | 5, 7 | Risk scores, alerts, DuckDB analytics |
| 9 | Entity Intelligence | 2, 3, 8 | Dossiers, link analysis, ACH |
| 10 | Advanced Geospatial | 3, 4 | 3D terrain, geofencing, range rings |
| 11 | Output & Distribution | 5, 6, 8 | PDF reports, bots, webhooks, widgets |
| 12 | Domain Modules | 8, 9 | Elections, nuclear, historical analogs, time machine |
| 13 | Animations & Video | 3, 4, 10 | Particle flows, replay, street-level |
| 14 | Immersive | All above | HUD, VR/AR, 3D extrusions |
