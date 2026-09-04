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


def _pretend_distro_install(monkeypatch, tmp_path: Path, packager: str) -> Path:
    """Lay out a payload the way the .deb and the .rpm install one."""
    payload = tmp_path / "usr" / "lib" / "check-opencloud-security"
    (payload / "opencloud_local_scan").mkdir(parents=True)
    (payload / selfupdate.DISTRO_MARKER_NAME).write_text(
        f"{packager}\n", encoding="utf-8"
    )
    module = payload / "opencloud_local_scan" / "selfupdate.py"
    module.touch()
    monkeypatch.setattr(selfupdate, "_module_path", lambda: module)
    return module


@pytest.mark.parametrize(
    ("packager", "command"),
    [("deb", "apt install --only-upgrade"), ("rpm", "dnf upgrade")],
)
def test_a_distribution_package_sends_the_operator_to_its_package_manager(
    monkeypatch, tmp_path, packager, command
):
    """
    pip would appear to succeed here and change nothing that runs.

    The .deb and the .rpm put the payload in one private directory and a
    launcher on PATH that only ever reads it. A pip upgrade installs into the
    user's site-packages, which that launcher never consults - so the operator
    is told the upgrade worked, has two versions on the host, and is still
    running the old one.
    """
    _pretend_distro_install(monkeypatch, tmp_path, packager)

    with pytest.raises(UpgradeError, match="distribution package") as raised:
        selfupdate.plan_upgrade()

    assert command in str(raised.value)
    assert "pip install" not in str(raised.value).split("instead")[0]


def test_a_marker_nobody_wrote_does_not_make_every_install_a_distro_one(
    monkeypatch, tmp_path
):
    """The negative case: without the marker, detection carries on as before."""
    payload = tmp_path / "opt" / "venv" / "lib" / "site-packages"
    payload.mkdir(parents=True)
    module = payload / "x.py"
    module.touch()
    monkeypatch.setattr(selfupdate, "_module_path", lambda: module)
    monkeypatch.setattr(selfupdate, "_in_virtualenv", lambda: True)

    assert selfupdate._distro_package(module) is None
    assert selfupdate.plan_upgrade().installer == "pip"


def test_an_unreadable_marker_still_counts_as_a_distribution_package(
    monkeypatch, tmp_path
):
    """The file being there is the claim; its contents only pick the wording."""
    module = _pretend_distro_install(monkeypatch, tmp_path, packager="")

    assert selfupdate._distro_package(module) == "unknown"
    with pytest.raises(UpgradeError, match="package manager"):
        selfupdate.plan_upgrade()


def test_a_dry_run_changes_nothing_but_still_names_the_command(monkeypatch):
    """--upgrade-self=check shows the command without a host changing itself."""
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
    """With --upgrade-self=run the command has to run, or nothing is upgraded."""
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


# --- Is the plugin itself out of date? ---


class FakeResponse:
    """Just enough of a requests response for the PyPI lookup."""

    def __init__(self, payload, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise selfupdate.requests.HTTPError(f"status {self.status}")

    def json(self):
        return self._payload


def answer_pypi(monkeypatch, payload, *, calls=None):
    """Make the PyPI lookup return a fixed document without touching the network."""

    def fake_get(url, timeout=None):
        if calls is not None:
            calls.append(url)
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)

    monkeypatch.setattr(selfupdate.requests, "get", fake_get)


def test_a_newer_published_version_becomes_a_note(monkeypatch, tmp_path):
    """A plugin that never reports its own age is a blind spot in the monitoring."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    answer_pypi(monkeypatch, {"info": {"version": "9.9.9"}})

    note = selfupdate.self_update_note("1.0.0")

    assert note is not None
    assert "9.9.9" in note
    assert "--upgrade-self" in note


def test_an_up_to_date_installation_says_nothing(monkeypatch, tmp_path):
    """A note on every single run would be noise, and noise gets filtered out."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    answer_pypi(monkeypatch, {"info": {"version": "1.0.0"}})

    assert selfupdate.self_update_note("1.0.0") is None
    assert selfupdate.self_update_note("1.1.0") is None, "a dev build is not out of date"


def test_the_answer_is_cached_so_every_check_does_not_hit_pypi(monkeypatch, tmp_path):
    """A check running every minute must not query PyPI every minute."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    calls: list[str] = []
    answer_pypi(monkeypatch, {"info": {"version": "9.9.9"}}, calls=calls)

    assert selfupdate.self_update_note("1.0.0") is not None
    assert selfupdate.self_update_note("1.0.0") is not None

    assert len(calls) == 1, calls
    assert selfupdate.cache_path().exists()


def test_a_stale_cache_is_refreshed(monkeypatch, tmp_path):
    """Cached forever would be the same blind spot with extra steps."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    calls: list[str] = []
    answer_pypi(monkeypatch, {"info": {"version": "9.9.9"}}, calls=calls)

    selfupdate.self_update_note("1.0.0")
    selfupdate.self_update_note("1.0.0", max_age=-1)

    assert len(calls) == 2, calls


def test_an_unreachable_pypi_is_silent(monkeypatch, tmp_path):
    """Whether PyPI answered says nothing about the instance being monitored."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    answer_pypi(monkeypatch, selfupdate.requests.ConnectionError("no route to host"))

    assert selfupdate.self_update_note("1.0.0") is None
    assert selfupdate.latest_released_version() is None


def test_a_nonsense_answer_is_silent(monkeypatch, tmp_path):
    """A captive portal returning HTML must not be read as a version."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    answer_pypi(monkeypatch, {"nothing": "useful"})

    assert selfupdate.self_update_note("1.0.0") is None


def test_check_only_is_the_same_request_as_upgrade_self_check(monkeypatch):
    """The pairing spelling must not accidentally upgrade a monitoring host."""
    import check_opencloud_security as check

    seen: list[bool] = []

    def fake_upgrade(*, dry_run=False, version=None):
        seen.append(dry_run)
        return 0

    monkeypatch.setattr(check, "upgrade_self", fake_upgrade)

    check._run_early_commands(["--upgrade-self", "--check-only"])
    check._run_early_commands(["--upgrade-self=check"])
    check._run_early_commands(["--upgrade-self"])

    assert seen == [True, True, False]
