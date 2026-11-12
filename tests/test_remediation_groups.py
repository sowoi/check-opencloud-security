"""
Grouped remediation: every open finding placed where its fix is made.

The grouping is only useful if it is complete and honest - a finding filed
under the wrong system sends somebody to edit the wrong file, and a change
credited with a grade it cannot deliver is the same broken promise the
ordered plan guards against.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_opencloud import FakeOpenCloud, InstanceBehaviour

import check_opencloud_security as check
from opencloud_local_scan import ScannerSettings, scan
from opencloud_local_scan.hardening import all_checks, header_names
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.remediation import plan
from opencloud_local_scan.remediation_groups import (
    CHECK_TARGETS,
    REVERSE_PROXY,
    SHARED_CHANGES,
    TARGETS,
    target_of,
)


def _document(
    *, rating: int, base_rating: int, caps: list[dict[str, Any]], **extra: Any
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


def _cap(check_id: str, severity: str, cap: int) -> dict[str, Any]:
    return {"check": check_id, "severity": severity, "cap": cap, "detail": ""}


def _changes(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every change in a plan's groups, by id."""
    return {
        change["id"]: change
        for group in result["groups"]
        for change in group["changes"]
    }


def test_every_catalogued_check_has_a_place_to_be_fixed():
    """A new check without a target would silently be filed under OpenCloud."""
    missing = [entry.id for entry in all_checks() if entry.id not in CHECK_TARGETS]

    assert missing == []
    assert set(CHECK_TARGETS.values()) <= set(TARGETS)
    assert all(target_of(name) == REVERSE_PROXY for name in header_names())


def test_a_shared_change_only_groups_checks_fixed_in_the_same_place():
    """One edit cannot span two systems; if it did, it would be two edits."""
    for change in SHARED_CHANGES:
        for member in change.members:
            assert target_of(member) == change.target, (change.id, member)


def test_a_real_scan_groups_missing_headers_into_one_proxy_change():
    """Two missing headers are one header block, and a separate OpenCloud setting is not."""
    behaviour = InstanceBehaviour(basic_auth=True)
    behaviour.headers.pop("X-Content-Type-Options")
    behaviour.headers.pop("Referrer-Policy")
    with FakeOpenCloud(behaviour) as instance:
        result = scan(
            instance.host,
            settings=ScannerSettings(
                scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=False
            ),
            release_settings=ReleaseSettings(mode="off"),
        )
    grouped = result["remediationPlan"]
    changes = _changes(grouped)

    headers = changes["securityHeaders"]
    assert {"X-Content-Type-Options", "Referrer-Policy"} <= set(headers["findings"])
    assert headers["resolvesSeveral"] is True
    assert "securityHeaders" not in _changes(
        {"groups": [g for g in grouped["groups"] if g["target"] != REVERSE_PROXY]}
    )

    basic = changes["basicAuthDisabled"]
    assert basic["findings"] == ["basicAuthDisabled"]
    assert basic["resolvesSeveral"] is False
    assert basic["steps"], "a capping finding points back at its plan step"
    assert basic["ratingAfter"] > grouped["currentRating"]
    assert "several findings at once" in grouped["groupSummary"]


def test_members_of_one_family_are_one_change():
    """Three exposed paths are one proxy fix, not three."""
    result = plan(
        _document(
            rating=2,
            base_rating=5,
            caps=[
                _cap("exposed:/config/opencloud.yaml", "critical", 2),
                _cap("exposed:/.env", "critical", 2),
                _cap("directoryListing", "critical", 2),
                _cap("basicAuthDisabled", "medium", 4),
            ],
        )
    )
    changes = _changes(result)

    static = changes["staticFiles"]
    assert sorted(static["findings"]) == [
        "directoryListing",
        "exposed:/.env",
        "exposed:/config/opencloud.yaml",
    ]
    assert len(static["steps"]) == 3
    # Fixing the proxy alone lifts the critical cap but not the medium one.
    assert static["ratingAfter"] == 4
    assert changes["basicAuthDisabled"]["ratingAfter"] == 2


def test_the_update_resolves_every_matching_advisory_at_once():
    """One update closes all the advisories; listing them apart hides that."""
    result = plan(
        _document(
            rating=2,
            base_rating=2,
            caps=[],
            updates={"availableVersion": "7.2.0", "track": "production"},
            vulnerabilities=[
                {"id": "GHSA-aaaa-bbbb-cccc", "severity": "high"},
                {"id": "GHSA-dddd-eeee-ffff", "severity": "medium"},
            ],
        )
    )
    upgrade = _changes(result)["upgrade"]

    assert upgrade["findings"] == [
        "versionCurrent",
        "advisory:GHSA-aaaa-bbbb-cccc",
        "advisory:GHSA-dddd-eeee-ffff",
    ]
    assert upgrade["ratingAfter"] == 5
    assert "7.2.0" in upgrade["action"]


def test_an_update_is_not_credited_with_a_cap_it_leaves_standing():
    """The grade beside a change is the rating function replayed, not a hope."""
    result = plan(
        _document(
            rating=2,
            base_rating=3,
            caps=[_cap("directoryListing", "critical", 2)],
            updates={"availableVersion": "7.2.0"},
        )
    )
    changes = _changes(result)

    assert changes["upgrade"]["ratingAfter"] == 2
    assert changes["staticFiles"]["ratingAfter"] == 3


def test_waived_and_hardcoded_findings_are_not_offered_as_changes():
    """A decision already made and a flag nobody can set are not work to do."""
    result = plan(
        _document(
            rating=4,
            base_rating=5,
            caps=[_cap("publicLinkExpirationEnforced", "medium", 4)],
            ignored=["basicAuthDisabled"],
            hardenings={"basicAuthDisabled": False, "passwordPolicyEnforced": False},
        )
    )
    findings = {name for change in _changes(result).values() for name in change["findings"]}

    assert "publicLinkExpirationEnforced" not in findings
    assert "basicAuthDisabled" not in findings
    assert "passwordPolicyEnforced" in findings


def test_a_clean_instance_has_no_groups():
    """Nothing open means nothing to group, and no sentence claiming otherwise."""
    result = plan(_document(rating=5, base_rating=5, caps=[]))

    assert result["groups"] == []
    assert result["groupSummary"] == ""


def test_the_plugin_explanation_lists_the_groups_with_letters():
    """--debug is where an operator reads the plan; the groups belong beside it."""
    document = _document(
        rating=2,
        base_rating=5,
        caps=[_cap("exposed:/.env", "critical", 2), _cap("directoryListing", "critical", 2)],
    )
    document["remediationPlan"] = plan(document)

    lines = check._remediation_group_lines(document)

    assert "--- Changes grouped by where they are made ---" in lines
    assert any(line.startswith("Reverse proxy: 2 finding(s)") for line in lines)
    assert any(
        "resolves 2:" in line and "exposed:/.env" in line and "directoryListing" in line
        for line in lines
    )
    assert check._remediation_group_lines({"remediationPlan": plan(
        _document(rating=5, base_rating=5, caps=[])
    )}) == []
