"""
Local security scanner for OpenCloud instances.

This package *is* the built-in scanner: it talks to an instance over plain
HTTP(S), reads the endpoints that OpenCloud exposes without authentication,
probes for common misconfigurations and produces a result document that the
``check_opencloud_security`` Nagios plugin can evaluate.

The ratings follow the scale of the Nextcloud scan API, so that existing
thresholds, graphs and alert rules keep their meaning::

    {
      "host": "cloud.example.com",
      "rating": 5,
      "ratingLabel": "A+",
      "productname": "OpenCloud",
      "version": "7.2.0",
      "vulnerabilities": [...],
      "hardenings": {...},
      "setup": {"https": {...}, "headers": {...}},
      "checks": [...]
    }
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version
from pathlib import Path

from .baseline import (
    Baseline,
    BaselineError,
    Comparison,
    Snapshot,
    load_baseline,
    snapshot_of,
)
from .completion import enable as enable_completion
from .config import (
    DEFAULT_CONFIG_NAME,
    DEFAULT_CONFIG_PATHS,
    Configuration,
    ConfigurationError,
    load_config_file,
    load_configuration,
)
from .factory import release_settings_from_config, scanner_settings_from_config
from .hardening import HARDENINGS, Hardening, is_actionable
from .hardening import describe as describe_hardening
from .releases import (
    DEFAULT_FEED_URL,
    ReleaseSettings,
    UpdateInfo,
    fetch_update_info,
    parse_release_feed,
)
from .releases import (
    MODES as RELEASE_MODES,
)
from .scanner import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    Finding,
    RatingCap,
    RatingExplanation,
    ScanError,
    ScannerSettings,
    derive_hardenings,
    failed_extra_checks,
    scan,
)
from .secrets import SecretProvider, SecretResolutionError
from .selfupdate import (
    UpgradeError,
    UpgradePlan,
    latest_released_version,
    plan_upgrade,
    self_update_note,
    upgrade_self,
)
from .service import ScanStore, build_server, serve
from .versions import (
    LifecycleStatus,
    ReleaseLine,
    ReleaseSchedule,
    compare_versions,
    is_end_of_life,
    is_legacy_version,
    lifecycle_status,
    load_latest_release,
    load_release_schedule,
    normalise_version,
    parse_version,
    release_line,
    select_version,
)
from .vulndb import Advisory, VulnerabilityDatabase, load_database
from .wizard import SetupAborted
from .wizard import run as run_setup

DISTRIBUTION_NAME = "check-opencloud-security"


def _version_from_pyproject() -> str | None:
    """
    Read the version straight out of ``pyproject.toml``.

    Only reached when the package is not installed, i.e. when the plugin is run
    from a checkout. ``tomllib`` is 3.11+, so this stays a regex.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable checkout
            return None
        if not re.search(
            r'^name\s*=\s*["\']' + re.escape(DISTRIBUTION_NAME) + r'["\']',
            text,
            re.MULTILINE,
        ):
            # A pyproject.toml of some enclosing project, not ours.
            continue
        match = re.search(
            r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE
        )
        return match.group(1) if match else None
    return None


def _detect_version() -> str:
    """
    The single source of truth for the version is ``pyproject.toml``.

    A checkout wins over the installed metadata, because an editable install
    records the version it was installed at and would otherwise keep reporting
    it after the file has been edited. Keeping the number in one place is what
    stops the plugin, the library and the packaging from drifting apart.
    """
    from_source = _version_from_pyproject()
    if from_source:
        return from_source
    try:
        return _installed_version(DISTRIBUTION_NAME)
    except PackageNotFoundError:  # pragma: no cover - neither installed nor a checkout
        return "0.0.0"


__version__ = _detect_version()

__all__ = [
    "DEFAULT_CONCURRENCY",
    "DEFAULT_CONFIG_NAME",
    "DEFAULT_CONFIG_PATHS",
    "DEFAULT_FEED_URL",
    "HARDENINGS",
    "MAX_CONCURRENCY",
    "RELEASE_MODES",
    "Advisory",
    "Baseline",
    "BaselineError",
    "Comparison",
    "Configuration",
    "ConfigurationError",
    "Finding",
    "Hardening",
    "LifecycleStatus",
    "RatingCap",
    "RatingExplanation",
    "ReleaseLine",
    "ReleaseSchedule",
    "ReleaseSettings",
    "ScanError",
    "ScanStore",
    "ScannerSettings",
    "SecretProvider",
    "SecretResolutionError",
    "SetupAborted",
    "Snapshot",
    "UpdateInfo",
    "UpgradeError",
    "UpgradePlan",
    "VulnerabilityDatabase",
    "__version__",
    "build_server",
    "compare_versions",
    "derive_hardenings",
    "describe_hardening",
    "enable_completion",
    "failed_extra_checks",
    "fetch_update_info",
    "is_actionable",
    "is_end_of_life",
    "is_legacy_version",
    "latest_released_version",
    "lifecycle_status",
    "load_baseline",
    "load_config_file",
    "load_configuration",
    "load_database",
    "load_latest_release",
    "load_release_schedule",
    "normalise_version",
    "parse_release_feed",
    "parse_version",
    "plan_upgrade",
    "release_line",
    "release_settings_from_config",
    "run_setup",
    "scan",
    "scanner_settings_from_config",
    "select_version",
    "self_update_note",
    "serve",
    "snapshot_of",
    "upgrade_self",
]
