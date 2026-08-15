"""
Server-side configuration of the web application.

Everything here is read from the environment at startup. That is the point:
the browser gets to choose *what* to scan, never *how hard*. Concurrency,
timeouts, worker counts and TTLs are operator territory and are deliberately
unreachable from any request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

ENV_PREFIX = "COS_WEB_"

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_RESULT_TTL_SECONDS = 3600
DEFAULT_MAX_WORKERS = 5
DEFAULT_SCAN_CONCURRENCY = 4
DEFAULT_SCAN_TIMEOUT_SECONDS = 15
DEFAULT_JOB_TIMEOUT_SECONDS = 180
DEFAULT_IP_RATE_LIMIT = 10
DEFAULT_IP_RATE_WINDOW_SECONDS = 60
DEFAULT_TARGET_COOLDOWN_SECONDS = 300


def _env(name: str) -> str | None:
    value = os.environ.get(f"{ENV_PREFIX}{name}")
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> tuple[str, ...]:
    raw = _env(name)
    if raw is None:
        return ()
    parts = [item.strip() for item in raw.replace(",", ";").split(";")]
    return tuple(part for part in parts if part)


@dataclass(frozen=True)
class WebSettings:
    """Everything the web application and its worker need to run."""

    redis_url: str = DEFAULT_REDIS_URL
    """Where ephemeral state lives. ``memory://`` runs without a Redis server."""

    result_ttl: int = DEFAULT_RESULT_TTL_SECONDS
    """How long a finished scan stays readable before Redis expires it."""

    max_workers: int = DEFAULT_MAX_WORKERS
    """How many scans the worker pool runs at once. Never client-configurable."""

    scan_concurrency: int = DEFAULT_SCAN_CONCURRENCY
    """Probes in flight within one scan. Never client-configurable."""

    scan_timeout: int = DEFAULT_SCAN_TIMEOUT_SECONDS
    job_timeout: int = DEFAULT_JOB_TIMEOUT_SECONDS

    verify_tls: bool = True
    """OpenCloud ships a self-signed certificate; the scanner degrades to a
    finding rather than a failure, so this stays on."""

    allow_private_targets: bool = False
    """Only ever true for a private deployment scanning its own network."""

    check_debug_ports: bool = False
    """Off by default. Connecting to extra ports on a host somebody else
    submitted is a port scan, and a public service should not run one
    uninvited. A private deployment scanning its own estate can turn it on."""

    extra_hosts_allowed: tuple[str, ...] = field(default_factory=tuple)
    """Hostnames exempted from the SSRF guard, for on-premise deployments."""

    ip_rate_limit: int = DEFAULT_IP_RATE_LIMIT
    ip_rate_window: int = DEFAULT_IP_RATE_WINDOW_SECONDS
    target_cooldown: int = DEFAULT_TARGET_COOLDOWN_SECONDS

    trust_forwarded_for: bool = False
    """Read the client address from ``X-Forwarded-For``. Only behind a proxy
    that overwrites the header, otherwise the rate limit is trivially evaded."""

    releases_mode: str = "off"
    """Update check against the OpenCloud release feed. ``off`` by default so
    that a public deployment does not hammer the feed once per visitor."""

    releases_token: str | None = None

    enable_docs: bool = False
    """Serve the OpenAPI schema and Swagger UI at ``/openapi.json``, ``/docs``
    and ``/redoc``. Off by default: a public deployment has three endpoints
    and a page describing them, and Swagger UI is the one part of this service
    that loads a script from somebody else's server."""

    @property
    def queue_name(self) -> str:
        """The ARQ queue the API and the worker agree on."""
        return "cos:web:scans"

    @classmethod
    def from_env(cls) -> WebSettings:
        """Build the settings from ``COS_WEB_*`` environment variables."""
        return cls(
            redis_url=_env("REDIS_URL") or DEFAULT_REDIS_URL,
            result_ttl=_env_int("RESULT_TTL", DEFAULT_RESULT_TTL_SECONDS, minimum=30),
            max_workers=_env_int("MAX_WORKERS", DEFAULT_MAX_WORKERS, minimum=1),
            scan_concurrency=_env_int(
                "SCAN_CONCURRENCY", DEFAULT_SCAN_CONCURRENCY, minimum=1
            ),
            scan_timeout=_env_int("SCAN_TIMEOUT", DEFAULT_SCAN_TIMEOUT_SECONDS, minimum=1),
            job_timeout=_env_int("JOB_TIMEOUT", DEFAULT_JOB_TIMEOUT_SECONDS, minimum=10),
            verify_tls=_env_bool("VERIFY_TLS", True),
            allow_private_targets=_env_bool("ALLOW_PRIVATE_TARGETS", False),
            check_debug_ports=_env_bool("CHECK_DEBUG_PORTS", False),
            extra_hosts_allowed=_env_list("ALLOWED_HOSTS"),
            ip_rate_limit=_env_int("IP_RATE_LIMIT", DEFAULT_IP_RATE_LIMIT),
            ip_rate_window=_env_int(
                "IP_RATE_WINDOW", DEFAULT_IP_RATE_WINDOW_SECONDS, minimum=1
            ),
            target_cooldown=_env_int("TARGET_COOLDOWN", DEFAULT_TARGET_COOLDOWN_SECONDS),
            trust_forwarded_for=_env_bool("TRUST_FORWARDED_FOR", False),
            releases_mode=(_env("RELEASES_MODE") or "off").lower(),
            releases_token=_env("RELEASES_TOKEN"),
            enable_docs=_env_bool("ENABLE_DOCS", False),
        )
