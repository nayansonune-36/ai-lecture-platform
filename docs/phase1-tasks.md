# Phase 1 Tasks

Goal: a professor can create a course and upload a lecture; it becomes adaptive HLS; an enrolled student can sign in and watch it with resume and captions. No AI yet (that is Phase 2).

How to use: paste one task block into the coding CLI at a time. Each task starts from a working repo and ends with something you can run and check. Do not start the next task until the acceptance checks pass.

Before task 1, put `AGENTS.md` at the repo root and the files in `docs/`.

---

## Task 1: Scaffold the monorepo and local infrastructure

**Paste to CLI**
```
Read AGENTS.md and docs/ARCHITECTURE.md. Create the monorepo layout from AGENTS.md:
apps/web (Vite + React + TypeScript), services/api (FastAPI, uv), services/worker (ARQ, uv),
packages/shared, infra, storage/ (gitignored). Use pnpm workspaces for the JS side.
Add infra/docker-compose.yml with postgres (pgvector image), redis, and caddy.
Postgres and redis must NOT publish ports to the host; only caddy publishes 80/443 (use 8080/8443 in dev).
Add .env.example, .gitignore, and a README with the run commands. Do not write feature code yet.
```
**Done when**
- `docker compose up -d` starts postgres, redis, caddy.
- `psql` inside the postgres container shows the `vector` extension available.
- `pnpm --filter web dev` and the API skeleton both start.

---

## Task 2: API skeleton, settings, health

**Paste to CLI**
```
In services/api create the FastAPI app: app/main.py, app/settings.py (pydantic-settings from env),
app/db.py (SQLAlchemy 2 async), routers/health.py with GET /api/v1/healthz and /api/v1/readyz
(readyz checks postgres, redis, and that STORAGE_ROOT exists and is writable).
Add ruff and mypy config and one pytest that hits /healthz. Route /api/* through Caddy to the API.
```
**Done when**
- `curl http://localhost:8080/api/v1/healthz` returns `{"status":"ok"}` through Caddy.
- `uv run pytest` passes.

---

## Task 3: Database migrations from schema.sql

**Paste to CLI**
```
Set up Alembic in services/api. Translate docs/schema.sql into the first migration and SQLAlchemy models
for: users, courses, enrollments, lectures, lecture_renditions, playback_progress, jobs.
Create the vector, pg_trgm, pgcrypto extensions in the migration. Include the transcript, chunk, chapter,
chat, device and license tables in the migration too, but models for them can wait.
Include the can_view_lecture SQL function. Add a seed script that creates one admin, one professor and
two students. Keep docs/schema.sql in sync if you change anything.
```
**Done when**
- `alembic upgrade head` works on an empty database and `alembic downgrade base` works too.
- Seed script is repeatable (running twice does not duplicate users).

---

## Task 4: Authentication

**Paste to CLI**
```
Implement auth per docs/api.md: POST /auth/login, /auth/refresh, /auth/logout, GET /me.
Argon2 password hashing, 15 min access JWT, 14 day rotating refresh tokens stored hashed in the database
(add a refresh_tokens table via migration). Add a get_current_user dependency and a require_role dependency.
Rate-limit failed logins (5 per 15 minutes per account and IP). Leave SSO as a stub endpoint returning 501.
Write tests: wrong password, expired token, refresh rotation, inactive user.
```
**Done when**
- Seed users can log in and `/me` returns their role.
- Reusing an old refresh token fails.

---

## Task 5: Courses and enrollment

**Paste to CLI**
```
Implement the courses and enrollments endpoints from docs/api.md. Professors create courses; only the owner
can edit or manage enrollments. Students see only courses they are enrolled in. Support adding enrollments
by email list and by CSV upload (create nothing for unknown emails; return them in an "unknown" list).
Write authorization tests proving a student cannot see or edit another course.
```
**Done when**
- Student A cannot read or list Student B's courses.
- CSV import reports unknown emails without failing.

---

## Task 6: Lecture records and resumable upload

**Paste to CLI**
```
Implement lecture endpoints from docs/api.md: create lecture, resumable chunked upload
(PUT /lectures/{id}/upload with Content-Range), upload/complete, get, patch, delete.
Store originals at STORAGE_ROOT/lectures/<lecture_id>/original.<ext>. Validate type (mp4, mov, mkv, webm)
and a configurable max size (default 8 GB). On upload/complete, set status=processing and enqueue a
'transcode' job (create the jobs row and push to the Redis queue). Students must never see
unpublished or non-ready lectures. Add tests including an interrupted-then-resumed upload.
```
**Done when**
- A 500 MB file uploaded in chunks, interrupted, and resumed ends up byte-identical (check the hash).
- A student gets 404 for a lecture that is not published.

---

## Task 7: Transcode worker (FFmpeg to HLS)

**Paste to CLI**
```
In services/worker implement the 'transcode' job. Use ffprobe to read duration and streams. Use FFmpeg to
produce HLS fMP4 renditions at 720p, 480p and 360p (skip renditions larger than the source), 6 second
segments, a master.m3u8, a poster image at 10% of the duration, and 5 second-interval thumbnails (optional sprite).
Output under STORAGE_ROOT/lectures/<id>/hls/. Update lectures (duration_ms, hls_master_path, poster_path,
status=ready), insert lecture_renditions rows, and update the jobs row (status, attempts, error).
The job must be idempotent and retry up to 3 times. Provide a small CLI to run a transcode on a local file for testing.
```
**Done when**
- A sample lecture produces a playable `master.m3u8` (verify with `ffprobe` and by opening in VLC).
- Re-running the job does not duplicate renditions.

---

## Task 8: Signed media URLs and Caddy forward_auth

**Paste to CLI**
```
Implement protected media delivery. POST /lectures/{id}/playback-token returns a signed manifest URL
(HMAC-SHA256 over path|exp|uid using MEDIA_SIGNING_KEY, 15 minute lifetime). Add GET /internal/auth/video
that Caddy calls via forward_auth to validate signature, expiry and can_view_lecture. Configure Caddy to serve
STORAGE_ROOT/lectures under /media/* only after that check passes, with Range request support and correct
HLS content types. The /internal/* path must not be reachable from outside Caddy.
Write tests: valid token plays, expired token fails, tampered signature fails, a non-enrolled user fails.
```
**Done when**
- Direct requests to `/media/...` without a valid signature return 401/403.
- A non-enrolled student's valid-looking token for another course fails.
- `curl` against ports 5432, 6379 and the storage path from another machine on the LAN is refused.

---

## Task 9: Web app shell, login and course pages

**Paste to CLI**
```
In apps/web build the shell: routing, login page, an auth store (access token in memory, refresh via
httpOnly cookie or secure refresh flow), TanStack Query, and an API client generated from the FastAPI
OpenAPI schema into packages/shared. Pages: course list, course detail with the lecture list (poster, title,
duration, resume progress bar). Set up i18n with English and Hindi strings for the shell. Make it a PWA
(manifest + service worker that does not cache media). Keep the design clean and responsive.
```
**Done when**
- A seeded student logs in and sees only their courses.
- The UI language switches between English and Hindi and renders Devanagari correctly.

---

## Task 10: Player with resume, quality and captions

**Paste to CLI**
```
Build the lecture page with an hls.js player. Fetch the signed manifest URL from the playback-token endpoint
and refresh it before expiry. Features: adaptive quality plus manual quality menu, playback speed, keyboard
shortcuts, resume from saved position (PUT /lectures/{id}/progress every 10 seconds and on pause/leave),
captions via a <track> loaded from /lectures/{id}/captions.vtt (use a sample VTT until Phase 2 produces real
ones), and a chapter list that seeks the player (use sample chapters until Phase 2). Handle errors: expired
token, network drop, and a lecture that is still processing.
```
**Done when**
- Quality switches without restarting playback.
- Closing and reopening the lecture resumes within 10 seconds of where you left.
- Captions toggle on and off.

---

## Task 11: Professor upload and management UI

**Paste to CLI**
```
Add the professor views: create course, manage enrollments (paste emails or upload CSV), create a lecture,
upload with a progress bar and resume after a dropped connection, and a pipeline status panel showing job
stages (transcode now; transcribe/index/chapters shown as "coming soon"). Add publish/unpublish and delete.
Hide these views from students and enforce it on the server as well.
```
**Done when**
- A professor uploads a lecture end to end from the browser, watches status move to ready, publishes, and a student sees it.

---

## Task 12: End-to-end check and hardening

**Paste to CLI**
```
Add a Playwright test covering: professor logs in, creates course, enrolls a student, uploads a short sample
video, waits for ready, publishes; the student logs in, plays the lecture, seeks, reloads and resumes;
a second non-enrolled student gets refused. Add a docs/runbook.md with how to start everything, where files
live, how to retry a failed job, and a backup note for Postgres and STORAGE_ROOT.
Review AGENTS.md "NEVER do these" and confirm each rule with a test or a documented check.
```
**Done when**
- The Playwright test passes from a clean database.
- You can follow the runbook from scratch on a second machine.

---

## Phase 1 exit checklist

- [ ] Professor uploads, processing completes, lecture plays at 3 qualities.
- [ ] Enrolled student can watch; non-enrolled student cannot, including by guessing media URLs.
- [ ] Resume works across devices (same account, different browser).
- [ ] Smartboard on the LAN plays a lecture through the hostname with HTTPS.
- [ ] Nothing but Caddy is reachable from another machine on the network.

## Next: Phase 2 (preview)

Whisper transcription with per-segment language detection, chunking, `bge-m3` embeddings, hybrid search, tutor chat with `[MM:SS]` citations and click-to-seek, transcript editor. Before starting, run 3 to 5 real Hindi/English lectures through faster-whisper `large-v3` and review the output with a professor.
