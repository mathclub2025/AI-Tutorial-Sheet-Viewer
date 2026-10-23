export interface Question {
  id: string;
  subject: string;
  module: number;
  topics: string[];
  difficulty: "easy" | "medium" | "hard";
  sheetType: "tutorial" | "pyq";
  year?: number;
  status: "pending" | "approved" | "flagged";
  questionImageUrl: string;
  solutionImageUrl: string;
  flagNote?: string;
}

export interface UploadMeta {
  subject: string;
  module: number;
  sheetType: "tutorial" | "pyq";
  year?: number;
}

export interface UploadBatch {
  batchId: string;
  status: "processing" | "ready" | "failed";
  questions: Question[];
}
