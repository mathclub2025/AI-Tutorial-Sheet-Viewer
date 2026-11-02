"use client";

import * as React from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { Button } from "@/components/ui/button";
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Trash2,
} from "lucide-react";

interface UploadDropzoneProps {
  onFileSelect: (file: File | null) => void;
  selectedFile?: File | null;
}

const MAX_FILE_SIZE = 15 * 1024 * 1024; // 15MB

const ACCEPTED_FILE_TYPES = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
};

export function UploadDropzone({
  onFileSelect,
  selectedFile: externalSelectedFile,
}: UploadDropzoneProps) {
  const [internalFile, setInternalFile] = React.useState<File | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Sync with external selectedFile if provided
  const currentFile = externalSelectedFile !== undefined ? externalSelectedFile : internalFile;

  const onDrop = React.useCallback(
    (acceptedFiles: File[], fileRejections: FileRejection[]) => {
      if (fileRejections.length > 0) {
        const firstError = fileRejections[0].errors[0];
        let message = "Invalid file";

        if (firstError?.code === "file-invalid-type") {
          message = "Only PDF, PNG, or JPG files are allowed";
        } else if (firstError?.code === "file-too-large") {
          message = "File exceeds maximum size limit (15MB)";
        } else if (firstError?.message) {
          message = firstError.message;
        }

        setErrorMessage(message);
        setInternalFile(null);
        onFileSelect(null);
        return;
      }

      if (acceptedFiles.length > 0) {
        const file = acceptedFiles[0];
        setInternalFile(file);
        setErrorMessage(null);
        onFileSelect(file);
      }
    },
    [onFileSelect]
  );

  const handleRemove = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setInternalFile(null);
    setErrorMessage(null);
    onFileSelect(null);
  };

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: ACCEPTED_FILE_TYPES,
    maxSize: MAX_FILE_SIZE,
    multiple: false,
    noClick: !!currentFile,
  });

  const fileSizeMB = currentFile
    ? (currentFile.size / (1024 * 1024)).toFixed(2)
    : null;

  const isPdf = currentFile?.name.toLowerCase().endsWith(".pdf");

  return (
    <div className="w-full space-y-3">
      {!currentFile ? (
        <div
          {...getRootProps()}
          className={`group flex flex-col items-center justify-center p-8 sm:p-12 min-h-[220px] border border-dashed rounded-xl cursor-pointer transition-all duration-200 text-center select-none backdrop-blur-sm shadow-2xl shadow-black/60 ${
            isDragActive
              ? "border-white/40 bg-[#16161A]"
              : "bg-[#121215]/60 hover:bg-[#16161A]/80 border-white/[0.15] hover:border-white/[0.3] text-zinc-200"
          }`}
        >
          <input {...getInputProps()} />

          <div className="w-12 h-12 rounded-xl bg-zinc-800/80 border border-white/[0.1] flex items-center justify-center text-zinc-200 mb-3 shadow-xs group-hover:scale-105 group-hover:border-white/[0.2] transition-all">
            <Upload className="h-5 w-5" />
          </div>

          <p className="text-sm font-semibold text-zinc-100 group-hover:text-white transition-colors">
            Choose a question paper or drag and drop
          </p>

          <p className="text-xs text-zinc-400 mt-1">
            PDF, PNG, or JPG up to 15 MB
          </p>
        </div>
      ) : (
        <div className="border border-white/[0.08] rounded-xl bg-[#121215]/90 backdrop-blur-md p-4 space-y-3 shadow-2xl shadow-black/60">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-lg bg-zinc-800/80 border border-white/[0.1] flex items-center justify-center text-zinc-200 shrink-0 shadow-xs">
                <FileText className="h-5 w-5 text-zinc-200" />
              </div>

              <div className="min-w-0">
                <p className="font-semibold text-sm text-zinc-100 truncate" title={currentFile.name}>
                  {currentFile.name}
                </p>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-zinc-400">
                  <span className="font-mono">{fileSizeMB} MB</span>
                  <span>•</span>
                  <span>{isPdf ? "PDF document" : "Image file"}</span>
                </div>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-950/40 text-emerald-300 border border-emerald-800/40 shrink-0">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span>Ready</span>
            </span>
          </div>

          <div className="flex items-center justify-between pt-3 border-t border-white/[0.08] text-xs">
            <button
              type="button"
              onClick={open}
              className="inline-flex items-center gap-1.5 font-medium text-[#E2B86B] hover:text-[#F3CE85] active:scale-[0.98] transition-all cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Choose different file</span>
            </button>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleRemove}
              className="h-7 px-2 text-xs text-zinc-400 hover:text-rose-400 hover:bg-rose-950/20 active:scale-[0.98] rounded-md transition-all cursor-pointer shadow-none"
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              <span>Remove</span>
            </Button>
          </div>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-center gap-2 p-3 text-xs rounded-md bg-rose-950/60 text-rose-300 border border-rose-800/80">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
}


export default UploadDropzone;

