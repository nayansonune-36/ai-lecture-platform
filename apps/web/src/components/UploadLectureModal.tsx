import { useState, useRef, type FormEvent, type ChangeEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api.js";
import { useTranslation } from "../i18n/index.js";
import { ProgressBar } from "./ProgressBar.js";

interface UploadLectureModalProps {
  courseId: string;
  isOpen: boolean;
  onClose: () => void;
  onCompleted?: (lectureId: string) => void;
}

const CHUNK_SIZE = 2 * 1024 * 1024; // 2 MB chunks for reliable streaming upload
const MAX_NETWORK_RETRIES = 5;

export function UploadLectureModal({
  courseId,
  isOpen,
  onClose,
  onCompleted,
}: UploadLectureModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);

  // Upload progress state
  const [isUploading, setIsUploading] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [uploadedBytes, setUploadedBytes] = useState(0);
  const [totalBytes, setTotalBytes] = useState(0);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  if (!isOpen) return null;

  const handleStartUpload = async (e: FormEvent) => {
    e.preventDefault();
    if (!file || !title.trim()) return;

    setIsUploading(true);
    setErrorMsg(null);
    setStatusMessage(null);
    setProgressPercent(0);
    setUploadedBytes(0);
    setTotalBytes(file.size);

    abortControllerRef.current = new AbortController();

    try {
      // 1. Create lecture record and obtain upload_url
      setStatusMessage("Creating lecture record...");
      const initRes = await api.lectures.create(courseId, {
        title: title.trim(),
        filename: file.name,
        description: description.trim() || null,
      });

      const lectureId = initRes.lecture.id;
      const uploadUrl = initRes.upload_url;

      // 2. Resumable chunked upload loop
      let offset = 0;
      let consecutiveFails = 0;

      while (offset < file.size) {
        const chunkEnd = Math.min(offset + CHUNK_SIZE, file.size);
        const chunkBlob = file.slice(offset, chunkEnd);
        const contentRange = `bytes ${offset}-${chunkEnd - 1}/${file.size}`;

        setStatusMessage(
          t("professor.uploading", {
            percent: Math.round((offset / file.size) * 100),
          })
        );

        try {
          await api.lectures.uploadChunk(uploadUrl, chunkBlob, contentRange);
          consecutiveFails = 0;
          offset = chunkEnd;
          setUploadedBytes(offset);
          setProgressPercent(Math.round((offset / file.size) * 100));
        } catch (uploadErr: unknown) {
          consecutiveFails++;
          if (consecutiveFails > MAX_NETWORK_RETRIES) {
            throw new Error(`Upload failed after ${MAX_NETWORK_RETRIES} resume attempts: ${uploadErr}`);
          }

          // Handle dropped connection and wait before resuming from the same offset
          setStatusMessage(t("professor.resuming"));
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      }

      // 3. Mark upload complete and queue transcode
      setStatusMessage("Finalizing upload and queueing transcode...");
      await api.lectures.completeUpload(lectureId);

      setStatusMessage(t("professor.upload_complete"));
      setProgressPercent(100);

      await queryClient.invalidateQueries({ queryKey: ["lectures", courseId] });

      setTimeout(() => {
        onClose();
        onCompleted?.(lectureId);
      }, 1200);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t("common.error"));
      setIsUploading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={!isUploading ? onClose : undefined}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{t("professor.upload_lecture")}</h2>
          {!isUploading && (
            <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Close">
              ✕
            </button>
          )}
        </div>

        {errorMsg && <div className="error-banner">{errorMsg}</div>}

        <form onSubmit={handleStartUpload} className="modal-form">
          <div className="form-group">
            <label htmlFor="lecture-title">{t("professor.lecture_title")} *</label>
            <input
              id="lecture-title"
              type="text"
              required
              placeholder="e.g. Lecture 04: Fast Fourier Transform"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={isUploading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="lecture-desc">{t("professor.course_desc")}</label>
            <textarea
              id="lecture-desc"
              rows={2}
              placeholder="Optional overview or topic list..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isUploading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="lecture-file">{t("professor.lecture_file")} *</label>
            <input
              id="lecture-file"
              type="file"
              required
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm"
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                if (e.target.files?.[0]) setFile(e.target.files[0]);
              }}
              disabled={isUploading}
            />
            {file && (
              <small className="help-text">
                Selected: <strong>{file.name}</strong> ({(file.size / (1024 * 1024)).toFixed(1)} MB)
              </small>
            )}
          </div>

          {isUploading && (
            <div className="upload-progress-box">
              <div className="progress-info-row">
                <span className="upload-status-text">{statusMessage}</span>
                <span className="upload-percent-text">{progressPercent}%</span>
              </div>
              <ProgressBar positionMs={uploadedBytes} durationMs={totalBytes || 100} />
            </div>
          )}

          <div className="modal-actions">
            {!isUploading && (
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Cancel
              </button>
            )}
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isUploading || !file || !title.trim()}
            >
              {isUploading ? t("common.loading") : t("professor.upload_btn")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
