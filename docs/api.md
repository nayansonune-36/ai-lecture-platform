# API Reference (v1)

Base path: `/api/v1`. JSON unless stated. All times are ISO 8601 UTC; media positions are integer milliseconds (`*_ms`).

## Conventions

- **Auth**: `Authorization: Bearer <access_token>`. Access tokens last 15 minutes; refresh tokens last 14 days.
- **Roles**: `student`, `professor`, `admin`. Course-level roles come from `enrollments`.
- **Errors**: `{"error": {"code": "string", "message": "human readable", "details": {}}}` with the right HTTP status.
- **Pagination**: `?limit=` (default 25, max 100) and `?cursor=`; responses return `next_cursor` or `null`.
- **Streaming**: chat uses Server-Sent Events (`text/event-stream`).
- **Authorization rule**: every lecture-scoped endpoint calls `can_view_lecture` (see `schema.sql`). Never trust a course or lecture id from the client without checking it.
- **Citations**: `[MM:SS]` in text (or `[H:MM:SS]` past one hour). The structured form is always returned too.

## Auth

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | Email + password, returns access and refresh tokens |
| GET | `/auth/sso/start` | public | Begin OIDC login (when SSO is configured) |
| GET | `/auth/sso/callback` | public | OIDC callback, issues tokens |
| POST | `/auth/refresh` | public | Rotate refresh token |
| POST | `/auth/logout` | any | Revoke refresh token |
| GET | `/me` | any | Current user and role |

## Users (admin)

| Method | Path | Purpose |
|---|---|---|
| GET | `/users` | List and search users |
| POST | `/users` | Create a user |
| POST | `/users/import` | Bulk create from CSV (email, name, role) |
| PATCH | `/users/{id}` | Change role, deactivate |

## Courses and enrollment

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/courses` | any | Courses the caller owns or is enrolled in |
| POST | `/courses` | professor | Create a course |
| GET | `/courses/{id}` | member | Course detail |
| PATCH | `/courses/{id}` | owner | Edit or archive |
| GET | `/courses/{id}/enrollments` | owner | List members |
| POST | `/courses/{id}/enrollments` | owner | Add by email list or CSV |
| DELETE | `/courses/{id}/enrollments/{user_id}` | owner | Remove a member (also revokes offline licenses) |

## Lectures and upload

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/courses/{id}/lectures` | member | Lectures (students see only published + ready) |
| POST | `/courses/{id}/lectures` | owner | Create lecture record, returns `upload_url` |
| PUT | `/lectures/{id}/upload` | owner | Resumable chunked upload (`Content-Range`) |
| POST | `/lectures/{id}/upload/complete` | owner | Finish upload, queue `transcode` |
| GET | `/lectures/{id}` | viewer | Detail: status, duration, language, chapters, summary |
| PATCH | `/lectures/{id}` | owner | Title, description, position, `published` |
| DELETE | `/lectures/{id}` | owner | Delete lecture and all derived files |
| GET | `/lectures/{id}/jobs` | owner | Pipeline progress (`transcode`, `transcribe`, `index`, `chapters`) |
| POST | `/lectures/{id}/reprocess` | owner | Re-run a stage: `{"stage": "transcribe"}` |

## Playback

| Method | Path | Purpose |
|---|---|---|
| POST | `/lectures/{id}/playback-token` | Returns `{"manifest_url", "expires_at"}`: a signed URL for `master.m3u8`. Segment URLs inherit the signature through the playlist. |
| GET | `/lectures/{id}/captions.vtt?lang=` | Captions as WebVTT |
| GET | `/lectures/{id}/chapters` | `[{"start_ms", "title", "summary"}]` |
| GET | `/lectures/{id}/progress` | Resume position |
| PUT | `/lectures/{id}/progress` | `{"position_ms": 83000, "completed": false}`; the player sends this about every 10 seconds |
| GET | `/internal/auth/video` | **Internal only.** Caddy `forward_auth` target. Validates signature, expiry and enrollment. Not routed from the outside. |

Signed URL format: `/media/lectures/{id}/hls/master.m3u8?exp=<unix>&uid=<user>&sig=<hmac>`. HMAC-SHA256 over `path|exp|uid` with `MEDIA_SIGNING_KEY`. Lifetime about 15 minutes.

## Transcript editing (professor)

| Method | Path | Purpose |
|---|---|---|
| GET | `/lectures/{id}/transcript` | Segments with `start_ms`, `end_ms`, `text`, `lang`, `edited` |
| PATCH | `/lectures/{id}/transcript/segments/{idx}` | Fix text; re-indexes affected chunks and regenerates VTT |

## Search

| Method | Path | Purpose |
|---|---|---|
| GET | `/lectures/{id}/search?q=` | Hybrid search inside one lecture |
| GET | `/courses/{id}/search?q=` | Hybrid search across a course |

Response:
```json
{"results": [{"lecture_id": "...", "start_ms": 83000, "end_ms": 121000,
              "text": "...", "score": 0.82}]}
```

## Tutor chat (text)

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat/sessions` | `{"course_id", "lecture_id"?}`; omit `lecture_id` to ask the whole course |
| GET | `/chat/sessions/{id}` | History |
| POST | `/chat/sessions/{id}/messages` | `{"content": "..."}`; returns an SSE stream |

SSE events:
- `token`: `{"text": "..."}`
- `citation`: `{"lecture_id", "start_ms", "label": "12:34"}`
- `done`: `{"message_id", "grounded": true}`
- `error`: `{"code", "message"}`

If retrieval is weak, the answer says the topic is not covered and `grounded` is `false`.

## Voice

| Method | Path | Purpose |
|---|---|---|
| POST | `/voice/transcribe` | Multipart audio (webm/opus or wav, max 60 s). Returns `{"text", "language"}`. Audio is not stored. |

The client then sends `text` to the chat endpoint. Optional: `POST /chat/sessions/{id}/voice-messages` does both in one call.

## Copilot

| Method | Path | Purpose |
|---|---|---|
| POST | `/copilot` | `{"lecture_id", "message", "current_ms"}` |

Returns the reply plus optional actions the player executes:
```json
{"reply": "She derives it at 24:10.",
 "actions": [{"type": "seek", "position_ms": 1450000}]}
```
Tools exposed to the model: `search_lecture(query)`, `seek(seconds)`, `summarize(start_ms, end_ms)`.

## Offline

| Method | Path | Purpose |
|---|---|---|
| POST | `/devices` | Register a device, send its public key (max 3 active devices per user) |
| GET | `/devices` | List user's registered devices |
| DELETE | `/devices/{id}` | Revoke device; invalidates all its licenses |
| GET | `/license-public-key` | Returns Ed25519 public key in PEM format for license verification |
| GET | `/lectures/{id}/offline-estimate?rendition=480` | Returns approximate bundle download size in bytes |
| POST | `/lectures/{id}/offline-bundle` | `{"device_id", "rendition": 480}`; queues or reuses `bundle` job, creates or refreshes offline license |
| GET | `/offline-bundles/{job_id}` | Status, size_bytes, sha256, signed download URL, and license token |
| POST | `/offline-licenses/renew` | `{"device_id"}`; extends licenses for lectures user can still view; returns renewed tokens and revoked list |

Bundle contents: encrypted HLS segments for one rendition, `captions.vtt`, `chapters.json`, and `index.sqlite` (chunks, FTS5, vectors, same logical schema as the server).

## Admin and health

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness: `{"status": "ok"}` |
| GET | `/readyz` | Postgres, Redis, storage, Ollama, Whisper reachable |
| GET | `/admin/jobs` | Queue and recent failures |
| POST | `/admin/jobs/{id}/retry` | Retry a failed job |

## Rate limits (starting values)

- `/chat/*` and `/copilot`: 10 requests per minute per user, one active generation per user.
- `/voice/transcribe`: 10 per minute per user.
- `/auth/login`: 5 failed attempts per 15 minutes per account and IP.
