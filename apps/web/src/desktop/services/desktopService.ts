import { invoke } from "@tauri-apps/api/core";
import type {
  DesktopState,
  LoginResult,
  CourseWithLectures,
  DownloadedLecture,
  DesktopSettingsInfo,
} from "../types.js";

export const desktopService = {
  async getDesktopState(): Promise<DesktopState> {
    return invoke<DesktopState>("get_desktop_state");
  },

  async validateAndSetServerUrl(
    serverUrl: string
  ): Promise<{ status: string; server_url: string }> {
    return invoke<{ status: string; server_url: string }>(
      "validate_and_set_server_url",
      { serverUrl }
    );
  },

  async login(email: string, password: string): Promise<LoginResult> {
    return invoke<LoginResult>("desktop_login", { email, password });
  },

  async logout(): Promise<void> {
    return invoke<void>("desktop_logout");
  },

  async getEnrolledCoursesAndLectures(): Promise<CourseWithLectures[]> {
    return invoke<CourseWithLectures[]>("get_enrolled_courses_and_lectures");
  },

  async getDownloadedLectures(): Promise<DownloadedLecture[]> {
    return invoke<DownloadedLecture[]>("get_downloaded_lectures");
  },

  async getSettings(): Promise<DesktopSettingsInfo> {
    return invoke<DesktopSettingsInfo>("get_desktop_settings");
  },

  async updateSettings(
    serverUrl?: string,
    deviceName?: string
  ): Promise<DesktopSettingsInfo> {
    return invoke<DesktopSettingsInfo>("update_desktop_settings", {
      serverUrl,
      deviceName,
    });
  },
};
