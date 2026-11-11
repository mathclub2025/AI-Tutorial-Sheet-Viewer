import { NextRequest, NextResponse } from "next/server";
export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[a-f0-9-]{36}$/i.test(id)) return new NextResponse(null, { status: 404 });
  const token = request.cookies.get("mathclub_session")?.value;
  if (!token) return new NextResponse(null, { status: 401 });
  const base = process.env.BACKEND_URL;
  if (!base) return new NextResponse(null, { status: 503 });
  try {
    const upstream = await fetch(`${base.replace(/\/$/, "")}/api/v1/admin/assets/${id}/download`, {
      headers: { Authorization: `Bearer ${token}` }, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(30000),
    });
    if (!upstream.ok) return new NextResponse(null, { status: upstream.status });
    const data = await upstream.json(); const target = new URL(data.url);
    if (!["http:", "https:"].includes(target.protocol) || target.username || target.password) return new NextResponse(null, {status:502});
    const response = NextResponse.redirect(target, 307);
    response.headers.set("Cache-Control", "private, no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    return response;
  } catch { return new NextResponse(null, {status:503}); }
}
