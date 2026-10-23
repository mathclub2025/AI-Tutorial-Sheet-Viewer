"use client";

import { useState } from "react";
import { Bookmark, BookmarkCheck, Check } from "lucide-react";
import { useApp } from "@/lib/store";
import type { Question } from "@/lib/types";
import { Chip } from "./ui";

/** Cropped question image when the pipeline provides one; typeset text until then. */
function Extract({ q }: { q: Question }) {
  if (q.imageUrl) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={q.imageUrl} alt={`Question: ${q.text.join(" ")}`} className="w-full rounded-lg border border-line bg-white" />;
  }
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-4 py-3 font-mono text-[14px] leading-7">
      {q.text.map((t, i) => (
        <p key={i}>{t}</p>
      ))}
      {q.table && (
        <div className="my-2 overflow-x-auto">
          <table className="border-collapse text-sm">
            <thead>
              <tr>
                {q.table.head.map((h, i) => (
                  <th key={i} className="border border-line bg-surface px-3 py-1 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {q.table.rows.map((r, i) => (
                <tr key={i}>
                  {r.map((c, j) => (
                    <td key={j} className="border border-line bg-surface px-3 py-1">{c}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function QuestionCard({ q, index }: { q: Question; index: number }) {
  const { settings, bookmarks, toggleBookmark, solved, toggleSolved } = useApp();
  const [show, setShow] = useState(false);
  const [armed, setArmed] = useState(false);
  const marked = bookmarks.includes(q.id);
  const done = solved.includes(q.id);

  const reveal = () => {
    if (show) return setShow(false);
    if (settings.confirmReveal && !armed) return setArmed(true);
    setShow(true);
    setArmed(false);
  };

  const btn = "rounded-lg border px-3.5 py-2 text-sm font-medium transition";

  return (
    <article className={`rounded-xl border border-line bg-surface ${settings.compact ? "p-3.5" : "p-5"}`}>
      <header className="mb-3 flex items-start gap-3">
        <span className="mt-0.5 font-mono text-sm text-muted">{String(index + 1).padStart(2, "0")}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {q.topics.slice(0, 3).map((t) => (
              <Chip key={t} tone="brand">{t}</Chip>
            ))}
            {settings.showMeta && <Chip tone={q.source.type === "PYQ" ? "accent" : "plain"}>{q.source.label}{q.source.year ? ` · ${q.source.year}` : ""}</Chip>}
          </div>
          {settings.showMeta && (
            <p className="mt-1.5 text-xs text-muted">
              {q.module} · {q.difficulty}
              {q.marks ? ` · ${q.marks} marks` : ""}
            </p>
          )}
        </div>
        <button
          onClick={() => toggleBookmark(q.id)}
          aria-pressed={marked}
          aria-label={marked ? "Remove bookmark" : "Bookmark"}
          title={marked ? "Remove bookmark" : "Bookmark"}
          className={`grid size-8 shrink-0 place-items-center rounded-lg transition hover:bg-surface-2 ${marked ? "text-brand" : "text-muted"}`}
        >
          {marked ? <BookmarkCheck size={18} /> : <Bookmark size={18} />}
        </button>
      </header>

      <Extract q={q} />

      <div className="mt-3 flex flex-wrap gap-2">
        <button onClick={reveal} className={`${btn} ${show ? "border-line text-ink hover:bg-surface-2" : "border-brand bg-brand text-brand-ink hover:opacity-90"}`}>
          {show ? "Hide answer" : armed ? "Tried it first? Tap again to reveal" : "Show answer"}
        </button>
        <button
          onClick={() => toggleSolved(q.id)}
          aria-pressed={done}
          className={`${btn} inline-flex items-center gap-1.5 ${done ? "border-brand text-brand" : "border-line text-muted hover:text-ink"}`}
        >
          {done && <Check size={15} />}
          {done ? "Solved" : "Mark solved"}
        </button>
      </div>

      {show && (
        <div className="mt-3 border-t border-line pt-3">
          {q.solutionImageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={q.solutionImageUrl} alt="Solution" className="w-full rounded-lg border border-line bg-white" />
          ) : (
            <div className="whitespace-pre-line text-[14.5px] leading-7">
              {q.steps.map((s) => `${s.title}\n${s.body}`).join("\n\n")}
              {"\n\n"}
              <strong className="font-semibold">Answer: </strong>
              {q.answer}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
