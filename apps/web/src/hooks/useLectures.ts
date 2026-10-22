import { useQuery } from "@tanstack/react-query";
import type { LectureOut } from "@lecture-platform/shared";
import { api } from "../services/api.js";
import { useAuth } from "../context/AuthContext.js";

export function useLectures(courseId: string | undefined) {
  const { isAuthenticated } = useAuth();

  return useQuery<LectureOut[]>({
    queryKey: ["lectures", courseId],
    queryFn: () => {
      if (!courseId) throw new Error("Course ID required");
      return api.lectures.list(courseId);
    },
    enabled: isAuthenticated && !!courseId,
    staleTime: 30 * 1000,
  });
}
