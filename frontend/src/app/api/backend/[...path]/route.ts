import { NextRequest, NextResponse } from "next/server";

const COOKIE = "mathclub_session";
const rules: Record<string, RegExp[]> = {
  GET: [/^auth\/me$/, /^catalog$/, /^questions\/[\w.:-]+(?:\/(?:assets|similar))?$/, /^admin\/documents(?:\/[\w.:-]+(?:\/(?:processing-jobs|download))?)?$/, /^admin\/questions(?:\/[\w.:-]+)?$/, /^admin\/assets\/[\w-]+\/download$/],
  POST: [/^auth\/(?:login|logout)$/, /^search(?:\/semantic)?$/, /^ask$/, /^questions\/[\w.:-]+\/explain$/, /^admin\/(?:uploads|assets\/uploads)$/, /^admin\/uploads\/[\w-]+\/confirm$/, /^admin\/questions\/[\w.:-]+\/(?:review|reindex)$/, /^admin\/documents\/[\w.:-]+\/(?:publication|process)$/],
  PATCH: [/^admin\/questions\/[\w.:-]+$/, /^admin\/documents\/[\w.:-]+\/classification$/],
};
function error(message: string, status: number) {
  return NextResponse.json({ message }, { status, headers: { "Cache-Control": "no-store" } });
}
async function relay(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const path = (await ctx.params).path.join("/");
  if (!rules[request.method]?.some(r => r.test(path))) return error("Operation not available", 404);
  const origin = process.env.WEBSITE_ORIGIN || request.nextUrl.origin;
  if (request.method !== "GET" && request.headers.get("origin") !== origin) return error("Request origin is not allowed", 403);
  const base = process.env.BACKEND_URL;
  if (!base) return error("The website backend has not been configured", 503);
  const staff = path.startsWith("auth/") || path.startsWith("admin/");
  const login = path === "auth/login";
  const token = request.cookies.get(COOKIE)?.value;
  if (staff && !login && !token) return error("Sign in to continue", 401);
  if (!staff && !process.env.BACKEND_API_KEY) return error("Student search is not configured", 503);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (staff && token) headers.Authorization = `Bearer ${token}`;
  if (!staff) headers["X-API-Key"] = process.env.BACKEND_API_KEY!;
  let body: string | undefined;
  if (request.method !== "GET") {
    if (!request.headers.get("content-type")?.startsWith("application/json")) return error("Send JSON metadata; upload files directly to storage", 415);
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = []; let size = 0;
    if (reader) while (true) {
      const part = await reader.read(); if (part.done) break;
      size += part.value.length;
      if (size > 65536) { await reader.cancel(); return error("Request is too large", 413); }
      chunks.push(part.value);
    }
    body = Buffer.concat(chunks).toString("utf8");
    try { JSON.parse(body || "{}"); } catch { return error("Invalid JSON", 400); }
  }
  try {
    const upstream = await fetch(`${base.replace(/\/$/, "")}/api/v1/${path}${request.nextUrl.search}`, {
      method: request.method, headers, body, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(60000),
    });
    const data = await upstream.json();
    if (login && upstream.ok && (typeof data.access_token !== "string" || !Number.isFinite(Date.parse(data.expires_at)))) return error("Invalid login response", 502);
    const response = NextResponse.json(login && upstream.ok ? { user: data.user, expires_at: data.expires_at } : data, {
      status: upstream.status, headers: { "Cache-Control": "no-store" },
    });
    for (const name of ["x-request-id", "retry-after"]) { const value = upstream.headers.get(name); if (value) response.headers.set(name, value); }
    if (login && upstream.ok) response.cookies.set(COOKIE, data.access_token, {
      httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", expires: new Date(data.expires_at),
    });
    if (path === "auth/logout" && upstream.ok || staff && !login && upstream.status === 401) response.cookies.delete(COOKIE);
    return response;
  } catch { return error("The backend is unavailable or timed out. Please try again.", 503); }
}
export const GET = relay;
export const POST = relay;
export const PATCH = relay;
