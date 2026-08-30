"""
The workflow files must not hand out more than the job in front of them needs.

Two properties, both of which were true of most of this directory and silently
untrue of part of it until a full-repository audit went looking. Neither is
visible in a green pipeline - a workflow with a write token and a mutable
action reference passes exactly like one without - so they are asserted here
rather than left to review.

The list of workflows is read from the directory rather than written out, so a
workflow added later is covered the moment it exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# `owner/repo@<40 hex>`, optionally with a subdirectory, followed by the
# comment naming the human-readable version the digest was resolved from.
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}\s+#\s*\S+")


def _uses_lines(path: Path) -> list[tuple[int, str]]:
    """Every `uses:` reference in one workflow, with its line number."""
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip().removeprefix("- ").strip()
        if stripped.startswith("uses:"):
            found.append((number, stripped.split(":", 1)[1].strip()))
    return found


def test_there_are_workflows_to_check():
    """The guard on the two tests below: an empty glob would pass both."""
    assert WORKFLOWS, "no workflows were found to check"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_a_workflow_declares_the_token_scope_it_needs(workflow: Path):
    """
    Without a `permissions:` block the token is whatever the repository grants.

    That default is set outside this file, is frequently write across every
    scope, and applies to jobs that install and execute the dependency tree on
    a push. Declaring the scope here means the workflow carries its own answer
    rather than inheriting one that can change without a commit.

    A job may ask for more than the top-level block - Bandit needs
    `security-events: write` to upload its SARIF - and that is the point of
    stating a read-only default: the extra grant is visible at the job that
    needs it instead of applying to all of them.
    """
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))

    assert document.get("permissions") is not None, (
        f"{workflow.name} declares no top-level permissions, so its token is "
        "whatever the repository default happens to be"
    )


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_a_workflow_pins_every_action_to_a_digest(workflow: Path):
    """
    A tag is mutable, and a moved tag runs somebody else's new code as us.

    The risk is not hypothetical for a repository whose workflows hold
    `contents: write` and publish to PyPI and Docker Hub. A digest is the only
    reference an upstream account cannot repoint, and the trailing comment is
    what keeps the pin readable - and reviewable - once it is 40 hex digits.
    """
    for number, reference in _uses_lines(workflow):
        if reference.startswith("./"):  # a local action cannot be pinned
            continue
        assert PINNED.match(reference), (
            f"{workflow.name}:{number} is not pinned to a digest with a "
            f"version comment: {reference}"
        )
