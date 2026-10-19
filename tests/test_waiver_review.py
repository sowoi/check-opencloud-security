"""
`check-opencloud-scanner review-waivers`: which waivers need a person.

A waiver goes wrong quietly, in one of five ways: its deadline passes, its
deadline is about to, it covers nothing, it covers what another record
already covers, or it never had a deadline at all. The review names each one
with a suggestion, and changes nothing - so the one thing tested beyond the
five is that the configuration is byte-for-byte what it was.

Every review is decided against a clock the test supplies.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from opencloud_local_scan.cli import main
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import ScannerSettings, scan
from opencloud_local_scan.waivers import (
    EXPIRED,
    EXPIRING,
    OVERLAPPING,
    PERMANENT,
    UNUSED,
    Waiver,
    failing_checks,
    next_expiry,
    parse_waiver,
    review,
    scan_clock,
)
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
AT = "2026-09-24T12:00:00Z"


def _temporary(pattern: str, days: float, reason: str = "Accepted for now") -> Waiver:
    return Waiver(pattern, NOW + timedelta(days=days), reason)


def _result(*failing: str, hardcoded: tuple[str, ...] = ()) -> dict:
    """A minimal result document in which exactly these checks fail."""
    return {
        "rating": 4,
        "extraChecks": [{"id": check, "passed": False} for check in failing]
        + [{"id": "corsOriginRestricted", "passed": True}],
        "hardenings": {name: False for name in hardcoded} | {"basicAuthDisabled": True},
        "setup": {"https": {"enforced": True}, "headers": {"X-Frame-Options": True}},
    }


def _kinds(outcome) -> dict[str, list[str]]:
    kinds: dict[str, list[str]] = {}
    for item in outcome.items:
        kinds.setdefault(item.kind, []).append(item.waiver.pattern)
    return kinds


# ------------------------------------------------------------ the library


def test_a_clean_configuration_reports_nothing():
    outcome = review(
        [_temporary("exposed:/.env", 60)], NOW, result=_result("exposed:/.env")
    )

    assert outcome.items == ()


def test_an_expired_waiver_is_reported_with_the_check_that_alerts_again():
    outcome = review(
        [_temporary("exposed:/.env", -3)], NOW, result=_result("exposed:/.env")
    )

    (item,) = outcome.items
    assert item.kind == EXPIRED
    assert item.related == ("exposed:/.env",)
    assert "3 days ago" in item.detail
    assert "alerts again" in item.detail


def test_an_expiry_carried_by_a_broader_waiver_says_nothing_alerted():
    """The case the scanner only logs at debug level: nobody re-decided it."""
    outcome = review(
        [Waiver("exposed:*"), _temporary("exposed:/.env", -1)],
        NOW,
        result=_result("exposed:/.env"),
    )

    (expired,) = outcome.of_kind(EXPIRED)
    assert "passed without an alert" in expired.detail


def test_the_expiry_boundary_is_the_scanners():
    """At the stroke of the deadline the waiver is over, as in a scan."""
    waiver = _temporary("exposed:/.env", 0)

    assert _kinds(review([waiver], NOW))[EXPIRED] == ["exposed:/.env"]
    assert EXPIRED not in _kinds(review([waiver], NOW - timedelta(seconds=1)))


def test_expiring_uses_the_plugins_window():
    waivers = [_temporary("exposed:/.env", 5), _temporary("debugPort:9205", 30)]

    within = review(waivers, NOW, expiring_within_days=7)
    off = review(waivers, NOW, expiring_within_days=0)

    assert _kinds(within)[EXPIRING] == ["exposed:/.env"]
    assert EXPIRING not in _kinds(off)


def test_a_waiver_matching_no_failing_check_is_unused():
    outcome = review([_temporary("debugPort:*", 60)], NOW, result=_result("exposed:/.env"))

    (item,) = outcome.items
    assert item.kind == UNUSED
    assert "silences the check the day it starts failing" in item.suggestion


def test_a_waiver_for_a_hardcoded_flag_is_unused():
    """Such a flag never alerts, so waiving it suppresses nothing at all."""
    outcome = review(
        [_temporary("publicLinkExpirationEnforced", 60)],
        NOW,
        result=_result(hardcoded=("publicLinkExpirationEnforced",)),
    )

    (item,) = outcome.items
    assert item.kind == UNUSED
    assert "hardcodes" in item.detail


def test_without_a_result_only_an_unknown_identifier_is_unused():
    outcome = review(
        [_temporary("debugPrt:*", 60), _temporary("debugPort:*", 60)], NOW
    )

    (item,) = outcome.items
    assert item.kind == UNUSED
    assert item.waiver.pattern == "debugPrt:*"
    assert "debugPort" in item.suggestion
    assert outcome.evidence is False


def test_a_permanent_wildcard_masks_a_temporary_deadline():
    outcome = review(
        [Waiver("*"), _temporary("exposed:/.env", 60)],
        NOW,
        result=_result("exposed:/.env"),
    )

    (overlap,) = outcome.of_kind(OVERLAPPING)
    assert overlap.waiver.pattern == "exposed:/.env"
    assert overlap.related == ("*",)
    assert "deadline will pass without anything alerting" in overlap.detail


def test_a_duplicate_is_reported_once():
    outcome = review(
        [Waiver("debugPort:*"), Waiver("DEBUGPORT:*")], NOW, result=_result("debugPort:9205")
    )

    (overlap,) = outcome.of_kind(OVERLAPPING)
    assert overlap.waiver.pattern == "DEBUGPORT:*"
    assert "Duplicates" in overlap.detail


def test_two_patterns_that_only_intersect_are_found_from_the_evidence():
    """Neither pattern contains the other; the scan shows a check both match."""
    waivers = [_temporary("*Proxy*", 60), _temporary("reverse*", 60)]

    with_evidence = review(waivers, NOW, result=_result("reverseProxyDetected"))
    without = review(waivers, NOW)

    (overlap,) = with_evidence.of_kind(OVERLAPPING)
    assert "reverseProxyDetected" in overlap.detail
    assert OVERLAPPING not in _kinds(without)


def test_an_expired_record_is_not_also_reported_as_overlapping():
    outcome = review(
        [Waiver("*"), _temporary("exposed:/.env", -1)], NOW, result=_result("exposed:/.env")
    )

    assert "exposed:/.env" not in _kinds(outcome).get(OVERLAPPING, [])


def test_every_permanent_waiver_gets_a_temporary_replacement_to_copy():
    outcome = review([Waiver("exposed:*")], NOW, result=_result("exposed:/.env"))

    (item,) = outcome.items
    assert item.kind == PERMANENT
    suggested = item.suggestion.split("'")[1]
    replacement = parse_waiver(suggested.replace("<why this is accepted>", "A reason"))
    assert replacement.pattern == "exposed:*"
    assert replacement.expires_at == datetime(2026, 12, 23, tzinfo=UTC)


def test_a_blanket_permanent_waiver_is_called_out():
    (item,) = review([Waiver("*")], NOW).of_kind(PERMANENT)

    assert "every check" in item.detail


def test_items_are_ordered_by_kind():
    outcome = review(
        [Waiver("debugPrt:*"), _temporary("exposed:/.env", -1)], NOW
    )

    assert [item.kind for item in outcome.items] == [EXPIRED, UNUSED, PERMANENT]


def test_the_next_expiry_agrees_with_the_plugins_warning(tmp_path):
    """The review and --waiver-warning must never disagree about a deadline."""
    # The scan judges its waivers by the real clock, so a fixed NOW would let
    # the ten-day waiver expire in the scan once the calendar passes it.
    now = scan_clock()
    waivers = (
        Waiver("exposed:/.env", now + timedelta(days=10), "Accepted for now"),
        Waiver("reverseProxyDetected", now + timedelta(days=20), "Accepted for now"),
    )
    settings = ScannerSettings(
        scheme="http",
        timeout=3,
        check_debug_ports=False,
        include_bundled_db=True,
        waivers=waivers,
    )
    with FakeOpenCloud(InstanceBehaviour(exposed_paths={"/.env"})) as instance:
        document = scan(
            instance.host, settings=settings, release_settings=ReleaseSettings(mode="off")
        )

    outcome = review(waivers, now, result=document)

    assert {"exposed:/.env", "reverseProxyDetected"} <= set(failing_checks(document))
    assert outcome.upcoming == next_expiry(document["waivers"])
    assert outcome.upcoming is not None
    assert outcome.upcoming.checks == ("exposed:/.env",)


# ------------------------------------------------------------ the command


@pytest.fixture
def config_file(tmp_path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "scanner": {
                    "ignore_hardenings": ["debugPrt:*"],
                    "temporary_waivers": [
                        "exposed:/.env|2026-09-01T00:00:00Z|Proxy rule pending"
                    ],
                },
                "waiver_warning": 30,
            }
        ),
        encoding="utf-8",
    )
    return path


def _review(capsys, *args: str) -> tuple[int, str]:
    code = main(list(args))
    return code, capsys.readouterr().out


def test_the_command_reads_the_configuration_and_changes_nothing(capsys, config_file):
    before = config_file.read_bytes()

    code, printed = _review(capsys, "-c", str(config_file), "review-waivers", "--at", AT)

    assert code == 1
    assert "Expired (1):" in printed
    assert "Unused (1):" in printed
    assert "Permanent (1):" in printed
    assert "Nothing was changed" in printed
    assert config_file.read_bytes() == before


def test_the_expiring_window_defaults_to_the_waiver_warning_setting(capsys, config_file):
    config_file.write_text(
        json.dumps(
            {
                "scanner": {
                    "temporary_waivers": ["exposed:/.env|2026-10-20T00:00:00Z|Soon"]
                },
                "waiver_warning": 30,
            }
        ),
        encoding="utf-8",
    )

    code, printed = _review(capsys, "-c", str(config_file), "review-waivers", "--at", AT)
    _, narrower = _review(
        capsys,
        "-c",
        str(config_file),
        "review-waivers",
        "--at",
        AT,
        "--expiring-within",
        "7",
    )

    assert code == 1
    assert "Expiring soon (1):" in printed
    assert "Expiring soon" not in narrower


def test_flags_replace_the_configured_waivers(capsys, config_file):
    code, printed = _review(
        capsys,
        "-c",
        str(config_file),
        "review-waivers",
        "--at",
        AT,
        "--waive-until",
        "debugPort:*|2027-01-01T00:00:00Z|Firewall change scheduled",
        "--ignore-hardening",
        "",
    )

    assert code == 0
    assert "Nothing to clean up." in printed


def test_json_output_and_exit_zero(capsys, config_file, tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps(_result("exposed:/.env")), encoding="utf-8")

    code, printed = _review(
        capsys,
        "-c",
        str(config_file),
        "review-waivers",
        "--at",
        AT,
        "--result",
        str(result),
        "--format",
        "json",
        "--exit-zero",
    )
    document = json.loads(printed)

    assert code == 0
    assert document["evidence"] is True
    assert document["counts"] == {
        "expired": 1,
        "expiring": 0,
        "unused": 1,
        "overlapping": 0,
        "permanent": 1,
    }
    expired = next(item for item in document["items"] if item["kind"] == "expired")
    assert expired["related"] == ["exposed:/.env"]
    assert expired["expiresAt"] == "2026-09-01T00:00:00+00:00"


def test_no_waivers_is_a_clean_review(capsys):
    code, printed = _review(capsys, "review-waivers", "--at", AT)

    assert code == 0
    assert "No waivers are configured" in printed


@pytest.mark.parametrize(
    "args",
    [
        ("--waive-until", "debugPort:*"),
        ("--at", "2026-09-24"),
        ("--result", "/nonexistent/result.json"),
        ("--expiring-within", "-1"),
    ],
)
def test_a_bad_input_is_a_usage_error(capsys, args):
    code, _ = _review(capsys, "review-waivers", *args)

    assert code == 2
