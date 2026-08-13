#!/usr/bin/env python3
"""Maintain CHANGELOG.md and RELEASE.md for a release.

The version is read from ``pyproject.toml`` and is only ever bumped by hand.
Whenever it changes, the release workflow calls this script to

* write ``RELEASE.md`` (overwritten on every release) with the notes of the
  version being released, and
* turn the ``## [Unreleased]`` section of ``CHANGELOG.md`` into the section of
  that version (older releases are kept below it).

Changes are collected under ``## [Unreleased]`` while they are developed, so
the notes of a release are written by the people who made the changes rather
than derived from commit subjects afterwards. The order of preference is:

1. a section already headed ``## [<version>]`` - notes written for exactly
   this release win over everything else,
2. the ``## [Unreleased]`` section, which is renamed to ``## [<version>]``,
3. failing both, notes generated from the commit subjects since the previous
   tag, grouped by their Conventional Commit type.
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404 - fixed argv, no shell
import sys
from datetime import datetime, timezone
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE = REPO_ROOT / "RELEASE.md"

CHANGELOG_HEADER = """# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
"""

# The heading changes are collected under until a release claims them.
UNRELEASED = "Unreleased"

# Conventional Commit type -> Keep a Changelog section.
SECTIONS: dict[str, str] = {
    "feat": "Added",
    "change": "Changed",
    "refactor": "Changed",
    "perf": "Changed",
    "deprecate": "Deprecated",
    "remove": "Removed",
    "revert": "Removed",
    "fix": "Fixed",
    "security": "Security",
    "docs": "Documentation",
}
SECTION_ORDER = [
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
    "Documentation",
]
# Commit types that are noise in a changelog.
IGNORED_TYPES = {"chore", "ci", "build", "test", "style"}

COMMIT_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<text>.+)$"
)


def run_git(*args: str) -> str:
    """Run a git command inside the repository and return its stdout."""
    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, git from PATH
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def project_version() -> str:
    """Read the current version from pyproject.toml."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def previous_tag(version: str) -> str | None:
    """Return the most recent tag that is not the tag of this release."""
    tags = run_git("tag", "--sort=-creatordate").splitlines()
    for tag in tags:
        if tag.strip() and tag.strip() != f"v{version}":
            return tag.strip()
    return None


def section_of(commit_type: str, breaking: bool) -> str | None:
    """Map a Conventional Commit type onto a changelog section."""
    if breaking:
        return "Changed"
    if commit_type in IGNORED_TYPES:
        return None
    return SECTIONS.get(commit_type, "Changed")


def collect_commits(since: str | None) -> dict[str, list[str]]:
    """Group commit subjects since ``since`` into changelog sections."""
    revision = f"{since}..HEAD" if since else "HEAD"
    log = run_git("log", revision, "--no-merges", "--pretty=format:%s")
    grouped: dict[str, list[str]] = {}
    for line in log.splitlines():
        subject = line.strip()
        if not subject:
            continue
        match = COMMIT_RE.match(subject)
        if match:
            section = section_of(match.group("type"), bool(match.group("breaking")))
            if section is None:
                continue
            scope = match.group("scope")
            text = match.group("text").strip()
            entry = f"**{scope}:** {text}" if scope else text
            if match.group("breaking"):
                entry = f"**Breaking:** {entry}"
        else:
            section = "Changed"
            entry = subject
        entry = entry[0].upper() + entry[1:]
        grouped.setdefault(section, []).append(entry)
    return grouped


def generate_body(since: str | None) -> str:
    """Render the changelog body for the commits since ``since``."""
    grouped = collect_commits(since)
    if not grouped:
        return "### Changed\n\n- Maintenance release without documented changes.\n"
    parts: list[str] = []
    for section in SECTION_ORDER:
        entries = grouped.get(section)
        if not entries:
            continue
        unique = list(dict.fromkeys(entries))
        body = "\n".join(f"- {entry}" for entry in unique)
        parts.append(f"### {section}\n\n{body}\n")
    return "\n".join(parts)


def _section_re(label: str) -> re.Pattern[str]:
    """Match one '## [label]' section and capture its body."""
    return re.compile(
        rf"^## \[{re.escape(label)}\][^\n]*\n(?P<body>.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )


def _has_content(body: str | None) -> bool:
    """
    Whether a changelog body says anything.

    An ``## [Unreleased]`` heading that nobody wrote under - the empty scaffold
    this script leaves behind after a release - must not be published as the
    notes of the next version.
    """
    if body is None:
        return False
    return any(
        line.strip() and not line.lstrip().startswith("#") for line in body.splitlines()
    )


def existing_entry(version: str) -> str | None:
    """Return the body of an already documented changelog section, if any."""
    if not CHANGELOG.exists():
        return None
    match = _section_re(version).search(CHANGELOG.read_text(encoding="utf-8"))
    if match is None:
        return None
    body = match.group("body").strip("\n")
    return body if _has_content(body) else None


def unreleased_entry() -> str | None:
    """Return the collected but unpublished notes, if there are any."""
    if not CHANGELOG.exists():
        return None
    match = _section_re(UNRELEASED).search(CHANGELOG.read_text(encoding="utf-8"))
    if match is None:
        return None
    body = match.group("body").strip("\n")
    return body if _has_content(body) else None


def promote_unreleased(version: str, released: str, body: str) -> None:
    """
    Turn the '[Unreleased]' section into the section of this version.

    The heading is replaced in place rather than a copy being prepended, so
    that the notes never end up in the file twice. A fresh empty
    '[Unreleased]' heading is left on top, ready for the next change.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    match = _section_re(UNRELEASED).search(text)
    if match is None:  # pragma: no cover - guarded by the caller
        prepend_changelog(version, released, body)
        return
    entry = f"## [{UNRELEASED}]\n\n## [{version}] - {released}\n\n{body.rstrip()}\n\n"
    CHANGELOG.write_text(text[: match.start()] + entry + text[match.end():], encoding="utf-8")


def prepend_changelog(version: str, released: str, body: str) -> None:
    """
    Insert a new version section above the previous release.

    It goes *below* an ``## [Unreleased]`` heading, which always stays on top
    so that the next change has somewhere to go.
    """
    entry = f"## [{version}] - {released}\n\n{body.rstrip()}\n"
    if not CHANGELOG.exists():
        CHANGELOG.write_text(f"{CHANGELOG_HEADER}\n{entry}", encoding="utf-8")
        return
    text = CHANGELOG.read_text(encoding="utf-8")
    unreleased = _section_re(UNRELEASED).search(text)
    if unreleased is not None:
        head = text[: unreleased.end()].rstrip("\n")
        tail = text[unreleased.end():].lstrip("\n")
        CHANGELOG.write_text(f"{head}\n\n{entry}\n{tail}", encoding="utf-8")
        return
    marker = re.search(r"^## \[", text, re.MULTILINE)
    if marker is None:
        CHANGELOG.write_text(f"{text.rstrip()}\n\n{entry}", encoding="utf-8")
        return
    head = text[: marker.start()].rstrip("\n")
    tail = text[marker.start() :]
    CHANGELOG.write_text(f"{head}\n\n{entry}\n{tail}", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the release workflow."""
    parser = argparse.ArgumentParser(description="Update CHANGELOG.md and RELEASE.md.")
    parser.add_argument("--version", default=None, help="Version to document. Default: pyproject.toml.")
    parser.add_argument("--previous-tag", default=None, help="Tag to compare against. Default: latest tag.")
    parser.add_argument("--date", default=None, help="Release date. Default: today (UTC).")
    parser.add_argument(
        "--require-unreleased",
        action="store_true",
        help="Fail instead of generating notes from commit subjects.",
    )
    args = parser.parse_args(argv)

    version = args.version or project_version()
    released = args.date or datetime.now(tz=timezone.utc).date().isoformat()

    body = existing_entry(version)
    source = "Reused"
    if body is None:
        body = unreleased_entry()
        if body is not None:
            source = "Promoted [Unreleased] to"
            promote_unreleased(version, released, body)
    if body is None:
        if args.require_unreleased:
            print(
                f"No [Unreleased] section in {CHANGELOG.name} and no notes for {version}. "
                "Collect the changes under '## [Unreleased]' before releasing.",
                file=sys.stderr,
            )
            return 1
        source = "Generated"
        since = args.previous_tag or previous_tag(version)
        body = generate_body(since)
        prepend_changelog(version, released, body)

    RELEASE.write_text(
        f"## check-opencloud-security {version}\n\n{body.rstrip()}\n", encoding="utf-8"
    )
    print(f"{source} release notes for {version}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
