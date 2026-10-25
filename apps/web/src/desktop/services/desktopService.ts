import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { isDesktop } from "../isDesktop.js";
import type {
  DesktopState,
  LoginResult,
  CourseWithLectures,
  DownloadedLecture,
  DownloadRecord,
  DownloadProgressEvent,
  DesktopSettingsInfo,
  OfflinePlaybackInfo,
  LocalServerInfo,
  ConnectivityStatus,
  SyncResult,
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

  async logout(wipeDownloads?: boolean): Promise<void> {
    return invoke<void>("desktop_logout", { wipeDownloads: wipeDownloads ?? false });
  },

  async offlineLogin(): Promise<LoginResult> {
    return invoke<LoginResult>("desktop_offline_login");
  },

  async checkConnectivity(): Promise<ConnectivityStatus> {
    return invoke<ConnectivityStatus>("check_connectivity");
  },

  async syncOfflineLicenses(): Promise<SyncResult> {
    return invoke<SyncResult>("sync_offline_licenses");
  },

  async flushProgressQueue(): Promise<number> {
    return invoke<number>("flush_progress_queue");
  },

  async getEnrolledCoursesAndLectures(): Promise<CourseWithLectures[]> {
    return invoke<CourseWithLectures[]>("get_enrolled_courses_and_lectures");
  },

  async listDownloads(): Promise<DownloadRecord[]> {
    return invoke<DownloadRecord[]>("list_downloads");
  },

  async getDownloadedLectures(): Promise<DownloadedLecture[]> {
    return invoke<DownloadedLecture[]>("list_downloads");
  },

  async startDownload(
    lectureId: string,
    rendition: number = 480,
    lectureTitle?: string,
    courseTitle?: string
  ): Promise<void> {
    return invoke<void>("start_download", {
      lectureId,
      rendition,
      lectureTitle,
      courseTitle,
    });
  },

  async pauseDownload(lectureId: string): Promise<void> {
    return invoke<void>("pause_download", { lectureId });
  },

  async resumeDownload(lectureId: string): Promise<void> {
    return invoke<void>("resume_download", { lectureId });
  },

  async cancelDownload(lectureId: string): Promise<void> {
    return invoke<void>("cancel_download", { lectureId });
  },

  async deleteDownload(lectureId: string): Promise<void> {
    return invoke<void>("delete_download", { lectureId });
  },

  async getOfflineEstimate(
    lectureId: string,
    rendition: number = 480
  ): Promise<number> {
    return invoke<number>("get_offline_estimate", { lectureId, rendition });
  },

  async onDownloadProgress(
    callback: (event: DownloadProgressEvent) => void
  ): Promise<() => void> {
    if (!isDesktop()) {
      return () => {};
    }
    const unlisten = await listen<DownloadProgressEvent>(
      "download_progress",
      (event) => {
        callback(event.payload);
      }
    );
    return unlisten;
  },

  async getLocalServerInfo(): Promise<LocalServerInfo> {
    return invoke<LocalServerInfo>("get_local_server_info");
  },

  async getOfflinePlaybackInfo(
    lectureId: string
  ): Promise<OfflinePlaybackInfo> {
    return invoke<OfflinePlaybackInfo>("get_offline_playback_info", {
      lectureId,
    });
  },

  async saveOfflineProgress(
    lectureId: string,
    positionMs: number,
    completed: boolean
  ): Promise<void> {
    return invoke<void>("save_offline_progress", {
      lectureId,
      positionMs,
      completed,
    });
  },

  async getOfflineProgress(lectureId: string): Promise<number> {
    return invoke<number>("get_offline_progress", { lectureId });
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
