"use client";

import { useState } from "react";
import { useApp, type NameDialogConfig } from "@/lib/studentStore";
import { Modal } from "./ui";

function Body({ cfg }: { cfg: NameDialogConfig }) {
  const { closeNameDialog } = useApp();
  const [v, setV] = useState(cfg.initial ?? "");
  const submit = () => {
    if (!v.trim()) return;
    cfg.onSubmit(v.trim());
    closeNameDialog();
  };
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="p-5"
    >
      <h2 className="text-lg font-semibold">{cfg.title}</h2>
      <input
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        onFocus={(e) => e.target.select()}
        placeholder={cfg.placeholder}
        aria-label={cfg.title}
        maxLength={60}
        className="mt-4 w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-[15px] outline-none focus:border-brand"
      />
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" onClick={closeNameDialog} className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-surface-2 cursor-pointer">
          Cancel
        </button>
        <button type="submit" disabled={!v.trim()} className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-ink hover:opacity-90 disabled:bg-line disabled:text-muted cursor-pointer">
          {cfg.confirm}
        </button>
      </div>
    </form>
  );
}

export default function NameDialog() {
  const { nameDialog, closeNameDialog } = useApp();
  return (
    <Modal open={!!nameDialog} onClose={closeNameDialog} label={nameDialog?.title ?? "Name"} className="max-w-sm">
      {nameDialog && <Body cfg={nameDialog} />}
    </Modal>
  );
}
