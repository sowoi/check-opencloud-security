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
from webapp.catalog import HEADER_IDS, check_catalogue


def test_every_check_declares_a_known_category():
    """A hardening flag or extra check with no category vanishes from the
    catalogue page rather than erroring, so this is the test that has to
    catch it instead."""
    for entry in all_checks():
        assert entry.category, entry.id
        assert entry.category in CATEGORIES, entry.id


def test_every_header_note_is_categorised_as_a_header():
    for name in HEADER_IDS:
        assert describe_hardening(name).category == "headers"


def test_the_catalogue_page_lists_every_known_check_exactly_once():
    """
    The page is derived, not maintained - this is what proves it stays that
    way as the scanner grows.

    Every id ``all_checks()`` and ``HEADER_IDS`` know about must appear on the
    catalogue exactly once: a category left blank would silently drop an
    entry, and a category listed twice would silently duplicate one.
    """
    expected = {entry.id for entry in all_checks()} | set(HEADER_IDS)

    listed: list[str] = []
    for category in check_catalogue():
        assert category.checks, category.id
        for check in category.checks:
            listed.append(check.id)

    assert set(listed) == expected
    assert len(listed) == len(expected)


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
