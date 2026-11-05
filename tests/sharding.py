"""
Run one slice of the suite: ``pytest --shard 2/4``.

The suite takes about fifteen minutes on a CI runner and almost all of it is
pytest, so CI runs it as several jobs side by side. No single test dominates
(the slowest is a few seconds out of eight minutes), so a test's slice is a
stable hash of its node id rather than a weights file that would go stale:
across thousands of tests the slices come out even, and a new test lands in
one without anyone deciding where.

The hash is SHA-256, not ``hash()``: string hashing is randomised per process,
and every slice must agree on where each test belongs. That still assumes a
node id is the same in every process (it is today, under any
``PYTHONHASHSEED``); parametrising over a ``set`` with positional ids would
break it quietly, a test running twice and another never. So each CI slice
writes what it ran (``--shard-list``), and the coverage job checks the lists
add up to the whole suite exactly once:

    python -m tests.sharding verify ALL.txt SLICE1.txt SLICE2.txt ...

where ``ALL.txt`` is ``pytest --collect-only --shard 1/1 --shard-list ALL.txt``.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

_SHARD = re.compile(r"(\d+)/(\d+)")


def parse_shard(value: str) -> tuple[int, int]:
    """``"2/4"`` -> ``(2, 4)``; the index counts from one."""
    match = _SHARD.fullmatch(value.strip())
    if not match:
        raise pytest.UsageError(f"--shard expects INDEX/COUNT such as 2/4, not {value!r}")
    index, count = int(match.group(1)), int(match.group(2))
    if not 1 <= index <= count:
        raise pytest.UsageError(f"--shard {value}: the index must lie between 1 and {count}")
    return index, count


def shard_of(nodeid: str, count: int) -> int:
    """The slice, from one, that a test belongs to."""
    digest = hashlib.sha256(nodeid.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count + 1


def addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("sharding")
    group.addoption("--shard", default=None, metavar="INDEX/COUNT",
                    help="run only the INDEX-th of COUNT slices of the suite")
    group.addoption("--shard-list", default=None, metavar="FILE",
                    help="write the node ids this slice runs to FILE, one per line")


def select(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = config.getoption("--shard")
    if value is None:
        return
    index, count = parse_shard(value)
    kept = [item for item in items if shard_of(item.nodeid, count) == index]
    dropped = [item for item in items if shard_of(item.nodeid, count) != index]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = kept

    listing = config.getoption("--shard-list")
    if listing:
        Path(listing).write_text("".join(f"{item.nodeid}\n" for item in kept), encoding="utf-8")


def verify(whole: Path, slices: list[Path]) -> list[str]:
    """What is wrong with the slices as a partition of the whole suite; empty if nothing."""
    expected = {nodeid for nodeid in whole.read_text(encoding="utf-8").splitlines() if nodeid}
    ran = Counter(nodeid for part in slices for nodeid in part.read_text(encoding="utf-8").splitlines() if nodeid)
    problems = [f"ran {times} times: {nodeid}" for nodeid, times in sorted(ran.items()) if times > 1]
    problems += [f"in no slice: {nodeid}" for nodeid in sorted(expected - ran.keys())]
    problems += [f"not in the suite: {nodeid}" for nodeid in sorted(ran.keys() - expected)]
    return problems


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "verify":
        sys.exit("usage: python -m tests.sharding verify ALL.txt SLICE.txt [SLICE.txt ...]")
    found = verify(Path(sys.argv[2]), [Path(arg) for arg in sys.argv[3:]])
    for problem in found:
        print(problem)
    print(f"{len(found)} problem(s) across {len(sys.argv) - 3} slices" if found else "the slices partition the suite")
    sys.exit(1 if found else 0)
