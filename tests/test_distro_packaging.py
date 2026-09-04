"""
What the .deb and the .rpm install, and where.

The plugin's audience is monitoring hosts, where software arrives through apt
and dnf. Those packages are assembled by `scripts/build_distro_packages.py`
from the wheel the release already builds, using the recipe in
`packaging/nfpm.yaml`.

nfpm is a Go binary that this suite deliberately does not require: what breaks
here is not nfpm's archive writing but the agreement between three files that
have to keep saying the same thing - the recipe, the launchers on PATH, and
the build script that fills the staging tree they point at. A path changed in
one of them produces a package that installs cleanly and then cannot find its
own code, which no test that only ran nfpm would notice either.
"""

from __future__ import annotations

import stat
import subprocess  # nosec B404 - runs this project's own launcher scripts
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_distro_packages as builder

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "packaging" / "nfpm.yaml"
LAUNCHERS = (
    ROOT / "packaging" / "check-opencloud-security.sh",
    ROOT / "packaging" / "check-opencloud-scanner.sh",
)


@pytest.fixture(scope="module")
def recipe() -> dict:
    """The nfpm recipe, with the one environment variable it expands set."""
    text = RECIPE.read_text(encoding="utf-8").replace("${COS_PACKAGE_VERSION}", "0.0.0")
    return yaml.safe_load(text)


def _destinations(recipe: dict, packager: str | None = None) -> set[str]:
    """Every path the recipe installs, for one packager or for all of them."""
    return {
        entry["dst"]
        for entry in recipe["contents"]
        if packager is None or entry.get("packager") in (None, packager)
    }


# --- the three files have to agree ------------------------------------------


def test_the_launchers_look_where_the_recipe_installs_the_payload(recipe):
    """
    The one agreement that makes the package work at all.

    The launcher hardcodes an absolute path because it has no way to discover
    one; the recipe decides where the payload lands. If those drift, apt
    installs a package whose commands exit "no such file" on a host where
    nothing looks wrong.
    """
    installed = {
        entry["dst"] for entry in recipe["contents"] if entry.get("type") == "tree"
    }

    assert installed == {builder.INSTALL_PREFIX}
    for launcher in LAUNCHERS:
        assert f'PAYLOAD="{builder.INSTALL_PREFIX}"' in launcher.read_text(
            encoding="utf-8"
        )


def test_every_staged_path_the_recipe_reads_is_one_the_build_script_writes(
    recipe, tmp_path, wheel
):
    """
    nfpm fails late and per-file; this fails once, here.

    A `src:` pointing at something the staging step does not produce is only
    discovered when nfpm runs, which on the release path is after the wheel
    has already gone to PyPI.
    """
    builder._stage(tmp_path, wheel, "0.0.0")

    staged = "build/distro-stage/"
    wanted = [
        entry["src"][len(staged) :]
        for entry in recipe["contents"]
        if str(entry.get("src", "")).startswith(staged)
    ]

    assert wanted, "the recipe no longer reads anything from the staging tree"
    for relative in wanted:
        assert (tmp_path / relative).exists(), f"{relative} is never staged"


def test_the_recipe_reads_nothing_from_a_path_that_does_not_exist(recipe):
    """Sources outside the staging tree are repository files, and must be there."""
    for entry in recipe["contents"]:
        source = str(entry.get("src", ""))
        if not source or source.startswith(("build/distro-stage/", "/")):
            continue
        assert (ROOT / source).exists(), f"{source} is in the recipe but not the tree"


# --- what an operator gets --------------------------------------------------


def test_both_commands_land_on_path_and_are_executable(recipe):
    """The package exists so that `check-opencloud-security` is simply there."""
    for entry in recipe["contents"]:
        if entry["dst"].startswith("/usr/bin/"):
            assert entry["file_info"]["mode"] == 0o755

    assert {"/usr/bin/check-opencloud-security", "/usr/bin/check-opencloud-scanner"} <= (
        _destinations(recipe)
    )


def test_the_check_is_linked_into_each_ecosystems_plugin_directory(recipe):
    """
    Debian puts monitoring plugins under /usr/lib, the RPM world under /usr/lib64.

    Getting this wrong does not fail the build: it produces a package that
    installs and a monitoring daemon that reports the check as missing.
    """
    links = {
        entry["dst"]: entry
        for entry in recipe["contents"]
        if entry.get("type") == "symlink"
    }

    assert "/usr/lib/nagios/plugins/check_opencloud_security" in links
    assert "/usr/lib64/nagios/plugins/check_opencloud_security" in links
    assert links["/usr/lib/nagios/plugins/check_opencloud_security"]["packager"] == "deb"
    assert (
        links["/usr/lib64/nagios/plugins/check_opencloud_security"]["packager"] == "rpm"
    )
    for link in links.values():
        assert link["src"] == "/usr/bin/check-opencloud-security"


def test_the_package_configures_nothing(recipe):
    """
    An installed example would give every invocation on the host a default target.

    `config/check-opencloud-security.example.yml` names a host that is not the
    operator's, and `/etc/check-opencloud-security/config.yml` is a path the
    plugin actually reads. The example therefore ships as documentation, and
    the directory ships empty.
    """
    assert "/etc/check-opencloud-security" in _destinations(recipe)
    for entry in recipe["contents"]:
        if entry["dst"] == "/etc/check-opencloud-security":
            assert entry["type"] == "dir"
    assert not [
        entry["dst"]
        for entry in recipe["contents"]
        if entry["dst"].startswith("/etc/check-opencloud-security/")
    ]


def test_no_unit_is_enabled_or_started_by_installing_the_package():
    """
    Installing a check must not begin scanning anything.

    The units need /etc/check-opencloud-security/env before they do anything
    useful, and a host that starts probing a target nobody named is a
    surprise, not a convenience.
    """
    for script in (ROOT / "packaging" / "scripts").glob("*.sh"):
        # Comments discuss what these deliberately do not do, so read the code.
        code = "\n".join(
            line
            for line in script.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "systemctl enable" not in code
        assert "systemctl start" not in code
        assert "daemon-reload" in code


def test_the_rpm_names_the_python_yaml_package_its_own_ecosystem_uses(recipe):
    """`python3-yaml` on Debian is `python3-pyyaml` on Fedora and RHEL."""
    assert "python3-yaml" in recipe["overrides"]["deb"]["depends"]
    assert "python3-pyyaml" in recipe["overrides"]["rpm"]["depends"]
    assert "python3-yaml" not in recipe["overrides"]["rpm"]["depends"]


def test_the_rpm_does_not_demand_a_python3_that_rhel_calls_something_else(recipe):
    """
    RHEL 9's `python3` is 3.9, and it packages 3.11 and 3.12 beside it.

    A versioned dependency there refuses to install on a host that runs this
    perfectly well - the launcher finds the newer interpreter by name. Debian
    has no such split, so it keeps the honest floor.
    """
    assert any(
        dependency.startswith("python3 (>=")
        for dependency in recipe["overrides"]["deb"]["depends"]
    )
    assert "python3" in recipe["overrides"]["rpm"]["depends"]
    assert not any(
        dependency.startswith("python3 ")
        for dependency in recipe["overrides"]["rpm"]["depends"]
    )


def test_the_stub_only_dependency_is_not_asked_of_a_distribution(recipe):
    """
    `types-requests` is in the wheel's metadata and no distribution packages it.

    It is a stub package with nothing to import at runtime, so demanding it
    would make the package uninstallable everywhere in exchange for nothing.
    """
    declared = " ".join(
        recipe["depends"]
        + recipe["overrides"]["deb"]["depends"]
        + recipe["overrides"]["rpm"]["depends"]
    )
    assert "types-requests" not in declared
    assert "python3-requests" in declared


# --- the staged payload -----------------------------------------------------


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    """Build the real wheel, because that is what the package is made of."""
    pytest.importorskip("build", reason="staging the payload needs a real wheel")
    pytest.importorskip("hatchling", reason="the wheel is built without isolation")
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(  # nosec B603 - fixed argument list, no shell
        [sys.executable, "-m", "build", "--wheel", "--no-isolation",
         "--outdir", str(out), str(ROOT)],
        check=True,
        capture_output=True,
    )
    return next(out.glob("*.whl"))


def test_the_payload_keeps_the_metadata_that_answers_version(tmp_path, wheel):
    """
    Without the .dist-info, `--version` reports 0.0.0 on every installed host.

    The payload sits in its own directory with no pyproject.toml above it, so
    `_detect_version` falls through to importlib.metadata - which reads the
    .dist-info the wheel carries and nothing else.
    """
    builder._stage(tmp_path, wheel, "0.0.0")
    payload = tmp_path / "payload"

    assert list(payload.glob("check_opencloud_security-*.dist-info"))
    assert (payload / "check_opencloud_security.py").is_file()
    assert (payload / "opencloud_local_scan" / "__init__.py").is_file()


def test_the_scanner_entry_point_is_a_script_rather_than_a_module_run(tmp_path, wheel):
    """
    `python -m` puts the caller's working directory first on sys.path before 3.11.

    A check runs from wherever cron happened to be. A `requests.py` sitting
    there must not become the requests this scan trusts, so the launcher runs
    a file inside the payload and sys.path starts at the payload instead.
    """
    builder._stage(tmp_path, wheel, "0.0.0")
    entrypoint = tmp_path / "payload" / "check-opencloud-scanner.py"

    assert entrypoint.is_file()
    assert "from opencloud_local_scan.cli import main" in entrypoint.read_text(
        encoding="utf-8"
    )
    for launcher in LAUNCHERS:
        text = launcher.read_text(encoding="utf-8")
        assert " -m " not in text
        assert 'exec "$candidate" "$ENTRYPOINT"' in text


def test_the_units_point_at_the_path_this_package_actually_installs(tmp_path, wheel):
    """
    The contrib units are written for pipx, which installs into /usr/local/bin.

    The package installs into /usr/bin. A unit shipped unrewritten fails on
    every host that enables it.
    """
    builder._stage(tmp_path, wheel, "0.0.0")

    for unit in (tmp_path / "systemd").glob("*.service"):
        text = unit.read_text(encoding="utf-8")
        assert "/usr/local/bin/" not in text
        assert "ExecStart=/usr/bin/check-opencloud-" in text


def test_the_launchers_are_staged_executable(tmp_path, wheel):
    """A launcher without the execute bit is a command that does not exist."""
    builder._stage(tmp_path, wheel, "0.0.0")

    for name in ("check-opencloud-security", "check-opencloud-scanner"):
        mode = (tmp_path / "bin" / name).stat().st_mode
        assert mode & stat.S_IXUSR
        assert mode & stat.S_IXOTH


def test_a_wheel_of_the_wrong_version_is_refused(tmp_path, wheel, monkeypatch):
    """
    Packaging a stale wheel would ship the old code under the new number.

    dist/ survives between builds, so the wheel sitting there is not
    necessarily the one for the version pyproject.toml now declares.
    """
    monkeypatch.setattr(builder, "_project_version", lambda: "99.99.99")
    monkeypatch.setattr(builder, "_nfpm", lambda: "/nonexistent/nfpm")

    with pytest.raises(builder.BuildError, match="Rebuild the wheel"):
        builder.build(tmp_path / "out", wheel)


# --- the launcher's own behaviour -------------------------------------------


def test_a_host_without_a_usable_python_gets_unknown_rather_than_a_verdict():
    """
    Exit 3 is Nagios UNKNOWN.

    A plugin that could not run has measured nothing. Exiting 0 would report
    the instance as healthy on the strength of a missing interpreter, and
    exiting 2 would page somebody about the wrong host.
    """
    launcher = ROOT / "packaging" / "check-opencloud-security.sh"
    completed = subprocess.run(  # nosec B603 - our own script, fixed argv
        ["/bin/sh", str(launcher), "--version"],
        env={"PATH": "/nonexistent", "COS_PYTHON": ""},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3
    assert "3.10" in completed.stderr
    assert "COS_PYTHON" in completed.stderr


def test_the_launcher_prefers_an_interpreter_the_operator_named():
    """
    COS_PYTHON is the escape hatch for a host whose python3 is not the one to use.

    Without it, a RHEL 9 host that installed python3.12 into a prefix of its
    own has no way to say so.
    """
    launcher = ROOT / "packaging" / "check-opencloud-security.sh"
    text = launcher.read_text(encoding="utf-8")

    assert "${COS_PYTHON:-}" in text
    # The named interpreter is tried before the distribution's default, and
    # every fallback is still version-checked rather than trusted by name.
    candidates = [line for line in text.splitlines() if line.startswith("for candidate")]
    assert len(candidates) == 1
    assert candidates[0].index("COS_PYTHON") < candidates[0].index("python3")
    assert "sys.version_info >= (3, 10)" in text
