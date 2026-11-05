#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write: keep hands off generated files.

Generated files are a function of their sources; a hand edit is overwritten
or fails a CI --check. The hook denies such edits and names the generator.
A version change asks the user first, because the version is theirs to set
and a bump on main publishes to PyPI. Inline styles and scripts in templates
are denied because the CSP has no 'unsafe-inline'.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys

_GENERATED = (
    ("RELEASE.md",
     "RELEASE.md is written by the release workflow from [Unreleased] (ADR 0048) - never edit it."),
    ("frontend/templates/docs/*",
     "Generated - edit README.md / docs/ and run `python scripts/build_frontend_documentation.py`."),
    ("frontend/templates/admin-docs/*",
     "Generated - edit the source documentation and run `python scripts/build_frontend_documentation.py`."),
    ("frontend/static/search-index*.json",
     "Generated - run `python scripts/build_search_index.py` (last, after the documentation)."),
    ("opencloud_local_scan/data/release_schedule.json",
     "Generated - run `uv run python scripts/update_release_schedule.py`."),
    ("opencloud_local_scan/data/vulnerabilities.json",
     "Generated - run `uv run python scripts/update_vulnerability_db.py`."),
)

_BLOCKS = {
    "README.md": ("<!-- release-schedule:start -->", "<!-- release-schedule:end -->",
                  ("The release schedule table is generated - run "
                   "`uv run python scripts/update_release_schedule.py`.")),
    "docker/setup-wizard.py": ("# --- embedded-blueprints:start ---", "# --- embedded-blueprints:end ---",
                               ("The embedded blueprints are generated - edit authentik/blueprints/ and run "
                                "`python scripts/embed_wizard_blueprints.py`.")),
}

_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]*)"', re.MULTILINE)
_VERSION_LITERAL = re.compile(r'^\s*__version__\s*=\s*["\']', re.MULTILINE)
_INLINE_MARKUP = re.compile(r'\sstyle\s*=|<style\b|\son[a-z]+\s*=\s*["\']|<script(?![^>]*\bsrc=)[^>]*>', re.IGNORECASE)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _spans(text: str, needle: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    while needle:
        index = text.find(needle, start)
        if index < 0:
            break
        spans.append((index, index + len(needle)))
        start = index + 1
    return spans


def _block(text: str, start_marker: str, end_marker: str) -> tuple[int, int] | None:
    start, end = text.find(start_marker), text.find(end_marker)
    if start < 0 or end < 0:
        return None
    return start, end + len(end_marker)


def _touches_block(rel: str, tool: str, tool_input: dict, current: str) -> str | None:
    if rel not in _BLOCKS:
        return None
    start_marker, end_marker, reason = _BLOCKS[rel]
    block = _block(current, start_marker, end_marker)
    if tool == "Write":
        new_block = _block(tool_input.get("content") or "", start_marker, end_marker)
        old_text = current[block[0]:block[1]] if block else None
        new_text = (tool_input.get("content") or "")[new_block[0]:new_block[1]] if new_block else None
        return reason if old_text != new_text else None
    new_string = tool_input.get("new_string") or ""
    if start_marker in new_string or end_marker in new_string:
        return reason
    if block is None:
        return None
    for lo, hi in _spans(current, tool_input.get("old_string") or ""):
        if lo < block[1] and hi > block[0]:
            return reason
    return None


_PRIVACY_FILES = (".claude/hooks/privacy_allowlist.txt", ".claude/hooks/privacy_guard.py")


def path_rule(rel: str, whole_file: bool = False) -> tuple[str, str] | None:
    """The decision that depends on the path alone.

    ``whole_file`` is for writes that cannot be inspected line by line (a
    Bash redirect, ``sed -i``, ``cp``): those also ask before touching
    pyproject.toml, where only the version line is the user's.
    """
    for pattern, reason in _GENERATED:
        if fnmatch.fnmatch(rel, pattern):
            return "deny", reason
    if rel in _PRIVACY_FILES:
        return "ask", ("This changes what the privacy guard lets into commits (real hosts, personal data). "
                       "Only the user approves that - confirm they asked for this exact change.")
    if whole_file and rel == "pyproject.toml":
        return "ask", ("A shell command is about to rewrite pyproject.toml, which holds the version only the "
                       "user may change - confirm this was asked for, or use the Edit tool.")
    return None


def decide(rel: str, tool: str, tool_input: dict, current: str) -> tuple[str, str] | None:
    """Return (decision, reason) for an edit to ``rel``, or None to allow it."""
    rule = path_rule(rel)
    if rule:
        return rule

    reason = _touches_block(rel, tool, tool_input, current)
    if reason:
        return "deny", reason

    if tool == "Write":
        new_text = tool_input.get("content") or ""
        old_fragment = current
    else:
        new_text = tool_input.get("new_string") or ""
        old_fragment = tool_input.get("old_string") or ""

    if rel == "pyproject.toml":
        before = _VERSION_LINE.findall(old_fragment if tool != "Write" else current)
        after = _VERSION_LINE.findall(new_text)
        if before != after:
            return "ask", ("This changes the project version. Only the user bumps the version "
                           "(a bump on main publishes to PyPI) - confirm this was asked for. "
                           "If it was: run `uv lock`, then `uv run python scripts/build_frontend_documentation.py "
                           "&& uv run python scripts/build_search_index.py`, and commit all of it in one push - "
                           "the Releases page and the search indexes render the version.")

    if rel.endswith(".py") and _VERSION_LITERAL.search(new_text) and not _VERSION_LITERAL.search(old_fragment):
        return "ask", ("A literal __version__ was added. The version lives only in pyproject.toml; "
                       "opencloud_local_scan.__version__ derives it.")

    if rel.startswith("frontend/templates/") and rel.endswith(".html"):
        added = set(_INLINE_MARKUP.findall(new_text)) - set(_INLINE_MARKUP.findall(old_fragment))
        if added:
            return "deny", ("The CSP has no 'unsafe-inline': no style=, <style>, on*= handlers or inline "
                            "<script> in templates. Use app.css utility classes or [data-...] rules. "
                            "Found: " + ", ".join(sorted(a.strip() for a in added)))
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        print("unreadable hook input - refusing (fail closed)", file=sys.stderr)
        return 2
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(root)).replace(os.sep, "/")
    if not path or rel.startswith(".."):
        return 0
    result = decide(rel, tool, tool_input, _read(path))
    if result:
        decision, reason = result
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": "Project guard (.claude/hooks/guard_edit.py): " + reason,
            }
        }, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
