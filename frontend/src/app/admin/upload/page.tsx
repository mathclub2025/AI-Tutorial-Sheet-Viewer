"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { SheetMetaForm } from "@/components/admin/SheetMetaForm";
import { UploadDropzone } from "@/components/admin/UploadDropzone";
import { AdminAuthGuard } from "@/components/admin/AdminAuthGuard";
import { uploadSheet } from "@/lib/adminApi";
import type { UploadMetaFormValues } from "@/lib/schemas";
import {
  AlertCircle,
  ArrowRight,
  RotateCcw,
  CheckCircle2,
} from "lucide-react";

export default function UploadPage() {
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [isUploading, setIsUploading] = React.useState<boolean>(false);
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [successBatchId, setSuccessBatchId] = React.useState<string | null>(null);

  const handleFileSelect = (file: File | null) => {
    setSelectedFile(file);
    if (file) {
      setUploadError(null);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setUploadError(null);
    setSuccessBatchId(null);
  };

  const handleSubmit = async (formData: UploadMetaFormValues) => {
    if (!selectedFile) {
      const errorMsg = "Please upload or select a question sheet file first.";
      setUploadError(errorMsg);
      toast.error(errorMsg);
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    setSuccessBatchId(null);

    try {
      const response = await uploadSheet(selectedFile, formData);
      setSuccessBatchId(response.batchId);
      toast.success("Sheet uploaded successfully.");
    } catch (err) {
      console.error("Upload failed:", err);
      const errorMsg = "An error occurred while uploading. Please check the file and try again.";
      setUploadError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <AdminAuthGuard>
      <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0">
        <div className="max-w-5xl mx-auto space-y-6 sm:space-y-8">
          {/* 1. Page Heading */}
          <div className="border-b border-white/[0.08] pb-5">
            <h1 className="font-serif-heading text-2xl sm:text-3xl text-white font-bold tracking-tight">
              Upload Question Sheet
            </h1>
            <p className="text-sm text-zinc-400 mt-1.5 max-w-2xl leading-relaxed">
              Upload a question paper and enter its academic details to begin question extraction.
            </p>
          </div>

          {/* 2. Feedback Banners */}
          {uploadError && (
            <div className="flex items-start gap-3 p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 backdrop-blur-sm shadow-2xl shadow-black/60">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-rose-400" />
              <div className="text-sm">
                <p className="font-semibold text-rose-200">Upload incomplete</p>
                <p className="mt-0.5 text-xs text-rose-300">{uploadError}</p>
              </div>
            </div>
          )}

          {successBatchId && (
            <div className="rounded-xl border border-emerald-800/40 bg-emerald-950/40 backdrop-blur-sm p-4 sm:p-5 shadow-2xl shadow-black/60">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-lg bg-zinc-800/80 border border-white/[0.08] text-emerald-400 flex items-center justify-center shrink-0 shadow-xs">
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-emerald-300">
                      Question sheet uploaded
                    </h3>
                    <p className="text-xs text-zinc-400 mt-0.5">
                      Batch ID: <span className="font-mono text-white font-semibold">{successBatchId}</span>
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2.5 shrink-0">
                  <button
                    type="button"
                    onClick={handleReset}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.08] bg-zinc-800 text-xs font-medium text-zinc-300 hover:text-white hover:bg-zinc-700 active:scale-[0.98] transition-all cursor-pointer shadow-xs"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    <span>Upload another</span>
                  </button>
                  <Link
                    href={`/admin/review/${successBatchId}`}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#F4F0EA] hover:bg-white active:scale-[0.98] text-[#0A0A0C] text-xs font-semibold transition-all shadow-sm"
                  >
                    <span>Open review batch</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              </div>
            </div>
          )}

          {/* 3. Main Workspace: Question paper and Sheet details */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-start">
            {/* Left: Question paper upload */}
            <div className="lg:col-span-7 space-y-3">
              <div>
                <h2 className="text-sm font-semibold text-zinc-200">
                  Question paper
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  PDF document or scanned image of the question paper.
                </p>
              </div>

              <UploadDropzone
                onFileSelect={handleFileSelect}
                selectedFile={selectedFile}
              />
            </div>

            {/* Right: Sheet details */}
            <div className="lg:col-span-5 space-y-3">
              <div>
                <h2 className="text-sm font-semibold text-zinc-200">
                  Sheet details
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Academic subject and classification taxonomy.
                </p>
              </div>

              <div className="bg-[#121215]/90 backdrop-blur-md rounded-xl border border-white/[0.08] p-5 sm:p-6 shadow-2xl shadow-black/60">
                <SheetMetaForm
                  onSubmit={handleSubmit}
                  isUploading={isUploading}
                />
              </div>
            </div>
          </div>
        </div>
      </main>
    </AdminAuthGuard>
  );
}


