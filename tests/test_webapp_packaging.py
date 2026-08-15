"""
What ends up on PyPI, and what deliberately does not.

The plugin is installed on monitoring hosts by people who want a check, not a
web application. The wheel therefore carries the plugin and the scanner
library and nothing else: no FastAPI wrapper, no templates, no CSS, and no
dependency on any of it.

These tests build the real artefacts with the real backend, because the only
thing worth asserting is what ``pip install`` would actually receive.
"""

from __future__ import annotations

import hashlib
import re
import subprocess  # nosec B404 - builds this project's own artefacts
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytest.importorskip("build", reason="the packaging tests need the build front end")
pytest.importorskip("hatchling", reason="the packaging tests build without isolation")


@pytest.fixture(scope="module")
def artefacts(tmp_path_factory) -> tuple[Path, Path]:
    """Build the wheel and the sdist once, the way the release workflow does."""
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(  # nosec B603 - fixed argument list, no shell
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(out), str(ROOT)],
        check=True,
        capture_output=True,
    )
    wheel = next(out.glob("*.whl"))
    sdist = next(out.glob("*.tar.gz"))
    return wheel, sdist


def _wheel_names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def _sdist_names(sdist: Path) -> list[str]:
    with tarfile.open(sdist) as archive:
        # Strip the leading 'project-1.2.3/' so the assertions read naturally.
        return [name.split("/", 1)[-1] for name in archive.getnames()]


def test_the_wheel_carries_the_plugin_and_the_scanner(artefacts):
    """A positive assertion first: the exclusions must not have excluded the check."""
    wheel, _ = artefacts
    names = _wheel_names(wheel)

    assert "check_opencloud_security.py" in names
    assert any(name.startswith("opencloud_local_scan/") for name in names)
    assert any(name.endswith("release_schedule.json") for name in names)


def test_the_wheel_contains_no_frontend_asset(artefacts):
    """
    Templates, CSS, JavaScript and SVGs have no business on a monitoring host.

    They are also the part most likely to be dragged in by accident, since a
    later change to the include list would pick up whole directories.
    """
    wheel, _ = artefacts
    names = _wheel_names(wheel)

    assert not [name for name in names if name.startswith("frontend/")]
    assert not [name for name in names if name.startswith("webapp/")]
    assert not [name for name in names if name.endswith((".html", ".css", ".js", ".svg"))]


def test_the_sdist_contains_no_frontend_or_web_application(artefacts):
    """
    The sdist is what a distribution packager builds from.

    Shipping the web application there would put a FastAPI service into
    somebody's system package without them ever asking for one.
    """
    _, sdist = artefacts
    names = _sdist_names(sdist)

    assert "check_opencloud_security.py" in names
    assert not [name for name in names if name.startswith("frontend/")]
    assert not [name for name in names if name.startswith("webapp/")]


def test_the_web_application_is_an_extra_and_never_a_dependency(artefacts):
    """
    Installing the plugin must not pull in FastAPI, Redis or ARQ.

    The check runs from cron on hosts where every added dependency is another
    thing that can fail at three in the morning.
    """
    wheel, _ = artefacts
    with zipfile.ZipFile(wheel) as archive:
        metadata = next(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".dist-info/METADATA")
        )

    required = re.findall(
        r"^Requires-Dist: ([A-Za-z0-9._-]+)(.*)$", metadata, re.MULTILINE
    )
    unconditional = {name.lower() for name, tail in required if "extra ==" not in tail}

    for package in ("fastapi", "uvicorn", "redis", "arq", "jinja2"):
        assert package not in unconditional
    # ... and they are on offer, so the extra actually installs something.
    conditional = {
        name.lower() for name, tail in required if "extra ==" in tail and "web" in tail
    }
    assert {"fastapi", "arq", "redis"} <= conditional


def test_the_web_tests_are_not_shipped_with_the_sdist(artefacts):
    """
    The sdist's tests must run against what the sdist contains.

    Shipping a test that imports ``webapp`` into an archive that has no
    ``webapp`` turns a packager's test run into a failure they cannot fix.
    """
    _, sdist = artefacts
    names = _sdist_names(sdist)

    assert "tests/test_local_scanner.py" in names
    assert not [name for name in names if name.startswith("tests/test_webapp_")]


def _bundle(tmp_path: Path) -> tuple[Path, list[str]]:
    """Build the release tarball and return it with its member names."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_web_bundle
    finally:
        sys.path.pop(0)

    archive = build_web_bundle.build(tmp_path, "bundle")
    with tarfile.open(archive) as tar:
        names = [name.split("/", 1)[-1] for name in tar.getnames()]
    return archive, names


def test_the_release_bundle_carries_everything_needed_to_run_the_service(tmp_path):
    """
    The tarball is the only way to get the web application, so it must be whole.

    Somebody downloads this instead of installing from PyPI precisely because
    the wheel leaves the frontend out; an archive missing a template or the
    compose file would strand them with no second source.
    """
    _, names = _bundle(tmp_path)

    for required in (
        "webapp/app.py",
        "webapp/tasks.py",
        "frontend/templates/index.html",
        "frontend/templates/scan.html",
        "frontend/static/css/app.css",
        "frontend/static/js/scan.js",
        "opencloud_local_scan/scanner.py",
        "opencloud_local_scan/data/release_schedule.json",
        "check_opencloud_security.py",
        "docker/Dockerfile.web",
        "docker/docker-compose.yml",
        "docs/webapp.md",
        "QUICKSTART.md",
    ):
        assert required in names, f"the bundle is missing {required}"


def test_the_release_bundle_leaks_no_local_state(tmp_path):
    """
    This archive is downloaded by strangers from a checkout that is somebody's
    working copy, so caches, keys and dotfiles must be filtered rather than
    trusted not to exist.
    """
    _, names = _bundle(tmp_path)

    assert not [name for name in names if "__pycache__" in name]
    assert not [name for name in names if name.endswith((".pyc", ".env", ".key", ".pem"))]
    assert not [name for name in names if name.startswith(("tests/", ".git"))]


def test_the_release_bundle_is_published_with_a_checksum(tmp_path):
    """A download nobody can verify is a download nobody should run."""
    archive, _ = _bundle(tmp_path)
    checksum = archive.with_suffix(archive.suffix + ".sha256")

    assert checksum.is_file()
    digest, _, filename = checksum.read_text(encoding="utf-8").strip().partition("  ")
    assert filename == archive.name
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_every_container_file_lives_in_the_docker_directory():
    """
    One place to look for a Dockerfile, so nobody edits the stale copy.

    The files moved out of the repository root; a new one landing back there
    would be found by half the documentation and none of the readers.
    """
    stray = [
        path.name
        for path in ROOT.iterdir()
        if path.name.startswith(("Dockerfile", "docker-compose"))
    ]
    assert not stray, f"container files belong in docker/: {stray}"

    for expected in (
        "docker/Dockerfile",
        "docker/Dockerfile.web",
        "docker/docker-compose.yml",
        "docker/docker-compose.monitoring.yml",
    ):
        assert (ROOT / expected).is_file(), f"missing {expected}"

    # The context root, and the only place the daemon reads it from.
    assert (ROOT / ".dockerignore").is_file()


@pytest.mark.parametrize(
    "compose", ("docker/docker-compose.yml", "docker/docker-compose.monitoring.yml")
)
def test_a_compose_file_builds_from_the_repository_root(compose):
    """
    An image needs webapp/, frontend/ and the wheel sources, which sit above it.

    A context of '.' inside docker/ builds an image that is missing the
    application, and it fails at run time rather than at build time.
    """
    text = (ROOT / compose).read_text(encoding="utf-8")

    assert "context: .." in text
    assert "context: .\n" not in text
    for line in text.splitlines():
        if line.strip().startswith("dockerfile:"):
            assert line.split(":", 1)[1].strip().startswith("docker/"), line
