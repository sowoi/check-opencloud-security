#!/usr/bin/env python3
"""
Build the standalone web application tarball for a GitHub release.

The PyPI wheel is the plugin and the scanner, and nothing else. Somebody who
wants to *run the web service* needs rather more than that: the FastAPI
wrapper, the frontend, the container files and enough documentation to start
it. That is what this produces.

    python scripts/build_web_bundle.py
    python scripts/build_web_bundle.py --output-dir dist --name my-bundle

The result is ``dist/check_opencloud_security_web.tar.gz``, containing a
single top-level directory so that unpacking it in a home directory does not
scatter files everywhere.

The manifest below is explicit rather than a set of exclusions. A tarball
assembled by leaving things out is one forgotten rule away from shipping a
developer's ``.env``, and this archive is meant to be downloaded by strangers.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "check_opencloud_security_web"

# Directories copied whole. Caches and compiled files are filtered out below.
DIRECTORIES: tuple[str, ...] = (
    "webapp",
    "frontend",
    "opencloud_local_scan",
)

FILES: tuple[str, ...] = (
    "check_opencloud_security.py",
    "pyproject.toml",
    "docker/Dockerfile.web",
    "docker/docker-compose.yml",
    "docker/README.md",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "SECURITY.md",
    "docs/webapp.md",
)

# Never, under any circumstances, in an archive people download.
EXCLUDED_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".git",
        ".env",
        "node_modules",
    }
)
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".env", ".key", ".pem", ".log")


def _keep(path: Path) -> bool:
    """Whether one path belongs in the bundle."""
    if any(part in EXCLUDED_NAMES for part in path.parts):
        return False
    return not path.name.endswith(EXCLUDED_SUFFIXES)


def _version() -> str:
    """The version in pyproject.toml, which is the only place it is written."""
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("pyproject.toml has no version")


def _stage(staging: Path) -> None:
    """Copy the manifest into the staging directory."""
    for name in DIRECTORIES:
        source = ROOT / name
        if not source.is_dir():
            raise SystemExit(f"missing directory: {name}")
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(ROOT)
            if not _keep(relative) or path.is_dir():
                continue
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)

    for name in FILES:
        source = ROOT / name
        if not source.is_file():
            raise SystemExit(f"missing file: {name}")
        destination = staging / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _quickstart(version: str) -> str:
    """The note that greets whoever unpacks the archive."""
    return f"""# check-opencloud-security - web application bundle

Version {version}. This is the complete public scan service: the FastAPI
application in `webapp/`, the frontend in `frontend/`, and the scanner it
calls in `opencloud_local_scan/`.

## Run it

    cd docker && docker compose up --build
    # then open http://127.0.0.1:8080

## Run it without Docker

    pip install ".[web]"
    redis-server &
    COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 python -m webapp.tasks &
    COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 \\
        uvicorn webapp.app:app --host 127.0.0.1 --port 8080

## Before you expose it

Read `docs/webapp.md`. The two settings that matter most are
`COS_WEB_MAX_WORKERS`, which decides how much of the outside world this
service can touch at once, and `COS_WEB_TRUST_FORWARDED_FOR`, which must stay
off unless a reverse proxy in front of it overwrites the header.

The command line plugin is on PyPI as `check-opencloud-security` and does not
include any of this.

## Trademarks and affiliation

This is an independent community project, not affiliated with, endorsed by or
supported by OpenCloud GmbH. "OpenCloud" and all related marks belong to their
respective owners and are used only to identify the software this tool checks.
"""


def build(output_dir: Path, name: str) -> Path:
    """Assemble the tarball and return where it landed."""
    version = _version()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{name}.tar.gz"
    staging_root = output_dir / f".{name}-staging"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging = staging_root / f"{name}-{version}"
    staging.mkdir(parents=True)

    try:
        _stage(staging)
        (staging / "QUICKSTART.md").write_text(_quickstart(version), encoding="utf-8")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname=staging.name)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output_dir / f"{name}.tar.gz.sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    return archive


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "dist", help="where to write the archive"
    )
    parser.add_argument("--name", default=DEFAULT_NAME, help="archive name without suffix")
    arguments = parser.parse_args(argv)

    archive = build(arguments.output_dir, arguments.name)
    size = archive.stat().st_size / 1024
    print(f"{archive} ({size:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
