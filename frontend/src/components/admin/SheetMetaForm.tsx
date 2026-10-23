"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { uploadMetaSchema, type UploadMetaFormValues } from "@/lib/schemas";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Loader2, Upload } from "lucide-react";

interface SheetMetaFormProps {
  onSubmit: (data: UploadMetaFormValues) => void;
  isUploading?: boolean;
}

export function SheetMetaForm({
  onSubmit,
  isUploading = false,
}: SheetMetaFormProps) {
  const form = useForm({
    resolver: zodResolver(uploadMetaSchema),
    defaultValues: {
      subject: "",
      module: 1,
      sheetType: "tutorial" as const,
      year: undefined,
    },
  });

  const sheetType = form.watch("sheetType");

  const handleSubmit = (values: UploadMetaFormValues) => {
    onSubmit(values);
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {/* 1. Subject */}
        <FormField
          control={form.control}
          name="subject"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormLabel className="text-xs font-medium text-zinc-300">
                Subject
              </FormLabel>
              <FormControl>
                <Input
                  placeholder="e.g., Probability & Statistics"
                  className="h-10 border border-white/[0.12] bg-[#0A0A0C] text-sm text-zinc-100 placeholder:text-zinc-500 focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20 rounded-lg transition-colors font-medium"
                  disabled={isUploading}
                  {...field}
                />
              </FormControl>
              <FormMessage className="text-xs text-rose-400" />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* 2. Module */}
          <FormField
            control={form.control}
            name="module"
            render={({ field }) => (
              <FormItem className="space-y-1">
                <FormLabel className="text-xs font-medium text-zinc-300">
                  Module (1–12)
                </FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={1}
                    max={12}
                    placeholder="1"
                    className="h-10 border border-white/[0.12] bg-[#0A0A0C] text-sm text-zinc-100 placeholder:text-zinc-500 focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20 rounded-lg transition-colors font-mono font-medium"
                    disabled={isUploading}
                    value={(field.value as string | number | undefined) ?? ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      field.onChange(val === "" ? "" : Number(val));
                    }}
                  />
                </FormControl>
                <FormMessage className="text-xs text-rose-400" />
              </FormItem>
            )}
          />

          {/* 3. Sheet Type */}
          <FormField
            control={form.control}
            name="sheetType"
            render={({ field }) => (
              <FormItem className="space-y-1">
                <FormLabel className="text-xs font-medium text-zinc-300">
                  Sheet type
                </FormLabel>
                <Select
                  onValueChange={field.onChange}
                  defaultValue={field.value}
                  value={field.value}
                  disabled={isUploading}
                >
                  <FormControl>
                    <SelectTrigger className="h-10 border border-white/[0.12] bg-[#0A0A0C] text-sm text-zinc-100 focus:border-zinc-400 focus:ring-1 focus:ring-zinc-400/20 rounded-lg transition-colors font-medium">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent className="border border-white/[0.1] bg-[#121215] text-zinc-100 rounded-lg shadow-2xl">
                    <SelectItem value="tutorial" className="text-sm cursor-pointer hover:bg-white/[0.06] text-zinc-200 font-medium">
                      Tutorial sheet
                    </SelectItem>
                    <SelectItem value="pyq" className="text-sm cursor-pointer hover:bg-white/[0.06] text-zinc-200 font-medium">
                      Past year question (PYQ)
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage className="text-xs text-rose-400" />
              </FormItem>
            )}
          />
        </div>

        {/* 4. Year (conditionally displayed if sheetType === "pyq") */}
        {sheetType === "pyq" && (
          <FormField
            control={form.control}
            name="year"
            render={({ field }) => (
              <FormItem className="space-y-1">
                <FormLabel className="text-xs font-medium text-zinc-300">
                  Examination year
                </FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="e.g., 2024"
                    className="h-10 border border-white/[0.12] bg-[#0A0A0C] text-sm text-zinc-100 placeholder:text-zinc-500 focus-visible:border-zinc-400 focus-visible:ring-1 focus-visible:ring-zinc-400/20 rounded-lg transition-colors font-mono font-medium"
                    disabled={isUploading}
                    value={(field.value as string | number | undefined) ?? ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      field.onChange(val === "" ? undefined : Number(val));
                    }}
                  />
                </FormControl>
                <FormMessage className="text-xs text-rose-400" />
              </FormItem>
            )}
          />
        )}

        <div className="pt-2">
          <Button
            type="submit"
            className="w-full h-10 bg-[#F4F0EA] hover:bg-white active:scale-[0.99] text-[#0A0A0C] font-semibold text-sm rounded-lg transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-sm border-0"
            disabled={isUploading}
          >
            {isUploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin text-[#0A0A0C]" />
                <span>Uploading & processing...</span>
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                <span>Upload & Process</span>
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}


export default SheetMetaForm;

