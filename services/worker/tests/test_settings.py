"""Tests for Worker Settings validation and storage root resolution."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from settings import Settings


def test_worker_settings_storage_root_relative_rejected() -> None:
    """Worker settings must reject relative STORAGE_ROOT."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(storage_root=Path("./worker_storage"))
    assert "STORAGE_ROOT must be an absolute path" in str(exc_info.value)


def test_worker_settings_storage_root_absolute_accepted(tmp_path: Path) -> None:
    """Worker settings must accept and resolve absolute writable STORAGE_ROOT."""
    valid_storage = tmp_path / "worker_storage"
    settings = Settings(storage_root=valid_storage)
    assert settings.storage_root == valid_storage.resolve()
    assert settings.resolved_storage_root == valid_storage.resolve()
    assert valid_storage.is_dir()
