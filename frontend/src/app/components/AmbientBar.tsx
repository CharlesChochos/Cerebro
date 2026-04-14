"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TickerEvent {
  title: string;
  severity: number;
  timestamp: string;
  category: string | null;
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function AmbientBar() {
  const [items, setItems] = useState<TickerEvent[]>([]);

  useEffect(() => {
    const fetchLatest = async () => {
      try {
        const res = await fetch(`${API_URL}/api/events?limit=15&sort=timestamp&order=desc`);
        if (res.ok) {
          const data = await res.json();
          const events = (data.events || data || []).slice(0, 15);
          setItems(
            events.map((e: Record<string, unknown>) => ({
              title: (e.title as string) || "Unknown event",
              severity: (e.severity as number) || 0,
              timestamp: (e.timestamp as string) || "",
              category: (e.category as string) || null,
            }))
          );
        }
      } catch {
        /* offline — no ticker */
      }
    };
    fetchLatest();
    const timer = setInterval(fetchLatest, 60_000);
    return () => clearInterval(timer);
  }, []);

  if (items.length === 0) return null;

  return (
    <div className="h-7 shrink-0 bg-zinc-950/90 border-t border-zinc-800/40 overflow-hidden z-[5] flex items-center">
      <div className="bg-red-600 px-2.5 py-0.5 text-[9px] font-bold text-white shrink-0 h-full flex items-center">
        LIVE
      </div>
      <div className="overflow-hidden whitespace-nowrap flex-1">
        <div
          className="inline-block whitespace-nowrap"
          style={{ animation: `cerebro-ticker ${Math.max(30, items.length * 5)}s linear infinite` }}
        >
          {items.map((item, i) => (
            <span key={i} className="inline-block mx-5 text-[11px]">
              <span
                className={`font-medium ${
                  item.severity > 70
                    ? "text-red-400"
                    : item.severity > 40
                    ? "text-amber-400"
                    : "text-zinc-400"
                }`}
              >
                {item.title}
              </span>
              <span className="text-zinc-600 ml-2">{formatTime(item.timestamp)}</span>
            </span>
          ))}
          {/* Duplicate for seamless loop */}
          {items.map((item, i) => (
            <span key={`dup-${i}`} className="inline-block mx-5 text-[11px]">
              <span
                className={`font-medium ${
                  item.severity > 70
                    ? "text-red-400"
                    : item.severity > 40
                    ? "text-amber-400"
                    : "text-zinc-400"
                }`}
              >
                {item.title}
              </span>
              <span className="text-zinc-600 ml-2">{formatTime(item.timestamp)}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
