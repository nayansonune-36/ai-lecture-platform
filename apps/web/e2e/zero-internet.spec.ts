import { test, expect } from "@playwright/test";

test.describe("Task O1: Zero-Internet Network Audit", () => {
  test("strictly blocks any external request and verifies all assets are locally hosted", async ({ page, baseURL }) => {
    const baseHost = new URL(baseURL || "http://localhost:5173").host;
    const externalRequestsAttempted: string[] = [];
    const localRequestsLoaded: string[] = [];

    // Enforce Zero-Internet: Intercept all requests with a deny list for anything outside baseURL host
    await page.route("**/*", async (route) => {
      const req = route.request();
      const url = new URL(req.url());

      // Allow same host or data/blob schemes
      if (url.host === baseHost || url.protocol === "data:" || url.protocol === "blob:") {
        localRequestsLoaded.push(req.url());
        return route.continue();
      }

      // External request detected! Block and track
      externalRequestsAttempted.push(req.url());
      await route.abort("blockedbyclient");
    });

    // 1. Navigate to the application shell
    await page.goto("/login");
    await expect(page.locator(".login-header h2")).toBeVisible();

    // 2. Verify login form and local SVG icon rendered
    await expect(page.locator(".login-icon-badge svg")).toBeVisible();

    // 3. Verify zero external requests were made during initial page load
    expect(externalRequestsAttempted).toHaveLength(0);

    // 4. Verify local assets loaded (HTML, JS, CSS, fonts)
    expect(localRequestsLoaded.length).toBeGreaterThan(0);
    const hasLocalOrigin = localRequestsLoaded.every((u) => {
      const parsed = new URL(u);
      return parsed.host === baseHost || parsed.protocol === "data:" || parsed.protocol === "blob:";
    });
    expect(hasLocalOrigin).toBe(true);

    // 5. Active test: Verify that any attempted external request is actively blocked by the deny list
    const externalFetchFailed = await page.evaluate(async () => {
      try {
        await fetch("https://fonts.googleapis.com/css?family=Roboto", { mode: "no-cors" });
        return false;
      } catch {
        return true; // Expected: fetch aborted by client
      }
    });
    expect(externalFetchFailed).toBe(true);
    expect(externalRequestsAttempted).toContain("https://fonts.googleapis.com/css?family=Roboto");

    // 6. Active test: Verify CDN script attempt is also blocked
    const cdnFetchFailed = await page.evaluate(async () => {
      try {
        await fetch("https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js", { mode: "no-cors" });
        return false;
      } catch {
        return true;
      }
    });
    expect(cdnFetchFailed).toBe(true);
    expect(externalRequestsAttempted).toContain("https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js");
  });

  test("Service Worker never loads or depends on external network resources", async ({ page }) => {
    // Read and verify the service worker script file content
    const response = await page.goto("/sw.js");
    expect(response?.status()).toBe(200);

    const swContent = await response?.text();
    expect(swContent).toBeDefined();

    // Verify service worker enforces same-origin only rule
    expect(swContent).toContain("url.origin !== self.location.origin");
    // Verify zero external domains in service worker
    expect(swContent).not.toMatch(/https?:\/\/(?!localhost|127\.0\.0\.1)/);
  });
});
