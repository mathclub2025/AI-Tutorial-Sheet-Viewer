export class ApiError extends Error {
  constructor(message: string, public status: number, public requestId?: string) { super(message); }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/backend/${path}`, { ...options, cache: "no-store", credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...options.headers }, signal: options.signal ?? AbortSignal.timeout(65000) });
  } catch (e) { if (e instanceof Error && e.name === "AbortError") throw e; throw new ApiError("Connection failed or timed out. Please try again.", 0); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && (path.startsWith("admin/") || path === "auth/me")) window.dispatchEvent(new Event("mathclub-session-expired"));
    throw new ApiError(data.message || `Request failed (${response.status})`, response.status, data.request_id);
  }
  return data as T;
}
export const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });
export const messageOf = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";
export interface Staff { id: string; name: string; email: string; role: "admin" | "reviewer" | "uploader" }
