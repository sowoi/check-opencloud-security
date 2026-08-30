"""
Two rate limits, both kept in Redis and both expiring on their own.

The client limit protects the service from one visitor; the target limit
protects an OpenCloud instance from the service. They are separate on purpose:
a busy but well-behaved client should not be able to make one instance the
target of a scan every second, and a popular instance should not lock out
everybody who wants to scan something else.

Client addresses are never stored in the clear. The key holds a truncated
HMAC of the address under a pepper, which is enough to count and useless
afterwards - the counter expires, and nothing on disk maps it back.

That pepper is per-process by default, which is right for a single process and
wrong the moment there are two. Each one derives a different key for the same
address, so a client silently gets one allowance per process and the limit
becomes a suggestion - with nothing in the log to say so. A deployment that
runs more than one web process therefore sets ``COS_WEB_RATE_LIMIT_SALT`` to
the same value everywhere, which is what makes them count together.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from .redis_backend import RedisBackend

# The fallback, regenerated on every restart. There is no reason for it to
# survive: a counter with a one-minute window has nothing to remember across a
# restart, and a key that never changes is a key that can be brute-forced
# offline. It is only ever right for a deployment running one web process.
_PROCESS_PEPPER = os.urandom(32)


def _pepper(salt: str | None) -> bytes:
    """The keying material for the fingerprints, configured or per-process."""
    return salt.encode("utf-8") if salt else _PROCESS_PEPPER


def _fingerprint(value: str, salt: str | None = None) -> str:
    digest = hmac.new(_pepper(salt), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:32]


def client_key(client: str, salt: str | None = None) -> str:
    """Rate-limit key for one client address."""
    return f"cos:web:rl:client:{_fingerprint(client, salt)}"


def target_key(host: str, salt: str | None = None) -> str:
    """Cooldown key for one scan target."""
    return f"cos:web:rl:target:{_fingerprint(host.lower(), salt)}"


def credential_key(client: str, salt: str | None = None) -> str:
    """Failed-authorisation key for one client address."""
    return f"cos:web:rl:auth:{_fingerprint(client, salt)}"


# An erasure request is rare and its credential belongs to the operator, so
# there is no legitimate caller who needs a sixth attempt inside five minutes.
# Only *failures* are counted: an operator working through a list of erasure
# requests presents the right token every time and never meets this.
CREDENTIAL_ATTEMPT_LIMIT = 5
CREDENTIAL_ATTEMPT_WINDOW_SECONDS = 300


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
    salt: str | None = None
    """Shared across every web process, or ``None`` for the per-process one.
    Two processes with different peppers do not share a counter, so this is
    what makes the client limit hold for a deployment that runs more than
    one."""

    async def check_client(self, client: str) -> LimitDecision:
        """Count one request from this client and decide whether it may run."""
        if self.client_limit <= 0:
            return LimitDecision(True)
        key = client_key(client, self.salt)
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
        key = target_key(host, self.salt)
        claimed = await self.backend.set(key, "1", ex=self.target_cooldown, nx=True)
        if claimed:
            return LimitDecision(True)
        retry_after = await self.backend.ttl(key)
        return LimitDecision(
            False, max(1, retry_after if retry_after > 0 else self.target_cooldown), "target"
        )

    async def check_credential(self, client: str) -> LimitDecision:
        """
        Whether this client may present an operator credential again.

        Counts nothing itself - only :meth:`record_failed_credential` does, and
        only on a wrong answer. A caller holding the right token is never
        slowed down, and a caller guessing gets five tries per window however
        fast it sends them.
        """
        key = credential_key(client, self.salt)
        raw = await self.backend.get(key)
        try:
            count = int(raw) if raw is not None else 0
        except ValueError:  # pragma: no cover - only a hand-edited key gets here
            count = 0
        if count < CREDENTIAL_ATTEMPT_LIMIT:
            return LimitDecision(True)
        retry_after = await self.backend.ttl(key)
        return LimitDecision(
            False,
            max(
                1,
                retry_after
                if retry_after > 0
                else CREDENTIAL_ATTEMPT_WINDOW_SECONDS,
            ),
            "credential",
        )

    async def record_failed_credential(self, client: str) -> None:
        """Count one wrong credential from this client, for the window."""
        key = credential_key(client, self.salt)
        count = await self.backend.incr(key)
        if count == 1:
            await self.backend.expire(key, CREDENTIAL_ATTEMPT_WINDOW_SECONDS)

    async def release_target(self, host: str) -> None:
        """Give the slot back when the request is rejected for another reason."""
        if self.target_cooldown > 0:
            await self.backend.delete(target_key(host, self.salt))

    async def forget_target(self, host: str) -> int:
        """
        Erase the cooldown derived from a host, and say whether one existed.

        The key holds a fingerprint and a counter, never the hostname, but it
        is still state derived from a target - so an erasure request removes it
        too, and the receipt counts it.
        """
        return await self.backend.delete(target_key(host, self.salt))
