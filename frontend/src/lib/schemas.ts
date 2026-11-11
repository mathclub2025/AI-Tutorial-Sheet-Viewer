import { z } from "zod";

export const uploadMetaSchema = z.object({
  subject: z.string().trim().max(100).min(1, { message: "Subject is required" }),
  module: z.coerce.number().int().min(1, { message: "Module must be at least 1" }).max(12, { message: "Module must be 12 or less" }),
  sheetType: z.enum(["tutorial", "pyq"], { message: "Select a sheet type" }),
  year: z.coerce.number().int().min(1990).max(2100).optional(),
});

export type UploadMetaFormValues = z.infer<typeof uploadMetaSchema>;
