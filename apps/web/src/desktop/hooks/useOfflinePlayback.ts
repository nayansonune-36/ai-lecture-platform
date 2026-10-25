import { useState, useEffect, useCallback, useRef } from "react";
import { desktopService } from "../services/desktopService.js";
import type { OfflinePlaybackInfo, ChapterItem } from "../types.js";
import type { HlsPlayerRef } from "../../components/HlsPlayer.js";

export function useOfflinePlayback(lectureId: string) {
  const [playbackInfo, setPlaybackInfo] = useState<OfflinePlaybackInfo | null>(null);
  const [chapters, setChapters] = useState<ChapterItem[]>([]);
  const [activeChapterIndex, setActiveChapterIndex] = useState<number>(-1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    let isCancelled = false;

    async function loadPlaybackData() {
      setLoading(true);
      setError(null);
      try {
        const info = await desktopService.getOfflinePlaybackInfo(lectureId);
        if (isCancelled || !mountedRef.current) return;
        setPlaybackInfo(info);

        if (info.chapters_url) {
          try {
            const res = await fetch(info.chapters_url);
            if (res.ok) {
              const data = await res.json();
              if (Array.isArray(data) && mountedRef.current && !isCancelled) {
                setChapters(data);
              }
            }
          } catch {
            // Chapters fetch optional
          }
        }
      } catch (err) {
        if (!isCancelled && mountedRef.current) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!isCancelled && mountedRef.current) {
          setLoading(false);
        }
      }
    }

    void loadPlaybackData();

    return () => {
      isCancelled = true;
      mountedRef.current = false;
    };
  }, [lectureId]);

  const handleProgressUpdate = useCallback(
    (positionMs: number, completed: boolean) => {
      void desktopService.saveOfflineProgress(lectureId, positionMs, completed);

      if (chapters.length > 0) {
        let activeIdx = -1;
        for (let i = 0; i < chapters.length; i++) {
          if (positionMs >= chapters[i].start_ms) {
            activeIdx = i;
          }
        }
        setActiveChapterIndex(activeIdx);
      }
    },
    [lectureId, chapters]
  );

  const seekToChapter = useCallback(
    (playerRef: React.RefObject<HlsPlayerRef | null>, startMs: number, index: number) => {
      if (playerRef.current) {
        playerRef.current.seekTo(startMs / 1000);
        setActiveChapterIndex(index);
      }
    },
    []
  );

  return {
    playbackInfo,
    chapters,
    activeChapterIndex,
    loading,
    error,
    handleProgressUpdate,
    seekToChapter,
  };
}
