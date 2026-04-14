"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────────── */

interface CountryProfile {
  id: string;
  country_code: string;
  country_name: string;
  period_start: string;
  period_end: string;
  risk_score: number;
  risk_trend: string;
  event_count: number;
  executive_summary: string;
  model_used: string | null;
  created_at: string;
}

interface WeeklyReport {
  id: string;
  week_start: string;
  week_end: string;
  title: string;
  executive_summary: string;
  global_risk_score: number;
  trending_topics: string;
  outlook: string;
  model_used: string | null;
  created_at: string;
}

interface Webhook {
  id: string;
  name: string;
  url: string;
  event_types: string[];
  filters: Record<string, unknown>;
  active: number;
  fire_count: number;
  error_count: number;
  last_fired: string | null;
  last_error: string | null;
  created_at: string;
}

interface WebhookLog {
  id: string;
  webhook_id: string;
  event_type: string;
  status_code: number | null;
  success: number;
  fired_at: string;
}

interface EmbedToken {
  id: string;
  token: string;
  widget_type: string;
  scope: Record<string, unknown>;
  expires_at: string;
  active: number;
  access_count: number;
  created_at: string;
}

/* ── Main Page ─────────────────────────────────────────────────────────── */

type Tab = "profiles" | "reports" | "webhooks" | "widgets";

export default function OutputPage() {
  const [tab, setTab] = useState<Tab>("profiles");

  const tabs: { key: Tab; label: string }[] = [
    { key: "profiles", label: "Country Profiles" },
    { key: "reports", label: "Weekly Reports" },
    { key: "webhooks", label: "Webhooks" },
    { key: "widgets", label: "Embed Widgets" },
  ];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-zinc-400 hover:text-zinc-200 text-sm">
            ← Home
          </Link>
          <h1 className="text-xl font-bold">Output &amp; Distribution</h1>
        </div>
        <span className="text-xs text-zinc-600">Phase 11</span>
      </header>

      <nav className="flex gap-1 px-6 pt-4">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-t text-sm font-medium transition-colors ${
              tab === t.key
                ? "bg-zinc-800 text-white"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="px-6 py-6">
        {tab === "profiles" && <CountryProfilesPanel />}
        {tab === "reports" && <WeeklyReportsPanel />}
        {tab === "webhooks" && <WebhooksPanel />}
        {tab === "widgets" && <WidgetsPanel />}
      </main>
    </div>
  );
}

/* ── Country Profiles Panel ────────────────────────────────────────────── */

function CountryProfilesPanel() {
  const [profiles, setProfiles] = useState<CountryProfile[]>([]);
  const [selected, setSelected] = useState<CountryProfile | null>(null);
  const [generating, setGenerating] = useState(false);
  const [form, setForm] = useState({ country_code: "", country_name: "", days: 7 });

  const load = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/reports/country-profiles?limit=20`);
    if (res.ok) {
      const data = await res.json();
      setProfiles(data.profiles || []);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    if (!form.country_code || !form.country_name) return;
    setGenerating(true);
    const res = await fetch(`${API_URL}/api/reports/country-profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    if (res.ok) {
      await load();
    }
    setGenerating(false);
  };

  return (
    <div className="space-y-6">
      {/* Generate form */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-zinc-300 mb-3">Generate Country Profile</h3>
        <div className="flex gap-3 items-end">
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Country Code</label>
            <input
              className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-24"
              placeholder="US"
              value={form.country_code}
              onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })}
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Country Name</label>
            <input
              className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-48"
              placeholder="United States"
              value={form.country_name}
              onChange={(e) => setForm({ ...form, country_name: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Days</label>
            <input
              type="number"
              className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-20"
              value={form.days}
              onChange={(e) => setForm({ ...form, days: parseInt(e.target.value) || 7 })}
            />
          </div>
          <button
            onClick={generate}
            disabled={generating}
            className="px-4 py-1.5 bg-cyan-900/50 hover:bg-cyan-800/60 border border-cyan-700/30 rounded text-sm text-cyan-300 disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* List */}
        <div className="space-y-2">
          {profiles.length === 0 && (
            <p className="text-zinc-600 text-sm">No profiles generated yet.</p>
          )}
          {profiles.map((p) => (
            <div
              key={p.id}
              onClick={() => setSelected(p)}
              className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                selected?.id === p.id
                  ? "border-cyan-700/50 bg-cyan-900/20"
                  : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm">
                  {p.country_name} ({p.country_code})
                </span>
                <TrendBadge trend={p.risk_trend} />
              </div>
              <div className="flex gap-4 mt-1 text-xs text-zinc-500">
                <span>Score: {p.risk_score?.toFixed(1)}</span>
                <span>Events: {p.event_count}</span>
                <span>{p.period_start} → {p.period_end}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Detail */}
        {selected && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
            <h3 className="text-lg font-bold">
              {selected.country_name} Risk Profile
            </h3>
            <div className="flex gap-4 text-xs text-zinc-500">
              <span>Score: {selected.risk_score?.toFixed(1)}</span>
              <TrendBadge trend={selected.risk_trend} />
              <span>{selected.event_count} events</span>
              {selected.model_used && (
                <span className="text-emerald-500">AI-generated</span>
              )}
            </div>
            <div className="text-sm text-zinc-300 whitespace-pre-wrap leading-relaxed">
              {selected.executive_summary}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Weekly Reports Panel ──────────────────────────────────────────────── */

function WeeklyReportsPanel() {
  const [reports, setReports] = useState<WeeklyReport[]>([]);
  const [selected, setSelected] = useState<WeeklyReport | null>(null);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/reports/weekly?limit=10`);
    if (res.ok) {
      const data = await res.json();
      setReports(data.reports || []);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    setGenerating(true);
    const res = await fetch(`${API_URL}/api/reports/weekly`, { method: "POST" });
    if (res.ok) {
      await load();
    }
    setGenerating(false);
  };

  const parseTrending = (topics: string): string[] => {
    try { return JSON.parse(topics); } catch { return []; }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Weekly Reports</h3>
        <button
          onClick={generate}
          disabled={generating}
          className="px-4 py-1.5 bg-amber-900/50 hover:bg-amber-800/60 border border-amber-700/30 rounded text-sm text-amber-300 disabled:opacity-50"
        >
          {generating ? "Generating…" : "Generate Weekly Report"}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          {reports.length === 0 && (
            <p className="text-zinc-600 text-sm">No reports generated yet.</p>
          )}
          {reports.map((r) => (
            <div
              key={r.id}
              onClick={() => setSelected(r)}
              className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                selected?.id === r.id
                  ? "border-amber-700/50 bg-amber-900/20"
                  : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
              }`}
            >
              <div className="font-medium text-sm">{r.title}</div>
              <div className="flex gap-4 mt-1 text-xs text-zinc-500">
                <span>{r.week_start} → {r.week_end}</span>
                <span>Risk: {r.global_risk_score?.toFixed(1)}</span>
                {r.model_used && <span className="text-emerald-500">AI</span>}
              </div>
            </div>
          ))}
        </div>

        {selected && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
            <h3 className="text-lg font-bold">{selected.title}</h3>
            <div className="flex gap-2 flex-wrap">
              {parseTrending(selected.trending_topics).map((t, i) => (
                <span key={i} className="px-2 py-0.5 bg-amber-900/30 border border-amber-700/20 rounded text-xs text-amber-300">
                  {t}
                </span>
              ))}
            </div>
            <div className="text-sm text-zinc-300 whitespace-pre-wrap leading-relaxed">
              {selected.executive_summary}
            </div>
            {selected.outlook && (
              <div>
                <h4 className="text-xs font-semibold text-zinc-400 uppercase mb-1">Outlook</h4>
                <p className="text-sm text-zinc-400">{selected.outlook}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Webhooks Panel ────────────────────────────────────────────────────── */

function WebhooksPanel() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [logs, setLogs] = useState<WebhookLog[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", url: "", secret: "", event_types: "alert,new_report" });

  const load = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/webhooks?active_only=false`);
    if (res.ok) {
      const data = await res.json();
      setWebhooks(data.webhooks || []);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadLogs = async (whId: string) => {
    setSelectedId(whId);
    const res = await fetch(`${API_URL}/api/webhooks/${whId}/logs`);
    if (res.ok) {
      const data = await res.json();
      setLogs(data.logs || []);
    }
  };

  const create = async () => {
    const res = await fetch(`${API_URL}/api/webhooks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: form.name,
        url: form.url,
        secret: form.secret || null,
        event_types: form.event_types.split(",").map((s) => s.trim()),
      }),
    });
    if (res.ok) {
      setShowCreate(false);
      setForm({ name: "", url: "", secret: "", event_types: "alert,new_report" });
      await load();
    }
  };

  const deleteHook = async (id: string) => {
    await fetch(`${API_URL}/api/webhooks/${id}`, { method: "DELETE" });
    await load();
    if (selectedId === id) { setSelectedId(null); setLogs([]); }
  };

  const testHook = async (id: string) => {
    await fetch(`${API_URL}/api/webhooks/${id}/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type: "test" }),
    });
    if (selectedId === id) loadLogs(id);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Webhooks</h3>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-4 py-1.5 bg-emerald-900/50 hover:bg-emerald-800/60 border border-emerald-700/30 rounded text-sm text-emerald-300"
        >
          {showCreate ? "Cancel" : "+ New Webhook"}
        </button>
      </div>

      {showCreate && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Name</label>
              <input
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-full"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">URL</label>
              <input
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-full"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Secret (optional)</label>
              <input
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-full"
                value={form.secret}
                onChange={(e) => setForm({ ...form, secret: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Event Types (comma-sep)</label>
              <input
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-full"
                value={form.event_types}
                onChange={(e) => setForm({ ...form, event_types: e.target.value })}
              />
            </div>
          </div>
          <button
            onClick={create}
            className="px-4 py-1.5 bg-emerald-900/50 border border-emerald-700/30 rounded text-sm text-emerald-300"
          >
            Create Webhook
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          {webhooks.length === 0 && <p className="text-zinc-600 text-sm">No webhooks registered.</p>}
          {webhooks.map((wh) => (
            <div
              key={wh.id}
              onClick={() => loadLogs(wh.id)}
              className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                selectedId === wh.id
                  ? "border-emerald-700/50 bg-emerald-900/20"
                  : "border-zinc-800 bg-zinc-900 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm">{wh.name}</span>
                <span className={`text-xs ${wh.active ? "text-emerald-400" : "text-red-400"}`}>
                  {wh.active ? "Active" : "Inactive"}
                </span>
              </div>
              <div className="text-xs text-zinc-500 mt-1 truncate">{wh.url}</div>
              <div className="flex gap-3 mt-2 text-xs text-zinc-500">
                <span>Fired: {wh.fire_count}</span>
                <span>Errors: {wh.error_count}</span>
                <span>Types: {wh.event_types.join(", ")}</span>
              </div>
              <div className="flex gap-2 mt-2">
                <button
                  onClick={(e) => { e.stopPropagation(); testHook(wh.id); }}
                  className="text-xs px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 rounded"
                >
                  Test
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteHook(wh.id); }}
                  className="text-xs px-2 py-0.5 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>

        {selectedId && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-zinc-300 mb-3">Delivery Logs</h4>
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {logs.length === 0 && <p className="text-zinc-600 text-xs">No logs yet.</p>}
              {logs.map((l) => (
                <div key={l.id} className="flex items-center gap-3 text-xs p-2 bg-zinc-800/50 rounded">
                  <span className={l.success ? "text-emerald-400" : "text-red-400"}>
                    {l.success ? "✓" : "✗"}
                  </span>
                  <span className="text-zinc-400">{l.event_type}</span>
                  <span className="text-zinc-500">{l.status_code ?? "—"}</span>
                  <span className="text-zinc-600 ml-auto">{l.fired_at?.slice(0, 19)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Widgets Panel ─────────────────────────────────────────────────────── */

function WidgetsPanel() {
  const [tokens, setTokens] = useState<EmbedToken[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ widget_type: "risk_score", country_code: "", hours: 168 });
  const [previewData, setPreviewData] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/widgets/tokens?active_only=false`);
    if (res.ok) {
      const data = await res.json();
      setTokens(data.tokens || []);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    const scope: Record<string, string> = {};
    if (form.country_code) scope.country_code = form.country_code;
    const res = await fetch(`${API_URL}/api/widgets/tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        widget_type: form.widget_type,
        scope,
        hours_valid: form.hours,
      }),
    });
    if (res.ok) {
      setShowCreate(false);
      await load();
    }
  };

  const revoke = async (id: string) => {
    await fetch(`${API_URL}/api/widgets/tokens/${id}`, { method: "DELETE" });
    await load();
  };

  const preview = async (token: string) => {
    const res = await fetch(`${API_URL}/api/widgets/embed?token=${token}`);
    if (res.ok) {
      setPreviewData(await res.json());
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Embed Widget Tokens</h3>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-4 py-1.5 bg-purple-900/50 hover:bg-purple-800/60 border border-purple-700/30 rounded text-sm text-purple-300"
        >
          {showCreate ? "Cancel" : "+ New Token"}
        </button>
      </div>

      {showCreate && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
          <div className="flex gap-3 items-end">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Widget Type</label>
              <select
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm"
                value={form.widget_type}
                onChange={(e) => setForm({ ...form, widget_type: e.target.value })}
              >
                <option value="risk_score">Risk Score</option>
                <option value="event_feed">Event Feed</option>
                <option value="alert_ticker">Alert Ticker</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Country Code (optional)</label>
              <input
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-24"
                value={form.country_code}
                onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Hours Valid</label>
              <input
                type="number"
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm w-24"
                value={form.hours}
                onChange={(e) => setForm({ ...form, hours: parseInt(e.target.value) || 168 })}
              />
            </div>
            <button
              onClick={create}
              className="px-4 py-1.5 bg-purple-900/50 border border-purple-700/30 rounded text-sm text-purple-300"
            >
              Create Token
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          {tokens.length === 0 && <p className="text-zinc-600 text-sm">No tokens created yet.</p>}
          {tokens.map((t) => (
            <div key={t.id} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900">
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm capitalize">{t.widget_type.replace("_", " ")}</span>
                <span className={`text-xs ${t.active ? "text-emerald-400" : "text-red-400"}`}>
                  {t.active ? "Active" : "Revoked"}
                </span>
              </div>
              <div className="text-xs text-zinc-600 font-mono mt-1 truncate">{t.token}</div>
              <div className="flex gap-3 mt-1 text-xs text-zinc-500">
                <span>Expires: {t.expires_at?.slice(0, 10)}</span>
                <span>Accesses: {t.access_count}</span>
                <span>Scope: {JSON.stringify(t.scope)}</span>
              </div>
              <div className="flex gap-2 mt-2">
                {t.active === 1 && (
                  <>
                    <button
                      onClick={() => preview(t.token)}
                      className="text-xs px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 rounded"
                    >
                      Preview
                    </button>
                    <button
                      onClick={() => revoke(t.id)}
                      className="text-xs px-2 py-0.5 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
                    >
                      Revoke
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        {previewData && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-zinc-300 mb-3">Widget Preview</h4>
            <pre className="text-xs text-zinc-400 bg-zinc-800 rounded p-3 overflow-auto max-h-96">
              {JSON.stringify(previewData, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Shared Components ─────────────────────────────────────────────────── */

function TrendBadge({ trend }: { trend: string }) {
  const color =
    trend === "rising"
      ? "text-red-400"
      : trend === "falling"
      ? "text-emerald-400"
      : "text-zinc-400";
  const arrow = trend === "rising" ? "↑" : trend === "falling" ? "↓" : "→";
  return <span className={`text-xs font-medium ${color}`}>{arrow} {trend}</span>;
}
