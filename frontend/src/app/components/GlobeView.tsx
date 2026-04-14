"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import SunCalc from "suncalc";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ───

interface GeoFeature {
  id: string;
  lat: number;
  lng: number;
  title: string;
  category: string | null;
  severity: number;
  confidence: number;
  source: string;
  timestamp: string;
  country_code: string | null;
}

interface Vessel {
  mmsi: string;
  name: string | null;
  vessel_type: string;
  flag: string | null;
  latitude: number;
  longitude: number;
  speed: number | null;
  course: number | null;
  heading: number | null;
  nav_status: string | null;
  destination: string | null;
  dark_since: string | null;
  last_seen: string;
  length: number | null;
  width: number | null;
}

interface Flight {
  icao24: string;
  callsign: string | null;
  origin_country: string;
  flight_type: string;
  latitude: number;
  longitude: number;
  altitude: number | null;
  velocity: number | null;
  heading: number | null;
  on_ground: number;
}

interface SavedView {
  id: string;
  name: string;
  description: string;
  center_lat: number;
  center_lng: number;
  zoom: number;
  bearing: number;
  pitch: number;
  layers: string[] | null;
  filters: Record<string, unknown> | null;
}

// ─── Constants ───

const CATEGORY_COLORS: Record<string, string> = {
  military: "#ef4444",
  political: "#3b82f6",
  economic: "#eab308",
  health: "#22c55e",
  environmental: "#10b981",
};

const SOURCE_LIST = ["gdelt", "rss", "yahoo_finance", "worldbank", "fred", "acled"];

const CATEGORY_LIST = ["military", "political", "economic", "health", "environmental"];

const VESSEL_TYPE_COLORS: Record<string, string> = {
  cargo: "#60a5fa",
  tanker: "#f97316",
  military: "#ef4444",
  fishing: "#22c55e",
  passenger: "#a78bfa",
  other: "#94a3b8",
};

const FLIGHT_TYPE_COLORS: Record<string, string> = {
  civilian: "#d4d4d8",
  military: "#ef4444",
  cargo: "#f59e0b",
  unknown: "#71717a",
};

function getMarkerColor(category: string | null): string {
  return CATEGORY_COLORS[category || ""] || "#71717a";
}

// ─── SVG Icon Generators for Vessels & Aircraft ───

function createVesselSVG(color: string, type: string): string {
  // Ship silhouette: cargo=box, tanker=wide, military=sleek, fishing=trawler, default=boat
  const shapes: Record<string, string> = {
    cargo: `<polygon points="16,4 28,12 28,24 4,24 4,12" fill="${color}" stroke="#18181b" stroke-width="1"/>
            <rect x="10" y="6" width="12" height="4" fill="${color}" opacity="0.6"/>`,
    tanker: `<polygon points="16,3 30,14 28,26 4,26 2,14" fill="${color}" stroke="#18181b" stroke-width="1"/>
             <ellipse cx="16" cy="16" rx="8" ry="3" fill="${color}" opacity="0.5"/>`,
    military: `<polygon points="16,2 26,10 24,28 8,28 6,10" fill="${color}" stroke="#18181b" stroke-width="1.5"/>
               <line x1="16" y1="6" x2="16" y2="14" stroke="#fff" stroke-width="1" opacity="0.5"/>`,
    fishing: `<polygon points="16,6 24,16 22,26 10,26 8,16" fill="${color}" stroke="#18181b" stroke-width="1"/>
              <line x1="16" y1="2" x2="16" y2="8" stroke="${color}" stroke-width="1.5"/>`,
    passenger: `<polygon points="16,4 26,12 26,26 6,26 6,12" fill="${color}" stroke="#18181b" stroke-width="1"/>
                <rect x="8" y="14" width="16" height="3" rx="1" fill="#fff" opacity="0.3"/>`,
  };
  const shape = shapes[type] || `<polygon points="16,4 24,12 22,26 10,26 8,12" fill="${color}" stroke="#18181b" stroke-width="1"/>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">${shape}</svg>`
  )}`;
}

function createAircraftSVG(color: string, type: string): string {
  const shapes: Record<string, string> = {
    civilian: `<polygon points="16,2 20,12 28,18 20,16 18,30 16,26 14,30 12,16 4,18 12,12" fill="${color}" stroke="#18181b" stroke-width="0.8"/>`,
    military: `<polygon points="16,2 20,10 30,16 20,14 18,28 16,24 14,28 12,14 2,16 12,10" fill="${color}" stroke="#18181b" stroke-width="1"/>
               <circle cx="16" cy="14" r="2" fill="#fff" opacity="0.4"/>`,
    cargo: `<polygon points="16,3 19,10 26,14 19,13 18,28 16,24 14,28 13,13 6,14 13,10" fill="${color}" stroke="#18181b" stroke-width="0.8"/>
            <rect x="14" y="12" width="4" height="8" rx="1" fill="${color}" opacity="0.5"/>`,
  };
  const shape = shapes[type] || shapes.civilian;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">${shape}</svg>`
  )}`;
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

// ─── Component ───

export default function GlobeView() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);

  // Filters
  const [enabledSources, setEnabledSources] = useState<Set<string>>(new Set(SOURCE_LIST));
  const [enabledCategories, setEnabledCategories] = useState<Set<string>>(new Set(CATEGORY_LIST));
  const [severityMin, setSeverityMin] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [timeRange, setTimeRange] = useState(168); // hours (7 days default)

  const [showVessels, setShowVessels] = useState(true);
  const [showFlights, setShowFlights] = useState(true);

  // Advanced overlay toggles
  const [showMaritimeZones, setShowMaritimeZones] = useState(false);
  const [showPredictions, setShowPredictions] = useState(false);
  const [showTerrain3D, setShowTerrain3D] = useState(false);
  const [showDensityGrid, setShowDensityGrid] = useState(false);
  const [heatmapCategory, setHeatmapCategory] = useState<string>("all");

  // Timelapse & swipe comparator
  const [showTimelapse, setShowTimelapse] = useState(false);
  const [timelapseDay, setTimelapseDay] = useState(0); // 0 = today, -N = N days ago
  const [timelapseRange] = useState(30); // total days available
  const [showSatelliteSwipe, setShowSatelliteSwipe] = useState(false);
  const [swipePosition, setSwipePosition] = useState(50); // percentage 0-100
  // ─── Phase 13 state ───
  const [showWebcams, setShowWebcams] = useState(false);
  const [showTradeFlows, setShowTradeFlows] = useState(false);
  const [showFrontlines, setShowFrontlines] = useState(false);
  const [showStreetImagery, setShowStreetImagery] = useState(false);
  const [showAnnotations, setShowAnnotations] = useState(false);
  const [drawMode, setDrawMode] = useState<string | null>(null); // marker/line/polygon/freehand/measure
  const [measurePoints, setMeasurePoints] = useState<[number, number][]>([]);
  const [measureResult, setMeasureResult] = useState<{ distance_km: number; bearing: number } | null>(null);
  const [showReplayControls, setShowReplayControls] = useState(false);
  const [replayHour, setReplayHour] = useState(0); // 0-23
  const [replayPlaying, setReplayPlaying] = useState(false);
  const replayTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const [tradeFlowType, setTradeFlowType] = useState("all");
  const [webcamData, setWebcamData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [tradeFlowData, setTradeFlowData] = useState<{ flows: Array<{ origin: number[]; destination: number[]; color: number[]; width: number; flow_type: string; commodity: string; origin_country: string; dest_country: string; volume_usd: number }> } | null>(null);
  const [frontlineData, setFrontlineData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [annotationData, setAnnotationData] = useState<GeoJSON.FeatureCollection | null>(null);

  // Split-screen dual view
  const [showSplitScreen, setShowSplitScreen] = useState(false);
  const splitMapContainer = useRef<HTMLDivElement>(null);
  const splitMapRef = useRef<maplibregl.Map | null>(null);

  // Keyboard shortcuts
  const [showShortcutHelp, setShowShortcutHelp] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  // ─── Phase 14 state ───
  const [showHudMode, setShowHudMode] = useState(false);
  const [showSatelliteOrbits, setShowSatelliteOrbits] = useState(false);
  const [showPulseBeacons, setShowPulseBeacons] = useState(false);
  const [showGlassmorphism, setShowGlassmorphism] = useState(false);
  const [showExtrudedCountries, setShowExtrudedCountries] = useState(false);
  const [extrusionMetric, setExtrusionMetric] = useState("risk_score");
  const [projectionMode, setProjectionMode] = useState<"globe" | "mercator">("globe");
  const [showWebXR, setShowWebXR] = useState(false);
  const [showAR, setShowAR] = useState(false);
  const [orbitData, setOrbitData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [beaconData, setBeaconData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [extrusionData, setExtrusionData] = useState<{ country_code: string; metric_value: number; normalized: number }[] | null>(null);

  // ─── Phase 15 state ───
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [cmdQuery, setCmdQuery] = useState("");
  const [showPiP, setShowPiP] = useState(false);
  const pipMapContainer = useRef<HTMLDivElement>(null);
  const pipMapRef = useRef<maplibregl.Map | null>(null);
  const [pipDragging, setPipDragging] = useState(false);
  const [pipPos, setPipPos] = useState({ x: 20, y: 20 });
  const pipDragStart = useRef({ x: 0, y: 0 });
  const [showPhotoPins, setShowPhotoPins] = useState(false);
  const [photoPinData, setPhotoPinData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [sunSimTime, setSunSimTime] = useState<Date | null>(null);
  const [showSunSim, setShowSunSim] = useState(false);

  // ─── Visual effects state ───
  const [showParticleFlow, setShowParticleFlow] = useState(false);
  const [particleTime, setParticleTime] = useState(0);
  const particleAnimFrame = useRef<number | null>(null);
  const [showClusterBreathing, setShowClusterBreathing] = useState(false);
  const clusterBreathFrame = useRef<number | null>(null);
  const [shockwaves, setShockwaves] = useState<{ id: string; x: number; y: number; time: number }[]>([]);
  const [animatedRiskScore, setAnimatedRiskScore] = useState<number | null>(null);
  const prevRiskScore = useRef<number | null>(null);
  const [showRiskOdometer, setShowRiskOdometer] = useState(true);

  // ─── Phase 16 state ───
  const [showDiseaseSpread, setShowDiseaseSpread] = useState(false);
  const [diseaseDay, setDiseaseDay] = useState(0);
  const [diseaseOutbreaks, setDiseaseOutbreaks] = useState<{ id: string; disease: string }[]>([]);
  const [selectedOutbreak, setSelectedOutbreak] = useState<string | null>(null);
  const diseaseAnimFrame = useRef<number | null>(null);
  const [diseaseAnimPlaying, setDiseaseAnimPlaying] = useState(false);

  const [showStormTracks, setShowStormTracks] = useState(false);
  const [stormList, setStormList] = useState<{ id: string; storm_name: string; category: number }[]>([]);

  const [showNewsTicker, setShowNewsTicker] = useState(false);
  const [tickerItems, setTickerItems] = useState<{ title: string; severity: number; timestamp: string }[]>([]);

  const [isRecordingTimelapse, setIsRecordingTimelapse] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunks = useRef<Blob[]>([]);

  const [showDocumentaryMode, setShowDocumentaryMode] = useState(false);
  const [documentaryProgressions, setDocumentaryProgressions] = useState<{ id: string; conflict_name: string }[]>([]);
  const [selectedProgression, setSelectedProgression] = useState<string | null>(null);
  const [documentarySteps, setDocumentarySteps] = useState<{ step_number: number; title: string; narration: string; center_lat: number; center_lng: number; zoom: number; bearing: number; pitch: number }[]>([]);
  const [currentDocStep, setCurrentDocStep] = useState(0);

  const [showVolumetricHeat, setShowVolumetricHeat] = useState(false);
  const [show3DBarCharts, setShow3DBarCharts] = useState(false);

  const [gestureMode, setGestureMode] = useState<"standard" | "tactical">("standard");

  // ─── Section 18: Interactive object visualization state ───
  const [showRadarCoverage, setShowRadarCoverage] = useState(false);
  const [radarData, setRadarData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [showDroneActivity, setShowDroneActivity] = useState(false);
  const [droneData, setDroneData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [showFlightReplay, setShowFlightReplay] = useState(false);
  const [replayTrack, setReplayTrack] = useState<{ lat: number; lng: number }[]>([]);
  const [replayProgress, setReplayProgress] = useState(0);
  const replayAnimFrame = useRef<number | null>(null);
  const vesselIconsLoaded = useRef(false);
  const flightIconsLoaded = useRef(false);

  // ─── Missile trajectories & weapons range rings ───
  const [showMissileArcs, setShowMissileArcs] = useState(false);
  const [missileTrajectoryData, setMissileTrajectoryData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [missileOrigin, setMissileOrigin] = useState<[number, number]>([51.4, 35.7]); // Tehran
  const [missileTarget, setMissileTarget] = useState<[number, number]>([32.1, 34.8]); // Tel Aviv
  const [missileType, setMissileType] = useState<"ballistic" | "cruise">("ballistic");

  const [showRangeRings, setShowRangeRings] = useState(false);
  const [rangeRingData, setRangeRingData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [weaponsList, setWeaponsList] = useState<{ id: string; name: string; range_km: number }[]>([]);
  const [selectedWeaponId, setSelectedWeaponId] = useState<string>("");
  const [rangeRingCenter, setRangeRingCenter] = useState<[number, number]>([51.4, 35.7]);

  // ─── Timelapse auto-play ───
  const [accumPlaying, setAccumPlaying] = useState(false);
  const accumIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Cinematic flythrough multi-waypoint ───
  const [flythroughActive, setFlythroughActive] = useState(false);

  // Data
  const [features, setFeatures] = useState<GeoFeature[]>([]);
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [flights, setFlights] = useState<Flight[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<GeoFeature | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<Vessel | null>(null);
  const [vesselTrack, setVesselTrack] = useState<{lat: number; lng: number}[]>([]);
  const [featureCount, setFeatureCount] = useState(0);
  const [loading, setLoading] = useState(false);

  // Overlay data
  const [maritimeZones, setMaritimeZones] = useState<GeoJSON.FeatureCollection | null>(null);
  const [predictivePositions, setPredictivePositions] = useState<GeoJSON.FeatureCollection | null>(null);

  // Saved views
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [showViewPanel, setShowViewPanel] = useState(false);

  // ─── Fetch events for viewport ───

  const fetchEvents = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;

    const bounds = map.getBounds();
    const params = new URLSearchParams({
      west: String(bounds.getWest()),
      south: String(bounds.getSouth()),
      east: String(bounds.getEast()),
      north: String(bounds.getNorth()),
      limit: "3000",
    });

    if (severityMin > 0) params.set("severity_min", String(severityMin));

    // Time filter
    if (timeRange < 8760) {
      const start = new Date(Date.now() - timeRange * 3600000).toISOString();
      params.set("time_start", start);
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/events/geo?${params}`);
      if (res.ok) {
        const data = await res.json();
        setFeatures(data.features);
        setFeatureCount(data.total);
      }
    } catch (err) {
      console.error("Geo fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [severityMin, timeRange]);

  // ─── Fetch vessels and flights ───

  const fetchVesselsAndFlights = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    const bounds = map.getBounds();
    const bbox = `west=${bounds.getWest()}&south=${bounds.getSouth()}&east=${bounds.getEast()}&north=${bounds.getNorth()}`;

    try {
      const [vRes, fRes] = await Promise.all([
        showVessels ? fetch(`${API_URL}/api/vessels?${bbox}&limit=3000`) : Promise.resolve(null),
        showFlights ? fetch(`${API_URL}/api/flights?${bbox}&limit=5000`) : Promise.resolve(null),
      ]);
      if (vRes?.ok) {
        const vData = await vRes.json();
        setVessels(vData.vessels || []);
      }
      if (fRes?.ok) {
        const fData = await fRes.json();
        setFlights(fData.flights || []);
      }
    } catch (err) {
      console.error("Vessel/flight fetch error:", err);
    }
  }, [showVessels, showFlights]);

  async function loadVesselTrack(mmsi: string) {
    try {
      const res = await fetch(`${API_URL}/api/vessels/${mmsi}/track?hours=24`);
      if (res.ok) {
        const data = await res.json();
        setVesselTrack(data.points.map((p: { latitude: number; longitude: number }) => ({
          lat: p.latitude,
          lng: p.longitude,
        })));
      }
    } catch (err) {
      console.error("Track fetch error:", err);
    }
  }

  // ─── Fetch overlay layers ───

  const fetchMaritimeZones = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/maritime/zones/geojson`);
      if (res.ok) {
        const data = await res.json();
        setMaritimeZones(data);
      }
    } catch (err) {
      console.error("Maritime zones fetch error:", err);
    }
  }, []);

  const fetchPredictions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/predictive/geojson`);
      if (res.ok) {
        const data = await res.json();
        setPredictivePositions(data);
      }
    } catch (err) {
      console.error("Predictions fetch error:", err);
    }
  }, []);

  // ─── Initialize Map ───

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        name: "Cerebro Dark",
        sources: {
          "osm-tiles": {
            type: "raster",
            tiles: [
              "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
              "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
              "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
            ],
            tileSize: 256,
            attribution: '&copy; <a href="https://carto.com">CARTO</a> &copy; <a href="https://www.openstreetmap.org">OSM</a>',
          },
        },
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": "#0a0a0a" },
          },
          {
            id: "osm",
            type: "raster",
            source: "osm-tiles",
            minzoom: 0,
            maxzoom: 19,
          },
        ],
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      },
      center: [20, 30],
      zoom: 2,
      maxPitch: 60,
      // Globe projection (MapLibre v4+ feature, not yet in all TS defs)
      ...(({ projection: { type: "globe" } }) as Record<string, unknown>),
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("load", () => {
      // Add GeoJSON sources for events
      map.addSource("events", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterMaxZoom: 12,
        clusterRadius: 50,
      });

      // Heatmap source (non-clustered)
      map.addSource("events-heat", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // ── Cluster circles ──
      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "events",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": [
            "step", ["get", "point_count"],
            "#3b82f6", 10,
            "#eab308", 50,
            "#ef4444",
          ],
          "circle-radius": [
            "step", ["get", "point_count"],
            15, 10,
            20, 50,
            28,
          ],
          "circle-opacity": 0.8,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#18181b",
        },
      });

      // ── Cluster count labels ──
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "events",
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 12,
        },
        paint: {
          "text-color": "#ffffff",
        },
      });

      // ── Individual event markers ──
      map.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: "events",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": [
            "interpolate", ["linear"], ["get", "severity"],
            0, 4,
            50, 7,
            100, 12,
          ],
          "circle-opacity": 0.85,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#18181b",
        },
      });

      // ── Heatmap layer ──
      map.addLayer({
        id: "heatmap",
        type: "heatmap",
        source: "events-heat",
        maxzoom: 10,
        paint: {
          "heatmap-weight": [
            "interpolate", ["linear"], ["get", "severity"],
            0, 0.1,
            100, 1,
          ],
          "heatmap-intensity": [
            "interpolate", ["linear"], ["zoom"],
            0, 0.5,
            10, 3,
          ],
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(0,0,0,0)",
            0.2, "#1e3a5f",
            0.4, "#2563eb",
            0.6, "#eab308",
            0.8, "#f97316",
            1, "#ef4444",
          ],
          "heatmap-radius": [
            "interpolate", ["linear"], ["zoom"],
            0, 15,
            10, 30,
          ],
          "heatmap-opacity": 0.6,
        },
        layout: {
          visibility: "none",
        },
      });

      // ── Vessel layer ──
      map.addSource("vessels", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Load vessel type SVG icons
      const vesselTypes = ["cargo", "tanker", "military", "fishing", "passenger", "other"];
      const vesselColors: Record<string, string> = { cargo: "#60a5fa", tanker: "#f97316", military: "#ef4444", fishing: "#22c55e", passenger: "#a78bfa", other: "#94a3b8" };
      for (const vt of vesselTypes) {
        const img = new Image(32, 32);
        img.src = createVesselSVG(vesselColors[vt] || "#94a3b8", vt);
        img.onload = () => { if (!map.hasImage(`vessel-${vt}`)) map.addImage(`vessel-${vt}`, img); };
      }
      // Dark vessel icon
      const darkImg = new Image(32, 32);
      darkImg.src = createVesselSVG("#ef4444", "military");
      darkImg.onload = () => { if (!map.hasImage("vessel-dark")) map.addImage("vessel-dark", darkImg); };
      vesselIconsLoaded.current = true;

      map.addLayer({
        id: "vessel-points",
        type: "symbol",
        source: "vessels",
        layout: {
          "icon-image": ["case",
            ["has", "dark_since"], "vessel-dark",
            ["concat", "vessel-", ["get", "vessel_type"]],
          ],
          "icon-size": 0.6,
          "icon-rotate": ["coalesce", ["get", "heading"], ["get", "course"], 0],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
        },
      });

      // ── Vessel track (trail) layer ──
      map.addSource("vessel-track", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "vessel-track-line",
        type: "line",
        source: "vessel-track",
        paint: {
          "line-color": "#60a5fa",
          "line-width": 2,
          "line-opacity": 0.6,
          "line-dasharray": [2, 2],
        },
      });

      // ── Flight layer ──
      map.addSource("flights", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Load aircraft type SVG icons
      const flightTypes = ["civilian", "military", "cargo", "unknown"];
      const flightColors: Record<string, string> = { civilian: "#d4d4d8", military: "#ef4444", cargo: "#f59e0b", unknown: "#71717a" };
      for (const ft of flightTypes) {
        const aImg = new Image(32, 32);
        aImg.src = createAircraftSVG(flightColors[ft] || "#d4d4d8", ft);
        aImg.onload = () => { if (!map.hasImage(`aircraft-${ft}`)) map.addImage(`aircraft-${ft}`, aImg); };
      }
      flightIconsLoaded.current = true;

      map.addLayer({
        id: "flight-points",
        type: "symbol",
        source: "flights",
        layout: {
          "icon-image": ["concat", "aircraft-", ["get", "flight_type"]],
          "icon-size": 0.5,
          "icon-rotate": ["coalesce", ["get", "heading"], 0],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
        },
      });

      // ── Maritime zones overlay ──
      map.addSource("maritime-zones", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "maritime-zones-fill",
        type: "fill",
        source: "maritime-zones",
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": ["get", "fill_opacity"],
        },
        layout: { visibility: "none" },
      });

      map.addLayer({
        id: "maritime-zones-line",
        type: "line",
        source: "maritime-zones",
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["get", "stroke_width"],
          "line-opacity": 0.6,
        },
        layout: { visibility: "none" },
      });

      map.addLayer({
        id: "maritime-zones-label",
        type: "symbol",
        source: "maritime-zones",
        layout: {
          "text-field": ["get", "name"],
          "text-size": 10,
          visibility: "none",
        },
        paint: {
          "text-color": "#94a3b8",
          "text-halo-color": "#18181b",
          "text-halo-width": 1,
        },
      });

      // ── Predictive positions overlay ──
      map.addSource("predictions", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "prediction-circles",
        type: "circle",
        source: "predictions",
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": [
            "interpolate", ["linear"], ["get", "probability"],
            0, 6,
            0.5, 10,
            1.0, 16,
          ],
          "circle-opacity": 0.4,
          "circle-stroke-width": 2,
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-opacity": 0.8,
        },
        layout: { visibility: "none" },
      });

      // ── Density grid overlay ──
      map.addSource("density-grid", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "density-grid-fill",
        type: "circle",
        source: "density-grid",
        paint: {
          "circle-color": [
            "interpolate", ["linear"], ["get", "intensity"],
            0, "#1e3a5f",
            5, "#eab308",
            15, "#ef4444",
          ],
          "circle-radius": [
            "interpolate", ["linear"], ["get", "count"],
            1, 8,
            10, 18,
            50, 30,
          ],
          "circle-opacity": 0.35,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#f97316",
          "circle-stroke-opacity": 0.5,
        },
        layout: { visibility: "none" },
      });

      // ── Satellite imagery layer (for swipe comparator) ──
      map.addSource("satellite-imagery", {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        maxzoom: 18,
      });

      map.addLayer({
        id: "satellite-layer",
        type: "raster",
        source: "satellite-imagery",
        layout: { visibility: "none" },
        paint: { "raster-opacity": 1.0 },
      }, "osm"); // Insert below the dark basemap

      // ── Click handlers ──

      // Click on cluster -> zoom in
      map.on("click", "clusters", (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ["clusters"] });
        if (!features.length) return;
        const clusterId = features[0].properties?.cluster_id;
        const source = map.getSource("events") as maplibregl.GeoJSONSource;
        source.getClusterExpansionZoom(clusterId).then((zoom) => {
          const geometry = features[0].geometry;
          if (geometry.type === "Point") {
            map.easeTo({
              center: geometry.coordinates as [number, number],
              zoom: zoom,
            });
          }
        });
      });

      // Click on event marker -> show popup
      map.on("click", "unclustered-point", (e) => {
        if (!e.features?.length) return;
        const props = e.features[0].properties;
        if (!props) return;
        const geometry = e.features[0].geometry;
        if (geometry.type !== "Point") return;

        const coords = geometry.coordinates.slice() as [number, number];
        const cat = props.category || "unclassified";
        const color = CATEGORY_COLORS[cat] || "#71717a";

        if (popupRef.current) popupRef.current.remove();

        const popup = new maplibregl.Popup({ closeOnClick: true, maxWidth: "320px" })
          .setLngLat(coords)
          .setHTML(`
            <div style="font-family: system-ui; color: #e4e4e7; background: #18181b; padding: 12px; border-radius: 8px; max-width: 300px;">
              <div style="display:flex; gap:6px; align-items:center; margin-bottom:6px;">
                <span style="background:${color}33; color:${color}; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600;">
                  ${cat.toUpperCase()}
                </span>
                <span style="font-size:10px; color:#71717a;">${props.source}</span>
                <span style="font-size:10px; color:#71717a;">${props.country_code || ""}</span>
              </div>
              <div style="font-size:13px; font-weight:500; margin-bottom:4px;">${props.title}</div>
              <div style="display:flex; gap:12px; font-size:11px; color:#a1a1aa;">
                <span>Severity: <b style="color:${props.severity >= 70 ? "#ef4444" : props.severity >= 40 ? "#eab308" : "#a1a1aa"}">${Math.round(props.severity)}</b></span>
                <span>Conf: ${Math.round(props.confidence * 100)}%</span>
                <span>${formatTime(props.timestamp)}</span>
              </div>
            </div>
          `)
          .addTo(map);

        popupRef.current = popup;
      });

      // Click on vessel marker -> show popup
      map.on("click", "vessel-points", (e) => {
        if (!e.features?.length) return;
        const props = e.features[0].properties;
        if (!props) return;
        const geometry = e.features[0].geometry;
        if (geometry.type !== "Point") return;
        const coords = geometry.coordinates.slice() as [number, number];
        const color = props.color || "#94a3b8";

        if (popupRef.current) popupRef.current.remove();
        const vesselName = props.name || "Unknown Vessel";
        const imgUrl = `https://photos.marinetraffic.com/ais/showphoto.aspx?mmsi=${props.mmsi}&size=thumb`;
        const mtLink = `https://www.marinetraffic.com/en/ais/details/ships/mmsi:${props.mmsi}`;
        const popup = new maplibregl.Popup({ closeOnClick: true, maxWidth: "340px" })
          .setLngLat(coords)
          .setHTML(`
            <div style="font-family: system-ui; color: #e4e4e7; background: #18181b; padding: 0; border-radius: 8px; max-width: 320px; overflow:hidden;">
              <div style="height:100px; background:#27272a; display:flex; align-items:center; justify-content:center; position:relative;">
                <img src="${imgUrl}" alt="${vesselName}" style="width:100%; height:100%; object-fit:cover;"
                  onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
                <div style="display:none; align-items:center; justify-content:center; width:100%; height:100%; position:absolute; top:0; left:0;">
                  <span style="font-size:36px;">🚢</span>
                </div>
                <div style="position:absolute; bottom:4px; right:4px; background:${color}; color:#fff; font-size:9px; padding:1px 6px; border-radius:3px; font-weight:600;">
                  ${(props.vessel_type || "unknown").toUpperCase()}
                </div>
              </div>
              <div style="padding:10px;">
                <div style="display:flex; gap:6px; align-items:center; margin-bottom:4px;">
                  <span style="font-size:10px; color:#71717a;">MMSI: ${props.mmsi}</span>
                  ${props.flag ? `<span style="font-size:10px; color:#71717a;">🏴 ${props.flag}</span>` : ""}
                  ${props.length ? `<span style="font-size:10px; color:#71717a;">${props.length}×${props.width || "?"}m</span>` : ""}
                </div>
                <div style="font-size:14px; font-weight:600; margin-bottom:6px;">${vesselName}</div>
                <div style="display:flex; gap:10px; font-size:11px; color:#a1a1aa; margin-bottom:6px;">
                  <span>⚡ ${props.speed != null ? Number(props.speed).toFixed(1) + " kn" : "N/A"}</span>
                  <span>🧭 ${props.course != null ? Math.round(Number(props.course)) + "°" : "N/A"}</span>
                  ${props.destination ? `<span>→ ${props.destination}</span>` : ""}
                </div>
                ${props.dark_since ? `<div style="color:#ef4444; font-size:11px; margin-bottom:4px;">⚠ AIS dark since ${formatTime(props.dark_since)}</div>` : ""}
                <div style="display:flex; gap:8px; align-items:center;">
                  <a href="${mtLink}" target="_blank" rel="noopener" style="font-size:10px; color:#60a5fa; text-decoration:none;">
                    View on MarineTraffic →
                  </a>
                  <span id="replay-btn-${props.mmsi}" style="font-size:10px; color:#22c55e; cursor:pointer; text-decoration:underline;">
                    ▶ Replay Track
                  </span>
                </div>
              </div>
            </div>
          `)
          .addTo(map);
        popupRef.current = popup;

        // Wire "Replay Track" button after popup is in DOM
        setTimeout(() => {
          const replayBtn = document.getElementById(`replay-btn-${props.mmsi}`);
          if (replayBtn) {
            replayBtn.addEventListener("click", () => {
              const mmsi = props.mmsi;
              const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
              fetch(`${API}/api/vessels/${mmsi}/track`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                  if (data?.track?.length >= 2) {
                    setReplayTrack(data.track.map((p: any) => ({ lat: p.lat ?? p.latitude, lng: p.lng ?? p.longitude })));
                    setShowFlightReplay(true);
                    popup.remove();
                  }
                })
                .catch(() => {});
            });
          }
        }, 50);
      });

      // Click on flight marker -> show popup
      map.on("click", "flight-points", (e) => {
        if (!e.features?.length) return;
        const props = e.features[0].properties;
        if (!props) return;
        const geometry = e.features[0].geometry;
        if (geometry.type !== "Point") return;
        const coords = geometry.coordinates.slice() as [number, number];
        const color = props.color || "#d4d4d8";

        if (popupRef.current) popupRef.current.remove();
        const popup = new maplibregl.Popup({ closeOnClick: true, maxWidth: "300px" })
          .setLngLat(coords)
          .setHTML(`
            <div style="font-family: system-ui; color: #e4e4e7; background: #18181b; padding: 12px; border-radius: 8px;">
              <div style="display:flex; gap:6px; align-items:center; margin-bottom:6px;">
                <span style="background:${color}33; color:${color}; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600;">
                  ${(props.flight_type || "unknown").toUpperCase()}
                </span>
                <span style="font-size:10px; color:#71717a;">${props.origin_country || ""}</span>
              </div>
              <div style="font-size:13px; font-weight:500; margin-bottom:4px;">${props.callsign || props.icao24}</div>
              <div style="display:flex; gap:12px; font-size:11px; color:#a1a1aa;">
                <span>Alt: ${props.altitude != null ? Math.round(props.altitude) + "m" : "N/A"}</span>
                <span>Speed: ${props.velocity != null ? Math.round(props.velocity) + " m/s" : "N/A"}</span>
                <span>Hdg: ${props.heading != null ? Math.round(props.heading) + "°" : "N/A"}</span>
              </div>
            </div>
          `)
          .addTo(map);
        popupRef.current = popup;
      });

      // Cursor changes
      map.on("mouseenter", "clusters", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "clusters", () => { map.getCanvas().style.cursor = ""; });
      map.on("mouseenter", "unclustered-point", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "unclustered-point", () => { map.getCanvas().style.cursor = ""; });
      map.on("mouseenter", "vessel-points", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "vessel-points", () => { map.getCanvas().style.cursor = ""; });
      map.on("mouseenter", "flight-points", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "flight-points", () => { map.getCanvas().style.cursor = ""; });

      mapRef.current = map;
    });

    // Fetch on viewport change (debounced)
    let timeout: ReturnType<typeof setTimeout>;
    map.on("moveend", () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        if (mapRef.current) {
          fetchEvents();
          fetchVesselsAndFlights();
        }
      }, 300);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ─── Update map data when features or filters change ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Filter features by enabled sources and categories
    const filtered = features.filter(
      (f) =>
        enabledSources.has(f.source) &&
        (f.category ? enabledCategories.has(f.category) : true)
    );

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: filtered.map((f) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [f.lng, f.lat],
        },
        properties: {
          id: f.id,
          title: f.title,
          category: f.category || "unclassified",
          severity: f.severity,
          confidence: f.confidence,
          source: f.source,
          timestamp: f.timestamp,
          country_code: f.country_code || "",
          color: getMarkerColor(f.category),
        },
      })),
    };

    const eventsSource = map.getSource("events") as maplibregl.GeoJSONSource;
    if (eventsSource) eventsSource.setData(geojson);

    const heatSource = map.getSource("events-heat") as maplibregl.GeoJSONSource;
    if (heatSource) heatSource.setData(geojson);
  }, [features, enabledSources, enabledCategories]);

  // ─── Update vessel/flight layers ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Vessels
    const vesselGeoJson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: (showVessels ? vessels : []).map((v) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [v.longitude, v.latitude] },
        properties: {
          mmsi: v.mmsi,
          name: v.name || "Unknown",
          vessel_type: v.vessel_type,
          flag: v.flag,
          speed: v.speed,
          course: v.course,
          heading: v.heading,
          destination: v.destination,
          dark_since: v.dark_since,
          length: v.length,
          width: v.width,
          color: v.dark_since ? "#ef4444" : (VESSEL_TYPE_COLORS[v.vessel_type] || "#94a3b8"),
        },
      })),
    };
    const vSrc = map.getSource("vessels") as maplibregl.GeoJSONSource;
    if (vSrc) vSrc.setData(vesselGeoJson);

    // Flights
    const flightGeoJson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: (showFlights ? flights : []).filter(f => !f.on_ground).map((f) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [f.longitude, f.latitude] },
        properties: {
          icao24: f.icao24,
          callsign: f.callsign,
          origin_country: f.origin_country,
          flight_type: f.flight_type,
          altitude: f.altitude,
          velocity: f.velocity,
          heading: f.heading,
          color: FLIGHT_TYPE_COLORS[f.flight_type] || "#d4d4d8",
        },
      })),
    };
    const fSrc = map.getSource("flights") as maplibregl.GeoJSONSource;
    if (fSrc) fSrc.setData(flightGeoJson);
  }, [vessels, flights, showVessels, showFlights]);

  // ─── Update vessel track trail ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const trackGeoJson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: vesselTrack.length >= 2 ? [{
        type: "Feature" as const,
        geometry: {
          type: "LineString" as const,
          coordinates: vesselTrack.map(p => [p.lng, p.lat]),
        },
        properties: {},
      }] : [],
    };
    const tSrc = map.getSource("vessel-track") as maplibregl.GeoJSONSource;
    if (tSrc) tSrc.setData(trackGeoJson);
  }, [vesselTrack]);

  // ─── Toggle heatmap visibility ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    map.setLayoutProperty("heatmap", "visibility", showHeatmap ? "visible" : "none");
  }, [showHeatmap]);

  // ─── Toggle maritime zones layer ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const vis = showMaritimeZones ? "visible" : "none";
    map.setLayoutProperty("maritime-zones-fill", "visibility", vis);
    map.setLayoutProperty("maritime-zones-line", "visibility", vis);
    map.setLayoutProperty("maritime-zones-label", "visibility", vis);
    if (showMaritimeZones && !maritimeZones) fetchMaritimeZones();
  }, [showMaritimeZones]);

  // ─── Update maritime zones data ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !maritimeZones) return;
    const src = map.getSource("maritime-zones") as maplibregl.GeoJSONSource;
    if (src) src.setData(maritimeZones);
  }, [maritimeZones]);

  // ─── Toggle predictions layer ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    map.setLayoutProperty("prediction-circles", "visibility", showPredictions ? "visible" : "none");
    if (showPredictions && !predictivePositions) fetchPredictions();
  }, [showPredictions]);

  // ─── Update predictions data ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !predictivePositions) return;
    const src = map.getSource("predictions") as maplibregl.GeoJSONSource;
    if (src) src.setData(predictivePositions);
  }, [predictivePositions]);

  // ─── Toggle density grid ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    map.setLayoutProperty("density-grid-fill", "visibility", showDensityGrid ? "visible" : "none");

    if (showDensityGrid) {
      // Fetch density grid data
      const catParam = heatmapCategory !== "all" ? `&category=${heatmapCategory}` : "";
      fetch(`${API_URL}/api/clusters/density?days=${Math.floor(timeRange / 24) || 7}${catParam}`)
        .then(r => r.json())
        .then(data => {
          const geojson: GeoJSON.FeatureCollection = {
            type: "FeatureCollection",
            features: (data.cells || []).map((c: { lat: number; lng: number; count: number; avg_severity: number; intensity: number }) => ({
              type: "Feature" as const,
              geometry: { type: "Point" as const, coordinates: [c.lng, c.lat] },
              properties: { count: c.count, avg_severity: c.avg_severity, intensity: c.intensity },
            })),
          };
          const src = map.getSource("density-grid") as maplibregl.GeoJSONSource;
          if (src) src.setData(geojson);
        })
        .catch(console.error);
    }
  }, [showDensityGrid, timeRange, heatmapCategory]);

  // ─── Toggle 3D terrain ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showTerrain3D) {
      if (!map.getSource("terrain-dem")) {
        map.addSource("terrain-dem", {
          type: "raster-dem",
          tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
          tileSize: 256,
          encoding: "terrarium",
          maxzoom: 14,
        });
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (map as any).setTerrain({ source: "terrain-dem", exaggeration: 1.5 });
      map.setPitch(45);
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (map as any).setTerrain(null);
      map.setPitch(0);
    }
  }, [showTerrain3D]);

  // ─── Historical imagery timelapse ───

  useEffect(() => {
    if (!showTimelapse) return;
    // When timelapse is active, filter events by the selected day
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const targetDate = new Date(Date.now() + timelapseDay * 86400000);
    const dayStart = new Date(targetDate);
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(targetDate);
    dayEnd.setHours(23, 59, 59, 999);

    // Filter the already-loaded features to only show events from that day
    const dayFeatures = features.filter((f) => {
      const ts = new Date(f.timestamp).getTime();
      return ts >= dayStart.getTime() && ts <= dayEnd.getTime();
    });

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: dayFeatures.map((f) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [f.lng, f.lat] },
        properties: {
          id: f.id, title: f.title, category: f.category || "unclassified",
          severity: f.severity, confidence: f.confidence, source: f.source,
          timestamp: f.timestamp, country_code: f.country_code || "",
          color: getMarkerColor(f.category),
        },
      })),
    };

    const evtSrc = map.getSource("events") as maplibregl.GeoJSONSource;
    if (evtSrc) evtSrc.setData(geojson);
    const heatSrc = map.getSource("events-heat") as maplibregl.GeoJSONSource;
    if (heatSrc) heatSrc.setData(geojson);
  }, [showTimelapse, timelapseDay, features]);

  // ─── Satellite swipe comparator ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showSatelliteSwipe) {
      map.setLayoutProperty("satellite-layer", "visibility", "visible");
    } else {
      map.setLayoutProperty("satellite-layer", "visibility", "none");
    }
  }, [showSatelliteSwipe]);

  // Satellite swipe — blend opacity based on slider position
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !showSatelliteSwipe) return;

    // Satellite opacity: 100% at swipe=0 (full satellite), 0% at swipe=100 (full dark)
    const satOpacity = 1.0 - swipePosition / 100;
    map.setPaintProperty("satellite-layer", "raster-opacity", satOpacity);
    map.triggerRepaint();
  }, [swipePosition, showSatelliteSwipe]);

  // ─── Refetch on filter change ───

  useEffect(() => {
    if (mapRef.current) {
      fetchEvents();
      fetchVesselsAndFlights();
    }
  }, [fetchEvents, fetchVesselsAndFlights]);

  // ─── Saved views ───

  async function loadSavedViews() {
    try {
      const res = await fetch(`${API_URL}/api/views`);
      if (res.ok) {
        const data = await res.json();
        setSavedViews(data.views);
      }
    } catch (err) {
      console.error("Failed to load views:", err);
    }
  }

  async function saveCurrentView() {
    const map = mapRef.current;
    if (!map) return;
    const center = map.getCenter();
    const name = prompt("View name:");
    if (!name) return;

    try {
      await fetch(`${API_URL}/api/views`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          center_lat: center.lat,
          center_lng: center.lng,
          zoom: map.getZoom(),
          bearing: map.getBearing(),
          pitch: map.getPitch(),
          layers: Array.from(enabledSources),
          filters: {
            categories: Array.from(enabledCategories),
            severity_min: severityMin,
            time_range: timeRange,
          },
        }),
      });
      loadSavedViews();
    } catch (err) {
      console.error("Failed to save view:", err);
    }
  }

  function restoreView(view: SavedView) {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({
      center: [view.center_lng, view.center_lat],
      zoom: view.zoom,
      bearing: view.bearing,
      pitch: view.pitch,
      duration: 1500,
    });
    if (view.layers) {
      setEnabledSources(new Set(view.layers));
    }
    if (view.filters) {
      const f = view.filters as Record<string, unknown>;
      if (f.categories) setEnabledCategories(new Set(f.categories as string[]));
      if (f.severity_min) setSeverityMin(f.severity_min as number);
      if (f.time_range) setTimeRange(f.time_range as number);
    }
  }

  // Toggle helpers
  function toggleSource(source: string) {
    setEnabledSources((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }

  function toggleCategory(cat: string) {
    setEnabledCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  // ─── Phase 13: Webcam layer ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showWebcams && !webcamData) {
      fetch(`${API_URL}/api/webcams/geojson`)
        .then(r => r.json())
        .then(data => setWebcamData(data))
        .catch(console.error);
    }

    // Add source/layer if needed
    if (!map.getSource("webcams")) {
      map.addSource("webcams", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "webcam-points",
        type: "circle",
        source: "webcams",
        paint: {
          "circle-color": "#a78bfa",
          "circle-radius": 6,
          "circle-opacity": 0.9,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#7c3aed",
        },
        layout: { visibility: "none" },
      });
    }

    map.setLayoutProperty("webcam-points", "visibility", showWebcams ? "visible" : "none");
    if (showWebcams && webcamData) {
      const src = map.getSource("webcams") as maplibregl.GeoJSONSource;
      if (src) src.setData(webcamData);
    }
  }, [showWebcams, webcamData]);

  // ─── Phase 13: Trade flow arcs (rendered as lines, deck.gl optional) ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showTradeFlows && !tradeFlowData) {
      fetch(`${API_URL}/api/trade-flows/arcs?limit=200`)
        .then(r => r.json())
        .then(data => setTradeFlowData(data))
        .catch(console.error);
    }

    // Add source/layer if needed
    if (!map.getSource("trade-arcs")) {
      map.addSource("trade-arcs", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "trade-arc-lines",
        type: "line",
        source: "trade-arcs",
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["get", "width"],
          "line-opacity": 0.6,
        },
        layout: {
          "line-cap": "round",
          visibility: "none",
        },
      });
    }

    map.setLayoutProperty("trade-arc-lines", "visibility", showTradeFlows ? "visible" : "none");

    if (showTradeFlows && tradeFlowData) {
      const filtered = tradeFlowType === "all"
        ? tradeFlowData.flows
        : tradeFlowData.flows.filter(f => f.flow_type === tradeFlowType);

      const geojson: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: filtered.map((f, i) => ({
          type: "Feature" as const,
          geometry: {
            type: "LineString" as const,
            coordinates: [f.origin, f.destination],
          },
          properties: {
            color: `rgb(${f.color.join(",")})`,
            width: f.width,
            flow_type: f.flow_type,
            commodity: f.commodity,
          },
        })),
      };
      const src = map.getSource("trade-arcs") as maplibregl.GeoJSONSource;
      if (src) src.setData(geojson);
    }
  }, [showTradeFlows, tradeFlowData, tradeFlowType]);

  // ─── Phase 13: Conflict frontlines ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showFrontlines && !frontlineData) {
      fetch(`${API_URL}/api/frontlines/geojson`)
        .then(r => r.json())
        .then(data => setFrontlineData(data))
        .catch(console.error);
    }

    if (!map.getSource("frontlines")) {
      map.addSource("frontlines", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "frontline-lines",
        type: "line",
        source: "frontlines",
        paint: {
          "line-color": ["get", "color"],
          "line-width": 3,
          "line-opacity": 0.8,
          "line-dasharray": [4, 2],
        },
        layout: { visibility: "none" },
      });
    }

    map.setLayoutProperty("frontline-lines", "visibility", showFrontlines ? "visible" : "none");
    if (showFrontlines && frontlineData) {
      const src = map.getSource("frontlines") as maplibregl.GeoJSONSource;
      if (src) src.setData(frontlineData);
    }
  }, [showFrontlines, frontlineData]);

  // ─── Phase 13: Map annotations ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showAnnotations && !annotationData) {
      fetch(`${API_URL}/api/annotations/geojson`)
        .then(r => r.json())
        .then(data => setAnnotationData(data))
        .catch(console.error);
    }

    if (!map.getSource("annotations")) {
      map.addSource("annotations", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // Point annotations
      map.addLayer({
        id: "annotation-points",
        type: "circle",
        source: "annotations",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-color": "#f97316",
          "circle-radius": 7,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
        layout: { visibility: "none" },
      });
      // Line/freehand annotations
      map.addLayer({
        id: "annotation-lines",
        type: "line",
        source: "annotations",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: {
          "line-color": "#f97316",
          "line-width": 2,
          "line-opacity": 0.8,
        },
        layout: { visibility: "none" },
      });
      // Polygon annotations
      map.addLayer({
        id: "annotation-fills",
        type: "fill",
        source: "annotations",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": "#f97316",
          "fill-opacity": 0.15,
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "annotation-outlines",
        type: "line",
        source: "annotations",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "line-color": "#f97316",
          "line-width": 2,
        },
        layout: { visibility: "none" },
      });
    }

    const vis = showAnnotations ? "visible" : "none";
    ["annotation-points", "annotation-lines", "annotation-fills", "annotation-outlines"].forEach(id => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });

    if (showAnnotations && annotationData) {
      const src = map.getSource("annotations") as maplibregl.GeoJSONSource;
      if (src) src.setData(annotationData);
    }
  }, [showAnnotations, annotationData]);

  // ─── Phase 13: Daily situation replay (24hr playback) ───

  useEffect(() => {
    if (!showReplayControls) {
      if (replayTimer.current) clearInterval(replayTimer.current);
      setReplayPlaying(false);
      return;
    }

    if (replayPlaying) {
      replayTimer.current = setInterval(() => {
        setReplayHour(h => {
          if (h >= 23) {
            setReplayPlaying(false);
            return 23;
          }
          return h + 1;
        });
      }, 1000); // 1 second per hour
    } else {
      if (replayTimer.current) clearInterval(replayTimer.current);
    }

    return () => {
      if (replayTimer.current) clearInterval(replayTimer.current);
    };
  }, [showReplayControls, replayPlaying]);

  // Filter events for replay hour
  useEffect(() => {
    if (!showReplayControls) return;
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const now = new Date();
    now.setHours(replayHour, 0, 0, 0);
    const hourStart = now.getTime();
    const hourEnd = hourStart + 3600000;

    const hourFeatures = features.filter(f => {
      const ts = new Date(f.timestamp).getTime();
      return ts >= hourStart && ts < hourEnd;
    });

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: hourFeatures.map(f => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [f.lng, f.lat] },
        properties: {
          id: f.id, title: f.title, category: f.category || "unclassified",
          severity: f.severity, confidence: f.confidence, source: f.source,
          timestamp: f.timestamp, country_code: f.country_code || "",
          color: getMarkerColor(f.category),
        },
      })),
    };

    const evtSrc = map.getSource("events") as maplibregl.GeoJSONSource;
    if (evtSrc) evtSrc.setData(geojson);
  }, [showReplayControls, replayHour, features]);

  // ─── Phase 13: Event ripple animation CSS injection ───

  useEffect(() => {
    // Inject ripple keyframe animation once
    const styleId = "cerebro-ripple-style";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `
        @keyframes cerebro-ripple {
          0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); }
          70% { box-shadow: 0 0 0 20px rgba(239, 68, 68, 0); }
          100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }
        .cerebro-ripple {
          animation: cerebro-ripple 1.5s ease-out;
        }
        @keyframes cerebro-pulse-beacon {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.5); }
        }
      `;
      document.head.appendChild(style);
    }
  }, []);

  // ─── Phase 13: Drawing mode click handler ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !drawMode) return;

    // Reset measure state when entering measure mode
    if (drawMode === "measure") {
      setMeasurePoints([]);
      setMeasureResult(null);
    }

    const handleDrawClick = async (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat;

      // ─── Measurement mode: collect 2 points, call API ───
      if (drawMode === "measure") {
        setMeasurePoints(prev => {
          const updated: [number, number][] = [...prev, [lat, lng]];
          if (updated.length === 2) {
            fetch(`${API_URL}/api/geospatial/measure/distance`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                points: updated.map(p => [p[0], p[1]]),
              }),
            })
              .then(r => r.ok ? r.json() : null)
              .then(data => {
                if (data) {
                  setMeasureResult({
                    distance_km: data.total_distance_km,
                    bearing: data.segments?.[0]?.bearing_deg ?? 0,
                  });
                }
              })
              .catch(() => {});

            // Draw line on map
            if (map.getSource("measure-line")) {
              (map.getSource("measure-line") as maplibregl.GeoJSONSource).setData({
                type: "Feature",
                geometry: { type: "LineString", coordinates: updated.map(p => [p[1], p[0]]) },
                properties: {},
              });
            } else {
              map.addSource("measure-line", {
                type: "geojson",
                data: {
                  type: "Feature",
                  geometry: { type: "LineString", coordinates: updated.map(p => [p[1], p[0]]) },
                  properties: {},
                },
              });
              map.addLayer({
                id: "measure-line-layer",
                type: "line",
                source: "measure-line",
                paint: {
                  "line-color": "#f59e0b",
                  "line-width": 2,
                  "line-dasharray": [4, 2],
                },
              });
            }
            return updated;
          }
          return updated;
        });
        return;
      }

      // ─── Standard annotation modes ───
      let geometry: Record<string, unknown>;
      if (drawMode === "marker") {
        geometry = { type: "Point", coordinates: [lng, lat] };
      } else if (drawMode === "circle") {
        geometry = { type: "Point", coordinates: [lng, lat] };
      } else {
        return;
      }

      try {
        await fetch(`${API_URL}/api/annotations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            annotation_type: drawMode,
            geometry_json: geometry,
            title: `${drawMode} at ${lat.toFixed(3)}, ${lng.toFixed(3)}`,
            layer_name: "default",
          }),
        });
        const res = await fetch(`${API_URL}/api/annotations/geojson`);
        if (res.ok) setAnnotationData(await res.json());
      } catch (err) {
        console.error("Annotation error:", err);
      }
      setDrawMode(null);
    };

    map.on("click", handleDrawClick);
    map.getCanvas().style.cursor = "crosshair";

    return () => {
      map.off("click", handleDrawClick);
      map.getCanvas().style.cursor = "";
      // Clean up measure line when exiting draw mode
      if (map.getLayer("measure-line-layer")) map.removeLayer("measure-line-layer");
      if (map.getSource("measure-line")) map.removeSource("measure-line");
    };
  }, [drawMode]);

  // ─── Phase 13: Cinematic flythrough ───

  function startFlythrough(target: [number, number], name: string) {
    const map = mapRef.current;
    if (!map || flythroughActive) return;
    setFlythroughActive(true);

    // Step 1: Zoom out to space view
    map.flyTo({ center: map.getCenter(), zoom: 1.5, pitch: 0, bearing: 0, duration: 2000 });

    // Step 2: Sweep to target continent level
    setTimeout(() => {
      map.flyTo({ center: target, zoom: 4, pitch: 30, bearing: 20, duration: 3000 });
    }, 2200);

    // Step 3: Zoom to city level with cinematic bearing rotation
    setTimeout(() => {
      map.flyTo({ center: target, zoom: 14, pitch: 60, bearing: 45, duration: 3000 });
    }, 5500);

    // Step 4: Slow orbit — rotate bearing 360° while maintaining position
    setTimeout(() => {
      let bearing = 45;
      const orbitInterval = setInterval(() => {
        bearing += 0.5;
        if (bearing >= 405) {
          clearInterval(orbitInterval);
          setFlythroughActive(false);
          return;
        }
        map.easeTo({ bearing, duration: 50, easing: (t: number) => t });
      }, 50);
    }, 8800);
  }

  /**
   * Multi-waypoint cinematic flythrough — visits a sequence of locations
   * with smooth camera transitions including bearing/pitch interpolation.
   */
  function startMultiWaypointFlythrough(waypoints: { coords: [number, number]; name: string; zoom: number; pitch: number; bearing: number; dwell: number }[]) {
    const map = mapRef.current;
    if (!map || flythroughActive || waypoints.length === 0) return;
    setFlythroughActive(true);

    let idx = 0;
    const flyToNext = () => {
      if (idx >= waypoints.length) {
        setFlythroughActive(false);
        return;
      }
      const wp = waypoints[idx];
      idx++;
      map.flyTo({
        center: wp.coords,
        zoom: wp.zoom,
        pitch: wp.pitch,
        bearing: wp.bearing,
        duration: 3000,
        essential: true,
      });
      // After arrival + dwell time, move to next
      setTimeout(flyToNext, 3000 + wp.dwell);
    };

    // Start with zoom-out
    map.flyTo({ center: map.getCenter(), zoom: 1.5, pitch: 0, bearing: 0, duration: 2000 });
    setTimeout(flyToNext, 2200);
  }

  // ─── Split-screen map initialization ───

  useEffect(() => {
    if (!showSplitScreen) {
      // Destroy split map when disabled
      if (splitMapRef.current) {
        splitMapRef.current.remove();
        splitMapRef.current = null;
      }
      return;
    }

    if (!splitMapContainer.current || splitMapRef.current) return;

    const primaryMap = mapRef.current;
    if (!primaryMap) return;

    const center = primaryMap.getCenter();
    const zoom = primaryMap.getZoom();

    const splitMap = new maplibregl.Map({
      container: splitMapContainer.current,
      style: {
        version: 8,
        name: "Cerebro Split - Satellite",
        sources: {
          "satellite-split": {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            maxzoom: 18,
          },
        },
        layers: [
          { id: "bg-split", type: "background", paint: { "background-color": "#0a0a0a" } },
          { id: "satellite-split", type: "raster", source: "satellite-split", minzoom: 0, maxzoom: 18 },
        ],
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      },
      center: [center.lng, center.lat],
      zoom: zoom,
      maxPitch: 60,
      ...(({ projection: { type: "globe" } }) as Record<string, unknown>),
    });

    splitMap.addControl(new maplibregl.NavigationControl(), "top-right");

    splitMap.on("load", () => {
      // Add events layer to split map
      splitMap.addSource("events-split", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      splitMap.addLayer({
        id: "events-split-points",
        type: "circle",
        source: "events-split",
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": [
            "interpolate", ["linear"], ["get", "severity"],
            0, 4, 50, 7, 100, 12,
          ],
          "circle-opacity": 0.85,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#18181b",
        },
      });

      splitMapRef.current = splitMap;
    });

    // Sync camera: primary -> split
    let syncing = false;
    const syncToSplit = () => {
      if (syncing || !splitMapRef.current) return;
      syncing = true;
      splitMapRef.current.jumpTo({
        center: primaryMap.getCenter(),
        zoom: primaryMap.getZoom(),
        bearing: primaryMap.getBearing(),
        pitch: primaryMap.getPitch(),
      });
      syncing = false;
    };

    const syncToPrimary = () => {
      if (syncing || !splitMapRef.current) return;
      syncing = true;
      primaryMap.jumpTo({
        center: splitMapRef.current.getCenter(),
        zoom: splitMapRef.current.getZoom(),
        bearing: splitMapRef.current.getBearing(),
        pitch: splitMapRef.current.getPitch(),
      });
      syncing = false;
    };

    primaryMap.on("move", syncToSplit);
    splitMap.on("move", syncToPrimary);

    return () => {
      primaryMap.off("move", syncToSplit);
      if (splitMapRef.current) {
        splitMapRef.current.off("move", syncToPrimary);
      }
    };
  }, [showSplitScreen]);

  // ─── Update split map events data ───

  useEffect(() => {
    const splitMap = splitMapRef.current;
    if (!splitMap || !splitMap.isStyleLoaded()) return;

    const filtered = features.filter(
      (f) => enabledSources.has(f.source) && (f.category ? enabledCategories.has(f.category) : true)
    );

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: filtered.map((f) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [f.lng, f.lat] },
        properties: {
          id: f.id, title: f.title, category: f.category || "unclassified",
          severity: f.severity, color: getMarkerColor(f.category),
        },
      })),
    };

    const src = splitMap.getSource("events-split") as maplibregl.GeoJSONSource;
    if (src) src.setData(geojson);
  }, [features, enabledSources, enabledCategories, showSplitScreen]);

  // ─── Global Keyboard Shortcuts ───

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Ignore when typing in inputs
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      const meta = e.metaKey || e.ctrlKey;

      // Cmd+K — search (already handled by browser/app)
      // Cmd+S — save view
      if (meta && e.key === "s") {
        e.preventDefault();
        saveCurrentView();
        return;
      }

      // ? — toggle shortcut help
      if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
        e.preventDefault();
        setShowShortcutHelp((p) => !p);
        return;
      }

      // Escape — close panels
      if (e.key === "Escape") {
        setShowShortcutHelp(false);
        setShowViewPanel(false);
        setDrawMode(null);
        if (popupRef.current) popupRef.current.remove();
        return;
      }

      // Single-key toggles (no modifier)
      if (!meta && !e.altKey) {
        switch (e.key) {
          case "h": setShowHeatmap((p) => !p); break;
          case "v": setShowVessels((p) => !p); break;
          case "a": setShowFlights((p) => !p); break;
          case "t": setShowTerrain3D((p) => !p); break;
          case "d": setShowSplitScreen((p) => !p); break;
          case "s": setShowSatelliteSwipe((p) => !p); break;
          case "m": setShowMaritimeZones((p) => !p); break;
          case "p": setShowPredictions((p) => !p); break;
          case "g": setShowDensityGrid((p) => !p); break;
          case "l": setShowTimelapse((p) => !p); break;
          case "w": setShowWebcams((p) => !p); break;
          case "f": setShowFrontlines((p) => !p); break;
          case "o": setShowTradeFlows((p) => !p); break;
          case "n": setShowAnnotations((p) => !p); break;
          case "i": setShowHudMode((p) => !p); break;
          case "b": setShowPulseBeacons((p) => !p); break;
          case "x": setShowSatelliteOrbits((p) => !p); break;
          case "e": setShowExtrudedCountries((p) => !p); break;
          // 1-5 toggle categories
          case "1": toggleCategory("military"); break;
          case "2": toggleCategory("political"); break;
          case "3": toggleCategory("economic"); break;
          case "4": toggleCategory("health"); break;
          case "5": toggleCategory("environmental"); break;
          // [ and ] adjust severity
          case "[": setSeverityMin((p) => Math.max(0, p - 10)); break;
          case "]": setSeverityMin((p) => Math.min(100, p + 10)); break;
          // + and - zoom
          case "=":
          case "+":
            mapRef.current?.zoomIn();
            break;
          case "-":
            mapRef.current?.zoomOut();
            break;
          // r — reset view
          case "r":
            mapRef.current?.flyTo({ center: [20, 30], zoom: 2, pitch: 0, bearing: 0, duration: 1000 });
            break;
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // ─── Phase 14: Satellite orbit tracks ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showSatelliteOrbits && !orbitData) {
      // Seed then fetch
      fetch(`${API_URL}/api/satellites/seed`, { method: "POST" }).catch(() => {});
      fetch(`${API_URL}/api/satellites/orbits/geojson`)
        .then(r => r.json())
        .then(data => setOrbitData(data))
        .catch(console.error);
    }

    if (!map.getSource("satellite-orbits")) {
      map.addSource("satellite-orbits", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "orbit-lines",
        type: "line",
        source: "satellite-orbits",
        paint: {
          "line-color": ["get", "color"],
          "line-width": 1.5,
          "line-opacity": 0.6,
          "line-dasharray": [4, 4],
        },
        layout: { visibility: "none" },
      });
    }

    map.setLayoutProperty("orbit-lines", "visibility", showSatelliteOrbits ? "visible" : "none");
    if (showSatelliteOrbits && orbitData) {
      const src = map.getSource("satellite-orbits") as maplibregl.GeoJSONSource;
      if (src) src.setData(orbitData);
    }
  }, [showSatelliteOrbits, orbitData]);

  // ─── Phase 14: Pulse beacons at monitored locations ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showPulseBeacons && !beaconData) {
      fetch(`${API_URL}/api/beacons/seed`, { method: "POST" }).catch(() => {});
      fetch(`${API_URL}/api/beacons/geojson`)
        .then(r => r.json())
        .then(data => setBeaconData(data))
        .catch(console.error);
    }

    if (!map.getSource("pulse-beacons")) {
      map.addSource("pulse-beacons", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // Outer pulsing ring
      map.addLayer({
        id: "beacon-pulse",
        type: "circle",
        source: "pulse-beacons",
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": 18,
          "circle-opacity": 0.2,
          "circle-stroke-width": 2,
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-opacity": 0.5,
        },
        layout: { visibility: "none" },
      });
      // Inner solid point
      map.addLayer({
        id: "beacon-core",
        type: "circle",
        source: "pulse-beacons",
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": 6,
          "circle-opacity": 0.9,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
        layout: { visibility: "none" },
      });
      // Labels
      map.addLayer({
        id: "beacon-labels",
        type: "symbol",
        source: "pulse-beacons",
        layout: {
          "text-field": ["get", "name"],
          "text-size": 10,
          "text-offset": [0, 1.8],
          visibility: "none",
        },
        paint: {
          "text-color": "#e4e4e7",
          "text-halo-color": "#18181b",
          "text-halo-width": 1,
        },
      });
    }

    const vis = showPulseBeacons ? "visible" : "none";
    ["beacon-pulse", "beacon-core", "beacon-labels"].forEach(id => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });

    if (showPulseBeacons && beaconData) {
      const src = map.getSource("pulse-beacons") as maplibregl.GeoJSONSource;
      if (src) src.setData(beaconData);
    }
  }, [showPulseBeacons, beaconData]);

  // ─── Phase 14: Country extrusion data fetch ───

  useEffect(() => {
    if (!showExtrudedCountries) return;

    fetch(`${API_URL}/api/extrusions/seed`, { method: "POST" }).catch(() => {});
    fetch(`${API_URL}/api/extrusions/data/${extrusionMetric}`)
      .then(r => r.json())
      .then(data => setExtrusionData(data.data))
      .catch(console.error);
  }, [showExtrudedCountries, extrusionMetric]);

  // ─── Phase 14: Projection morph (globe ↔ mercator) ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const m = map as any;
    if (m.setProjection) {
      m.setProjection(projectionMode === "globe" ? { type: "globe" } : { type: "mercator" });
    }
  }, [projectionMode]);

  // ─── Phase 14: HUD scan-line CSS injection ───

  useEffect(() => {
    const styleId = "cerebro-hud-style";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `
        @keyframes cerebro-scanline {
          0% { transform: translateY(-100%); }
          100% { transform: translateY(100vh); }
        }
        .cerebro-hud-scanline {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          height: 2px;
          background: linear-gradient(90deg, transparent, rgba(0, 255, 200, 0.4), transparent);
          animation: cerebro-scanline 4s linear infinite;
          pointer-events: none;
          z-index: 9999;
        }
        .cerebro-hud-overlay {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 100;
          border: 1px solid rgba(0, 255, 200, 0.15);
          box-shadow: inset 0 0 100px rgba(0, 255, 200, 0.03);
        }
        .cerebro-hud-corner {
          position: absolute;
          width: 30px;
          height: 30px;
          border-color: rgba(0, 255, 200, 0.4);
        }
        .cerebro-hud-corner.tl { top: 12px; left: 12px; border-top: 2px solid; border-left: 2px solid; }
        .cerebro-hud-corner.tr { top: 12px; right: 12px; border-top: 2px solid; border-right: 2px solid; }
        .cerebro-hud-corner.bl { bottom: 12px; left: 12px; border-bottom: 2px solid; border-left: 2px solid; }
        .cerebro-hud-corner.br { bottom: 12px; right: 12px; border-bottom: 2px solid; border-right: 2px solid; }
        .cerebro-glassmorphism {
          background: rgba(24, 24, 27, 0.6) !important;
          backdrop-filter: blur(12px) saturate(1.5);
          -webkit-backdrop-filter: blur(12px) saturate(1.5);
          border: 1px solid rgba(255, 255, 255, 0.08) !important;
        }
      `;
      document.head.appendChild(style);
    }
  }, []);

  // ─── Phase 15: Photo pin layer ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showPhotoPins && !photoPinData) {
      fetch(`${API_URL}/api/photo-pins/geojson`)
        .then(r => r.json())
        .then(data => setPhotoPinData(data))
        .catch(console.error);
    }

    if (!map.getSource("photo-pins")) {
      map.addSource("photo-pins", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "photo-pin-points",
        type: "circle",
        source: "photo-pins",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": 7,
          "circle-opacity": 0.9,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
        layout: { visibility: "none" },
      });
      // Mismatch lines (red dashed)
      map.addLayer({
        id: "photo-pin-mismatch",
        type: "line",
        source: "photo-pins",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: {
          "line-color": "#ef4444",
          "line-width": 2,
          "line-opacity": 0.7,
          "line-dasharray": [4, 3],
        },
        layout: { visibility: "none" },
      });
    }

    const vis = showPhotoPins ? "visible" : "none";
    ["photo-pin-points", "photo-pin-mismatch"].forEach(id => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });

    if (showPhotoPins && photoPinData) {
      const src = map.getSource("photo-pins") as maplibregl.GeoJSONSource;
      if (src) src.setData(photoPinData);
    }
  }, [showPhotoPins, photoPinData]);

  // ─── Phase 15: SunCalc time-of-day lighting simulation ───

  useEffect(() => {
    if (!showSunSim || !sunSimTime) return;
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const center = map.getCenter();
    const sunPos = SunCalc.getPosition(sunSimTime, center.lat, center.lng);
    const altDeg = sunPos.altitude * (180 / Math.PI);
    const azDeg = sunPos.azimuth * (180 / Math.PI) + 180;

    // Map sun altitude to sky brightness: below horizon = dark, high = bright
    const brightness = Math.max(0, Math.min(1, (altDeg + 10) / 80));
    const skyColor = `rgba(${Math.round(30 + brightness * 200)}, ${Math.round(30 + brightness * 200)}, ${Math.round(50 + brightness * 205)}, 1)`;

    // Apply atmospheric coloring to the background layer
    if (map.getLayer("background")) {
      map.setPaintProperty("background", "background-color",
        brightness < 0.15 ? "#050510" : brightness < 0.4 ? "#1a1a3a" : "#0a0a0a"
      );
    }

    // Adjust raster layer brightness to simulate sun
    if (map.getLayer("osm")) {
      map.setPaintProperty("osm", "raster-brightness-max", 0.3 + brightness * 0.7);
    }
  }, [showSunSim, sunSimTime]);

  // Reset lighting when sun sim disabled
  useEffect(() => {
    if (showSunSim) return;
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    if (map.getLayer("background")) map.setPaintProperty("background", "background-color", "#0a0a0a");
    if (map.getLayer("osm")) map.setPaintProperty("osm", "raster-brightness-max", 1.0);
  }, [showSunSim]);

  // ─── Phase 15: PiP inset map ───

  useEffect(() => {
    if (!showPiP) {
      if (pipMapRef.current) {
        pipMapRef.current.remove();
        pipMapRef.current = null;
      }
      return;
    }

    if (!pipMapContainer.current || pipMapRef.current) return;
    const primaryMap = mapRef.current;
    if (!primaryMap) return;

    const center = primaryMap.getCenter();

    const pipMap = new maplibregl.Map({
      container: pipMapContainer.current,
      style: {
        version: 8, name: "PiP",
        sources: {
          "pip-sat": {
            type: "raster",
            tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            tileSize: 256, maxzoom: 18,
          },
        },
        layers: [
          { id: "bg-pip", type: "background", paint: { "background-color": "#0a0a0a" } },
          { id: "sat-pip", type: "raster", source: "pip-sat", minzoom: 0, maxzoom: 18 },
        ],
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      },
      center: [center.lng, center.lat],
      zoom: primaryMap.getZoom() + 4,
      interactive: true,
      attributionControl: false,
    });

    pipMap.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    pipMap.on("load", () => { pipMapRef.current = pipMap; });

    // Sync PiP center when primary moves
    const syncPiP = () => {
      if (pipMapRef.current) {
        pipMapRef.current.setCenter(primaryMap.getCenter());
      }
    };
    primaryMap.on("moveend", syncPiP);

    return () => {
      primaryMap.off("moveend", syncPiP);
    };
  }, [showPiP]);

  // ─── Phase 15: Command palette Cmd+K handler ───

  useEffect(() => {
    function handleCmdK(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowCommandPalette(p => !p);
        setCmdQuery("");
      }
    }
    window.addEventListener("keydown", handleCmdK);
    return () => window.removeEventListener("keydown", handleCmdK);
  }, []);

  // ─── Particle flow animation (deck.gl-style on MapLibre) ───

  useEffect(() => {
    if (!showParticleFlow) {
      if (particleAnimFrame.current) {
        cancelAnimationFrame(particleAnimFrame.current);
        particleAnimFrame.current = null;
      }
      // Remove particle layer
      const map = mapRef.current;
      if (map && map.isStyleLoaded()) {
        if (map.getLayer("particle-trail")) map.removeLayer("particle-trail");
        if (map.getSource("particle-trail")) map.removeSource("particle-trail");
      }
      return;
    }

    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Generate animated particle trail data from trade arcs if available
    if (!map.getSource("particle-trail")) {
      map.addSource("particle-trail", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "particle-trail",
        type: "circle",
        source: "particle-trail",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "phase"], 0, 2, 1, 5],
          "circle-color": ["get", "color"],
          "circle-opacity": ["interpolate", ["linear"], ["get", "phase"], 0, 0.3, 0.5, 0.9, 1, 0.1],
          "circle-blur": 0.4,
        },
      });
    }

    // Animate particles along trade flow paths
    let t = 0;
    const animate = () => {
      t += 0.005;
      if (t > 1) t = 0;
      setParticleTime(t);

      // Generate particle positions from existing trade flow data
      if (tradeFlowData?.flows) {
        const features: GeoJSON.Feature[] = [];
        for (const flow of tradeFlowData.flows.slice(0, 50)) {
          // Create 5 particles per flow at different phases
          for (let p = 0; p < 5; p++) {
            const phase = (t + p * 0.2) % 1;
            const lng = flow.origin[0] + (flow.destination[0] - flow.origin[0]) * phase;
            const lat = flow.origin[1] + (flow.destination[1] - flow.origin[1]) * phase;
            features.push({
              type: "Feature",
              geometry: { type: "Point", coordinates: [lng, lat] },
              properties: {
                phase,
                color: `rgb(${flow.color.join(",")})`,
              },
            });
          }
        }
        const src = map.getSource("particle-trail") as maplibregl.GeoJSONSource;
        if (src) {
          src.setData({ type: "FeatureCollection", features });
        }
      }

      particleAnimFrame.current = requestAnimationFrame(animate);
    };
    particleAnimFrame.current = requestAnimationFrame(animate);

    return () => {
      if (particleAnimFrame.current) cancelAnimationFrame(particleAnimFrame.current);
    };
  }, [showParticleFlow, tradeFlowData]);

  // ─── Animated cluster breathing ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (!showClusterBreathing) {
      if (clusterBreathFrame.current) {
        cancelAnimationFrame(clusterBreathFrame.current);
        clusterBreathFrame.current = null;
      }
      // Reset to static values
      if (map.getLayer("clusters")) {
        map.setPaintProperty("clusters", "circle-radius", [
          "step", ["get", "point_count"], 15, 10, 20, 50, 28,
        ]);
      }
      return;
    }

    let phase = 0;
    const breathe = () => {
      phase += 0.02;
      const scale = 1 + Math.sin(phase) * 0.15; // 0.85 to 1.15 scale
      if (map.getLayer("clusters")) {
        map.setPaintProperty("clusters", "circle-radius", [
          "step", ["get", "point_count"],
          15 * scale, 10,
          20 * scale, 50,
          28 * scale,
        ]);
      }
      clusterBreathFrame.current = requestAnimationFrame(breathe);
    };
    clusterBreathFrame.current = requestAnimationFrame(breathe);

    return () => {
      if (clusterBreathFrame.current) cancelAnimationFrame(clusterBreathFrame.current);
    };
  }, [showClusterBreathing]);

  // ─── Shockwave propagation trigger ───

  function triggerShockwave(lngLat: { lng: number; lat: number }) {
    const map = mapRef.current;
    if (!map) return;
    const point = map.project([lngLat.lng, lngLat.lat]);
    const id = `sw-${Date.now()}`;
    setShockwaves(prev => [...prev, { id, x: point.x, y: point.y, time: Date.now() }]);
    // Auto-remove after animation completes
    setTimeout(() => {
      setShockwaves(prev => prev.filter(s => s.id !== id));
    }, 3000);
  }

  // Auto-trigger shockwaves for high-severity events that appear
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    // Find events with severity > 80 that are "fresh" (within last 2 hours)
    const cutoff = Date.now() - 2 * 3600000;
    const cascadeEvents = features.filter(f =>
      f.severity > 80 && new Date(f.timestamp).getTime() > cutoff
    );
    // Only trigger for the top 3 most severe
    cascadeEvents.slice(0, 3).forEach((evt, i) => {
      setTimeout(() => {
        triggerShockwave({ lng: evt.lng, lat: evt.lat });
      }, i * 500);
    });
  // Only run when features list changes significantly
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureCount]);

  // ─── Animated risk score (odometer effect) ───

  useEffect(() => {
    // Compute average risk from visible events
    if (features.length === 0) return;
    const avg = Math.round(features.reduce((s, f) => s + f.severity, 0) / features.length);
    if (prevRiskScore.current !== avg) {
      prevRiskScore.current = avg;
      // Trigger animation by setting the score (CSS handles the roll)
      setAnimatedRiskScore(avg);
    }
  }, [features]);

  // ─── Phase 16: Disease outbreak spread animation ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showDiseaseSpread && diseaseOutbreaks.length === 0) {
      fetch(`${API_URL}/api/disease-outbreaks/seed`, { method: "POST" }).catch(() => {});
      fetch(`${API_URL}/api/disease-outbreaks`)
        .then(r => r.json())
        .then(data => {
          setDiseaseOutbreaks(data.outbreaks || []);
          if (data.outbreaks?.length > 0) setSelectedOutbreak(data.outbreaks[0].id);
        })
        .catch(console.error);
    }

    if (!map.getSource("disease-spread")) {
      map.addSource("disease-spread", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "disease-spread-fill",
        type: "fill",
        source: "disease-spread",
        paint: {
          "fill-color": "#ef4444",
          "fill-opacity": ["get", "opacity"],
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "disease-spread-outline",
        type: "line",
        source: "disease-spread",
        paint: {
          "line-color": "#ef4444",
          "line-width": 1,
          "line-opacity": 0.5,
        },
        layout: { visibility: "none" },
      });
    }

    const vis = showDiseaseSpread ? "visible" : "none";
    ["disease-spread-fill", "disease-spread-outline"].forEach(id => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });

    if (showDiseaseSpread && selectedOutbreak) {
      fetch(`${API_URL}/api/disease-outbreaks/${selectedOutbreak}/spread?day=${diseaseDay}`)
        .then(r => r.json())
        .then(data => {
          const src = map.getSource("disease-spread") as maplibregl.GeoJSONSource;
          if (src) src.setData(data);
        })
        .catch(console.error);
    }
  }, [showDiseaseSpread, selectedOutbreak, diseaseDay, diseaseOutbreaks.length]);

  // Disease spread animation player
  useEffect(() => {
    if (!diseaseAnimPlaying) {
      if (diseaseAnimFrame.current) {
        clearInterval(diseaseAnimFrame.current as unknown as number);
        diseaseAnimFrame.current = null;
      }
      return;
    }
    const timer = setInterval(() => {
      setDiseaseDay(d => {
        if (d >= 29) { setDiseaseAnimPlaying(false); return 29; }
        return d + 1;
      });
    }, 300);
    diseaseAnimFrame.current = timer as unknown as number;
    return () => clearInterval(timer);
  }, [diseaseAnimPlaying]);

  // ─── Phase 16: Storm track layers ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showStormTracks && stormList.length === 0) {
      fetch(`${API_URL}/api/storms/seed`, { method: "POST" }).catch(() => {});
      fetch(`${API_URL}/api/storms`)
        .then(r => r.json())
        .then(data => setStormList(data.storms || []))
        .catch(console.error);
    }

    if (!map.getSource("storm-tracks")) {
      map.addSource("storm-tracks", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "storm-cone",
        type: "fill",
        source: "storm-tracks",
        filter: ["==", ["get", "type"], "uncertainty_cone"],
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": 0.15,
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "storm-line",
        type: "line",
        source: "storm-tracks",
        filter: ["==", ["get", "type"], "track_line"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": 3,
          "line-dasharray": [2, 1],
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "storm-points",
        type: "circle",
        source: "storm-tracks",
        filter: ["==", ["get", "type"], "track_point"],
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": 6,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
        layout: { visibility: "none" },
      });
    }

    const vis = showStormTracks ? "visible" : "none";
    ["storm-cone", "storm-line", "storm-points"].forEach(id => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });

    if (showStormTracks && stormList.length > 0) {
      // Load all storm tracks into one FeatureCollection
      Promise.all(stormList.map(s =>
        fetch(`${API_URL}/api/storms/${s.id}/track`).then(r => r.json())
      )).then(results => {
        const allFeatures = results.flatMap(r => r.features || []);
        const src = map.getSource("storm-tracks") as maplibregl.GeoJSONSource;
        if (src) src.setData({ type: "FeatureCollection", features: allFeatures });
      }).catch(console.error);
    }
  }, [showStormTracks, stormList.length]);

  // ─── Phase 16: News ticker ───

  useEffect(() => {
    if (!showNewsTicker) return;
    // Use existing events as ticker feed
    const items = features.slice(0, 20).map(f => ({
      title: f.title,
      severity: f.severity,
      timestamp: f.timestamp,
    }));
    setTickerItems(items);
  }, [showNewsTicker, features]);

  // ─── Phase 16: Timelapse video capture ───

  function startTimelapseCapture() {
    const map = mapRef.current;
    if (!map) return;
    const canvas = map.getCanvas();
    const stream = canvas.captureStream(10); // 10 FPS
    const recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
    recordedChunks.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) recordedChunks.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(recordedChunks.current, { type: "video/webm" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cerebro-timelapse-${Date.now()}.webm`;
      a.click();
      URL.revokeObjectURL(url);
    };
    recorder.start();
    mediaRecorderRef.current = recorder;
    setIsRecordingTimelapse(true);
  }

  function stopTimelapseCapture() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setIsRecordingTimelapse(false);
  }

  // ─── Phase 16: Conflict documentary mode ───

  useEffect(() => {
    if (!showDocumentaryMode) return;
    if (documentaryProgressions.length === 0) {
      fetch(`${API_URL}/api/conflict-progressions/seed`, { method: "POST" }).catch(() => {});
      fetch(`${API_URL}/api/conflict-progressions`)
        .then(r => r.json())
        .then(data => {
          setDocumentaryProgressions(data.progressions || []);
          if (data.progressions?.length > 0) {
            setSelectedProgression(data.progressions[0].id);
          }
        })
        .catch(console.error);
    }
  }, [showDocumentaryMode, documentaryProgressions.length]);

  // Load steps when progression changes
  useEffect(() => {
    if (!selectedProgression) return;
    fetch(`${API_URL}/api/conflict-progressions/${selectedProgression}/steps`)
      .then(r => r.json())
      .then(data => {
        setDocumentarySteps(data.steps || []);
        setCurrentDocStep(0);
      })
      .catch(console.error);
  }, [selectedProgression]);

  // Navigate camera to current documentary step
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !showDocumentaryMode || documentarySteps.length === 0) return;
    const step = documentarySteps[currentDocStep];
    if (!step) return;
    map.flyTo({
      center: [step.center_lng, step.center_lat],
      zoom: step.zoom,
      bearing: step.bearing,
      pitch: step.pitch,
      duration: 2000,
    });
  }, [currentDocStep, showDocumentaryMode, documentarySteps]);

  // ─── Phase 16: 3D volumetric heatmap (fill-extrusion) ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (!map.getSource("volumetric-heat")) {
      // Create grid cells from events
      map.addSource("volumetric-heat", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "volumetric-heat-extrusion",
        type: "fill-extrusion",
        source: "volumetric-heat",
        paint: {
          "fill-extrusion-color": [
            "interpolate", ["linear"], ["get", "intensity"],
            0, "#22c55e",
            0.3, "#eab308",
            0.6, "#f97316",
            1, "#ef4444",
          ],
          "fill-extrusion-height": ["*", ["get", "intensity"], 200000],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.7,
        },
        layout: { visibility: "none" },
      });
    }

    map.setLayoutProperty("volumetric-heat-extrusion", "visibility",
      showVolumetricHeat ? "visible" : "none");

    if (showVolumetricHeat && features.length > 0) {
      // Build grid cells (2° x 2° grid)
      const grid: Record<string, { count: number; totalSev: number; lat: number; lng: number }> = {};
      for (const f of features) {
        const gLat = Math.floor(f.lat / 2) * 2;
        const gLng = Math.floor(f.lng / 2) * 2;
        const key = `${gLat},${gLng}`;
        if (!grid[key]) grid[key] = { count: 0, totalSev: 0, lat: gLat, lng: gLng };
        grid[key].count++;
        grid[key].totalSev += f.severity;
      }
      const maxCount = Math.max(...Object.values(grid).map(g => g.count), 1);
      const gridFeatures: GeoJSON.Feature[] = Object.values(grid).map(g => ({
        type: "Feature" as const,
        geometry: {
          type: "Polygon" as const,
          coordinates: [[
            [g.lng, g.lat], [g.lng + 2, g.lat],
            [g.lng + 2, g.lat + 2], [g.lng, g.lat + 2],
            [g.lng, g.lat],
          ]],
        },
        properties: {
          intensity: g.count / maxCount,
          count: g.count,
          avg_severity: g.totalSev / g.count,
        },
      }));
      const src = map.getSource("volumetric-heat") as maplibregl.GeoJSONSource;
      if (src) src.setData({ type: "FeatureCollection", features: gridFeatures });
    }
  }, [showVolumetricHeat, features]);

  // ─── Phase 16: 3D extruded bar charts ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (!map.getSource("bar-charts-3d")) {
      map.addSource("bar-charts-3d", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "bar-chart-extrusion",
        type: "fill-extrusion",
        source: "bar-charts-3d",
        paint: {
          "fill-extrusion-color": ["get", "color"],
          "fill-extrusion-height": ["get", "height"],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.85,
        },
        layout: { visibility: "none" },
      });
    }

    map.setLayoutProperty("bar-chart-extrusion", "visibility",
      show3DBarCharts ? "visible" : "none");

    if (show3DBarCharts && features.length > 0) {
      // Group events by country and build bar chart features
      const countryStats: Record<string, { count: number; totalSev: number; lat: number; lng: number }> = {};
      for (const f of features) {
        const cc = f.country_code || "XX";
        if (!countryStats[cc]) countryStats[cc] = { count: 0, totalSev: 0, lat: f.lat, lng: f.lng };
        countryStats[cc].count++;
        countryStats[cc].totalSev += f.severity;
      }
      const maxCount = Math.max(...Object.values(countryStats).map(s => s.count), 1);
      const barFeatures: GeoJSON.Feature[] = Object.entries(countryStats).map(([cc, s]) => {
        const barWidth = 0.5; // degrees
        return {
          type: "Feature" as const,
          geometry: {
            type: "Polygon" as const,
            coordinates: [[
              [s.lng - barWidth, s.lat - barWidth],
              [s.lng + barWidth, s.lat - barWidth],
              [s.lng + barWidth, s.lat + barWidth],
              [s.lng - barWidth, s.lat + barWidth],
              [s.lng - barWidth, s.lat - barWidth],
            ]],
          },
          properties: {
            country: cc,
            height: (s.count / maxCount) * 500000,
            color: s.totalSev / s.count > 60 ? "#ef4444" : s.totalSev / s.count > 30 ? "#eab308" : "#22c55e",
            count: s.count,
          },
        };
      });
      const src = map.getSource("bar-charts-3d") as maplibregl.GeoJSONSource;
      if (src) src.setData({ type: "FeatureCollection", features: barFeatures });
    }
  }, [show3DBarCharts, features]);

  // ─── Phase 16: Custom gesture handlers ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (gestureMode === "tactical") {
      // Tactical mode: two-finger rotate, three-finger pitch
      map.touchZoomRotate.enableRotation();
      map.touchPitch.enable();
      // Double-tap to mark location
      const handleDoubleTap = (e: maplibregl.MapMouseEvent) => {
        const { lng, lat } = e.lngLat;
        new maplibregl.Popup({ closeButton: true, className: "cerebro-tactical-popup" })
          .setLngLat([lng, lat])
          .setHTML(`<div style="color:#fff;font-size:11px;background:#18181b;padding:6px 10px;border-radius:6px;">
            <strong>Tactical Mark</strong><br/>
            ${lat.toFixed(4)}, ${lng.toFixed(4)}
          </div>`)
          .addTo(map);
      };
      map.on("dblclick", handleDoubleTap);
      return () => { map.off("dblclick", handleDoubleTap); };
    } else {
      // Standard mode
      map.touchZoomRotate.enableRotation();
      map.touchPitch.enable();
    }
  }, [gestureMode]);

  // ─── Missile trajectory arcs ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Ensure source/layers exist
    if (!map.getSource("missile-arcs")) {
      map.addSource("missile-arcs", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "missile-arcs-line",
        type: "line",
        source: "missile-arcs",
        paint: {
          "line-color": ["case",
            ["==", ["get", "type"], "ballistic"], "#ef4444",
            "#f59e0b"
          ],
          "line-width": 2.5,
          "line-opacity": 0.85,
          "line-dasharray": [4, 3],
        },
      });
      // Endpoint markers
      map.addLayer({
        id: "missile-arcs-points",
        type: "circle",
        source: "missile-arcs",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 6,
          "circle-color": "#ef4444",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
      });
    }

    if (showMissileArcs) {
      // Fetch trajectory from backend
      fetch(`${API_URL}/api/trajectory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_lat: missileOrigin[1],
          origin_lng: missileOrigin[0],
          target_lat: missileTarget[1],
          target_lng: missileTarget[0],
          trajectory_type: missileType,
          num_points: 80,
        }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.arc_points) {
            const arcLine: GeoJSON.Feature = {
              type: "Feature",
              geometry: {
                type: "LineString",
                coordinates: data.arc_points.map((p: { lng: number; lat: number; alt_km: number }) => [p.lng, p.lat]),
              },
              properties: { type: missileType, range_km: data.range_km || 0 },
            };
            const originPt: GeoJSON.Feature = {
              type: "Feature",
              geometry: { type: "Point", coordinates: missileOrigin },
              properties: { label: "LAUNCH" },
            };
            const targetPt: GeoJSON.Feature = {
              type: "Feature",
              geometry: { type: "Point", coordinates: missileTarget },
              properties: { label: "TARGET" },
            };
            const fc: GeoJSON.FeatureCollection = {
              type: "FeatureCollection",
              features: [arcLine, originPt, targetPt],
            };
            setMissileTrajectoryData(fc);
            const src = map.getSource("missile-arcs") as maplibregl.GeoJSONSource;
            if (src) src.setData(fc);
          }
        })
        .catch(console.error);
      map.setLayoutProperty("missile-arcs-line", "visibility", "visible");
      map.setLayoutProperty("missile-arcs-points", "visibility", "visible");
    } else {
      if (map.getLayer("missile-arcs-line")) map.setLayoutProperty("missile-arcs-line", "visibility", "none");
      if (map.getLayer("missile-arcs-points")) map.setLayoutProperty("missile-arcs-points", "visibility", "none");
    }
  }, [showMissileArcs, missileOrigin, missileTarget, missileType]);

  // ─── Weapons range rings ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (!map.getSource("range-rings")) {
      map.addSource("range-rings", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "range-rings-fill",
        type: "fill",
        source: "range-rings",
        paint: {
          "fill-color": "rgba(239, 68, 68, 0.08)",
        },
      });
      map.addLayer({
        id: "range-rings-line",
        type: "line",
        source: "range-rings",
        paint: {
          "line-color": "#ef4444",
          "line-width": 1.5,
          "line-opacity": 0.6,
          "line-dasharray": [6, 4],
        },
      });
    }

    if (showRangeRings && selectedWeaponId) {
      fetch(`${API_URL}/api/weapons/${selectedWeaponId}/range-rings?lat=${rangeRingCenter[1]}&lng=${rangeRingCenter[0]}`)
        .then(r => r.json())
        .then(data => {
          const fc = data.rings || data;
          setRangeRingData(fc);
          const src = map.getSource("range-rings") as maplibregl.GeoJSONSource;
          if (src && fc.type === "FeatureCollection") src.setData(fc);
        })
        .catch(console.error);
      map.setLayoutProperty("range-rings-fill", "visibility", "visible");
      map.setLayoutProperty("range-rings-line", "visibility", "visible");
    } else {
      if (map.getLayer("range-rings-fill")) map.setLayoutProperty("range-rings-fill", "visibility", "none");
      if (map.getLayer("range-rings-line")) map.setLayoutProperty("range-rings-line", "visibility", "none");
    }
  }, [showRangeRings, selectedWeaponId, rangeRingCenter]);

  // Fetch weapons list on first toggle
  useEffect(() => {
    if (showRangeRings && weaponsList.length === 0) {
      fetch(`${API_URL}/api/weapons`)
        .then(r => r.json())
        .then(data => {
          const list = data.weapons || data || [];
          setWeaponsList(list);
          if (list.length > 0 && !selectedWeaponId) setSelectedWeaponId(list[0].id);
        })
        .catch(console.error);
    }
  }, [showRangeRings]);

  // ─── Timelapse auto-play ───

  useEffect(() => {
    if (accumPlaying && showTimelapse) {
      accumIntervalRef.current = setInterval(() => {
        setTimelapseDay(prev => {
          if (prev >= 0) {
            setAccumPlaying(false);
            return 0;
          }
          return prev + 1;
        });
      }, 800);
    }
    return () => {
      if (accumIntervalRef.current) clearInterval(accumIntervalRef.current);
    };
  }, [accumPlaying, showTimelapse]);

  // ─── Section 18: Radar/sensor coverage layer ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showRadarCoverage && !radarData) {
      fetch(`${API_URL}/api/radar/coverage`)
        .then(r => r.json())
        .then(data => setRadarData(data))
        .catch(console.error);
    }

    if (!map.getSource("radar-coverage")) {
      map.addSource("radar-coverage", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "radar-coverage-fill",
        type: "fill",
        source: "radar-coverage",
        filter: ["==", ["get", "type"], "coverage"],
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": 0.1,
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "radar-coverage-outline",
        type: "line",
        source: "radar-coverage",
        filter: ["==", ["get", "type"], "coverage"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": 1.5,
          "line-opacity": 0.5,
          "line-dasharray": [4, 2],
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "radar-stations",
        type: "circle",
        source: "radar-coverage",
        filter: ["==", ["get", "type"], "station"],
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": 5,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "radar-labels",
        type: "symbol",
        source: "radar-coverage",
        filter: ["==", ["get", "type"], "station"],
        layout: {
          "text-field": ["get", "name"],
          "text-size": 9,
          "text-offset": [0, 1.5],
          visibility: "none",
        },
        paint: {
          "text-color": "#e4e4e7",
          "text-halo-color": "#18181b",
          "text-halo-width": 1,
        },
      });
    }

    const vis = showRadarCoverage ? "visible" : "none";
    ["radar-coverage-fill", "radar-coverage-outline", "radar-stations", "radar-labels"].forEach(id => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });

    if (showRadarCoverage && radarData) {
      const src = map.getSource("radar-coverage") as maplibregl.GeoJSONSource;
      if (src) src.setData(radarData);
    }
  }, [showRadarCoverage, radarData]);

  // ─── Section 18: Drone/UAV activity layer ───

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (showDroneActivity && !droneData) {
      fetch(`${API_URL}/api/drones/activity`)
        .then(r => r.json())
        .then(data => setDroneData(data))
        .catch(console.error);
    }

    if (!map.getSource("drone-activity")) {
      map.addSource("drone-activity", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // Patrol radius
      map.addLayer({
        id: "drone-patrol-fill",
        type: "fill",
        source: "drone-activity",
        filter: ["==", ["get", "type"], "patrol_radius"],
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": 0.08,
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "drone-patrol-outline",
        type: "line",
        source: "drone-activity",
        filter: ["==", ["get", "type"], "patrol_radius"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": 1.5,
          "line-opacity": 0.4,
          "line-dasharray": [2, 3],
        },
        layout: { visibility: "none" },
      });
      // Diamond markers
      map.addLayer({
        id: "drone-diamond",
        type: "fill",
        source: "drone-activity",
        filter: ["==", ["get", "type"], "drone_marker"],
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": 0.8,
        },
        layout: { visibility: "none" },
      });
      map.addLayer({
        id: "drone-diamond-outline",
        type: "line",
        source: "drone-activity",
        filter: ["==", ["get", "type"], "drone_marker"],
        paint: {
          "line-color": "#fff",
          "line-width": 1.5,
        },
        layout: { visibility: "none" },
      });
      // Labels
      map.addLayer({
        id: "drone-labels",
        type: "symbol",
        source: "drone-activity",
        filter: ["==", ["get", "type"], "drone_label"],
        layout: {
          "text-field": ["get", "drone_type"],
          "text-size": 9,
          "text-offset": [0, 2],
          visibility: "none",
        },
        paint: {
          "text-color": "#e4e4e7",
          "text-halo-color": "#18181b",
          "text-halo-width": 1,
        },
      });
    }

    const vis = showDroneActivity ? "visible" : "none";
    ["drone-patrol-fill", "drone-patrol-outline", "drone-diamond", "drone-diamond-outline", "drone-labels"].forEach(id => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    });

    if (showDroneActivity && droneData) {
      const src = map.getSource("drone-activity") as maplibregl.GeoJSONSource;
      if (src) src.setData(droneData);
    }
  }, [showDroneActivity, droneData]);

  // ─── Section 18: Flight path replay animation ───

  function startFlightReplay(track: { lat: number; lng: number }[]) {
    if (track.length < 2) return;
    setReplayTrack(track);
    setReplayProgress(0);
    setShowFlightReplay(true);
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !showFlightReplay || replayTrack.length < 2) return;

    if (!map.getSource("replay-marker")) {
      map.addSource("replay-marker", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("replay-trail", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "replay-trail-line",
        type: "line",
        source: "replay-trail",
        paint: { "line-color": "#22c55e", "line-width": 2, "line-opacity": 0.6 },
      });
      map.addLayer({
        id: "replay-marker-dot",
        type: "circle",
        source: "replay-marker",
        paint: {
          "circle-color": "#22c55e",
          "circle-radius": 8,
          "circle-stroke-width": 3,
          "circle-stroke-color": "#fff",
        },
      });
    }

    let progress = 0;
    const animate = () => {
      progress += 0.005;
      if (progress > 1) {
        setShowFlightReplay(false);
        return;
      }
      setReplayProgress(progress);

      const idx = Math.min(Math.floor(progress * (replayTrack.length - 1)), replayTrack.length - 2);
      const frac = (progress * (replayTrack.length - 1)) - idx;
      const p1 = replayTrack[idx];
      const p2 = replayTrack[idx + 1];
      const lng = p1.lng + (p2.lng - p1.lng) * frac;
      const lat = p1.lat + (p2.lat - p1.lat) * frac;

      // Update marker position
      const markerSrc = map.getSource("replay-marker") as maplibregl.GeoJSONSource;
      if (markerSrc) {
        markerSrc.setData({
          type: "FeatureCollection",
          features: [{
            type: "Feature",
            geometry: { type: "Point", coordinates: [lng, lat] },
            properties: {},
          }],
        });
      }

      // Update trail
      const trailCoords = replayTrack.slice(0, idx + 1).map(p => [p.lng, p.lat]);
      trailCoords.push([lng, lat]);
      const trailSrc = map.getSource("replay-trail") as maplibregl.GeoJSONSource;
      if (trailSrc) {
        trailSrc.setData({
          type: "FeatureCollection",
          features: [{
            type: "Feature",
            geometry: { type: "LineString", coordinates: trailCoords },
            properties: {},
          }],
        });
      }

      replayAnimFrame.current = requestAnimationFrame(animate);
    };
    replayAnimFrame.current = requestAnimationFrame(animate);

    return () => {
      if (replayAnimFrame.current) cancelAnimationFrame(replayAnimFrame.current);
    };
  }, [showFlightReplay, replayTrack]);

  // ─── Phase 15: Multi-angle terrain presets ───

  function setTerrainAngle(preset: "birds_eye" | "oblique" | "horizon" | "N" | "S" | "E" | "W") {
    const map = mapRef.current;
    if (!map) return;
    const center = map.getCenter();
    switch (preset) {
      case "birds_eye":
        map.easeTo({ pitch: 0, bearing: 0, duration: 800 });
        break;
      case "oblique":
        map.easeTo({ pitch: 60, duration: 800 });
        break;
      case "horizon":
        map.easeTo({ pitch: 80, duration: 800 });
        break;
      case "N":
        map.easeTo({ bearing: 0, pitch: 60, duration: 800 });
        break;
      case "S":
        map.easeTo({ bearing: 180, pitch: 60, duration: 800 });
        break;
      case "E":
        map.easeTo({ bearing: 90, pitch: 60, duration: 800 });
        break;
      case "W":
        map.easeTo({ bearing: 270, pitch: 60, duration: 800 });
        break;
    }
  }

  // Command palette items
  const cmdItems = [
    { label: "Toggle Heatmap", key: "h", action: () => setShowHeatmap(p => !p) },
    { label: "Toggle Vessels (AIS)", key: "v", action: () => setShowVessels(p => !p) },
    { label: "Toggle Flights (ADS-B)", key: "a", action: () => setShowFlights(p => !p) },
    { label: "Toggle 3D Terrain", key: "t", action: () => setShowTerrain3D(p => !p) },
    { label: "Measure Distance", key: "", action: () => { setDrawMode("measure"); setMeasurePoints([]); setMeasureResult(null); } },
    { label: "Toggle Split-Screen", key: "d", action: () => setShowSplitScreen(p => !p) },
    { label: "Toggle Maritime Zones", key: "m", action: () => setShowMaritimeZones(p => !p) },
    { label: "Toggle Predictions", key: "p", action: () => setShowPredictions(p => !p) },
    { label: "Toggle Density Grid", key: "g", action: () => setShowDensityGrid(p => !p) },
    { label: "Toggle Trade Flows", key: "o", action: () => setShowTradeFlows(p => !p) },
    { label: "Toggle Frontlines", key: "f", action: () => setShowFrontlines(p => !p) },
    { label: "Toggle Webcams", key: "w", action: () => setShowWebcams(p => !p) },
    { label: "Toggle Annotations", key: "n", action: () => setShowAnnotations(p => !p) },
    { label: "Toggle HUD Mode", key: "i", action: () => setShowHudMode(p => !p) },
    { label: "Toggle Satellite Orbits", key: "x", action: () => setShowSatelliteOrbits(p => !p) },
    { label: "Toggle Pulse Beacons", key: "b", action: () => setShowPulseBeacons(p => !p) },
    { label: "Toggle 3D Extrusions", key: "e", action: () => setShowExtrudedCountries(p => !p) },
    { label: "Toggle Photo Pins", key: "", action: () => setShowPhotoPins(p => !p) },
    { label: "Toggle PiP View", key: "", action: () => setShowPiP(p => !p) },
    { label: "Toggle Sun Simulation", key: "", action: () => { setShowSunSim(p => !p); setSunSimTime(new Date()); } },
    { label: "Toggle Glassmorphism", key: "", action: () => setShowGlassmorphism(p => !p) },
    { label: "Save Current View", key: "⌘S", action: () => saveCurrentView() },
    { label: "Reset View", key: "r", action: () => mapRef.current?.flyTo({ center: [20, 30], zoom: 2, pitch: 0, bearing: 0, duration: 1000 }) },
    { label: "Bird's Eye View", key: "", action: () => setTerrainAngle("birds_eye") },
    { label: "Oblique View (60°)", key: "", action: () => setTerrainAngle("oblique") },
    { label: "Horizon View (80°)", key: "", action: () => setTerrainAngle("horizon") },
    { label: "View from North", key: "", action: () => setTerrainAngle("N") },
    { label: "View from South", key: "", action: () => setTerrainAngle("S") },
    { label: "View from East", key: "", action: () => setTerrainAngle("E") },
    { label: "View from West", key: "", action: () => setTerrainAngle("W") },
    { label: "Flythrough: Baghdad", key: "", action: () => startFlythrough([44.4, 33.3], "Baghdad") },
    { label: "Flythrough: Kyiv", key: "", action: () => startFlythrough([30.5, 50.4], "Kyiv") },
    { label: "Flythrough: South China Sea", key: "", action: () => startFlythrough([112.0, 16.0], "SCS") },
    { label: "Open Events Page", key: "", action: () => window.location.href = "/events" },
    { label: "Open Entities Page", key: "", action: () => window.location.href = "/entities" },
    { label: "Open Query Interface", key: "", action: () => window.location.href = "/query" },
    { label: "Open Risk Dashboard", key: "", action: () => window.location.href = "/risk" },
    { label: "Keyboard Shortcuts Help", key: "?", action: () => setShowShortcutHelp(true) },
    { label: "Toggle Particle Flow", key: "", action: () => setShowParticleFlow(p => !p) },
    { label: "Toggle Cluster Breathing", key: "", action: () => setShowClusterBreathing(p => !p) },
    { label: "Toggle Risk Odometer", key: "", action: () => setShowRiskOdometer(p => !p) },
    { label: "Toggle Disease Spread", key: "", action: () => setShowDiseaseSpread(p => !p) },
    { label: "Toggle Storm Tracks", key: "", action: () => setShowStormTracks(p => !p) },
    { label: "Toggle News Ticker", key: "", action: () => setShowNewsTicker(p => !p) },
    { label: "Toggle Documentary Mode", key: "", action: () => setShowDocumentaryMode(p => !p) },
    { label: "Toggle Volumetric Heatmap", key: "", action: () => setShowVolumetricHeat(p => !p) },
    { label: "Toggle 3D Bar Charts", key: "", action: () => setShow3DBarCharts(p => !p) },
    { label: "Record Timelapse Video", key: "", action: () => isRecordingTimelapse ? stopTimelapseCapture() : startTimelapseCapture() },
    { label: "Switch Tactical Gestures", key: "", action: () => setGestureMode(g => g === "standard" ? "tactical" : "standard") },
    { label: "Toggle Radar Coverage", key: "", action: () => setShowRadarCoverage(p => !p) },
    { label: "Toggle Drone/UAV Activity", key: "", action: () => setShowDroneActivity(p => !p) },
    { label: "Toggle Missile Arcs", key: "", action: () => setShowMissileArcs(p => !p) },
    { label: "Toggle Range Rings", key: "", action: () => setShowRangeRings(p => !p) },
    { label: "Timelapse Auto-Play", key: "", action: () => { if (!showTimelapse) { setShowTimelapse(true); } setTimelapseDay(-timelapseRange); setAccumPlaying(true); } },
    { label: "Grand Tour Flythrough", key: "", action: () => startMultiWaypointFlythrough([
      { coords: [30.5, 50.4], name: "Kyiv", zoom: 10, pitch: 55, bearing: 30, dwell: 2500 },
      { coords: [44.4, 33.3], name: "Baghdad", zoom: 11, pitch: 60, bearing: -20, dwell: 2500 },
      { coords: [56.3, 26.6], name: "Hormuz", zoom: 9, pitch: 50, bearing: 90, dwell: 2500 },
      { coords: [112.0, 16.0], name: "SCS", zoom: 6, pitch: 45, bearing: 0, dwell: 3000 },
    ]) },
  ];

  const filteredCmdItems = cmdQuery
    ? cmdItems.filter(item => item.label.toLowerCase().includes(cmdQuery.toLowerCase()))
    : cmdItems;

  return (
    <div className="h-full w-full bg-zinc-950 text-white flex flex-col">
      <div className="flex flex-1 overflow-hidden relative">
        {/* ── Floating map controls ── */}
        <div className="absolute top-2 left-2 z-20 flex items-center gap-2">
          <button
            onClick={() => setSidebarCollapsed((p) => !p)}
            className="w-8 h-8 rounded-lg bg-zinc-900/90 border border-zinc-700/50 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-800 transition-all text-xs backdrop-blur-sm"
            title={sidebarCollapsed ? "Show layer controls" : "Hide layer controls"}
          >
            {sidebarCollapsed ? "☰" : "✕"}
          </button>
          {sidebarCollapsed && (
            <div className="flex items-center gap-2 bg-zinc-900/80 backdrop-blur-sm rounded-lg border border-zinc-700/30 px-2.5 py-1.5 text-[10px] text-zinc-400">
              {loading && <span className="text-cyan-400 animate-pulse">Loading...</span>}
              <span>{featureCount.toLocaleString()} on map</span>
              {vessels.length > 0 && <span className="text-blue-400">{vessels.length} vessels</span>}
              {flights.length > 0 && <span className="text-zinc-400">{flights.length} flights</span>}
              <button
                onClick={() => setShowSplitScreen((p) => !p)}
                className={`px-1.5 py-0.5 rounded font-medium transition-colors ${
                  showSplitScreen
                    ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                    : "bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-700"
                }`}
                title="Split-screen dual view (D)"
              >
                {showSplitScreen ? "⬛" : "◫"}
              </button>
              <button
                onClick={() => setShowShortcutHelp((p) => !p)}
                className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-700 font-medium"
                title="Keyboard shortcuts (?)"
              >
                ⌨
              </button>
            </div>
          )}
        </div>

        {/* ── Control Panel ── */}
        <aside className={`${sidebarCollapsed ? "w-0 overflow-hidden opacity-0 p-0 border-0" : "w-64 overflow-y-auto p-3 border-r border-zinc-800"} transition-all duration-300 space-y-4 text-xs z-10 shrink-0 ${showGlassmorphism ? "cerebro-glassmorphism" : "bg-zinc-900/80"}`}>
          {/* Source Layers */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Source Layers
            </h3>
            {SOURCE_LIST.map((s) => (
              <label key={s} className="flex items-center gap-2 py-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enabledSources.has(s)}
                  onChange={() => toggleSource(s)}
                  className="rounded border-zinc-600 bg-zinc-800 text-cyan-500 focus:ring-0 w-3.5 h-3.5"
                />
                <span className={enabledSources.has(s) ? "text-zinc-200" : "text-zinc-600"}>
                  {s.replace("_", " ")}
                </span>
              </label>
            ))}
          </section>

          {/* SIGINT Layers */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              SIGINT Tracking
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={showVessels}
                onChange={(e) => setShowVessels(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              <span className={showVessels ? "text-zinc-200" : "text-zinc-600"}>
                Vessels (AIS)
              </span>
              {vessels.length > 0 && (
                <span className="text-[9px] text-zinc-600 ml-auto">{vessels.length}</span>
              )}
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={showFlights}
                onChange={(e) => setShowFlights(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-zinc-400 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-zinc-400" />
              <span className={showFlights ? "text-zinc-200" : "text-zinc-600"}>
                Flights (ADS-B)
              </span>
              {flights.length > 0 && (
                <span className="text-[9px] text-zinc-600 ml-auto">{flights.length}</span>
              )}
            </label>
          </section>

          {/* Category Filters */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Categories
            </h3>
            {CATEGORY_LIST.map((cat) => (
              <label key={cat} className="flex items-center gap-2 py-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enabledCategories.has(cat)}
                  onChange={() => toggleCategory(cat)}
                  className="rounded border-zinc-600 bg-zinc-800 focus:ring-0 w-3.5 h-3.5"
                />
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: CATEGORY_COLORS[cat] }}
                />
                <span className={enabledCategories.has(cat) ? "text-zinc-200" : "text-zinc-600"}>
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </span>
              </label>
            ))}
          </section>

          {/* Severity Filter */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Min Severity: {severityMin}
            </h3>
            <input
              type="range"
              min={0}
              max={100}
              value={severityMin}
              onChange={(e) => setSeverityMin(Number(e.target.value))}
              className="w-full accent-cyan-500"
            />
          </section>

          {/* Time Range */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Time Range
            </h3>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300"
            >
              <option value={6}>Last 6 hours</option>
              <option value={24}>Last 24 hours</option>
              <option value={72}>Last 3 days</option>
              <option value={168}>Last 7 days</option>
              <option value={720}>Last 30 days</option>
              <option value={8760}>All time</option>
            </select>
          </section>

          {/* Heatmap Toggle */}
          <section>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showHeatmap}
                onChange={(e) => setShowHeatmap(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-orange-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="text-zinc-200">Heatmap Layer</span>
            </label>
          </section>

          {/* Geospatial Overlays */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Geospatial Overlays
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={showMaritimeZones}
                onChange={(e) => setShowMaritimeZones(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-cyan-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-cyan-500" />
              <span className={showMaritimeZones ? "text-zinc-200" : "text-zinc-600"}>
                Maritime Zones
              </span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={showPredictions}
                onChange={(e) => setShowPredictions(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-orange-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-orange-500" />
              <span className={showPredictions ? "text-zinc-200" : "text-zinc-600"}>
                Predictive Positions
              </span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={showDensityGrid}
                onChange={(e) => setShowDensityGrid(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-yellow-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-yellow-500" />
              <span className={showDensityGrid ? "text-zinc-200" : "text-zinc-600"}>
                Smart Density Grid
              </span>
            </label>
          </section>

          {/* Terrain & Analysis */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Terrain & Analysis
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={showTerrain3D}
                onChange={(e) => setShowTerrain3D(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className={showTerrain3D ? "text-zinc-200" : "text-zinc-600"}>
                3D Terrain
              </span>
            </label>
            <div className="mt-2">
              <label className="text-zinc-500 text-[10px] block mb-1">Heatmap Category</label>
              <select
                value={heatmapCategory}
                onChange={(e) => setHeatmapCategory(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300"
              >
                <option value="all">All Categories</option>
                {CATEGORY_LIST.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat.charAt(0).toUpperCase() + cat.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </section>

          {/* Imagery & Timelapse */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Imagery & Timelapse
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={showSatelliteSwipe}
                onChange={(e) => setShowSatelliteSwipe(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-purple-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-purple-500" />
              <span className={showSatelliteSwipe ? "text-zinc-200" : "text-zinc-600"}>
                Satellite Swipe
              </span>
            </label>
            {showSatelliteSwipe && (
              <div className="mt-1 ml-5">
                <label className="text-zinc-500 text-[10px] block mb-1">
                  Swipe: {swipePosition}%
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={swipePosition}
                  onChange={(e) => setSwipePosition(Number(e.target.value))}
                  className="w-full accent-purple-500"
                />
                <div className="flex justify-between text-[9px] text-zinc-600 mt-0.5">
                  <span>Satellite</span>
                  <span>Dark Map</span>
                </div>
              </div>
            )}
            <label className="flex items-center gap-2 py-1 cursor-pointer mt-1">
              <input
                type="checkbox"
                checked={showTimelapse}
                onChange={(e) => setShowTimelapse(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-amber-500 focus:ring-0 w-3.5 h-3.5"
              />
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className={showTimelapse ? "text-zinc-200" : "text-zinc-600"}>
                Historical Timelapse
              </span>
            </label>
            {showTimelapse && (
              <div className="mt-1 ml-5">
                <label className="text-zinc-500 text-[10px] block mb-1">
                  Day: {timelapseDay === 0 ? "Today" : `${Math.abs(timelapseDay)}d ago`}
                </label>
                <input
                  type="range"
                  min={-timelapseRange}
                  max={0}
                  value={timelapseDay}
                  onChange={(e) => setTimelapseDay(Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
                <div className="flex justify-between text-[9px] text-zinc-600 mt-0.5">
                  <span>{timelapseRange}d ago</span>
                  <span>Today</span>
                </div>
                <div className="flex gap-1 mt-1">
                  <button onClick={() => { setTimelapseDay(-timelapseRange); setAccumPlaying(true); }}
                    className={`flex-1 px-2 py-0.5 rounded text-[10px] border transition-colors ${
                      accumPlaying
                        ? "bg-amber-500/20 border-amber-500/50 text-amber-400"
                        : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200"
                    }`}>
                    {accumPlaying ? "⏸ Pause" : "▶ Auto-Play"}
                  </button>
                  <button onClick={() => { setAccumPlaying(false); setTimelapseDay(-timelapseRange); }}
                    className="px-2 py-0.5 rounded text-[10px] border bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors">
                    ⏮ Reset
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Phase 13: Animations & Video */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Animations & Video
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showTradeFlows}
                onChange={(e) => setShowTradeFlows(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              <span className={showTradeFlows ? "text-zinc-200" : "text-zinc-600"}>Trade Flow Arcs</span>
            </label>
            {showTradeFlows && (
              <div className="ml-5 mt-1">
                <select value={tradeFlowType} onChange={(e) => setTradeFlowType(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300 text-[10px]">
                  <option value="all">All Types</option>
                  <option value="trade">Trade</option>
                  <option value="energy">Energy</option>
                  <option value="arms">Arms</option>
                  <option value="aid">Aid</option>
                </select>
              </div>
            )}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showFrontlines}
                onChange={(e) => setShowFrontlines(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-red-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-red-400" />
              <span className={showFrontlines ? "text-zinc-200" : "text-zinc-600"}>Conflict Frontlines</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showWebcams}
                onChange={(e) => setShowWebcams(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-violet-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-violet-400" />
              <span className={showWebcams ? "text-zinc-200" : "text-zinc-600"}>Public Webcams</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showStreetImagery}
                onChange={(e) => setShowStreetImagery(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-teal-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-teal-400" />
              <span className={showStreetImagery ? "text-zinc-200" : "text-zinc-600"}>Street Imagery</span>
            </label>
          </section>

          {/* Phase 13: Drawing & Annotations */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Drawing Tools
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showAnnotations}
                onChange={(e) => setShowAnnotations(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-orange-500 focus:ring-0 w-3.5 h-3.5" />
              <span className={showAnnotations ? "text-zinc-200" : "text-zinc-600"}>Show Annotations</span>
            </label>
            <div className="flex gap-1 mt-1">
              {(["marker", "line", "polygon", "freehand", "measure"] as const).map((mode) => (
                <button key={mode} onClick={() => { setDrawMode(drawMode === mode ? null : mode); setMeasurePoints([]); setMeasureResult(null); }}
                  className={`px-2 py-1 rounded text-[10px] border transition-colors ${
                    drawMode === mode
                      ? "bg-orange-500/20 border-orange-500/50 text-orange-400"
                      : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200"
                  }`}>
                  {mode === "marker" ? "📍" : mode === "line" ? "╱" : mode === "polygon" ? "⬡" : mode === "freehand" ? "✏️" : "📏"}
                </button>
              ))}
            </div>
            {drawMode && (
              <div className="mt-1 text-[10px] text-orange-400 animate-pulse">
                {drawMode === "measure"
                  ? measurePoints.length === 0
                    ? "Click start point"
                    : measurePoints.length === 1
                      ? "Click end point"
                      : "Measurement complete"
                  : `Click map to place ${drawMode}`}
              </div>
            )}
            {measureResult && (
              <div className="mt-1 p-2 bg-zinc-800/80 border border-amber-500/30 rounded text-[10px]">
                <div className="text-amber-400 font-semibold">📏 Measurement</div>
                <div className="text-zinc-300">{measureResult.distance_km.toFixed(2)} km ({(measureResult.distance_km * 0.539957).toFixed(2)} nm)</div>
                <div className="text-zinc-500">Bearing: {measureResult.bearing.toFixed(1)}°</div>
              </div>
            )}
          </section>

          {/* Phase 13: Situation Replay */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Situation Replay
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showReplayControls}
                onChange={(e) => setShowReplayControls(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-rose-500 focus:ring-0 w-3.5 h-3.5" />
              <span className={showReplayControls ? "text-zinc-200" : "text-zinc-600"}>24hr Replay</span>
            </label>
            {showReplayControls && (
              <div className="mt-1 space-y-1">
                <div className="flex items-center gap-2">
                  <button onClick={() => setReplayPlaying(!replayPlaying)}
                    className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded px-2 py-0.5 text-[10px] text-zinc-300">
                    {replayPlaying ? "⏸ Pause" : "▶ Play"}
                  </button>
                  <button onClick={() => { setReplayHour(0); setReplayPlaying(false); }}
                    className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded px-2 py-0.5 text-[10px] text-zinc-300">
                    ⏮ Reset
                  </button>
                  <span className="text-[10px] text-zinc-400 ml-auto">
                    {String(replayHour).padStart(2, "0")}:00
                  </span>
                </div>
                <input type="range" min={0} max={23} value={replayHour}
                  onChange={(e) => setReplayHour(Number(e.target.value))}
                  className="w-full accent-rose-500" />
                <div className="flex justify-between text-[9px] text-zinc-600">
                  <span>00:00</span><span>12:00</span><span>23:00</span>
                </div>
              </div>
            )}
          </section>

          {/* Phase 13: Cinematic Flythrough */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Cinematic Flythrough
            </h3>
            <div className="space-y-1">
              {[
                { name: "Baghdad", coords: [44.4, 33.3] as [number, number] },
                { name: "Kyiv", coords: [30.5, 50.4] as [number, number] },
                { name: "South China Sea", coords: [112.0, 16.0] as [number, number] },
                { name: "Strait of Hormuz", coords: [56.3, 26.6] as [number, number] },
              ].map(({ name, coords }) => (
                <button key={name} onClick={() => startFlythrough(coords, name)}
                  className="w-full text-left bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-1 text-[10px] text-zinc-300 transition-colors">
                  🎬 {name}
                </button>
              ))}
              <button onClick={() => startMultiWaypointFlythrough([
                { coords: [30.5, 50.4], name: "Kyiv", zoom: 10, pitch: 55, bearing: 30, dwell: 2500 },
                { coords: [44.4, 33.3], name: "Baghdad", zoom: 11, pitch: 60, bearing: -20, dwell: 2500 },
                { coords: [56.3, 26.6], name: "Hormuz", zoom: 9, pitch: 50, bearing: 90, dwell: 2500 },
                { coords: [112.0, 16.0], name: "SCS", zoom: 6, pitch: 45, bearing: 0, dwell: 3000 },
              ])}
                disabled={flythroughActive}
                className={`w-full text-left rounded px-2 py-1 text-[10px] transition-colors border ${
                  flythroughActive
                    ? "bg-yellow-500/10 border-yellow-500/30 text-yellow-400 animate-pulse"
                    : "bg-zinc-800 hover:bg-zinc-700 border-zinc-700 text-zinc-300"
                }`}>
                🌐 {flythroughActive ? "Flying..." : "Grand Tour (4 hotspots)"}
              </button>
            </div>
          </section>

          {/* Phase 14: Immersive & Holographic */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Immersive / 3D
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showHudMode}
                onChange={(e) => setShowHudMode(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className={showHudMode ? "text-emerald-300" : "text-zinc-600"}>Iron Man HUD</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showGlassmorphism}
                onChange={(e) => setShowGlassmorphism(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-sky-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-sky-400" />
              <span className={showGlassmorphism ? "text-zinc-200" : "text-zinc-600"}>Glassmorphism</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showSatelliteOrbits}
                onChange={(e) => setShowSatelliteOrbits(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-cyan-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              <span className={showSatelliteOrbits ? "text-zinc-200" : "text-zinc-600"}>Satellite Orbits</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showPulseBeacons}
                onChange={(e) => setShowPulseBeacons(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-yellow-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-yellow-400" />
              <span className={showPulseBeacons ? "text-zinc-200" : "text-zinc-600"}>Pulse Beacons</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showExtrudedCountries}
                onChange={(e) => setShowExtrudedCountries(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-pink-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-pink-400" />
              <span className={showExtrudedCountries ? "text-zinc-200" : "text-zinc-600"}>3D Extrusions</span>
            </label>
            {showExtrudedCountries && (
              <div className="ml-5 mt-1">
                <select value={extrusionMetric} onChange={(e) => setExtrusionMetric(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300 text-[10px]">
                  <option value="risk_score">Risk Score</option>
                  <option value="event_count">Event Count</option>
                  <option value="threat_level">Threat Level</option>
                </select>
              </div>
            )}

            {/* Projection mode */}
            <div className="mt-2">
              <label className="text-zinc-500 text-[10px] block mb-1">Projection</label>
              <div className="flex gap-1">
                {(["globe", "mercator"] as const).map((mode) => (
                  <button key={mode} onClick={() => setProjectionMode(mode)}
                    className={`flex-1 px-2 py-1 rounded text-[10px] border transition-colors ${
                      projectionMode === mode
                        ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-400"
                        : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200"
                    }`}>
                    {mode === "globe" ? "🌍 Globe" : "🗺️ Flat"}
                  </button>
                ))}
              </div>
            </div>

            {/* WebXR / AR stubs */}
            <div className="mt-2 space-y-1">
              <button onClick={() => setShowWebXR(true)}
                className="w-full text-left bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-1 text-[10px] text-zinc-400 border border-zinc-700 transition-colors">
                🥽 WebXR VR Mode
              </button>
              <button onClick={() => setShowAR(true)}
                className="w-full text-left bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-1 text-[10px] text-zinc-400 border border-zinc-700 transition-colors">
                📱 AR Camera Overlay
              </button>
            </div>
          </section>

          {/* Visual Effects */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Visual Effects
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showParticleFlow}
                onChange={(e) => setShowParticleFlow(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-teal-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-teal-400" />
              <span className={showParticleFlow ? "text-teal-300" : "text-zinc-600"}>Particle Flow</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showClusterBreathing}
                onChange={(e) => setShowClusterBreathing(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              <span className={showClusterBreathing ? "text-blue-300" : "text-zinc-600"}>Cluster Breathing</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showRiskOdometer}
                onChange={(e) => setShowRiskOdometer(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-orange-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-orange-400" />
              <span className={showRiskOdometer ? "text-orange-300" : "text-zinc-600"}>Risk Odometer</span>
            </label>
          </section>

          {/* Phase 16: Data Overlays */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Data Overlays
            </h3>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showDiseaseSpread}
                onChange={(e) => setShowDiseaseSpread(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-red-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-red-400" />
              <span className={showDiseaseSpread ? "text-red-300" : "text-zinc-600"}>Disease Spread</span>
            </label>
            {showDiseaseSpread && (
              <div className="ml-5 mt-1 space-y-1">
                <div className="flex items-center gap-2">
                  <button onClick={() => { setDiseaseDay(0); setDiseaseAnimPlaying(true); }}
                    className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded px-2 py-0.5 text-[9px] text-zinc-300">
                    {diseaseAnimPlaying ? "⏹ Stop" : "▶ Play"}
                  </button>
                  <span className="text-[10px] text-zinc-400">Day {diseaseDay}/29</span>
                </div>
                <input type="range" min={0} max={29} value={diseaseDay}
                  onChange={(e) => setDiseaseDay(Number(e.target.value))}
                  className="w-full accent-red-500" />
              </div>
            )}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showStormTracks}
                onChange={(e) => setShowStormTracks(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-yellow-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-yellow-400" />
              <span className={showStormTracks ? "text-yellow-300" : "text-zinc-600"}>Storm Tracks</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showNewsTicker}
                onChange={(e) => setShowNewsTicker(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-cyan-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              <span className={showNewsTicker ? "text-cyan-300" : "text-zinc-600"}>News Ticker</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showVolumetricHeat}
                onChange={(e) => setShowVolumetricHeat(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-orange-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-orange-400" />
              <span className={showVolumetricHeat ? "text-orange-300" : "text-zinc-600"}>3D Heatmap</span>
            </label>
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={show3DBarCharts}
                onChange={(e) => setShow3DBarCharts(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-pink-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-pink-400" />
              <span className={show3DBarCharts ? "text-pink-300" : "text-zinc-600"}>3D Bar Charts</span>
            </label>

            {/* Missile trajectory arcs */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showMissileArcs}
                onChange={(e) => setShowMissileArcs(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-red-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-red-500" />
              <span className={showMissileArcs ? "text-red-300" : "text-zinc-600"}>Missile Arcs</span>
            </label>
            {showMissileArcs && (
              <div className="ml-5 mt-1 space-y-1">
                <select value={missileType} onChange={(e) => setMissileType(e.target.value as "ballistic" | "cruise")}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300 text-[10px]">
                  <option value="ballistic">Ballistic</option>
                  <option value="cruise">Cruise</option>
                </select>
                <div className="text-[9px] text-zinc-500">
                  Origin: {missileOrigin[1].toFixed(1)}°, {missileOrigin[0].toFixed(1)}°
                </div>
                <div className="text-[9px] text-zinc-500">
                  Target: {missileTarget[1].toFixed(1)}°, {missileTarget[0].toFixed(1)}°
                </div>
                <div className="text-[9px] text-zinc-600 italic">
                  Click map to set origin/target
                </div>
              </div>
            )}

            {/* Weapons range rings */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showRangeRings}
                onChange={(e) => setShowRangeRings(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-amber-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className={showRangeRings ? "text-amber-300" : "text-zinc-600"}>Range Rings</span>
            </label>
            {showRangeRings && weaponsList.length > 0 && (
              <div className="ml-5 mt-1 space-y-1">
                <select value={selectedWeaponId} onChange={(e) => setSelectedWeaponId(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300 text-[10px]">
                  {weaponsList.map(w => (
                    <option key={w.id} value={w.id}>{w.name} ({w.range_km} km)</option>
                  ))}
                </select>
                <div className="text-[9px] text-zinc-500">
                  Center: {rangeRingCenter[1].toFixed(1)}°, {rangeRingCenter[0].toFixed(1)}°
                </div>
              </div>
            )}

            {/* Radar coverage */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showRadarCoverage}
                onChange={(e) => setShowRadarCoverage(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className={showRadarCoverage ? "text-emerald-300" : "text-zinc-600"}>Radar Coverage</span>
            </label>

            {/* Drone/UAV activity */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showDroneActivity}
                onChange={(e) => setShowDroneActivity(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-purple-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-purple-400" />
              <span className={showDroneActivity ? "text-purple-300" : "text-zinc-600"}>Drone/UAV Activity</span>
            </label>

            {/* Documentary mode */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showDocumentaryMode}
                onChange={(e) => setShowDocumentaryMode(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-indigo-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-indigo-400" />
              <span className={showDocumentaryMode ? "text-indigo-300" : "text-zinc-600"}>Documentary Mode</span>
            </label>

            {/* Timelapse capture */}
            <div className="mt-2">
              <button onClick={isRecordingTimelapse ? stopTimelapseCapture : startTimelapseCapture}
                className={`w-full text-left rounded px-2 py-1.5 text-[10px] border transition-colors flex items-center gap-2 ${
                  isRecordingTimelapse
                    ? "bg-red-500/20 border-red-500/50 text-red-400"
                    : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-700"
                }`}>
                {isRecordingTimelapse ? "⏹ Stop Recording" : "🎬 Record Timelapse"}
                {isRecordingTimelapse && <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />}
              </button>
            </div>

            {/* Gesture mode */}
            <div className="mt-2">
              <label className="text-zinc-500 text-[10px] block mb-1">Gesture Mode</label>
              <div className="flex gap-1">
                {(["standard", "tactical"] as const).map(mode => (
                  <button key={mode} onClick={() => setGestureMode(mode)}
                    className={`flex-1 px-2 py-1 rounded text-[10px] border transition-colors ${
                      gestureMode === mode
                        ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-400"
                        : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200"
                    }`}>
                    {mode === "standard" ? "🖱️ Standard" : "🎯 Tactical"}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Phase 15: Camera & Lighting */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-2 tracking-wider">
              Camera & Lighting
            </h3>
            {/* Multi-angle terrain presets */}
            <div className="mb-2">
              <label className="text-zinc-500 text-[10px] block mb-1">Terrain Angle</label>
              <div className="grid grid-cols-4 gap-1">
                {([
                  ["birds_eye", "⬇ Top"],
                  ["oblique", "📐 60°"],
                  ["horizon", "🌅 80°"],
                  ["N", "⬆ N"],
                  ["S", "⬇ S"],
                  ["E", "➡ E"],
                  ["W", "⬅ W"],
                ] as [string, string][]).map(([preset, label]) => (
                  <button key={preset} onClick={() => setTerrainAngle(preset as "birds_eye" | "oblique" | "horizon" | "N" | "S" | "E" | "W")}
                    className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded px-1 py-1 text-[9px] text-zinc-400 hover:text-zinc-200 transition-colors">
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* SunCalc time-of-day lighting */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showSunSim}
                onChange={(e) => {
                  setShowSunSim(e.target.checked);
                  if (e.target.checked && !sunSimTime) setSunSimTime(new Date());
                }}
                className="rounded border-zinc-600 bg-zinc-800 text-amber-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              <span className={showSunSim ? "text-amber-300" : "text-zinc-600"}>Sun Simulation</span>
            </label>
            {showSunSim && sunSimTime && (
              <div className="ml-5 mt-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-400">
                    {sunSimTime.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                <input type="range" min={0} max={1440} step={10}
                  value={sunSimTime.getHours() * 60 + sunSimTime.getMinutes()}
                  onChange={(e) => {
                    const mins = Number(e.target.value);
                    const d = new Date(sunSimTime);
                    d.setHours(Math.floor(mins / 60), mins % 60, 0, 0);
                    setSunSimTime(d);
                  }}
                  className="w-full accent-amber-500" />
                <div className="flex justify-between text-[9px] text-zinc-600">
                  <span>00:00</span><span>12:00</span><span>24:00</span>
                </div>
              </div>
            )}

            {/* Photo pins */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showPhotoPins}
                onChange={(e) => setShowPhotoPins(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-rose-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-rose-400" />
              <span className={showPhotoPins ? "text-rose-300" : "text-zinc-600"}>Photo Pins</span>
            </label>

            {/* PiP inset view */}
            <label className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={showPiP}
                onChange={(e) => setShowPiP(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-violet-500 focus:ring-0 w-3.5 h-3.5" />
              <span className="w-2 h-2 rounded-full bg-violet-400" />
              <span className={showPiP ? "text-violet-300" : "text-zinc-600"}>Picture-in-Picture</span>
            </label>

            {/* Command palette hint */}
            <div className="mt-2">
              <button onClick={() => { setShowCommandPalette(true); setCmdQuery(""); }}
                className="w-full text-left bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded px-2 py-1.5 text-[10px] text-zinc-400 transition-colors flex items-center gap-2">
                <span>🔍 Command Palette</span>
                <kbd className="ml-auto bg-zinc-700 border border-zinc-600 rounded px-1 py-0.5 text-[9px] text-zinc-500 font-mono">⌘K</kbd>
              </button>
            </div>
          </section>

          {/* Saved Views */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[10px] uppercase text-zinc-500 font-semibold tracking-wider">
                Saved Views
              </h3>
              <button
                onClick={() => { setShowViewPanel(!showViewPanel); loadSavedViews(); }}
                className="text-cyan-400 hover:text-cyan-300 text-[10px]"
              >
                {showViewPanel ? "Hide" : "Show"}
              </button>
            </div>
            <button
              onClick={saveCurrentView}
              className="w-full bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded px-2 py-1.5 transition-colors mb-2"
            >
              Save Current View
            </button>
            {showViewPanel && savedViews.length > 0 && (
              <div className="space-y-1">
                {savedViews.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => restoreView(v)}
                    className="w-full text-left bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-1.5 text-zinc-300 transition-colors"
                  >
                    {v.name}
                  </button>
                ))}
              </div>
            )}
          </section>
        </aside>

        {/* ── Map Container(s) ── */}
        <div className="flex-1 relative flex h-full">
          {/* Primary map */}
          <div className={`relative h-full ${showSplitScreen ? "w-1/2" : "w-full"}`}>
            <div ref={mapContainer} className="w-full h-full" />

            {/* Satellite swipe divider line */}
            {showSatelliteSwipe && (
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-white/60 pointer-events-none z-10"
                style={{ left: `${100 - swipePosition}%` }}
              >
                <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 bg-zinc-900/90 border border-white/40 rounded-full px-2 py-1 text-[9px] text-white whitespace-nowrap">
                  ◀ Satellite | Dark ▶
                </div>
              </div>
            )}

            {/* Timelapse date indicator */}
            {showTimelapse && (
              <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-zinc-900/90 border border-amber-500/30 rounded-lg px-4 py-2 z-10 text-center">
                <div className="text-amber-400 text-xs font-semibold">
                  {new Date(Date.now() + timelapseDay * 86400000).toLocaleDateString(undefined, {
                    weekday: "short", month: "short", day: "numeric", year: "numeric",
                  })}
                </div>
                <div className="text-[9px] text-zinc-500 mt-0.5">
                  Historical Timelapse Mode
                </div>
              </div>
            )}

            {/* Replay time HUD */}
            {showReplayControls && (
              <div className="absolute top-3 right-3 bg-zinc-900/90 border border-rose-500/30 rounded-lg px-4 py-2 z-10 text-center">
                <div className="text-rose-400 text-lg font-mono font-bold">
                  {String(replayHour).padStart(2, "0")}:00
                </div>
                <div className="text-[9px] text-zinc-500">
                  {replayPlaying ? "▶ Playing" : "⏸ Paused"} — Situation Replay
                </div>
              </div>
            )}

            {/* Drawing mode indicator */}
            {drawMode && (
              <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-zinc-900/90 border border-orange-500/30 rounded-lg px-4 py-2 z-10 text-center">
                <div className="text-orange-400 text-xs font-semibold">
                  Drawing: {drawMode.charAt(0).toUpperCase() + drawMode.slice(1)}
                </div>
                <div className="text-[9px] text-zinc-500">Click map to place • Press Esc to cancel</div>
              </div>
            )}

            {/* Phase 14: Iron Man HUD overlay */}
            {showHudMode && (
              <>
                <div className="cerebro-hud-scanline" />
                <div className="cerebro-hud-overlay">
                  <div className="cerebro-hud-corner tl" />
                  <div className="cerebro-hud-corner tr" />
                  <div className="cerebro-hud-corner bl" />
                  <div className="cerebro-hud-corner br" />
                  {/* HUD telemetry readout */}
                  <div className="absolute top-14 left-4 text-[10px] font-mono text-emerald-400/70 space-y-1 pointer-events-none">
                    <div>SYS: CEREBRO v14.0</div>
                    <div>STATUS: OPERATIONAL</div>
                    <div>EVENTS: {featureCount.toLocaleString()}</div>
                    <div>VESSELS: {vessels.length}</div>
                    <div>FLIGHTS: {flights.length}</div>
                    <div>UTC: {new Date().toISOString().slice(11, 19)}</div>
                  </div>
                  {/* Targeting reticle center */}
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16 pointer-events-none">
                    <div className="absolute inset-0 border border-emerald-400/30 rounded-full" />
                    <div className="absolute top-1/2 left-0 right-0 h-px bg-emerald-400/20" />
                    <div className="absolute left-1/2 top-0 bottom-0 w-px bg-emerald-400/20" />
                  </div>
                </div>
              </>
            )}

            {/* Phase 14: 3D Extrusion data HUD */}
            {showExtrudedCountries && extrusionData && (
              <div className="absolute bottom-16 right-3 bg-zinc-900/90 border border-pink-500/30 rounded-lg px-3 py-2 z-10 max-w-[180px]">
                <div className="text-[10px] text-pink-400 font-semibold mb-1">
                  {extrusionMetric.replace("_", " ").toUpperCase()}
                </div>
                {extrusionData.slice(0, 8).map((d, i) => (
                  <div key={d.country_code} className="flex items-center gap-2 text-[10px]">
                    <span className="text-zinc-500 w-3">{i + 1}</span>
                    <span className="text-zinc-300 w-6">{d.country_code}</span>
                    <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div className="h-full bg-pink-500 rounded-full" style={{ width: `${(d.normalized || 0) * 100}%` }} />
                    </div>
                    <span className="text-zinc-500 w-10 text-right">{Math.round(d.metric_value)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Phase 14: WebXR / AR modals — with session initialization */}
            {showWebXR && (
              <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setShowWebXR(false)}>
                <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-sm text-center" onClick={(e) => e.stopPropagation()}>
                  <div className="text-4xl mb-3">🥽</div>
                  <h3 className="text-sm font-semibold text-white mb-2">WebXR VR Mode</h3>
                  <p className="text-xs text-zinc-400 mb-4">
                    Immersive VR globe exploration requires a WebXR-compatible headset (Quest, Vision Pro, etc.)
                    and a browser with WebXR support.
                  </p>
                  <div className="text-[10px] text-zinc-500 mb-3">
                    {typeof navigator !== "undefined" && "xr" in navigator
                      ? "✅ WebXR API detected — headset may be connected"
                      : "⚠️ WebXR API not available in this browser"}
                  </div>
                  <div className="flex gap-2 justify-center">
                    {typeof navigator !== "undefined" && "xr" in navigator && (
                      <button onClick={async () => {
                        try {
                          const xr = (navigator as unknown as { xr: { isSessionSupported: (mode: string) => Promise<boolean>; requestSession: (mode: string) => Promise<unknown> } }).xr;
                          const supported = await xr.isSessionSupported("immersive-vr");
                          if (supported) {
                            await xr.requestSession("immersive-vr");
                          } else {
                            alert("Immersive VR not supported on this device. Connect a VR headset and try again.");
                          }
                        } catch (e) {
                          alert(`WebXR session failed: ${(e as Error).message}`);
                        }
                      }}
                        className="bg-emerald-600 hover:bg-emerald-500 rounded px-4 py-2 text-xs text-white font-semibold">
                        Enter VR
                      </button>
                    )}
                    <button onClick={() => setShowWebXR(false)}
                      className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-600 rounded px-4 py-2 text-xs text-zinc-300">
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}

            {showAR && (
              <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setShowAR(false)}>
                <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-sm text-center" onClick={(e) => e.stopPropagation()}>
                  <div className="text-4xl mb-3">📱</div>
                  <h3 className="text-sm font-semibold text-white mb-2">AR Camera Overlay</h3>
                  <p className="text-xs text-zinc-400 mb-4">
                    Augmented Reality overlay projects Cerebro intelligence data onto your phone camera feed.
                    Requires a mobile device with camera access and AR capabilities.
                  </p>
                  <div className="text-[10px] text-zinc-500 mb-3">
                    {typeof navigator !== "undefined" && "mediaDevices" in navigator
                      ? "✅ Camera API available"
                      : "⚠️ Camera API not available"}
                  </div>
                  <div className="flex gap-2 justify-center">
                    {typeof navigator !== "undefined" && "mediaDevices" in navigator && (
                      <button onClick={async () => {
                        try {
                          const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
                          // Create a floating camera feed overlay
                          const video = document.createElement("video");
                          video.srcObject = stream;
                          video.autoplay = true;
                          video.playsInline = true;
                          video.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;object-fit:cover;z-index:100;opacity:0.4;pointer-events:none;";
                          video.id = "cerebro-ar-feed";
                          document.body.appendChild(video);
                          setShowAR(false);
                          // Stop after 30s or on next toggle
                          setTimeout(() => {
                            stream.getTracks().forEach(t => t.stop());
                            document.getElementById("cerebro-ar-feed")?.remove();
                          }, 30000);
                        } catch (e) {
                          alert(`Camera access failed: ${(e as Error).message}`);
                        }
                      }}
                        className="bg-emerald-600 hover:bg-emerald-500 rounded px-4 py-2 text-xs text-white font-semibold">
                        Start AR
                      </button>
                    )}
                    <button onClick={() => {
                      setShowAR(false);
                      // Clean up any running AR feed
                      const feed = document.getElementById("cerebro-ar-feed");
                      if (feed) {
                        const video = feed as HTMLVideoElement;
                        const stream = video.srcObject as MediaStream;
                        stream?.getTracks().forEach(t => t.stop());
                        feed.remove();
                      }
                    }}
                      className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-600 rounded px-4 py-2 text-xs text-zinc-300">
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Phase 15: PiP floating inset map */}
            {showPiP && (
              <div
                className="absolute z-30 rounded-lg overflow-hidden border border-violet-500/40 shadow-2xl"
                style={{
                  width: 280, height: 200,
                  right: pipPos.x, bottom: pipPos.y,
                }}
              >
                {/* Draggable title bar */}
                <div
                  className="bg-zinc-900/95 border-b border-violet-500/30 px-2 py-1 flex items-center justify-between cursor-move select-none"
                  onMouseDown={(e) => {
                    setPipDragging(true);
                    pipDragStart.current = { x: e.clientX - pipPos.x, y: e.clientY - pipPos.y };
                    const onMove = (ev: MouseEvent) => {
                      setPipPos({
                        x: ev.clientX - pipDragStart.current.x,
                        y: ev.clientY - pipDragStart.current.y,
                      });
                    };
                    const onUp = () => {
                      setPipDragging(false);
                      window.removeEventListener("mousemove", onMove);
                      window.removeEventListener("mouseup", onUp);
                    };
                    window.addEventListener("mousemove", onMove);
                    window.addEventListener("mouseup", onUp);
                  }}
                >
                  <span className="text-[9px] text-violet-400 font-semibold">PiP — Satellite View</span>
                  <button onClick={() => setShowPiP(false)}
                    className="text-zinc-500 hover:text-white text-xs leading-none">✕</button>
                </div>
                <div ref={pipMapContainer} className="w-full" style={{ height: 174 }} />
              </div>
            )}

            {/* Shockwave propagation rings */}
            {shockwaves.map((sw) => (
              <div key={sw.id} className="absolute pointer-events-none z-20"
                style={{ left: sw.x, top: sw.y }}>
                <div className="cerebro-shockwave" />
                <div className="cerebro-shockwave wave-2" />
                <div className="cerebro-shockwave wave-3" />
              </div>
            ))}

            {/* Risk score odometer HUD */}
            {showRiskOdometer && animatedRiskScore !== null && (
              <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-zinc-900/90 border border-orange-500/30 rounded-lg px-4 py-2 z-10 flex items-center gap-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Risk Index</div>
                <div className="flex font-mono text-2xl font-bold" key={animatedRiskScore}>
                  {String(animatedRiskScore).padStart(3, "0").split("").map((digit, i) => (
                    <div key={`${i}-${digit}`} className="cerebro-odometer-digit"
                      style={{ width: "0.65em" }}>
                      <span className={`${
                        animatedRiskScore > 70 ? "text-red-400" :
                        animatedRiskScore > 40 ? "text-amber-400" : "text-emerald-400"
                      }`}>
                        {digit}
                      </span>
                    </div>
                  ))}
                </div>
                <div className={`w-2 h-2 rounded-full ${
                  animatedRiskScore > 70 ? "bg-red-500 animate-pulse" :
                  animatedRiskScore > 40 ? "bg-amber-500" : "bg-emerald-500"
                }`} />
              </div>
            )}

            {/* News ticker overlay */}
            {showNewsTicker && tickerItems.length > 0 && (
              <div className="absolute bottom-0 left-0 right-0 z-20 bg-zinc-950/90 border-t border-zinc-800 overflow-hidden">
                <div className="flex items-center">
                  <div className="bg-red-600 px-3 py-1.5 text-[10px] font-bold text-white shrink-0 z-10">
                    LIVE
                  </div>
                  <div className="overflow-hidden whitespace-nowrap flex-1">
                    <div className="inline-block animate-[cerebro-ticker_60s_linear_infinite] whitespace-nowrap">
                      {tickerItems.map((item, i) => (
                        <span key={i} className="inline-block mx-6 text-xs">
                          <span className={`font-semibold ${
                            item.severity > 70 ? "text-red-400" :
                            item.severity > 40 ? "text-amber-400" : "text-zinc-300"
                          }`}>
                            {item.title}
                          </span>
                          <span className="text-zinc-600 ml-2">{formatTime(item.timestamp)}</span>
                        </span>
                      ))}
                      {/* Duplicate for seamless loop */}
                      {tickerItems.map((item, i) => (
                        <span key={`dup-${i}`} className="inline-block mx-6 text-xs">
                          <span className={`font-semibold ${
                            item.severity > 70 ? "text-red-400" :
                            item.severity > 40 ? "text-amber-400" : "text-zinc-300"
                          }`}>
                            {item.title}
                          </span>
                          <span className="text-zinc-600 ml-2">{formatTime(item.timestamp)}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Documentary mode narration panel */}
            {showDocumentaryMode && documentarySteps.length > 0 && (
              <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-30 bg-zinc-900/95 border border-indigo-500/30 rounded-xl px-6 py-4 max-w-lg w-full shadow-2xl backdrop-blur-sm">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[10px] text-indigo-400 font-semibold uppercase tracking-wider">
                    Documentary Mode — Step {currentDocStep + 1}/{documentarySteps.length}
                  </div>
                  <button onClick={() => setShowDocumentaryMode(false)}
                    className="text-zinc-500 hover:text-white text-xs">✕</button>
                </div>
                <h3 className="text-sm font-bold text-white mb-1">
                  {documentarySteps[currentDocStep]?.title}
                </h3>
                <p className="text-xs text-zinc-400 mb-3 leading-relaxed">
                  {documentarySteps[currentDocStep]?.narration}
                </p>
                <div className="flex items-center gap-2">
                  <button onClick={() => setCurrentDocStep(Math.max(0, currentDocStep - 1))}
                    disabled={currentDocStep === 0}
                    className="bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 border border-zinc-700 rounded px-3 py-1 text-[10px] text-zinc-300">
                    ◀ Prev
                  </button>
                  <div className="flex-1 flex gap-1">
                    {documentarySteps.map((_, i) => (
                      <button key={i} onClick={() => setCurrentDocStep(i)}
                        className={`flex-1 h-1.5 rounded-full transition-colors ${
                          i === currentDocStep ? "bg-indigo-500" :
                          i < currentDocStep ? "bg-indigo-500/30" : "bg-zinc-700"
                        }`} />
                    ))}
                  </div>
                  <button onClick={() => setCurrentDocStep(Math.min(documentarySteps.length - 1, currentDocStep + 1))}
                    disabled={currentDocStep === documentarySteps.length - 1}
                    className="bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 border border-zinc-700 rounded px-3 py-1 text-[10px] text-zinc-300">
                    Next ▶
                  </button>
                </div>
              </div>
            )}

            {/* Recording indicator */}
            {isRecordingTimelapse && (
              <div className="absolute top-3 right-3 z-30 bg-red-900/90 border border-red-500/50 rounded-lg px-3 py-2 flex items-center gap-2">
                <span className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                <span className="text-[10px] text-red-300 font-semibold">REC</span>
                <button onClick={stopTimelapseCapture}
                  className="bg-red-500/20 hover:bg-red-500/40 rounded px-2 py-0.5 text-[9px] text-red-300 border border-red-500/30">
                  Stop
                </button>
              </div>
            )}

            {/* Map label */}
            {showSplitScreen && (
              <div className="absolute bottom-3 left-3 bg-zinc-900/80 border border-zinc-700 rounded px-2 py-1 text-[10px] text-zinc-400 z-10">
                Dark Basemap
              </div>
            )}
          </div>

          {/* Split divider */}
          {showSplitScreen && (
            <div className="w-0.5 bg-cyan-500/40 z-10 shrink-0" />
          )}

          {/* Split-screen secondary map */}
          {showSplitScreen && (
            <div className="relative w-1/2">
              <div ref={splitMapContainer} className="absolute inset-0" />
              <div className="absolute bottom-3 left-3 bg-zinc-900/80 border border-zinc-700 rounded px-2 py-1 text-[10px] text-zinc-400 z-10">
                Satellite Imagery
              </div>
            </div>
          )}
        </div>

        {/* Phase 15: Command Palette overlay */}
        {showCommandPalette && (
          <div className="absolute inset-0 z-[60] flex items-start justify-center pt-[15vh] bg-black/50 backdrop-blur-sm"
            onClick={() => setShowCommandPalette(false)}>
            <div className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-full max-w-lg overflow-hidden"
              onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
                <span className="text-zinc-500 text-sm">🔍</span>
                <input
                  autoFocus
                  value={cmdQuery}
                  onChange={(e) => setCmdQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setShowCommandPalette(false);
                    if (e.key === "Enter" && filteredCmdItems.length > 0) {
                      filteredCmdItems[0].action();
                      setShowCommandPalette(false);
                    }
                  }}
                  placeholder="Type a command..."
                  className="flex-1 bg-transparent border-none outline-none text-sm text-white placeholder-zinc-500"
                />
                <kbd className="bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-[10px] text-zinc-500 font-mono">ESC</kbd>
              </div>
              <div className="max-h-[50vh] overflow-y-auto py-1">
                {filteredCmdItems.length === 0 && (
                  <div className="px-4 py-6 text-center text-zinc-500 text-xs">No matching commands</div>
                )}
                {filteredCmdItems.map((item, i) => (
                  <button key={i} onClick={() => { item.action(); setShowCommandPalette(false); }}
                    className="w-full text-left px-4 py-2 hover:bg-zinc-800 flex items-center justify-between transition-colors group">
                    <span className="text-sm text-zinc-300 group-hover:text-white">{item.label}</span>
                    {item.key && (
                      <kbd className="bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-[10px] text-zinc-500 font-mono">
                        {item.key}
                      </kbd>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Keyboard shortcut help overlay */}
        {showShortcutHelp && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowShortcutHelp(false)}>
            <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-md w-full shadow-2xl" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-white">Keyboard Shortcuts</h2>
                <button onClick={() => setShowShortcutHelp(false)} className="text-zinc-500 hover:text-white text-lg">✕</button>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                {[
                  ["h", "Toggle heatmap"],
                  ["v", "Toggle vessels"],
                  ["a", "Toggle flights (ADS-B)"],
                  ["t", "Toggle 3D terrain"],
                  ["d", "Toggle split-screen"],
                  ["s", "Toggle satellite swipe"],
                  ["m", "Toggle maritime zones"],
                  ["p", "Toggle predictions"],
                  ["g", "Toggle density grid"],
                  ["l", "Toggle timelapse"],
                  ["w", "Toggle webcams"],
                  ["f", "Toggle frontlines"],
                  ["o", "Toggle trade flows"],
                  ["n", "Toggle annotations"],
                  ["i", "Toggle HUD mode"],
                  ["b", "Toggle pulse beacons"],
                  ["x", "Toggle satellite orbits"],
                  ["e", "Toggle 3D extrusions"],
                  ["1-5", "Toggle categories"],
                  ["[ / ]", "Adjust severity ±10"],
                  ["+ / -", "Zoom in / out"],
                  ["r", "Reset view"],
                  ["?", "Show this help"],
                  ["Esc", "Close panels"],
                  ["⌘S", "Save current view"],
                ].map(([key, desc]) => (
                  <div key={key} className="flex items-center gap-2 py-0.5">
                    <kbd className="bg-zinc-800 border border-zinc-600 rounded px-1.5 py-0.5 text-[10px] text-zinc-300 font-mono min-w-[28px] text-center">
                      {key}
                    </kbd>
                    <span className="text-zinc-400">{desc}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 text-[10px] text-zinc-600 text-center">
                Shortcuts are disabled when focused on input fields
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
