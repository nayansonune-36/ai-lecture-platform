import { createApiClient, type ApiClient } from "@lecture-platform/shared";

let accessTokenInMemory: string | null = null;
let refreshHandler: (() => Promise<string | null>) | null = null;

export const api: ApiClient = createApiClient({
  baseUrl: "/api/v1",
  getAccessToken: () => accessTokenInMemory,
  onUnauthorized: () => (refreshHandler ? refreshHandler() : Promise.resolve(null)),
});

export function setMemoryAccessToken(token: string | null): void {
  accessTokenInMemory = token;
}

export function getMemoryAccessToken(): string | null {
  return accessTokenInMemory;
}

export function setOnUnauthorizedHandler(handler: () => Promise<string | null>): void {
  refreshHandler = handler;
}
