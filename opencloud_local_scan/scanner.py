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
  version disclosure and maintenance mode.
* ``vulnerabilities`` from the local advisory database and ``rating`` (0-5).
* ``lifecycle`` - which release line the instance runs, whether that line is
  rolling, production or LTS, and how long it is still supported. See
  :mod:`opencloud_local_scan.versions`.

Update information comes from the release feed
(:mod:`opencloud_local_scan.releases`), not from the instance, because
OpenCloud does not report pending updates.
"""

from __future__ import annotations

import fnmatch
import logging
import re
import socket
import ssl
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import partial
from typing import Any, TypeVar

import requests

from .releases import ReleaseSettings, UpdateInfo, fetch_update_info
from .versions import (
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
STATUS_PATH = "/status.php"
WEBFINGER_PATH = "/.well-known/webfinger"

# Requested to find out how the server answers for something that cannot exist.
CATCH_ALL_PATH = "/check-opencloud-security-probe-404"

SEVERITY_RATING_CAP: dict[str, int] = {"critical": 2, "high": 3, "medium": 4, "low": 5}

MIN_RATING = 0
MAX_RATING = 5

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_TLS_MIN_DAYS = 14
DEFAULT_DEBUG_PORT_TIMEOUT_SECONDS = 3

# One worker means "scan sequentially", which stays the default: a monitoring
# plugin must not surprise an instance with a burst of parallel requests.
DEFAULT_CONCURRENCY = 1
MAX_CONCURRENCY = 32

USER_AGENT = "check-opencloud-security local scanner"

REQUEST_ERRORS = (requests.exceptions.RequestException, ValueError)


class ScanError(RuntimeError):
    """Raised when the instance cannot be scanned at all."""


@dataclass(frozen=True)
class ScannerSettings:
    """Tunables for a scan run."""

    timeout: int = DEFAULT_TIMEOUT_SECONDS
    verify_tls: bool = True
    proxy: str | None = None
    scheme: str = "https"
    port: int | None = None
    extra_checks: bool = True
    extra_checks_affect_rating: bool = True
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
    release_track: str | None = None
    """The track this instance follows: rolling, production or lts.

    ``None`` lets the schedule decide, which picks whichever track supports
    the installed line longest. Setting it says "this is the track we signed
    up for" and is judged accordingly - a rolling instance sitting on an old
    production line is then behind, not current.
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

    @property
    def proxies(self) -> dict[str, str] | None:
        """requests-style proxy mapping."""
        return {"http": self.proxy, "https": self.proxy} if self.proxy else None

    @property
    def workers(self) -> int:
        """The concurrency actually used, clamped to something sane."""
        return max(1, min(int(self.concurrency), MAX_CONCURRENCY))


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
            self._sessions.session = session
        return session

    def get(
        self,
        path: str,
        *,
        allow_redirects: bool = True,
        method: str = "GET",
        base_url: str | None = None,
    ) -> requests.Response | None:
        """Perform one request, returning None when it fails."""
        url = f"{base_url or self.base_url}{path}"
        try:
            return self._session.request(
                method,
                url,
                timeout=self.settings.timeout,
                verify=self.settings.verify_tls,
                proxies=self.settings.proxies,
                allow_redirects=allow_redirects,
                headers={"User-Agent": self.settings.user_agent},
            )
        except REQUEST_ERRORS as exc:
            LOGGER.debug("Request to %s failed: %s", url, exc)
            return None


def _host_and_port(host: str, settings: ScannerSettings) -> tuple[str, int]:
    """Split an optional ':port' suffix off the host and apply the default."""
    hostname = host.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        hostname = hostname.removeprefix(prefix)
    hostname = hostname.split("/", 1)[0]

    port = settings.port
    if hostname.startswith("["):  # bracketed IPv6 literal
        closing = hostname.find("]")
        if closing != -1 and hostname[closing + 1:].startswith(":"):
            port = port or int(hostname[closing + 2:])
            hostname = hostname[: closing + 1]
    elif hostname.count(":") == 1:
        hostname, _, raw_port = hostname.partition(":")
        port = port or int(raw_port)

    if port is None:
        port = 443 if settings.scheme == "https" else 80
    return hostname, port


def _base_url(hostname: str, port: int, scheme: str) -> str:
    """Build the base URL, omitting the port when it is the scheme default."""
    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return f"{scheme}://{hostname}"
    return f"{scheme}://{hostname}:{port}"


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
    return payload


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
    return result


def _hsts_max_age(value: str | None) -> int | None:
    """Read the max-age directive of a Strict-Transport-Security header."""
    if not value:
        return None
    match = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _csp_has_unsafe_inline(value: str | None) -> bool | None:
    """
    Whether the CSP allows inline scripts.

    None when there is no policy at all - that is already reported through
    ``setup.headers`` and must not be confused with a weak policy.
    """
    if not value:
        return None
    for directive in value.split(";"):
        name, _, sources = directive.strip().partition(" ")
        if name.strip().lower() == "script-src":
            return "'unsafe-inline'" in sources.lower()
    return "'unsafe-inline'" in value.lower()


def _check_https(probe: _Probe, hostname: str) -> dict[str, Any]:
    """Determine whether HTTPS is used and enforced for plain HTTP requests."""
    used = probe.base_url.startswith("https://")
    enforced = False

    plain = probe.derive(f"http://{hostname}")
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


def _tls_handshake(
    hostname: str, port: int, timeout: int, *, verify: bool
) -> tuple[dict[str, Any] | None, str, Exception | None]:
    """Open one TLS connection and return (certificate, protocol, error)."""
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((hostname, port), timeout=timeout) as raw,
            context.wrap_socket(raw, server_hostname=hostname) as tls,
        ):
            return tls.getpeercert(), tls.version() or "unknown", None
    except (OSError, ssl.SSLError) as exc:
        return None, "", exc


def _certificate_finding(
    certificate: Mapping[str, Any] | None, settings: ScannerSettings
) -> Finding | None:
    """Turn the certificate's notAfter field into a finding."""
    not_after = (certificate or {}).get("notAfter")
    if not isinstance(not_after, str):
        return None
    try:
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return Finding(
            "tlsCertificate", "medium", False, f"Unparsable certificate date {not_after!r}"
        )
    days_left = (expires - datetime.now(timezone.utc)).days
    return Finding(
        "tlsCertificate",
        "high" if days_left <= 0 else "medium",
        days_left >= settings.tls_min_days,
        f"Certificate expires in {days_left} day(s) ({not_after})",
    )


def _tls_findings(
    hostname: str, port: int, settings: ScannerSettings, *, verification_required: bool = True
) -> list[Finding]:
    """
    Inspect the TLS certificate, its trust chain and the negotiated protocol.

    OpenCloud generates a self-signed certificate during ``opencloud init``
    unless real ones are configured, so an untrusted chain is a common and
    important finding rather than a scan failure.
    """
    findings: list[Finding] = []
    certificate, protocol, error = _tls_handshake(
        hostname, port, settings.timeout, verify=True
    )
    trusted = error is None

    if error is not None:
        # Retry without verification: a certificate that merely is not
        # trusted still tells us the protocol and the expiry date.
        certificate, protocol, insecure_error = _tls_handshake(
            hostname, port, settings.timeout, verify=False
        )
        if insecure_error is not None:
            return [
                Finding(
                    "tlsHandshake",
                    "high",
                    False,
                    f"TLS handshake with {hostname}:{port} failed: {insecure_error}",
                )
            ]

    findings.append(
        Finding("tlsHandshake", "high", True, f"TLS handshake succeeded ({protocol})")
    )
    findings.append(
        Finding(
            "tlsTrusted",
            # An operator who passed --insecure knowingly accepts the
            # certificate, so the finding is reported but does not weigh in.
            "high" if verification_required else "low",
            trusted or not verification_required,
            "Certificate chain is trusted"
            if trusted
            else f"Certificate is not trusted (self-signed or unknown CA): {error}",
        )
    )

    modern = protocol in {"TLSv1.3", "TLSv1.2"}
    findings.append(
        Finding(
            "tlsProtocol",
            "high",
            modern,
            f"Negotiated {protocol}" + ("" if modern else " (TLS 1.2 or newer expected)"),
        )
    )

    certificate_finding = _certificate_finding(certificate, settings)
    if certificate_finding is not None:
        findings.append(certificate_finding)
    return findings


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


def _basic_auth_finding(challenge: str | None) -> Finding:
    """HTTP basic authentication must not be offered by a production instance."""
    if challenge is None:
        return Finding(
            "basicAuthDisabled", "high", True, "No WWW-Authenticate challenge observed"
        )
    offered = "basic" in challenge.lower()
    return Finding(
        "basicAuthDisabled",
        "high",
        not offered,
        f"WWW-Authenticate: {challenge}"
        + (" (PROXY_ENABLE_BASIC_AUTH is on)" if offered else ""),
    )


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

    def reachable(port: int) -> bool:
        try:
            with socket.create_connection(
                (hostname, port), timeout=settings.debug_port_timeout
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


def _status_findings(status: Mapping[str, Any]) -> list[Finding]:
    """Report maintenance mode, pending upgrades and an unfinished setup."""
    findings: list[Finding] = []
    if status.get("maintenance"):
        findings.append(
            Finding("maintenanceMode", "medium", False, "Instance is in maintenance mode")
        )
    if status.get("needsDbUpgrade"):
        findings.append(
            Finding("databaseUpgrade", "high", False, "Instance needs a database upgrade")
        )
    if status.get("installed") is False:
        findings.append(
            Finding("installed", "critical", False, "Instance reports that it is not installed")
        )
    return findings


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
    *,
    verification_required: bool = True,
) -> list[Finding]:
    """Run every check that goes beyond product, version and headers."""
    findings: list[Finding] = []
    if probe.base_url.startswith("https://"):
        findings.extend(
            _tls_findings(
                hostname, port, settings, verification_required=verification_required
            )
        )
    findings.extend(_authentication_findings(probe))
    findings.append(_basic_auth_finding(challenge))
    findings.extend(_exposed_path_findings(probe))
    findings.append(_directory_listing_finding(probe, root_response))
    findings.extend(_debug_endpoint_findings(probe))
    if settings.check_debug_ports:
        findings.extend(_debug_port_findings(hostname, settings))
    findings.extend(_disclosure_findings(root_response))
    webfinger = _webfinger_finding(probe)
    if webfinger is not None:
        findings.append(webfinger)
    findings.extend(_status_findings(status))
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
    hostname, port = _host_and_port(host, settings)
    base_url = _base_url(hostname, port, settings.scheme)
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
        base_url=_base_url(hostname, fallback_port, "http"), settings=settings
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
    ]
    root_response, capabilities, challenge = _run_all(settings, opening)

    version = select_version(status) or select_version(_dig(capabilities, "version") or {})
    product = str(status.get("productname") or status.get("product") or "OpenCloud")
    edition = str(status.get("edition") or "")

    headers = _check_headers(root_response)
    https = _check_https(probe, hostname)
    hardenings = derive_hardenings(root_response, capabilities, challenge)

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
        "scanner": "check-opencloud-security built-in scanner",
        "updates": update_info.as_dict(),
        "extraChecks": [finding.as_dict() for finding in findings],
        "advisorySources": database.sources,
        "capabilitiesAvailable": capabilities is not None,
    }
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
