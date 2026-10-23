import { searchLocal } from "./search";
import type { SearchResult, SourceFilter } from "./types";

/**
 * Single seam between UI and backend.
 * - No NEXT_PUBLIC_API_URL  -> mock (local scrubber over src/data/questions.ts)
 * - With it                 -> POST {url}/search  { query, source }  ->  SearchResult
 */
const API = process.env.NEXT_PUBLIC_API_URL;

export async function searchQuestions(query: string, source: SourceFilter): Promise<SearchResult> {
  if (!API) {
    await new Promise((r) => setTimeout(r, 650)); // feel of a real request
    return searchLocal(query, source);
  }
  const res = await fetch(`${API.replace(/\/$/, "")}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, source }),
  });
  if (!res.ok) throw new Error(`Search failed (${res.status})`);
  return res.json();
}
