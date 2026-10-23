import React from "react";
import { useServerSetup } from "../hooks/useServerSetup.js";

interface ServerSetupScreenProps {
  initialUrl?: string;
  onConfigured: (url: string) => void;
}

export const ServerSetupScreen: React.FC<ServerSetupScreenProps> = ({
  initialUrl = "",
  onConfigured,
}) => {
  const { serverUrl, setServerUrl, loading, error, handleSubmit } = useServerSetup(onConfigured);

  React.useEffect(() => {
    if (initialUrl && !serverUrl) {
      setServerUrl(initialUrl);
    }
  }, [initialUrl, serverUrl, setServerUrl]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        padding: "24px",
        backgroundColor: "#f9fafb",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "440px",
          backgroundColor: "#ffffff",
          borderRadius: "8px",
          padding: "32px",
          boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
        }}
      >
        <h1 style={{ fontSize: "20px", fontWeight: "600", marginBottom: "8px", color: "#111827" }}>
          Connect to Lecture Platform
        </h1>
        <p style={{ fontSize: "14px", color: "#6b7280", marginBottom: "24px" }}>
          Enter the address of your university's lecture server to get started.
        </p>

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

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "20px" }}>
            <label
              htmlFor="server-address"
              style={{ display: "block", fontSize: "13px", fontWeight: "500", color: "#374151", marginBottom: "6px" }}
            >
              Server Address
            </label>
            <input
              id="server-address"
              type="text"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              placeholder="http://localhost:8080 or lectures.campus.local"
              disabled={loading}
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

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "10px 16px",
              backgroundColor: loading ? "#9ca3af" : "#2563eb",
              color: "#ffffff",
              border: "none",
              borderRadius: "6px",
              fontSize: "14px",
              fontWeight: "500",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Checking server..." : "Connect to Server"}
          </button>
        </form>
      </div>
    </div>
  );
};
