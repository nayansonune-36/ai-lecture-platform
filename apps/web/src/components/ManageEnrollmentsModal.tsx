import { useState, useEffect, type FormEvent, type ChangeEvent } from "react";
import type { EnrollmentMemberOut, EnrollmentRole } from "@lecture-platform/shared";
import { api } from "../services/api.js";
import { useTranslation } from "../i18n/index.js";

interface ManageEnrollmentsModalProps {
  courseId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ManageEnrollmentsModal({ courseId, isOpen, onClose }: ManageEnrollmentsModalProps) {
  const { t } = useTranslation();

  const [activeTab, setActiveTab] = useState<"paste" | "csv">("paste");
  const [emailsText, setEmailsText] = useState("");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [role, setRole] = useState<EnrollmentRole>("student");

  const [members, setMembers] = useState<EnrollmentMemberOut[]>([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{
    addedCount: number;
    alreadyCount: number;
    unknown: string[];
  } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadMembers = async () => {
    setIsLoadingMembers(true);
    try {
      const data = await api.courses.getEnrollments(courseId);
      setMembers(data);
    } catch {
      // ignore
    } finally {
      setIsLoadingMembers(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadMembers();
      setFeedback(null);
      setErrorMsg(null);
    }
  }, [isOpen, courseId]);

  if (!isOpen) return null;

  const handlePasteSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const rawEmails = emailsText
      .split(/[\n,;\s]+/)
      .map((e) => e.trim())
      .filter((e) => e.includes("@"));

    if (rawEmails.length === 0) return;

    setIsSubmitting(true);
    setErrorMsg(null);
    setFeedback(null);

    try {
      const res = await api.courses.addEnrollments(courseId, {
        emails: rawEmails,
        role,
      });

      setFeedback({
        addedCount: res.added.length,
        alreadyCount: res.already_enrolled.length,
        unknown: res.unknown,
      });
      setEmailsText("");
      await loadMembers();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCsvSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!csvFile) return;

    setIsSubmitting(true);
    setErrorMsg(null);
    setFeedback(null);

    try {
      const res = await api.courses.addEnrollmentsCsv(courseId, csvFile, role);
      setFeedback({
        addedCount: res.added.length,
        alreadyCount: res.already_enrolled.length,
        unknown: res.unknown,
      });
      setCsvFile(null);
      await loadMembers();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRemove = async (userId: string) => {
    try {
      await api.courses.removeEnrollment(courseId, userId);
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t("common.error"));
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card modal-large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{t("professor.manage_enrollments")}</h2>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {errorMsg && <div className="error-banner">{errorMsg}</div>}

        {feedback && (
          <div className="feedback-banner">
            <p className="feedback-success">
              {t("professor.added_count", { count: feedback.addedCount })}
              {feedback.alreadyCount > 0 && ` (${feedback.alreadyCount} already enrolled)`}
            </p>
            {feedback.unknown.length > 0 && (
              <p className="feedback-warning">
                {t("professor.unknown_emails", { emails: feedback.unknown.join(", ") })}
              </p>
            )}
          </div>
        )}

        {/* Tab switcher */}
        <div className="tab-switcher">
          <button
            type="button"
            className={`tab-btn ${activeTab === "paste" ? "active-tab" : ""}`}
            onClick={() => setActiveTab("paste")}
          >
            {t("professor.enroll_emails_tab")}
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === "csv" ? "active-tab" : ""}`}
            onClick={() => setActiveTab("csv")}
          >
            {t("professor.enroll_csv_tab")}
          </button>
        </div>

        {activeTab === "paste" ? (
          <form onSubmit={handlePasteSubmit} className="enrollment-form">
            <div className="form-group">
              <label htmlFor="paste-emails">{t("professor.enroll_emails_tab")}</label>
              <textarea
                id="paste-emails"
                rows={4}
                value={emailsText}
                onChange={(e) => setEmailsText(e.target.value)}
                placeholder={t("professor.paste_emails_placeholder")}
                disabled={isSubmitting}
              />
            </div>

            <div className="form-row">
              <div className="form-group role-select-group">
                <label htmlFor="role-select">{t("professor.enroll_role")}</label>
                <select
                  id="role-select"
                  value={role}
                  onChange={(e) => setRole(e.target.value as EnrollmentRole)}
                  disabled={isSubmitting}
                >
                  <option value="student">Student</option>
                  <option value="ta">Teaching Assistant</option>
                  <option value="instructor">Instructor</option>
                </select>
              </div>

              <button
                type="submit"
                className="btn btn-primary add-members-btn"
                disabled={isSubmitting || !emailsText.trim()}
              >
                {isSubmitting ? t("common.loading") : t("professor.add_enrollments_btn")}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleCsvSubmit} className="enrollment-form">
            <div className="form-group">
              <label htmlFor="csv-file">{t("professor.enroll_csv_tab")}</label>
              <input
                id="csv-file"
                type="file"
                accept=".csv,text/csv"
                onChange={(e: ChangeEvent<HTMLInputElement>) => {
                  if (e.target.files?.[0]) setCsvFile(e.target.files[0]);
                }}
                disabled={isSubmitting}
              />
              <small className="help-text">CSV should contain an email column with student email addresses.</small>
            </div>

            <div className="form-row">
              <div className="form-group role-select-group">
                <label htmlFor="csv-role-select">{t("professor.enroll_role")}</label>
                <select
                  id="csv-role-select"
                  value={role}
                  onChange={(e) => setRole(e.target.value as EnrollmentRole)}
                  disabled={isSubmitting}
                >
                  <option value="student">Student</option>
                  <option value="ta">Teaching Assistant</option>
                  <option value="instructor">Instructor</option>
                </select>
              </div>

              <button
                type="submit"
                className="btn btn-primary add-members-btn"
                disabled={isSubmitting || !csvFile}
              >
                {isSubmitting ? t("common.loading") : t("professor.add_enrollments_btn")}
              </button>
            </div>
          </form>
        )}

        {/* Existing members section */}
        <div className="existing-members-section">
          <h3 className="existing-members-title">
            {t("professor.enrolled_members")} ({members.length})
          </h3>

          {isLoadingMembers ? (
            <div className="state-container"><div className="spinner" /></div>
          ) : members.length === 0 ? (
            <p className="empty-members-text">No members enrolled yet.</p>
          ) : (
            <div className="members-table-wrapper">
              <table className="members-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.user_id}>
                      <td className="member-name-cell">{m.name}</td>
                      <td className="member-email-cell">{m.email}</td>
                      <td>
                        <span className="user-role-badge">{m.role}</span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="remove-member-btn"
                          onClick={() => handleRemove(m.user_id)}
                          title="Remove member"
                        >
                          ✕ {t("professor.remove_member")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
