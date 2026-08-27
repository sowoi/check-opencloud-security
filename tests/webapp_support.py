"""
Shared plumbing for the web application tests.

The application is an optional extra, so every module that uses this one is
skipped rather than failed when FastAPI is not installed - the plugin's own
suite has to keep running on a monitoring host that installed the check and
nothing else.

Every client here talks to ``memory://``, which is the in-process backend from
:mod:`webapp.redis_backend`. It has real TTL semantics and a clock the tests
can move, so expiry is tested by expiring something rather than by waiting an
hour for Redis to do it.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi", reason="the web application extra is not installed")

from fastapi.testclient import TestClient

from webapp.app import create_app
from webapp.redis_backend import memory_backend, reset_memory_backends
from webapp.settings import WebSettings

MEMORY_URL = "memory://tests"


def settings(**overrides: Any) -> WebSettings:
    """Web settings for a test: no cooldown and no client limit unless asked."""
    defaults: dict[str, Any] = {
        "redis_url": MEMORY_URL,
        "ip_rate_limit": 0,
        "target_cooldown": 0,
        "result_ttl": 3600,
        "public_base_url": "http://testserver",
    }
    defaults.update(overrides)
    return WebSettings(**defaults)


def client(**overrides: Any) -> TestClient:
    """A test client wired to a fresh application against ``memory://``."""
    return TestClient(create_app(settings(**overrides)))


def backend():
    """The in-memory backend the clients share, for TTL and key assertions."""
    return memory_backend(MEMORY_URL)


@pytest.fixture(autouse=True)
def _isolated_backend():
    """
    Give every test an empty store.

    Without this a uuid, a rate-limit counter or a queue entry from an earlier
    test would still be there, and a test asserting "this scan is not visible"
    could pass for the wrong reason.
    """
    reset_memory_backends()
    yield
    reset_memory_backends()


# Documentation addresses have no A record, and CI has no resolver worth
# depending on. This is the smallest possible stand-in: the example domains
# answer with one documentation address, and one name answers with a private
# one so that the rebinding guard has something to catch.
EXAMPLE_ADDRESS = "203.0.113.10"
REBOUND_ADDRESS = "10.0.0.7"
EXAMPLE_SUFFIXES = (".example.com", ".example.org", ".example.net")
REBOUND_HOST = "rebound.example.com"


@pytest.fixture(autouse=True)
def _offline_resolver(monkeypatch):
    """
    Resolve the example domains without asking a name server.

    ``socket.getaddrinfo`` is global, so the replacement has to delegate:
    the worker tests scan a fake instance on 127.0.0.1 and have to keep being
    able to reach it. Only the example domains are answered here.

    The public-address test is widened for exactly the one documentation
    address those answers contain - RFC 5737 ranges are reserved, so Python
    quite correctly calls them private, and a stub that did not say so would
    be testing the guard against itself.
    """
    import ipaddress
    import socket

    from webapp import ssrf

    stub = ipaddress.ip_address(EXAMPLE_ADDRESS)
    really_public = ssrf._address_public
    real_getaddrinfo = socket.getaddrinfo

    def answer(address: str):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0))
        ]

    def fake_getaddrinfo(host: str, *args: Any, **kwargs: Any):
        if host == REBOUND_HOST:
            return answer(REBOUND_ADDRESS)
        if host.endswith(EXAMPLE_SUFFIXES) or host in {"example.com", "example.org"}:
            return answer(EXAMPLE_ADDRESS)
        return real_getaddrinfo(host, *args, **kwargs)

    def address_public(address):
        return True if address == stub else really_public(address)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(ssrf, "_address_public", address_public)
