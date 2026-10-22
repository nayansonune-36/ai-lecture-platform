"""Initial database schema from docs/schema.sql.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-23
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Extensions
    # -------------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # -------------------------------------------------------------------------
    # 2. Enums
    # -------------------------------------------------------------------------
    op.execute("CREATE TYPE user_role AS ENUM ('student', 'professor', 'admin');")
    op.execute("CREATE TYPE enrollment_role AS ENUM ('student', 'ta', 'instructor');")
    op.execute("CREATE TYPE lecture_status AS ENUM ('uploaded', 'processing', 'ready', 'failed');")
    op.execute(
        "CREATE TYPE job_type AS ENUM ('transcode', 'transcribe', 'index', 'chapters', 'bundle');"
    )
    op.execute(
        "CREATE TYPE job_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'cancelled');"
    )
    op.execute("CREATE TYPE chat_role AS ENUM ('user', 'assistant');")

    # -------------------------------------------------------------------------
    # 3. Users, sessions, and courses
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE users (
        id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        email          text NOT NULL,
        name           text NOT NULL,
        role           user_role NOT NULL DEFAULT 'student',
        password_hash  text,
        sso_subject    text UNIQUE,
        is_active      boolean NOT NULL DEFAULT true,
        created_at     timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX users_email_lower_uq ON users (lower(email));
    """)

    op.execute("""
    CREATE TABLE refresh_tokens (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash  text NOT NULL UNIQUE,
        expires_at  timestamptz NOT NULL,
        revoked_at  timestamptz,
        created_at  timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id);
    """)

    op.execute("""
    CREATE TABLE courses (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        code         text NOT NULL,
        title        text NOT NULL,
        description  text,
        term         text,
        owner_id     uuid NOT NULL REFERENCES users(id),
        archived     boolean NOT NULL DEFAULT false,
        created_at   timestamptz NOT NULL DEFAULT now(),
        UNIQUE (code, term)
    );
    """)

    op.execute("""
    CREATE TABLE enrollments (
        course_id   uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        user_id     uuid NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
        role        enrollment_role NOT NULL DEFAULT 'student',
        created_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (course_id, user_id)
    );
    CREATE INDEX enrollments_user_idx ON enrollments (user_id);
    """)

    # -------------------------------------------------------------------------
    # 4. Lectures and media
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE lectures (
        id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        course_id         uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        title             text NOT NULL,
        description       text,
        position          integer NOT NULL DEFAULT 0,
        status            lecture_status NOT NULL DEFAULT 'uploaded',
        published         boolean NOT NULL DEFAULT false,
        duration_ms       bigint,
        primary_language  text,
        original_path     text NOT NULL,
        hls_master_path   text,
        poster_path       text,
        created_by        uuid NOT NULL REFERENCES users(id),
        created_at        timestamptz NOT NULL DEFAULT now(),
        updated_at        timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX lectures_course_idx ON lectures (course_id, position);
    """)

    op.execute("""
    CREATE TABLE lecture_renditions (
        id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        lecture_id     uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
        height         integer NOT NULL,
        bitrate_kbps   integer NOT NULL,
        playlist_path  text NOT NULL,
        size_bytes     bigint,
        UNIQUE (lecture_id, height)
    );
    """)

    # -------------------------------------------------------------------------
    # 5. Transcripts, chunks, chapters, summaries
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE transcript_segments (
        id          bigserial PRIMARY KEY,
        lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
        idx         integer NOT NULL,
        start_ms    bigint NOT NULL,
        end_ms      bigint NOT NULL CHECK (end_ms >= start_ms),
        text        text NOT NULL,
        lang        text,
        edited      boolean NOT NULL DEFAULT false,
        edited_by   uuid REFERENCES users(id),
        UNIQUE (lecture_id, idx)
    );
    """)

    op.execute("""
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
    CREATE INDEX chunks_embedding_hnsw ON transcript_chunks
        USING hnsw (embedding vector_cosine_ops);
    """)

    op.execute("""
    CREATE TABLE chapters (
        id          bigserial PRIMARY KEY,
        lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
        idx         integer NOT NULL,
        start_ms    bigint NOT NULL,
        title       text NOT NULL,
        summary     text,
        UNIQUE (lecture_id, idx)
    );
    """)

    op.execute("""
    CREATE TABLE lecture_summaries (
        lecture_id    uuid PRIMARY KEY REFERENCES lectures(id) ON DELETE CASCADE,
        summary       text NOT NULL,
        model         text NOT NULL,
        generated_at  timestamptz NOT NULL DEFAULT now()
    );
    """)

    # -------------------------------------------------------------------------
    # 6. Student activity
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE playback_progress (
        user_id      uuid NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
        lecture_id   uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
        position_ms  bigint NOT NULL DEFAULT 0,
        completed    boolean NOT NULL DEFAULT false,
        updated_at   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, lecture_id)
    );
    """)

    op.execute("""
    CREATE TABLE chat_sessions (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        course_id   uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        lecture_id  uuid REFERENCES lectures(id) ON DELETE SET NULL,
        created_at  timestamptz NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE chat_messages (
        id          bigserial PRIMARY KEY,
        session_id  uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
        role        chat_role NOT NULL,
        content     text NOT NULL,
        citations   jsonb NOT NULL DEFAULT '[]',
        grounded    boolean,
        created_at  timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX chat_messages_session_idx ON chat_messages (session_id, id);
    """)

    # -------------------------------------------------------------------------
    # 7. Offline devices and licenses
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE devices (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name        text NOT NULL,
        public_key  text NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now(),
        revoked_at  timestamptz
    );
    """)

    op.execute("""
    CREATE TABLE offline_licenses (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     uuid NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
        device_id   uuid NOT NULL REFERENCES devices(id)  ON DELETE CASCADE,
        lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
        rendition   integer NOT NULL,
        issued_at   timestamptz NOT NULL DEFAULT now(),
        expires_at  timestamptz NOT NULL,
        revoked_at  timestamptz,
        UNIQUE (device_id, lecture_id)
    );
    """)

    # -------------------------------------------------------------------------
    # 8. Background jobs
    # -------------------------------------------------------------------------
    op.execute("""
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
    """)

    # -------------------------------------------------------------------------
    # 9. Access helper function
    # -------------------------------------------------------------------------
    op.execute("""
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
    """)


def downgrade() -> None:
    # 1. Drop function
    op.execute("DROP FUNCTION IF EXISTS can_view_lecture(uuid, uuid);")

    # 2. Drop tables in reverse foreign key order
    op.execute("DROP TABLE IF EXISTS jobs CASCADE;")
    op.execute("DROP TABLE IF EXISTS offline_licenses CASCADE;")
    op.execute("DROP TABLE IF EXISTS devices CASCADE;")
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE;")
    op.execute("DROP TABLE IF EXISTS chat_sessions CASCADE;")
    op.execute("DROP TABLE IF EXISTS playback_progress CASCADE;")
    op.execute("DROP TABLE IF EXISTS lecture_summaries CASCADE;")
    op.execute("DROP TABLE IF EXISTS chapters CASCADE;")
    op.execute("DROP TABLE IF EXISTS transcript_chunks CASCADE;")
    op.execute("DROP TABLE IF EXISTS transcript_segments CASCADE;")
    op.execute("DROP TABLE IF EXISTS lecture_renditions CASCADE;")
    op.execute("DROP TABLE IF EXISTS lectures CASCADE;")
    op.execute("DROP TABLE IF EXISTS enrollments CASCADE;")
    op.execute("DROP TABLE IF EXISTS courses CASCADE;")
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")

    # 3. Drop enums
    op.execute("DROP TYPE IF EXISTS chat_role CASCADE;")
    op.execute("DROP TYPE IF EXISTS job_status CASCADE;")
    op.execute("DROP TYPE IF EXISTS job_type CASCADE;")
    op.execute("DROP TYPE IF EXISTS lecture_status CASCADE;")
    op.execute("DROP TYPE IF EXISTS enrollment_role CASCADE;")
    op.execute("DROP TYPE IF EXISTS user_role CASCADE;")

    # 4. Note: Extensions vector, pg_trgm, pgcrypto are left intact or dropped if desired
    # op.execute("DROP EXTENSION IF EXISTS pgcrypto;")
    # op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
    # op.execute("DROP EXTENSION IF EXISTS vector;")
