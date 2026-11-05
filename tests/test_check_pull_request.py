"""Tests for scripts/check_pull_request.py.

Two rules used to live only as checkboxes in the pull request template: that
every change is written up in CHANGELOG.md, and that a version
bump - which publishes to PyPI the moment it lands - moves forward and says
what it is. These tests hold the script that checks them to failing when it
should, and to staying quiet when it should.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess  # nosec B404 - builds a throwaway repository with fixed argv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "check_pull_request", REPO_ROOT / "scripts" / "check_pull_request.py"
)
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
sys.modules["check_pull_request"] = script
SPEC.loader.exec_module(script)

CHANGELOG = """# Changelog

## [Unreleased]

{unreleased}

## [1.0.0] - 2026-01-01

### Added

- The first release.
"""

PYPROJECT = """[project]
name = "example"
version = "{version}"

[tool.other]
version = "9.9.9"
"""

RELEASE = "## check-opencloud-security {version}\n\n{body}\n"


def documented(**overrides: object) -> dict:
    """A pull request that documents itself, so a test can break one thing."""
    arguments: dict = {
        "changed_files": ["webapp/app.py", "CHANGELOG.md"],
        "labels": set(),
        "author": "a-contributor",
        "version": "1.1.0",
        "base_changelog": CHANGELOG.format(unreleased=""),
        "head_changelog": CHANGELOG.format(unreleased="### Fixed\n\n- A thing."),
    }
    arguments.update(overrides)
    return arguments


def bump(**overrides: object) -> dict:
    """A forward, untagged bump, so a test can break one thing."""
    arguments: dict = {
        "base_version": "1.0.0",
        "head_version": "1.1.0",
        "tags": ["v0.9.0", "v1.0.0"],
        "bump_subjects": [("a" * 40, "chore(release): bump to version 1.1.0", "1.1.0")],
    }
    arguments.update(overrides)
    return arguments


def test_a_documented_change_passes():
    """The negative case's guard: a correct pull request must not be refused."""
    assert script.check_changelog(**documented()) == []


def test_a_change_without_a_changelog_entry_is_refused():
    """The rule the template could only ask for."""
    problems = script.check_changelog(
        **documented(head_changelog=CHANGELOG.format(unreleased=""))
    )

    assert any("CHANGELOG.md has no new entry" in p for p in problems)


def test_an_entry_under_an_old_release_does_not_count():
    """Notes added to a published section never reach the next release."""
    base = CHANGELOG.format(unreleased="")
    head = base.replace("- The first release.", "- The first release.\n- Sneaked in.")

    problems = script.check_changelog(**documented(base_changelog=base, head_changelog=head))

    assert any("CHANGELOG.md has no new entry" in p for p in problems)


def test_an_entry_under_the_declared_version_counts():
    """A release branch may already have renamed its section to the version."""
    base = CHANGELOG.format(unreleased="")
    head = base.replace("## [Unreleased]", "## [1.1.0]\n\n### Fixed\n\n- A thing.")

    assert script.check_changelog(**documented(base_changelog=base, head_changelog=head)) == []


def test_release_md_is_not_asked_of_a_pull_request():
    """The release workflow writes RELEASE.md from the changelog and overwrites it."""
    assert script.check_changelog(**documented()) == []
    # Touching it is not a substitute for the changelog entry it is written from.
    problems = script.check_changelog(
        **documented(
            changed_files=["webapp/app.py", "RELEASE.md"],
            head_changelog=CHANGELOG.format(unreleased=""),
        )
    )
    assert any("CHANGELOG.md has no new entry" in p for p in problems)
    assert not any("RELEASE.md" in p for p in problems)


@pytest.mark.parametrize(
    "exemption",
    [{"labels": {"skip-changelog"}}, {"author": "dependabot[bot]"}, {"author": "github-actions[bot]"}],
    ids=["label", "dependabot", "refresh-bot"],
)
def test_the_stated_exemptions_skip_the_changelog_check(exemption):
    """A refreshed advisory database is not a change anybody writes notes for."""
    undocumented = documented(changed_files=["uv.lock"], head_changelog=CHANGELOG.format(unreleased=""))

    assert script.check_changelog(**undocumented)
    assert script.check_changelog(**{**undocumented, **exemption}) == []


def test_an_unchanged_version_is_not_checked_against_the_tags():
    """Only a bump publishes; an ordinary pull request has no version to judge."""
    assert script.check_version(**bump(head_version="1.0.0", tags=["v1.0.0"], bump_subjects=[])) == []


def test_a_forward_bump_passes_without_any_label():
    """The guard for the refusals below - and no label is asked of a release."""
    assert script.check_version(**bump()) == []


def test_a_version_that_moves_backwards_is_refused():
    """PyPI never takes a lower number, and a downgrade on main is a mistake."""
    problems = script.check_version(**bump(head_version="0.9.5", bump_subjects=[]))

    assert any("not forward" in p for p in problems)


def test_a_version_that_was_already_tagged_is_refused():
    """The publish workflow would skip it silently; say so before the merge instead."""
    problems = script.check_version(
        **bump(base_version="0.9.0", head_version="1.0.0", bump_subjects=[])
    )

    assert any("v1.0.0 already exists" in p for p in problems)
    assert not any("not newer than the latest release" in p for p in problems)


def test_a_version_behind_the_newest_tag_is_refused():
    """A branch cut before a release must not publish a number below it."""
    problems = script.check_version(
        **bump(base_version="0.8.0", head_version="0.9.5", tags=["v1.0.0"], bump_subjects=[])
    )

    assert any("not newer than the latest release, v1.0.0" in p for p in problems)


def test_a_version_that_is_not_x_y_z_is_refused():
    """Every comparison above assumes three numbers."""
    problems = script.check_version(**bump(head_version="1.1", bump_subjects=[]))

    assert problems == ["The version '1.1' is not of the form X.Y.Z."]


def test_a_bump_commit_naming_another_version_is_refused():
    """The history once said "Bump to version 1.23.3" over a commit that set 1.21.3."""
    wrong = [("b" * 40, "Bump to version 1.23.3", "1.1.0")]

    problems = script.check_version(**bump(bump_subjects=wrong))

    assert any("subject says 1.23.3" in p for p in problems)
    assert script.check_version(**bump()) == []


def test_the_project_version_ignores_other_tables():
    """A `version` key in a tool table is not the package version."""
    assert script.project_version(PYPROJECT.format(version="1.2.3")) == "1.2.3"


# --- the whole script, against a real repository -----------------------------


def _git(repo: Path, *args: str) -> str:
    """Run git in the throwaway repository with an identity and no signing."""
    return subprocess.run(  # nosec B603 B607 - fixed argv, git from PATH
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


LOCK = """version = 1

[[package]]
name = "check-opencloud-security"
version = "{version}"
source = {{ editable = "." }}

[[package]]
name = "requests"
version = "{requests}"
"""


def _regenerate(repo: Path, version: str) -> None:
    """What the two generators would write for a version: each file names it."""
    for name in script.VERSION_EMBEDDING:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"rendered for {version}\n", encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """A released 1.0.0 on main and a branch to open pull requests from."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.format(version="1.0.0"), encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG.format(unreleased=""), encoding="utf-8")
    (tmp_path / "RELEASE.md").write_text(RELEASE.format(version="1.0.0", body="- First."), encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text(LOCK.format(version="1.0.0", requests="2.0.0"), encoding="utf-8")
    _regenerate(tmp_path, "1.0.0")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "feat: first")
    _git(tmp_path, "tag", "v1.0.0")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    return tmp_path


def test_the_script_passes_a_documented_bump_end_to_end(repo, capsys):
    """Everything wired together: diff, versions, tags and commit subjects."""
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(CHANGELOG.format(unreleased="### Fixed\n\n- x."), encoding="utf-8")
    _git(repo, "commit", "-qam", "fix: x")
    (repo / "pyproject.toml").write_text(PYPROJECT.format(version="1.1.0"), encoding="utf-8")
    _regenerate(repo, "1.1.0")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "chore(release): bump to version 1.1.0")
    # RELEASE.md still describes 1.0.0, as it does until the release rewrites it.
    assert (repo / "RELEASE.md").read_text(encoding="utf-8").startswith(
        "## check-opencloud-security 1.0.0"
    )

    assert script.main(["--base", "main"]) == 0
    assert "version 1.1.0 is in order" in capsys.readouterr().out


def test_the_script_refuses_a_mislabelled_bump_commit_end_to_end(repo, capsys):
    """The subject check reads the version each commit actually set, from git."""
    (repo / "CHANGELOG.md").write_text(CHANGELOG.format(unreleased="### Fixed\n\n- x."), encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT.format(version="1.1.0"), encoding="utf-8")
    _git(repo, "commit", "-qam", "Bump to version 1.3.3")

    assert script.main(["--base", "main"]) == 1
    assert "subject says 1.3.3" in capsys.readouterr().out


def test_the_script_refuses_an_undocumented_change_end_to_end(repo, capsys):
    """The ordinary failure: code changed, notes did not."""
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "fix: x")

    assert script.main(["--base", "main"]) == 1
    output = capsys.readouterr().out
    assert "CHANGELOG.md has no new entry" in output
    assert script.main(["--base", "main", "--labels", "skip-changelog"]) == 0


# --- a release pull request ---------------------------------------------------


def _release_files(version: str, requests: str = "2.0.0") -> tuple[str, str]:
    return PYPROJECT.format(version=version), LOCK.format(version=version, requests=requests)


def release(**overrides: object) -> dict:
    """A pull request that only bumps, so a test can break one thing."""
    arguments: dict = {
        "changed_files": ["pyproject.toml", "uv.lock", *script.VERSION_EMBEDDING],
        "base_version": "1.0.0",
        "head_version": "1.0.1",
        "base_files": _release_files("1.0.0"),
        "head_files": _release_files("1.0.1"),
    }
    arguments.update(overrides)
    return arguments


def test_a_bump_and_nothing_else_is_a_release():
    """Its notes are already under [Unreleased]; asking for another entry was noise."""
    assert script.is_release_only(**release()) is True
    assert script.check_changelog(**documented(head_changelog=documented()["base_changelog"],
                                               release_only=True)) == []


def test_a_release_that_carries_another_change_is_not_one():
    """A change riding along with the bump still has to describe itself."""
    assert script.is_release_only(**release(changed_files=["pyproject.toml", "webapp/app.py"])) is False


def test_a_dependency_change_in_the_lock_is_not_hidden_by_a_bump():
    """Only the project's own version line may differ in uv.lock."""
    assert script.is_release_only(**release(head_files=_release_files("1.0.1", requests="2.1.0"))) is False


def test_without_a_version_change_nothing_is_a_release():
    """A pull request touching only uv.lock is an ordinary change."""
    assert script.is_release_only(**release(head_version="1.0.0", head_files=_release_files("1.0.0"))) is False


def test_a_bump_without_the_regenerated_pages_is_refused():
    """The Releases page and the search indexes render the version - 1.32.1 went red on them."""
    problems = script.check_regenerated(
        changed_files=["pyproject.toml", "uv.lock"], base_version="1.0.0", head_version="1.0.1"
    )
    assert len(problems) == 1
    assert "frontend/templates/admin-docs/releases.html" in problems[0]
    assert "build_frontend_documentation.py" in problems[0]
    assert script.check_regenerated(
        changed_files=["pyproject.toml", *script.VERSION_EMBEDDING], base_version="1.0.0", head_version="1.0.1"
    ) == []


def test_a_change_that_keeps_the_version_needs_no_regeneration():
    """Only a bump moves what those files render."""
    assert script.check_regenerated(changed_files=["app.py"], base_version="1.0.0", head_version="1.0.0") == []


def test_the_script_passes_a_release_pull_request_end_to_end(repo, capsys):
    """Version line, lock line, regenerated files - and no new changelog entry."""
    (repo / "pyproject.toml").write_text(PYPROJECT.format(version="1.0.1"), encoding="utf-8")
    (repo / "uv.lock").write_text(LOCK.format(version="1.0.1", requests="2.0.0"), encoding="utf-8")
    _regenerate(repo, "1.0.1")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "release: 1.0.1")

    assert script.main(["--base", "main"]) == 0
    assert "releases 1.0.1" in capsys.readouterr().out


def test_the_script_refuses_a_bump_that_did_not_regenerate_end_to_end(repo, capsys):
    """The failure the release of 1.32.1 met only in CI, caught before the push."""
    (repo / "pyproject.toml").write_text(PYPROJECT.format(version="1.0.1"), encoding="utf-8")
    _git(repo, "commit", "-qam", "release: 1.0.1")

    assert script.main(["--base", "main"]) == 1
    assert "were not regenerated" in capsys.readouterr().out


def test_the_real_lock_and_pyproject_differ_only_in_the_version_after_a_bump():
    """The lock pattern was written against uv's layout; if uv moved it, no release would ever qualify."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    version = script.project_version(pyproject)
    assert version is not None
    assert script.LOCK_VERSION.search(lock), "uv.lock no longer has the project entry the pattern expects"

    bumped_pyproject = pyproject.replace(f'version = "{version}"', 'version = "99.0.0"', 1)
    bumped_lock = script.LOCK_VERSION.sub(r'\1"99.0.0"', lock, count=1)
    assert bumped_lock != lock
    assert script.without_version(pyproject, lock) == script.without_version(bumped_pyproject, bumped_lock)

    # A dependency that moved with the bump keeps the two apart.
    changed = re.sub(r'(name = "requests"\nversion = )"[^"]*"', r'\1"0.0.1"', bumped_lock, count=1)
    assert changed != bumped_lock
    assert script.without_version(pyproject, lock) != script.without_version(bumped_pyproject, changed)
