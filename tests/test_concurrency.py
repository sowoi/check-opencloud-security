"""
Tests for scanning an instance with several probes in flight at once.

Concurrency is a pure speed setting: the same instance must produce the same
result document whether it was scanned with one worker or with many, and a
single worker must genuinely stay single-threaded.
"""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest

from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    ScannerSettings,
    _run_all,
    scan,
)
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

SETTINGS = ScannerSettings(
    scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
)
NO_UPDATES = ReleaseSettings(mode="off")

# An instance with plenty to find, so that the comparison covers findings
# that actually failed rather than a uniform list of passes.
LOUD_INSTANCE = InstanceBehaviour(
    exposed_paths={"/opencloud.yaml", "/.env", "/.git/config"},
    basic_auth=True,
    unprotected=True,
    debug_endpoints=True,
    webfinger_version=True,
    disclose_server="nginx/1.24.0",
)


def _scan(behaviour: InstanceBehaviour, concurrency: int) -> dict:
    with FakeOpenCloud(behaviour) as instance:
        return scan(
            instance.host,
            settings=replace(SETTINGS, concurrency=concurrency),
            release_settings=NO_UPDATES,
        )


def test_scanning_without_multithreading_is_the_default():
    """Nobody should get parallel requests against their instance unasked."""
    assert DEFAULT_CONCURRENCY == 1
    assert ScannerSettings().concurrency == 1
    assert ScannerSettings().workers == 1


@pytest.mark.parametrize("concurrency", [2, 8])
def test_a_parallel_scan_finds_exactly_what_a_sequential_scan_finds(concurrency):
    """Speeding a scan up must not change a single verdict it reaches."""
    sequential = _scan(LOUD_INSTANCE, 1)
    parallel = _scan(LOUD_INSTANCE, concurrency)

    assert parallel["extraChecks"] == sequential["extraChecks"]
    assert parallel["hardenings"] == sequential["hardenings"]
    assert parallel["setup"] == sequential["setup"]
    assert parallel["rating"] == sequential["rating"]

    # Guard against a vacuous comparison: this instance must actually fail
    # things, otherwise the test would still pass with concurrency ignored.
    assert any(not check["passed"] for check in sequential["extraChecks"])


def test_findings_keep_their_order_no_matter_who_answers_first():
    """
    The result document is compared and diffed by operators, so a scan must
    not reshuffle its checks depending on which probe won the race.
    """
    order = [check["id"] for check in _scan(LOUD_INSTANCE, 1)["extraChecks"]]
    for _ in range(3):
        assert [check["id"] for check in _scan(LOUD_INSTANCE, 8)["extraChecks"]] == order


def test_a_single_worker_never_leaves_the_calling_thread():
    """Concurrency 1 means no thread pool at all, not a pool of size one."""
    caller = threading.get_ident()
    settings = ScannerSettings(concurrency=1)
    threads = _run_all(settings, [threading.get_ident for _ in range(4)])
    assert threads == [caller] * 4


def test_more_workers_actually_spread_the_work_over_threads():
    """Without this, the option would be an expensive no-op."""
    settings = ScannerSettings(concurrency=4)
    barrier = threading.Barrier(4, timeout=10)

    def task() -> int:
        # Only completes if four probes really run at the same time.
        barrier.wait()
        return threading.get_ident()

    threads = _run_all(settings, [task for _ in range(4)])
    assert len(set(threads)) == 4
    assert threading.get_ident() not in threads


def test_concurrency_is_clamped_to_something_sane():
    """A typo such as 10000 must not try to open ten thousand sockets."""
    assert ScannerSettings(concurrency=MAX_CONCURRENCY * 10).workers == MAX_CONCURRENCY
    assert ScannerSettings(concurrency=0).workers == 1
    assert ScannerSettings(concurrency=-5).workers == 1


def test_the_pool_is_no_larger_than_the_work_it_is_given():
    """Five spare threads for two probes is waste, not speed."""
    settings = ScannerSettings(concurrency=16)
    threads = _run_all(settings, [threading.get_ident for _ in range(2)])
    assert len(set(threads)) <= 2
