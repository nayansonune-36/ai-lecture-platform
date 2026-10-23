/**
 * Generated API client for AI Lecture Platform backend.
 * Provides typed operations derived from FastAPI OpenAPI schema.
 */

import type { components } from "./schema.js";

export type UserOut = components["schemas"]["UserOut"];
export type UserRole = components["schemas"]["UserRole"];
export type CourseOut = components["schemas"]["CourseOut"];
export type CourseCreate = components["schemas"]["CourseCreate"];
export type CourseUpdate = components["schemas"]["CourseUpdate"];
export type ChunkUploadResponse = components["schemas"]["ChunkUploadResponse"];
export type UploadCompleteResponse = components["schemas"]["UploadCompleteResponse"];
export type LectureOut = components["schemas"]["LectureOut"];
export type LectureCreate = components["schemas"]["LectureCreate"];
export type LectureCreateResponse = components["schemas"]["LectureCreateResponse"];
export type LectureUpdate = components["schemas"]["LectureUpdate"];
export type LectureStatus = components["schemas"]["LectureStatus"];
export type JobOut = components["schemas"]["JobOut"];
export type JobStatus = components["schemas"]["JobStatus"];
export type JobType = components["schemas"]["JobType"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type LoginResponse = components["schemas"]["LoginResponse"];
export type RefreshRequest = components["schemas"]["RefreshRequest"];
export type RefreshResponse = components["schemas"]["RefreshResponse"];
export type LogoutRequest = components["schemas"]["LogoutRequest"];
export type LogoutResponse = components["schemas"]["LogoutResponse"];
export type EnrollmentMemberOut = components["schemas"]["EnrollmentMemberOut"];
export type EnrollmentRole = components["schemas"]["EnrollmentRole"];
export interface EnrollmentAddRequest {
  emails: string[];
  role?: EnrollmentRole;
}
export type EnrollmentAddResponse = components["schemas"]["EnrollmentAddResponse"];
export type HealthzResponse = components["schemas"]["HealthzResponse"];
export type ReadyzResponse = components["schemas"]["ReadyzResponse"];
export type StatusResponse = components["schemas"]["StatusResponse"];
export type PlaybackTokenResponse = components["schemas"]["PlaybackTokenResponse"];
export type ChapterOut = components["schemas"]["ChapterOut"];
export type PlaybackProgressOut = components["schemas"]["PlaybackProgressOut"];
export type PlaybackProgressUpdate = components["schemas"]["PlaybackProgressUpdate"];
export type DeviceCreate = components["schemas"]["DeviceCreate"];
export type DeviceOut = components["schemas"]["DeviceOut"];
export type LicenseRenewRequest = components["schemas"]["LicenseRenewRequest"];
export type LicenseRenewResponse = components["schemas"]["LicenseRenewResponse"];
export type RenewedLicenseOut = components["schemas"]["RenewedLicenseOut"];
export type LicensePublicKeyResponse = components["schemas"]["LicensePublicKeyResponse"];
export type OfflineBundleRequest = components["schemas"]["OfflineBundleRequest"];
export type OfflineBundleResponse = components["schemas"]["OfflineBundleResponse"];
export type OfflineEstimateResponse = components["schemas"]["OfflineEstimateResponse"];

export class ApiError extends Error {
  public status: number;
  public code: string;
  public detail?: unknown;

  constructor(status: number, message: string, code: string = "api_error", detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export interface ApiClientConfig {
  baseUrl?: string;
  getAccessToken?: () => string | null;
  onUnauthorized?: () => Promise<string | null>;
}

export class ApiClient {
  private baseUrl: string;
  private getAccessToken: () => string | null;
  private onUnauthorized?: () => Promise<string | null>;
  private isRefreshing = false;

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = config.baseUrl ?? "/api/v1";
    this.getAccessToken = config.getAccessToken ?? (() => null);
    this.onUnauthorized = config.onUnauthorized;
  }

  public setTokenGetter(getter: () => string | null): void {
    this.getAccessToken = getter;
  }

  public setUnauthorizedHandler(handler: () => Promise<string | null>): void {
    this.onUnauthorized = handler;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    isRetry = false
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
    const headers = new Headers(options.headers);

    if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const token = this.getAccessToken();
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401 && !isRetry && this.onUnauthorized && !this.isRefreshing) {
      this.isRefreshing = true;
      try {
        const newToken = await this.onUnauthorized();
        this.isRefreshing = false;
        if (newToken) {
          headers.set("Authorization", `Bearer ${newToken}`);
          return this.request<T>(endpoint, { ...options, headers }, true);
        }
      } catch {
        this.isRefreshing = false;
      }
    }

    if (!response.ok) {
      let code = "http_error";
      let message = `Request failed with status ${response.status}`;
      let detail: unknown = undefined;

      try {
        const errJson = await response.json();
        detail = errJson;
        if (typeof errJson.detail === "string") {
          message = errJson.detail;
        } else if (errJson.message) {
          message = errJson.message;
        }
        if (errJson.code) {
          code = errJson.code;
        }
      } catch {
        // Fallback to text message
        try {
          const txt = await response.text();
          if (txt) message = txt;
        } catch {
          // ignore
        }
      }

      throw new ApiError(response.status, message, code, detail);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  }

  // --- Auth endpoints ---
  public auth = {
    login: (body: LoginRequest): Promise<LoginResponse> =>
      this.request<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    refresh: (body: RefreshRequest): Promise<RefreshResponse> =>
      this.request<RefreshResponse>("/auth/refresh", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    logout: (body?: LogoutRequest): Promise<LogoutResponse> =>
      this.request<LogoutResponse>("/auth/logout", {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      }),

    me: (): Promise<UserOut> =>
      this.request<UserOut>("/me", {
        method: "GET",
      }),
  };

  // --- Course endpoints ---
  public courses = {
    list: (): Promise<CourseOut[]> =>
      this.request<CourseOut[]>("/courses", {
        method: "GET",
      }),

    get: (id: string): Promise<CourseOut> =>
      this.request<CourseOut>(`/courses/${id}`, {
        method: "GET",
      }),

    create: (body: CourseCreate): Promise<CourseOut> =>
      this.request<CourseOut>("/courses", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    update: (id: string, body: CourseUpdate): Promise<CourseOut> =>
      this.request<CourseOut>(`/courses/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),

    getEnrollments: (id: string): Promise<EnrollmentMemberOut[]> =>
      this.request<EnrollmentMemberOut[]>(`/courses/${id}/enrollments`, {
        method: "GET",
      }),

    addEnrollments: (id: string, body: EnrollmentAddRequest): Promise<EnrollmentAddResponse> =>
      this.request<EnrollmentAddResponse>(`/courses/${id}/enrollments`, {
        method: "POST",
        body: JSON.stringify(body),
      }),

    addEnrollmentsCsv: (id: string, file: Blob, role?: EnrollmentRole): Promise<EnrollmentAddResponse> => {
      const formData = new FormData();
      formData.append("file", file);
      if (role) formData.append("role", role);
      return this.request<EnrollmentAddResponse>(`/courses/${id}/enrollments`, {
        method: "POST",
        body: formData,
      });
    },

    removeEnrollment: (id: string, userId: string): Promise<StatusResponse> =>
      this.request<StatusResponse>(`/courses/${id}/enrollments/${userId}`, {
        method: "DELETE",
      }),
  };

  // --- Lecture endpoints ---
  public lectures = {
    list: (courseId: string): Promise<LectureOut[]> =>
      this.request<LectureOut[]>(`/courses/${courseId}/lectures`, {
        method: "GET",
      }),

    get: (id: string): Promise<LectureOut> =>
      this.request<LectureOut>(`/lectures/${id}`, {
        method: "GET",
      }),

    create: (courseId: string, body: LectureCreate): Promise<LectureCreateResponse> =>
      this.request<LectureCreateResponse>(`/courses/${courseId}/lectures`, {
        method: "POST",
        body: JSON.stringify(body),
      }),

    uploadChunk: (
      lectureIdOrUrl: string,
      chunk: Blob,
      contentRange: string
    ): Promise<ChunkUploadResponse> => {
      const endpoint = lectureIdOrUrl.startsWith("/api/v1")
        ? lectureIdOrUrl.replace(/^\/api\/v1/, "")
        : lectureIdOrUrl.startsWith("/")
        ? lectureIdOrUrl
        : `/lectures/${lectureIdOrUrl}/upload`;
      return this.request<ChunkUploadResponse>(endpoint, {
        method: "PUT",
        headers: {
          "Content-Range": contentRange,
          "Content-Type": "application/octet-stream",
        },
        body: chunk,
      });
    },

    completeUpload: (lectureId: string): Promise<UploadCompleteResponse> =>
      this.request<UploadCompleteResponse>(`/lectures/${lectureId}/upload/complete`, {
        method: "POST",
      }),

    update: (id: string, body: LectureUpdate): Promise<LectureOut> =>
      this.request<LectureOut>(`/lectures/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),

    delete: (id: string): Promise<StatusResponse> =>
      this.request<StatusResponse>(`/lectures/${id}`, {
        method: "DELETE",
      }),

    getJobs: (id: string): Promise<JobOut[]> =>
      this.request<JobOut[]>(`/lectures/${id}/jobs`, {
        method: "GET",
      }),
  };

  // --- Health endpoints ---
  public health = {
    healthz: (): Promise<HealthzResponse> =>
      this.request<HealthzResponse>("/healthz", {
        method: "GET",
      }),

    readyz: (): Promise<ReadyzResponse> =>
      this.request<ReadyzResponse>("/readyz", {
        method: "GET",
      }),
  };

  // --- Playback endpoints ---
  public playback = {
    getToken: (lectureId: string): Promise<PlaybackTokenResponse> =>
      this.request<PlaybackTokenResponse>(`/lectures/${lectureId}/playback-token`, {
        method: "POST",
      }),

    getCaptionsUrl: (lectureId: string, lang?: string): string => {
      const q = lang ? `?lang=${encodeURIComponent(lang)}` : "";
      return `${this.baseUrl}/lectures/${lectureId}/captions.vtt${q}`;
    },

    getChapters: (lectureId: string): Promise<ChapterOut[]> =>
      this.request<ChapterOut[]>(`/lectures/${lectureId}/chapters`, {
        method: "GET",
      }),

    getProgress: (lectureId: string): Promise<PlaybackProgressOut> =>
      this.request<PlaybackProgressOut>(`/lectures/${lectureId}/progress`, {
        method: "GET",
      }),

    saveProgress: (lectureId: string, body: PlaybackProgressUpdate): Promise<PlaybackProgressOut> =>
      this.request<PlaybackProgressOut>(`/lectures/${lectureId}/progress`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
  };

  // --- Device & Offline endpoints ---
  public offline = {
    getDevices: (): Promise<DeviceOut[]> =>
      this.request<DeviceOut[]>("/devices", {
        method: "GET",
      }),

    registerDevice: (body: DeviceCreate): Promise<DeviceOut> =>
      this.request<DeviceOut>("/devices", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    revokeDevice: (deviceId: string): Promise<StatusResponse> =>
      this.request<StatusResponse>(`/devices/${deviceId}`, {
        method: "DELETE",
      }),

    getLicensePublicKey: (): Promise<LicensePublicKeyResponse> =>
      this.request<LicensePublicKeyResponse>("/license-public-key", {
        method: "GET",
      }),

    renewLicenses: (body: LicenseRenewRequest): Promise<LicenseRenewResponse> =>
      this.request<LicenseRenewResponse>("/offline-licenses/renew", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    getOfflineEstimate: (lectureId: string, rendition: number = 480): Promise<OfflineEstimateResponse> =>
      this.request<OfflineEstimateResponse>(`/lectures/${lectureId}/offline-estimate?rendition=${rendition}`, {
        method: "GET",
      }),

    requestOfflineBundle: (lectureId: string, body: OfflineBundleRequest): Promise<OfflineBundleResponse> =>
      this.request<OfflineBundleResponse>(`/lectures/${lectureId}/offline-bundle`, {
        method: "POST",
        body: JSON.stringify(body),
      }),

    getOfflineBundleStatus: (jobId: string): Promise<OfflineBundleResponse> =>
      this.request<OfflineBundleResponse>(`/offline-bundles/${jobId}`, {
        method: "GET",
      }),
  };
}

export const createApiClient = (config?: ApiClientConfig): ApiClient => new ApiClient(config);
