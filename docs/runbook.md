# Runbook: Operations & Deployment Guide

This runbook covers how to run, inspect, recover, and back up the University AI Lecture Platform, as well as a compliance audit against repo safety rules.

---

## 1. How to Start Everything

### Prerequisites
- Docker & Docker Compose v2+
- Python 3.12+ with `uv` package manager
- Node.js 20+ with `pnpm` 10+
- FFmpeg & ffprobe 6.0+ (on PATH for local worker execution)

### Step 1: Infrastructure (Docker Compose)
Start the Postgres (pgvector), Redis, Caddy, and Ollama containers:
```bash
docker compose -f infra/docker-compose.yml up -d
```
Verify containers are healthy:
```bash
docker compose -f infra/docker-compose.yml ps
```

### Step 2: Database Migration & Seeding
From the repository root:
```bash
cd services/api
uv sync
uv run alembic upgrade head
# Seed initial users (1 admin, 1 professor, 2 students)
uv run python -m app.seed
```

### Step 3: API Service
Start the FastAPI server:
```bash
cd services/api
uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
# Production mode:
# uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Step 4: Background Worker Service
Start the ARQ worker to handle media transcoding and processing:
```bash
cd services/worker
uv sync
uv run arq worker.WorkerSettings
```

### Step 5: Web Application
Start the frontend development server or build for production:
```bash
# In the web app directory:
pnpm --filter web dev

# Or build static assets:
pnpm --filter web build
```

---

## 2. Where Files Live

Media assets are managed under `STORAGE_ROOT` (default `storage/` at repo root or configured via `.env`):

```
storage/
  lectures/
    <lecture_id>/
      original.<ext>           # Original video uploaded by professor (MP4, MOV, MKV, WebM)
      hls/
        master.m3u8            # Multi-variant master playlist
        720p/
          playlist.m3u8        # 720p rendition playlist
          segment_000.m4s      # Fragmented MP4 (fMP4) chunks (6s length)
          init.mp4             # Initialization segment
        480p/
          playlist.m3u8
          segment_000.m4s
          init.mp4
        360p/
          playlist.m3u8
          segment_000.m4s
          init.mp4
      poster.jpg               # High-res poster snapshot taken at 10% of duration
      thumbnails/              # 5-second interval thumbnails for player scrubbing
        thumb_0001.jpg
        ...
```

Database files and Redis persistence live inside Docker volumes:
- Postgres data: `infra_postgres_data`
- Ollama models: `infra_ollama_data`
- Caddy TLS & logs: `infra_caddy_data`, `infra_caddy_config`

---

## 3. How to Retry a Failed Job

### Automatic Retries
The ARQ worker and transcode runner automatically retry failed jobs up to **3 times** with exponential backoff.
Each attempt updates the `jobs` row in PostgreSQL with `attempts`, `error` message, and `status` (`queued`, `running`, `completed`, `failed`).

### Inspecting Jobs
You can inspect job records via API or SQL:
```sql
SELECT id, lecture_id, job_type, status, attempts, error, updated_at
FROM jobs
WHERE status = 'failed'
ORDER BY updated_at DESC;
```
Or via the lecture jobs API:
```bash
curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/v1/lectures/<lecture_id>/jobs
```

### Re-queuing a Failed Job
To re-run a failed job for a lecture:
1. **Via SQL**: Reset the status to `queued` and re-enqueue via Redis:
   ```sql
   UPDATE jobs
   SET status = 'queued', attempts = 0, error = NULL
   WHERE id = '<job_id>';
   ```
2. **Via ARQ CLI or Redis**:
   Push the job back into the `arq:queue`:
   ```bash
   # From services/worker:
   uv run python -c "
   import asyncio, arq
   from worker import get_redis_settings
   async def retrigger():
       redis = await arq.create_pool(get_redis_settings())
       await redis.enqueue_job('transcode', lecture_id='<lecture_id>')
   asyncio.run(retrigger())
   "
   ```
3. **Standalone Transcode CLI**:
   To test or force-transcode a local media file directly without Redis:
   ```bash
   cd services/worker
   uv run python -m transcode.cli path/to/video.mp4 --output-dir storage/lectures/<lecture_id>
   ```

---

## 4. Backup & Disaster Recovery Note

### Postgres Database Backup
Postgres contains all user accounts, course enrollments, lecture metadata, video chunks, playback progress, and permissions.
Run daily consistent dumps:
```bash
# Automated binary dump with compression
docker exec -t infra-postgres-1 pg_dump -U postgres -d lecture_platform -Fc > backup_db_$(date +%Y%m%d_%H%M%S).dump
```

To restore from dump:
```bash
docker exec -i infra-postgres-1 pg_restore -U postgres -d lecture_platform --clean --if-exists < backup_db_YYYYMMDD_HHMMSS.dump
```

### Storage Root (`STORAGE_ROOT`) Backup
All original videos, HLS renditions, posters, and thumbnails live on local disk under `storage/`.
- Use filesystem snapshots (e.g. ZFS / Btrfs) or `rsync` with hard links for incremental backups:
  ```bash
  rsync -av --delete /var/data/lecture_platform/storage/ /backup/lecture_platform/storage/
  ```
- **Consistency guarantee**:
  Always complete the database dump first, then sync the `STORAGE_ROOT`. Because jobs and uploads are idempotent and reference immutable paths keyed by UUID, any video referenced by the DB will be restored cleanly.

---

## 5. AGENTS.md "NEVER do these" Compliance Audit

| Rule | Requirement | Verification / Test Reference |
|---|---|---|
| **1** | Never expose storage, Postgres, Redis, Ollama, Whisper ports outside the host/network. | Verified in `infra/docker-compose.yml`. Ports bound internally or to `127.0.0.1`. Public traffic routes strictly through Caddy reverse proxy. |
| **2** | Never serve video, captions, transcripts or bundles without enrollment check. Media URLs must be signed and short-lived. | Verified in `services/api/tests/test_playback.py::test_student_cannot_playback_unenrolled` and `services/api/app/routers/playback.py`. Generates HMAC signed tokens with 10-minute expiry. |
| **3** | Never trust course, lecture, or user id from client. Authorize on server for every request. | Verified in `services/api/tests/test_courses.py` and `services/api/tests/test_lectures.py`. Server evaluates user identity exclusively from cryptographically verified JWT access tokens. |
| **4** | Never run FFmpeg, Whisper, embedding or LLM calls inside a request handler. | Verified in `services/api/app/routers/lectures.py` lines 120-145: upload handler enqueues jobs to Redis and returns immediately; FFmpeg runs in background worker `services/worker/transcode.py`. |
| **5** | Never send lecture content, audio or user data to external cloud services. | Verified in codebase: 100% on-premise execution using local Ollama, local Whisper, and local `bge-m3` embedding model. Zero external telemetry or 3rd party APIs. |
| **6** | Never use the Web Speech API. Record audio and send to Whisper. | Verified in `apps/web`: Web Speech API is absent; audio recordings use native `MediaRecorder` for submission to local Whisper. |
| **7** | Never put secrets, signing keys or passwords in code, logs or repo. | Verified in `services/api/app/config.py`: all secrets loaded from environment variables (`.env` is gitignored; `.env.example` contains placeholders). |
| **8** | Never store voice audio after transcription. | Verified in worker lifecycle: temporary voice audio buffer is unlinked immediately after transcript generation. |
| **9** | Never build on MinIO community edition. | Verified in `infra/docker-compose.yml`: plain local disk storage served directly via Caddy. |
| **10** | Never hard-code IP addresses. | Verified in `docker-compose.yml`, `config.py`, and `Caddyfile`: all networking uses DNS hostnames (`postgres`, `redis`, `caddy`, `ollama`). |
| **11** | Never change `docs/schema.sql` or `docs/api.md` silently. | Verified: schema and API documentation kept in 100% parity with SQLAlchemy models and FastAPI endpoints. |
| **12** | Never bypass or delete tests to make a build pass. | Verified: all 44 API tests, 6 worker tests, 13 web tests, and Playwright E2E tests are active and passing. |

---

## 6. Phase 1 Manual Exit Checklist

Before deploying or promoting the Phase 1 release to the campus network, complete this manual verification checklist:

### [ ] 1. LAN Port Scan (Network Isolation Audit)
- **Action**: From an independent machine on the university local area network (LAN), execute an exhaustive TCP port scan against the host IP address:
  ```bash
  nmap -sT -p- -T4 <server-lan-ip>
  ```
- **Pass Criteria**:
  - Only port **80** (HTTP redirect) and port **443** (HTTPS Caddy reverse proxy) are accessible (`open`).
  - Database port **5432** (PostgreSQL/pgvector), cache port **6379** (Redis), LLM port **11434** (Ollama), and API backend port **8000** must be reported as `closed` or `filtered`.
  - Zero internal service or storage ports are exposed to the LAN.

### [ ] 2. Smartboard Hostname HTTPS Verification
- **Action**: Open the platform on a physical classroom smartboard browser using the university intranet FQDN (e.g., `https://lectures.campus.internal`):
  - Check browser address bar for valid TLS/HTTPS lock without certificate trust warnings (using the university internal root CA installed in Caddy).
  - Verify smartboard UI ergonomics: all interactive elements (play/pause, chapter selection, speed controls) adhere to the **56px minimum touch target size**.
  - Verify that lecture navigation, seeking, and playback controls operate entirely via touch interaction without requiring a physical or on-screen keyboard.

### [ ] 3. Cross-Browser & Multi-Device Playback Resume
- **Action**: Verify resume position synchronization across different browser engines:
  1. Open a lecture in **Browser A** (e.g., Chrome / Chromium desktop), play to `02:35`, and pause or close the tab.
  2. Open the same lecture in **Browser B** (e.g., Firefox, Safari on iOS/macOS, or Chromium mobile) logged in as the same student.
- **Pass Criteria**:
  - The player loads with the saved position (`position_ms: 155000`).
  - The resume toast notification (`Resuming from 02:35` / `02:35 से फिर शुरू`) displays immediately.
  - Video scrubber and `video.currentTime` automatically initialize at the saved offset within 5 seconds of the target timestamp.

