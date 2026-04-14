"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SlimHeader() {
  const [health, setHealth] = useState<{
    status: string;
    counts?: { events: number; entities: number; alerts: number };
  } | null>(null);
  const [clock, setClock] = useState("");

  // Fetch health on mount + every 30s
  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch(`${API_URL}/health`);
        if (res.ok) setHealth(await res.json());
      } catch {
        setHealth(null);
      }
    };
    fetchHealth();
    const timer = setInterval(fetchHealth, 30_000);
    return () => clearInterval(timer);
  }, []);

  // UTC clock
  useEffect(() => {
    const tick = () => {
      setClock(
        new Date().toLocaleTimeString("en-US", {
          timeZone: "UTC",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
      );
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  const isHealthy = health?.status === "healthy";

  return (
    <header className="h-10 shrink-0 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800/40 flex items-center justify-between px-4 z-[15]">
      {/* Left: logo + status */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold tracking-tight text-white">
          Cerebro
        </span>
        <div className="flex items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isHealthy ? "bg-emerald-400" : "bg-red-500 animate-pulse"
            }`}
          />
          <span className="text-[10px] text-zinc-500">
            {isHealthy ? "ONLINE" : "OFFLINE"}
          </span>
        </div>
      </div>

      {/* Center: counts */}
      {health?.counts && (
        <div className="flex items-center gap-4 text-[10px] text-zinc-500">
          <span>
            <span className="text-zinc-400 font-medium">{health.counts.events.toLocaleString()}</span> events
          </span>
          <span>
            <span className="text-zinc-400 font-medium">{health.counts.entities.toLocaleString()}</span> entities
          </span>
          {health.counts.alerts > 0 && (
            <span className="text-red-400 font-medium">
              {health.counts.alerts} alerts
            </span>
          )}
        </div>
      )}

      {/* Right: clock + shortcut hint */}
      <div className="flex items-center gap-3">
        <span className="text-[10px] font-mono text-zinc-500">
          {clock} <span className="text-zinc-600">UTC</span>
        </span>
        <kbd className="text-[9px] text-zinc-600 border border-zinc-800 rounded px-1.5 py-0.5 bg-zinc-900/50">
          ⌘K
        </kbd>
      </div>
    </header>
  );
}
