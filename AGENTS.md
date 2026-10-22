# AGENTS.md

Instructions for AI coding agents working in this repo. Read this file and `docs/ARCHITECTURE.md` before changing code.

## Project

A private, offline-capable AI lecture platform for one university. Professors upload lectures, students watch, ask an AI tutor that answers from the lecture and cites `[MM:SS]`, and can download lectures for offline use. Lectures are in English and Hindi (often mixed).

## Repo layout

```
apps/
  web/            React + TypeScript + Vite PWA (student, professor, smartboard views)
  desktop/        Tauri v2 shell (professor app, student offline app); wraps apps/web
services/
  api/            FastAPI app (app/, tests/, alembic/)
  worker/         ARQ workers: transcode, transcribe, index, chapters, bundle
packages/
  shared/         Shared TypeScript types and the API client (generated from OpenAPI)
infra/
  docker-compose.yml    postgres (pgvector), redis, caddy, ollama
  caddy/Caddyfile
docs/
  ARCHITECTURE.md  schema.sql  api.md  phase1-tasks.md
storage/          Local media root (gitignored)
```

## Commands

Update this section as soon as the real commands exist.

```
# infra
docker compose -f infra/docker-compose.yml up -d

# api
cd services/api && uv sync && uv run alembic upgrade head && uv run fastapi dev app/main.py
cd services/api && uv run pytest

# worker
cd services/worker && uv sync && uv run arq worker.WorkerSettings

# web
pnpm install && pnpm --filter web dev
pnpm --filter web test
pnpm --filter web test:e2e
pnpm --filter web lint && pnpm --filter web typecheck
```

## Conventions

**General**
- Small, focused commits. One task from `docs/phase1-tasks.md` per commit or PR.
- Do not add a dependency without saying why in the commit message. Prefer the standard library and what is already in the stack.
- Every new endpoint, table or job type must be reflected in `docs/api.md` or `docs/schema.sql` in the same change.
- All configuration comes from environment variables, loaded through one settings module. Provide `.env.example`; never commit `.env`.

**Python (api, worker)**
- Python 3.12, type hints everywhere, `ruff` for lint and format, `mypy` on `app/`.
- FastAPI routers per resource; business logic in `services/` modules, not in route functions.
- SQLAlchemy 2.x async with Alembic migrations. Schema changes only through migrations; keep `docs/schema.sql` in sync.
- Pydantic models for every request and response.
- Long work (FFmpeg, Whisper, embedding, LLM) runs in workers, never in a request handler.
- Jobs are idempotent: re-running a job for the same lecture must not duplicate rows or files.

**TypeScript (web, desktop)**
- Strict mode, no `any`. Use the generated API client in `packages/shared`.
- Server state through TanStack Query. Keep components small.
- Smartboard view: minimum touch target 56px, no typing required, large text.
- All user-visible strings go through an i18n layer (English and Hindi UI).

**Time and units**
- Media positions are integer milliseconds in the database and API (`start_ms`, `position_ms`). Format to `MM:SS` (or `H:MM:SS` past one hour) only in the UI and in tutor output.

**Languages (English + Hindi)**
- Never assume ASCII or English. Use UTF-8 end to end. Test with Devanagari input.
- Use `simple` Postgres text search config plus `pg_trgm`. Do not add an English stemmer.
- Embeddings are `bge-m3`, 1024 dimensions. Do not change the model or dimension without a migration plan.
- The tutor answers in the language of the question.

## Tutor rules (do not weaken)

1. Answer only from retrieved lecture chunks. No outside knowledge presented as lecture content.
2. Every factual statement carries a `[MM:SS]` citation that maps to a real chunk.
3. If retrieval is weak, say the topic is not covered. Do not guess.
4. Retrieval is always scoped to the lecture or course the user is allowed to view.

## NEVER do these

- **Never expose storage, Postgres, Redis, Ollama or Whisper ports outside the host or Docker network.** Everything goes through Caddy.
- **Never serve video, captions, transcripts or bundles without an enrollment check.** Media URLs must be signed and short-lived.
- **Never trust a course, lecture or user id from the client.** Authorize on the server for every request.
- **Never run FFmpeg, Whisper, embedding or LLM calls inside a request handler.**
- **Never send lecture content, audio or user data to an external cloud service** (no Google Speech, no hosted LLM APIs, no analytics SDKs). Everything stays on university hardware.
- **Never use the Web Speech API.** Record audio and send it to our Whisper.
- **Never put secrets, signing keys or passwords in code, logs or the repo.**
- **Never store voice audio** after transcription.
- **Never build on MinIO community edition.** Use plain disk behind Caddy now; SeaweedFS or Garage later.
- **Never hard-code IP addresses.** Use hostnames and environment variables.
- **Never change `docs/schema.sql` or `docs/api.md` silently.** Update them with the code change.
- **Never bypass or delete tests to make a build pass.**

## Definition of done

- Code runs locally from a clean checkout following the commands above.
- Lint, types and tests pass.
- New behavior has tests (API: pytest with a test database; web: component or Playwright test for the main flow).
- Docs updated: `docs/api.md`, `docs/schema.sql`, `.env.example`, and the Commands section here if they changed.
- Authorization is covered by at least one test that proves a non-enrolled user is refused.

## When unsure

Ask before making architectural changes or adding services. Prefer the smallest change that satisfies the task.
