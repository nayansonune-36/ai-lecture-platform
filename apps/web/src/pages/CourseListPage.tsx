import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useCourses } from "../hooks/useCourses.js";
import { useAuth } from "../context/AuthContext.js";
import { useTranslation } from "../i18n/index.js";
import { CreateCourseModal } from "../components/CreateCourseModal.js";

export function CourseListPage() {
  const { user } = useAuth();
  const { data: courses, isLoading, error, refetch } = useCourses();
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const isProfessorOrAdmin = user?.role === "professor" || user?.role === "admin";

  const filteredCourses = useMemo(() => {
    if (!courses) return [];
    if (!searchQuery.trim()) return courses;
    const q = searchQuery.toLowerCase();
    return courses.filter(
      (c) =>
        c.code.toLowerCase().includes(q) ||
        c.title.toLowerCase().includes(q) ||
        (c.description && c.description.toLowerCase().includes(q))
    );
  }, [courses, searchQuery]);

  if (isLoading) {
    return (
      <div className="state-container">
        <div className="spinner" />
        <p>{t("common.loading")}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="state-container error-state">
        <p className="error-text">{t("common.error")}</p>
        <button type="button" onClick={() => refetch()} className="btn btn-secondary">
          {t("common.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("courses.title")}</h1>
          <p className="page-subtitle">{t("courses.subtitle")}</p>
        </div>

        <div className="header-actions-group">
          <div className="search-bar-wrapper">
            <svg className="search-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="search"
              className="search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("courses.search_placeholder")}
              aria-label={t("courses.search_placeholder")}
            />
          </div>

          {isProfessorOrAdmin && (
            <button
              type="button"
              className="btn btn-primary create-course-btn"
              onClick={() => setShowCreateModal(true)}
            >
              + {t("professor.create_course")}
            </button>
          )}
        </div>
      </div>

      {filteredCourses.length === 0 ? (
        <div className="empty-state">
          <svg className="empty-icon" viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <p>{t("courses.empty")}</p>
        </div>
      ) : (
        <div className="courses-grid">
          {filteredCourses.map((course) => (
            <article key={course.id} className="course-card">
              <div className="course-card-header">
                <span className="course-code-badge">{course.code}</span>
                {course.term && <span className="course-term-badge">{course.term}</span>}
              </div>

              <h2 className="course-title">{course.title}</h2>
              {course.description && (
                <p className="course-description">{course.description}</p>
              )}

              <div className="course-card-footer">
                <Link
                  to={`/courses/${course.id}`}
                  className="btn btn-primary course-action-btn"
                >
                  {t("courses.view_course")}
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="5" y1="12" x2="19" y2="12" />
                    <polyline points="12 5 19 12 12 19" />
                  </svg>
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}

      {isProfessorOrAdmin && (
        <CreateCourseModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
        />
      )}
    </div>
  );
}
