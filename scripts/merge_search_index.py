#!/usr/bin/env python3
"""
Resolve a merge conflict in a search index by rebuilding it.

Registered as a git merge driver by ``scripts/setup_git_merge_drivers.py``;
``.gitattributes`` points the four ``frontend/static/search-index*.json`` files
at it. Run once per conflicted path, with the path git wants the result written
to and the path the file has in the tree.

**Why these files conflict at all.** They are generated - a pure function of the
templates, the catalogues and the version - and they are also checked in,
because the frontend serves them and `tests/test_webapp_search.py` reads them.
So any two branches that touch a template, a string or `pyproject.toml` produce
different bytes on the same lines, and git has no way to know that neither side
was written by a person. Every one of those conflicts is noise, and resolving
one by hand means choosing between two stale answers.

**Why rebuilding is the right resolution and not merely the convenient one.**
The index is authoritative exactly once, in the release workflow: `publish-
pypi.yml` regenerates all four, and `test_only_the_release_workflow_refreshes
_the_index` forbids any other workflow from doing so, precisely so that search
does not drift between published versions. A rebuild here therefore cannot
disagree with anything the project promises - it produces what the next release
would produce anyway.

Falls back to leaving git's own result in place if the rebuild fails. A merge
driver that cannot finish must not also destroy the conflict it was asked to
settle: the developer still has the markers, and a message saying why.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404 - fixed argv built here, never a shell string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_search_index.py"


def rebuild() -> None:
    """Regenerate every index from the tree as it now stands."""
    subprocess.run(  # nosec B603 - argv built above, no shell
        [sys.executable, str(BUILDER)],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
    )


def main() -> int:
    """Rebuild the indexes and hand git the one it asked about."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", help="where git wants the merged file (%%A)")
    parser.add_argument("path", help="the file's path in the tree (%%P)")
    args = parser.parse_args()

    source = ROOT / args.path
    try:
        rebuild()
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        print(
            f"Could not rebuild {args.path}: {exc}\n"
            f"{detail.decode('utf-8', 'replace').strip()}\n"
            "Leaving the conflict in place. Resolve it with:\n"
            "    python scripts/build_search_index.py && git add "
            "frontend/static/search-index*.json",
            file=sys.stderr,
        )
        return 1

    if not source.exists():  # pragma: no cover - the builder writes all four
        print(f"{args.path} was not rebuilt; leaving the conflict.", file=sys.stderr)
        return 1

    shutil.copyfile(source, args.result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
