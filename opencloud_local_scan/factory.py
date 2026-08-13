"""
Build scanner and release settings from the layered configuration.

Keeping this in one place means the plugin, the one-shot CLI and the
container service all understand exactly the same YAML keys, environment
variables and secret references.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Configuration
from .releases import (
    DEFAULT_FEED_URL,
    MODES,
    ReleaseSettings,
)
from .releases import (
    DEFAULT_TIMEOUT_SECONDS as DEFAULT_RELEASE_TIMEOUT_SECONDS,
)
from .scanner import (
    DEFAULT_CONCURRENCY,
    DEFAULT_DEBUG_PORT_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TLS_MIN_DAYS,
    USER_AGENT,
    ScannerSettings,
)
from .versions import RELEASE_TRACKS, ReleaseSchedule, load_release_schedule


def _int_tuple(config: Configuration, name: str) -> tuple[int, ...]:
    """Read a list of integers from a ';' or ',' separated configuration value."""
    entries = [
        part.strip()
        for item in config.get_list(name)
        for part in item.split(",")
        if part.strip().isdigit()
    ]
    return tuple(sorted({int(item) for item in entries}))


def _release_schedule(config: Configuration) -> ReleaseSchedule | None:
    """Load a replacement release schedule, if one is configured.

    Lets a site that mirrors the OpenCloud documentation - or one that tracks
    a vendor's own support commitments - point the end-of-life check at its
    own file instead of the bundled one.
    """
    path = config.get("SCANNER_RELEASE_SCHEDULE")
    if not path:
        return None
    return load_release_schedule(Path(path))


def _release_track(config: Configuration) -> str | None:
    """Read the release track the instance follows, if one is declared."""
    track = (config.get("SCANNER_RELEASE_TRACK") or "").strip().lower()
    return track if track in RELEASE_TRACKS else None


def _waivers(config: Configuration) -> tuple[str, ...]:
    """Read the hardening measures and checks that should not be reported."""
    entries = [
        part.strip()
        for item in config.get_list("SCANNER_IGNORE_HARDENINGS")
        for part in item.split(",")
        if part.strip()
    ]
    return tuple(dict.fromkeys(entries))


def scanner_settings_from_config(
    config: Configuration, **overrides: Any
) -> ScannerSettings:
    """
    Build :class:`ScannerSettings` from configuration file and environment.

    Keyword overrides (typically parsed command line flags) win over both;
    passing ``None`` means "not specified on the command line".
    """
    port = config.get("SCANNER_TARGET_PORT")
    settings = ScannerSettings(
        timeout=config.get_int(
            "SCANNER_TIMEOUT", config.get_int("TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        ),
        verify_tls=config.get_bool("SCANNER_VERIFY_TLS", True),
        proxy=config.get("SCANNER_PROXY") or config.get("PROXY"),
        scheme=config.get("SCANNER_SCHEME") or "https",
        port=int(port) if port else None,
        extra_checks=config.get_bool("SCANNER_EXTRA_CHECKS", True),
        extra_checks_affect_rating=config.get_bool("SCANNER_EXTRA_CHECKS_RATING", True),
        tls_min_days=config.get_int("SCANNER_TLS_MIN_DAYS", DEFAULT_TLS_MIN_DAYS),
        check_debug_ports=config.get_bool("SCANNER_CHECK_DEBUG_PORTS", True),
        debug_ports=_int_tuple(config, "SCANNER_DEBUG_PORTS"),
        debug_port_timeout=config.get_int(
            "SCANNER_DEBUG_PORT_TIMEOUT", DEFAULT_DEBUG_PORT_TIMEOUT_SECONDS
        ),
        concurrency=config.get_int("SCANNER_CONCURRENCY", DEFAULT_CONCURRENCY),
        use_release_schedule=config.get_bool("SCANNER_USE_RELEASE_SCHEDULE", True),
        release_schedule=_release_schedule(config),
        release_track=_release_track(config),
        ignore_hardenings=_waivers(config),
        vulnerability_files=tuple(config.get_list("SCANNER_VULNERABILITY_DB")),
        vulnerability_feed=config.get("SCANNER_VULNERABILITY_FEED"),
        include_bundled_db=config.get_bool("SCANNER_BUNDLED_DB", True),
        user_agent=config.get("SCANNER_USER_AGENT") or USER_AGENT,
    )

    changes = {key: value for key, value in overrides.items() if value is not None}
    if not changes:
        return settings
    return ScannerSettings(**{**settings.__dict__, **changes})


def release_settings_from_config(
    config: Configuration, **overrides: Any
) -> ReleaseSettings:
    """Build :class:`ReleaseSettings` from configuration and overrides."""
    mode = (config.get("RELEASES_MODE") or "auto").strip().lower()
    if mode not in MODES:
        mode = "auto"

    settings = ReleaseSettings(
        mode=mode,
        feed_url=config.get("RELEASES_FEED_URL") or DEFAULT_FEED_URL,
        latest_version=config.get("RELEASES_LATEST_VERSION"),
        token=config.get("RELEASES_TOKEN"),
        timeout=config.get_int(
            "RELEASES_TIMEOUT", config.get_int("TIMEOUT", DEFAULT_RELEASE_TIMEOUT_SECONDS)
        ),
        verify_tls=config.get_bool("RELEASES_VERIFY_TLS", True),
        proxy=config.get("RELEASES_PROXY") or config.get("PROXY"),
    )

    changes = {key: value for key, value in overrides.items() if value is not None}
    if not changes:
        return settings
    return ReleaseSettings(**{**settings.__dict__, **changes})
