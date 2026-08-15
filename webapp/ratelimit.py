"""
Two rate limits, both kept in Redis and both expiring on their own.

The client limit protects the service from one visitor; the target limit
protects an OpenCloud instance from the service. They are separate on purpose:
a busy but well-behaved client should not be able to make one instance the
target of a scan every second, and a popular instance should not lock out
everybody who wants to scan something else.

Client addresses are never stored in the clear. The key holds a truncated
HMAC of the address under a per-process key, which is enough to count and
useless afterwards - the counter expires, and nothing on disk maps it back.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from .redis_backend import RedisBackend

# Regenerated on every restart. There is no reason for it to survive: a
# counter with a one-minute window has nothing to remember across a restart,
# and a key that never changes is a key that can be brute-forced offline.
_PEPPER = os.urandom(32)


def _fingerprint(value: str) -> str:
    digest = hmac.new(_PEPPER, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:32]


def client_key(client: str) -> str:
    """Rate-limit key for one client address."""
    return f"cos:web:rl:client:{_fingerprint(client)}"


def target_key(host: str) -> str:
    """Cooldown key for one scan target."""
    return f"cos:web:rl:target:{_fingerprint(host.lower())}"


@dataclass(frozen=True)
class LimitDecision:
    """Whether a request may proceed, and when to try again if not."""

    allowed: bool
    retry_after: int = 0
    scope: str = ""


@dataclass
class RateLimiter:
    """Fixed-window client limit plus a per-target cooldown."""

    backend: RedisBackend
    client_limit: int
    client_window: int
    target_cooldown: int

    async def check_client(self, client: str) -> LimitDecision:
        """Count one request from this client and decide whether it may run."""
        if self.client_limit <= 0:
            return LimitDecision(True)
        key = client_key(client)
        count = await self.backend.incr(key)
        if count == 1:
            await self.backend.expire(key, self.client_window)
        if count > self.client_limit:
            retry_after = await self.backend.ttl(key)
            return LimitDecision(
                False, max(1, retry_after if retry_after > 0 else self.client_window), "client"
            )
        return LimitDecision(True)

    async def check_target(self, host: str) -> LimitDecision:
        """
        Claim the cooldown slot for one target.

        ``SET NX`` is what makes this safe under concurrency: the first
        request to arrive creates the key, everyone else sees it already
        there, and no read-then-write window exists for two simultaneous
        requests to slip through.
        """
        if self.target_cooldown <= 0:
            return LimitDecision(True)
        key = target_key(host)
        claimed = await self.backend.set(key, "1", ex=self.target_cooldown, nx=True)
        if claimed:
            return LimitDecision(True)
        retry_after = await self.backend.ttl(key)
        return LimitDecision(
            False, max(1, retry_after if retry_after > 0 else self.target_cooldown), "target"
        )

    async def release_target(self, host: str) -> None:
        """Give the slot back when the request is rejected for another reason."""
        if self.target_cooldown > 0:
            await self.backend.delete(target_key(host))
