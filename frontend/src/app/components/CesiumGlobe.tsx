"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { useCesiumViewer } from "./cesium/useCesiumViewer";

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

// Create SVG airplane billboard — proper airplane silhouette
function createAirplaneSVG(color: string): string {
  // Top-down airplane: fuselage + swept wings + tail
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><g fill="${color}" stroke="#000" stroke-width="0.4"><path d="M16 1 L17.5 10 L28 15 L17.5 17 L18 26 L16 24 L14 26 L14.5 17 L4 15 L14.5 10Z"/><path d="M14 24 L12 28 L16 26 L20 28 L18 24" opacity="0.8"/></g></svg>`)}`;
}
// Create SVG ship billboard — boat hull shape
function createShipSVG(color: string): string {
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="${color}" stroke="#000" stroke-width="0.4"><path d="M12 2 L15 8 L15 16 L18 20 L6 20 L9 16 L9 8Z"/><rect x="11" y="6" width="2" height="10" fill="#fff" opacity="0.3"/></g></svg>`)}`;
}
// Create SVG webcam billboard — camera icon
function createWebcamSVG(): string {
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#7c3aed" stroke="#c084fc" stroke-width="1.5"/><rect x="6" y="8" width="12" height="8" rx="1.5" fill="#fff" opacity="0.9"/><circle cx="12" cy="12" r="2.5" fill="#7c3aed"/><path d="M9 8 L12 5 L15 8" fill="#fff" opacity="0.7"/></svg>`)}`;
}
// Create SVG fire billboard — flame icon
function createFireSVG(): string {
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><path d="M10 1 C10 1 14 6 14 10 C14 13 12 15 10 16 C8 15 6 13 6 10 C6 6 10 1 10 1Z" fill="#ff4500" stroke="#fbbf24" stroke-width="0.8"/><path d="M10 7 C10 7 12 9 12 11 C12 12.5 11 13.5 10 14 C9 13.5 8 12.5 8 11 C8 9 10 7 10 7Z" fill="#fbbf24"/></svg>`)}`;
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
  const [showBuildings, setShowBuildings] = useState(true);
  const [showAtmosphere, setShowAtmosphere] = useState(true);
  const [showLighting, setShowLighting] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

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

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchEvents(), fetchVesselsAndFlights(), fetchFires(), fetchSatellites(), fetchWebcams()])
      .finally(() => setLoading(false));
  }, [fetchEvents, fetchVesselsAndFlights, fetchFires, fetchSatellites, fetchWebcams]);

  // ─── Camera altitude monitor ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    const interval = setInterval(() => {
      if (!viewer.isDestroyed()) setCameraAlt(viewer.camera.positionCartographic.height);
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

  // ─── Click handlers — zoom to entity + show 3D model + detail panel ───

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    import("cesium").then((Cesium) => {
      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

      // Track the 3D model entity shown on click so we can remove it later
      let activeModel: InstanceType<typeof Cesium.Entity> | null = null;

      // Double-click → zoom in toward globe position
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      handler.setInputAction((movement: any) => {
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

      // Single click → select entity, show 3D model + detail panel
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      handler.setInputAction((movement: any) => {
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

  // ─── Render ───

  return (
    <div className="h-full w-full bg-zinc-950 text-white flex relative">

      {/* ── Top-left badge + toggle ── */}
      <div className="absolute top-2 left-2 z-20 flex items-center gap-2 pointer-events-auto">
        <button
          onClick={() => setSidebarCollapsed(p => !p)}
          className="w-8 h-8 rounded-lg bg-zinc-900/90 border border-zinc-700/50 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-800 transition-all text-xs backdrop-blur-sm"
          title={sidebarCollapsed ? "Show layer controls" : "Hide layer controls"}
        >
          {sidebarCollapsed ? "☰" : "✕"}
        </button>
        {sidebarCollapsed && (
          <div className="flex items-center gap-2 bg-zinc-900/80 backdrop-blur-sm rounded-lg border border-zinc-700/30 px-2.5 py-1.5 text-[10px] text-zinc-400">
            {loading && <span className="text-cyan-400 animate-pulse">Loading…</span>}
            <span className="text-red-400">{events.length} events</span>
            {fires.length > 0 && <span className="text-orange-400">🔥{fires.length}</span>}
            {webcams.length > 0 && <span className="text-purple-400">📷{webcams.length}</span>}
            {satelliteOrbits?.features?.length ? <span className="text-cyan-400">🛰{satelliteOrbits.features.length}</span> : null}
            {vessels.length > 0 && <span className="text-blue-400">{vessels.length} vessels</span>}
            {flights.length > 0 && <span className="text-zinc-300">{flights.length} flights</span>}
            <span className="text-emerald-400 font-medium">3D</span>
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
      <aside className={`absolute top-12 left-2 z-20 transition-all duration-300 rounded-xl overflow-hidden ${sidebarCollapsed ? "w-0 opacity-0 pointer-events-none" : "w-60 opacity-100"}`}>
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
        <div ref={containerRef} className="w-full h-full" />

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
