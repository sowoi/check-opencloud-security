"""
The comparison page: two uuids a reader holds, and what moved between them.

Every expectation here is derived from two real scans of
``tests/fake_opencloud.py`` - the same instance, scanned twice with a finding
fixed in between - rather than from a hardcoded list of identifiers, which
would go stale the moment a check is added.

The page decides nothing. What it must never do is decide something
*differently* from the two surfaces that answer the same question: the
``compare_scans`` tool an agent calls and the ``--baseline`` arithmetic an
operator's monitoring runs. One test below holds the page and the tool to the
same answer for the same pair.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    MEMORY_URL,
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.catalog import finding_id
from webapp.redis_backend import memory_backend
from webapp.store import ScanStore
from webapp.tasks import run_scan
from webapp.workflows import compare_documents

EARLIER = "b6f2c0c5-1c4b-4f4e-9a3b-0d3f8b7c1a20"
LATER = "c7a3d1d6-2d5c-4a5f-8b4c-1e4f9c8d2b31"
UNKNOWN = "d8b4e2e7-3e6d-4b60-9c5d-2f50ad9e3c42"


def _scan(store: ScanStore, configured, identifier: str, target: str) -> None:
    """Store one finished scan of a running fake instance."""
    asyncio.run(
        store.create(
            identifier,
            target=target,
            ignore_hardenings=(),
            output_format="dashboard",
        )
    )
    asyncio.run(run_scan({"web_settings": configured, "store": store}, identifier))


@pytest.fixture
def improved_pair():
    """
    The same instance twice: an exposed deployment file, and then not.

    One host for both scans, because two fake instances listen on two ports
    and would compare as two different targets - which is a case of its own,
    tested separately.
    """
    configured = settings(allow_private_targets=True, verify_tls=False, scan_timeout=5)
    store = ScanStore(backend=memory_backend(MEMORY_URL), ttl=configured.result_ttl)
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    with FakeOpenCloud(behaviour) as instance:
        target = f"http://{instance.host}"
        _scan(store, configured, EARLIER, target)
        # The fix, between the two scans.
        instance.behaviour.exposed_paths = set()
        _scan(store, configured, LATER, target)

    earlier = asyncio.run(store.get(EARLIER))
    later = asyncio.run(store.get(LATER))
    assert earlier is not None and earlier.result is not None
    assert later is not None and later.result is not None
    return earlier.result, later.result


def test_the_page_offers_a_form_before_any_uuid_is_given():
    """A reader arrives here from a link, not with two uuids already typed."""
    page = client().get("/compare")

    assert page.status_code == 200
    assert 'action="/compare"' in page.text
    assert 'name="baseline"' in page.text and 'name="current"' in page.text
    # Nothing is claimed about a comparison nobody asked for.
    assert "compare-verdict" not in page.text


def test_a_fixed_finding_is_reported_as_resolved(improved_pair):
    """The whole point: the reader asked whether the fix worked."""
    earlier, _later = improved_pair
    page = client().get(f"/compare?baseline={EARLIER}&current={LATER}")

    assert page.status_code == 200
    fixed = "exposed:/opencloud.yaml"
    assert fixed in {
        entry["id"] for entry in earlier["extraChecks"] if not entry["passed"]
    }, "the earlier scan must fail this for the test to mean anything"
    assert fixed in page.text
    assert 'data-verdict="improved"' in page.text
    # And the negative: a finding that was fixed is not also reported as new.
    introduced = page.text.split("compare.introduced", 1)[0]
    assert "regressed" not in introduced


def test_the_page_and_the_agent_tool_answer_the_same_pair_identically(improved_pair):
    """
    Two surfaces, one arithmetic.

    A reader and the agent auditing the same instance must not be told
    different things about the same two scans - which is exactly what a second
    implementation in the page would eventually produce.
    """
    earlier, later = improved_pair
    comparison = compare_documents(EARLIER, LATER, earlier, later)
    page = client().get(f"/compare?baseline={EARLIER}&current={LATER}")

    assert f'data-verdict="{comparison["verdict"]}"' in page.text
    assert comparison["resolved"], "the pair must have a resolved finding"
    # The page prints an identifier without the family the arithmetic uses,
    # which is the one difference between the two - and the reason this asks
    # for the same transformation rather than for the raw string.
    for finding in comparison["resolved"] + comparison["introduced"]:
        assert finding_id(finding) in page.text


def test_a_finding_is_named_the_way_the_catalogue_names_it(improved_pair):
    """
    The comparison's own names carry a family the catalogue does not use.

    A baseline snapshot calls it `check:exposed:/opencloud.yaml` so that a
    hardening and a check of the same name cannot collide. Printed unchanged,
    the identifier does not match the catalogue and its link goes nowhere.
    """
    page = client().get(f"/compare?baseline={EARLIER}&current={LATER}")

    assert "exposed:/opencloud.yaml" in page.text
    assert "check:exposed:" not in page.text
    assert "hardening:" not in page.text
    assert 'href="/catalogue#check-exposed"' in page.text


def test_both_scan_times_are_shown_rather_than_called_unparsable(improved_pair):
    """
    The scanner writes this timestamp from its own clock, and it is not one of
    the fields a scanned host has any say in.

    It used to go through the allow-list meant for a version string a stranger
    chose - a list with no ':' in it - so every comparison reported both times
    as "unparsable", here and to an agent.
    """
    page = client().get(f"/compare?baseline={EARLIER}&current={LATER}")

    assert "unparsable" not in page.text
    assert page.text.count("20") >= 2  # both dates rendered at all


def test_comparing_a_scan_with_itself_is_refused(improved_pair):
    """An empty diff of a scan against itself reads as 'nothing is wrong'."""
    page = client().get(f"/compare?baseline={EARLIER}&current={EARLIER}")

    assert page.status_code == 422
    assert "nothing to compare" in page.text
    assert "compare-verdict" not in page.text


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_an_expired_uuid_says_which_of_the_two_is_gone(improved_pair, side):
    """'One of your uuids has expired' sends somebody looking through both."""
    known = {"baseline": EARLIER, "current": LATER}
    known[side] = UNKNOWN
    page = client().get(f"/compare?baseline={known['baseline']}&current={known['current']}")

    assert page.status_code == 404
    # The whole phrase, because the page's own lede mentions both scans.
    gone = "The earlier scan is unknown"
    other = "The later scan is unknown"
    if side == "current":
        gone, other = other, gone
    assert gone in page.text
    assert other not in page.text


def test_a_scan_that_has_not_finished_is_not_compared(improved_pair):
    """
    409, not 404: there is nothing to compare *yet*.

    Answering 'not found' would send a reader to scan the instance again when
    the scan they have is still running.
    """
    configured = settings()
    store = ScanStore(backend=memory_backend(MEMORY_URL), ttl=configured.result_ttl)
    asyncio.run(
        store.create(
            UNKNOWN,
            target="http://opencloud.example.com",
            ignore_hardenings=(),
            output_format="dashboard",
        )
    )

    page = client().get(f"/compare?baseline={EARLIER}&current={UNKNOWN}")

    assert page.status_code == 409
    assert "not finished" in page.text


def test_two_different_instances_are_compared_but_said_so():
    """
    Staging against production is a fair question; answered silently it is not.

    The same fake server under two names, because what the comparison calls
    the same instance is the name that was scanned - two ports on one address
    are one target, and would not exercise this at all.
    """
    configured = settings(allow_private_targets=True, verify_tls=False, scan_timeout=5)
    store = ScanStore(backend=memory_backend(MEMORY_URL), ttl=configured.result_ttl)
    with FakeOpenCloud() as instance:
        _scan(store, configured, EARLIER, f"http://127.0.0.1:{instance.port}")
        _scan(store, configured, LATER, f"http://localhost:{instance.port}")

    page = client().get(f"/compare?baseline={EARLIER}&current={LATER}")

    assert page.status_code == 200
    assert "different instances" in page.text
    # Shown, not refused.
    assert "compare-verdict" in page.text


def test_the_comparison_page_is_never_indexable(improved_pair):
    """It carries two results, and a result is never indexed (ADR 0009)."""
    for path in ("/compare", f"/compare?baseline={EARLIER}&current={LATER}"):
        page = client().get(path)
        assert 'content="noindex, nofollow"' in page.text, path
        assert "rel=\"canonical\"" not in page.text, path


def test_a_comparison_stores_nothing(improved_pair):
    """
    ADR 0002 and ADR 0029: a comparison is two live results and arithmetic.

    A stored comparison would be a scan result under another name, outliving
    the results it describes and exempt from their erasure.
    """
    # Read straight out of the stand-in's own dictionaries: there is no
    # listing API here, deliberately - the service has none either.
    backend = memory_backend(MEMORY_URL)
    before = set(backend._values) | set(backend._lists)

    page = client().get(f"/compare?baseline={EARLIER}&current={LATER}")

    assert page.status_code == 200
    assert before, "the two scans must be in the store for this to mean anything"
    assert set(backend._values) | set(backend._lists) == before
