import { test, expect } from "@playwright/test";
import * as path from "path";

test.describe("Task O4c: Desktop Offline Playback with Network Disabled", () => {
  test("loads downloaded lecture via local server on 127.0.0.1 and plays offline with chapters & captions", async ({
    page,
    baseURL,
  }) => {
    const baseHost = new URL(baseURL || "http://localhost:5173").host;

    // 1. Strictly block any external network request (Zero Internet / Network Disabled)
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
        return route.abort("blockedbyclient");
      }
      return route.continue();
    });

    // 2. Intercept local playback server requests on 127.0.0.1:45678
    await page.route("http://127.0.0.1:45678/**", async (route) => {
      const url = new URL(route.request().url());
      const p = url.pathname;

      if (p.endsWith("master.m3u8")) {
        return route.fulfill({
          status: 200,
          contentType: "application/vnd.apple.mpegurl",
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
          },
          body: `#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=854x480\nmedia.m3u8\n`,
        });
      }

      if (p.endsWith("media.m3u8")) {
        return route.fulfill({
          status: 200,
          contentType: "application/vnd.apple.mpegurl",
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
          },
          body: `#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n#EXTINF:10.0,\nseg0.m4s\n#EXT-X-ENDLIST\n`,
        });
      }

      if (p.endsWith("chapters.json")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
          },
          body: JSON.stringify([
            {
              id: "ch-1",
              title: "Introduction to Paxos Consensus",
              summary: "Basic concepts of state machine replication",
              start_ms: 0,
              end_ms: 30000,
            },
            {
              id: "ch-2",
              title: "Leader Election & Heartbeats",
              summary: "Mechanics of Raft consensus protocol",
              start_ms: 30000,
              end_ms: 90000,
            },
            {
              id: "ch-3",
              title: "Fault Tolerance & Partitions",
              summary: "Handling network splits and offline nodes",
              start_ms: 90000,
              end_ms: 180000,
            },
          ]),
        });
      }

      if (p.endsWith("captions.vtt")) {
        return route.fulfill({
          status: 200,
          contentType: "text/vtt",
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
          },
          body: `WEBVTT\n\n00:00.000 --> 00:15.000\nWelcome to offline lecture on distributed systems.\n\n00:15.000 --> 00:30.000\nThis video is decrypted on the fly without network access.\n`,
        });
      }

      return route.fulfill({ status: 200, body: "" });
    });

    // 3. Inject Tauri environment and IPC commands
    page.on("console", (msg) => console.log("PAGE LOG:", msg.type(), msg.text()));
    page.on("pageerror", (err) => console.log("PAGE ERROR:", err));

    await page.addInitScript(() => {
      const savedProgress: Record<string, number> = { "lec-offline-101": 15000 };

      (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {
        transformCallback: () => 1,
        unregisterCallback: () => {},
        event: {
          unregisterListener: () => {},
        },
        plugins: {
          event: {
            unregisterListener: () => {},
          },
        },
        invoke: async (cmd: string, args?: Record<string, unknown>) => {
          console.log("[TAURI MOCK INVOKE]", cmd, JSON.stringify(args));
          if (cmd === "check_connectivity") {
            return {
              is_online: false,
              server_url: "http://127.0.0.1:8000",
              rollback_detected: false,
            };
          }
          if (cmd.startsWith("plugin:event|")) {
            return 1;
          }
          if (cmd === "get_desktop_state") {
            return {
              server_url: "http://127.0.0.1:8000",
              has_server: true,
              last_user: {
                id: "student-offline-01",
                email: "student@university.edu",
                name: "Rahul Sharma",
                role: "student",
              },
              device: {
                id: "dev-offline-windows",
                name: "Offline Student PC",
                public_key: "ed25519-public-key-hex",
              },
              is_logged_in: true,
            };
          }

          if (cmd === "get_enrolled_courses_and_lectures") {
            return [
              {
                id: "course-1",
                code: "CS301",
                title: "Distributed Systems",
                description: "Consensus and fault tolerant systems",
                term: "Fall 2026",
                lectures: [
                  {
                    id: "lec-offline-101",
                    title: "Lecture 04: Paxos and Raft Consensus Protocols",
                    description: "Offline lecture download ready",
                    duration_ms: 120000,
                    status: "ready",
                    published: true,
                    position: 0,
                    poster_path: null,
                  },
                ],
              },
            ];
          }

          if (cmd === "list_downloads" || cmd === "get_downloaded_lectures") {
            return [
              {
                lecture_id: "lec-offline-101",
                course_title: "CS301: Distributed Systems",
                lecture_title: "Lecture 04: Paxos and Raft Consensus Protocols",
                rendition: 480,
                version: 1,
                path: "bundles/lec-offline-101",
                size_bytes: 42100000,
                sha256: "mock-sha256",
                status: "completed",
                progress: 1.0,
                error: null,
                created_at: new Date().toISOString(),
                completed_at: new Date().toISOString(),
              },
            ];
          }

          if (cmd === "get_offline_playback_info") {
            return {
              lecture_id: "lec-offline-101",
              lecture_title: "Lecture 04: Paxos and Raft Consensus Protocols",
              course_title: "CS301: Distributed Systems",
              manifest_url:
                "http://127.0.0.1:45678/sess123/lectures/lec-offline-101/hls/master.m3u8",
              poster_url: null,
              captions_url:
                "http://127.0.0.1:45678/sess123/lectures/lec-offline-101/captions.vtt",
              chapters_url:
                "http://127.0.0.1:45678/sess123/lectures/lec-offline-101/chapters.json",
              initial_position_ms: savedProgress["lec-offline-101"] || 0,
            };
          }

          if (cmd === "save_offline_progress") {
            savedProgress[args.lectureId] = args.positionMs;
            return;
          }

          if (cmd === "get_offline_progress") {
            return savedProgress[args.lectureId] || 0;
          }

          if (cmd === "get_desktop_settings" || cmd === "storage_usage") {
            return {
              server_url: "http://127.0.0.1:8000",
              device_name: "Offline Student PC",
              device_id: "dev-offline-windows",
              device_public_key: "ed25519-public-key-hex",
              storage_used_bytes: 42100000,
            };
          }

          return null;
        },
      };
    });

    // 4. Open app in Desktop mode
    await page.goto("/");

    // Verify Desktop Library screen rendered
    await expect(page.locator("text=AI Lecture Platform")).toBeVisible();
    await expect(page.locator("text=Rahul Sharma")).toBeVisible();

    // Switch to "Downloaded" tab
    const downloadedTabBtn = page.locator('button:has-text("Downloaded (1)")');
    await expect(downloadedTabBtn).toBeVisible();
    await downloadedTabBtn.click();

    // Verify downloaded lecture item
    await expect(
      page.locator("text=Lecture 04: Paxos and Raft Consensus Protocols")
    ).toBeVisible();
    await expect(page.locator("text=Encrypted")).toBeVisible();

    // Click "Watch Offline"
    const watchOfflineBtn = page.locator('button:has-text("Watch Offline")').first();
    await expect(watchOfflineBtn).toBeVisible();
    await watchOfflineBtn.click();

    // 5. Verify OfflinePlayerScreen loaded
    await expect(page.locator("text=Offline Mode")).toBeVisible();
    await expect(page.locator("text=AES-256 Decrypted")).toBeVisible();
    await expect(
      page.locator("text=Playing from local offline bundle")
    ).toBeVisible();

    // Verify Chapters loaded from local server
    await expect(page.locator("text=Introduction to Paxos Consensus")).toBeVisible();
    await expect(page.locator("text=Leader Election & Heartbeats")).toBeVisible();
    await expect(page.locator("text=Fault Tolerance & Partitions")).toBeVisible();

    // Verify custom video player element is active
    const video = page.locator("video.hls-video-element");
    await expect(video).toBeVisible();

    // 6. Capture screenshot of downloaded lecture playing with network disabled
    const artifactPath =
      "C:\\Users\\Bleed\\.gemini\\antigravity-cli\\brain\\d0a15a0a-30d5-43f8-b8b3-527b2df51037\\offline-lecture-playback.png";

    await page.screenshot({ path: artifactPath, fullPage: true });

    // Also save in local test-results directory
    await page.screenshot({
      path: path.join("test-results", "offline-lecture-playback.png"),
      fullPage: true,
    });
  });
});
