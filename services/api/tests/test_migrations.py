"""Tests for Alembic migrations."""

import io
from contextlib import redirect_stdout

from alembic.command import downgrade, upgrade
from alembic.config import Config


def test_alembic_upgrade_sql() -> None:
    """Verify that alembic upgrade head generates valid SQL containing required elements."""
    alembic_cfg = Config("alembic.ini")
    buf = io.StringIO()

    with redirect_stdout(buf):
        upgrade(alembic_cfg, "head", sql=True)

    sql_output = buf.getvalue()

    # Check extensions
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in sql_output
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm;" in sql_output
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto;" in sql_output

    # Check enums
    assert "CREATE TYPE user_role" in sql_output
    assert "CREATE TYPE enrollment_role" in sql_output
    assert "CREATE TYPE lecture_status" in sql_output
    assert "CREATE TYPE job_type" in sql_output
    assert "CREATE TYPE job_status" in sql_output
    assert "CREATE TYPE chat_role" in sql_output

    # Check core tables
    assert "CREATE TABLE users" in sql_output
    assert "CREATE TABLE refresh_tokens" in sql_output
    assert "CREATE TABLE courses" in sql_output
    assert "CREATE TABLE enrollments" in sql_output
    assert "CREATE TABLE lectures" in sql_output
    assert "CREATE TABLE lecture_renditions" in sql_output
    assert "CREATE TABLE transcript_segments" in sql_output
    assert "CREATE TABLE transcript_chunks" in sql_output
    assert "CREATE TABLE chapters" in sql_output
    assert "CREATE TABLE lecture_summaries" in sql_output
    assert "CREATE TABLE playback_progress" in sql_output
    assert "CREATE TABLE chat_sessions" in sql_output
    assert "CREATE TABLE chat_messages" in sql_output
    assert "CREATE TABLE devices" in sql_output
    assert "CREATE TABLE offline_licenses" in sql_output
    assert "CREATE TABLE bundles" in sql_output
    assert "CREATE TABLE jobs" in sql_output

    # Check helper SQL function
    assert "CREATE OR REPLACE FUNCTION can_view_lecture" in sql_output


def test_alembic_downgrade_sql() -> None:
    """Verify that alembic downgrade generates valid drop statements."""
    alembic_cfg = Config("alembic.ini")
    buf = io.StringIO()

    with redirect_stdout(buf):
        downgrade(alembic_cfg, "0002_add_bundles_table:base", sql=True)

    sql_output = buf.getvalue()

    assert "DROP TABLE IF EXISTS bundles" in sql_output
    assert "DROP FUNCTION IF EXISTS can_view_lecture" in sql_output
    assert "DROP TABLE IF EXISTS jobs" in sql_output
    assert "DROP TABLE IF EXISTS users" in sql_output
    assert "DROP TYPE IF EXISTS user_role" in sql_output
