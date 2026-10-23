"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { Question } from "@/lib/types";
import { getBatchQuestions, updateQuestion } from "@/lib/adminApi";
import { QuestionReviewCard } from "@/components/admin/QuestionReviewCard";
import { AdminAuthGuard } from "@/components/admin/AdminAuthGuard";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { AlertCircle, RotateCcw, ArrowLeft, Layers } from "lucide-react";

type FilterType = "all" | "pending" | "approved" | "flagged";

function ReviewBatchContent() {
  const params = useParams();
  const batchId =
    typeof params?.batchId === "string"
      ? params.batchId
      : Array.isArray(params?.batchId)
      ? params.batchId[0]
      : "";

  const [questions, setQuestions] = React.useState<Question[]>([]);
  const [isLoading, setIsLoading] = React.useState<boolean>(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [activeFilter, setActiveFilter] = React.useState<FilterType>("all");

  const loadQuestions = React.useCallback(async () => {
    if (!batchId) return;
    setIsLoading(true);
    setLoadError(null);

    try {
      const data = await getBatchQuestions(batchId);
      setQuestions(data);
    } catch (error) {
      console.error("Failed to fetch questions:", error);
      setLoadError("Failed to load questions for this batch.");
    } finally {
      setIsLoading(false);
    }
  }, [batchId]);

  React.useEffect(() => {
    loadQuestions();
  }, [loadQuestions]);

  const handleUpdate = async (id: string, updates: Partial<Question>) => {
    const previousQuestions = questions;

    setQuestions((prevQuestions) =>
      prevQuestions.map((q) => (q.id === id ? { ...q, ...updates } : q))
    );

    try {
      const persistedQuestion = await updateQuestion(id, updates);
      setQuestions((prevQuestions) =>
        prevQuestions.map((q) => (q.id === id ? persistedQuestion : q))
      );
    } catch (error) {
      console.error("Failed to update question in mock API:", error);
      setQuestions(previousQuestions);
      toast.error("Failed to save changes. Reverting to previous state.");
    }
  };

  const filteredQuestions =
    activeFilter === "all"
      ? questions
      : questions.filter((question) => question.status === activeFilter);

  const filterOptions: { label: string; value: FilterType }[] = [
    { label: "All Questions", value: "all" },
    { label: "Pending", value: "pending" },
    { label: "Approved", value: "approved" },
    { label: "Flagged", value: "flagged" },
  ];

  if (isLoading) {
    return (
      <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0">
        <div className="max-w-4xl mx-auto space-y-4">
          <div className="h-4 w-32 bg-zinc-800/80 rounded animate-pulse" />
          <div className="h-8 w-64 bg-zinc-800/80 rounded animate-pulse" />
          <div className="space-y-4 pt-4">
            {[1, 2].map((i) => (
              <div key={i} className="h-72 bg-[#121215]/90 rounded-xl border border-white/[0.08] animate-pulse" />
            ))}
          </div>
        </div>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0">
        <div className="max-w-4xl mx-auto space-y-4">
          <div className="flex items-center gap-2">
            <Link
              href="/admin/review"
              className="text-xs text-zinc-400 hover:text-zinc-100 inline-flex items-center gap-1 font-medium transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back to Batches</span>
            </Link>
          </div>
          <div className="p-5 rounded-xl bg-rose-950/60 border border-rose-800/80 text-rose-300 space-y-3 backdrop-blur-sm shadow-2xl shadow-black/60">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-rose-400 shrink-0" />
              <p className="text-sm font-semibold text-rose-200">{loadError}</p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={loadQuestions}
              className="text-xs h-8 bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700 hover:text-white rounded-md cursor-pointer"
            >
              <RotateCcw className="h-3.5 w-3.5 mr-1" />
              Retry
            </Button>
          </div>
        </div>
      </main>
    );
  }

  const batchSubject = questions[0]?.subject || "Academic Question Batch";

  return (
    <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0">
      <div className="max-w-4xl mx-auto space-y-6 sm:space-y-8">
        {/* Header with Breadcrumb & Title */}
        <div className="space-y-2 border-b border-white/[0.08] pb-5">
          <div className="flex items-center gap-2 pb-1 text-xs font-medium text-zinc-400">
            <Link
              href="/admin/review"
              className="hover:text-[#F3CE85] inline-flex items-center gap-1.5 transition-colors font-medium text-zinc-400"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Review Queue</span>
            </Link>
            <span className="text-zinc-600">/</span>
            <span className="font-mono text-zinc-200 bg-zinc-800/90 border border-zinc-700/80 px-2 py-0.5 rounded text-xs font-semibold shadow-sm">
              {batchId}
            </span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-3 pt-1">
            <div>
              <h1 className="font-serif-heading text-2xl sm:text-3xl text-zinc-100 font-bold tracking-tight">
                {batchSubject}
              </h1>
              <p className="text-sm text-zinc-400 mt-1 leading-relaxed">
                Review problem statements, verify mathematical segmentations, inspect paired solution working, and adjust topics.
              </p>
            </div>

            <div className="text-xs text-zinc-400 font-medium shrink-0">
              <span className="text-zinc-100 font-mono font-bold">{questions.length}</span> questions in batch
            </div>
          </div>
        </div>

        {/* Filter Segmented Pills */}
        <div className="flex flex-wrap items-center gap-1.5 bg-[#121215]/90 backdrop-blur-md border border-white/[0.08] p-1.5 rounded-xl w-fit shadow-2xl shadow-black/60">
          {filterOptions.map((option) => {
            const isSelected = activeFilter === option.value;
            const count =
              option.value === "all"
                ? questions.length
                : questions.filter((q) => q.status === option.value).length;

            return (
              <button
                key={option.value}
                type="button"
                onClick={() => setActiveFilter(option.value)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  isSelected
                    ? "bg-[#F4F0EA] text-[#0A0A0C] font-semibold shadow-sm"
                    : "text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04]"
                }`}
              >
                <span>{option.label}</span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                    isSelected
                      ? "bg-black/10 text-[#0A0A0C] font-semibold"
                      : "bg-zinc-800 border border-white/[0.08] text-zinc-300 shadow-sm"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Question Cards or Empty Category Text */}
        {questions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/[0.15] bg-[#121215]/60 backdrop-blur-md p-8 sm:p-12 text-center space-y-3 shadow-2xl shadow-black/60">
            <div className="mx-auto w-10 h-10 rounded-lg bg-zinc-800/80 text-zinc-300 flex items-center justify-center border border-white/[0.1]">
              <Layers className="h-5 w-5" />
            </div>
            <p className="text-sm font-semibold text-zinc-100">
              No questions found for this batch.
            </p>
            <Link href="/admin/review">
              <Button size="sm" variant="outline" className="text-xs rounded-lg border-white/[0.15] text-zinc-200 bg-zinc-800/90 hover:bg-zinc-700 hover:text-white">
                Return to Batches
              </Button>
            </Link>
          </div>
        ) : filteredQuestions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/[0.12] bg-[#121215]/60 backdrop-blur-md p-8 text-center text-xs text-zinc-400 shadow-2xl shadow-black/60">
            No questions currently match the &ldquo;{activeFilter}&rdquo; filter status.
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {filteredQuestions.map((question) => (
              <QuestionReviewCard
                key={question.id}
                question={question}
                onUpdate={handleUpdate}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}


export default function ReviewBatchPage() {
  return (
    <AdminAuthGuard>
      <React.Suspense
        fallback={
          <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0">
            <div className="max-w-4xl mx-auto">
              <p className="text-[#626A76] text-sm">Loading questions...</p>
            </div>
          </main>
        }
      >
        <ReviewBatchContent />
      </React.Suspense>
    </AdminAuthGuard>
  );
}
