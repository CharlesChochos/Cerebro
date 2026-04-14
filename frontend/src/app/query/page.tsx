"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────────────────── */

interface Turn {
  id: string;
  turn_number: number;
  question: string;
  answer: string;
  event_ids: string[];
  entity_ids: string[];
  grounding_score: number | null;
  suggested_questions: string[];
  input_tokens: number;
  output_tokens: number;
  created_at: string;
}

interface Session {
  id: string;
  title: string;
  turn_count: number;
  updated_at: string;
}

interface QueryResponse {
  answer: string;
  session_id: string;
  turn_number: number;
  event_ids_referenced: string[];
  entity_ids_referenced: string[];
  suggested_questions: string[];
  grounding_score: number;
  input_tokens: number;
  output_tokens: number;
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function groundingColor(score: number | null): string {
  if (score === null) return "text-zinc-500";
  if (score >= 0.8) return "text-emerald-400";
  if (score >= 0.5) return "text-yellow-400";
  return "text-red-400";
}

/* ── Page Component ───────────────────────────────────────────────────── */

export default function QueryPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [showSidebar, setShowSidebar] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  /* Scroll to bottom when new turns arrive */
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  /* Focus input on load */
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  /* Fetch session list */
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/sessions?limit=30`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions);
      }
    } catch (e) {
      console.error("Failed to fetch sessions:", e);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  /* Load a session */
  const loadSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API_URL}/api/sessions/${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        setActiveSessionId(sessionId);
        setTurns(data.turns);
        const lastTurn = data.turns[data.turns.length - 1];
        if (lastTurn?.suggested_questions) {
          setSuggestedQuestions(lastTurn.suggested_questions);
        }
        setError(null);
      }
    } catch (e) {
      console.error("Failed to load session:", e);
    }
  };

  /* Start new session */
  const startNewSession = () => {
    setActiveSessionId(null);
    setTurns([]);
    setSuggestedQuestions([]);
    setError(null);
    inputRef.current?.focus();
  };

  /* Delete session */
  const deleteSession = async (sessionId: string) => {
    try {
      await fetch(`${API_URL}/api/sessions/${sessionId}`, { method: "DELETE" });
      if (activeSessionId === sessionId) {
        startNewSession();
      }
      fetchSessions();
    } catch (e) {
      console.error("Failed to delete session:", e);
    }
  };

  /* Submit question */
  const submitQuestion = async (q?: string) => {
    const text = q || question;
    if (!text.trim() || loading) return;

    setLoading(true);
    setError(null);
    setQuestion("");
    setSuggestedQuestions([]);

    // Optimistically add user turn
    const tempTurn: Turn = {
      id: "pending",
      turn_number: turns.length + 1,
      question: text,
      answer: "",
      event_ids: [],
      entity_ids: [],
      grounding_score: null,
      suggested_questions: [],
      input_tokens: 0,
      output_tokens: 0,
      created_at: new Date().toISOString(),
    };
    setTurns((prev) => [...prev, tempTurn]);

    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          session_id: activeSessionId,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const data: QueryResponse = await res.json();

      // Update session ID (might be new)
      if (!activeSessionId) {
        setActiveSessionId(data.session_id);
      }

      // Replace pending turn with real data
      const realTurn: Turn = {
        id: `turn-${data.turn_number}`,
        turn_number: data.turn_number,
        question: text,
        answer: data.answer,
        event_ids: data.event_ids_referenced,
        entity_ids: data.entity_ids_referenced,
        grounding_score: data.grounding_score,
        suggested_questions: data.suggested_questions,
        input_tokens: data.input_tokens,
        output_tokens: data.output_tokens,
        created_at: new Date().toISOString(),
      };

      setTurns((prev) => [...prev.slice(0, -1), realTurn]);
      setSuggestedQuestions(data.suggested_questions || []);

      // Refresh session list
      fetchSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to get answer");
      // Remove the pending turn
      setTurns((prev) => prev.filter((t) => t.id !== "pending"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-lg font-bold tracking-tight text-white hover:text-cyan-300 transition-colors"
            >
              Cerebro
            </Link>
            <span className="text-zinc-600">/</span>
            <h1 className="text-sm font-medium text-zinc-300">
              Intelligence Query
            </h1>
          </div>
          <nav className="flex gap-3 text-sm">
            <Link href="/globe" className="text-zinc-400 hover:text-white transition-colors">Globe</Link>
            <Link href="/events" className="text-zinc-400 hover:text-white transition-colors">Events</Link>
            <Link href="/briefs" className="text-zinc-400 hover:text-white transition-colors">Briefs</Link>
            <Link href="/entities" className="text-zinc-400 hover:text-white transition-colors">Entities</Link>
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="text-zinc-400 hover:text-white transition-colors"
            >
              {showSidebar ? "Hide History" : "History"}
            </button>
          </nav>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar — conversation history */}
        {showSidebar && (
          <aside className="w-64 border-r border-zinc-800 bg-zinc-900/30 flex flex-col">
            <div className="p-3 border-b border-zinc-800">
              <button
                onClick={startNewSession}
                className="w-full px-3 py-2 bg-cyan-900/30 hover:bg-cyan-800/40 border border-cyan-700/30 rounded-lg text-sm font-medium text-cyan-300 transition-colors"
              >
                + New Conversation
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2">
              {sessions.length === 0 ? (
                <p className="text-xs text-zinc-600 text-center py-4">
                  No conversations yet
                </p>
              ) : (
                sessions.map((s) => (
                  <div
                    key={s.id}
                    className={`group flex items-center gap-1 mb-1 rounded-lg transition-colors ${
                      activeSessionId === s.id
                        ? "bg-zinc-800"
                        : "hover:bg-zinc-800/50"
                    }`}
                  >
                    <button
                      onClick={() => loadSession(s.id)}
                      className="flex-1 text-left p-2 min-w-0"
                    >
                      <p className="text-xs text-zinc-300 truncate">
                        {s.title || "Untitled"}
                      </p>
                      <p className="text-xs text-zinc-600">
                        {s.turn_count} turns · {timeAgo(s.updated_at)}
                      </p>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSession(s.id);
                      }}
                      className="p-1 mr-1 text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Delete session"
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>
          </aside>
        )}

        {/* Main chat area */}
        <main className="flex-1 flex flex-col">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="max-w-3xl mx-auto">
              {turns.length === 0 && !loading && (
                <div className="text-center py-20">
                  <h2 className="text-2xl font-bold text-zinc-300 mb-2">
                    Ask Cerebro
                  </h2>
                  <p className="text-zinc-500 text-sm mb-8">
                    Ask questions about global events, security situations, and
                    geopolitical developments. Every answer is grounded in source data.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto">
                    {[
                      "What are the most critical events in the last 24 hours?",
                      "Is there any military escalation near the South China Sea?",
                      "What economic indicators are showing stress right now?",
                      "Are there any suspicious vessel movements in the Persian Gulf?",
                    ].map((q) => (
                      <button
                        key={q}
                        onClick={() => submitQuestion(q)}
                        className="text-left p-3 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-900 text-xs text-zinc-400 transition-colors"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {turns.map((turn) => (
                <div key={turn.id} className="mb-6">
                  {/* User question */}
                  <div className="flex justify-end mb-3">
                    <div className="bg-cyan-900/30 border border-cyan-800/30 rounded-lg px-4 py-2 max-w-md">
                      <p className="text-sm text-cyan-200">{turn.question}</p>
                    </div>
                  </div>

                  {/* Assistant answer */}
                  {turn.id === "pending" ? (
                    <div className="flex items-center gap-2 text-zinc-500 text-sm">
                      <div className="animate-pulse flex gap-1">
                        <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" />
                        <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce [animation-delay:150ms]" />
                        <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce [animation-delay:300ms]" />
                      </div>
                      Analyzing intelligence data...
                    </div>
                  ) : (
                    <div>
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-3">
                        <pre className="whitespace-pre-wrap text-sm text-zinc-300 font-sans leading-relaxed">
                          {turn.answer}
                        </pre>
                      </div>
                      {/* Metadata bar */}
                      <div className="flex items-center gap-3 mt-1 px-1 text-xs text-zinc-600">
                        <span className={groundingColor(turn.grounding_score)}>
                          Grounding:{" "}
                          {turn.grounding_score !== null
                            ? `${(turn.grounding_score * 100).toFixed(0)}%`
                            : "N/A"}
                        </span>
                        {turn.event_ids.length > 0 && (
                          <span>{turn.event_ids.length} events cited</span>
                        )}
                        {turn.input_tokens > 0 && (
                          <span>
                            {(turn.input_tokens + turn.output_tokens).toLocaleString()} tokens
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {error && (
                <div className="mb-4 p-3 rounded-lg bg-red-950/30 border border-red-900/30 text-sm text-red-400">
                  {error}
                </div>
              )}

              <div ref={chatEndRef} />
            </div>
          </div>

          {/* Suggested questions */}
          {suggestedQuestions.length > 0 && (
            <div className="px-4 pb-2">
              <div className="max-w-3xl mx-auto flex gap-2 flex-wrap">
                {suggestedQuestions.map((sq, i) => (
                  <button
                    key={i}
                    onClick={() => submitQuestion(sq)}
                    disabled={loading}
                    className="px-3 py-1.5 rounded-full border border-zinc-700 bg-zinc-900/50 hover:bg-zinc-800 text-xs text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
                  >
                    {sq}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input bar */}
          <div className="border-t border-zinc-800 bg-zinc-950/90 backdrop-blur p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitQuestion();
              }}
              className="max-w-3xl mx-auto flex gap-3"
            >
              <input
                ref={inputRef}
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about global events, security situations, or geopolitical developments..."
                className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-600 transition-colors"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !question.trim()}
                className="px-5 py-2.5 bg-cyan-700 hover:bg-cyan-600 disabled:bg-zinc-700 disabled:text-zinc-500 rounded-lg text-sm font-medium transition-colors"
              >
                {loading ? "..." : "Ask"}
              </button>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}
