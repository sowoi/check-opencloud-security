"""
Handing a scan to the worker pool.

Enqueueing is deliberately separate from the store: the store owns the state a
visitor can see, the queue owns the fact that a worker will eventually pick
the job up. The job payload is the uuid and nothing else, so no target and no
waiver list ever travels through the queue - the worker reads those back out
of the scan's own namespace.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .redis_backend import MEMORY_SCHEME
from .settings import WebSettings

LOGGER = logging.getLogger("check_opencloud.web.queue")

JOB_NAME = "run_scan"


class ScanQueue(Protocol):
    """Somewhere to put a scan so that a worker runs it."""

    async def enqueue(self, uuid: str) -> None: ...

    async def close(self) -> None: ...


class InertQueue:
    """
    Accepts jobs and runs none of them.

    Selected by ``memory://``. A scan enqueued here stays ``queued`` forever,
    which is exactly the state the overload tests need to observe and exactly
    what a deployment with no worker running would show.
    """

    def __init__(self) -> None:
        self.jobs: list[str] = []

    async def enqueue(self, uuid: str) -> None:
        self.jobs.append(uuid)

    async def close(self) -> None:
        return None


class ArqQueue:
    """The real queue: an ARQ job on a Redis-backed FIFO."""

    def __init__(self, pool: Any, queue_name: str) -> None:
        self._pool = pool
        self._queue_name = queue_name

    async def enqueue(self, uuid: str) -> None:
        await self._pool.enqueue_job(JOB_NAME, uuid, _queue_name=self._queue_name)

    async def close(self) -> None:
        await self._pool.aclose()


def redis_settings(settings: WebSettings) -> Any:
    """ARQ's own connection settings, derived from the configured URL."""
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(settings.redis_url)


async def create_queue(settings: WebSettings) -> ScanQueue:
    """Open the queue this deployment is configured for."""
    if settings.redis_url.startswith(MEMORY_SCHEME):
        return InertQueue()
    from arq import create_pool

    pool = await create_pool(redis_settings(settings))
    return ArqQueue(pool, settings.queue_name)
