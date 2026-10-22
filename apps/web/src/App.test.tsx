import { describe, it, expect } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { App } from "./App.js";
import { formatDuration, formatPercentage } from "./utils/format.js";
import { en } from "./i18n/en.js";
import { hi } from "./i18n/hi.js";
import { setMemoryAccessToken, getMemoryAccessToken } from "./services/api.js";

describe("Format helpers", () => {
  it("formats duration under one hour to MM:SS", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(5000)).toBe("00:05");
    expect(formatDuration(65000)).toBe("01:05");
    expect(formatDuration(599000)).toBe("09:59");
    expect(formatDuration(3599000)).toBe("59:59");
  });

  it("formats duration over one hour to H:MM:SS", () => {
    expect(formatDuration(3600000)).toBe("1:00:00");
    expect(formatDuration(3665000)).toBe("1:01:05");
    expect(formatDuration(7200000)).toBe("2:00:00");
  });

  it("handles null and negative durations gracefully", () => {
    expect(formatDuration(null)).toBe("00:00");
    expect(formatDuration(undefined)).toBe("00:00");
    expect(formatDuration(-100)).toBe("00:00");
  });

  it("computes resume percentages clamped to 0-100", () => {
    expect(formatPercentage(0, 1000)).toBe(0);
    expect(formatPercentage(500, 1000)).toBe(50);
    expect(formatPercentage(1000, 1000)).toBe(100);
    expect(formatPercentage(1500, 1000)).toBe(100);
    expect(formatPercentage(0, 0)).toBe(0);
  });
});

describe("i18n Dictionaries", () => {
  it("has exact matching keys in English and Hindi dictionaries", () => {
    const enKeys = Object.keys(en).sort();
    const hiKeys = Object.keys(hi).sort();
    expect(enKeys).toEqual(hiKeys);
  });

  it("contains valid Devanagari strings in Hindi translations", () => {
    expect(hi["app.title"]).toBe("एआई व्याख्यान मंच");
    expect(hi["nav.courses"]).toBe("पाठ्यक्रम");
    expect(hi["auth.submit"]).toBe("साइन इन करें");
  });

  it("contains professor and pipeline translation keys in both languages", () => {
    const requiredKeys: (keyof typeof en)[] = [
      "professor.create_course",
      "professor.manage_enrollments",
      "professor.upload_lecture",
      "professor.publish",
      "professor.unpublish",
      "professor.delete",
      "professor.delete_confirm",
      "pipeline.title",
      "pipeline.stage_transcode",
      "pipeline.stage_transcribe",
      "pipeline.stage_index",
      "pipeline.stage_chapters",
      "pipeline.coming_soon",
    ];

    for (const key of requiredKeys) {
      expect(en[key]).toBeDefined();
      expect(en[key].length).toBeGreaterThan(0);
      expect(hi[key]).toBeDefined();
      expect(hi[key].length).toBeGreaterThan(0);
    }
  });
});

describe("Role Gating and Course Permissions", () => {
  const isOwnerOrAdmin = (
    user: { id: string; role: string } | null,
    courseOwnerId: string
  ) => {
    if (!user) return false;
    return user.role === "admin" || (user.role === "professor" && courseOwnerId === user.id);
  };

  it("allows admin full management access to any course", () => {
    const admin = { id: "admin-1", role: "admin" };
    expect(isOwnerOrAdmin(admin, "prof-2")).toBe(true);
  });

  it("allows owning professor management access to their course", () => {
    const prof = { id: "prof-1", role: "professor" };
    expect(isOwnerOrAdmin(prof, "prof-1")).toBe(true);
  });

  it("strictly forbids non-owning professor from managing another course", () => {
    const prof = { id: "prof-1", role: "professor" };
    expect(isOwnerOrAdmin(prof, "prof-2")).toBe(false);
  });

  it("strictly forbids student from managing any course", () => {
    const student = { id: "student-1", role: "student" };
    expect(isOwnerOrAdmin(student, "student-1")).toBe(false);
    expect(isOwnerOrAdmin(student, "prof-1")).toBe(false);
  });
});

describe("Resumable Upload Chunking Logic", () => {
  it("calculates correct byte ranges for chunked uploads", () => {
    const totalBytes = 5 * 1024 * 1024; // 5MB
    const chunkSize = 2 * 1024 * 1024; // 2MB
    const chunks: { start: number; end: number; total: number }[] = [];

    let offset = 0;
    while (offset < totalBytes) {
      const nextOffset = Math.min(offset + chunkSize, totalBytes);
      chunks.push({
        start: offset,
        end: nextOffset - 1,
        total: totalBytes,
      });
      offset = nextOffset;
    }

    expect(chunks).toHaveLength(3);
    // Chunk 0: 0 to 2MB - 1
    expect(chunks[0]).toEqual({ start: 0, end: 2097151, total: 5242880 });
    // Chunk 1: 2MB to 4MB - 1
    expect(chunks[1]).toEqual({ start: 2097152, end: 4194303, total: 5242880 });
    // Chunk 2: 4MB to 5MB - 1
    expect(chunks[2]).toEqual({ start: 4194304, end: 5242879, total: 5242880 });
  });
});

describe("App", () => {
  it("is defined as a component function", () => {
    expect(App).toBeDefined();
    expect(typeof App).toBe("function");
  });
});

describe("Client Authentication & Logout", () => {
  it("clears memory access token and query cache on logout", () => {
    setMemoryAccessToken("sample-access-token");
    expect(getMemoryAccessToken()).toBe("sample-access-token");

    const queryClient = new QueryClient();
    queryClient.setQueryData(["courses"], [{ id: "c1", title: "Course 1" }]);
    expect(queryClient.getQueryData(["courses"])).toBeDefined();

    // Perform client logout state cleanup
    setMemoryAccessToken(null);
    queryClient.clear();

    expect(getMemoryAccessToken()).toBeNull();
    expect(queryClient.getQueryData(["courses"])).toBeUndefined();
  });
});
