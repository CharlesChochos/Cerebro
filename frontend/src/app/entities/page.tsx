"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Entity {
  id: string;
  name: string;
  entity_type: string;
  aliases: string[] | null;
  metadata: Record<string, unknown> | null;
  first_seen: string | null;
  last_seen: string | null;
  event_count: number;
}

interface EntitiesResponse {
  total: number;
  limit: number;
  offset: number;
  entities: Entity[];
}

interface EntityDetail extends Entity {
  relations: {
    name: string;
    entity_type: string;
    relation_type: string;
    confidence: number;
    source_entity_id: string;
    target_entity_id: string;
  }[];
}

const ENTITY_TYPES = ["all", "location", "organization", "actor"];

const TYPE_COLORS: Record<string, string> = {
  location: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  organization: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  actor: "bg-amber-500/20 text-amber-400 border-amber-500/30",
};

function formatTime(ts: string | null): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return ts;
  }
}

export default function EntitiesPage() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [entityType, setEntityType] = useState("all");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [sort, setSort] = useState("event_count");
  const [offset, setOffset] = useState(0);
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const limit = 30;

  const fetchEntities = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      sort,
    });
    if (entityType !== "all") params.set("entity_type", entityType);
    if (search) params.set("search", search);

    try {
      const res = await fetch(`${API_URL}/api/entities?${params}`);
      if (res.ok) {
        const data: EntitiesResponse = await res.json();
        setEntities(data.entities);
        setTotal(data.total);
      }
    } catch (err) {
      console.error("Failed to fetch entities:", err);
    } finally {
      setLoading(false);
    }
  }, [entityType, search, sort, offset]);

  useEffect(() => {
    fetchEntities();
  }, [fetchEntities]);

  async function loadEntityDetail(id: string) {
    setDetailLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/entities/${id}`);
      if (res.ok) {
        const data: EntityDetail = await res.json();
        setSelectedEntity(data);
      }
    } catch (err) {
      console.error("Failed to fetch entity detail:", err);
    } finally {
      setDetailLoading(false);
    }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setOffset(0);
    setSearch(searchInput);
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <header className="border-b border-zinc-800 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <Link href="/" className="text-xl font-bold tracking-tight">
            Cerebro
          </Link>
          <nav className="flex items-center gap-4">
            <Link href="/events" className="text-sm text-zinc-400 hover:text-white transition-colors">
              Events
            </Link>
            <Link href="/sources" className="text-sm text-zinc-400 hover:text-white transition-colors">
              Sources
            </Link>
            <span className="text-sm text-zinc-500">
              {total.toLocaleString()} entities
            </span>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          {/* Type tabs */}
          <div className="flex gap-1 flex-wrap">
            {ENTITY_TYPES.map((t) => (
              <button
                key={t}
                onClick={() => { setEntityType(t); setOffset(0); }}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  entityType === t
                    ? "bg-zinc-700 text-white"
                    : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          {/* Sort */}
          <select
            value={sort}
            onChange={(e) => { setSort(e.target.value); setOffset(0); }}
            className="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-zinc-500"
          >
            <option value="event_count">Most Events</option>
            <option value="last_seen">Recently Active</option>
            <option value="name">Name A-Z</option>
          </select>

          {/* Search */}
          <form onSubmit={handleSearch} className="flex gap-2 sm:ml-auto">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search entities..."
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

        <div className="flex gap-6">
          {/* Entity list */}
          <div className={`flex-1 ${selectedEntity ? "max-w-[60%]" : ""}`}>
            {loading ? (
              <div className="text-center py-12 text-zinc-500">Loading...</div>
            ) : entities.length === 0 ? (
              <div className="text-center py-12 text-zinc-500">No entities found</div>
            ) : (
              <div className="space-y-1">
                {entities.map((entity) => (
                  <button
                    key={entity.id}
                    onClick={() => loadEntityDetail(entity.id)}
                    className={`w-full text-left flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                      selectedEntity?.id === entity.id
                        ? "border-zinc-600 bg-zinc-800"
                        : "border-zinc-800 bg-zinc-900/50 hover:bg-zinc-900"
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span
                          className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${
                            TYPE_COLORS[entity.entity_type] || "bg-zinc-800 text-zinc-400 border-zinc-700"
                          }`}
                        >
                          {entity.entity_type.toUpperCase()}
                        </span>
                        <span className="text-sm font-medium text-zinc-200 truncate">
                          {entity.name}
                        </span>
                      </div>
                      <div className="flex gap-3 text-[10px] text-zinc-600">
                        <span>Last seen: {formatTime(entity.last_seen)}</span>
                      </div>
                    </div>
                    <div className="text-right min-w-[3.5rem]">
                      <div className="text-sm font-bold text-zinc-300">
                        {entity.event_count}
                      </div>
                      <div className="text-[10px] text-zinc-600">events</div>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* Pagination */}
            {total > limit && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-zinc-800">
                <button
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                  className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-md disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                <span className="text-sm text-zinc-500">
                  {offset + 1}–{Math.min(offset + limit, total)} of {total}
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

          {/* Entity detail panel */}
          {selectedEntity && (
            <div className="w-[40%] sticky top-6 self-start rounded-lg border border-zinc-800 bg-zinc-900/80 p-5">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-base font-semibold text-white">
                    {selectedEntity.name}
                  </h3>
                  <span
                    className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${
                      TYPE_COLORS[selectedEntity.entity_type] || "bg-zinc-800 text-zinc-400 border-zinc-700"
                    }`}
                  >
                    {selectedEntity.entity_type.toUpperCase()}
                  </span>
                </div>
                <button
                  onClick={() => setSelectedEntity(null)}
                  className="text-zinc-500 hover:text-white text-sm"
                >
                  ✕
                </button>
              </div>

              {detailLoading ? (
                <div className="text-center py-6 text-zinc-500">Loading...</div>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2 mb-4 text-xs">
                    <div className="bg-zinc-800 rounded p-2">
                      <div className="text-zinc-500">Events</div>
                      <div className="font-medium">{selectedEntity.event_count}</div>
                    </div>
                    <div className="bg-zinc-800 rounded p-2">
                      <div className="text-zinc-500">First Seen</div>
                      <div className="font-medium">{formatTime(selectedEntity.first_seen)}</div>
                    </div>
                  </div>

                  {selectedEntity.aliases && selectedEntity.aliases.length > 0 && (
                    <div className="mb-4">
                      <div className="text-[10px] text-zinc-500 uppercase mb-1">Aliases</div>
                      <div className="flex flex-wrap gap-1">
                        {selectedEntity.aliases.map((a, i) => (
                          <span key={i} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded">
                            {a}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {selectedEntity.metadata && Object.keys(selectedEntity.metadata).length > 0 && (
                    <div className="mb-4">
                      <div className="text-[10px] text-zinc-500 uppercase mb-1">Metadata</div>
                      <div className="text-xs text-zinc-400 bg-zinc-800 rounded p-2 font-mono">
                        {JSON.stringify(selectedEntity.metadata, null, 2)}
                      </div>
                    </div>
                  )}

                  {/* Relations */}
                  {selectedEntity.relations && selectedEntity.relations.length > 0 && (
                    <div>
                      <div className="text-[10px] text-zinc-500 uppercase mb-2">
                        Connected Entities ({selectedEntity.relations.length})
                      </div>
                      <div className="space-y-1 max-h-64 overflow-y-auto">
                        {selectedEntity.relations.map((rel, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 text-xs bg-zinc-800 rounded p-2"
                          >
                            <span
                              className={`text-[9px] font-medium px-1 py-0.5 rounded ${
                                TYPE_COLORS[rel.entity_type] || "bg-zinc-700 text-zinc-400"
                              }`}
                            >
                              {rel.entity_type}
                            </span>
                            <span className="text-zinc-300 truncate">{rel.name}</span>
                            <span className="text-zinc-600 ml-auto text-[10px]">
                              {rel.relation_type}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
