"""
The addresses an operator has excluded from this deployment.

Every other rule in the SSRF guard is a property of the address - private,
link-local, metadata. This one is a decision somebody made: an instance owner
who asked to be left alone, a host being used to make the service hammer
somebody, a range that is simply not a scanning target here. The tests below
pin the two things that make such a decision worth anything: that it holds
wherever a target enters (submission, worker, redirect), and that the settings
which exist to *loosen* the guard cannot reopen it.
"""

from __future__ import annotations

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.ssrf import (
    TargetRejected,
    denylist,
    ensure_blocklist_ready,
    redirect_guard,
    revalidate,
    validate_target,
)

# The offline resolver in webapp_support answers every ``*.example.com`` name
# with this one documentation address, so a range covering it is a range that
# every example host in these tests resolves into.
EXAMPLE_RANGE = "203.0.113.0/24"
OTHER_RANGE = "198.51.100.0/24"


def _submit(test_client, target: str = "https://cloud.example.com"):
    return test_client.post("/api/scans", json={"target_url": target})


def test_an_excluded_hostname_is_refused_and_its_neighbour_is_still_scanned():
    """
    The list refuses what it names, and only what it names.

    Without the second half this would pass just as well for a guard that
    refused everything, which is not a feature anybody asked for.
    """
    test_client = client(blocked_targets=("cloud.example.com",))

    refused = _submit(test_client, "https://cloud.example.com")
    accepted = _submit(test_client, "https://other.example.com")

    assert refused.status_code == 400
    assert "uuid" not in refused.json()
    assert accepted.status_code == 202


def test_an_excluded_hostname_is_refused_however_it_is_spelled():
    """
    A visitor must not get past an exclusion with a capital letter.

    Case, a trailing dot and an explicit port are all the same host as far as
    DNS is concerned, so they have to be the same host here too.
    """
    test_client = client(blocked_targets=("Cloud.Example.com.",))

    for spelling in (
        "https://cloud.example.com",
        "https://CLOUD.example.com",
        "https://cloud.example.com.",
        "https://cloud.example.com:8443",
        "cloud.example.com/subfolder",
    ):
        assert _submit(test_client, spelling).status_code == 400, spelling


def test_a_suffix_excludes_the_domain_and_everything_under_it_but_not_a_lookalike():
    """
    ``.cloud.example.com`` is a domain, not a string the hostname ends with.

    The lookalike is the point: a suffix match written as a plain
    ``endswith`` would refuse ``notcloud.example.com``, an unrelated instance
    whose owner never asked for anything.
    """
    test_client = client(blocked_targets=(".cloud.example.com",))

    assert _submit(test_client, "https://cloud.example.com").status_code == 400
    assert _submit(test_client, "https://a.cloud.example.com").status_code == 400
    assert _submit(test_client, "https://notcloud.example.com").status_code == 202


def test_a_wildcard_is_accepted_as_a_spelling_of_a_suffix():
    """Most people write ``*.example.com``, and being right about the syntax
    is not what an operator should have to get right about an exclusion."""
    assert denylist(("*.cloud.example.com",)) == denylist((".cloud.example.com",))


def test_an_excluded_range_catches_a_name_that_resolves_into_it():
    """
    An exclusion by address survives the target being given a second name.

    This is the half a hostname entry cannot do: the range is checked against
    what the name actually resolves to, so pointing a fresh DNS record at the
    same machine does not buy a scan.
    """
    covered = client(blocked_targets=(EXAMPLE_RANGE,))
    elsewhere = client(blocked_targets=(OTHER_RANGE,))

    assert _submit(covered, "https://anything.example.com").status_code == 400
    assert _submit(elsewhere, "https://anything.example.com").status_code == 202


def test_an_exclusion_outranks_the_hosts_the_operator_allowed():
    """
    The allowlist exempts a host from the SSRF rules, never from this list.

    Two settings pointing at the same host have to resolve one way round or
    the other, and refusing is the only safe answer: the allowlist exists to
    reach an internal instance, the exclusion to promise somebody they will
    not be scanned.
    """
    both = client(
        extra_hosts_allowed=("cloud.example.com",),
        blocked_targets=("cloud.example.com",),
    )
    allowed_only = client(extra_hosts_allowed=("cloud.example.com",))

    assert _submit(both, "https://cloud.example.com").status_code == 400
    assert _submit(allowed_only, "https://cloud.example.com").status_code == 202


def test_an_exclusion_outranks_the_private_target_escape_hatch():
    """
    An on-premise deployment scanning its own estate still has exclusions.

    ``COS_WEB_ALLOW_PRIVATE_TARGETS`` turns the address rules off wholesale,
    and a list that went with them would silently stop protecting the one
    deployment shape that can reach an internal network at all.
    """
    excluded = client(
        allow_private_targets=True, blocked_targets=("10.0.0.0/8",)
    )
    permitted = client(allow_private_targets=True)

    assert _submit(excluded, "http://10.1.2.3").status_code == 400
    assert _submit(permitted, "http://10.1.2.3").status_code == 202


def test_an_address_submitted_as_a_literal_is_excluded_too():
    """Naming a host must not be a way round a range, nor the other way about."""
    test_client = client(
        allow_private_targets=True, blocked_targets=("192.0.2.7",)
    )

    assert _submit(test_client, "http://192.0.2.7").status_code == 400
    assert _submit(test_client, "http://192.0.2.8").status_code == 202


def test_the_worker_refuses_a_target_excluded_after_it_was_queued():
    """
    The exclusion is re-read where the scan actually happens.

    A queue is not instantaneous. An operator who adds an entry while a job
    is waiting has said "do not scan that", and the job that was already in
    flight is exactly the one they were trying to stop.
    """
    target = validate_target("https://cloud.example.com")

    assert revalidate(target).hostname == "cloud.example.com"
    with pytest.raises(TargetRejected):
        revalidate(target, blocked_targets=("cloud.example.com",))


def test_a_redirect_into_an_excluded_target_is_not_followed():
    """
    The address a visitor submitted is only the first one a scan connects to.

    A target that answers ``302`` towards an excluded host would otherwise
    have the scan reach it one hop later and report the answer back.
    """
    guarded = redirect_guard(blocked_targets=(EXAMPLE_RANGE,))
    unguarded = redirect_guard()

    assert guarded("https://cloud.example.com/login") is False
    assert unguarded("https://cloud.example.com/login") is True


def test_the_refusal_says_nothing_about_why_the_address_is_excluded():
    """
    The list is the operator's business, not the visitor's.

    Echoing the entry that matched would turn every refusal into a read of
    the configuration, one submission at a time.
    """
    response = _submit(
        client(blocked_targets=(".cloud.example.com", EXAMPLE_RANGE)),
        "https://cloud.example.com",
    )

    body = response.json()["detail"]
    assert response.status_code == 400
    assert ".cloud.example.com" not in body
    assert EXAMPLE_RANGE not in body


def test_a_deployment_whose_exclusions_do_not_parse_refuses_to_start():
    """
    A typo in this list is invisible at runtime.

    The service would come up, answer normally, and scan the instance it was
    told to leave alone - there is no log line anybody reads in time for
    that. Failing at startup is the only version an operator notices.
    """
    with pytest.raises(ValueError, match="COS_WEB_BLOCKED_TARGETS"):
        client(blocked_targets=("cloud.example.com", "not a hostname!"))

    with pytest.raises(ValueError, match="COS_WEB_BLOCKED_TARGETS"):
        client(blocked_targets=("203.0.113.0/64",))

    assert client(blocked_targets=("cloud.example.com", EXAMPLE_RANGE)) is not None


def test_an_empty_list_changes_nothing():
    """
    The default has to be the behaviour that existed before the setting did.

    A deployment that never sets the variable must not start refusing
    anything, and an entry of empty whitespace is not an exclusion.
    """
    ensure_blocklist_ready(("", "   "))

    assert not denylist(())
    assert _submit(client(), "https://cloud.example.com").status_code == 202
    assert _submit(client(blocked_targets=("",)), "https://cloud.example.com").status_code == 202
