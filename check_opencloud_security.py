#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""
Check an OpenCloud instance for known vulnerabilities.

The plugin uses a built-in scanner: every check runs locally, talking to the
instance itself, reading the endpoints OpenCloud exposes without
authentication, probing for common misconfigurations and rating the result.
No data about the instance leaves your network - the only optional outbound
request is the release feed used for the update check.

Authors: Massoud Ahmed
"""
import argparse
import contextlib
import contextvars
import hashlib
import hmac
import io
import ipaddress
import json
import logging
import socket
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import IntEnum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NoReturn, TypeVar
from urllib.parse import urlsplit

import requests

from opencloud_local_scan import (
    MAX_CONCURRENCY,
    Configuration,
    ConfigurationError,
    ReleaseSettings,
    ScanError,
    ScannerSettings,
    UpdateInfo,
    __version__,
    failed_extra_checks,
    fetch_update_info,
    load_configuration,
    release_settings_from_config,
    run_setup,
    scanner_settings_from_config,
    upgrade_self,
)
from opencloud_local_scan import scan as local_scan
from opencloud_local_scan.baseline import (
    BaselineError,
    Comparison,
    load_baseline,
    snapshot_of,
)
from opencloud_local_scan.completion import enable as enable_completion
from opencloud_local_scan.hardening import describe as describe_hardening
from opencloud_local_scan.hardening import is_actionable
from opencloud_local_scan.prometheus import render as render_prometheus_metrics
from opencloud_local_scan.releases import MODES as UPDATE_SOURCES
from opencloud_local_scan.selfupdate import self_update_note
from opencloud_local_scan.versions import RELEASE_TRACK_CHOICES, TRACK_AUTO

LOGGER = logging.getLogger("check_opencloud")

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_HOST_CONCURRENCY = 5
DEFAULT_PROMETHEUS_SCRAPE_INTERVAL_SECONDS = 60

# Values accepted by --upgrade-self. 'check' is the dry run: it works out and
# prints the command without letting a monitoring host change itself.
UPGRADE_RUN = "run"
UPGRADE_CHECK = "check"

PROGRAM_NAME = "check_opencloud_security"

# --check-only is a synonym of --upgrade-self=check, because that is the
# spelling people reach for first. It means nothing on its own, so using it
# alone is rejected rather than ignored.
CHECK_ONLY_FLAG = "--check-only"

# Flags that were removed but are still in people's shell history and in their
# monitoring definitions. Silently ignoring one of these is worse than not
# recognising it, so each names its replacement.
RETIRED_FLAGS = {"--dry-run": "--upgrade-self=check"}

# argparse's own exit code for a usage error; reused so that a rejected flag
# looks the same however it was rejected.
ARGPARSE_ERROR = 2

# Rating values produced by the built-in scanner, from best (5) to worst (0).
# The scale follows the ratings of the Nextcloud scan API, so that existing
# thresholds, graphs and alert rules keep their meaning.
RATE_MAP: dict[int, str] = {5: "A+", 4: "A", 3: "C", 2: "D", 1: "E", 0: "F"}
MIN_RATING = 0
MAX_RATING = 5

# Default rating thresholds: a rating at or below these values triggers the
# corresponding state. 3 == "C", 1 == "E".
DEFAULT_WARNING_RATING = 3
DEFAULT_CRITICAL_RATING = 1

# Prefix for all environment variables recognized by this plugin, e.g. COS_HOST.
ENV_PREFIX = "COS_"

# Worker-local result buffers let concurrent host scans keep their output and
# perfdata separate until the coordinator renders the ordered result blocks.
_RESULT_BUFFER: contextvars.ContextVar[io.StringIO | None] = contextvars.ContextVar(
    "result_buffer", default=None
)
_BASELINE_LOCK = threading.Lock()

# Nagios states that may trigger the optional webhook, keyed by the value
# accepted for --webhook-on.
WEBHOOK_TRIGGERS: dict[str, frozenset["NagiosExitCode"]] = {}
DEFAULT_WEBHOOK_ON = "critical"
DEFAULT_WEBHOOK_FORMAT = "generic"
DEFAULT_WEBHOOK_TIMEOUT_SECONDS = 10

DEFAULT_RETRIES = 2
DEFAULT_BACKOFF_FACTOR = 0.5

# Errors expected from a failing HTTP call or an unparsable JSON body.
REQUEST_ERRORS = (requests.exceptions.RequestException, ValueError)

T = TypeVar("T")


class NagiosExitCode(IntEnum):
    """Standard Nagios/Icinga plugin exit codes."""

    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


# Which states trigger the webhook, for each --webhook-on value. Higher
# settings include every state that is at least as severe.
WEBHOOK_TRIGGERS.update({
    "critical": frozenset({NagiosExitCode.CRITICAL}),
    "warning": frozenset({NagiosExitCode.CRITICAL, NagiosExitCode.WARNING}),
    "unknown": frozenset(
        {NagiosExitCode.CRITICAL, NagiosExitCode.WARNING, NagiosExitCode.UNKNOWN}
    ),
    "always": frozenset(NagiosExitCode),
})


@dataclass(frozen=True)
class ScanContext:
    """Immutable configuration for a single scan run."""

    host: str
    proxy: str | None = None
    debug: bool = False
    retries: int = DEFAULT_RETRIES
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    warning_rating: int = DEFAULT_WARNING_RATING
    critical_rating: int = DEFAULT_CRITICAL_RATING
    check_hardening: bool = False
    webhook_url: str | None = None
    webhook_on: str = DEFAULT_WEBHOOK_ON
    webhook_format: str = DEFAULT_WEBHOOK_FORMAT
    webhook_timeout: int = DEFAULT_WEBHOOK_TIMEOUT_SECONDS
    webhook_secret: str | None = None
    allow_private_webhooks: bool = False
    # Stored as a tuple of pairs so ScanContext stays hashable/frozen.
    webhook_headers: tuple[tuple[str, str], ...] = ()
    scanner_settings: ScannerSettings | None = None
    # Update check against the published OpenCloud releases.
    release_settings: ReleaseSettings | None = None
    update_check: bool = True
    update_warning: bool = False
    # Remember the findings of the last run and report only what changed.
    baseline_path: str | None = None
    warn_on_new: bool = False
    diff_format: str = "text"
    # Look up whether a newer plugin version has been published.
    self_update_check: bool = False


@dataclass
class ScanResult:
    """Result of a completed scan."""

    response: dict[str, Any]
    uuid: str


# --- Configuration helpers ---
# Replaced in main() by the configuration loaded from the YAML file; the
# default instance still resolves COS_ environment variables and secret
# references, so importing the module keeps working without a config file.
_CONFIG: Configuration = Configuration()


def _set_configuration(config: Configuration) -> None:
    """Install the configuration used as the source for argparse defaults."""
    global _CONFIG
    _CONFIG = config


def _env(name: str) -> str | None:
    """
    Read a configuration value (e.g. HOST -> COS_HOST or 'host:' in YAML).

    Environment variables win over the configuration file, and both support
    secret references such as 'secret://token' or a '<NAME>_FILE' variant.
    """
    return _CONFIG.get(name)


def _env_bool(name: str) -> bool:
    """Interpret a configuration value as a boolean flag."""
    return _CONFIG.get_bool(name)


def _allow_private_webhooks_default() -> bool:
    """Read the webhook opt-out from its public environment or nested config key."""
    name = "ALLOW_PRIVATE_WEBHOOKS"
    if any(
        f"{ENV_PREFIX}{suffix}" in _CONFIG.environ
        for suffix in (name, f"{name}_FILE")
    ):
        return _env_bool(name)
    return _env_bool(f"WEBHOOK_{name}")


def _waiver_patterns(values: list[str] | None) -> tuple[str, ...] | None:
    """
    Split repeated --ignore-hardening values into a flat list of patterns.

    Each occurrence may itself carry a comma-separated list, so that a single
    environment variable or command line argument can waive several measures.
    Returning None leaves the configured value untouched.
    """
    if values is None:
        return None
    patterns = [
        part.strip() for value in values for part in value.split(",") if part.strip()
    ]
    return tuple(dict.fromkeys(patterns))


def _env_int(name: str, default: int) -> int:
    """Read a configuration value as an int, falling back to default."""
    return _CONFIG.get_int(name, default)


def _env_float(name: str, default: float) -> float:
    """Read a configuration value as a float, falling back to default."""
    return _CONFIG.get_float(name, default)


def _fail(message: str, exit_code: NagiosExitCode = NagiosExitCode.UNKNOWN) -> NoReturn:
    """Print a Nagios-formatted failure message and terminate the program."""
    buffer = _RESULT_BUFFER.get()
    print(message, file=buffer)
    sys.exit(int(exit_code))


def _safe_monitoring_text(value: object, limit: int = 1024) -> str:
    """Flatten untrusted text before it reaches Nagios line delimiters."""
    flattened = " ".join(str(value).split())
    printable = "".join(
        character for character in flattened if character.isprintable() and character != "|"
    )
    return printable[:limit]


def _proxies(context: ScanContext) -> dict[str, str] | None:
    """requests-style proxy mapping for the configured proxy, if any."""
    return {"http": context.proxy, "https": context.proxy} if context.proxy else None


def _call_with_retry(
    func: Callable[[], T], *, retries: int, backoff_factor: float, description: str
) -> T:
    """
    Call func(), retrying on transient request errors with exponential backoff.

    Sleeps backoff_factor * 2**attempt seconds between attempts (0, 1, 2, ...).
    Re-raises the last encountered error once retries are exhausted.
    """
    last_exc: BaseException = RuntimeError(f"{description}: no attempt was made")
    for attempt in range(retries + 1):
        try:
            return func()
        except REQUEST_ERRORS as exc:
            last_exc = exc
            if attempt == retries:
                break
            sleep_seconds = backoff_factor * (2**attempt)
            LOGGER.debug(
                "%s failed (attempt %d/%d): %s - retrying in %.1fs",
                description,
                attempt + 1,
                retries + 1,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
    raise last_exc


# --- Utility Functions ---
def check_if_ip_or_host(host: str, context: ScanContext | None = None) -> None:
    """
    Validate the target address.

    The built-in scanner is perfectly happy with a literal address, so
    scanning an appliance at 10.0.0.5 is a normal thing to do. Only an address
    that is neither a valid IP nor a plausible hostname is rejected here.
    """
    candidate = host.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    # An IPv6 literal may carry a zone index (fe80::1%eth0), which
    # ipaddress rejects but which is still unmistakably an address.
    candidate = candidate.split("%", 1)[0]
    # A port suffix is allowed on hostnames and on bracketed IPv6 literals.
    if candidate.count(":") == 1:
        candidate = candidate.split(":", 1)[0]

    if not candidate:
        _fail(f"UNKNOWN: {host!r} is not a usable target address.")

    with contextlib.suppress(ValueError):
        ipaddress.ip_address(candidate)
        return

    if any(character.isspace() for character in candidate) or "/" in candidate:
        _fail(f"UNKNOWN: {host!r} is not a usable target address.")


def send_scan_request(context: ScanContext) -> ScanResult:
    """
    Obtain a scan result for the configured host.

    The built-in scanner always runs in-process. The function exists to keep
    the request, retry and error handling in one place.
    """
    LOGGER.debug("Running local scan for host: %s", context.host)
    try:
        response = _call_with_retry(
            lambda: local_scan(
                context.host,
                settings=context.scanner_settings
                or ScannerSettings(timeout=context.timeout),
                release_settings=context.release_settings,
            ),
            retries=context.retries,
            backoff_factor=context.backoff_factor,
            description=f"Scanning {context.host}",
        )
    except ScanError as exc:
        LOGGER.debug("Local scan failed for %s: %s", context.host, exc, exc_info=True)
        _notify_and_fail(context, f"UNKNOWN: {context.host} Scan failed: {exc}")
    except REQUEST_ERRORS as exc:  # pragma: no cover - defensive
        LOGGER.debug("Local scan failed for %s: %s", context.host, exc, exc_info=True)
        _notify_and_fail(context, f"UNKNOWN: {context.host} Scan failed: {exc}")
    return ScanResult(response=response, uuid=f"local-{context.host}")


def check_vulnerabilities(
    context: ScanContext,
    scan_result: ScanResult,
    duration_seconds: float | None = None,
) -> None:
    """Check the OpenCloud instance for known vulnerabilities and print the result."""

    response_scan = scan_result.response

    rating: int = response_scan.get("rating", -1)
    product: str = response_scan.get("product", "Unknown")
    version: str = response_scan.get("version") or "Unknown"
    domain: str = response_scan.get("domain", "Unknown")
    scan_date: str = response_scan.get("scannedAt", {}).get("date", "Unknown")
    rate: str = RATE_MAP.get(rating, "Unknown")

    vulnerabilities: list[dict[str, Any]] = response_scan.get("vulnerabilities", [])
    num_vulns: int = len(vulnerabilities)

    msg, exit_code = _evaluate_rating(context, response_scan, rating, num_vulns)

    missing_hardenings = _collect_missing_hardenings(response_scan)
    waived = _waived(response_scan)
    # Flags OpenCloud hardcodes are recorded but never alerted on: they say
    # nothing about this instance and cannot be cleared by anyone. Waived ones
    # drop out too, so that accepting a measure also silences its alert.
    actionable_hardenings = [
        name for name in missing_hardenings if is_actionable(name) and name not in waived
    ]
    detail_lines = [
        f"{product} {version} on {domain}, rating: {rate}, last scanned: {scan_date}"
    ]

    lifecycle_line = _format_lifecycle(response_scan)
    if lifecycle_line:
        detail_lines.append(lifecycle_line)

    schedule_note = _schedule_note(response_scan)
    if schedule_note:
        detail_lines.append(schedule_note)

    if num_vulns:
        detail_lines.append(
            f"Known vulnerabilities: {_format_vulnerabilities(vulnerabilities)}"
        )

    if context.check_hardening:
        if actionable_hardenings:
            detail_lines.append(
                f"Missing hardening: {', '.join(actionable_hardenings)} "
                "(run with --debug for what each means and how to fix it)"
            )
            if exit_code is NagiosExitCode.OK:
                msg = (
                    f"WARNING: {len(actionable_hardenings)} hardening measure(s) missing, "
                    "but no known vulnerabilities."
                )
                exit_code = NagiosExitCode.WARNING
        else:
            detail_lines.append("Hardening: all checked measures in place")

    if waived:
        detail_lines.append(
            f"Ignored by configuration ({len(waived)}): {', '.join(waived)}"
        )

    extra_failures = failed_extra_checks(response_scan)
    if response_scan.get("extraChecks"):
        if extra_failures:
            detail_lines.append(
                f"Additional checks failed ({len(extra_failures)}): "
                f"{', '.join(extra_failures[:5])}"
                + (f" (+{len(extra_failures) - 5} more)" if len(extra_failures) > 5 else "")
            )
        else:
            detail_lines.append("Additional checks: all passed")

    update_info = _resolve_update_info(context, response_scan)
    if update_info is not None and (update_info.known or update_info.error):
        detail_lines.append(update_info.summary())
        if context.update_warning and update_info.available and exit_code is NagiosExitCode.OK:
            msg = (
                "WARNING: Update available "
                f"({update_info.available_version or 'unknown version'}), "
                "but no known vulnerabilities."
            )
            exit_code = NagiosExitCode.WARNING

    msg, exit_code, baseline_lines, baseline_diff = _apply_baseline(
        context,
        response_scan,
        hardenings=actionable_hardenings if context.check_hardening else [],
        waived=waived,
        message=msg,
        exit_code=exit_code,
    )
    detail_lines.extend(baseline_lines)

    note = _self_update_line(context)
    if note:
        detail_lines.append(note)

    if context.debug:
        detail_lines.extend(
            _explain_lines(context, response_scan, missing_hardenings, extra_failures)
        )

    perfdata = _build_perfdata(
        rating,
        RATE_MAP,
        num_vulns,
        duration_seconds,
        context=context,
        missing_hardenings=len(actionable_hardenings) if context.check_hardening else None,
        failed_extra_checks_count=len(extra_failures) if response_scan.get("extraChecks") else None,
        update_available=update_info.available if update_info is not None else None,
        support_days_left=_support_days_left(response_scan),
    )

    if _webhook_should_fire(context, exit_code):
        payload = _build_webhook_payload(
            context,
            scan_result=scan_result,
            response_scan=response_scan,
            message=msg,
            exit_code=exit_code,
            rating=rating,
            rate=rate,
            vulnerabilities=vulnerabilities,
            missing_hardenings=actionable_hardenings,
            duration_seconds=duration_seconds,
            update_info=update_info,
            extra_failures=extra_failures,
            baseline_diff=baseline_diff,
        )
        if not _send_webhook(context, payload):
            detail_lines.append("Webhook delivery failed (see debug log)")

    safe_message = _safe_monitoring_text(msg)
    safe_details = [_safe_monitoring_text(line) for line in detail_lines]
    _fail(
        f"{safe_message}\n" + "\n".join(safe_details) + f" | {perfdata}",
        exit_code,
    )


def _apply_baseline(
    context: ScanContext,
    response_scan: dict[str, Any],
    *,
    hardenings: list[str],
    waived: list[str],
    message: str,
    exit_code: NagiosExitCode,
) -> tuple[str, NagiosExitCode, list[str], Comparison | None]:
    """
    Compare this run against the last one and record it.

    With ``--warn-on-new`` an unchanged picture stops alerting, so that a
    problem someone is already working on does not page anyone a second time.
    Anything new, a worse rating, and a release past its end of life all keep
    their original status - see opencloud_local_scan.baseline for why.

    A baseline that cannot be written is reported as a line of output and
    nothing more: it would be absurd for a bookkeeping failure to change the
    verdict on the instance.
    """
    if not context.baseline_path:
        return message, exit_code, [], None

    # Loading, comparing and saving form one read-modify-write operation; two
    # host workers must not overwrite one another's snapshots.
    with _BASELINE_LOCK:
        store = load_baseline(context.baseline_path)
        current = snapshot_of(response_scan, waived=waived, missing_hardenings=hardenings)
        comparison = store.compare(context.host, current)

        lines = [f"Baseline: {comparison.summary()}", comparison.render(context.diff_format)]
        if context.warn_on_new and not comparison.regressed and exit_code is not NagiosExitCode.OK:
            lines.append(
                f"Suppressed by --warn-on-new: this run would otherwise be {exit_code.name} "
                f"({message})"
            )
            message = f"OK: nothing new since the last run ({exit_code.name} state unchanged)."
            exit_code = NagiosExitCode.OK

        store.record(context.host, current)
        try:
            store.save()
        except BaselineError as exc:
            LOGGER.debug("Baseline not written: %s", exc)
            lines.append(f"Baseline could not be written: {exc}")

    return message, exit_code, lines, comparison


def _self_update_line(context: ScanContext) -> str | None:
    """
    Report a newer published version of the plugin itself, as a note.

    Never touches the exit code: whether PyPI answered says nothing about the
    health of the instance being monitored.
    """
    if not context.self_update_check:
        return None
    try:
        return self_update_note(__version__)
    except OSError as exc:  # pragma: no cover - defensive
        LOGGER.debug("Self-update check failed: %s", exc)
        return None


def _resolve_update_info(
    context: ScanContext, response_scan: dict[str, Any]
) -> UpdateInfo | None:
    """
    Determine the update state of the instance.

    The scan result normally carries the answer already; the fallback exists
    for callers that hand in a result document produced elsewhere.
    """
    if not context.update_check:
        return None

    embedded = response_scan.get("updates")
    if isinstance(embedded, dict):
        return UpdateInfo(
            available=embedded.get("available"),
            version=embedded.get("version"),
            available_version=embedded.get("availableVersion"),
            released_at=embedded.get("releasedAt"),
            source=str(embedded.get("source") or "unknown"),
            error=embedded.get("error"),
            track=embedded.get("track"),
            newest_release=embedded.get("newestRelease"),
        )

    settings = context.release_settings
    if settings is None or settings.effective_mode() == "off":
        return None
    return fetch_update_info(settings, response_scan.get("version"))


def _webhook_should_fire(context: ScanContext, exit_code: NagiosExitCode) -> bool:
    """Decide whether the configured webhook applies to this result."""
    if not context.webhook_url:
        return False
    return exit_code in WEBHOOK_TRIGGERS.get(context.webhook_on, frozenset())


def _build_base_payload(
    context: ScanContext, message: str, exit_code: NagiosExitCode
) -> dict[str, Any]:
    """Build the fields every webhook payload carries, regardless of outcome."""
    return {
        "plugin": "check-opencloud-security",
        "plugin_version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": context.host,
        "status": exit_code.name,
        "exit_code": int(exit_code),
        "message": message,
    }


def _build_webhook_payload(
    context: ScanContext,
    *,
    scan_result: ScanResult,
    response_scan: dict[str, Any],
    message: str,
    exit_code: NagiosExitCode,
    rating: int,
    rate: str,
    vulnerabilities: list[dict[str, Any]],
    missing_hardenings: list[str],
    duration_seconds: float | None,
    update_info: UpdateInfo | None = None,
    extra_failures: list[str] | None = None,
    baseline_diff: Comparison | None = None,
) -> dict[str, Any]:
    """
    Build the JSON document posted to the webhook.

    The payload is intentionally flat and self-describing so it can be
    consumed by generic receivers (alertmanager bridges, chat bots, ticket
    systems) without needing to parse the plugin's human-readable output.
    """
    payload = {
        **_build_base_payload(context, message, exit_code),
        "rating": rating,
        "rating_label": rate,
        "product": response_scan.get("product"),
        "product_version": response_scan.get("version"),
        "domain": response_scan.get("domain"),
        "scanned_at": response_scan.get("scannedAt", {}).get("date"),
        "eol": bool(response_scan.get("EOL")) or rating == MIN_RATING,
        "release_type": response_scan.get("releaseType"),
        "lifecycle": _lifecycle(response_scan) or None,
        "vulnerability_count": len(vulnerabilities),
        "vulnerabilities": [
            entry.get("id") for entry in vulnerabilities if isinstance(entry, dict)
        ],
        # Only the measures an administrator can act on, matching the alert
        # text and the hardenings_missing metric.
        "missing_hardenings": missing_hardenings if context.check_hardening else [],
        "failed_extra_checks": extra_failures or [],
        "scan_backend": "local",
        "scan_uuid": scan_result.uuid,
        "update": update_info.as_dict() if update_info is not None else None,
        "duration_seconds": round(duration_seconds, 3) if duration_seconds is not None else None,
    }
    if baseline_diff is not None:
        payload["baseline_diff"] = baseline_diff.as_dict()
        if context.diff_format in {"slack", "json"}:
            slack = baseline_diff.slack_blocks()
            payload["blocks"] = slack["blocks"]
            payload["attachments"] = slack["attachments"]
    return payload


# Matches the adapter script documented in docs/webhook-recipes.md, so
# switching from that adapter to --webhook-format slack/discord changes
# nothing a reader of the notification would notice.
_WEBHOOK_STATUS_COLORS = {
    "OK": "#2eb886",
    "WARNING": "#daa038",
    "CRITICAL": "#a30200",
    "UNKNOWN": "#767676",
}


def _webhook_status_line(payload: dict[str, Any]) -> str:
    """One human-readable line, shared by every chat-native webhook format."""
    text = f"*{payload.get('host', '?')}* - {payload.get('status', 'UNKNOWN')}\n{payload.get('message', '')}"
    if payload.get("rating_label"):
        text += (
            f"\nRating {payload['rating_label']}, "
            f"OpenCloud {payload.get('product_version') or '?'}"
        )
    return text


def _slack_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Render the result as a Slack Block Kit attachment.

    Mattermost accepts this shape directly, and the common Matrix webhook
    bridges (matrix-hookshot's outbound webhook connector) accept it too -
    there is no single native Matrix webhook contract to target instead.
    """
    color = _WEBHOOK_STATUS_COLORS.get(str(payload.get("status")), "#767676")
    return {"attachments": [{"color": color, "text": _webhook_status_line(payload)}]}


def _discord_field(name: str, value: object) -> dict[str, Any] | None:
    return {"name": name, "value": str(value), "inline": True} if value else None


def _discord_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Render the result as a single Discord webhook embed."""
    color = _WEBHOOK_STATUS_COLORS.get(str(payload.get("status")), "#767676")
    update = payload.get("update") or {}
    fields = [
        field
        for field in (
            _discord_field("Rating", payload.get("rating_label")),
            _discord_field("OpenCloud version", payload.get("product_version")),
            _discord_field("Update available", update.get("availableVersion")),
        )
        if field is not None
    ]
    return {
        "embeds": [
            {
                "title": f"{payload.get('host', '?')} - {payload.get('status', 'UNKNOWN')}",
                "description": payload.get("message", ""),
                "color": int(color.lstrip("#"), 16),
                "fields": fields,
            }
        ]
    }


_WEBHOOK_FORMATTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "slack": _slack_webhook_payload,
    "discord": _discord_webhook_payload,
}


def _format_webhook_body(context: ScanContext, payload: dict[str, Any]) -> dict[str, Any]:
    """
    The JSON body actually POSTed, in the format the operator selected.

    The 'generic' default - the plugin's own flat document - is unchanged
    from before this option existed; every other format is opt-in.
    """
    formatter = _WEBHOOK_FORMATTERS.get(context.webhook_format)
    return formatter(payload) if formatter is not None else payload


def _send_webhook(context: ScanContext, payload: dict[str, Any]) -> bool:
    """
    POST the payload to the configured webhook URL.

    Delivery is best-effort: a failing webhook is logged but never changes the
    check's own state, because the monitoring result must stay truthful about
    the OpenCloud instance rather than about the notification channel.
    """
    url = context.webhook_url
    if not url:
        return True
    
    validated_ip: str | None = None
    if not context.allow_private_webhooks:
        is_safe, validated_ip = _resolve_and_validate_webhook_url(url)
        if not is_safe:
            LOGGER.warning(
                "Webhook URL points to a restricted private/local IP address "
                "and was blocked: %s",
                _redact_url(url),
            )
            return False

    body = _format_webhook_body(context, payload)

    headers = {"Content-Type": "application/json"}
    headers.update(dict(context.webhook_headers))

    if context.webhook_secret:
        # Signed over what is actually sent: a receiver verifying the
        # signature has to verify the body it received, not a document that
        # was only ever an intermediate step for a chat-native format.
        body_json = json.dumps(body, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(
            context.webhook_secret.encode("utf-8"),
            body_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-COS-Signature"] = f"sha256={signature}"

    LOGGER.debug(
        "Posting %s webhook for %s to %s",
        payload["status"],
        context.host,
        _redact_url(url),
    )

    def _post() -> None:
        if not context.allow_private_webhooks and _webhook_address_has_changed(
            url, validated_ip
        ):
            raise ValueError(
                "Webhook URL DNS resolution changed between validation and delivery "
                "(possible DNS rebinding attack); webhook blocked"
            )

        response = requests.post(
            url,
            json=body,
            headers=headers,
            proxies=_proxies(context),
            timeout=context.webhook_timeout,
        )
        response.raise_for_status()

    try:
        _call_with_retry(
            _post,
            retries=context.retries,
            backoff_factor=context.backoff_factor,
            description=f"Webhook notification for {context.host}",
        )
    except REQUEST_ERRORS as exc:
        LOGGER.warning("Webhook notification for %s failed: %s", context.host, exc)
        LOGGER.debug("Webhook failure detail", exc_info=True)
        return False

    LOGGER.debug("Webhook notification for %s delivered", context.host)
    return True


def _redact_url(url: str) -> str:
    """Scheme and host only.

    A webhook URL is routinely the credential itself - the token sits in the
    path or the query of a chat provider's endpoint - so the whole of it must
    never reach a log file that is read by more people than the secret is.
    """
    parts = urlsplit(url)
    if not parts.hostname:
        return "<redacted>"
    host = parts.hostname
    if parts.port:
        host = f"{host}:{parts.port}"
    return f"{parts.scheme}://{host}/<redacted>"


def _resolve_webhook_address(url: str) -> str | None:
    """Resolve webhook URL to an IP address, or None if unresolvable/invalid."""
    try:
        hostname = urlsplit(url).hostname
        if not hostname:
            return None
        return socket.gethostbyname(hostname)
    except (ValueError, socket.gaierror):
        return None


def _resolve_and_validate_webhook_url(url: str) -> tuple[bool, str | None]:
    """
    Validate that a webhook URL is safe and return the resolved IP.
    
    Returns (is_safe, resolved_ip) where:
    - is_safe: True if the address is not private/loopback/link-local
    - resolved_ip: The resolved IP address string, or None if unresolvable
    """
    resolved_ip = _resolve_webhook_address(url)
    if not resolved_ip:
        return False, None
    
    try:
        address = ipaddress.ip_address(resolved_ip)
        is_safe = not (address.is_private or address.is_loopback or address.is_link_local)
        return is_safe, resolved_ip
    except ValueError:
        return False, None


def _is_safe_webhook_url(url: str) -> bool:
    """Return whether url resolves to an address that is safe for a webhook."""
    is_safe, _ = _resolve_and_validate_webhook_url(url)
    return is_safe


def _webhook_address_has_changed(url: str, original_ip: str | None) -> bool:
    """
    Check if a webhook URL's DNS resolution has changed since validation.

    Returns True if DNS has changed (rebinding attack detected or resolution failed).
    Returns False if the address is the same.
    This mitigates DNS rebinding attacks by detecting when a hostname resolves to
    a different IP address between validation and actual webhook delivery.
    """
    current_ip = _resolve_webhook_address(url)
    return current_ip != original_ip


def _notify_and_fail(
    context: ScanContext,
    message: str,
    exit_code: NagiosExitCode = NagiosExitCode.UNKNOWN,
) -> NoReturn:
    """
    Fire the webhook (if configured for this state) and then terminate.

    Used for aborts that happen before a scan result exists, so that an
    unreachable instance can raise an alert just like a vulnerable one.
    """
    if _webhook_should_fire(context, exit_code):
        payload = _build_base_payload(context, message, exit_code)
        if not _send_webhook(context, payload):
            _fail(
                _safe_monitoring_text(message)
                + "\nWebhook delivery failed (see debug log)",
                exit_code,
            )
    _fail(_safe_monitoring_text(message), exit_code)


def _evaluate_rating(
    context: ScanContext,
    response_scan: dict[str, Any],
    rating: int,
    num_vulns: int,
) -> tuple[str, NagiosExitCode]:
    """
    Map a scan rating and vulnerability count onto a Nagios state.

    The rating thresholds (context.warning_rating / context.critical_rating)
    are inclusive: a rating at or below the threshold triggers that state.
    Known vulnerabilities always raise the state to at least WARNING, even
    when the rating itself still looks acceptable.
    """
    if rating not in RATE_MAP:
        return "UNKNOWN: Scan result unclear. Please verify manually.", NagiosExitCode.UNKNOWN

    rate = RATE_MAP[rating]
    is_eol = bool(response_scan.get("EOL")) or rating == MIN_RATING

    if is_eol:
        lifecycle = _lifecycle(response_scan)
        track = str(lifecycle.get("releaseType") or "")
        target = str(lifecycle.get("upgradeTo") or "")
        line = str(lifecycle.get("line") or "")
        described = f"The {line} {track} release line".strip() if line else "This server version"
        upgrade = f" Upgrade to {target}." if target else ""
        return (
            f"CRITICAL: {described} is end-of-life and has no security fixes.{upgrade}",
            NagiosExitCode.CRITICAL,
        )

    if rating <= context.critical_rating:
        if num_vulns:
            return (
                f"CRITICAL: Found {num_vulns} vulnerabilities (rating {rate}).",
                NagiosExitCode.CRITICAL,
            )
        return (
            (
                f"CRITICAL: Rating {rate} is at or below the critical threshold "
                f"{RATE_MAP[context.critical_rating]}."
            ),
            NagiosExitCode.CRITICAL,
        )

    if num_vulns:
        return (
            f"WARNING: Found {num_vulns} vulnerabilities (rating {rate}).",
            NagiosExitCode.WARNING,
        )

    if rating <= context.warning_rating:
        return (
            (
                f"WARNING: Rating {rate} is at or below the warning threshold "
                f"{RATE_MAP[context.warning_rating]}, but no known vulnerabilities."
            ),
            NagiosExitCode.WARNING,
        )

    if rating == MAX_RATING:
        return "OK: Server is up to date. No known vulnerabilities.", NagiosExitCode.OK
    return "OK: Update available, but no known vulnerabilities.", NagiosExitCode.OK


def _format_vulnerabilities(vulnerabilities: list[dict[str, Any]], limit: int = 5) -> str:
    """Summarize vulnerability identifiers, truncating long lists."""
    names = [
        str(entry.get("id") or entry.get("cwe") or "unnamed")
        for entry in vulnerabilities
        if isinstance(entry, dict)
    ]
    shown = names[:limit]
    remaining = len(names) - len(shown)
    summary = ", ".join(shown) if shown else "details unavailable"
    return f"{summary} (+{remaining} more)" if remaining > 0 else summary


def _lifecycle(response_scan: dict[str, Any]) -> dict[str, Any]:
    """Return the lifecycle section of a scan result, or an empty mapping."""
    lifecycle = response_scan.get("lifecycle")
    return lifecycle if isinstance(lifecycle, dict) else {}


def _support_days_left(response_scan: dict[str, Any]) -> int | None:
    """Days until the instance's release line stops receiving fixes."""
    remaining = _lifecycle(response_scan).get("daysRemaining")
    return remaining if isinstance(remaining, int) else None


def _schedule_note(response_scan: dict[str, Any]) -> str | None:
    """
    Say so when the bundled release schedule is older than the instance.

    A schedule that ships inside a package is a snapshot of a page that keeps
    moving, so an instance can perfectly well be newer than the file it is
    compared against. That is never held against it - the note says as much -
    but it has to be visible, because a support window worked out from stale
    data is worth re-reading at the source.
    """
    note = _lifecycle(response_scan).get("scheduleNote")
    return f"Release schedule: {note}" if isinstance(note, str) and note else None


def _format_lifecycle(response_scan: dict[str, Any]) -> str | None:
    """
    Describe where the instance stands in the OpenCloud release lifecycle.

    OpenCloud maintains rolling, production and LTS releases side by side and
    each has its own support window, so the release type is at least as
    interesting as the version number itself.
    """
    lifecycle = _lifecycle(response_scan)
    track = lifecycle.get("releaseType")
    if not track:
        reason = lifecycle.get("reason")
        return f"Release lifecycle: unknown ({reason})" if reason else None

    line = lifecycle.get("line") or "?"
    declared = lifecycle.get("declaredTrack")
    if declared == TRACK_AUTO:
        origin = ", track detected"
    elif declared and declared != track:
        # The instance runs a release of a different track than the one it
        # follows; naming both is the only way that reads honestly.
        origin = f", {declared} track declared"
    elif declared:
        origin = " track declared"
    else:
        origin = ""
    parts = [f"Release lifecycle: {line} ({track}{origin})"]

    end_of_life = lifecycle.get("endOfLife")
    remaining = lifecycle.get("daysRemaining")
    state = lifecycle.get("state")
    reason = str(lifecycle.get("reason") or "")
    if state == "endOfLife":
        # A version that was never published on the declared track has no end
        # of support date of its own; the reason carries the explanation.
        parts.append(
            f"out of support since {end_of_life}" if end_of_life else (reason or "not supported")
        )
    elif state == "unknown":
        parts.append(reason or "support state unknown")
    elif reason.startswith("ahead of the "):
        # Running newer code than the declared track ships is a choice, not a
        # problem, but it must not be reported as "current" on that track.
        parts.append(reason)
    elif end_of_life and isinstance(remaining, int):
        parts.append(f"supported until {end_of_life} ({remaining} days left)")
    else:
        parts.append("current release")

    target = lifecycle.get("upgradeTo")
    if target:
        parts.append(f"upgrade to {target}")
    return ", ".join(parts)


def _collect_missing_hardenings(
    response_scan: dict[str, Any], *, actionable_only: bool = False
) -> list[str]:
    """
    List the hardening measures the scanner reported as absent.

    Covers the 'hardenings' block (HSTS quality, CSP without 'unsafe-inline',
    basic auth disabled, public link policies, ...), the security-related
    response headers under 'setup.headers', and whether HTTPS is enforced.

    With ``actionable_only``, flags that OpenCloud hardcodes are left out.
    ``publicLinkExpirationEnforced`` is the reason this option exists: every
    instance reports it as missing and no setting can change that, so alerting
    on it trains operators to ignore the hardening line altogether.
    """
    missing: list[str] = []

    hardenings = response_scan.get("hardenings")
    if isinstance(hardenings, dict):
        missing.extend(name for name, enabled in sorted(hardenings.items()) if not enabled)

    setup = response_scan.get("setup")
    if isinstance(setup, dict):
        https = setup.get("https")
        if isinstance(https, dict) and not https.get("enforced", True):
            missing.append("httpsEnforced")

        headers = setup.get("headers")
        if isinstance(headers, dict):
            missing.extend(name for name, enabled in sorted(headers.items()) if not enabled)

    if actionable_only:
        return [name for name in missing if is_actionable(name)]
    return missing


def _waived(response_scan: dict[str, Any]) -> list[str]:
    """List the measures and checks the operator has chosen to accept."""
    ignored = response_scan.get("ignored")
    if not isinstance(ignored, list):
        return []
    return [str(name) for name in ignored]


def _explain_lines(
    context: ScanContext,
    response_scan: dict[str, Any],
    missing_hardenings: list[str],
    extra_failures: list[str],
) -> list[str]:
    """
    Spell out how the rating was reached and what each finding means.

    The plugin normally prints identifiers, which is what a monitoring system
    wants but not what a human debugging one wants. This is the long form:
    the arithmetic behind the rating, then a paragraph per finding naming the
    OpenCloud setting that governs it.
    """
    lines: list[str] = ["", "--- Why this rating ---"]

    explanation = response_scan.get("ratingExplanation")
    if isinstance(explanation, dict):
        base = explanation.get("base")
        if isinstance(base, dict):
            lines.append(
                f"Starting point: {base.get('rating')}/5 - {base.get('reason')}"
            )
        for cap in explanation.get("caps") or []:
            if not isinstance(cap, dict):
                continue
            verdict = (
                f"caps the rating at {cap.get('cap')}/5"
                if cap.get("applied")
                else f"would cap at {cap.get('cap')}/5, but the rating was already lower"
            )
            detail = f" - {cap.get('detail')}" if cap.get("detail") else ""
            lines.append(
                f"Failed check {cap.get('check')} [{cap.get('severity')}] {verdict}{detail}"
            )
        if not explanation.get("caps"):
            lines.append("No failed additional check lowered the rating.")
    else:
        lines.append("The scan result carries no rating explanation.")

    rating = response_scan.get("rating", -1)
    lines.append(
        f"Final rating: {rating}/5 ({RATE_MAP.get(rating, 'Unknown')}). "
        f"WARNING at or below {RATE_MAP.get(context.warning_rating, '?')}, "
        f"CRITICAL at or below {RATE_MAP.get(context.critical_rating, '?')}."
    )
    if not context.check_hardening:
        lines.append(
            "Hardening measures are observed but not reported (--check-hardening is off)."
        )

    lines.extend(_remediation_lines(response_scan))

    waived = _waived(response_scan)
    if waived:
        lines.append("")
        lines.append("--- Ignored by configuration ---")
        lines.append(
            "These were observed as failing but are accepted, so they neither "
            "raise an alert nor lower the rating: " + ", ".join(waived)
        )

    if missing_hardenings:
        lines.append("")
        lines.append("--- Missing hardening measures ---")
        for name in missing_hardenings:
            marker = " [ignored by configuration]" if name in waived else ""
            lines.append(describe_hardening(name).describe() + marker)

    unexplained = [name for name in extra_failures if name not in missing_hardenings]
    if unexplained:
        lines.append("")
        lines.append("--- Failed additional checks ---")
        details = {
            str(check.get("id")): str(check.get("detail") or "")
            for check in response_scan.get("extraChecks") or []
            if isinstance(check, dict)
        }
        for name in unexplained:
            detail = details.get(name) or "no further detail reported"
            marker = " [ignored by configuration]" if name in waived else ""
            lines.append(f"{name}: {detail}{marker}")

    # The performance data is appended to the last line of the output, so the
    # block deliberately ends on a short sentence rather than a long URL.
    lines.append("--- end of explanation ---")
    return lines


def _remediation_lines(response_scan: dict[str, Any]) -> list[str]:
    """
    The ordered fix list, with the letters this layer is responsible for.

    The scanner worked the order and the predicted ratings out while it was
    rating the instance; the only thing added here is the grade each number
    maps to, because turning a number into a letter is a judgement and
    judgements are this file's job.
    """
    plan = response_scan.get("remediationPlan")
    if not isinstance(plan, dict) or not plan.get("steps"):
        return []

    lines = ["", "--- What would raise the rating ---", str(plan.get("summary") or "")]
    for step in plan["steps"]:
        if not isinstance(step, dict):
            continue
        after = step.get("ratingAfter")
        grade = RATE_MAP.get(after, "?") if isinstance(after, int) else "?"
        moves = (step.get("ratingGain") or 0) > 0
        outcome = f"then {after}/5 ({grade})" if moves else f"still {after}/5 ({grade})"
        lines.append(
            f"{step.get('order')}. {step.get('id')} [{step.get('severity')}] - {outcome}"
        )
        lines.append(f"    {step.get('title')}")
        if step.get("detail"):
            lines.append(f"    Observed: {step['detail']}")
        lines.append(f"    Fix: {step.get('action')}")
    for step in plan.get("blocked") or []:
        if isinstance(step, dict):
            lines.append(
                f"Not fixable: {step.get('id')} - OpenCloud hardcodes this, so "
                "the plan above cannot reach further."
            )
    return lines


def _build_perfdata(
    rating: int,
    rate_map: dict[int, str],
    num_vulns: int,
    duration_seconds: float | None,
    context: ScanContext | None = None,
    missing_hardenings: int | None = None,
    failed_extra_checks_count: int | None = None,
    update_available: bool | None = None,
    support_days_left: int | None = None,
) -> str:
    """
    Build a Nagios/Icinga performance data string.

    Format reference: 'label'=value[UOM];[warn];[crit];[min];[max]
    See https://nagios-plugins.org/doc/guidelines.html#AEN200

    The rating metric carries the configured warning/critical thresholds so
    that graphing frontends can render them alongside the measured value.
    """
    rating_value = str(rating) if rating in rate_map else "U"
    # Nagios range syntax: '@start:end' means "alert when inside the range",
    # which matches our inclusive at-or-below-threshold semantics.
    warn = f"@{MIN_RATING}:{context.warning_rating}" if context else ""
    crit = f"@{MIN_RATING}:{context.critical_rating}" if context else ""
    parts = [
        f"rating={rating_value};{warn};{crit};0;5",
        f"vulnerabilities={num_vulns};;;0;",
    ]
    if duration_seconds is not None:
        parts.append(f"time={duration_seconds:.3f}s;;;0;")
    if missing_hardenings is not None:
        parts.append(f"hardenings_missing={missing_hardenings};;;0;")
    if failed_extra_checks_count is not None:
        parts.append(f"extra_checks_failed={failed_extra_checks_count};;;0;")
    if update_available is not None:
        parts.append(f"update_available={int(update_available)};;;0;1")
    if support_days_left is not None:
        # No min: the value goes negative once the release line is out of
        # support, which is exactly what an operator wants to see on a graph.
        parts.append(f"support_days_left={support_days_left};;;;")
    return " ".join(parts)


# --- Main ---
def build_arg_parser() -> argparse.ArgumentParser:
    """
    Build and return the command-line argument parser.

    Every option can also be supplied via a COS_-prefixed environment
    variable (e.g. COS_HOST, COS_PROXY). An explicit command-line flag
    always takes precedence over its environment variable counterpart.
    """
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=__doc__,
    )

    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}\nhttps://github.com/sowoi/check-opencloud-security",
    )
    parser.add_argument(
        "--configure",
        action="store_true",
        default=False,
        help=(
            "Ask for the settings this check needs, explaining each one, and save "
            "them as JSON. Only required settings are asked for; optional ones "
            "are offered group by group and skipped with Enter. The file is "
            "found automatically afterwards. Combine with --config to choose "
            "where it is written."
        ),
    )
    parser.add_argument(
        "--upgrade-self",
        nargs="?",
        const=UPGRADE_RUN,
        default=None,
        choices=(UPGRADE_RUN, UPGRADE_CHECK),
        metavar="{run,check}",
        help=(
            "Upgrade this program with whichever tool installed it (pipx, uv or "
            "pip) and exit. '--upgrade-self=check' only prints the command that "
            "would run, and changes nothing."
        ),
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=_env_bool("DEBUG"),
        help=f"Enable debug mode. Default: False (env: {ENV_PREFIX}DEBUG).",
    )
    parser.add_argument(
        "-H",
        "--host",
        required=_env("HOST") is None,
        default=_env("HOST"),
        help=(
            "OpenCloud server address (hostname or IP, optionally with a port). "
            "Accepts a comma-separated list (e.g. 'a.example.com,b.example.com') "
            f"to check multiple hosts in one run. Required, env: {ENV_PREFIX}HOST."
        ),
    )
    parser.add_argument(
        "-P",
        "--proxy",
        default=_env("PROXY"),
        help=f"Proxy server address. Default: None (env: {ENV_PREFIX}PROXY).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Path to a configuration file ('.json' is read as JSON, anything else "
            "as YAML). Default: the first existing file of ./.env.json, "
            "./check-opencloud-security.yml, ~/.config/check-opencloud-security/.env.json "
            "or /etc/check-opencloud-security/ (env: "
            f"{ENV_PREFIX}CONFIG_FILE). With --configure, where to save."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            "Port the instance listens on. Default: taken from --host, otherwise "
            f"443 (env: {ENV_PREFIX}SCANNER_TARGET_PORT). OpenCloud's own proxy "
            "usually listens on 9200."
        ),
    )
    parser.add_argument(
        "--scheme",
        choices=("https", "http"),
        default=None,
        help=(
            "Scheme used to reach the instance. Default: https, with an automatic "
            f"fallback to http (env: {ENV_PREFIX}SCANNER_SCHEME)."
        ),
    )
    parser.add_argument(
        "--no-extra-checks",
        action="store_true",
        default=_env_bool("NO_EXTRA_CHECKS"),
        help=(
            "Only check product, version and security headers, skipping the "
            "additional TLS, exposure, debug and authentication checks. "
            f"Default: False (env: {ENV_PREFIX}NO_EXTRA_CHECKS)."
        ),
    )
    parser.add_argument(
        "--ignore-hardening",
        action="append",
        default=None,
        metavar="NAME",
        help=(
            "Hardening measure or additional check to accept and stop alerting "
            "on, e.g. 'cspWithoutUnsafeInline'. Repeatable, also accepts a "
            "comma-separated list, and shell-style wildcards such as "
            "'debugPort:*'. A waived check no longer lowers the rating. "
            f"Default: none (env: {ENV_PREFIX}SCANNER_IGNORE_HARDENINGS)."
        ),
    )
    parser.add_argument(
        "--release-track",
        choices=sorted(RELEASE_TRACK_CHOICES),
        default=None,
        help=(
            "The OpenCloud release track this instance follows. Determines how "
            "long its release is supported and which release it is told to "
            "upgrade to. 'auto' asks the release schedule which track the "
            f"installed release belongs to. Default: {TRACK_AUTO} "
            f"(env: {ENV_PREFIX}SCANNER_RELEASE_TRACK)."
        ),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=_env_bool("INSECURE"),
        help=(
            "Do not verify the TLS certificate of the scanned instance. OpenCloud "
            "self-signs by default, so this is common for internal instances; the "
            "untrusted chain is still reported, it just stops counting against the "
            f"rating. Default: False (env: {ENV_PREFIX}INSECURE)."
        ),
    )
    parser.add_argument(
        "--ca-file",
        default=None,
        help=(
            "PEM CA bundle used to verify an internal TLS certificate. "
            f"Default: scanner.tls_ca_file (env: {ENV_PREFIX}SCANNER_TLS_CA_FILE)."
        ),
    )
    parser.add_argument(
        "--no-debug-ports",
        action="store_true",
        default=_env_bool("NO_DEBUG_PORTS"),
        help=(
            "Skip probing the OpenCloud debug ports (9205, 9141, 9124, 9134, 9239). "
            f"Default: False (env: {ENV_PREFIX}NO_DEBUG_PORTS)."
        ),
    )
    parser.add_argument(
        "--update-source",
        choices=UPDATE_SOURCES,
        default=_env("UPDATE_SOURCE"),
        help=(
            "Where the newest OpenCloud release is looked up: 'feed' (the GitHub "
            "release feed), 'pinned' (the version given with --latest-version), "
            "'bundled' (the release recorded in the shipped data file, fully "
            "offline), 'off', or 'auto' to pick whichever is configured. "
            f"Default: auto (env: {ENV_PREFIX}UPDATE_SOURCE)."
        ),
    )
    parser.add_argument(
        "--release-feed",
        default=None,
        help=(
            "URL of the release feed used with --update-source feed. Default: the "
            "GitHub releases API of opencloud-eu/opencloud "
            f"(env: {ENV_PREFIX}RELEASES_FEED_URL)."
        ),
    )
    parser.add_argument(
        "--release-token",
        default=None,
        help=(
            "Bearer token for the release feed, useful against GitHub's "
            f"unauthenticated rate limit (env: {ENV_PREFIX}RELEASES_TOKEN, "
            "supports secret:// references)."
        ),
    )
    parser.add_argument(
        "--latest-version",
        default=None,
        help=(
            "Newest OpenCloud release, given explicitly instead of being looked "
            f"up. Implies --update-source pinned (env: {ENV_PREFIX}RELEASES_LATEST_VERSION)."
        ),
    )
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        default=_env_bool("NO_UPDATE_CHECK"),
        help=(
            "Never look up the newest release. Equivalent to --update-source off. "
            f"Default: False (env: {ENV_PREFIX}NO_UPDATE_CHECK)."
        ),
    )
    parser.add_argument(
        "--update-warning",
        action="store_true",
        default=_env_bool("UPDATE_WARNING"),
        help=(
            "Report WARNING when a newer OpenCloud release is available. "
            f"Default: False (env: {ENV_PREFIX}UPDATE_WARNING)."
        ),
    )
    parser.add_argument(
        "--baseline",
        default=_env("BASELINE"),
        metavar="PATH",
        help=(
            "Remember the findings of this run in PATH and report what changed "
            "since the last one. One entry per host, so a single file can serve "
            "a whole --host list. "
            f"Example: /var/lib/check_opencloud/baseline.json (env: {ENV_PREFIX}BASELINE)."
        ),
    )
    parser.add_argument(
        "--warn-on-new",
        action="store_true",
        default=_env_bool("WARN_ON_NEW"),
        help=(
            "Only alert when something is new or worse than in the baseline. "
            "Requires --baseline. A release past its end of life always alerts. "
            f"Default: False (env: {ENV_PREFIX}WARN_ON_NEW)."
        ),
    )
    parser.add_argument(
        "--diff-format",
        choices=("text", "markdown", "slack", "json"),
        default=_env("DIFF_FORMAT") or "text",
        help=(
            "Render baseline changes as concise text, Markdown, or Slack Block Kit JSON. "
            f"Default: text (env: {ENV_PREFIX}DIFF_FORMAT)."
        ),
    )
    parser.add_argument(
        "--self-update-check",
        action="store_true",
        default=_env_bool("SELF_UPDATE_CHECK"),
        help=(
            "Add a note when a newer version of this plugin is published on "
            "PyPI. Cached for a day and never changes the exit code. "
            f"Default: False (env: {ENV_PREFIX}SELF_UPDATE_CHECK)."
        ),
    )
    parser.add_argument(
        CHECK_ONLY_FLAG,
        action="store_true",
        help="Only valid with --upgrade-self: print the upgrade command without running it.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_env_int("CONCURRENCY", DEFAULT_HOST_CONCURRENCY),
        help=(
            "Maximum number of target hosts checked in parallel. One worker is "
            "used per host up to this ceiling; a single-host check stays "
            "single-threaded. "
            f"Default: {DEFAULT_HOST_CONCURRENCY} (env: {ENV_PREFIX}CONCURRENCY)."
        ),
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("nagios", "prometheus"),
        default=_env("FORMAT") or "nagios",
        help=(
            "Output format for a one-shot scan: 'nagios' or Prometheus text exposition. "
            f"Default: nagios (env: {ENV_PREFIX}FORMAT)."
        ),
    )
    parser.add_argument(
        "--prometheus-listen-port",
        type=int,
        default=_env_int("PROMETHEUS_LISTEN_PORT", 0),
        metavar="PORT",
        help=(
            "Serve Prometheus metrics on PORT until stopped; /metrics refreshes scans "
            f"after --scrape-interval (env: {ENV_PREFIX}PROMETHEUS_LISTEN_PORT)."
        ),
    )
    parser.add_argument(
        "--prometheus-listen-addr",
        default=_env("PROMETHEUS_LISTEN_ADDR") or "127.0.0.1",
        metavar="ADDRESS",
        help=(
            "Address for the Prometheus exporter server. "
            f"Default: 127.0.0.1 (env: {ENV_PREFIX}PROMETHEUS_LISTEN_ADDR)."
        ),
    )
    parser.add_argument(
        "--scrape-interval",
        type=int,
        default=_env_int(
            "SCRAPE_INTERVAL", DEFAULT_PROMETHEUS_SCRAPE_INTERVAL_SECONDS
        ),
        metavar="SECONDS",
        help=(
            "Seconds to cache Prometheus scan results; 0 scans on every scrape. "
            f"Default: {DEFAULT_PROMETHEUS_SCRAPE_INTERVAL_SECONDS} "
            f"(env: {ENV_PREFIX}SCRAPE_INTERVAL)."
        ),
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=_env_int("RETRIES", DEFAULT_RETRIES),
        help=(
            f"Number of retry attempts for transient network errors. "
            f"Default: {DEFAULT_RETRIES} (env: {ENV_PREFIX}RETRIES)."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        # Left unset on purpose: a more specific 'scanner.timeout:' in the
        # configuration must not be overruled by a default nobody asked for.
        default=None,
        help=(
            f"HTTP timeout in seconds for each request. "
            f"Default: {DEFAULT_TIMEOUT_SECONDS} (env: {ENV_PREFIX}TIMEOUT)."
        ),
    )
    parser.add_argument(
        "-w",
        "--warning",
        type=int,
        default=_env_int("WARNING", DEFAULT_WARNING_RATING),
        help=(
            "Rating (0-5) at or below which the check reports WARNING. "
            f"Default: {DEFAULT_WARNING_RATING} ({RATE_MAP[DEFAULT_WARNING_RATING]}), "
            f"env: {ENV_PREFIX}WARNING."
        ),
    )
    parser.add_argument(
        "-c",
        "--critical",
        type=int,
        default=_env_int("CRITICAL", DEFAULT_CRITICAL_RATING),
        help=(
            "Rating (0-5) at or below which the check reports CRITICAL. "
            f"Default: {DEFAULT_CRITICAL_RATING} ({RATE_MAP[DEFAULT_CRITICAL_RATING]}), "
            f"env: {ENV_PREFIX}CRITICAL."
        ),
    )
    parser.add_argument(
        "--check-hardening",
        action="store_true",
        default=_env_bool("CHECK_HARDENING"),
        help=(
            "Also report hardening measures and security headers the scanner "
            "found missing, raising an otherwise OK result to WARNING. "
            f"Default: False (env: {ENV_PREFIX}CHECK_HARDENING)."
        ),
    )
    parser.add_argument(
        "--webhook-url",
        default=_env("WEBHOOK_URL"),
        help=(
            "Optional HTTP(S) endpoint that receives a JSON notification when the "
            "check reaches the state selected by --webhook-on. Disabled when unset "
            f"(env: {ENV_PREFIX}WEBHOOK_URL)."
        ),
    )
    parser.add_argument(
        "--webhook-on",
        choices=sorted(WEBHOOK_TRIGGERS),
        default=_env("WEBHOOK_ON") or DEFAULT_WEBHOOK_ON,
        help=(
            "Lowest state that triggers the webhook: 'critical' only, 'warning' and "
            "worse, 'unknown' and worse, or 'always'. "
            f"Default: {DEFAULT_WEBHOOK_ON} (env: {ENV_PREFIX}WEBHOOK_ON)."
        ),
    )
    parser.add_argument(
        "--webhook-format",
        choices=("generic", "slack", "discord"),
        default=_env("WEBHOOK_FORMAT") or DEFAULT_WEBHOOK_FORMAT,
        help=(
            "Shape of the webhook body: the plugin's own flat JSON document "
            "('generic'), or a payload a Slack or Discord incoming webhook "
            "accepts directly. Mattermost and the common Matrix webhook "
            "bridges also accept 'slack'. "
            f"Default: {DEFAULT_WEBHOOK_FORMAT} (env: {ENV_PREFIX}WEBHOOK_FORMAT)."
        ),
    )
    parser.add_argument(
        "--webhook-header",
        action="append",
        default=None,
        metavar="NAME:VALUE",
        help=(
            "Extra HTTP header for the webhook request, e.g. "
            "'X-Auth-Token: <token>'. May be given multiple times "
            f"(env: {ENV_PREFIX}WEBHOOK_HEADERS, entries separated by ';')."
        ),
    )
    parser.add_argument(
        "--webhook-timeout",
        type=int,
        default=_env_int("WEBHOOK_TIMEOUT", DEFAULT_WEBHOOK_TIMEOUT_SECONDS),
        help=(
            f"HTTP timeout in seconds for the webhook call. "
            f"Default: {DEFAULT_WEBHOOK_TIMEOUT_SECONDS} (env: {ENV_PREFIX}WEBHOOK_TIMEOUT)."
        ),
    )
    parser.add_argument(
        "--webhook-secret",
        default=_env("WEBHOOK_SECRET"),
        help=(
            "Shared secret for signing webhook payloads with HMAC-SHA256. "
            "If set, the X-COS-Signature header is added to every webhook POST. "
            "The receiver must verify the signature using the same secret "
            f"(env: {ENV_PREFIX}WEBHOOK_SECRET)."
        ),
    )
    parser.add_argument(
        "--allow-private-webhooks",
        action="store_true",
        default=_allow_private_webhooks_default(),
        help=(
            "Allow webhooks to private, loopback, and link-local addresses. "
            f"Default: False (env: {ENV_PREFIX}ALLOW_PRIVATE_WEBHOOKS)."
        ),
    )
    parser.add_argument(
        "--backoff-factor",
        type=float,
        default=_env_float("BACKOFF_FACTOR", DEFAULT_BACKOFF_FACTOR),
        help=(
            f"Exponential backoff factor (in seconds) between retries. "
            f"Default: {DEFAULT_BACKOFF_FACTOR} (env: {ENV_PREFIX}BACKOFF_FACTOR)."
        ),
    )

    enable_completion(parser)
    return parser


def _parse_webhook_headers(raw_headers: list[str] | None) -> tuple[tuple[str, str], ...]:
    """
    Parse 'Name: value' header strings into a tuple of pairs.

    Falls back to the COS_WEBHOOK_HEADERS environment variable (entries
    separated by ';') when no --webhook-header flag was given. Entries without
    a colon are skipped with a warning rather than aborting the check.
    """
    entries = raw_headers
    if entries is None:
        env_value = _env("WEBHOOK_HEADERS")
        entries = env_value.split(";") if env_value else []

    headers: list[tuple[str, str]] = []
    for entry in entries:
        name, separator, value = entry.partition(":")
        if not separator or not name.strip():
            LOGGER.warning("Ignoring malformed webhook header %r (expected 'Name: value').", entry)
            continue
        headers.append((name.strip(), value.strip()))
    return tuple(headers)


def _validate_thresholds(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject rating thresholds outside 0-5 or with critical above warning."""
    for name in ("warning", "critical"):
        value = getattr(args, name)
        if not MIN_RATING <= value <= MAX_RATING:
            parser.error(
                f"--{name} must be a rating between {MIN_RATING} and {MAX_RATING}, got {value}."
            )
    if args.critical > args.warning:
        parser.error(
            f"--critical ({args.critical}) must not be higher than --warning ({args.warning})."
        )
    if args.timeout is not None and args.timeout <= 0:
        parser.error(f"--timeout must be a positive number of seconds, got {args.timeout}.")
    if args.webhook_timeout <= 0:
        parser.error(
            "--webhook-timeout must be a positive number of seconds, "
            f"got {args.webhook_timeout}."
        )
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error(f"--port must be between 1 and 65535, got {args.port}.")
    if args.concurrency is not None and not 1 <= args.concurrency <= MAX_CONCURRENCY:
        parser.error(
            f"--concurrency must be between 1 and {MAX_CONCURRENCY}, got {args.concurrency}."
        )
    if args.prometheus_listen_port and not 1 <= args.prometheus_listen_port <= 65535:
        parser.error(
            "--prometheus-listen-port must be between 1 and 65535, "
            f"got {args.prometheus_listen_port}."
        )
    if args.scrape_interval < 0:
        parser.error(f"--scrape-interval must not be negative, got {args.scrape_interval}.")
    if args.webhook_url and not args.webhook_url.lower().startswith(("http://", "https://")):
        parser.error(f"--webhook-url must be an http(s) URL, got {args.webhook_url!r}.")
    # A --warn-on-new with nowhere to remember the last run would report
    # "nothing new" forever without ever having compared anything.
    if args.warn_on_new and not args.baseline:
        parser.error("--warn-on-new needs --baseline PATH to compare this run against.")
    if args.check_only:
        parser.error(
            f"{CHECK_ONLY_FLAG} is only meaningful together with --upgrade-self "
            f"(use: --upgrade-self {CHECK_ONLY_FLAG}, or --upgrade-self=check)."
        )


def _normalise_host(raw: str) -> str:
    """
    Reduce a --host value to the bare host (optionally with a port).

    A full URL is a natural thing to paste, so 'https://cloud.example.com/'
    and 'cloud.example.com' are treated alike. Credentials, path, query and
    fragment are dropped; the port is kept, because OpenCloud's own proxy
    listens on 9200 rather than on 443.
    """
    host = raw.strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    # Drop path, query and fragment, but keep a bracketed IPv6 literal intact.
    for separator in ("/", "?", "#"):
        head, sep, _ = host.partition(separator)
        if sep and not (separator == "/" and not head):
            host = head
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    return host.strip().rstrip(".")


def _parse_hosts(raw_host: str) -> list[str]:
    """
    Split a --host value into a list of hosts.

    Accepts a single hostname, a full URL or a comma-separated list (e.g.
    'a.example.com, https://b.example.com'). Blank entries (from stray commas
    or surrounding whitespace) are dropped.
    """
    hosts = [_normalise_host(part) for part in raw_host.split(",")]
    return [host for host in hosts if host]


def _build_context(host: str, args: argparse.Namespace) -> ScanContext:
    """Build a ScanContext for a single host from the parsed CLI arguments."""
    # A timeout given on the command line applies to everything; without one,
    # the scanner and the release check fall back to their own configuration.
    timeout = args.timeout if args.timeout is not None else _env_int(
        "TIMEOUT", DEFAULT_TIMEOUT_SECONDS
    )
    scanner_settings = scanner_settings_from_config(
        _CONFIG,
        timeout=args.timeout,
        proxy=args.proxy,
        scheme=args.scheme,
        port=args.port,
        extra_checks=False if args.no_extra_checks else None,
        verify_tls=False if args.insecure else None,
        tls_ca_file=args.ca_file,
        check_debug_ports=False if args.no_debug_ports else None,
        release_track=args.release_track,
        ignore_hardenings=_waiver_patterns(args.ignore_hardening),
    )
    mode = "off" if args.no_update_check else args.update_source
    if mode is None and args.latest_version:
        mode = "pinned"
    release_settings = release_settings_from_config(
        _CONFIG,
        mode=mode,
        feed_url=args.release_feed,
        latest_version=args.latest_version,
        token=args.release_token,
        timeout=args.timeout,
        proxy=args.proxy,
        verify_tls=False if args.insecure else None,
    )

    return ScanContext(
        host=host,
        proxy=args.proxy,
        debug=args.debug,
        retries=args.retries,
        backoff_factor=args.backoff_factor,
        timeout=timeout,
        warning_rating=args.warning,
        critical_rating=args.critical,
        check_hardening=args.check_hardening,
        webhook_url=args.webhook_url,
        webhook_on=args.webhook_on,
        webhook_format=args.webhook_format,
        webhook_timeout=args.webhook_timeout,
        webhook_secret=args.webhook_secret,
        allow_private_webhooks=args.allow_private_webhooks,
        webhook_headers=_parse_webhook_headers(args.webhook_header),
        scanner_settings=scanner_settings,
        release_settings=release_settings,
        update_check=not args.no_update_check,
        update_warning=args.update_warning,
        baseline_path=args.baseline,
        warn_on_new=args.warn_on_new,
        diff_format=args.diff_format,
        self_update_check=args.self_update_check,
    )


# Priority used to determine the overall (worst) status across multiple
# hosts. UNKNOWN ranks below WARNING/CRITICAL so that a host we couldn't
# reach never masks a confirmed vulnerability found on another host.
_STATUS_PRIORITY: dict[NagiosExitCode, int] = {
    NagiosExitCode.CRITICAL: 3,
    NagiosExitCode.WARNING: 2,
    NagiosExitCode.UNKNOWN: 1,
    NagiosExitCode.OK: 0,
}


def _aggregate_exit_code(exit_codes: list[NagiosExitCode]) -> NagiosExitCode:
    """Return the worst status among exit_codes (CRITICAL > WARNING > UNKNOWN > OK)."""
    return max(exit_codes, key=lambda code: _STATUS_PRIORITY.get(code, 0))


def _run_single_host_check(context: ScanContext) -> tuple[str, NagiosExitCode]:
    """
    Run the full scan-and-check flow for a single host.

    Unlike calling check_if_ip_or_host/send_scan_request/check_vulnerabilities
    directly, this captures the printed result and exit code instead of
    terminating the process. Its ContextVar buffer is local to the worker, so
    parallel host checks cannot mix their detail lines or perfdata.
    """
    buffer = io.StringIO()
    token = _RESULT_BUFFER.set(buffer)
    exit_code = NagiosExitCode.UNKNOWN
    try:
        check_if_ip_or_host(context.host, context)
        start = time.perf_counter()
        scan_result = send_scan_request(context)
        duration_seconds = time.perf_counter() - start
        check_vulnerabilities(context, scan_result, duration_seconds=duration_seconds)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            exit_code = NagiosExitCode(exc.code)
    except Exception as exc:
        LOGGER.exception("Unhandled scan failure for host %s", context.host)
        print(
            _safe_monitoring_text(
                f"UNKNOWN: {context.host} Scan failed: {exc}"
            ),
            file=buffer,
        )
    finally:
        _RESULT_BUFFER.reset(token)
    return buffer.getvalue().rstrip("\n"), exit_code


def _summarize_multi_host_result(exit_codes: list[NagiosExitCode]) -> str:
    """Build a one-line summary of how many hosts ended up in each status."""
    counts = Counter(code.name for code in exit_codes)
    breakdown = ", ".join(
        f"{counts[name]} {name}"
        for name in ("CRITICAL", "WARNING", "UNKNOWN", "OK")
        if counts.get(name)
    )
    overall = _aggregate_exit_code(exit_codes)
    return f"Checked {len(exit_codes)} host(s): overall {overall.name} ({breakdown})"


def _host_worker_count(hosts: list[str], args: argparse.Namespace) -> int:
    """Return one host worker per target, constrained by the configured ceiling."""
    return min(len(hosts), args.concurrency)


def _serial_host_context(context: ScanContext) -> ScanContext:
    """Disable probe parallelism when an outer host-worker pool is active."""
    if context.scanner_settings is None:
        return context
    return replace(
        context,
        scanner_settings=replace(context.scanner_settings, concurrency=1),
    )


def _run_multi_host_checks(hosts: list[str], args: argparse.Namespace) -> NagiosExitCode:
    """
    Run the scan-and-check flow for several hosts in parallel.

    A ThreadPoolExecutor creates one worker per host up to --concurrency
    (default five). Each worker captures its own output; after all workers
    finish, this coordinator prints result blocks in host input order and
    returns the worst status across them.
    """
    contexts = [_build_context(host, args) for host in hosts]
    workers = _host_worker_count(hosts, args)
    LOGGER.debug("Running %d host scans with %d worker(s)", len(hosts), workers)

    def _run(context: ScanContext) -> tuple[str, NagiosExitCode]:
        LOGGER.debug("Starting scan for host: %s", context.host)
        # Host and probe pools must not nest. Scanner concurrency remains
        # available for single-host checks through scanner.concurrency.
        return _run_single_host_check(_serial_host_context(context))

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="opencloud-host") as pool:
        results = list(pool.map(_run, contexts))

    blocks = [f"[{host}]\n{message}" for host, (message, _) in zip(hosts, results)]
    exit_codes = [exit_code for _, exit_code in results]

    print(_summarize_multi_host_result(exit_codes))
    print()
    print("\n\n".join(blocks))

    return _aggregate_exit_code(exit_codes)


def _prometheus_scan(context: ScanContext) -> str:
    """Run one scan and render either its metrics or a scrape-success failure sample."""
    start = time.perf_counter()
    try:
        response = _call_with_retry(
            lambda: local_scan(
                context.host,
                settings=context.scanner_settings
                or ScannerSettings(timeout=context.timeout),
                release_settings=context.release_settings,
            ),
            retries=context.retries,
            backoff_factor=context.backoff_factor,
            description=f"Scanning {context.host}",
        )
    except (ScanError, *REQUEST_ERRORS) as exc:
        LOGGER.info("Prometheus scan of %s failed: %s", context.host, exc)
        return render_prometheus_metrics(
            context.host,
            None,
            duration_seconds=time.perf_counter() - start,
            success=False,
        )
    return render_prometheus_metrics(
        context.host,
        response,
        duration_seconds=time.perf_counter() - start,
        success=True,
    )


def _prometheus_metrics(hosts: list[str], args: argparse.Namespace) -> str:
    """
    Collect Prometheus metrics for all requested hosts.

    Multi-host collections use the same bounded host pool as normal checks,
    while each worker scans its instance serially to avoid nested pools.
    """
    contexts = [_build_context(host, args) for host in hosts]
    if len(contexts) == 1:
        return _prometheus_scan(contexts[0])
    with ThreadPoolExecutor(
        max_workers=_host_worker_count(hosts, args),
        thread_name_prefix="opencloud-prometheus",
    ) as pool:
        documents = list(pool.map(_prometheus_scan, map(_serial_host_context, contexts)))
    declarations: set[str] = set()
    lines: list[str] = []
    for document in documents:
        for line in document.splitlines():
            if line.startswith("#"):
                if line in declarations:
                    continue
                declarations.add(line)
            lines.append(line)
    return "\n".join(lines) + "\n"


class _PrometheusExporter:
    """Thread-safe cache that refreshes one or more scan results for /metrics."""

    def __init__(self, hosts: list[str], args: argparse.Namespace) -> None:
        self.hosts = hosts
        self.args = args
        self._body = ""
        self._created_at = 0.0
        self._lock = threading.Lock()

    def metrics(self) -> str:
        """Return cached metrics, refreshing them after the configured interval."""
        with self._lock:
            if (
                not self._body
                or time.monotonic() - self._created_at >= self.args.scrape_interval
            ):
                self._body = _prometheus_metrics(self.hosts, self.args)
                self._created_at = time.monotonic()
            return self._body


def build_prometheus_server(
    hosts: list[str], args: argparse.Namespace
) -> ThreadingHTTPServer:
    """Build a /metrics-only HTTP exporter without starting it, for tests and callers."""
    exporter = _PrometheusExporter(hosts, args)

    class Handler(BaseHTTPRequestHandler):
        """Serve the current OpenCloud scan metrics."""

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.debug("%s - %s", self.address_string(), format % args)

        def do_GET(self) -> None:
            """Return Prometheus metrics only at the conventional /metrics endpoint."""
            if self.path.split("?", 1)[0] != "/metrics":
                self.send_error(HTTPStatus.NOT_FOUND, "Use /metrics")
                return
            body = exporter.metrics().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer(
        (args.prometheus_listen_addr, args.prometheus_listen_port), Handler
    )


def serve_prometheus_metrics(hosts: list[str], args: argparse.Namespace) -> None:
    """Run the Prometheus /metrics exporter until interrupted by its supervisor."""
    server = build_prometheus_server(hosts, args)
    LOGGER.info(
        "OpenCloud Prometheus exporter listening on %s:%d",
        args.prometheus_listen_addr,
        args.prometheus_listen_port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        LOGGER.info("Shutting down Prometheus exporter")
    finally:
        server.server_close()


def _run_early_commands(argv: list[str] | None = None) -> int | None:
    """
    Handle the modes that do not scan anything.

    ``--configure`` and ``--upgrade-self`` are intercepted before the real
    parser is built, because that parser insists on a host and neither of
    these has one. Returns an exit code when it handled the run.
    """
    early = argparse.ArgumentParser(add_help=False)
    early.add_argument("--configure", action="store_true")
    early.add_argument(
        "--upgrade-self",
        nargs="?",
        const=UPGRADE_RUN,
        default=None,
        choices=(UPGRADE_RUN, UPGRADE_CHECK),
    )
    early.add_argument(CHECK_ONLY_FLAG, action="store_true")
    early.add_argument("--config", default=None)
    try:
        known, remaining = early.parse_known_args(argv)
    except SystemExit:
        # An invalid value: let the real parser report it against the full
        # option list rather than this stripped-down one.
        return None

    if known.upgrade_self is not None:
        retired = _retired_flag_error(remaining)
        if retired is not None:
            print(retired, file=sys.stderr)
            return ARGPARSE_ERROR
        return upgrade_self(
            dry_run=known.upgrade_self == UPGRADE_CHECK or known.check_only,
            version=__version__,
        )
    if known.configure:
        return run_setup(path=known.config)
    return None


def _retired_flag_error(remaining: list[str]) -> str | None:
    """
    Report a flag that used to work here, instead of ignoring it.

    ``--upgrade-self --dry-run`` was the spelling of a check that changed
    nothing. Everything else in this mode is harmlessly ignored, but that one
    would now upgrade for real - the exact opposite of what it asked for.
    """
    for argument in remaining:
        name = argument.split("=", 1)[0]
        if name in RETIRED_FLAGS:
            return (
                f"{PROGRAM_NAME}: error: unrecognized arguments: {name} "
                f"(use {RETIRED_FLAGS[name]} instead)"
            )
    return None


def _preparse_config(argv: list[str] | None = None) -> Configuration:
    """
    Load the configuration file before the real parser is built.

    argparse defaults are read from the merged configuration, so the
    '--config' flag (and COS_CONFIG_FILE) has to be evaluated first.
    """
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", default=None)
    known, _ = pre_parser.parse_known_args(argv)
    return load_configuration(known.config)


def main() -> None:
    """Main entry point."""
    early = _run_early_commands()
    if early is not None:
        sys.exit(early)

    try:
        _set_configuration(_preparse_config())
    except ConfigurationError as exc:
        _fail(f"UNKNOWN: {exc}")

    parser = build_arg_parser()
    try:
        args = parser.parse_args()
    except ConfigurationError as exc:  # pragma: no cover - defensive
        parser.error(str(exc))

    hosts = _parse_hosts(args.host or "")
    if not hosts:
        parser.error(f"--host must not be empty (or set the {ENV_PREFIX}HOST environment variable).")

    _validate_thresholds(parser, args)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if _CONFIG.source:
        LOGGER.debug("Using configuration file %s", _CONFIG.source)

    if args.prometheus_listen_port:
        serve_prometheus_metrics(hosts, args)
        return

    if args.output_format == "prometheus":
        print(_prometheus_metrics(hosts, args), end="")
        return

    if len(hosts) == 1:
        try:
            context = _build_context(hosts[0], args)
        except ConfigurationError as exc:
            _fail(f"UNKNOWN: {exc}")
        LOGGER.debug("Starting scan for host: %s", context.host)

        check_if_ip_or_host(context.host, context)

        start = time.perf_counter()
        scan_result = send_scan_request(context)
        duration_seconds = time.perf_counter() - start

        check_vulnerabilities(context, scan_result, duration_seconds=duration_seconds)
        return

    LOGGER.debug("Starting scan for %d hosts: %s", len(hosts), ", ".join(hosts))
    exit_code = _run_multi_host_checks(hosts, args)
    sys.exit(int(exit_code))


if __name__ == "__main__":
    main()
