import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api.js";
import { useTranslation } from "../i18n/index.js";

interface CreateCourseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated?: (courseId: string) => void;
}

export function CreateCourseModal({ isOpen, onClose, onCreated }: CreateCourseModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [term, setTerm] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!code.trim() || !title.trim()) return;

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      const course = await api.courses.create({
        code: code.trim().toUpperCase(),
        title: title.trim(),
        term: term.trim() || null,
        description: description.trim() || null,
      });

      await queryClient.invalidateQueries({ queryKey: ["courses"] });
      onClose();
      onCreated?.(course.id);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t("common.error");
      setErrorMsg(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{t("professor.create_course_title")}</h2>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {errorMsg && <div className="error-banner">{errorMsg}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-group">
            <label htmlFor="course-code">{t("professor.course_code")} *</label>
            <input
              id="course-code"
              type="text"
              required
              placeholder="e.g. CS201"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="form-group">
            <label htmlFor="course-title">{t("professor.course_title")} *</label>
            <input
              id="course-title"
              type="text"
              required
              placeholder="e.g. Data Structures and Algorithms"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="form-group">
            <label htmlFor="course-term">{t("professor.course_term")}</label>
            <input
              id="course-term"
              type="text"
              placeholder="e.g. Fall 2026"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="form-group">
            <label htmlFor="course-desc">{t("professor.course_desc")}</label>
            <textarea
              id="course-desc"
              rows={3}
              placeholder="Course syllabus and overview..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isSubmitting || !code || !title}>
              {isSubmitting ? t("common.loading") : t("professor.save_course")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
