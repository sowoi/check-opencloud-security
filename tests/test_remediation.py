"""
What the remediation planner promises, and what it must never promise.

The plan is advice with a number attached, which makes a wrong number worse
than no plan: an operator who fixes what they were told to fix and does not
get the grade they were told they would get has been misled by a tool that
was meant to save them the analysis. Every test here protects one way the
plan could quietly become wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_opencloud import FakeOpenCloud, InstanceBehaviour

from opencloud_local_scan import ScannerSettings, scan
from opencloud_local_scan.remediation import plan


def _document(
    *,
    rating: int,
    base_rating: int,
    caps: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    """A result document with just enough in it to be planned against."""
    document: dict[str, Any] = {
        "rating": rating,
        "version": "7.1.0",
        "ratingExplanation": {
            "rating": rating,
            "base": {"rating": base_rating, "reason": "a reason"},
            "caps": caps,
        },
    }
    document.update(extra)
    return document


def _cap(check: str, severity: str, cap: int) -> dict[str, Any]:
    return {"check": check, "severity": severity, "cap": cap, "detail": ""}


def test_a_clean_instance_is_told_there_is_nothing_to_do():
    """A plan that invents work on a perfect instance is a plan nobody trusts."""
    result = plan(_document(rating=5, base_rating=5, caps=[]))

    assert result["steps"] == []
    assert result["achievableRating"] == 5
    assert "Nothing to fix" in result["summary"]


def test_each_step_predicts_the_rating_that_step_actually_produces():
    """The predicted grade is the promise; a wrong one is worse than none."""
    result = plan(
        _document(
            rating=2,
            base_rating=5,
            caps=[
                _cap("directoryListing", "critical", 2),
                _cap("basicAuthDisabled", "medium", 4),
            ],
        )
    )

    first, second = result["steps"]
    assert first["id"] == "directoryListing"
    assert first["ratingAfter"] == 4
    assert second["ratingAfter"] == 5
    # The negative half: nothing claims a gain it cannot deliver, and the
    # last step is not silently credited with the whole climb.
    assert first["ratingGain"] == 2
    assert second["ratingGain"] == 1


def test_findings_of_one_severity_do_not_each_promise_the_same_gain():
    """Two mediums share one cap: fixing one of them changes nothing."""
    result = plan(
        _document(
            rating=4,
            base_rating=5,
            caps=[
                _cap("basicAuthDisabled", "medium", 4),
                _cap("maintenanceMode", "medium", 4),
            ],
        )
    )

    first, second = result["steps"]
    assert first["ratingGain"] == 0
    assert second["ratingGain"] == 1
    # Still listed, because a step that gains nothing on its own is the step
    # without which the next one gains nothing either.
    assert first["ratingAfter"] == 4


def test_the_update_is_planned_before_the_findings_it_would_unblock():
    """Fixing findings cannot lift a rating above what the version allows."""
    result = plan(
        _document(
            rating=3,
            base_rating=4,
            caps=[_cap("tlsCertificate", "medium", 4)],
            updates={"availableVersion": "7.4.0", "track": "production"},
        )
    )

    kinds = [step["kind"] for step in result["steps"]]
    assert "upgrade" in kinds
    assert result["achievableRating"] == 5
    # The negative half: the update is not offered as a fix for a finding
    # that is capping below it. A high finding caps at 3, so an update from
    # base 4 is worth nothing until that finding is gone.
    blocked = plan(
        _document(
            rating=3,
            base_rating=4,
            caps=[_cap("tlsTrusted", "high", 3)],
            updates={"availableVersion": "7.4.0"},
        )
    )
    assert blocked["steps"][0]["id"] == "tlsTrusted"
    assert blocked["steps"][1]["kind"] == "upgrade"


def test_an_end_of_life_instance_is_planned_against_its_open_findings():
    """An F short-circuits the rating; the plan still has to be honest."""
    result = plan(
        {
            "rating": 0,
            "EOL": True,
            "version": "1.0.0",
            "latestVersionInBranch": "7.4.0",
            "extraChecks": [
                {
                    "id": "tlsTrusted",
                    "severity": "high",
                    "passed": False,
                    "detail": "self-signed",
                }
            ],
            "ratingExplanation": {
                "rating": 0,
                "base": {"rating": 0, "reason": "out of support"},
                "caps": [],
            },
        }
    )

    assert result["steps"][0]["kind"] == "upgrade"
    # The negative half: the update alone does not promise the top grade
    # while a high finding is still open.
    assert result["steps"][0]["ratingAfter"] == 3
    assert result["achievableRating"] == 5


def test_the_update_step_never_names_a_version_the_scan_did_not_report():
    """A release number nobody published is an operator sent looking for it."""
    result = plan(
        _document(rating=4, base_rating=4, caps=[], updates={"available": True})
    )

    step = result["steps"][0]
    assert step["targetVersion"] == ""
    assert "7." not in step["action"]
    assert "could not name one" in step["action"]


def test_a_waived_finding_is_listed_but_never_planned_as_a_fix():
    """A waiver hides an alert, not the evidence - and never earns a grade."""
    result = plan(
        _document(
            rating=5,
            base_rating=5,
            caps=[],
            extraChecks=[
                {"id": "tlsTrusted", "passed": False, "ignored": True},
                {"id": "directoryListing", "passed": True},
            ],
        )
    )

    assert result["waived"] == ["tlsTrusted"]
    assert [step["id"] for step in result["steps"]] == []


def test_every_step_carries_the_wording_an_operator_can_act_on():
    """An identifier without a fix is the research task the plan replaces."""
    result = plan(
        _document(
            rating=2,
            base_rating=5,
            caps=[_cap("exposed:/config/opencloud.yaml", "critical", 2)],
        )
    )

    step = result["steps"][0]
    assert step["title"] and step["action"] and step["reference"]
    # The negative half: the catalogue really answered, rather than falling
    # back to the placeholder it uses for an identifier it does not know.
    assert "No description is available" not in step["title"]
    assert "See the scan result" not in step["action"]


def test_a_real_scan_carries_a_plan_that_matches_its_own_rating():
    """Derived from the document it ships in, so the two cannot disagree."""
    behaviour = InstanceBehaviour(
        exposed_paths={"/config/opencloud.yaml": "secret: x"},
        basic_auth=True,
        directory_listing=True,
    )
    with FakeOpenCloud(behaviour) as instance:
        result = scan(
            instance.host,
            ScannerSettings(scheme="http", check_debug_ports=False),
        )

    carried = result["remediationPlan"]
    assert carried["currentRating"] == result["rating"]
    assert carried["achievableRating"] >= result["rating"]
    planned = {step["id"] for step in carried["steps"]}
    capping = {
        cap["check"] for cap in result["ratingExplanation"]["caps"]
    }
    assert planned == capping
    # The negative half: a check that passed is never offered as a fix.
    passed = {
        entry["id"] for entry in result["extraChecks"] if entry.get("passed")
    }
    assert not planned & passed


def test_every_check_a_real_scan_can_fail_has_a_fix_to_offer():
    """An identifier the catalogue cannot explain is an unanswered alert."""
    from opencloud_local_scan import describe_hardening

    behaviour = InstanceBehaviour(
        exposed_paths={"/config/opencloud.yaml": "secret: x"},
        basic_auth=True,
        directory_listing=True,
        unprotected=True,
        debug_endpoints=True,
        disclose_server=True,
    )
    with FakeOpenCloud(behaviour) as instance:
        result = scan(
            instance.host,
            ScannerSettings(scheme="http", check_debug_ports=False),
        )

    failed = [
        str(entry["id"])
        for entry in result["extraChecks"]
        if not entry.get("passed")
    ]
    assert failed, "the fake instance is meant to fail several checks"
    for identifier in failed:
        note = describe_hardening(identifier)
        assert note.remediation != "See the scan result for the raw finding.", (
            f"{identifier} has no fix in the catalogue"
        )
        assert note.title != identifier, f"{identifier} has no title"
