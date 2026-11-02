"use client";

import * as React from "react";
import type { Question } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ImageViewerDialog } from "@/components/admin/ImageViewerDialog";
import { TagEditor } from "@/components/admin/TagEditor";
import { ZoomIn, Maximize2, Columns2, Edit3 } from "lucide-react";
import { toast } from "sonner";

export interface QuestionEditDialogProps {
  question: Question;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (id: string, updates: Partial<Question>) => void;
}

export function QuestionEditDialog({
  question,
  open,
  onOpenChange,
  onSave,
}: QuestionEditDialogProps) {
  const [subject, setSubject] = React.useState<string>(question.subject);
  const [module, setModule] = React.useState<number>(question.module);
  const [difficulty, setDifficulty] = React.useState<"easy" | "medium" | "hard">(
    question.difficulty
  );
  const [sheetType, setSheetType] = React.useState<"tutorial" | "pyq">(
    question.sheetType
  );
  const [solutionImageUrl, setSolutionImageUrl] = React.useState<string>(
    question.solutionImageUrl
  );
  const [topics, setTopics] = React.useState<string[]>(question.topics || []);
  const [viewerImage, setViewerImage] = React.useState<{
    src: string;
    alt: string;
    title: string;
    subtitle?: string;
    initialMode?: "primary" | "paired" | "split";
  } | null>(null);

  React.useEffect(() => {
    setSubject(question.subject);
    setModule(question.module);
    setDifficulty(question.difficulty);
    setSheetType(question.sheetType);
    setSolutionImageUrl(question.solutionImageUrl);
    setTopics(question.topics || []);
  }, [question.id, question.topics]);

  const handleSave = () => {
    onSave(question.id, {
      subject,
      module,
      difficulty,
      sheetType,
      solutionImageUrl,
      topics,
    });
    onOpenChange(false);
    toast.success("Changes saved");
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg sm:max-w-xl max-h-[90vh] overflow-y-auto rounded-xl border border-white/[0.1] shadow-2xl bg-[#121215]/98 backdrop-blur-xl text-zinc-100 p-5 sm:p-6">
          <DialogHeader className="space-y-1 pb-3 border-b border-white/[0.08]">
            <div className="flex items-center gap-2.5 text-[#E2B86B]">
              <div className="w-8 h-8 rounded-lg bg-zinc-800/80 border border-white/[0.08] flex items-center justify-center shadow-xs">
                <Edit3 className="h-4 w-4 text-[#E2B86B]" />
              </div>
              <DialogTitle className="text-lg font-semibold text-white">
                Edit Question Details
              </DialogTitle>
            </div>
            <DialogDescription className="text-xs text-zinc-400 leading-relaxed">
              Update problem metadata, edit mathematical topics, and verify visual question/solution pairing.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3.5 py-3">
            {/* Subject */}
            <div className="space-y-1.5">
              <Label htmlFor="edit-subject" className="text-xs font-medium text-zinc-300">
                Subject
              </Label>
              <Input
                id="edit-subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g. Probability and Statistics"
                className="bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 placeholder:text-zinc-500 rounded-lg focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20 text-sm h-9.5 shadow-2xs font-medium"
              />
            </div>

            {/* Module */}
            <div className="space-y-1.5">
              <Label htmlFor="edit-module" className="text-xs font-medium text-zinc-300">
                Module (1-12)
              </Label>
              <Input
                id="edit-module"
                type="number"
                min={1}
                max={12}
                value={module}
                onChange={(e) => setModule(Number(e.target.value))}
                placeholder="1-12"
                className="bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 placeholder:text-zinc-500 rounded-lg focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20 text-sm h-9.5 font-mono shadow-2xs font-medium"
              />
            </div>

            {/* Difficulty & Sheet Type */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-zinc-300">
                  Difficulty
                </Label>
                <Select
                  value={difficulty}
                  onValueChange={(val: "easy" | "medium" | "hard") =>
                    setDifficulty(val)
                  }
                >
                  <SelectTrigger className="bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 rounded-lg text-sm h-9.5 shadow-2xs font-medium focus:border-zinc-400">
                    <SelectValue placeholder="Select difficulty" />
                  </SelectTrigger>
                  <SelectContent className="rounded-lg border border-white/[0.1] bg-[#121215] text-zinc-100 shadow-2xl">
                    <SelectItem value="easy" className="cursor-pointer hover:bg-white/[0.06] text-zinc-200">Easy</SelectItem>
                    <SelectItem value="medium" className="cursor-pointer hover:bg-white/[0.06] text-zinc-200">Medium</SelectItem>
                    <SelectItem value="hard" className="cursor-pointer hover:bg-white/[0.06] text-zinc-200">Hard</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-zinc-300">
                  Sheet Type
                </Label>
                <Select
                  value={sheetType}
                  onValueChange={(val: "tutorial" | "pyq") => setSheetType(val)}
                >
                  <SelectTrigger className="bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 rounded-lg text-sm h-9.5 shadow-2xs font-medium focus:border-zinc-400">
                    <SelectValue placeholder="Select sheet type" />
                  </SelectTrigger>
                  <SelectContent className="rounded-lg border border-white/[0.1] bg-[#121215] text-zinc-100 shadow-2xl">
                    <SelectItem value="tutorial" className="cursor-pointer hover:bg-white/[0.06] text-zinc-200">Tutorial Sheet</SelectItem>
                    <SelectItem value="pyq" className="cursor-pointer hover:bg-white/[0.06] text-zinc-200">PYQ</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Solution Image URL */}
            <div className="space-y-1.5">
              <Label htmlFor="edit-solution-image-url" className="text-xs font-medium text-zinc-300">
                Solution Image URL (re-pair if mismatched)
              </Label>
              <Input
                id="edit-solution-image-url"
                type="text"
                value={solutionImageUrl}
                onChange={(e) => setSolutionImageUrl(e.target.value)}
                placeholder="https://..."
                className="bg-[#0A0A0C] border border-white/[0.12] text-zinc-100 placeholder:text-zinc-500 rounded-lg focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20 text-xs font-mono h-9.5 shadow-2xs"
              />
            </div>

            {/* Topic Tags */}
            <div className="space-y-1.5 pt-1">
              <TagEditor
                tags={topics}
                onChange={setTopics}
                placeholder="Add topic (e.g. Bayes' Theorem)..."
              />
            </div>

            {/* Side by side image pairing preview */}
            <div className="space-y-2 pt-2 border-t border-white/[0.08]">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium text-zinc-300">
                  Visual Pairing Preview
                </Label>
                <button
                  type="button"
                  onClick={() =>
                    setViewerImage({
                      src: question.questionImageUrl,
                      alt: `Question: ${subject}`,
                      title: `${subject} - Visual Pairing Inspection`,
                      subtitle: `Module ${module} • ${sheetType.toUpperCase()}`,
                      initialMode: "split",
                    })
                  }
                  className="text-xs text-[#E2B86B] hover:text-[#F3CE85] hover:underline font-medium flex items-center gap-1 cursor-pointer transition-colors"
                >
                  <Columns2 className="h-3.5 w-3.5" />
                  <span>Compare Fullscreen</span>
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                {/* Question Image Preview - CRISP SOLID BG-WHITE */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-zinc-300 font-medium">
                    <span>Question</span>
                    <span className="flex items-center gap-0.5 text-[#E2B86B] text-[10px] font-medium">
                      <ZoomIn className="h-2.5 w-2.5" /> Enlarge
                    </span>
                  </div>
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label="View full-size question image"
                    onClick={() =>
                      setViewerImage({
                        src: question.questionImageUrl,
                        alt: `Question: ${subject}`,
                        title: `${subject} - Question Image Preview`,
                        subtitle: `Module ${module} • ${sheetType.toUpperCase()}`,
                        initialMode: "primary",
                      })
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setViewerImage({
                          src: question.questionImageUrl,
                          alt: `Question: ${subject}`,
                          title: `${subject} - Question Image Preview`,
                          subtitle: `Module ${module} • ${sheetType.toUpperCase()}`,
                          initialMode: "primary",
                        });
                      }
                    }}
                    className="group relative cursor-zoom-in rounded-xl border border-zinc-300 bg-white p-2.5 flex items-center justify-center min-h-[120px] hover:border-zinc-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-400 transition-all shadow-xs"
                  >
                    <img
                      src={question.questionImageUrl}
                      alt="Current Question"
                      className="max-h-36 w-auto max-w-full object-contain rounded"
                    />
                    <div className="absolute bottom-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity bg-[#0A0A0C]/90 text-white border border-white/[0.12] shadow-xs rounded px-1.5 py-0.5 text-[10px] flex items-center gap-1 pointer-events-none font-medium">
                      <Maximize2 className="h-2.5 w-2.5 text-[#E2B86B]" />
                      <span>Full size</span>
                    </div>
                  </div>
                </div>

                {/* Solution Image Preview - CRISP SOLID BG-WHITE */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-zinc-300 font-medium">
                    <span>Solution</span>
                    <span className="flex items-center gap-0.5 text-emerald-400 text-[10px] font-medium">
                      <ZoomIn className="h-2.5 w-2.5" /> Enlarge
                    </span>
                  </div>
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label="View full-size solution image"
                    onClick={() =>
                      setViewerImage({
                        src: solutionImageUrl || question.solutionImageUrl,
                        alt: `Solution: ${subject}`,
                        title: `${subject} - Solution Image Preview`,
                        subtitle: `Module ${module} • ${sheetType.toUpperCase()}`,
                        initialMode: "paired",
                      })
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setViewerImage({
                          src: solutionImageUrl || question.solutionImageUrl,
                          alt: `Solution: ${subject}`,
                          title: `${subject} - Solution Image Preview`,
                          subtitle: `Module ${module} • ${sheetType.toUpperCase()}`,
                          initialMode: "paired",
                        });
                      }
                    }}
                    className="group relative cursor-zoom-in rounded-xl border border-zinc-300 bg-white p-2.5 flex items-center justify-center min-h-[120px] hover:border-zinc-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-400 transition-all shadow-xs"
                  >
                    <img
                      src={solutionImageUrl || question.solutionImageUrl}
                      alt="Current Solution"
                      className="max-h-36 w-auto max-w-full object-contain rounded"
                    />
                    <div className="absolute bottom-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity bg-[#0A0A0C]/90 text-white border border-white/[0.12] shadow-xs rounded px-1.5 py-0.5 text-[10px] flex items-center gap-1 pointer-events-none font-medium">
                      <Maximize2 className="h-2.5 w-2.5 text-emerald-400" />
                      <span>Full size</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0 pt-3 border-t border-white/[0.08]">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="rounded-lg border border-white/[0.08] bg-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-700 active:scale-[0.98] h-9 px-4 text-xs font-medium cursor-pointer transition-all shadow-2xs"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="default"
              onClick={handleSave}
              className="rounded-lg bg-[#F4F0EA] hover:bg-white active:scale-[0.98] text-[#0A0A0C] font-semibold h-9 px-4 text-xs cursor-pointer transition-all shadow-sm border-0"
            >
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Full Size Image Viewer */}
      <ImageViewerDialog
        open={Boolean(viewerImage)}
        onOpenChange={(viewerOpen) => {
          if (!viewerOpen) setViewerImage(null);
        }}
        imageUrl={question.questionImageUrl}
        imageAlt={`Question: ${subject}`}
        title={viewerImage?.title || `${subject} - Visual Pairing Preview`}
        subtitle={viewerImage?.subtitle}
        pairedImageUrl={solutionImageUrl || question.solutionImageUrl}
        pairedImageAlt={`Solution: ${subject}`}
        pairedTitle="Solution"
        initialMode={viewerImage?.initialMode || "primary"}
      />
    </>
  );
}

export default QuestionEditDialog;
