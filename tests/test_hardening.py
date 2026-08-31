"""
The catalogue pipeline: nothing added to the scanner may go uncatalogued.

``webapp.catalog.check_catalogue`` and the ``/catalogue`` page never keep a
list of their own - they read ``opencloud_local_scan.all_checks`` and
``webapp.catalog.HEADER_IDS`` directly, so a new hardening flag or extra
check reaches the public catalogue the moment it is added to
``opencloud_local_scan/hardening.py``, with no second list to update and no
release to wait for. The one thing that pipeline depends on is every entry
naming a real category - an entry left at the default empty string is
grouped under a category nothing iterates over and silently disappears from
the page instead of failing loudly. These tests are what makes that failure
loud instead of silent.
"""

from __future__ import annotations

from opencloud_local_scan import CATEGORIES, all_checks, describe_hardening
from opencloud_local_scan.hardening import ADVISORY_CHECKS
from opencloud_local_scan.scanner import ADVISORY_CHECK_IDS
from webapp.catalog import (
    ADVISORY_HEADER_IDS,
    HEADER_IDS,
    allowed_waivers,
    check_catalogue,
)


def test_every_check_declares_a_known_category():
    """A hardening flag or extra check with no category vanishes from the
    catalogue page rather than erroring, so this is the test that has to
    catch it instead."""
    for entry in all_checks():
        assert entry.category, entry.id
        assert entry.category in CATEGORIES, entry.id


def test_every_header_note_is_categorised_as_a_header():
    for name in (*HEADER_IDS, *ADVISORY_HEADER_IDS):
        assert describe_hardening(name).category == "headers"


def test_the_catalogue_page_lists_every_known_check_exactly_once():
    """
    The page is derived, not maintained - this is what proves it stays that
    way as the scanner grows.

    Every id ``all_checks()``, ``HEADER_IDS`` and ``ADVISORY_HEADER_IDS`` know
    about must appear on the catalogue exactly once: a category left blank
    would silently drop an entry, and a category listed twice would silently
    duplicate one.
    """
    expected = (
        {entry.id for entry in all_checks()} | set(HEADER_IDS) | set(ADVISORY_HEADER_IDS)
    )

    listed: list[str] = []
    for category in check_catalogue():
        assert category.checks, category.id
        for check in category.checks:
            listed.append(check.id)

    assert set(listed) == expected
    assert len(listed) == len(expected)


def test_an_advisory_header_is_explained_but_never_offered_as_a_waiver():
    """
    Nothing alerts on an advisory header, so there is nothing to waive - and
    offering the tick box anyway would tell a visitor the opposite, that this
    is a finding serious enough to need accepting. It still has to be
    explained, which is the half that makes the distinction honest rather than
    a way of hiding three checks.
    """
    waivable = allowed_waivers()
    catalogued = {
        check.id for category in check_catalogue() for check in category.checks
    }

    for name in ADVISORY_HEADER_IDS:
        assert name in catalogued, name
        assert name not in waivable, name

    # The negative case: an ordinary header is offered, so the assertion above
    # is about these three headers and not about waivers being empty.
    for name in HEADER_IDS:
        assert name in waivable, name


def test_an_advisory_check_is_explained_but_never_offered_as_a_waiver():
    """
    The same bargain as the advisory headers, for what is not a header. It
    reaches the catalogue through ``all_checks`` like every other entry, and
    it must not reach the waiver list: the tick box would tell a visitor this
    is a finding serious enough to need accepting, when nothing alerts on it
    at all. See ADR 0034.
    """
    waivable = allowed_waivers()
    catalogued = {
        check.id for category in check_catalogue() for check in category.checks
    }

    for name in ADVISORY_CHECKS:
        assert name in catalogued, name
        assert name not in waivable, name

    # The negative case: an ordinary hardening flag is offered, so this is
    # about the advisory checks and not about waivers being empty.
    assert "basicAuthDisabled" in waivable


def test_the_measured_advisory_checks_are_all_catalogued():
    """
    The scanner writes ``setup.advisoryChecks`` from its own tuple and the
    catalogue explains them from its own dict. Nothing links the two at
    runtime, so a check added to one and not the other would be reported
    without an explanation, or explained without ever being measured.
    """
    assert set(ADVISORY_CHECK_IDS) == set(ADVISORY_CHECKS)


def test_a_family_member_finding_inherits_its_family_category():
    """
    ``exposed:/config/opencloud.yaml`` is not in the catalogue - only the
    family entry ``exposed`` is, since the subject is an open-ended path -
    but a result page showing that finding must still be able to badge and
    link it correctly, which means the category has to travel from the
    family to every member ``describe_hardening`` builds for it on demand.
    """
    family = next(entry for entry in all_checks() if entry.id == "exposed")
    member = describe_hardening("exposed:/config/opencloud.yaml")

    assert family.category == "exposure"
    assert member.category == family.category
