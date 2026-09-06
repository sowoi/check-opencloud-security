#!/usr/bin/env python3
"""
Register this repository's merge drivers in the local clone.

Run once after cloning::

    python scripts/setup_git_merge_drivers.py

``.gitattributes`` is committed and says *which* files get a driver;
``.git/config`` is not committed and says what the driver *is*. Git deliberately
splits it that way - a driver is an arbitrary command, and a repository that
could hand one to everybody who clones it would be a repository that runs code
on clone. So this cannot be automatic, and a clone that has not run it simply
gets the ordinary conflict it would have got anyway.

Idempotent: running it again rewrites the same values.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - fixed argv built here, never a shell string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: name -> (description, command). ``%A`` is the file git wants written, ``%P``
#: the path it has in the tree; git substitutes both before running this.
DRIVERS = {
    "search-index": (
        "rebuild the generated search index instead of merging it",
        f"{sys.executable} scripts/merge_search_index.py %A %P",
    ),
}


def configure(git: str, name: str, description: str, command: str) -> None:
    """Write one driver into this clone's own config.

    Both keys or neither: git answers a named driver with no command by
    failing the merge outright rather than falling back to a normal one, so a
    half-written section is worse than an absent one.
    """
    for key, value in (("driver", command), ("name", description)):
        subprocess.run(  # nosec B603 - argv built above, no shell
            [git, "config", f"merge.{name}.{key}", value],
            cwd=str(ROOT),
            check=True,
        )


def main() -> int:
    """Register every driver and say what happened."""
    git = shutil.which("git")
    if git is None:
        print("git is not on PATH, so there is nothing to configure.", file=sys.stderr)
        return 1
    for name, (description, command) in DRIVERS.items():
        configure(git, name, description, command)
        print(f"merge.{name}: {description}")
    print(
        "\nRegistered in .git/config. Conflicts in the files .gitattributes "
        "points at these drivers now resolve themselves."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
