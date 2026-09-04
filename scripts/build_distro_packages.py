#!/usr/bin/env python3
"""
Build the .deb and the .rpm from the wheel that was already built.

The plugin's audience is monitoring hosts, where software arrives through
``apt install`` and ``dnf install`` rather than through pip. This turns the
artifact the release already produces into packages for both, using
`nfpm <https://nfpm.goreleaser.com/>`_ - which builds a .deb and an .rpm from
one recipe without needing dpkg-dev, rpmbuild or a matching distribution to
build on. See ``adr/0039``.

    python scripts/build_distro_packages.py                     # needs dist/*.whl
    python scripts/build_distro_packages.py --wheel dist/x.whl
    python scripts/build_distro_packages.py --packager deb      # just the one

The wheel is unpacked into one private directory, ``/usr/lib/check-opencloud-security``,
rather than into the system's site-packages: a distribution package that wrote
into site-packages would fight with a ``pip install`` of the same name on the
same host, and this way the interpreter can move underneath it without a
rebuild. The two commands on ``PATH`` are shell launchers from ``packaging/``
that find an interpreter and hand over to that directory.

The layout, the dependencies and everything else the packages declare live in
``packaging/nfpm.yaml``. This script only assembles what that recipe points at.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess  # nosec B404 - fixed argv built here, never a shell string
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "packaging" / "nfpm.yaml"
PACKAGERS = ("deb", "rpm")

#: Where the recipe's `src:` paths resolve. Fixed rather than passed in:
#: nfpm expands environment variables in scalar fields such as `version`, but
#: not inside a content `src`, so the recipe has to name this literally and
#: nfpm has to be run from the repository root.
STAGE = ROOT / "build" / "distro-stage"

#: Where the payload lands on the installed host. The launchers in
#: ``packaging/`` hardcode the same path; ``tests/test_distro_packaging.py``
#: holds them to it.
INSTALL_PREFIX = "/usr/lib/check-opencloud-security"

#: Dropped beside the payload so that ``--upgrade-self`` can tell it is looking
#: at a distribution package and send the operator to apt or dnf instead of
#: letting pip install a second copy that the launcher would never run. Its
#: content is the packager, so the message can name the right command.
MARKER_NAME = "distro-package"

LAUNCHERS = {
    "check-opencloud-security": "check-opencloud-security.sh",
    "check-opencloud-scanner": "check-opencloud-scanner.sh",
}

UNITS = (
    "check-opencloud-security.service",
    "check-opencloud-security.timer",
    "check-opencloud-security-refresh.service",
    "check-opencloud-security-refresh.timer",
)

#: The contrib units are written for a pipx/pip install, which puts its
#: commands in /usr/local/bin. The package puts them in /usr/bin.
UNIT_REWRITES = (("/usr/local/bin/", "/usr/bin/"),)


class BuildError(RuntimeError):
    """Raised when the packages cannot be built."""


def _project_version() -> str:
    """The version in pyproject.toml, which is the only place it is written."""
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise BuildError("pyproject.toml has no version")


def _find_wheel(explicit: Path | None) -> Path:
    """The wheel to package, and a clear error rather than a wrong one."""
    if explicit is not None:
        if not explicit.is_file():
            raise BuildError(f"no such wheel: {explicit}")
        return explicit
    candidates = sorted((ROOT / "dist").glob("check_opencloud_security-*.whl"))
    if not candidates:
        raise BuildError(
            "no wheel in dist/. Run 'uv build' first, or pass --wheel."
        )
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise BuildError(
            f"dist/ holds several wheels ({names}). Pass --wheel to say which one."
        )
    return candidates[0]


def _wheel_version(wheel: Path) -> str:
    """The version the wheel's filename declares."""
    # check_opencloud_security-1.2.3-py3-none-any.whl
    parts = wheel.name.split("-")
    if len(parts) < 2:
        raise BuildError(f"cannot read a version from {wheel.name}")
    return parts[1]


def _entrypoint_script() -> str:
    """
    The scanner's entry point, as a file the launcher can run.

    ``python -m`` would do the same job, but before 3.11 it puts the caller's
    working directory first on ``sys.path``. A check runs from wherever cron
    happened to be, and a module sitting there must not be able to shadow one
    the scan trusts. Running a script inside the payload puts the payload
    first instead. The plugin needs no such file: its module is already a
    script.
    """
    return '''"""
The `check-opencloud-scanner` command, as installed by the .deb and the .rpm.

Generated by scripts/build_distro_packages.py - see the note there for why the
launcher runs this rather than `python -m opencloud_local_scan.cli`.
"""

import sys

from opencloud_local_scan.cli import main

if __name__ == "__main__":
    sys.exit(main())
'''


def _readme(version: str) -> str:
    """The note that answers "where did it put everything"."""
    return f"""# check-opencloud-security {version}

A Nagios/Icinga plugin that rates the security of an OpenCloud instance with a
scanner built in. It probes the instance itself and decides the rating locally:
no third party is asked for a verdict, and an instance that never faces the
internet is checked exactly like one that does.

## What this package installed

    /usr/bin/check-opencloud-security          the check
    /usr/bin/check-opencloud-scanner           the same scanner, as a JSON tool
    /usr/lib/nagios/plugins/                   a symlink to the check
    {INSTALL_PREFIX}/     the code itself
    /etc/check-opencloud-security/             empty, and searched for config.yml
    /usr/lib/systemd/system/                   four units, none of them enabled

## Run it

    check-opencloud-security --host opencloud.example.com --check-hardening

## Configure it

Nothing here configures a target: an example naming a host that is not yours,
installed as a live configuration, would give every invocation on this machine
a default it never asked for. Start from the examples in this directory:

    cp /usr/share/doc/check-opencloud-security/config.example.yml \\
       /etc/check-opencloud-security/config.yml

    cp /usr/share/doc/check-opencloud-security/env.example \\
       /etc/check-opencloud-security/env      # for the systemd units

`check-opencloud-security --configure` asks the same questions interactively.
Precedence is command-line flag > environment variable > configuration file.

## Scheduling it

The units ship disabled and need `/etc/check-opencloud-security/env` first:

    systemctl enable --now check-opencloud-security.timer

`check-opencloud-security-refresh.timer` keeps the bundled release schedule and
advisory database current, which matters here because both ship *inside* the
package.

## Updating it

Through apt or dnf, like anything else this host installed. `--upgrade-self`
knows it is looking at a distribution package and will say so rather than let
pip install a second copy beside this one.

## Interpreter

The launchers need Python 3.10 or newer and search for one: `python3` first,
then `python3.14` down to `python3.10`. Set `COS_PYTHON` to override that.
RHEL 9 answers 3.9 to `python3` and carries newer ones beside it, which is why
the search exists.

## More

    https://github.com/sowoi/check-opencloud-security

## Trademarks and affiliation

This is an independent community project, not affiliated with, endorsed by or
supported by OpenCloud GmbH. "OpenCloud" and all related marks belong to their
respective owners and are used only to identify the software this tool checks.
"""


def _stage(stage: Path, wheel: Path, version: str) -> None:
    """Assemble everything ``packaging/nfpm.yaml`` points at."""
    payload = stage / "payload"
    payload.mkdir(parents=True)
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(payload)  # nosec B202 - our own freshly built wheel

    if not (payload / "check_opencloud_security.py").is_file():
        raise BuildError(f"{wheel.name} carries no check_opencloud_security.py")
    if not (payload / "opencloud_local_scan").is_dir():
        raise BuildError(f"{wheel.name} carries no opencloud_local_scan/")

    (payload / "check-opencloud-scanner.py").write_text(
        _entrypoint_script(), encoding="utf-8"
    )

    binaries = stage / "bin"
    binaries.mkdir()
    for installed, source in LAUNCHERS.items():
        shutil.copy2(ROOT / "packaging" / source, binaries / installed)
        (binaries / installed).chmod(0o755)

    units = stage / "systemd"
    units.mkdir()
    for unit in UNITS:
        text = (ROOT / "contrib" / "systemd" / unit).read_text(encoding="utf-8")
        for old, new in UNIT_REWRITES:
            text = text.replace(old, new)
        (units / unit).write_text(text, encoding="utf-8")

    documentation = stage / "doc"
    documentation.mkdir()
    (documentation / "README.md").write_text(_readme(version), encoding="utf-8")


def _nfpm() -> str:
    """Where nfpm is, or an error naming how to get it."""
    found = shutil.which("nfpm")
    if found is None:
        raise BuildError(
            "nfpm is not on PATH. Install it from "
            "https://nfpm.goreleaser.com/install/ , or run this in the "
            "goreleaser/nfpm container."
        )
    return found


def _target(output_dir: Path, packager: str, version: str) -> Path:
    """
    The filename to write, spelled out rather than left to nfpm.

    Both ecosystems have a conventional name and nfpm produces it, but naming
    it here means the release workflow attaches a file it can predict.
    """
    if packager == "deb":
        return output_dir / f"check-opencloud-security_{version}_all.deb"
    return output_dir / f"check-opencloud-security-{version}-1.noarch.rpm"


def build(
    output_dir: Path, wheel: Path | None = None, packagers: tuple[str, ...] = PACKAGERS
) -> list[Path]:
    """Build each requested package and return where they landed."""
    version = _project_version()
    source = _find_wheel(wheel)
    built = _wheel_version(source)
    if built != version:
        raise BuildError(
            f"{source.name} is version {built}, but pyproject.toml declares "
            f"{version}. Rebuild the wheel rather than packaging a stale one."
        )

    nfpm = _nfpm()
    output_dir.mkdir(parents=True, exist_ok=True)
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    artifacts: list[Path] = []
    try:
        _stage(STAGE, source, version)
        environment = {**os.environ, "COS_PACKAGE_VERSION": version}
        for packager in packagers:
            # Rewritten per packager so the installed marker can name the
            # command that actually manages this copy.
            (STAGE / "payload" / MARKER_NAME).write_text(
                f"{packager}\n", encoding="utf-8"
            )
            target = _target(output_dir, packager, version)
            completed = subprocess.run(  # nosec B603 - argv built above, no shell
                [nfpm, "package", "--config", str(RECIPE),
                 "--packager", packager, "--target", str(target)],
                cwd=ROOT,
                env=environment,
                check=False,
            )
            if completed.returncode != 0:
                raise BuildError(
                    f"nfpm failed to build the {packager} package "
                    f"(exit {completed.returncode})."
                )
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            target.with_name(target.name + ".sha256").write_text(
                f"{digest}  {target.name}\n", encoding="utf-8"
            )
            artifacts.append(target)
    finally:
        shutil.rmtree(STAGE, ignore_errors=True)

    return artifacts


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "distro-packages",
        help="where to write the packages (default: distro-packages/)",
    )
    parser.add_argument(
        "--wheel", type=Path, default=None, help="the wheel to package (default: dist/)"
    )
    parser.add_argument(
        "--packager",
        action="append",
        choices=PACKAGERS,
        help="build only this one; repeatable (default: both)",
    )
    arguments = parser.parse_args(argv)

    try:
        artifacts = build(
            arguments.output_dir,
            arguments.wheel,
            tuple(arguments.packager) if arguments.packager else PACKAGERS,
        )
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    for artifact in artifacts:
        size = artifact.stat().st_size / 1024
        print(f"{artifact} ({size:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
