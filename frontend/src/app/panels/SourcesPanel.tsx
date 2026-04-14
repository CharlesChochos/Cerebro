"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SourceInfo {
  source: string;
  total_events: number;
  confirmed_events: number;
  accuracy: number | null;
  last_ingestion: string | null;
  avg_latency_seconds: number | null;
  status: string;
  event_count_in_db: number;
  categories: Record<string, number>;
}

interface SourcesResponse {
  sources: SourceInfo[];
}

const SOURCE_LABELS: Record<string, string> = {
  gdelt: "GDELT Events 2.0",
  rss: "RSS Feeds (39 sources)",
  yahoo_finance: "Yahoo Finance",
  worldbank: "World Bank",
  fred: "FRED Economic Data",
  acled: "ACLED Conflict Data",
};

function accuracyColor(score: number | null): string {
  if (score === null) return "text-zinc-500";
  if (score >= 0.9) return "text-emerald-400";
  if (score >= 0.7) return "text-yellow-400";
  if (score >= 0.5) return "text-orange-400";
  return "text-red-400";
}

function statusColor(status: string): string {
  if (status === "active") return "text-emerald-400";
  if (status === "degraded") return "text-yellow-400";
  return "text-red-400";
}

function formatTime(ts: string | null): string {
  if (!ts) return "Never";
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function SourcesPanel() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchSources() {
      try {
        const res = await fetch(`${API_URL}/api/sources`);
        if (res.ok) {
          const data: SourcesResponse = await res.json();
          setSources(data.sources);
        }
      } catch (err) {
        console.error("Failed to fetch sources:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchSources();
  }, []);

  const totalEvents = sources.reduce((sum, s) => sum + s.event_count_in_db, 0);

  return (
    <div className="text-white">
      <div className="px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold">Data Sources</h2>
          <span className="text-sm text-zinc-500">
            {totalEvents.toLocaleString()} total events from {sources.length} sources
          </span>
        </div>

        {loading ? (
          <div className="text-center py-12 text-zinc-500">Loading...</div>
        ) : sources.length === 0 ? (
          <div className="text-center py-12 text-zinc-500">No source data available</div>
        ) : (
          <div className="grid gap-4">
            {sources.map((src) => (
              <div
                key={src.source}
                className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-200">
                      {SOURCE_LABELS[src.source] || src.source}
                    </h3>
                    <span className="text-[10px] text-zinc-600 font-mono">
                      {src.source}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className={`text-lg font-bold ${accuracyColor(src.accuracy)}`}>
                      {src.accuracy !== null
                        ? `${Math.round(src.accuracy * 100)}%`
                        : "\u2014"}
                    </div>
                    <div className="text-[10px] text-zinc-600">accuracy</div>
                  </div>
                </div>

                {/* Stats grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                  <div className="bg-zinc-900 rounded-md p-2">
                    <div className="text-xs text-zinc-500">Events in DB</div>
                    <div className="text-sm font-medium text-zinc-200">
                      {src.event_count_in_db.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-zinc-900 rounded-md p-2">
                    <div className="text-xs text-zinc-500">Confirmed / Total</div>
                    <div className="text-sm font-medium">
                      <span className="text-emerald-400">{src.confirmed_events}</span>
                      {" / "}
                      <span className="text-zinc-300">{src.total_events}</span>
                    </div>
                  </div>
                  <div className="bg-zinc-900 rounded-md p-2">
                    <div className="text-xs text-zinc-500">Status</div>
                    <div className={`text-sm font-medium capitalize ${statusColor(src.status)}`}>
                      {src.status}
                    </div>
                  </div>
                  <div className="bg-zinc-900 rounded-md p-2">
                    <div className="text-xs text-zinc-500">Last Ingestion</div>
                    <div className="text-sm font-medium text-zinc-200">
                      {formatTime(src.last_ingestion)}
                    </div>
                  </div>
                </div>

                {/* Category breakdown */}
                {Object.keys(src.categories).length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {Object.entries(src.categories)
                      .sort(([, a], [, b]) => b - a)
                      .map(([cat, count]) => (
                        <span
                          key={cat}
                          className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded"
                        >
                          {cat}: {count}
                        </span>
                      ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
