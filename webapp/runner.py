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

from .catalog import DEFAULT_RELEASE_TRACK, sanitize_release_track
from .settings import WebSettings
from .ssrf import Target, redirect_guard, revalidate

LOGGER = logging.getLogger("check_opencloud.web.runner")


def scanner_settings_for(
    target: Target,
    ignore_hardenings: tuple[str, ...],
    settings: WebSettings,
    release_track: str = DEFAULT_RELEASE_TRACK,
) -> ScannerSettings:
    """Build the frozen scanner settings for one web-submitted scan."""
    return ScannerSettings(
        release_track=sanitize_release_track(release_track),
        timeout=settings.scan_timeout,
        verify_tls=settings.verify_tls,
        scheme=target.scheme,
        port=target.port,
        extra_checks=True,
        extra_checks_affect_rating=True,
        check_debug_ports=settings.check_debug_ports,
        concurrency=settings.scan_concurrency,
        ignore_hardenings=ignore_hardenings,
        redirect_guard=redirect_guard(
            allow_private=settings.allow_private_targets,
            allowed_hosts=settings.extra_hosts_allowed,
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
) -> dict[str, Any]:
    """
    Re-check the target, then run the scan and return the result document.

    The second validation is not belt and braces: between accepting the
    request and running the job, the answer to the DNS query may have changed
    to a private address. Resolving again here is what makes that window a
    single lookup wide.
    """
    checked = revalidate(
        target,
        allow_private=settings.allow_private_targets,
        allowed_hosts=settings.extra_hosts_allowed,
    )
    return scan(
        checked.scan_host,
        settings=scanner_settings_for(
            checked, ignore_hardenings, settings, release_track
        ),
        release_settings=release_settings_for(settings),
    )
