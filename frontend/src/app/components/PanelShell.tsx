"use client";

import { Suspense, lazy, useEffect, useRef, type ComponentType } from "react";
import { usePanels } from "../contexts/PanelContext";

/* ── Lazy-loaded panel components ── */
const panelComponents: Record<string, () => Promise<{ default: ComponentType }>> = {
  events: () => import("../panels/EventsPanel"),
  entities: () => import("../panels/EntitiesPanel"),
  intel: () => import("../panels/BriefsPanel"),
  risk: () => import("../panels/RiskPanel"),
  "entity-intel": () => import("../panels/EntityIntelPanel"),
  sources: () => import("../panels/SourcesPanel"),
  satellite: () => import("../panels/SatellitePanel"),
  geospatial: () => import("../panels/GeospatialPanel"),
  output: () => import("../panels/OutputPanel"),
};

// Build lazy components once
const lazyPanels: Record<string, React.LazyExoticComponent<ComponentType>> = {};
for (const [id, loader] of Object.entries(panelComponents)) {
  lazyPanels[id] = lazy(loader);
}

function PanelLoading() {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="w-5 h-5 border-2 border-cyan-500/40 border-t-cyan-400 rounded-full animate-spin" />
    </div>
  );
}

interface PanelShellProps {
  /** Called when panels open/close so the map can call resize() */
  onLayoutChange?: () => void;
}

export default function PanelShell({ onLayoutChange }: PanelShellProps) {
  const { activeRight, activeBottom, closePanel } = usePanels();
  const rightRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Notify parent (globe) of layout changes for map.resize()
  useEffect(() => {
    onLayoutChange?.();
  }, [activeRight, activeBottom, onLayoutChange]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (activeRight) closePanel("right");
        else if (activeBottom) closePanel("bottom");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeRight, activeBottom, closePanel]);

  const RightComponent = activeRight && lazyPanels[activeRight];
  const BottomComponent = activeBottom && lazyPanels[activeBottom];

  return (
    <>
      {/* ── Right Drawer ── */}
      <div
        ref={rightRef}
        className={`fixed top-0 right-0 h-full z-30 transition-transform duration-300 ease-in-out ${
          activeRight ? "translate-x-0" : "translate-x-full"
        }`}
        style={{ width: 460 }}
      >
        <div className="h-full bg-zinc-950/95 backdrop-blur-md border-l border-zinc-800/60 flex flex-col overflow-hidden shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/60 shrink-0">
            <h2 className="text-sm font-semibold text-zinc-200 capitalize">
              {activeRight?.replace("-", " ") ?? ""}
            </h2>
            <button
              onClick={() => closePanel("right")}
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-zinc-800 text-zinc-500 hover:text-white transition-colors text-xs"
            >
              ✕
            </button>
          </div>

          {/* Panel Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {RightComponent && (
              <Suspense fallback={<PanelLoading />}>
                <RightComponent />
              </Suspense>
            )}
          </div>
        </div>
      </div>

      {/* ── Bottom Sheet ── */}
      <div
        ref={bottomRef}
        className={`fixed bottom-0 left-14 right-0 z-20 transition-transform duration-300 ease-in-out ${
          activeBottom ? "translate-y-0" : "translate-y-full"
        }`}
        style={{ height: "40vh" }}
      >
        <div className="h-full bg-zinc-950/95 backdrop-blur-md border-t border-zinc-800/60 flex flex-col overflow-hidden shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/60 shrink-0">
            <h2 className="text-sm font-semibold text-zinc-200 capitalize">
              {activeBottom?.replace("-", " ") ?? ""}
            </h2>
            <button
              onClick={() => closePanel("bottom")}
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-zinc-800 text-zinc-500 hover:text-white transition-colors text-xs"
            >
              ✕
            </button>
          </div>

          {/* Panel Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {BottomComponent && (
              <Suspense fallback={<PanelLoading />}>
                <BottomComponent />
              </Suspense>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
