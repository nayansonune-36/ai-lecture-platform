"""Ed25519 offline license signing and verification."""

import base64
import logging
import uuid
from datetime import datetime
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.settings import get_settings

logger = logging.getLogger(__name__)

_cached_private_key: Ed25519PrivateKey | None = None
_cached_public_pem: str | None = None


def _load_private_key(key_str: str) -> Ed25519PrivateKey:
    """Parse private key from PEM or base64 or hex string."""
    key_bytes = key_str.strip().encode("utf-8")

    # 1. Standard PEM format
    if b"BEGIN" in key_bytes:
        loaded = serialization.load_pem_private_key(key_bytes, password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError("Configured LICENSE_SIGNING_KEY is not an Ed25519 private key")
        return loaded

    # 2. Try raw hex seed (64 hex characters = 32 bytes)
    try:
        raw_seed = bytes.fromhex(key_str.strip())
        if len(raw_seed) == 32:
            return Ed25519PrivateKey.from_private_bytes(raw_seed)
    except ValueError:
        pass

    # 3. Try base64-encoded PEM or raw bytes
    try:
        decoded = base64.b64decode(key_str.strip())
        if b"BEGIN" in decoded:
            loaded = serialization.load_pem_private_key(decoded, password=None)
            if isinstance(loaded, Ed25519PrivateKey):
                return loaded
        if len(decoded) == 32:
            return Ed25519PrivateKey.from_private_bytes(decoded)
    except Exception:
        pass

    raise ValueError("Could not parse LICENSE_SIGNING_KEY as PEM, hex, or base64")


def get_private_key() -> Ed25519PrivateKey:
    """Retrieve or initialize the Ed25519 private key singleton."""
    global _cached_private_key, _cached_public_pem
    if _cached_private_key is not None:
        return _cached_private_key

    settings = get_settings()
    key_str = getattr(settings, "license_signing_key", "").strip()

    if key_str:
        _cached_private_key = _load_private_key(key_str)
    else:
        # Development fallback: generate a fixed ephemeral key for dev/test
        logger.warning("LICENSE_SIGNING_KEY is not configured in settings. Generating dev keypair.")
        _cached_private_key = Ed25519PrivateKey.generate()

    pub = _cached_private_key.public_key()
    _cached_public_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return _cached_private_key


def get_public_key_pem() -> str:
    """Return the Ed25519 public key in PEM format."""
    global _cached_public_pem
    if _cached_public_pem is None:
        get_private_key()
    assert _cached_public_pem is not None
    return _cached_public_pem


def issue_license_token(
    user_id: uuid.UUID,
    device_id: uuid.UUID,
    lecture_id: uuid.UUID,
    bundle_sha256: str,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    """Sign an offline license token using Ed25519 private key.

    Contains user_id, device_id, lecture_id, bundle_sha256, issued_at, expires_at.
    """
    priv = get_private_key()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "device_id": str(device_id),
        "lecture_id": str(lecture_id),
        "bundle_sha256": bundle_sha256,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    return jwt.encode(payload, priv_pem, algorithm="EdDSA")


def verify_license_token(
    token: str,
    public_key_pem: str | None = None,
) -> dict[str, Any]:
    """Verify an offline license token signature and expiration."""
    pub_pem = public_key_pem or get_public_key_pem()
    return jwt.decode(token, pub_pem, algorithms=["EdDSA"])
