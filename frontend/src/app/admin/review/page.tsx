"use client";

import * as React from "react";
import Link from "next/link";
import {
  listBatches,
  getBatchQuestions,
  type BatchListItem,
} from "@/lib/adminApi";
import type { Question } from "@/lib/types";
import { AdminAuthGuard } from "@/components/admin/AdminAuthGuard";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Search,
  X,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  ArrowRight,
  Upload,
  Calendar,
  SearchX,
  RotateCcw,
  Filter,
} from "lucide-react";

type SheetTypeFilter = "all" | "tutorial" | "pyq";
type StatusFilter = "all" | "pending" | "in_review" | "completed";

export default function ReviewBatchesPage() {
  const [batches, setBatches] = React.useState<BatchListItem[]>([]);
  const [batchQuestionsMap, setBatchQuestionsMap] = React.useState<
    Record<string, Question[]>
  >({});
  const [isLoading, setIsLoading] = React.useState<boolean>(true);

  // Filter states
  const [searchQuery, setSearchQuery] = React.useState<string>("");
  const [sheetTypeFilter, setSheetTypeFilter] =
    React.useState<SheetTypeFilter>("all");
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");

  React.useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    listBatches()
      .then(async (data) => {
        if (!isMounted) return;
        setBatches(data);

        // Fetch question details for each batch to get exact question status records
        try {
          const questionPairs = await Promise.all(
            data.map(async (batch) => {
              try {
                const qs = await getBatchQuestions(batch.batchId);
                return [batch.batchId, qs] as const;
              } catch {
                return [batch.batchId, []] as const;
              }
            })
          );
          if (isMounted) {
            setBatchQuestionsMap(Object.fromEntries(questionPairs));
            setIsLoading(false);
          }
        } catch (err) {
          console.error("Failed to fetch batch questions:", err);
          if (isMounted) {
            setIsLoading(false);
          }
        }
      })
      .catch((err) => {
        console.error("Failed to list batches:", err);
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  /**
   * Explicit Review Progress & Status Definitions:
   * - "Reviewed" = approved + flagged
   * - "Pending" = awaiting admin action
   */
  const batchMetrics = React.useMemo(() => {
    const map: Record<
      string,
      {
        total: number;
        approved: number;
        flagged: number;
        reviewed: number;
        pending: number;
        progressPercent: number;
        status: "pending" | "in_review" | "completed";
      }
    > = {};

    batches.forEach((batch) => {
      const qs = batchQuestionsMap[batch.batchId] || [];
      const total = qs.length;
      const approved = qs.filter((q) => q.status === "approved").length;
      const flagged = qs.filter((q) => q.status === "flagged").length;
      const reviewed = approved + flagged;
      const pending = qs.filter((q) => q.status === "pending").length;

      const progressPercent =
        total > 0 ? Math.min(100, Math.round((reviewed / total) * 100)) : 0;

      let status: "pending" | "in_review" | "completed";
      if (total > 0 && reviewed === total) {
        status = "completed";
      } else if (reviewed > 0) {
        status = "in_review";
      } else {
        status = "pending";
      }

      map[batch.batchId] = {
        total,
        approved,
        flagged,
        reviewed,
        pending,
        progressPercent,
        status,
      };
    });

    return map;
  }, [batches, batchQuestionsMap]);

  // Aggregate global counts
  const { totalQuestions, approvedCount, flaggedCount, pendingCount } =
    React.useMemo(() => {
      let totalQuestions = 0;
      let approvedCount = 0;
      let flaggedCount = 0;
      let pendingCount = 0;

      Object.values(batchMetrics).forEach((metric) => {
        totalQuestions += metric.total;
        approvedCount += metric.approved;
        flaggedCount += metric.flagged;
        pendingCount += metric.pending;
      });

      return {
        totalQuestions,
        approvedCount,
        flaggedCount,
        pendingCount,
      };
    }, [batchMetrics]);

  const totalBatches = batches.length;

  // Filter batches
  const filteredBatches = React.useMemo(() => {
    return batches.filter((batch) => {
      const query = searchQuery.trim().toLowerCase();
      const matchesSearch =
        !query ||
        batch.subject.toLowerCase().includes(query) ||
        batch.batchId.toLowerCase().includes(query);

      const matchesSheetType =
        sheetTypeFilter === "all" || batch.sheetType === sheetTypeFilter;

      const metric = batchMetrics[batch.batchId];
      const batchStatus = metric?.status || "pending";
      const matchesStatus =
        statusFilter === "all" || batchStatus === statusFilter;

      return matchesSearch && matchesSheetType && matchesStatus;
    });
  }, [batches, searchQuery, sheetTypeFilter, statusFilter, batchMetrics]);

  const isFilterActive =
    searchQuery.trim() !== "" ||
    sheetTypeFilter !== "all" ||
    statusFilter !== "all";

  const clearAllFilters = () => {
    setSearchQuery("");
    setSheetTypeFilter("all");
    setStatusFilter("all");
  };

  return (
    <AdminAuthGuard>
      <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0">
        <div className="max-w-6xl mx-auto space-y-6 sm:space-y-8">
          {/* 1. Header with Visual Hierarchy & Action */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-white/[0.08]">
            <div>
              <h1 className="font-serif-heading text-2xl sm:text-3xl text-white font-bold tracking-tight">
                Review Batches
              </h1>
              <p className="text-sm text-zinc-400 mt-1 max-w-xl leading-relaxed">
                Inspect question and solution pairings, calibrate topic tags, verify mathematical difficulty, and approve extracted problem sets.
              </p>
            </div>
            <Link href="/admin/upload" className="shrink-0">
              <Button
                size="sm"
                className="bg-[#F4F0EA] hover:bg-white text-[#0A0A0C] text-xs h-9 px-4 rounded-lg flex items-center gap-2 transition-all cursor-pointer font-semibold shadow-sm border-0"
              >
                <Upload className="h-4 w-4" />
                <span>Upload Question Sheet</span>
              </Button>
            </Link>
          </div>

          {/* 2. Coordinated Metric Overview Strip */}
          <section aria-labelledby="summary-metrics-heading">
            <h2 id="summary-metrics-heading" className="sr-only">
              Review Workspace Summary Metrics
            </h2>
            <div className="rounded-xl border border-white/[0.08] bg-[#121215]/90 backdrop-blur-md shadow-2xl shadow-black/60 overflow-hidden">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 divide-y sm:divide-y-0 lg:divide-x divide-white/[0.08]">
                {/* 1. Total Batches */}
                <div className="p-4 sm:p-5 space-y-1">
                  <div className="flex items-center justify-between text-xs font-medium text-zinc-300">
                    <span>Total Batches</span>
                    <Layers className="h-3.5 w-3.5 text-[#E2B86B]" />
                  </div>
                  <div className="text-2xl sm:text-3xl font-semibold text-white font-mono tabular-nums tracking-tight">
                    {isLoading ? "—" : totalBatches}
                  </div>
                  <p className="text-[11px] text-zinc-400">Active sheet sets</p>
                </div>

                {/* 2. Total Questions */}
                <div className="p-4 sm:p-5 space-y-1">
                  <div className="flex items-center justify-between text-xs font-medium text-zinc-300">
                    <span>Questions</span>
                    <FileText className="h-3.5 w-3.5 text-zinc-300" />
                  </div>
                  <div className="text-2xl sm:text-3xl font-semibold text-white font-mono tabular-nums tracking-tight">
                    {isLoading ? "—" : totalQuestions}
                  </div>
                  <p className="text-[11px] text-zinc-400">Segmented problems</p>
                </div>

                {/* 3. Pending Review */}
                <div className="p-4 sm:p-5 space-y-1">
                  <div className="flex items-center justify-between text-xs font-medium text-zinc-300">
                    <span>Pending</span>
                    <Clock className="h-3.5 w-3.5 text-amber-400" />
                  </div>
                  <div className="text-2xl sm:text-3xl font-semibold text-amber-400 font-mono tabular-nums tracking-tight">
                    {isLoading ? "—" : pendingCount}
                  </div>
                  <p className="text-[11px] text-zinc-400">Awaiting review</p>
                </div>

                {/* 4. Approved */}
                <div className="p-4 sm:p-5 space-y-1">
                  <div className="flex items-center justify-between text-xs font-medium text-zinc-300">
                    <span>Approved</span>
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  </div>
                  <div className="text-2xl sm:text-3xl font-semibold text-emerald-400 font-mono tabular-nums tracking-tight">
                    {isLoading ? "—" : approvedCount}
                  </div>
                  <p className="text-[11px] text-zinc-400">Verified problems</p>
                </div>

                {/* 5. Flagged */}
                <div className="p-4 sm:p-5 space-y-1 col-span-2 sm:col-span-1">
                  <div className="flex items-center justify-between text-xs font-medium text-zinc-300">
                    <span>Flagged</span>
                    <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                  </div>
                  <div className="text-2xl sm:text-3xl font-semibold text-rose-400 font-mono tabular-nums tracking-tight">
                    {isLoading ? "—" : flaggedCount}
                  </div>
                  <p className="text-[11px] text-zinc-400">Needs attention</p>
                </div>
              </div>
            </div>
          </section>

          {/* 3. Search & Filter Toolbar */}
          <div className="space-y-3 pt-1">
            <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
              {/* Search input */}
              <div className="relative flex-1 min-w-[260px]">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500 pointer-events-none" />
                <Input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by subject name or batch ID..."
                  className="pl-10 pr-9 h-10 text-xs sm:text-sm bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 placeholder:text-zinc-500 rounded-lg focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20 shadow-2xs"
                  aria-label="Search batches by subject or batch ID"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 text-zinc-400 hover:text-white rounded cursor-pointer"
                    aria-label="Clear search query"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>

              {/* Filter controls row */}
              <div className="flex flex-wrap sm:flex-nowrap items-center gap-2.5">
                {/* Sheet Type Filter */}
                <div className="w-full sm:w-44">
                  <Select
                    value={sheetTypeFilter}
                    onValueChange={(val: SheetTypeFilter) =>
                      setSheetTypeFilter(val)
                    }
                  >
                    <SelectTrigger
                      className="h-10 text-xs bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 rounded-lg focus:border-zinc-400 shadow-2xs font-medium"
                      aria-label="Filter by sheet type"
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <Filter className="h-3.5 w-3.5 text-zinc-400 shrink-0" />
                        <span className="text-zinc-400 font-normal">Type:</span>
                        <SelectValue placeholder="All Sheet Types" />
                      </div>
                    </SelectTrigger>
                    <SelectContent className="rounded-lg border border-white/[0.1] bg-[#121215] text-zinc-100 shadow-2xl">
                      <SelectItem value="all" className="text-xs cursor-pointer hover:bg-white/[0.06] focus:bg-white/[0.06] focus:text-white text-zinc-200">
                        All Sheet Types
                      </SelectItem>
                      <SelectItem value="tutorial" className="text-xs cursor-pointer hover:bg-white/[0.06] focus:bg-white/[0.06] focus:text-white text-zinc-200">
                        Tutorial Sheet
                      </SelectItem>
                      <SelectItem value="pyq" className="text-xs cursor-pointer hover:bg-white/[0.06] focus:bg-white/[0.06] focus:text-white text-zinc-200">
                        Past Year Question (PYQ)
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Review Status Filter */}
                <div className="w-full sm:w-48">
                  <Select
                    value={statusFilter}
                    onValueChange={(val: StatusFilter) => setStatusFilter(val)}
                  >
                    <SelectTrigger
                      className="h-10 text-xs bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 rounded-lg focus:border-zinc-400 shadow-2xs font-medium"
                      aria-label="Filter by review status"
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <Clock className="h-3.5 w-3.5 text-zinc-400 shrink-0" />
                        <span className="text-zinc-400 font-normal">Status:</span>
                        <SelectValue placeholder="All Statuses" />
                      </div>
                    </SelectTrigger>
                    <SelectContent className="rounded-lg border border-white/[0.1] bg-[#121215] text-zinc-100 shadow-2xl">
                      <SelectItem value="all" className="text-xs cursor-pointer hover:bg-white/[0.06] focus:bg-white/[0.06] focus:text-white text-zinc-200">
                        All Statuses
                      </SelectItem>
                      <SelectItem value="pending" className="text-xs cursor-pointer hover:bg-white/[0.06] focus:bg-white/[0.06] focus:text-white text-zinc-200">
                        Pending Review
                      </SelectItem>
                      <SelectItem value="in_review" className="text-xs cursor-pointer hover:bg-white/[0.06] focus:bg-white/[0.06] focus:text-white text-zinc-200">
                        In Review
                      </SelectItem>
                      <SelectItem value="completed" className="text-xs cursor-pointer hover:bg-white/[0.06] focus:bg-white/[0.06] focus:text-white text-zinc-200">
                        Completed
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Reset all filters shortcut button */}
                {isFilterActive && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={clearAllFilters}
                    className="h-10 px-3 text-xs text-zinc-300 border border-white/[0.08] bg-zinc-800 hover:bg-zinc-700 hover:text-white rounded-lg flex items-center gap-1.5 shrink-0 cursor-pointer shadow-2xs"
                    aria-label="Clear all active filters"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    <span>Reset</span>
                  </Button>
                )}
              </div>
            </div>

            {/* Active filter badges & Counter strip */}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400 pt-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-zinc-400">
                  Showing <strong className="text-white font-mono">{filteredBatches.length}</strong> of{" "}
                  <span className="font-mono">{batches.length}</span> {batches.length === 1 ? "batch" : "batches"}
                </span>

                {isFilterActive && (
                  <div className="flex flex-wrap items-center gap-1.5 pl-1">
                    {searchQuery && (
                      <Badge
                        variant="secondary"
                        className="text-xs bg-zinc-800/90 text-zinc-200 border border-zinc-700/80 flex items-center gap-1.5 py-0.5 px-2 rounded-md"
                      >
                        <span>&ldquo;{searchQuery}&rdquo;</span>
                        <button
                          type="button"
                          onClick={() => setSearchQuery("")}
                          aria-label="Remove search query filter"
                          className="hover:text-rose-400 cursor-pointer"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    )}

                    {sheetTypeFilter !== "all" && (
                      <Badge
                        variant="secondary"
                        className="text-xs bg-zinc-800/90 text-zinc-200 border border-zinc-700/80 flex items-center gap-1.5 py-0.5 px-2 rounded-md"
                      >
                        <span>
                          Type: {sheetTypeFilter === "pyq" ? "PYQ" : "Tutorial Sheet"}
                        </span>
                        <button
                          type="button"
                          onClick={() => setSheetTypeFilter("all")}
                          aria-label="Remove sheet type filter"
                          className="hover:text-rose-400 cursor-pointer"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    )}

                    {statusFilter !== "all" && (
                      <Badge
                        variant="secondary"
                        className="text-xs bg-zinc-800/90 text-zinc-200 border border-zinc-700/80 flex items-center gap-1.5 py-0.5 px-2 rounded-md"
                      >
                        <span>
                          Status:{" "}
                          {statusFilter === "pending"
                            ? "Pending Review"
                            : statusFilter === "in_review"
                            ? "In Review"
                            : "Completed"}
                        </span>
                        <button
                          type="button"
                          onClick={() => setStatusFilter("all")}
                          aria-label="Remove review status filter"
                          className="hover:text-rose-400 cursor-pointer"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 4. Batch Cards Grid or Empty States */}
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
              {[1, 2, 3, 4].map((i) => (
                <Card
                  key={i}
                  className="rounded-xl border border-white/[0.08] bg-[#121215]/90 p-5 space-y-3 animate-pulse shadow-2xl shadow-black/60"
                >
                  <div className="flex justify-between">
                    <div className="h-4 w-28 bg-zinc-800 rounded" />
                    <div className="h-5 w-20 bg-zinc-800 rounded" />
                  </div>
                  <div className="h-6 w-3/4 bg-zinc-800 rounded" />
                  <div className="h-4 w-1/2 bg-zinc-800 rounded" />
                </Card>
              ))}
            </div>
          ) : batches.length === 0 ? (
            <div className="rounded-xl border border-dashed border-white/[0.15] bg-[#121215]/60 p-8 sm:p-12 text-center space-y-3 shadow-2xl shadow-black/60">
              <div className="mx-auto w-10 h-10 rounded-lg bg-zinc-800/80 text-zinc-300 flex items-center justify-center border border-white/[0.08]">
                <Layers className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <h3 className="font-serif-heading text-lg font-semibold text-white">
                  No batches yet
                </h3>
                <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                  No question sheets have been uploaded for review yet. Upload a sheet to start the question extraction workflow.
                </p>
              </div>
              <Link href="/admin/upload" className="inline-block pt-1">
                <Button
                  size="sm"
                  className="bg-[#F4F0EA] hover:bg-white text-[#0A0A0C] text-xs h-9 px-4 rounded-lg font-semibold shadow-sm border-0"
                >
                  <Upload className="h-3.5 w-3.5 mr-1.5" />
                  Upload Question Sheet
                </Button>
              </Link>
            </div>
          ) : filteredBatches.length === 0 ? (
            <div className="rounded-xl border border-dashed border-white/[0.15] bg-[#121215]/60 p-8 sm:p-10 text-center space-y-3 shadow-2xl shadow-black/60">
              <div className="mx-auto w-10 h-10 rounded-lg bg-zinc-800/80 flex items-center justify-center text-zinc-400 border border-white/[0.08]">
                <SearchX className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <h3 className="font-serif-heading text-base font-semibold text-white">
                  No batches match your filter criteria
                </h3>
                <p className="text-xs text-zinc-400 max-w-md mx-auto">
                  Try adjusting your search query or clear the active sheet-type and status filters.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={clearAllFilters}
                className="border border-white/[0.08] bg-zinc-800 text-xs h-9 rounded-lg hover:bg-zinc-700 text-zinc-200 hover:text-white"
              >
                <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
                Clear All Filters
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5">
              {filteredBatches.map((batch) => {
                const formattedDate = new Date(
                  batch.uploadedAt
                ).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                });

                const metric = batchMetrics[batch.batchId] || {
                  total: 0,
                  approved: 0,
                  flagged: 0,
                  reviewed: 0,
                  pending: 0,
                  progressPercent: 0,
                  status: "pending",
                };

                const isCompleted = metric.status === "completed";
                const isInProgress = metric.status === "in_review";

                return (
                  <Link
                    key={batch.batchId}
                    href={`/admin/review/${batch.batchId}`}
                    className="block group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 rounded-xl active:scale-[0.995] transition-transform"
                  >
                    <Card
                      className="h-full rounded-xl border border-white/[0.08] bg-[#121215]/90 backdrop-blur-md p-5 shadow-2xl shadow-black/60 hover:border-white/[0.2] transition-all flex flex-col justify-between"
                    >
                      <CardHeader className="p-0 pb-3 space-y-2.5">
                        {/* Top Metadata Row */}
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-xs font-semibold text-zinc-200 bg-zinc-800/90 border border-zinc-700/80 px-2 py-0.5 rounded-md shadow-2xs">
                            {batch.batchId}
                          </span>
                          <div className="flex items-center gap-1.5">
                            <Badge
                              variant="secondary"
                              className="text-xs font-medium bg-zinc-800/80 text-zinc-300 border border-zinc-700/80 rounded shadow-2xs"
                            >
                              {batch.sheetType === "pyq" ? "PYQ" : "Tutorial Sheet"}
                            </Badge>

                            {isCompleted ? (
                              <Badge className="bg-emerald-950/40 text-emerald-300 border border-emerald-800/40 text-xs px-2 py-0.5 font-medium rounded shadow-2xs">
                                Completed
                              </Badge>
                            ) : isInProgress ? (
                              <Badge className="bg-zinc-800/90 text-zinc-200 border border-zinc-700/80 text-xs px-2 py-0.5 font-medium rounded shadow-2xs">
                                In Review
                              </Badge>
                            ) : (
                              <Badge
                                variant="outline"
                                className="border-amber-800/40 bg-amber-950/40 text-amber-300 text-xs px-2 py-0.5 font-medium rounded shadow-2xs"
                              >
                                Pending Review
                              </Badge>
                            )}
                          </div>
                        </div>

                        {/* Subject Heading */}
                        <CardTitle className="font-serif-heading text-lg font-semibold text-white group-hover:text-[#F3CE85] transition-colors leading-snug">
                          {batch.subject}
                        </CardTitle>
                      </CardHeader>

                      <CardContent className="p-0 pt-1 space-y-3">
                        {/* Review Progress Bar & Stats */}
                        <div className="space-y-1.5 pt-2 border-t border-white/[0.08]">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-zinc-300 text-xs">
                              Review Progress
                            </span>
                            <span className="font-mono font-medium text-white text-xs">
                              {metric.reviewed} of {metric.total} reviewed ({metric.progressPercent}%)
                            </span>
                          </div>
                          <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden border border-white/[0.08]">
                            <div
                              className={`h-full transition-all duration-300 rounded-full ${
                                isCompleted
                                  ? "bg-emerald-500"
                                  : "bg-[#E2B86B]"
                              }`}
                              style={{ width: `${metric.progressPercent}%` }}
                            />
                          </div>
                        </div>

                        {/* Bottom Metadata: Questions, Date & Arrow */}
                        <div className="flex items-center justify-between text-xs text-zinc-400 pt-1">
                          <div className="flex items-center gap-3">
                            <span className="flex items-center gap-1 font-medium text-zinc-300">
                              <FileText className="h-3.5 w-3.5 text-zinc-300" />
                              <span className="font-mono text-white font-semibold">{metric.total}</span> Questions
                            </span>
                            <span className="text-zinc-600">•</span>
                            <span className="flex items-center gap-1 text-zinc-400 font-mono text-xs">
                              <Calendar className="h-3.5 w-3.5 text-zinc-500" />
                              {formattedDate}
                            </span>
                          </div>

                          <div className="flex items-center gap-1 text-[#E2B86B] hover:text-[#F3CE85] font-medium text-xs group-hover:translate-x-0.5 transition-transform">
                            <span>Inspect & Review</span>
                            <ArrowRight className="h-3.5 w-3.5" />
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </AdminAuthGuard>
  );
}

