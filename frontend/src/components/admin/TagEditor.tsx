"use client";

import * as React from "react";
import { X, Plus, AlertCircle, Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export interface TagEditorProps {
  tags: string[];
  onChange: (newTags: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function TagEditor({
  tags,
  onChange,
  placeholder = "Add topic (e.g. Bayes' Theorem)...",
  disabled = false,
}: TagEditorProps) {
  const [inputValue, setInputValue] = React.useState<string>("");
  const [error, setError] = React.useState<string | null>(null);

  const handleAddTag = () => {
    const trimmed = inputValue.trim();

    // 1. Reject empty tags
    if (!trimmed) {
      setError("Topic tag cannot be empty.");
      return;
    }

    // 2. Reject duplicate tags (case-insensitive)
    const isDuplicate = tags.some(
      (existingTag) =>
        existingTag.trim().toLowerCase() === trimmed.toLowerCase()
    );

    if (isDuplicate) {
      setError(`"${trimmed}" is already added.`);
      return;
    }

    // Add new tag
    onChange([...tags, trimmed]);
    setInputValue("");
    setError(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddTag();
    }
  };

  const handleRemove = (indexToRemove: number) => {
    const removedTag = tags[indexToRemove];
    onChange(tags.filter((_, index) => index !== indexToRemove));
    if (
      error &&
      removedTag &&
      error.toLowerCase().includes(removedTag.toLowerCase())
    ) {
      setError(null);
    }
  };

  return (
    <div className="w-full space-y-2.5">
      <div className="flex items-center justify-between text-xs text-zinc-300 font-medium">
        <span className="flex items-center gap-1.5 font-medium text-zinc-200">
          <Tag className="h-3.5 w-3.5 text-[#E2B86B]" />
          <span>Topic tags ({tags.length})</span>
        </span>
        {tags.length > 0 && (
          <span className="text-[11px] text-zinc-400">Click &times; to remove</span>
        )}
      </div>

      {/* Tags list in flex-wrap row */}
      {tags.length > 0 ? (
        <div
          className="flex flex-wrap items-center gap-1.5"
          role="list"
          aria-label="Topic tags"
        >
          {tags.map((tag, index) => (
            <Badge
              key={`${tag}-${index}`}
              variant="secondary"
              className="flex items-center gap-1.5 text-xs py-0.5 px-2.5 bg-zinc-800/90 text-zinc-200 border border-zinc-700/80 rounded-md font-medium shadow-2xs group transition-all hover:bg-zinc-700/80"
            >
              <span>{tag}</span>
              <button
                type="button"
                onClick={() => handleRemove(index)}
                disabled={disabled}
                className="rounded p-0.5 hover:bg-zinc-600/80 text-zinc-400 hover:text-white transition-colors focus:outline-none focus:ring-1 focus:ring-zinc-400 cursor-pointer"
                aria-label={`Remove topic tag ${tag}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-zinc-400 italic">
          No topic tags assigned yet. Add mathematical concepts below to assist categorization.
        </p>
      )}

      {/* Input row with Add button */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 max-w-sm">
          <Input
            type="text"
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value);
              if (error) setError(null);
            }}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            className={`h-9 text-xs bg-[#0A0A0C] rounded-lg text-zinc-100 placeholder:text-zinc-500 shadow-2xs ${
              error
                ? "border-rose-500 focus-visible:ring-rose-500/20"
                : "border-white/[0.12] focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20"
            }`}
            aria-invalid={Boolean(error)}
            aria-errormessage={error ? "tag-editor-error" : undefined}
          />
          <Button
            type="button"
            size="sm"
            onClick={handleAddTag}
            disabled={disabled || !inputValue.trim()}
            className="h-9 px-3 text-xs bg-[#F4F0EA] hover:bg-white active:scale-[0.98] text-[#0A0A0C] font-semibold rounded-lg shrink-0 flex items-center gap-1 cursor-pointer transition-all shadow-sm disabled:opacity-50 border-0"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Add</span>
          </Button>
        </div>

        {/* Validation feedback message */}
        {error && (
          <p
            id="tag-editor-error"
            className="text-[11px] text-rose-400 font-medium flex items-center gap-1 pt-0.5"
            role="alert"
          >
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-rose-400" />
            <span>{error}</span>
          </p>
        )}
      </div>
    </div>
  );
}

export default TagEditor;
