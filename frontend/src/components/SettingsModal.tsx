"use client";

import { useState } from "react";
import { Database, Monitor, Moon, SlidersHorizontal, Sun, UserCircle2 } from "lucide-react";
import { QUESTIONS } from "@/data/questions";
import { SettingsTab, useApp } from "@/lib/store";
import { Avatar } from "./Sidebar";
import { CloseBtn, Modal, Toggle } from "./ui";

const TABS: { id: SettingsTab; label: string; icon: typeof Sun }[] = [
  { id: "profile", label: "Profile", icon: UserCircle2 },
  { id: "preference", label: "Preferences", icon: SlidersHorizontal },
  { id: "data", label: "Study data", icon: Database },
];

const btn = "rounded-lg border border-line px-3.5 py-2 text-sm font-medium transition hover:bg-surface-2";

function Row({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line py-4 last:border-0">
      <div className="min-w-0">
        <p className="text-[15px] font-medium">{title}</p>
        {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

/** Crops to a centred square and shrinks to 192px so it fits comfortably in localStorage. */
function toAvatar(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      const side = Math.min(img.width, img.height);
      const c = document.createElement("canvas");
      c.width = c.height = 192;
      c.getContext("2d")!.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, 192, 192);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("unreadable"));
    };
    img.src = url;
  });
}

function Profile() {
  const { settings, updateSettings, notify } = useApp();
  const [name, setName] = useState(settings.name);
  const pick = async (f?: File) => {
    if (!f) return;
    if (!f.type.startsWith("image/")) return notify("Choose an image file");
    try {
      updateSettings({ avatar: await toAvatar(f) });
    } catch {
      notify("That image couldn't be read");
    }
  };
  return (
    <>
      <div className="flex items-center gap-4 py-5">
        <Avatar name={settings.name} size={64} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-medium">{settings.name || "Guest"}</p>
          <p className="text-sm text-muted">No accounts yet. Your name, photo, progress and chats stay in this browser.</p>
        </div>
      </div>
      <Row title="Profile photo" hint="Saved on this device only">
        <div className="flex gap-2">
          <label className={`${btn} cursor-pointer`}>
            {settings.avatar ? "Change" : "Upload"}
            <input type="file" accept="image/*" className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
          {settings.avatar && (
            <button className={`${btn} text-muted`} onClick={() => updateSettings({ avatar: undefined })}>
              Remove
            </button>
          )}
        </div>
      </Row>
      <Row title="Display name" hint="Shown in the sidebar">
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            updateSettings({ name: e.target.value });
          }}
          placeholder="Guest"
          aria-label="Display name"
          maxLength={40}
          className="w-44 rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand sm:w-56"
        />
      </Row>
    </>
  );
}

function Preference() {
  const { settings: s, updateSettings: u } = useApp();
  const themes = [
    { v: "system", i: Monitor },
    { v: "light", i: Sun },
    { v: "dark", i: Moon },
  ] as const;
  return (
    <>
      <Row title="Theme" hint="Adjust your display appearance">
        <div role="radiogroup" aria-label="Theme" className="flex rounded-lg border border-line p-0.5">
          {themes.map(({ v, i: I }) => (
            <button key={v} role="radio" aria-checked={s.theme === v} aria-label={v} onClick={() => u({ theme: v })} className={`grid size-8 place-items-center rounded-md transition ${s.theme === v ? "bg-brand-soft text-brand" : "text-muted hover:text-ink"}`}>
              <I size={15} />
            </button>
          ))}
        </div>
      </Row>
      <Row title="Questions per search" hint="Shown before “Show more”">
        <div role="radiogroup" aria-label="Questions per search" className="flex rounded-lg border border-line p-0.5">
          {([3, 5, 8] as const).map((n) => (
            <button key={n} role="radio" aria-checked={s.perPage === n} onClick={() => u({ perPage: n })} className={`h-8 w-10 rounded-md text-sm font-medium transition ${s.perPage === n ? "bg-brand-soft text-brand" : "text-muted hover:text-ink"}`}>
              {n}
            </button>
          ))}
        </div>
      </Row>
      <Row title="Default source" hint="Tutorial sheets, PYQs or both">
        <select value={s.sourceFilter} onChange={(e) => u({ sourceFilter: e.target.value as typeof s.sourceFilter })} aria-label="Default source" className="rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand">
          <option value="all">All sources</option>
          <option value="Tutorial">Tutorial sheets</option>
          <option value="PYQ">PYQs</option>
        </select>
      </Row>
      <Row title="Try before reveal" hint="Ask for a second tap before showing an answer">
        <Toggle on={s.confirmReveal} onChange={(v) => u({ confirmReveal: v })} label="Try before reveal" />
      </Row>
      <Row title="Show source details" hint="Module, difficulty and marks on each card">
        <Toggle on={s.showMeta} onChange={(v) => u({ showMeta: v })} label="Show source details" />
      </Row>
      <Row title="Compact cards" hint="Tighter spacing">
        <Toggle on={s.compact} onChange={(v) => u({ compact: v })} label="Compact cards" />
      </Row>
    </>
  );
}

function StudyData() {
  const { solved, bookmarks, conversations, clearHistory, resetProgress, notify } = useApp();
  const saved = QUESTIONS.filter((q) => bookmarks.includes(q.id));
  const exportData = () => {
    const blob = new Blob([JSON.stringify({ solved, bookmarks, conversations }, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "mathsclub-study-data.json" });
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <>
      <dl className="grid grid-cols-3 divide-x divide-line border-b border-line py-5 text-center">
        {[
          ["Solved", solved.length],
          ["Saved", bookmarks.length],
          ["Chats", conversations.length],
        ].map(([l, n]) => (
          <div key={l}>
            <dd className="text-2xl font-semibold">{n}</dd>
            <dt className="text-sm text-muted">{l}</dt>
          </div>
        ))}
      </dl>
      <h3 className="pb-2 pt-4 text-sm font-medium text-muted">Saved questions</h3>
      {saved.length === 0 ? (
        <p className="text-sm text-muted">Nothing saved yet. Use the bookmark on a question to keep it here.</p>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {saved.map((q) => (
            <li key={q.id} className="px-4 py-3 text-sm">
              <p className="line-clamp-1">{q.text[0]}</p>
              <p className="mt-0.5 text-xs text-muted">{q.topics.join(", ")} · {q.source.label}</p>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4">
        <Row title="Export" hint="Progress and chats as a JSON file">
          <button className={btn} onClick={exportData}>Export</button>
        </Row>
        <Row title="Clear chat history" hint="Keeps solved marks and saved questions">
          <button className={btn} onClick={() => { clearHistory(); notify("Chat history cleared"); }}>Clear</button>
        </Row>
        <Row title="Reset progress" hint="Removes solved marks and saved questions">
          <button className={`${btn} text-orange`} onClick={() => { resetProgress(); notify("Progress reset"); }}>Reset</button>
        </Row>
      </div>
    </>
  );
}

export default function SettingsModal() {
  const { settingsTab, openSettings, closeSettings } = useApp();
  const tab = settingsTab ?? "profile";
  const current = TABS.find((t) => t.id === tab)!;
  return (
    <Modal open={settingsTab !== null} onClose={closeSettings} label="Settings" className="max-w-3xl">
      <div className="flex h-[min(600px,84vh)] flex-col sm:flex-row">
        <nav aria-label="Settings sections" className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-surface-2 p-2 sm:w-56 sm:flex-col sm:border-b-0 sm:border-r sm:p-3">
          {TABS.map(({ id, label, icon: I }) => (
            <button
              key={id}
              onClick={() => openSettings(id)}
              aria-current={tab === id}
              className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${tab === id ? "bg-surface font-medium" : "text-muted hover:text-ink"}`}
            >
              <I size={17} /> {label}
            </button>
          ))}
        </nav>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col px-5 pb-5 pt-4 sm:px-7">
          <div className="flex items-center justify-between border-b border-line pb-3">
            <h2 className="text-lg font-semibold">{current.label}</h2>
            <CloseBtn onClick={closeSettings} />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {tab === "profile" && <Profile />}
            {tab === "preference" && <Preference />}
            {tab === "data" && <StudyData />}
          </div>
        </div>
      </div>
    </Modal>
  );
}
