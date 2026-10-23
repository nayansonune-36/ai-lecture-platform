import { useState, useEffect, useCallback } from "react";
import { desktopService } from "../services/desktopService.js";
import type { CourseWithLectures, DownloadedLecture } from "../types.js";

export function useLibrary(isLoggedIn: boolean) {
  const [courses, setCourses] = useState<CourseWithLectures[]>([]);
  const [downloaded, setDownloaded] = useState<DownloadedLecture[]>([]);
  const [activeTab, setActiveTab] = useState<"available" | "downloaded">("available");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!isLoggedIn) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [coursesData, downloadedData] = await Promise.all([
        desktopService.getEnrolledCoursesAndLectures(),
        desktopService.getDownloadedLectures(),
      ]);
      setCourses(coursesData);
      setDownloaded(downloadedData);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [isLoggedIn]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    courses,
    downloaded,
    activeTab,
    setActiveTab,
    loading,
    error,
    refresh,
  };
}
