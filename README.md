# Cerebro

**Global Intelligence Monitoring System**

Cerebro is a real-time global intelligence monitoring system that ingests data from 18 free sources across six intelligence categories, processes them through Claude API for classification, entity extraction, and cross-domain fusion, and outputs actionable intelligence briefs, risk scores, alerts, and scenario projections through a web dashboard.

## Architecture

```
                    +------------------+
                    |  18 Free Sources |
                    |  (OSINT, GEOINT, |
                    |  FININT, SIGINT, |
                    |    SPECINT)      |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Python Backend  |
                    |  (Ingestion +    |
                    |   Processing)    |
                    +--------+---------+
                             |
                 +-----------+-----------+
                 |                       |
        +--------v---------+   +---------v--------+
        |  SQLite + FTS5   |   |   Claude API     |
        |  + SpatiaLite    |   |   (Haiku/Sonnet/ |
        |  (Primary DB)    |   |    Opus)         |
        +--------+---------+   +---------+--------+
                 |                       |
                 +-----------+-----------+
                             |
                    +--------v---------+
                    |  FastAPI Server  |
                    |  (REST API)      |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Next.js on      |
                    |  Vercel          |
                    |  (Dashboard +    |
                    |   MapLibre GL)   |
                    +------------------+
```

## Tech Stack

| Component | Technology | Role |
|-----------|-----------|------|
| Backend | Python 3.12 | Ingestion, processing, API server, cron jobs |
| Primary DB | SQLite + FTS5 + SpatiaLite | Events, entities, alerts, geo queries, full-text search |
| Analytics | DuckDB | Time-series aggregations, anomaly baselines, OLAP |
| AI/ML Layer | Claude API (Haiku/Sonnet/Opus) | Classification, NER, fusion, briefs, vision, NL queries |
| Frontend | Next.js on Vercel (free tier) | Dashboard, map, timeline, NL query, briefs |
| Map | MapLibre GL | Interactive globe, layers, 3D terrain |
| Hosting | Oracle Cloud free tier / local | Python backend VM (4 OCPU, 24GB RAM) |
| Auth | Supabase (free tier) | 50k MAU, user management |
| Monitoring | Sentry (free tier) | Error tracking (5k events/mo) |

## Intelligence Categories

### OSINT -- Open Source Intelligence
- **GDELT Project** -- Global news events, 15-min updates, 100+ languages
- **ACLED** -- Armed conflict events with actors and fatalities
- **RSS Fleet** -- 50+ feeds (Reuters, AP, BBC, Al Jazeera, TASS, Xinhua)
- **Reddit** -- r/worldnews, r/geopolitics, r/economics
- **Telegram** -- Public OSINT channels

### GEOINT -- Geospatial Intelligence
- **Copernicus Sentinel-1/2** -- 10m optical + SAR imagery, 5-day revisit
- **NASA VIIRS/MODIS** -- Nighttime lights + fire detection
- **OpenStreetMap Overpass** -- Infrastructure change detection

### FININT -- Financial Intelligence
- **Yahoo Finance** -- Real-time equity/FX/commodity quotes
- **FRED** -- 800k+ economic time series from St. Louis Fed
- **World Bank / IMF / BIS** -- 190+ country macro indicators

### SIGINT -- Signals Intelligence
- **AISstream.io** -- Real-time global vessel positions (WebSocket)
- **OpenSky Network** -- All flights globally, 10-sec updates

### SPECINT -- Specialized Intelligence
- **WHO Disease Outbreak News** -- Official outbreak reports
- **ProMED-mail** -- Early outbreak warning
- **EIA** -- Oil, gas, electricity data
- **NOAA** -- Weather, severe events, ocean temps
- **UN Comtrade** -- Bilateral trade by commodity

## Key Capabilities

### AI-Powered Analysis
- **Event classification** -- Automatic categorization with severity and confidence scores
- **Entity extraction** -- Named entity recognition building a knowledge graph
- **Cross-domain fusion** -- Connecting signals across sources (vessel dark + conflict + commodity spike)
- **Intelligence briefs** -- Auto-generated daily/weekly reports with full source provenance
- **Red team analysis** -- Automatic devil's advocate on high-risk assessments
- **Historical analog matching** -- "This looks 73% like Crimea 2014"
- **Cascade modeling** -- Second-order effects prediction

### Interactive Globe
- Multi-layer intelligence globe (conflict, vessels, flights, nightlights, fires, weather, trade)
- Real-time vessel and aircraft tracking
- Satellite imagery timelapse with AI-annotated change detection
- Geofencing and area monitoring
- 3D terrain rendering
- Event density heatmaps

### Entity Intelligence
- God's Eye-style entity omnisearch across all data layers
- Palantir-style entity dossiers with relationship graphs
- Analysis of competing hypotheses (ACH) workspace
- Interactive link analysis with shortest-path detection
- Sanctions evasion path detection

### Natural Language Interface
- Ask questions in plain English, get sourced answers
- Contextual conversation memory for follow-up queries
- Proactive intelligence push (Cerebro surfaces insights unprompted)
- Ambient narration mode (live feed of system activity)

## Cost Profile

| Item | Cost |
|------|------|
| Infrastructure | $0/month (all free tiers) |
| Claude API | $50--300/month |
| **Total** | **$50--300/month** |

### Claude API Cost Breakdown

| Task | Model | Est. Cost/mo |
|------|-------|-------------|
| Event classification | Haiku (batch) | ~$15 |
| NER + entity extraction | Haiku/Sonnet (batch) | ~$30 |
| Satellite change detection | Sonnet (vision) | ~$20 |
| Cross-domain fusion | Sonnet | ~$30 |
| Intelligence briefs | Opus | ~$60 |
| NL query answering | Sonnet | ~$25 |
| Autonomous deep dive | Sonnet (tool use) | ~$25 |
| Red team analysis | Sonnet | ~$15 |
| World state compression | Opus (1x/day) | ~$3 |
| Prediction resolution | Sonnet (batch) | ~$5 |

## Project Structure

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

## Database Design

**Primary storage:** SQLite with FTS5 (full-text search) and SpatiaLite (geospatial queries)

### Core Tables
- `events` -- All ingested events with category, severity, confidence, geo coordinates
- `entities` -- Knowledge graph nodes (person, org, vessel, location)
- `entity_relations` -- Knowledge graph edges with confidence
- `alerts` -- Generated alerts with decay and corroboration tracking
- `briefs` -- Generated intelligence reports with grounding scores
- `predictions` -- Logged forecasts with outcomes for scorecard
- `narrative_arcs` -- Evolving story threads
- `world_state` -- Nightly compressed institutional memory
- `vessel_tracks` -- AIS position history
- `satellite_cache` -- Cached Sentinel-2 imagery
- `geofences` -- User-drawn monitoring polygons
- `conversation_sessions` -- NL query conversation memory
- `source_reliability` -- Per-source accuracy tracking
- `audit_log` -- Data lineage and provenance

**Analytical layer:** DuckDB for OLAP queries, reading SQLite directly

## Implementation Plan

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the full 15-phase build plan with dependency ordering and validation checklists.

### Phase Summary

| Phase | Name | Key Deliverable |
|-------|------|----------------|
| 0 | Scaffolding & DB | Bootable project, schema, API, deployed frontend |
| 1 | First Source E2E | GDELT -> Claude -> API -> frontend pipeline |
| 2 | Core Data Sources | 8 sources, entity extraction, knowledge graph |
| 3 | Map Foundation | Interactive globe with events, layers, clustering |
| 4 | SIGINT Tracking | Live vessel + aircraft on globe |
| 5 | Intelligence Layer | Fusion, briefs, world state, red team |
| 6 | NL Query | Chat interface with sourced answers |
| 7 | SPECINT + Satellite | All 18 sources, satellite vision |
| 8 | Alerts & Risk | Risk scores, alerts, DuckDB analytics |
| 9 | Entity Intelligence | Dossiers, link analysis, ACH |
| 10 | Advanced Geospatial | 3D terrain, geofencing, range rings |
| 11 | Output & Distribution | PDF reports, bots, webhooks, widgets |
| 12 | Domain Modules | Elections, nuclear, analogs, time machine |
| 13 | Animations & Video | Particle flows, replay, street-level |
| 14 | Immersive | HUD, VR/AR, 3D extrusions |

## Constraints

- **Solo builder** -- You + Claude Code, no team
- **Zero infrastructure cost** -- free tiers only, no AWS/GCP bills
- **Claude API is the only expense** -- replaces what would traditionally require 4 ML engineers and GPU clusters
- **Free data sources only** -- 18 permanently free APIs, RSS feeds, and open datasets
- **12-week timeline** -- working system with all sources, dashboard, alerts, NL query, and briefs

## License

Private project. All rights reserved.
