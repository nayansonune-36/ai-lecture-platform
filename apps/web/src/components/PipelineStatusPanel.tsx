import { useQuery } from "@tanstack/react-query";
import type { JobOut } from "@lecture-platform/shared";
import { api } from "../services/api.js";
import { useTranslation } from "../i18n/index.js";

interface PipelineStatusPanelProps {
  lectureId: string;
  isProcessing?: boolean;
}

export function PipelineStatusPanel({ lectureId, isProcessing = false }: PipelineStatusPanelProps) {
  const { t } = useTranslation();

  const { data: jobs, refetch } = useQuery<JobOut[]>({
    queryKey: ["lectureJobs", lectureId],
    queryFn: () => api.lectures.getJobs(lectureId),
    refetchInterval: isProcessing ? 3000 : false,
    staleTime: 5000,
  });

  const transcodeJob = jobs?.find((j) => j.type === "transcode");

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "completed":
        return <span className="stage-badge stage-completed">✓ Completed</span>;
      case "running":
        return <span className="stage-badge stage-running"><span className="mini-spin" /> In Progress</span>;
      case "queued":
        return <span className="stage-badge stage-queued">Queued</span>;
      case "failed":
        return <span className="stage-badge stage-failed">Failed</span>;
      default:
        return <span className="stage-badge stage-queued">Pending</span>;
    }
  };

  return (
    <div className="pipeline-panel-card">
      <div className="pipeline-panel-header">
        <h3 className="pipeline-panel-title">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          {t("pipeline.title")}
        </h3>
        {isProcessing && (
          <button type="button" onClick={() => refetch()} className="pipeline-refresh-btn" title="Refresh">
            ↻
          </button>
        )}
      </div>

      <div className="pipeline-stages-list">
        {/* Stage 1: Transcode (Active) */}
        <div className="pipeline-stage-item active-stage">
          <div className="stage-icon-circle stage-active-icon">1</div>
          <div className="stage-info">
            <div className="stage-name-row">
              <span className="stage-name">{t("pipeline.stage_transcode")}</span>
              {getStatusBadge(transcodeJob?.status)}
            </div>
            <p className="stage-desc">Produces adaptive 720p/480p/360p fMP4 HLS, master playlist, poster, and thumbnails.</p>
            {transcodeJob && transcodeJob.attempts > 1 && (
              <small className="stage-retry-info">Attempts: {transcodeJob.attempts}</small>
            )}
          </div>
        </div>

        {/* Stage 2: Transcribe (Phase 2) */}
        <div className="pipeline-stage-item upcoming-stage">
          <div className="stage-icon-circle stage-upcoming-icon">2</div>
          <div className="stage-info">
            <div className="stage-name-row">
              <span className="stage-name">{t("pipeline.stage_transcribe")}</span>
              <span className="stage-badge stage-upcoming">{t("pipeline.coming_soon")}</span>
            </div>
            <p className="stage-desc">Whisper large-v3 speech-to-text with mixed English and Hindi timestamps.</p>
          </div>
        </div>

        {/* Stage 3: Index (Phase 2) */}
        <div className="pipeline-stage-item upcoming-stage">
          <div className="stage-icon-circle stage-upcoming-icon">3</div>
          <div className="stage-info">
            <div className="stage-name-row">
              <span className="stage-name">{t("pipeline.stage_index")}</span>
              <span className="stage-badge stage-upcoming">{t("pipeline.coming_soon")}</span>
            </div>
            <p className="stage-desc">30-60s window chunks, multilingual bge-m3 embeddings, and Postgres pgvector indexing.</p>
          </div>
        </div>

        {/* Stage 4: Chapters & Summary (Phase 2) */}
        <div className="pipeline-stage-item upcoming-stage">
          <div className="stage-icon-circle stage-upcoming-icon">4</div>
          <div className="stage-info">
            <div className="stage-name-row">
              <span className="stage-name">{t("pipeline.stage_chapters")}</span>
              <span className="stage-badge stage-upcoming">{t("pipeline.coming_soon")}</span>
            </div>
            <p className="stage-desc">LLM-generated topic markers and concise lecture summaries.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
