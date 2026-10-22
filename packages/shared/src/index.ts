/**
 * Shared TypeScript types and API Client for AI Lecture Platform.
 * Reflects docs/schema.sql, docs/api.md, and OpenAPI specifications.
 */

export * from "./client.js";
export type * from "./schema.js";

// Legacy camelCase interfaces maintained for backwards compatibility
export interface LegacyUser {
  id: string;
  email: string;
  name: string;
  role: "student" | "professor" | "admin";
  isActive: boolean;
  createdAt: string;
}

export interface LegacyCourse {
  id: string;
  code: string;
  title: string;
  description: string | null;
  term: string | null;
  isArchived: boolean;
  createdAt: string;
}

export interface LegacyLecture {
  id: string;
  courseId: string;
  title: string;
  description: string | null;
  status: "uploaded" | "processing" | "ready" | "failed";
  durationMs: number | null;
  language: string | null;
  published: boolean;
  position: number;
  createdAt: string;
}
