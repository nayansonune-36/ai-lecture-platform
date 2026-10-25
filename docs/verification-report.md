# Verification Pass Report: Tasks O4a – O4d

**Date**: 2026-10-25  
**Scope**: Full stack verification of offline student desktop application, download manager, encrypted local playback server, and license lifecycle synchronization.

---

## 1. Git Status & Commit History

### `git status`
```text
On branch master
nothing to commit, working tree clean
```

### `git log --oneline -15`
```text
5adae1e docs: add verification pass report for Tasks O4a-O4d
ef4f601 chore(desktop): resolve clippy warnings and add uninstall/reinstall test checklist
8068c0c fix(desktop): derive public key from existing keyring secret if present
56ab45c feat(offline): add LICENSE_TTL_SECONDS dev setting and clean clippy warnings
028b9ad chore(desktop): add target and src-tauri target to root .gitignore
a78668e feat(desktop): Task O4d license lifecycle, clock rollback protection, and progress sync
5dbfc9d feat(desktop): Task O4c local playback server and offline player
271e3bf feat(desktop): Task O4b download manager with resumable Range streaming and AES-256-GCM chunked encryption at rest
a4cb841 feat(desktop): Task O4a Tauri v2 student desktop app with Windows native keystore and offline shell
4876b31 feat(offline): Task O3 devices and Ed25519 offline license management
e48a0ce feat(offline): Task O2 offline bundle builder with Range resume and authorization
10099cb fix(e2e): zero-internet non-throwing route guard, pinned image tags, and manual air-gap checklist
c7c153d feat(offline): Task O1 zero-internet audit, local bundled fonts, SW isolation, and air-gapped runbook
8bb5abd feat(phase-1): private offline-capable AI lecture platform core implementation
```

---

## 2. Test Suite Execution Results

All test suites and linters pass cleanly with zero failures and zero linter warnings.

| Target / Suite | Command | Final Result Line |
| :--- | :--- | :--- |
| **Backend API** | `cd services/api && uv run pytest` | `54 passed, 2 warnings in 34.78s` |
| **Worker Queue** | `cd services/worker && uv run pytest` | `10 passed in 11.81s` |
| **Web Vitest** | `pnpm --filter web test` | `Tests  14 passed (14) (1.59s)` |
| **Web TypeScript** | `pnpm --filter web typecheck` | `$ tsc --noEmit` (exit code `0`) |
| **Web ESLint** | `pnpm --filter web lint` | `$ eslint .` (exit code `0`) |
| **Playwright E2E** | `pnpm --filter web test:e2e` | `4 passed (15.0s)` |
| **Desktop Rust Unit Tests** | `cd apps/desktop/src-tauri && cargo test` | `test result: ok. 22 passed; 0 failed; finished in 0.45s` |
| **Desktop Rust Clippy** | `cd apps/desktop/src-tauri && cargo clippy --all-targets --all-features` | `Finished 'dev' profile in 2.76s` (0 warnings, 0 errors) |

---

## 3. Requirements Traceability Matrix (O4a – O4d)

The following table reviews every requirement from tasks **O4a**, **O4b**, **O4c**, and **O4d**, noting whether it is implemented and citing the exact test or implementation file proving it, or explicitly acknowledging where no automated test exists.

### Task O4a: Tauri v2 Student Desktop App (Windows First)

| Requirement | Status | Verification Evidence / File | Test Coverage |
| :--- | :--- | :--- | :--- |
| Put all desktop-only UI in `apps/web/src/desktop/` using plain, minimal components. | **Implemented** | [apps/web/src/desktop/](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/) (`DesktopApp.tsx`, `ServerSetup.tsx`, `LoginScreen.tsx`, `LibraryView.tsx`, `OfflinePlayer.tsx`) | Tested in E2E (`desktop-offline-player.spec.ts`) |
| Put ALL logic in Rust commands and a thin TypeScript service layer (`apps/web/src/desktop/services/`), with React hooks on top. Screens must contain no business logic. | **Implemented** | [desktopService.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/services/desktopService.ts), [useLibrary.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/hooks/useLibrary.ts), [useDownloads.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/hooks/useDownloads.ts), [useConnectivity.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/hooks/useConnectivity.ts) | E2E mock tests |
| Tauri v2 project wrapping `apps/web`. Detect desktop mode (`window.__TAURI_INTERNALS__`) and show desktop routes only there. | **Implemented** | [tauri.conf.json](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/tauri.conf.json), [App.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/App.tsx#L40) (`isDesktop()`) | Tested in Vitest (`App.test.tsx`) & E2E |
| Keep Tauri's `useHttpsScheme` at default (`false`). | **Implemented** | [tauri.conf.json](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/tauri.conf.json) (omitted / default false) | Code inspection |
| Minimal capabilities and strict CSP: `connect-src` only to server & `127.0.0.1`; `media-src 127.0.0.1`. | **Implemented** | [tauri.conf.json](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/tauri.conf.json#L24) (`security.csp`) | Code inspection & E2E zero-internet audit |
| First-run "Server address" screen. Validate by calling `/api/v1/healthz` from Rust. Persist URL. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L34) (`validate_and_save_server_url`), [ServerSetup.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/ServerSetup.tsx) | *No Rust unit test* (requires live HTTP server); verified in manual test checklist |
| Rust: SQLite (`rusqlite`) in app data dir, migrations, tables: `settings`, `downloads`, `licenses`, `progress_queue`. | **Implemented** | [db.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/db.rs) | Rust test: `db::tests::test_database_migrations` |
| Device identity: generate Ed25519 keypair, store secret in Windows Credential Manager (`keyring` crate with `windows-native`), register via `POST /devices`, store `device_id`. | **Implemented** | [device.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/device.rs), [keyring_store.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/keyring_store.rs) | Rust tests: `keyring_store::tests::test_secret_store_and_read_back_with_new_entry`, `device::tests::test_device_identity_persistence_across_fresh_entry` |
| Remove silent in-memory fallback from `keyring_store.rs`. Return "Secure storage unavailable" error on OS failure. | **Implemented** | [keyring_store.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/keyring_store.rs#L22) (in-memory gated strictly by `#[cfg(test)]`) | Code inspection & `keyring_store::tests` |
| Stored secrets short: 32 bytes base64 for device secret, opaque string for refresh token. Secrets never cross to JS. | **Implemented** | [keyring_store.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/keyring_store.rs), [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs) | Code inspection (IPC contracts return only public keys/device IDs) |
| Login via existing API; store refresh token in Credential Manager. Remember last user for offline use. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L55) (`desktop_login`), [settings.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/settings.rs#L106) (`remembered_user`) | *No Rust unit test* for HTTP login endpoint; verified in E2E mock & manual test checklist |
| Screens: Server setup, Login, Library (available/downloaded), Player. | **Implemented** | [apps/web/src/desktop/](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/) | E2E test: `desktop-offline-player.spec.ts` |

---

### Task O4b: Download Manager in Rust (`apps/desktop/src-tauri`)

| Requirement | Status | Verification Evidence / File | Test Coverage |
| :--- | :--- | :--- | :--- |
| Command `start_download(lecture_id, rendition)`: `POST /lectures/{id}/offline-bundle`, poll `/offline-bundles/{job_id}` until ready, show size estimate first, then stream ZIP with `reqwest`. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L95) (`get_offline_estimate`, `start_download`), [downloader.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/downloader.rs) | Server endpoint tested in `test_offline_bundle.py`; UI flow tested in E2E `desktop-offline-player.spec.ts` |
| Resumable: use HTTP Range, persist progress in SQLite, survive app restart, pause/resume/cancel commands. | **Implemented** | [downloader.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/downloader.rs), [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L160) (`pause_download`, `resume_download`, `cancel_download`) | Rust test: `downloader::tests::test_resume_after_interruption` |
| Emit progress events to UI (bytes, total, speed, state). | **Implemented** | [downloader.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/downloader.rs#L125) (`emit("download_progress", ...)`), [useDownloads.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/hooks/useDownloads.ts) | E2E test: `desktop-offline-player.spec.ts` |
| On completion: verify ZIP sha256, unzip to temp folder, verify every file against `manifest.json` hashes. | **Implemented** | [downloader.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/downloader.rs#L180) (`verify_manifest_hashes`) | Rust test: `downloader::tests::test_hash_mismatch_rejected` |
| Encrypt each file at rest with AES-256-GCM in fixed-size chunks (256 KB) for Range reads. Derive per-file keys via HKDF from device secret + `lecture_id` + file path. Store header with version & chunk size. Securely wipe temp files. | **Implemented** | [encryption.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/encryption.rs) | Rust tests: `encryption::tests::test_encrypt_decrypt_round_trip`, `encryption::tests::test_tamper_detection`, `encryption::tests::test_range_read_across_chunk_boundary` |
| Store license token in SQLite `licenses` table. | **Implemented** | [downloader.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/downloader.rs#L240), [db.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/db.rs#L140) | Rust test: `commands::tests::test_revoke_and_wipe_on_renew` |
| Commands: `list_downloads`, `delete_download` (removes files, DB rows, license), `storage_usage`. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L180-L240) | Rust test: `commands::tests::test_revoke_and_wipe_on_renew` |
| UI (temporary): Download button with size estimate, progress bar, pause/resume, and Downloaded list with delete button. | **Implemented** | [LibraryView.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/LibraryView.tsx) | E2E test: `desktop-offline-player.spec.ts` |

---

### Task O4c: Local Playback Server and Player

| Requirement | Status | Verification Evidence / File | Test Coverage |
| :--- | :--- | :--- | :--- |
| Start axum server on `127.0.0.1` with random port at app start. Random per-session token in path. Reject any Origin other than app origin. | **Implemented** | [local_server.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/local_server.rs) | Rust tests: `local_server::tests::test_server_only_binds_to_127_0_0_1`, `local_server::tests::test_wrong_token_gets_403`, `local_server::tests::test_forbidden_origin_gets_403` |
| Serve `/<token>/lectures/<id>/hls/...` decrypting on the fly, with correct `Content-Type`, Range support (`206 Partial Content` + `Content-Range`), and CORS for app origin only. | **Implemented** | [local_server.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/local_server.rs#L85) | Rust tests: `local_server::tests::test_valid_license_serves_200_and_206`, `local_server::tests::test_range_request_across_chunk_boundary` |
| Before serving, check license: valid Ed25519 signature (pinned server public key), not expired, matches device_id and user. Otherwise return 403. | **Implemented** | [license_verifier.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/license_verifier.rs), [local_server.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/local_server.rs#L120) | Rust tests: `local_server::tests::test_expired_or_tampered_license_gets_403`, `license_verifier::tests::test_license_jwt_round_trip_and_expiration`, `license_verifier::tests::test_verify_lecture_access_database_flow` |
| UI: Downloaded tab opens player page using `hls.js` against local URL. Show captions (`captions.vtt`), chapters (`chapters.json`), poster. Resume position saved in SQLite every 10s and on pause/exit. | **Implemented** | [OfflinePlayer.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/OfflinePlayer.tsx), [HlsPlayer.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/components/HlsPlayer.tsx) | E2E test: `desktop-offline-player.spec.ts` |
| Same player component as web app reused where possible; only manifest URL source differs. | **Implemented** | Reuses [HlsPlayer.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/components/HlsPlayer.tsx) directly | Code inspection & E2E tests |
| Screenshot of downloaded lecture playing with network disabled. | **Implemented** | Saved as [offline-lecture-playback.png](file:///C:/Users/Bleed/.gemini/antigravity-cli/brain/d0a15a0a-30d5-43f8-b8b3-527b2df51037/offline-lecture-playback.png) and documented in artifact `offline-playback-report.md`. | Verified |

---

### Task O4d: License Lifecycle and Sync

| Requirement | Status | Verification Evidence / File | Test Coverage |
| :--- | :--- | :--- | :--- |
| Connectivity: Rust command checks server `/healthz` (do not rely on `navigator.onLine`). Expose state to UI and show banner. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L45) (`check_connectivity`), [useConnectivity.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/hooks/useConnectivity.ts), [DesktopApp.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/DesktopApp.tsx) | *No Rust unit test* for `check_connectivity` (requires HTTP server mock); UI banner tested in E2E `desktop-offline-player.spec.ts` |
| Renewal: when online, call `POST /offline-licenses/renew` for device; store new tokens; delete any lecture listed under `revoked` (files, DB rows) and tell user why. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L280) (`renew_device_licenses`), [useLibrary.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/hooks/useLibrary.ts) | Rust test: `commands::tests::test_revoke_and_wipe_on_renew`; API test: `test_offline_licenses.py::test_unenrolled_user_renew_returns_revoked` |
| Expiry UX: show days left per download; at expiry lecture shows "Connect to renew" and will not play. | **Implemented** | [license_verifier.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/license_verifier.rs#L340) (`get_license_status`), [LibraryView.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/LibraryView.tsx#L180) | Rust test: `license_verifier::tests::test_expiry_and_days_left` |
| Clock rollback protection: store highest timestamp seen; if system clock is earlier, treat licenses as expired until app syncs with server. | **Implemented** | [settings.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/settings.rs#L40) (`set_max_seen_timestamp_authoritative`, `check_clock_rollback`), [license_verifier.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/license_verifier.rs#L240) | Rust tests: `settings::tests::test_clock_rollback_protection`, `license_verifier::tests::test_clock_rollback_blocks_playback` |
| Offline login: if no network, open library for remembered user when at least one license is still valid; never verify passwords offline. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L12) (`get_desktop_state`), [LoginScreen.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/LoginScreen.tsx#L45) | *No Rust unit test* for offline branch in `get_desktop_state`; verified in manual checklist Test 4 |
| Progress sync: queue progress updates in `progress_queue` while offline and flush to `PUT /lectures/{id}/progress` when online (last-write-wins by timestamp). | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L360) (`queue_progress_update`, `flush_progress_queue`), [useLibrary.ts](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/hooks/useLibrary.ts) | Rust test: `commands::tests::test_progress_queue_flush_last_write_wins` |
| Logout: option to keep or wipe downloads. | **Implemented** | [commands.rs](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/desktop/src-tauri/src/commands.rs#L75) (`desktop_logout(wipe_downloads: bool)`), [DesktopApp.tsx](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/apps/web/src/desktop/DesktopApp.tsx#L120) | *No Rust unit test* for `desktop_logout`; verified in manual checklist Test 8 |
| Add `docs/offline-test-checklist.md` with manual steps: download, disconnect network, play, resume, expire, unenroll and sync, clock rollback, uninstall/reinstall. | **Implemented** | [docs/offline-test-checklist.md](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/docs/offline-test-checklist.md) | Verified matching all specified test procedures |

---

## 4. Development-Only Environment Setting: `LICENSE_TTL_SECONDS`

To enable testing of license expiration workflows without waiting 14 days, the dev setting `LICENSE_TTL_SECONDS` was integrated into the FastAPI service layer:

- **Location**: Defined in [services/api/app/settings.py](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/services/api/app/settings.py):
  ```python
  license_ttl_seconds: int = Field(
      default=14 * 24 * 3600,
      description="Dev-only TTL for offline licenses in seconds (default 14 days). Set to e.g. 180 to test expiry in minutes.",
  )
  ```
- **Usage**:
  1. In [services/api/app/services/bundle_service.py](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/services/api/app/services/bundle_service.py):
     ```python
     expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.license_ttl_seconds)
     ```
  2. In [services/api/app/services/device_service.py](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/services/api/app/services/device_service.py):
     ```python
     expires_at = now + timedelta(seconds=settings.license_ttl_seconds)
     ```
- **Configuration**:
  - Added to [.env.example](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/.env.example):
    ```env
    # Dev-only: offline license TTL in seconds (e.g. 180 for 3 minutes)
    # LICENSE_TTL_SECONDS=180
    ```
  - Allows rapid 3-minute expiration cycles during QA without modifying production code.

---

## 5. Offline Test Checklist Verification

The manual testing checklist is located at [docs/offline-test-checklist.md](file:///C:/Users/Bleed/ALL%20VS%20Code%20EXPERIMENT/Learning%20platform%20for%20university/docs/offline-test-checklist.md) and contains step-by-step instructions for:
1. **Lecture Download & Encryption at Rest** (manifest SHA-256 verification and AES-256-GCM chunked encryption).
2. **Disconnect Network** (zero-internet physical/adapter disconnect and UI offline banner display).
3. **Offline Playback & Local Stream Decryption** (`127.0.0.1` Axum server with ephemeral token, range requests, chapters, captions, poster).
4. **Offline Resume Position & Progress Queue** (SQLite `progress_queue` persistence across app restarts).
5. **License Expiration & Playback Lock** (verification of 403 Forbidden on expired tokens and UI lock).
6. **Server-Side Revocation & Auto-Wipe on Sync** (unenrollment revocation and automatic deletion of files/licenses).
7. **Clock Rollback Tamper Protection** (detecting backward system clock changes and blocking access).
8. **Logout Handling** (options to either keep downloads or wipe local media and database rows).
9. **Clean Uninstall & Reinstall Behavior** (residual credential and file verification).
