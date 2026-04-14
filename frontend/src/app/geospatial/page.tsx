"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────────── */

interface Geofence {
  id: string;
  name: string;
  description: string | null;
  category: string;
  active: number;
  event_count: number;
  bbox_west: number;
  bbox_south: number;
  bbox_east: number;
  bbox_north: number;
}

interface WeaponsSystem {
  id: string;
  name: string;
  system_type: string;
  country_code: string;
  min_range_km: number;
  max_range_km: number;
  altitude_max_km: number | null;
  speed_mach: number | null;
  description: string | null;
}

interface Deployment {
  id: string;
  system_id: string;
  system_name: string;
  system_type: string;
  max_range_km: number;
  name: string | null;
  lat: number;
  lng: number;
  country_code: string | null;
  status: string;
  confidence: number;
}

interface TrajectoryPoint {
  lat: number;
  lng: number;
  altitude_km: number;
  t: number;
}

interface Measurement {
  id: string;
  name: string;
  profile_type: string;
  total_distance_km: number | null;
  total_area_km2: number | null;
  created_at: string;
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

type Tab = "geofences" | "weapons" | "measure" | "trajectories" | "export";

function systemTypeBadge(t: string): string {
  switch (t) {
    case "sam": return "bg-red-500/20 text-red-400 border-red-500/30";
    case "cruise_missile": return "bg-orange-500/20 text-orange-400 border-orange-500/30";
    case "ballistic_missile": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
    case "artillery": return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
    case "radar": return "bg-cyan-500/20 text-cyan-400 border-cyan-500/30";
    default: return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
  }
}

function countryFlag(code: string | null): string {
  if (!code) return "";
  switch (code) {
    case "US": return "🇺🇸";
    case "RU": return "🇷🇺";
    case "CN": return "🇨🇳";
    case "IL": return "🇮🇱";
    default: return code;
  }
}

/* ── Page Component ───────────────────────────────────────────────────── */

export default function GeospatialPage() {
  const [tab, setTab] = useState<Tab>("geofences");
  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [weapons, setWeapons] = useState<WeaponsSystem[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [trajectory, setTrajectory] = useState<{ points: TrajectoryPoint[]; distance_km: number; trajectory_type: string } | null>(null);
  const [measureResult, setMeasureResult] = useState<{ total_distance_km?: number; total_area_km2?: number; segments?: unknown[] } | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [fencesRes, wpnRes, depRes, measRes] = await Promise.all([
        fetch(`${API_URL}/api/geofences`),
        fetch(`${API_URL}/api/weapons`),
        fetch(`${API_URL}/api/deployments`),
        fetch(`${API_URL}/api/measurements`),
      ]);

      if (fencesRes.ok) setGeofences((await fencesRes.json()).geofences);
      if (wpnRes.ok) setWeapons((await wpnRes.json()).weapons_systems);
      if (depRes.ok) setDeployments((await depRes.json()).deployments);
      if (measRes.ok) setMeasurements((await measRes.json()).measurements);
    } catch (e) {
      console.error("Failed to fetch geospatial data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const computeDistance = async () => {
    // Example: London to Paris
    const res = await fetch(`${API_URL}/api/measure/distance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ points: [[51.5074, -0.1278], [48.8566, 2.3522]] }),
    });
    if (res.ok) setMeasureResult(await res.json());
  };

  const computeTrajectory = async (type: "ballistic" | "cruise") => {
    const res = await fetch(`${API_URL}/api/trajectory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        launch_lat: 34, launch_lng: 35,
        target_lat: 50, target_lng: 10,
        trajectory_type: type,
        max_altitude_km: type === "ballistic" ? 150 : 0.05,
        num_points: 30,
      }),
    });
    if (res.ok) setTrajectory(await res.json());
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-lg font-bold tracking-tight text-white hover:text-cyan-300 transition-colors">
              Cerebro
            </Link>
            <span className="text-zinc-600">/</span>
            <h1 className="text-sm font-medium text-zinc-300">Geospatial Tools</h1>
          </div>
          <nav className="flex gap-3 text-sm">
            <Link href="/globe" className="text-zinc-400 hover:text-white transition-colors">Globe</Link>
            <Link href="/events" className="text-zinc-400 hover:text-white transition-colors">Events</Link>
            <Link href="/risk" className="text-zinc-400 hover:text-white transition-colors">Risk</Link>
            <Link href="/entity-intel" className="text-zinc-400 hover:text-white transition-colors">Entities</Link>
          </nav>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Tab bar */}
        <div className="flex gap-1 mb-6 bg-zinc-900/50 rounded-lg p-1 w-fit">
          {([
            { key: "geofences", label: "Geofences" },
            { key: "weapons", label: "Weapons & Range Rings" },
            { key: "measure", label: "Measure" },
            { key: "trajectories", label: "Trajectories" },
            { key: "export", label: "KML Export" },
          ] as { key: Tab; label: string }[]).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === t.key ? "bg-zinc-700 text-white" : "text-zinc-400 hover:text-white hover:bg-zinc-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-20 text-zinc-500">Loading geospatial data...</div>
        ) : (
          <>
            {/* ── Geofences Tab ────────────────────────────────── */}
            {tab === "geofences" && (
              <div className="space-y-4 max-w-4xl">
                <h3 className="text-sm font-semibold text-zinc-300">
                  Active Geofences ({geofences.length})
                </h3>
                {geofences.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No geofences configured. Create one via the API.</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {geofences.map((f) => (
                      <div key={f.id} className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium text-white">{f.name}</span>
                          <span className="px-2 py-0.5 rounded text-xs bg-zinc-800 text-zinc-400">
                            {f.category}
                          </span>
                        </div>
                        {f.description && (
                          <p className="text-xs text-zinc-500 mb-2">{f.description}</p>
                        )}
                        <div className="flex gap-3 text-xs text-zinc-500">
                          <span>{f.event_count} events inside</span>
                          <span>
                            bbox: [{f.bbox_west?.toFixed(1)}, {f.bbox_south?.toFixed(1)}] to [{f.bbox_east?.toFixed(1)}, {f.bbox_north?.toFixed(1)}]
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Weapons Tab ──────────────────────────────────── */}
            {tab === "weapons" && (
              <div className="space-y-6 max-w-5xl">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                    Weapons Systems ({weapons.length})
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {weapons.map((w) => (
                      <div key={w.id} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-white">{w.name}</span>
                          <span className={`px-2 py-0.5 rounded text-xs border ${systemTypeBadge(w.system_type)}`}>
                            {w.system_type.replace("_", " ")}
                          </span>
                          <span className="text-xs">{countryFlag(w.country_code)}</span>
                        </div>
                        <p className="text-xs text-zinc-500">{w.description}</p>
                        <div className="flex gap-3 mt-2 text-xs text-zinc-400">
                          <span>Range: {w.min_range_km}–{w.max_range_km} km</span>
                          {w.speed_mach && <span>Speed: Mach {w.speed_mach}</span>}
                          {w.altitude_max_km && <span>Alt: {w.altitude_max_km} km</span>}
                        </div>
                        {/* Range bar visualization */}
                        <div className="mt-2 h-2 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-red-500/70"
                            style={{ width: `${Math.min(100, (w.max_range_km / 2500) * 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                    Known Deployments ({deployments.length})
                  </h3>
                  {deployments.length === 0 ? (
                    <p className="text-zinc-600 text-sm">No deployments recorded yet.</p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {deployments.map((d) => (
                        <div key={d.id} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50 flex items-center justify-between">
                          <div>
                            <span className="text-sm text-white">{d.name || d.system_name}</span>
                            <span className={`ml-2 px-2 py-0.5 rounded text-xs border ${systemTypeBadge(d.system_type)}`}>
                              {d.system_name}
                            </span>
                            {d.country_code && <span className="ml-2 text-xs">{countryFlag(d.country_code)}</span>}
                          </div>
                          <div className="text-xs text-zinc-500">
                            ({d.lat.toFixed(2)}, {d.lng.toFixed(2)}) · conf={d.confidence} · {d.max_range_km}km range
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Measure Tab ──────────────────────────────────── */}
            {tab === "measure" && (
              <div className="space-y-6 max-w-3xl">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-300 mb-3">Distance Calculator</h3>
                  <button
                    onClick={computeDistance}
                    className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-sm transition-colors"
                  >
                    Compute London → Paris Distance
                  </button>
                  {measureResult && (
                    <div className="mt-3 p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                      <p className="text-lg font-bold text-cyan-400">
                        {measureResult.total_distance_km?.toFixed(1)} km
                      </p>
                      {measureResult.segments && (
                        <p className="text-xs text-zinc-500 mt-1">
                          {(measureResult.segments as { distance_km: number }[]).length} segment(s)
                        </p>
                      )}
                    </div>
                  )}
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                    Saved Measurements ({measurements.length})
                  </h3>
                  {measurements.length === 0 ? (
                    <p className="text-zinc-600 text-sm">No measurements saved.</p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {measurements.map((m) => (
                        <div key={m.id} className="p-2 rounded border border-zinc-800 bg-zinc-900/50 text-xs flex justify-between">
                          <div>
                            <span className="text-white">{m.name}</span>
                            <span className="text-zinc-600 ml-2">{m.profile_type}</span>
                          </div>
                          <div className="text-zinc-500">
                            {m.total_distance_km && <span>{m.total_distance_km.toFixed(1)} km</span>}
                            {m.total_area_km2 && <span>{m.total_area_km2.toFixed(1)} km²</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Trajectories Tab ─────────────────────────────── */}
            {tab === "trajectories" && (
              <div className="space-y-6 max-w-4xl">
                <div className="flex gap-3">
                  <button
                    onClick={() => computeTrajectory("ballistic")}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg text-sm transition-colors"
                  >
                    Simulate Ballistic Arc
                  </button>
                  <button
                    onClick={() => computeTrajectory("cruise")}
                    className="px-4 py-2 bg-orange-600 hover:bg-orange-500 rounded-lg text-sm transition-colors"
                  >
                    Simulate Cruise Trajectory
                  </button>
                </div>

                {trajectory && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-zinc-300">
                        {trajectory.trajectory_type === "ballistic" ? "Ballistic" : "Cruise"} trajectory — {trajectory.distance_km} km
                      </span>
                    </div>

                    {/* Altitude profile */}
                    <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                      <h4 className="text-xs text-zinc-400 mb-2">Altitude Profile</h4>
                      <svg viewBox="0 0 600 200" className="w-full h-48">
                        {/* Grid lines */}
                        {[0, 50, 100, 150].map((alt) => (
                          <line key={alt} x1="40" y1={180 - (alt / 160) * 160} x2="580" y2={180 - (alt / 160) * 160}
                            stroke="#333" strokeWidth="0.5" />
                        ))}
                        {/* Alt labels */}
                        {[0, 50, 100, 150].map((alt) => (
                          <text key={`l-${alt}`} x="5" y={184 - (alt / 160) * 160} fill="#666" fontSize="8">{alt}km</text>
                        ))}
                        {/* Trajectory line */}
                        <polyline
                          fill="none"
                          stroke={trajectory.trajectory_type === "ballistic" ? "#a855f7" : "#f97316"}
                          strokeWidth="2"
                          points={trajectory.points.map((p, i) => {
                            const x = 40 + (i / (trajectory.points.length - 1)) * 540;
                            const maxAlt = Math.max(1, ...trajectory.points.map((pp) => pp.altitude_km));
                            const y = 180 - (p.altitude_km / Math.max(maxAlt, 1)) * 160;
                            return `${x},${y}`;
                          }).join(" ")}
                        />
                        {/* Ground line */}
                        <line x1="40" y1="180" x2="580" y2="180" stroke="#555" strokeWidth="1" />
                      </svg>
                    </div>

                    {/* Data table */}
                    <div className="max-h-48 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="text-zinc-500">
                          <tr>
                            <th className="text-left p-1">t</th>
                            <th className="text-left p-1">Lat</th>
                            <th className="text-left p-1">Lng</th>
                            <th className="text-left p-1">Altitude (km)</th>
                          </tr>
                        </thead>
                        <tbody className="text-zinc-400">
                          {trajectory.points.filter((_, i) => i % 3 === 0).map((p, i) => (
                            <tr key={i} className="border-t border-zinc-800/50">
                              <td className="p-1">{p.t}</td>
                              <td className="p-1">{p.lat.toFixed(3)}</td>
                              <td className="p-1">{p.lng.toFixed(3)}</td>
                              <td className="p-1">{p.altitude_km}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── Export Tab ───────────────────────────────────── */}
            {tab === "export" && (
              <div className="space-y-4 max-w-2xl">
                <h3 className="text-sm font-semibold text-zinc-300 mb-3">KML/KMZ Export</h3>
                <p className="text-xs text-zinc-500">
                  Download data in KML format for use with Google Earth, QGIS, or other GIS tools.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {[
                    { label: "Events (KML)", href: "/api/export/events.kml", desc: "All geolocated events" },
                    { label: "Events (KMZ)", href: "/api/export/events.kmz", desc: "Compressed KML" },
                    { label: "Geofences (KML)", href: "/api/export/geofences.kml", desc: "Monitoring polygons" },
                    { label: "Deployments (KML)", href: "/api/export/deployments.kml", desc: "Weapons positions" },
                  ].map((item) => (
                    <a
                      key={item.href}
                      href={`${API_URL}${item.href}`}
                      download
                      className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800 transition-colors block"
                    >
                      <p className="text-sm font-medium text-cyan-400">{item.label}</p>
                      <p className="text-xs text-zinc-500 mt-1">{item.desc}</p>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
