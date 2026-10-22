import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "./i18n/index.js";
import { AuthProvider } from "./context/AuthContext.js";
import { Layout } from "./components/Layout.js";
import { ProtectedRoute } from "./components/ProtectedRoute.js";
import { LoginPage } from "./pages/LoginPage.js";
import { CourseListPage } from "./pages/CourseListPage.js";
import { CourseDetailPage } from "./pages/CourseDetailPage.js";
import { LecturePage } from "./pages/LecturePage.js";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />

              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Navigate to="/courses" replace />} />
                <Route path="courses" element={<CourseListPage />} />
                <Route path="courses/:id" element={<CourseDetailPage />} />
                <Route path="lectures/:id" element={<LecturePage />} />
              </Route>

              <Route path="*" element={<Navigate to="/courses" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

export default App;
