"use client";

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import {
  BookOpen,
  Layers,
  ArrowRight,
  Check,
  Compass,
  FileText,
} from "lucide-react";

export default function RoleSelectionPage() {
  // Ensure the page renders in the dark graphite theme matching the Mathematics Club aesthetic
  React.useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  return (
    <div className="relative min-h-screen bg-transparent text-[#F4F0EA] flex flex-col font-sans selection:bg-[#E2B86B]/20 selection:text-[#F4F0EA]">
      {/* 1. Header Bar */}
      <header className="sticky top-0 z-20 border-b border-white/[0.07] bg-[#0D0D10]/80 backdrop-blur-md px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-zinc-800/80 border border-white/[0.1] p-1 flex items-center justify-center shrink-0">
              <Image
                src="/logo.png"
                alt="Mathematics Club Logo"
                width={32}
                height={32}
                priority
                className="object-contain"
              />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-tight text-white block leading-tight">
                Mathematics Club
              </span>
              <span className="text-xs text-zinc-400 block">VIT Chennai</span>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-2">
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs text-zinc-400 bg-white/[0.04] border border-white/[0.08]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#E2B86B]" />
              School of Advanced Sciences
            </span>
          </div>
        </div>
      </header>

      {/* 2. Main Hero & Portal Options */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-12 sm:py-16 md:py-20 flex flex-col justify-center">
        {/* Editorial Heading */}
        <div className="text-center max-w-2xl mx-auto mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium text-[#E2B86B] bg-[#E2B86B]/10 border border-[#E2B86B]/25 mb-4">
            <Compass className="w-3.5 h-3.5" />
            <span>Academic Portal Gateway</span>
          </div>

          <h1 className="font-serif-heading text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-[#F4F0EA] leading-tight">
            Select Your Portal
          </h1>

          <p className="mt-4 text-sm sm:text-base text-zinc-400 leading-relaxed max-w-xl mx-auto">
            Choose your workspace to begin. Access interactive practice tutorial sheets or manage question ingestion and batch reviews.
          </p>
        </div>

        {/* Two Balanced Portal Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8 max-w-4xl mx-auto w-full">
          {/* Card 1: Student Portal */}
          <Link
            href="/student"
            className="group relative flex flex-col justify-between rounded-2xl border border-white/[0.08] bg-[#121215]/85 backdrop-blur-md p-7 sm:p-8 transition-all duration-200 hover:border-[#3FB0BA]/50 hover:bg-[#16161A]/95 hover:shadow-2xl hover:shadow-black/60 cursor-pointer overflow-hidden"
          >
            {/* Subtle Mathematical Wave Line Art Motif */}
            <div
              aria-hidden="true"
              className="absolute -right-8 -bottom-8 w-48 h-48 opacity-[0.04] group-hover:opacity-[0.08] transition-opacity pointer-events-none text-[#3FB0BA]"
            >
              <svg viewBox="0 0 200 200" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M 0,100 C 50,40 100,160 150,100 C 200,40 250,160 300,100" />
                <path d="M 0,120 C 50,60 100,180 150,120 C 200,60 250,180 300,120" />
                <path d="M 0,80 C 50,20 100,140 150,80 C 200,20 250,140 300,80" />
              </svg>
            </div>

            <div>
              {/* Header Badge & Icon */}
              <div className="flex items-start justify-between mb-6">
                <div className="w-12 h-12 rounded-xl bg-[#172d34]/70 border border-[#3FB0BA]/30 flex items-center justify-center text-[#3FB0BA] group-hover:scale-105 transition-transform shadow-xs">
                  <BookOpen className="w-6 h-6" />
                </div>
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium text-[#3FB0BA] bg-[#1F6F78]/20 border border-[#3FB0BA]/25">
                  Practice & PYQs
                </span>
              </div>

              {/* Title & Body */}
              <h2 className="font-serif-heading text-xl sm:text-2xl font-bold text-[#F4F0EA] group-hover:text-white transition-colors">
                Student Portal
              </h2>

              <p className="mt-2.5 text-sm text-zinc-400 leading-relaxed">
                Topic-wise practice questions from verified tutorial sheets and past papers. Includes step-by-step solution reveals, formula tables, and study progress tracking.
              </p>

              {/* Feature Points */}
              <ul className="mt-6 space-y-2.5 text-xs text-zinc-300 border-t border-white/[0.07] pt-5">
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-[#1F6F78]/30 flex items-center justify-center text-[#3FB0BA] shrink-0">
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Natural language topic search across subjects</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-[#1F6F78]/30 flex items-center justify-center text-[#3FB0BA] shrink-0">
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Step-by-step solution reveals with tables</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-[#1F6F78]/30 flex items-center justify-center text-[#3FB0BA] shrink-0">
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Offline bookmarking, projects & JSON export</span>
                </li>
              </ul>
            </div>

            {/* Action Button */}
            <div className="mt-8 pt-4">
              <span className="w-full inline-flex items-center justify-center gap-2 py-3 px-5 rounded-lg text-sm font-semibold bg-white/[0.06] border border-white/[0.12] text-[#F4F0EA] group-hover:bg-[#172d34] group-hover:border-[#3FB0BA]/40 group-hover:text-white transition-all">
                <span>Open Student Portal</span>
                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform text-[#3FB0BA]" />
              </span>
            </div>
          </Link>

          {/* Card 2: Admin Portal */}
          <Link
            href="/admin/upload"
            className="group relative flex flex-col justify-between rounded-2xl border border-white/[0.08] bg-[#121215]/85 backdrop-blur-md p-7 sm:p-8 transition-all duration-200 hover:border-[#E2B86B]/50 hover:bg-[#16161A]/95 hover:shadow-2xl hover:shadow-black/60 cursor-pointer overflow-hidden"
          >
            {/* Subtle Mathematical Coordinate / Matrix Motif */}
            <div
              aria-hidden="true"
              className="absolute -right-8 -bottom-8 w-48 h-48 opacity-[0.04] group-hover:opacity-[0.08] transition-opacity pointer-events-none text-[#E2B86B]"
            >
              <svg viewBox="0 0 200 200" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="100" cy="100" r="80" strokeDasharray="4 4" />
                <circle cx="100" cy="100" r="50" />
                <line x1="20" y1="100" x2="180" y2="100" />
                <line x1="100" y1="20" x2="100" y2="180" />
              </svg>
            </div>

            <div>
              {/* Header Badge & Icon */}
              <div className="flex items-start justify-between mb-6">
                <div className="w-12 h-12 rounded-xl bg-amber-950/40 border border-[#E2B86B]/30 flex items-center justify-center text-[#E2B86B] group-hover:scale-105 transition-transform shadow-xs">
                  <Layers className="w-6 h-6" />
                </div>
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium text-[#E2B86B] bg-amber-950/40 border border-[#E2B86B]/25">
                  Direct Access · No Login
                </span>
              </div>

              {/* Title & Body */}
              <h2 className="font-serif-heading text-xl sm:text-2xl font-bold text-[#F4F0EA] group-hover:text-white transition-colors">
                Admin Portal
              </h2>

              <p className="mt-2.5 text-sm text-zinc-400 leading-relaxed">
                Ingest question sheets, inspect extracted problems and solutions, calibrate topic tags, and manage batch approvals or flags directly.
              </p>

              {/* Feature Points */}
              <ul className="mt-6 space-y-2.5 text-xs text-zinc-300 border-t border-white/[0.07] pt-5">
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-amber-950/50 flex items-center justify-center text-[#E2B86B] shrink-0">
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Question sheet upload dropzone (PDF & Images)</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-amber-950/50 flex items-center justify-center text-[#E2B86B] shrink-0">
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Question review, formula editing & topic tagging</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="w-4 h-4 rounded-full bg-amber-950/50 flex items-center justify-center text-[#E2B86B] shrink-0">
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Direct workspace access without password gate</span>
                </li>
              </ul>
            </div>

            {/* Action Button */}
            <div className="mt-8 pt-4">
              <span className="w-full inline-flex items-center justify-center gap-2 py-3 px-5 rounded-lg text-sm font-semibold bg-[#E2B86B] text-[#0A0A0C] hover:bg-[#F0C97E] transition-all shadow-sm">
                <span>Open Admin Desk</span>
                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </span>
            </div>
          </Link>
        </div>
      </main>

      {/* 3. Footer */}
      <footer className="border-t border-white/[0.07] bg-[#0A0A0C]/90 py-6 px-6 text-center text-xs text-zinc-500">
        <p>Mathematics Club · School of Advanced Sciences · VIT Chennai</p>
      </footer>
    </div>
  );
}
