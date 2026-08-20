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
DEFAULT_MAX_BATCH_TARGETS = 10
DEFAULT_MCP_MAX_CONCURRENT_WAITS = 8


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


def _read_encryption_keys() -> dict[int, str]:
    """Read encryption keys from COS_WEB_ENCRYPTION_KEY_<VERSION> env vars."""
    keys: dict[int, str] = {}
    for env_var, value in os.environ.items():
        if env_var.startswith("COS_WEB_ENCRYPTION_KEY_"):
            try:
                version_str = env_var[len("COS_WEB_ENCRYPTION_KEY_"):]
                version = int(version_str)
                key = value.strip()
                if key:
                    keys[version] = key
            except (ValueError, IndexError):
                continue
    return keys


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

    public_base_url: str | None = None
    """The origin this service is reached at, for the canonical links and the
    sitemap. Unset means the address of the request is used, which is right
    for a direct deployment and wrong behind a proxy: the service would
    otherwise publish URLs only the proxy can reach."""

    allow_indexing: bool = True
    """Let search engines index the landing page and the four explanations.
    Result pages are never indexable whatever this says. Turn it off for a
    deployment that should not be found at all: ``robots.txt`` becomes a flat
    refusal and every page carries ``noindex``."""

    releases_mode: str = "off"
    """Update check against the OpenCloud release feed. ``off`` by default so
    that a public deployment does not hammer the feed once per visitor."""

    releases_token: str | None = None

    enable_docs: bool = False
    """Serve the browsable API pages at ``/docs`` and ``/redoc``. Off by
    default because they are a convenience for an operator rather than part
    of the service. The machine-readable documents - ``/openapi.json``,
    ``/arazzo.json`` and ``/.well-known/ai.json`` - are always public: an
    agent that cannot read the contract has to guess at it."""

    enable_mcp: bool = True
    """Serve the MCP endpoint at ``/mcp``, so an agent can execute the same
    workflows the Arazzo document describes. Turns itself off when the ``mcp``
    extra is not installed, so a deployment without it still starts."""

    mcp_allowed_hosts: tuple[str, ...] = field(default_factory=tuple)
    """Host header values the MCP endpoint accepts, as DNS-rebinding
    protection. Empty means accept any, which is right behind a proxy that
    already decides which names reach this service and wrong for an MCP
    endpoint exposed straight to a browser."""

    mcp_max_concurrent_waits: int = DEFAULT_MCP_MAX_CONCURRENT_WAITS
    """How many MCP tool calls may sit waiting for a scan at once. A waiting
    call holds a connection and a task for as long as the scan takes, so a
    ceiling stops one agent pinning the process open. Reaching it refuses
    nothing: the scan is submitted and the uuid returned for the caller to
    poll, exactly as ``wait: false`` would have answered. ``0`` never waits
    in the tool call at all."""

    webhook_secret: str | None = None
    """Shared secret for signing webhook payloads. If set, webhook POSTs include
    an X-COS-Signature header. The receiver must verify the signature."""

    encrypt_results: bool = False
    """Encrypt sensitive scan results in Redis using AES-256-GCM. When enabled,
    only the result data is encrypted; metadata like UUIDs and timestamps remain
    in clear text for listing and TTL operations."""

    max_batch_targets: int = DEFAULT_MAX_BATCH_TARGETS
    """How many targets one ``POST /api/scans/batch`` may carry. A batch is a
    convenience, not a discount: every target in it is still counted against
    the client limit and still claims its own target cooldown."""

    audit_log: bool = False
    """Write an audit record for every scan request, rejection and triggered
    limit. Off by default: the ordinary log deliberately carries lifecycle
    markers and uuids only, and an operator has to choose to keep more."""

    audit_log_targets: bool = False
    """Record the target hostname in the clear instead of as a fingerprint.
    Reasonable for a deployment scanning its own estate, not for a public one:
    a log of targets is a log of who scanned what."""

    audit_salt: str | None = None
    """Salt for the audit fingerprints. Unset means a random one per process,
    so nothing correlates across a restart; setting one makes correlation
    possible and rotating it ends it. A salt that is set is a secret: the
    fingerprints in the log are only pseudonyms for as long as it is unknown,
    since the address space is small enough to hash exhaustively."""

    purge_token: str | None = None
    """Bearer token for ``DELETE /api/purge``. Unset means the endpoint does
    not exist at all: erasure walks the keyspace and deletes other people's
    results, so it belongs to the operator answering the request, not to
    whoever can type a hostname."""

    purge_signing_key: str | None = None
    """Signs the proof of deletion. Unset returns an unsigned receipt, which
    still states what was removed but cannot be checked by whoever holds it."""

    encryption_keys: dict[int, str] = field(default_factory=dict)
    """Encryption key mapping: version -> key (hex). Keys are read from
    COS_WEB_ENCRYPTION_KEY_<VERSION> env vars. New encryptions use the highest
    version; old versions still decrypt existing data."""

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
            public_base_url=_env("PUBLIC_BASE_URL"),
            allow_indexing=_env_bool("ALLOW_INDEXING", True),
            releases_mode=(_env("RELEASES_MODE") or "off").lower(),
            releases_token=_env("RELEASES_TOKEN"),
            enable_docs=_env_bool("ENABLE_DOCS", False),
            enable_mcp=_env_bool("ENABLE_MCP", True),
            mcp_allowed_hosts=_env_list("MCP_ALLOWED_HOSTS"),
            mcp_max_concurrent_waits=_env_int(
                "MCP_MAX_CONCURRENT_WAITS",
                DEFAULT_MCP_MAX_CONCURRENT_WAITS,
                minimum=0,
            ),
            webhook_secret=_env("WEBHOOK_SECRET"),
            encrypt_results=_env_bool("ENCRYPT_RESULTS", False),
            max_batch_targets=_env_int(
                "MAX_BATCH_TARGETS", DEFAULT_MAX_BATCH_TARGETS, minimum=1
            ),
            audit_log=_env_bool("AUDIT_LOG", False),
            audit_log_targets=_env_bool("AUDIT_LOG_TARGETS", False),
            audit_salt=_env("AUDIT_SALT"),
            purge_token=_env("PURGE_TOKEN"),
            purge_signing_key=_env("PURGE_SIGNING_KEY"),
            encryption_keys=_read_encryption_keys(),
        )
