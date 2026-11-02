"use client";

import * as React from "react";
import type { Question } from "@/lib/types";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { TagEditor } from "@/components/admin/TagEditor";
import { QuestionEditDialog } from "@/components/admin/QuestionEditDialog";
import { ImageViewerDialog } from "@/components/admin/ImageViewerDialog";
import {
  ZoomIn,
  Maximize2,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Columns2,
  Edit3,
} from "lucide-react";
import { toast } from "sonner";

export interface QuestionReviewCardProps {
  question: Question;
  onUpdate: (id: string, updates: Partial<Question>) => void;
  defaultSolutionOpen?: boolean;
}

export function QuestionReviewCard({
  question,
  onUpdate,
  defaultSolutionOpen = false,
}: QuestionReviewCardProps) {
  const [flagNote, setFlagNote] = React.useState<string>(question.flagNote || "");
  const [flagError, setFlagError] = React.useState<string | null>(null);
  const [showFlagInput, setShowFlagInput] = React.useState<boolean>(false);
  const [editDialogOpen, setEditDialogOpen] = React.useState<boolean>(false);
  const [isSolutionOpen, setIsSolutionOpen] = React.useState<boolean>(
    defaultSolutionOpen
  );

  const [viewerState, setViewerState] = React.useState<{
    open: boolean;
    initialMode: "primary" | "paired" | "split";
    title: string;
    subtitle?: string;
  }>({
    open: false,
    initialMode: "primary",
    title: "",
  });

  React.useEffect(() => {
    if (question.flagNote !== undefined) {
      setFlagNote(question.flagNote);
    }
  }, [question.flagNote]);

  const renderStatusBadge = () => {
    switch (question.status) {
      case "approved":
        return (
          <Badge className="bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 capitalize flex items-center gap-1.5 font-medium px-2.5 py-0.5 text-xs rounded-md">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
            <span>Approved</span>
          </Badge>
        );
      case "flagged":
        return (
          <Badge className="bg-rose-950/60 text-rose-300 border border-rose-800/60 capitalize flex items-center gap-1.5 font-medium px-2.5 py-0.5 text-xs rounded-md">
            <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
            <span>Flagged</span>
          </Badge>
        );
      case "pending":
      default:
        return (
          <Badge
            variant="outline"
            className="border-amber-800/60 bg-amber-950/60 text-amber-300 capitalize flex items-center gap-1.5 font-medium px-2.5 py-0.5 text-xs rounded-md"
          >
            <Clock className="h-3.5 w-3.5 text-amber-400" />
            <span>Pending Review</span>
          </Badge>
        );
    }
  };

  const openImageViewer = (
    mode: "primary" | "paired" | "split",
    title: string,
    subtitle?: string
  ) => {
    setViewerState({
      open: true,
      initialMode: mode,
      title,
      subtitle,
    });
  };

  const handleConfirmFlag = () => {
    const trimmed = flagNote.trim();
    if (!trimmed) {
      setFlagError("A reason is required to flag this question.");
      return;
    }

    onUpdate(question.id, { status: "flagged", flagNote: trimmed });
    setShowFlagInput(false);
    setFlagError(null);
    toast.error("Question flagged for correction");
  };

  return (
    <>
      <Card
        className="rounded-xl border border-white/[0.08] bg-[#121215]/90 backdrop-blur-md shadow-2xl shadow-black/60 overflow-hidden transition-all hover:border-white/[0.15]"
      >
        <CardHeader className="p-5 sm:p-6 pb-0 space-y-3">
          {/* 1. Status Badge & Action summary */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>{renderStatusBadge()}</div>

            {/* Quick action: Inspect Pairing */}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                openImageViewer(
                  "split",
                  `${question.subject} - Pairing Inspection`,
                  `Module ${question.module} • ${question.sheetType.toUpperCase()}`
                )
              }
              className="h-8 px-3 text-xs text-zinc-200 bg-zinc-800/80 border border-white/[0.08] hover:bg-zinc-700 hover:text-white rounded-lg flex items-center gap-1.5 transition-all cursor-pointer font-medium shadow-2xs"
              title="Inspect question and solution side-by-side"
            >
              <Columns2 className="h-3.5 w-3.5 text-[#E2B86B]" />
              <span>Inspect Pairing</span>
            </Button>
          </div>

          {/* Persistent Flag Reason Banner (Visible when question is flagged) */}
          {question.status === "flagged" && (
            <div className="rounded-lg border border-rose-800/40 bg-rose-950/40 backdrop-blur-xs p-3.5 space-y-1.5 shadow-2xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-400">
                  <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                  <span>Flag Reason:</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setShowFlagInput(true);
                    setFlagError(null);
                  }}
                  className="text-xs text-rose-300 hover:underline font-medium cursor-pointer"
                >
                  Edit Note
                </button>
              </div>
              <p className="text-xs text-rose-200 font-normal leading-relaxed pl-5">
                {question.flagNote || "Reason not provided."}
              </p>
            </div>
          )}

          {/* 2. Subject, Module, and Sheet Type catalog label */}
          <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm text-zinc-300 font-medium pt-1">
            <span className="font-semibold text-white">{question.subject}</span>
            <span className="text-zinc-600">•</span>
            <span className="text-zinc-300">Module {question.module}</span>
            <span className="text-zinc-600">•</span>
            <Badge
              variant="secondary"
              className="text-xs font-medium bg-zinc-800/90 text-zinc-300 border border-zinc-700/80 rounded-md shadow-2xs"
            >
              {question.sheetType.toUpperCase()}
            </Badge>
            {question.sheetType === "pyq" && question.year && (
              <>
                <span className="text-zinc-600">•</span>
                <span className="font-mono text-zinc-300">{question.year}</span>
              </>
            )}
          </div>
        </CardHeader>

        <CardContent className="p-5 sm:p-6 pt-4 space-y-5">
          {/* 3. The question image preview - SOLID CRISP BG-WHITE FOR 100% MATH LEGIBILITY */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs font-medium">
              <span className="text-zinc-200 font-medium">Problem Statement</span>
              <span className="flex items-center gap-1 text-xs text-[#E2B86B] hover:text-[#F3CE85] font-medium transition-colors">
                <ZoomIn className="h-3 w-3" /> Click to enlarge
              </span>
            </div>

            <div
              role="button"
              tabIndex={0}
              aria-label={`View full-size question image for ${question.subject}`}
              onClick={() =>
                openImageViewer(
                  "primary",
                  `${question.subject} - Question Image`,
                  `Module ${question.module} • ${question.sheetType.toUpperCase()}${
                    question.year ? ` • ${question.year}` : ""
                  }`
                )
              }
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  openImageViewer(
                    "primary",
                    `${question.subject} - Question Image`,
                    `Module ${question.module} • ${question.sheetType.toUpperCase()}${
                      question.year ? ` • ${question.year}` : ""
                    }`
                  );
                }
              }}
              className="group relative cursor-zoom-in rounded-xl border border-zinc-300 bg-white p-3.5 flex items-center justify-center overflow-hidden transition-all hover:border-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 shadow-xs"
            >
              <img
                src={question.questionImageUrl}
                alt={`Question: ${question.subject}`}
                className="w-auto max-w-full h-auto max-h-64 sm:max-h-80 md:max-h-[380px] object-contain rounded select-none"
              />
              <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5 rounded-md bg-[#0A0A0C]/90 px-2.5 py-1 text-xs font-medium text-white border border-white/[0.12] transition-opacity group-hover:opacity-100 opacity-90 sm:opacity-0 pointer-events-none shadow-xs">
                <Maximize2 className="h-3 w-3 text-[#E2B86B]" />
                <span>Full Size</span>
              </div>
            </div>
          </div>

          {/* 4. Interactive topic tag editor */}
          <div>
            <TagEditor
              tags={question.topics || []}
              onChange={(newTags) => {
                const currentTags = question.topics || [];
                const isDifferent =
                  newTags.length !== currentTags.length ||
                  newTags.some((tag, index) => tag !== currentTags[index]);

                if (isDifferent) {
                  onUpdate(question.id, { topics: newTags });
                  toast("Topics updated", { duration: 1500 });
                }
              }}
            />
          </div>

          {/* 5. Collapsible Solution Image Preview - SOLID CRISP BG-WHITE */}
          <div className="space-y-2 border-t border-white/[0.08] pt-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-zinc-200">Paired Solution</span>
                <span className="text-xs text-zinc-400 font-mono">
                  ({isSolutionOpen ? "Visible" : "Hidden"})
                </span>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsSolutionOpen((prev) => !prev)}
                className="h-8 px-2.5 text-xs text-zinc-300 border border-white/[0.08] bg-zinc-800/80 hover:bg-zinc-700 hover:text-white rounded-lg flex items-center gap-1.5 cursor-pointer font-medium shadow-2xs"
                aria-expanded={isSolutionOpen}
                aria-controls={`solution-preview-${question.id}`}
              >
                {isSolutionOpen ? (
                  <>
                    <EyeOff className="h-3.5 w-3.5 text-zinc-400" />
                    <span>Hide Solution</span>
                    <ChevronUp className="h-3.5 w-3.5 text-zinc-400" />
                  </>
                ) : (
                  <>
                    <Eye className="h-3.5 w-3.5 text-[#E2B86B]" />
                    <span>Show Solution</span>
                    <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
                  </>
                )}
              </Button>
            </div>

            {isSolutionOpen && (
              <div
                id={`solution-preview-${question.id}`}
                className="space-y-1.5 pt-1 animate-in fade-in-50 duration-200"
              >
                <div className="flex items-center justify-between text-xs font-medium">
                  <span className="text-zinc-200 font-medium">Solution Working</span>
                  <span className="flex items-center gap-1 text-xs text-[#E2B86B] hover:text-[#F3CE85] font-medium transition-colors">
                    <ZoomIn className="h-3 w-3" /> Click to enlarge
                  </span>
                </div>

                <div
                  role="button"
                  tabIndex={0}
                  aria-label={`View full-size solution image for ${question.subject}`}
                  onClick={() =>
                    openImageViewer(
                      "paired",
                      `${question.subject} - Solution Image`,
                      `Module ${question.module} • ${question.sheetType.toUpperCase()}`
                    )
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openImageViewer(
                        "paired",
                        `${question.subject} - Solution Image`,
                        `Module ${question.module} • ${question.sheetType.toUpperCase()}`
                      );
                    }
                  }}
                  className="group relative cursor-zoom-in rounded-xl border border-zinc-300 bg-white p-3.5 flex items-center justify-center overflow-hidden transition-all hover:border-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 shadow-xs"
                >
                  <img
                    src={question.solutionImageUrl}
                    alt={`Solution: ${question.subject}`}
                    className="w-auto max-w-full h-auto max-h-64 sm:max-h-80 md:max-h-[380px] object-contain rounded select-none"
                  />
                  <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5 rounded-md bg-[#0A0A0C]/90 px-2.5 py-1 text-xs font-medium text-white border border-white/[0.12] transition-opacity group-hover:opacity-100 opacity-90 sm:opacity-0 pointer-events-none shadow-xs">
                    <Maximize2 className="h-3 w-3 text-[#E2B86B]" />
                    <span>Full Size</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 6. Action buttons with consistent status cues */}
          <div className="flex flex-wrap items-center gap-2.5 pt-2">
            <Button
              variant="default"
              className="bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white rounded-lg flex items-center gap-1.5 font-medium cursor-pointer transition-all shadow-xs"
              onClick={() => {
                onUpdate(question.id, { status: "approved" });
                setShowFlagInput(false);
                setFlagError(null);
                toast.success("Question approved");
              }}
            >
              <CheckCircle2 className="h-4 w-4 stroke-[2.2]" />
              <span>{question.status === "approved" ? "Approved" : "Approve"}</span>
            </Button>

            <Button
              variant={question.status === "flagged" ? "destructive" : "outline"}
              className={
                question.status === "flagged"
                  ? "bg-rose-600 hover:bg-rose-500 active:scale-[0.98] text-white rounded-lg flex items-center gap-1.5 font-medium cursor-pointer transition-all shadow-xs"
                  : "border border-rose-700/60 text-rose-300 bg-rose-950/40 hover:bg-rose-900/50 active:scale-[0.98] rounded-lg flex items-center gap-1.5 font-medium cursor-pointer transition-all shadow-xs"
              }
              onClick={() => {
                setShowFlagInput(true);
                setFlagError(null);
              }}
            >
              <AlertTriangle className="h-4 w-4 text-rose-400" />
              <span>{question.status === "flagged" ? "Flagged" : "Flag"}</span>
            </Button>

            <Button
              variant="outline"
              className="border border-white/[0.08] bg-zinc-800/80 hover:bg-zinc-700 active:scale-[0.98] text-zinc-200 hover:text-white rounded-lg flex items-center gap-1.5 cursor-pointer font-medium transition-all shadow-2xs"
              onClick={() => setEditDialogOpen(true)}
            >
              <Edit3 className="h-3.5 w-3.5 text-zinc-400" />
              <span>Edit Metadata</span>
            </Button>
          </div>

          {/* Flag Reason Textarea */}
          {showFlagInput && (
            <div className="space-y-3 pt-3 border-t border-white/[0.08]">
              <div className="space-y-1.5">
                <Label
                  htmlFor={`flag-reason-input-${question.id}`}
                  className="text-xs font-semibold text-rose-400 flex items-center gap-1.5"
                >
                  <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                  <span>Reason for flagging (Required)</span>
                </Label>
                <Textarea
                  id={`flag-reason-input-${question.id}`}
                  value={flagNote}
                  onChange={(e) => {
                    setFlagNote(e.target.value);
                    if (flagError) setFlagError(null);
                  }}
                  placeholder="Explain why this question needs correction (e.g. incorrect diagram, missing equation steps, solution mismatch)..."
                  className={`text-xs min-h-[80px] bg-[#0A0A0C] text-zinc-100 placeholder:text-zinc-500 rounded-lg ${
                    flagError
                      ? "border-rose-500 focus-visible:ring-rose-500/20"
                      : "border-white/[0.12] focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20"
                  }`}
                  aria-invalid={Boolean(flagError)}
                />
              </div>

              {flagError && (
                <p className="text-[11px] text-rose-400 font-semibold">
                  {flagError}
                </p>
              )}

              <div className="flex items-center gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleConfirmFlag}
                  disabled={!flagNote.trim()}
                  className="bg-rose-600 hover:bg-rose-500 text-white rounded-lg cursor-pointer font-medium"
                >
                  Confirm Flag
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setShowFlagInput(false);
                    setFlagError(null);
                    setFlagNote(question.flagNote || "");
                  }}
                  className="border border-white/[0.08] bg-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-700 rounded-lg cursor-pointer"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>


      {/* Edit Dialog */}
      <QuestionEditDialog
        question={question}
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
        onSave={onUpdate}
      />

      {/* Full-size Image Viewer Dialog */}
      <ImageViewerDialog
        open={viewerState.open}
        onOpenChange={(open) => {
          setViewerState((prev) => ({ ...prev, open }));
        }}
        imageUrl={question.questionImageUrl}
        imageAlt={`Question: ${question.subject}`}
        title={viewerState.title}
        subtitle={viewerState.subtitle}
        pairedImageUrl={question.solutionImageUrl}
        pairedImageAlt={`Solution for ${question.subject}`}
        pairedTitle="Solution"
        initialMode={viewerState.initialMode}
      />
    </>
  );
}

export default QuestionReviewCard;
