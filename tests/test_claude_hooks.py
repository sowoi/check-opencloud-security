"""
The Claude Code hooks in ``.claude/hooks/``: guards that must keep refusing.

``.claude/settings.json`` runs these scripts before every Bash command and
every file edit, and when a session ends. They enforce the rules AGENTS.md
states in prose - no merge, tag, force-push or advisory publication, no hand
edit to a generated file, no real host, scan output or personal data in a
commit - so a regression here silently turns a hard rule back into a hope.

Every fake leak below is assembled from pieces at run time, so this file
itself never carries a real-looking host, address or token: the privacy guard
checks its own test file like any other (see the last test).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / ".claude" / "hooks"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="the hooks need git")

# Fake values, built so that no literal in this file matches the guard.
INSTANCE_HOST = "files.acme-" + "corp" + ".de"
REFERENCE_HOST = "wiki.nft-howto" + ".org"
KNOWN_HOST = "known-ref" + ".net"
PERSON = "jane.doe" + "@" + "mail-provider" + ".de"
ROLE_MAILBOX = "support" + "@" + "vendor-x" + ".com"
PUBLIC_IP = "85.214" + ".12.34"
PUBLIC_IP6 = "2a01:4f8" + ":c0c:1234::1"
GITHUB_TOKEN = "gh" + "p_" + "a" * 36
BEARER = "Bear" + "er " + "abcDEF123456" * 3
SCAN_RESULT = '{"scannedAt": {"date": "2026-01-01"}, "ratingExplanation": {"rating": 5}}\n'
EXPORT_NAME = "scan-" + "0b7c2a53-8f1e-4c1a-9a55-2d5b0c7e6f10" + ".pdf"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"claude_hook_{name}", HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard_bash = _load("guard_bash")
guard_edit = _load("guard_edit")
privacy_guard = _load("privacy_guard")


def _hook(script: str, payload: object, *args: str, project: Path = REPO_ROOT) -> tuple[int, dict]:
    """Run a hook the way Claude Code does and return (exit code, parsed stdout)."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        [sys.executable, str(HOOKS / script), *args],
        input=stdin, capture_output=True, text=True, check=False,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
    )
    return result.returncode, (json.loads(result.stdout) if result.stdout.strip() else {})


def _decision(output: dict) -> str:
    specific = output.get("hookSpecificOutput") or {}
    return specific.get("permissionDecision") or output.get("decision") or (
        "message" if output.get("systemMessage") else "allow")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", *args],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository whose ``origin/main`` already mentions one public host."""
    path = tmp_path / "repo"
    (path / "docs").mkdir(parents=True)
    (path / "docs" / "reference.md").write_text(f"See https://{KNOWN_HOST}/manual\n")
    _git(path, "init", "-q", "-b", "feature")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    _git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return path


# --- guard_bash.py -------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "python scripts/security_advisories.py --publish",
    "uv run --frozen python scripts/security_advisories.py --sync",
    "gh pr merge 80 --squash",
    "gh release create v1.0.0",
    "gh api -X POST repos/o/r/security-advisories -f summary=x",
    "git tag v1.24.1",
    "git tag -d v1.24.1",
    "git push --force origin feature",
    "git push -f",
    "git push --force-with-lease",
    "git push origin +feature",
    "git push origin HEAD:main",
    "git push --repo origin HEAD:main",
    "git push --repo=origin HEAD:main",
    "git push --tags",
    "git status && git push origin v1.2.3",
    "cd sub && git push -f",
    "(git push -f)",
    "git -C sub reset --hard HEAD",
    "FOO=1 git reset --hard",
    "git merge --abort",
    "git clean -fd",
    "uvx ruff format .",
    "uvx ruff@0.9 format .",
])
def test_the_bash_guard_refuses_what_only_the_user_may_do(command):
    """Merging, tagging, force-pushing, publishing and reformatting are refused."""
    assert guard_bash.check(command), command
    code, output = _hook("guard_bash.py", {"tool_input": {"command": command}})
    assert code == 0 and _decision(output) == "deny"


@pytest.mark.parametrize("command", [
    "python scripts/security_advisories.py --check",
    "gh pr checks 80 --watch --interval 60",
    "gh pr create --base main --head release/1.24.1 --title t --body-file f",
    "gh api repos/o/r/security-advisories",
    "git tag",
    "git tag --list 'v*' --sort=-v:refname | head -1",
    "git tag --contains abc --sort=v:refname",
    "git push -u origin release/1.24.1",
    "git push -u origin HEAD",
    "git reset HEAD file",
    "git merge --continue",
    "git clean -n",
    "git fetch origin --tags",
    "git add -A -- . ':!.claude'",
    "uvx ruff check .",
    "uv run --group test --extra signing pytest -q",
])
def test_the_bash_guard_allows_what_the_workflows_need(command):
    """The commands the skills run day to day pass untouched."""
    assert guard_bash.check(command) is None, command


@pytest.mark.parametrize("command", [
    "cat > notes.md <<'X'\nDo not run `ruff format` or gh pr merge here\nX",
    "git commit -m 'never git push --force or git reset --hard'",
    "git clean -n; ls -f",
])
def test_the_bash_guard_ignores_commands_that_are_only_mentioned(command):
    """A rule matches a command being run, not text that names one."""
    assert guard_bash.check(command) is None


def test_the_bash_guard_fails_closed_on_unreadable_input():
    """Input the guard cannot read refuses the call instead of allowing it."""
    code, _ = _hook("guard_bash.py", "not json")
    assert code == 2


# --- guard_edit.py -------------------------------------------------------------

def _edit(old: str, new: str) -> dict:
    return {"old_string": old, "new_string": new}


@pytest.mark.parametrize("path", [
    "RELEASE.md",
    "frontend/templates/docs/installation.html",
    "frontend/templates/admin-docs/architecture.html",
    "frontend/static/search-index.de.json",
    "opencloud_local_scan/data/release_schedule.json",
    "opencloud_local_scan/data/vulnerabilities.json",
])
def test_the_edit_guard_refuses_generated_files(path):
    """A generated file is regenerated, never edited by hand."""
    decision = guard_edit.decide(path, "Edit", _edit("a", "b"), "a")
    assert decision and decision[0] == "deny"


def test_the_edit_guard_refuses_edits_inside_a_generated_block():
    """The README release-schedule table is generated; the rest of README is not."""
    readme = "# Title\n<!-- release-schedule:start -->\n| 7.2 |\n<!-- release-schedule:end -->\nText\n"
    inside = guard_edit.decide("README.md", "Edit", _edit("| 7.2 |", "| 7.3 |"), readme)
    outside = guard_edit.decide("README.md", "Edit", _edit("Text", "More text"), readme)
    rewritten = guard_edit.decide("README.md", "Write", {"content": readme.replace("7.2", "7.3")}, readme)
    unchanged = guard_edit.decide("README.md", "Write", {"content": readme + "More\n"}, readme)
    assert inside and inside[0] == "deny"
    assert rewritten and rewritten[0] == "deny"
    assert outside is None and unchanged is None


def test_the_edit_guard_asks_before_the_version_changes():
    """Only the user bumps the version; other pyproject edits pass."""
    bump = guard_edit.decide("pyproject.toml", "Edit", _edit('version = "1.0.0"', 'version = "1.0.1"'), "")
    other = guard_edit.decide("pyproject.toml", "Edit", _edit("[project]", "[project]\n"), "")
    literal = guard_edit.decide("pkg/mod.py", "Edit", _edit("x", '__version__ = "1.0"'), "")
    assert bump and bump[0] == "ask"
    assert literal and literal[0] == "ask"
    assert other is None


@pytest.mark.parametrize("markup", ['<div style="x">', '<button onclick="go()">', "<script>run()</script>"])
def test_the_edit_guard_refuses_inline_markup_in_templates(markup):
    """The CSP has no 'unsafe-inline', so templates carry no inline style or script."""
    decision = guard_edit.decide("frontend/templates/about.html", "Edit", _edit("a", markup), "a")
    assert decision and decision[0] == "deny"


def test_the_edit_guard_allows_external_scripts_and_data_attributes():
    """A script with src and a data-* attribute are what the CSP expects."""
    markup = '<script src="/static/x.js" defer></script><div class="x" data-on="y">'
    assert guard_edit.decide("frontend/templates/about.html", "Edit", _edit("a", markup), "a") is None


def test_the_edit_guard_asks_before_the_privacy_allowlist_changes():
    """What the privacy guard lets through is the user's decision."""
    decision = guard_edit.decide(".claude/hooks/privacy_allowlist.txt", "Edit", _edit("a", "b"), "a")
    assert decision and decision[0] == "ask"


def test_the_edit_guard_ignores_files_outside_the_project(tmp_path):
    """A scratch file elsewhere is none of the project's business."""
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "RELEASE.md"), "content": "x"}}
    code, output = _hook("guard_edit.py", payload)
    assert code == 0 and output == {}


# --- stop_checks.py ------------------------------------------------------------

def _fake_check(repo: Path, script: str, body: str) -> None:
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / script).write_text(body)


@pytest.fixture
def check_repo(repo: Path) -> Path:
    """The repository with a project interpreter the stop checks will use."""
    venv_bin = repo / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    (repo / ".gitignore").write_text(".venv/\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-q", "-m", "ignore venv")
    return repo


def test_the_stop_checks_stay_quiet_when_nothing_changed(check_repo):
    """A clean tree runs no check at all."""
    assert _hook("stop_checks.py", {}, project=check_repo) == (0, {})


def test_the_stop_checks_block_on_a_failing_generator_check(check_repo):
    """A changed source whose --check fails keeps the session going."""
    _fake_check(check_repo, "security_advisories.py", "import sys; print('entry lacks a record'); sys.exit(1)\n")
    (check_repo / "CHANGELOG.md").write_text("### Security\n")
    code, output = _hook("stop_checks.py", {}, project=check_repo)
    assert code == 0 and output["decision"] == "block"
    assert "entry lacks a record" in output["reason"]


def test_the_stop_checks_report_a_missing_dependency_as_skipped(check_repo):
    """An environment without the project's packages is not a stale file."""
    _fake_check(check_repo, "security_advisories.py", "import not_a_real_module_for_this_test\n")
    (check_repo / "CHANGELOG.md").write_text("### Security\n")
    code, output = _hook("stop_checks.py", {}, project=check_repo)
    assert code == 0 and "decision" not in output
    assert "skipped" in output["systemMessage"]


def test_the_stop_checks_only_warn_about_a_stale_search_index(check_repo):
    """CI rebuilds the search index, so a stale one never blocks."""
    _fake_check(check_repo, "build_search_index.py", "import sys; sys.exit(1)\n")
    (check_repo / "frontend").mkdir()
    (check_repo / "frontend" / "page.html").write_text("<p>x</p>\n")
    code, output = _hook("stop_checks.py", {}, project=check_repo)
    assert code == 0 and "decision" not in output
    assert "warning only" in output["systemMessage"]


def test_the_stop_checks_do_not_loop(check_repo):
    """A stop the hook already blocked once is let through."""
    _fake_check(check_repo, "security_advisories.py", "import sys; sys.exit(1)\n")
    (check_repo / "CHANGELOG.md").write_text("### Security\n")
    assert _hook("stop_checks.py", {"stop_hook_active": True}, project=check_repo) == (0, {})


# --- privacy_guard.py: judging -------------------------------------------------

@pytest.fixture
def judge(repo, monkeypatch, tmp_path):
    """Evaluate staged-looking text against ``repo`` with an empty allowlist."""
    allowlist = tmp_path / "allowlist.txt"
    allowlist.write_text("")
    monkeypatch.setattr(privacy_guard, "ROOT", str(repo))
    monkeypatch.setattr(privacy_guard, "ALLOWLIST", str(allowlist))

    def evaluate(files: dict[str, str], message: str = "") -> dict[str, list[str]]:
        source = privacy_guard.Source("staged")
        for path, text in files.items():
            source.add_path(path)
            for number, line in enumerate(text.splitlines(), 1):
                source.add_line(path, number, line)
        if message:
            source.messages.append(message)
        return privacy_guard.evaluate([source])

    evaluate.allowlist = allowlist  # type: ignore[attr-defined]
    return evaluate


@pytest.mark.parametrize(("path", "text"), [
    ("docs/guide.md", f"Run it against {INSTANCE_HOST} first."),
    ("docs/guide.md", f"See https://{REFERENCE_HOST}/status.php for the result."),
    ("docs/guide.md", f"check_opencloud_security.py -H {REFERENCE_HOST}"),
    ("tests/test_x.py", f'TARGET = "{INSTANCE_HOST}"'),
    ("docs/guide.md", f"Contact {PERSON}"),
    ("docs/guide.md", f"Server at {PUBLIC_IP}"),
    ("docs/guide.md", f"Server at {PUBLIC_IP6}"),
    ("config/x.yml", f"token: {GITHUB_TOKEN}"),
    ("config/x.yml", f"Authorization: {BEARER}"),
    ("reports/result.json", SCAN_RESULT),
    ("reports/metrics.prom", 'opencloud_security_rating_score{host="x"} 2\n'),
    ("reports/out.txt", "OpenCloud 7.2.3 on opencloud.example.com, rating: A+, last scanned: now\n"),
    (f"downloads/{EXPORT_NAME}", ""),
])
def test_the_privacy_guard_blocks_instances_scans_and_personal_data(judge, path, text):
    """Anything that identifies an instance, a person or a scan is refused."""
    found = judge({path: text})
    assert found["block"], (path, text)


def test_the_privacy_guard_blocks_a_host_in_the_commit_message(judge):
    """AGENTS.md: a real hostname never appears in a commit message either."""
    found = judge({}, message=f"fix: scanned https://{INSTANCE_HOST} and it rated F")
    assert found["block"]


@pytest.mark.parametrize(("path", "text"), [
    ("docs/guide.md", f"Background: https://{REFERENCE_HOST}/nat"),
    ("docs/guide.md", f"Write to {ROLE_MAILBOX}"),
    ("tests/test_x.py", f'ADDRESS = "{PUBLIC_IP}"'),
    ("tests/test_x.py", f'headers = {{"Authorization": "{BEARER}"}}'),
])
def test_the_privacy_guard_asks_about_what_may_be_a_public_reference(judge, path, text):
    """A new reference host, a role mailbox and test fixtures are shown, not refused."""
    found = judge({path: text})
    assert not found["block"] and found["review"], (path, text)


@pytest.mark.parametrize(("path", "text"), [
    ("docs/guide.md", "Use opencloud.example.com, cloud.test, x.invalid and opencloud.internal."),
    ("docs/guide.md", "Documentation addresses 192.0.2.10, 2001:db8::1 and 10.0.0.5 stay private."),
    ("docs/guide.md", "Version 7.2.3, file opencloud.yaml, README.md and setup-wizard.py."),
    ("webapp/view.py", 'logger.info("x"); request.app.state; t("nav.ai")'),
    ("docs/guide.md", "Co-Authored-By: Claude <noreply@anthropic.com>"),
    ("docs/guide.md", f"Reference: https://{KNOWN_HOST}/other-page"),
    ("tests/fixtures/result.json", SCAN_RESULT),
    ("frontend/static/search-index.json", f'"text": "{INSTANCE_HOST}"'),
])
def test_the_privacy_guard_passes_reserved_known_and_generated_content(judge, path, text):
    """Reserved names, values already on main, fixtures and generated files pass."""
    assert judge({path: text}) == {"block": [], "review": []}, (path, text)


def test_the_privacy_guard_honours_the_allowlist(judge):
    """A public reference the user approved passes."""
    judge.allowlist.write_text(f"# approved\n*.{REFERENCE_HOST.split('.', 1)[1]}\n")
    assert judge({"docs/guide.md": f"https://{REFERENCE_HOST}/nat"}) == {"block": [], "review": []}


# --- privacy_guard.py: the hook entry points -------------------------------------

def _commit_payload(command: str) -> dict:
    return {"tool_input": {"command": command}}


def test_a_commit_with_a_staged_leak_is_refused(repo):
    """Staged content that names an instance stops the commit."""
    (repo / "docs" / "leak.md").write_text(f"Scan against {INSTANCE_HOST}\n")
    _git(repo, "add", "docs/leak.md")
    code, output = _hook("privacy_guard.py", _commit_payload("git commit -m docs"), "pre-tool-use", project=repo)
    assert code == 0 and _decision(output) == "deny"
    assert INSTANCE_HOST in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_commit_that_stages_everything_checks_untracked_files(repo):
    """`git add -A && git commit` is judged on what it is about to stage."""
    (repo / "scan-result.json").write_text(SCAN_RESULT)
    _, output = _hook("privacy_guard.py", _commit_payload("git add -A && git commit -m wip"),
                      "pre-tool-use", project=repo)
    assert _decision(output) == "deny"


def test_a_commit_with_a_new_reference_host_asks(repo):
    """A new host that does not look like an instance is the user's call."""
    (repo / "docs" / "ref.md").write_text(f"https://{REFERENCE_HOST}/nat\n")
    _git(repo, "add", "docs/ref.md")
    _, output = _hook("privacy_guard.py", _commit_payload("git commit -m ref"), "pre-tool-use", project=repo)
    assert _decision(output) == "ask"


def test_a_clean_commit_and_unrelated_commands_pass(repo):
    """Nothing to report means no output at all."""
    for command in ("git commit -m docs", "git status", "ls -la"):
        assert _hook("privacy_guard.py", _commit_payload(command), "pre-tool-use", project=repo) == (0, {})


def test_a_push_of_a_leaking_commit_is_refused(repo):
    """The commits a push would send are checked, not only the last one."""
    (repo / "docs" / "people.md").write_text(f"Contact {PERSON}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "people")
    (repo / "docs" / "more.md").write_text("Nothing here.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "more")
    _, output = _hook("privacy_guard.py", _commit_payload("git push -u origin feature"), "pre-tool-use", project=repo)
    assert _decision(output) == "deny"
    assert PERSON in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_pull_request_body_file_is_checked(repo):
    """The body of a pull request is public the moment it is created."""
    (repo / "body.md").write_text(f"Tested on https://{INSTANCE_HOST}\n")
    _, output = _hook("privacy_guard.py", _commit_payload("gh pr create --title t --body-file body.md"),
                      "pre-tool-use", project=repo)
    assert _decision(output) == "deny"


def test_the_stop_hook_blocks_once_then_warns(repo):
    """An unpushed leak keeps the session going once, then tells the user."""
    (repo / "docs" / "leak.md").write_text(f"Server at {PUBLIC_IP}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "leak")
    _, first = _hook("privacy_guard.py", {}, "stop", project=repo)
    _, again = _hook("privacy_guard.py", {"stop_hook_active": True}, "stop", project=repo)
    assert first["decision"] == "block" and PUBLIC_IP in first["reason"]
    assert "decision" not in again and PUBLIC_IP in again["systemMessage"]


def test_the_stop_hook_is_silent_without_findings(repo):
    """A clean branch ends the session without a word."""
    assert _hook("privacy_guard.py", {}, "stop", project=repo) == (0, {})


def test_the_privacy_guard_fails_closed_on_unreadable_input(repo):
    """Before a command, unreadable input refuses; at the end of a session it does not loop."""
    assert _hook("privacy_guard.py", "not json", "pre-tool-use", project=repo)[0] == 2
    assert _hook("privacy_guard.py", "not json", "stop", project=repo) == (0, {})


def test_this_file_passes_the_privacy_guard(judge, monkeypatch):
    """The fake leaks above are assembled at run time, so this file is clean."""
    monkeypatch.setattr(privacy_guard, "_base_ref", lambda: None)
    text = Path(__file__).read_text(encoding="utf-8")
    assert judge({"tests/test_claude_hooks.py": text}) == {"block": [], "review": []}


# --- guard_bash.py: reading a command ------------------------------------------

@pytest.mark.parametrize("command", [
    "echo $(git push -f)",
    "`git push -f`",
    "bash -c 'git push -f'",
    'sh -c "gh pr merge 1"',
    "eval 'git reset --hard'",
    "{ git push -f; }",
    "true & git push -f",
    "xargs git push -f < /dev/null",
    "xargs -0 git push -f",
    "nohup git push -f",
    "timeout 5 git push -f",
    "! git push -f",
    "git push -o ci.skip origin main",
    'git commit -m "run `git push -f` now"',
    "cat <<'X' > /tmp/notes\nbody\nX\ngit push -f",
    "cat <<A <<B\na\nA\nb\nB\ngit push -f",
])
def test_the_bash_guard_sees_commands_inside_substitutions_and_shells(command):
    """A refused command stays refused inside $(...), bash -c, eval, braces or xargs."""
    assert guard_bash.check(command), command


@pytest.mark.parametrize("command", [
    "git commit -m \"$(cat <<'EOF'\nfix: don't `ruff format` or git push -f (never)\nEOF\n)\"",
    "cat <<'X' > /tmp/notes.md\ngit push -f\nrm RELEASE.md\nX",
    "git commit -m 'a; git push -f | b && c'",
    "echo \"it's fine; git push -f\"",
    "ls # git push -f",
    "uvx ruff format --check .",
    "uvx ruff format --diff .",
    "git tag 2>/dev/null",
    "git tag -l 2> /dev/null",
    "git push origin release/1.24.1 2>&1 | tail -3",
])
def test_the_bash_guard_ignores_quoted_text_heredocs_and_read_only_forms(command):
    """Quoted text, heredoc bodies, comments and read-only modes are not commands to refuse."""
    assert guard_bash.decide(command, str(REPO_ROOT), str(REPO_ROOT)) is None, command


@pytest.mark.parametrize("command", [
    "echo x > RELEASE.md",
    "cat notes >> RELEASE.md",
    "tee RELEASE.md < notes",
    "sed -i '' 's/a/b/' frontend/templates/docs/csp.html",
    "sed -i.bak -e 's/a/b/' RELEASE.md",
    "perl -pi -e 's/a/b/' RELEASE.md",
    "cp /tmp/index.json frontend/static/search-index.json",
    "rm frontend/templates/docs/csp.html",
    'echo x > "RELEASE.md"',
    f"echo x > {REPO_ROOT}/RELEASE.md",
])
def test_every_shell_write_form_to_a_generated_file_is_refused(command):
    """A redirect, tee, sed -i, cp or rm is no way around the Edit guard."""
    decision = guard_bash.decide(command, str(REPO_ROOT), str(REPO_ROOT))
    assert decision and decision[0] == "deny", command


@pytest.mark.parametrize("command", [
    "printf '%s' x >> .claude/hooks/privacy_allowlist.txt",
    "mv notes .claude/hooks/privacy_guard.py",
    "sed -i '' 's/1.0.0/2.0.0/' pyproject.toml",
])
def test_the_bash_guard_asks_before_shell_writes_to_guarded_files(command):
    """The privacy allowlist and pyproject.toml are the user's to change."""
    decision = guard_bash.decide(command, str(REPO_ROOT), str(REPO_ROOT))
    assert decision and decision[0] == "ask", command


@pytest.mark.parametrize("command", [
    "echo x > /tmp/scratch.txt",
    "sed -n 1,5p RELEASE.md",
    "sed 's/a/b/' RELEASE.md > /tmp/out",
    "cp RELEASE.md /tmp/release.md",
    "python scripts/build_search_index.py > /dev/null",
    "echo ok >&2",
    "ls &> /dev/null",
])
def test_the_bash_guard_allows_reads_and_writes_elsewhere(command):
    """Reading a protected file, or writing somewhere else, is fine."""
    assert guard_bash.decide(command, str(REPO_ROOT), str(REPO_ROOT)) is None, command


def test_the_bash_guard_resolves_writes_from_the_working_directory():
    """A relative path is resolved from the directory the command runs in."""
    payload = {"tool_input": {"command": "echo x > ../RELEASE.md"}, "cwd": str(REPO_ROOT / "docs")}
    code, output = _hook("guard_bash.py", payload)
    assert code == 0 and _decision(output) == "deny"


# --- stop_checks.py: what counts as a missing dependency -------------------------

def test_the_stop_checks_block_a_failure_that_only_mentions_an_import_error(check_repo):
    """Only a traceback ending in an import error means the environment is incomplete."""
    _fake_check(check_repo, "security_advisories.py",
                "import sys; print('ImportError: in the docs'); print('stale entry'); sys.exit(1)\n")
    (check_repo / "CHANGELOG.md").write_text("### Security\n")
    _, output = _hook("stop_checks.py", {}, project=check_repo)
    assert output["decision"] == "block"


# --- privacy_guard.py: reading diffs, commands and history -----------------------

def test_a_line_starting_with_plus_plus_is_not_a_file_header():
    """Added text such as `++ /dev/null` cannot hide the lines after it."""
    source = privacy_guard.Source("staged")
    patch = ("diff --git a/notes.md b/notes.md\n--- a/notes.md\n+++ b/notes.md\n@@ -0,0 +1,3 @@\n"
             f"+intro\n++ /dev/null\n+see {INSTANCE_HOST}\n")
    privacy_guard._parse_patch(patch, source)
    assert [text for _, text in source.files["notes.md"]] == ["intro", "+ /dev/null", f"see {INSTANCE_HOST}"]


def test_a_value_inside_a_longer_known_one_is_still_new(judge, repo):
    """`main` knowing a longer host or address does not make a shorter one known."""
    (repo / "docs" / "longer.md").write_text(f"my{INSTANCE_HOST} and 8{PUBLIC_IP}5\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "longer")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    found = judge({"docs/guide.md": f"Run it against {INSTANCE_HOST} at {PUBLIC_IP}"})
    assert len(found["block"]) == 2
    assert judge({"docs/guide.md": f"Old box my{INSTANCE_HOST}"}) == {"block": [], "review": []}


@pytest.mark.parametrize(("words", "stages", "files"), [
    (["-m", "add a feature"], False, []),
    (["-m", "fix", "-a"], True, []),
    (["-am", "fix"], True, []),
    (["--all", "-m", "fix"], True, []),
    (["-m", "fix", "docs/leak.md"], True, []),
    (["-F", "msg.txt"], False, ["msg.txt"]),
    (["-Fmsg.txt"], False, ["msg.txt"]),
    (["--file=msg.txt"], False, ["msg.txt"]),
    (["-sF", "msg.txt"], False, ["msg.txt"]),
    (["--amend", "--no-edit"], False, []),
])
def test_commit_options_are_read_as_git_reads_them(words, stages, files):
    """Only -a/--all/-i/-o or a pathspec take working-tree content; -F names a message file."""
    assert privacy_guard.commit_details(words) == (stages, files)


def test_the_word_add_in_a_message_does_not_widen_the_check(repo):
    """An untracked file is not judged for a commit that does not include it."""
    (repo / "scratch.json").write_text(SCAN_RESULT)
    code, output = _hook("privacy_guard.py", _commit_payload("git commit -m 'add a feature'"),
                         "pre-tool-use", project=repo)
    assert (code, output) == (0, {})


def test_a_commit_of_named_paths_checks_the_working_tree(repo):
    """`git commit <path>` commits what is on disk, so that is what gets checked."""
    (repo / "docs" / "reference.md").write_text(f"Scan against {INSTANCE_HOST}\n")
    _, output = _hook("privacy_guard.py", _commit_payload("git commit -m docs docs/reference.md"),
                      "pre-tool-use", project=repo)
    assert _decision(output) == "deny"


@pytest.mark.parametrize("option", ["-F msg.txt", "-Fmsg.txt", "--file=msg.txt"])
def test_a_commit_message_file_is_checked(repo, option):
    """A message read from a file is a commit message like any other."""
    (repo / "msg.txt").write_text(f"fix: scanned https://{INSTANCE_HOST}\n")
    _, output = _hook("privacy_guard.py", {"tool_input": {"command": f"git commit {option}"}, "cwd": str(repo)},
                      "pre-tool-use", project=repo)
    assert _decision(output) == "deny"


@pytest.mark.parametrize("command", [
    "gh pr create --title t -F body.md",
    "gh pr create --title t --body-file=body.md",
    "gh issue comment 5 --body-file body.md",
])
def test_every_form_of_a_gh_body_file_is_checked(repo, command):
    """The short -F and the = form of --body-file are read too, for issues as well."""
    (repo / "body.md").write_text(f"Tested on https://{INSTANCE_HOST}\n")
    _, output = _hook("privacy_guard.py", {"tool_input": {"command": command}, "cwd": str(repo)},
                      "pre-tool-use", project=repo)
    assert _decision(output) == "deny"


def test_a_push_checks_the_branch_it_pushes(repo):
    """Pushing another branch checks that branch, not the one checked out."""
    _git(repo, "switch", "-q", "-c", "leaky")
    (repo / "docs" / "leak.md").write_text(f"Contact {PERSON}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "leak")
    _git(repo, "switch", "-q", "feature")

    def push(target: str) -> dict:
        return _hook("privacy_guard.py", _commit_payload(f"git push origin {target}"),
                     "pre-tool-use", project=repo)[1]

    assert _decision(push("leaky")) == "deny"
    assert _decision(push("leaky:review")) == "deny"
    assert push("feature") == {}

    for command in (
        "git push --repo origin leaky",
        "git push --repo=origin leaky:review",
    ):
        _, output = _hook(
            "privacy_guard.py",
            _commit_payload(command),
            "pre-tool-use",
            project=repo,
        )
        assert _decision(output) == "deny"


def test_a_push_checks_what_a_merge_commit_added(repo):
    """Content added while committing a merge is part of what is pushed."""
    _git(repo, "switch", "-q", "-c", "side")
    (repo / "docs" / "side.md").write_text("Side work.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "side")
    _git(repo, "switch", "-q", "feature")
    _git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    (repo / "docs" / "merge.md").write_text(f"Server at {PUBLIC_IP}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "merge side")
    _, output = _hook("privacy_guard.py", _commit_payload("git push -u origin feature"), "pre-tool-use", project=repo)
    assert _decision(output) == "deny"
    assert PUBLIC_IP in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_push_of_something_unreadable_asks(repo):
    """Commits the guard cannot read are the user's call, not a silent pass."""
    _, output = _hook("privacy_guard.py", _commit_payload("git push origin no-such-branch"),
                      "pre-tool-use", project=repo)
    assert _decision(output) == "ask"


# --- changelog_docs_gate.py -------------------------------------------------------

_CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n### Added\n\n### Fixed\n\n## [1.0.0]\n\n### Added\n\n- Old.\n"


@pytest.fixture
def changelog_repo(repo: Path) -> Path:
    (repo / "CHANGELOG.md").write_text(_CHANGELOG)
    _git(repo, "add", "CHANGELOG.md")
    _git(repo, "commit", "-q", "-m", "changelog")
    return repo


def _add_entry(repo: Path, section: str, text: str) -> None:
    content = (repo / "CHANGELOG.md").read_text().replace(f"### {section}\n\n", f"### {section}\n\n- {text}\n", 1)
    (repo / "CHANGELOG.md").write_text(content)


def test_a_new_added_entry_stops_the_commit_once(changelog_repo):
    """The first commit is sent to /check-changelog-docs, the retry goes through."""
    _add_entry(changelog_repo, "Added", "A new --foo flag.")
    _git(changelog_repo, "add", "CHANGELOG.md")
    _, output = _hook("changelog_docs_gate.py", _commit_payload("git commit -m foo"), project=changelog_repo)
    assert _decision(output) == "deny"
    assert "/check-changelog-docs" in output["hookSpecificOutput"]["permissionDecisionReason"]
    assert _hook("changelog_docs_gate.py", _commit_payload("git commit -m foo"), project=changelog_repo) == (0, {})
    _add_entry(changelog_repo, "Added", "Another flag.")
    _git(changelog_repo, "add", "CHANGELOG.md")
    _, output = _hook("changelog_docs_gate.py", _commit_payload("git commit -m bar"), project=changelog_repo)
    assert _decision(output) == "deny"


def test_a_commit_that_stages_the_changelog_itself_is_checked(changelog_repo):
    """`git commit -am` judges the working tree, not the empty index."""
    _add_entry(changelog_repo, "Added", "A new --foo flag.")
    _, output = _hook("changelog_docs_gate.py", _commit_payload("git commit -am foo"), project=changelog_repo)
    assert _decision(output) == "deny"


@pytest.mark.parametrize("command", ["git commit -m fix", "git status", "ls"])
def test_other_sections_and_commands_pass_the_changelog_gate(changelog_repo, command):
    """Fixed entries, released sections and non-commits are left alone."""
    _add_entry(changelog_repo, "Fixed", "A bug.")
    (changelog_repo / "CHANGELOG.md").write_text(
        (changelog_repo / "CHANGELOG.md").read_text() + "- Late note under 1.0.0.\n")
    _git(changelog_repo, "add", "CHANGELOG.md")
    assert _hook("changelog_docs_gate.py", _commit_payload(command), project=changelog_repo) == (0, {})


# --- .claude/settings.json -------------------------------------------------------

def test_every_blocking_guard_fails_closed_and_the_privacy_guard_is_filtered():
    """A guard that cannot run refuses the call; the privacy guard only runs for git and gh."""
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    handlers = [h for group in settings["hooks"]["PreToolUse"] for h in group["hooks"]
                if "changelog_docs_gate.py" not in h["command"]]  # a reminder, deliberately fail-open
    assert handlers and all("exit 2" in h["command"] for h in handlers)
    privacy = [h for h in handlers if "privacy_guard.py" in h["command"]]
    assert sorted(h["if"] for h in privacy) == ["Bash(gh *)", "Bash(git *)"]
    stop = [h["command"] for group in settings["hooks"]["Stop"] for h in group["hooks"]]
    assert any("stop_checks.py" in c for c in stop) and any("privacy_guard.py\" stop" in c for c in stop)


@pytest.mark.parametrize("exit_code, expected_exit, says_broken", [
    (0, 0, False),   # allowed: nothing to add
    (2, 2, False),   # a deliberate refusal speaks for itself
    (1, 2, True),    # an uncaught exception fails closed
    (127, 2, True),  # an interpreter that is not there fails closed
])
def test_a_guard_wrapper_reports_a_broken_guard_but_not_a_refusal(tmp_path, exit_code, expected_exit, says_broken):
    """
    A refusal used to arrive with "could not run" appended, because the
    wrapper's ``||`` also fired on the deliberate exit 2 - and an agent read
    that as a broken hook rather than a decision.
    """
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    handlers = [h for group in settings["hooks"]["PreToolUse"] for h in group["hooks"]
                if "changelog_docs_gate.py" not in h["command"]]
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for name in ("guard_bash.py", "guard_branch.py", "guard_edit.py", "privacy_guard.py"):
        (hooks / name).write_text(f"import sys\nprint('stub refusal', file=sys.stderr)\nsys.exit({exit_code})\n")
    for handler in handlers:
        result = subprocess.run(  # nosec B603 B607 - the repository's own hook wrapper
            ["sh", "-c", handler["command"]],
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
            input="{}", capture_output=True, text=True, check=False,
        )
        assert result.returncode == expected_exit, handler["command"]
        assert ("could not run" in result.stderr) is says_broken, result.stderr
