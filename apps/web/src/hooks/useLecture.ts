import { useQuery } from "@tanstack/react-query";
import type { LectureOut } from "@lecture-platform/shared";
import { api } from "../services/api.js";
import { useAuth } from "../context/AuthContext.js";

export function useLecture(lectureId: string | undefined) {
  const { isAuthenticated } = useAuth();

  return useQuery<LectureOut>({
    queryKey: ["lecture", lectureId],
    queryFn: () => {
      if (!lectureId) throw new Error("Lecture ID is required");
      return api.lectures.get(lectureId);
    },
    enabled: isAuthenticated && !!lectureId,
    staleTime: 30 * 1000,
  });
}
