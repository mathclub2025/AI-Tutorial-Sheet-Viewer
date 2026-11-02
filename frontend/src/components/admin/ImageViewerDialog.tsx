"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, Columns2, FileQuestion, CheckCircle2 } from "lucide-react";

export interface ImageViewerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  imageUrl: string;
  imageAlt: string;
  title?: string;
  subtitle?: string;
  pairedImageUrl?: string;
  pairedImageAlt?: string;
  pairedTitle?: string;
  initialMode?: "primary" | "paired" | "split";
}

export function ImageViewerDialog({
  open,
  onOpenChange,
  imageUrl,
  imageAlt,
  title = "Full-size Image Viewer",
  subtitle,
  pairedImageUrl,
  pairedImageAlt = "Paired Solution Image",
  pairedTitle = "Solution",
  initialMode = "primary",
}: ImageViewerDialogProps) {
  const [viewMode, setViewMode] = React.useState<"primary" | "paired" | "split">(
    initialMode
  );

  React.useEffect(() => {
    if (open) {
      setViewMode(initialMode);
    }
  }, [open, initialMode, imageUrl, pairedImageUrl]);

  // Explicit listener for Escape key
  React.useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onOpenChange(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onOpenChange]);

  const hasPairing = Boolean(pairedImageUrl);
  const currentImageUrl =
    viewMode === "paired" ? pairedImageUrl || imageUrl : imageUrl;
  const currentAlt =
    viewMode === "paired" ? pairedImageAlt : imageAlt;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="z-[60] w-[96vw] sm:w-[92vw] max-w-5xl max-h-[94vh] p-4 sm:p-6 flex flex-col gap-3 overflow-hidden bg-[#121215]/98 backdrop-blur-xl border border-white/[0.1] text-zinc-100 shadow-2xl rounded-xl"
        aria-describedby="image-viewer-description"
      >
        <DialogHeader className="pr-8 text-left space-y-2">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <DialogTitle className="text-base sm:text-lg font-semibold tracking-tight text-white">
                {title}
              </DialogTitle>
              <DialogDescription
                id="image-viewer-description"
                className="text-xs text-zinc-400 mt-0.5 leading-relaxed"
              >
                {subtitle ||
                  "Inspect mathematical equations, formulas, diagrams, and pairing alignment."}
              </DialogDescription>
            </div>

            {/* Pairing inspection mode selector */}
            {hasPairing && (
              <div
                className="inline-flex items-center p-0.5 rounded-lg bg-[#0A0A0C] border border-white/[0.1] self-start sm:self-auto shrink-0 shadow-2xs"
                role="tablist"
                aria-label="Pairing inspection view modes"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={viewMode === "primary"}
                  onClick={() => setViewMode("primary")}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 cursor-pointer ${
                    viewMode === "primary"
                      ? "bg-zinc-800 text-white border border-white/[0.1] shadow-xs font-medium"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  <FileQuestion className="h-3.5 w-3.5 text-[#E2B86B]" />
                  <span>Question</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={viewMode === "paired"}
                  onClick={() => setViewMode("paired")}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 cursor-pointer ${
                    viewMode === "paired"
                      ? "bg-zinc-800 text-white border border-white/[0.1] shadow-xs font-medium"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  <span>{pairedTitle}</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={viewMode === "split"}
                  onClick={() => setViewMode("split")}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 cursor-pointer ${
                    viewMode === "split"
                      ? "bg-zinc-800 text-white border border-white/[0.1] shadow-xs font-medium"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  <Columns2 className="h-3.5 w-3.5 text-[#E2B86B]" />
                  <span>Side-by-side</span>
                </button>
              </div>
            )}
          </div>
        </DialogHeader>

        {/* Image preview area - CRISP SOLID BG-WHITE FOR MAXIMUM LEGIBILITY */}
        {viewMode === "split" && hasPairing ? (
          <div className="relative flex-1 min-h-[260px] max-h-[70vh] sm:max-h-[74vh] grid grid-cols-1 md:grid-cols-2 gap-3 overflow-auto p-1">
            {/* Question column */}
            <div className="flex flex-col space-y-1.5 rounded-xl border border-zinc-300 bg-white p-2.5 sm:p-3 shadow-xs">
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-900 pb-2 border-b border-zinc-200">
                <span>Question Statement</span>
                <Badge variant="outline" className="text-[10px] bg-zinc-100 border-zinc-300 text-zinc-800 font-medium shadow-none">
                  Primary
                </Badge>
              </div>
              <div className="flex-1 flex items-center justify-center overflow-auto min-h-[180px] bg-white rounded-lg p-2 border border-zinc-200">
                {imageUrl ? (
                  <img
                    src={imageUrl}
                    alt={imageAlt}
                    className="max-h-[58vh] w-auto max-w-full object-contain rounded select-none"
                  />
                ) : (
                  <p className="text-xs text-zinc-600">No question image</p>
                )}
              </div>
            </div>

            {/* Solution column */}
            <div className="flex flex-col space-y-1.5 rounded-xl border border-zinc-300 bg-white p-2.5 sm:p-3 shadow-xs">
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-900 pb-2 border-b border-zinc-200">
                <span>{pairedTitle} Working</span>
                <Badge variant="outline" className="text-[10px] bg-emerald-50 border-emerald-200 text-emerald-800 font-medium shadow-none">
                  Paired Working
                </Badge>
              </div>
              <div className="flex-1 flex items-center justify-center overflow-auto min-h-[180px] bg-white rounded-lg p-2 border border-zinc-200">
                {pairedImageUrl ? (
                  <img
                    src={pairedImageUrl}
                    alt={pairedImageAlt}
                    className="max-h-[58vh] w-auto max-w-full object-contain rounded select-none"
                  />
                ) : (
                  <p className="text-xs text-zinc-600">No solution image</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="relative flex-1 min-h-[220px] max-h-[68vh] sm:max-h-[74vh] flex items-center justify-center overflow-auto rounded-xl border border-zinc-300 bg-white p-2 sm:p-4 shadow-xs">
            {currentImageUrl ? (
              <img
                src={currentImageUrl}
                alt={currentAlt || "Full size mathematical preview"}
                className="max-h-[64vh] sm:max-h-[70vh] w-auto max-w-full object-contain select-none rounded"
              />
            ) : (
              <p className="text-xs text-zinc-600">No image available</p>
            )}
          </div>
        )}

        {/* Footer actions */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2.5 border-t border-white/[0.08]">
          <div className="flex items-center gap-3">
            {currentImageUrl && (
              <a
                href={currentImageUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-[#E2B86B] hover:text-[#F3CE85] hover:underline font-medium transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                <span>
                  Open {viewMode === "paired" ? "solution" : "current"} in new tab
                </span>
              </a>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              className="text-xs h-8 px-4 border border-white/[0.08] bg-zinc-800 hover:bg-zinc-700 active:scale-[0.98] text-zinc-300 hover:text-white rounded-lg cursor-pointer font-medium shadow-none transition-all"
              aria-label="Close image viewer"
            >
              Close (Esc)
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default ImageViewerDialog;
