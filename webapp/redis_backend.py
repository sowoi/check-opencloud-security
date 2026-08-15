"""
The little slice of Redis this application actually uses.

Two implementations sit behind one narrow protocol: the real
``redis.asyncio`` client, and an in-process one selected with ``memory://``.
The in-process backend exists so the test suite - and a single-container
evaluation run - needs no Redis server, and so that TTL behaviour can be
tested by moving a clock instead of waiting an hour.

Only the commands used by :mod:`webapp.store` and :mod:`webapp.ratelimit` are
here. Anything wider would be a Redis client, and there is a perfectly good
one on PyPI already.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

MEMORY_SCHEME = "memory://"


@runtime_checkable
class RedisBackend(Protocol):
    """The commands the web application needs from Redis."""

    async def get(self, key: str) -> str | None: ...

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool: ...

    async def delete(self, *keys: str) -> int: ...

    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> bool: ...

    async def ttl(self, key: str) -> int: ...

    async def rpush(self, key: str, value: str) -> int: ...

    async def lrem(self, key: str, count: int, value: str) -> int: ...

    async def lpos(self, key: str, value: str) -> int | None: ...

    async def llen(self, key: str) -> int: ...

    async def close(self) -> None: ...


class MemoryRedis:
    """
    An in-process stand-in for Redis, with real expiry semantics.

    Instances are shared per URL through :func:`memory_backend`, so the API
    and a fake worker in the same process see the same state - exactly the
    relationship the real deployment has through a Redis server.
    """

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lists: dict[str, list[str]] = {}
        self._expiry: dict[str, float] = {}
        self._offset = 0.0

    # -- test seam ---------------------------------------------------------
    def advance(self, seconds: float) -> None:
        """Move this backend's clock forward, expiring whatever is due."""
        self._offset += seconds
        self._sweep()

    def clear(self) -> None:
        """Forget everything. Used between tests."""
        self._values.clear()
        self._lists.clear()
        self._expiry.clear()
        self._offset = 0.0

    # -- internals ---------------------------------------------------------
    def _now(self) -> float:
        return time.monotonic() + self._offset

    def _sweep(self) -> None:
        now = self._now()
        for key in [key for key, due in self._expiry.items() if due <= now]:
            self._expiry.pop(key, None)
            self._values.pop(key, None)
            self._lists.pop(key, None)

    def _live(self, key: str) -> bool:
        due = self._expiry.get(key)
        if due is not None and due <= self._now():
            self._expiry.pop(key, None)
            self._values.pop(key, None)
            self._lists.pop(key, None)
            return False
        return True

    # -- commands ----------------------------------------------------------
    async def get(self, key: str) -> str | None:
        return self._values.get(key) if self._live(key) else None

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        if nx and self._live(key) and key in self._values:
            return False
        self._values[key] = value
        if ex is not None:
            self._expiry[key] = self._now() + ex
        else:
            self._expiry.pop(key, None)
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            self._expiry.pop(key, None)
            if self._values.pop(key, None) is not None:
                removed += 1
            if self._lists.pop(key, None) is not None:
                removed += 1
        return removed

    async def incr(self, key: str) -> int:
        current = int(await self.get(key) or 0) + 1
        self._values[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        if not self._live(key) or (key not in self._values and key not in self._lists):
            return False
        self._expiry[key] = self._now() + seconds
        return True

    async def ttl(self, key: str) -> int:
        if not self._live(key) or (key not in self._values and key not in self._lists):
            return -2
        due = self._expiry.get(key)
        if due is None:
            return -1
        return max(0, round(due - self._now()))

    async def rpush(self, key: str, value: str) -> int:
        self._live(key)
        self._lists.setdefault(key, []).append(value)
        return len(self._lists[key])

    async def lrem(self, key: str, count: int, value: str) -> int:
        self._live(key)
        items = self._lists.get(key)
        if not items:
            return 0
        before = len(items)
        if count == 0:
            self._lists[key] = [item for item in items if item != value]
        else:
            remaining = abs(count)
            kept: list[str] = []
            for item in items if count > 0 else reversed(items):
                if remaining and item == value:
                    remaining -= 1
                    continue
                kept.append(item)
            self._lists[key] = kept if count > 0 else list(reversed(kept))
        return before - len(self._lists[key])

    async def lpos(self, key: str, value: str) -> int | None:
        self._live(key)
        try:
            return self._lists.get(key, []).index(value)
        except ValueError:
            return None

    async def llen(self, key: str) -> int:
        self._live(key)
        return len(self._lists.get(key, []))

    async def close(self) -> None:
        return None


_MEMORY_BACKENDS: dict[str, MemoryRedis] = {}


def memory_backend(url: str = MEMORY_SCHEME) -> MemoryRedis:
    """Return the process-wide in-memory backend for this URL."""
    return _MEMORY_BACKENDS.setdefault(url, MemoryRedis())


def reset_memory_backends() -> None:
    """Drop every in-memory backend. Called by the test fixtures."""
    for backend in _MEMORY_BACKENDS.values():
        backend.clear()
    _MEMORY_BACKENDS.clear()


class _RealRedis:
    """Thin adapter mapping the protocol onto ``redis.asyncio``."""

    def __init__(self, client: object) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)  # type: ignore[attr-defined]
        return None if value is None else _text(value)

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        stored = await self._client.set(key, value, ex=ex, nx=nx)  # type: ignore[attr-defined]
        return bool(stored)

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return int(await self._client.delete(*keys))  # type: ignore[attr-defined]

    async def incr(self, key: str) -> int:
        return int(await self._client.incr(key))  # type: ignore[attr-defined]

    async def expire(self, key: str, seconds: int) -> bool:
        return bool(await self._client.expire(key, seconds))  # type: ignore[attr-defined]

    async def ttl(self, key: str) -> int:
        return int(await self._client.ttl(key))  # type: ignore[attr-defined]

    async def rpush(self, key: str, value: str) -> int:
        return int(await self._client.rpush(key, value))  # type: ignore[attr-defined]

    async def lrem(self, key: str, count: int, value: str) -> int:
        return int(await self._client.lrem(key, count, value))  # type: ignore[attr-defined]

    async def lpos(self, key: str, value: str) -> int | None:
        position = await self._client.lpos(key, value)  # type: ignore[attr-defined]
        return None if position is None else int(position)

    async def llen(self, key: str) -> int:
        return int(await self._client.llen(key))  # type: ignore[attr-defined]

    async def close(self) -> None:
        await self._client.aclose()  # type: ignore[attr-defined]


def _text(value: object) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def create_backend(url: str) -> RedisBackend:
    """
    Open a backend for this URL.

    ``memory://`` selects the in-process implementation; anything else is
    handed to ``redis.asyncio``, which is imported lazily so that the test
    suite does not need the driver installed.
    """
    if url.startswith(MEMORY_SCHEME):
        return memory_backend(url)
    from redis.asyncio import Redis

    return _RealRedis(Redis.from_url(url, decode_responses=True))
