"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { useCesiumViewer } from "./cesium/useCesiumViewer";
import TacticalChrome, { presetFilter, type StylePreset } from "./TacticalChrome";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ───

interface GeoFeature {
  id: string; lat: number; lng: number; title: string;
  category: string | null; severity: number; confidence: number;
  source: string; timestamp: string; country_code: string | null;
}
interface Vessel {
  mmsi: string; name: string | null; vessel_type: string; flag: string | null;
  latitude: number; longitude: number; speed: number | null;
  course: number | null; heading: number | null; last_seen: string;
}
interface Flight {
  icao24: string; callsign: string | null; origin_country: string;
  flight_type: string; latitude: number; longitude: number;
  altitude: number | null; velocity: number | null;
  heading: number | null; on_ground: number;
}
interface FireDetection {
  id: string; lat: number; lng: number; brightness: number | null;
  frp: number | null; confidence: string; capture_date: string; satellite: string;
}
interface SatelliteOrbit {
  type: string;
  features: Array<{
    type: string;
    geometry: { type: string; coordinates: number[][] };
    properties: { name: string; norad_id: number; altitude_km: number; color: string; category: string; country_code: string };
  }>;
}
interface WebcamFeature {
  type: string;
  geometry: { type: string; coordinates: [number, number] };
  properties: {
    id: string; title: string; stream_url: string | null;
    thumbnail_url: string | null; category: string; country_code: string;
  };
}
interface GeofenceFeature {
  type: string;
  geometry: { type: string; coordinates: number[][][] }; // Polygon
  properties: {
    id: string; name: string; description: string; category: string;
    event_count: number; alert_on_entry: number; alert_severity_min: number;
    created_at: string;
  };
}

// ─── Helpers ───

const CATEGORY_COLORS: Record<string, string> = {
  military: "#ef4444", political: "#3b82f6", economic: "#eab308",
  health: "#22c55e", environmental: "#10b981",
};
function getMarkerColor(category: string | null) {
  return CATEGORY_COLORS[category || ""] || "#71717a";
}
function formatTime(ts: string) {
  try { return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return ts; }
}

// ─── Reticle (corner-bracket) markers — tactical/WORLDVIEW style ───
// Each marker: 4 L-shaped corners around the entity with a center dot/glyph.
// Color drives the bracket stroke; glyph is the centered character.

function bracketReticle(color: string, glyph = ""): string {
  // 24x24, corner brackets at offsets 2..6 / 22..18, center dot at 12,12
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
    <g stroke="${color}" stroke-width="1.4" fill="none" stroke-linecap="square">
      <polyline points="2,7 2,2 7,2"/>
      <polyline points="26,7 26,2 21,2"/>
      <polyline points="2,21 2,26 7,26"/>
      <polyline points="26,21 26,26 21,26"/>
    </g>
    <circle cx="14" cy="14" r="1.5" fill="${color}"/>
    ${glyph ? `<text x="14" y="11" fill="${color}" font-family="ui-monospace,Menlo" font-size="6" text-anchor="middle" letter-spacing="0.5">${glyph}</text>` : ""}
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// Airplane: bracket reticle + ▲ glyph inside
function createAirplaneSVG(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
    <g stroke="${color}" stroke-width="1.3" fill="none" stroke-linecap="square">
      <polyline points="2,7 2,2 7,2"/><polyline points="26,7 26,2 21,2"/>
      <polyline points="2,21 2,26 7,26"/><polyline points="26,21 26,26 21,26"/>
    </g>
    <path d="M14 6 L16 13 L22 15 L16 16 L14 22 L12 16 L6 15 L12 13Z" fill="${color}" opacity="0.95"/>
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// Ship: bracket reticle + ■ hull glyph
function createShipSVG(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
    <g stroke="${color}" stroke-width="1.2" fill="none" stroke-linecap="square">
      <polyline points="2,6 2,2 6,2"/><polyline points="22,6 22,2 18,2"/>
      <polyline points="2,18 2,22 6,22"/><polyline points="22,18 22,22 18,22"/>
    </g>
    <path d="M12 5 L15 11 L15 15 L17 18 L7 18 L9 15 L9 11Z" fill="${color}" opacity="0.9"/>
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// Webcam: bracket reticle + ⊙ camera glyph
function createWebcamSVG(): string {
  return bracketReticle("#22d3ee", "CAM");
}

// Fire: bracket reticle + flame (amber)
function createFireSVG(): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
    <g stroke="#fbbf24" stroke-width="1.2" fill="none" stroke-linecap="square">
      <polyline points="2,6 2,2 6,2"/><polyline points="22,6 22,2 18,2"/>
      <polyline points="2,18 2,22 6,22"/><polyline points="22,18 22,22 18,22"/>
    </g>
    <path d="M12 5 C12 5 16 9 16 13 C16 15 14 17 12 17 C10 17 8 15 8 13 C8 9 12 5 12 5Z" fill="#ff6b35" stroke="#fbbf24" stroke-width="0.6"/>
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// ─── Component ───

export default function CesiumGlobe() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewerReady, setViewerReady] = useState(0);
  const viewerRef = useCesiumViewer(containerRef, {
    onReady: () => setViewerReady((n) => n + 1),
  });

  // Data state
  const [events, setEvents] = useState<GeoFeature[]>([]);
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [flights, setFlights] = useState<Flight[]>([]);
  const [fires, setFires] = useState<FireDetection[]>([]);
  const [satelliteOrbits, setSatelliteOrbits] = useState<SatelliteOrbit | null>(null);
  const [webcams, setWebcams] = useState<WebcamFeature[]>([]);
  const [loading, setLoading] = useState(false);

  // Layer visibility
  const [showEvents, setShowEvents] = useState(true);
  const [showVessels, setShowVessels] = useState(true);
  const [showFlights, setShowFlights] = useState(true);
  const [showFires, setShowFires] = useState(true);
  const [showSatellites, setShowSatellites] = useState(true);
  const [showWebcams, setShowWebcams] = useState(true);
  const [showGeofences, setShowGeofences] = useState(true);
  const [showLiveImagery, setShowLiveImagery] = useState(false);
  const [showBuildings, setShowBuildings] = useState(true);
  const [showAtmosphere, setShowAtmosphere] = useState(true);
  const [showLighting, setShowLighting] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  // Tactical chrome / style preset
  const [stylePreset, setStylePreset] = useState<StylePreset>("crt");
  const [cameraCoords, setCameraCoords] = useState({ lat: 0, lng: 0, alt: 15_000_000 });
  const [frameMs, setFrameMs] = useState(0);

  // Camera & overlays
  const [cameraAlt, setCameraAlt] = useState(15_000_000);
  const [streetViewOpen, setStreetViewOpen] = useState(false);
  const [streetViewPos, setStreetViewPos] = useState<{ lat: number; lng: number } | null>(null);
  const [webcamPopup, setWebcamPopup] = useState<{ title: string; url: string | null } | null>(null);
  // Selected entity detail panel (replaces the fragile positioned popups)
  const [selectedEntity, setSelectedEntity] = useState<{
    type: string; title: string; details: Record<string, string | number>;
    lat: number; lng: number; alt?: number;
  } | null>(null);

  // Geofences
  const [geofences, setGeofences] = useState<GeofenceFeature[]>([]);
  const [drawMode, setDrawMode] = useState(false);
  // Refs so the click handler effect doesn't have to re-register on every state change
  const drawModeRef = useRef(false);
  useEffect(() => { drawModeRef.current = drawMode; }, [drawMode]);
  // Points held in a ref to avoid re-renders during point capture; mirrored to state for UI
  const drawPointsRef = useRef<Array<[number, number]>>([]);
  const [drawPointCount, setDrawPointCount] = useState(0);
  const [saveFenceOpen, setSaveFenceOpen] = useState(false);
  const [fenceForm, setFenceForm] = useState({ name: "", category: "custom", description: "" });
  const [selectedFence, setSelectedFence] = useState<GeofenceFeature | null>(null);

  // ─── Data Fetching ───

  const fetchEvents = useCallback(async () => {
    try {
      const params = new URLSearchParams({ west: "-180", south: "-90", east: "180", north: "90", limit: "2000" });
      const res = await fetch(`${API_URL}/api/events/geo?${params}`);
      if (res.ok) { const d = await res.json(); setEvents(d.features || []); }
    } catch { /* silent */ }
  }, []);

  const fetchVesselsAndFlights = useCallback(async () => {
    try {
      const [vRes, fRes] = await Promise.all([
        fetch(`${API_URL}/api/vessels?limit=5000`).catch(() => null),
        fetch(`${API_URL}/api/flights?limit=5000`).catch(() => null),
      ]);
      if (vRes?.ok) { const d = await vRes.json(); setVessels(d.vessels || []); }
      if (fRes?.ok) { const d = await fRes.json(); setFlights(d.flights || []); }
    } catch { /* silent */ }
  }, []);

  const fetchFires = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/fires`);
      if (res.ok) { const d = await res.json(); setFires(d.fires || []); }
    } catch { /* silent */ }
  }, []);

  const fetchSatellites = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/satellites/orbits/geojson`);
      if (res.ok) { setSatelliteOrbits(await res.json()); }
    } catch { /* silent */ }
  }, []);

  const fetchWebcams = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/webcams/geojson`);
      if (res.ok) {
        const d = await res.json();
        const seen = new Set<string>();
        const unique = (d.features || []).filter((f: WebcamFeature) => {
          const key = `${f.properties?.title}|${f.geometry?.coordinates}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return f.geometry?.coordinates?.[0] != null;
        });
        setWebcams(unique);
      }
    } catch { /* silent */ }
  }, []);

  const fetchGeofences = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/geofences/geojson`);
      if (res.ok) {
        const d = await res.json();
        setGeofences(d.features || []);
      }
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchEvents(), fetchVesselsAndFlights(), fetchFires(),
      fetchSatellites(), fetchWebcams(), fetchGeofences(),
    ]).finally(() => setLoading(false));
  }, [fetchEvents, fetchVesselsAndFlights, fetchFires, fetchSatellites, fetchWebcams, fetchGeofences]);

  // ─── Live polling — refresh vessels/flights every 20s ───
  useEffect(() => {
    const interval = setInterval(() => { fetchVesselsAndFlights(); }, 20_000);
    return () => clearInterval(interval);
  }, [fetchVesselsAndFlights]);

  // ─── NASA GIBS live satellite imagery overlay (MODIS Terra, daily) ───
  // GIBS is free, no auth required: https://nasa-gibs.github.io/gibs-api-docs/
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    let added: unknown = null;
    let cancelled = false;

    import("cesium").then((Cesium) => {
      if (cancelled || !showLiveImagery) return;
      // GIBS imagery is delayed ~1 day. Use yesterday's date.
      const d = new Date(Date.now() - 24 * 60 * 60 * 1000);
      const dateStr = d.toISOString().slice(0, 10);
      const provider = new Cesium.WebMapTileServiceImageryProvider({
        url: `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${dateStr}/250m/{TileMatrix}/{TileRow}/{TileCol}.jpg`,
        layer: "MODIS_Terra_CorrectedReflectance_TrueColor",
        style: "default",
        format: "image/jpeg",
        tileMatrixSetID: "250m",
        maximumLevel: 8,
        tileWidth: 512,
        tileHeight: 512,
        tilingScheme: new Cesium.GeographicTilingScheme(),
        credit: new Cesium.Credit("NASA EOSDIS GIBS"),
      });
      const layer = viewer.imageryLayers.addImageryProvider(provider);
      layer.alpha = 0.85;
      added = layer;
      viewer.scene.requestRender();
    });

    return () => {
      cancelled = true;
      if (added && viewer && !viewer.isDestroyed()) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        viewer.imageryLayers.remove(added as any);
        viewer.scene.requestRender();
      }
    };
  }, [showLiveImagery, viewerReady]);

  // ─── Camera altitude monitor ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    let lastFrameStart = performance.now();
    const interval = setInterval(() => {
      if (viewer.isDestroyed()) return;
      const c = viewer.camera.positionCartographic;
      // Cesium gives lat/lng in radians; convert to degrees
      const lat = (c.latitude * 180) / Math.PI;
      const lng = (c.longitude * 180) / Math.PI;
      setCameraAlt(c.height);
      setCameraCoords({ lat, lng, alt: c.height });
      // Cheap frame-time estimate: time between sampling intervals
      const now = performance.now();
      setFrameMs(Math.max(0, (now - lastFrameStart) / 100));
      lastFrameStart = now;
    }, 500);
    return () => clearInterval(interval);
  }, [viewerReady]);

  // ─── Render events (points + clustering) ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("events")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!showEvents || events.length === 0) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("events");
      ds.clustering.enabled = true;
      ds.clustering.pixelRange = 50;
      ds.clustering.minimumClusterSize = 3;

      for (const evt of events) {
        if (!evt.lat || !evt.lng) continue;
        ds.entities.add({
          position: Cesium.Cartesian3.fromDegrees(evt.lng, evt.lat),
          point: {
            pixelSize: 6, color: Cesium.Color.fromCssColorString(getMarkerColor(evt.category)),
            outlineColor: Cesium.Color.BLACK, outlineWidth: 1,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 5_000_000),
          },
          properties: { type: "event", id: evt.id, title: evt.title, category: evt.category, severity: evt.severity, source: evt.source, timestamp: evt.timestamp, lat: evt.lat, lng: evt.lng },
        });
      }

      ds.clustering.clusterEvent.addEventListener((clustered: unknown[], cluster: {
        billboard: { show: boolean }; label: { show: boolean; text: string; font: string; fillColor: unknown };
        point?: { show: boolean; pixelSize: number; color: unknown; outlineColor: unknown; outlineWidth: number };
      }) => {
        cluster.billboard.show = false;
        cluster.label.show = true;
        cluster.label.text = String(clustered.length);
        cluster.label.font = "bold 11px sans-serif";
        cluster.label.fillColor = Cesium.Color.WHITE;
        if (cluster.point) {
          cluster.point.show = true;
          cluster.point.pixelSize = Math.min(8 + Math.log2(clustered.length) * 2, 16);
          cluster.point.color = Cesium.Color.fromCssColorString("#ef4444").withAlpha(0.5);
          cluster.point.outlineColor = Cesium.Color.WHITE;
          cluster.point.outlineWidth = 1;
        }
      });

      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [events, showEvents, viewerReady]);

  // ─── Render vessels (oriented ship billboards) ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("vessels")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!showVessels || vessels.length === 0) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("vessels");
      ds.clustering.enabled = true;
      ds.clustering.pixelRange = 35;
      ds.clustering.minimumClusterSize = 4;

      // Pre-create billboard images for each color
      const colorMap: Record<string, string> = {
        military: "#ef4444", tanker: "#f97316", cargo: "#60a5fa", fishing: "#22c55e", default: "#94a3b8",
      };
      const svgCache: Record<string, string> = {};
      for (const [key, col] of Object.entries(colorMap)) {
        svgCache[key] = createShipSVG(col);
      }

      for (const v of vessels) {
        if (!v.latitude || !v.longitude) continue;
        const colorKey = colorMap[v.vessel_type] ? v.vessel_type : "default";
        const color = colorMap[colorKey];
        const headingRad = v.heading != null ? Cesium.Math.toRadians(-(v.heading || 0)) : 0;

        ds.entities.add({
          position: Cesium.Cartesian3.fromDegrees(v.longitude, v.latitude),
          billboard: {
            image: svgCache[colorKey],
            width: 14,
            height: 14,
            rotation: headingRad,
            alignedAxis: Cesium.Cartesian3.UNIT_Z,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 3_000_000),
          },
          label: {
            text: v.name || v.mmsi, font: "10px sans-serif",
            fillColor: Cesium.Color.fromCssColorString(color),
            pixelOffset: new Cesium.Cartesian2(0, -14), showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#18181b").withAlpha(0.8),
            backgroundPadding: new Cesium.Cartesian2(4, 2),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 80_000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: {
            type: "vessel", title: v.name || `MMSI: ${v.mmsi}`, mmsi: v.mmsi, name: v.name,
            vessel_type: v.vessel_type, flag: v.flag, speed: v.speed,
            lat: v.latitude, lng: v.longitude,
          },
        });
      }

      ds.clustering.clusterEvent.addEventListener((clustered: unknown[], cluster: {
        billboard: { show: boolean }; label: { show: boolean; text: string; font: string; fillColor: unknown };
        point?: { show: boolean; pixelSize: number; color: unknown; outlineColor: unknown; outlineWidth: number };
      }) => {
        cluster.billboard.show = false;
        cluster.label.show = true;
        cluster.label.text = String(clustered.length);
        cluster.label.font = "bold 10px sans-serif";
        cluster.label.fillColor = Cesium.Color.WHITE;
        if (cluster.point) {
          cluster.point.show = true;
          cluster.point.pixelSize = Math.min(6 + Math.log2(clustered.length) * 2, 14);
          cluster.point.color = Cesium.Color.fromCssColorString("#3b82f6").withAlpha(0.5);
          cluster.point.outlineColor = Cesium.Color.fromCssColorString("#60a5fa");
          cluster.point.outlineWidth = 1;
        }
      });

      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [vessels, showVessels, viewerReady]);

  // ─── Render flights (oriented airplane billboards at real altitude) ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("flights")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!showFlights || flights.length === 0) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("flights");
      ds.clustering.enabled = true;
      ds.clustering.pixelRange = 30;
      ds.clustering.minimumClusterSize = 4;

      const svgCache: Record<string, string> = {};
      const flightColors: Record<string, string> = { military: "#ef4444", cargo: "#f59e0b", civilian: "#d4d4d8" };
      for (const [key, col] of Object.entries(flightColors)) {
        svgCache[key] = createAirplaneSVG(col);
      }

      for (const f of flights) {
        if (!f.latitude || !f.longitude) continue;
        const altitude = f.on_ground ? 0 : (f.altitude || 10000);
        const colorKey = flightColors[f.flight_type] ? f.flight_type : "civilian";
        const headingRad = f.heading != null ? Cesium.Math.toRadians(-(f.heading || 0)) : 0;

        ds.entities.add({
          position: Cesium.Cartesian3.fromDegrees(f.longitude, f.latitude, altitude),
          billboard: {
            image: svgCache[colorKey],
            width: 16,
            height: 16,
            rotation: headingRad,
            alignedAxis: Cesium.Cartesian3.UNIT_Z,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 4_000_000),
          },
          label: {
            text: f.callsign || f.icao24, font: "9px sans-serif",
            fillColor: Cesium.Color.fromCssColorString(flightColors[colorKey] || "#d4d4d8"),
            pixelOffset: new Cesium.Cartesian2(0, -14), showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#18181b").withAlpha(0.8),
            backgroundPadding: new Cesium.Cartesian2(3, 2),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 120_000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: {
            type: "flight", title: f.callsign || f.icao24, icao24: f.icao24,
            callsign: f.callsign, altitude: f.altitude, velocity: f.velocity,
            heading: f.heading, origin_country: f.origin_country, flight_type: f.flight_type,
            lat: f.latitude, lng: f.longitude,
          },
        });
      }

      ds.clustering.clusterEvent.addEventListener((clustered: unknown[], cluster: {
        billboard: { show: boolean }; label: { show: boolean; text: string; font: string; fillColor: unknown };
        point?: { show: boolean; pixelSize: number; color: unknown; outlineColor: unknown; outlineWidth: number };
      }) => {
        cluster.billboard.show = false;
        cluster.label.show = true;
        cluster.label.text = String(clustered.length);
        cluster.label.font = "bold 9px sans-serif";
        cluster.label.fillColor = Cesium.Color.WHITE;
        if (cluster.point) {
          cluster.point.show = true;
          cluster.point.pixelSize = Math.min(5 + Math.log2(clustered.length) * 1.5, 12);
          cluster.point.color = Cesium.Color.fromCssColorString("#d4d4d8").withAlpha(0.4);
          cluster.point.outlineColor = Cesium.Color.fromCssColorString("#a1a1aa");
          cluster.point.outlineWidth = 1;
        }
      });

      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [flights, showFlights, viewerReady]);

  // ─── Render fire detections ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("fires")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!showFires || fires.length === 0) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("fires");
      const fireSvg = createFireSVG();
      for (const fire of fires) {
        if (!fire.lat || !fire.lng) continue;
        ds.entities.add({
          position: Cesium.Cartesian3.fromDegrees(fire.lng, fire.lat),
          billboard: {
            image: fireSvg,
            width: 16,
            height: 16,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 6_000_000),
          },
          properties: {
            type: "fire", title: `Fire (${fire.satellite})`,
            brightness: fire.brightness, frp: fire.frp,
            confidence: fire.confidence, date: fire.capture_date,
            lat: fire.lat, lng: fire.lng,
          },
        });
      }
      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [fires, showFires, viewerReady]);

  // ─── Render satellites (3D model entities + orbit lines) ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("satellites")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!showSatellites || !satelliteOrbits?.features?.length) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("satellites");
      ds.clustering.enabled = true;
      ds.clustering.pixelRange = 40;
      ds.clustering.minimumClusterSize = 5;

      for (const feature of satelliteOrbits.features) {
        if (feature.geometry?.type !== "LineString") continue;
        const coords = feature.geometry.coordinates;
        const altMeters = (feature.properties.altitude_km || 500) * 1000;
        const color = feature.properties.color || "#00ffff";
        const catIcons: Record<string, string> = {
          military: "🛡", earth_obs: "🔭", weather: "🌤",
          navigation: "📡", science: "🔬", comms: "📶",
        };
        const catIcon = catIcons[feature.properties.category] || "🛰";

        // Orbit path line — very faint, only visible when zoomed out moderately
        const positions = coords.map(([lng, lat]) =>
          Cesium.Cartesian3.fromDegrees(lng, lat, altMeters)
        );
        ds.entities.add({
          polyline: {
            positions,
            width: 0.5,
            material: Cesium.Color.fromCssColorString(color).withAlpha(0.04),
            arcType: Cesium.ArcType.NONE,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(2_000_000, 15_000_000),
          },
        });

        // Satellite entity at orbit midpoint — small point, NOT 3D model by default
        const midIdx = Math.floor(coords.length / 2);
        const [satLng, satLat] = coords[midIdx];

        ds.entities.add({
          position: Cesium.Cartesian3.fromDegrees(satLng, satLat, altMeters),
          point: {
            pixelSize: 4,
            color: Cesium.Color.fromCssColorString(color),
            outlineColor: Cesium.Color.WHITE, outlineWidth: 0.5,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 12_000_000),
          },
          label: {
            text: `${catIcon} ${feature.properties.name}`,
            font: "9px sans-serif",
            fillColor: Cesium.Color.fromCssColorString(color),
            pixelOffset: new Cesium.Cartesian2(0, -12),
            showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#0a0a0a").withAlpha(0.85),
            backgroundPadding: new Cesium.Cartesian2(4, 2),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 2_000_000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: {
            type: "satellite",
            title: `${catIcon} ${feature.properties.name}`,
            norad_id: feature.properties.norad_id,
            altitude_km: feature.properties.altitude_km,
            category: feature.properties.category,
            country_code: feature.properties.country_code,
            lat: satLat, lng: satLng, alt: altMeters,
          },
        });
      }

      ds.clustering.clusterEvent.addEventListener((clustered: unknown[], cluster: {
        billboard: { show: boolean }; label: { show: boolean; text: string; font: string; fillColor: unknown };
        point?: { show: boolean; pixelSize: number; color: unknown; outlineColor: unknown; outlineWidth: number };
      }) => {
        cluster.billboard.show = false;
        cluster.label.show = true;
        cluster.label.text = `🛰${clustered.length}`;
        cluster.label.font = "bold 9px sans-serif";
        cluster.label.fillColor = Cesium.Color.fromCssColorString("#22d3ee");
        if (cluster.point) {
          cluster.point.show = true;
          cluster.point.pixelSize = Math.min(5 + Math.log2(clustered.length) * 1.5, 12);
          cluster.point.color = Cesium.Color.fromCssColorString("#06b6d4").withAlpha(0.4);
          cluster.point.outlineColor = Cesium.Color.fromCssColorString("#22d3ee");
          cluster.point.outlineWidth = 1;
        }
      });

      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [satelliteOrbits, showSatellites, viewerReady]);

  // ─── Render webcam markers ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("webcams")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!showWebcams || webcams.length === 0) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("webcams");
      ds.clustering.enabled = true;
      ds.clustering.pixelRange = 30;
      ds.clustering.minimumClusterSize = 3;

      const webcamSvg = createWebcamSVG();
      for (const cam of webcams) {
        const [lng, lat] = cam.geometry.coordinates;
        ds.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lng, lat),
          billboard: {
            image: webcamSvg,
            width: 18,
            height: 18,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 2_000_000),
          },
          label: {
            text: cam.properties.title,
            font: "9px sans-serif",
            fillColor: Cesium.Color.fromCssColorString("#c084fc"),
            pixelOffset: new Cesium.Cartesian2(0, -16),
            showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString("#18181b").withAlpha(0.8),
            backgroundPadding: new Cesium.Cartesian2(4, 2),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 200_000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: {
            type: "webcam", title: cam.properties.title,
            stream_url: cam.properties.stream_url, category: cam.properties.category,
            lat, lng,
          },
        });
      }

      ds.clustering.clusterEvent.addEventListener((clustered: unknown[], cluster: {
        billboard: { show: boolean }; label: { show: boolean; text: string; font: string; fillColor: unknown };
        point?: { show: boolean; pixelSize: number; color: unknown; outlineColor: unknown; outlineWidth: number };
      }) => {
        cluster.billboard.show = false;
        cluster.label.show = true;
        cluster.label.text = `📷 ${clustered.length}`;
        cluster.label.font = "bold 10px sans-serif";
        cluster.label.fillColor = Cesium.Color.fromCssColorString("#c084fc");
        if (cluster.point) {
          cluster.point.show = true;
          cluster.point.pixelSize = Math.min(8 + Math.log2(clustered.length) * 2, 14);
          cluster.point.color = Cesium.Color.fromCssColorString("#7c3aed").withAlpha(0.5);
          cluster.point.outlineColor = Cesium.Color.fromCssColorString("#c084fc");
          cluster.point.outlineWidth = 1;
        }
      });

      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [webcams, showWebcams, viewerReady]);

  // ─── Render geofences as semi-transparent polygons ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("geofences")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!showGeofences || geofences.length === 0) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("geofences");
      const categoryColors: Record<string, string> = {
        military: "#ef4444", economic: "#eab308", environmental: "#10b981",
        political: "#3b82f6", custom: "#a855f7",
      };

      for (const gf of geofences) {
        // GeoJSON Polygon: coordinates is [ring][point][lng/lat] — use the outer ring
        const ring = gf.geometry?.coordinates?.[0];
        if (!Array.isArray(ring) || ring.length < 3) continue;

        // Flatten to Cesium degrees array: [lng, lat, lng, lat, ...]
        const flat: number[] = [];
        for (const [lng, lat] of ring) flat.push(lng, lat);

        const color = categoryColors[gf.properties.category] || "#a855f7";
        const cesiumColor = Cesium.Color.fromCssColorString(color);

        // Compute centroid for label placement
        let cLng = 0, cLat = 0;
        for (const [lng, lat] of ring) { cLng += lng; cLat += lat; }
        cLng /= ring.length; cLat /= ring.length;

        ds.entities.add({
          polygon: {
            hierarchy: Cesium.Cartesian3.fromDegreesArray(flat),
            material: cesiumColor.withAlpha(0.18),
            outline: true,
            outlineColor: cesiumColor.withAlpha(0.95),
            outlineWidth: 2,
            height: 0,
          },
          // Outline polyline (polygon outlineWidth is ignored on most GPUs)
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray([...flat, ring[0][0], ring[0][1]]),
            width: 2.5,
            material: cesiumColor.withAlpha(0.9),
            clampToGround: true,
          },
          position: Cesium.Cartesian3.fromDegrees(cLng, cLat),
          label: {
            text: `${gf.properties.name} · ${gf.properties.event_count} events`,
            font: "bold 11px sans-serif",
            fillColor: Cesium.Color.WHITE,
            outlineColor: cesiumColor,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            showBackground: true,
            backgroundColor: cesiumColor.withAlpha(0.85),
            backgroundPadding: new Cesium.Cartesian2(6, 3),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 15_000_000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: { type: "geofence", ...gf.properties },
        });
      }

      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [geofences, showGeofences, viewerReady]);

  // ─── Render in-progress drawing polyline ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      const existing = viewer.dataSources.getByName("draw-preview")[0];
      if (existing) viewer.dataSources.remove(existing);
      if (!drawMode || drawPointCount === 0) { viewer.scene.requestRender(); return; }

      const ds = new Cesium.CustomDataSource("draw-preview");
      const flat: number[] = [];
      for (const [lng, lat] of drawPointsRef.current) flat.push(lng, lat);

      // Render the current ring as a closed-ish polyline + vertices
      if (drawPointCount >= 1) {
        const closed = drawPointCount >= 3
          ? [...flat, drawPointsRef.current[0][0], drawPointsRef.current[0][1]]
          : flat;
        ds.entities.add({
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray(closed),
            width: 3,
            material: Cesium.Color.fromCssColorString("#22d3ee").withAlpha(0.9),
            clampToGround: true,
          },
        });
        if (drawPointCount >= 3) {
          ds.entities.add({
            polygon: {
              hierarchy: Cesium.Cartesian3.fromDegreesArray(flat),
              material: Cesium.Color.fromCssColorString("#22d3ee").withAlpha(0.18),
              height: 0,
            },
          });
        }
      }
      for (const [lng, lat] of drawPointsRef.current) {
        ds.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lng, lat),
          point: {
            pixelSize: 8,
            color: Cesium.Color.fromCssColorString("#22d3ee"),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1.5,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
      }
      viewer.dataSources.add(ds);
      viewer.scene.requestRender();
    });
  }, [drawMode, drawPointCount, viewerReady]);

  // ─── Click handlers — zoom to entity + show 3D model + detail panel ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    import("cesium").then((Cesium) => {
      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

      // Track the 3D model entity shown on click so we can remove it later
      let activeModel: InstanceType<typeof Cesium.Entity> | null = null;

      // Double-click → zoom in toward globe position (skipped while drawing)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      handler.setInputAction((movement: any) => {
        if (drawModeRef.current) return;
        const cartesian = viewer.camera.pickEllipsoid(movement.position, viewer.scene.globe.ellipsoid);
        if (Cesium.defined(cartesian)) {
          const carto = Cesium.Cartographic.fromCartesian(cartesian);
          const targetAlt = Math.max(viewer.camera.positionCartographic.height * 0.25, 300);
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromRadians(carto.longitude, carto.latitude, targetAlt),
            duration: 1.2,
          });
        }
      }, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

      // Single click → either capture a draw point OR select entity + show 3D model
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      handler.setInputAction((movement: any) => {
        // ── Draw mode: capture a polygon vertex and exit ──
        if (drawModeRef.current) {
          const cartesian = viewer.camera.pickEllipsoid(movement.position, viewer.scene.globe.ellipsoid);
          if (Cesium.defined(cartesian)) {
            const carto = Cesium.Cartographic.fromCartesian(cartesian);
            const lng = Cesium.Math.toDegrees(carto.longitude);
            const lat = Cesium.Math.toDegrees(carto.latitude);
            drawPointsRef.current = [...drawPointsRef.current, [lng, lat]];
            setDrawPointCount(drawPointsRef.current.length);
          }
          return;
        }

        // Remove previous 3D model preview
        if (activeModel) {
          viewer.entities.remove(activeModel);
          activeModel = null;
        }

        const picked = viewer.scene.pick(movement.position);
        if (!Cesium.defined(picked) || !picked.id?.properties) {
          setSelectedEntity(null);
          setWebcamPopup(null);
          return;
        }

        const props = picked.id.properties;
        const entityType = props.type?.getValue();
        const lat = props.lat?.getValue();
        const lng = props.lng?.getValue();

        // Webcam click → open stream panel
        if (entityType === "webcam") {
          setWebcamPopup({
            title: props.title?.getValue() || "Camera Feed",
            url: props.stream_url?.getValue() || null,
          });
          setSelectedEntity(null);
          if (lat && lng) {
            viewer.camera.flyTo({
              destination: Cesium.Cartesian3.fromDegrees(lng, lat, 30_000),
              duration: 1.5,
            });
          }
          return;
        }

        // Build detail object from entity properties
        const details: Record<string, string | number> = {};
        const title = props.title?.getValue() || "Unknown";

        // Entity-type-specific details + 3D model
        let modelUri = "";
        let modelScale = 1;
        let alt = 0;

        if (entityType === "flight") {
          details["Callsign"] = props.callsign?.getValue() || "—";
          details["ICAO24"] = props.icao24?.getValue() || "—";
          details["Type"] = props.flight_type?.getValue() || "civilian";
          details["Altitude"] = `${Math.round(props.altitude?.getValue() || 0)} m`;
          details["Velocity"] = `${Math.round(props.velocity?.getValue() || 0)} m/s`;
          details["Heading"] = `${Math.round(props.heading?.getValue() || 0)}°`;
          details["Origin"] = props.origin_country?.getValue() || "—";
          modelUri = "/models/airplane.glb";
          modelScale = 2000;
          alt = props.altitude?.getValue() || 10000;
        } else if (entityType === "vessel") {
          details["Name"] = props.name?.getValue() || "—";
          details["MMSI"] = props.mmsi?.getValue() || "—";
          details["Type"] = props.vessel_type?.getValue() || "—";
          details["Flag"] = props.flag?.getValue() || "—";
          details["Speed"] = `${props.speed?.getValue() || 0} kn`;
          modelUri = "/models/ship.glb";
          modelScale = 1000;
        } else if (entityType === "satellite") {
          details["NORAD ID"] = props.norad_id?.getValue() || "—";
          details["Altitude"] = `${props.altitude_km?.getValue() || 0} km`;
          details["Category"] = props.category?.getValue() || "—";
          details["Country"] = props.country_code?.getValue() || "—";
          modelUri = "/models/satellite.glb";
          modelScale = 50000;
          alt = (props.altitude_km?.getValue() || 500) * 1000;
        } else if (entityType === "event") {
          details["Category"] = props.category?.getValue() || "—";
          details["Severity"] = props.severity?.getValue() || "—";
          details["Source"] = props.source?.getValue() || "—";
          details["Time"] = formatTime(props.timestamp?.getValue() || "");
        } else if (entityType === "fire") {
          details["Brightness"] = `${props.brightness?.getValue() || 0} K`;
          details["FRP"] = `${props.frp?.getValue() || 0} MW`;
          details["Confidence"] = props.confidence?.getValue() || "—";
          details["Date"] = props.date?.getValue() || "—";
        }

        setSelectedEntity({ type: entityType || "unknown", title, details, lat, lng, alt });
        setWebcamPopup(null);

        // Fly to entity — zoom close enough to see the 3D model
        if (lat && lng) {
          const flyAlt = entityType === "satellite" ? Math.max(alt * 0.15, 200_000) :
                         entityType === "flight" ? Math.max(alt * 1.2, 2000) : 2000;
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(lng, lat, flyAlt),
            duration: 1.5,
          });
        }

        // Add 3D model preview at entity position
        if (modelUri && lat && lng) {
          const heading = props.heading?.getValue() || 0;
          const hpr = new Cesium.HeadingPitchRoll(Cesium.Math.toRadians(heading), 0, 0);
          const position = Cesium.Cartesian3.fromDegrees(lng, lat, alt);
          const orientation = Cesium.Transforms.headingPitchRollQuaternion(position, hpr);

          activeModel = viewer.entities.add({
            position,
            orientation: orientation as unknown as undefined,
            model: {
              uri: modelUri,
              minimumPixelSize: 128,
              maximumScale: modelScale,
              color: Cesium.Color.WHITE,
              silhouetteColor: Cesium.Color.fromCssColorString("#22d3ee"),
              silhouetteSize: 3,
            },
          });
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

      return () => {
        if (activeModel) viewer.entities.remove(activeModel);
        if (!handler.isDestroyed()) handler.destroy();
      };
    });
  }, [viewerReady]);

  // ─── Toggle helpers ───

  const toggleBuildings = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    const prims = viewer.scene.primitives;
    for (let i = 0; i < prims.length; i++) {
      const p = prims.get(i);
      if (p.constructor?.name === "Cesium3DTileset") p.show = !showBuildings;
    }
    setShowBuildings(p => !p);
    viewer.scene.requestRender();
  }, [showBuildings, viewerReady]);

  const toggleAtmosphere = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show = !showAtmosphere;
    setShowAtmosphere(p => !p);
    viewer.scene.requestRender();
  }, [showAtmosphere, viewerReady]);

  const toggleLighting = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    viewer.scene.globe.enableLighting = !showLighting;
    setShowLighting(p => !p);
    viewer.scene.requestRender();
  }, [showLighting, viewerReady]);

  const openStreetView = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    const carto = viewer.camera.positionCartographic;
    setStreetViewPos({ lat: (carto.latitude * 180) / Math.PI, lng: (carto.longitude * 180) / Math.PI });
    setStreetViewOpen(true);
  }, [viewerReady]);

  const flyTo = useCallback((lng: number, lat: number, alt: number) => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    import("cesium").then((Cesium) => {
      viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(lng, lat, alt), duration: 2 });
    });
  }, [viewerReady]);

  // ─── Geofence drawing controls ───

  const startDrawing = useCallback(() => {
    drawPointsRef.current = [];
    setDrawPointCount(0);
    setSelectedEntity(null);
    setDrawMode(true);
  }, []);

  const cancelDrawing = useCallback(() => {
    drawPointsRef.current = [];
    setDrawPointCount(0);
    setDrawMode(false);
    setSaveFenceOpen(false);
  }, []);

  const undoLastPoint = useCallback(() => {
    drawPointsRef.current = drawPointsRef.current.slice(0, -1);
    setDrawPointCount(drawPointsRef.current.length);
  }, []);

  const finishDrawing = useCallback(() => {
    if (drawPointsRef.current.length < 3) return;
    setDrawMode(false);
    setSaveFenceOpen(true);
  }, []);

  const saveGeofence = useCallback(async () => {
    if (!fenceForm.name.trim() || drawPointsRef.current.length < 3) return;
    // Polygon must be closed (first == last)
    const ring = [...drawPointsRef.current];
    if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) {
      ring.push(ring[0]);
    }
    try {
      const res = await fetch(`${API_URL}/api/geofences`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: fenceForm.name.trim(),
          polygon: ring,
          description: fenceForm.description,
          category: fenceForm.category,
          alert_on_entry: true,
          alert_severity_min: 0,
        }),
      });
      if (res.ok) {
        await fetchGeofences();
        setFenceForm({ name: "", category: "custom", description: "" });
        drawPointsRef.current = [];
        setDrawPointCount(0);
        setSaveFenceOpen(false);
      }
    } catch { /* silent */ }
  }, [fenceForm, fetchGeofences]);

  const deleteGeofence = useCallback(async (id: string) => {
    try {
      const res = await fetch(`${API_URL}/api/geofences/${id}`, { method: "DELETE" });
      if (res.ok) {
        setSelectedFence(null);
        await fetchGeofences();
      }
    } catch { /* silent */ }
  }, [fetchGeofences]);

  // ─── Render ───

  return (
    <div className="h-full w-full bg-zinc-950 text-white flex relative">

      {/* ── Top-left badge + toggle (lowered when tactical chrome owns the header) ── */}
      <div
        className={`absolute left-2 z-40 flex items-center gap-2 pointer-events-auto transition-all ${
          stylePreset !== "off" ? "top-24" : "top-2"
        }`}
      >
        <button
          onClick={() => setSidebarCollapsed(p => !p)}
          className="w-8 h-8 rounded-lg bg-zinc-900/90 border border-zinc-700/50 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-800 transition-all text-xs backdrop-blur-sm"
          title={sidebarCollapsed ? "Show layer controls" : "Hide layer controls"}
        >
          {sidebarCollapsed ? "☰" : "✕"}
        </button>
        {sidebarCollapsed && stylePreset === "off" && (
          <div className="flex items-center gap-2 bg-zinc-900/80 backdrop-blur-sm rounded-lg border border-zinc-700/30 px-2.5 py-1.5 text-[10px] text-zinc-400">
            {loading && <span className="text-cyan-400 animate-pulse">Loading…</span>}
            <span className="text-red-400">{events.length} events</span>
            {fires.length > 0 && <span className="text-orange-400">🔥{fires.length}</span>}
            {webcams.length > 0 && <span className="text-purple-400">📷{webcams.length}</span>}
            {satelliteOrbits?.features?.length ? <span className="text-cyan-400">🛰{satelliteOrbits.features.length}</span> : null}
            {vessels.length > 0 && <span className="text-blue-400">{vessels.length} vessels</span>}
            {flights.length > 0 && <span className="text-zinc-300">{flights.length} flights</span>}
            {geofences.length > 0 && <span className="text-fuchsia-400">⛶{geofences.length}</span>}
            <span className="flex items-center gap-1 text-emerald-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              LIVE
            </span>
          </div>
        )}
      </div>

      {/* ── Street View button ── */}
      {cameraAlt < 5_000_000 && (
        <div className="absolute bottom-12 right-4 z-20">
          <button onClick={openStreetView}
            className="flex items-center gap-2 px-3 py-2 bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-600 rounded-lg text-xs text-white backdrop-blur-sm transition-all shadow-lg">
            🚶 Street View
          </button>
        </div>
      )}

      {/* ── Layer Sidebar (slides over globe, doesn't push it) ── */}
      <aside className={`absolute left-2 z-30 transition-all duration-300 rounded-xl overflow-hidden ${sidebarCollapsed ? "w-0 opacity-0 pointer-events-none" : "w-60 opacity-100"} ${stylePreset !== "off" ? "top-36" : "top-12"}`}>
        <div className="bg-zinc-900/90 backdrop-blur-md border border-zinc-700/50 rounded-xl max-h-[calc(100vh-6rem)] overflow-y-auto p-3 space-y-3 text-xs">

          {/* Data Layers */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-1.5 tracking-wider">Data Layers</h3>
            {[
              { label: `Events (${events.length})`, checked: showEvents, onChange: () => setShowEvents(p => !p), color: "bg-red-400" },
              { label: `Vessels (${vessels.length})`, checked: showVessels, onChange: () => setShowVessels(p => !p), color: "bg-blue-400" },
              { label: `Flights (${flights.length})`, checked: showFlights, onChange: () => setShowFlights(p => !p), color: "bg-zinc-400" },
              { label: `Fires (${fires.length})`, checked: showFires, onChange: () => setShowFires(p => !p), color: "bg-orange-400" },
              { label: `Satellites (${satelliteOrbits?.features?.length ?? 0})`, checked: showSatellites, onChange: () => setShowSatellites(p => !p), color: "bg-cyan-400" },
              { label: `Webcams (${webcams.length})`, checked: showWebcams, onChange: () => setShowWebcams(p => !p), color: "bg-purple-400" },
              { label: `Geofences (${geofences.length})`, checked: showGeofences, onChange: () => setShowGeofences(p => !p), color: "bg-fuchsia-400" },
            ].map(({ label, checked, onChange, color }) => (
              <label key={label} className="flex items-center gap-2 py-0.5 cursor-pointer">
                <input type="checkbox" checked={checked} onChange={onChange}
                  className="rounded border-zinc-600 bg-zinc-800 focus:ring-0 w-3.5 h-3.5" />
                <span className={`w-2 h-2 rounded-full ${color}`} />
                <span className={checked ? "text-zinc-200" : "text-zinc-600"}>{label}</span>
              </label>
            ))}
          </section>

          {/* 3D Features */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-1.5 tracking-wider">3D Features</h3>
            {[
              { label: "Live Sat Imagery (MODIS)", checked: showLiveImagery, onChange: () => setShowLiveImagery(p => !p) },
              { label: "3D Buildings", checked: showBuildings, onChange: toggleBuildings },
              { label: "Atmosphere", checked: showAtmosphere, onChange: toggleAtmosphere },
              { label: "Day/Night Lighting", checked: showLighting, onChange: toggleLighting },
            ].map(({ label, checked, onChange }) => (
              <label key={label} className="flex items-center gap-2 py-0.5 cursor-pointer">
                <input type="checkbox" checked={checked} onChange={onChange}
                  className="rounded border-zinc-600 bg-zinc-800 focus:ring-0 w-3.5 h-3.5" />
                <span className={checked ? "text-zinc-200" : "text-zinc-600"}>{label}</span>
              </label>
            ))}
          </section>

          {/* Geofences */}
          <section>
            <div className="flex items-center justify-between mb-1.5">
              <h3 className="text-[10px] uppercase text-zinc-500 font-semibold tracking-wider">Geofences</h3>
              {!drawMode && (
                <button
                  onClick={startDrawing}
                  className="text-[10px] px-2 py-0.5 rounded bg-fuchsia-600/80 hover:bg-fuchsia-500 text-white font-medium transition-colors"
                  title="Click points on the globe to draw a monitoring polygon"
                >
                  ＋ Draw
                </button>
              )}
            </div>
            {geofences.length === 0 ? (
              <div className="text-[10px] text-zinc-600 italic py-1">No geofences yet</div>
            ) : (
              <div className="space-y-0.5 max-h-40 overflow-y-auto">
                {geofences.map((g) => (
                  <button
                    key={g.properties.id}
                    onClick={() => {
                      setSelectedFence(g);
                      const ring = g.geometry?.coordinates?.[0];
                      if (ring && ring.length) {
                        let cLng = 0, cLat = 0;
                        for (const [lng, lat] of ring) { cLng += lng; cLat += lat; }
                        flyTo(cLng / ring.length, cLat / ring.length, 2_000_000);
                      }
                    }}
                    className="w-full text-left px-2 py-1 rounded hover:bg-zinc-800 text-[10px] text-zinc-300 truncate flex items-center justify-between gap-2"
                  >
                    <span className="truncate">{g.properties.name}</span>
                    <span className="text-fuchsia-400">{g.properties.event_count}</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* Quick Navigation */}
          <section>
            <h3 className="text-[10px] uppercase text-zinc-500 font-semibold mb-1.5 tracking-wider">Quick Navigation</h3>
            <div className="grid grid-cols-2 gap-1">
              {[
                { label: "Overview", lng: 20, lat: 30, alt: 15_000_000 },
                { label: "Middle East", lng: 45, lat: 30, alt: 3_000_000 },
                { label: "Europe", lng: 10, lat: 50, alt: 4_000_000 },
                { label: "East Asia", lng: 120, lat: 35, alt: 4_000_000 },
                { label: "Americas", lng: -90, lat: 30, alt: 8_000_000 },
                { label: "Gaza", lng: 34.3, lat: 31.3, alt: 80_000 },
                { label: "Hormuz", lng: 56.3, lat: 26.6, alt: 200_000 },
                { label: "SCS", lng: 112.3, lat: 16, alt: 2_000_000 },
              ].map((loc) => (
                <button key={loc.label} onClick={() => flyTo(loc.lng, loc.lat, loc.alt)}
                  className="px-2 py-1 rounded text-[10px] hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors truncate text-left">
                  {loc.label}
                </button>
              ))}
            </div>
          </section>
        </div>
      </aside>

      {/* ── Cesium Container ── */}
      <div className="flex-1 relative h-full">
        <div
          ref={containerRef}
          className="w-full h-full"
          style={{ filter: presetFilter(stylePreset), transition: "filter 0.3s ease-out" }}
        />

        {/* ── Tactical HUD overlay (classifications, MGRS, REC timestamp, style switcher) ── */}
        <TacticalChrome
          preset={stylePreset}
          onPresetChange={setStylePreset}
          stats={{
            entities: events.length + vessels.length + flights.length + fires.length,
            sources: 18,
            density: (events.length + vessels.length + flights.length) / Math.max(1, cameraAlt / 100_000),
            frameMs,
          }}
          coords={cameraCoords}
          pinLabel={selectedEntity ? `${selectedEntity.type.toUpperCase()} · ${selectedEntity.title}` : null}
        />

        {/* ── Geofence drawing toolbar (top-center, only while drawing) ── */}
        {drawMode && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 bg-zinc-900/95 backdrop-blur-md border border-fuchsia-500/40 rounded-xl shadow-2xl px-4 py-2.5 flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-fuchsia-400 animate-pulse" />
              <span className="text-xs font-medium text-white">
                Click globe to add vertices · {drawPointCount} point{drawPointCount === 1 ? "" : "s"}
              </span>
            </div>
            <div className="h-4 w-px bg-zinc-700" />
            <div className="flex items-center gap-1.5">
              <button
                onClick={undoLastPoint}
                disabled={drawPointCount === 0}
                className="text-[11px] px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Undo
              </button>
              <button
                onClick={finishDrawing}
                disabled={drawPointCount < 3}
                className="text-[11px] px-2.5 py-1 rounded bg-fuchsia-600 hover:bg-fuchsia-500 text-white font-medium disabled:bg-zinc-800 disabled:text-zinc-600 disabled:cursor-not-allowed"
              >
                ✓ Finish ({drawPointCount}/3+)
              </button>
              <button
                onClick={cancelDrawing}
                className="text-[11px] px-2 py-1 rounded bg-zinc-800 hover:bg-red-900/60 hover:text-red-300 text-zinc-400"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ── Save geofence dialog ── */}
        {saveFenceOpen && (
          <div className="absolute inset-0 z-40 bg-black/60 backdrop-blur-sm flex items-center justify-center">
            <div className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-96 overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-700 flex items-center justify-between">
                <span className="text-sm font-semibold text-white">Save Geofence</span>
                <button onClick={cancelDrawing} className="text-zinc-500 hover:text-white">✕</button>
              </div>
              <div className="p-4 space-y-3">
                <div>
                  <label className="text-[10px] uppercase text-zinc-500 font-semibold">Name</label>
                  <input
                    type="text"
                    autoFocus
                    value={fenceForm.name}
                    onChange={(e) => setFenceForm({ ...fenceForm, name: e.target.value })}
                    placeholder="e.g. Strait of Hormuz"
                    className="w-full mt-1 bg-zinc-950 border border-zinc-700 rounded-md px-2.5 py-1.5 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-fuchsia-500"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase text-zinc-500 font-semibold">Category</label>
                  <select
                    value={fenceForm.category}
                    onChange={(e) => setFenceForm({ ...fenceForm, category: e.target.value })}
                    className="w-full mt-1 bg-zinc-950 border border-zinc-700 rounded-md px-2.5 py-1.5 text-sm text-white"
                  >
                    <option value="custom">Custom</option>
                    <option value="military">Military</option>
                    <option value="economic">Economic</option>
                    <option value="environmental">Environmental</option>
                    <option value="political">Political</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase text-zinc-500 font-semibold">Description (optional)</label>
                  <textarea
                    value={fenceForm.description}
                    onChange={(e) => setFenceForm({ ...fenceForm, description: e.target.value })}
                    rows={2}
                    className="w-full mt-1 bg-zinc-950 border border-zinc-700 rounded-md px-2.5 py-1.5 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-fuchsia-500 resize-none"
                  />
                </div>
                <div className="text-[10px] text-zinc-500">
                  {drawPointCount} vertices · alerts will fire when new events enter this area
                </div>
              </div>
              <div className="px-4 py-3 border-t border-zinc-700 flex gap-2 justify-end">
                <button onClick={cancelDrawing} className="text-xs px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300">Cancel</button>
                <button
                  onClick={saveGeofence}
                  disabled={!fenceForm.name.trim()}
                  className="text-xs px-3 py-1.5 rounded bg-fuchsia-600 hover:bg-fuchsia-500 text-white font-medium disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  Save Geofence
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Selected geofence panel (left side) ── */}
        {selectedFence && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 w-72 bg-zinc-900/95 border border-fuchsia-700/40 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-zinc-800/80 border-b border-zinc-700/50">
              <span className="text-xs font-semibold text-fuchsia-300 truncate">⛶ {selectedFence.properties.name}</span>
              <button onClick={() => setSelectedFence(null)} className="text-zinc-500 hover:text-white text-sm">✕</button>
            </div>
            <div className="px-4 py-3 space-y-1.5 text-[11px]">
              <div className="flex justify-between"><span className="text-zinc-500">Category</span><span className="text-zinc-200">{selectedFence.properties.category}</span></div>
              <div className="flex justify-between"><span className="text-zinc-500">Events inside</span><span className="text-fuchsia-300 font-medium">{selectedFence.properties.event_count}</span></div>
              <div className="flex justify-between"><span className="text-zinc-500">Alerts on entry</span><span className="text-zinc-200">{selectedFence.properties.alert_on_entry ? "Yes" : "No"}</span></div>
              {selectedFence.properties.description && (
                <div className="pt-1 text-zinc-400 italic">{selectedFence.properties.description}</div>
              )}
            </div>
            <div className="px-4 pb-3 flex gap-2">
              <button
                onClick={() => deleteGeofence(selectedFence.properties.id)}
                className="flex-1 text-[10px] py-1.5 rounded bg-red-900/40 hover:bg-red-800 text-red-300 hover:text-white transition-colors"
              >
                Delete Geofence
              </button>
            </div>
          </div>
        )}

        {/* ── Selected Entity Detail Panel (right side) ── */}
        {selectedEntity && (
          <div className="absolute top-3 right-3 z-30 w-72 bg-zinc-900/95 border border-zinc-700/70 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-800/80 border-b border-zinc-700/50">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-white truncate">{selectedEntity.title}</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 uppercase">{selectedEntity.type}</span>
              </div>
              <button onClick={() => setSelectedEntity(null)} className="text-zinc-500 hover:text-white text-sm ml-2">✕</button>
            </div>
            <div className="px-4 py-3 space-y-1.5">
              {Object.entries(selectedEntity.details).map(([key, val]) => (
                <div key={key} className="flex justify-between text-[11px]">
                  <span className="text-zinc-500">{key}</span>
                  <span className="text-zinc-200 font-medium">{String(val)}</span>
                </div>
              ))}
            </div>
            {/* Action buttons */}
            <div className="px-4 pb-3 flex gap-2">
              {selectedEntity.type === "flight" && (
                <button onClick={() => flyTo(selectedEntity.lng, selectedEntity.lat, (selectedEntity.alt || 10000) * 1.5)}
                  className="flex-1 text-[10px] py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors">
                  ✈️ Track Flight
                </button>
              )}
              {selectedEntity.type === "vessel" && (
                <button onClick={() => flyTo(selectedEntity.lng, selectedEntity.lat, 2000)}
                  className="flex-1 text-[10px] py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors">
                  🚢 Zoom to Ship
                </button>
              )}
              {selectedEntity.type === "satellite" && (
                <button onClick={() => flyTo(selectedEntity.lng, selectedEntity.lat, (selectedEntity.alt || 500000) * 0.2)}
                  className="flex-1 text-[10px] py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors">
                  🛰 Track Satellite
                </button>
              )}
            </div>
          </div>
        )}

        {/* ── Webcam Stream Panel (right side, below entity panel) ── */}
        {webcamPopup && (
          <div className="absolute bottom-16 right-3 z-30 w-80 bg-zinc-900/98 border border-purple-700/50 rounded-xl shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-zinc-800 border-b border-zinc-700">
              <span className="text-xs font-semibold text-purple-300 truncate">📷 {webcamPopup.title}</span>
              <div className="flex gap-2">
                {webcamPopup.url && (
                  <a href={webcamPopup.url} target="_blank" rel="noopener noreferrer"
                    className="text-[10px] text-zinc-400 hover:text-white px-2 py-0.5 bg-zinc-700 rounded">Open ↗</a>
                )}
                <button onClick={() => setWebcamPopup(null)} className="text-zinc-500 hover:text-white text-xs">✕</button>
              </div>
            </div>
            {webcamPopup.url ? (
              <iframe
                src={webcamPopup.url}
                className="w-full h-52 bg-black"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                referrerPolicy="no-referrer-when-downgrade"
                title={webcamPopup.title}
              />
            ) : (
              <div className="h-32 flex items-center justify-center text-zinc-600 text-xs">No stream URL available</div>
            )}
          </div>
        )}

        {/* ── Street View overlay ── */}
        {streetViewOpen && streetViewPos && (
          <div className="absolute inset-0 z-40 bg-black/70 backdrop-blur-sm flex items-center justify-center">
            <div className="bg-zinc-900 border border-zinc-700 rounded-xl overflow-hidden shadow-2xl w-[90%] max-w-3xl">
              <div className="flex items-center justify-between px-4 py-2 bg-zinc-800 border-b border-zinc-700">
                <span className="text-sm font-medium text-white">
                  🚶 Street View — {streetViewPos.lat.toFixed(4)}°, {streetViewPos.lng.toFixed(4)}°
                </span>
                <div className="flex gap-3 items-center">
                  <a href={`https://maps.google.com/maps?q=&layer=c&cbll=${streetViewPos.lat},${streetViewPos.lng}&cbp=11,0,0,0,0`}
                    target="_blank" rel="noopener noreferrer" className="text-xs text-zinc-400 hover:text-white">
                    Open in Google Maps ↗
                  </a>
                  <button onClick={() => setStreetViewOpen(false)} className="text-zinc-500 hover:text-white text-sm">✕</button>
                </div>
              </div>
              <iframe
                src={`https://maps.google.com/maps?q=&layer=c&cbll=${streetViewPos.lat},${streetViewPos.lng}&cbp=11,0,0,0,0&output=embed`}
                className="w-full h-96 bg-zinc-950" title="Street View" allowFullScreen />
              <div className="px-4 py-2 text-[10px] text-zinc-600">
                Zoom the 3D globe to street level, then click Street View to update this location.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
