import React from "react";
import { useLibrary } from "../hooks/useLibrary.js";
import type { UserProfile } from "../types.js";

interface LibraryScreenProps {
  user: UserProfile;
  onOpenSettings: () => void;
  onSignOut: () => void;
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

export const LibraryScreen: React.FC<LibraryScreenProps> = ({
  user,
  onOpenSettings,
  onSignOut,
}) => {
  const {
    courses,
    downloaded,
    activeTab,
    setActiveTab,
    loading,
    error,
    refresh,
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
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px" }}>
                      {course.lectures.map((lec) => (
                        <div
                          key={lec.id}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "12px 16px",
                            backgroundColor: "#f9fafb",
                            borderRadius: "6px",
                            border: "1px solid #f3f4f6",
                          }}
                        >
                          <div>
                            <div style={{ fontSize: "14px", fontWeight: "500", color: "#1f2937" }}>
                              {lec.title}
                            </div>
                            <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "2px" }}>
                              Duration: {formatDuration(lec.duration_ms)} • Status: {lec.status}
                            </div>
                          </div>

                          <button
                            disabled={lec.status !== "ready"}
                            style={{
                              padding: "6px 12px",
                              backgroundColor: lec.status === "ready" ? "#2563eb" : "#e5e7eb",
                              color: lec.status === "ready" ? "#ffffff" : "#9ca3af",
                              border: "none",
                              borderRadius: "6px",
                              fontSize: "12px",
                              fontWeight: "500",
                              cursor: lec.status === "ready" ? "pointer" : "not-allowed",
                            }}
                          >
                            Download
                          </button>
                        </div>
                      ))}
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
              textAlign: "center",
              padding: "64px 24px",
              backgroundColor: "#ffffff",
              borderRadius: "8px",
              border: "1px solid #e5e7eb",
            }}
          >
            {downloaded.length === 0 ? (
              <>
                <p style={{ fontSize: "16px", fontWeight: "500", color: "#374151", marginBottom: "8px" }}>
                  No downloaded lectures yet
                </p>
                <p style={{ fontSize: "14px", color: "#6b7280" }}>
                  Lectures you download for offline viewing will appear here.
                </p>
              </>
            ) : (
              <div style={{ textAlign: "left" }}>
                {downloaded.map((dl) => (
                  <div
                    key={dl.lecture_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "12px",
                      borderBottom: "1px solid #f3f4f6",
                    }}
                  >
                    <div>
                      <div style={{ fontSize: "14px", fontWeight: "500" }}>{dl.lecture_title}</div>
                      <div style={{ fontSize: "12px", color: "#6b7280" }}>{dl.course_title}</div>
                    </div>
                    <span style={{ fontSize: "12px", color: "#16a34a" }}>Downloaded</span>
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
