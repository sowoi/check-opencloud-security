"""
Update check-opencloud-security itself.

``--upgrade-self`` upgrades the installed package with the same tool that
installed it. Which tool that was is worked out from where the running module
sits, because a pipx installation upgraded with plain ``pip`` silently breaks
the pipx metadata, and a ``uv tool`` installation is not visible to pip at
all.

Detection order, most specific first:

* a ``distro-package`` marker beside the payload -> refuse, apt or dnf owns it
* a path under a Homebrew ``Cellar/``    -> refuse, ``brew`` owns it
* a path under ``pipx/venvs/``           -> ``pipx upgrade``
* a path under ``uv/tools/``             -> ``uv tool upgrade``
* an editable checkout or a source tree  -> refuse, this is a git working copy
* anything else                          -> ``pip install --upgrade`` into the
  interpreter that is running, adding ``--user`` when that interpreter is not
  a virtual environment and its site-packages are not writable.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess  # nosec B404 - fixed argv built here, never a shell string
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from .versions import compare_versions

LOGGER = logging.getLogger("check_opencloud.selfupdate")

PACKAGE_NAME = "check-opencloud-security"

# Markers that identify the installer from the installation path.
PIPX_MARKERS = ("/pipx/venvs/", "\\pipx\\venvs\\")
UV_MARKERS = ("/uv/tools/", "\\uv\\tools\\")

#: Homebrew installs every formula under `<prefix>/Cellar/<name>/<version>/`,
#: on macOS and on Linux alike, and the prefix moves between the two - so the
#: Cellar directory is the part that identifies it. No Windows spelling: brew
#: does not run there, and inventing one would only widen what this matches.
HOMEBREW_MARKERS = ("/Cellar/",)

#: Written beside the payload by the .deb and the .rpm, holding the packager
#: that built them. A file rather than a path prefix, because a package can be
#: relocated and because this is the packaging *declaring* what it is instead
#: of this module inferring it from where it happens to sit.
DISTRO_MARKER_NAME = "distro-package"

#: How each ecosystem upgrades one package, for the refusal message.
DISTRO_COMMANDS = {
    "deb": "apt install --only-upgrade check-opencloud-security",
    "rpm": "dnf upgrade check-opencloud-security",
}


class UpgradeError(RuntimeError):
    """Raised when the upgrade cannot be attempted or did not succeed."""


@dataclass(frozen=True)
class UpgradePlan:
    """How this installation would be upgraded."""

    installer: str
    command: tuple[str, ...]
    explanation: str

    @property
    def display(self) -> str:
        """The command as it would be typed."""
        return " ".join(self.command)


def _module_path() -> Path:
    """Where the running package lives."""
    return Path(__file__).resolve()


def _is_source_checkout(path: Path) -> bool:
    """
    Whether we are running from a git working copy rather than an install.

    Upgrading such a checkout with a package manager would install a second,
    shadowing copy and leave the operator editing files that no longer run.
    """
    for parent in path.parents:
        if (parent / ".git").exists() and (parent / "pyproject.toml").exists():
            return True
    return False


def _distro_package(path: Path) -> str | None:
    """
    The packager that installed this copy, or ``None`` if pip-style tooling did.

    Returns the marker's contents - ``deb`` or ``rpm`` - so the refusal can
    name the right command. An unreadable or empty marker still counts as a
    distribution package: the file being there is the claim, and its contents
    only decide the wording.
    """
    for parent in path.parents:
        marker = parent / DISTRO_MARKER_NAME
        if not marker.is_file():
            continue
        try:
            return marker.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:  # pragma: no cover - marker present but unreadable
            return "unknown"
    return None


def _pipx_available() -> str | None:
    return shutil.which("pipx")


def _uv_available() -> str | None:
    return shutil.which("uv")


def _in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _site_packages_writable(path: Path) -> bool:
    """Whether pip could install into this interpreter without --user."""
    for parent in path.parents:
        if parent.name == "site-packages":
            return os.access(parent, os.W_OK)
    return os.access(path.parent, os.W_OK)


def plan_upgrade(package: str = PACKAGE_NAME) -> UpgradePlan:
    """
    Work out how this installation should be upgraded.

    Raises :class:`UpgradeError` when it must not be attempted at all.
    """
    path = _module_path()
    text = str(path)

    # Before every other case: pip would appear to succeed here. It installs
    # into the user's site-packages, which the launcher this package puts on
    # PATH never consults, so the operator is left with two versions, told the
    # upgrade worked, and still running the old one.
    packager = _distro_package(path)
    if packager is not None:
        manager = DISTRO_COMMANDS.get(
            packager, "your distribution's package manager"
        )
        raise UpgradeError(
            f"{package} was installed from a distribution package "
            f"({packager}). Upgrade it with '{manager}' instead - installing "
            "over it with pip leaves a second copy that this command would "
            "never run."
        )

    # Same failure as the distro package, by a different route. Homebrew's
    # formula is a virtualenv under the Cellar, so pip finds it writable and
    # upgrades it - and the next `brew upgrade` of anything relinks the Cellar
    # and puts the old version back, silently, with no record that pip was
    # ever there.
    if any(marker in text for marker in HOMEBREW_MARKERS):
        raise UpgradeError(
            f"{package} was installed with Homebrew. Upgrade it with "
            f"'brew upgrade {package}' instead - pip would write into the "
            "Cellar, and the next brew operation would undo it."
        )

    if _is_source_checkout(path):
        raise UpgradeError(
            f"{package} is running from a source checkout ({path.parent.parent}). "
            "Update it with 'git pull' instead - installing over a working copy "
            "would leave you editing files that are no longer executed."
        )

    if any(marker in text for marker in PIPX_MARKERS):
        pipx = _pipx_available()
        if pipx is None:
            raise UpgradeError(
                f"{package} was installed with pipx, but pipx is not on PATH. "
                f"Install pipx, then run 'pipx upgrade {package}'."
            )
        return UpgradePlan(
            installer="pipx",
            command=(pipx, "upgrade", package),
            explanation="Installed with pipx, so pipx keeps the isolated venv consistent.",
        )

    if any(marker in text for marker in UV_MARKERS):
        uv = _uv_available()
        if uv is None:
            raise UpgradeError(
                f"{package} was installed as a uv tool, but uv is not on PATH. "
                f"Install uv, then run 'uv tool upgrade {package}'."
            )
        return UpgradePlan(
            installer="uv",
            command=(uv, "tool", "upgrade", package),
            explanation="Installed as a uv tool, which pip cannot see.",
        )

    command = [sys.executable, "-m", "pip", "install", "--upgrade", package]
    explanation = f"Installed with pip into {sys.prefix}."
    if not _in_virtualenv() and not _site_packages_writable(path):
        command.insert(5, "--user")
        explanation = (
            "Installed with pip outside a virtual environment and system "
            "site-packages is not writable, so --user is used."
        )
    return UpgradePlan(
        installer="pip", command=tuple(command), explanation=explanation
    )


def run_upgrade(plan: UpgradePlan) -> int:
    """Execute the planned command, streaming its output to the terminal."""
    LOGGER.debug("Running %s", plan.display)
    try:
        completed = subprocess.run(  # nosec B603 - argv built above, no shell
            list(plan.command), check=False
        )
    except OSError as exc:
        raise UpgradeError(f"Could not run '{plan.display}': {exc}") from exc
    if completed.returncode != 0:
        raise UpgradeError(
            f"'{plan.display}' failed with exit code {completed.returncode}."
        )
    return completed.returncode


def upgrade_self(
    *,
    package: str = PACKAGE_NAME,
    dry_run: bool = False,
    version: str | None = None,
    output: Callable[[str], None] | None = None,
) -> int:
    """
    Upgrade the installed package. Returns a process exit code.

    ``dry_run`` prints the command that would run without running it, which is
    what an operator wants before letting a monitoring host change itself.
    """
    say: Callable[[str], None] = print if output is None else output

    try:
        plan = plan_upgrade(package)
    except UpgradeError as exc:
        say(f"UNKNOWN: {exc}")
        return 3

    say(f"Installed with: {plan.installer}")
    say(f"Reason:         {plan.explanation}")
    if version:
        say(f"Current version: {version}")
    say(f"Command:        {plan.display}")

    if dry_run:
        say("Dry run - nothing was changed.")
        return 0

    say("")
    try:
        run_upgrade(plan)
    except UpgradeError as exc:
        say(f"UNKNOWN: {exc}")
        return 3

    say("")
    say(f"{package} upgraded. Check the result with: {package} --version")
    return 0


# --- Is the plugin itself out of date? ---
#
# A monitoring plugin that reports on everyone else's updates but never on its
# own is a blind spot: an instance can be checked for years by a version that
# no longer knows about the advisories that matter. The check is off by
# default, cached, and can only ever add a note - it must never decide the
# exit code, because whether PyPI is reachable says nothing about the health
# of the host being monitored.

PYPI_URL = "https://pypi.org/pypi/{package}/json"
CACHE_FILENAME = "pypi-version.json"
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
PYPI_TIMEOUT_SECONDS = 5


def cache_path(package: str = PACKAGE_NAME) -> Path:
    """Where the last answer from PyPI is remembered."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return Path(base) / package / CACHE_FILENAME


def _read_cache(path: Path, max_age: float) -> str | None:
    """Return the cached version if it is still fresh, otherwise None."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        checked_at = float(raw.get("checkedAt", 0))
    except (TypeError, ValueError):
        return None
    if time.time() - checked_at > max_age:
        return None
    version = raw.get("version")
    return str(version) if version else None


def _write_cache(path: Path, version: str) -> None:
    """Remember an answer. Failing to cache is not worth reporting."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": version, "checkedAt": time.time()}),
            encoding="utf-8",
        )
    except OSError as exc:
        LOGGER.debug("Could not write %s: %s", path, exc)


def _fetch_latest(package: str, timeout: float) -> str | None:
    """Ask PyPI for the newest published version."""
    try:
        response = requests.get(
            PYPI_URL.format(package=package), timeout=timeout
        )
        response.raise_for_status()
        info = response.json().get("info", {})
    except (requests.RequestException, ValueError) as exc:
        LOGGER.debug("PyPI lookup for %s failed: %s", package, exc)
        return None
    version = info.get("version") if isinstance(info, dict) else None
    return str(version) if version else None


def latest_released_version(
    *,
    package: str = PACKAGE_NAME,
    max_age: float = CACHE_MAX_AGE_SECONDS,
    timeout: float = PYPI_TIMEOUT_SECONDS,
    use_cache: bool = True,
) -> str | None:
    """
    The newest version of the package on PyPI, or None if it cannot be found.

    Every failure - no network, a proxy in the way, PyPI down, a response that
    is not the JSON we expect - returns None silently. This is a footnote, not
    a check.
    """
    path = cache_path(package)
    if use_cache:
        cached = _read_cache(path, max_age)
        if cached is not None:
            return cached
    version = _fetch_latest(package, timeout)
    if version is not None and use_cache:
        _write_cache(path, version)
    return version


def self_update_note(
    current: str,
    *,
    package: str = PACKAGE_NAME,
    max_age: float = CACHE_MAX_AGE_SECONDS,
    timeout: float = PYPI_TIMEOUT_SECONDS,
    use_cache: bool = True,
) -> str | None:
    """
    A one-line note when a newer plugin version exists, otherwise None.

    Returns None when the installed version is newer than the published one
    too, which is the normal state of a source checkout between releases.
    """
    latest = latest_released_version(
        package=package, max_age=max_age, timeout=timeout, use_cache=use_cache
    )
    if latest is None or compare_versions(latest, current) <= 0:
        return None
    return (
        f"Plugin update available: {package} {latest} is published, "
        f"this is {current} (upgrade with --upgrade-self)"
    )
