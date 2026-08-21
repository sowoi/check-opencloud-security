"""Sign exported result bytes for downstream automation."""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "X-COS-Signature"
SIGNATURE_ALGORITHM = "HMAC-SHA256"


def sign_bytes(body: bytes, key: str | None) -> str | None:
    """Return a versioned HMAC value, or no value when signing is disabled."""
    if not key:
        return None
    digest = hmac.new(
        key.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return f"{SIGNATURE_ALGORITHM}={digest}"


def verify_bytes(body: bytes, signature: str, key: str) -> bool:
    """Verify a value returned in :data:`SIGNATURE_HEADER`."""
    expected = sign_bytes(body, key)
    if expected is None:
        return False
    return hmac.compare_digest(expected, signature)
