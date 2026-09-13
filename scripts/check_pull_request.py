#!/usr/bin/env python3
"""
Hold a pull request to the two rules the pull request template can only ask for.

    python scripts/check_pull_request.py --base origin/main
    python scripts/check_pull_request.py --base origin/main --labels release

**Every change is documented.** A pull request that changes anything has to
add to ``CHANGELOG.md`` - under ``## [Unreleased]`` or under the heading of the
version in ``pyproject.toml`` - and to ``RELEASE.md``, whose heading has to
name that same version. The ``skip-changelog`` label is the stated exception,
and a pull request opened by one of this repository's bots is exempt: a
refreshed advisory database is not a change anybody writes notes for.

**A version bump is deliberate.** A bump that lands on ``main`` publishes to
PyPI immediately, so a pull request that changes the ``version`` in
``pyproject.toml`` has to

* carry the ``release`` label - the maintainer saying "merging this publishes",
* move the version forward, past both ``main`` and every existing tag,
* name a version no tag exists for yet, and
* not describe itself as some other version: a commit that changes the version
  line and names a different number in its subject is refused.

The script reads git and nothing else. It needs the base commit and the tags
in the clone, which is why the workflow checks out with ``fetch-depth: 0``.
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404 - fixed argv, no shell
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RELEASE_LABEL = "release"
SKIP_CHANGELOG_LABEL = "skip-changelog"

#: Pull requests these accounts open carry no notes of their own.
AUTOMATED_AUTHORS = frozenset({"github-actions[bot]", "dependabot[bot]"})

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
SEMVER_IN_TEXT = re.compile(r"\b\d+\.\d+\.\d+\b")
PROJECT_VERSION = re.compile(
    r"^\[project\]$.*?^version\s*=\s*[\"']([^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)


def git(*args: str, check: bool = True) -> str:
    """Run git in the repository and return its stdout."""
    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, git from PATH
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout if result.returncode == 0 else ""


def file_at(commit: str, path: str) -> str:
    """The content of a file at a commit, or an empty string where it is absent."""
    return git("show", f"{commit}:{path}", check=False)


def project_version(pyproject: str) -> str | None:
    """The version under ``[project]``, matched directly - 3.10 has no tomllib."""
    match = PROJECT_VERSION.search(pyproject)
    return match.group(1) if match else None


def parse_version(version: str) -> tuple[int, int, int] | None:
    """``1.22.0`` as a comparable tuple, or None for anything that is not X.Y.Z."""
    match = VERSION_RE.match(version)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def changelog_section(changelog: str, heading: str) -> str:
    """The body under ``## [<heading>]``, up to the next second-level heading."""
    match = re.search(
        rf"^## \[{re.escape(heading)}\][^\n]*\n(?P<body>.*?)(?=^## |\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip() if match else ""


def release_heading_version(release: str) -> str | None:
    """The version ``RELEASE.md`` is written for."""
    match = re.search(r"^## check-opencloud-security (\S+)\s*$", release, re.MULTILINE)
    return match.group(1) if match else None


def check_changelog(
    *,
    changed_files: list[str],
    labels: set[str],
    author: str,
    version: str,
    base_changelog: str,
    head_changelog: str,
    head_release: str,
) -> list[str]:
    """Every problem with how this pull request documents itself."""
    if not changed_files or SKIP_CHANGELOG_LABEL in labels or author in AUTOMATED_AUTHORS:
        return []

    problems = []
    added_to_changelog = any(
        changelog_section(base_changelog, heading) != changelog_section(head_changelog, heading)
        and changelog_section(head_changelog, heading)
        for heading in ("Unreleased", version)
    )
    if not added_to_changelog:
        problems.append(
            f"CHANGELOG.md has no new entry under '## [Unreleased]' or '## [{version}]'. "
            f"Describe the change there, or label the pull request '{SKIP_CHANGELOG_LABEL}' "
            "if it genuinely needs no notes."
        )
    if "RELEASE.md" not in changed_files:
        problems.append(
            "RELEASE.md is unchanged. Add the same entry there as in CHANGELOG.md."
        )
    heading = release_heading_version(head_release)
    if heading != version:
        problems.append(
            f"RELEASE.md is written for {heading or 'no version'}, but pyproject.toml "
            f"declares {version}. Its entries belong under "
            f"'## check-opencloud-security {version}'."
        )
    return problems


def check_version(
    *,
    base_version: str,
    head_version: str,
    labels: set[str],
    tags: list[str],
    bump_subjects: list[tuple[str, str, str]],
) -> list[str]:
    """
    Every problem with a version change - none when the version did not move.

    ``bump_subjects`` holds ``(sha, subject, version it set)`` for each commit
    in the pull request that changed the version line.
    """
    problems = []
    for sha, subject, set_version in bump_subjects:
        named = [v for v in SEMVER_IN_TEXT.findall(subject) if v != set_version]
        if named:
            problems.append(
                f"Commit {sha[:12]} sets the version to {set_version} but its subject "
                f"says {', '.join(named)}: {subject!r}. Reword it so the history "
                "names the version it actually released."
            )

    if head_version == base_version:
        return problems

    new = parse_version(head_version)
    if new is None:
        return [*problems, f"The version {head_version!r} is not of the form X.Y.Z."]

    if RELEASE_LABEL not in labels:
        problems.append(
            f"This pull request changes the version from {base_version} to {head_version}, "
            f"and merging it publishes to PyPI. Label it '{RELEASE_LABEL}' to confirm that."
        )
    old = parse_version(base_version)
    if old is not None and new <= old:
        problems.append(
            f"The version moves from {base_version} to {head_version}, which is not forward."
        )
    if f"v{head_version}" in tags:
        problems.append(
            f"The tag v{head_version} already exists, so this version was already released."
        )
    released = [v for v in (parse_version(t[1:]) for t in tags if t.startswith("v")) if v]
    if f"v{head_version}" not in tags and released and new <= max(released):
        newest = ".".join(str(part) for part in max(released))
        problems.append(
            f"{head_version} is not newer than the latest release, v{newest}."
        )
    return problems


def bump_commits(base: str, head: str) -> list[tuple[str, str, str]]:
    """The commits between base and head that changed the version, with their subjects."""
    found = []
    log = git("log", "--no-merges", "--format=%H%x00%s", f"{base}..{head}", "--", "pyproject.toml")
    for line in log.splitlines():
        sha, _, subject = line.partition("\x00")
        after = project_version(file_at(sha, "pyproject.toml"))
        before = project_version(file_at(f"{sha}^", "pyproject.toml"))
        if after and after != before:
            found.append((sha, subject, after))
    return found


def main(argv: list[str] | None = None) -> int:
    """Entry point for the pull request policy workflow."""
    parser = argparse.ArgumentParser(description="Check a pull request's changelog and version.")
    parser.add_argument("--base", required=True, help="The commit the pull request targets.")
    parser.add_argument("--head", default="HEAD", help="The pull request's commit. Default: HEAD.")
    parser.add_argument("--labels", default="", help="Comma-separated pull request labels.")
    parser.add_argument("--author", default="", help="The login that opened the pull request.")
    args = parser.parse_args(argv)

    merge_base = git("merge-base", args.base, args.head).strip()
    labels = {label.strip() for label in args.labels.split(",") if label.strip()}
    changed = git("diff", "--name-only", f"{merge_base}...{args.head}").split()
    base_version = project_version(file_at(merge_base, "pyproject.toml"))
    head_version = project_version(file_at(args.head, "pyproject.toml"))
    if base_version is None or head_version is None:
        raise SystemExit("pyproject.toml declares no version under [project].")

    problems = check_changelog(
        changed_files=changed,
        labels=labels,
        author=args.author,
        version=head_version,
        base_changelog=file_at(merge_base, "CHANGELOG.md"),
        head_changelog=file_at(args.head, "CHANGELOG.md"),
        head_release=file_at(args.head, "RELEASE.md"),
    )
    problems += check_version(
        base_version=base_version,
        head_version=head_version,
        labels=labels,
        tags=git("tag", "--list").split(),
        bump_subjects=bump_commits(merge_base, args.head),
    )

    for problem in problems:
        print(f"::error::{problem}")
    if not problems:
        print(f"The pull request documents itself and version {head_version} is in order.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
