export interface UserProfile {
  id: string;
  email: string;
  name: string;
  role: string;
}

export interface DeviceInfo {
  id: string | null;
  name: string;
  public_key: string;
}

export interface DesktopState {
  server_url: string | null;
  has_server: boolean;
  last_user: UserProfile | null;
  device: DeviceInfo;
  is_logged_in: boolean;
}

export interface LoginResult {
  user: UserProfile;
  device_id: string;
}

export interface LectureItem {
  id: string;
  title: string;
  description: string | null;
  duration_ms: number | null;
  status: string;
  published: boolean;
  position: number;
  poster_path: string | null;
}

export interface CourseWithLectures {
  id: string;
  code: string;
  title: string;
  description: string | null;
  term: string | null;
  lectures: LectureItem[];
}

export interface DownloadRecord {
  lecture_id: string;
  course_title: string;
  lecture_title: string;
  rendition: number;
  version: number;
  path: string | null;
  size_bytes: number;
  sha256: string;
  status: "pending" | "downloading" | "paused" | "encrypting" | "completed" | "failed" | string;
  progress: number;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  days_left?: number | null;
  is_expired?: boolean;
  expires_at?: string | null;
}

export type DownloadedLecture = DownloadRecord;

export interface ConnectivityStatus {
  is_online: boolean;
  server_url: string | null;
  rollback_detected: boolean;
}

export interface SyncResult {
  is_online: boolean;
  renewed_count: number;
  revoked_count: number;
  revoked_titles: string[];
  progress_flushed_count: number;
  error: string | null;
}

export interface DownloadProgressEvent {
  lecture_id: string;
  bytes_downloaded: number;
  total_bytes: number;
  speed_bps: number;
  state: "pending" | "downloading" | "paused" | "encrypting" | "completed" | "failed" | string;
  error?: string | null;
}

export interface ChapterItem {
  id?: string;
  lecture_id?: string;
  title: string;
  summary?: string;
  start_ms: number;
  end_ms?: number;
}

export interface OfflinePlaybackInfo {
  lecture_id: string;
  lecture_title: string;
  course_title: string;
  manifest_url: string;
  poster_url: string | null;
  captions_url: string | null;
  chapters_url: string | null;
  initial_position_ms: number;
}

export interface LocalServerInfo {
  port: number;
  session_token: string;
  base_url: string;
}

export interface DesktopSettingsInfo {
  server_url: string;
  device_name: string;
  device_id: string | null;
  device_public_key: string;
  storage_used_bytes: number;
}
