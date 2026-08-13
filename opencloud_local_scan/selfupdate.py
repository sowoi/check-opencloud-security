"""
Update check-opencloud-security itself.

``--upgrade-self`` upgrades the installed package with the same tool that
installed it. Which tool that was is worked out from where the running module
sits, because a pipx installation upgraded with plain ``pip`` silently breaks
the pipx metadata, and a ``uv tool`` installation is not visible to pip at
all.

Detection order, most specific first:

* a path under ``pipx/venvs/``           -> ``pipx upgrade``
* a path under ``uv/tools/``             -> ``uv tool upgrade``
* an editable checkout or a source tree  -> refuse, this is a git working copy
* anything else                          -> ``pip install --upgrade`` into the
  interpreter that is running, adding ``--user`` when that interpreter is not
  a virtual environment and its site-packages are not writable.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess  # nosec B404 - fixed argv built here, never a shell string
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("check_opencloud.selfupdate")

PACKAGE_NAME = "check-opencloud-security"

# Markers that identify the installer from the installation path.
PIPX_MARKERS = ("/pipx/venvs/", "\\pipx\\venvs\\")
UV_MARKERS = ("/uv/tools/", "\\uv\\tools\\")


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
