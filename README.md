# AI Lecture Platform

A private, offline-capable AI lecture platform for a university. Professors upload lectures, the platform processes and indexes them, students watch with adaptive HLS and synchronized captions, and an AI tutor answers queries citing exact `[MM:SS]` timestamps.

## Repository Layout

```
apps/
  web/            React + TypeScript + Vite PWA (student, professor, smartboard views)
  desktop/        Tauri v2 shell (professor app, student offline app; wraps apps/web)
services/
  api/            FastAPI app (app/, tests/, alembic/)
  worker/         ARQ workers (transcode, transcribe, index, chapters, bundle)
packages/
  shared/         Shared TypeScript types and API client
infra/
  docker-compose.yml    postgres (pgvector), redis, caddy, ollama
  caddy/Caddyfile
docs/
  ARCHITECTURE.md  schema.sql  api.md  phase1-tasks.md
storage/          Local media root (gitignored)
```

## Prerequisites

- **Docker** and Docker Compose
- **Node.js** (v20+ recommended) and **pnpm** (v11+)
- **Python** (v3.12) and **uv**

## Environment Setup

Copy `.env.example` to create your local `.env`:

```bash
cp .env.example .env
```

Review and adjust environment variables as needed.

## Run Commands

### 1. Infrastructure (Docker)

Start the local backing services (PostgreSQL with pgvector, Redis, Caddy, Ollama):

```bash
docker compose -f infra/docker-compose.yml up -d
```

> **Security Note:** PostgreSQL, Redis, and Ollama do **not** publish ports to the host machine. Only Caddy publishes ports (`8080` for HTTP and `8443` for HTTPS in development).

To verify the `vector` extension inside PostgreSQL:
```bash
docker compose -f infra/docker-compose.yml exec postgres psql -U postgres -d lecture_platform -c "CREATE EXTENSION IF NOT EXISTS vector; \dx vector;"
```

### 2. Backend API (`services/api`)

```bash
cd services/api
uv sync
uv run pytest
uv run fastapi dev app/main.py
```

Linting and type checking:
```bash
uv run ruff check .
uv run mypy app/
```

### 3. Background Worker (`services/worker`)

```bash
cd services/worker
uv sync
uv run arq worker.WorkerSettings
```

### 4. Frontend Web App (`apps/web`)

From the repository root:

```bash
pnpm install
pnpm --filter web dev
```

Testing, linting, and type checking:
```bash
pnpm --filter web test
pnpm --filter web lint
pnpm --filter web typecheck
```

Access the application through Caddy at `http://localhost:8080/` (or directly via Vite at `http://localhost:5173/`).
API endpoints are reverse-proxied by Caddy at `http://localhost:8080/api/*`.
