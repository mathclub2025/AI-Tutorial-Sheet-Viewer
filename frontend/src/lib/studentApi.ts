import { z } from "zod";
import { api, json } from "./api";
import type { SearchResult, SourceFilter, Question } from "./studentTypes";
const questionSchema = z.object({
  id: z.string(), text: z.string(), subject: z.string(), module: z.string().nullable().optional(),
  topic: z.string().nullable().optional(), topics: z.array(z.string()).default([]),
  difficulty: z.enum(["easy", "medium", "hard"]).nullable().optional(), marks: z.number().nullable().optional(),
  official_solution: z.string().nullable().optional(),
  source: z.object({ source_type: z.enum(["tutorial", "pyq", "practice"]), document_title: z.string().nullable().optional(), year: z.number().nullable().optional() }),
});
function view(q: z.infer<typeof questionSchema>): Question {
  const type = q.source.source_type === "tutorial" ? "Tutorial" : q.source.source_type === "pyq" ? "PYQ" : "Practice";
  return { id: q.id, subject: q.subject, module: q.module || "", topics: q.topics.length ? q.topics : q.topic ? [q.topic] : [], keywords: [],
    source: { type, label: q.source.document_title || type, year: q.source.year ?? undefined },
    difficulty: q.difficulty ? ({ easy: "Easy", medium: "Medium", hard: "Hard" } as const)[q.difficulty] : undefined,
    marks: q.marks ?? undefined, text: [q.text], steps: [], answer: q.official_solution || "An approved solution is not available yet." };
}
export async function searchQuestions(query: string, source: SourceFilter): Promise<SearchResult> {
  if (query.trim().length < 3 || query.length > 2000) throw new Error("Enter between 3 and 2000 characters.");
  const mode = process.env.NEXT_PUBLIC_SEARCH_MODE === "semantic" ? "search/semantic" : "search";
  const filters = source === "all" ? {} : { source_type: source.toLowerCase() };
  const data = z.object({ items: z.array(z.object({ question: questionSchema })) }).parse(await api(mode, json("POST", { query: query.trim(), filters, limit: 20 })));
  const questions = data.items.map(hit => view(hit.question));
  const subjects = [...new Set(questions.map(q => q.subject))];
  return { questions, subject: subjects.length === 1 ? subjects[0] : null, topics: [...new Set(questions.flatMap(q => q.topics))] };
}
export async function refreshQuestion(id: string): Promise<{ question: Question; expires: number }> {
  const q = view(questionSchema.parse(await api(`questions/${encodeURIComponent(id)}`)));
  const assets = z.object({ question_image_url: z.string().nullable(), solution_image_url: z.string().nullable(), expires_in_seconds: z.number() }).parse(await api(`questions/${encodeURIComponent(id)}/assets`));
  return { question: { ...q, imageUrl: assets.question_image_url || undefined, solutionImageUrl: assets.solution_image_url || undefined }, expires: assets.expires_in_seconds };
}
