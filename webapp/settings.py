"""
Server-side configuration of the web application.

Everything here is read from the environment at startup. That is the point:
the browser gets to choose *what* to scan, never *how hard*. Concurrency,
timeouts, worker counts and TTLs are operator territory and are deliberately
unreachable from any request.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from opencloud_local_scan.advisory_source import OSV_QUERY_URL
from opencloud_local_scan.schedule_source import LIFECYCLE_URL

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
# One reverse proxy, which is what a deployment that turns
# COS_WEB_TRUST_FORWARDED_FOR on almost always has.
DEFAULT_TRUSTED_PROXY_HOPS = 1
DEFAULT_MCP_MAX_CONCURRENT_WAITS = 8
# An audit trail written to a file outlives the container, which is the point
# of it and also the risk: a log nobody rotates fills the volume it sits on and
# takes the service down with it. Ten megabytes and five generations is about
# a week of a busy public deployment and bounded at 60 MB whatever happens.
DEFAULT_AUDIT_LOG_MAX_BYTES = 10_000_000
DEFAULT_AUDIT_LOG_BACKUPS = 5

#: How many audit records the admin area keeps in memory to show a deployment
#: that logs to stdout, where there is no file to read back. Bounded on
#: purpose: this is a window onto the log, not a second copy of it.
DEFAULT_ADMIN_AUDIT_BUFFER = 200

#: The shortest gap between two operator-triggered refreshes of the same
#: reference data. The daily refresh asks upstream once; a button that can be
#: pressed in a loop must not turn one deployment into a source of load on
#: somebody else's documentation site.
DEFAULT_ADMIN_REFRESH_COOLDOWN_SECONDS = 60

#: The header the authentik outpost puts the signed-in username in. Fixed
#: rather than configurable: an operator who could name it could be talked
#: into naming one an ordinary client can send.
ADMIN_USER_HEADER = "x-authentik-username"
ADMIN_EMAIL_HEADER = "x-authentik-email"
ADMIN_GROUPS_HEADER = "x-authentik-groups"

#: The header carrying the secret only the outpost knows.
ADMIN_PROXY_HEADER = "x-cos-admin-proxy"

#: Below this the shared secret is not worth comparing.
ADMIN_PROXY_SECRET_MINIMUM = 32
# Who rotates the audit file: this process, by size, or something on the host
# that moves it aside and expects the writer to notice. The names are the
# accepted values of COS_WEB_AUDIT_LOG_ROTATION.
AUDIT_ROTATION_SERVICE = "service"
AUDIT_ROTATION_EXTERNAL = "external"
AUDIT_ROTATIONS = (AUDIT_ROTATION_SERVICE, AUDIT_ROTATION_EXTERNAL)
_META_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9:._-]{0,63}$")
_RESERVED_META_NAMES = frozenset(
    {
        "description",
        "robots",
        "referrer",
        "viewport",
        "theme-color",
        "google-site-verification",
    }
)


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
class IndexMetaTag:
    """One operator-supplied, inert ``name``/``content`` tag."""

    name: str
    content: str


def _env_index_meta_tags() -> tuple[IndexMetaTag, ...]:
    """Read a semicolon-separated ``name=content`` list without raw markup."""
    raw = _env("INDEX_META_TAG")
    if raw is None:
        return ()
    tags: list[IndexMetaTag] = []
    names: set[str] = set()
    for item in raw.split(";"):
        name, separator, content = item.partition("=")
        name = name.strip()
        content = content.strip()
        lowered = name.lower()
        if (
            not separator
            or not _META_NAME.fullmatch(name)
            or not content
            or len(content) > 512
            or lowered in names
            or lowered in _RESERVED_META_NAMES
            or lowered.startswith(("twitter:", "fb:"))
        ):
            raise ValueError(
                "COS_WEB_INDEX_META_TAG must be up to 10 semicolon-separated "
                "name=content pairs with unique non-reserved names and content "
                "no longer than 512 characters"
            )
        names.add(lowered)
        tags.append(IndexMetaTag(name=name, content=content))
    if not tags or len(tags) > 10:
        raise ValueError(
            "COS_WEB_INDEX_META_TAG must contain between 1 and 10 name=content pairs"
        )
    return tuple(tags)


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

    ipv6_enabled: bool = False
    """Whether this deployment's containers have outbound IPv6 connectivity.
    Off by default: Docker's default bridge network has no IPv6 route unless
    the host and this stack were both set up for it, which most installs are
    not. Left off, the IPv4/IPv6 TLS-parity check is skipped and the result
    notes why instead of reporting a target's IPv6 side as unreachable for a
    limitation of this deployment rather than of the target."""

    extra_hosts_allowed: tuple[str, ...] = field(default_factory=tuple)
    """Hostnames exempted from the SSRF guard, for on-premise deployments."""

    ip_rate_limit: int = DEFAULT_IP_RATE_LIMIT
    ip_rate_window: int = DEFAULT_IP_RATE_WINDOW_SECONDS
    target_cooldown: int = DEFAULT_TARGET_COOLDOWN_SECONDS

    trust_forwarded_for: bool = False
    """Read the client address from ``X-Forwarded-For``. Only behind a proxy
    that appends to or overwrites the header, and only with
    ``trusted_proxy_hops`` set to match how many of them there are."""

    trusted_proxy_hops: int = DEFAULT_TRUSTED_PROXY_HOPS
    """How many proxies of this deployment's own sit in front of the service.

    ``X-Forwarded-For`` is read from the *right*, because that is the end
    only a proxy writes. nginx's ``proxy_add_x_forwarded_for``, Traefik and
    most content delivery networks append, so the leftmost entry is whatever
    the client sent - reading it would let any caller mint a fresh rate-limit
    bucket, a fresh audit identity and a fresh allowance of purge attempts per
    request, by adding one header.

    ``1`` is right for the ordinary case of a single reverse proxy. Two
    proxies - a CDN in front of an ingress - is ``2``.

    Counting too few is safe: it reports the address of a proxy further out,
    which is written by a proxy either way. **Counting more than there are is
    not**, and nothing here can make it safe. With this set to ``2`` behind a
    single proxy, a request carrying ``X-Forwarded-For: spoofed`` arrives as
    ``spoofed, <real>`` and the second entry from the right is the one the
    client wrote. The count is clamped to the number of entries the header
    carries, but that only stops a read past the end - it cannot tell an entry
    a proxy appended from one a client sent, because nothing in the header
    says which is which. Set this to the number of proxies you operate, and
    only for proxies that overwrite or append the header themselves."""

    rate_limit_salt: str | None = None
    """Salt for the rate-limit and cooldown fingerprints. Unset means a random
    one per process, which is correct for a deployment running a single web
    process and silently wrong for one running several: each derives a
    different Redis key for the same address, so a client gets one allowance
    per process and the limit stops being one. Set the same value everywhere
    to make them count together. Like ``audit_salt`` it is a secret - the
    address space is small enough to hash exhaustively - and rotating it
    resets every counter rather than corrupting one."""

    public_base_url: str | None = None
    """The origin this service is reached at, for the canonical links and the
    sitemap. Unset means the address of the request is used, which is right
    for a direct deployment and wrong behind a proxy: the service would
    otherwise publish URLs only the proxy can reach."""

    index_meta_tags: tuple[IndexMetaTag, ...] = field(default_factory=tuple)
    """Optional custom ``<meta name=... content=...>`` elements on the
    landing page. They are parsed from a bounded ``;``-separated
    ``name=content`` list rather than raw HTML, so operator configuration
    cannot add scripts, redirects, or attributes that weaken the page."""

    allow_indexing: bool = True
    """Let search engines index the landing page and the four explanations.
    Result pages are never indexable whatever this says. Turn it off for a
    deployment that should not be found at all: ``robots.txt`` becomes a flat
    refusal and every page carries ``noindex``."""

    releases_mode: str = "off"
    """Update check against the OpenCloud release feed. ``off`` by default so
    that a public deployment does not hammer the feed once per visitor."""

    releases_token: str | None = None

    schedule_refresh: bool = True
    """Re-read the OpenCloud release lifecycle page once a day and rate scans
    against what it says. On by default: this is one request a day for the
    whole deployment, and without it a long-running service keeps rating
    instances against the schedule that happened to ship in its image. Turn
    it off for a deployment with no outbound access, which then uses the
    bundled schedule exactly as before."""

    schedule_refresh_url: str = LIFECYCLE_URL
    """Where that schedule is read from. Operator configuration, so it may
    point at a mirror of the documentation; it is never a request field."""

    schedule_refresh_hour: int = 4
    """The hour (UTC) of the daily read. Off-peak by default, and worth
    varying between deployments so they do not all arrive at once."""

    advisory_refresh: bool = True
    """Ask OSV once a day which advisories affect OpenCloud, and rate scans
    against the answer. On by default for the same reason the check exists at
    all: an advisory published the day after this image was built would
    otherwise reach nobody running it, and the visitor would be told their
    instance is fine. A refresh never removes an advisory and never believes
    an unbounded one."""

    advisory_refresh_url: str = OSV_QUERY_URL
    """Where the advisories are read from. Operator configuration, so it may
    point at a mirror of the feed; it is never a request field."""

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

    mcp_auth_enabled: bool = False
    """Require an OpenID Connect access token on ``/mcp``. Off by default: a
    public scan service is public, and an account would only make an agent
    identifiable without making anybody safer. On, this service becomes an
    OAuth resource server - it verifies a token an identity provider such as
    authentik issued, and never issues, stores or sees a credential itself.
    A deployment that turns it on without an issuer refuses to start rather
    than serve an endpoint its operator believes is protected."""

    mcp_auth_issuer: str | None = None
    """The identity provider that issues those tokens, exactly as the ``iss``
    claim spells it. For authentik that is
    ``https://authentik.example.com/application/o/<application-slug>/``."""

    mcp_auth_jwks_url: str | None = None
    """Where the provider publishes its signing keys. Unset derives
    ``<issuer>/jwks/``, which is what authentik and most others serve; a
    provider that puts them elsewhere is named here rather than unsupported."""

    mcp_auth_audience: str | None = None
    """The ``aud`` claim a token must carry, normally the client ID the agent
    authenticated as. Required whenever the sign-in is on: a token whose
    audience is never compared is one the provider minted for somebody
    else's application, and startup refuses rather than accept it."""

    mcp_auth_scopes: tuple[str, ...] = field(default_factory=tuple)
    """Scopes a token must carry as well as being valid. Empty means any
    authenticated caller may use the endpoint."""

    mcp_auth_resource_url: str | None = None
    """The URL agents reach ``/mcp`` at, used as the OAuth resource
    identifier and as the base of the RFC 9728 metadata. Unset derives it
    from ``COS_WEB_PUBLIC_BASE_URL``, which behind a proxy is the only place
    this service can learn its own address from."""

    admin_enabled: bool = False
    """Serve the operator's area at ``/admin``. Off by default, and off is a
    real absence: with this unset the routes are never registered, so the
    path answers the same 404 any other unknown one does rather than a 401
    that tells a stranger the area exists.

    It is never authenticated by this service. An authentik proxy provider
    terminates the sign-in in front of it and forwards the identity it
    established; this service checks that the request really came through
    that outpost and that the person it names is one of
    ``COS_WEB_ADMIN_USERS``. A deployment that turns the area on without the
    shared secret refuses to start, because the alternative is an
    unauthenticated console."""

    admin_proxy_secret: str | None = None
    """The secret the authentik outpost sends with every forwarded request,
    and the only reason to believe an identity header at all. Without it the
    headers naming the signed-in operator are just headers, and anybody who
    can reach the container could set them. Required whenever the admin area
    is on, at least ``ADMIN_PROXY_SECRET_MINIMUM`` characters, and compared
    in constant time."""

    admin_users: tuple[str, ...] = field(default_factory=tuple)
    """Who may use the area, by the username authentik signs them in as.
    Empty with the area enabled is refused at startup: a list nobody is on is
    almost always a configuration that was meant to name somebody, and
    reading it as "everybody authentik authenticated" would hand the console
    to every account in the directory."""

    admin_audit_buffer: int = DEFAULT_ADMIN_AUDIT_BUFFER
    """How many recent audit records to keep in memory for the live view.
    ``0`` keeps none, and the view then works only where
    ``COS_WEB_AUDIT_LOG_FILE`` gave it a file to read."""

    admin_refresh_cooldown: int = DEFAULT_ADMIN_REFRESH_COOLDOWN_SECONDS
    """The shortest gap between two operator-triggered refreshes of the same
    reference data, so a button cannot be held down against somebody else's
    server."""

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

    audit_log_file: str | None = None
    """Write the audit records to this file instead of the process output.
    Unset means they go where every other log line goes, which a container
    keeps only for as long as the container lives - an audit trail that a
    ``docker compose down`` erases is not one. A path here is expected to be
    on a mount that outlives the container; the process refuses to start when
    it cannot write there, because an audit trail that silently goes nowhere
    is worse than one nobody asked for."""

    audit_log_max_bytes: int = DEFAULT_AUDIT_LOG_MAX_BYTES
    """Size at which the audit file is rotated. ``0`` never rotates, which
    only makes sense when something outside this service does."""

    audit_log_backups: int = DEFAULT_AUDIT_LOG_BACKUPS
    """Rotated generations kept beside the audit file. With the size above
    this is the whole of what the trail may ever occupy on disk."""

    audit_log_rotation: str = AUDIT_ROTATION_SERVICE
    """Who rotates that file. ``service`` is this process, by size, and needs
    nothing installed on the host. ``external`` hands the job to whatever the
    host already runs - logrotate, normally - and this process only notices
    that the file it holds was moved out from under it and reopens the new
    one. Two rotators on one file is how a trail loses records, so this is a
    choice rather than a fallback, and an unrecognised value refuses to
    start."""

    purge_token: str | None = None
    """Bearer token for ``DELETE /api/purge``. Unset means the endpoint does
    not exist at all: erasure walks the keyspace and deletes other people's
    results, so it belongs to the operator answering the request, not to
    whoever can type a hostname."""

    purge_signing_key: str | None = None
    """Signs the proof of deletion. Unset returns an unsigned receipt, which
    still states what was removed but cannot be checked by whoever holds it."""

    export_signing_key: str | None = None
    """Signs exported result bytes for CI and archival verification."""

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
            ipv6_enabled=_env_bool("IPV6_ENABLED", False),
            extra_hosts_allowed=_env_list("ALLOWED_HOSTS"),
            ip_rate_limit=_env_int("IP_RATE_LIMIT", DEFAULT_IP_RATE_LIMIT),
            ip_rate_window=_env_int(
                "IP_RATE_WINDOW", DEFAULT_IP_RATE_WINDOW_SECONDS, minimum=1
            ),
            target_cooldown=_env_int("TARGET_COOLDOWN", DEFAULT_TARGET_COOLDOWN_SECONDS),
            trust_forwarded_for=_env_bool("TRUST_FORWARDED_FOR", False),
            trusted_proxy_hops=_env_int(
                "TRUSTED_PROXY_HOPS", DEFAULT_TRUSTED_PROXY_HOPS, minimum=1
            ),
            rate_limit_salt=_env("RATE_LIMIT_SALT"),
            public_base_url=_env("PUBLIC_BASE_URL"),
            index_meta_tags=_env_index_meta_tags(),
            allow_indexing=_env_bool("ALLOW_INDEXING", True),
            releases_mode=(_env("RELEASES_MODE") or "off").lower(),
            releases_token=_env("RELEASES_TOKEN"),
            schedule_refresh=_env_bool("SCHEDULE_REFRESH", True),
            schedule_refresh_url=_env("SCHEDULE_REFRESH_URL") or LIFECYCLE_URL,
            schedule_refresh_hour=min(
                23, _env_int("SCHEDULE_REFRESH_HOUR", 4, minimum=0)
            ),
            advisory_refresh=_env_bool("ADVISORY_REFRESH", True),
            advisory_refresh_url=_env("ADVISORY_REFRESH_URL") or OSV_QUERY_URL,
            enable_docs=_env_bool("ENABLE_DOCS", False),
            enable_mcp=_env_bool("ENABLE_MCP", True),
            mcp_allowed_hosts=_env_list("MCP_ALLOWED_HOSTS"),
            mcp_max_concurrent_waits=_env_int(
                "MCP_MAX_CONCURRENT_WAITS",
                DEFAULT_MCP_MAX_CONCURRENT_WAITS,
                minimum=0,
            ),
            mcp_auth_enabled=_env_bool("MCP_AUTH_ENABLED", False),
            mcp_auth_issuer=_env("MCP_AUTH_ISSUER"),
            mcp_auth_jwks_url=_env("MCP_AUTH_JWKS_URL"),
            mcp_auth_audience=_env("MCP_AUTH_AUDIENCE"),
            mcp_auth_scopes=_env_list("MCP_AUTH_SCOPES"),
            mcp_auth_resource_url=_env("MCP_AUTH_RESOURCE_URL"),
            admin_enabled=_env_bool("ADMIN_ENABLED", False),
            admin_proxy_secret=_env("ADMIN_PROXY_SECRET"),
            admin_users=_env_list("ADMIN_USERS"),
            admin_audit_buffer=_env_int(
                "ADMIN_AUDIT_BUFFER", DEFAULT_ADMIN_AUDIT_BUFFER, minimum=0
            ),
            admin_refresh_cooldown=_env_int(
                "ADMIN_REFRESH_COOLDOWN",
                DEFAULT_ADMIN_REFRESH_COOLDOWN_SECONDS,
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
            audit_log_file=_env("AUDIT_LOG_FILE"),
            audit_log_max_bytes=_env_int(
                "AUDIT_LOG_MAX_BYTES", DEFAULT_AUDIT_LOG_MAX_BYTES, minimum=0
            ),
            audit_log_backups=_env_int(
                "AUDIT_LOG_BACKUPS", DEFAULT_AUDIT_LOG_BACKUPS, minimum=0
            ),
            audit_log_rotation=_env("AUDIT_LOG_ROTATION") or AUDIT_ROTATION_SERVICE,
            purge_token=_env("PURGE_TOKEN"),
            purge_signing_key=_env("PURGE_SIGNING_KEY"),
            export_signing_key=_env("EXPORT_SIGNING_KEY"),
            encryption_keys=_read_encryption_keys(),
        )
