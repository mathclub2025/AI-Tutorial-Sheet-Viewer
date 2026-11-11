"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, json, messageOf } from "@/lib/api";
export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  return <div className="min-h-screen flex items-center justify-center p-4"><Card className="w-full max-w-sm rounded-xl border-white/[0.08] bg-[#121215]/90">
    <CardHeader><CardTitle className="font-serif-heading text-xl text-white">Admin Portal</CardTitle></CardHeader>
    <CardContent><form className="space-y-4" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(""); try { await api("auth/login", json("POST", { email, password })); router.replace("/admin/upload"); } catch(e) { setError(messageOf(e)); } finally { setBusy(false); } }}>
      <label className="block text-sm">Email<Input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label className="block text-sm">Password<Input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <Button type="submit" disabled={busy} className="w-full">{busy ? "Signing in…" : "Sign in"}</Button>
      <Link href="/student" className="block text-center text-xs text-zinc-400">Back to Student Portal</Link>
    </form></CardContent></Card></div>;
}
