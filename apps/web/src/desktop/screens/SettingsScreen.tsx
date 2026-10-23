import React from "react";
import { useDesktopSettings } from "../hooks/useDesktopSettings.js";

interface SettingsScreenProps {
  onBack: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0.0 MB";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) {
    return `${(mb / 1024).toFixed(2)} GB`;
  }
  return `${mb.toFixed(2)} MB`;
}

export const SettingsScreen: React.FC<SettingsScreenProps> = ({ onBack }) => {
  const {
    settings,
    serverUrl,
    setServerUrl,
    deviceName,
    setDeviceName,
    loading,
    saving,
    error,
    success,
    handleSave,
  } = useDesktopSettings();

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
      {/* Header */}
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
          <button
            onClick={onBack}
            style={{
              padding: "6px 12px",
              backgroundColor: "#f3f4f6",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            ← Back to Library
          </button>
          <h1 style={{ fontSize: "18px", fontWeight: "600", color: "#111827", margin: 0 }}>
            Desktop Settings
          </h1>
        </div>
      </header>

      {/* Content */}
      <main style={{ flex: 1, padding: "24px", maxWidth: "680px", margin: "0 auto", width: "100%" }}>
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

        {success && (
          <div
            style={{
              padding: "12px",
              backgroundColor: "#dcfce7",
              color: "#15803d",
              borderRadius: "6px",
              fontSize: "14px",
              marginBottom: "16px",
            }}
          >
            {success}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", padding: "48px", color: "#6b7280" }}>
            Loading settings...
          </div>
        ) : (
          <form
            onSubmit={handleSave}
            style={{
              backgroundColor: "#ffffff",
              borderRadius: "8px",
              border: "1px solid #e5e7eb",
              padding: "24px",
            }}
          >
            <div style={{ marginBottom: "20px" }}>
              <label
                htmlFor="settings-server"
                style={{ display: "block", fontSize: "13px", fontWeight: "500", color: "#374151", marginBottom: "6px" }}
              >
                Server Address
              </label>
              <input
                id="settings-server"
                type="text"
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  border: "1px solid #d1d5db",
                  borderRadius: "6px",
                  fontSize: "14px",
                  boxSizing: "border-box",
                }}
              />
              <span style={{ fontSize: "12px", color: "#6b7280", marginTop: "4px", display: "block" }}>
                The backend API address for lecture downloads and synchronization.
              </span>
            </div>

            <div style={{ marginBottom: "20px" }}>
              <label
                htmlFor="settings-device-name"
                style={{ display: "block", fontSize: "13px", fontWeight: "500", color: "#374151", marginBottom: "6px" }}
              >
                Device Name
              </label>
              <input
                id="settings-device-name"
                type="text"
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  border: "1px solid #d1d5db",
                  borderRadius: "6px",
                  fontSize: "14px",
                  boxSizing: "border-box",
                }}
              />
            </div>

            <div style={{ marginBottom: "20px", padding: "16px", backgroundColor: "#f9fafb", borderRadius: "6px" }}>
              <div style={{ fontSize: "13px", fontWeight: "500", color: "#374151", marginBottom: "8px" }}>
                Device Identity & Storage
              </div>
              <div style={{ fontSize: "13px", color: "#4b5563", marginBottom: "6px" }}>
                <strong>Device ID:</strong> {settings?.device_id || "Unregistered"}
              </div>
              <div
                style={{
                  fontSize: "12px",
                  color: "#6b7280",
                  wordBreak: "break-all",
                  marginBottom: "8px",
                  fontFamily: "monospace",
                }}
              >
                <strong>Public Key:</strong> {settings?.device_public_key}
              </div>
              <div style={{ fontSize: "13px", color: "#4b5563" }}>
                <strong>Offline Storage Used:</strong> {formatBytes(settings?.storage_used_bytes || 0)}
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button
                type="button"
                onClick={onBack}
                style={{
                  padding: "8px 16px",
                  backgroundColor: "#ffffff",
                  border: "1px solid #d1d5db",
                  borderRadius: "6px",
                  fontSize: "14px",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                style={{
                  padding: "8px 16px",
                  backgroundColor: saving ? "#9ca3af" : "#2563eb",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "6px",
                  fontSize: "14px",
                  fontWeight: "500",
                  cursor: saving ? "not-allowed" : "pointer",
                }}
              >
                {saving ? "Saving..." : "Save Settings"}
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
};
