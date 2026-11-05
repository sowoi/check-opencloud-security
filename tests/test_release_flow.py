"""The release, end to end, on a copy of the repository.

Each step of a release has its own tests: check_pull_request.py judges the
bump, release_notes.py renames [Unreleased] and names the version in the
advisory records, the two generators render the version, and
security_advisories.py checks the records. ADR 0080 rests on those steps
fitting together - a bump that passes the pull request check must leave a
release whose commit the workflow can make and whose checks stay green. That
fit is what this module tests, with the real scripts on a copy of the tracked
files rather than with stand-ins.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess  # nosec B404 - runs this repository's own scripts and git
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-pypi.yml"

SECURITY_ENTRY = "**A release-flow fixture.** Nothing was ever wrong."

RECORD = """\
slug: release-flow-fixture
state: draft
changelog_version: unreleased   # the release writes its number in
changelog_entry: "A release-flow fixture."
shipped: true
severity: low
cwe_ids:
  - CWE-693
package: plugin
introduced: "1.0.0"
fixed: unreleased
summary: A fixture the release-flow test adds and resolves
verified: Written by tests/test_release_flow.py.
description: |
  ### Impact

  None; the record exists only on a throwaway copy.
"""

PROJECT_LOCK_ENTRY = re.compile(r'(\[\[package\]\]\nname = "check-opencloud-security"\nversion = )"[^"]*"')
PROJECT_VERSION = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.MULTILINE)


def _git(repo: Path, *args: str) -> str:
    """Git in the copy, with an identity and no signing."""
    return subprocess.run(  # nosec B603 B607 - fixed argv, git from PATH
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


def _script(repo: Path, name: str, *args: str) -> subprocess.CompletedProcess[str]:
    """One of the copy's own scripts, so it reads and writes the copy."""
    return subprocess.run(  # nosec B603 - this interpreter and a script of the copy
        [sys.executable, str(repo / "scripts" / name), *args],
        cwd=repo, check=False, capture_output=True, text=True,
    )


def _ok(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _changed(repo: Path) -> set[str]:
    return {line[3:] for line in _git(repo, "status", "--porcelain", "--untracked-files=all").splitlines()}


def release_commit_paths() -> list[str]:
    """What the release workflow's "Commit release notes" step stages."""
    steps = yaml.safe_load(PUBLISH_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    run = next(
        step["run"]
        for job in steps.values()
        for step in job["steps"]
        if step.get("name") == "Commit release notes"
    )
    paths: list[str] = []
    for command in re.sub(r"\\\n", " ", run).splitlines():
        words = shlex.split(command, comments=True)
        if words[:2] == ["git", "add"]:
            paths.extend(words[2:])
    return paths


def _staged_by_the_workflow(path: str, staged: list[str]) -> bool:
    return any(path == entry or (entry.endswith("/") and path.startswith(entry)) for entry in staged)


@pytest.fixture(scope="module")
def released(tmp_path_factory) -> dict:
    """A copy of the tracked tree taken through a bump and the release workflow."""
    repo = tmp_path_factory.mktemp("release-flow")
    for name in _git(REPO_ROOT, "ls-files", "-z").split("\0"):
        source = REPO_ROOT / name
        if name and source.is_file():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    # main: an [Unreleased] security fix with its record, as a fix PR leaves it.
    changelog = repo / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    text = text.replace("## [Unreleased]\n", f"## [Unreleased]\n\n### Security\n\n- {SECURITY_ENTRY}\n", 1)
    changelog.write_text(text, encoding="utf-8")
    record = repo / "security" / "advisories" / "release-flow-fixture.yml"
    record.write_text(RECORD, encoding="utf-8")

    pyproject = repo / "pyproject.toml"
    match = PROJECT_VERSION.search(pyproject.read_text(encoding="utf-8"))
    assert match, "pyproject.toml names no version"
    current = match.group(2)
    major, minor, patch = (int(part) for part in current.split("."))
    version = f"{major}.{minor}.{patch + 1}"

    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", "main")
    _git(repo, "tag", f"v{current}")
    before = _script(repo, "security_advisories.py", "--check")

    # The release pull request, as AGENTS.md describes it.
    _git(repo, "checkout", "-q", "-b", f"release/{version}")
    pyproject.write_text(
        PROJECT_VERSION.sub(lambda m: f'{m.group(1)}"{version}"', pyproject.read_text(encoding="utf-8"), count=1),
        encoding="utf-8",
    )
    _git(repo, "commit", "-qam", f"release: {version}")
    unregenerated = _script(repo, "check_pull_request.py", "--base", "main")

    lock = repo / "uv.lock"
    lock_text, found = PROJECT_LOCK_ENTRY.subn(rf'\g<1>"{version}"', lock.read_text(encoding="utf-8"))
    assert found == 1, "uv.lock has no entry for the project"
    lock.write_text(lock_text, encoding="utf-8")
    _ok(_script(repo, "build_frontend_documentation.py"))
    _ok(_script(repo, "build_search_index.py"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"release: {version}")
    pull_request = _script(repo, "check_pull_request.py", "--base", "main")

    # What publish-pypi.yml does once the bump is on main.
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--ff-only", f"release/{version}")
    _ok(_script(repo, "release_notes.py", "--version", version))
    _ok(_script(repo, "build_frontend_documentation.py"))
    _ok(_script(repo, "build_search_index.py"))

    return {
        "repo": repo,
        "version": version,
        "before": before,
        "unregenerated": unregenerated,
        "pull_request": pull_request,
        "changed": _changed(repo),
        "record": record.read_text(encoding="utf-8"),
    }


def test_the_unreleased_record_passes_the_check_before_the_release(released):
    """A fix PR can write its record before anyone knows the version."""
    _ok(released["before"])


def test_a_bump_without_the_generators_is_refused(released):
    """The pull request check catches what the release of 1.32.1 met only in CI."""
    result = released["unregenerated"]
    assert result.returncode == 1
    assert "were not regenerated" in result.stdout


def test_the_bump_as_documented_passes_the_pull_request_check(released):
    """Version, lock line and the two generators are the whole release PR."""
    output = _ok(released["pull_request"])
    assert f"releases {released['version']}" in output


def test_the_release_names_its_version_in_the_waiting_record(released):
    """The marker becomes the number, and the comment after it survives."""
    record = released["record"]
    assert "unreleased" not in record.lower().replace("# the release writes its number in", "")
    assert f'changelog_version: "{released["version"]}"   # the release writes its number in' in record
    assert f'fixed: "{released["version"]}"' in record


def test_the_checks_stay_green_after_the_release(released):
    """The commit the workflow makes is one every check on main accepts."""
    repo = released["repo"]
    _ok(_script(repo, "security_advisories.py", "--check"))
    _ok(_script(repo, "build_frontend_documentation.py", "--check"))
    _ok(_script(repo, "build_search_index.py", "--check"))
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{released['version']}]" in changelog


def test_the_workflow_commits_everything_the_release_changes(released):
    """A file the release rewrites but the workflow does not stage leaves main stale."""
    staged = release_commit_paths()
    assert released["changed"], "the release changed nothing"
    missed = sorted(path for path in released["changed"] if not _staged_by_the_workflow(path, staged))
    assert missed == []


def test_an_unstaged_path_would_be_noticed():
    """The comparison above can fail: a path outside the staged list is missed."""
    staged = release_commit_paths()
    assert _staged_by_the_workflow("security/advisories/x.yml", staged)
    assert _staged_by_the_workflow("CHANGELOG.md", staged)
    assert not _staged_by_the_workflow("webapp/decision_records.py", staged)
    assert not _staged_by_the_workflow("security/advisories", ["security/advisories/"])
