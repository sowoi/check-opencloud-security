"""
Interactive setup for check-opencloud-security.

``check-opencloud-security --configure`` asks for the handful of values a
check cannot run without, explains what each one is for, shows example data,
and writes the answers to a JSON configuration file that every later run finds
on its own.

Two rules shape the questions:

* **Only what is required is asked.** Exactly one value has no sensible
  default - the host. Everything else already works out of the box, so asking
  about it would be a quiz rather than a setup.
* **Optional settings are offered, never imposed.** They are grouped by
  subject and each group is skipped with a single Enter, so an operator who
  wants a webhook does not have to page through TLS and threshold questions
  to reach it.

An existing configuration is loaded first and every stored value is offered
as the default for its question, which makes ``--configure`` an editor rather
than a form that has to be filled in again from the top. Pressing Enter keeps
what is already configured, so the risky operation - replacing a working setup
with an empty one - takes deliberate effort.

The file is written with owner-only permissions, because a webhook URL or a
release token is a credential. Values that really are secrets can be kept out
of the file entirely by answering with a ``secret://``, ``file://`` or
``env://`` reference - see :mod:`opencloud_local_scan.secrets`.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_CONFIG_NAME,
    DEFAULT_CONFIG_PATHS,
    JSON_SUFFIXES,
    load_config_file,
)
from .releases import MODES as UPDATE_MODES
from .scanner import DEFAULT_CONCURRENCY, MAX_CONCURRENCY
from .versions import RELEASE_TRACK_CHOICES

# Where the wizard offers to save, in the order it offers them.
SAVE_LOCATIONS: tuple[str, ...] = (
    f"./{DEFAULT_CONFIG_NAME}",
    f"~/.config/check-opencloud-security/{DEFAULT_CONFIG_NAME}",
    f"/etc/check-opencloud-security/{DEFAULT_CONFIG_NAME}",
)

# Owner read/write only: the file may hold a webhook URL or a token.
FILE_MODE = stat.S_IRUSR | stat.S_IWUSR

YES = {"y", "yes", "j", "ja", "1", "true"}
NO = {"n", "no", "nein", "0", "false"}

CLEAR = "-"
"""Typed at a prompt to remove a configured value rather than keep it.

Enter keeps the current value, which is what makes the wizard an editor - so
there has to be some way of saying "remove this", and it cannot be the empty
answer without taking Enter's meaning away."""


class SetupAborted(RuntimeError):
    """Raised when the operator interrupts the wizard."""


@dataclass
class Question:
    """One prompt: what it configures, why, and what a good answer looks like."""

    key: str
    """Dotted configuration key, e.g. ``webhook.url``."""
    prompt: str
    explain: str
    example: str
    default: str | None = None
    validate: Callable[[str], str | None] = lambda value: None
    """Returns an error message for a bad answer, or None when it is fine."""
    cast: Callable[[str], Any] = str
    secret: bool = False
    """Hint that the answer may be a secret reference rather than a value."""
    current: bool = False
    """Whether the default shown is the value already configured."""


@dataclass
class Group:
    """A set of questions the operator can accept or skip as a whole."""

    name: str
    summary: str
    questions: list[Question] = field(default_factory=list)


# --- validators -------------------------------------------------------------
def _non_empty(value: str) -> str | None:
    return None if value.strip() else "A value is required."


def _port(value: str) -> str | None:
    try:
        number = int(value)
    except ValueError:
        return "Enter a whole number, e.g. 9200."
    return None if 1 <= number <= 65535 else "A port must be between 1 and 65535."


def _positive_int(value: str) -> str | None:
    try:
        number = int(value)
    except ValueError:
        return "Enter a whole number."
    return None if number > 0 else "Enter a number greater than zero."


def _rating(value: str) -> str | None:
    try:
        number = int(value)
    except ValueError:
        return "Enter a whole number between 0 and 5."
    return None if 0 <= number <= 5 else "A rating is between 0 (F) and 5 (A+)."


def _concurrency(value: str) -> str | None:
    try:
        number = int(value)
    except ValueError:
        return "Enter a whole number."
    if not 1 <= number <= MAX_CONCURRENCY:
        return f"Enter a number between 1 and {MAX_CONCURRENCY}."
    return None


def _http_url(value: str) -> str | None:
    if not value.lower().startswith(("http://", "https://")):
        return "The URL must start with http:// or https://."
    return None


def _choice(allowed: Sequence[str]) -> Callable[[str], str | None]:
    options = ", ".join(allowed)
    def check(value: str) -> str | None:
        return None if value.strip().lower() in allowed else f"Choose one of: {options}."
    return check


def _positive_float(value: str) -> str | None:
    try:
        number = float(value)
    except ValueError:
        return "Enter a number, e.g. 0.5."
    return None if number >= 0 else "Enter a number of zero or more."


# --- the questions ----------------------------------------------------------
def required_questions() -> list[Question]:
    """The values a check genuinely cannot run without."""
    return [
        Question(
            key="host",
            prompt="OpenCloud address",
            explain=(
                "The instance to check. A hostname, an IP address or a full URL, "
                "optionally with a port. Several instances can be listed "
                "comma-separated and are then checked in one run."
            ),
            example="opencloud.example.com, 10.0.0.5:9200, https://cloud.example.com",
            validate=_non_empty,
        ),
    ]


def optional_groups() -> list[Group]:
    """Everything that already has a working default, grouped by subject."""
    return [
        Group(
            name="Connection",
            summary="port, scheme, TLS verification, proxy, timeout",
            questions=[
                Question(
                    key="scanner.target_port",
                    prompt="Port",
                    explain=(
                        "The port the instance listens on. Leave empty to take it "
                        "from the address, falling back to 443. OpenCloud's own "
                        "proxy service usually listens on 9200."
                    ),
                    example="9200",
                    validate=_port,
                    cast=int,
                ),
                Question(
                    key="scanner.scheme",
                    prompt="Scheme",
                    explain=(
                        "How to reach the instance. 'https' is tried first and "
                        "falls back to plain http automatically, which is then "
                        "reported as a critical finding."
                    ),
                    example="https",
                    default="https",
                    validate=_choice(("https", "http")),
                ),
                Question(
                    key="scanner.verify_tls",
                    prompt="Verify the TLS certificate",
                    explain=(
                        "'opencloud init' generates a self-signed certificate, so "
                        "an internal instance often has no trusted chain. Keep "
                        "this at yes for a properly certified instance: the "
                        "untrusted chain is then reported as a finding instead of "
                        "being accepted silently. Answer no for a knowingly "
                        "self-signed deployment - the finding is still reported, "
                        "it just stops counting against the rating."
                    ),
                    example="yes",
                    default="yes",
                    validate=_choice(tuple(YES | NO)),
                    cast=lambda value: value.strip().lower() in YES,
                ),
                Question(
                    key="proxy",
                    prompt="HTTP proxy",
                    explain=(
                        "Proxy used to reach the instance and the release feed. "
                        "Leave empty when the monitoring host has direct access."
                    ),
                    example="http://proxy.example.com:3128",
                ),
                Question(
                    key="timeout",
                    prompt="Timeout in seconds",
                    explain=(
                        "How long a single HTTP request may take before it counts "
                        "as failed. Raise it for a slow link, lower it to keep the "
                        "check inside a tight monitoring interval."
                    ),
                    example="10",
                    default="10",
                    validate=_positive_int,
                    cast=int,
                ),
            ],
        ),
        Group(
            name="Thresholds",
            summary="when the check warns and when it turns critical",
            questions=[
                Question(
                    key="warning",
                    prompt="WARNING at or below rating",
                    explain=(
                        "The instance is rated 0-5 (5 = A+, 3 = C, 0 = F). At or "
                        "below this rating the check reports WARNING."
                    ),
                    example="3",
                    default="3",
                    validate=_rating,
                    cast=int,
                ),
                Question(
                    key="critical",
                    prompt="CRITICAL at or below rating",
                    explain=(
                        "At or below this rating the check reports CRITICAL. It "
                        "must not be higher than the warning threshold."
                    ),
                    example="1",
                    default="1",
                    validate=_rating,
                    cast=int,
                ),
                Question(
                    key="check_hardening",
                    prompt="Report missing hardening measures",
                    explain=(
                        "Also alert on hardening measures and security headers "
                        "that are absent, such as a weak Content-Security-Policy, "
                        "rather than on vulnerabilities and failed checks alone."
                    ),
                    example="no",
                    default="no",
                    validate=_choice(tuple(YES | NO)),
                    cast=lambda value: value.strip().lower() in YES,
                ),
            ],
        ),
        Group(
            name="Webhook",
            summary="notify Uptime Kuma, Slack, Alertmanager, ... on a bad result",
            questions=[
                Question(
                    key="webhook.url",
                    prompt="Webhook URL",
                    explain=(
                        "Endpoint that receives a JSON payload when the check "
                        "reaches the state selected below. For Uptime Kuma this "
                        "is the push URL of a Push monitor."
                    ),
                    example="https://kuma.example.com/api/push/AbC123XyZ",
                    validate=_http_url,
                    secret=True,
                ),
                Question(
                    key="webhook.on",
                    prompt="Notify from state",
                    explain=(
                        "The lowest state that fires the webhook: 'critical' only, "
                        "'warning' and worse, 'unknown' and worse, or 'always' for "
                        "every run - which is what an Uptime Kuma push monitor "
                        "needs to tell 'all good' from 'nothing reported'."
                    ),
                    example="critical",
                    default="critical",
                    validate=_choice(("critical", "warning", "unknown", "always")),
                ),
                Question(
                    key="webhook.format",
                    prompt="Payload format",
                    explain=(
                        "'generic' posts the plugin's own flat JSON document. "
                        "'slack' also works for Mattermost and the common "
                        "Matrix webhook bridges; 'discord' posts a single embed."
                    ),
                    example="generic",
                    default="generic",
                    validate=_choice(("generic", "slack", "discord")),
                ),
                Question(
                    key="webhook.headers",
                    prompt="Extra headers",
                    explain=(
                        "Additional HTTP headers for the webhook request, "
                        "separated by ';'. Use this for an authentication token."
                    ),
                    example="X-Auth-Token: s3cr3t; X-Env: prod",
                    secret=True,
                ),
                Question(
                    key="webhook.allow_private_webhooks",
                    prompt="Allow private webhook addresses",
                    explain=(
                        "Permit delivery to private, loopback, or link-local "
                        "addresses. Leave this off unless the receiver is an "
                        "intentional internal service."
                    ),
                    example="no",
                    default="no",
                    validate=_choice(tuple(YES | NO)),
                    cast=lambda value: value.strip().lower() in YES,
                ),
            ],
        ),
        Group(
            name="Release track",
            summary="which OpenCloud track this instance follows",
            questions=[
                Question(
                    key="scanner.release_track",
                    prompt="Release track",
                    explain=(
                        "OpenCloud ships three tracks side by side: 'rolling' (a "
                        "release every ~3 weeks), 'production' (~6 months) and "
                        "'lts' (2 years of backports). The track decides how long "
                        "the installed release is supported and which release "
                        "this instance is told to upgrade to. Leave it at 'auto' "
                        "unless you know: the release schedule then works the "
                        "track out from the version the instance reports, and one "
                        "configuration can cover instances on different tracks. "
                        "Name a track only when you deliberately follow it - the "
                        "release is then judged on that track alone, so a rolling "
                        "instance still on an old production line is reported as "
                        "behind. A release newer than the current one of your "
                        "track is reported as ahead of it, never as end of life."
                    ),
                    example="auto",
                    default="auto",
                    validate=_choice(tuple(sorted(RELEASE_TRACK_CHOICES))),
                ),
            ],
        ),
        Group(
            name="Update check",
            summary="how the newest OpenCloud release is looked up",
            questions=[
                Question(
                    key="update_source",
                    prompt="Update source",
                    explain=(
                        "Where the newest release comes from: 'feed' asks GitHub, "
                        "'bundled' uses the release shipped with this package and "
                        "needs no network at all, 'pinned' uses a version you "
                        "state yourself, 'off' disables the check, and 'auto' "
                        "picks whichever is configured."
                    ),
                    example="auto",
                    default="auto",
                    validate=_choice(tuple(UPDATE_MODES)),
                ),
                Question(
                    key="releases.token",
                    prompt="GitHub token for the release feed",
                    explain=(
                        "Optional. GitHub allows sixty anonymous API requests per "
                        "hour and IP address; a read-only token lifts that limit. "
                        "A secret:// or env:// reference keeps it out of this file."
                    ),
                    example="env://GITHUB_TOKEN",
                    secret=True,
                ),
                Question(
                    key="update_warning",
                    prompt="WARNING when an update is available",
                    explain=(
                        "Raise an otherwise OK result to WARNING as soon as a "
                        "newer OpenCloud release exists."
                    ),
                    example="no",
                    default="no",
                    validate=_choice(tuple(YES | NO)),
                    cast=lambda value: value.strip().lower() in YES,
                ),
            ],
        ),
        Group(
            name="Scan behaviour",
            summary="parallelism, debug ports, waived findings",
            questions=[
                Question(
                    key="scanner.concurrency",
                    prompt="Probes in parallel",
                    explain=(
                        "A scan spends nearly all its time waiting for answers, so "
                        f"running probes in parallel shortens it. {DEFAULT_CONCURRENCY} "
                        "means no multithreading, which is the safest setting for "
                        f"the instance. At most {MAX_CONCURRENCY}."
                    ),
                    example="8",
                    default=str(DEFAULT_CONCURRENCY),
                    validate=_concurrency,
                    cast=int,
                ),
                Question(
                    key="scanner.check_debug_ports",
                    prompt="Probe the service debug ports",
                    explain=(
                        "The OpenCloud services expose /metrics, /config and "
                        "pprof on separate ports (9205, 9141, 9124, 9134, 9239). "
                        "They bind to loopback by default, so one that answers "
                        "from outside is a real finding. Each probe is a TCP "
                        "connect, so a firewalled host costs time."
                    ),
                    example="yes",
                    default="yes",
                    validate=_choice(tuple(YES | NO)),
                    cast=lambda value: value.strip().lower() in YES,
                ),
                Question(
                    key="scanner.ignore_hardenings",
                    prompt="Waived measures and checks",
                    explain=(
                        "Findings to accept and stop alerting on, comma-separated, "
                        "with shell-style wildcards allowed. A waived finding stays "
                        "in the result and stops lowering the rating. Only use this "
                        "for measures you have consciously decided against."
                    ),
                    example="cspWithoutUnsafeInline, debugPort:*",
                ),
            ],
        ),
    ]


def _lookup(data: Mapping[str, Any], key: str) -> Any:
    """Read a dotted key out of a nested configuration document."""
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _as_answer(value: Any) -> str | None:
    """
    Render a stored value the way the operator would have typed it.

    The prompt loop only speaks strings, and a default has to survive being
    read back and cast again, so a boolean becomes 'yes'/'no' and a list
    becomes the comma-separated form the questions document.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        rendered = ", ".join(str(item) for item in value)
        return rendered or None
    text = str(value)
    return text or None


def existing_configuration(path: str | None) -> tuple[dict[str, Any], Path | None]:
    """
    Load the configuration --configure should start from.

    An explicit ``--config`` wins; otherwise the first of the default
    locations that exists is used, which is the same file the check itself
    would have picked up. An unreadable file is not an error here: the wizard
    is how an operator recovers from one.
    """
    candidates = [path] if path else list(DEFAULT_CONFIG_PATHS)
    for candidate in candidates:
        target = Path(candidate).expanduser()
        if not target.is_file():
            continue
        try:
            return load_config_file(target), target
        except Exception:  # noqa: BLE001 - a broken file is what we are replacing
            return {}, target
    return {}, None


def _with_existing(question: Question, existing: Mapping[str, Any]) -> Question:
    """Offer the configured value as the default, keeping the original as a hint."""
    stored = _as_answer(_lookup(existing, question.key))
    if stored is None:
        return question
    return replace(question, default=stored, current=True)


# --- prompting --------------------------------------------------------------
@dataclass
class Prompter:
    """Reads answers and writes explanations, so the wizard stays testable."""

    input: Callable[[str], str] = input
    output: Callable[[str], None] = print

    def say(self, message: str = "") -> None:
        """Print one line."""
        self.output(message)

    def ask(self, question: Question) -> str | None:
        """
        Ask one question until the answer is usable.

        Returns None when the operator left it empty and it has no default,
        which means "do not write this key at all", and :data:`CLEAR` when
        they asked for a configured value to be removed.
        """
        self.say()
        self.say(f"  {question.prompt}")
        for line in _wrap(question.explain):
            self.say(f"    {line}")
        self.say(f"    Example: {question.example}")
        if question.secret:
            self.say("    May be a secret://, file:// or env:// reference.")

        if question.default and question.current:
            self.say(f"    Configured now: {question.default}")
            self.say(f"    Enter keeps it, '{CLEAR}' removes it.")
            suffix = f" [{question.default}]"
        elif question.default:
            suffix = f" [{question.default}]"
        else:
            suffix = " [skip]"
        while True:
            answer = self.read(f"    > {question.prompt}{suffix}: ").strip()
            if not answer:
                return question.default
            if answer == CLEAR and question.current:
                return CLEAR
            error = question.validate(answer)
            if error is None:
                return answer
            self.say(f"    {error}")

    def confirm(self, message: str, *, default: bool = False) -> bool:
        """Ask a yes/no question."""
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self.read(f"{message} {suffix}: ").strip().lower()
            if not answer:
                return default
            if answer in YES:
                return True
            if answer in NO:
                return False
            self.say("  Please answer yes or no.")

    def choose(self, message: str, options: Sequence[str], *, default: int = 0) -> int:
        """Ask the operator to pick one of several options."""
        self.say()
        self.say(message)
        for index, option in enumerate(options, start=1):
            marker = " (default)" if index - 1 == default else ""
            self.say(f"  {index}) {option}{marker}")
        while True:
            answer = self.read(f"  > 1-{len(options)} [{default + 1}]: ").strip()
            if not answer:
                return default
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
            self.say(f"  Enter a number between 1 and {len(options)}.")

    def read(self, prompt: str) -> str:
        """Read one answer, turning Ctrl-C and Ctrl-D into a clean abort."""
        try:
            return self.input(prompt)
        except (EOFError, KeyboardInterrupt) as exc:
            raise SetupAborted("Setup cancelled - nothing was written.") from exc


def _wrap(text: str, width: int = 72) -> list[str]:
    """Wrap an explanation without pulling in textwrap's extra behaviour."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if current and sum(len(part) + 1 for part in current) + len(word) > width:
            lines.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _assign(data: dict[str, Any], key: str, value: Any) -> None:
    """Store a dotted key as a nested mapping, the way the loader reads it."""
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        nested = target.setdefault(part, {})
        if not isinstance(nested, dict):  # pragma: no cover - defensive
            nested = {}
            target[part] = nested
        target = nested
    target[parts[-1]] = value


def _remove(data: dict[str, Any], key: str) -> None:
    """Delete a dotted key, and any mapping it leaves empty behind it."""
    parts = key.split(".")
    trail: list[tuple[dict[str, Any], str]] = []
    target: Any = data
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            return
        trail.append((target, part))
        target = nested
    target.pop(parts[-1], None)
    for parent, name in reversed(trail):
        if parent[name] == {}:
            del parent[name]


def _split_list(value: str) -> list[str]:
    """Split a comma or semicolon separated answer into a list."""
    parts = [part.strip() for part in value.replace(";", ",").split(",")]
    return [part for part in parts if part]


def collect(
    prompter: Prompter,
    *,
    include_optional: bool | None = None,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run the interview and return the configuration document.

    ``include_optional`` forces the optional part on or off; the default asks.
    ``existing`` is a configuration already on disk: each stored value becomes
    the default for its question, so Enter keeps it and the wizard edits
    instead of starting over.
    """
    existing = existing or {}
    # Start from what is already there: the wizard asks about a subset of the
    # settings, and rewriting the file from scratch would silently drop the
    # hand-edited keys it has no question for.
    data: dict[str, Any] = deepcopy(dict(existing))

    prompter.say("check-opencloud-security setup")
    prompter.say("=" * 30)
    if existing:
        prompter.say()
        prompter.say(
            "Editing the existing configuration. The value in brackets is what "
            "is configured now; press Enter to keep it."
        )
    prompter.say()
    prompter.say("Required settings. Everything else already has a working default.")

    for question in required_questions():
        answer = prompter.ask(_with_existing(question, existing))
        if answer == CLEAR:
            _remove(data, question.key)
        elif answer is not None:
            _assign(data, question.key, question.cast(answer))

    prompter.say()
    wants_optional = (
        prompter.confirm(
            "Review the optional settings as well?", default=bool(existing)
        )
        if include_optional is None
        else include_optional
    )
    if not wants_optional:
        prompter.say()
        if existing:
            prompter.say("Keeping the optional settings that are already configured.")
        else:
            prompter.say("Skipping the optional settings - defaults apply.")
        return data

    for group in optional_groups():
        prompter.say()
        configured = [
            question.key
            for question in group.questions
            if _lookup(existing, question.key) is not None
        ]
        summary = group.summary
        if configured:
            summary += f"; {len(configured)} configured"
        if not prompter.confirm(
            f"Configure {group.name} ({summary})?", default=bool(configured)
        ):
            continue
        for question in group.questions:
            answer = prompter.ask(_with_existing(question, existing))
            if answer is None:
                continue
            if answer == CLEAR:
                _remove(data, question.key)
            elif question.key in {"scanner.ignore_hardenings", "webhook.headers"}:
                _assign(data, question.key, _split_list(answer))
            else:
                _assign(data, question.key, question.cast(answer))

    return data



# --- the test scan ----------------------------------------------------------
def _hosts(data: Mapping[str, Any]) -> list[str]:
    """The instances the collected configuration would check."""
    raw = _lookup(data, "host")
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def test_scan(data: Mapping[str, Any], prompter: Prompter) -> bool:
    """
    Scan the configured host with the answers just given, and report.

    A configuration is only worth saving if it works, and the two mistakes
    that make it not work - the wrong port and a self-signed certificate - are
    invisible until something scans. Returns whether the scan succeeded.
    """
    from .config import Configuration, _flatten
    from .factory import release_settings_from_config, scanner_settings_from_config
    from .scanner import ScanError, scan

    hosts = _hosts(data)
    if not hosts:  # pragma: no cover - the host question is required
        return False

    config = Configuration(values=_flatten(dict(data)), raw=dict(data))
    try:
        settings = scanner_settings_from_config(config)
        releases = release_settings_from_config(config)
    except Exception as exc:  # noqa: BLE001 - a bad answer must not crash the wizard
        prompter.say(f"  The settings could not be used: {exc}")
        return False

    ok = True
    for host in hosts:
        prompter.say()
        prompter.say(f"  Scanning {host} ...")
        try:
            result = scan(host, settings=settings, release_settings=releases)
        except ScanError as exc:
            ok = False
            prompter.say(f"  Failed: {exc}")
            for line in _wrap(_diagnose(str(exc)), width=68):
                prompter.say(f"    {line}")
            continue
        except Exception as exc:  # noqa: BLE001 - report, never traceback at a prompt
            ok = False
            prompter.say(f"  Failed: {exc}")
            continue

        for line in _summarize(result):
            prompter.say(f"    {line}")
    return ok


def _summarize(result: Mapping[str, Any]) -> list[str]:
    """The few lines of a result document worth showing at a prompt."""
    rating = result.get("rating")
    grade = rating if rating is not None else "?"
    product = result.get("product", "OpenCloud")
    lines = [f"{product} {result.get('version', '?')} - rating {grade}/5"]
    if result.get("EOL"):
        lines.append("This release no longer receives security fixes.")

    failed = [
        check["id"]
        for check in result.get("extraChecks", [])
        if not check.get("passed") and not check.get("ignored")
    ]
    advisories = len(result.get("vulnerabilities", []))
    lines.append(f"{len(failed)} failed check(s), {advisories} advisory match(es)")

    updates = result.get("updates") or {}
    if updates.get("error"):
        lines.append(f"Update check: {updates['error']}")
    elif updates.get("available"):
        lines.append(f"A newer release is available: {updates.get('availableVersion')}")
    return lines


def _diagnose(error: str) -> str:
    """Turn the usual scan failure into the answer that most often fixes it."""
    lowered = error.lower()
    if "certificate" in lowered or "ssl" in lowered:
        return (
            "That looks like the self-signed certificate 'opencloud init' "
            "creates. Answer no to 'Verify the TLS certificate' - the finding "
            "is still reported, it just stops counting against the rating."
        )
    if "unreachable" in lowered or "timed out" in lowered or "timeout" in lowered:
        return (
            "Nothing answered there. OpenCloud's own proxy usually listens on "
            "9200 rather than 443, so check the port, and check that this host "
            "may reach the instance at all."
        )
    if "no opencloud instance" in lowered:
        return (
            "Something answered, but not with an OpenCloud status document. "
            "Either the address belongs to something else, or a reverse proxy "
            "in front of it does not forward /status.php."
        )
    return "Check the address, the port and the scheme before saving."


def save(data: dict[str, Any], path: Path) -> Path:
    """Write the configuration as JSON, readable only by its owner.

    Written to a temporary file and moved into place rather than written
    where it belongs and narrowed afterwards: a secret that was
    world-readable for a moment was world-readable. ``mkstemp`` creates at
    owner-only, so the token is never on disk under a wider mode - not in the
    window before a ``chmod``, and not for the whole write when the
    destination already existed at 0644, which is what re-running
    ``--configure`` to rotate a token does.

    The move is atomic as well, so a write that fails leaves the previous
    configuration intact instead of a truncated one.
    """
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2, sort_keys=False) + "\n")
        try:
            os.chmod(temporary, FILE_MODE)
        except OSError:  # pragma: no cover - filesystem without permission bits
            pass
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise
    return path


def _writable(path: Path) -> bool:
    """Whether the wizard could write there without becoming root."""
    candidate = path.expanduser()
    probe = candidate.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return os.access(probe, os.W_OK)


def choose_path(prompter: Prompter, explicit: str | None) -> Path:
    """Ask where the configuration should live."""
    if explicit:
        return Path(explicit).expanduser()

    options = []
    for location in SAVE_LOCATIONS:
        note = "" if _writable(Path(location)) else "  (not writable as this user)"
        options.append(f"{location}{note}")
    options.append("somewhere else")

    index = prompter.choose("Where should the configuration be saved?", options)
    if index == len(options) - 1:
        while True:
            answer = prompter.read("  > Path: ").strip()
            if answer:
                return Path(answer).expanduser()
            prompter.say("  Enter a path.")
    return Path(SAVE_LOCATIONS[index]).expanduser()


def _verify_before_saving(
    prompter: Prompter, data: Mapping[str, Any], *, verify: bool | None
) -> bool:
    """
    Offer a scan with the answers just given. Returns whether to save.

    A wizard that cannot tell you whether its output works is a form. The scan
    is offered rather than imposed, because the instance may be unreachable
    from where the file is being written, and a failing scan does not block
    saving - the operator decides.
    """
    prompter.say()
    if verify is None:
        verify = prompter.confirm(
            "Test these settings against the instance now?", default=True
        )
    if not verify:
        return True

    if test_scan(data, prompter):
        prompter.say()
        prompter.say("  The settings work.")
        return True

    prompter.say()
    return prompter.confirm("The test scan failed. Save anyway?", default=True)


def run(
    prompter: Prompter | None = None,
    *,
    path: str | None = None,
    include_optional: bool | None = None,
    force: bool = False,
    verify: bool | None = None,
) -> int:
    """
    Run the wizard end to end. Returns a process exit code.

    The configuration already on disk is loaded first and offered value by
    value, so this edits a setup rather than replacing it. An existing file is
    still shown and confirmed before it is written, so that a misremembered
    ``--configure`` cannot quietly discard a working one.

    ``verify`` forces the closing test scan on or off; the default asks.
    """
    prompter = prompter or Prompter()
    try:
        existing, source = existing_configuration(path)
        if source is not None:
            prompter.say(f"Reading the current configuration from {source}")
        data = collect(prompter, include_optional=include_optional, existing=existing)
        target = choose_path(prompter, path if path else (str(source) if source else None))

        if target.suffix.lower() not in JSON_SUFFIXES:
            prompter.say()
            prompter.say(
                f"Note: {target.name} is not a .json file, so it will be read as "
                "YAML. Saving JSON under that name will not work."
            )
            if not prompter.confirm("Save anyway?"):
                target = target.with_suffix(".json")
                prompter.say(f"Saving to {target} instead.")

        if target.exists() and not force:
            prompter.say()
            prompter.say(f"{target} already exists:")
            try:
                existing = load_config_file(target)
                for line in json.dumps(existing, indent=2).splitlines()[:20]:
                    prompter.say(f"  {line}")
            except Exception:  # noqa: BLE001 - unreadable is reason enough to warn
                prompter.say("  (unreadable)")
            if not prompter.confirm("Overwrite it?"):
                prompter.say("Nothing was written.")
                return 1

        if not _verify_before_saving(prompter, data, verify=verify):
            return 1

        written = save(data, target)
    except SetupAborted as exc:
        prompter.say()
        prompter.say(str(exc))
        return 1

    prompter.say()
    prompter.say(f"Saved to {written}")
    prompter.say()
    prompter.say(json.dumps(data, indent=2))
    prompter.say()
    if str(written.parent) == "." or written.parent == Path.cwd():
        prompter.say("It is found automatically when the check runs from this directory.")
    elif any(
        written == Path(location).expanduser() for location in SAVE_LOCATIONS
    ):
        prompter.say("It is found automatically from now on.")
    else:
        prompter.say(f"Point the check at it with --config {written}")
    prompter.say()
    prompter.say("Try it with:  check-opencloud-security")
    return 0
