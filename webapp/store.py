"""
Ephemeral, per-scan state in Redis.

Three keys per scan, all under a namespace derived from a ``uuid4``, all with
a TTL::

    scan:{uuid}:status      queued | running | completed | failed
    scan:{uuid}:result      the result document produced by the scanner
    scan:{uuid}:metadata    what was asked for, and when

The uuid is a capability: knowing it is the only way to reach the scan, and
there is deliberately no way to enumerate the namespace. Nothing outside this
module builds a key, so the isolation is one function wide and can be tested
as such.

The FIFO position shown to a waiting visitor comes from one shared list of
pending uuids. It holds identifiers and nothing else, so reading a position
out of it tells you the length of the queue and never anything about another
scan's target or result.
"""

from __future__ import annotations

import json
import time
import uuid as uuid_module
from dataclasses import dataclass
from typing import Any

from .catalog import DEFAULT_RELEASE_TRACK
from .encryption import EncryptionConfig, decrypt_value, encrypt_value
from .redis_backend import RedisBackend

QUEUE_KEY = "cos:web:queue"

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"

TERMINAL_STATES = frozenset({STATE_COMPLETED, STATE_FAILED})


def is_scan_uuid(candidate: str) -> bool:
    """Whether a path segment is one of our identifiers.

    Nothing this service issues is anything but a uuid4, so a lookup for
    something else is a probe. Refusing it before it reaches Redis keeps
    caller-controlled text out of a key name entirely.
    """
    try:
        return uuid_module.UUID(candidate).version == 4
    except (ValueError, AttributeError, TypeError):
        return False


def status_key(uuid: str) -> str:
    """Redis key holding the lifecycle state of one scan."""
    return f"scan:{uuid}:status"


def result_key(uuid: str) -> str:
    """Redis key holding the result document of one scan."""
    return f"scan:{uuid}:result"


def metadata_key(uuid: str) -> str:
    """Redis key holding what the visitor asked for."""
    return f"scan:{uuid}:metadata"


@dataclass(frozen=True)
class ScanRecord:
    """Everything known about one scan, assembled for the holder of its uuid."""

    uuid: str
    state: str
    metadata: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    queue_position: int | None
    queue_length: int
    expires_in: int

    def as_dict(self) -> dict[str, Any]:
        """The JSON body of ``GET /api/scans/{uuid}``."""
        payload: dict[str, Any] = {
            "uuid": self.uuid,
            "state": self.state,
            "target": self.metadata.get("target"),
            "ignoreHardenings": self.metadata.get("ignoreHardenings", []),
            "outputFormat": self.metadata.get("outputFormat", "dashboard"),
            "releaseTrack": self.metadata.get("releaseTrack"),
            "createdAt": self.metadata.get("createdAt"),
            "startedAt": self.metadata.get("startedAt"),
            "finishedAt": self.metadata.get("finishedAt"),
            "expiresIn": self.expires_in,
            "queue": {
                "position": self.queue_position,
                "length": self.queue_length,
            },
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass
class ScanStore:
    """Reads and writes the per-scan namespace, and nothing else."""

    backend: RedisBackend
    ttl: int
    encryption_config: EncryptionConfig | None = None

    async def create(
        self,
        uuid: str,
        *,
        target: str,
        ignore_hardenings: tuple[str, ...],
        output_format: str,
        release_track: str = DEFAULT_RELEASE_TRACK,
    ) -> None:
        """Register a new scan as ``queued`` and put it at the back of the line."""
        metadata = {
            "target": target,
            "ignoreHardenings": list(ignore_hardenings),
            "outputFormat": output_format,
            "releaseTrack": release_track,
            "createdAt": _now(),
            "startedAt": None,
            "finishedAt": None,
        }
        await self.backend.set(metadata_key(uuid), _dump(metadata), ex=self.ttl)
        await self.backend.set(status_key(uuid), _dump({"state": STATE_QUEUED}), ex=self.ttl)
        await self.backend.rpush(QUEUE_KEY, uuid)
        # The queue is a display aid, not a job store; it must not outlive the
        # scans it refers to if a worker dies.
        await self.backend.expire(QUEUE_KEY, max(self.ttl, 3600))

    async def mark_running(self, uuid: str) -> None:
        """A worker picked this scan up."""
        await self.backend.lrem(QUEUE_KEY, 1, uuid)
        await self._patch_metadata(uuid, {"startedAt": _now()})
        await self.backend.set(status_key(uuid), _dump({"state": STATE_RUNNING}), ex=self.ttl)

    async def mark_completed(self, uuid: str, result: dict[str, Any]) -> None:
        """Store the result document and stop the clock."""
        await self.backend.lrem(QUEUE_KEY, 1, uuid)
        result_str = _dump(result)
        if self.encryption_config:
            result_str = encrypt_value(result_str, self.encryption_config)
        await self.backend.set(result_key(uuid), result_str, ex=self.ttl)
        await self._patch_metadata(uuid, {"finishedAt": _now()})
        await self.backend.set(
            status_key(uuid), _dump({"state": STATE_COMPLETED}), ex=self.ttl
        )

    async def mark_failed(self, uuid: str, error: str) -> None:
        """Record why the scan could not produce a result."""
        await self.backend.lrem(QUEUE_KEY, 1, uuid)
        await self._patch_metadata(uuid, {"finishedAt": _now()})
        await self.backend.set(
            status_key(uuid),
            _dump({"state": STATE_FAILED, "error": error}),
            ex=self.ttl,
        )

    async def get(self, uuid: str) -> ScanRecord | None:
        """
        Assemble one scan, or ``None`` when it never existed or has expired.

        The caller turns ``None`` into a 404 without distinguishing the two:
        a visitor must not be able to probe which uuids were ever real.
        """
        if not is_scan_uuid(uuid):
            return None
        raw_status = await self.backend.get(status_key(uuid))
        if raw_status is None:
            return None
        status = _load(raw_status) or {}
        metadata = _load(await self.backend.get(metadata_key(uuid))) or {}
        state = str(status.get("state") or STATE_QUEUED)

        result = None
        if state == STATE_COMPLETED:
            result_str = await self.backend.get(result_key(uuid))
            if result_str is not None:
                if self.encryption_config:
                    decrypted = decrypt_value(result_str, self.encryption_config)
                    if decrypted is None:
                        return None
                    result = _load(decrypted)
                else:
                    result = _load(result_str)

        position: int | None = None
        length = await self.backend.llen(QUEUE_KEY)
        if state == STATE_QUEUED:
            index = await self.backend.lpos(QUEUE_KEY, uuid)
            position = None if index is None else index + 1

        expires_in = await self.backend.ttl(status_key(uuid))
        return ScanRecord(
            uuid=uuid,
            state=state,
            metadata=metadata,
            result=result,
            error=status.get("error"),
            queue_position=position,
            queue_length=length,
            expires_in=max(0, expires_in) if expires_in >= 0 else self.ttl,
        )

    async def _patch_metadata(self, uuid: str, changes: dict[str, Any]) -> None:
        metadata = _load(await self.backend.get(metadata_key(uuid))) or {}
        metadata.update(changes)
        await self.backend.set(metadata_key(uuid), _dump(metadata), ex=self.ttl)


def _now() -> float:
    return round(time.time(), 3)


def _dump(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), default=str)


def _load(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        loaded = json.loads(raw)
    except ValueError:  # pragma: no cover - only a corrupted key gets here
        return None
    return loaded if isinstance(loaded, dict) else None
