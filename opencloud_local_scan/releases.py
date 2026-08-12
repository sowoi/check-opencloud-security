"""
Update check for OpenCloud.

OpenCloud has no update API and no updater server, so the newest release is
determined from a **release feed** instead - by default the GitHub releases
API of ``opencloud-eu/opencloud``, which is also what the official install
script uses.

Three transports are available, selected with ``--update-source``:

``feed``
    ``GET <feed_url>`` and read the release tag. The GitHub releases API
    (a single object with ``tag_name``, or a list of them) and a plain
    ``{"version": "7.2.0"}`` document are both understood, so an air-gapped
    site can serve its own file.

``pinned``
    Compare against ``releases.latest_version`` from the configuration. No
    network access at all - the right choice when a configuration management
    system already knows which release should be deployed.

``bundled``
    Compare against the release recorded in the package's
    ``data/release_schedule.json``.

``auto`` (the default) uses ``pinned`` when a version is configured and
``feed`` otherwise. ``off`` disables the update check.

Whatever the transport, the recommended target is **track aware**. A release
feed only knows the newest release overall, and that is always a rolling one;
offering it to a production or LTS instance would quietly move it onto the
rolling track. For those instances the target therefore comes from the
release schedule, and the newest release overall is reported separately as
:attr:`UpdateInfo.newest_release`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from .versions import (
    TRACK_LTS,
    TRACK_PRODUCTION,
    LifecycleStatus,
    compare_versions,
    load_latest_release,
    newest,
    normalise_version,
    parse_version,
    release_line,
)

LOGGER = logging.getLogger("check_opencloud.releases")

# The same endpoint the official bare-metal install script reads.
DEFAULT_FEED_URL = "https://api.github.com/repos/opencloud-eu/opencloud/releases/latest"
DEFAULT_TIMEOUT_SECONDS = 10

MODES = ("auto", "feed", "pinned", "bundled", "off")


@dataclass
class UpdateInfo:
    """Update state of the scanned OpenCloud instance."""

    available: bool | None = None
    version: str | None = None
    available_version: str | None = None
    released_at: str | None = None
    source: str = "none"
    error: str | None = None
    track: str | None = None
    """The release track the recommended target belongs to, when known."""
    newest_release: str | None = None
    """The newest release overall, when it differs from the recommended one."""

    @property
    def known(self) -> bool:
        """True when the update state could actually be determined."""
        return self.available is not None

    def as_dict(self) -> dict[str, Any]:
        """Render the update state for JSON output."""
        return {
            "available": self.available,
            "version": self.version,
            "availableVersion": self.available_version,
            "releasedAt": self.released_at,
            "source": self.source,
            "error": self.error,
            "track": self.track,
            "newestRelease": self.newest_release,
        }

    def summary(self) -> str:
        """One-line, human readable rendering used in the plugin output."""
        if self.error and not self.known:
            return f"Update check via {self.source} failed: {self.error}"
        if not self.known:
            return "Update check not performed"
        installed = f", installed {self.version}" if self.version else ""
        track = f" on the {self.track} track" if self.track else ""
        if self.available:
            target = self.available_version or "unknown version"
            return (
                f"Update check ({self.source}{installed}): "
                f"update available{track}: {target}"
            )
        return f"Update check ({self.source}{installed}): up to date{track}"


@dataclass(frozen=True)
class ReleaseSettings:
    """Where to look up the newest published OpenCloud release."""

    mode: str = "auto"
    feed_url: str = DEFAULT_FEED_URL
    latest_version: str | None = None
    token: str | None = None
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    verify_tls: bool = True
    proxy: str | None = None

    @property
    def proxies(self) -> dict[str, str] | None:
        """requests-style proxy mapping."""
        return {"http": self.proxy, "https": self.proxy} if self.proxy else None

    def effective_mode(self) -> str:
        """
        Resolve 'auto' into the transport that is actually usable.

        A pinned version wins over the network, because an operator who
        states the expected release means it.
        """
        if self.mode != "auto":
            return self.mode
        if self.latest_version:
            return "pinned"
        if self.feed_url:
            return "feed"
        return "bundled"


def _tag_from_entry(entry: Any) -> tuple[str | None, str | None]:
    """Read (version, published date) from one release feed entry."""
    if not isinstance(entry, dict):
        return None, None
    if entry.get("draft") or entry.get("prerelease"):
        return None, None
    tag = entry.get("tag_name") or entry.get("name") or entry.get("version")
    version = normalise_version(tag if isinstance(tag, str) else None)
    if not version or not parse_version(version):
        return None, None
    published = entry.get("published_at") or entry.get("released_at") or entry.get("date")
    return version, str(published) if published else None


def parse_release_feed(document: Any) -> tuple[str | None, str | None]:
    """
    Extract the newest release from a feed document.

    Understands a single GitHub release object, a list of them, and a plain
    ``{"version": "7.2.0"}`` document served by a local mirror.
    """
    if isinstance(document, dict) and "releases" in document:
        document = document["releases"]

    if isinstance(document, list):
        candidates = [_tag_from_entry(entry) for entry in document]
        versions = {version: date for version, date in candidates if version}
        best = newest(versions)
        return best, versions.get(best) if best else None

    return _tag_from_entry(document)


def _fetch_via_feed(settings: ReleaseSettings, installed: str | None) -> UpdateInfo:
    """Ask the release feed for the newest published release."""
    if not settings.feed_url:
        return UpdateInfo(source="feed", version=installed, error="No release feed configured.")

    headers = {"Accept": "application/json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.token:
        # An unauthenticated GitHub API is rate limited per IP; a token
        # raises that limit for monitoring hosts checking many instances.
        headers["Authorization"] = "Bearer " + settings.token

    LOGGER.debug("Querying release feed %s", settings.feed_url)
    try:
        response = requests.get(
            settings.feed_url,
            headers=headers,
            timeout=settings.timeout,
            verify=settings.verify_tls,
            proxies=settings.proxies,
        )
        response.raise_for_status()
        document = response.json()
    except (requests.exceptions.RequestException, ValueError) as exc:
        return UpdateInfo(source="feed", version=installed, error=str(exc))

    latest, released_at = parse_release_feed(document)
    if not latest:
        return UpdateInfo(
            source="feed",
            version=installed,
            error="Release feed did not contain a usable version.",
        )
    return _compare(installed, latest, source="feed", released_at=released_at)


def _compare(
    installed: str | None, latest: str | None, *, source: str, released_at: str | None = None
) -> UpdateInfo:
    """Build the UpdateInfo for a known newest release."""
    latest = normalise_version(latest)
    if not latest:
        return UpdateInfo(source=source, version=installed, error="No release version available.")
    if not parse_version(installed):
        return UpdateInfo(
            source=source,
            version=installed,
            available_version=latest,
            released_at=released_at,
            error="The instance did not report a usable version.",
        )
    return UpdateInfo(
        available=compare_versions(installed, latest) < 0,
        version=installed,
        available_version=latest,
        released_at=released_at,
        source=source,
    )


def _retarget_to_track(
    info: UpdateInfo, lifecycle: LifecycleStatus, installed_version: str | None
) -> UpdateInfo:
    """Keep a production or LTS instance on its own release track.

    A release feed only reports the newest release overall, which is a rolling
    one, so recommending it would move the instance onto the rolling track.
    The release schedule knows the newest release of the instance's own track,
    and that is what gets recommended - unless the feed happens to report a
    newer patch of the very same line, in which case the feed is fresher.
    """
    installed_line = release_line(installed_version)
    feed_target = info.available_version
    candidates = [lifecycle.upgrade_to]
    if feed_target and release_line(feed_target) == installed_line:
        candidates.append(feed_target)

    target = newest([candidate for candidate in candidates if candidate])
    if target == feed_target:
        info.track = lifecycle.release_type
        return info

    info.newest_release = feed_target
    info.available_version = target
    info.released_at = None
    info.track = lifecycle.release_type
    info.available = bool(target) and compare_versions(installed_version, target) < 0
    return info


def fetch_update_info(
    settings: ReleaseSettings | None,
    installed_version: str | None = None,
    lifecycle: LifecycleStatus | None = None,
) -> UpdateInfo:
    """
    Determine whether a newer OpenCloud release than the installed one exists.

    When ``lifecycle`` places the instance on the production or LTS track, the
    recommended release is taken from the release schedule instead of the
    feed, so that the instance is not pushed onto the rolling track.

    Never raises: transport problems are reported through
    :attr:`UpdateInfo.error` so that a monitoring run still produces a result
    for the security part of the check.
    """
    info = _resolve_update_info(settings, installed_version)
    if lifecycle is None or info.source == "disabled":
        # An operator who turned the update check off must not be told about
        # updates through the back door of the release schedule.
        return info
    if lifecycle.release_type in (TRACK_PRODUCTION, TRACK_LTS):
        return _retarget_to_track(info, lifecycle, installed_version)
    if info.known:
        info.track = lifecycle.release_type
    return info


def _resolve_update_info(
    settings: ReleaseSettings | None, installed_version: str | None
) -> UpdateInfo:
    """Ask the configured transport for the newest release."""
    if settings is None:
        return UpdateInfo(source="disabled", version=installed_version)

    mode = settings.effective_mode()
    if mode == "off":
        return UpdateInfo(source="disabled", version=installed_version)

    if mode == "pinned":
        return _compare(installed_version, settings.latest_version, source="pinned")

    if mode == "bundled":
        return _compare(installed_version, load_latest_release(), source="bundled release data")

    info = _fetch_via_feed(settings, installed_version)
    if info.known or settings.mode != "auto":
        return info

    # The feed was unreachable; the release shipped with the package is a
    # stale but offline answer, which beats reporting nothing at all.
    fallback = _compare(installed_version, load_latest_release(), source="bundled release data")
    if fallback.known:
        fallback.error = info.error
        return fallback
    return info
