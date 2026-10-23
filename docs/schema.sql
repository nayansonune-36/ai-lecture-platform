-- AI Lecture Platform: PostgreSQL 16 schema (baseline)
-- Requires: pgvector, pg_trgm, pgcrypto
-- Embedding model: bge-m3 (1024 dimensions). If the model changes, change vector(1024) everywhere.
-- Text search uses the 'simple' config on purpose: Postgres has no Hindi stemmer.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
CREATE TYPE user_role        AS ENUM ('student', 'professor', 'admin');
CREATE TYPE enrollment_role  AS ENUM ('student', 'ta', 'instructor');
CREATE TYPE lecture_status   AS ENUM ('uploaded', 'processing', 'ready', 'failed');
CREATE TYPE job_type         AS ENUM ('transcode', 'transcribe', 'index', 'chapters', 'bundle');
CREATE TYPE job_status       AS ENUM ('queued', 'running', 'succeeded', 'failed', 'cancelled');
CREATE TYPE chat_role        AS ENUM ('user', 'assistant');

-- ---------------------------------------------------------------------------
-- Users, sessions and courses
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          text NOT NULL,
    name           text NOT NULL,
    role           user_role NOT NULL DEFAULT 'student',
    password_hash  text,                 -- null when the account is SSO-only
    sso_subject    text UNIQUE,          -- OIDC "sub" claim
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_lower_uq ON users (lower(email));

CREATE TABLE refresh_tokens (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  text NOT NULL UNIQUE,          -- store a hash, never the token
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id);

CREATE TABLE courses (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code         text NOT NULL,          -- e.g. PHY201
    title        text NOT NULL,
    description  text,
    term         text,                   -- e.g. 2026-autumn
    owner_id     uuid NOT NULL REFERENCES users(id),
    archived     boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (code, term)
);

CREATE TABLE enrollments (
    course_id   uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
    role        enrollment_role NOT NULL DEFAULT 'student',
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (course_id, user_id)
);
CREATE INDEX enrollments_user_idx ON enrollments (user_id);

-- ---------------------------------------------------------------------------
-- Lectures and media
-- ---------------------------------------------------------------------------
CREATE TABLE lectures (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id         uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title             text NOT NULL,
    description       text,
    position          integer NOT NULL DEFAULT 0,       -- order inside the course
    status            lecture_status NOT NULL DEFAULT 'uploaded',
    published         boolean NOT NULL DEFAULT false,   -- students see it only when true AND status = 'ready'
    duration_ms       bigint,
    primary_language  text,                             -- 'en', 'hi', or 'mixed'
    original_path     text NOT NULL,                    -- relative to STORAGE_ROOT
    hls_master_path   text,                             -- e.g. lectures/<id>/hls/master.m3u8
    poster_path       text,
    created_by        uuid NOT NULL REFERENCES users(id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX lectures_course_idx ON lectures (course_id, position);

CREATE TABLE lecture_renditions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id     uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    height         integer NOT NULL,                    -- 720, 480, 360
    bitrate_kbps   integer NOT NULL,
    playlist_path  text NOT NULL,
    size_bytes     bigint,
    UNIQUE (lecture_id, height)
);

-- ---------------------------------------------------------------------------
-- Transcripts, chunks, chapters
-- ---------------------------------------------------------------------------
-- Raw Whisper output, one row per segment. Professors edit these.
CREATE TABLE transcript_segments (
    id          bigserial PRIMARY KEY,
    lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    idx         integer NOT NULL,
    start_ms    bigint NOT NULL,
    end_ms      bigint NOT NULL CHECK (end_ms >= start_ms),
    text        text NOT NULL,
    lang        text,                                   -- per-segment detected language
    edited      boolean NOT NULL DEFAULT false,
    edited_by   uuid REFERENCES users(id),
    UNIQUE (lecture_id, idx)
);

-- Retrieval units: 30 to 60 second windows with overlap.
CREATE TABLE transcript_chunks (
    id          bigserial PRIMARY KEY,
    lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    idx         integer NOT NULL,
    start_ms    bigint NOT NULL,
    end_ms      bigint NOT NULL CHECK (end_ms >= start_ms),
    text        text NOT NULL,
    lang        text,
    embedding   vector(1024),
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    UNIQUE (lecture_id, idx)
);
CREATE INDEX chunks_lecture_idx ON transcript_chunks (lecture_id, start_ms);
CREATE INDEX chunks_tsv_gin     ON transcript_chunks USING gin (tsv);
CREATE INDEX chunks_trgm_gin    ON transcript_chunks USING gin (text gin_trgm_ops);
CREATE INDEX chunks_embedding_hnsw ON transcript_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE chapters (
    id          bigserial PRIMARY KEY,
    lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    idx         integer NOT NULL,
    start_ms    bigint NOT NULL,
    title       text NOT NULL,
    summary     text,
    UNIQUE (lecture_id, idx)
);

CREATE TABLE lecture_summaries (
    lecture_id    uuid PRIMARY KEY REFERENCES lectures(id) ON DELETE CASCADE,
    summary       text NOT NULL,
    model         text NOT NULL,
    generated_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Student activity
-- ---------------------------------------------------------------------------
CREATE TABLE playback_progress (
    user_id      uuid NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    lecture_id   uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    position_ms  bigint NOT NULL DEFAULT 0,
    completed    boolean NOT NULL DEFAULT false,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, lecture_id)
);

CREATE TABLE chat_sessions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id   uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lecture_id  uuid REFERENCES lectures(id) ON DELETE SET NULL,  -- null = whole course
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id          bigserial PRIMARY KEY,
    session_id  uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        chat_role NOT NULL,
    content     text NOT NULL,
    citations   jsonb NOT NULL DEFAULT '[]',   -- [{"lecture_id": "...", "start_ms": 83000, "chunk_id": 42}]
    grounded    boolean,                       -- false when the tutor answered "not covered"
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chat_messages_session_idx ON chat_messages (session_id, id);

-- ---------------------------------------------------------------------------
-- Offline bundles, devices and licenses
-- ---------------------------------------------------------------------------
CREATE TABLE bundles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    rendition   integer NOT NULL,              -- height (720, 480, 360)
    version     integer NOT NULL DEFAULT 1,
    path        text NOT NULL,                 -- relative to STORAGE_ROOT
    size_bytes  bigint NOT NULL,
    sha256      text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (lecture_id, rendition, version)
);
CREATE INDEX bundles_lecture_rendition_idx ON bundles (lecture_id, rendition);

CREATE TABLE devices (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    public_key  text NOT NULL,                 -- device key used to wrap the bundle key
    created_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz
);

CREATE TABLE offline_licenses (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    device_id   uuid NOT NULL REFERENCES devices(id)  ON DELETE CASCADE,
    lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    rendition   integer NOT NULL,              -- chosen height
    issued_at   timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,          -- issued_at + 14 days, renewed when online
    revoked_at  timestamptz,
    UNIQUE (device_id, lecture_id)
);

-- ---------------------------------------------------------------------------
-- Background jobs (the queue itself is Redis; this table is the durable record)
-- ---------------------------------------------------------------------------
CREATE TABLE jobs (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id   uuid REFERENCES lectures(id) ON DELETE CASCADE,
    type         job_type NOT NULL,
    status       job_status NOT NULL DEFAULT 'queued',
    attempts     integer NOT NULL DEFAULT 0,
    payload      jsonb NOT NULL DEFAULT '{}',
    error        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    started_at   timestamptz,
    finished_at  timestamptz
);
CREATE INDEX jobs_lecture_idx ON jobs (lecture_id, type);
CREATE INDEX jobs_status_idx  ON jobs (status, created_at);

-- ---------------------------------------------------------------------------
-- Access helper: may this user view this lecture?
-- Students: enrolled in the course, lecture published and ready.
-- Course owner, instructors and admins: always.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION can_view_lecture(p_user uuid, p_lecture uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM lectures l
        JOIN courses c ON c.id = l.course_id
        LEFT JOIN enrollments e ON e.course_id = c.id AND e.user_id = p_user
        JOIN users u ON u.id = p_user AND u.is_active
        WHERE l.id = p_lecture
          AND (
                u.role = 'admin'
             OR c.owner_id = p_user
             OR e.role = 'instructor'
             OR (e.user_id IS NOT NULL AND l.published AND l.status = 'ready')
          )
    );
$$;
