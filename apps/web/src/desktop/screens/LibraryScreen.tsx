import React from "react";
import { useLibrary } from "../hooks/useLibrary.js";
import type { UserProfile } from "../types.js";

interface LibraryScreenProps {
  user: UserProfile;
  onOpenSettings: () => void;
  onSignOut: () => void;
  onPlayLecture?: (lectureId: string) => void;
}

function formatDuration(ms?: number | null): string {
  if (!ms || ms <= 0) return "--:--";
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

function formatBytes(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatSpeed(bps?: number | null): string {
  if (!bps || bps <= 0) return "0 B/s";
  return `${formatBytes(bps)}/s`;
}

export const LibraryScreen: React.FC<LibraryScreenProps> = ({
  user,
  onOpenSettings,
  onSignOut,
  onPlayLecture,
}) => {
  const {
    courses,
    downloadRecords,
    downloaded,
    estimates,
    activeProgress,
    activeTab,
    setActiveTab,
    loading,
    error,
    refresh,
    startDownload,
    pauseDownload,
    resumeDownload,
    cancelDownload,
    deleteDownload,
  } = useLibrary(true);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "100vh",
        backgroundColor: "#f9fafb",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Top Navbar */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 24px",
          backgroundColor: "#ffffff",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ fontSize: "18px", fontWeight: "600", color: "#111827" }}>
            AI Lecture Platform
          </span>
          <span
            style={{
              fontSize: "11px",
              padding: "2px 8px",
              backgroundColor: "#e0f2fe",
              color: "#0369a1",
              borderRadius: "9999px",
              fontWeight: "600",
            }}
          >
            Desktop
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <span style={{ fontSize: "14px", color: "#4b5563" }}>
            Signed in as <strong>{user.name}</strong>
          </span>
          <button
            onClick={onOpenSettings}
            style={{
              padding: "6px 12px",
              backgroundColor: "#f3f4f6",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              fontSize: "13px",
              color: "#374151",
              cursor: "pointer",
            }}
          >
            Settings
          </button>
          <button
            onClick={onSignOut}
            style={{
              padding: "6px 12px",
              backgroundColor: "#ffffff",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              fontSize: "13px",
              color: "#dc2626",
              cursor: "pointer",
            }}
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main style={{ flex: 1, padding: "24px", maxWidth: "1000px", margin: "0 auto", width: "100%" }}>
        {/* Navigation Tabs */}
        <div
          style={{
            display: "flex",
            gap: "12px",
            borderBottom: "1px solid #e5e7eb",
            paddingBottom: "8px",
            marginBottom: "24px",
          }}
        >
          <button
            onClick={() => setActiveTab("available")}
            style={{
              padding: "8px 16px",
              backgroundColor: activeTab === "available" ? "#2563eb" : "transparent",
              color: activeTab === "available" ? "#ffffff" : "#4b5563",
              border: "none",
              borderRadius: "6px",
              fontSize: "14px",
              fontWeight: "500",
              cursor: "pointer",
            }}
          >
            Available Lectures
          </button>
          <button
            onClick={() => setActiveTab("downloaded")}
            style={{
              padding: "8px 16px",
              backgroundColor: activeTab === "downloaded" ? "#2563eb" : "transparent",
              color: activeTab === "downloaded" ? "#ffffff" : "#4b5563",
              border: "none",
              borderRadius: "6px",
              fontSize: "14px",
              fontWeight: "500",
              cursor: "pointer",
            }}
          >
            Downloaded ({downloaded.length})
          </button>
          <button
            onClick={refresh}
            style={{
              marginLeft: "auto",
              padding: "6px 12px",
              backgroundColor: "#ffffff",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              fontSize: "13px",
              color: "#374151",
              cursor: "pointer",
            }}
          >
            Refresh
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: "12px",
              backgroundColor: "#fee2e2",
              color: "#b91c1c",
              borderRadius: "6px",
              fontSize: "14px",
              marginBottom: "16px",
            }}
          >
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", padding: "48px", color: "#6b7280" }}>
            Loading lectures...
          </div>
        ) : activeTab === "available" ? (
          /* Available Tab */
          <div>
            {courses.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "48px",
                  backgroundColor: "#ffffff",
                  borderRadius: "8px",
                  border: "1px solid #e5e7eb",
                  color: "#6b7280",
                }}
              >
                No enrolled courses found.
              </div>
            ) : (
              courses.map((course) => (
                <div
                  key={course.id}
                  style={{
                    backgroundColor: "#ffffff",
                    borderRadius: "8px",
                    border: "1px solid #e5e7eb",
                    padding: "20px",
                    marginBottom: "20px",
                  }}
                >
                  <h2 style={{ fontSize: "16px", fontWeight: "600", color: "#111827", margin: 0 }}>
                    {course.code}: {course.title}
                  </h2>
                  {course.description && (
                    <p style={{ fontSize: "13px", color: "#6b7280", marginTop: "4px", marginBottom: "16px" }}>
                      {course.description}
                    </p>
                  )}

                  {course.lectures.length === 0 ? (
                    <p style={{ fontSize: "13px", color: "#9ca3af", fontStyle: "italic", marginTop: "12px" }}>
                      No published lectures in this course yet.
                    </p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "12px" }}>
                      {course.lectures.map((lec) => {
                        const dl = downloadRecords[lec.id];
                        const prog = activeProgress[lec.id];
                        const estimateBytes = estimates[lec.id];
                        const isCompleted = dl?.status === "completed";
                        const isDownloading =
                          prog?.state === "downloading" ||
                          (!prog && dl?.status === "downloading");
                        const isPaused =
                          prog?.state === "paused" ||
                          (!prog && dl?.status === "paused");
                        const isPending =
                          prog?.state === "pending" ||
                          (!prog && dl?.status === "pending");
                        const isEncrypting =
                          prog?.state === "encrypting" ||
                          (!prog && dl?.status === "encrypting");
                        const isFailed =
                          prog?.state === "failed" ||
                          (!prog && dl?.status === "failed");

                        const bytesDown = prog?.bytes_downloaded ?? (dl ? dl.progress * dl.size_bytes : 0);
                        const totalBytes = prog?.total_bytes || dl?.size_bytes || estimateBytes || 0;
                        const pct = totalBytes > 0 ? Math.min(100, Math.round((bytesDown / totalBytes) * 100)) : 0;

                        return (
                          <div
                            key={lec.id}
                            style={{
                              padding: "14px 16px",
                              backgroundColor: "#f9fafb",
                              borderRadius: "6px",
                              border: "1px solid #e5e7eb",
                            }}
                          >
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                marginBottom: isDownloading || isPaused || isPending || isEncrypting ? "10px" : "0",
                              }}
                            >
                              <div>
                                <div style={{ fontSize: "14px", fontWeight: "500", color: "#1f2937" }}>
                                  {lec.title}
                                </div>
                                <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "3px" }}>
                                  Duration: {formatDuration(lec.duration_ms)} • Status: {lec.status}
                                  {estimateBytes && !isCompleted && (
                                    <span style={{ marginLeft: "8px", color: "#4b5563" }}>
                                      • Est: ~{formatBytes(estimateBytes)} (480p)
                                    </span>
                                  )}
                                </div>
                              </div>

                              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                                {isCompleted ? (
                                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                                    <span
                                      style={{
                                        padding: "4px 10px",
                                        backgroundColor: "#dcfce7",
                                        color: "#15803d",
                                        borderRadius: "9999px",
                                        fontSize: "12px",
                                        fontWeight: "600",
                                      }}
                                    >
                                      Downloaded
                                    </span>
                                    <button
                                      onClick={() => onPlayLecture?.(lec.id)}
                                      style={{
                                        padding: "6px 12px",
                                        backgroundColor: "#16a34a",
                                        color: "#ffffff",
                                        border: "none",
                                        borderRadius: "6px",
                                        fontSize: "12px",
                                        fontWeight: "500",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Watch Offline
                                    </button>
                                  </div>
                                ) : isDownloading ? (
                                  <>
                                    <button
                                      onClick={() => pauseDownload(lec.id)}
                                      style={{
                                        padding: "6px 12px",
                                        backgroundColor: "#fef3c7",
                                        color: "#b45309",
                                        border: "1px solid #fde68a",
                                        borderRadius: "6px",
                                        fontSize: "12px",
                                        fontWeight: "500",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Pause
                                    </button>
                                    <button
                                      onClick={() => cancelDownload(lec.id)}
                                      style={{
                                        padding: "6px 12px",
                                        backgroundColor: "#fee2e2",
                                        color: "#b91c1c",
                                        border: "1px solid #fecaca",
                                        borderRadius: "6px",
                                        fontSize: "12px",
                                        fontWeight: "500",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Cancel
                                    </button>
                                  </>
                                ) : isPaused ? (
                                  <>
                                    <button
                                      onClick={() => resumeDownload(lec.id)}
                                      style={{
                                        padding: "6px 12px",
                                        backgroundColor: "#2563eb",
                                        color: "#ffffff",
                                        border: "none",
                                        borderRadius: "6px",
                                        fontSize: "12px",
                                        fontWeight: "500",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Resume
                                    </button>
                                    <button
                                      onClick={() => cancelDownload(lec.id)}
                                      style={{
                                        padding: "6px 12px",
                                        backgroundColor: "#fee2e2",
                                        color: "#b91c1c",
                                        border: "1px solid #fecaca",
                                        borderRadius: "6px",
                                        fontSize: "12px",
                                        fontWeight: "500",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Cancel
                                    </button>
                                  </>
                                ) : isPending || isEncrypting ? (
                                  <span
                                    style={{
                                      fontSize: "12px",
                                      color: "#6b7280",
                                      fontStyle: "italic",
                                    }}
                                  >
                                    {isEncrypting ? "Encrypting at rest..." : "Preparing..."}
                                  </span>
                                ) : isFailed ? (
                                  <button
                                    onClick={() => startDownload(lec.id, 480, lec.title, course.title)}
                                    style={{
                                      padding: "6px 12px",
                                      backgroundColor: "#ef4444",
                                      color: "#ffffff",
                                      border: "none",
                                      borderRadius: "6px",
                                      fontSize: "12px",
                                      fontWeight: "500",
                                      cursor: "pointer",
                                    }}
                                  >
                                    Retry Download
                                  </button>
                                ) : (
                                  <button
                                    disabled={lec.status !== "ready"}
                                    onClick={() => startDownload(lec.id, 480, lec.title, course.title)}
                                    style={{
                                      padding: "6px 14px",
                                      backgroundColor: lec.status === "ready" ? "#2563eb" : "#e5e7eb",
                                      color: lec.status === "ready" ? "#ffffff" : "#9ca3af",
                                      border: "none",
                                      borderRadius: "6px",
                                      fontSize: "12px",
                                      fontWeight: "500",
                                      cursor: lec.status === "ready" ? "pointer" : "not-allowed",
                                    }}
                                  >
                                    Download (480p)
                                  </button>
                                )}
                              </div>
                            </div>

                            {/* Active download progress bar */}
                            {(isDownloading || isPaused || isPending || isEncrypting) && (
                              <div style={{ marginTop: "8px" }}>
                                <div
                                  style={{
                                    height: "6px",
                                    backgroundColor: "#e5e7eb",
                                    borderRadius: "3px",
                                    overflow: "hidden",
                                  }}
                                >
                                  <div
                                    style={{
                                      height: "100%",
                                      width: `${pct}%`,
                                      backgroundColor: isPaused ? "#f59e0b" : "#2563eb",
                                      transition: "width 0.2s ease",
                                    }}
                                  />
                                </div>
                                <div
                                  style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    fontSize: "11px",
                                    color: "#6b7280",
                                    marginTop: "4px",
                                  }}
                                >
                                  <span>
                                    {isEncrypting
                                      ? "Encrypting files with AES-256-GCM..."
                                      : isPending
                                      ? "Preparing bundle on server..."
                                      : isPaused
                                      ? `Paused (${pct}%)`
                                      : `${pct}% • ${formatBytes(bytesDown)} of ${formatBytes(totalBytes)}`}
                                  </span>
                                  {isDownloading && prog?.speed_bps ? (
                                    <span>{formatSpeed(prog.speed_bps)}</span>
                                  ) : null}
                                </div>
                              </div>
                            )}

                            {isFailed && (
                              <div
                                style={{
                                  fontSize: "12px",
                                  color: "#dc2626",
                                  marginTop: "6px",
                                }}
                              >
                                Error: {dl?.error || prog?.error || "Download failed"}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        ) : (
          /* Downloaded Tab */
          <div
            style={{
              backgroundColor: "#ffffff",
              borderRadius: "8px",
              border: "1px solid #e5e7eb",
              padding: "20px",
            }}
          >
            <h2 style={{ fontSize: "16px", fontWeight: "600", color: "#111827", margin: "0 0 16px 0" }}>
              Offline Downloads ({downloaded.length})
            </h2>

            {downloaded.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "48px 24px",
                  color: "#6b7280",
                }}
              >
                <p style={{ fontSize: "15px", fontWeight: "500", color: "#374151", marginBottom: "6px" }}>
                  No downloaded lectures yet
                </p>
                <p style={{ fontSize: "13px", color: "#6b7280" }}>
                  Lectures downloaded for offline viewing will appear here with encrypted storage at rest.
                </p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {downloaded.map((dl) => (
                  <div
                    key={dl.lecture_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "14px 16px",
                      backgroundColor: "#f9fafb",
                      borderRadius: "6px",
                      border: "1px solid #e5e7eb",
                    }}
                  >
                    <div>
                      <div style={{ fontSize: "14px", fontWeight: "600", color: "#1f2937" }}>
                        {dl.lecture_title}
                      </div>
                      <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "3px" }}>
                        {dl.course_title} • Rendition: {dl.rendition}p • Stored: {formatBytes(dl.size_bytes)}
                        {dl.completed_at && ` • Downloaded: ${new Date(dl.completed_at).toLocaleDateString()}`}
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <span
                        style={{
                          fontSize: "12px",
                          color: "#16a34a",
                          fontWeight: "500",
                          backgroundColor: "#dcfce7",
                          padding: "3px 8px",
                          borderRadius: "4px",
                        }}
                      >
                        Encrypted
                      </span>
                      <button
                        onClick={() => onPlayLecture?.(dl.lecture_id)}
                        style={{
                          padding: "6px 14px",
                          backgroundColor: "#2563eb",
                          color: "#ffffff",
                          border: "none",
                          borderRadius: "6px",
                          fontSize: "12px",
                          cursor: "pointer",
                          fontWeight: "500",
                        }}
                      >
                        Watch Offline
                      </button>
                      <button
                        onClick={() => deleteDownload(dl.lecture_id)}
                        style={{
                          padding: "6px 12px",
                          backgroundColor: "#ffffff",
                          border: "1px solid #d1d5db",
                          borderRadius: "6px",
                          fontSize: "12px",
                          color: "#dc2626",
                          cursor: "pointer",
                          fontWeight: "500",
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
};
