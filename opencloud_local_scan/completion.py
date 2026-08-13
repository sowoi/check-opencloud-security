"""
Shell completion, when ``argcomplete`` is available.

Completion is an optional extra rather than a dependency: a monitoring host
runs this from cron or an Icinga command definition and has no use for it, and
the plugin has to keep working on a machine where it is not installed.

``argcomplete.autocomplete()`` only does anything when the shell invokes the
program with ``_ARGCOMPLETE`` set; in a normal run it returns immediately.
Values declared with argparse's ``choices=`` are completed for free, so the
only completer defined here is for the one argument whose useful values live
in a catalogue rather than in the parser.
"""

from __future__ import annotations

import argparse
from typing import Any

__all__ = ["enable", "hardening_completer", "is_available"]


def is_available() -> bool:
    """Whether argcomplete can be imported."""
    try:
        import argcomplete  # noqa: F401
    except ImportError:
        return False
    return True


def hardening_completer(prefix: str = "", **_: Any) -> list[str]:
    """
    Suggest the identifiers ``--ignore-hardening`` accepts.

    Waiving a finding means typing an identifier exactly, and a typo produces
    a waiver that silently matches nothing. Completing them from the catalogue
    is the difference between that and an accurate waiver.
    """
    from .hardening import HARDENINGS

    return sorted(name for name in HARDENINGS if name.startswith(prefix))


def enable(parser: argparse.ArgumentParser) -> bool:
    """
    Wire completion onto ``parser``. Returns False when argcomplete is absent.

    Safe to call unconditionally: outside a completion request this costs one
    import and nothing else.
    """
    try:
        import argcomplete
    except ImportError:
        return False

    for action in parser._actions:
        if "--ignore-hardening" in action.option_strings:
            action.completer = hardening_completer  # type: ignore[attr-defined]

    argcomplete.autocomplete(parser)
    return True
