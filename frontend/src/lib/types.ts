export interface Question {
  id: string;
  subject: string;
  module: string | number;
  topics: string[];
  difficulty: "easy" | "medium" | "hard" | "unassigned";
  sheetType: "tutorial" | "pyq";
  year?: number;
  status: "pending" | "approved" | "flagged";
  questionImageUrl: string;
  solutionImageUrl: string;
  flagNote?: string;
  revision: number;
  documentId: string;
  documentVersion: string;
  text: string;
  officialSolution?: string;
  solutionStatus?: string;
  solutionAssetId?: string | null;
  solutionDocumentId?: string | null;
  approveSolution?: boolean;
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
