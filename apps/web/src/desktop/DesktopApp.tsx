import React, { useState } from "react";
import { useDesktopState } from "./hooks/useDesktopState.js";
import { ServerSetupScreen } from "./screens/ServerSetupScreen.js";
import { LoginScreen } from "./screens/LoginScreen.js";
import { LibraryScreen } from "./screens/LibraryScreen.js";
import { SettingsScreen } from "./screens/SettingsScreen.js";
import { OfflinePlayerScreen } from "./screens/OfflinePlayerScreen.js";
import { desktopService } from "./services/desktopService.js";
import type { UserProfile } from "./types.js";

type DesktopScreen = "server_setup" | "login" | "library" | "settings" | "player";

export const DesktopApp: React.FC = () => {
  const { state, loading, refresh } = useDesktopState();
  const [currentScreen, setCurrentScreen] = useState<DesktopScreen | null>(null);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [selectedLectureId, setSelectedLectureId] = useState<string | null>(null);

  React.useEffect(() => {
    if (!loading && state) {
      if (!state.has_server) {
        setCurrentScreen("server_setup");
      } else if (!state.is_logged_in && !currentUser) {
        setCurrentScreen("login");
      } else if (!currentScreen) {
        if (state.last_user && !currentUser) {
          setCurrentUser(state.last_user);
        }
        setCurrentScreen("library");
      }
    }
  }, [loading, state, currentUser, currentScreen]);

  if (loading || !state) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
          backgroundColor: "#f9fafb",
          fontFamily: "system-ui, -apple-system, sans-serif",
          color: "#4b5563",
        }}
      >
        Initializing desktop application...
      </div>
    );
  }

  const handleServerConfigured = () => {
    void refresh();
    setCurrentScreen("login");
  };

  const handleLoginSuccess = (user: UserProfile) => {
    setCurrentUser(user);
    void refresh();
    setCurrentScreen("library");
  };

  const handleSignOut = async (wipeDownloads?: boolean) => {
    try {
      await desktopService.logout(wipeDownloads);
    } catch (err) {
      console.error("Sign out error:", err);
    }
    setCurrentUser(null);
    void refresh();
    setCurrentScreen("login");
  };

  const handlePlayLecture = (lectureId: string) => {
    setSelectedLectureId(lectureId);
    setCurrentScreen("player");
  };

  switch (currentScreen) {
    case "server_setup":
      return (
        <ServerSetupScreen
          initialUrl={state.server_url || ""}
          onConfigured={handleServerConfigured}
        />
      );

    case "login":
      return (
        <LoginScreen
          serverUrl={state.server_url || ""}
          lastUser={state.last_user}
          onLoginSuccess={handleLoginSuccess}
          onChangeServer={() => setCurrentScreen("server_setup")}
        />
      );

    case "settings":
      return (
        <SettingsScreen
          onBack={() => setCurrentScreen("library")}
        />
      );

    case "player":
      if (!selectedLectureId) {
        setCurrentScreen("library");
        return null;
      }
      return (
        <OfflinePlayerScreen
          lectureId={selectedLectureId}
          onBack={() => {
            setSelectedLectureId(null);
            setCurrentScreen("library");
          }}
        />
      );

    case "library":
    default:
      if (!currentUser) {
        return (
          <LoginScreen
            serverUrl={state.server_url || ""}
            lastUser={state.last_user}
            onLoginSuccess={handleLoginSuccess}
            onChangeServer={() => setCurrentScreen("server_setup")}
          />
        );
      }
      return (
        <LibraryScreen
          user={currentUser}
          onOpenSettings={() => setCurrentScreen("settings")}
          onSignOut={handleSignOut}
          onPlayLecture={handlePlayLecture}
        />
      );
  }
};
