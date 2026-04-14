"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────────── */

interface Entity {
  id: string;
  name: string;
  entity_type: string;
  event_count: number;
  aliases?: string[] | null;
}

interface Dossier {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  event_count: number;
  source_count: number;
  relation_count: number;
  sanctions_flags: number;
  summary?: string;
  key_facts?: string[];
  risk_assessment?: string;
  timeline_events?: { date: string; event: string; source: string }[];
  events?: { id: string; source: string; title: string; severity: number; timestamp: string }[];
  relations?: { related_name: string; related_type: string; relation_type: string; confidence: number; related_id: string }[];
  sanctions_matches?: { name: string; program: string }[];
}

interface GraphData {
  nodes: { id: string; name: string; type: string; event_count: number; depth: number }[];
  edges: { id: string; source: string; target: string; relation: string; confidence: number }[];
  node_count: number;
  edge_count: number;
}

interface ACHFramework {
  id: string;
  title: string;
  description?: string;
  hypotheses: string[];
  evidence: string[];
  matrix: string[][];
  conclusion?: string;
  scores?: { hypothesis: string; inconsistent: number; consistent: number; inconsistency_ratio: number }[];
}

interface SearchResults {
  entities: Entity[];
  events: { id: string; source: string; title: string; severity: number }[];
  total_hits: number;
  query: string;
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

type Tab = "search" | "dossier" | "graph" | "ach";

function typeColor(t: string): string {
  switch (t) {
    case "organization": return "text-cyan-400";
    case "person": return "text-amber-400";
    case "location": return "text-emerald-400";
    case "vessel": return "text-purple-400";
    default: return "text-zinc-400";
  }
}

function typeBg(t: string): string {
  switch (t) {
    case "organization": return "bg-cyan-500/20 border-cyan-500/30";
    case "person": return "bg-amber-500/20 border-amber-500/30";
    case "location": return "bg-emerald-500/20 border-emerald-500/30";
    case "vessel": return "bg-purple-500/20 border-purple-500/30";
    default: return "bg-zinc-500/20 border-zinc-500/30";
  }
}

function cellColor(value: string): string {
  switch (value) {
    case "C": return "bg-emerald-600 text-white";
    case "I": return "bg-red-600 text-white";
    case "N": return "bg-zinc-700 text-zinc-300";
    case "NA": return "bg-zinc-900 text-zinc-600";
    default: return "bg-zinc-800 text-zinc-500";
  }
}

/* ── Force Graph Component (SVG) ──────────────────────────────────────── */

function ForceGraph({ data, onNodeClick }: { data: GraphData; onNodeClick?: (id: string) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});

  useEffect(() => {
    if (!data.nodes.length) return;

    // Simple circular layout with center node at origin
    const cx = 400, cy = 300;
    const pos: Record<string, { x: number; y: number }> = {};

    const centerNode = data.nodes.find((n) => n.depth === 0);
    if (centerNode) pos[centerNode.id] = { x: cx, y: cy };

    const otherNodes = data.nodes.filter((n) => n.depth > 0);
    otherNodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / otherNodes.length;
      const radius = 120 + node.depth * 80;
      pos[node.id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      };
    });

    setPositions(pos);
  }, [data]);

  if (!data.nodes.length) {
    return <div className="text-zinc-600 text-sm py-8 text-center">No graph data.</div>;
  }

  const nodeRadius = (n: { event_count: number }) => Math.max(6, Math.min(20, 6 + n.event_count));

  return (
    <svg ref={svgRef} viewBox="0 0 800 600" className="w-full h-[500px] bg-zinc-900/50 rounded-lg border border-zinc-800">
      {/* Edges */}
      {data.edges.map((edge) => {
        const from = positions[edge.source];
        const to = positions[edge.target];
        if (!from || !to) return null;
        return (
          <g key={edge.id}>
            <line
              x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke="#555" strokeWidth={Math.max(0.5, edge.confidence * 2)} opacity={0.6}
            />
            <text
              x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 4}
              fill="#777" fontSize="8" textAnchor="middle"
            >
              {edge.relation}
            </text>
          </g>
        );
      })}
      {/* Nodes */}
      {data.nodes.map((node) => {
        const pos = positions[node.id];
        if (!pos) return null;
        const r = nodeRadius(node);
        const fill = node.depth === 0 ? "#06b6d4" :
          node.type === "organization" ? "#22d3ee" :
          node.type === "person" ? "#fbbf24" :
          node.type === "location" ? "#34d399" : "#a78bfa";

        return (
          <g key={node.id}
            className="cursor-pointer"
            onClick={() => onNodeClick?.(node.id)}
          >
            <circle cx={pos.x} cy={pos.y} r={r} fill={fill} opacity={0.85}
              stroke={node.depth === 0 ? "#fff" : "transparent"} strokeWidth={node.depth === 0 ? 2 : 0}
            />
            <text x={pos.x} y={pos.y + r + 12} fill="#ccc" fontSize="10" textAnchor="middle">
              {node.name.length > 15 ? node.name.slice(0, 14) + "\u2026" : node.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ── Page Component ───────────────────────────────────────────────────── */

export default function EntityIntelPage() {
  const [tab, setTab] = useState<Tab>("search");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResults | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [achList, setAchList] = useState<{ id: string; title: string }[]>([]);
  const [selectedAch, setSelectedAch] = useState<ACHFramework | null>(null);
  const [loading, setLoading] = useState(false);

  const doSearch = useCallback(async () => {
    if (searchQuery.length < 2) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/entity-search?q=${encodeURIComponent(searchQuery)}&limit=20`);
      if (res.ok) setSearchResults(await res.json());
    } catch (e) {
      console.error("Search failed:", e);
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  const loadDossier = useCallback(async (entityId: string) => {
    setLoading(true);
    setSelectedEntity(entityId);
    try {
      const res = await fetch(`${API_URL}/api/entities/${entityId}/dossier`);
      if (res.ok) {
        setDossier(await res.json());
        setTab("dossier");
      }
    } catch (e) {
      console.error("Dossier failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadGraph = useCallback(async (entityId: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/entities/${entityId}/graph?depth=2&max_nodes=40`);
      if (res.ok) {
        setGraphData(await res.json());
        setTab("graph");
      }
    } catch (e) {
      console.error("Graph failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAchList = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/ach?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setAchList(data.frameworks);
      }
    } catch (e) {
      console.error("ACH list failed:", e);
    }
  }, []);

  const loadAchDetail = useCallback(async (id: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/ach/${id}`);
      if (res.ok) setSelectedAch(await res.json());
    } catch (e) {
      console.error("ACH detail failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateAchCell = useCallback(async (frameworkId: string, eIdx: number, hIdx: number, currentValue: string) => {
    const next: Record<string, string> = { C: "I", I: "N", N: "NA", NA: "C" };
    const newValue = next[currentValue] || "C";
    try {
      const res = await fetch(`${API_URL}/api/ach/${frameworkId}/cell`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evidence_idx: eIdx, hypothesis_idx: hIdx, value: newValue }),
      });
      if (res.ok) {
        setSelectedAch((prev) => {
          if (!prev) return prev;
          const newMatrix = prev.matrix.map((row) => [...row]);
          newMatrix[eIdx][hIdx] = newValue;
          return { ...prev, matrix: newMatrix };
        });
      }
    } catch (e) {
      console.error("ACH cell update failed:", e);
    }
  }, []);

  useEffect(() => {
    loadAchList();
  }, [loadAchList]);

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-lg font-bold tracking-tight text-white hover:text-cyan-300 transition-colors">
              Cerebro
            </Link>
            <span className="text-zinc-600">/</span>
            <h1 className="text-sm font-medium text-zinc-300">Entity Intelligence</h1>
          </div>
          <nav className="flex gap-3 text-sm">
            <Link href="/globe" className="text-zinc-400 hover:text-white transition-colors">Globe</Link>
            <Link href="/events" className="text-zinc-400 hover:text-white transition-colors">Events</Link>
            <Link href="/briefs" className="text-zinc-400 hover:text-white transition-colors">Briefs</Link>
            <Link href="/risk" className="text-zinc-400 hover:text-white transition-colors">Risk</Link>
            <Link href="/satellite" className="text-zinc-400 hover:text-white transition-colors">SPECINT</Link>
          </nav>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Tab bar */}
        <div className="flex gap-1 mb-6 bg-zinc-900/50 rounded-lg p-1 w-fit">
          {([
            { key: "search", label: "Omnisearch" },
            { key: "dossier", label: "Dossier" },
            { key: "graph", label: "Link Analysis" },
            { key: "ach", label: "ACH Matrix" },
          ] as { key: Tab; label: string }[]).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === t.key ? "bg-zinc-700 text-white" : "text-zinc-400 hover:text-white hover:bg-zinc-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {loading && <div className="text-center py-4 text-zinc-500">Loading...</div>}

        {/* ── Search Tab ───────────────────────────────────── */}
        {tab === "search" && (
          <div className="space-y-4 max-w-4xl">
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
                placeholder="Search across all intelligence layers..."
                className="flex-1 px-4 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500"
              />
              <button
                onClick={doSearch}
                className="px-6 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-sm font-medium transition-colors"
              >
                Search
              </button>
            </div>

            {searchResults && (
              <div className="space-y-4">
                <p className="text-xs text-zinc-500">
                  {searchResults.total_hits} results for &ldquo;{searchResults.query}&rdquo;
                </p>

                {searchResults.entities.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                      Entities ({searchResults.entities.length})
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {searchResults.entities.map((e) => (
                        <button
                          key={e.id}
                          onClick={() => loadDossier(e.id)}
                          className={`p-3 rounded-lg border text-left transition-colors hover:brightness-125 ${typeBg(e.entity_type)}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-white">{e.name}</span>
                            <span className={`text-xs ${typeColor(e.entity_type)}`}>{e.entity_type}</span>
                          </div>
                          <p className="text-xs text-zinc-500 mt-1">{e.event_count} events</p>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {searchResults.events.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                      Events ({searchResults.events.length})
                    </h4>
                    <div className="flex flex-col gap-1">
                      {searchResults.events.slice(0, 10).map((e) => (
                        <div key={e.id} className="p-2 rounded border border-zinc-800 bg-zinc-900/50 text-xs">
                          <span className="text-cyan-400 mr-2">[{e.source}]</span>
                          <span className="text-zinc-300">{e.title}</span>
                          <span className="text-zinc-600 ml-2">sev={e.severity}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Dossier Tab ──────────────────────────────────── */}
        {tab === "dossier" && dossier && (
          <div className="space-y-6 max-w-4xl">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-bold">{dossier.entity_name}</h2>
                  <span className={`px-2 py-0.5 rounded text-xs border ${typeBg(dossier.entity_type)}`}>
                    {dossier.entity_type}
                  </span>
                  {dossier.sanctions_flags > 0 && (
                    <span className="px-2 py-0.5 rounded text-xs bg-red-500/20 text-red-400 border border-red-500/30">
                      SANCTIONS FLAG
                    </span>
                  )}
                </div>
                <p className="text-sm text-zinc-500 mt-1">
                  {dossier.event_count} events · {dossier.source_count} sources · {dossier.relation_count} relations
                </p>
              </div>
              <button
                onClick={() => selectedEntity && loadGraph(selectedEntity)}
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-xs transition-colors"
              >
                View Graph
              </button>
            </div>

            {/* Summary */}
            {dossier.summary && (
              <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Executive Summary</h3>
                <p className="text-sm text-zinc-300 whitespace-pre-line">{dossier.summary}</p>
              </div>
            )}

            {/* Key Facts */}
            {dossier.key_facts && dossier.key_facts.length > 0 && (
              <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Key Facts</h3>
                <ul className="space-y-1">
                  {dossier.key_facts.map((fact, i) => (
                    <li key={i} className="text-sm text-zinc-300 flex gap-2">
                      <span className="text-cyan-400">&#x2022;</span>
                      {fact}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risk Assessment */}
            {dossier.risk_assessment && (
              <div className="p-4 rounded-lg border border-orange-500/20 bg-orange-500/5">
                <h3 className="text-xs font-semibold text-orange-400 uppercase tracking-wider mb-2">Risk Assessment</h3>
                <p className="text-sm text-zinc-300 whitespace-pre-line">{dossier.risk_assessment}</p>
              </div>
            )}

            {/* Sanctions Matches */}
            {dossier.sanctions_matches && dossier.sanctions_matches.length > 0 && (
              <div className="p-4 rounded-lg border border-red-500/30 bg-red-500/5">
                <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">Sanctions Matches</h3>
                {dossier.sanctions_matches.map((s, i) => (
                  <p key={i} className="text-sm text-red-300">
                    {s.name} — <span className="text-zinc-500">{s.program}</span>
                  </p>
                ))}
              </div>
            )}

            {/* Relations */}
            {dossier.relations && dossier.relations.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                  Related Entities ({dossier.relations.length})
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {dossier.relations.map((r, i) => (
                    <button
                      key={i}
                      onClick={() => loadDossier(r.related_id)}
                      className="p-2 rounded border border-zinc-800 bg-zinc-900/50 text-left text-xs hover:bg-zinc-800 transition-colors"
                    >
                      <span className={typeColor(r.related_type)}>{r.related_name}</span>
                      <span className="text-zinc-600 ml-2">{r.relation_type}</span>
                      <span className="text-zinc-700 ml-1">(conf={r.confidence})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Timeline */}
            {dossier.timeline_events && dossier.timeline_events.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Activity Timeline</h3>
                <div className="border-l-2 border-zinc-800 pl-4 space-y-3">
                  {dossier.timeline_events.map((t, i) => (
                    <div key={i} className="relative">
                      <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-cyan-500" />
                      <p className="text-xs text-zinc-500">{t.date} · {t.source}</p>
                      <p className="text-sm text-zinc-300">{t.event}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "dossier" && !dossier && (
          <p className="text-zinc-600 text-sm">Search for an entity to view its dossier.</p>
        )}

        {/* ── Graph Tab ────────────────────────────────────── */}
        {tab === "graph" && (
          <div className="space-y-4">
            {graphData ? (
              <>
                <div className="flex items-center gap-4">
                  <h3 className="text-sm font-semibold text-zinc-300">
                    Link Analysis — {graphData.node_count} nodes, {graphData.edge_count} edges
                  </h3>
                  <div className="flex gap-2 text-xs">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-cyan-400 inline-block" /> Organization</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400 inline-block" /> Person</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" /> Location</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-400 inline-block" /> Vessel</span>
                  </div>
                </div>
                <ForceGraph data={graphData} onNodeClick={(id) => loadDossier(id)} />
              </>
            ) : (
              <p className="text-zinc-600 text-sm">Select an entity to view its link analysis graph.</p>
            )}
          </div>
        )}

        {/* ── ACH Tab ──────────────────────────────────────── */}
        {tab === "ach" && (
          <div className="space-y-6 max-w-6xl">
            {!selectedAch ? (
              <div>
                <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                  ACH Frameworks ({achList.length})
                </h3>
                {achList.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No ACH frameworks created yet.</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {achList.map((f) => (
                      <button
                        key={f.id}
                        onClick={() => loadAchDetail(f.id)}
                        className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50 text-left hover:bg-zinc-800 transition-colors"
                      >
                        <p className="text-sm font-medium text-white">{f.title}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-bold">{selectedAch.title}</h3>
                    {selectedAch.description && (
                      <p className="text-sm text-zinc-400 mt-0.5">{selectedAch.description}</p>
                    )}
                  </div>
                  <button
                    onClick={() => setSelectedAch(null)}
                    className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded text-xs transition-colors"
                  >
                    Back to list
                  </button>
                </div>

                {/* Matrix */}
                <div className="overflow-x-auto">
                  <table className="min-w-full border-collapse">
                    <thead>
                      <tr>
                        <th className="p-2 text-left text-xs text-zinc-500 border-b border-zinc-800 w-48">Evidence</th>
                        {selectedAch.hypotheses.map((h, i) => (
                          <th key={i} className="p-2 text-center text-xs text-zinc-300 border-b border-zinc-800 min-w-[100px]">
                            H{i + 1}: {h.length > 25 ? h.slice(0, 24) + "\u2026" : h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAch.evidence.map((ev, eIdx) => (
                        <tr key={eIdx}>
                          <td className="p-2 text-xs text-zinc-400 border-b border-zinc-800/50">
                            E{eIdx + 1}: {ev.length > 50 ? ev.slice(0, 49) + "\u2026" : ev}
                          </td>
                          {selectedAch.hypotheses.map((_, hIdx) => {
                            const value = selectedAch.matrix[eIdx]?.[hIdx] || "N";
                            return (
                              <td key={hIdx} className="p-1 border-b border-zinc-800/50 text-center">
                                <button
                                  onClick={() => updateAchCell(selectedAch.id, eIdx, hIdx, value)}
                                  className={`w-10 h-8 rounded text-xs font-bold ${cellColor(value)} hover:opacity-80 transition-opacity`}
                                  title={`Click to cycle: C→I→N→NA`}
                                >
                                  {value}
                                </button>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Legend */}
                <div className="flex gap-4 text-xs mt-3">
                  <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-emerald-600 inline-flex items-center justify-center text-white text-[10px]">C</span> Consistent</span>
                  <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-red-600 inline-flex items-center justify-center text-white text-[10px]">I</span> Inconsistent</span>
                  <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-zinc-700 inline-flex items-center justify-center text-zinc-300 text-[10px]">N</span> Neutral</span>
                  <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-zinc-900 inline-flex items-center justify-center text-zinc-600 text-[10px]">NA</span> Not Applicable</span>
                </div>

                {/* Scores */}
                {selectedAch.scores && (
                  <div className="mt-4">
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                      Hypothesis Ranking (fewest inconsistencies = most likely)
                    </h4>
                    <div className="space-y-2">
                      {selectedAch.scores.map((s, i) => (
                        <div key={i} className={`p-2 rounded border text-sm ${
                          i === 0 ? "border-emerald-500/30 bg-emerald-500/10" : "border-zinc-800 bg-zinc-900/50"
                        }`}>
                          <div className="flex items-center justify-between">
                            <span className={i === 0 ? "text-emerald-400 font-medium" : "text-zinc-300"}>
                              {i === 0 ? "MOST LIKELY: " : ""}{s.hypothesis}
                            </span>
                            <span className="text-xs text-zinc-500">
                              C={s.consistent} I={s.inconsistent} ratio={s.inconsistency_ratio}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Conclusion */}
                {selectedAch.conclusion && (
                  <div className="mt-4 p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                      Claude&apos;s Analysis
                    </h4>
                    <p className="text-sm text-zinc-300 whitespace-pre-line">{selectedAch.conclusion}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
