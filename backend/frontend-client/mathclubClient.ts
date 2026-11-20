/** Browser-facing TypeScript reference; no secrets embedded. Prefer auth gateway/cookie sessions. */
export type SourceType = "tutorial" | "pyq" | "practice";
export type ExplanationLevel = "beginner" | "standard" | "advanced";
export interface SearchFilters {
  subject?: string | null;
  module?: string | null;
  topic?: string | null;
  year?: number | null;
  source_type?: SourceType | null;
}
export interface SourceReference {
  source_type: SourceType;
  document_id: string | null;
  document_title: string | null;
  page_number: number | null;
  question_number: string | null;
  year: number | null;
}
export interface Question {
  id: string;
  text: string;
  subject: string;
  module: string | null;
  topic: string | null;
  source: SourceReference;
  official_solution: string | null;
  image_url: string | null;
}
export interface SearchHit { question: Question; relevance_score: number | null }
export interface SearchResponse { items: SearchHit[]; total: number; request_id: string; captured: boolean }
export interface Citation { question_id: string; source: SourceReference }
export interface AskRequest {
  query?: string;
  question_id?: string;
  filters?: SearchFilters;
  limit?: number;
  explanation_level?: ExplanationLevel;
}
export interface AskResponse {
  status: "answered" | "no_matches";
  answer: string | null;
  citations: Citation[];
  matched_questions: SearchHit[];
  request_id: string;
  captured: boolean;
}
export interface ExplainResponse {
  answer: string;
  citations: Citation[];
  request_id: string;
  captured: boolean;
}
export interface SimilarResponse { items: SearchHit[]; request_id: string }

export interface CatalogResponse { combinations: SearchFilters[]; request_id: string }
export interface Capabilities {
  mode: "demo" | "http" | "unconfigured";
  features: string[];
  query_capture_required: boolean;
  capture_configured: boolean;
  document_orchestration_configured: boolean;
  contract_version: string;
}
export interface ClientOptions { credentials?: RequestCredentials; timeoutMs?: number }
export interface RequestOptions { signal?: AbortSignal }
export interface ValidationDetail { location: (string | number)[]; type: string; message: string }

export class MathClubAPIError extends Error {
  constructor(public status: number, public requestId: string | null, message: string,
              public code = "HTTP_ERROR", public details: ValidationDetail[] = [],
              public retryAfter: number | null = null) {
    super(message);
    this.name = "MathClubAPIError";
  }
}

/** Use a same-origin authenticated gateway in production. Never bundle service keys. */
export class MathClubClient {
  constructor(private baseUrl: string, private extraHeaders: () => Record<string, string> = () => ({}),
              private options: ClientOptions = {}) {}

  private async fetchJSON<T>(path: string, method = "GET", body?: object,
                             request: RequestOptions = {}): Promise<T> {
    const controller = new AbortController();
    let timedOut = false;
    const abort = () => controller.abort();
    if (request.signal?.aborted) controller.abort();
    request.signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, this.options.timeoutMs ?? 50000);
    try {
      const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
        method,
        credentials: this.options.credentials ?? "same-origin",
        signal: controller.signal,
        headers: { ...this.extraHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      const data = await response.json().catch(() => null);
      const requestId = response.headers.get("X-Request-ID") ?? data?.request_id ?? null;
      if (!response.ok) {
        const retry = response.headers.get("Retry-After");
        throw new MathClubAPIError(response.status, requestId,
          typeof data?.message === "string" ? data.message : `Request failed (${response.status})`,
          data?.error ?? "HTTP_ERROR", Array.isArray(data?.details) ? data.details : [],
          retry !== null && Number.isFinite(Number(retry)) ? Number(retry) : null);
      }
      if (data === null || typeof data !== "object" || Array.isArray(data)) {
        throw new MathClubAPIError(response.status, requestId, "Server returned an invalid response", "INVALID_RESPONSE");
      }
      return data as T; // Full shape validation is enforced by the API's response models.
    } catch (error) {
      if (error instanceof MathClubAPIError) throw error;
      if (controller.signal.aborted) {
        throw new MathClubAPIError(0, null, timedOut ? "Request timed out" : "Request cancelled",
                                  timedOut ? "TIMEOUT" : "CANCELLED");
      }
      throw new MathClubAPIError(0, null, "Could not reach MathClub", "NETWORK_ERROR");
    } finally {
      clearTimeout(timer);
      request.signal?.removeEventListener("abort", abort);
    }
  }

  catalog(options?: RequestOptions) {
    return this.fetchJSON<CatalogResponse>("/api/v1/catalog", "GET", undefined, options);
  }
  capabilities(options?: RequestOptions) {
    return this.fetchJSON<Capabilities>("/api/v1/capabilities", "GET", undefined, options);
  }
  search(query: string, filters: SearchFilters = {}, limit = 5, options?: RequestOptions) {
    return this.fetchJSON<SearchResponse>("/api/v1/search", "POST", { query, filters, limit }, options);
  }
  ask(payload: AskRequest, options?: RequestOptions) {
    return this.fetchJSON<AskResponse>("/api/v1/ask", "POST", payload, options);
  }
  getQuestion(id: string, options?: RequestOptions) {
    return this.fetchJSON<Question>(`/api/v1/questions/${encodeURIComponent(id)}`, "GET", undefined, options);
  }
  similar(id: string, limit = 5, options?: RequestOptions) {
    return this.fetchJSON<SimilarResponse>(`/api/v1/questions/${encodeURIComponent(id)}/similar?limit=${limit}`,
                                          "GET", undefined, options);
  }
  explain(id: string, instruction?: string, explanation_level: ExplanationLevel = "standard", options?: RequestOptions) {
    return this.fetchJSON<ExplainResponse>(`/api/v1/questions/${encodeURIComponent(id)}/explain`,
                                           "POST", { instruction, explanation_level }, options);
  }
}
