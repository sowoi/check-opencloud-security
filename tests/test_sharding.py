"""
`pytest --shard INDEX/COUNT` runs one slice of the suite; CI runs them side by side.

A slicing that drops a test is worse than a slow suite: the test goes green
by never running. So the assignment must be stable across processes, every
test must land in exactly one slice, and the check CI runs on the slices'
lists must catch it when that stops being true.
"""

from __future__ import annotations

import subprocess  # nosec B404 - runs this repository's own pytest with fixed argv
import sys
from pathlib import Path

import pytest

from tests import sharding

ROOT = Path(__file__).resolve().parent.parent
NODEIDS = [f"tests/test_m{m}.py::test_{t}[case {t}]" for m in range(40) for t in range(100)]


@pytest.mark.parametrize(("value", "expected"), [("1/4", (1, 4)), ("4/4", (4, 4)), (" 1/1 ", (1, 1))])
def test_a_slice_is_named_by_index_and_count(value: str, expected: tuple[int, int]):
    assert sharding.parse_shard(value) == expected


@pytest.mark.parametrize("value", ["0/4", "5/4", "4", "1-4", "a/b", "1/0"])
def test_a_slice_outside_the_count_is_refused(value: str):
    """`--shard 0/4` would silently run nothing; a typo must stop the run instead."""
    with pytest.raises(pytest.UsageError):
        sharding.parse_shard(value)


def test_every_test_lands_in_exactly_one_slice_and_the_slices_are_even():
    """Four slices of four thousand ids: none lost, none twice, none far from a quarter."""
    slices = {index: [n for n in NODEIDS if sharding.shard_of(n, 4) == index] for index in range(1, 5)}

    assert sorted(n for part in slices.values() for n in part) == sorted(NODEIDS)
    assert all(abs(len(part) - len(NODEIDS) / 4) < len(NODEIDS) * 0.05 for part in slices.values())


def test_the_slice_does_not_depend_on_the_process_hash_seed():
    """`hash()` would differ per process and split the suite differently in every job."""
    script = "from tests import sharding; print(sharding.shard_of('tests/test_a.py::test_b', 7))"
    answers = {
        subprocess.run(  # nosec B603 - fixed argv
            [sys.executable, "-c", script], cwd=ROOT, check=True, capture_output=True, text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "", "PYTHONPATH": str(ROOT)},
        ).stdout.strip()
        for seed in ("0", "1", "12345")
    }

    assert answers == {str(sharding.shard_of("tests/test_a.py::test_b", 7))}


def _write(path: Path, nodeids: list[str]) -> Path:
    path.write_text("".join(f"{n}\n" for n in nodeids), encoding="utf-8")
    return path


def test_slices_that_partition_the_suite_pass_the_check(tmp_path: Path):
    whole = _write(tmp_path / "whole.txt", NODEIDS[:9])
    parts = [_write(tmp_path / f"{i}.txt", NODEIDS[i:9:3]) for i in range(3)]

    assert sharding.verify(whole, parts) == []


def test_a_lost_a_doubled_and_a_foreign_test_are_each_reported(tmp_path: Path):
    """The three ways a node id that differs between processes shows up."""
    whole = _write(tmp_path / "whole.txt", ["a::x", "a::y", "a::with space"])
    parts = [_write(tmp_path / "1.txt", ["a::x", "a::with space"]), _write(tmp_path / "2.txt", ["a::x", "a::z"])]

    assert sharding.verify(whole, parts) == [
        "ran 2 times: a::x",
        "in no slice: a::y",
        "not in the suite: a::z",
    ]


def test_the_option_runs_only_its_slice_and_writes_what_it_ran(tmp_path: Path):
    """End to end on this very module: the listed ids are the slice, and two slices are the module."""
    listed = []
    for index in (1, 2):
        listing = tmp_path / f"{index}.txt"
        subprocess.run(  # nosec B603 - this repository's pytest, fixed argv
            [sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "no:cacheprovider",
             "--shard", f"{index}/2", "--shard-list", str(listing), "tests/test_sharding.py"],
            cwd=ROOT, check=True, capture_output=True,
        )
        listed.append(listing.read_text(encoding="utf-8").splitlines())

    assert all(sharding.shard_of(n, 2) == i for i, part in enumerate(listed, 1) for n in part)
    assert not set(listed[0]) & set(listed[1])
    assert "tests/test_sharding.py::test_the_option_runs_only_its_slice_and_writes_what_it_ran" in listed[0] + listed[1]
