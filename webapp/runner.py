"""
Where a queued scan actually becomes a scan.

The whole of the request's influence is four values: the host, the waivers,
the release track the instance follows and - only for how the answer is
rendered - the output format. Everything that
decides how hard the instance is hit comes from :class:`WebSettings`, which
comes from the environment. This function is the seam where that is enforced,
so there is one place to read when the question is "can a visitor make this
service noisier?".
"""

from __future__ import annotations

import logging
from typing import Any

from opencloud_local_scan import ReleaseSettings, ScannerSettings, scan
from opencloud_local_scan.versions import ReleaseSchedule
from opencloud_local_scan.vulndb import VulnerabilityDatabase

from .catalog import DEFAULT_RELEASE_TRACK, sanitize_release_track
from .settings import WebSettings
from .ssrf import Target, redirect_guard, redirect_pinner, revalidate

LOGGER = logging.getLogger("check_opencloud.web.runner")


def scanner_settings_for(
    target: Target,
    ignore_hardenings: tuple[str, ...],
    settings: WebSettings,
    release_track: str = DEFAULT_RELEASE_TRACK,
    release_schedule: ReleaseSchedule | None = None,
    blocked_targets: tuple[str, ...] | None = None,
) -> ScannerSettings:
    """Build the frozen scanner settings for one web-submitted scan.

    ``release_schedule`` is the possibly refreshed lifecycle schedule the
    worker read from Redis; ``None`` means the scanner falls back to the one
    bundled in the wheel, which is what a deployment with the daily refresh
    switched off does on every scan.

    ``blocked_targets`` is the effective exclusion list - the environment's
    and the operator area's together - as it stood when this job started.
    ``None`` means the environment's alone, which is what a caller outside
    the worker has.
    """
    exclusions = (
        settings.blocked_targets if blocked_targets is None else blocked_targets
    )
    return ScannerSettings(
        release_track=sanitize_release_track(release_track),
        release_schedule=release_schedule,
        timeout=settings.scan_timeout,
        verify_tls=settings.verify_tls,
        scheme=target.scheme,
        port=target.port,
        extra_checks=True,
        extra_checks_affect_rating=True,
        ipv6_enabled=settings.ipv6_enabled,
        check_debug_ports=settings.check_debug_ports,
        # Never every resolved address: a stranger's submission would buy a
        # dozen requests and a demo sign-in per node of somebody else's pool
        # (ADR 0042). Spelled out so no default can change it.
        check_all_addresses=False,
        concurrency=settings.scan_concurrency,
        ignore_hardenings=ignore_hardenings,
        redirect_guard=redirect_guard(
            allow_private=settings.allow_private_targets,
            allowed_hosts=settings.extra_hosts_allowed,
            blocked_targets=exclusions,
        ),
        pinned_addresses=((target.hostname, target.addresses),),
        redirect_pinner=redirect_pinner(
            allow_private=settings.allow_private_targets,
            allowed_hosts=settings.extra_hosts_allowed,
            blocked_targets=exclusions,
        ),
    )


def release_settings_for(settings: WebSettings) -> ReleaseSettings:
    """Update-check settings; ``off`` keeps a public deployment off the feed."""
    return ReleaseSettings(
        mode=settings.releases_mode,
        token=settings.releases_token,
        timeout=settings.scan_timeout,
        verify_tls=True,
    )


def execute_scan(
    target: Target,
    ignore_hardenings: tuple[str, ...],
    settings: WebSettings,
    release_track: str = DEFAULT_RELEASE_TRACK,
    release_schedule: ReleaseSchedule | None = None,
    database: VulnerabilityDatabase | None = None,
    blocked_targets: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """
    Re-check the target, then run the scan and return the result document.

    The second validation is not belt and braces: between accepting the
    request and running the job, the answer to the DNS query may have changed
    to a private address. Resolving again here is what makes that window a
    single lookup wide.

    ``blocked_targets`` is read by the caller from Redis when the job starts,
    so an exclusion added while this job waited in the queue is honoured here
    - which is the whole of what "immediately" means for a scan that was
    accepted before anybody typed it.
    """
    exclusions = (
        settings.blocked_targets if blocked_targets is None else blocked_targets
    )
    checked = revalidate(
        target,
        allow_private=settings.allow_private_targets,
        allowed_hosts=settings.extra_hosts_allowed,
        blocked_targets=exclusions,
    )
    return scan(
        checked.scan_host,
        settings=scanner_settings_for(
            checked,
            ignore_hardenings,
            settings,
            release_track,
            release_schedule,
            exclusions,
        ),
        release_settings=release_settings_for(settings),
        # The advisory database the daily refresh last accepted; ``None``
        # falls back to the one bundled in the wheel, exactly as the plugin
        # does on a monitoring host.
        database=database,
    )
