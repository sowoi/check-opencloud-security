#!/usr/bin/env python3
"""
Check a branch against the two rules the pull request template asks for.

    python scripts/check_pull_request.py --base origin/main
    python scripts/check_pull_request.py --base origin/main --labels skip-changelog

Run it before opening a pull request; no workflow runs it.

**Every change is documented.** A pull request that changes anything has to
add to ``CHANGELOG.md`` - under ``## [Unreleased]`` or under the heading of the
version in ``pyproject.toml``. ``RELEASE.md`` is not asked for: the release
workflow writes it from that section with ``scripts/release_notes.py`` and
overwrites whatever a pull request put there. The ``skip-changelog`` label is
the stated exception, and a pull request opened by one of this repository's
bots is exempt: a refreshed advisory database is not a change anybody writes
notes for.

**A version bump is deliberate.** A bump that lands on ``main`` publishes to
PyPI immediately, so a pull request that changes the ``version`` in
``pyproject.toml`` has to

* move the version forward, past both ``main`` and every existing tag,
* name a version no tag exists for yet, and
* not describe itself as some other version: a commit that changes the version
  line and names a different number in its subject is refused, and
* bring the files that embed the version, regenerated, in the same pull
  request. The operator area's Releases page and every search index render
  the version; a bot commit that regenerated them afterwards would start no
  checks of its own, so the bump would sit on red ones.

**A release needs no notes of its own.** A pull request that changes the
version and nothing else - the version line in ``pyproject.toml`` and
``uv.lock``, and the files above - is a release: what it releases is already
written under ``## [Unreleased]``, so it is not asked for a new entry.

The script reads git and nothing else. It needs the base commit and the tags
in the clone.
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404 - fixed argv, no shell
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_CHANGELOG_LABEL = "skip-changelog"

#: Pull requests these accounts open carry no notes of their own.
AUTOMATED_AUTHORS = frozenset({"github-actions[bot]", "dependabot[bot]"})

#: What a version bump regenerates: everything that renders the version.
#: ``scripts/build_frontend_documentation.py`` writes the first,
#: ``scripts/build_search_index.py`` the rest - in that order, because the
#: operator index embeds the Releases page.
VERSION_EMBEDDING = (
    "frontend/templates/admin-docs/releases.html",
    "frontend/static/search-index.json",
    "frontend/static/search-index.de.json",
    "frontend/static/search-index.es.json",
    "frontend/static/search-index.fr.json",
    "webapp/data/admin-search-index.json",
    "webapp/data/admin-search-index.de.json",
    "webapp/data/admin-search-index.es.json",
    "webapp/data/admin-search-index.fr.json",
)

REGENERATE = (
    "uv run python scripts/build_frontend_documentation.py && "
    "uv run python scripts/build_search_index.py"
)

#: The project's own entry in uv.lock, whose version follows pyproject.toml.
LOCK_VERSION = re.compile(
    r'^(\[\[package\]\]\nname = "check-opencloud-security"\nversion = )"[^"]*"',
    re.MULTILINE,
)

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


def without_version(pyproject: str, lock: str) -> tuple[str, str]:
    """Both files with the project's own version blanked out."""
    blank_pyproject = re.sub(
        r"^(\[project\]$.*?^version\s*=\s*)[\"'][^\"']*[\"']",
        r'\1""',
        pyproject,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )
    return blank_pyproject, LOCK_VERSION.sub(r'\1""', lock, count=1)


def is_release_only(
    *,
    changed_files: list[str],
    base_version: str,
    head_version: str,
    base_files: tuple[str, str],
    head_files: tuple[str, str],
) -> bool:
    """
    True for a pull request that changes the version and nothing else.

    ``base_files`` and ``head_files`` are ``(pyproject.toml, uv.lock)`` on
    each side: the two may differ only in the version, or a dependency change
    would ride along without a changelog entry.
    """
    if head_version == base_version:
        return False
    allowed = {"pyproject.toml", "uv.lock", *VERSION_EMBEDDING}
    if not set(changed_files) <= allowed:
        return False
    return without_version(*base_files) == without_version(*head_files)


def check_regenerated(*, changed_files: list[str], base_version: str, head_version: str) -> list[str]:
    """A bump brings the files that render the version, regenerated, with it."""
    if head_version == base_version:
        return []
    missing = [path for path in VERSION_EMBEDDING if path not in changed_files]
    if not missing:
        return []
    problem = (
        f"The version moves to {head_version}, but these files render it and were not "
        f"regenerated: {', '.join(missing)}. Run `{REGENERATE}` and commit the result "
        "with the bump - a bot commit afterwards would run no checks."
    )
    return [problem]


def check_changelog(
    *,
    changed_files: list[str],
    labels: set[str],
    author: str,
    version: str,
    base_changelog: str,
    head_changelog: str,
    release_only: bool = False,
) -> list[str]:
    """Every problem with how this pull request documents itself."""
    if (
        not changed_files
        or release_only
        or SKIP_CHANGELOG_LABEL in labels
        or author in AUTOMATED_AUTHORS
    ):
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
    return problems


def check_version(
    *,
    base_version: str,
    head_version: str,
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
    """Entry point."""
    parser = argparse.ArgumentParser(description="Check a pull request's changelog and version.")
    parser.add_argument("--base", required=True, help="The commit the pull request targets.")
    parser.add_argument("--head", default="HEAD", help="The pull request's commit. Default: HEAD.")
    parser.add_argument("--labels", default="", help="Comma-separated labels; skip-changelog skips the entry check.")
    parser.add_argument("--author", default="", help="The login that opened the pull request.")
    args = parser.parse_args(argv)

    merge_base = git("merge-base", args.base, args.head).strip()
    labels = {label.strip() for label in args.labels.split(",") if label.strip()}
    changed = git("diff", "--name-only", f"{merge_base}...{args.head}").split()
    base_version = project_version(file_at(merge_base, "pyproject.toml"))
    head_version = project_version(file_at(args.head, "pyproject.toml"))
    if base_version is None or head_version is None:
        raise SystemExit("pyproject.toml declares no version under [project].")

    release_only = is_release_only(
        changed_files=changed,
        base_version=base_version,
        head_version=head_version,
        base_files=(file_at(merge_base, "pyproject.toml"), file_at(merge_base, "uv.lock")),
        head_files=(file_at(args.head, "pyproject.toml"), file_at(args.head, "uv.lock")),
    )
    problems = check_changelog(
        changed_files=changed,
        labels=labels,
        author=args.author,
        version=head_version,
        base_changelog=file_at(merge_base, "CHANGELOG.md"),
        head_changelog=file_at(args.head, "CHANGELOG.md"),
        release_only=release_only,
    )
    problems += check_regenerated(
        changed_files=changed, base_version=base_version, head_version=head_version
    )
    problems += check_version(
        base_version=base_version,
        head_version=head_version,
        tags=git("tag", "--list").split(),
        bump_subjects=bump_commits(merge_base, args.head),
    )

    for problem in problems:
        print(f"::error::{problem}")
    if not problems and release_only:
        print(f"The pull request releases {head_version}; its notes are under [Unreleased].")
    elif not problems:
        print(f"The pull request documents itself and version {head_version} is in order.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
