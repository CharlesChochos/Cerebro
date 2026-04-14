"use client";

import dynamic from "next/dynamic";
import { PanelProvider } from "./contexts/PanelContext";
import SlimHeader from "./components/SlimHeader";
import NavRail from "./components/NavRail";
import GlobeView from "./components/GlobeView";
import PanelShell from "./components/PanelShell";
import FloatingChat from "./components/FloatingChat";
import AmbientBar from "./components/AmbientBar";

// Feature flag: use CesiumJS 3D globe or fall back to MapLibre 2.5D
const USE_CESIUM = process.env.NEXT_PUBLIC_USE_CESIUM === "true";

const CesiumGlobe = USE_CESIUM
  ? dynamic(() => import("./components/CesiumGlobe"), {
      ssr: false,
      loading: () => (
        <div className="h-full w-full flex items-center justify-center bg-zinc-950 text-zinc-500 text-sm">
          Loading 3D Globe…
        </div>
      ),
    })
  : null;

const Globe = CesiumGlobe ?? GlobeView;

export default function Home() {
  return (
    <PanelProvider>
      <div className="h-screen w-screen overflow-hidden flex flex-col bg-zinc-950 text-white">
        <SlimHeader />

        <div className="flex flex-1 overflow-hidden relative">
          <NavRail />

          {/* Globe fills the remaining space */}
          <div className="flex-1 relative overflow-hidden">
            <Globe />
          </div>
        </div>

        <AmbientBar />

        {/* Overlay layers */}
        <PanelShell />
        <FloatingChat />
      </div>
    </PanelProvider>
  );
}
