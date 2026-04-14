"use client";

import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* -- Types ----------------------------------------------------------------- */

interface Brief {
  id: string;
  brief_type: string;
  title: string;
  summary: string | null;
  grounding_score: number | null;
  model_used: string | null;
  token_count: number | null;
  created_at: string;
}

interface Prediction {
  id: string;
  prediction: string;
  confidence: number;
  timeframe: string;
  category: string | null;
  outcome: string | null;
  created_at: string;
}

interface RedTeamAnalysis {
  id: string;
  counterarguments: { claim: string; counter: string; severity: string }[];
  alternative_hypotheses: { hypothesis: string; plausibility: number }[];
  confidence_adjustment: number;
  created_at: string;
}

interface BriefDetail extends Brief {
  content: string;
  event_ids: string[];
  entity_ids: string[];
  predictions: Prediction[];
  red_team: RedTeamAnalysis[];
  metadata: Record<string, unknown> | null;
}

interface FusionSignal {
  id: string;
  signal_type: string;
  title: string;
  description: string;
  severity: number;
  confidence: number;
  event_ids: string[];
  grounding_score: number | null;
  created_at: string;
}

interface WorldState {
  id: string;
  date: string;
  content: string;
  token_count: number;
  events_summarized: number;
  created_at: string;
}

/* -- Helpers --------------------------------------------------------------- */

const BRIEF_TYPE_LABELS: Record<string, string> = {
  daily: "Daily Brief",
  flash: "Flash Alert",
  weekly: "Weekly Summary",
  regional: "Regional Brief",
};

const BRIEF_TYPE_COLORS: Record<string, string> = {
  daily: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  flash: "bg-red-500/20 text-red-400 border-red-500/30",
  weekly: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  regional: "bg-amber-500/20 text-amber-400 border-amber-500/30",
};

const SIGNAL_TYPE_COLORS: Record<string, string> = {
  sanctions_evasion: "text-red-400",
  military_escalation: "text-orange-400",
  economic_crisis: "text-yellow-400",
  health_emergency: "text-green-400",
  geopolitical_shift: "text-blue-400",
  supply_chain_disruption: "text-purple-400",
};

function groundingColor(score: number | null): string {
  if (score === null) return "text-zinc-500";
  if (score >= 0.8) return "text-emerald-400";
  if (score >= 0.5) return "text-yellow-400";
  return "text-red-400";
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/* -- Tabs ------------------------------------------------------------------ */

type Tab = "briefs" | "fusion" | "worldstate";

/* -- Panel Component ------------------------------------------------------- */

export default function BriefsPanel() {
  const [tab, setTab] = useState<Tab>("briefs");
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [fusionSignals, setFusionSignals] = useState<FusionSignal[]>([]);
  const [worldState, setWorldState] = useState<WorldState | null>(null);
  const [selectedBrief, setSelectedBrief] = useState<BriefDetail | null>(null);
  const [briefFilter, setBriefFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  /* Fetch briefs list */
  const fetchBriefs = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "30" });
      if (briefFilter !== "all") params.set("brief_type", briefFilter);
      const res = await fetch(`${API_URL}/api/briefs?${params}`);
      if (res.ok) {
        const data = await res.json();
        setBriefs(data.briefs);
      }
    } catch (e) {
      console.error("Failed to fetch briefs:", e);
    }
  }, [briefFilter]);

  /* Fetch fusion signals */
  const fetchFusion = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/fusion?limit=30`);
      if (res.ok) {
        const data = await res.json();
        setFusionSignals(data.signals);
      }
    } catch (e) {
      console.error("Failed to fetch fusion signals:", e);
    }
  }, []);

  /* Fetch world state */
  const fetchWorldState = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/worldstate`);
      if (res.ok) {
        const data = await res.json();
        setWorldState(data.world_state);
      }
    } catch (e) {
      console.error("Failed to fetch world state:", e);
    }
  }, []);

  /* Fetch brief detail */
  const fetchBriefDetail = async (id: string) => {
    try {
      const res = await fetch(`${API_URL}/api/briefs/${id}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedBrief(data);
      }
    } catch (e) {
      console.error("Failed to fetch brief detail:", e);
    }
  };

  /* Initial load */
  useEffect(() => {
    setLoading(true);
    Promise.all([fetchBriefs(), fetchFusion(), fetchWorldState()]).finally(() =>
      setLoading(false)
    );
  }, [fetchBriefs, fetchFusion, fetchWorldState]);

  /* Refetch briefs when filter changes */
  useEffect(() => {
    fetchBriefs();
  }, [fetchBriefs]);

  return (
    <div className="text-white">
      {/* Tab bar */}
      <div className="flex gap-1 mb-6 bg-zinc-900/50 rounded-lg p-1 w-fit">
        {(["briefs", "fusion", "worldstate"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === t
                ? "bg-zinc-700 text-white"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800"
            }`}
          >
            {t === "briefs" ? "Briefs" : t === "fusion" ? "Fusion Signals" : "World State"}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-20 text-zinc-500">Loading intelligence data...</div>
      ) : (
        <>
          {/* -- Briefs Tab ------------------------------------------------- */}
          {tab === "briefs" && (
            <div className="flex gap-6">
              {/* Brief list */}
              <div className={`flex flex-col gap-3 ${selectedBrief ? "w-1/3" : "w-full max-w-3xl"}`}>
                {/* Filter */}
                <div className="flex gap-2 mb-2">
                  {["all", "daily", "flash", "weekly", "regional"].map((t) => (
                    <button
                      key={t}
                      onClick={() => setBriefFilter(t)}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                        briefFilter === t
                          ? "bg-zinc-700 text-white"
                          : "text-zinc-500 hover:text-white"
                      }`}
                    >
                      {t === "all" ? "All" : BRIEF_TYPE_LABELS[t] || t}
                    </button>
                  ))}
                </div>

                {briefs.length === 0 ? (
                  <div className="text-center py-12 text-zinc-600">
                    No briefs generated yet. Run the intelligence pipeline to create your first brief.
                  </div>
                ) : (
                  briefs.map((b) => (
                    <button
                      key={b.id}
                      onClick={() => fetchBriefDetail(b.id)}
                      className={`text-left p-4 rounded-lg border transition-colors ${
                        selectedBrief?.id === b.id
                          ? "border-cyan-600/50 bg-cyan-900/10"
                          : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`px-2 py-0.5 rounded text-xs border ${BRIEF_TYPE_COLORS[b.brief_type] || "text-zinc-400"}`}>
                          {BRIEF_TYPE_LABELS[b.brief_type] || b.brief_type}
                        </span>
                        <span className="text-xs text-zinc-600">{timeAgo(b.created_at)}</span>
                      </div>
                      <h3 className="text-sm font-medium text-zinc-200 mb-1">{b.title}</h3>
                      {b.summary && (
                        <p className="text-xs text-zinc-500 line-clamp-2">{b.summary}</p>
                      )}
                      <div className="flex gap-4 mt-2 text-xs text-zinc-600">
                        <span className={groundingColor(b.grounding_score)}>
                          Grounding: {b.grounding_score !== null ? `${(b.grounding_score * 100).toFixed(0)}%` : "N/A"}
                        </span>
                        {b.token_count && <span>{b.token_count.toLocaleString()} tokens</span>}
                      </div>
                    </button>
                  ))
                )}
              </div>

              {/* Brief detail panel */}
              {selectedBrief && (
                <div className="flex-1 border border-zinc-800 rounded-lg bg-zinc-900/30 overflow-y-auto max-h-[calc(100vh-200px)]">
                  <div className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-lg font-bold text-white">{selectedBrief.title}</h2>
                      <button
                        onClick={() => setSelectedBrief(null)}
                        className="text-zinc-500 hover:text-white text-sm"
                      >
                        Close
                      </button>
                    </div>

                    {/* Metadata bar */}
                    <div className="flex gap-4 mb-4 text-xs text-zinc-500">
                      <span className={groundingColor(selectedBrief.grounding_score)}>
                        Grounding: {selectedBrief.grounding_score !== null ? `${(selectedBrief.grounding_score * 100).toFixed(0)}%` : "N/A"}
                      </span>
                      <span>Model: {selectedBrief.model_used}</span>
                      <span>Events referenced: {selectedBrief.event_ids?.length || 0}</span>
                      <span>Entities: {selectedBrief.entity_ids?.length || 0}</span>
                    </div>

                    {/* Brief content (rendered as pre-formatted text for markdown) */}
                    <div className="prose prose-invert prose-sm max-w-none mb-6">
                      <pre className="whitespace-pre-wrap text-sm text-zinc-300 font-sans leading-relaxed bg-transparent p-0">
                        {selectedBrief.content}
                      </pre>
                    </div>

                    {/* Predictions */}
                    {selectedBrief.predictions.length > 0 && (
                      <div className="mt-6 border-t border-zinc-800 pt-4">
                        <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                          Predictions ({selectedBrief.predictions.length})
                        </h3>
                        <div className="flex flex-col gap-2">
                          {selectedBrief.predictions.map((p) => (
                            <div key={p.id} className="p-3 bg-zinc-900 rounded border border-zinc-800">
                              <p className="text-sm text-zinc-300">{p.prediction}</p>
                              <div className="flex gap-3 mt-1 text-xs text-zinc-500">
                                <span>Confidence: {(p.confidence * 100).toFixed(0)}%</span>
                                <span>Timeframe: {p.timeframe}</span>
                                <span className={
                                  p.outcome === "correct" ? "text-emerald-400" :
                                  p.outcome === "incorrect" ? "text-red-400" :
                                  "text-zinc-500"
                                }>
                                  {p.outcome ? p.outcome.toUpperCase() : "PENDING"}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Red Team Analysis */}
                    {selectedBrief.red_team.length > 0 && (
                      <div className="mt-6 border-t border-zinc-800 pt-4">
                        <h3 className="text-sm font-semibold text-red-400 mb-3">
                          Red Team Analysis
                        </h3>
                        {selectedBrief.red_team.map((rt) => (
                          <div key={rt.id} className="mb-4">
                            <div className="text-xs text-zinc-600 mb-2">
                              Confidence adjustment: <span className={rt.confidence_adjustment < 0 ? "text-red-400" : "text-emerald-400"}>
                                {rt.confidence_adjustment > 0 ? "+" : ""}{rt.confidence_adjustment}
                              </span>
                            </div>
                            {rt.counterarguments.map((ca, i) => (
                              <div key={i} className="p-2 mb-2 bg-red-950/20 border border-red-900/30 rounded text-xs">
                                <p className="text-red-300 font-medium">Challenging: {ca.claim}</p>
                                <p className="text-zinc-400 mt-1">{ca.counter}</p>
                              </div>
                            ))}
                            {rt.alternative_hypotheses.length > 0 && (
                              <div className="mt-2">
                                <p className="text-xs text-zinc-500 mb-1">Alternative Hypotheses:</p>
                                {rt.alternative_hypotheses.map((ah, i) => (
                                  <div key={i} className="p-2 mb-1 bg-zinc-900 border border-zinc-800 rounded text-xs">
                                    <span className="text-zinc-300">{ah.hypothesis}</span>
                                    <span className="ml-2 text-zinc-600">
                                      (plausibility: {(ah.plausibility * 100).toFixed(0)}%)
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* -- Fusion Signals Tab ----------------------------------------- */}
          {tab === "fusion" && (
            <div className="flex flex-col gap-3 max-w-4xl">
              {fusionSignals.length === 0 ? (
                <div className="text-center py-12 text-zinc-600">
                  No fusion signals detected yet. Signals appear when cross-domain patterns are found across multiple sources.
                </div>
              ) : (
                fusionSignals.map((sig) => (
                  <div key={sig.id} className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`text-sm font-semibold ${SIGNAL_TYPE_COLORS[sig.signal_type] || "text-zinc-400"}`}>
                        {sig.signal_type.replace(/_/g, " ").toUpperCase()}
                      </span>
                      <span className="text-xs text-zinc-600">{timeAgo(sig.created_at)}</span>
                    </div>
                    <h3 className="text-sm font-medium text-zinc-200 mb-1">{sig.title}</h3>
                    <p className="text-xs text-zinc-400 mb-3">{sig.description}</p>
                    <div className="flex gap-4 text-xs text-zinc-600">
                      <span>Severity: <span className={sig.severity >= 80 ? "text-red-400" : sig.severity >= 50 ? "text-yellow-400" : "text-zinc-400"}>{sig.severity}</span></span>
                      <span>Confidence: {(sig.confidence * 100).toFixed(0)}%</span>
                      <span className={groundingColor(sig.grounding_score)}>
                        Grounding: {sig.grounding_score !== null ? `${(sig.grounding_score * 100).toFixed(0)}%` : "N/A"}
                      </span>
                      <span>Sources: {sig.event_ids?.length || 0} events</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* -- World State Tab --------------------------------------------- */}
          {tab === "worldstate" && (
            <div className="max-w-4xl">
              {worldState ? (
                <div className="border border-zinc-800 rounded-lg bg-zinc-900/30 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-bold text-white">World State — {worldState.date}</h2>
                    <div className="flex gap-3 text-xs text-zinc-500">
                      <span>{worldState.events_summarized} events summarized</span>
                      <span>{worldState.token_count?.toLocaleString()} tokens</span>
                    </div>
                  </div>
                  <pre className="whitespace-pre-wrap text-sm text-zinc-300 font-sans leading-relaxed">
                    {worldState.content}
                  </pre>
                </div>
              ) : (
                <div className="text-center py-12 text-zinc-600">
                  No world state generated yet. The world state is compressed nightly from the day&#39;s events.
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
