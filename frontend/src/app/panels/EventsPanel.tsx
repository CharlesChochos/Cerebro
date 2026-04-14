"use client";

import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CerebroEvent {
  id: string;
  source: string;
  timestamp: string;
  category: string | null;
  severity: number;
  confidence: number;
  title: string;
  summary: string | null;
  country_code: string | null;
  region: string | null;
  source_url: string | null;
  entities: { name: string; type: string; role: string }[];
}

interface EventsResponse {
  total: number;
  limit: number;
  offset: number;
  events: CerebroEvent[];
}

const CATEGORIES = ["all", "military", "political", "economic", "health", "environmental"];
const SOURCES = ["all", "gdelt", "rss", "yahoo_finance", "worldbank", "fred", "acled"];

const SOURCE_LABELS: Record<string, string> = {
  all: "All Sources",
  gdelt: "GDELT",
  rss: "RSS Feeds",
  yahoo_finance: "Yahoo Finance",
  worldbank: "World Bank",
  fred: "FRED",
  acled: "ACLED",
};

const CATEGORY_COLORS: Record<string, string> = {
  military: "bg-red-500/20 text-red-400 border-red-500/30",
  political: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  economic: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  health: "bg-green-500/20 text-green-400 border-green-500/30",
  environmental: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
};

const SOURCE_COLORS: Record<string, string> = {
  gdelt: "text-cyan-400",
  rss: "text-orange-400",
  yahoo_finance: "text-yellow-400",
  worldbank: "text-blue-400",
  fred: "text-green-400",
  acled: "text-red-400",
};

function severityColor(severity: number): string {
  if (severity >= 80) return "text-red-400";
  if (severity >= 60) return "text-orange-400";
  if (severity >= 40) return "text-yellow-400";
  return "text-zinc-400";
}

function formatTime(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return timestamp;
  }
}

export default function EventsPanel() {
  const [events, setEvents] = useState<CerebroEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("all");
  const [source, setSource] = useState("all");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      sort: "timestamp",
      order: "desc",
    });
    if (category !== "all") params.set("category", category);
    if (source !== "all") params.set("source", source);
    if (search) params.set("search", search);

    try {
      const res = await fetch(`${API_URL}/api/events?${params}`);
      if (res.ok) {
        const data: EventsResponse = await res.json();
        setEvents(data.events);
        setTotal(data.total);
      }
    } catch (err) {
      console.error("Failed to fetch events:", err);
    } finally {
      setLoading(false);
    }
  }, [category, source, search, offset]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setOffset(0);
    setSearch(searchInput);
  }

  return (
    <div className="text-white">
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        {/* Category tabs */}
        <div className="flex gap-1 flex-wrap">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => { setCategory(cat); setOffset(0); }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                category === cat
                  ? "bg-zinc-700 text-white"
                  : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800"
              }`}
            >
              {cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>

        {/* Source filter */}
        <select
          value={source}
          onChange={(e) => { setSource(e.target.value); setOffset(0); }}
          className="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-zinc-500"
        >
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {SOURCE_LABELS[s] || s}
            </option>
          ))}
        </select>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2 sm:ml-auto">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search events..."
            className="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500 w-64"
          />
          <button
            type="submit"
            className="bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 rounded-md text-sm transition-colors"
          >
            Search
          </button>
        </form>
      </div>

      {/* Event count */}
      <div className="mb-4">
        <span className="text-sm text-zinc-500">
          {total.toLocaleString()} events
        </span>
      </div>

      {/* Event list */}
      {loading ? (
        <div className="text-center py-12 text-zinc-500">Loading...</div>
      ) : events.length === 0 ? (
        <div className="text-center py-12 text-zinc-500">No events found</div>
      ) : (
        <div className="space-y-2">
          {events.map((event) => (
            <div
              key={event.id}
              className="flex items-start gap-4 p-4 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-900 transition-colors"
            >
              {/* Severity indicator */}
              <div className="flex flex-col items-center gap-1 min-w-[3rem]">
                <span className={`text-lg font-bold ${severityColor(event.severity)}`}>
                  {Math.round(event.severity)}
                </span>
                <span className="text-[10px] text-zinc-600 uppercase">Sev</span>
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  {event.category && (
                    <span
                      className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${
                        CATEGORY_COLORS[event.category] || "bg-zinc-800 text-zinc-400 border-zinc-700"
                      }`}
                    >
                      {event.category.toUpperCase()}
                    </span>
                  )}
                  <span className={`text-[10px] font-medium ${SOURCE_COLORS[event.source] || "text-zinc-500"}`}>
                    {SOURCE_LABELS[event.source] || event.source}
                  </span>
                  {event.country_code && (
                    <span className="text-[10px] text-zinc-500">
                      {event.country_code}
                    </span>
                  )}
                  <span className="text-[10px] text-zinc-600">
                    {formatTime(event.timestamp)}
                  </span>
                </div>

                <h3 className="text-sm font-medium text-zinc-200 truncate">
                  {event.title}
                </h3>

                {event.summary && (
                  <p className="text-xs text-zinc-500 mt-1 line-clamp-2">
                    {event.summary}
                  </p>
                )}

                {event.region && (
                  <p className="text-[10px] text-zinc-600 mt-1">
                    {event.region}
                  </p>
                )}
              </div>

              {/* Confidence */}
              <div className="text-right min-w-[3rem]">
                <span className="text-xs text-zinc-500">
                  {Math.round(event.confidence * 100)}%
                </span>
                <div className="text-[10px] text-zinc-600">conf</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-zinc-800">
          <button
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-md disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Previous
          </button>
          <span className="text-sm text-zinc-500">
            {offset + 1}–{Math.min(offset + limit, total)} of {total.toLocaleString()}
          </span>
          <button
            onClick={() => setOffset(offset + limit)}
            disabled={offset + limit >= total}
            className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-md disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
