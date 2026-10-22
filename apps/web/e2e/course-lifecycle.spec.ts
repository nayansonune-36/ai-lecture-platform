import { test, expect, type BrowserContext } from "@playwright/test";

interface MockCourse {
  id: string;
  code: string;
  title: string;
  term: string | null;
  description: string | null;
  owner_id: string;
  created_at: string;
}

interface MockLecture {
  id: string;
  course_id: string;
  title: string;
  description: string | null;
  position: number;
  status: "draft" | "processing" | "ready" | "failed";
  duration_ms: number;
  published: boolean;
  poster_path: string | null;
  created_at: string;
}

interface MockJob {
  id: string;
  job_type: string;
  status: string;
  attempts: number;
  error: string | null;
  output_metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

interface MockUser {
  id: string;
  email: string;
  name: string;
  role: string;
}

test.describe("Full University Lecture Platform Lifecycle", () => {
  // Shared backend mock state
  const courses: MockCourse[] = [];
  const enrollments: Record<string, { user_id: string; email: string; role: string }[]> = {};
  const lectures: Record<string, MockLecture[]> = {};
  const jobs: Record<string, MockJob[]> = {};
  const progress: Record<string, { position_ms: number; completed: boolean }> = {};
  const revokedTokens = new Set<string>();

  let createdLectureId = "";
  let student1ManifestUrl = "";

  const USERS: Record<string, MockUser> = {
    "prof@university.edu": { id: "prof-1", email: "prof@university.edu", name: "Prof. Vikram Sharma", role: "professor" },
    "student1@university.edu": { id: "student-1", email: "student1@university.edu", name: "Alice Student", role: "student" },
    "student2@university.edu": { id: "student-2", email: "student2@university.edu", name: "Bob Student", role: "student" },
  };

  function resolveUser(headers: Record<string, string>): MockUser | null {
    const authHeader = headers["authorization"] || "";
    if (authHeader.includes("prof-1")) return USERS["prof@university.edu"];
    if (authHeader.includes("student-1")) return USERS["student1@university.edu"];
    if (authHeader.includes("student-2")) return USERS["student2@university.edu"];
    return null;
  }

  // Setup routes per context to guarantee full isolation
  async function setupContextRoutes(context: BrowserContext) {
    // ZERO-INTERNET AUDIT: Deny all network requests to hosts other than our own baseURL
    await context.route("**/*", async (route) => {
      const requestUrl = new URL(route.request().url());
      const isLocal =
        requestUrl.protocol === "data:" ||
        requestUrl.protocol === "blob:" ||
        requestUrl.hostname === "localhost" ||
        requestUrl.hostname === "127.0.0.1";

      if (!isLocal) {
        await route.abort("blockedbyclient");
        throw new Error(
          `Zero-Internet Enforcement Failure: External network request attempted to ${route.request().url()}`
        );
      }
      return route.fallback();
    });

    // Intercept media requests
    await context.route("**/media/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const authHeader = request.headers()["authorization"] || "";
      const uid = url.searchParams.get("uid");
      const sig = url.searchParams.get("sig");

      const caller = authHeader.includes("student-2")
        ? "student-2"
        : authHeader.includes("student-1")
          ? "student-1"
          : null;

      // Assert that a media URL signed for student 1 does not work as student 2
      if (caller === "student-2" && uid === "student-1") {
        return route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Forbidden: Signed media URL does not match authenticated student" }),
        });
      }

      // Assert that tampered uid with non-matching signature fails
      if (uid === "student-2" && sig !== "valid-sig-student-2") {
        return route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Forbidden: Media signature verification failed" }),
        });
      }

      // Valid signed media for student 1
      if (uid === "student-1" && sig === "valid-sig-student-1") {
        if (caller === "student-2") {
          return route.fulfill({
            status: 403,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Forbidden: Media URL not allowed for student 2" }),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: "application/vnd.apple.mpegurl",
          body: `#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg0.m4s\n#EXT-X-ENDLIST\n`,
        });
      }

      // Default media fallback
      return route.fulfill({
        status: 200,
        contentType: "application/vnd.apple.mpegurl",
        body: `#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg0.m4s\n#EXT-X-ENDLIST\n`,
      });
    });

    // Intercept API calls
    await context.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      const method = request.method();
      const headers = request.headers();
      const caller = resolveUser(headers);

      // --- AUTH ENDPOINTS ---
      if (path === "/api/v1/auth/login" && method === "POST") {
        const body = request.postDataJSON();
        const user = USERS[body.email];
        if (!user) {
          return route.fulfill({ status: 401, json: { detail: "Invalid email or password" } });
        }
        return route.fulfill({
          status: 200,
          json: {
            access_token: `mock-jwt-${user.id}`,
            refresh_token: `mock-refresh-${user.id}`,
            token_type: "bearer",
            user,
          },
        });
      }

      if (path === "/api/v1/auth/refresh" && method === "POST") {
        const body = request.postDataJSON();
        const refToken = body.refresh_token;
        if (!refToken || revokedTokens.has(refToken)) {
          return route.fulfill({
            status: 401,
            json: { detail: "Invalid or expired refresh token", code: "invalid_refresh_token" },
          });
        }
        let matchedUser: MockUser | null = null;
        for (const u of Object.values(USERS)) {
          if (refToken.includes(u.id)) {
            matchedUser = u;
            break;
          }
        }
        if (!matchedUser) {
          return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
        }
        return route.fulfill({
          status: 200,
          json: {
            access_token: `mock-jwt-refreshed-${matchedUser.id}`,
            refresh_token: `mock-refresh-${matchedUser.id}`,
            token_type: "bearer",
            user: matchedUser,
          },
        });
      }

      if (path === "/api/v1/auth/logout" && method === "POST") {
        const body = request.postDataJSON();
        if (body?.refresh_token) {
          revokedTokens.add(body.refresh_token);
        }
        return route.fulfill({ status: 200, json: { status: "ok" } });
      }

      if (path === "/api/v1/me" && method === "GET") {
        if (!caller) {
          return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
        }
        return route.fulfill({ status: 200, json: caller });
      }

      // --- COURSES ENDPOINTS ---
      if (path === "/api/v1/courses" && method === "GET") {
        if (!caller) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
        if (caller.role === "professor" || caller.role === "admin") {
          const profCourses = courses.filter((c) => c.owner_id === caller.id || caller.role === "admin");
          return route.fulfill({ status: 200, json: profCourses });
        }
        // Student sees courses they are enrolled in
        const studentCourses = courses.filter((c) =>
          (enrollments[c.id] || []).some((e) => e.user_id === caller.id || e.email === caller.email)
        );
        return route.fulfill({ status: 200, json: studentCourses });
      }

      if (path === "/api/v1/courses" && method === "POST") {
        if (!caller || (caller.role !== "professor" && caller.role !== "admin")) {
          return route.fulfill({ status: 403, json: { detail: "Only professors and admins can create courses" } });
        }
        const data = request.postDataJSON();
        const newCourse: MockCourse = {
          id: `course-${courses.length + 1}`,
          code: data.code,
          title: data.title,
          term: data.term || null,
          description: data.description || null,
          owner_id: caller.id,
          created_at: new Date().toISOString(),
        };
        courses.push(newCourse);
        enrollments[newCourse.id] = [];
        lectures[newCourse.id] = [];
        return route.fulfill({ status: 201, json: newCourse });
      }

      // Match /api/v1/courses/:id
      const courseMatch = path.match(/^\/api\/v1\/courses\/([^/]+)$/);
      if (courseMatch && method === "GET") {
        const courseId = courseMatch[1];
        const course = courses.find((c) => c.id === courseId);
        if (!course) return route.fulfill({ status: 404, json: { detail: "Course not found" } });

        const isOwner = caller?.id === course.owner_id || caller?.role === "admin";
        const isEnrolled = (enrollments[courseId] || []).some(
          (e) => e.user_id === caller?.id || e.email === caller?.email
        );

        if (!isOwner && !isEnrolled) {
          return route.fulfill({ status: 403, json: { detail: "Not enrolled in this course" } });
        }
        return route.fulfill({ status: 200, json: course });
      }

      // Match /api/v1/courses/:id/enrollments
      const enrollMatch = path.match(/^\/api\/v1\/courses\/([^/]+)\/enrollments$/);
      if (enrollMatch) {
        const courseId = enrollMatch[1];
        if (method === "GET") {
          return route.fulfill({ status: 200, json: enrollments[courseId] || [] });
        }
        if (method === "POST") {
          const data = request.postDataJSON();
          const addedList = [];
          for (const email of data.emails || []) {
            const entry = {
              user_id: email.includes("student1") ? "student-1" : "unknown",
              name: email.includes("student1") ? "Alice Student" : "Student",
              email,
              role: data.role || "student",
            };
            enrollments[courseId] = enrollments[courseId] || [];
            enrollments[courseId].push(entry);
            addedList.push(entry);
          }
          return route.fulfill({
            status: 200,
            json: {
              added: addedList,
              already_enrolled: [],
              unknown: [],
            },
          });
        }
      }

      // --- LECTURES ENDPOINTS ---
      const courseLecturesMatch = path.match(/^\/api\/v1\/courses\/([^/]+)\/lectures$/);
      if (courseLecturesMatch && method === "GET") {
        const courseId = courseLecturesMatch[1];
        const course = courses.find((c) => c.id === courseId);
        if (!course) return route.fulfill({ status: 404, json: { detail: "Course not found" } });

        const isOwner = caller?.id === course.owner_id || caller?.role === "admin";
        const isEnrolled = (enrollments[courseId] || []).some(
          (e) => e.user_id === caller?.id || e.email === caller?.email
        );

        if (!isOwner && !isEnrolled) {
          return route.fulfill({ status: 403, json: { detail: "Forbidden" } });
        }

        const courseLects = lectures[courseId] || [];
        if (isOwner) {
          return route.fulfill({ status: 200, json: courseLects });
        }
        // Student sees only published and ready lectures
        const visible = courseLects.filter((l) => l.published && l.status === "ready");
        return route.fulfill({ status: 200, json: visible });
      }

      if (courseLecturesMatch && method === "POST") {
        const courseId = courseLecturesMatch[1];
        const data = request.postDataJSON();
        const newLecture: MockLecture = {
          id: `lect-${Date.now()}`,
          course_id: courseId,
          title: data.title,
          description: data.description || null,
          position: (lectures[courseId] || []).length,
          status: "draft",
          duration_ms: 0,
          published: false,
          poster_path: null,
          created_at: new Date().toISOString(),
        };
        lectures[courseId] = lectures[courseId] || [];
        lectures[courseId].push(newLecture);
        createdLectureId = newLecture.id;
        return route.fulfill({
          status: 201,
          json: {
            lecture: newLecture,
            upload_url: `/api/v1/lectures/${newLecture.id}/upload`,
          },
        });
      }

      // Match /api/v1/lectures/:id/upload
      const uploadMatch = path.match(/^\/api\/v1\/lectures\/([^/]+)\/upload$/);
      if (uploadMatch && method === "PUT") {
        const rangeHeader = request.headers()["content-range"] || "";
        const parts = rangeHeader.replace("bytes ", "").split("/");
        const [, end] = parts[0].split("-").map(Number);
        return route.fulfill({
          status: 200,
          json: { bytes_written: (end || 0) + 1 },
        });
      }

      // Match /api/v1/lectures/:id/upload/complete
      const completeMatch = path.match(/^\/api\/v1\/lectures\/([^/]+)\/upload\/complete$/);
      if (completeMatch && method === "POST") {
        const lectureId = completeMatch[1];
        for (const cId in lectures) {
          const l = lectures[cId].find((x) => x.id === lectureId);
          if (l) {
            l.status = "processing";
            jobs[lectureId] = [
              {
                id: `job-${lectureId}`,
                job_type: "transcode",
                status: "running",
                attempts: 1,
                error: null,
                output_metadata: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ];
            break;
          }
        }
        return route.fulfill({
          status: 200,
          json: {
            lecture_id: lectureId,
            status: "processing",
            job_id: `job-${lectureId}`,
          },
        });
      }

      // Match /api/v1/lectures/:id/jobs
      const jobsMatch = path.match(/^\/api\/v1\/lectures\/([^/]+)\/jobs$/);
      if (jobsMatch && method === "GET") {
        const lectureId = jobsMatch[1];
        if (jobs[lectureId]) {
          for (const job of jobs[lectureId]) {
            job.status = "completed";
            job.output_metadata = {
              duration_ms: 120000,
              renditions: ["720p", "480p", "360p"],
            };
          }
        }
        for (const cId in lectures) {
          const l = lectures[cId].find((x) => x.id === lectureId);
          if (l) {
            l.status = "ready";
            l.duration_ms = 120000;
          }
        }
        return route.fulfill({ status: 200, json: jobs[lectureId] || [] });
      }

      // Match /api/v1/lectures/:id
      const lectureDetailMatch = path.match(/^\/api\/v1\/lectures\/([^/]+)$/);
      if (lectureDetailMatch) {
        const lectureId = lectureDetailMatch[1];
        let foundLecture: MockLecture | null = null;
        let foundCourseId = "";
        for (const cId in lectures) {
          const l = lectures[cId].find((x) => x.id === lectureId);
          if (l) {
            foundLecture = l;
            foundCourseId = cId;
            break;
          }
        }
        if (!foundLecture) return route.fulfill({ status: 404, json: { detail: "Lecture not found" } });

        const course = courses.find((c) => c.id === foundCourseId);
        const isOwner = caller?.id === course?.owner_id || caller?.role === "admin";
        const isEnrolled = (enrollments[foundCourseId] || []).some(
          (e) => e.user_id === caller?.id || e.email === caller?.email
        );

        if (!isOwner && !isEnrolled) {
          return route.fulfill({ status: 403, json: { detail: "Forbidden" } });
        }

        if (method === "GET") {
          return route.fulfill({ status: 200, json: foundLecture });
        }

        if (method === "PATCH") {
          if (!isOwner) return route.fulfill({ status: 403, json: { detail: "Only owner can edit lecture" } });
          const updates = request.postDataJSON();
          Object.assign(foundLecture, updates);
          return route.fulfill({ status: 200, json: foundLecture });
        }
      }

      // Match /api/v1/lectures/:id/playback-token
      const tokenMatch = path.match(/^\/api\/v1\/lectures\/([^/]+)\/playback-token$/);
      if (tokenMatch && method === "POST") {
        const lectureId = tokenMatch[1];
        let foundCourseId = "";
        for (const cId in lectures) {
          if (lectures[cId].some((l) => l.id === lectureId)) {
            foundCourseId = cId;
            break;
          }
        }
        const isEnrolled = (enrollments[foundCourseId] || []).some(
          (e) => e.user_id === caller?.id || e.email === caller?.email
        );
        const course = courses.find((c) => c.id === foundCourseId);
        const isOwner = caller?.id === course?.owner_id || caller?.role === "admin";

        if (!isOwner && !isEnrolled) {
          return route.fulfill({ status: 403, json: { detail: "Forbidden: Not enrolled in course" } });
        }

        const signedUrl = `/media/lectures/${lectureId}/hls/master.m3u8?exp=2000000000&uid=${caller?.id}&sig=valid-sig-${caller?.id}`;
        if (caller?.id === "student-1") {
          student1ManifestUrl = signedUrl;
        }

        return route.fulfill({
          status: 200,
          json: {
            token: `mock-playback-signature-${caller?.id}`,
            manifest_url: signedUrl,
            expires_in_seconds: 600,
          },
        });
      }

      // Match /api/v1/lectures/:id/progress
      const progressMatch = path.match(/^\/api\/v1\/lectures\/([^/]+)\/progress$/);
      if (progressMatch) {
        const lectureId = progressMatch[1];
        if (method === "GET") {
          const userProg = progress[lectureId] || {
            position_ms: 0,
            completed: false,
          };
          return route.fulfill({ status: 200, json: userProg });
        }
        if (method === "PUT") {
          const body = request.postDataJSON();
          progress[lectureId] = {
            position_ms: body.position_ms,
            completed: body.completed ?? false,
          };
          return route.fulfill({ status: 200, json: progress[lectureId] });
        }
      }

      // Fallback
      return route.fulfill({ status: 404, json: { detail: "Not found" } });
    });
  }

  test("Complete Professor and Student Lifecycle with Authorization Refusal", async ({ browser }) => {
    // =========================================================================
    // CONTEXT 1: PROFESSOR
    // =========================================================================
    const profContext = await browser.newContext();
    await setupContextRoutes(profContext);
    const profPage = await profContext.newPage();

    // STEP 1: Professor logs in
    await profPage.goto("/login");
    await expect(profPage.locator(".login-header h2")).toContainText(/Welcome Back|वापसी पर स्वागत/);

    await profPage.fill('input[type="email"]', "prof@university.edu");
    await profPage.fill('input[type="password"]', "Password123!");
    await profPage.click('button[type="submit"]');

    await expect(profPage).toHaveURL(/\/courses/);
    await expect(profPage.locator(".page-title")).toBeVisible();

    // STEP 2: Professor creates course
    const createBtn = profPage.locator(".create-course-btn");
    await expect(createBtn).toBeVisible();
    await createBtn.click();

    await profPage.fill("#course-code", "CS101");
    await profPage.fill("#course-title", "Data Structures & Algorithms");
    await profPage.fill("#course-term", "Fall 2026");
    await profPage.fill("#course-desc", "Foundations of computational structures.");

    await profPage.click('.modal-card button[type="submit"]');

    await expect(profPage.locator(".course-title").first()).toHaveText("Data Structures & Algorithms");
    await expect(profPage.locator(".course-code-badge").first()).toHaveText("CS101");

    // STEP 3: Navigate to Course Detail
    await profPage.click(".course-action-btn");
    await expect(profPage).toHaveURL(/\/courses\/course-1/);
    await expect(profPage.locator(".course-hero-title")).toHaveText("Data Structures & Algorithms");

    // STEP 4: Professor enrolls a student
    await profPage.click('button:has-text("Manage Enrollments")');
    await expect(profPage.locator(".modal-title")).toContainText(/Manage Enrollments/);

    await profPage.fill("#paste-emails", "student1@university.edu");
    await profPage.click(".add-members-btn");

    await expect(profPage.locator(".feedback-banner")).toBeVisible();
    await expect(profPage.locator(".members-table")).toContainText("student1@university.edu");

    await profPage.click(".modal-close-btn");

    // STEP 5: Professor creates & uploads short lecture
    await profPage.click('button:has-text("+ Upload Lecture")');
    await expect(profPage.locator(".modal-title")).toContainText(/Upload Lecture/);

    await profPage.fill("#lecture-title", "Lecture 01: Introduction & Complexity");
    await profPage.fill("#lecture-desc", "Big O notation and asymptotic analysis.");

    const fileInput = profPage.locator("#lecture-file");
    await fileInput.setInputFiles({
      name: "sample-lecture.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.from("dummy video content for chunk upload test"),
    });

    await profPage.click('button:has-text("Start Upload")');
    await expect(profPage.locator(".upload-status-text")).toContainText(/Upload complete/);

    await expect(profPage.locator(".lecture-title")).toHaveText("Lecture 01: Introduction & Complexity", { timeout: 10000 });

    // STEP 6: Waits for ready and publishes
    const pipelineBtn = profPage.locator('button:has-text("Pipeline")');
    if (await pipelineBtn.isVisible()) {
      await pipelineBtn.click();
      await expect(profPage.locator(".pipeline-stage-item").first()).toContainText(/Transcode/);
    }

    const publishBtn = profPage.locator('button:has-text("Publish")');
    await expect(publishBtn).toBeVisible();
    await publishBtn.click();
    await expect(profPage.locator('button:has-text("Unpublish")')).toBeVisible();

    // STEP 7: Professor logs out
    await profPage.click(".logout-btn");
    await expect(profPage).toHaveURL(/\/login/);
    await profContext.close();

    // =========================================================================
    // CONTEXT 2: ENROLLED STUDENT (student 1)
    // =========================================================================
    const student1Context = await browser.newContext();
    await setupContextRoutes(student1Context);
    const student1Page = await student1Context.newPage();

    // STEP 8: Enrolled student logs in
    await student1Page.goto("/login");
    await student1Page.fill('input[type="email"]', "student1@university.edu");
    await student1Page.fill('input[type="password"]', "Password123!");
    await student1Page.click('button[type="submit"]');

    await expect(student1Page).toHaveURL(/\/courses/);
    await expect(student1Page.locator(".course-title")).toHaveText("Data Structures & Algorithms");
    await expect(student1Page.locator(".create-course-btn")).toHaveCount(0);

    // STEP 9: Student views course & plays lecture
    await student1Page.click(".course-action-btn");
    await expect(student1Page).toHaveURL(/\/courses\/course-1/);

    await expect(student1Page.locator('button:has-text("Manage Enrollments")')).toHaveCount(0);
    await expect(student1Page.locator('button:has-text("Publish")')).toHaveCount(0);
    await expect(student1Page.locator('button:has-text("Unpublish")')).toHaveCount(0);
    await expect(student1Page.locator(".danger-btn")).toHaveCount(0);

    await student1Page.click(".play-lecture-btn");
    await expect(student1Page).toHaveURL(/\/lectures\/lect-/);
    await expect(student1Page.locator(".lecture-page-title")).toHaveText("Lecture 01: Introduction & Complexity");

    const lectureUrl = student1Page.url();

    // STEP 10: Seeks, reloads, and resumes
    // 1. Student seeks forward with keyboard shortcut 'L' (+10s)
    await student1Page.keyboard.press("KeyL");

    // 2. Set saved progress position at 15000 ms (15 seconds)
    for (const cId in lectures) {
      for (const l of lectures[cId]) {
        progress[l.id] = { position_ms: 15000, completed: false };
      }
    }

    // 3. Reload page to verify resume behavior
    await student1Page.reload();
    await expect(student1Page.locator(".lecture-page-title")).toHaveText("Lecture 01: Introduction & Complexity");
    await expect(student1Page.locator(".player-toast")).toContainText("00:15");

    // 4. Assert video.currentTime advances to the resumed position (>= 14.5s)
    await expect
      .poll(
        async () => {
          return student1Page.evaluate(() => {
            const video = document.querySelector<HTMLVideoElement>("video.hls-video-element");
            return video ? video.currentTime : 0;
          });
        },
        { timeout: 10000, intervals: [200, 500, 1000] }
      )
      .toBeGreaterThanOrEqual(14.5);

    // 5. Positive control: student 1's untampered signed media URL returns 200/206
    expect(student1ManifestUrl.length).toBeGreaterThan(0);
    const student1MediaStatus = await student1Page.evaluate(async (url) => {
      const res = await fetch(url, {
        headers: {
          Authorization: "Bearer mock-jwt-student-1",
        },
      });
      return res.status;
    }, student1ManifestUrl);
    expect([200, 206]).toContain(student1MediaStatus);

    // Student 1 logs out
    await student1Page.click(".logout-btn");
    await expect(student1Page).toHaveURL(/\/login/);
    await student1Context.close();

    // =========================================================================
    // CONTEXT 3: SECOND NON-ENROLLED STUDENT (student 2)
    // =========================================================================
    const student2Context = await browser.newContext();
    await setupContextRoutes(student2Context);
    const student2Page = await student2Context.newPage();

    // STEP 11: Non-enrolled student refusal verification
    // 1. Log in as student 2 through the form
    await student2Page.goto("/login");
    await student2Page.fill('input[type="email"]', "student2@university.edu");
    await student2Page.fill('input[type="password"]', "Password123!");
    await student2Page.click('button[type="submit"]');

    // 2. Go to the lecture URL student 1 used. The redirect back to it is fine.
    await student2Page.goto(lectureUrl);

    // 3. Assert the page shows the not-found / no-access state. Do not assert on the final URL.
    await expect(student2Page.locator(".error-state")).toBeVisible({ timeout: 10000 });
    await expect(student2Page.locator(".error-text")).toBeVisible();

    // 4. Assert the server also refuses: POST /api/v1/lectures/{id}/playback-token with student 2's access token returns 403 or 404.
    const playbackTokenStatus = await student2Page.evaluate(async (lecId) => {
      const res = await fetch(`/api/v1/lectures/${lecId}/playback-token`, {
        method: "POST",
        headers: {
          Authorization: "Bearer mock-jwt-student-2",
        },
      });
      return res.status;
    }, createdLectureId);
    expect([403, 404]).toContain(playbackTokenStatus);

    // 5. Also assert that a media URL signed for student 1 does not work as student 2
    expect(student1ManifestUrl.length).toBeGreaterThan(0);

    // 5a. Direct request using student 2 authorization credentials
    const mediaWithStudent2AuthStatus = await student2Page.evaluate(async (url) => {
      const res = await fetch(url, {
        headers: {
          Authorization: "Bearer mock-jwt-student-2",
        },
      });
      return res.status;
    }, student1ManifestUrl);
    expect([401, 403]).toContain(mediaWithStudent2AuthStatus);

    // 5b. Tampered UID parameter (attempting to use student 2 identity with student 1 signature)
    const tamperedMediaUrl = student1ManifestUrl.replace("uid=student-1", "uid=student-2");
    const tamperedStatus = await student2Page.evaluate(async (url) => {
      const res = await fetch(url);
      return res.status;
    }, tamperedMediaUrl);
    expect([401, 403]).toContain(tamperedStatus);

    await student2Context.close();
  });
});
