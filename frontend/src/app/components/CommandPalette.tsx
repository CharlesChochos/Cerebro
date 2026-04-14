"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";

/**
 * CommandPalette — global Cmd+K launcher.
 *
 * When on the home page (/), commands open panels via a dispatched custom event
 * that the PanelProvider listens for. On other routes, it falls back to router.push.
 */

interface Command {
  id: string;
  label: string;
  section: string;
  panelId?: string;        // panel to open (used on home page)
  panelZone?: "right" | "bottom" | "chat";
  href: string;            // fallback route (used on non-home pages)
  keywords: string[];
}

const COMMANDS: Command[] = [
  // Panels
  { id: "events", label: "Event Feed", section: "Intelligence", panelId: "events", panelZone: "right", href: "/events", keywords: ["events", "feed", "gdelt", "acled"] },
  { id: "entities", label: "Entities", section: "Intelligence", panelId: "entities", panelZone: "right", href: "/entities", keywords: ["entities", "people", "orgs"] },
  { id: "briefs", label: "Intel Briefs", section: "Intelligence", panelId: "intel", panelZone: "right", href: "/briefs", keywords: ["briefs", "reports", "daily", "flash"] },
  { id: "query", label: "Ask Cerebro", section: "Intelligence", panelId: "query", panelZone: "chat", href: "/query", keywords: ["query", "ask", "search", "claude", "ai"] },
  { id: "satellite", label: "SPECINT / Satellite", section: "Intelligence", panelId: "satellite", panelZone: "bottom", href: "/satellite", keywords: ["satellite", "specint", "imagery", "radar"] },
  { id: "risk", label: "Risk & Alerts", section: "Risk", panelId: "risk", panelZone: "right", href: "/risk", keywords: ["risk", "alerts", "velocity", "predictions"] },
  { id: "entity-intel", label: "Entity Intelligence", section: "Intelligence", panelId: "entity-intel", panelZone: "right", href: "/entity-intel", keywords: ["dossier", "ach", "sanctions", "graph", "entity"] },
  { id: "geospatial", label: "Geospatial Tools", section: "Geospatial", panelId: "geospatial", panelZone: "bottom", href: "/geospatial", keywords: ["geo", "geofence", "weapons", "kml", "trajectory", "measure"] },
  { id: "output", label: "Output & Distribution", section: "Output", panelId: "output", panelZone: "right", href: "/output", keywords: ["output", "webhooks", "widgets", "profiles", "weekly", "reports"] },
  { id: "sources", label: "Sources", section: "System", panelId: "sources", panelZone: "right", href: "/sources", keywords: ["sources", "ingestion", "feeds"] },
  // Navigation (always route-based)
  { id: "globe", label: "Intelligence Globe", section: "Navigation", href: "/globe", keywords: ["globe", "map", "3d"] },
  { id: "home", label: "Home / Dashboard", section: "Navigation", href: "/", keywords: ["home", "dashboard", "main"] },
];

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const pathname = usePathname();

  const filtered = COMMANDS.filter((cmd) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      cmd.label.toLowerCase().includes(q) ||
      cmd.section.toLowerCase().includes(q) ||
      cmd.keywords.some((k) => k.includes(q))
    );
  });

  // Group by section
  const sections = new Map<string, Command[]>();
  for (const cmd of filtered) {
    const arr = sections.get(cmd.section) || [];
    arr.push(cmd);
    sections.set(cmd.section, arr);
  }

  const flatList = filtered;

  const executeCommand = useCallback(
    (cmd: Command) => {
      // On the home page, open panels directly instead of navigating
      if (pathname === "/" && cmd.panelId && cmd.panelZone) {
        window.dispatchEvent(
          new CustomEvent("cerebro:open-panel", {
            detail: { id: cmd.panelId, zone: cmd.panelZone },
          })
        );
      } else {
        router.push(cmd.href);
      }
      setOpen(false);
    },
    [pathname, router]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K to toggle
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => {
          if (!prev) {
            setQuery("");
            setSelectedIndex(0);
          }
          return !prev;
        });
        return;
      }

      if (!open) return;

      if (e.key === "Escape") {
        setOpen(false);
        return;
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, flatList.length - 1));
        return;
      }

      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
        return;
      }

      if (e.key === "Enter" && flatList[selectedIndex]) {
        e.preventDefault();
        executeCommand(flatList[selectedIndex]);
      }
    },
    [open, flatList, selectedIndex, executeCommand],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Palette */}
      <div className="relative w-full max-w-lg bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden">
        {/* Search input */}
        <div className="flex items-center border-b border-zinc-800 px-4">
          <svg
            className="w-4 h-4 text-zinc-500 mr-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={inputRef}
            className="flex-1 bg-transparent py-3 text-sm text-zinc-100 placeholder-zinc-500 outline-none"
            placeholder="Search panels, tools, commands..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className="text-[10px] text-zinc-600 border border-zinc-700 rounded px-1.5 py-0.5">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto py-2">
          {flatList.length === 0 && (
            <p className="px-4 py-6 text-sm text-zinc-500 text-center">No results found.</p>
          )}
          {Array.from(sections.entries()).map(([section, cmds]) => (
            <div key={section}>
              <div className="px-4 py-1 text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">
                {section}
              </div>
              {cmds.map((cmd) => {
                const idx = flatList.indexOf(cmd);
                return (
                  <button
                    key={cmd.id}
                    className={`w-full text-left px-4 py-2 text-sm flex items-center gap-3 transition-colors ${
                      idx === selectedIndex
                        ? "bg-zinc-800 text-white"
                        : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
                    }`}
                    onClick={() => executeCommand(cmd)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                  >
                    <span className="flex-1">{cmd.label}</span>
                    {cmd.panelZone && (
                      <span className="text-[9px] text-zinc-600 bg-zinc-800 rounded px-1.5 py-0.5">
                        {cmd.panelZone === "chat" ? "chat" : "panel"}
                      </span>
                    )}
                    {idx === selectedIndex && (
                      <kbd className="text-[10px] text-zinc-600 border border-zinc-700 rounded px-1 py-0.5">
                        ↵
                      </kbd>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="border-t border-zinc-800 px-4 py-2 flex gap-4 text-[10px] text-zinc-600">
          <span>↑↓ navigate</span>
          <span>↵ select</span>
          <span>esc close</span>
        </div>
      </div>
    </div>
  );
}
