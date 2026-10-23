import { QUESTIONS, SUBJECTS } from "@/data/questions";
import type { Question, SearchResult, SourceFilter } from "./types";

/**
 * Lightweight local query scrubber used by the MOCK API only.
 * Same idea as the planned backend: normalise -> tokenise -> score against
 * subject/topic/keyword vocab. No external AI calls.
 */
const STOP = new Set(
  "i want to a an the of on in for from and or me my some any questions question problems problem practice practise based about related please give show need get on with by".split(" "),
);

const SYNONYMS: Record<string, string> = {
  average: "mean",
  avg: "mean",
  sd: "standard",
  stdev: "standard",
  stats: "statistics",
  statistic: "statistics",
  prob: "probability",
  eigen: "eigenvalues",
  eigenvalue: "eigenvalues",
  eigenvector: "eigenvectors",
  derivative: "derivatives",
  partial: "partial",
  permutation: "permutations",
  combination: "combinations",
  bayes: "bayes",
  baye: "bayes",
};

export function normalise(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[’']s\b/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t && !STOP.has(t))
    .map((t) => SYNONYMS[t] ?? t);
}

const stem = (t: string) => t.replace(/(ies|es|s)$/, "");
const tokensOf = (s: string) => normalise(s).map(stem);

function score(q: Question, qTokens: string[]) {
  let s = 0;
  const hit = new Set<string>();
  for (const topic of q.topics) {
    const tt = tokensOf(topic);
    const matched = tt.filter((t) => qTokens.includes(t)).length;
    if (matched) {
      s += 3 * (matched / tt.length) * Math.max(1, tt.length > 1 ? 1.5 : 1);
      if (matched === tt.length) hit.add(topic);
    }
  }
  for (const k of q.keywords) {
    if (tokensOf(k).some((t) => qTokens.includes(t))) s += 1;
  }
  // module name is only a tie-breaker, never a reason to match on its own
  if (s > 0 && tokensOf(q.module).some((t) => qTokens.includes(t))) s += 0.5;
  return { s, hit };
}

export function searchLocal(query: string, source: SourceFilter = "all"): SearchResult {
  const allTokens = tokensOf(query);
  // subject words ("probability", "statistics"…) identify the subject but must not drive topic matches
  const subjectWords = new Set(SUBJECTS.flatMap((s) => tokensOf(s.name)));
  const qTokens = allTokens.filter((t) => !subjectWords.has(t));

  // subject detection
  let subject: string | null = null;
  let best = 0;
  for (const sub of SUBJECTS) {
    const st = tokensOf(sub.name);
    const n = st.filter((t) => allTokens.includes(t)).length + (allTokens.includes(sub.short.toLowerCase()) ? 1 : 0);
    if (n > best) {
      best = n;
      subject = sub.name;
    }
  }

  const topics = new Set<string>();
  const ranked = QUESTIONS.filter((q) => source === "all" || q.source.type === source)
    .map((q) => {
      const { s, hit } = score(q, qTokens);
      const inSubject = subject && q.subject === subject ? 1 : 0;
      return { q, s: s ? s + inSubject : 0, hit };
    })
    .filter((r) => r.s >= 1)
    .sort((a, b) => b.s - a.s);

  // Subject named but no topic: return that subject's whole bank.
  if (!ranked.length && subject) {
    const all = QUESTIONS.filter((q) => q.subject === subject && (source === "all" || q.source.type === source));
    return { subject, topics: [], questions: all };
  }

  ranked.forEach((r) => r.hit.forEach((t) => topics.add(t)));
  if (!subject && ranked[0]) subject = ranked[0].q.subject;

  return { subject, topics: [...topics], questions: ranked.map((r) => r.q) };
}
