import { test, expect } from "@playwright/test";

test.describe("Task O1: Zero-Internet Network Audit", () => {
  test("strictly blocks any external request and verifies all assets are locally hosted", async ({ page, baseURL }) => {
    const baseHost = new URL(baseURL || "http://localhost:5173").host;
    const violations: string[] = [];

    // Zero-Internet Guard: Intercept all requests; push blocked non-local URLs into violations array
    await page.route("**/*", async (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const isLocal =
        url.protocol === "data:" ||
        url.protocol === "blob:" ||
        url.host === baseHost ||
        url.hostname === "localhost" ||
        url.hostname === "127.0.0.1";

      if (!isLocal) {
        violations.push(req.url());
        return route.abort("blockedbyclient");
      }
      return route.continue();
    });

    // 1. Navigate to the application shell
    await page.goto("/login");
    await expect(page.locator(".login-header h2")).toBeVisible();

    // 2. Verify login form and local SVG icon rendered
    await expect(page.locator(".login-icon-badge svg")).toBeVisible();

    // 3. Navigate across app pages
    await page.goto("/courses");
    await expect(page).toHaveURL(/\/login/); // ProtectedRoute redirects unauthenticated

    // Assert zero non-local URLs were requested during app usage
    expect(violations).toEqual([]);
  });

  test("Service Worker never loads or depends on external network resources", async ({ page, baseURL }) => {
    const baseHost = new URL(baseURL || "http://localhost:5173").host;
    const violations: string[] = [];

    await page.route("**/*", async (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const isLocal =
        url.protocol === "data:" ||
        url.protocol === "blob:" ||
        url.host === baseHost ||
        url.hostname === "localhost" ||
        url.hostname === "127.0.0.1";

      if (!isLocal) {
        violations.push(req.url());
        return route.abort("blockedbyclient");
      }
      return route.continue();
    });

    const response = await page.goto("/sw.js");
    expect(response?.status()).toBe(200);

    const swContent = await response?.text();
    expect(swContent).toBeDefined();

    // Verify service worker enforces same-origin only rule
    expect(swContent).toContain("url.origin !== self.location.origin");
    // Verify zero external domains in service worker
    expect(swContent).not.toMatch(/https?:\/\/(?!localhost|127\.0\.0\.1)/);

    // Assert zero non-local URLs were requested
    expect(violations).toEqual([]);
  });
});
