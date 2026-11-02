import { z } from "zod";

export const uploadMetaSchema = z.object({
  subject: z.string().min(1, { message: "Subject is required" }),
  module: z.coerce.number().min(1, { message: "Module must be at least 1" }).max(12, { message: "Module must be 12 or less" }),
  sheetType: z.enum(["tutorial", "pyq"], { message: "Select a sheet type" }),
  year: z.coerce.number().optional(),
});

export type UploadMetaFormValues = z.infer<typeof uploadMetaSchema>;
