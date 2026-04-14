"use client";

import { usePanels, type PanelZone } from "../contexts/PanelContext";

export interface PanelDef {
  id: string;
  label: string;
  icon: string;
  zone: PanelZone;
  shortcut?: string;
}

export const PANEL_REGISTRY: PanelDef[] = [
  { id: "events", label: "Events", icon: "⚡", zone: "right", shortcut: "E" },
  { id: "entities", label: "Entities", icon: "👤", zone: "right" },
  { id: "intel", label: "Intel Briefs", icon: "📋", zone: "right" },
  { id: "risk", label: "Risk & Alerts", icon: "🔴", zone: "right" },
  { id: "entity-intel", label: "Entity Intel", icon: "🕵️", zone: "right" },
  { id: "sources", label: "Sources", icon: "📡", zone: "right" },
  { id: "satellite", label: "Satellite", icon: "🛰️", zone: "bottom" },
  { id: "geospatial", label: "Geospatial", icon: "🌐", zone: "bottom" },
  { id: "output", label: "Output", icon: "📤", zone: "right" },
];

export default function NavRail() {
  const { activeRight, activeBottom, togglePanel } = usePanels();

  return (
    <nav className="w-14 shrink-0 bg-zinc-950/95 border-r border-zinc-800/60 flex flex-col items-center py-3 gap-1 z-10 backdrop-blur-sm">
      {/* Logo */}
      <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500/20 to-emerald-500/20 border border-cyan-500/30 flex items-center justify-center mb-4 cursor-default" title="Cerebro">
        <span className="text-sm font-bold text-cyan-400">C</span>
      </div>

      {/* Panel icons */}
      {PANEL_REGISTRY.map((panel) => {
        const isActive =
          (panel.zone === "right" && activeRight === panel.id) ||
          (panel.zone === "bottom" && activeBottom === panel.id);

        return (
          <button
            key={panel.id}
            onClick={() => togglePanel(panel.id, panel.zone)}
            className={`group relative w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-200 ${
              isActive
                ? "bg-cyan-500/15 text-white border border-cyan-500/30"
                : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/60 border border-transparent"
            }`}
            title={panel.label}
          >
            <span className="text-base">{panel.icon}</span>

            {/* Active indicator bar */}
            {isActive && (
              <span className="absolute left-0 top-2 bottom-2 w-0.5 bg-cyan-400 rounded-r" />
            )}

            {/* Tooltip */}
            <span className="absolute left-full ml-2 px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-[10px] text-zinc-300 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
              {panel.label}
            </span>
          </button>
        );
      })}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Chat toggle at bottom */}
      <button
        onClick={() => togglePanel("query", "chat")}
        className="w-10 h-10 rounded-lg flex items-center justify-center text-zinc-500 hover:text-emerald-400 hover:bg-emerald-500/10 border border-transparent hover:border-emerald-500/20 transition-all"
        title="Ask Cerebro"
      >
        <span className="text-base">💬</span>
      </button>
    </nav>
  );
}
