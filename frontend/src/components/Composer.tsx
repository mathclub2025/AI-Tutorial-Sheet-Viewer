"use client";

import { useRef, useState } from "react";
import { ArrowUp, Check, ChevronDown } from "lucide-react";
import { useApp } from "@/lib/store";
import type { SourceFilter } from "@/lib/types";
import { useOutside } from "./ui";

const SOURCES: { v: SourceFilter; label: string }[] = [
  { v: "all", label: "All sources" },
  { v: "Tutorial", label: "Tutorial sheets" },
  { v: "PYQ", label: "Previous year papers" },
];

export default function Composer({ autoFocus = false }: { autoFocus?: boolean }) {
  const { send, loading, settings, updateSettings, draft, setDraft } = useApp();
  const [menu, setMenu] = useState(false);
  const ref = useOutside<HTMLDivElement>(menu, () => setMenu(false));
  const ta = useRef<HTMLTextAreaElement>(null);
  const current = SOURCES.find((s) => s.v === settings.sourceFilter)!;

  const submit = () => {
    if (!draft.trim() || loading) return;
    const t = draft;
    setDraft("");
    if (ta.current) ta.current.style.height = "auto";
    send(t);
  };

  return (
    <div className="rounded-2xl border border-line bg-surface p-3 transition focus-within:border-brand">
      <textarea
        ref={ta}
        autoFocus={autoFocus}
        rows={1}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          e.target.style.height = "auto";
          e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Ask for a topic, e.g. mean, median and mode"
        aria-label="Ask for practice questions"
        className="block max-h-40 w-full resize-none bg-transparent px-1.5 py-1.5 text-[15px] outline-none placeholder:text-muted/70"
      />
      <div className="mt-1 flex items-center">
        <div ref={ref} className="relative">
          <button
            onClick={() => setMenu((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={menu}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm text-muted transition hover:bg-surface-2 hover:text-ink"
          >
            {current.label}
            <ChevronDown size={14} />
          </button>
          {menu && (
            <div role="menu" className="absolute bottom-10 left-0 z-20 w-56 rounded-xl border border-line bg-surface p-1 shadow-lg">
              {SOURCES.map((s) => (
                <button
                  key={s.v}
                  role="menuitemradio"
                  aria-checked={s.v === settings.sourceFilter}
                  onClick={() => {
                    updateSettings({ sourceFilter: s.v });
                    setMenu(false);
                  }}
                  className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition hover:bg-surface-2"
                >
                  {s.label}
                  {s.v === settings.sourceFilter && <Check size={15} className="text-brand" />}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={submit}
          disabled={!draft.trim() || loading}
          aria-label="Send"
          className="ml-auto grid size-9 place-items-center rounded-lg bg-brand text-brand-ink transition enabled:hover:opacity-90 disabled:bg-line disabled:text-muted"
        >
          <ArrowUp size={18} />
        </button>
      </div>
    </div>
  );
}
