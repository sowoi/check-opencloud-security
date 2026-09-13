"""Tests for scripts/check_pull_request.py.

Two rules used to live only as checkboxes in the pull request template: that
every change is written up in CHANGELOG.md and RELEASE.md, and that a version
bump - which publishes to PyPI the moment it lands - is somebody's deliberate
decision. A checkbox is ticked or not; these tests hold the script that
replaced it to failing when it should, and to staying quiet when it should.
"""

from __future__ import annotations

import importlib.util
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
        "changed_files": ["webapp/app.py", "CHANGELOG.md", "RELEASE.md"],
        "labels": set(),
        "author": "a-contributor",
        "version": "1.1.0",
        "base_changelog": CHANGELOG.format(unreleased=""),
        "head_changelog": CHANGELOG.format(unreleased="### Fixed\n\n- A thing."),
        "head_release": RELEASE.format(version="1.1.0", body="- A thing."),
    }
    arguments.update(overrides)
    return arguments


def bump(**overrides: object) -> dict:
    """A labelled, forward, untagged bump, so a test can break one thing."""
    arguments: dict = {
        "base_version": "1.0.0",
        "head_version": "1.1.0",
        "labels": {"release"},
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


def test_a_change_missing_from_release_md_is_refused():
    """AGENTS.md asks for both files; the release body comes from the second."""
    problems = script.check_changelog(**documented(changed_files=["webapp/app.py", "CHANGELOG.md"]))

    assert any("RELEASE.md is unchanged" in p for p in problems)
    assert not any("CHANGELOG.md" in p and "no new entry" in p for p in problems)


def test_release_md_written_for_another_version_is_refused():
    """Entries under a stale heading are notes for a release that already went out."""
    problems = script.check_changelog(
        **documented(head_release=RELEASE.format(version="1.0.0", body="- A thing."))
    )

    assert any("RELEASE.md is written for 1.0.0" in p for p in problems)


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


def test_an_unchanged_version_needs_no_label():
    """Only a bump publishes; an ordinary pull request must not be asked to label itself."""
    assert script.check_version(**bump(head_version="1.0.0", labels=set(), bump_subjects=[])) == []


def test_a_labelled_forward_bump_passes():
    """The guard for the refusals below."""
    assert script.check_version(**bump()) == []


def test_a_bump_without_the_release_label_is_refused():
    """Merging a bump publishes to PyPI, so somebody has to say they mean it."""
    problems = script.check_version(**bump(labels=set()))

    assert any("Label it 'release'" in p for p in problems)


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


def test_the_repository_documents_releases_under_the_heading_the_check_reads():
    """Checked against the real files, so a renamed heading fails here, not on every pull request."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    release = (REPO_ROOT / "RELEASE.md").read_text(encoding="utf-8")

    assert script.release_heading_version(release) == script.project_version(pyproject)


# --- the whole script, against a real repository -----------------------------


def _git(repo: Path, *args: str) -> str:
    """Run git in the throwaway repository with an identity and no signing."""
    return subprocess.run(  # nosec B603 B607 - fixed argv, git from PATH
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """A released 1.0.0 on main and a branch to open pull requests from."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.format(version="1.0.0"), encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG.format(unreleased=""), encoding="utf-8")
    (tmp_path / "RELEASE.md").write_text(RELEASE.format(version="1.0.0", body="- First."), encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
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
    (repo / "RELEASE.md").write_text(RELEASE.format(version="1.0.0", body="- First.\n- x."), encoding="utf-8")
    _git(repo, "commit", "-qam", "fix: x")
    (repo / "pyproject.toml").write_text(PYPROJECT.format(version="1.1.0"), encoding="utf-8")
    (repo / "RELEASE.md").write_text(RELEASE.format(version="1.1.0", body="- x."), encoding="utf-8")
    _git(repo, "commit", "-qam", "chore(release): bump to version 1.1.0")

    assert script.main(["--base", "main", "--labels", "release"]) == 0
    assert script.main(["--base", "main"]) == 1
    assert "Label it 'release'" in capsys.readouterr().out


def test_the_script_refuses_a_mislabelled_bump_commit_end_to_end(repo, capsys):
    """The subject check reads the version each commit actually set, from git."""
    (repo / "CHANGELOG.md").write_text(CHANGELOG.format(unreleased="### Fixed\n\n- x."), encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT.format(version="1.1.0"), encoding="utf-8")
    (repo / "RELEASE.md").write_text(RELEASE.format(version="1.1.0", body="- x."), encoding="utf-8")
    _git(repo, "commit", "-qam", "Bump to version 1.3.3")

    assert script.main(["--base", "main", "--labels", "release"]) == 1
    assert "subject says 1.3.3" in capsys.readouterr().out


def test_the_script_refuses_an_undocumented_change_end_to_end(repo, capsys):
    """The ordinary failure: code changed, notes did not."""
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "fix: x")

    assert script.main(["--base", "main"]) == 1
    output = capsys.readouterr().out
    assert "CHANGELOG.md has no new entry" in output
    assert script.main(["--base", "main", "--labels", "skip-changelog"]) == 0
