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
}

export type DownloadedLecture = DownloadRecord;

export interface DownloadProgressEvent {
  lecture_id: string;
  bytes_downloaded: number;
  total_bytes: number;
  speed_bps: number;
  state: "pending" | "downloading" | "paused" | "encrypting" | "completed" | "failed" | string;
  error?: string | null;
}

export interface DesktopSettingsInfo {
  server_url: string;
  device_name: string;
  device_id: string | null;
  device_public_key: string;
  storage_used_bytes: number;
}
