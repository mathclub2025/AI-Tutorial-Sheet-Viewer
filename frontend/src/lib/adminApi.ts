import { Question, UploadMeta } from "@/lib/types";

// ============================================================================
// SHARED IN-MEMORY MOCK DATA STORE
// NOTE: These are mock implementations designed for testing and development.
// All updates persist in-memory across client navigations within the session,
// but reset on full page reload or server restart.
// No real database persistence or external endpoints are claimed.
// ============================================================================

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export interface BatchListItem {
  batchId: string;
  uploadedAt: string;
  subject: string;
  questionCount: number;
  sheetType: "tutorial" | "pyq";
}

// In-memory batches store (starts clean/empty; populated when question sheets are uploaded)
const mockBatches: BatchListItem[] = [];

// Questions mapped per batch ID (populated when batches are uploaded)
const mockQuestionsByBatch: Record<string, Question[]> = {};

/**
 * MOCK: Upload sheet file and metadata.
 * Registers a new batch and initializes segmented questions in the shared mock store.
 */
export async function uploadSheet(
  file: File,
  meta: UploadMeta
): Promise<{ batchId: string }> {
  await delay(1200);

  const timestamp = Date.now();
  const batchId = `batch_${timestamp}`;

  // Generate initial mock questions for this specific sheet
  const newQuestions: Question[] = [
    {
      id: `${batchId}_q1`,
      subject: meta.subject,
      module: meta.module,
      topics: ["foundational theory", "problem formulation"],
      difficulty: "easy",
      sheetType: meta.sheetType,
      year: meta.year,
      status: "pending",
      questionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Question+1`,
      solutionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Solution+1`,
    },
    {
      id: `${batchId}_q2`,
      subject: meta.subject,
      module: meta.module,
      topics: ["analytical derivation", "formula application"],
      difficulty: "medium",
      sheetType: meta.sheetType,
      year: meta.year,
      status: "pending",
      questionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Question+2`,
      solutionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Solution+2`,
    },
    {
      id: `${batchId}_q3`,
      subject: meta.subject,
      module: meta.module,
      topics: ["advanced problem solving", "edge cases"],
      difficulty: "hard",
      sheetType: meta.sheetType,
      year: meta.year,
      status: "pending",
      questionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Question+3`,
      solutionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Solution+3`,
    },
    {
      id: `${batchId}_q4`,
      subject: meta.subject,
      module: meta.module,
      topics: ["worked examples", "verification"],
      difficulty: "medium",
      sheetType: meta.sheetType,
      year: meta.year,
      status: "pending",
      questionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Question+4`,
      solutionImageUrl: `https://placehold.co/600x400?text=${encodeURIComponent(meta.subject)}+Solution+4`,
    },
  ];

  // Store batch questions
  mockQuestionsByBatch[batchId] = newQuestions;

  // Prepend to mock batches list so newly uploaded batch appears at the top
  const newBatch: BatchListItem = {
    batchId,
    uploadedAt: new Date().toISOString(),
    subject: meta.subject,
    questionCount: newQuestions.length,
    sheetType: meta.sheetType,
  };
  mockBatches.unshift(newBatch);

  return { batchId };
}

/**
 * MOCK: Get processing status of an uploaded sheet batch.
 */
export async function getBatchStatus(
  batchId: string
): Promise<{ status: "processing" | "ready" | "failed" }> {
  await delay(600);
  const exists = Boolean(mockQuestionsByBatch[batchId]);
  return {
    status: exists ? "ready" : "processing",
  };
}

/**
 * MOCK: Retrieve extracted questions for a specific batch.
 */
export async function getBatchQuestions(batchId: string): Promise<Question[]> {
  await delay(600);
  const questions = mockQuestionsByBatch[batchId];
  if (!questions) {
    return [];
  }
  // Return shallow copies to prevent uncoordinated in-place mutations
  return questions.map((q) => ({ ...q, topics: [...q.topics] }));
}

/**
 * MOCK: Update a question's fields or approval status in the shared store.
 */
export async function updateQuestion(
  id: string,
  updates: Partial<Question>
): Promise<Question> {
  await delay(300);

  for (const batchId in mockQuestionsByBatch) {
    const list = mockQuestionsByBatch[batchId];
    const index = list.findIndex((q) => q.id === id);

    if (index !== -1) {
      const existing = list[index];
      const updated: Question = {
        ...existing,
        ...updates,
        id, // ensure ID is preserved
        topics: updates.topics ? [...updates.topics] : [...existing.topics],
      };

      list[index] = updated;
      return { ...updated, topics: [...updated.topics] };
    }
  }

  throw new Error(`Question with ID "${id}" was not found in the mock service.`);
}

/**
 * MOCK: Retrieve list of all uploaded batches.
 */
export async function listBatches(): Promise<BatchListItem[]> {
  await delay(600);
  return mockBatches.map((b) => ({ ...b }));
}
