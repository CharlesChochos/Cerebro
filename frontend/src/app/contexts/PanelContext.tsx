"use client";

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";

export type PanelZone = "right" | "bottom" | "chat";

export interface PanelState {
  activeRight: string | null;
  activeBottom: string | null;
  chatOpen: boolean;
}

interface PanelContextValue extends PanelState {
  openPanel: (id: string, zone: PanelZone) => void;
  closePanel: (zone: PanelZone) => void;
  togglePanel: (id: string, zone: PanelZone) => void;
  toggleChat: () => void;
  closeAll: () => void;
}

const PanelContext = createContext<PanelContextValue | null>(null);

const STORAGE_KEY = "cerebro-panels";

function loadSaved(): Partial<PanelState> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function persist(state: PanelState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* quota exceeded — ignore */
  }
}

const EMPTY_STATE: PanelState = { activeRight: null, activeBottom: null, chatOpen: false };

export function PanelProvider({ children }: { children: ReactNode }) {
  // Start with empty state to match server HTML, then hydrate from localStorage
  const [state, setState] = useState<PanelState>(EMPTY_STATE);
  const [hydrated, setHydrated] = useState(false);

  // Restore saved panel state after mount (avoids hydration mismatch)
  useEffect(() => {
    const saved = loadSaved();
    setState({
      activeRight: saved.activeRight ?? null,
      activeBottom: saved.activeBottom ?? null,
      chatOpen: saved.chatOpen ?? false,
    });
    setHydrated(true);
  }, []);

  // Persist to localStorage on changes (only after initial hydration)
  useEffect(() => {
    if (hydrated) persist(state);
  }, [state, hydrated]);

  // Listen for custom events from CommandPalette (which lives outside PanelProvider)
  useEffect(() => {
    const handler = (e: Event) => {
      const { id, zone } = (e as CustomEvent).detail as { id: string; zone: PanelZone };
      setState((prev) => {
        if (zone === "right") return { ...prev, activeRight: id };
        if (zone === "bottom") return { ...prev, activeBottom: id };
        if (zone === "chat") return { ...prev, chatOpen: true };
        return prev;
      });
    };
    window.addEventListener("cerebro:open-panel", handler);
    return () => window.removeEventListener("cerebro:open-panel", handler);
  }, []);

  const openPanel = useCallback((id: string, zone: PanelZone) => {
    setState((prev) => {
      if (zone === "right") return { ...prev, activeRight: id };
      if (zone === "bottom") return { ...prev, activeBottom: id };
      if (zone === "chat") return { ...prev, chatOpen: true };
      return prev;
    });
  }, []);

  const closePanel = useCallback((zone: PanelZone) => {
    setState((prev) => {
      if (zone === "right") return { ...prev, activeRight: null };
      if (zone === "bottom") return { ...prev, activeBottom: null };
      if (zone === "chat") return { ...prev, chatOpen: false };
      return prev;
    });
  }, []);

  const togglePanel = useCallback((id: string, zone: PanelZone) => {
    setState((prev) => {
      if (zone === "right") {
        return { ...prev, activeRight: prev.activeRight === id ? null : id };
      }
      if (zone === "bottom") {
        return { ...prev, activeBottom: prev.activeBottom === id ? null : id };
      }
      if (zone === "chat") {
        return { ...prev, chatOpen: !prev.chatOpen };
      }
      return prev;
    });
  }, []);

  const toggleChat = useCallback(() => {
    setState((prev) => ({ ...prev, chatOpen: !prev.chatOpen }));
  }, []);

  const closeAll = useCallback(() => {
    setState({ activeRight: null, activeBottom: null, chatOpen: false });
  }, []);

  return (
    <PanelContext value={{ ...state, openPanel, closePanel, togglePanel, toggleChat, closeAll }}>
      {children}
    </PanelContext>
  );
}

export function usePanels(): PanelContextValue {
  const ctx = useContext(PanelContext);
  if (!ctx) throw new Error("usePanels must be used within a PanelProvider");
  return ctx;
}
