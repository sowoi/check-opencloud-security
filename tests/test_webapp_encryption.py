"""
Encryption of results at rest, and the ways it can silently not happen.

Encryption is the one setting whose failure mode is invisible: everything
keeps working, the scan still renders, and the only difference is that the
result document is sitting in Redis in the clear. Every test here is written
so that it fails if that state can be reached again.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    MEMORY_URL,
    _isolated_backend,
    _offline_resolver,
    backend,
    client,
    settings,
)
from webapp.encryption import ensure_encryption_ready
from webapp.store import ScanStore, result_key

pytest.importorskip("cryptography", reason="the web application extra is not installed")

KEY = "11" * 32
UUID = "44444444-4444-4444-8444-444444444444"
SECRET_HOST = "confidential.example.com"

RESULT = {
    "domain": SECRET_HOST,
    "rating": 2,
    "productname": "OpenCloud",
    "extraChecks": {"basicAuthDisabled": False},
}


def _store(**overrides):
    """A store wired the way a process that writes results should wire one."""
    config = settings(encrypt_results=True, encryption_keys={1: KEY}, **overrides)
    return ScanStore(
        backend=backend(),
        ttl=300,
        encryption_config=config if config.encrypt_results else None,
    )


def _stored_result() -> str | None:
    return backend()._values.get(result_key(UUID))


def test_a_completed_result_is_unreadable_in_the_store_when_encryption_is_on():
    """The whole point of the setting: whoever reads Redis learns nothing."""
    store = _store()

    asyncio.run(store.create(UUID, target=f"https://{SECRET_HOST}",
                             ignore_hardenings=(), output_format="dashboard"))
    asyncio.run(store.mark_completed(UUID, RESULT))

    raw = _stored_result()
    assert raw is not None
    assert raw.startswith("v1:")
    assert SECRET_HOST not in raw
    assert "basicAuthDisabled" not in raw


def test_the_same_store_reads_its_own_encrypted_result_back():
    """Encryption that cannot be undone by the service is data loss, not privacy."""
    store = _store()

    asyncio.run(store.create(UUID, target=f"https://{SECRET_HOST}",
                             ignore_hardenings=(), output_format="dashboard"))
    asyncio.run(store.mark_completed(UUID, RESULT))
    record = asyncio.run(store.get(UUID))

    assert record is not None
    assert record.result == RESULT


def test_a_store_without_the_configuration_writes_the_result_in_the_clear():
    """
    The negative half, and the bug this suite was written for.

    The worker used to build its store without the encryption configuration,
    so the setting encrypted nothing while looking like it did. If this test
    ever stops describing an unconfigured store, the configured one has
    stopped mattering.
    """
    plain = ScanStore(backend=backend(), ttl=300, encryption_config=None)

    asyncio.run(plain.create(UUID, target=f"https://{SECRET_HOST}",
                             ignore_hardenings=(), output_format="dashboard"))
    asyncio.run(plain.mark_completed(UUID, RESULT))

    raw = _stored_result()
    assert raw is not None
    assert SECRET_HOST in raw


def test_the_worker_builds_its_store_with_encryption_when_it_is_configured(monkeypatch):
    """The worker writes the result, so the worker is where encryption happens."""
    from webapp import tasks

    monkeypatch.setenv("COS_WEB_REDIS_URL", MEMORY_URL)
    monkeypatch.setenv("COS_WEB_ENCRYPT_RESULTS", "true")
    monkeypatch.setenv("COS_WEB_ENCRYPTION_KEY_1", KEY)

    ctx: dict = {}
    asyncio.run(tasks.startup(ctx))
    try:
        assert ctx["store"].encryption_config is not None
        assert ctx["store"].encryption_config.encrypt_results is True
    finally:
        asyncio.run(tasks.shutdown(ctx))


def test_the_worker_leaves_encryption_off_when_it_was_never_asked_for(monkeypatch):
    """The negative case: nothing here turns encryption on by itself."""
    from webapp import tasks

    monkeypatch.setenv("COS_WEB_REDIS_URL", MEMORY_URL)

    ctx: dict = {}
    asyncio.run(tasks.startup(ctx))
    try:
        assert ctx["store"].encryption_config is None
    finally:
        asyncio.run(tasks.shutdown(ctx))


def test_asking_for_encryption_without_a_key_refuses_to_start():
    """Starting anyway would store plaintext under a setting that promised not to."""
    with pytest.raises(ValueError, match="unencrypted"):
        ensure_encryption_ready(settings(encrypt_results=True))

    with pytest.raises(ValueError):
        client(encrypt_results=True)


def test_a_malformed_key_is_refused_without_putting_the_key_in_the_message():
    """A rejected key ends up in a log or an issue report; it must not be readable there."""
    secret = "zz" * 32

    with pytest.raises(ValueError) as raised:
        ensure_encryption_ready(settings(encrypt_results=True, encryption_keys={1: secret}))

    assert secret not in str(raised.value)
    assert "version 1" in str(raised.value)


def test_a_short_key_is_refused_rather_than_used():
    """AES-256 with 8 bytes of key is not AES-256."""
    with pytest.raises(ValueError, match="256 bits"):
        ensure_encryption_ready(settings(encrypt_results=True, encryption_keys={1: "11" * 8}))


def test_a_deployment_that_never_enabled_encryption_is_left_alone():
    """The check must not become a reason a working deployment stops booting."""
    ensure_encryption_ready(settings())
    ensure_encryption_ready(settings(encryption_keys={1: "nonsense"}))
