import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { useCourse } from "../hooks/useCourse.js";
import { useLectures } from "../hooks/useLectures.js";
import { useAuth } from "../context/AuthContext.js";
import { useTranslation } from "../i18n/index.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { ProgressBar } from "../components/ProgressBar.js";
import { ManageEnrollmentsModal } from "../components/ManageEnrollmentsModal.js";
import { UploadLectureModal } from "../components/UploadLectureModal.js";
import { PipelineStatusPanel } from "../components/PipelineStatusPanel.js";
import { formatDuration } from "../utils/format.js";
import { api } from "../services/api.js";

export function CourseDetailPage() {
  const { id: courseId } = useParams<{ id: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  const { data: course, isLoading: courseLoading, error: courseError } = useCourse(courseId);
  const { data: lectures, isLoading: lecturesLoading, error: lecturesError, refetch } = useLectures(courseId);

  const [isEnrollmentsOpen, setIsEnrollmentsOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [expandedPipelineLectureId, setExpandedPipelineLectureId] = useState<string | null>(null);

  const isOwnerOrAdmin =
    user?.role === "admin" || (user?.role === "professor" && course?.owner_id === user?.id);

  const togglePublishMutation = useMutation({
    mutationFn: async ({ id, published }: { id: string; published: boolean }) => {
      return api.lectures.update(id, { published });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lectures", courseId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      return api.lectures.delete(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lectures", courseId] });
    },
  });

  const handleTogglePublish = (lectureId: string, currentPublished: boolean) => {
    togglePublishMutation.mutate({ id: lectureId, published: !currentPublished });
  };

  const handleDeleteLecture = (lectureId: string) => {
    if (window.confirm(t("professor.delete_confirm"))) {
      deleteMutation.mutate(lectureId);
    }
  };

  if (courseLoading || lecturesLoading) {
    return (
      <div className="state-container">
        <div className="spinner" />
        <p>{t("common.loading")}</p>
      </div>
    );
  }

  if (courseError || !course) {
    return (
      <div className="state-container error-state">
        <p className="error-text">{t("common.error")}</p>
        <Link to="/courses" className="btn btn-secondary">
          {t("lectures.back")}
        </Link>
      </div>
    );
  }

  return (
    <div className="page-container">
      <nav className="breadcrumb-nav">
        <Link to="/courses" className="breadcrumb-link">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          {t("lectures.back")}
        </Link>
      </nav>

      <section className="course-hero">
        <div className="course-hero-header">
          <div className="course-hero-badges">
            <span className="course-code-badge">{course.code}</span>
            {course.term && <span className="course-term-badge">{course.term}</span>}
          </div>
          {isOwnerOrAdmin && (
            <div className="hero-action-btns">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setIsEnrollmentsOpen(true)}
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                {t("professor.manage_enrollments")}
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setIsUploadOpen(true)}
              >
                + {t("professor.upload_lecture")}
              </button>
            </div>
          )}
        </div>
        <h1 className="course-hero-title">{course.title}</h1>
        {course.description && (
          <p className="course-hero-description">{course.description}</p>
        )}
      </section>

      <section className="lectures-section">
        <div className="section-header">
          <h2 className="section-title">
            {t("lectures.title")}
            {lectures && <span className="item-count">({lectures.length})</span>}
          </h2>
          {isOwnerOrAdmin && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => setIsUploadOpen(true)}
            >
              + {t("professor.upload_lecture")}
            </button>
          )}
        </div>

        {lecturesError && (
          <div className="error-banner">
            <p>{t("common.error")}</p>
            <button type="button" onClick={() => refetch()} className="btn btn-secondary btn-sm">
              {t("common.retry")}
            </button>
          </div>
        )}

        {!lectures || lectures.length === 0 ? (
          <div className="empty-state">
            <svg className="empty-icon" viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.5">
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            <p>{t("lectures.empty")}</p>
          </div>
        ) : (
          <div className="lectures-grid">
            {lectures.map((lecture) => {
              // Simulated position or playback resume position (0 if unstarted)
              const positionMs = 0;
              const durationMs = lecture.duration_ms ?? 0;
              const hasStarted = positionMs > 0;
              const posterSrc = lecture.poster_path ? `/media/${lecture.poster_path}` : null;

              return (
                <article key={lecture.id} className="lecture-card">
                  <div className="lecture-thumbnail-wrapper">
                    {posterSrc ? (
                      <img
                        src={posterSrc}
                        alt={lecture.title}
                        className="lecture-poster-img"
                        loading="lazy"
                        onError={(e) => {
                          // Replace broken image with fallback placeholder
                          (e.currentTarget as HTMLElement).style.display = "none";
                          const fallback = e.currentTarget.nextElementSibling as HTMLElement | null;
                          if (fallback) fallback.style.display = "flex";
                        }}
                      />
                    ) : null}

                    <div
                      className="lecture-poster-fallback"
                      style={{ display: posterSrc ? "none" : "flex" }}
                    >
                      <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <polygon points="5 3 19 12 5 21 5 3" />
                      </svg>
                    </div>

                    {durationMs > 0 && (
                      <span className="duration-pill">
                        {formatDuration(durationMs)}
                      </span>
                    )}

                    {/* Overlay progress on bottom of thumbnail */}
                    <div className="thumbnail-progress-overlay">
                      <ProgressBar
                        positionMs={positionMs}
                        durationMs={durationMs}
                      />
                    </div>
                  </div>

                  <div className="lecture-card-body">
                    <div className="lecture-header-meta">
                      <span className="lecture-position">#{lecture.position + 1}</span>
                      <StatusBadge status={lecture.status} published={lecture.published} />
                    </div>

                    <h3 className="lecture-title">{lecture.title}</h3>
                    {lecture.description && (
                      <p className="lecture-description">{lecture.description}</p>
                    )}

                    <div className="lecture-card-footer">
                      <div className="lecture-timing-info">
                        <span className="timing-label">{t("lectures.duration")}:</span>
                        <span className="timing-value">{formatDuration(durationMs)}</span>
                      </div>

                      <div className="lecture-card-actions">
                        {isOwnerOrAdmin && (
                          <div className="admin-actions-bar">
                            <button
                              type="button"
                              className={`btn btn-sm ${lecture.published ? "btn-secondary" : "btn-accent"}`}
                              onClick={() => handleTogglePublish(lecture.id, lecture.published)}
                              title={lecture.published ? t("professor.unpublish") : t("professor.publish")}
                            >
                              {lecture.published ? t("professor.unpublish") : t("professor.publish")}
                            </button>

                            <button
                              type="button"
                              className="btn btn-secondary btn-sm danger-btn"
                              onClick={() => handleDeleteLecture(lecture.id)}
                              title={t("professor.delete")}
                            >
                              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                                <polyline points="3 6 5 6 21 6" />
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                              </svg>
                            </button>

                            {lecture.status === "processing" && (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() =>
                                  setExpandedPipelineLectureId(
                                    expandedPipelineLectureId === lecture.id ? null : lecture.id
                                  )
                                }
                              >
                                {t("pipeline.title")}
                              </button>
                            )}
                          </div>
                        )}

                        <Link
                          to={`/lectures/${lecture.id}`}
                          className={`btn btn-primary btn-sm play-lecture-btn ${
                            lecture.status !== "ready" && !isOwnerOrAdmin ? "disabled-link" : ""
                          }`}
                          aria-disabled={lecture.status !== "ready" && !isOwnerOrAdmin}
                          onClick={(e) => {
                            if (lecture.status !== "ready" && !isOwnerOrAdmin) e.preventDefault();
                          }}
                        >
                          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                            <polygon points="5 3 19 12 5 21 5 3" />
                          </svg>
                          {hasStarted ? t("lectures.resume") : t("lectures.start")}
                        </Link>
                      </div>
                    </div>

                    {isOwnerOrAdmin && expandedPipelineLectureId === lecture.id && (
                      <div className="card-pipeline-drawer">
                        <PipelineStatusPanel
                          lectureId={lecture.id}
                          isProcessing={lecture.status === "processing"}
                        />
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {isOwnerOrAdmin && (
        <>
          <ManageEnrollmentsModal
            isOpen={isEnrollmentsOpen}
            onClose={() => setIsEnrollmentsOpen(false)}
            courseId={course.id}
          />
          <UploadLectureModal
            isOpen={isUploadOpen}
            onClose={() => setIsUploadOpen(false)}
            courseId={course.id}
          />
        </>
      )}
    </div>
  );
}
