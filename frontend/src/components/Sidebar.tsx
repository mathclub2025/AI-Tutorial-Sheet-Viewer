"use client";

import { useMemo, useState } from "react";
import { Bookmark, ChevronDown, ChevronRight, ChevronsUpDown, Folder, FolderPlus, Pencil, Plus, Monitor, Moon, PanelLeft, Pin, Search, Settings as Cog, SquarePen, Sun, Trash2, User } from "lucide-react";
import { useApp } from "@/lib/store";
import type { Conversation, Settings } from "@/lib/types";
import { Logo, useOutside } from "./ui";

export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const { settings } = useApp();
  const initial = name.trim()[0]?.toUpperCase();
  if (settings.avatar) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={settings.avatar} alt="" width={size} height={size} className="shrink-0 rounded-full object-cover" style={{ width: size, height: size }} />;
  }
  return (
    <span className="grid shrink-0 place-items-center rounded-full bg-brand-soft font-semibold text-brand" style={{ width: size, height: size, fontSize: size * 0.4 }}>
      {initial ?? <User size={size * 0.5} />}
    </span>
  );
}

export function ThemeSwitch() {
  const { settings, updateSettings } = useApp();
  const opts: { v: Settings["theme"]; icon: typeof Sun; label: string }[] = [
    { v: "system", icon: Monitor, label: "System" },
    { v: "light", icon: Sun, label: "Light" },
    { v: "dark", icon: Moon, label: "Dark" },
  ];
  return (
    <div role="radiogroup" aria-label="Theme" className="flex rounded-lg border border-line p-0.5">
      {opts.map(({ v, icon: I, label }) => (
        <button
          key={v}
          role="radio"
          aria-checked={settings.theme === v}
          aria-label={label}
          title={label}
          onClick={() => updateSettings({ theme: v })}
          className={`grid size-7 place-items-center rounded-md transition ${settings.theme === v ? "bg-brand-soft text-brand" : "text-muted hover:text-ink"}`}
        >
          <I size={14} />
        </button>
      ))}
    </div>
  );
}

function ProfileMenu() {
  const { settings, openSettings, solved } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useOutside<HTMLDivElement>(open, () => setOpen(false));
  const label = settings.name || "Guest";
  const row = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition hover:bg-surface-2";
  return (
    <div ref={ref} className="relative">
      {open && (
        <div role="menu" className="absolute bottom-[calc(100%+6px)] left-0 right-0 z-30 rounded-xl border border-line bg-surface p-1 shadow-lg">
          <div className="flex items-center gap-3 px-3 py-2.5">
            <Avatar name={settings.name} />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{label}</p>
              <p className="text-xs text-muted">Saved on this device</p>
            </div>
          </div>
          <div className="my-1 border-t border-line" />
          <button role="menuitem" className={row} onClick={() => { setOpen(false); openSettings("profile"); }}>
            <Cog size={16} className="text-muted" /> Settings
          </button>
          <div className="flex items-center justify-between px-3 py-1.5 text-sm">
            <span className="flex items-center gap-3"><Sun size={16} className="text-muted" /> Theme</span>
            <ThemeSwitch />
          </div>
        </div>
      )}
      <button onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open} className="flex w-full items-center gap-3 rounded-xl border border-line bg-surface p-2.5 text-left transition hover:bg-surface-2">
        <Avatar name={settings.name} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{label}</span>
          <span className="block text-xs text-muted">{solved.length} solved</span>
        </span>
        <ChevronsUpDown size={15} className="text-muted" />
      </button>
    </div>
  );
}

function dayLabel(t: number) {
  const diff = Math.floor((new Date(new Date().toDateString()).getTime() - new Date(new Date(t).toDateString()).getTime()) / 864e5);
  return diff <= 0 ? "Today" : diff === 1 ? "Yesterday" : "Earlier";
}

function ChatRow({ c, nested = false }: { c: Conversation; nested?: boolean }) {
  const { active, setActiveId, deleteChat, setSidebarOpen } = useApp();
  return (
    <li className="group relative">
      <button
        onClick={() => {
          setActiveId(c.id);
          if (window.innerWidth < 1024) setSidebarOpen(false);
        }}
        aria-current={active?.id === c.id}
        className={`flex w-full items-center gap-2 rounded-lg py-2 pr-3 text-left text-sm transition ${nested ? "pl-9" : "pl-3"} ${active?.id === c.id ? "bg-surface font-medium" : "text-ink/80 hover:bg-surface"}`}
      >
        {c.pinned && <Pin size={12} className="shrink-0 text-muted" />}
        <span className="truncate">{c.title}</span>
      </button>
      <button
        onClick={() => deleteChat(c.id)}
        aria-label={`Delete ${c.title}`}
        className="absolute right-1.5 top-1/2 hidden size-7 -translate-y-1/2 place-items-center rounded-md bg-surface text-muted hover:text-orange group-hover:grid"
      >
        <Trash2 size={14} />
      </button>
    </li>
  );
}

export default function Sidebar() {
  const { conversations, setSearchOpen, setSidebarOpen, sidebarOpen, bookmarks, openSettings, newChat, projects, createProject, renameProject, deleteProject, openNameDialog } = useApp();
  const [openProjects, setOpenProjects] = useState<string[]>([]);
  const toggleProject = (id: string) => setOpenProjects((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const groups = useMemo(() => {
    const loose = conversations.filter((c) => !c.projectId || !projects.some((p) => p.id === c.projectId));
    const pinned = loose.filter((c) => c.pinned);
    const g: Record<string, typeof pinned> = {};
    loose.filter((c) => !c.pinned).forEach((c) => (g[dayLabel(c.updatedAt)] ??= []).push(c));
    return [["Pinned", pinned] as const, ...(["Today", "Yesterday", "Earlier"] as const).map((k) => [k, g[k] ?? []] as const)].filter(([, l]) => l.length);
  }, [conversations, projects]);

  const nav = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition hover:bg-surface";

  return (
    <>
      {sidebarOpen && <button aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-30 bg-[#0c181c]/40 lg:hidden" />}
      <aside
        aria-label="Sidebar"
        className={`fixed inset-y-0 left-0 z-40 flex w-[272px] shrink-0 flex-col bg-bg p-3 transition-transform duration-200 lg:static lg:transition-[margin] ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:-ml-[272px]"
        }`}
      >
        <div className="flex items-center justify-between px-1 pb-4 pt-1">
          <div className="flex items-center gap-2.5">
            <Logo size={34} />
            <div className="leading-tight">
              <p className="text-sm font-semibold">Maths Club</p>
              <p className="text-xs text-muted">VIT Chennai</p>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} aria-label="Collapse sidebar" className="grid size-8 place-items-center rounded-lg text-muted hover:bg-surface hover:text-ink">
            <PanelLeft size={17} />
          </button>
        </div>

        <nav className="space-y-0.5">
          <button className={nav} onClick={() => newChat()}>
            <SquarePen size={17} className="text-muted" /> New chat
          </button>
          <button className={nav} onClick={() => setSearchOpen(true)}>
            <Search size={17} className="text-muted" /> Search
            <kbd className="ml-auto font-mono text-[11px] text-muted">Ctrl K</kbd>
          </button>
          <button className={nav} onClick={() => openSettings("data")}>
            <Bookmark size={17} className="text-muted" /> Saved
            <span className="ml-auto text-xs text-muted">{bookmarks.length}</span>
          </button>
        </nav>

        <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
          <div className="mb-4">
            <div className="flex items-center justify-between px-3 pb-1">
              <h3 className="text-xs font-medium text-muted">Projects</h3>
              <button
                onClick={() =>
                  openNameDialog({
                    title: "New project",
                    placeholder: "e.g. Exam revision",
                    confirm: "Create",
                    onSubmit: (n) => {
                      const id = createProject(n);
                      setOpenProjects((p) => [...p, id]);
                    },
                  })
                }
                aria-label="New project"
                title="New project"
                className="grid size-7 place-items-center rounded-md text-muted hover:bg-surface hover:text-ink"
              >
                <FolderPlus size={16} />
              </button>
            </div>
            {projects.length === 0 && <p className="px-3 py-1 text-xs text-muted">Group related chats together.</p>}
            <ul>
              {projects.map((p) => {
                const chats = conversations.filter((c) => c.projectId === p.id);
                const open = openProjects.includes(p.id);
                return (
                  <li key={p.id}>
                    <div className="group relative">
                      <button onClick={() => toggleProject(p.id)} aria-expanded={open} className={nav}>
                        {open ? <ChevronDown size={14} className="text-muted" /> : <ChevronRight size={14} className="text-muted" />}
                        <Folder size={16} className="text-muted" />
                        <span className="truncate">{p.name}</span>
                        <span className="ml-auto text-xs text-muted group-hover:invisible">{chats.length}</span>
                      </button>
                      <div className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 items-center rounded-md bg-surface group-hover:flex">
                        <button
                          aria-label={`New chat in ${p.name}`}
                          title="New chat in project"
                          onClick={() => {
                            newChat(p.id);
                            setOpenProjects((o) => (o.includes(p.id) ? o : [...o, p.id]));
                          }}
                          className="grid size-7 place-items-center rounded-md text-muted hover:text-ink"
                        >
                          <Plus size={14} />
                        </button>
                        <button
                          aria-label={`Rename ${p.name}`}
                          title="Rename"
                          onClick={() => openNameDialog({ title: "Rename project", initial: p.name, confirm: "Save", onSubmit: (n) => renameProject(p.id, n) })}
                          className="grid size-7 place-items-center rounded-md text-muted hover:text-ink"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          aria-label={`Delete ${p.name}`}
                          title="Delete project (chats are kept)"
                          onClick={() => deleteProject(p.id)}
                          className="grid size-7 place-items-center rounded-md text-muted hover:text-orange"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                    {open && (
                      <ul>
                        {chats.length === 0 && <li className="py-1 pl-9 text-xs text-muted">No chats yet</li>}
                        {chats.map((c) => (
                          <ChatRow key={c.id} c={c} nested />
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
          {groups.map(([label, list]) => (
            <section key={label} className="mb-4">
              <h3 className="px-3 pb-1 text-xs font-medium text-muted">{label}</h3>
              <ul>
                {list.map((c) => (
                  <ChatRow key={c.id} c={c} />
                ))}
              </ul>
            </section>
          ))}
        </div>

        <div className="pt-3">
          <ProfileMenu />
        </div>
      </aside>
    </>
  );
}
