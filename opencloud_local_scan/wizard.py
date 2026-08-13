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

The file is written with owner-only permissions, because a webhook URL or a
release token is a credential. Values that really are secrets can be kept out
of the file entirely by answering with a ``secret://``, ``file://`` or
``env://`` reference - see :mod:`opencloud_local_scan.secrets`.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG_NAME, JSON_SUFFIXES, load_config_file
from .releases import MODES as UPDATE_MODES
from .scanner import DEFAULT_CONCURRENCY, MAX_CONCURRENCY
from .versions import RELEASE_TRACKS

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
                    key="webhook.headers",
                    prompt="Extra headers",
                    explain=(
                        "Additional HTTP headers for the webhook request, "
                        "separated by ';'. Use this for an authentication token."
                    ),
                    example="X-Auth-Token: s3cr3t; X-Env: prod",
                    secret=True,
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
                    key="scanner.release_track",
                    prompt="Release track",
                    explain=(
                        "Which track this instance follows: 'rolling' (a release "
                        "every ~3 weeks), 'production' (~6 months) or 'lts' (2 "
                        "years of backports). It decides how long the installed "
                        "release is supported and which release the instance is "
                        "told to upgrade to. Leave empty to infer it."
                    ),
                    example="production",
                    validate=_choice(tuple(sorted(RELEASE_TRACKS))),
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
        which means "do not write this key at all".
        """
        self.say()
        self.say(f"  {question.prompt}")
        for line in _wrap(question.explain):
            self.say(f"    {line}")
        self.say(f"    Example: {question.example}")
        if question.secret:
            self.say("    May be a secret://, file:// or env:// reference.")

        suffix = f" [{question.default}]" if question.default else " [skip]"
        while True:
            answer = self.read(f"    > {question.prompt}{suffix}: ").strip()
            if not answer:
                return question.default
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


def _split_list(value: str) -> list[str]:
    """Split a comma or semicolon separated answer into a list."""
    parts = [part.strip() for part in value.replace(";", ",").split(",")]
    return [part for part in parts if part]


def collect(prompter: Prompter, *, include_optional: bool | None = None) -> dict[str, Any]:
    """
    Run the interview and return the configuration document.

    ``include_optional`` forces the optional part on or off; the default asks.
    """
    data: dict[str, Any] = {}

    prompter.say("check-opencloud-security setup")
    prompter.say("=" * 30)
    prompter.say()
    prompter.say("Required settings. Everything else already has a working default.")

    for question in required_questions():
        answer = prompter.ask(question)
        if answer is not None:
            _assign(data, question.key, question.cast(answer))

    prompter.say()
    wants_optional = (
        prompter.confirm("Configure optional settings as well?")
        if include_optional is None
        else include_optional
    )
    if not wants_optional:
        prompter.say()
        prompter.say("Skipping the optional settings - defaults apply.")
        return data

    for group in optional_groups():
        prompter.say()
        if not prompter.confirm(f"Configure {group.name} ({group.summary})?"):
            continue
        for question in group.questions:
            answer = prompter.ask(question)
            if answer is None:
                continue
            if question.key in {"scanner.ignore_hardenings", "webhook.headers"}:
                _assign(data, question.key, _split_list(answer))
            else:
                _assign(data, question.key, question.cast(answer))

    return data


def save(data: dict[str, Any], path: Path) -> Path:
    """Write the configuration as JSON, readable only by its owner."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, FILE_MODE)
    except OSError:  # pragma: no cover - filesystem without permission bits
        pass
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


def run(
    prompter: Prompter | None = None,
    *,
    path: str | None = None,
    include_optional: bool | None = None,
    force: bool = False,
) -> int:
    """
    Run the wizard end to end. Returns a process exit code.

    An existing file is shown and confirmed before it is replaced, so that a
    misremembered ``--configure`` cannot quietly discard a working setup.
    """
    prompter = prompter or Prompter()
    try:
        data = collect(prompter, include_optional=include_optional)
        target = choose_path(prompter, path)

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
