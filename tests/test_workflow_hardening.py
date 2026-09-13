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
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOWS_DIR.glob("*.yml"))

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


def _document(workflow: Path) -> dict:
    """The parsed workflow."""
    return yaml.safe_load(workflow.read_text(encoding="utf-8"))


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_a_checkout_keeps_no_token_unless_its_job_pushes(workflow: Path):
    """
    actions/checkout writes the job's token into .git/config by default.

    Every later step - and every artifact that uploads the workspace - can then
    read it. Only a job that pushes with git needs it there; zizmor's
    `artipacked` audit says the same in CI, and this says it before a push.
    """
    for name, job in _document(workflow)["jobs"].items():
        steps = job.get("steps", [])
        pushes = any("git push" in str(step.get("run", "")) for step in steps)
        for step in steps:
            if not str(step.get("uses", "")).startswith("actions/checkout@"):
                continue
            persists = (step.get("with") or {}).get("persist-credentials", True)
            assert persists is pushes, (
                f"{workflow.name}: job {name!r} "
                + ("pushes, so its checkout must keep the token"
                   if pushes else "never pushes, so its checkout must set persist-credentials: false")
            )


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_uv_sync_is_locked(workflow: Path):
    """An unlocked sync resolves afresh, so CI can pass on versions uv.lock does not pin."""
    for line in workflow.read_text(encoding="utf-8").splitlines():
        if "uv sync" in line:
            assert "--locked" in line, f"{workflow.name}: {line.strip()}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_a_workflow_that_can_write_or_sign_restores_no_cache(workflow: Path):
    """
    A cache is shared across runs, including those of pull requests.

    A workflow that pushes, opens pull requests, publishes or signs must not
    restore one, or whatever a poisoned cache holds ends up in a release.
    """
    text = workflow.read_text(encoding="utf-8")
    document = _document(workflow)
    grants = [document.get("permissions") or {}]
    grants += [job.get("permissions") or {} for job in document["jobs"].values()]
    privileged = any(
        isinstance(grant, dict)
        and any(grant.get(scope) == "write" for scope in ("contents", "id-token", "attestations"))
        for grant in grants
    )

    if privileged:
        assert "enable-cache: true" not in text, workflow.name
        assert "cache-from:" not in text or "push: false" in text, workflow.name


def test_the_nox_matrix_names_every_supported_python():
    """A version dropped from the matrix is a `requires-python` promise nobody tests."""
    noxfile = (ROOT / "noxfile.py").read_text(encoding="utf-8")
    supported = re.search(r"PYTHON_VERSIONS = (\[.*?\])", noxfile)
    assert supported
    job = _document(WORKFLOWS_DIR / "run-python-version-test.yml")["jobs"]["uv-test"]

    assert job["strategy"]["matrix"]["python"] == yaml.safe_load(supported.group(1))


def test_both_workflows_install_the_same_shellcheck():
    """actionlint lints `run:` blocks with the shellcheck the scripts are held to."""
    def pins(name: str) -> dict:
        text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
        return dict(re.findall(r"(SHELLCHECK_(?:VERSION|SHA256)):\s*\"([^\"]+)\"", text))

    assert pins("workflow-lint.yml") == pins("static-analysis.yml") != {}
