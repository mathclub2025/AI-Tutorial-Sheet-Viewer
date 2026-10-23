"use client";

import * as React from "react";
import { User } from "lucide-react";

export function AdminHeader() {
  return (
    <header className="h-14 border-b border-white/[0.07] bg-[#0D0D10]/90 backdrop-blur-md px-6 lg:px-8 hidden md:flex items-center justify-end sticky top-0 z-20">
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/80 border border-white/[0.08] flex items-center justify-center text-zinc-200 shadow-2xs">
          <User className="h-4 w-4 text-zinc-200" />
        </div>
        <div className="text-left text-xs">
          <span className="block font-semibold text-white">Admin</span>
          <span className="block text-[11px] text-zinc-400">Maths Club</span>
        </div>
      </div>
    </header>
  );
}


export default AdminHeader;

