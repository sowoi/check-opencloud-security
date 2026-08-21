"""
The ARQ worker.

Run it with::

    python -m webapp.tasks

One job per scan, ``max_jobs`` of them at a time, and that number comes from
``COS_WEB_MAX_WORKERS`` - never from a request. The scan itself is blocking
(the scanner speaks ``requests``), so it goes to a thread and leaves the event
loop free to keep the other jobs' status keys current.

Logging here is lifecycle only: a uuid and a state. No target, no client, no
result. A queue log that records what everybody scanned is a database of what
everybody scanned, however briefly it is kept.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any, ClassVar

from opencloud_local_scan import ScanError

from .advisories import refresh_advisories, stored_database
from .catalog import sanitize_release_track
from .encryption import ensure_encryption_ready
from .queue import redis_settings
from .redis_backend import RedisBackend, create_backend
from .runner import execute_scan
from .schedule import refresh_schedule, stored_schedule
from .settings import WebSettings
from .ssrf import TargetRejected, validate_target
from .store import WORKER_HEARTBEAT_KEY, ScanStore

LOGGER = logging.getLogger("check_opencloud.web.worker")
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TTL_SECONDS = HEARTBEAT_INTERVAL_SECONDS * 3
# A whole minute for one documentation page, so that a slow morning is a slow
# refresh rather than a missed one.
REFRESH_JOB_TIMEOUT_SECONDS = 60


async def publish_worker_heartbeat(backend: RedisBackend) -> None:
    """Publish a short-lived signal that this worker can reach Redis."""
    await backend.set(WORKER_HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL_SECONDS)


async def _heartbeat(backend: RedisBackend) -> None:
    while True:
        await publish_worker_heartbeat(backend)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def run_scan(ctx: dict[str, Any], uuid: str) -> str:
    """
    Run one queued scan and record the outcome under its own uuid.

    Returns the final state so that a failed job is still a *completed* job:
    the failure belongs in the visitor's result page, not in an ARQ retry
    loop that would scan a stranger's instance three more times.
    """
    settings: WebSettings = ctx["web_settings"]
    store: ScanStore = ctx["store"]

    record = await store.get(uuid)
    if record is None:
        LOGGER.info("scan_expired %s", uuid)
        return "expired"

    await store.mark_running(uuid)
    LOGGER.info("scan_started %s", uuid)

    try:
        target = validate_target(
            str(record.metadata.get("target") or ""),
            allow_private=settings.allow_private_targets,
            allowed_hosts=settings.extra_hosts_allowed,
        )
        ignore = tuple(str(name) for name in record.metadata.get("ignoreHardenings") or ())
        track = sanitize_release_track(record.metadata.get("releaseTrack"))
        # The lifecycle schedule the daily refresh last accepted, or the one
        # bundled in the wheel. Read per job rather than at startup so a
        # worker that has been up for a week rates against this morning's
        # picture of the world.
        schedule = await stored_schedule(store.backend, settings)
        # The advisories the daily refresh last accepted, likewise: an
        # advisory published after this image was built is exactly the one a
        # visitor most needs to hear about.
        database = await stored_database(store.backend, settings)
        result = await asyncio.wait_for(
            asyncio.to_thread(
                execute_scan, target, ignore, settings, track, schedule, database
            ),
            timeout=settings.job_timeout,
        )
    except TargetRejected as exc:
        await store.mark_failed(uuid, str(exc))
        LOGGER.info("scan_rejected %s", uuid)
        return "failed"
    except asyncio.TimeoutError:
        await store.mark_failed(uuid, "The instance took too long to answer.")
        LOGGER.info("scan_timeout %s", uuid)
        return "failed"
    except ScanError as exc:
        await store.mark_failed(uuid, str(exc))
        LOGGER.info("scan_failed %s", uuid)
        return "failed"
    except Exception:  # pragma: no cover - defensive; a crash must not leak
        await store.mark_failed(uuid, "The scan could not be completed.")
        LOGGER.exception("scan_error %s", uuid)
        return "failed"

    await store.mark_completed(uuid, result)
    LOGGER.info("scan_completed %s", uuid)
    return "completed"


async def refresh_release_schedule(ctx: dict[str, Any]) -> str:
    """
    Re-read the OpenCloud lifecycle page. Scheduled daily, and at startup.

    The whole point is that a deployment does not have to be redeployed to
    learn about a release. It cannot fail a scan: every outcome other than
    ``updated`` leaves the schedule exactly as it was, and the job returns
    the outcome rather than raising.
    """
    settings: WebSettings = ctx["web_settings"]
    return await refresh_schedule(ctx["backend"], settings)


async def refresh_advisory_database(ctx: dict[str, Any]) -> str:
    """
    Ask the advisory feed which vulnerabilities affect OpenCloud. Daily.

    Kept a separate job from the release schedule so that one source being
    down does not stop the other being read, and so an operator reading the
    log can see which of them it was.
    """
    settings: WebSettings = ctx["web_settings"]
    return await refresh_advisories(ctx["backend"], settings)


async def startup(ctx: dict[str, Any]) -> None:
    """Open the store the worker writes its state to."""
    settings = WebSettings.from_env()
    ctx["web_settings"] = settings
    ctx["backend"] = create_backend(settings.redis_url)
    # The worker is the process that writes the result document, so this is
    # the store that decides whether results are encrypted at rest. Leaving
    # the configuration out here meant COS_WEB_ENCRYPT_RESULTS encrypted
    # nothing at all while looking like it did.
    ensure_encryption_ready(settings)
    ctx["store"] = ScanStore(
        backend=ctx["backend"],
        ttl=settings.result_ttl,
        encryption_config=settings if settings.encrypt_results else None,
    )
    await publish_worker_heartbeat(ctx["backend"])
    ctx["heartbeat_task"] = asyncio.create_task(_heartbeat(ctx["backend"]))


async def shutdown(ctx: dict[str, Any]) -> None:
    """Close the store connection."""
    heartbeat_task = ctx.get("heartbeat_task")
    if heartbeat_task is not None:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
    backend = ctx.get("backend")
    if backend is not None:
        await backend.delete(WORKER_HEARTBEAT_KEY)
        await backend.close()


class WorkerSettings:
    """ARQ entry point. Concurrency is read from the environment, once."""

    functions: ClassVar[list] = [run_scan]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 1
    keep_result = 0


def reference_data_jobs(settings: WebSettings) -> list:
    """
    The daily reference-data refreshes, as ARQ cron jobs - each one optional.

    ``run_at_startup`` matters as much as the daily run: a deployment brought
    up hours after a release - or after an advisory - should not wait for the
    next small hours to hear about it. ``unique`` keeps a horizontally scaled
    deployment to one fetch, however many workers it runs. The two are
    separate jobs, and deliberately not at the same minute: one source being
    slow or down should have nothing to do with the other.
    """
    from arq import cron

    jobs = []
    if settings.schedule_refresh:
        jobs.append(
            cron(
                refresh_release_schedule,
                name="refresh_release_schedule",
                hour=settings.schedule_refresh_hour,
                minute=17,
                run_at_startup=True,
                unique=True,
                timeout=REFRESH_JOB_TIMEOUT_SECONDS,
                max_tries=1,
            )
        )
    if settings.advisory_refresh:
        jobs.append(
            cron(
                refresh_advisory_database,
                name="refresh_advisory_database",
                hour=settings.schedule_refresh_hour,
                minute=41,
                run_at_startup=True,
                unique=True,
                timeout=REFRESH_JOB_TIMEOUT_SECONDS,
                max_tries=1,
            )
        )
    return jobs


def _configure_worker_settings() -> type[WorkerSettings]:
    """
    Fill in the settings ARQ reads off the class, at import time of the worker.

    ``redis_settings`` has to be a real ``RedisSettings`` instance rather than
    something lazy, and building it imports ``arq``. Doing that here rather
    than in the class body keeps :mod:`webapp.tasks` importable - and the
    worker's job function testable - on an installation without ARQ.
    """
    settings = WebSettings.from_env()
    WorkerSettings.cron_jobs = reference_data_jobs(settings)  # type: ignore[attr-defined]
    WorkerSettings.max_jobs = settings.max_workers  # type: ignore[attr-defined]
    WorkerSettings.job_timeout = settings.job_timeout + 30  # type: ignore[attr-defined]
    WorkerSettings.queue_name = settings.queue_name  # type: ignore[attr-defined]
    WorkerSettings.redis_settings = redis_settings(settings)  # type: ignore[attr-defined]
    return WorkerSettings


def main() -> None:  # pragma: no cover - process entry point
    """Run the worker: ``python -m webapp.tasks``."""
    from arq import run_worker

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_worker(_configure_worker_settings())  # type: ignore[arg-type]


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
