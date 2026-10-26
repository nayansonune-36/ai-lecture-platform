"""Tests for Settings validation and storage root resolution."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import Settings


def test_settings_storage_root_relative_path_rejected() -> None:
    """Relative STORAGE_ROOT must fail at startup with a clear error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(storage_root=Path("./relative/storage"))
    assert "STORAGE_ROOT must be an absolute path" in str(exc_info.value)


def test_settings_storage_root_absolute_path_accepted(tmp_path: Path) -> None:
    """Absolute writable STORAGE_ROOT must be accepted and resolved."""
    valid_storage = tmp_path / "valid_storage"
    settings = Settings(storage_root=valid_storage)
    assert settings.storage_root == valid_storage.resolve()
    assert settings.resolved_storage_root == valid_storage.resolve()
    assert valid_storage.is_dir()
