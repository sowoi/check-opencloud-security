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
from webapp.encryption import decrypt_value, encrypt_value, ensure_encryption_ready
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


OLD_KEY = "22" * 32
NEW_KEY = "33" * 32


def test_a_rotated_key_writes_under_the_new_version_and_still_reads_the_old_one():
    """
    The reason the stored value carries a version at all.

    Rotation is the whole justification for the ``v<n>:`` prefix, and it is a
    two-sided promise: everything written after the rotation must use the new
    key, and everything written before it must still come back. Half of that
    is silent data loss and the other half is a key that was never retired.
    """
    before = settings(encrypt_results=True, encryption_keys={1: OLD_KEY})
    stored = encrypt_value("the result document", before)
    assert stored.startswith("v1:")

    after = settings(encrypt_results=True, encryption_keys={1: OLD_KEY, 2: NEW_KEY})
    assert decrypt_value(stored, after) == "the result document"
    assert encrypt_value("written after the rotation", after).startswith("v2:")


def test_a_value_whose_key_version_is_gone_is_lost_rather_than_guessed():
    """
    The negative half of rotation: retiring a key retires what it wrote.

    Nothing may fall back to another version - a value that decrypted under a
    key the operator deliberately removed would mean removing it changed
    nothing.
    """
    stored = encrypt_value("written under the retired key", settings(
        encrypt_results=True, encryption_keys={1: OLD_KEY}))

    retired = settings(encrypt_results=True, encryption_keys={2: NEW_KEY})

    assert decrypt_value(stored, retired) is None


def test_the_wrong_key_is_refused_rather_than_returning_rubbish():
    """AES-GCM authenticates; a wrong key must be an unreadable value, never a plausible one."""
    stored = encrypt_value("the result document", settings(
        encrypt_results=True, encryption_keys={1: OLD_KEY}))

    other = settings(encrypt_results=True, encryption_keys={1: NEW_KEY})

    assert decrypt_value(stored, other) is None


def test_a_tampered_value_does_not_decrypt():
    """
    The store is Redis, and Redis is a place other processes can write.

    The authentication tag is what makes an edited ciphertext an error rather
    than a different result document, so it has to be asserted here.
    """
    config = settings(encrypt_results=True, encryption_keys={1: KEY})
    stored = encrypt_value("the result document", config)

    body = stored[len("v1:") :]
    flipped = ("A" if body[0] != "A" else "B") + body[1:]

    assert decrypt_value(f"v1:{flipped}", config) is None
    assert decrypt_value(stored, config) == "the result document"


@pytest.mark.parametrize(
    "damaged",
    [
        "v1:not base64 at all",
        "v1:" + "AAAA",          # decodes, but shorter than a nonce and a tag
        "v1:",
        "vnotanumber:AAAA",
        "v1",                    # a 'v' with no colon behind it
    ],
)
def test_a_value_that_is_not_a_ciphertext_is_none_rather_than_an_exception(damaged):
    """
    Reading is done by the request path, which has to answer either way.

    Whatever is under the key - a truncated write, a value from a different
    scheme, something hand-edited - the reader gets None and renders a missing
    result. An exception here would be a 500 on a page that should say 404.
    """
    assert decrypt_value(damaged, settings(encrypt_results=True, encryption_keys={1: KEY})) is None


def test_turning_encryption_on_leaves_what_was_already_written_readable():
    """
    A deployment enables the setting with results already in Redis under a TTL.

    Those are plaintext and have to keep rendering until they expire, so a
    value that does not carry a version prefix is passed through rather than
    treated as a failed decryption.
    """
    config = settings(encrypt_results=True, encryption_keys={1: KEY})

    assert decrypt_value('{"domain": "already.example.com"}', config) == (
        '{"domain": "already.example.com"}'
    )


def test_nothing_is_encrypted_or_decrypted_where_the_setting_is_off():
    """The negative case: the functions are on every read and write path, including unconfigured ones."""
    off = settings()

    assert encrypt_value("the result document", off) == "the result document"
    assert decrypt_value("v1:whatever", off) == "v1:whatever"

    # On, but with no key: 'ensure_encryption_ready' is what refuses this at
    # startup. If a process reaches the write path anyway, it must not claim
    # a version prefix it has no key behind.
    keyless = settings(encrypt_results=True)
    assert encrypt_value("the result document", keyless) == "the result document"
