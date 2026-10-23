"""Add bundles table for offline lecture packaging.

Revision ID: 0002_add_bundles_table
Revises: 0001_initial_schema
Create Date: 2026-10-23
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_bundles_table"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE bundles (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        lecture_id  uuid NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
        rendition   integer NOT NULL,
        version     integer NOT NULL DEFAULT 1,
        path        text NOT NULL,
        size_bytes  bigint NOT NULL,
        sha256      text NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now(),
        UNIQUE (lecture_id, rendition, version)
    );
    CREATE INDEX bundles_lecture_rendition_idx ON bundles (lecture_id, rendition);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bundles CASCADE;")
