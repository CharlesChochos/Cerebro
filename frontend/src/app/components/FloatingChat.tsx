"use client";

import { useState, useRef, useEffect } from "react";
import { usePanels } from "../contexts/PanelContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function FloatingChat() {
  const { chatOpen, toggleChat } = usePanels();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (chatOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [chatOpen]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      if (res.ok) {
        const data = await res.json();
        setMessages((prev) => [...prev, { role: "assistant", content: data.answer || data.response || "No response." }]);
      } else {
        setMessages((prev) => [...prev, { role: "assistant", content: "Error: could not reach Cerebro." }]);
      }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Network error." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating button */}
      {!chatOpen && (
        <button
          onClick={toggleChat}
          className="fixed bottom-6 right-6 z-40 w-12 h-12 rounded-full bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-500/20 flex items-center justify-center transition-all hover:scale-105"
          title="Ask Cerebro"
        >
          <span className="text-lg">💬</span>
        </button>
      )}

      {/* Chat panel */}
      {chatOpen && (
        <div className="fixed bottom-6 right-6 z-40 w-96 h-[480px] bg-zinc-950/95 backdrop-blur-md border border-zinc-800/60 rounded-xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/60 shrink-0">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-sm font-semibold text-zinc-200">Ask Cerebro</span>
            </div>
            <button
              onClick={toggleChat}
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-zinc-800 text-zinc-500 hover:text-white transition-colors text-xs"
            >
              ✕
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-center text-zinc-600 text-xs mt-8">
                <p className="mb-1">Ask anything about global events.</p>
                <p className="text-zinc-700">Try: &quot;What happened in Ukraine today?&quot;</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`text-xs leading-relaxed rounded-lg px-3 py-2 max-w-[85%] ${
                  msg.role === "user"
                    ? "bg-emerald-600/20 border border-emerald-500/20 text-emerald-100 ml-auto"
                    : "bg-zinc-800/60 border border-zinc-700/40 text-zinc-300"
                }`}
              >
                {msg.content}
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <div className="w-3 h-3 border border-emerald-500/40 border-t-emerald-400 rounded-full animate-spin" />
                Thinking...
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-zinc-800/60 p-3 shrink-0">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                placeholder="Ask a question..."
                className="flex-1 bg-zinc-800/60 border border-zinc-700/40 rounded-lg px-3 py-2 text-xs text-white placeholder-zinc-500 outline-none focus:border-emerald-500/40"
              />
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 rounded-lg px-3 py-2 text-xs text-white font-medium transition-colors"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
