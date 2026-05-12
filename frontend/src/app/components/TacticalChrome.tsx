"use client";

import { useEffect, useState } from "react";

export type StylePreset = "off" | "crt" | "nightvision" | "flir";

interface Props {
  preset: StylePreset;
  onPresetChange: (p: StylePreset) => void;
  stats: { entities: number; sources: number; density: number; frameMs: number };
  coords: { lat: number; lng: number; alt: number };
  pinLabel?: string | null;
}

/** Format a 6/8-digit MGRS-ish reference from lat/lng (approximate, for HUD aesthetic). */
function fmtMGRS(lat: number, lng: number): string {
  // Simplified UTM-like grid string for HUD display only — not a real MGRS conversion.
  const zone = Math.floor((lng + 180) / 6) + 1;
  const band = "CDEFGHJKLMNPQRSTUVWX"[Math.max(0, Math.min(19, Math.floor((lat + 80) / 8)))];
  const e = Math.floor((((lng % 6) + 6) % 6) * 16666);
  const n = Math.floor((((lat % 8) + 8) % 8) * 12500);
  return `${zone.toString().padStart(2, "0")}${band} ${String(e).padStart(5, "0").slice(0, 5)} ${String(n).padStart(5, "0").slice(0, 5)}`;
}

function fmtDMS(value: number, posChar: string, negChar: string): string {
  const sign = value < 0 ? negChar : posChar;
  const abs = Math.abs(value);
  const d = Math.floor(abs);
  const m = Math.floor((abs - d) * 60);
  const s = ((abs - d) * 60 - m) * 60;
  return `${d.toString().padStart(2, "0")}°${m.toString().padStart(2, "0")}'${s.toFixed(2).padStart(5, "0")}"${sign}`;
}

/** Tactical/CRT chrome overlay — classification banners, MGRS, stats, REC timestamp. */
export default function TacticalChrome({ preset, onPresetChange, stats, coords, pinLabel }: Props) {
  const [now, setNow] = useState(() => new Date());
  // Clock tick for REC timestamp
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  if (preset === "off") return null;

  const stamp = now.toISOString().replace("T", " ").slice(0, 19) + "Z";
  // Pseudo orbital pass identifier — purely cosmetic
  const orbId = 47000 + Math.floor((now.getTime() / 60000) % 1000);
  const passId = `DESC-${Math.floor((now.getTime() / 600000) % 999)}`;

  const styleClasses: Record<StylePreset, string> = {
    off: "",
    crt: "text-amber-400",
    nightvision: "text-emerald-400",
    flir: "text-orange-300",
  };

  const accent = styleClasses[preset];

  return (
    <>
      {/* ─── Scanlines overlay (mix-blend-multiply so it doesn't fully darken) ─── */}
      <div
        className="pointer-events-none absolute inset-0 z-20"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, rgba(0,0,0,0.18) 0px, rgba(0,0,0,0.18) 1px, transparent 1px, transparent 3px)",
          mixBlendMode: "multiply",
        }}
      />
      {/* CRT phosphor vignette */}
      <div
        className="pointer-events-none absolute inset-0 z-20"
        style={{
          background:
            "radial-gradient(circle at center, transparent 55%, rgba(0,0,0,0.45) 88%, rgba(0,0,0,0.85) 100%)",
        }}
      />

      {/* ─── Top-left: WORLDVIEW branding + classification ─── */}
      <div className={`pointer-events-none absolute top-3 left-16 z-30 font-mono ${accent}`}>
        <div className="flex items-baseline gap-2 leading-none">
          <span className="text-2xl font-extrabold tracking-[0.18em]">WORLDVIEW</span>
        </div>
        <div className="text-[10px] tracking-[0.35em] opacity-80 mt-0.5">
          NO PLACE LEFT BEHIND
        </div>
        <div className="mt-3 text-[10px] tracking-[0.18em] font-bold border-l-2 border-current pl-1.5">
          TOP SECRET // SI-TK // NOFORN
        </div>
        <div className="text-[9px] opacity-70 mt-0.5 pl-1.5">
          KH11-{orbId} OPS-{(orbId * 7) % 9999}
        </div>
      </div>

      {/* ─── Top-right: REC + orbital pass ─── */}
      <div className={`pointer-events-none absolute top-3 right-3 z-30 font-mono text-right ${accent}`}>
        <div className="flex items-center justify-end gap-1.5 text-[10px] font-bold tracking-widest">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span>REC {stamp}</span>
        </div>
        <div className="text-[9px] opacity-80 mt-0.5 tracking-widest">
          ORB: {orbId} PASS: {passId}
        </div>
      </div>

      {/* ─── Top-center: stats line (OPTIC VIS:N SRC:N DENS:N Nms) ─── */}
      <div className={`pointer-events-none absolute top-3 left-1/2 -translate-x-1/2 z-30 font-mono text-[10px] tracking-widest opacity-85 ${accent}`}>
        <span className="opacity-70">OPTIC</span>{" "}
        <span>VIS:{stats.entities}</span>{" "}
        <span>SRC:{stats.sources}</span>{" "}
        <span>DENS:{stats.density.toFixed(2)}</span>{" "}
        <span>{stats.frameMs.toFixed(1)}ms</span>
      </div>

      {/* ─── Bottom-left: MGRS coords + DMS ─── */}
      <div className={`pointer-events-none absolute bottom-4 left-4 z-30 font-mono text-[10px] tracking-wider ${accent}`}>
        <div className="opacity-80">L_ MGRS: {fmtMGRS(coords.lat, coords.lng)}</div>
        <div className="opacity-70 mt-0.5">
          {fmtDMS(coords.lat, "N", "S")} {fmtDMS(coords.lng, "E", "W")}
        </div>
        <div className="opacity-60 mt-0.5">ALT: {Math.round(coords.alt).toLocaleString()} m</div>
        {pinLabel && <div className="opacity-80 mt-0.5">📍 {pinLabel}</div>}
      </div>

      {/* ─── Style preset switcher (bottom-right) ─── */}
      <div className="absolute bottom-4 right-4 z-40 pointer-events-auto">
        <div className={`font-mono text-[9px] tracking-widest mb-1 opacity-70 ${accent}`}>STYLE PRESETS</div>
        <div className="flex gap-1">
          {(["off", "crt", "nightvision", "flir"] as StylePreset[]).map((p) => (
            <button
              key={p}
              onClick={() => onPresetChange(p)}
              className={`font-mono text-[10px] uppercase tracking-wider px-2 py-1 rounded border transition-colors ${
                preset === p
                  ? "bg-zinc-900/90 border-current text-current"
                  : "bg-zinc-900/60 border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-500"
              }`}
            >
              {p === "nightvision" ? "NV" : p}
            </button>
          ))}
        </div>
      </div>

      {/* ─── Side ticks (decorative — left edge) ─── */}
      <div className={`pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 z-30 font-mono text-[8px] opacity-50 leading-tight ${accent}`}>
        {[60, 45, 30, 15, 0, -15, -30, -45, -60].map((v) => (
          <div key={v} className="my-2 flex items-center gap-1">
            <span className="w-2 h-px bg-current" />
            <span>{v >= 0 ? "+" : ""}{v}°</span>
          </div>
        ))}
      </div>
    </>
  );
}

/** CSS filter string applied to the Cesium canvas for each preset. */
export function presetFilter(p: StylePreset): string {
  switch (p) {
    case "crt":
      return "sepia(0.45) saturate(1.35) hue-rotate(-15deg) contrast(1.08) brightness(0.95)";
    case "nightvision":
      return "hue-rotate(70deg) saturate(2.2) contrast(1.25) brightness(0.85)";
    case "flir":
      return "invert(1) hue-rotate(180deg) saturate(2.5) contrast(1.3)";
    default:
      return "";
  }
}
