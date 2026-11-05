#!/usr/bin/env python3
"""Report the CI tool pins that have fallen behind their latest release.

Dependabot keeps the pinned actions, the locked Python packages and the
Docker base images current. It does not know about the other pins CI runs:

- ``uvx tool@x.y.z`` and ``--with package==x.y.z`` (ruff, zizmor, Bandit)
- ``npx @scope/tool@x.y.z`` (Biome) and npm packages named by an
  ``*_VERSION`` variable (mermaid-cli)
- binaries fetched with ``curl`` and checked against a SHA-256, named by an
  ``*_VERSION`` variable (shellcheck, hadolint, actionlint, nfpm)
- uv itself, through ``required-version`` in ``pyproject.toml``

Those go stale silently. This script finds them in ``.github/workflows/``
and compares each with the newest release its registry names:

    python scripts/check_tool_pins.py            # report, exit 1 if behind
    python scripts/check_tool_pins.py --markdown # the same as a Markdown table
    python scripts/check_tool_pins.py --list     # the pins only, no network

It only reports. Raising a binary pin means reading the release and taking a
new SHA-256 on purpose, and the same pin is usually repeated in ``CLAUDE.md``
and the skills, so the weekly workflow opens an issue rather than a pull
request.

A ``*_VERSION`` variable this script has no source for is an error, not a
skip: a new pin should be watched from the day it is added.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

# Where the release named by each `*_VERSION` workflow variable is published.
VERSION_VARIABLES: dict[str, tuple[str, str]] = {
    "ACTIONLINT_VERSION": ("github", "rhysd/actionlint"),
    "HADOLINT_VERSION": ("github", "hadolint/hadolint"),
    "MERMAID_CLI_VERSION": ("npm", "@mermaid-js/mermaid-cli"),
    "NFPM_VERSION": ("github", "goreleaser/nfpm"),
    "SHELLCHECK_VERSION": ("github", "koalaman/shellcheck"),
}

_VERSION = r"(\d+(?:\.\d+)+)"
_UVX_TOOL = re.compile(r"(?<![\w.-])([A-Za-z][\w.-]*)@" + _VERSION + r"\b")
_PINNED_PACKAGE = re.compile(r"(?<![\w.-])([A-Za-z][\w.-]*)==" + _VERSION + r"\b")
_NPX_TOOL = re.compile(r"npx\s+(?:--yes\s+)?(@?[\w.-]+(?:/[\w.-]+)?)@" + _VERSION + r"\b")
_VARIABLE = re.compile(r"^\s*([A-Z][A-Z0-9_]*_VERSION):\s*[\"']?([^\"'\s#]+)")
_YAML_NODE = re.compile(r"^\s*(?:- |[\w-]+:(?:\s|$))")
_TIMEOUT = 20
_ATTEMPTS = 3


@dataclass(frozen=True)
class Pin:
    """One pinned tool version and where it is written."""

    registry: str  # "pypi", "npm" or "github"
    name: str
    version: str
    location: str


def _location(path: Path, number: int) -> str:
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path(path.name)
    return f"{shown.as_posix()}:{number}"


def workflow_pins(workflows: Iterable[Path]) -> list[Pin]:
    """Every tool pin in the given workflow files, in file order."""
    pins: list[Pin] = []
    for path in workflows:
        uvx_continues = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split(" # ", 1)[0]
            if code.lstrip().startswith("#"):
                continue
            where = _location(path, number)

            variable = _VARIABLE.match(code)
            if variable:
                name, version = variable.groups()
                if name not in VERSION_VARIABLES:
                    raise SystemExit(
                        f"{where}: {name} has no release source; add it to "
                        "VERSION_VARIABLES in scripts/check_tool_pins.py"
                    )
                registry, package = VERSION_VARIABLES[name]
                pins.append(Pin(registry, package, version, where))
                continue

            for match in _NPX_TOOL.finditer(code):
                pins.append(Pin("npm", match.group(1), match.group(2), where))

            # A folded `run: >` block puts the uvx arguments on the lines below;
            # the next YAML key or list item ends it.
            starts_node = _YAML_NODE.match(code) is not None
            in_uvx = "uvx " in code or (uvx_continues and not starts_node and code.strip() != "")
            uvx_continues = in_uvx
            if not in_uvx or "npx " in code:
                continue
            for pattern in (_UVX_TOOL, _PINNED_PACKAGE):
                for match in pattern.finditer(code):
                    pins.append(Pin("pypi", match.group(1), match.group(2), where))
    return pins


def uv_pin(pyproject: Path) -> Pin | None:
    """The uv floor CI installs, from ``[tool.uv] required-version``."""
    with pyproject.open("rb") as handle:
        required = tomllib.load(handle).get("tool", {}).get("uv", {}).get("required-version")
    if not required:
        return None
    match = re.fullmatch(r"\s*>=\s*" + _VERSION + r"\s*", required)
    if not match:
        raise SystemExit(f"pyproject.toml: required-version {required!r} is not a plain >= floor")
    return Pin("pypi", "uv", match.group(1), "pyproject.toml [tool.uv] required-version")


def all_pins() -> list[Pin]:
    pins = workflow_pins(sorted(WORKFLOWS_DIR.glob("*.yml")))
    uv = uv_pin(ROOT / "pyproject.toml")
    return pins + ([uv] if uv else [])


def _get_json(url: str) -> dict:
    headers = {"Accept": "application/json", "User-Agent": "check-opencloud-security-pin-report"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # nosec B310
                return json.load(response)
        except urllib.error.HTTPError as error:
            # A 5xx is the registry having a bad minute; a 4xx is an answer.
            if error.code < 500 or attempt == _ATTEMPTS - 1:
                raise
        except OSError:
            if attempt == _ATTEMPTS - 1:
                raise
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def latest_release(registry: str, name: str, get_json: Callable[[str], dict] = _get_json) -> str:
    """The newest stable release of one tool, as its registry names it."""
    if registry == "pypi":
        return str(get_json(f"https://pypi.org/pypi/{name}/json")["info"]["version"])
    if registry == "npm":
        return str(get_json(f"https://registry.npmjs.org/{name}/latest")["version"])
    if registry == "github":
        # releases/latest already leaves out drafts and pre-releases.
        tag = str(get_json(f"https://api.github.com/repos/{name}/releases/latest")["tag_name"])
        return tag.removeprefix("v")
    raise ValueError(f"unknown registry {registry!r}")


def is_behind(pinned: str, latest: str) -> bool:
    """True when ``latest`` is a newer numeric release than ``pinned``."""
    def parts(version: str) -> tuple[int, ...] | None:
        match = re.fullmatch(_VERSION, version)
        return tuple(int(part) for part in match.group(1).split(".")) if match else None

    pinned_parts, latest_parts = parts(pinned), parts(latest)
    if pinned_parts is None or latest_parts is None:
        return False
    width = max(len(pinned_parts), len(latest_parts))
    return pinned_parts + (0,) * (width - len(pinned_parts)) < latest_parts + (0,) * (width - len(latest_parts))


@dataclass(frozen=True)
class Row:
    registry: str
    name: str
    pinned: str
    latest: str | None
    error: str | None
    locations: tuple[str, ...]

    @property
    def behind(self) -> bool:
        return self.latest is not None and is_behind(self.pinned, self.latest)


def compare(pins: list[Pin], get_json: Callable[[str], dict] = _get_json) -> list[Row]:
    """One row per distinct pinned version, with the newest release beside it."""
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for pin in pins:
        grouped.setdefault((pin.registry, pin.name, pin.version), []).append(pin.location)

    latest: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    rows = []
    for (registry, name, version), locations in grouped.items():
        if (registry, name) not in latest:
            try:
                latest[(registry, name)] = (latest_release(registry, name, get_json), None)
            except Exception as failure:  # noqa: BLE001 - one registry down must not hide the rest
                latest[(registry, name)] = (None, f"{type(failure).__name__}: {failure}")
        found, problem = latest[(registry, name)]
        rows.append(Row(registry, name, version, found, problem, tuple(locations)))
    return rows


def markdown(rows: list[Row]) -> str:
    lines = [
        "| Tool | Source | Pinned | Latest | Where |",
        "|------|--------|--------|--------|-------|",
    ]
    for row in sorted(rows, key=lambda r: (not r.behind, r.error is None, r.name)):
        latest = row.latest or f"unknown ({row.error})"
        if row.behind:
            latest = f"**{latest}**"
        where = "<br>".join(f"`{location}`" for location in row.locations)
        lines.append(f"| `{row.name}` | {row.registry} | {row.pinned} | {latest} | {where} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the pins found, without the network")
    parser.add_argument("--markdown", action="store_true", help="print a Markdown table")
    args = parser.parse_args(argv)

    pins = all_pins()
    if args.list:
        for pin in pins:
            print(f"{pin.registry:7} {pin.name:28} {pin.version:10} {pin.location}")
        return 0

    rows = compare(pins)
    if args.markdown:
        print(markdown(rows))
    else:
        for row in rows:
            state = "behind" if row.behind else ("unknown" if row.error else "current")
            print(f"{state:8} {row.name:28} {row.pinned:10} -> {row.latest or row.error}")
    return 1 if any(row.behind for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
