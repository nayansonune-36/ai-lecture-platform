# AI Lecture Platform: Architecture

A private, YouTube-like lecture catalog for one university. Professors publish, enrolled students learn, and an AI tutor answers from the actual lecture and cites `[MM:SS]`. Everything runs on university hardware.

Status: design baseline, Oct 2026. Update this file whenever a decision changes.

## 1. Goals and non-goals

**Goals**
- Professors create courses and upload lectures. The platform transcodes to adaptive HLS, transcribes, indexes and summarizes automatically.
- Students watch with adaptive quality, resume, captions and chapters.
- Students ask a text or voice tutor. Answers come only from the lecture and carry clickable `[MM:SS]` citations that seek the player.
- Students download the lectures they are enrolled in for offline playback and offline Q&A.
- Lectures are in English and Hindi, often mixed in one sentence.
- Content never reaches the open internet.

**Non-goals (day one)**
- Mirroring YouTube or offline access to millions of videos. That is petabytes of storage plus copyright and ToS problems. We design for scale (object storage, CDN-style serving, async jobs) but build for the real university catalog.
- Live streaming.
- Stopping someone from filming their screen. We keep content off the open internet; we do not claim DRM.

## 2. Decisions and corrections to the first plan

1. **Web Speech API is not used.** In Chrome it sends audio to Google, and it is unreliable in Android WebView. Voice input is recorded in the app and transcribed locally with faster-whisper (server) or whisper.cpp (offline client).
2. **Cloudflare Tunnel is for the app, API and chat only.** Cloudflare restricts serving large video through its free proxy. For remote video, use Tailscale/WireGuard, or a public IP and domain from university IT.
3. **Raw storage (`:9000`) and Ollama are never exposed to the LAN.** One Caddy reverse proxy is the only entry point. Video is served through short-lived signed URLs.
4. **Tauri only where native features are needed.** The smartboard and remote students use the same React app as a PWA. Tauri is used for the professor desktop app and the student offline app (local files, local DB, sidecars).
5. **Offline LLM runs on laptops only.** A 3 to 4B model needs about 8 GB of free RAM. On phones, offline Q&A is retrieval-only: the best transcript passages with timestamps, no generated answer.

## 3. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + TypeScript + Vite, hls.js | One codebase for web, PWA and Tauri |
| Desktop / offline app | Tauri v2 (Rust) | Local files, sidecars, encrypted storage |
| API | Python 3.12, FastAPI | Same language as the ML tools |
| Jobs | Redis + ARQ | Async transcode, transcribe, index, chapters, bundle |
| Database | PostgreSQL 16 + pgvector + pg_trgm | Users, courses, transcripts, vectors in one place |
| Video storage | Plain disk behind Caddy to start; SeaweedFS or Garage later | MinIO community edition is in maintenance mode, do not build on it |
| Transcoding | FFmpeg, HLS fMP4, 720/480/360p, thumbnails | |
| Speech-to-text | faster-whisper `large-v3` (server), whisper.cpp (client) | English + Hindi, segment timestamps |
| Embeddings | `bge-m3` via Ollama (1024 dims) | Multilingual, English question can hit Hindi passage |
| LLM | Ollama: Qwen3 8B or Gemma 3 12B on server; 4B model on laptops | Benchmark both on Hindi |
| Offline index | SQLite + FTS5 (`unicode61`) + sqlite-vec | Same logical schema as server |
| Auth | University SSO (OIDC) if available, otherwise local accounts with JWT (argon2 hashes) | Enrollment-based access |
| Proxy | Caddy | TLS, `forward_auth`, signed video URLs |

## 4. System diagram

```
 Professor (Tauri desktop)    Smartboard (PWA, LAN)    Student (PWA or Tauri, WAN)
            \                         |                        /
             \                        |             Tailscale / university IP / tunnel (API only)
              +-----------------------+-----------------------+
                                      |
                              Caddy reverse proxy
                    (TLS, forward_auth, signed video URLs)
                                      |
      +----------------+--------------+--------------+------------------+
      |                |                             |                  |
 FastAPI API     Video files (HLS)           Ollama (LLM + embed)   Whisper STT
 auth, courses,  served by Caddy             GPU, queued            GPU, queued
 chat, search
      |
 PostgreSQL + pgvector        Redis queue --> Workers
 users, transcripts,          1. FFmpeg    -> HLS + thumbnails
 chunks, vectors              2. Whisper   -> timestamped transcript -> VTT
                              3. Chunk + embed -> index
                              4. LLM       -> chapters + summary
```

## 5. Core flows

### 5.1 Upload and processing
1. Professor uploads a video (chunked, resumable). API stores the original and queues jobs.
2. `transcode`: FFmpeg produces HLS renditions at 720/480/360p, a poster and thumbnails.
3. `transcribe`: faster-whisper with per-segment language detection. Output normalized to one script per language (see 6).
4. `index`: segments are grouped into 30 to 60 second chunks with overlap. Each chunk keeps `start_ms` and `end_ms`, gets an embedding and a full-text entry.
5. `chapters`: the LLM produces chapters and a summary.
6. The professor reviews and edits the transcript. A correction re-indexes only the affected chunks. This improves answers more than any model change.

### 5.2 Ask the tutor
1. Text, or voice transcribed by Whisper (server, or local sidecar offline).
2. Hybrid retrieval, restricted to the lecture or course: vector similarity plus keyword search, then rerank. Vector gets the higher weight.
3. Top chunks go to the LLM with the rule: answer only from these passages, cite `[MM:SS]`, answer in the language of the question.
4. If retrieval is weak, the tutor says "not covered in this lecture" instead of guessing.
5. The UI parses `[MM:SS]` into links that seek the player. The response streams over SSE.

### 5.3 Copilot (seek by command)
LLM tool calling with three tools: `search_lecture(query)`, `seek(seconds)`, `summarize(start, end)`. "Jump to where she derives the wave equation" becomes search, then seek.

### 5.4 Offline bundle
1. Student taps Download for a lecture they are enrolled in.
2. Server builds a bundle: HLS segments for one chosen rendition, VTT captions, and a SQLite file with chunks, FTS and vectors.
3. The Tauri app stores it encrypted with a per-device key. A license expires after 14 days and renews when online.
4. Playback goes through a small local HTTP server inside the Tauri app, so hls.js works unchanged.
5. Offline tutor: local whisper.cpp plus a small LLM on laptops, retrieval-only on phones.

## 6. Hindi and English

- **Transcription**: `large-v3` or `large-v3-turbo`. Detect language per segment. Store Devanagari for Hindi speech and Latin for English technical terms. Normalize at ingest so search is consistent.
- **Evaluate before committing**: run 3 to 5 real lectures through the model and read the output. If Hindi accuracy is poor, test AI4Bharat IndicWhisper.
- **Embeddings**: `bge-m3` only (nomic-embed-text is English-biased).
- **Keyword search**: Postgres `simple` text config plus `pg_trgm` (no Hindi stemmer exists). SQLite FTS5 `unicode61` handles Devanagari.
- **Tutor language**: answers in the question's language. Citations stay `[MM:SS]`.
- **Evaluation set** must include Hindi question over English passage and the reverse.
- Captions are VTT in the spoken language. Translated captions are a later feature.

## 7. Access and content protection

- Every request is authenticated. Enrollment is checked on every API call and on every video request.
- Video URLs are signed (HMAC over path, user id and expiry, about 15 minutes) and verified by Caddy `forward_auth` against the API.
- HLS AES-128 encryption with keys served only after the enrollment check.
- Optional per-user watermark overlay if the university wants it.
- Offline bundles are encrypted at rest, bound to a device, and expire.
- Smartboard and server are reached by hostname (for example `lectures.campus.local` via local DNS), never a raw IP, so HTTPS certificates stay valid.
- Postgres, Redis, Ollama and Whisper listen on localhost or the internal Docker network only.

## 8. Smartboard (LAN)

Streams HLS from the server through Caddy, no downloads. Large touch targets, push-to-talk mic button that sends audio to the server's Whisper, thick scrubber with chapter markers, no typing required.

## 9. Hardware (pilot, one PC)

- NVIDIA GPU with 12 to 16 GB VRAM, 32 to 64 GB RAM, NVMe for the database and a large HDD for video.
- About 1 GB per lecture hour for three renditions.
- Transcription runs faster than real time on a good GPU.
- The bottleneck is concurrent LLM answers. 20 to 30 simultaneous questions will queue, so stream responses, cap context size and queue requests.

## 10. Build order

1. Auth, enrollment, upload, FFmpeg to HLS, player with resume and captions.
2. Whisper transcripts, chunking, hybrid search, tutor with `[MM:SS]` citations and click-to-seek.
3. Smartboard UI with voice, then chapters and summaries.
4. Remote access (Tailscale or university IP), signed URLs, encryption.
5. Offline bundles, local SQLite index, Whisper and LLM sidecar.
6. Copilot tool calling.

## 11. Open questions

- University SSO (Google Workspace or Microsoft) or local accounts?
- Students, courses and remote share at launch?
- Exact GPU on the PC?
- Monorepo (default) or separate repos?
