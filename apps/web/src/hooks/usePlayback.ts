import { useQuery } from "@tanstack/react-query";
import type { ChapterOut, PlaybackProgressOut, PlaybackTokenResponse } from "@lecture-platform/shared";
import { api } from "../services/api.js";
import { useAuth } from "../context/AuthContext.js";

export function usePlaybackToken(lectureId: string | undefined, enabled = true) {
  const { isAuthenticated } = useAuth();

  return useQuery<PlaybackTokenResponse>({
    queryKey: ["playbackToken", lectureId],
    queryFn: () => {
      if (!lectureId) throw new Error("Lecture ID required");
      return api.playback.getToken(lectureId);
    },
    enabled: isAuthenticated && !!lectureId && enabled,
    // Refresh token after 12 minutes (token lifetime is 15 minutes)
    staleTime: 12 * 60 * 1000,
    refetchInterval: 12 * 60 * 1000,
  });
}

export function usePlaybackProgress(lectureId: string | undefined, enabled = true) {
  const { isAuthenticated } = useAuth();

  return useQuery<PlaybackProgressOut>({
    queryKey: ["playbackProgress", lectureId],
    queryFn: () => {
      if (!lectureId) throw new Error("Lecture ID required");
      return api.playback.getProgress(lectureId);
    },
    enabled: isAuthenticated && !!lectureId && enabled,
    staleTime: 60 * 1000,
  });
}

export function useChapters(lectureId: string | undefined, enabled = true) {
  const { isAuthenticated } = useAuth();

  return useQuery<ChapterOut[]>({
    queryKey: ["chapters", lectureId],
    queryFn: () => {
      if (!lectureId) throw new Error("Lecture ID required");
      return api.playback.getChapters(lectureId);
    },
    enabled: isAuthenticated && !!lectureId && enabled,
    staleTime: 5 * 60 * 1000,
  });
}
