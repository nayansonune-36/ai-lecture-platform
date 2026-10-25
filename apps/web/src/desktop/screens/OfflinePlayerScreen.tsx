import React, { useRef } from "react";
import { HlsPlayer, type HlsPlayerRef } from "../../components/HlsPlayer.js";
import { useOfflinePlayback } from "../hooks/useOfflinePlayback.js";

interface OfflinePlayerScreenProps {
  lectureId: string;
  onBack: () => void;
}

function formatDuration(ms?: number | null): string {
  if (!ms || ms <= 0) return "00:00";
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

export const OfflinePlayerScreen: React.FC<OfflinePlayerScreenProps> = ({
  lectureId,
  onBack,
}) => {
  const playerRef = useRef<HlsPlayerRef | null>(null);
  const {
    playbackInfo,
    chapters,
    activeChapterIndex,
    loading,
    error,
    handleProgressUpdate,
    seekToChapter,
  } = useOfflinePlayback(lectureId);

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
          backgroundColor: "#111827",
          color: "#f3f4f6",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: "16px", marginBottom: "8px" }}>
            Preparing offline playback...
          </div>
          <div style={{ fontSize: "13px", color: "#9ca3af" }}>
            Verifying offline license and decrypting media stream on 127.0.0.1
          </div>
        </div>
      </div>
    );
  }

  if (error || !playbackInfo) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
          backgroundColor: "#f9fafb",
          fontFamily: "system-ui, -apple-system, sans-serif",
          padding: "24px",
        }}
      >
        <div
          style={{
            maxWidth: "480px",
            width: "100%",
            backgroundColor: "#ffffff",
            padding: "24px",
            borderRadius: "8px",
            border: "1px solid #fee2e2",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: "18px",
              fontWeight: "600",
              color: "#b91c1c",
              marginBottom: "12px",
            }}
          >
            Offline Playback Error
          </div>
          <p style={{ fontSize: "14px", color: "#4b5563", marginBottom: "20px" }}>
            {error || "Could not load offline lecture bundle."}
          </p>
          <button
            onClick={onBack}
            style={{
              padding: "8px 16px",
              backgroundColor: "#2563eb",
              color: "#ffffff",
              border: "none",
              borderRadius: "6px",
              fontSize: "14px",
              fontWeight: "500",
              cursor: "pointer",
            }}
          >
            ‹ Back to Library
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "100vh",
        backgroundColor: "#0f172a",
        color: "#f8fafc",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Top Navbar */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 24px",
          backgroundColor: "#1e293b",
          borderBottom: "1px solid #334155",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <button
            onClick={onBack}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 12px",
              backgroundColor: "#334155",
              color: "#f8fafc",
              border: "none",
              borderRadius: "6px",
              fontSize: "13px",
              cursor: "pointer",
              fontWeight: "500",
            }}
          >
            ‹ Back
          </button>

          <div>
            <h1
              style={{
                fontSize: "16px",
                fontWeight: "600",
                margin: 0,
                color: "#ffffff",
              }}
            >
              {playbackInfo.lecture_title}
            </h1>
            <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "2px" }}>
              {playbackInfo.course_title}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            style={{
              padding: "4px 10px",
              backgroundColor: "#065f46",
              color: "#34d399",
              borderRadius: "9999px",
              fontSize: "11px",
              fontWeight: "600",
              letterSpacing: "0.5px",
            }}
          >
            Offline Mode
          </span>
          <span
            style={{
              padding: "4px 10px",
              backgroundColor: "#1e3a8a",
              color: "#93c5fd",
              borderRadius: "9999px",
              fontSize: "11px",
              fontWeight: "600",
            }}
          >
            AES-256 Decrypted
          </span>
        </div>
      </header>

      {/* Main Content Area */}
      <div
        style={{
          display: "flex",
          flex: 1,
          padding: "24px",
          gap: "24px",
          maxWidth: "1400px",
          margin: "0 auto",
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        {/* Video Player Column */}
        <div style={{ flex: 3, display: "flex", flexDirection: "column" }}>
          <div
            style={{
              borderRadius: "8px",
              overflow: "hidden",
              backgroundColor: "#000000",
              boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
          >
            <HlsPlayer
              ref={playerRef}
              manifestUrl={playbackInfo.manifest_url}
              posterUrl={playbackInfo.poster_url}
              captionsUrl={playbackInfo.captions_url}
              initialPositionMs={playbackInfo.initial_position_ms}
              onProgressUpdate={handleProgressUpdate}
            />
          </div>

          <div
            style={{
              marginTop: "16px",
              padding: "16px",
              backgroundColor: "#1e293b",
              borderRadius: "8px",
              border: "1px solid #334155",
            }}
          >
            <div style={{ fontSize: "14px", fontWeight: "600", color: "#f1f5f9" }}>
              {playbackInfo.lecture_title}
            </div>
            <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
              Course: {playbackInfo.course_title} • Playing from local offline bundle
            </div>
          </div>
        </div>

        {/* Chapters Sidebar Column */}
        <div
          style={{
            flex: 1,
            backgroundColor: "#1e293b",
            borderRadius: "8px",
            border: "1px solid #334155",
            padding: "16px",
            maxHeight: "650px",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div
            style={{
              fontSize: "15px",
              fontWeight: "600",
              color: "#f1f5f9",
              marginBottom: "14px",
              borderBottom: "1px solid #334155",
              paddingBottom: "8px",
            }}
          >
            Chapters ({chapters.length})
          </div>

          {chapters.length === 0 ? (
            <div
              style={{
                fontSize: "13px",
                color: "#94a3b8",
                textAlign: "center",
                padding: "32px 8px",
                fontStyle: "italic",
              }}
            >
              No chapters in this bundle
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {chapters.map((ch, idx) => {
                const isActive = activeChapterIndex === idx;
                return (
                  <button
                    key={ch.id || idx}
                    onClick={() => seekToChapter(playerRef, ch.start_ms, idx)}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "10px",
                      padding: "10px",
                      backgroundColor: isActive ? "#334155" : "#0f172a",
                      border: isActive ? "1px solid #3b82f6" : "1px solid #1e293b",
                      borderRadius: "6px",
                      color: "#f8fafc",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "11px",
                        fontFamily: "monospace",
                        color: isActive ? "#60a5fa" : "#94a3b8",
                        backgroundColor: "#1e293b",
                        padding: "2px 6px",
                        borderRadius: "4px",
                        marginTop: "2px",
                      }}
                    >
                      {formatDuration(ch.start_ms)}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          fontSize: "13px",
                          fontWeight: isActive ? "600" : "500",
                          color: isActive ? "#ffffff" : "#e2e8f0",
                        }}
                      >
                        {ch.title}
                      </div>
                      {ch.summary && (
                        <div
                          style={{
                            fontSize: "11px",
                            color: "#94a3b8",
                            marginTop: "2px",
                          }}
                        >
                          {ch.summary}
                        </div>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
