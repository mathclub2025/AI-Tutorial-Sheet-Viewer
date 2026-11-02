"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { searchQuestions } from "./studentApi";
import type { Conversation, Message, Project, Settings } from "./studentTypes";

export type SettingsTab = "profile" | "preference" | "data";

const DEFAULT_SETTINGS: Settings = {
  name: "",
  theme: "system",
  perPage: 5,
  sourceFilter: "all",
  showMeta: true,
  confirmReveal: false,
  compact: false,
};

export interface NameDialogConfig {
  title: string;
  initial?: string;
  placeholder?: string;
  confirm: string;
  onSubmit: (value: string) => void;
}

interface Ctx {
  ready: boolean;
  settings: Settings;
  updateSettings: (p: Partial<Settings>) => void;
  conversations: Conversation[];
  active: Conversation | null;
  setActiveId: (id: string | null) => void;
  newChat: (projectId?: string) => void;
  projects: Project[];
  createProject: (name: string) => string;
  renameProject: (id: string, name: string) => void;
  deleteProject: (id: string) => void;
  moveChat: (id: string, projectId: string | null) => void;
  nameDialog: NameDialogConfig | null;
  openNameDialog: (c: NameDialogConfig) => void;
  closeNameDialog: () => void;
  send: (text: string) => Promise<void>;
  loading: boolean;
  renameChat: (id: string, title: string) => void;
  deleteChat: (id: string) => void;
  pinChat: (id: string) => void;
  clearHistory: () => void;
  bookmarks: string[];
  toggleBookmark: (id: string) => void;
  solved: string[];
  toggleSolved: (id: string) => void;
  resetProgress: () => void;
  sidebarOpen: boolean;
  setSidebarOpen: (v: boolean) => void;
  settingsTab: SettingsTab | null;
  openSettings: (t?: SettingsTab) => void;
  closeSettings: () => void;
  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;
  toast: string | null;
  notify: (m: string) => void;
  draft: string;
  setDraft: (v: string) => void;
}

const AppCtx = createContext<Ctx | null>(null);
export const useApp = () => {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
};

const uid = () => Math.random().toString(36).slice(2, 10);

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {}
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [pendingProject, setPendingProject] = useState<string | undefined>();
  const [nameDialog, setNameDialog] = useState<NameDialogConfig | null>(null);
  const [bookmarks, setBookmarks] = useState<string[]>([]);
  const [solved, setSolved] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsTab, setSettingsTab] = useState<SettingsTab | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // One-time hydration from localStorage (must run client-side after mount).
  useEffect(() => {
    const saved = load<Partial<Settings> & { email?: string }>("mc.settings", {});
    if (saved.name === "Student") saved.name = ""; // placeholder from an earlier build
    setSettings({ ...DEFAULT_SETTINGS, ...saved });
    setConversations(load("mc.chats.v2", []));
    setProjects(load("mc.projects.v2", []));
    setBookmarks(load("mc.bookmarks.v2", []));
    setSolved(load("mc.solved.v2", []));
    if (window.innerWidth < 1024) setSidebarOpen(false);
    setReady(true);
  }, []);

  useEffect(() => { if (ready) save("mc.settings", settings); }, [settings, ready]);
  useEffect(() => { if (ready) save("mc.chats.v2", conversations); }, [conversations, ready]);
  useEffect(() => { if (ready) save("mc.projects.v2", projects); }, [projects, ready]);
  useEffect(() => { if (ready) save("mc.bookmarks.v2", bookmarks); }, [bookmarks, ready]);
  useEffect(() => { if (ready) save("mc.solved.v2", solved); }, [solved, ready]);

  // theme
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      document.documentElement.classList.toggle("dark", settings.theme === "dark" || (settings.theme === "system" && mq.matches));
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [settings.theme]);

  // ⌘/Ctrl+K
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const notify = useCallback((m: string) => {
    setToast(m);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2400);
  }, []);

  const active = useMemo(() => conversations.find((c) => c.id === activeId) ?? null, [conversations, activeId]);

  const send = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || loading) return;
      const userMsg: Message = { id: uid(), role: "user", text: q };
      let id = activeId;
      if (!id || !conversations.some((c) => c.id === id)) {
        id = uid();
        const conv: Conversation = { id, title: q.length > 42 ? q.slice(0, 42) + "…" : q, updatedAt: Date.now(), projectId: pendingProject, messages: [userMsg] };
        setConversations((p) => [conv, ...p]);
        setActiveId(id);
      } else {
        setConversations((p) => p.map((c) => (c.id === id ? { ...c, updatedAt: Date.now(), messages: [...c.messages, userMsg] } : c)));
      }
      setLoading(true);
      const cid = id;
      try {
        const result = await searchQuestions(q, settings.sourceFilter);
        const n = result.questions.length;
        const reply: Message = {
          id: uid(),
          role: "assistant",
          result,
          text: n
            ? `Found ${n} question${n > 1 ? "s" : ""}${result.subject ? ` in ${result.subject}` : ""}. Solutions stay hidden until you reveal them.`
            : "I couldn't match that to any topic yet. Try naming a topic, like “variance”, “Bayes theorem” or “eigenvalues”.",
        };
        setConversations((p) => p.map((c) => (c.id === cid ? { ...c, updatedAt: Date.now(), messages: [...c.messages, reply] } : c)));
      } catch {
        notify("Couldn't reach the question bank. Try again.");
      } finally {
        setLoading(false);
      }
    },
    [activeId, conversations, loading, settings.sourceFilter, notify, pendingProject],
  );

  const value: Ctx = {
    ready,
    settings,
    updateSettings: (p) => setSettings((s) => ({ ...s, ...p })),
    conversations: [...conversations].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned) || b.updatedAt - a.updatedAt),
    active,
    setActiveId: (id) => {
      setPendingProject(undefined);
      setActiveId(id);
    },
    projects,
    createProject: (name) => {
      const id = uid();
      setProjects((p) => [...p, { id, name: name.trim() }]);
      return id;
    },
    renameProject: (id, name) => setProjects((p) => p.map((x) => (x.id === id ? { ...x, name: name.trim() || x.name } : x))),
    deleteProject: (id) => {
      setProjects((p) => p.filter((x) => x.id !== id));
      setConversations((p) => p.map((c) => (c.projectId === id ? { ...c, projectId: undefined } : c)));
    },
    moveChat: (id, projectId) => setConversations((p) => p.map((c) => (c.id === id ? { ...c, projectId: projectId ?? undefined } : c))),
    nameDialog,
    openNameDialog: setNameDialog,
    closeNameDialog: () => setNameDialog(null),
    newChat: (projectId) => {
      setPendingProject(projectId);
      setActiveId(null);
      setDraft("");
      if (window.innerWidth < 1024) setSidebarOpen(false);
    },
    send,
    loading,
    renameChat: (id, title) => setConversations((p) => p.map((c) => (c.id === id ? { ...c, title: title.trim() || c.title } : c))),
    deleteChat: (id) => {
      setConversations((p) => p.filter((c) => c.id !== id));
      if (activeId === id) setActiveId(null);
    },
    pinChat: (id) => setConversations((p) => p.map((c) => (c.id === id ? { ...c, pinned: !c.pinned } : c))),
    clearHistory: () => {
      setConversations([]);
      setActiveId(null);
    },
    bookmarks,
    toggleBookmark: (id) => setBookmarks((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id])),
    solved,
    toggleSolved: (id) => setSolved((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id])),
    resetProgress: () => {
      setSolved([]);
      setBookmarks([]);
    },
    sidebarOpen,
    setSidebarOpen,
    settingsTab,
    openSettings: (t = "profile") => setSettingsTab(t),
    closeSettings: () => setSettingsTab(null),
    searchOpen,
    setSearchOpen,
    toast,
    notify,
    draft,
    setDraft,
  };

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}
