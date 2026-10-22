import { useQuery } from "@tanstack/react-query";
import type { CourseOut } from "@lecture-platform/shared";
import { api } from "../services/api.js";
import { useAuth } from "../context/AuthContext.js";

export function useCourses() {
  const { isAuthenticated } = useAuth();

  return useQuery<CourseOut[]>({
    queryKey: ["courses"],
    queryFn: () => api.courses.list(),
    enabled: isAuthenticated,
    staleTime: 60 * 1000,
  });
}
