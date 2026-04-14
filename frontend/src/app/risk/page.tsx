"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────────── */

interface RiskScore {
  id: string;
  scope_type: string;
  scope_value: string;
  score: number;
  components: Record<string, number> | null;
  event_count: number;
  source_count: number;
  trend: string;
  updated_at: string;
}

interface Alert {
  id: string;
  config_id: string;
  alert_type: string;
  title: string;
  description: string;
  severity: number;
  scope_type: string;
  scope_value: string;
  event_ids: string[];
  acknowledged: number;
  created_at: string;
}

interface Velocity {
  id: string;
  scope_type: string;
  scope_value: string;
  period: string;
  event_count: number;
  avg_severity: number;
  baseline_rate: number;
  velocity_ratio: number;
  updated_at: string;
}

interface Scorecard {
  total_predictions: number;
  resolved: number;
  pending: number;
  correct: number;
  incorrect: number;
  expired: number;
  accuracy: number | null;
  calibration: Record<string, {
    total: number;
    correct: number;
    accuracy: number | null;
    expected_range: string;
  }>;
}

interface SurpriseData {
  date: string;
  surprise_score: number;
  predictions_made?: number;
  predictions_correct?: number;
  unexpected_events?: number;
  miss_rate?: number;
  reason?: string;
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

type Tab = "risk" | "alerts" | "velocity" | "predictions";

function scoreColor(score: number): string {
  if (score >= 80) return "text-red-400";
  if (score >= 60) return "text-orange-400";
  if (score >= 40) return "text-yellow-400";
  return "text-emerald-400";
}

function scoreBg(score: number): string {
  if (score >= 80) return "bg-red-500/20 border-red-500/30";
  if (score >= 60) return "bg-orange-500/20 border-orange-500/30";
  if (score >= 40) return "bg-yellow-500/20 border-yellow-500/30";
  return "bg-emerald-500/20 border-emerald-500/30";
}

function trendIcon(trend: string): { icon: string; color: string } {
  switch (trend) {
    case "spike": return { icon: "⬆⬆", color: "text-red-400" };
    case "rising": return { icon: "↑", color: "text-orange-400" };
    case "falling": return { icon: "↓", color: "text-blue-400" };
    default: return { icon: "→", color: "text-zinc-500" };
  }
}

function alertTypeBadge(type: string): string {
  switch (type) {
    case "threshold": return "bg-red-500/20 text-red-400 border-red-500/30";
    case "velocity_spike": return "bg-orange-500/20 text-orange-400 border-orange-500/30";
    case "anomaly": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
    default: return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
  }
}

function velocityBar(ratio: number): string {
  if (ratio >= 5) return "w-full bg-red-500";
  if (ratio >= 3) return "w-4/5 bg-orange-500";
  if (ratio >= 2) return "w-3/5 bg-yellow-500";
  if (ratio >= 1.5) return "w-2/5 bg-emerald-500";
  return "w-1/5 bg-zinc-600";
}

/* ── Page Component ───────────────────────────────────────────────────── */

export default function RiskDashboard() {
  const [tab, setTab] = useState<Tab>("risk");
  const [risks, setRisks] = useState<RiskScore[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unackCount, setUnackCount] = useState(0);
  const [velocities, setVelocities] = useState<Velocity[]>([]);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [surprise, setSurprise] = useState<SurpriseData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [riskRes, alertRes, velRes, scRes, surpRes] = await Promise.all([
        fetch(`${API_URL}/api/risk?limit=50`),
        fetch(`${API_URL}/api/alerts?limit=50`),
        fetch(`${API_URL}/api/velocity?limit=50`),
        fetch(`${API_URL}/api/predictions/scorecard`),
        fetch(`${API_URL}/api/predictions/surprise`),
      ]);

      if (riskRes.ok) setRisks((await riskRes.json()).scores);
      if (alertRes.ok) {
        const data = await alertRes.json();
        setAlerts(data.alerts);
        setUnackCount(data.unacknowledged_count);
      }
      if (velRes.ok) setVelocities((await velRes.json()).velocities);
      if (scRes.ok) setScorecard(await scRes.json());
      if (surpRes.ok) setSurprise(await surpRes.json());
    } catch (e) {
      console.error("Failed to fetch risk data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const acknowledgeAlert = async (alertId: string) => {
    try {
      const res = await fetch(`${API_URL}/api/alerts/${alertId}/acknowledge`, {
        method: "POST",
      });
      if (res.ok) {
        setAlerts((prev) =>
          prev.map((a) => (a.id === alertId ? { ...a, acknowledged: 1 } : a))
        );
        setUnackCount((prev) => Math.max(0, prev - 1));
      }
    } catch (e) {
      console.error("Failed to acknowledge alert:", e);
    }
  };

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
            <h1 className="text-sm font-medium text-zinc-300">Risk &amp; Alerts</h1>
          </div>
          <nav className="flex gap-3 text-sm">
            <Link href="/globe" className="text-zinc-400 hover:text-white transition-colors">Globe</Link>
            <Link href="/events" className="text-zinc-400 hover:text-white transition-colors">Events</Link>
            <Link href="/briefs" className="text-zinc-400 hover:text-white transition-colors">Briefs</Link>
            <Link href="/query" className="text-zinc-400 hover:text-white transition-colors">Query</Link>
            <Link href="/satellite" className="text-zinc-400 hover:text-white transition-colors">SPECINT</Link>
          </nav>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Tab bar */}
        <div className="flex gap-1 mb-6 bg-zinc-900/50 rounded-lg p-1 w-fit">
          {(
            [
              { key: "risk", label: "Risk Scores" },
              { key: "alerts", label: `Alerts${unackCount > 0 ? ` (${unackCount})` : ""}` },
              { key: "velocity", label: "Velocity" },
              { key: "predictions", label: "Predictions" },
            ] as { key: Tab; label: string }[]
          ).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === t.key
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-20 text-zinc-500">Loading risk data...</div>
        ) : (
          <>
            {/* ── Risk Scores Tab ──────────────────────────────── */}
            {tab === "risk" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-zinc-300">
                    Active Risk Scores ({risks.length})
                  </h3>
                </div>

                {risks.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No risk scores computed yet.</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {risks.map((r) => {
                      const trend = trendIcon(r.trend);
                      return (
                        <div
                          key={r.id}
                          className={`p-4 rounded-lg border ${scoreBg(r.score)}`}
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div>
                              <span className="text-xs text-zinc-500 uppercase tracking-wider">
                                {r.scope_type}
                              </span>
                              <p className="text-sm font-semibold text-white">
                                {r.scope_value}
                              </p>
                            </div>
                            <div className="text-right">
                              <span className={`text-2xl font-bold ${scoreColor(r.score)}`}>
                                {r.score}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 text-xs text-zinc-400 mt-2">
                            <span className={trend.color}>
                              {trend.icon} {r.trend}
                            </span>
                            <span>{r.event_count} events</span>
                            <span>{r.source_count} sources</span>
                          </div>

                          {r.components && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {Object.entries(r.components).map(([k, v]) => (
                                <span
                                  key={k}
                                  className="px-2 py-0.5 rounded text-xs bg-zinc-800 text-zinc-400"
                                >
                                  {k}: {typeof v === "number" ? v.toFixed(0) : v}
                                </span>
                              ))}
                            </div>
                          )}

                          {r.updated_at && (
                            <p className="text-xs text-zinc-600 mt-2">
                              Updated: {r.updated_at.slice(0, 16)}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ── Alerts Tab ──────────────────────────────────── */}
            {tab === "alerts" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-zinc-300">
                    Alert History ({alerts.length})
                  </h3>
                  {unackCount > 0 && (
                    <span className="px-2 py-1 rounded text-xs bg-red-500/20 text-red-400 border border-red-500/30">
                      {unackCount} unacknowledged
                    </span>
                  )}
                </div>

                {alerts.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No alerts fired yet.</p>
                ) : (
                  <div className="flex flex-col gap-2 max-w-4xl">
                    {alerts.map((a) => (
                      <div
                        key={a.id}
                        className={`p-3 rounded-lg border ${
                          a.acknowledged
                            ? "border-zinc-800 bg-zinc-900/30"
                            : "border-red-500/30 bg-red-500/5"
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`px-2 py-0.5 rounded text-xs border ${alertTypeBadge(
                              a.alert_type
                            )}`}
                          >
                            {a.alert_type}
                          </span>
                          <span className="text-xs text-zinc-500">
                            sev={a.severity}
                          </span>
                          <span className="text-xs text-zinc-600">
                            {a.scope_type}: {a.scope_value}
                          </span>
                          {!a.acknowledged && (
                            <button
                              onClick={() => acknowledgeAlert(a.id)}
                              className="ml-auto px-2 py-0.5 rounded text-xs bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors border border-zinc-700"
                            >
                              Acknowledge
                            </button>
                          )}
                          {!!a.acknowledged && (
                            <span className="ml-auto text-xs text-zinc-600">
                              Acknowledged
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-zinc-200 font-medium">
                          {a.title}
                        </p>
                        <p className="text-xs text-zinc-500 mt-0.5">
                          {a.description}
                        </p>
                        <p className="text-xs text-zinc-600 mt-1">
                          {a.created_at?.slice(0, 16)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Velocity Tab ─────────────────────────────────── */}
            {tab === "velocity" && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-zinc-300">
                  Event Velocity ({velocities.length})
                </h3>

                {velocities.length === 0 ? (
                  <p className="text-zinc-600 text-sm">No velocity data yet.</p>
                ) : (
                  <div className="flex flex-col gap-2 max-w-3xl">
                    {velocities.map((v) => (
                      <div
                        key={v.id}
                        className={`p-3 rounded-lg border ${
                          v.velocity_ratio >= 3
                            ? "border-red-500/30 bg-red-500/5"
                            : "border-zinc-800 bg-zinc-900/50"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-zinc-500 uppercase">
                              {v.scope_type}
                            </span>
                            <span className="text-sm font-medium text-white">
                              {v.scope_value}
                            </span>
                            <span className="px-1.5 py-0.5 rounded text-xs bg-zinc-800 text-zinc-400">
                              {v.period}
                            </span>
                          </div>
                          <span
                            className={`text-lg font-bold ${
                              v.velocity_ratio >= 3
                                ? "text-red-400"
                                : v.velocity_ratio >= 2
                                ? "text-orange-400"
                                : "text-zinc-400"
                            }`}
                          >
                            {v.velocity_ratio.toFixed(1)}x
                          </span>
                        </div>

                        {/* Velocity bar */}
                        <div className="w-full h-2 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${velocityBar(v.velocity_ratio)}`}
                            style={{
                              width: `${Math.min(100, (v.velocity_ratio / 5) * 100)}%`,
                            }}
                          />
                        </div>

                        <div className="flex gap-4 text-xs text-zinc-500 mt-2">
                          <span>{v.event_count} events</span>
                          <span>avg sev: {v.avg_severity?.toFixed(0)}</span>
                          <span>baseline: {v.baseline_rate?.toFixed(1)}/period</span>
                          {v.velocity_ratio >= 3 && (
                            <span className="text-red-400 font-medium">SPIKE</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Predictions Tab ──────────────────────────────── */}
            {tab === "predictions" && (
              <div className="space-y-6 max-w-4xl">
                {/* Scorecard summary */}
                {scorecard && (
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-300 mb-3">
                      Prediction Scorecard
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <StatCard label="Total" value={scorecard.total_predictions} />
                      <StatCard
                        label="Accuracy"
                        value={
                          scorecard.accuracy !== null
                            ? `${(scorecard.accuracy * 100).toFixed(1)}%`
                            : "N/A"
                        }
                        highlight={
                          scorecard.accuracy !== null && scorecard.accuracy >= 0.7
                        }
                      />
                      <StatCard label="Correct" value={scorecard.correct} color="text-emerald-400" />
                      <StatCard label="Incorrect" value={scorecard.incorrect} color="text-red-400" />
                      <StatCard label="Expired" value={scorecard.expired} color="text-orange-400" />
                      <StatCard label="Pending" value={scorecard.pending} color="text-cyan-400" />
                      <StatCard label="Resolved" value={scorecard.resolved} />
                    </div>

                    {/* Calibration chart */}
                    {scorecard.calibration && (
                      <div className="mt-6">
                        <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                          Calibration by Confidence Bucket
                        </h4>
                        <div className="flex flex-col gap-2">
                          {Object.entries(scorecard.calibration).map(
                            ([bucket, data]) => (
                              <div
                                key={bucket}
                                className="flex items-center gap-3 text-sm"
                              >
                                <span className="w-20 text-xs text-zinc-400 text-right">
                                  {bucket}
                                </span>
                                <div className="flex-1 h-5 rounded bg-zinc-800 overflow-hidden relative">
                                  {data.accuracy !== null && (
                                    <div
                                      className={`h-full rounded ${
                                        data.accuracy >= 0.7
                                          ? "bg-emerald-600"
                                          : data.accuracy >= 0.4
                                          ? "bg-yellow-600"
                                          : "bg-red-600"
                                      }`}
                                      style={{
                                        width: `${data.accuracy * 100}%`,
                                      }}
                                    />
                                  )}
                                  <span className="absolute inset-0 flex items-center justify-center text-xs text-white/80">
                                    {data.accuracy !== null
                                      ? `${(data.accuracy * 100).toFixed(0)}%`
                                      : "no data"}
                                    {" "}({data.correct}/{data.total})
                                  </span>
                                </div>
                                <span className="w-24 text-xs text-zinc-600">
                                  expected: {data.expected_range}
                                </span>
                              </div>
                            )
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Surprise index */}
                {surprise && (
                  <div className="p-4 rounded-lg border border-zinc-800 bg-zinc-900/50">
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                      Surprise Index — {surprise.date}
                    </h4>
                    <div className="flex items-center gap-4">
                      <span
                        className={`text-3xl font-bold ${
                          surprise.surprise_score >= 70
                            ? "text-red-400"
                            : surprise.surprise_score >= 40
                            ? "text-orange-400"
                            : "text-emerald-400"
                        }`}
                      >
                        {surprise.surprise_score}
                      </span>
                      <div className="text-xs text-zinc-500 space-y-0.5">
                        {surprise.reason === "no_predictions" ? (
                          <p>No predictions made for this date.</p>
                        ) : (
                          <>
                            <p>Predictions made: {surprise.predictions_made}</p>
                            <p>Correct: {surprise.predictions_correct}</p>
                            <p>Unexpected high-severity events: {surprise.unexpected_events}</p>
                            <p>Miss rate: {((surprise.miss_rate ?? 0) * 100).toFixed(0)}%</p>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ── Stat Card ─────────────────────────────────────────────────────────── */

function StatCard({
  label,
  value,
  color,
  highlight,
}: {
  label: string;
  value: string | number;
  color?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`p-3 rounded-lg border ${
        highlight
          ? "border-emerald-500/30 bg-emerald-500/10"
          : "border-zinc-800 bg-zinc-900/50"
      }`}
    >
      <span className="text-xs text-zinc-500 uppercase tracking-wider">
        {label}
      </span>
      <p className={`text-lg font-bold mt-0.5 ${color ?? "text-white"}`}>
        {value}
      </p>
    </div>
  );
}
