"""
Encryption layer for sensitive Redis data.

Results are encrypted at rest using AES-256-GCM when enabled. Each encrypted
value includes a version number allowing key rotation: new encryptions use the
current key, old encryptions with older keys still decrypt. Metadata that
identifies scans (UUIDs, timestamps, hostnames) remains in clear text to allow
listing and TTL operations.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptionConfig(Protocol):
    """Settings for encryption."""

    @property
    def encrypt_results(self) -> bool:
        """Whether result encryption is enabled."""

    @property
    def encryption_keys(self) -> Mapping[int, str]:
        """Encryption key mapping by version."""


def ensure_encryption_ready(config: EncryptionConfig) -> None:
    """
    Refuse to start when encryption is asked for but cannot happen.

    ``encrypt_value`` returns its input unchanged when no key is configured,
    which is the right behaviour for a deployment that never turned encryption
    on and a silent disaster for one that did: results would be written to
    Redis in the clear by a service whose operator believes otherwise. There
    is no safe way to guess, so a misconfigured process refuses to run instead
    of quietly storing plaintext.
    """
    if not config.encrypt_results:
        return
    if not config.encryption_keys:
        raise ValueError(
            "COS_WEB_ENCRYPT_RESULTS is on but no COS_WEB_ENCRYPTION_KEY_<version> "
            "is set. Results would be stored unencrypted."
        )
    for version in sorted(config.encryption_keys):
        key = _hex_to_bytes(config.encryption_keys[version], f"encryption key version {version}")
        if len(key) != 32:
            raise ValueError(
                f"Encryption key version {version} must be 256 bits (32 bytes), "
                f"got {len(key)} bytes."
            )


def _get_current_key_version(config: EncryptionConfig) -> int | None:
    """Return the highest encryption key version, or None if no keys are set."""
    if not config.encryption_keys:
        return None
    return max(config.encryption_keys.keys())


def _hex_to_bytes(hex_string: str, name: str) -> bytes:
    """Convert hex string to bytes, raising ValueError on invalid input."""
    try:
        return bytes.fromhex(hex_string)
    except ValueError as e:
        # The value is key material. A traceback out of the encrypt path is
        # logged by the worker, and a malformed key is exactly the moment an
        # operator copies that log into an issue report.
        raise ValueError(f"Invalid {name} format: expected 64 hex characters") from e


def encrypt_value(value: str, config: EncryptionConfig) -> str:
    """
    Encrypt a value using AES-256-GCM if encryption is enabled.

    Returns the encrypted value in format: "v<version>:<base64_encrypted_data>"
    If encryption is disabled or no keys are configured, returns the value unchanged.
    """
    if not config.encrypt_results or not config.encryption_keys:
        return value

    version = _get_current_key_version(config)
    if version is None:
        return value

    key_hex = config.encryption_keys[version]
    key = _hex_to_bytes(key_hex, f"encryption key version {version}")

    if len(key) != 32:
        raise ValueError(f"Encryption key must be 256 bits (32 bytes), got {len(key)} bytes")

    nonce = os.urandom(12)
    cipher = AESGCM(key)
    ciphertext = cipher.encrypt(nonce, value.encode("utf-8"), None)
    
    encrypted_data = nonce + ciphertext
    encoded = base64.b64encode(encrypted_data).decode("ascii")
    
    return f"v{version}:{encoded}"


def decrypt_value(encrypted_value: str, config: EncryptionConfig) -> str | None:
    """
    Decrypt a value encrypted with encrypt_value.

    Returns the decrypted value, or None if decryption fails (invalid format,
    missing key, or authentication failure).
    """
    if not config.encrypt_results:
        return encrypted_value

    if not encrypted_value.startswith("v"):
        return encrypted_value

    try:
        colon_idx = encrypted_value.index(":")
        version_str = encrypted_value[1:colon_idx]
        version = int(version_str)
        encoded = encrypted_value[colon_idx + 1 :]

        if version not in config.encryption_keys:
            return None

        key_hex = config.encryption_keys[version]
        key = _hex_to_bytes(key_hex, f"encryption key version {version}")

        if len(key) != 32:
            return None

        encrypted_data = base64.b64decode(encoded)

        if len(encrypted_data) < 12 + 16:
            return None

        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        cipher = AESGCM(key)
        plaintext = cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError, ValueError, TypeError):
        return None


def encrypt_result_dict(result: dict, config: EncryptionConfig) -> dict:
    """
    Encrypt the 'result' field of a scan record if encryption is enabled.

    Metadata fields (uuid, timestamp, target, status) remain in clear text
    to allow listing and TTL operations.
    """
    if not config.encrypt_results or "result" not in result:
        return result

    result = result.copy()
    if isinstance(result["result"], str):
        result["result"] = encrypt_value(result["result"], config)
    return result


def decrypt_result_dict(result: dict, config: EncryptionConfig) -> dict | None:
    """
    Decrypt the 'result' field of a scan record if it's encrypted.

    Returns None if decryption fails.
    """
    if "result" not in result:
        return result

    result = result.copy()
    if isinstance(result["result"], str):
        decrypted = decrypt_value(result["result"], config)
        if decrypted is None:
            return None
        result["result"] = decrypted
    return result
