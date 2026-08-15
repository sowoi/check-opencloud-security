"""
The public web application around the built-in scanner.

This package is *not* part of the PyPI distribution. The wheel and the sdist
carry the plugin and ``opencloud_local_scan`` only, so that a monitoring host
installing ``check-opencloud-security`` gets a small dependency-free check and
nothing else. The web application is shipped as the GitHub release tarball
built by ``scripts/build_web_bundle.py``.

The layering of the project holds here too: this package *serves*, it does not
*measure* and it does not *judge*. Every verdict in the result document comes
from ``opencloud_local_scan.scan``; the grade letters come from the same 0-5
scale the plugin uses. Nothing in here re-implements a check.
"""

from __future__ import annotations

__all__ = ["__version__"]

try:  # pragma: no cover - trivial and environment dependent
    from opencloud_local_scan import __version__
except ImportError:  # pragma: no cover - the scanner is always present in practice
    __version__ = "0.0.0"
