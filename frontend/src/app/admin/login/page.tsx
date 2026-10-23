"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Compass, ArrowRight } from "lucide-react";

export default function AdminLoginPage() {
  const router = useRouter();

  React.useEffect(() => {
    localStorage.setItem("admin_authed", "true");
    document.cookie = "admin_authed=true; path=/; max-age=86400";
    router.replace("/admin/upload");
  }, [router]);

  return (
    <div className="min-h-screen bg-transparent relative flex items-center justify-center p-4">
      <Card className="w-full max-w-sm rounded-xl border border-white/[0.08] bg-[#121215]/90 backdrop-blur-md shadow-2xl shadow-black/60">
        <CardHeader className="space-y-3 text-center pb-2 pt-6 px-6">
          <div className="mx-auto w-10 h-10 rounded-lg bg-zinc-800/80 border border-white/[0.1] flex items-center justify-center text-zinc-200 shadow-sm">
            <Compass className="h-5 w-5 text-zinc-200" />
          </div>
          <div>
            <CardTitle className="font-serif-heading text-xl font-bold tracking-tight text-zinc-100">
              Admin Portal
            </CardTitle>
            <p className="text-xs text-zinc-400 mt-1 leading-relaxed">
              Login requirement is disabled. Direct access is enabled.
            </p>
          </div>
        </CardHeader>

        <CardContent className="pt-2 pb-6 px-6 space-y-4">
          <Link href="/admin/upload" className="block w-full">
            <Button
              className="w-full h-10 bg-[#F4F0EA] hover:bg-white text-[#0A0A0C] font-semibold text-sm rounded-lg transition-colors cursor-pointer shadow-sm border-0 inline-flex items-center justify-center gap-2"
            >
              <span>Go to Admin Desk</span>
              <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>

          <div className="pt-2 text-center">
            <Link
              href="/"
              className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors inline-flex items-center gap-1.5 cursor-pointer"
            >
              <span>&larr;</span> Back to Portal Selection
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
