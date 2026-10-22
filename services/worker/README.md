# Worker Service

ARQ background worker for transcoding, transcription, indexing, chaptering, and bundling.

## Commands

```bash
# Sync dependencies
uv sync

# Run the ARQ worker
uv run arq worker.WorkerSettings

# Run transcode pipeline locally on a video file (standalone)
uv run python cli.py path/to/video.mp4 --output-dir ./output_hls --skip-db

# Run transcode pipeline for a database lecture record
uv run python cli.py path/to/video.mp4 --lecture-id <UUID>

# Run test suite
uv run pytest

# Lint and typecheck
uv run ruff check .
uv run mypy .
```
