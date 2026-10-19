"""
Re-measure a few findings without running a full scan.

After an operator changes one reverse-proxy setting, the question is "did
that fix it?", not "what is the state of the whole instance?". This module
answers the narrow question: every requested finding id is mapped to the
probe group that produces it, only those groups run, and the result says
what each probe measured.

Like :func:`opencloud_local_scan.scanner.scan`, it measures and never
judges: there is no rating, no waiver and no exit code here. Whether a
still-failing check is a WARNING or a CRITICAL is the plugin's decision.

The probes are the scanner's own functions, called with the same
arguments a full scan passes them, so a check verified here cannot come back
with a different answer in the next full scan. Findings that need the whole
picture - an advisory against the version, end of life, parity between
several addresses - are reported as not verifiable rather than guessed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

import requests

from .caa import check_caa_record
from .dnssec import check_dnssec
from .hardening import HARDENINGS
from .scanner import (
    ADVISORY_CHECK_NAMES,
    ADVISORY_HEADERS,
    SCAN_HEADERS,
    Finding,
    ScannerSettings,
    _authentication_challenge,
    _authentication_findings,
    _backend_port_finding,
    _basic_auth_finding,
    _check_advisory_checks,
    _check_advisory_headers,
    _check_headers,
    _check_https,
    _companion_findings,
    _cookie_findings,
    _cors_finding,
    _debug_endpoint_findings,
    _debug_port_findings,
    _demo_user_finding,
    _directory_listing_finding,
    _disclosure_findings,
    _exposed_path_findings,
    _fetch_capabilities,
    _forwarded_host_finding,
    _identity_provider,
    _identity_provider_finding,
    _open_instance,
    _Probe,
    _reverse_proxy,
    _reverse_proxy_finding,
    _run_all,
    _trace_finding,
    _version_findings,
    _web_embed_findings,
    _webfinger_finding,
    derive_hardenings,
)
from .tls import inspect as inspect_tls
from .versions import select_version

#: Findings that depend on more than a probe can re-measure on its own.
_UNVERIFIABLE: dict[str, str] = {
    "eol": "End of life follows from the version and the release schedule; run a full scan.",
    "httpsAvailable": "Whether HTTPS is usable is decided while connecting; run a full scan.",
    "addressParity": "Address parity compares every resolved address; run a full scan.",
    "tlsAddressParity": "Address parity compares every resolved address; run a full scan.",
}

#: Families whose members are named ``family:subject`` and that one probe
#: group produces together. Asking for the bare family root verifies them all.
_FAMILIES: dict[str, str] = {
    "exposed": "exposedPaths",
    "authentication": "authentication",
    "debugEndpoint": "debugEndpoints",
    "debugPort": "debugPorts",
    "versionDisclosure": "root",
}

#: Exact extra-check ids and the probe group that measures them.
_CHECK_GROUPS: dict[str, str] = {
    "cookieSecure": "root",
    "cookieHttpOnly": "root",
    "cookieSameSite": "root",
    "cookiePrefix": "root",
    "reverseProxyDetected": "root",
    "basicAuthDisabled": "identity",
    "identityProviderDetected": "identity",
    "demoUsersDisabled": "identity",
    "directoryListing": "directoryListing",
    "companionEditorHttps": "companion",
    "companionAdminConsole": "companion",
    "webEmbedMessageOriginRestricted": "webEmbed",
    "webEmbedDelegatedAuthenticationRestricted": "webEmbed",
    "corsOriginRestricted": "cors",
    "traceMethodDisabled": "trace",
    "forwardedHostIgnored": "forwardedHost",
    "webfingerVersionDisclosure": "webfinger",
    "versionDetection": "version",
    "backendPortClosed": "debugPorts",
    "httpsEnforced": "https",
    "tlsCaaRecord": "caa",
    "tlsDnssec": "dnssec",
}


def probe_group(finding_id: str) -> str | None:
    """
    The probe group that re-measures ``finding_id``, or ``None``.

    ``None`` means this build cannot verify the id in isolation - either it
    needs a full scan (see :data:`_UNVERIFIABLE`) or it is not an id the
    scanner produces at all.
    """
    if finding_id in _UNVERIFIABLE or finding_id.startswith("vulnerability:"):
        return None
    if finding_id in _CHECK_GROUPS:
        return _CHECK_GROUPS[finding_id]
    if finding_id in SCAN_HEADERS or finding_id in ADVISORY_HEADERS:
        return "root"
    if finding_id in ADVISORY_CHECK_NAMES:
        return "advisoryChecks"
    if finding_id in HARDENINGS:
        return "hardenings"
    if finding_id.startswith("tls"):
        return "tls"
    family, _, _subject = finding_id.partition(":")
    return _FAMILIES.get(family)


def _unverifiable_reason(finding_id: str) -> str:
    if finding_id.startswith("vulnerability:"):
        return "A known vulnerability is cleared by upgrading; run a full scan."
    return _UNVERIFIABLE.get(finding_id, "This build does not know how to verify this id.")


def _observation(name: str, passed: bool, detail: str = "") -> Finding:
    """A header or hardening flag, in the same shape as an extra check."""
    return Finding(name, "", passed, detail)


@dataclass
class _Session:
    """What the probe groups share: one connection, fetched pages cached."""

    probe: _Probe
    status: Mapping[str, Any]
    hostname: str
    port: int
    settings: ScannerSettings
    verification_required: bool
    _cache: dict[str, Any] = field(default_factory=dict)

    def _once(self, key: str, produce: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = produce()
        return self._cache[key]

    @property
    def root(self) -> requests.Response | None:
        return self._once("root", lambda: self.probe.get("/", allow_redirects=True))

    @property
    def opening(self) -> tuple[Any, Any, Any]:
        """Capabilities, authentication challenge and identity provider."""

        def fetch() -> tuple[Any, Any, Any]:
            tasks: list[Callable[[], Any]] = [
                partial(_fetch_capabilities, self.probe),
                partial(_authentication_challenge, self.probe),
                partial(_identity_provider, self.probe, self.hostname),
            ]
            capabilities, challenge, provider = _run_all(self.settings, tasks)
            return capabilities, challenge, provider

        return self._once("opening", fetch)


def _group_root(session: _Session) -> list[Finding]:
    root = session.root
    findings = [
        _observation(name, present)
        for measured in (_check_headers(root), _check_advisory_headers(root))
        for name, present in measured.items()
    ]
    findings.extend(_cookie_findings(root))
    findings.append(_reverse_proxy_finding(_reverse_proxy(root)))
    findings.extend(_disclosure_findings(root))
    return findings


def _group_hardenings(session: _Session) -> list[Finding]:
    capabilities, challenge, provider = session.opening
    flags = derive_hardenings(session.root, capabilities, challenge, provider)
    return [_observation(name, enabled) for name, enabled in flags.items()]


def _group_identity(session: _Session) -> list[Finding]:
    _capabilities, challenge, provider = session.opening
    findings = [
        _basic_auth_finding(challenge, provider),
        _identity_provider_finding(provider or {}),
    ]
    demo = _demo_user_finding(session.probe, provider)
    if demo is not None:
        findings.append(demo)
    return findings


def _group_https(session: _Session) -> list[Finding]:
    https = _check_https(session.probe, session.hostname)
    return [_observation("httpsEnforced", bool(https["enforced"]))]


def _group_advisory_checks(session: _Session) -> list[Finding]:
    checks = _check_advisory_checks(session.probe, session.root)
    return [_observation(name, satisfied) for name, satisfied in checks.items()]


def _group_tls(session: _Session) -> list[Finding]:
    if not session.probe.base_url.startswith("https://"):
        return []
    pinned = dict(session.settings.pinned_addresses).get(
        session.hostname.strip("[]").lower().rstrip("."), ()
    )
    inspection = inspect_tls(
        session.hostname,
        session.port,
        session.settings.timeout,
        connect_host=next(iter(pinned), None),
        ca_file=session.settings.tls_ca_file,
    )
    if inspection is None:
        return []
    return [
        Finding(*check)
        for check in inspection.checks(
            min_days=session.settings.tls_min_days,
            verification_required=session.verification_required,
        )
    ]


def _group_dns(check: Callable[[str, float], Any]) -> Callable[[_Session], list[Finding]]:
    def run(session: _Session) -> list[Finding]:
        answer = check(session.hostname, session.settings.timeout)
        return [] if answer is None else [Finding(*answer)]

    return run


def _group_debug_ports(session: _Session) -> list[Finding]:
    findings = _debug_port_findings(session.hostname, session.settings)
    findings.append(
        _backend_port_finding(session.probe, session.hostname, session.port, session.status)
    )
    return findings


def _optional(
    produce: Callable[[_Probe], Finding | None],
) -> Callable[[_Session], list[Finding]]:
    def run(session: _Session) -> list[Finding]:
        finding = produce(session.probe)
        return [] if finding is None else [finding]

    return run


def _group_version(session: _Session) -> list[Finding]:
    return _version_findings(session.status, select_version(session.status))


_GROUPS: dict[str, Callable[[_Session], list[Finding]]] = {
    "root": _group_root,
    "hardenings": _group_hardenings,
    "identity": _group_identity,
    "https": _group_https,
    "advisoryChecks": _group_advisory_checks,
    "tls": _group_tls,
    "caa": _group_dns(check_caa_record),
    "dnssec": _group_dns(check_dnssec),
    "debugPorts": _group_debug_ports,
    "exposedPaths": lambda session: _exposed_path_findings(session.probe),
    "authentication": lambda session: _authentication_findings(session.probe),
    "debugEndpoints": lambda session: _debug_endpoint_findings(session.probe),
    "companion": lambda session: _companion_findings(session.probe),
    "webEmbed": lambda session: _web_embed_findings(session.probe),
    "directoryListing": lambda session: [
        _directory_listing_finding(session.probe, session.root)
    ],
    "cors": _optional(_cors_finding),
    "trace": _optional(_trace_finding),
    "forwardedHost": _optional(_forwarded_host_finding),
    "webfinger": _optional(_webfinger_finding),
    "version": _group_version,
}


def _matches(finding_id: str, requested: str) -> bool:
    """Whether a measured finding answers the requested id (or its family)."""
    return finding_id == requested or finding_id.startswith(f"{requested}:")


def verify(
    host: str,
    finding_ids: Iterable[str],
    settings: ScannerSettings | None = None,
) -> dict[str, Any]:
    """
    Re-measure only the findings named in ``finding_ids``.

    Returns a document with one entry per requested id, in the order given:
    ``verifiable``, ``passed`` (``None`` when nothing was measured), the
    ``checks`` that answered it, and a ``reason`` when it could not be
    verified. ``probeGroups`` lists the groups that actually ran.

    Raises :class:`~opencloud_local_scan.scanner.ScanError` when the instance
    cannot be reached, exactly as :func:`~opencloud_local_scan.scanner.scan`
    does.
    """
    settings = settings or ScannerSettings()
    requested = list(dict.fromkeys(item.strip() for item in finding_ids if item.strip()))
    verification_required = settings.verify_tls
    probe, status, hostname, port, settings, _untrusted, https_unavailable = _open_instance(
        host, settings
    )
    session = _Session(probe, status, hostname, port, settings, verification_required)
    measured: dict[str, list[Finding]] = {}
    try:
        for finding_id in requested:
            group = probe_group(finding_id)
            if group is not None and group not in measured:
                measured[group] = _GROUPS[group](session)
    finally:
        probe.close()

    results: list[dict[str, Any]] = []
    for finding_id in requested:
        group = probe_group(finding_id)
        if group is None:
            results.append(
                {
                    "id": finding_id,
                    "verifiable": False,
                    "passed": None,
                    "group": None,
                    "checks": [],
                    "reason": _unverifiable_reason(finding_id),
                }
            )
            continue
        checks = [f for f in measured[group] if _matches(f.id, finding_id)]
        reason = ""
        if not checks:
            reason = (
                "The instance answered over plain HTTP, so there is no TLS to inspect."
                if group == "tls" and https_unavailable
                else "The probe produced no observation for this id."
            )
        results.append(
            {
                "id": finding_id,
                "verifiable": True,
                "passed": all(f.passed for f in checks) if checks else None,
                "group": group,
                "checks": [f.as_dict() for f in checks],
                "reason": reason,
            }
        )

    return {
        "domain": hostname,
        "url": probe.base_url,
        "verifiedAt": datetime.now(UTC).isoformat(),
        "probeGroups": list(measured),
        "results": results,
    }


__all__ = ["probe_group", "verify"]
