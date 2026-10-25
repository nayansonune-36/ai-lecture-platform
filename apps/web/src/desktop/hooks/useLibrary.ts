import { useState, useEffect, useCallback, useRef } from "react";
import { desktopService } from "../services/desktopService.js";
import type {
  CourseWithLectures,
  DownloadRecord,
  DownloadProgressEvent,
} from "../types.js";

export function useLibrary(isLoggedIn: boolean) {
  const [courses, setCourses] = useState<CourseWithLectures[]>([]);
  const [downloadRecords, setDownloadRecords] = useState<Record<string, DownloadRecord>>({});
  const [estimates, setEstimates] = useState<Record<string, number>>({});
  const [activeProgress, setActiveProgress] = useState<Record<string, DownloadProgressEvent>>({});
  const [activeTab, setActiveTab] = useState<"available" | "downloaded">("available");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mountedRef = useRef(true);

  const refreshDownloads = useCallback(async () => {
    try {
      const records = await desktopService.listDownloads();
      const mapping: Record<string, DownloadRecord> = {};
      for (const rec of records) {
        mapping[rec.lecture_id] = rec;
      }
      if (mountedRef.current) {
        setDownloadRecords(mapping);
      }
    } catch {
      // Ignored if offline or DB busy
    }
  }, []);

  const loadEstimate = useCallback(
    async (lectureId: string, rendition: number = 480) => {
      if (estimates[lectureId] !== undefined) {
        return;
      }
      try {
        const est = await desktopService.getOfflineEstimate(lectureId, rendition);
        if (mountedRef.current && est > 0) {
          setEstimates((prev) => ({ ...prev, [lectureId]: est }));
        }
      } catch {
        // Silently skip if estimate fails (e.g. server offline)
      }
    },
    [estimates]
  );

  const refresh = useCallback(async () => {
    if (!isLoggedIn) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [coursesData, records] = await Promise.all([
        desktopService.getEnrolledCoursesAndLectures().catch(() => []),
        desktopService.listDownloads().catch(() => []),
      ]);

      const mapping: Record<string, DownloadRecord> = {};
      for (const rec of records) {
        mapping[rec.lecture_id] = rec;
      }

      if (mountedRef.current) {
        setCourses(coursesData);
        setDownloadRecords(mapping);
      }

      // Fetch size estimates for lectures in background
      for (const course of coursesData) {
        for (const lec of course.lectures) {
          if (lec.status === "ready") {
            void loadEstimate(lec.id, 480);
          }
        }
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [isLoggedIn, loadEstimate]);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  // Subscribe to Tauri download progress events
  useEffect(() => {
    let unlisten: (() => void) | undefined;

    const setupListener = async () => {
      unlisten = await desktopService.onDownloadProgress((event) => {
        if (!mountedRef.current) return;
        setActiveProgress((prev) => ({
          ...prev,
          [event.lecture_id]: event,
        }));

        if (event.state === "completed" || event.state === "failed" || event.state === "paused") {
          void refreshDownloads();
        }
      });
    };

    void setupListener();

    return () => {
      try {
        if (unlisten) {
          unlisten();
        }
      } catch {
        // Safe ignore
      }
    };
  }, [refreshDownloads]);

  const startDownload = useCallback(
    async (
      lectureId: string,
      rendition: number = 480,
      lectureTitle?: string,
      courseTitle?: string
    ) => {
      setError(null);
      try {
        await desktopService.startDownload(lectureId, rendition, lectureTitle, courseTitle);
        void refreshDownloads();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refreshDownloads]
  );

  const pauseDownload = useCallback(
    async (lectureId: string) => {
      try {
        await desktopService.pauseDownload(lectureId);
        void refreshDownloads();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refreshDownloads]
  );

  const resumeDownload = useCallback(
    async (lectureId: string) => {
      try {
        await desktopService.resumeDownload(lectureId);
        void refreshDownloads();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refreshDownloads]
  );

  const cancelDownload = useCallback(
    async (lectureId: string) => {
      try {
        await desktopService.cancelDownload(lectureId);
        setActiveProgress((prev) => {
          const next = { ...prev };
          delete next[lectureId];
          return next;
        });
        void refreshDownloads();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refreshDownloads]
  );

  const deleteDownload = useCallback(
    async (lectureId: string) => {
      try {
        await desktopService.deleteDownload(lectureId);
        setDownloadRecords((prev) => {
          const next = { ...prev };
          delete next[lectureId];
          return next;
        });
        setActiveProgress((prev) => {
          const next = { ...prev };
          delete next[lectureId];
          return next;
        });
        void refreshDownloads();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refreshDownloads]
  );

  const downloadedList = Object.values(downloadRecords).filter(
    (d) => d.status === "completed"
  );

  return {
    courses,
    downloadRecords,
    downloaded: downloadedList,
    estimates,
    activeProgress,
    activeTab,
    setActiveTab,
    loading,
    error,
    refresh,
    loadEstimate,
    startDownload,
    pauseDownload,
    resumeDownload,
    cancelDownload,
    deleteDownload,
  };
}
