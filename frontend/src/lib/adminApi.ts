import type { Question, UploadMeta } from "./types";
import { api, json } from "./api";
export interface DocumentRecord {
  id: string; created_at: string; subject: string; module: string | null; source_type: "tutorial" | "pyq";
  document_version: string; processing_status: string; indexing_status: string; visibility: "public" | "private";
  question_count: number; approved_count: number; flagged_count: number; pending_count: number;
}
interface ReviewRecord {
  id: string; document_id: string; revision: number; status: string; text: string;
  subject: string | null; module: string | null; topics: string[]; difficulty: "easy" | "medium" | "hard" | null;
  source_type: "tutorial" | "pyq"; year: number | null; flag_note: string | null;
  question_asset_id: string | null; solution_asset_id: string | null; official_solution: string | null;
  solution_status: string | null; solution_document_id: string | null; document_version: string;
}
interface Page<T> { items: T[]; total: number; offset: number; limit: number }
export interface BatchListItem {
  batchId: string; uploadedAt: string; subject: string; questionCount: number; sheetType: "tutorial" | "pyq";
  approvedCount: number; flaggedCount: number; pendingCount: number;
}
export async function allPages<T>(path: string): Promise<T[]> {
  const result: T[] = []; let offset = 0;
  while (true) {
    const page = await api<Page<T>>(`${path}${path.includes("?") ? "&" : "?"}offset=${offset}&limit=100`);
    if (!Array.isArray(page.items)) throw new Error("Invalid list response from backend");
    result.push(...page.items); offset += page.items.length;
    if (offset >= page.total) return result;
    if (!page.items.length) throw new Error("The list changed while loading. Please refresh.");
  }
}
async function assetUrl(id: string | null): Promise<string> {
  return id ? `/api/assets/${encodeURIComponent(id)}` : "";
}
async function view(q: ReviewRecord): Promise<Question> {
  const [questionImageUrl, solutionImageUrl] = await Promise.all([assetUrl(q.question_asset_id), assetUrl(q.solution_asset_id)]);
  return { id: q.id, documentId: q.document_id, documentVersion: q.document_version, revision: q.revision,
    subject: q.subject || "", module: q.module || "", topics: q.topics, difficulty: q.difficulty || "unassigned",
    sheetType: q.source_type, year: q.year ?? undefined, status: q.flag_note ? "flagged" : q.status === "approved" ? "approved" : "pending",
    questionImageUrl, solutionImageUrl, flagNote: q.flag_note ?? undefined, text: q.text,
    officialSolution: q.official_solution ?? undefined, solutionStatus: q.solution_status ?? undefined,
    solutionAssetId: q.solution_asset_id, solutionDocumentId: q.solution_document_id };
}
interface Upload { id: string; upload_url: string | null; required_headers: Record<string,string>; confirmed: boolean; document_id: string | null; asset_id: string | null }
const attempts = new WeakMap<File, Map<string, { key: string; upload?: Upload; sent?: boolean }>>();
async function upload(file: File, path: string, metadata: Record<string, unknown>): Promise<Upload> {
  if (!file.size || file.size > 15 * 1024 * 1024) throw new Error("Choose a file between 1 byte and 15 MB.");
  const signature = JSON.stringify([path, metadata]);
  let map = attempts.get(file); if (!map) { map = new Map(); attempts.set(file, map); }
  let attempt = map.get(signature); if (!attempt) { attempt = { key: crypto.randomUUID() }; map.set(signature, attempt); }
  if (!attempt.upload) attempt.upload = await api<Upload>(path, json("POST", { ...metadata, filename: file.name, content_type: file.type, size_bytes: file.size, client_upload_key: attempt.key }));
  if (attempt.upload.confirmed) return attempt.upload;
  if (!attempt.sent) {
    if (!attempt.upload.upload_url) throw new Error("Upload URL unavailable. Select the file again.");
    const headers = Object.fromEntries(Object.entries(attempt.upload.required_headers).filter(([key]) => key.toLowerCase() !== "content-length"));
    const response = await fetch(attempt.upload.upload_url, { method: "PUT", headers, body: file, credentials: "omit", signal: AbortSignal.timeout(120000) });
    if (!response.ok) throw new Error(`Storage upload failed (${response.status}). Retry, or reselect the file if the upload has expired.`);
    attempt.sent = true;
  }
  return api<Upload>(`admin/uploads/${attempt.upload.id}/confirm`, json("POST", {}));
}
export async function uploadSheet(file: File, meta: UploadMeta): Promise<{ batchId: string }> {
  const result = await upload(file, "admin/uploads", { title: file.name, document_type: meta.sheetType === "pyq" ? "question_paper" : "tutorial_sheet", source_type: meta.sheetType, subject: meta.subject, module: `Module ${meta.module}`, year: meta.year, process: true });
  if (!result.document_id) throw new Error("Upload confirmation did not return a document");
  return { batchId: result.document_id };
}
export async function uploadAnswerSheet(file: File, question: Question): Promise<DocumentRecord> {
  const result = await upload(file, "admin/uploads", { title: file.name, document_type: "answer_sheet", source_type: question.sheetType, subject: question.subject, module: String(question.module) || undefined, process: false });
  if (!result.document_id) throw new Error("Answer-sheet confirmation did not return a document");
  return getDocument(result.document_id);
}
export async function uploadSolution(file: File, question: Question, source?: DocumentRecord): Promise<string> {
  const result = await upload(file, "admin/assets/uploads", { document_id: source?.id || question.documentId, document_version: source?.document_version || question.documentVersion, kind: "solution_image" });
  if (!result.asset_id) throw new Error("Solution upload did not return an asset");
  return result.asset_id;
}
export const getDocument = (id: string) => api<DocumentRecord>(`admin/documents/${encodeURIComponent(id)}`);
export async function getBatchStatus(id: string): Promise<{ status: "processing" | "ready" | "failed" }> {
  const doc = await getDocument(id);
  return { status: doc.processing_status === "succeeded" ? "ready" : doc.processing_status === "failed" ? "failed" : "processing" };
}
export async function getBatchQuestions(id: string): Promise<Question[]> {
  const rows = await allPages<ReviewRecord>(`admin/questions?document_id=${encodeURIComponent(id)}`);
  const results: Question[] = [];
  for (let i = 0; i < rows.length; i += 5) results.push(...await Promise.all(rows.slice(i, i + 5).filter(q => !["archived", "rejected"].includes(q.status)).map(view)));
  return results;
}
export async function updateQuestion(id: string, updates: Partial<Question>): Promise<Question> {
  if (!updates.revision) throw new Error("Reload this question before saving.");
  const path = `admin/questions/${encodeURIComponent(id)}`;
  if (updates.status || updates.approveSolution) return view(await api<ReviewRecord>(`${path}/review`, json("POST", {
    expected_revision: updates.revision, status: updates.status === "approved" || updates.approveSolution ? "approved" : "pending_review",
    flagged: updates.status === "flagged", note: updates.flagNote, approve_solution: updates.approveSolution ?? false,
  })));
  const body: Record<string, unknown> = { expected_revision: updates.revision };
  if (updates.subject !== undefined) body.subject = updates.subject;
  if (updates.module !== undefined) body.module = String(updates.module) || null;
  if (updates.topics !== undefined) body.topics = updates.topics;
  if (updates.difficulty !== undefined) body.difficulty = updates.difficulty === "unassigned" ? null : updates.difficulty;
  if (updates.text !== undefined) body.text = updates.text;
  if (updates.officialSolution !== undefined) body.official_solution = updates.officialSolution || null;
  if (updates.solutionDocumentId !== undefined) body.solution_document_id = updates.solutionDocumentId;
  if (updates.solutionAssetId !== undefined) body.solution_asset_id = updates.solutionAssetId;
  return view(await api<ReviewRecord>(path, json("PATCH", body)));
}
export async function listBatches(): Promise<BatchListItem[]> {
  return (await allPages<DocumentRecord>("admin/documents")).map(d => ({ batchId: d.id, uploadedAt: d.created_at, subject: d.subject || "Unassigned", questionCount: d.question_count, sheetType: d.source_type,
    approvedCount: d.approved_count, flaggedCount: d.flagged_count, pendingCount: d.pending_count }));
}
export const publishDocument = (id: string, visibility: "public" | "private") => api<DocumentRecord>(`admin/documents/${encodeURIComponent(id)}/publication`, json("POST", { visibility }));
export const classifyDocument = (doc: DocumentRecord, source: "tutorial" | "pyq") => api<DocumentRecord>(`admin/documents/${encodeURIComponent(doc.id)}/classification`, json("PATCH", { expected_source_type: doc.source_type, source_type: source }));
