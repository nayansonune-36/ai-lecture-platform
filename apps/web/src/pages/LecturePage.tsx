import { useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useLecture } from "../hooks/useLecture.js";
import { usePlaybackToken, usePlaybackProgress, useChapters } from "../hooks/usePlayback.js";
import { useTranslation } from "../i18n/index.js";
import { useAuth } from "../context/AuthContext.js";
import { HlsPlayer, type HlsPlayerRef } from "../components/HlsPlayer.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { PipelineStatusPanel } from "../components/PipelineStatusPanel.js";
import { formatDuration } from "../utils/format.js";
import { api } from "../services/api.js";

export function LecturePage() {
  const { id: lectureId } = useParams<{ id: string }>();
  const { user } = useAuth();
  const { t } = useTranslation();
  const playerRef = useRef<HlsPlayerRef | null>(null);

  const isProfessorOrAdmin = user?.role === "professor" || user?.role === "admin";
  const [showPipeline, setShowPipeline] = useState(false);

  const {
    data: lecture,
    isLoading: lectureLoading,
    error: lectureError,
    refetch: refetchLecture,
  } = useLecture(lectureId);

  const isReady = lecture?.status === "ready";

  const {
    data: tokenData,
    isLoading: tokenLoading,
    error: tokenError,
    refetch: refetchToken,
  } = usePlaybackToken(lectureId, isReady);

  const { data: progressData } = usePlaybackProgress(lectureId, isReady);
  const { data: chapters } = useChapters(lectureId, isReady);

  const [activeChapterIndex, setActiveChapterIndex] = useState<number>(0);

  const handleProgressUpdate = async (positionMs: number, completed: boolean) => {
    if (!lectureId) return;
    try {
      await api.playback.saveProgress(lectureId, {
        position_ms: positionMs,
        completed,
      });

      // Update active chapter based on current position
      if (chapters && chapters.length > 0) {
        let activeIdx = 0;
        for (let i = 0; i < chapters.length; i++) {
          if (positionMs >= chapters[i].start_ms) {
            activeIdx = i;
          }
        }
        setActiveChapterIndex(activeIdx);
      }
    } catch {
      // Background progress save error silently caught
    }
  };

  const handleChapterClick = (startMs: number, index: number) => {
    if (playerRef.current) {
      playerRef.current.seekTo(startMs / 1000);
      setActiveChapterIndex(index);
    }
  };

  if (lectureLoading || (isReady && (tokenLoading || !progressData))) {
    return (
      <div className="state-container">
        <div className="spinner" />
        <p>{t("common.loading")}</p>
      </div>
    );
  }

  if (lectureError || !lecture) {
    return (
      <div className="state-container error-state">
        <p className="error-text">{t("common.error")}</p>
        <Link to="/courses" className="btn btn-secondary">
          {t("lectures.back")}
        </Link>
      </div>
    );
  }

  const backUrl = `/courses/${lecture.course_id}`;

  // Handle case where lecture is still processing or not yet ready
  if (!isReady) {
    return (
      <div className="page-container">
        <nav className="breadcrumb-nav">
          <Link to={backUrl} className="breadcrumb-link">
            ‹ {t("lectures.back")}
          </Link>
        </nav>

        <div className="processing-state-card">
          <div className="processing-icon-spinner" />
          <h2>{t("player.processing_title")}</h2>
          <p className="processing-desc">{t("player.processing_desc")}</p>
          <div className="processing-meta">
            <span>{lecture.title}</span>
            <StatusBadge status={lecture.status} published={lecture.published} />
          </div>
          <button
            type="button"
            onClick={() => refetchLecture()}
            className="btn btn-primary"
          >
            {t("player.refresh_status")}
          </button>

          <div className="processing-pipeline-wrapper">
            <PipelineStatusPanel
              lectureId={lecture.id}
              isProcessing={lecture.status === "processing"}
            />
          </div>
        </div>
      </div>
    );
  }

  const posterUrl = lecture.poster_path ? `/media/${lecture.poster_path}` : null;
  const captionsUrl = api.playback.getCaptionsUrl(lecture.id, "en");
  const manifestUrl = tokenData?.manifest_url || "";

  return (
    <div className="page-container lecture-page-layout">
      <nav className="breadcrumb-nav">
        <Link to={backUrl} className="breadcrumb-link">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          {t("lectures.back")}
        </Link>
      </nav>

      <div className="lecture-content-grid">
        {/* Left Column: Video Player and Metadata */}
        <div className="lecture-main-column">
          {tokenError ? (
            <div className="error-banner">
              <p>{t("player.error_expired")}</p>
              <button
                type="button"
                onClick={() => refetchToken()}
                className="btn btn-secondary btn-sm"
              >
                {t("common.retry")}
              </button>
            </div>
          ) : (
            <HlsPlayer
              ref={playerRef}
              manifestUrl={manifestUrl}
              posterUrl={posterUrl}
              captionsUrl={captionsUrl}
              initialPositionMs={progressData?.position_ms ?? 0}
              durationMs={lecture.duration_ms ?? 0}
              onProgressUpdate={handleProgressUpdate}
              onTokenExpired={() => refetchToken()}
            />
          )}

          <div className="shortcuts-hint-bar">
            <small>{t("player.shortcuts_hint")}</small>
          </div>

          <div className="lecture-meta-header">
            <div className="lecture-meta-tags">
              <span className="lecture-position">#{lecture.position + 1}</span>
              <StatusBadge status={lecture.status} published={lecture.published} />
              {lecture.duration_ms && (
                <span className="duration-tag">{formatDuration(lecture.duration_ms)}</span>
              )}
            </div>

            <h1 className="lecture-page-title">{lecture.title}</h1>

            {lecture.description && (
              <p className="lecture-page-desc">{lecture.description}</p>
            )}

            {isProfessorOrAdmin && (
              <div className="lecture-admin-pipeline-toggle">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowPipeline(!showPipeline)}
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="20" x2="18" y2="10" />
                    <line x1="12" y1="20" x2="12" y2="4" />
                    <line x1="6" y1="20" x2="6" y2="14" />
                  </svg>
                  {showPipeline ? "Hide Pipeline" : t("pipeline.title")}
                </button>
                {showPipeline && (
                  <div style={{ marginTop: "1rem" }}>
                    <PipelineStatusPanel
                      lectureId={lecture.id}
                      isProcessing={false}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Chapters Sidebar */}
        <div className="lecture-sidebar-column">
          <div className="chapters-sidebar-card">
            <h2 className="chapters-sidebar-title">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="8" y1="6" x2="21" y2="6" />
                <line x1="8" y1="12" x2="21" y2="12" />
                <line x1="8" y1="18" x2="21" y2="18" />
                <line x1="3" y1="6" x2="3.01" y2="6" />
                <line x1="3" y1="12" x2="3.01" y2="12" />
                <line x1="3" y1="18" x2="3.01" y2="18" />
              </svg>
              {t("player.chapters")}
            </h2>

            {!chapters || chapters.length === 0 ? (
              <p className="empty-chapters-text">No chapters available</p>
            ) : (
              <div className="chapters-list">
                {chapters.map((ch, idx) => (
                  <button
                    key={ch.start_ms}
                    type="button"
                    className={`chapter-item-btn ${activeChapterIndex === idx ? "active-chapter" : ""}`}
                    onClick={() => handleChapterClick(ch.start_ms, idx)}
                  >
                    <div className="chapter-item-time">
                      {formatDuration(ch.start_ms)}
                    </div>
                    <div className="chapter-item-content">
                      <div className="chapter-item-title">{ch.title}</div>
                      {ch.summary && (
                        <div className="chapter-item-summary">{ch.summary}</div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
