"""
Tests that the version has exactly one source.

``pyproject.toml`` is what a release is cut from, so the plugin and the library
must report whatever it says. They have drifted before, and a plugin that
reports the wrong version sends an operator looking at the wrong changelog.
"""

from __future__ import annotations

import re
from pathlib import Path

import check_opencloud_security as plugin
import opencloud_local_scan

REPO_ROOT = Path(__file__).resolve().parent.parent


def pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no version"
    return match.group(1)


def test_the_library_reports_the_version_from_pyproject():
    """The library is where the number is derived, so it has to match the file."""
    assert opencloud_local_scan.__version__ == pyproject_version()


def test_the_plugin_reports_the_same_version_as_the_library():
    """The plugin must not carry a second copy that can fall behind."""
    assert plugin.__version__ == opencloud_local_scan.__version__


def test_no_module_hardcodes_a_version_literal():
    """A literal here is exactly how the two numbers drifted apart before."""
    sources = [
        REPO_ROOT / "check_opencloud_security.py",
        REPO_ROOT / "opencloud_local_scan" / "__init__.py",
    ]
    for source in sources:
        text = source.read_text(encoding="utf-8")
        assert not re.search(
            r'^__version__\s*=\s*["\']\d', text, re.MULTILINE
        ), f"{source.name} assigns __version__ a literal instead of deriving it"


def test_the_version_is_read_from_the_project_and_not_an_enclosing_one(tmp_path):
    """A parent directory's pyproject.toml must not be able to hijack the version."""
    from opencloud_local_scan import _version_from_pyproject

    assert _version_from_pyproject() == pyproject_version()


def test_the_reported_version_looks_like_a_release(capsys):
    """A fallback of '0.0.0' would mean the detection silently failed."""
    assert opencloud_local_scan.__version__ != "0.0.0"
    assert re.match(r"^\d+\.\d+\.\d+", opencloud_local_scan.__version__)
