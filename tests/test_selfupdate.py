"""
Tests for ``--upgrade-self``.

Which tool installed the package decides which command may be used: upgrading
a pipx installation with plain pip corrupts the pipx metadata, and a uv tool
is invisible to pip altogether. Getting the detection wrong therefore breaks
the installation it was meant to update.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencloud_local_scan import selfupdate
from opencloud_local_scan.selfupdate import UpgradeError


def pretend_installed_at(monkeypatch, path: str, *, tools=("pipx", "uv")):
    """Run the detection as if the package lived at ``path``."""
    monkeypatch.setattr(selfupdate, "_module_path", lambda: Path(path))
    monkeypatch.setattr(selfupdate, "_is_source_checkout", lambda _: False)
    monkeypatch.setattr(
        selfupdate.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in tools else None,
    )


def test_a_pipx_installation_is_upgraded_with_pipx(monkeypatch):
    """pip would leave pipx's own metadata pointing at the old version."""
    pretend_installed_at(
        monkeypatch, "/home/u/.local/pipx/venvs/check-opencloud-security/lib/x.py"
    )

    plan = selfupdate.plan_upgrade()

    assert plan.installer == "pipx"
    assert plan.command == (
        "/usr/bin/pipx",
        "upgrade",
        "check-opencloud-security",
    )
    assert "pip install" not in plan.display


def test_a_uv_tool_installation_is_upgraded_with_uv(monkeypatch):
    """pip cannot see a uv tool at all, so it would report nothing to do."""
    pretend_installed_at(
        monkeypatch, "/home/u/.local/share/uv/tools/check-opencloud-security/x.py"
    )

    plan = selfupdate.plan_upgrade()

    assert plan.installer == "uv"
    assert plan.command[:3] == ("/usr/bin/uv", "tool", "upgrade")


def test_anything_else_falls_back_to_pip(monkeypatch):
    """A plain pip install is the common case and must still be upgradable."""
    pretend_installed_at(monkeypatch, "/opt/venv/lib/python3.12/site-packages/x.py")
    monkeypatch.setattr(selfupdate, "_in_virtualenv", lambda: True)

    plan = selfupdate.plan_upgrade()

    assert plan.installer == "pip"
    assert plan.command[1:5] == ("-m", "pip", "install", "--upgrade")
    assert "--user" not in plan.command


def test_a_system_install_outside_a_virtualenv_uses_user(monkeypatch):
    """Without --user, pip would try to write into a read-only system directory."""
    pretend_installed_at(monkeypatch, "/usr/lib/python3/site-packages/x.py")
    monkeypatch.setattr(selfupdate, "_in_virtualenv", lambda: False)
    monkeypatch.setattr(selfupdate, "_site_packages_writable", lambda _: False)

    plan = selfupdate.plan_upgrade()

    assert "--user" in plan.command
    assert plan.command.index("--user") > plan.command.index("--upgrade")


def test_a_missing_installer_is_reported_rather_than_worked_around(monkeypatch):
    """Silently falling back to pip here is exactly what breaks a pipx install."""
    pretend_installed_at(
        monkeypatch, "/home/u/.local/pipx/venvs/check-opencloud-security/x.py", tools=()
    )

    with pytest.raises(UpgradeError, match="pipx is not on PATH"):
        selfupdate.plan_upgrade()


def test_a_source_checkout_is_refused():
    """Installing over a working copy leaves the operator editing dead files."""
    # The test suite itself runs from the checkout, so this is the real thing.
    assert selfupdate._is_source_checkout(selfupdate._module_path())
    with pytest.raises(UpgradeError, match="source checkout"):
        selfupdate.plan_upgrade()


def test_an_installed_copy_is_not_mistaken_for_a_checkout(monkeypatch):
    """The checkout guard must not block the installations it exists to protect."""
    monkeypatch.setattr(
        selfupdate, "_module_path", lambda: Path("/opt/venv/lib/site-packages/x.py")
    )
    monkeypatch.setattr(selfupdate, "_in_virtualenv", lambda: True)

    assert selfupdate.plan_upgrade().installer == "pip"


def test_a_dry_run_changes_nothing_but_still_names_the_command(monkeypatch):
    """The point of --dry-run is to see the command without a host changing itself."""
    pretend_installed_at(
        monkeypatch, "/home/u/.local/pipx/venvs/check-opencloud-security/x.py"
    )
    ran = []
    monkeypatch.setattr(selfupdate, "run_upgrade", lambda plan: ran.append(plan))
    said: list[str] = []

    code = selfupdate.upgrade_self(dry_run=True, version="1.2.3", output=said.append)

    assert code == 0
    assert ran == []
    assert any("pipx upgrade" in line for line in said)
    assert any("1.2.3" in line for line in said)


def test_a_real_run_executes_the_planned_command(monkeypatch):
    """Without --dry-run the command has to actually run, or nothing is upgraded."""
    pretend_installed_at(
        monkeypatch, "/home/u/.local/pipx/venvs/check-opencloud-security/x.py"
    )
    ran = []
    monkeypatch.setattr(selfupdate, "run_upgrade", lambda plan: ran.append(plan) or 0)

    code = selfupdate.upgrade_self(output=lambda _: None)

    assert code == 0
    assert [plan.installer for plan in ran] == ["pipx"]


def test_a_failed_upgrade_exits_unknown(monkeypatch):
    """A monitoring plugin reports a problem it cannot classify as UNKNOWN (3)."""
    pretend_installed_at(
        monkeypatch, "/home/u/.local/pipx/venvs/check-opencloud-security/x.py"
    )

    def explode(plan):
        raise UpgradeError("boom")

    monkeypatch.setattr(selfupdate, "run_upgrade", explode)
    said: list[str] = []

    code = selfupdate.upgrade_self(output=said.append)

    assert code == 3
    assert any(line.startswith("UNKNOWN: ") and "boom" in line for line in said)


def test_a_non_zero_exit_from_the_installer_is_an_error(monkeypatch):
    """A failed 'pipx upgrade' must not be reported as a successful upgrade."""
    plan = selfupdate.UpgradePlan("pipx", ("/usr/bin/pipx", "upgrade", "x"), "test")

    class Completed:
        returncode = 1

    monkeypatch.setattr(selfupdate.subprocess, "run", lambda *a, **k: Completed())

    with pytest.raises(UpgradeError, match="exit code 1"):
        selfupdate.run_upgrade(plan)


def test_the_command_is_never_a_shell_string(monkeypatch):
    """Building a shell string out of a package name is how injection starts."""
    for path in (
        "/home/u/.local/pipx/venvs/check-opencloud-security/x.py",
        "/home/u/.local/share/uv/tools/check-opencloud-security/x.py",
        "/opt/venv/lib/python3.12/site-packages/x.py",
    ):
        pretend_installed_at(monkeypatch, path)
        monkeypatch.setattr(selfupdate, "_in_virtualenv", lambda: True)
        plan = selfupdate.plan_upgrade()
        assert isinstance(plan.command, tuple)
        assert all(isinstance(part, str) for part in plan.command)
        assert not any(char in part for part in plan.command for char in ";|&$")
