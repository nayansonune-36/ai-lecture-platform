"""Tests for core security and password hashing."""

from app.core.security import hash_password, verify_password


def test_password_hashing_and_verification() -> None:
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
