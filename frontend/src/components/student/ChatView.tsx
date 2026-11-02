"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Folder, FolderMinus, Copy, Check, Ellipsis, Menu, Pencil, Pin, PinOff, RefreshCw, Share2, ThumbsDown, ThumbsUp, Trash2, SearchX } from "lucide-react";
import { useApp } from "@/lib/studentStore";
import type { Message } from "@/lib/studentTypes";
import Composer from "./Composer";
import QuestionCard from "./QuestionCard";
import { Chip, IconBtn, Logo, useOutside } from "./ui";

function Welcome() {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col items-center justify-center px-4 pb-16 pt-6 text-center">
      <Logo size={64} />
      <h1 className="mt-6 text-2xl font-semibold tracking-tight sm:text-3xl text-ink">What do you want to practise?</h1>
      <p className="mt-2 max-w-md text-[15px] text-muted">
        Name a topic and get the questions on it from tutorial sheets and past papers. Answers stay hidden until you ask.
      </p>
      <div className="mt-8 w-full text-left">
        <Composer autoFocus />
      </div>
    </div>
  );
}

function AssistantMessage({ m, onRetry }: { m: Message; onRetry: () => void }) {
  const { settings, notify } = useApp();
  const [shown, setShown] = useState<number>(settings.perPage);
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState<"up" | "down" | null>(null);
  const qs = m.result?.questions ?? [];

  const copy = async () => {
    const txt = qs.map((q, i) => `${i + 1}. ${q.text.join(" ")}`).join("\n") || m.text;
    try {
      await navigator.clipboard.writeText(txt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      notify("Copy isn't available here");
    }
  };

  return (
    <div>
      <p className="text-[15px] leading-7 text-ink">{m.text}</p>
      {m.result && qs.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {m.result.subject && <Chip>{m.result.subject}</Chip>}
          {m.result.topics.map((t) => (
            <Chip key={t} tone="brand">{t}</Chip>
          ))}
        </div>
      )}
      {qs.length === 0 && (
        <div className="mt-4 flex items-center gap-3 rounded-2xl border border-dashed border-line p-4 text-sm text-muted">
          <SearchX size={20} /> No matching questions for this topic yet.
        </div>
      )}
      <div className="mt-4 space-y-4">
        {qs.slice(0, shown).map((q, i) => (
          <QuestionCard key={q.id} q={q} index={i} />
        ))}
      </div>
      {qs.length > shown && (
        <button onClick={() => setShown((s) => s + settings.perPage)} className="mt-4 rounded-lg border border-line px-4 py-2 text-sm font-medium transition hover:bg-surface-2 cursor-pointer">
          Show {Math.min(settings.perPage, qs.length - shown)} more · {qs.length - shown} left
        </button>
      )}
      <div className="mt-3 flex items-center gap-0.5">
        <IconBtn label={copied ? "Copied" : "Copy questions"} onClick={copy}>{copied ? <Check size={16} /> : <Copy size={16} />}</IconBtn>
        <IconBtn label="Search again" onClick={onRetry}><RefreshCw size={16} /></IconBtn>
        <IconBtn label="Good match" active={vote === "up"} onClick={() => { setVote("up"); notify("Thanks, noted."); }}><ThumbsUp size={16} /></IconBtn>
        <IconBtn label="Wrong match" active={vote === "down"} onClick={() => { setVote("down"); notify("Thanks, we'll tune the topic mapping."); }}><ThumbsDown size={16} /></IconBtn>
      </div>
    </div>
  );
}

function ChatMenu() {
  const { active, pinChat, renameChat, deleteChat, notify, projects, moveChat, openNameDialog } = useApp();
  const [open, setOpen] = useState(false);
  const [sub, setSub] = useState(false);
  const close = () => {
    setOpen(false);
    setSub(false);
  };
  const ref = useOutside<HTMLDivElement>(open, close);
  if (!active) return null;
  const item = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition hover:bg-surface-2 cursor-pointer";
  return (
    <div ref={ref} className="relative">
      <button onClick={() => (open ? close() : setOpen(true))} aria-label="Chat options" aria-haspopup="menu" aria-expanded={open} className="grid size-10 place-items-center rounded-lg border border-line text-muted transition hover:bg-surface-2 hover:text-ink cursor-pointer">
        <Ellipsis size={18} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-12 z-30 w-56 rounded-xl border border-line bg-surface p-1 shadow-lg">
          {!sub ? (
            <>
              <button role="menuitem" className={item} onClick={() => { pinChat(active.id); close(); }}>
                {active.pinned ? <PinOff size={16} /> : <Pin size={16} />} {active.pinned ? "Unpin" : "Pin"}
              </button>
              <button role="menuitem" className={item} onClick={() => { close(); openNameDialog({ title: "Rename chat", initial: active.title, confirm: "Save", onSubmit: (t) => renameChat(active.id, t) }); }}>
                <Pencil size={16} /> Rename
              </button>
              <button role="menuitem" className={item} onClick={() => setSub(true)}>
                <Folder size={16} /> Move to project <ChevronRight size={15} className="ml-auto text-muted" />
              </button>
              <button role="menuitem" className={`${item} text-orange`} onClick={() => { deleteChat(active.id); notify("Chat deleted"); close(); }}>
                <Trash2 size={16} /> Delete chat
              </button>
            </>
          ) : (
            <>
              <button className={`${item} text-muted`} onClick={() => setSub(false)}>
                <ChevronLeft size={16} /> Move to project
              </button>
              <div className="my-1 border-t border-line" />
              {projects.length === 0 && <p className="px-3 py-2 text-sm text-muted">No projects yet. Create one from the sidebar.</p>}
              {projects.map((p) => (
                <button key={p.id} role="menuitemradio" aria-checked={active.projectId === p.id} className={item} onClick={() => { moveChat(active.id, p.id); notify(`Moved to ${p.name}`); close(); }}>
                  <Folder size={16} className="text-muted" /> <span className="truncate">{p.name}</span>
                  {active.projectId === p.id && <Check size={15} className="ml-auto text-brand" />}
                </button>
              ))}
              {active.projectId && (
                <button className={`${item} text-muted`} onClick={() => { moveChat(active.id, null); close(); }}>
                  <FolderMinus size={16} /> Remove from project
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatView() {
  const { active, loading, send, setSidebarOpen, sidebarOpen, notify } = useApp();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [active?.messages.length, loading]);

  const share = async () => {
    if (!active) return;
    try {
      const lines = active.messages.flatMap((m) => (m.result?.questions ?? []).map((q, i) => `${i + 1}. [${q.source.label}] ${q.text.join(" ")}`));
      await navigator.clipboard.writeText([active.title, ...lines].join("\n"));
      notify("Questions copied as text");
    } catch {
      notify("Copy isn't available here");
    }
  };

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden rounded-none bg-surface lg:rounded-2xl lg:border lg:border-line">
      <header className="flex items-center gap-3 px-4 py-3 sm:px-6">
        {!sidebarOpen && (
          <button onClick={() => setSidebarOpen(true)} aria-label="Open sidebar" className="grid size-10 place-items-center rounded-xl text-muted hover:bg-surface-2 hover:text-ink cursor-pointer">
            <Menu size={20} />
          </button>
        )}
        <h2 className="min-w-0 flex-1 truncate text-sm font-medium text-muted">{active?.title ?? ""}</h2>
        <ChatMenu />
        {active && (
          <button onClick={share} className="hidden h-10 items-center gap-2 rounded-lg border border-line px-4 text-sm font-medium transition hover:bg-surface-2 sm:inline-flex cursor-pointer">
            <Share2 size={16} /> Share
          </button>
        )}
      </header>

      {!active ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Welcome />
        </div>
      ) : (
        <>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-6 sm:px-6">
              {active.messages.map((m, i) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <p className="max-w-[85%] rounded-2xl bg-surface-2 px-4 py-2.5 text-[15px] leading-7 text-ink">{m.text}</p>
                  </div>
                ) : (
                  <AssistantMessage key={m.id} m={m} onRetry={() => { const prev = active.messages[i - 1]; if (prev) send(prev.text); }} />
                ),
              )}
              {loading && (
                <div className="flex items-center gap-3 text-sm text-muted" role="status" aria-live="polite">
                  <Logo size={22} />
                  Matching topics in the question bank
                  <span className="flex gap-1">
                    {[0, 1, 2].map((d) => (
                      <span key={d} className="dot size-1.5 rounded-full bg-brand" style={{ animationDelay: `${d * 0.15}s` }} />
                    ))}
                  </span>
                </div>
              )}
              <div ref={end} />
            </div>
          </div>
          <div className="mx-auto w-full max-w-3xl px-4 pb-4 sm:px-6">
            <Composer />
            <p className="mt-2 text-center text-xs text-muted">Questions and solutions come from verified club sheets, not a generative model.</p>
          </div>
        </>
      )}
    </div>
  );
}
