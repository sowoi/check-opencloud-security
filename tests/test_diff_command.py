"""
`check-opencloud-scanner diff`: what changed between two archived scans.

The comparison itself belongs to the baseline and is tested there. What is
tested here is the part an operator sees at three in the morning: that two
files produce an honest answer, that two *different instances* do not quietly
produce one, and that the exit code says whether things got worse.

Expectations are derived from real scans of the fake instance rather than
written out, so a change to what the scanner reports moves this test with it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencloud_local_scan.cli import main
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import ScannerSettings, scan
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

SETTINGS = ScannerSettings(
    scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
)
NO_UPDATES = ReleaseSettings(mode="off")


def _scan(behaviour: InstanceBehaviour) -> dict:
    with FakeOpenCloud(behaviour) as instance:
        return scan(instance.host, settings=SETTINGS, release_settings=NO_UPDATES)


def _write(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def exposed() -> dict:
    """An instance publishing its configuration file to the internet."""
    return _scan(InstanceBehaviour(exposed_paths={"/.env"}))


@pytest.fixture(scope="module")
def repaired() -> dict:
    """The same instance after somebody fixed the reverse proxy."""
    return _scan(InstanceBehaviour())


def test_a_resolved_finding_is_reported_as_resolved(tmp_path, capsys, exposed, repaired):
    """The whole point: showing that the fix landed, not merely that it is quiet."""
    before = _write(tmp_path / "before.json", exposed)
    after = _write(tmp_path / "after.json", repaired)

    code = main(["diff", str(before), str(after)])
    printed = capsys.readouterr().out

    assert code == 0, "an instance that improved must not fail a pipeline"
    assert "- exposed:/.env" in printed
    assert "+ exposed:/.env" not in printed


def test_a_new_finding_is_reported_and_fails(tmp_path, capsys, exposed, repaired):
    """The same two documents the other way round: this is a regression."""
    before = _write(tmp_path / "before.json", repaired)
    after = _write(tmp_path / "after.json", exposed)

    code = main(["diff", str(before), str(after)])
    printed = capsys.readouterr().out

    assert code == 1
    assert "+ exposed:/.env" in printed
    assert "New since last run" in printed


def test_the_exit_code_can_be_suppressed_for_a_reporting_step(
    tmp_path, capsys, exposed, repaired
):
    """A pipeline that files the diff somewhere still wants to reach the next step."""
    before = _write(tmp_path / "before.json", repaired)
    after = _write(tmp_path / "after.json", exposed)

    code = main(["diff", str(before), str(after), "--exit-zero"])

    assert code == 0
    assert "+ exposed:/.env" in capsys.readouterr().out


def test_the_scan_times_are_the_documents_own_not_the_time_of_the_diff(
    tmp_path, capsys, exposed, repaired
):
    """
    Half the answer is *when*.

    The baseline stamps a snapshot with the moment it was taken, which is
    right while monitoring and wrong here - these two documents were written
    weeks ago, and printing today's date twice would say nothing.
    """
    before = _write(tmp_path / "before.json", exposed)
    after = _write(tmp_path / "after.json", repaired)

    main(["diff", str(before), str(after)])
    printed = capsys.readouterr().out

    assert exposed["scannedAt"]["date"] in printed
    assert repaired["scannedAt"]["date"] in printed


def test_two_different_instances_are_refused_unless_that_was_the_point(
    tmp_path, capsys, repaired
):
    """
    'Did the fix work' is a question about one instance.

    Comparing a staging host against production produces a confident, entirely
    meaningless list of changes, so it has to be asked for explicitly.
    """
    before = _write(tmp_path / "before.json", repaired)
    elsewhere = {**repaired, "domain": "other.example.com"}
    after = _write(tmp_path / "after.json", elsewhere)

    assert main(["diff", str(before), str(after)]) == 2

    assert main(["diff", str(before), str(after), "--allow-different-hosts"]) in (0, 1)
    assert "other.example.com" in capsys.readouterr().out


def test_a_failed_scan_is_refused_rather_than_compared(tmp_path, repaired):
    """
    A document recording a failure has no findings - only silence.

    Diffing it against a real scan would report every finding as resolved,
    which is the most dangerous wrong answer this command could give.
    """
    before = _write(tmp_path / "before.json", repaired)
    after = tmp_path / "after.json"
    after.write_text(
        json.dumps({"host": "cloud.example.com", "error": "connection refused"}),
        encoding="utf-8",
    )

    assert main(["diff", str(before), str(after)]) == 2


def test_a_file_holding_several_hosts_is_refused(tmp_path, exposed, repaired):
    """Picking the first of four hosts would compare the wrong instance confidently."""
    both = tmp_path / "both.json"
    both.write_text(json.dumps([exposed, repaired]), encoding="utf-8")
    single = _write(tmp_path / "single.json", repaired)

    assert main(["diff", str(both), str(single)]) == 2


def test_a_single_host_array_is_read_as_the_document_it_holds(
    tmp_path, capsys, exposed, repaired
):
    """`scan host` prints an object, `scan a b` prints an array - both get archived."""
    before = tmp_path / "before.json"
    before.write_text(json.dumps([exposed]), encoding="utf-8")
    after = _write(tmp_path / "after.json", repaired)

    assert main(["diff", str(before), str(after)]) == 0
    assert "- exposed:/.env" in capsys.readouterr().out


def test_a_missing_or_unreadable_file_is_an_error_not_an_empty_diff(tmp_path, repaired):
    """A typo in a path must not look like an instance with nothing wrong with it."""
    existing = _write(tmp_path / "before.json", repaired)

    assert main(["diff", str(existing), str(tmp_path / "absent.json")]) == 2

    rubbish = tmp_path / "rubbish.json"
    rubbish.write_text("not json at all", encoding="utf-8")
    assert main(["diff", str(existing), str(rubbish)]) == 2


@pytest.mark.parametrize("format_name", ("json", "slack", "markdown"))
def test_every_rendering_produces_the_same_verdict(
    tmp_path, capsys, exposed, repaired, format_name
):
    """The format decides what it looks like, never what it says."""
    before = _write(tmp_path / "before.json", repaired)
    after = _write(tmp_path / "after.json", exposed)

    code = main(["diff", str(before), str(after), "--format", format_name])
    printed = capsys.readouterr().out

    assert code == 1
    assert "exposed:/.env" in printed
    if format_name in {"json", "slack"}:
        json.loads(printed)


def test_the_json_rendering_carries_the_structured_comparison(
    tmp_path, capsys, exposed, repaired
):
    """What a script reads: the same document the webhook's baseline_diff carries."""
    before = _write(tmp_path / "before.json", repaired)
    after = _write(tmp_path / "after.json", exposed)

    main(["diff", str(before), str(after), "--format", "json"])
    document = json.loads(capsys.readouterr().out)

    assert document["regressed"] is True
    assert document["first_run"] is False
    assert document["summary"]
    assert any("exposed:/.env" in change["change"] for change in document["changes"])
