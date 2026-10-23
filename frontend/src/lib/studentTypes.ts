/** Shapes mirror the JSON the segmentation pipeline will emit for the student practice portal. */

export type SourceType = "Tutorial" | "PYQ";

export interface SolutionStep {
  title: string;
  body: string;
}

export interface Question {
  id: string;
  subject: string;
  module: string;
  topics: string[];
  keywords: string[];
  source: { type: SourceType; label: string; year?: number };
  marks?: number;
  difficulty: "Easy" | "Medium" | "Hard";
  /** URL of the cropped question image. Falls back to `text` rendering when absent. */
  imageUrl?: string;
  text: string[];
  table?: { head: string[]; rows: string[][] };
  /** URL of the cropped solution image. Falls back to `steps` when absent. */
  solutionImageUrl?: string;
  steps: SolutionStep[];
  answer: string;
}

export type StudentQuestion = Question;

export interface SearchResult {
  subject: string | null;
  topics: string[];
  questions: Question[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  result?: SearchResult;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  pinned?: boolean;
  projectId?: string;
  messages: Message[];
}

export interface Project {
  id: string;
  name: string;
}

export type SourceFilter = "all" | SourceType;

export interface Settings {
  name: string;
  /** Profile photo as a small data URL, kept in localStorage only. */
  avatar?: string;
  theme: "system" | "light" | "dark";
  perPage: 3 | 5 | 8;
  sourceFilter: SourceFilter;
  showMeta: boolean;
  confirmReveal: boolean;
  compact: boolean;
}
