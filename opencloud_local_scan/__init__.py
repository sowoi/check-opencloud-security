"""
Local security scanner for OpenCloud instances.

OpenCloud offers no public scan API, so this package *is* the scanner: it
talks to an instance over plain HTTP(S), reads the endpoints that OpenCloud
exposes without authentication, probes for common misconfigurations and
produces a result document that the ``check_opencloud_security`` Nagios
plugin can evaluate.

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

from .config import Configuration, ConfigurationError, load_configuration
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

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_FEED_URL",
    "HARDENINGS",
    "RELEASE_MODES",
    "Advisory",
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
    "UpdateInfo",
    "VulnerabilityDatabase",
    "__version__",
    "build_server",
    "compare_versions",
    "derive_hardenings",
    "describe_hardening",
    "failed_extra_checks",
    "fetch_update_info",
    "is_actionable",
    "is_end_of_life",
    "is_legacy_version",
    "lifecycle_status",
    "load_configuration",
    "load_database",
    "load_latest_release",
    "load_release_schedule",
    "normalise_version",
    "parse_release_feed",
    "parse_version",
    "release_line",
    "release_settings_from_config",
    "scan",
    "scanner_settings_from_config",
    "select_version",
    "serve",
]
