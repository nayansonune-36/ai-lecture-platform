import React, { useState } from "react";
import { useLibrary } from "../hooks/useLibrary.js";
import { useConnectivity } from "../hooks/useConnectivity.js";
import type { UserProfile } from "../types.js";

interface LibraryScreenProps {
  user: UserProfile;
  onOpenSettings: () => void;
  onSignOut: (wipeDownloads?: boolean) => void;
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

  const { isOnline, rollbackDetected, checking, syncing, checkNow, syncNow } = useConnectivity();
  const [revocationNotice, setRevocationNotice] = useState<string | null>(null);
  const [showSignOutModal, setShowSignOutModal] = useState(false);

  const handleManualSync = async () => {
    const res = await syncNow();
    if (res) {
      if (res.revoked_count > 0 && res.revoked_titles.length > 0) {
        setRevocationNotice(res.revoked_titles.join(", "));
      }
      void refresh();
    }
  };

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
      {/* Top Connectivity Banner */}
      {!isOnline && (
        <div
          style={{
            backgroundColor: "#fef3c7",
            color: "#92400e",
            padding: "10px 24px",
            fontSize: "13px",
            fontWeight: "500",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid #fde68a",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span>⚠️</span>
            <span>
              <strong>Offline Mode:</strong> Server is unreachable. You can continue watching downloaded lectures.
            </span>
          </div>
          <button
            onClick={() => void checkNow()}
            disabled={checking}
            style={{
              padding: "4px 10px",
              backgroundColor: "#ffffff",
              border: "1px solid #d97706",
              borderRadius: "4px",
              fontSize: "12px",
              color: "#b45309",
              cursor: checking ? "not-allowed" : "pointer",
              fontWeight: "500",
            }}
          >
            {checking ? "Checking..." : "Retry Connection"}
          </button>
        </div>
      )}

      {rollbackDetected && (
        <div
          style={{
            backgroundColor: "#fee2e2",
            color: "#991b1b",
            padding: "10px 24px",
            fontSize: "13px",
            fontWeight: "500",
            borderBottom: "1px solid #fecaca",
          }}
        >
          ⛔ <strong>Clock Rollback Detected:</strong> System clock is earlier than latest verified server time. Offline playback is locked until you connect to the server and sync.
        </div>
      )}

      {revocationNotice && (
        <div
          style={{
            backgroundColor: "#fee2e2",
            color: "#991b1b",
            padding: "10px 24px",
            fontSize: "13px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid #fecaca",
          }}
        >
          <div>
            ⚠️ <strong>License Revoked:</strong> The following lectures were revoked by the server and removed: <strong>{revocationNotice}</strong>
          </div>
          <button
            onClick={() => setRevocationNotice(null)}
            style={{
              background: "none",
              border: "none",
              color: "#991b1b",
              cursor: "pointer",
              fontSize: "14px",
            }}
          >
            ✕
          </button>
        </div>
      )}

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
          {isOnline ? (
            <span
              style={{
                fontSize: "11px",
                padding: "2px 8px",
                backgroundColor: "#dcfce7",
                color: "#166534",
                borderRadius: "9999px",
                fontWeight: "600",
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}
            >
              <span style={{ fontSize: "8px" }}>●</span> Online
            </span>
          ) : (
            <span
              style={{
                fontSize: "11px",
                padding: "2px 8px",
                backgroundColor: "#fef3c7",
                color: "#92400e",
                borderRadius: "9999px",
                fontWeight: "600",
              }}
            >
              Offline
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {isOnline && (
            <button
              onClick={() => void handleManualSync()}
              disabled={syncing}
              style={{
                padding: "6px 12px",
                backgroundColor: "#f0fdf4",
                border: "1px solid #bbf7d0",
                borderRadius: "6px",
                fontSize: "13px",
                color: "#166534",
                cursor: syncing ? "not-allowed" : "pointer",
                fontWeight: "500",
              }}
            >
              {syncing ? "Syncing..." : "Sync Licenses"}
            </button>
          )}

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
            onClick={() => setShowSignOutModal(true)}
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

      {/* Sign Out Modal */}
      {showSignOutModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0, 0, 0, 0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: "#ffffff",
              borderRadius: "8px",
              padding: "24px",
              maxWidth: "440px",
              width: "100%",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
            }}
          >
            <h3 style={{ fontSize: "16px", fontWeight: "600", color: "#111827", margin: "0 0 8px 0" }}>
              Sign Out of AI Lecture Platform
            </h3>
            <p style={{ fontSize: "14px", color: "#4b5563", marginBottom: "20px", lineHeight: "1.5" }}>
              Would you like to keep your downloaded lectures on this device for offline viewing, or wipe all downloaded content?
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <button
                onClick={() => {
                  setShowSignOutModal(false);
                  onSignOut(false);
                }}
                style={{
                  padding: "10px 16px",
                  backgroundColor: "#2563eb",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: "500",
                  cursor: "pointer",
                }}
              >
                Keep Downloads & Sign Out
              </button>
              <button
                onClick={() => {
                  setShowSignOutModal(false);
                  onSignOut(true);
                }}
                style={{
                  padding: "10px 16px",
                  backgroundColor: "#fee2e2",
                  color: "#b91c1c",
                  border: "1px solid #fecaca",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: "500",
                  cursor: "pointer",
                }}
              >
                Wipe All Downloads & Sign Out
              </button>
              <button
                onClick={() => setShowSignOutModal(false)}
                style={{
                  padding: "8px 16px",
                  backgroundColor: "#ffffff",
                  color: "#6b7280",
                  border: "1px solid #d1d5db",
                  borderRadius: "6px",
                  fontSize: "13px",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

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

                      {dl.is_expired ? (
                        <span
                          style={{
                            fontSize: "12px",
                            color: "#b91c1c",
                            fontWeight: "600",
                            backgroundColor: "#fee2e2",
                            padding: "3px 8px",
                            borderRadius: "4px",
                          }}
                        >
                          Expired — Connect to renew
                        </span>
                      ) : (
                        <span
                          style={{
                            fontSize: "12px",
                            color: "#2563eb",
                            fontWeight: "500",
                            backgroundColor: "#eff6ff",
                            padding: "3px 8px",
                            borderRadius: "4px",
                          }}
                        >
                          {dl.days_left !== undefined && dl.days_left !== null
                            ? `${dl.days_left} day${dl.days_left === 1 ? "" : "s"} left`
                            : "Active"}
                        </span>
                      )}

                      <button
                        onClick={() => {
                          if (dl.is_expired) {
                            alert("This lecture's offline license has expired. Please connect to the university network to renew.");
                            return;
                          }
                          onPlayLecture?.(dl.lecture_id);
                        }}
                        disabled={dl.is_expired}
                        style={{
                          padding: "6px 14px",
                          backgroundColor: dl.is_expired ? "#9ca3af" : "#2563eb",
                          color: "#ffffff",
                          border: "none",
                          borderRadius: "6px",
                          fontSize: "12px",
                          cursor: dl.is_expired ? "not-allowed" : "pointer",
                          fontWeight: "500",
                        }}
                      >
                        {dl.is_expired ? "Connect to renew" : "Watch Offline"}
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
