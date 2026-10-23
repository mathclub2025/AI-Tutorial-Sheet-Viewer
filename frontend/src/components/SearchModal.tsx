"use client";

import { useState } from "react";
import { MessageSquare, Search } from "lucide-react";
import { useApp } from "@/lib/store";
import { Modal } from "./ui";

function Body() {
  const { setSearchOpen, conversations, setActiveId, setDraft, newChat } = useApp();
  const [q, setQ] = useState("");
  const list = conversations.filter((c) => c.title.toLowerCase().includes(q.toLowerCase()));
  const close = () => setSearchOpen(false);

  return (
    <>
      <div className="flex items-center gap-3 border-b border-line px-5 py-4">
        <Search size={18} className="text-muted" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your chats" aria-label="Search your chats" className="w-full bg-transparent text-[15px] outline-none placeholder:text-muted" />
        <kbd className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted">Esc</kbd>
      </div>
      <ul className="max-h-80 overflow-y-auto p-2">
        {list.map((c) => (
          <li key={c.id}>
            <button onClick={() => { setActiveId(c.id); close(); }} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-surface-2">
              <MessageSquare size={16} className="text-muted" /> <span className="truncate">{c.title}</span>
            </button>
          </li>
        ))}
        {list.length === 0 && (
          <li className="px-3 py-8 text-center text-sm text-muted">
            {q ? (
              <>
                No chats match.{" "}
                <button className="font-medium text-brand underline" onClick={() => { newChat(); setDraft(q); close(); }}>Practise “{q}” instead</button>
              </>
            ) : (
              "No chats yet."
            )}
          </li>
        )}
      </ul>
    </>
  );
}

export default function SearchModal() {
  const { searchOpen, setSearchOpen } = useApp();
  return (
    <Modal open={searchOpen} onClose={() => setSearchOpen(false)} label="Search chats" className="max-w-xl">
      <Body />
    </Modal>
  );
}
