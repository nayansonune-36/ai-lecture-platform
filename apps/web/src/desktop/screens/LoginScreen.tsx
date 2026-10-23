import React from "react";
import { useDesktopAuth } from "../hooks/useDesktopAuth.js";
import type { UserProfile } from "../types.js";

interface LoginScreenProps {
  serverUrl: string;
  lastUser: UserProfile | null;
  onLoginSuccess: (user: UserProfile) => void;
  onChangeServer: () => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({
  serverUrl,
  lastUser,
  onLoginSuccess,
  onChangeServer,
}) => {
  const {
    user,
    email,
    setEmail,
    password,
    setPassword,
    loading,
    error,
    handleLogin,
  } = useDesktopAuth(lastUser);

  React.useEffect(() => {
    if (user) {
      onLoginSuccess(user);
    }
  }, [user, onLoginSuccess]);

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
          maxWidth: "400px",
          backgroundColor: "#ffffff",
          borderRadius: "8px",
          padding: "32px",
          boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
        }}
      >
        <h1 style={{ fontSize: "20px", fontWeight: "600", marginBottom: "4px", color: "#111827" }}>
          Student Sign In
        </h1>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "20px" }}>
          <span style={{ fontSize: "13px", color: "#6b7280" }}>
            Server: <strong style={{ color: "#374151" }}>{serverUrl}</strong>
          </span>
          <button
            onClick={onChangeServer}
            style={{
              background: "none",
              border: "none",
              color: "#2563eb",
              fontSize: "12px",
              cursor: "pointer",
              padding: 0,
              textDecoration: "underline",
            }}
          >
            Change
          </button>
        </div>

        {lastUser && (
          <div
            style={{
              padding: "10px 12px",
              backgroundColor: "#f3f4f6",
              borderRadius: "6px",
              fontSize: "13px",
              color: "#4b5563",
              marginBottom: "16px",
            }}
          >
            Last signed in as <strong>{lastUser.name}</strong> ({lastUser.email})
          </div>
        )}

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

        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: "16px" }}>
            <label
              htmlFor="email"
              style={{ display: "block", fontSize: "13px", fontWeight: "500", color: "#374151", marginBottom: "6px" }}
            >
              Email address
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="student@university.edu"
              required
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

          <div style={{ marginBottom: "20px" }}>
            <label
              htmlFor="password"
              style={{ display: "block", fontSize: "13px", fontWeight: "500", color: "#374151", marginBottom: "6px" }}
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
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
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
};
