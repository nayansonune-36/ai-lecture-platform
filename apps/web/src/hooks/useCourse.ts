import { useQuery } from "@tanstack/react-query";
import type { CourseOut } from "@lecture-platform/shared";
import { api } from "../services/api.js";
import { useAuth } from "../context/AuthContext.js";

export function useCourse(courseId: string | undefined) {
  const { isAuthenticated } = useAuth();

  return useQuery<CourseOut>({
    queryKey: ["course", courseId],
    queryFn: () => {
      if (!courseId) throw new Error("Course ID required");
      return api.courses.get(courseId);
    },
    enabled: isAuthenticated && !!courseId,
    staleTime: 60 * 1000,
  });
}
