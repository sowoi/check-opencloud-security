"""
Built-in security scanner for OpenCloud.

Every check in this module runs locally: the scanner talks to the instance
directly and produces a result document (``product``, ``version``,
``rating``, ``hardenings``, ``setup``, ``vulnerabilities``) that drives the
plugin, the webhook payload and the performance data. The ratings follow the
scale of the Nextcloud scan API.

What is inspected:

* ``product`` / ``version`` / ``edition`` / ``domain`` from ``status.php``,
  falling back to ``/ocs/v1.php/cloud/capabilities``. OpenCloud reports a
  legacy version (``0.1.0.0``) for old sync clients, so ``productversion`` is
  the field that counts - see :mod:`opencloud_local_scan.versions`.
* ``setup.https`` and ``setup.headers`` from live HTTP responses, measured
  against the headers OpenCloud's proxy service sets by default.
* ``hardenings`` derived from what the instance actually answers: HSTS
  quality, CSP quality, whether HTTP basic authentication is offered, and the
  sharing/password policy from the capabilities document.
* ``extraChecks`` - TLS state, authentication on the protected endpoints,
  exposed configuration or data paths, reachable service debug ports,
  the documented demo accounts of the built-in identity provider, and
  version disclosure.
* ``vulnerabilities`` from the local advisory database and ``rating`` (0-5).
* ``lifecycle`` - which release line the instance runs, whether that line is
  rolling, production or LTS, and how long it is still supported. See
  :mod:`opencloud_local_scan.versions`.

Update information comes from the release feed
(:mod:`opencloud_local_scan.releases`), not from the instance, because
OpenCloud does not report pending updates.
"""

from __future__ import annotations

import base64
import fnmatch
import ipaddress
import logging
import re
import socket
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import partial
from typing import Any, TypeVar
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager

from .caa import check_caa_record
from .releases import ReleaseSettings, UpdateInfo, fetch_update_info
from .remediation import SEVERITY_RATING_CAP as _SEVERITY_RATING_CAP
from .remediation import plan as remediation_plan
from .tls import TlsInspection
from .tls import inspect as inspect_tls
from .versions import (
    TRACK_AUTO,
    ReleaseSchedule,
    compare_versions,
    is_legacy_version,
    load_release_schedule,
    release_line,
    select_version,
)
from .vulndb import VulnerabilityDatabase, load_database

LOGGER = logging.getLogger("check_opencloud.scanner")

# Security headers OpenCloud's proxy service sets by default. A missing one
# means something in front of the instance strips it, or the proxy was
# reconfigured - both are worth reporting.
SCAN_HEADERS: tuple[str, ...] = (
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "X-Permitted-Cross-Domain-Policies",
    "X-Robots-Tag",
    "X-XSS-Protection",
    "Referrer-Policy",
)

# Expected values; None means "any non-empty value is accepted".
HEADER_EXPECTATIONS: dict[str, str | None] = {
    "Strict-Transport-Security": "max-age",
    "Content-Security-Policy": None,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "sameorigin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-Robots-Tag": None,
    "X-XSS-Protection": None,
    "Referrer-Policy": None,
}

# HSTS max-age considered long enough (one year). OpenCloud itself sends ten.
HSTS_MIN_MAX_AGE = 31_536_000

# Endpoints that must not answer an unauthenticated request with content.
PROTECTED_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("/remote.php/dav/files/", "critical"),
    ("/graph/v1.0/users", "critical"),
    ("/ocs/v1.php/cloud/user", "high"),
)

# Status codes that count as "authentication demanded". 405/501 appear when a
# reverse proxy answers a GET on a WebDAV collection.
AUTH_REQUIRED_STATUS = frozenset({401, 403, 405, 501})

# Paths that must never be readable from the internet. OpenCloud is a single
# Go binary serving embedded assets, so none of these can come from OpenCloud
# itself - a hit always means a misconfigured reverse proxy publishing the
# deployment directory.
EXPOSED_PATHS: tuple[tuple[str, str], ...] = (
    ("/opencloud.yaml", "critical"),
    ("/config/opencloud.yaml", "critical"),
    ("/.opencloud/config/opencloud.yaml", "critical"),
    ("/proxy/server.key", "critical"),
    ("/idm/opencloud.boltdb", "critical"),
    ("/.env", "critical"),
    ("/docker-compose.yml", "high"),
    ("/storage/users/", "high"),
    ("/.git/config", "high"),
)

# Debug endpoints of the OpenCloud services. They belong on the loopback-only
# debug listener, never on the public address.
DEBUG_ENDPOINTS: tuple[str, ...] = ("/metrics", "/config", "/debug/pprof/")

# Default debug ports of the services that carry the most information.
DEFAULT_DEBUG_PORTS: tuple[tuple[int, str], ...] = (
    (9205, "proxy"),
    (9141, "frontend"),
    (9124, "graph"),
    (9134, "idp"),
    (9239, "idm"),
)

CAPABILITIES_PATH = "/ocs/v1.php/cloud/capabilities"
OPENID_CONFIGURATION_PATH = "/.well-known/openid-configuration"
APP_LIST_PATH = "/app/list"
CALDAV_PATH = "/.well-known/caldav"
WEB_CONFIG_PATH = "/config.json"
BACKEND_PORT = 9200

# What a path answers when something is actually wired to it: a redirect to
# the service, or the service asking who is calling. A 200 proves nothing on
# an instance whose frontend answers every unknown path with its own shell.
SERVICE_PRESENT_STATUS = frozenset({401, 207})

# Reverse proxies that say who they are, in the header they say it in. Traefik
# and HAProxy are absent on purpose: neither announces itself by default, so
# not finding one proves nothing - which is why the finding below never costs
# the rating anything.
PROXY_SERVER_FINGERPRINTS: tuple[tuple[str, str], ...] = (
    ("openresty", "OpenResty"),
    ("nginx", "Nginx"),
    ("apache", "Apache"),
    ("caddy", "Caddy"),
    ("traefik", "Traefik"),
    ("envoy", "Envoy"),
    ("haproxy", "HAProxy"),
    ("cloudflare", "Cloudflare"),
    ("litespeed", "LiteSpeed"),
    ("varnish", "Varnish"),
    ("ats", "Apache Traffic Server"),
)

# Headers no origin sets for itself: something forwarded or cached the response.
PROXY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Via", ""),
    ("X-Varnish", "Varnish"),
    ("CF-Ray", "Cloudflare"),
    ("X-Cache", ""),
    ("X-Cache-Status", ""),
    ("X-Served-By", ""),
    ("X-Proxy-Cache", ""),
)

# Fingerprints of the identity providers an OpenCloud is usually put behind.
# Matched against the issuer URL only, because that is all this scan looks at.
IDP_FINGERPRINTS: tuple[tuple[str, str], ...] = (
    ("/realms/", "Keycloak"),
    ("/application/o/", "Authentik"),
    ("/api/oidc", "Authelia"),
    ("/oauth/v2", "Zitadel"),
    ("keycloak", "Keycloak"),
    ("authentik", "Authentik"),
    ("authelia", "Authelia"),
    ("zitadel", "Zitadel"),
    ("kanidm", "Kanidm"),
    ("login.microsoftonline.com", "Microsoft Entra ID"),
    ("accounts.google.com", "Google"),
    ("okta.com", "Okta"),
    ("auth0.com", "Auth0"),
)

IDP_SECURITY_ADVISORIES: dict[str, str] = {
    "Keycloak": "https://github.com/keycloak/keycloak/security/advisories",
    "Authelia": "https://github.com/authelia/authelia/security/advisories",
    "Authentik": "https://github.com/goauthentik/authentik/security/advisories",
}

# The accounts OpenCloud's built-in identity management creates when
# IDM_CREATE_DEMO_USERS is on. Their names and passwords are published in the
# OpenCloud documentation, which is why probing them is not password guessing:
# each pair either is the documented default or is not, and the answer is the
# same for everybody. Dennis is an administrator, so an instance that left
# these on has handed the internet an admin account with the password 'demo'.
DEMO_USERS: tuple[tuple[str, str], ...] = (
    ("dennis", "demo"),
    ("margaret", "demo"),
    ("alan", "demo"),
    ("lynn", "demo"),
    ("mary", "demo"),
)

# Asked with the credentials above: it answers with the account behind them,
# and refuses everybody else. The format parameter makes the answer JSON,
# which is what tells a real answer apart from a frontend catch-all page.
DEMO_USER_PATH = "/ocs/v1.php/cloud/user?format=json"

# An administrator account reachable with a documented password is as bad as
# this scan gets: it is not a weakness that might be exploitable, it is an
# open door with the key printed in the manual.
DEMO_USER_SEVERITY = "critical"

# Content types an OCS answer can have. A catch-all single page application
# answers text/html, so anything else is the service itself replying.
DEMO_USER_CONTENT_TYPES = frozenset(
    {"application/json", "text/json", "application/xml", "text/xml"}
)
STATUS_PATH = "/status.php"
WEBFINGER_PATH = "/.well-known/webfinger"

# ownCloud, Infinite Scale and Nextcloud serve the same status.php - OpenCloud
# inherited the endpoint from them - so the document alone does not say what is
# running. Their releases, advisories and hardening defaults are not
# OpenCloud's, and rating one of them against the OpenCloud release schedule
# would produce a confident answer about the wrong software. Scanning stops
# instead.
FOREIGN_PRODUCTS: tuple[str, ...] = ("owncloud", "infinitescale", "nextcloud")

# Requested to find out how the server answers for something that cannot exist.
CATCH_ALL_PATH = "/check-opencloud-security-probe-404"

# Re-exported from the remediation planner, which has to replay this
# arithmetic with one finding removed at a time and would otherwise keep a
# second copy of it. One table, two readers.
SEVERITY_RATING_CAP = _SEVERITY_RATING_CAP

# Basic authentication is a finding, not a catastrophe. Every client that
# cannot speak OpenID Connect - CalDAV and CardDAV calendars, WebDAV mounts,
# backup jobs - authenticates with it, so an instance that offers it has often
# made a deliberate trade rather than a mistake. When an external identity
# provider is doing the actual sign-in it is softer still, because the
# passwords being replayed are then app tokens rather than the account the
# provider protects with a second factor.
BASIC_AUTH_SEVERITY = "medium"
BASIC_AUTH_SEVERITY_WITH_IDP = "low"

MIN_RATING = 0
MAX_RATING = 5

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_TLS_MIN_DAYS = 14
DEFAULT_DEBUG_PORT_TIMEOUT_SECONDS = 3

# One worker means "scan sequentially", which stays the default: a monitoring
# plugin must not surprise an instance with a burst of parallel requests.
DEFAULT_CONCURRENCY = 1
MAX_CONCURRENCY = 32

# What requests itself defaults to, kept for the hand-walked chain below.
MAX_REDIRECTS = 30

DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024

USER_AGENT = "check-opencloud-security local scanner"

REQUEST_ERRORS = (requests.exceptions.RequestException, ValueError)


class ScanError(RuntimeError):
    """Raised when the instance cannot be scanned at all."""


@dataclass(frozen=True)
class ScannerSettings:
    """Tunables for a scan run."""

    timeout: int = DEFAULT_TIMEOUT_SECONDS
    verify_tls: bool = True
    tls_ca_file: str | None = None
    """PEM CA bundle used to verify an internal TLS deployment."""
    proxy: str | None = None
    scheme: str = "https"
    port: int | None = None
    extra_checks: bool = True
    extra_checks_affect_rating: bool = True
    ipv6_enabled: bool = True
    """Whether this process itself has outbound IPv6 connectivity.

    Guards the IPv4/IPv6 TLS-parity check, which dials an instance's IPv6
    address directly: a host or container with no IPv6 route of its own
    cannot reach that address at all, and reporting the resulting timeout as
    a finding would penalise the rating for a limitation of the scanner
    rather than of the target. False skips the probe instead - the address
    is still listed under ``addresses``, just not dialled a second time.
    """
    tls_min_days: int = DEFAULT_TLS_MIN_DAYS
    check_debug_ports: bool = True
    debug_ports: tuple[int, ...] = ()
    debug_port_timeout: int = DEFAULT_DEBUG_PORT_TIMEOUT_SECONDS
    concurrency: int = DEFAULT_CONCURRENCY
    """How many probes may be in flight at once.

    The scan is dominated by waiting for the instance to answer, so raising
    this shortens a run considerably. It stays at 1 by default because that
    is the only setting whose load on the instance is beyond argument, and
    because a sequential run is reproducible when a check turns flaky.
    """
    use_release_schedule: bool = True
    release_schedule: ReleaseSchedule | None = None
    """Overrides the bundled schedule; ``None`` loads the bundled one."""
    release_track: str | None = TRACK_AUTO
    """The track this instance follows: rolling, production, lts or auto.

    ``'auto'`` is the default and lets the schedule decide, which picks
    whichever track supports the installed line longest. ``None`` is treated
    identically, so a caller that has no opinion may pass either. Naming a
    real track says "this is the track we signed up for" and is judged
    accordingly - a rolling instance sitting on an old production line is then
    behind, not current.
    """
    ignore_hardenings: tuple[str, ...] = ()
    """Hardening measures and additional checks to disregard.

    Entries are matched against both namespaces, because they overlap
    (``basicAuthDisabled`` is a hardening *and* a check), and shell-style
    wildcards are allowed so that families such as ``debugPort:*`` can be
    waived in one go.
    """
    vulnerability_files: tuple[str, ...] = ()
    vulnerability_feed: str | None = None
    include_bundled_db: bool = True
    user_agent: str = USER_AGENT
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    """How much of a response body is read before the rest is dropped.

    Every document this scan looks at is a few kilobytes; a target that
    answers with an endless body would otherwise hold a worker for as long
    as it keeps sending. ``0`` restores the old behaviour of reading whatever
    arrives.
    """
    redirect_guard: Callable[[str], bool] | None = None
    """Decides whether one redirect may be followed.

    ``None`` lets :mod:`requests` follow redirects as it always has, which is
    what an operator scanning their own instance wants. A caller that scans a
    host somebody else named - the web service does - passes a check here,
    because the address that was validated is only the *first* one: without
    this, a target answering ``302 Location: http://127.0.0.1:...`` turns the
    scanner into a way to read the scanning host's own network.
    """
    pinned_addresses: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """Validated addresses for the initial hostname, used by web scans."""
    redirect_pinner: Callable[[str], tuple[str, ...] | None] | None = None
    """Validate and return addresses for each redirect before it is followed."""

    @property
    def proxies(self) -> dict[str, str] | None:
        """requests-style proxy mapping."""
        return {"http": self.proxy, "https": self.proxy} if self.proxy else None

    @property
    def tls_verify(self) -> bool | str:
        """The verification setting understood by requests."""
        return self.tls_ca_file if self.verify_tls and self.tls_ca_file else self.verify_tls

    @property
    def workers(self) -> int:
        """The concurrency actually used, clamped to something sane."""
        return max(1, min(int(self.concurrency), MAX_CONCURRENCY))


class _PinnedPoolManager(PoolManager):
    """Route validated hostnames to their already-checked IP addresses."""

    def __init__(self, pins: dict[str, tuple[str, ...]]) -> None:
        super().__init__()
        self._pins = pins

    def pin(self, hostname: str, addresses: tuple[str, ...]) -> None:
        """Replace a hostname's connection pin before the next request."""
        self._pins[hostname.lower().rstrip(".")] = addresses
        self.clear()

    def connection_from_host(
        self,
        host: str | None,
        port: int | None = None,
        scheme: str | None = "http",
        pool_kwargs: dict[str, Any] | None = None,
    ):
        original = host or ""
        addresses = self._pins.get(original.lower().rstrip("."))
        if addresses:
            host = addresses[0]
            pool_kwargs = dict(pool_kwargs or {})
            if scheme == "https":
                pool_kwargs.setdefault("assert_hostname", original)
                pool_kwargs.setdefault("server_hostname", original)
        return super().connection_from_host(host, port, scheme, pool_kwargs)


class _PinnedHTTPAdapter(HTTPAdapter):
    """Requests adapter that keeps the URL host for Host/SNI but dials its IP."""

    def __init__(self, pins: dict[str, tuple[str, ...]]) -> None:
        self._pinned_pool = _PinnedPoolManager(pins)
        super().__init__()

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        self.poolmanager = self._pinned_pool

    def pin(self, hostname: str, addresses: tuple[str, ...]) -> None:
        """Update the pool used by this session."""
        self._pinned_pool.pin(hostname, addresses)


_T = TypeVar("_T")


def _run_all(
    settings: ScannerSettings, tasks: Sequence[Callable[[], _T]]
) -> list[_T]:
    """
    Run independent probes, in parallel when the operator asked for it.

    Results keep the order of ``tasks`` regardless of how they were run, so
    that the findings a scan reports never depend on which probe answered
    first. Call sites must not nest: every one of them owns its pool, and a
    nested pool would multiply the configured concurrency.
    """
    if settings.workers == 1 or len(tasks) < 2:
        return [task() for task in tasks]
    with ThreadPoolExecutor(
        max_workers=min(settings.workers, len(tasks)),
        thread_name_prefix="opencloud-scan",
    ) as pool:
        return list(pool.map(lambda task: task(), tasks))


@dataclass
class Finding:
    """A single extra security finding."""

    id: str
    severity: str
    passed: bool
    detail: str = ""
    ignored: bool = False
    """Waived by configuration: still reported, but not counted anywhere."""

    def as_dict(self) -> dict[str, Any]:
        """Render the finding for JSON output."""
        return {
            "id": self.id,
            "severity": self.severity,
            "passed": self.passed,
            "detail": self.detail,
            "ignored": self.ignored,
        }

    @property
    def counts(self) -> bool:
        """Whether this finding should influence the verdict."""
        return not self.passed and not self.ignored


@dataclass
class _Probe:
    """Shared HTTP helper bound to one host."""

    base_url: str
    settings: ScannerSettings
    session: requests.Session = field(default_factory=requests.Session)
    _sessions: threading.local = field(default_factory=threading.local, repr=False)
    _owner: int = field(default_factory=threading.get_ident, repr=False)

    def __post_init__(self) -> None:
        """Mount the pinning adapter before the first request is made."""
        self._mount(self.session)

    def _mount(self, session: requests.Session) -> None:
        pins = dict(self.settings.pinned_addresses)
        if pins:
            adapter = _PinnedHTTPAdapter(pins)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

    def _pin_redirect(self, url: str, addresses: tuple[str, ...]) -> None:
        """Pin a validated redirect on the session making this request."""
        for prefix in ("http://", "https://"):
            adapter = self._session.get_adapter(prefix)
            if isinstance(adapter, _PinnedHTTPAdapter):
                hostname = urlsplit(url).hostname
                if hostname:
                    adapter.pin(hostname, addresses)
                return

    @staticmethod
    def _headers(url: str) -> dict[str, str]:
        """Keep the validated hostname while the adapter dials its IP."""
        return {
            "User-Agent": USER_AGENT,
            "Host": urlsplit(url).netloc,
        }

    def derive(self, base_url: str) -> _Probe:
        """A probe for another base URL that reuses this one's connections."""
        return replace(self, base_url=base_url)

    @property
    def _session(self) -> requests.Session:
        """
        The session belonging to the calling thread.

        A :class:`requests.Session` keeps mutable state that is not safe to
        share, so a parallel scan hands every worker its own rather than
        risking responses that belong to another probe.
        """
        if threading.get_ident() == self._owner:
            return self.session
        session = getattr(self._sessions, "session", None)
        if session is None:
            session = requests.Session()
            self._mount(session)
            self._sessions.session = session
        return session

    def get(
        self,
        path: str,
        *,
        allow_redirects: bool = True,
        method: str = "GET",
        base_url: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response | None:
        """
        Perform one request, returning None when it fails.

        ``headers`` are sent with this request only and are deliberately not
        carried into a redirect: the one caller that uses them sends an
        Authorization header, and replaying that to wherever a Location
        points would hand a credential to another host.
        """
        url = f"{base_url or self.base_url}{path}"
        guard = self.settings.redirect_guard
        follow = allow_redirects and guard is None
        try:
            response = self._capped(
                self._session.request(
                    method,
                    url,
                    timeout=self.settings.timeout,
                    verify=self.settings.tls_verify,
                    proxies=self.settings.proxies,
                    allow_redirects=follow,
                    headers={
                        **self._headers(url),
                        "User-Agent": self.settings.user_agent,
                        **(headers or {}),
                    },
                    stream=self.settings.max_response_bytes > 0,
                )
            )
        except REQUEST_ERRORS as exc:
            LOGGER.debug("Request to %s failed: %s", url, exc)
            return None
        if follow or not allow_redirects or guard is None:
            return response
        return self._follow(response, method=method, guard=guard)

    def _capped(self, response: requests.Response) -> requests.Response:
        """Read at most ``max_response_bytes`` of the body, then let go."""
        limit = self.settings.max_response_bytes
        if limit <= 0:
            return response
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) >= limit:
                LOGGER.debug("Truncating oversized response from %s", response.url)
                del body[limit:]
                break
        # requests offers no public way to hand a body back to a response.
        response._content = bytes(body)
        response._content_consumed = True  # type: ignore[attr-defined]
        response.close()
        return response

    def _follow(
        self,
        response: requests.Response,
        *,
        method: str,
        guard: Callable[[str], bool],
    ) -> requests.Response | None:
        """
        Walk the redirect chain by hand, asking ``guard`` about every hop.

        The unfollowed redirect is returned rather than an error: a scan of an
        instance that redirects somewhere it may not be followed still has a
        response to report, and the caller reads a 3xx exactly as it would
        have without a guard.
        """
        for _ in range(MAX_REDIRECTS):
            if not response.is_redirect:
                return response
            location = response.headers.get("Location") or ""
            target = urljoin(response.url, location)
            if not guard(target):
                LOGGER.debug("Refusing to follow redirect to %s", target)
                return response
            if self.settings.redirect_pinner is not None:
                addresses = self.settings.redirect_pinner(target)
                if not addresses:
                    LOGGER.debug("Refusing to pin redirect to %s", target)
                    return response
                self._pin_redirect(target, addresses)
            try:
                response = self._capped(
                    self._session.request(
                        method,
                        target,
                        timeout=self.settings.timeout,
                        verify=self.settings.tls_verify,
                        proxies=self.settings.proxies,
                        allow_redirects=False,
                        headers={
                            **self._headers(target),
                            "User-Agent": self.settings.user_agent,
                        },
                        stream=self.settings.max_response_bytes > 0,
                    )
                )
            except REQUEST_ERRORS as exc:
                LOGGER.debug("Request to %s failed: %s", target, exc)
                return None
        return response


def _resolved_addresses(hostname: str, settings: ScannerSettings) -> dict[str, list[str]]:
    """
    The addresses the instance's name points at, split by family.

    Pinned addresses win when the caller supplied them: the web application
    resolves the name itself before it lets a scan start and dials exactly
    those, so a second lookup here could report an address the scan never
    connected to. A name that does not resolve - or a scan of a bare IP -
    yields empty lists rather than an error; this is context beside the
    result, never a finding.
    """
    pinned = {name.lower(): values for name, values in settings.pinned_addresses}
    candidates: tuple[str, ...] | list[str] | None = pinned.get(hostname.lower())
    if candidates is None:
        try:
            infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except OSError as exc:
            LOGGER.debug("Could not resolve %s: %s", hostname, exc)
            infos = []
        candidates = [str(info[4][0]) for info in infos]

    addresses: dict[str, list[str]] = {"ipv4": [], "ipv6": []}
    for candidate in candidates:
        try:
            # A link-local answer carries the zone as '%eth0', which is not
            # part of the address.
            address = ipaddress.ip_address(str(candidate).split("%")[0].strip("[]"))
        except ValueError:
            continue
        bucket = addresses["ipv6" if address.version == 6 else "ipv4"]
        if str(address) not in bucket:
            bucket.append(str(address))
    return addresses


def _address_tls_inspections(
    hostname: str, port: int, settings: ScannerSettings, addresses: Mapping[str, list[str]]
) -> dict[str, TlsInspection]:
    """Inspect one IPv4 and one IPv6 endpoint without repeating heavy probes."""
    inspections: dict[str, TlsInspection] = {}
    for family in ("ipv4", "ipv6"):
        candidates = addresses.get(family) or []
        if candidates:
            inspections[family] = inspect_tls(
                hostname,
                port,
                settings.timeout,
                connect_host=candidates[0],
                probe_deprecated=False,
                check_stapling=False,
                ca_file=settings.tls_ca_file,
            )
    return inspections


def _address_parity_may_run(settings: ScannerSettings, addresses: Mapping[str, list[str]]) -> bool:
    """Whether the IPv4/IPv6 TLS-parity probe is worth dialling for this scan.

    Needs both address families to compare, and needs a scanner that can
    actually reach an IPv6 address in the first place - see
    :attr:`ScannerSettings.ipv6_enabled`.
    """
    return settings.ipv6_enabled and bool(addresses["ipv4"]) and bool(addresses["ipv6"])


def _address_parity_finding(inspections: Mapping[str, TlsInspection]) -> Finding | None:
    """Both DNS families must present the same usable TLS identity."""
    ipv4, ipv6 = inspections.get("ipv4"), inspections.get("ipv6")
    if ipv4 is None or ipv6 is None:
        return None
    if not ipv4.reachable or not ipv6.reachable:
        unavailable = "IPv4" if not ipv4.reachable else "IPv6"
        return Finding("tlsAddressParity", "medium", False, f"{unavailable} TLS endpoint is unreachable")
    left = ipv4.certificate.serial if ipv4.certificate else ""
    right = ipv6.certificate.serial if ipv6.certificate else ""
    differences = [
        field
        for field in ("protocol", "cipher", "trusted")
        if getattr(ipv4, field) != getattr(ipv6, field)
    ]
    if left != right:
        differences.append("certificate")
    return Finding(
        "tlsAddressParity",
        "medium",
        not differences,
        "IPv4 and IPv6 present the same TLS identity"
        if not differences
        else "IPv4 and IPv6 differ in " + ", ".join(differences),
    )


def _host_and_port(host: str, settings: ScannerSettings) -> tuple[str, int, str]:
    """Split the host, optional port and installation base path."""
    candidate = host.strip().rstrip("/")
    parsed = urlsplit(
        candidate if "://" in candidate else f"//{candidate}",
        scheme=settings.scheme,
    )
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = settings.port or parsed.port
    base_path = parsed.path.rstrip("/")

    if port is None:
        port = 443 if settings.scheme == "https" else 80
    return hostname, port, base_path


def _base_url(hostname: str, port: int, scheme: str, base_path: str = "") -> str:
    """Build the base URL, omitting the port when it is the scheme default."""
    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return f"{scheme}://{hostname}{base_path}"
    return f"{scheme}://{hostname}:{port}{base_path}"


def _dig(data: Any, *path: str) -> Any:
    """Walk nested mappings, returning None as soon as a key is missing."""
    current = data
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _fetch_status(probe: _Probe) -> dict[str, Any]:
    """Read and validate status.php, the entry point of every scan."""
    response = probe.get(STATUS_PATH)
    if response is None:
        raise ScanError(f"{probe.base_url}{STATUS_PATH} is unreachable")
    if response.status_code >= 400:
        raise ScanError(
            f"{probe.base_url}{STATUS_PATH} returned HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ScanError(f"{probe.base_url}{STATUS_PATH} did not return JSON: {exc}") from exc
    if not isinstance(payload, dict) or not any(
        key in payload for key in ("version", "productversion", "productname")
    ):
        raise ScanError(f"No OpenCloud instance found at {probe.base_url}")
    foreign = _foreign_product(payload)
    if foreign:
        raise ScanError(
            f"{probe.base_url} is not an OpenCloud instance: "
            f"{STATUS_PATH} reports {foreign}"
        )
    return payload


def _foreign_product(payload: Mapping[str, Any]) -> str | None:
    """Name the product when status.php belongs to another product.

    Matching is on the product name only. 'opencloud' does not contain either
    product identifier, so no OpenCloud instance can be rejected by accident,
    while 'ownCloud GmbH', 'Infinite Scale' and 'Nextcloud Hub' all are.
    """
    for key in ("productname", "ProductName", "product"):
        reported = str(payload.get(key) or "").strip()
        collapsed = re.sub(r"[^a-z]", "", reported.lower())
        if any(other in collapsed for other in FOREIGN_PRODUCTS):
            return reported
    return None


def _fetch_capabilities(probe: _Probe) -> dict[str, Any] | None:
    """
    Read the public capabilities document.

    ``/ocs/v1.php/cloud/capabilities`` is unauthenticated by design and is the
    only way to learn how sharing and password policies are configured.
    Returns None when the endpoint is unavailable; every check that builds on
    it is then simply not reported.
    """
    response = probe.get(f"{CAPABILITIES_PATH}?format=json")
    if response is None or response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    data = _dig(payload, "ocs", "data")
    return dict(data) if isinstance(data, Mapping) else None


def _csp_restricts_framing(value: str | None) -> bool:
    """Whether a CSP 'frame-ancestors' directive blocks being framed at all."""
    if not value:
        return False
    sources = _csp_directive(value, "frame-ancestors")
    if not sources:
        return False
    return "*" not in sources.split()


def _check_headers(response: requests.Response | None) -> dict[str, bool]:
    """Evaluate the security headers OpenCloud sets by default."""
    if response is None:
        return {name: False for name in SCAN_HEADERS}

    result: dict[str, bool] = {}
    for name in SCAN_HEADERS:
        value = response.headers.get(name)
        expected = HEADER_EXPECTATIONS.get(name)
        if not value:
            result[name] = False
        elif expected is None:
            result[name] = True
        else:
            result[name] = expected.lower() in value.lower()

    if not result["X-Frame-Options"]:
        # A CSP 'frame-ancestors' directive supersedes X-Frame-Options in every
        # browser that honours it, and is the header OpenCloud's own docs
        # recommend as the alternative - flagging it missing anyway would
        # contradict that guidance and give a false clickjacking alarm.
        result["X-Frame-Options"] = _csp_restricts_framing(
            response.headers.get("Content-Security-Policy")
        )
    return result


def _set_cookie_values(response: requests.Response | None) -> list[str]:
    """Read every Set-Cookie field without retaining any cookie value."""
    if response is None:
        return []
    raw_headers = getattr(getattr(response, "raw", None), "headers", None)
    getlist = getattr(raw_headers, "getlist", None)
    values = getlist("Set-Cookie") if callable(getlist) else None
    if values is None:
        value = response.headers.get("Set-Cookie")
        values = [value] if value else []
    return [str(value) for value in values if value]


def _cookie_findings(response: requests.Response | None) -> list[Finding]:
    """Check security attributes on cookies the public response actually set."""
    observed = _set_cookie_values(response)
    if not observed:
        return []
    missing: dict[str, list[str]] = {"Secure": [], "HttpOnly": [], "SameSite": []}
    for value in observed:
        name = value.split("=", 1)[0].strip()
        name = re.sub(r"[^A-Za-z0-9_.-]", "?", name)[:80] or "unnamed cookie"
        attributes = {part.strip().split("=", 1)[0].lower() for part in value.split(";")[1:]}
        if "secure" not in attributes:
            missing["Secure"].append(name)
        if "httponly" not in attributes:
            missing["HttpOnly"].append(name)
        if "samesite" not in attributes:
            missing["SameSite"].append(name)
    findings: list[Finding] = []
    for attribute, severity, identifier in (
        ("Secure", "high", "cookieSecure"),
        ("HttpOnly", "medium", "cookieHttpOnly"),
        ("SameSite", "low", "cookieSameSite"),
    ):
        names = missing[attribute]
        findings.append(
            Finding(
                identifier,
                severity,
                not names,
                f"Observed cookies {'; '.join(names)} lack {attribute}"
                if names
                else f"Every observed cookie sets {attribute}",
            )
        )
    return findings


def _hsts_max_age(value: str | None) -> int | None:
    """Read the max-age directive of a Strict-Transport-Security header."""
    if not value:
        return None
    match = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _csp_directive(value: str, directive: str) -> str | None:
    """Return the source list of one CSP directive, or None if absent."""
    for part in value.split(";"):
        name, _, sources = part.strip().partition(" ")
        if name.strip().lower() == directive:
            return sources
    return None


# CSP2+ browsers ignore 'unsafe-inline' outright whenever the same source
# list carries a nonce or a hash - the keyword is left in only so that older,
# nonce-unaware browsers still get *some* script-execution policy. A source
# list is neutralised by either kind of source, so it is enough to recognise
# the two prefixes rather than parse a full nonce/hash grammar.
_HASH_SOURCE_PREFIXES = ("'sha256-", "'sha384-", "'sha512-")


def _csp_has_nonce_or_hash(sources: str) -> bool:
    """Whether a CSP source list carries a nonce-source or a hash-source."""
    lowered = sources.lower()
    if "'nonce-" in lowered:
        return True
    return any(prefix in lowered for prefix in _HASH_SOURCE_PREFIXES)


def _csp_has_unsafe_inline(value: str | None) -> bool | None:
    """
    Whether the CSP lets injected markup or a data: call execute as script.

    Checks ``script-src`` for ``'unsafe-inline'`` and ``'unsafe-eval'``, the
    two keywords that undo most of what a CSP is for: the first lets any
    injected ``<script>`` or event handler run, the second lets a gadget in
    already-loaded code turn a string into code via ``eval()`` or the
    ``Function`` constructor. When there is no ``script-src``, CSP's own
    fallback rule applies and ``default-src`` governs script execution
    instead - style-only directives such as ``style-src 'unsafe-inline'``
    must not be mistaken for this, which is why the whole header is never
    scanned as one string.

    ``'unsafe-inline'`` is exempted when the same source list also carries a
    nonce or a hash: that is the standard 'strict-dynamic' rollout pattern
    (``script-src 'nonce-xyz' 'strict-dynamic' 'unsafe-inline' https:;``), and
    every browser that understands nonces also ignores 'unsafe-inline' in
    that case per the CSP spec - the keyword there is a fallback for browsers
    old enough to ignore the nonce too, not a real weakening of the policy.
    'unsafe-eval' gets no such exemption: nothing about a nonce or hash makes
    eval() safe again.

    None when there is no policy at all - that is already reported through
    ``setup.headers`` and must not be confused with a weak policy.
    """
    if not value:
        return None
    sources = _csp_directive(value, "script-src")
    if sources is None:
        sources = _csp_directive(value, "default-src") or ""
    lowered = sources.lower()
    if "'unsafe-eval'" in lowered:
        return True
    return "'unsafe-inline'" in lowered and not _csp_has_nonce_or_hash(sources)


def _check_https(probe: _Probe, hostname: str) -> dict[str, Any]:
    """Determine whether HTTPS is used and enforced for plain HTTP requests."""
    used = probe.base_url.startswith("https://")
    enforced = False

    base_path = urlsplit(probe.base_url).path.rstrip("/")
    plain = probe.derive(_base_url(hostname, 80, "http", base_path))
    response = plain.get("/", allow_redirects=False)
    if response is not None:
        location = response.headers.get("Location", "")
        enforced = response.is_redirect and location.lower().startswith("https://")
    elif used:
        # Port 80 closed or filtered: plain HTTP simply cannot be spoken.
        enforced = True

    return {"used": used, "enforced": enforced}


def _authentication_challenge(probe: _Probe) -> str | None:
    """
    Read the WWW-Authenticate challenges of a protected endpoint.

    OpenCloud advertises ``Basic`` there only when
    ``PROXY_ENABLE_BASIC_AUTH=true``, which its own documentation rules out
    for production.
    """
    response = probe.get(PROTECTED_ENDPOINTS[0][0], allow_redirects=False)
    if response is None:
        return None
    return response.headers.get("WWW-Authenticate")


def _identity_provider(probe: _Probe, hostname: str) -> dict[str, Any]:
    """
    Work out who actually signs users in, by asking where login points.

    Nothing is submitted anywhere: this reads the OpenID Connect discovery
    document the instance publishes and, when that is a redirect, the address
    in the Location header. No login form is filled in and no credential is
    ever sent here - working out who signs users in must not become an attempt
    to sign in. (:func:`_demo_user_finding` does send one, and only one: the
    published demo password, and only to the instance's own provider.)

    An issuer on a different host than the instance means an external provider
    such as Keycloak, Authentik or Authelia is in front of it. That is context
    for the rest of the scan rather than a verdict: it is not required, and an
    instance using the built-in provider is not thereby failing anything.
    """
    provider: dict[str, Any] = {
        "detected": False,
        "external": False,
        "issuer": "",
        "vendor": "",
        "version": "",
        "advisoryUrl": "",
    }
    response = probe.get(OPENID_CONFIGURATION_PATH, allow_redirects=False)
    if response is None:
        return provider

    issuer = ""
    if response.is_redirect:
        issuer = urljoin(probe.base_url, response.headers.get("Location") or "")
    elif response.status_code == 200:
        try:
            document = response.json()
        except ValueError:
            document = None
        if isinstance(document, Mapping):
            issuer = str(document.get("issuer") or "")

    if not issuer.lower().startswith(("http://", "https://")):
        return provider

    parts = urlsplit(issuer)
    if not parts.hostname:
        return provider

    provider["detected"] = True
    provider["issuer"] = f"{parts.scheme}://{parts.netloc}"
    provider["external"] = parts.hostname.lower().rstrip(".") != hostname.lower().rstrip(
        "."
    )
    provider["vendor"] = _identity_provider_vendor(issuer)
    provider["advisoryUrl"] = IDP_SECURITY_ADVISORIES.get(provider["vendor"], "")
    return provider


def _integrations(probe: _Probe, capabilities: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    Report the two integrations that can be seen from outside.

    Both answers are observations, never verdicts: the scan can say that an
    app provider is registered and that something answers the CalDAV
    well-known path, and it deliberately stops there. Whether Collabora or
    Radicale is *configured correctly* is a question about credentials, share
    permissions and a second service's own settings, none of which an
    unauthenticated caller can see - and guessing at it would be worse than
    saying nothing.

    ``/app/list`` is unprotected by OpenCloud's own proxy policy, and the
    CalDAV path is only read, never authenticated against.
    """
    apps_response, caldav_response = _run_all(
        probe.settings,
        [
            partial(probe.get, APP_LIST_PATH),
            partial(probe.get, CALDAV_PATH, allow_redirects=False),
        ],
    )

    apps: list[str] = []
    if apps_response is not None and apps_response.status_code == 200:
        try:
            document = apps_response.json()
        except ValueError:
            document = None
        for entry in _dig(document, "mime-types") or []:
            if not isinstance(entry, Mapping):
                continue
            for provider in entry.get("app_providers") or []:
                name = str((provider or {}).get("name") or "").strip()
                if name and name not in apps:
                    apps.append(name)

    calendar_present = caldav_response is not None and (
        caldav_response.is_redirect
        or caldav_response.status_code in SERVICE_PRESENT_STATUS
    )

    return {
        "office": {
            "detected": bool(apps),
            "apps": sorted(apps),
            "groupware": bool(_dig(capabilities, "capabilities", "groupware", "enabled")),
        },
        "calendar": {
            "detected": calendar_present,
            "advertised": bool(
                _dig(capabilities, "capabilities", "core", "support_radicale")
            ),
        },
    }


def _reverse_proxy(root_response: requests.Response | None) -> dict[str, Any]:
    """
    Look for a reverse proxy in front of the instance.

    OpenCloud's own proxy service sets no ``Server`` header, so one naming
    Nginx, Caddy or Cloudflare - or a header only a forwarder adds, such as
    ``Via`` - means something else answered first.

    A negative is weak evidence and is treated as such everywhere it is used:
    Traefik and HAProxy announce nothing by default, and an operator may well
    have stripped the header on purpose, which is itself good practice.
    """
    proxy: dict[str, Any] = {"detected": False, "vendor": "", "evidence": ""}
    if root_response is None:
        return proxy

    headers = root_response.headers
    server = str(headers.get("Server") or "")
    lowered = server.lower()
    for fingerprint, vendor in PROXY_SERVER_FINGERPRINTS:
        if fingerprint in lowered:
            proxy.update(detected=True, vendor=vendor, evidence=f"Server: {server}")
            return proxy

    for name, vendor in PROXY_HEADERS:
        value = headers.get(name)
        if value:
            proxy.update(
                detected=True,
                vendor=vendor,
                evidence=f"{name}: {value}",
            )
            return proxy
    return proxy


def _reverse_proxy_finding(proxy: Mapping[str, Any]) -> Finding:
    """Record whether anything sits in front of the instance."""
    if proxy.get("detected"):
        vendor = str(proxy.get("vendor") or "a reverse proxy")
        return Finding(
            "reverseProxyDetected",
            "low",
            True,
            f"{vendor} in front of the instance ({proxy.get('evidence')})",
        )
    return Finding(
        "reverseProxyDetected",
        "low",
        False,
        "No proxy-style Server or Via header; a proxy that announces nothing "
        "cannot be seen from outside",
    )


def _identity_provider_finding(provider: Mapping[str, Any]) -> Finding:
    """Say whether the scan could find out who signs users in."""
    if provider.get("detected"):
        vendor = str(provider.get("vendor") or "")
        if not provider.get("external"):
            # Deliberately not the issuer URL: for the built-in provider that
            # is the instance's own address, which says nothing and makes the
            # finding differ between two scans of the same deployment.
            return Finding(
                "identityProviderDetected", "low", True, "Issued by the instance itself"
            )
        issuer = str(urlsplit(str(provider.get("issuer") or "")).hostname or "")
        return Finding(
            "identityProviderDetected",
            "low",
            True,
            f"Issued by {vendor or 'an external provider'} at {issuer}",
        )
    return Finding(
        "identityProviderDetected",
        "low",
        False,
        "No OpenID Connect discovery document at "
        f"{OPENID_CONFIGURATION_PATH} and no redirect from it",
    )


def _identity_provider_vendor(issuer: str) -> str:
    """Name the provider when its issuer URL gives it away, else nothing."""
    candidate = issuer.lower()
    for fingerprint, vendor in IDP_FINGERPRINTS:
        if fingerprint in candidate:
            return vendor
    return ""


def _demo_user_probe(
    probe: _Probe, username: str, password: str
) -> requests.Response | None:
    """Ask the account endpoint as one documented demo user."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return probe.get(
        DEMO_USER_PATH,
        allow_redirects=False,
        headers={"Authorization": f"Basic {token}"},
    )


def _demo_login_succeeded(response: requests.Response | None) -> bool:
    """Decide whether an answer means the credentials were actually accepted."""
    if response is None or response.status_code != 200:
        return False
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    return content_type in DEMO_USER_CONTENT_TYPES and bool(response.content.strip())


def _demo_user_finding(
    probe: _Probe, identity_provider: Mapping[str, Any] | None
) -> Finding | None:
    """
    Check whether the built-in identity management still has its demo users.

    ``IDM_CREATE_DEMO_USERS`` populates a fresh instance with five accounts
    whose names and passwords are printed in the OpenCloud documentation, one
    of them an administrator. They exist so that somebody can try the software
    out; left on, they are an administrator account whose password everybody
    already knows.

    This is the one place the scan sends a credential, and it does so because
    there is no other way to see the accounts from outside: nothing OpenCloud
    exposes unauthenticated lists users. What is sent is not a guess at
    somebody's password but a published default, and a rejection tells the
    scan what it came for. Only the built-in provider is asked - with an
    external identity provider the accounts come from there, and pushing
    logins at a stranger's Keycloak is not this scan's business.
    """
    provider = identity_provider or {}
    if not provider.get("detected") or provider.get("external"):
        return None

    control, *responses = _run_all(
        probe.settings,
        [partial(probe.get, DEMO_USER_PATH, allow_redirects=False)]
        + [
            partial(_demo_user_probe, probe, username, password)
            for username, password in DEMO_USERS
        ],
    )
    if _demo_login_succeeded(control):
        # The endpoint answers anybody, so an answer proves nothing about the
        # credentials that were sent. The missing authentication is reported
        # by its own check; this one has nothing to say.
        return Finding(
            "demoUsersDisabled",
            DEMO_USER_SEVERITY,
            True,
            f"{DEMO_USER_PATH.split('?')[0]} answers without authentication, "
            "so the demo accounts could not be tested",
        )

    accepted = [
        username
        for (username, _), response in zip(DEMO_USERS, responses)
        if _demo_login_succeeded(response)
    ]
    if accepted:
        return Finding(
            "demoUsersDisabled",
            DEMO_USER_SEVERITY,
            False,
            "Documented demo accounts still sign in: "
            + ", ".join(accepted)
            + " (IDM_CREATE_DEMO_USERS)",
        )
    return Finding(
        "demoUsersDisabled",
        DEMO_USER_SEVERITY,
        True,
        "No documented demo account was accepted by the built-in identity provider",
    )


def _catch_all_probe(probe: _Probe) -> requests.Response | None:
    """
    Fetch a path that cannot exist, to learn how the server answers 404.

    The OpenCloud web frontend is a single page application that serves its
    application shell with HTTP 200 for many unknown paths. Taking that at
    face value would report the whole deployment directory as world-readable.
    """
    response = probe.get(CATCH_ALL_PATH, allow_redirects=False)
    if response is None or response.status_code != 200:
        return None
    return response


def _looks_like_catch_all(response: requests.Response, control: requests.Response) -> bool:
    """Decide whether a 200 response is just the server's catch-all page."""
    if len(response.content) == len(control.content):
        return True
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    # None of the probed files is HTML; an HTML answer is the frontend, not
    # the file itself.
    return content_type in {"text/html", "application/xhtml+xml"}


def _exposed_path_findings(probe: _Probe) -> list[Finding]:
    """Check that deployment internals are not readable over HTTP."""
    # The control probe joins the batch: it is independent of the paths and
    # only needed once every answer is in.
    control, *responses = _run_all(
        probe.settings,
        [partial(_catch_all_probe, probe)]
        + [
            partial(probe.get, path, allow_redirects=False)
            for path, _ in EXPOSED_PATHS
        ],
    )
    findings: list[Finding] = []
    for (path, severity), response in zip(EXPOSED_PATHS, responses):
        if response is None:
            findings.append(Finding(f"exposed:{path}", severity, True, "Not reachable"))
            continue

        exposed = response.status_code == 200 and bool(response.content.strip())
        detail = f"HTTP {response.status_code}"
        if exposed and control is not None and _looks_like_catch_all(response, control):
            exposed = False
            detail = f"HTTP {response.status_code} - catch-all response, file not served"
        elif exposed:
            detail = f"HTTP {response.status_code} - publicly readable"

        findings.append(Finding(f"exposed:{path}", severity, not exposed, detail))
    return findings


def _authentication_findings(probe: _Probe) -> list[Finding]:
    """Every protected endpoint must demand authentication."""
    responses = _run_all(
        probe.settings,
        [
            partial(probe.get, path, allow_redirects=False)
            for path, _ in PROTECTED_ENDPOINTS
        ],
    )
    findings: list[Finding] = []
    for (path, severity), response in zip(PROTECTED_ENDPOINTS, responses):
        if response is None:
            findings.append(
                Finding(f"authentication:{path}", severity, True, "Endpoint not reachable")
            )
            continue
        # A redirect to the login page is an acceptable answer as well.
        protected = (
            response.status_code in AUTH_REQUIRED_STATUS
            or response.is_redirect
            or response.status_code == 404
        )
        findings.append(
            Finding(
                f"authentication:{path}",
                severity,
                protected,
                f"{path} answered HTTP {response.status_code}"
                + ("" if protected else " without demanding authentication"),
            )
        )
    return findings


def _basic_auth_finding(
    challenge: str | None, identity_provider: Mapping[str, Any] | None = None
) -> Finding:
    """
    Report HTTP basic authentication, and weigh it for what it costs.

    Offering it is worth knowing about: a password works on every request
    without the identity provider seeing it. It is not, though, the mistake
    it used to be rated as - clients that cannot speak OpenID Connect, which
    is most calendar, contact and WebDAV clients, have nothing else to use,
    so a deployment that wants CalDAV at all has to leave it on.

    When an external provider is doing the sign-in, the severity drops again:
    the interactive login still goes through that provider and whatever it
    enforces, and basic auth is the side door for the clients that cannot.
    """
    external = bool((identity_provider or {}).get("external"))
    severity = BASIC_AUTH_SEVERITY_WITH_IDP if external else BASIC_AUTH_SEVERITY
    if challenge is None:
        return Finding(
            "basicAuthDisabled",
            severity,
            True,
            "No WWW-Authenticate challenge observed",
        )
    offered = "basic" in challenge.lower()
    detail = f"WWW-Authenticate: {challenge}"
    if offered:
        detail += " (PROXY_ENABLE_BASIC_AUTH is on)"
        if external:
            vendor = str((identity_provider or {}).get("vendor") or "")
            detail += (
                f"; interactive login goes through {vendor or 'an external provider'}, "
                "so this affects clients that cannot use it"
            )
    return Finding("basicAuthDisabled", severity, not offered, detail)


def _directory_listing_finding(
    probe: _Probe, root_response: requests.Response | None
) -> Finding:
    """
    A generated directory index means the deployment directory is served raw.

    OpenCloud serves its web assets from the binary, so an "Index of /" page
    can only come from a web server that was pointed at the deployment
    directory - which then also serves opencloud.yaml and the boltdb files.
    """
    candidates = [root_response]
    candidates.extend(
        _run_all(
            probe.settings,
            [
                partial(probe.get, path, allow_redirects=False)
                for path in ("/storage/", "/data/")
            ],
        )
    )

    for response in candidates:
        if response is None or response.status_code != 200:
            continue
        body = response.text[:2000].lower()
        if "index of /" in body or "<title>index of" in body:
            return Finding(
                "directoryListing",
                "critical",
                False,
                f"Directory listing enabled for {response.url}",
            )
    return Finding("directoryListing", "critical", True, "No directory listing found")


def _debug_endpoint_findings(probe: _Probe) -> list[Finding]:
    """The service debug endpoints must not be served on the public address."""
    control, *responses = _run_all(
        probe.settings,
        [partial(_catch_all_probe, probe)]
        + [partial(probe.get, path, allow_redirects=False) for path in DEBUG_ENDPOINTS],
    )
    findings: list[Finding] = []
    for path, response in zip(DEBUG_ENDPOINTS, responses):
        if response is None:
            findings.append(
                Finding(f"debugEndpoint:{path}", "high", True, "Not reachable")
            )
            continue
        exposed = response.status_code == 200 and bool(response.content.strip())
        if exposed and control is not None and _looks_like_catch_all(response, control):
            exposed = False
        findings.append(
            Finding(
                f"debugEndpoint:{path}",
                "high",
                not exposed,
                f"HTTP {response.status_code}"
                + (" - debug endpoint publicly readable" if exposed else ""),
            )
        )
    return findings


def _debug_port_findings(hostname: str, settings: ScannerSettings) -> list[Finding]:
    """
    Check that the per-service debug listeners are not reachable.

    OpenCloud binds them to 127.0.0.1 by default; publishing them exposes
    Prometheus metrics, a configuration dump and optionally pprof.
    """
    configured = settings.debug_ports or tuple(port for port, _ in DEFAULT_DEBUG_PORTS)
    names = dict(DEFAULT_DEBUG_PORTS)

    pins = dict(settings.pinned_addresses)
    connect_host = next(
        iter(pins.get(hostname.strip("[]").lower().rstrip("."), ())),
        hostname.strip("[]"),
    )

    def reachable(port: int) -> bool:
        try:
            with socket.create_connection(
                (connect_host, port), timeout=settings.debug_port_timeout
            ):
                return True
        except OSError:
            return False

    states = _run_all(settings, [partial(reachable, port) for port in configured])
    findings: list[Finding] = []
    for port, is_reachable in zip(configured, states):
        service = names.get(port, "service")
        findings.append(
            Finding(
                f"debugPort:{port}",
                "high",
                not is_reachable,
                f"{service} debug port {port} is reachable"
                if is_reachable
                else f"{service} debug port {port} is closed",
            )
        )
    return findings


def _backend_port_finding(
    probe: _Probe,
    hostname: str,
    primary_port: int,
    status: Mapping[str, Any],
) -> Finding:
    """Prove whether the origin's direct OpenCloud listener is also public."""
    if primary_port == BACKEND_PORT:
        return Finding(
            "backendPortClosed",
            "high",
            True,
            f"Port {BACKEND_PORT} is the explicitly scanned endpoint",
        )

    base_path = urlsplit(probe.base_url).path.rstrip("/")
    short = replace(
        probe.settings,
        timeout=probe.settings.debug_port_timeout,
        verify_tls=False,
    )
    candidate: Mapping[str, Any] | None = None
    exposed_scheme = ""
    candidate_paths = (base_path, "") if base_path else ("",)
    for candidate_path in candidate_paths:
        for scheme in ("http", "https"):
            direct = _Probe(
                base_url=_base_url(
                    hostname, BACKEND_PORT, scheme, candidate_path
                ),
                settings=short,
            )
            try:
                candidate = _fetch_status(direct)
            except ScanError:
                continue
            exposed_scheme = scheme
            break
        if candidate is not None:
            break

    same_product = (
        candidate is not None
        and str(candidate.get("productname") or candidate.get("product") or "").lower()
        == str(status.get("productname") or status.get("product") or "").lower()
    )
    primary_version = select_version(status)
    candidate_version = select_version(candidate or {})
    same_version = not primary_version or not candidate_version or (
        primary_version == candidate_version
    )
    exposed = same_product and same_version
    return Finding(
        "backendPortClosed",
        "high",
        not exposed,
        (
            f"OpenCloud {candidate_version or 'instance'} is reachable directly over "
            f"{exposed_scheme.upper()} on port {BACKEND_PORT}"
            if exposed
            else f"No matching OpenCloud listener found on port {BACKEND_PORT}"
        ),
    )


def _web_embed_findings(probe: _Probe) -> list[Finding]:
    """Read the public web configuration and reject unsafe iframe trust."""
    response = probe.get(WEB_CONFIG_PATH, allow_redirects=False)
    embed = None
    if response is not None and response.status_code == 200:
        try:
            document = response.json()
        except ValueError:
            document = None
        if isinstance(document, Mapping):
            candidate = _dig(document, "options", "embed")
            if isinstance(candidate, Mapping):
                embed = candidate

    wildcard = embed is not None and embed.get("messagesOrigin") == "*"
    delegated = embed is not None and embed.get("delegateAuthentication") is True
    delegated_origin = (
        str(embed.get("delegateAuthenticationOrigin") or "").strip()
        if embed is not None
        else ""
    )
    return [
        Finding(
            "webEmbedMessageOriginRestricted",
            "high",
            not wildcard,
            (
                "WEB_OPTION_EMBED_MESSAGES_ORIGIN allows every parent origin"
                if wildcard
                else "No wildcard embed message origin published"
            ),
        ),
        Finding(
            "webEmbedDelegatedAuthenticationRestricted",
            "critical",
            not delegated or bool(delegated_origin),
            (
                "Delegated iframe authentication is enabled without an origin"
                if delegated and not delegated_origin
                else "Delegated iframe authentication is off or origin-restricted"
            ),
        ),
    ]


def _disclosure_findings(response: requests.Response | None) -> list[Finding]:
    """Report software versions leaked through response headers."""
    if response is None:
        return []
    findings: list[Finding] = []
    for header in ("Server", "X-Powered-By"):
        value = response.headers.get(header, "")
        leaks = bool(re.search(r"\d+\.\d+", value))
        findings.append(
            Finding(
                f"versionDisclosure:{header}",
                "low",
                not leaks,
                f"{header}: {value}" if value else f"{header} not sent",
            )
        )
    return findings


def _webfinger_finding(probe: _Probe) -> Finding | None:
    """The public webfinger document should not publish the exact version."""
    response = probe.get(f"{WEBFINGER_PATH}?resource=acct%3Ame", allow_redirects=False)
    if response is None or response.status_code >= 400:
        return None
    body = response.text[:4000]
    leaks = bool(re.search(r"version[\"']?\s*[:=]\s*[\"']?\d+\.\d+", body, re.IGNORECASE))
    return Finding(
        "webfingerVersionDisclosure",
        "low",
        not leaks,
        "Webfinger publishes the instance version"
        if leaks
        else "Webfinger does not publish a version",
    )


def _version_findings(status: Mapping[str, Any], version: str | None) -> list[Finding]:
    """Report that the real release could not be determined."""
    if version:
        return []
    reported = status.get("productversion") or status.get("versionstring")
    return [
        Finding(
            "versionDetection",
            "medium",
            False,
            "Only the legacy compatibility version "
            f"({reported or 'none'}) was reported; 'productversion' is missing, "
            "so advisories and the release state cannot be evaluated",
        )
    ]


def _capability_hardenings(capabilities: Mapping[str, Any] | None) -> dict[str, bool]:
    """
    Derive hardening flags from the public capabilities document.

    Only keys the instance actually reports become findings, so an OpenCloud
    release that does not publish a setting never produces a false alarm.
    """
    if capabilities is None:
        return {}

    sharing = _dig(capabilities, "capabilities", "files_sharing")
    if not isinstance(sharing, Mapping):
        return {}

    hardenings: dict[str, bool] = {}

    public = sharing.get("public")
    if isinstance(public, Mapping):
        enforced = _dig(public, "password", "enforced_for")
        if isinstance(enforced, Mapping):
            hardenings["publicLinkPasswordEnforced"] = all(
                bool(value) for value in enforced.values()
            )
        elif isinstance(_dig(public, "password", "enforced"), bool):
            hardenings["publicLinkPasswordEnforced"] = bool(
                _dig(public, "password", "enforced")
            )
        expire = _dig(public, "expire_date", "enabled")
        if isinstance(expire, bool):
            hardenings["publicLinkExpirationEnforced"] = expire

    enumeration = sharing.get("user_enumeration")
    if isinstance(enumeration, Mapping) and isinstance(enumeration.get("enabled"), bool):
        hardenings["userEnumerationRestricted"] = not enumeration["enabled"] or bool(
            enumeration.get("group_members_only")
        )

    policy = _dig(capabilities, "capabilities", "password_policy")
    if isinstance(policy, Mapping):
        minimum = policy.get("min_characters")
        if isinstance(minimum, int):
            hardenings["passwordPolicyEnforced"] = minimum >= 8
        elif "max_characters" in policy:
            hardenings["passwordPolicyEnforced"] = False

    return hardenings


def derive_hardenings(
    root_response: requests.Response | None,
    capabilities: Mapping[str, Any] | None,
    challenge: str | None,
) -> dict[str, bool]:
    """
    Report the hardening measures that go beyond a header being present.

    ``setup.headers`` already answers "is the header there?". This block
    answers "is it any good?" - plus the settings only the instance itself
    can tell us about.
    """
    headers = root_response.headers if root_response is not None else {}

    hardenings: dict[str, bool] = {}

    hsts = headers.get("Strict-Transport-Security")
    max_age = _hsts_max_age(hsts)
    if hsts:
        hardenings["hstsLongMaxAge"] = bool(max_age and max_age >= HSTS_MIN_MAX_AGE)
        hardenings["hstsPreload"] = "preload" in hsts.lower()

    unsafe_inline = _csp_has_unsafe_inline(headers.get("Content-Security-Policy"))
    if unsafe_inline is not None:
        hardenings["cspWithoutUnsafeInline"] = not unsafe_inline

    if challenge is not None:
        hardenings["basicAuthDisabled"] = "basic" not in challenge.lower()

    hardenings.update(_capability_hardenings(capabilities))
    return dict(sorted(hardenings.items()))


@dataclass(frozen=True)
class RatingCap:
    """One failed extra check that held the rating down."""

    check: str
    severity: str
    cap: int
    detail: str = ""
    applied: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Render the cap for JSON output."""
        return {
            "check": self.check,
            "severity": self.severity,
            "cap": self.cap,
            "detail": self.detail,
            "applied": self.applied,
        }


@dataclass(frozen=True)
class RatingExplanation:
    """
    The audit trail behind a rating.

    A rating on its own is a verdict without an argument. This records how it
    was reached: the starting point that the version and the advisory database
    produced, and every failed extra check that pulled it down afterwards.
    """

    rating: int
    base_rating: int
    base_reason: str
    caps: tuple[RatingCap, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Render the explanation for JSON output."""
        return {
            "rating": self.rating,
            "base": {"rating": self.base_rating, "reason": self.base_reason},
            "caps": [cap.as_dict() for cap in self.caps],
        }

    def lines(self) -> list[str]:
        """Render the explanation as human-readable lines, in the order applied."""
        result = [f"Starting point: {self.base_rating}/5 - {self.base_reason}"]
        for cap in self.caps:
            verdict = (
                f"caps the rating at {cap.cap}/5"
                if cap.applied
                else f"would cap at {cap.cap}/5, already lower"
            )
            detail = f" ({cap.detail})" if cap.detail else ""
            result.append(f"Failed check {cap.check} [{cap.severity}] {verdict}{detail}")
        if not self.caps:
            result.append("No failed extra check lowered the rating.")
        result.append(f"Final rating: {self.rating}/5")
        return result


def _is_ignored(name: str, patterns: Iterable[str]) -> bool:
    """
    Whether an identifier has been waived by configuration.

    Matching is case-insensitive and accepts shell-style wildcards, so that
    generated families of identifiers - ``exposed:/some/path``,
    ``debugPort:9205`` - can be waived with a single ``debugPort:*`` rather
    than one entry per port.
    """
    candidate = name.casefold()
    return any(
        candidate == pattern.casefold() or fnmatch.fnmatch(candidate, pattern.casefold())
        for pattern in patterns
        if pattern
    )


def _apply_waivers(
    settings: ScannerSettings,
    findings: list[Finding],
    hardenings: Mapping[str, bool],
    headers: Mapping[str, bool],
    https: Mapping[str, Any],
) -> list[str]:
    """
    Mark everything the operator has chosen to accept, and report what matched.

    Only *failing* items can be waived: a waiver for something that passes
    would quietly turn into a blind spot the day it starts failing. Findings
    are flagged in place rather than deleted, so the result document still
    shows what was observed - a waiver hides an alert, not the evidence.
    """
    patterns = settings.ignore_hardenings
    if not patterns:
        return []

    ignored: list[str] = []
    for finding in findings:
        if not finding.passed and _is_ignored(finding.id, patterns):
            finding.ignored = True
            ignored.append(finding.id)

    ignored.extend(
        name for name, enabled in hardenings.items() if not enabled and _is_ignored(name, patterns)
    )
    ignored.extend(
        name for name, present in headers.items() if not present and _is_ignored(name, patterns)
    )
    if not https.get("enforced", True) and _is_ignored("httpsEnforced", patterns):
        ignored.append("httpsEnforced")

    unique = sorted(set(ignored))
    LOGGER.debug("Waived %d finding(s) by configuration: %s", len(unique), unique)
    return unique


def _rating_caps(rating: int, findings: Iterable[Finding]) -> tuple[int, list[RatingCap]]:
    """
    Lower the rating according to the worst failed extra check.

    Returns the capped rating together with every cap that was considered, so
    that a rating can explain itself. A cap is marked ``applied`` when it is
    one of the strictest, i.e. when it is a reason the rating ended where it
    did. The others are kept but marked as not applied - "this would have
    capped at 4 anyway" is useful when reading a report, and hiding it invites
    the suspicion that a finding was silently ignored.
    """
    failed = [finding for finding in findings if finding.counts]
    capped = rating
    for finding in failed:
        capped = min(capped, SEVERITY_RATING_CAP.get(finding.severity, MAX_RATING))
    capped = max(capped, MIN_RATING)

    caps = [
        RatingCap(
            check=finding.id,
            severity=finding.severity,
            cap=SEVERITY_RATING_CAP.get(finding.severity, MAX_RATING),
            detail=finding.detail,
            # Order-independent: a cap is a reason for the outcome when it is
            # as strict as the outcome, whatever order the checks ran in.
            applied=SEVERITY_RATING_CAP.get(finding.severity, MAX_RATING) == capped
            and capped < rating,
        )
        for finding in failed
    ]
    caps.sort(key=lambda entry: (entry.cap, entry.check))
    return capped, caps


def _compute_rating(
    *,
    eol: bool,
    vulnerabilities: list[dict[str, Any]],
    update_available: bool | None,
    behind_line: bool,
    findings: list[Finding],
    settings: ScannerSettings,
) -> RatingExplanation:
    """
    Map the collected evidence onto a 0-5 scale.

    5 (A+) fully up to date, 4 (A) a patch update is pending on the same
    release line, 3 (C) a whole release line behind, 2 (D) known
    vulnerabilities, 1 (E) critical or high vulnerabilities, 0 (F) the
    release line is out of support.
    """
    if eol:
        return RatingExplanation(
            rating=MIN_RATING,
            base_rating=MIN_RATING,
            base_reason=(
                "the installed release line is out of support and receives no "
                "security fixes, which overrides every other signal"
            ),
        )

    if vulnerabilities:
        severities = {str(entry.get("severity", "")).lower() for entry in vulnerabilities}
        worst = severities & {"critical", "high"}
        rating = 1 if worst else 2
        count = len(vulnerabilities)
        plural = "advisory matches" if count == 1 else "advisories match"
        reason = f"{count} {plural} the installed version"
        base_reason = f"{reason}, at least one of them critical or high" if worst else reason
    elif behind_line:
        rating = 3
        base_reason = "the instance is a whole release line behind"
    elif update_available:
        rating = 4
        base_reason = "an update is pending on the same release line"
    else:
        rating = MAX_RATING
        base_reason = (
            "the installed release is current and no advisory matches this version"
        )

    caps: list[RatingCap] = []
    base_rating = rating
    if settings.extra_checks and settings.extra_checks_affect_rating:
        rating, caps = _rating_caps(rating, findings)
    elif findings and not settings.extra_checks_affect_rating:
        base_reason += "; failed extra checks are reported but do not affect the rating"

    return RatingExplanation(
        rating=rating,
        base_rating=base_rating,
        base_reason=base_reason,
        caps=tuple(caps),
    )


def _base_of(caps: list[RatingCap], rating: int) -> int:
    """
    Recover the rating that applied before any cap was imposed.

    The caps record what each finding allowed at most; the value the scan
    started from is therefore the lowest cap that was *not* applied, or the
    rating itself when every cap bit.
    """
    unapplied = [cap.cap for cap in caps if not cap.applied]
    return min(unapplied) if unapplied else rating


def _collect_extra_findings(
    probe: _Probe,
    hostname: str,
    port: int,
    settings: ScannerSettings,
    status: Mapping[str, Any],
    version: str | None,
    root_response: requests.Response | None,
    challenge: str | None,
    identity_provider: Mapping[str, Any] | None = None,
    reverse_proxy: Mapping[str, Any] | None = None,
    tls_inspection: TlsInspection | None = None,
    address_parity: Finding | None = None,
    caa_finding: Finding | None = None,
    *,
    verification_required: bool = True,
) -> list[Finding]:
    """Run every check that goes beyond product, version and headers."""
    findings: list[Finding] = []
    if tls_inspection is not None:
        findings.extend(
            Finding(*check)
            for check in tls_inspection.checks(
                min_days=settings.tls_min_days,
                verification_required=verification_required,
            )
        )
    if caa_finding is not None:
        findings.append(caa_finding)
    if address_parity is not None:
        findings.append(address_parity)
    findings.extend(_cookie_findings(root_response))
    findings.extend(_authentication_findings(probe))
    findings.append(_basic_auth_finding(challenge, identity_provider))
    findings.append(_identity_provider_finding(identity_provider or {}))
    demo_users = _demo_user_finding(probe, identity_provider)
    if demo_users is not None:
        findings.append(demo_users)
    findings.append(
        _reverse_proxy_finding(
            reverse_proxy if reverse_proxy is not None else _reverse_proxy(root_response)
        )
    )
    findings.extend(_exposed_path_findings(probe))
    findings.append(_directory_listing_finding(probe, root_response))
    findings.extend(_debug_endpoint_findings(probe))
    findings.extend(_web_embed_findings(probe))
    if settings.check_debug_ports:
        findings.extend(_debug_port_findings(hostname, settings))
        findings.append(_backend_port_finding(probe, hostname, port, status))
    findings.extend(_disclosure_findings(root_response))
    webfinger = _webfinger_finding(probe)
    if webfinger is not None:
        findings.append(webfinger)
    findings.extend(_version_findings(status, version))
    return findings


def _open_instance(host: str, settings: ScannerSettings) -> tuple[
    _Probe, dict[str, Any], str, int, ScannerSettings, str | None, str | None
]:
    """
    Reach the instance, degrading from verified HTTPS to HTTP if necessary.

    Returns the usable probe, the status document, hostname, port, the
    settings actually used, and the reasons why TLS verification or HTTPS as
    a whole had to be given up (None when they were fine).
    """
    hostname, port, base_path = _host_and_port(host, settings)
    base_url = _base_url(hostname, port, settings.scheme, base_path)
    probe = _Probe(base_url=base_url, settings=settings)

    https_error: ScanError | None = None
    try:
        return probe, _fetch_status(probe), hostname, port, settings, None, None
    except ScanError as exc:
        if settings.scheme != "https":
            raise
        https_error = exc

    if settings.verify_tls:
        # A self-signed certificate is OpenCloud's default. Scanning must not
        # stop there - the untrusted chain becomes a finding instead.
        insecure = replace(settings, verify_tls=False)
        insecure_probe = _Probe(base_url=base_url, settings=insecure)
        try:
            status = _fetch_status(insecure_probe)
        except ScanError:
            LOGGER.debug("Instance is unreachable over HTTPS even without verification")
        else:
            LOGGER.debug("HTTPS scan needed to skip certificate verification")
            return (
                insecure_probe,
                status,
                hostname,
                port,
                insecure,
                str(https_error),
                None,
            )

    # An instance that is only reachable over plain HTTP is still worth
    # reporting - as a critical finding rather than as a failed scan.
    LOGGER.debug("HTTPS scan failed (%s), retrying over HTTP", https_error)
    fallback_port = port if port != 443 else 80
    plain_probe = _Probe(
        base_url=_base_url(hostname, fallback_port, "http", base_path), settings=settings
    )
    try:
        status = _fetch_status(plain_probe)
    except ScanError:
        raise https_error from None
    return plain_probe, status, hostname, fallback_port, settings, None, str(https_error)


def scan(
    host: str,
    settings: ScannerSettings | None = None,
    release_settings: ReleaseSettings | None = None,
    database: VulnerabilityDatabase | None = None,
) -> dict[str, Any]:
    """
    Scan one OpenCloud instance and return the result document.

    Raises :class:`ScanError` when the instance does not expose a usable
    ``status.php``; every other problem is reported inside the result.
    """
    settings = settings or ScannerSettings()
    verification_required = settings.verify_tls
    (
        probe,
        status,
        hostname,
        port,
        settings,
        tls_untrusted,
        https_unavailable,
    ) = _open_instance(host, settings)

    # The instance answers these three independently of one another.
    opening: list[Callable[[], Any]] = [
        partial(probe.get, "/", allow_redirects=True),
        partial(_fetch_capabilities, probe),
        partial(_authentication_challenge, probe),
        partial(_identity_provider, probe, hostname),
    ]
    root_response, capabilities, challenge, identity_provider = _run_all(
        settings, opening
    )

    version = select_version(status) or select_version(_dig(capabilities, "version") or {})
    product = str(status.get("productname") or status.get("product") or "OpenCloud")
    edition = str(status.get("edition") or "")

    headers = _check_headers(root_response)
    https = _check_https(probe, hostname)
    hardenings = derive_hardenings(root_response, capabilities, challenge)
    reverse_proxy = _reverse_proxy(root_response)
    integrations = (
        _integrations(probe, capabilities)
        if settings.extra_checks
        else {"office": {}, "calendar": {}}
    )

    schedule = settings.release_schedule
    if schedule is None:
        schedule = load_release_schedule()
    lifecycle = schedule.status_for(version, track=settings.release_track)

    update_info: UpdateInfo = fetch_update_info(release_settings, version, lifecycle)

    eol = bool(settings.use_release_schedule and lifecycle.eol)

    # "Behind the branch" means the instance has to leave its release line to
    # get back into support, which is a bigger job than a patch update.
    behind_line = False
    latest_in_branch: bool | None = None
    if update_info.available_version and version:
        behind_line = release_line(update_info.available_version) != release_line(version)
        latest_in_branch = behind_line or compare_versions(
            version, update_info.available_version
        ) >= 0
    elif update_info.available is False:
        latest_in_branch = True

    database = database or load_database(
        extra_files=settings.vulnerability_files,
        feed_url=settings.vulnerability_feed,
        include_bundled=settings.include_bundled_db,
        timeout=settings.timeout,
        verify=settings.verify_tls,
        proxies=settings.proxies,
    )
    vulnerabilities = [advisory.as_dict() for advisory in database.matches(version)]

    # The TLS layer is inspected once, before the findings are assembled, so
    # that the full detail can be published beside them: the findings say what
    # is wrong, the `tls` block says what was actually observed.
    addresses = _resolved_addresses(hostname, settings)
    tls_inspection = (
        inspect_tls(
            hostname,
            port,
            settings.timeout,
            connect_host=next(
                iter(
                    dict(settings.pinned_addresses).get(
                        hostname.strip("[]").lower().rstrip("."), ()
                    )
                ),
                None,
            ),
            ca_file=settings.tls_ca_file,
        )
        if settings.extra_checks and probe.base_url.startswith("https://")
        else None
    )
    address_tls = (
        _address_tls_inspections(hostname, port, settings, addresses)
        if settings.extra_checks
        and probe.base_url.startswith("https://")
        and _address_parity_may_run(settings, addresses)
        else {}
    )
    # CAA is a DNS record, not a TLS handshake property, but it answers the
    # same "who may issue this instance a certificate" question the TLS
    # findings above do, so it is gated and reported alongside them.
    caa_check = (
        check_caa_record(hostname, settings.timeout)
        if settings.extra_checks and probe.base_url.startswith("https://")
        else None
    )
    caa_finding = Finding(*caa_check) if caa_check is not None else None
    findings = (
        _collect_extra_findings(
            probe,
            hostname,
            port,
            settings,
            status,
            version,
            root_response,
            challenge,
            identity_provider,
            reverse_proxy,
            tls_inspection,
            _address_parity_finding(address_tls),
            caa_finding,
            verification_required=verification_required,
        )
        if settings.extra_checks
        else []
    )
    if settings.extra_checks and https_unavailable:
        findings.insert(
            0,
            Finding(
                "httpsAvailable", "critical", False, f"HTTPS unusable: {https_unavailable}"
            ),
        )
    if tls_untrusted:
        LOGGER.debug("Scanned with certificate verification disabled: %s", tls_untrusted)

    # Waivers are applied last, so that every finding - including the ones
    # added above - can be waived, and so that the rating below is computed
    # from what the operator actually wants to be alerted about.
    ignored_names = _apply_waivers(settings, findings, hardenings, headers, https)

    explanation = _compute_rating(
        eol=eol,
        vulnerabilities=vulnerabilities,
        update_available=update_info.available,
        behind_line=behind_line,
        findings=findings,
        settings=settings,
    )
    rating = explanation.rating

    scanned_at = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "domain": hostname,
        "addresses": addresses,
        # Whether this scanner could dial an IPv6 address at all; a
        # deployment with no IPv6 route reports it here rather than as a
        # failed - and rating-affecting - reachability check.
        "ipv6Enabled": settings.ipv6_enabled,
        "url": f"{probe.base_url}{STATUS_PATH}",
        "product": product,
        "version": version or "",
        "legacyVersion": str(status.get("version") or ""),
        "edition": edition,
        "scannedAt": {
            "date": scanned_at.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "timezone_type": 3,
            "timezone": "UTC",
        },
        "rating": rating,
        "ratingExplanation": explanation.as_dict(),
        "EOL": eol,
        "releaseType": lifecycle.release_type,
        "lifecycle": lifecycle.as_dict(),
        "ignored": ignored_names,
        "latestVersionInBranch": latest_in_branch,
        "vulnerabilities": vulnerabilities,
        "hardenings": hardenings,
        "setup": {"https": https, "headers": headers},
        "tls": tls_inspection.as_dict() if tls_inspection is not None else None,
        "tlsByAddress": {family: item.as_dict() for family, item in address_tls.items()},
        "identityProvider": identity_provider,
        "reverseProxy": reverse_proxy,
        "integrations": integrations,
        "scanner": "check-opencloud-security built-in scanner",
        "updates": update_info.as_dict(),
        "extraChecks": [finding.as_dict() for finding in findings],
        "advisorySources": database.sources,
        "capabilitiesAvailable": capabilities is not None,
    }
    # Derived from the document above and stored nowhere else: the plan is
    # the rating's own arithmetic replayed with one finding removed at a time.
    result["remediationPlan"] = remediation_plan(result)
    return result


def failed_extra_checks(result: Mapping[str, Any]) -> list[str]:
    """
    List the ids of extra checks that did not pass, worst severity first.

    Waived checks are left out: they are still in the result document, but a
    check an operator has explicitly accepted is not a failure to report.
    """
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    failures = [
        entry
        for entry in result.get("extraChecks", [])
        if isinstance(entry, dict)
        and not entry.get("passed", True)
        and not entry.get("ignored", False)
    ]
    failures.sort(key=lambda entry: order.get(str(entry.get("severity")), 9))
    return [str(entry.get("id")) for entry in failures]


__all__ = [
    "Finding",
    "RatingCap",
    "RatingExplanation",
    "ScanError",
    "ScannerSettings",
    "derive_hardenings",
    "failed_extra_checks",
    "is_legacy_version",
    "scan",
]
