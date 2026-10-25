# Offline Lecture Platform — Manual QA & Verification Checklist

This document details the manual testing procedure for validating the offline-first desktop student experience, cryptographic license lifecycle, on-the-fly chunked playback, clock rollback protection, and network synchronization in Task O4d.

---

## Prerequisites

1. **Host Environment**: Windows 10/11 x64.
2. **Server Services Running**:
   ```powershell
   docker compose -f infra/docker-compose.yml up -d
   cd services/api && uv run alembic upgrade head && uv run fastapi dev app/main.py
   cd services/worker && uv run arq worker.WorkerSettings
   ```
3. **Desktop App**:
   ```powershell
   cd apps/desktop && pnpm tauri dev
   ```
4. **Test Accounts**:
   - Professor: `prof@university.edu` / `AdminPass123!`
   - Student: `student@university.edu` / `StudentPass123!`
   - Course: e.g. "CS301 Distributed Systems" with published lectures.

---

## Test Steps

### Test 1: Lecture Download & Encryption at Rest
- [ ] Launch desktop application and configure server URL (`http://127.0.0.1:8000`).
- [ ] Log in as `student@university.edu`.
- [ ] Navigate to **Available Lectures**. Verify size estimate displays for selected rendition (e.g. 480p).
- [ ] Click **Download**. Observe progress bar, bytes downloaded, and speed indicators.
- [ ] Verify background completion:
  - SQLite database: check `downloads` row has status `completed` and `licenses` has token.
  - Disk storage: Navigate to `%LOCALAPPDATA%/desktop/bundles/<lecture_id>/`.
  - Confirm every file has `.enc` extension (`hls/media.m3u8.enc`, `init.mp4.enc`, `seg-00000.m4s.enc`, `captions.vtt.enc`, `chapters.json.enc`).
  - Confirm zero plaintext `.zip` or unencrypted `.mp4`/`.ts` files remain in `temp_downloads/` or `temp_extract/`.

---

### Test 2: Disconnect Network (Zero-Internet Mode)
- [ ] Disconnect physical network: unplug Ethernet cable or toggle Windows Wi-Fi / Airplane mode off (or shut down backend API: `Ctrl+C`).
- [ ] Observe Desktop UI top banner:
  - Top header turns to amber: **⚠️ Offline Mode: Server is unreachable. You can continue watching downloaded lectures.**
  - "Retry Connection" button appears.
  - "Available Lectures" tab reflects offline state.

---

### Test 3: Offline Playback & Local Stream Decryption
- [ ] While fully disconnected from internet/network, switch to **Downloaded** tab.
- [ ] Verify downloaded lecture displays **Encrypted** badge and **Active** / **X days left** badge.
- [ ] Click **Watch Offline**.
- [ ] Verify offline player view opens:
  - Video starts playing immediately from `http://127.0.0.1:<port>/<session_token>/lectures/<id>/hls/master.m3u8`.
  - Open DevTools Network tab: confirm all segment requests are sent to `127.0.0.1` and return `206 Partial Content`.
  - Confirm captions display from local `captions.vtt`.
  - Confirm chapter markers appear in the player timeline from local `chapters.json`.
  - Confirm poster displays from local bundle.

---

### Test 4: Offline Resume Position & Progress Queue
- [ ] While watching offline, seek to `02:45` (165,000 ms) and pause.
- [ ] Close the video player or quit the application entirely (`Alt+F4`).
- [ ] Check local SQLite database:
  ```powershell
  sqlite3 "$env:LOCALAPPDATA/desktop/offline.db" "SELECT * FROM progress_queue;"
  ```
  - Verify a progress update row exists with `lecture_id`, `position_ms = 165000`, and `attempts = 0`.
- [ ] Relaunch the application while still offline.
- [ ] Log in using **Continue Offline as Student** (no password prompt).
- [ ] Open the downloaded lecture: verify player resumes directly at `02:45`.

---

### Test 5: License Expiration & Playback Lock
- [ ] Close player and locate the lecture's license token in SQLite:
  ```powershell
  sqlite3 "$env:LOCALAPPDATA/desktop/offline.db" "UPDATE licenses SET expires_at = datetime('now', '-1 day');"
  ```
  *(Or issue a JWT with an `exp` claim set in the past).*
- [ ] Refresh the **Downloaded** tab in the desktop application.
- [ ] Verify UI status:
  - Badge switches from green/blue to red: **Expired — Connect to renew**.
  - "Watch Offline" button changes to **Connect to renew** and is disabled.
- [ ] Attempt direct HTTP request to local server stream via browser/curl:
  ```powershell
  curl -i "http://127.0.0.1:<port>/<session_token>/lectures/<id>/hls/media.m3u8"
  ```
  - Verify response status is **403 Forbidden** with `License validation failed (License token has expired)`.

---

### Test 6: Server-Side Revocation & Auto-Wipe on Sync
- [ ] Reconnect host network to the university server.
- [ ] On the server (as Professor or Admin):
  - Unpublish the lecture OR unenroll the student from the course:
    ```sql
    DELETE FROM enrollments WHERE user_id = '<student_uuid>';
    ```
- [ ] In the desktop application, click **Sync Licenses** (or let background connectivity check trigger).
- [ ] Verify sync outcome:
  - Application displays notification banner:
    **⚠️ License Revoked: The following lectures were revoked by the server and removed: [Lecture Title]**.
  - Disk storage: confirm directory `%LOCALAPPDATA%/desktop/bundles/<lecture_id>/` is completely deleted.
  - SQLite database: confirm rows in `downloads`, `licenses`, and `progress_queue` for this lecture are deleted.

---

### Test 7: Clock Rollback Tamper Protection
- [ ] Download a valid lecture and confirm it plays offline.
- [ ] Note current system time `T0`. Local database records `max_seen_timestamp = T0`.
- [ ] Disconnect network.
- [ ] Change the Windows system clock backwards by 30 days:
  - Windows Settings > Time & Language > Date & Time > Set date 1 month in the past.
- [ ] Return to the desktop app and attempt to play the lecture:
  - App detects `current_clock < max_seen_timestamp`.
  - Red security banner appears: **⛔ Clock Rollback Detected: System clock is earlier than latest verified server time.**
  - All licenses are treated as expired.
  - Video player returns 403 Forbidden.
- [ ] Reconnect network and sync with server (or correct Windows clock to current time and sync):
  - Authoritative server timestamp is received via HTTP headers.
  - `max_seen_timestamp` is updated to real server time.
  - Clock rollback lock is cleared; legitimate offline playback resumes.

---

### Test 8: Logout (Keep Downloads vs Wipe All)
- [ ] Click **Sign Out** in the top navigation bar.
- [ ] Observe confirmation dialog offering two choices:
  1. **Keep Downloads & Sign Out**:
     - Retains all encrypted bundles on disk and SQLite license rows.
     - User can later log in offline using "Continue Offline" without server access.
  2. **Wipe All Downloads & Sign Out**:
     - Deletes all encrypted bundles in `%LOCALAPPDATA%/desktop/bundles/`.
     - Clears `downloads`, `licenses`, and `progress_queue` SQLite tables.
     - Leaves zero residual media on the machine.
