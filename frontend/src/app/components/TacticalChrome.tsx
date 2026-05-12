"use client";

export type StylePreset = "off" | "crt" | "nightvision" | "flir";

interface Props {
  preset: StylePreset;
  onPresetChange: (p: StylePreset) => void;
}

/** Minimal visual overlay: scanlines + vignette + style preset switcher.
 *  No chrome text, no classification banners — just the CRT/NV/FLIR look. */
export default function TacticalChrome({ preset, onPresetChange }: Props) {
  const accent: Record<StylePreset, string> = {
    off: "text-zinc-400",
    crt: "text-amber-400",
    nightvision: "text-emerald-400",
    flir: "text-orange-300",
  };

  return (
    <>
      {/* Scanlines + vignette only render when a style preset is active */}
      {preset !== "off" && (
        <>
          <div
            className="pointer-events-none absolute inset-0 z-20"
            style={{
              backgroundImage:
                "repeating-linear-gradient(0deg, rgba(0,0,0,0.18) 0px, rgba(0,0,0,0.18) 1px, transparent 1px, transparent 3px)",
              mixBlendMode: "multiply",
            }}
          />
          <div
            className="pointer-events-none absolute inset-0 z-20"
            style={{
              background:
                "radial-gradient(circle at center, transparent 60%, rgba(0,0,0,0.40) 90%, rgba(0,0,0,0.75) 100%)",
            }}
          />
        </>
      )}

      {/* Compact style preset switcher (bottom-right, always visible) */}
      <div className="absolute bottom-4 right-4 z-40 pointer-events-auto">
        <div className="flex gap-1">
          {(["off", "crt", "nightvision", "flir"] as StylePreset[]).map((p) => (
            <button
              key={p}
              onClick={() => onPresetChange(p)}
              className={`font-mono text-[10px] uppercase tracking-wider px-2 py-1 rounded border transition-colors ${
                preset === p
                  ? `bg-zinc-900/90 border-current ${accent[p]}`
                  : "bg-zinc-900/60 border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-500"
              }`}
              title={p === "off" ? "Normal view" : `${p.toUpperCase()} optic mode`}
            >
              {p === "nightvision" ? "NV" : p}
            </button>
          ))}
        </div>
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
