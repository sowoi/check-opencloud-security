"""
scripts/check_tool_pins.py reports the CI tool pins Dependabot cannot see.

A pin the report does not find is a pin that goes stale without anyone being
told, so the discovery is tested against the real workflows. The comparison
runs on a canned registry, never the network.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("check_tool_pins", REPO_ROOT / "scripts" / "check_tool_pins.py")
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
sys.modules["check_tool_pins"] = script
SPEC.loader.exec_module(script)


def _workflow(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "w.yml"
    path.write_text(body, encoding="utf-8")
    return path


def test_every_known_pin_in_the_workflows_is_found():
    """These are the pins Dependabot does not update; losing one from the report hides it."""
    names = {pin.name for pin in script.all_pins()}

    assert {
        "ruff", "zizmor", "bandit", "bandit-sarif-formatter", "uv",
        "@biomejs/biome", "@mermaid-js/mermaid-cli",
        "koalaman/shellcheck", "hadolint/hadolint", "rhysd/actionlint", "goreleaser/nfpm",
    } <= names


def test_an_action_digest_or_a_comment_is_not_taken_for_a_pin():
    """Actions belong to Dependabot; a version in a comment pins nothing."""
    names = {pin.name for pin in script.all_pins()}

    assert not any(name.startswith(("actions/", "astral-sh/")) for name in names)


def test_a_uses_line_and_a_commented_version_are_ignored(tmp_path: Path):
    """The negative case on a file whose content is known."""
    workflow = _workflow(tmp_path, (
        "steps:\n"
        "  - uses: owner/action@" + "0" * 40 + " # v1.2.3\n"
        "  # run: uvx ruff@0.0.1 check\n"
        "  - run: uvx ruff@0.17.1 check # was ruff@0.16.0\n"
    ))

    assert [(p.name, p.version) for p in script.workflow_pins([workflow])] == [("ruff", "0.17.1")]


def test_a_folded_uvx_command_is_read_across_its_lines(tmp_path: Path):
    """Bandit's `run: >` block names its packages on the lines below `uvx`."""
    workflow = _workflow(tmp_path, (
        "steps:\n"
        "  - run: >\n"
        "      uvx --with formatter==1.2.3\n"
        "      tool@4.5.6 --recursive .\n"
        "  - run: echo other@9.9.9\n"
    ))
    found = {(pin.name, pin.version) for pin in script.workflow_pins([workflow])}

    assert found == {("formatter", "1.2.3"), ("tool", "4.5.6")}


def test_a_version_variable_without_a_source_is_refused(tmp_path: Path):
    """A new curl-fetched binary must be watched from the day it is added, not skipped."""
    workflow = _workflow(tmp_path, '        env:\n          NEWTOOL_VERSION: "1.0.0"\n')

    with pytest.raises(SystemExit, match="NEWTOOL_VERSION"):
        script.workflow_pins([workflow])


def test_a_known_version_variable_is_read(tmp_path: Path):
    workflow = _workflow(tmp_path, '        env:\n          HADOLINT_VERSION: "2.0.0"\n')

    assert script.workflow_pins([workflow]) == [
        script.Pin("github", "hadolint/hadolint", "2.0.0", "w.yml:2")
    ]


def test_the_uv_floor_is_read_and_an_exact_pin_refused(tmp_path: Path):
    """CI installs the floor; an `==` pin would break every newer local uv."""
    floor = tmp_path / "floor.toml"
    floor.write_text('[tool.uv]\nrequired-version = ">=0.13.1"\n', encoding="utf-8")
    exact = tmp_path / "exact.toml"
    exact.write_text('[tool.uv]\nrequired-version = "==0.13.1"\n', encoding="utf-8")
    none = tmp_path / "none.toml"
    none.write_text("[tool.uv]\n", encoding="utf-8")

    assert script.uv_pin(floor).version == "0.13.1"
    assert script.uv_pin(none) is None
    with pytest.raises(SystemExit):
        script.uv_pin(exact)


@pytest.mark.parametrize(("pinned", "latest", "behind"), [
    ("1.2.3", "1.2.4", True),
    ("1.9.0", "1.10.0", True),
    ("2.47", "2.47.0", False),
    ("1.2.3", "1.2.3", False),
    ("1.3.0", "1.2.9", False),
    ("1.2.3", "nightly", False),
])
def test_only_a_newer_numeric_release_counts_as_behind(pinned: str, latest: str, behind: bool):
    """Compared as numbers: a string compare would call 1.10 older than 1.9."""
    assert script.is_behind(pinned, latest) is behind


def test_the_report_marks_what_is_behind_and_survives_a_registry_failure():
    """One registry being down must not hide what the others found."""
    pins = [
        script.Pin("pypi", "ruff", "0.1.0", "a.yml:1"),
        script.Pin("github", "koalaman/shellcheck", "0.11.0", "a.yml:2"),
        script.Pin("github", "koalaman/shellcheck", "0.11.0", "b.yml:3"),
        script.Pin("npm", "@biomejs/biome", "2.0.0", "a.yml:4"),
    ]
    answers: dict[str, dict] = {
        "https://pypi.org/pypi/ruff/json": {"info": {"version": "0.2.0"}},
        "https://api.github.com/repos/koalaman/shellcheck/releases/latest": {"tag_name": "v0.11.0"},
    }

    def get_json(url: str) -> dict:
        if url not in answers:
            raise OSError("registry down")
        return answers[url]

    rows = {row.name: row for row in script.compare(pins, get_json)}

    assert rows["ruff"].behind
    assert not rows["koalaman/shellcheck"].behind
    assert rows["koalaman/shellcheck"].locations == ("a.yml:2", "b.yml:3")
    assert rows["@biomejs/biome"].error and not rows["@biomejs/biome"].behind
    table = script.markdown(list(rows.values()))
    assert "**0.2.0**" in table and "registry down" in table
