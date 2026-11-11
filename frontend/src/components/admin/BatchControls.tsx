"use client";
import { useState } from "react";
import { publishDocument, classifyDocument, type DocumentRecord } from "@/lib/adminApi";
import { messageOf } from "@/lib/api";
import { useStaff } from "./AdminAuthGuard";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
export function BatchControls({ doc, reload }: { doc: DocumentRecord; reload: () => Promise<void> }) {
  const staff = useStaff(); const [busy, setBusy] = useState(false);
  return <div className="rounded-xl border border-zinc-700 p-4 space-y-3">
    <p className="text-sm">Extraction: {doc.processing_status} · Index: {doc.indexing_status} · Visibility: {doc.visibility}</p>
    {doc.processing_status === "failed" && <p role="alert">Extraction failed. Check the job and retry the existing failed task through backend operations.</p>}
    {staff?.role !== "uploader" && <div className="flex flex-wrap gap-3">
      <Button disabled={busy || doc.processing_status !== "succeeded"} onClick={async () => {
        setBusy(true); try { await publishDocument(doc.id, doc.visibility === "public" ? "private" : "public"); await reload(); toast.success("Publication updated"); }
        catch(e) { toast.error(messageOf(e)); } finally { setBusy(false); }
      }}>{doc.visibility === "public" ? "Unpublish batch" : "Publish approved questions"}</Button>
      <label className="text-sm">Batch source <select aria-label="Batch source" className="bg-zinc-900 border border-zinc-600 rounded p-2" value={doc.source_type} disabled={busy || doc.processing_status !== "succeeded"} onChange={async e => {
        const source = e.target.value as "tutorial" | "pyq";
        if (!window.confirm("Change the entire batch classification? This unpublishes it and requires questions and solutions to be reviewed again.")) return;
        setBusy(true); try { await classifyDocument(doc, source); await reload(); } catch(error) { toast.error(messageOf(error)); } finally { setBusy(false); }
      }}><option value="tutorial">Tutorial</option><option value="pyq">PYQ</option></select></label>
    </div>}
    <p className="text-xs text-zinc-400">Only approved questions are published. Solutions require their own approval.</p>
  </div>;
}
