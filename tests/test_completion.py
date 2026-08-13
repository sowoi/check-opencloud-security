"""
Shell completion: the optional extra, and what it must never break.

Completion is a convenience, but it sits in the startup path of a monitoring
plugin, so the load-bearing property is that a host without ``argcomplete``
runs exactly as before. The completions themselves are exercised through the
real argcomplete protocol rather than by calling the completer directly - a
completer that is defined but never wired onto the argument would still pass
the direct call.
"""

from __future__ import annotations

import builtins
import os
import pathlib
import subprocess
import sys

import pytest

from opencloud_local_scan import completion
from opencloud_local_scan.hardening import HARDENINGS

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "check_opencloud_security.py"

IFS = "\013"


def complete(tmp_path, line: str, argv: list[str]) -> list[str]:
    """Ask a command for its completions the way a shell does."""
    out = tmp_path / "completions"
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT),
        "_ARGCOMPLETE": "1",
        "_ARGCOMPLETE_IFS": IFS,
        "_ARGCOMPLETE_SHELL": "bash",
        # argcomplete answers on file descriptor 8, not stdout; this redirects
        # it to somewhere a test can read.
        "_ARGCOMPLETE_STDOUT_FILENAME": str(out),
        "COMP_LINE": line,
        "COMP_POINT": str(len(line)),
        "COMP_TYPE": "9",
    }
    subprocess.run(
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        env=environment,
        check=False,
    )
    if not out.exists():
        return []
    return [word for word in out.read_text().split(IFS) if word]


def test_argcomplete_is_reported_as_available_when_it_is_installed():
    """The rest of this file is meaningless if the extra is missing."""
    assert completion.is_available() is True


def test_completion_is_skipped_when_argcomplete_is_not_installed(monkeypatch):
    """A monitoring host installs the plugin without the extra and must still run."""
    real_import = builtins.__import__

    def refuse_argcomplete(name, *args, **kwargs):
        if name == "argcomplete":
            raise ImportError("No module named 'argcomplete'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_argcomplete)

    assert completion.is_available() is False
    assert completion.enable(_a_parser()) is False


def _a_parser():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--ignore-hardening", action="append")
    return parser


def test_enable_attaches_the_completer_to_ignore_hardening():
    """Without the wiring the completer exists but is never consulted."""
    parser = _a_parser()

    assert completion.enable(parser) is True

    completers = {
        action.dest: getattr(action, "completer", None)
        for action in parser._actions
    }
    assert completers["ignore_hardening"] is completion.hardening_completer
    assert completers["help"] is None


def test_the_hardening_completer_offers_the_real_catalogue():
    """A hardcoded list would go stale the moment a check is added."""
    suggestions = completion.hardening_completer("")

    assert set(suggestions) == set(HARDENINGS)
    assert suggestions == sorted(suggestions)


def test_the_hardening_completer_narrows_to_the_prefix():
    """Suggesting everything regardless of what was typed is not completion."""
    everything = completion.hardening_completer("")
    narrowed = completion.hardening_completer("publicLink")

    assert narrowed, "the catalogue should contain publicLink* identifiers"
    assert set(narrowed) < set(everything)
    assert all(name.startswith("publicLink") for name in narrowed)
    assert completion.hardening_completer("zzz-no-such-check") == []


@pytest.mark.skipif(
    not completion.is_available(), reason="argcomplete is not installed"
)
def test_the_plugin_completes_hardening_identifiers_for_a_real_shell(tmp_path):
    """End to end over the argcomplete protocol: the wiring is what can break."""
    words = complete(
        tmp_path,
        "check-opencloud-security --ignore-hardening publicLink",
        [str(PLUGIN)],
    )

    assert words
    assert all(word.startswith("publicLink") for word in words)
    assert set(words) <= set(HARDENINGS)


@pytest.mark.skipif(
    not completion.is_available(), reason="argcomplete is not installed"
)
def test_the_plugin_completes_the_values_of_upgrade_self(tmp_path):
    """The two values are the whole replacement for --dry-run; they must be findable."""
    words = complete(
        tmp_path, "check-opencloud-security --upgrade-self ", [str(PLUGIN)]
    )

    assert "run" in words
    assert "check" in words


@pytest.mark.skipif(
    not completion.is_available(), reason="argcomplete is not installed"
)
def test_the_scanner_cli_completes_too(tmp_path):
    """Both entry points are declared as completable, so both are tested."""
    words = complete(
        tmp_path,
        "check-opencloud-scanner ",
        ["-m", "opencloud_local_scan.cli"],
    )

    assert "scan" in words
    assert "serve" in words


def test_both_entry_points_are_marked_for_global_completion():
    """
    activate-global-python-argcomplete only registers a script that says so in
    its first kilobyte, so the marker's position is part of the feature.
    """
    for script in (PLUGIN, REPO_ROOT / "opencloud_local_scan" / "cli.py"):
        head = script.read_bytes()[:1024]
        assert b"PYTHON_ARGCOMPLETE_OK" in head, script


def test_completion_does_not_run_outside_a_completion_request(tmp_path):
    """
    A stray completion write would corrupt the plugin's output, which a
    monitoring system parses.
    """
    assert os.environ.get("_ARGCOMPLETE") is None

    result = subprocess.run(
        [sys.executable, str(PLUGIN), "--version"],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT)},
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("check_opencloud_security")
    assert IFS not in result.stdout
    assert result.stderr == ""
