"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────────── */

interface SatelliteImage {
  id: string;
  source: string;
  lat: number;
  lng: number;
  capture_date: string;
  cloud_cover: number | null;
  thumbnail_url: string | null;
  resolution_m: number | null;
  annotations: Record<string, unknown> | null;
  created_at: string;
}

interface FireDetection {
  id: string;
  lat: number;
  lng: number;
  brightness: number | null;
  frp: number | null;
  confidence: string;
  capture_date: string;
}

interface NightlightReading {
  id: string;
  lat: number;
  lng: number;
  country_code: string | null;
  region: string | null;
  radiance: number;
  baseline_radiance: number;
  change_pct: number;
  capture_date: string;
}

interface DiseaseOutbreak {
  id: string;
  source: string;
  disease: string;
  title: string;
  summary: string | null;
  country_code: string | null;
  case_count: number | null;
  death_count: number | null;
  status: string;
  severity: number;
  published_at: string;
}

interface WeatherEvent {
  id: string;
  event_type: string;
  title: string;
  severity: string | null;
  urgency: string | null;
  lat: number | null;
  lng: number | null;
  area_desc: string | null;
  effective: string | null;
  expires: string | null;
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

type Tab = "satellite" | "fires" | "nightlights" | "outbreaks" | "weather";

function changeColor(pct: number): string {
  if (pct <= -40) return "text-red-400";
  if (pct <= -20) return "text-orange-400";
  if (pct >= 30) return "text-emerald-400";
  return "text-zinc-400";
}

function confidenceColor(conf: string): string {
  if (conf === "high") return "text-red-400";
  if (conf === "nominal") return "text-yellow-400";
  return "text-zinc-500";
}

function severityBadge(sev: string | null): string {
  if (sev === "Extreme") return "bg-red-500/20 text-red-400 border-red-500/30";
  if (sev === "Severe") return "bg-orange-500/20 text-orange-400 border-orange-500/30";
  if (sev === "Moderate") return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
  return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
}

/* ── Swipe Comparator Component ───────────────────────────────────────── */

function SwipeComparator({
  before,
  after,
}: {
  before: SatelliteImage;
  after: SatelliteImage;
}) {
  const [sliderPos, setSliderPos] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const handleMove = useCallback(
    (clientX: number) => {
      if (!containerRef.current || !dragging.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = clientX - rect.left;
      const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
      setSliderPos(pct);
    },
    []
  );

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => handleMove(e.clientX);
    const handleMouseUp = () => { dragging.current = false; };
    const handleTouchMove = (e: TouchEvent) => handleMove(e.touches[0].clientX);

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    window.addEventListener("touchmove", handleTouchMove);
    window.addEventListener("touchend", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleMouseUp);
    };
  }, [handleMove]);

  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden">
      <div className="flex justify-between px-3 py-1 bg-zinc-900 text-xs text-zinc-500">
        <span>Before: {before.capture_date}</span>
        <span>After: {after.capture_date}</span>
      </div>
      <div
        ref={containerRef}
        className="relative h-64 bg-zinc-800 cursor-col-resize select-none"
        onMouseDown={() => { dragging.current = true; }}
        onTouchStart={() => { dragging.current = true; }}
      >
        {/* Before (full width, clipped) */}
        <div
          className="absolute inset-0 flex items-center justify-center bg-zinc-900"
          style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
        >
          <div className="text-center text-zinc-500 text-sm">
            <p className="font-medium">{before.capture_date}</p>
            <p className="text-xs">
              ({before.lat.toFixed(2)}, {before.lng.toFixed(2)})
            </p>
            <p className="text-xs mt-1">
              Cloud: {before.cloud_cover?.toFixed(0) ?? "?"}%
            </p>
            {before.thumbnail_url && (
              <p className="text-xs text-cyan-400 mt-1">Thumbnail available</p>
            )}
          </div>
        </div>

        {/* After (full width, clipped from left) */}
        <div
          className="absolute inset-0 flex items-center justify-center bg-zinc-950"
          style={{ clipPath: `inset(0 0 0 ${sliderPos}%)` }}
        >
          <div className="text-center text-zinc-500 text-sm">
            <p className="font-medium">{after.capture_date}</p>
            <p className="text-xs">
              ({after.lat.toFixed(2)}, {after.lng.toFixed(2)})
            </p>
            <p className="text-xs mt-1">
              Cloud: {after.cloud_cover?.toFixed(0) ?? "?"}%
            </p>
            {after.annotations && (
              <p className="text-xs text-amber-400 mt-1">Claude Vision annotated</p>
            )}
          </div>
        </div>

        {/* Slider line */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white z-10"
          style={{ left: `${sliderPos}%` }}
        >
          <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-6 h-6 bg-white rounded-full flex items-center justify-center shadow-lg">
            <span className="text-black text-xs font-bold">⟷</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Page Component ───────────────────────────────────────────────────── */

export default function SatellitePage() {
  const [tab, setTab] = useState<Tab>("satellite");
  const [images, setImages] = useState<SatelliteImage[]>([]);
  const [fires, setFires] = useState<FireDetection[]>([]);
  const [nightlights, setNightlights] = useState<NightlightReading[]>([]);
  const [outbreaks, setOutbreaks] = useState<DiseaseOutbreak[]>([]);
  const [weather, setWeather] = useState<WeatherEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [satRes, fireRes, nlRes, obRes, wxRes] = await Promise.all([
        fetch(`${API_URL}/api/satellite?limit=20`),
        fetch(`${API_URL}/api/fires?limit=100`),
        fetch(`${API_URL}/api/nightlights?min_change=10`),
        fetch(`${API_URL}/api/outbreaks?limit=30`),
        fetch(`${API_URL}/api/weather?limit=30`),
      ]);

      if (satRes.ok) setImages((await satRes.json()).images);
      if (fireRes.ok) setFires((await fireRes.json()).fires);
      if (nlRes.ok) setNightlights((await nlRes.json()).readings);
      if (obRes.ok) setOutbreaks((await obRes.json()).outbreaks);
      if (wxRes.ok) setWeather((await wxRes.json()).weather_events);
    } catch (e) {
      console.error("Failed to fetch SPECINT data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
            <h1 className="text-sm font-medium text-zinc-300">SPECINT Dashboard</h1>
          </div>
          <nav className="flex gap-3 text-sm">
            <Link href="/globe" className="text-zinc-400 hover:text-white transition-colors">Globe</Link>
            <Link href="/events" className="text-zinc-400 hover:text-white transition-colors">Events</Link>
            <Link href="/briefs" className="text-zinc-400 hover:text-white transition-colors">Briefs</Link>
            <Link href="/query" className="text-zinc-400 hover:text-white transition-colors">Query</Link>
          </nav>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Tab bar */}
        <div className="flex gap-1 mb-6 bg-zinc-900/50 rounded-lg p-1 w-fit">
          {(["satellite", "fires", "nightlights", "outbreaks", "weather"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === t ? "bg-zinc-700 text-white" : "text-zinc-400 hover:text-white hover:bg-zinc-800"
              }`}
            >
              {t === "satellite" ? "Satellite" : t === "fires" ? "Fires" : t === "nightlights" ? "Nightlights" : t === "outbreaks" ? "Outbreaks" : "Weather"}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-20 text-zinc-500">Loading SPECINT data...</div>
        ) : (
          <>
            {/* ── Satellite Tab ─────────────────────────────────── */}
            {tab === "satellite" && (
              <div className="space-y-6">
                {/* Swipe Comparator */}
                {images.length >= 2 && (
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-300 mb-3">Before/After Comparator</h3>
                    <SwipeComparator before={images[1]} after={images[0]} />
                  </div>
                )}

                {/* Image grid */}
                <div>
                  <h3 className="text-sm font-semibold text-zinc-300 mb-3">Cached Imagery ({images.length})</h3>
                  {images.length === 0 ? (
                    <p className="text-zinc-600 text-sm">No satellite imagery cached yet.</p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {images.map((img) => (
                        <div key={img.id} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
                          <div className="flex justify-between items-start mb-2">
                            <span className="text-xs text-cyan-400 font-medium">{img.source}</span>
                            <span className="text-xs text-zinc-600">{img.capture_date}</span>
                          </div>
                          <p className="text-xs text-zinc-400 mb-1">
                            ({img.lat.toFixed(2)}, {img.lng.toFixed(2)}) · {img.resolution_m}m
                          </p>
                          <p className="text-xs text-zinc-600">
                            Cloud: {img.cloud_cover?.toFixed(0) ?? "?"}%
                          </p>
                          {img.annotations && (
                            <p className="text-xs text-amber-400 mt-1">Annotated by Claude Vision</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Fires Tab ─────────────────────────────────────── */}
            {tab === "fires" && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                  Active Fire Detections ({fires.length})
                </h3>
                {fires.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No fire detections loaded.</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                    {fires.map((f) => (
                      <div key={f.id} className="p-2 rounded border border-zinc-800 bg-zinc-900/50 text-xs">
                        <div className="flex justify-between">
                          <span className={confidenceColor(f.confidence)}>
                            {f.confidence.toUpperCase()}
                          </span>
                          <span className="text-zinc-600">{f.capture_date}</span>
                        </div>
                        <p className="text-zinc-400 mt-1">
                          ({f.lat.toFixed(3)}, {f.lng.toFixed(3)})
                        </p>
                        {f.frp && <p className="text-zinc-500">FRP: {f.frp.toFixed(1)} MW</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Nightlights Tab ───────────────────────────────── */}
            {tab === "nightlights" && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                  Nightlight Anomalies ({nightlights.length})
                </h3>
                {nightlights.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No nightlight anomalies detected.</p>
                ) : (
                  <div className="flex flex-col gap-2 max-w-3xl">
                    {nightlights.map((n) => (
                      <div key={n.id} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
                        <div className="flex justify-between items-start">
                          <div>
                            <span className={`text-sm font-semibold ${changeColor(n.change_pct)}`}>
                              {n.change_pct > 0 ? "+" : ""}{n.change_pct.toFixed(1)}%
                            </span>
                            {n.country_code && (
                              <span className="ml-2 text-xs text-zinc-500">{n.country_code}</span>
                            )}
                            {n.region && (
                              <span className="ml-2 text-xs text-zinc-600">{n.region}</span>
                            )}
                          </div>
                          <span className="text-xs text-zinc-600">{n.capture_date}</span>
                        </div>
                        <p className="text-xs text-zinc-500 mt-1">
                          Radiance: {n.baseline_radiance.toFixed(1)} → {n.radiance.toFixed(1)} nW/cm²/sr
                        </p>
                        <p className="text-xs text-zinc-400 mt-0.5">
                          ({n.lat.toFixed(2)}, {n.lng.toFixed(2)})
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Outbreaks Tab ─────────────────────────────────── */}
            {tab === "outbreaks" && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                  Disease Outbreaks ({outbreaks.length})
                </h3>
                {outbreaks.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No disease outbreaks tracked.</p>
                ) : (
                  <div className="flex flex-col gap-2 max-w-4xl">
                    {outbreaks.map((o) => (
                      <div key={o.id} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-semibold text-red-400">{o.disease}</span>
                          <span className={`px-2 py-0.5 rounded text-xs border ${
                            o.status === "active" ? "bg-red-500/20 text-red-400 border-red-500/30" :
                            "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"
                          }`}>
                            {o.status}
                          </span>
                          <span className="text-xs text-zinc-600">sev={o.severity}</span>
                          {o.country_code && <span className="text-xs text-zinc-500">{o.country_code}</span>}
                        </div>
                        <p className="text-sm text-zinc-300">{o.title}</p>
                        {o.summary && <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{o.summary}</p>}
                        <div className="flex gap-3 mt-1 text-xs text-zinc-600">
                          {o.case_count !== null && <span>Cases: {o.case_count.toLocaleString()}</span>}
                          {o.death_count !== null && <span>Deaths: {o.death_count.toLocaleString()}</span>}
                          <span>{o.source}</span>
                          <span>{o.published_at?.slice(0, 10)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Weather Tab ───────────────────────────────────── */}
            {tab === "weather" && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                  Weather Alerts ({weather.length})
                </h3>
                {weather.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No active weather alerts.</p>
                ) : (
                  <div className="flex flex-col gap-2 max-w-4xl">
                    {weather.map((w) => (
                      <div key={w.id} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`px-2 py-0.5 rounded text-xs border ${severityBadge(w.severity)}`}>
                            {w.severity || "Unknown"}
                          </span>
                          <span className="text-xs text-zinc-600">{w.event_type}</span>
                          {w.urgency && <span className="text-xs text-amber-400">{w.urgency}</span>}
                        </div>
                        <p className="text-sm text-zinc-300">{w.title}</p>
                        {w.area_desc && <p className="text-xs text-zinc-500 mt-1">{w.area_desc}</p>}
                        <div className="flex gap-3 mt-1 text-xs text-zinc-600">
                          {w.effective && <span>From: {w.effective.slice(0, 16)}</span>}
                          {w.expires && <span>Until: {w.expires.slice(0, 16)}</span>}
                          {w.lat && w.lng && <span>({w.lat.toFixed(2)}, {w.lng.toFixed(2)})</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
