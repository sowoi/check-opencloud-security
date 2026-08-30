"""
Erasure on request, and the receipt that has to outlive the data.

Two things are worth protecting here and both are asserted negatively as well
as positively: that the data really is gone afterwards, and that nothing else
went with it. A purge that quietly deletes a neighbouring scan is a far worse
bug than one that fails loudly.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    backend,
    client,
    settings,
)
from webapp.purge import PurgeRejected, fingerprint, normalise_target, sign, verify
from webapp.ratelimit import target_key
from webapp.store import metadata_key, result_key, status_key

# At least MIN_TOKEN_LENGTH characters, because the application refuses to
# start with a credential short enough to guess and these tests start it.
TOKEN = "erasure-token-for-tests-0123456789abcdef"
SIGNING_KEY = "receipt-signing-key-for-tests"

AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _enabled_client(**overrides):
    overrides.setdefault("purge_token", TOKEN)
    overrides.setdefault("purge_signing_key", SIGNING_KEY)
    return client(**overrides)


def _submit(test_client, target):
    response = test_client.post("/api/scans", json={"target_url": target})
    assert response.status_code == 202, response.text
    return response.json()["uuid"]


def test_a_purge_deletes_every_scan_held_for_the_named_instance():
    """The whole point: an erasure request leaves nothing behind to serve."""
    test_client = _enabled_client()
    first = _submit(test_client, "https://forget.example.com")
    second = _submit(test_client, "https://forget.example.com/")

    response = test_client.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted"]["scans"] == 2
    assert payload["remaining"] == 0
    assert payload["complete"] is True
    assert test_client.get(f"/api/scans/{first}").status_code == 404
    assert test_client.get(f"/api/scans/{second}").status_code == 404


def test_a_purge_leaves_every_other_instance_alone():
    """Erasure is aimed at one target; a purge that over-deletes is a data loss bug."""
    test_client = _enabled_client()
    doomed = _submit(test_client, "https://forget.example.com")
    spared = _submit(test_client, "https://keep.example.com")

    test_client.request("DELETE", "/api/purge?target=forget.example.com", headers=AUTH)

    assert test_client.get(f"/api/scans/{doomed}").status_code == 404
    survivor = test_client.get(f"/api/scans/{spared}")
    assert survivor.status_code == 200
    assert survivor.json()["target"].endswith("keep.example.com")


def test_a_purge_removes_the_keys_themselves_and_not_only_the_view_of_them():
    """A 404 could come from a status key alone; the payload has to go too."""
    test_client = _enabled_client()
    identifier = _submit(test_client, "https://forget.example.com")
    store = backend()

    test_client.request("DELETE", "/api/purge?target=forget.example.com", headers=AUTH)

    for key in (status_key(identifier), result_key(identifier), metadata_key(identifier)):
        assert key not in store._values


def test_a_purge_drops_the_queue_entry_so_no_worker_picks_the_scan_up():
    """A queued uuid that outlives its metadata would be scanned after erasure."""
    test_client = _enabled_client()
    identifier = _submit(test_client, "https://forget.example.com")

    response = test_client.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    )

    assert response.json()["deleted"]["queueEntries"] == 1
    queue = backend()._lists.get("cos:web:queue", [])
    assert identifier not in queue


def test_a_purge_also_erases_the_cooldown_derived_from_the_target():
    """The cooldown key is state about the instance, so erasure has to take it."""
    test_client = _enabled_client(target_cooldown=300)
    _submit(test_client, "https://forget.example.com")
    assert target_key("forget.example.com") in backend()._values

    response = test_client.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    )

    assert response.json()["deleted"]["rateLimitKeys"] == 1
    assert target_key("forget.example.com") not in backend()._values


def test_a_purge_matches_the_instance_however_the_request_spells_it():
    """Whoever asks to be forgotten will not spell the URL the way we stored it."""
    test_client = _enabled_client()
    identifier = _submit(test_client, "https://forget.example.com")

    response = test_client.request(
        "DELETE", "/api/purge?target=HTTPS://Forget.example.com:443/status", headers=AUTH
    )

    assert response.json()["deleted"]["scans"] == 1
    assert test_client.get(f"/api/scans/{identifier}").status_code == 404


def test_a_purge_for_an_instance_with_nothing_stored_still_answers_with_a_receipt():
    """A controller must be able to prove no data was held, not only that it deleted some."""
    test_client = _enabled_client()

    response = test_client.request(
        "DELETE", "/api/purge?target=stranger.example.com", headers=AUTH
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted"]["scans"] == 0
    assert payload["complete"] is True
    assert payload["statement"]


def test_the_receipt_is_signed_and_verifies_against_the_configured_key():
    """A proof the operator can rewrite afterwards is not a proof."""
    test_client = _enabled_client()
    _submit(test_client, "https://forget.example.com")

    payload = test_client.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    ).json()

    assert payload["signature"]["algorithm"] == "HMAC-SHA256"
    assert verify(payload, SIGNING_KEY) is True
    assert verify(payload, "some-other-key") is False


def test_a_tampered_receipt_stops_verifying():
    """The signature has to cover the counts, not just the target."""
    test_client = _enabled_client()
    _submit(test_client, "https://forget.example.com")
    payload = test_client.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    ).json()

    forged = json.loads(json.dumps(payload))
    forged["deleted"]["scans"] = 99

    assert verify(payload, SIGNING_KEY) is True
    assert verify(forged, SIGNING_KEY) is False


def test_an_unsigned_receipt_is_returned_when_no_signing_key_is_configured():
    """The erasure still happens; only its provability depends on the operator."""
    test_client = client(purge_token=TOKEN, purge_signing_key=None)
    identifier = _submit(test_client, "https://forget.example.com")

    payload = test_client.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    ).json()

    assert payload["signature"] is None
    assert payload["deleted"]["scans"] == 1
    assert test_client.get(f"/api/scans/{identifier}").status_code == 404


def test_the_endpoint_does_not_exist_until_an_operator_configures_a_token():
    """An unauthenticated purge would let anyone delete a stranger's running scan."""
    test_client = client()
    identifier = _submit(test_client, "https://forget.example.com")

    response = test_client.request("DELETE", "/api/purge?target=forget.example.com")

    assert response.status_code == 404
    assert test_client.get(f"/api/scans/{identifier}").status_code == 200


def test_a_wrong_token_erases_nothing():
    """The obvious attack: guess the secret, delete somebody else's results."""
    test_client = _enabled_client()
    identifier = _submit(test_client, "https://forget.example.com")

    response = test_client.request(
        "DELETE",
        "/api/purge?target=forget.example.com",
        headers={"Authorization": "Bearer not-the-token"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert test_client.get(f"/api/scans/{identifier}").status_code == 200


def test_a_missing_or_unusable_target_is_refused_before_anything_is_deleted():
    """A purge with no target must not become a purge of everything."""
    test_client = _enabled_client()
    identifier = _submit(test_client, "https://forget.example.com")

    empty = test_client.request("DELETE", "/api/purge", headers=AUTH)
    wildcard = test_client.request("DELETE", "/api/purge?target=*", headers=AUTH)

    assert empty.status_code == 422
    assert wildcard.status_code == 422
    assert test_client.get(f"/api/scans/{identifier}").status_code == 200


def test_the_receipt_says_what_the_service_cannot_erase():
    """A proof of deletion that hides a remaining copy is worse than none."""
    test_client = _enabled_client(audit_log=True, audit_log_targets=True)

    payload = test_client.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    ).json()

    notes = " ".join(payload["notes"])
    assert "downloaded" in notes
    assert "audit record" in notes


def test_a_purge_is_recorded_in_the_audit_trail_when_one_is_kept(caplog):
    """An erasure the controller cannot show it performed will be asked about twice."""
    test_client = _enabled_client(audit_log=True)
    _submit(test_client, "https://forget.example.com")

    with caplog.at_level("INFO", logger="check_opencloud.web.audit"):
        payload = test_client.request(
            "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
        ).json()

    records = [json.loads(entry.message) for entry in caplog.records]
    purges = [entry for entry in records if entry["event"] == "data_purged"]
    assert len(purges) == 1
    assert purges[0]["receipt"] == payload["receiptId"]
    assert purges[0]["scans"] == 1
    assert purges[0]["target"] != "forget.example.com"


def test_normalising_a_target_keeps_a_hostname_and_refuses_a_pattern():
    """The hostname reaches a key comparison, so what counts as one is load-bearing."""
    assert normalise_target("https://Instance.example.com:9200/x") == "instance.example.com"
    assert normalise_target(" instance.example.com ") == "instance.example.com"

    for bad in ("", "   ", "*", "scan:*", "not a host"):
        try:
            normalise_target(bad)
        except PurgeRejected:
            continue
        raise AssertionError(f"{bad!r} should not be accepted as a target")


def test_the_receipt_carries_no_fingerprint_when_there_is_no_key_to_make_one_with():
    """
    An unkeyed hash of a hostname is not a pseudonym.

    The receipt calls the fingerprint safe to file. With no key it would be a
    plain SHA-256 of a hostname, and the space of hostnames is small enough to
    enumerate - so the honest answer is no fingerprint at all.
    """
    unsigned = client(purge_token=TOKEN, purge_signing_key=None)
    signed = _enabled_client()

    without = unsigned.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    ).json()
    with_key = signed.request(
        "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
    ).json()

    assert without["targetFingerprint"] is None
    assert with_key["targetFingerprint"] is not None
    assert with_key["targetFingerprint"] != hashlib.sha256(
        b"forget.example.com"
    ).hexdigest()[:32]


def test_the_fingerprint_and_the_signature_do_not_share_a_domain():
    """One key does two jobs, so each has to label its own input."""
    body = {"target": "forget.example.com"}

    assert fingerprint("forget.example.com", SIGNING_KEY) != sign(body, SIGNING_KEY)
    assert fingerprint("forget.example.com", SIGNING_KEY) != hmac.new(
        SIGNING_KEY.encode(), b"forget.example.com", hashlib.sha256
    ).hexdigest()[:32]


def test_a_credential_with_non_ascii_bytes_is_refused_rather_than_crashing():
    """
    `hmac.compare_digest` raises on non-ASCII `str`, and Starlette hands
    header values over as latin-1 - so an unauthenticated request could turn
    an authorisation check into a 500.
    """
    test_client = _enabled_client()
    identifier = _submit(test_client, "https://forget.example.com")

    response = test_client.request(
        "DELETE",
        "/api/purge?target=forget.example.com",
        headers={b"Authorization": "Bearer schl\u00fcssel".encode("latin-1")},
    )

    assert response.status_code == 401
    assert test_client.get(f"/api/scans/{identifier}").status_code == 200


def test_a_wrong_credential_is_only_guessable_five_times():
    """
    The purge token is the whole of the authorisation for the one destructive
    call this service has, and it is compared on a route that counted nothing.
    Constant-time comparison stops the token leaking a character at a time; it
    does nothing about simply trying, which is what this covers.
    """
    test_client = _enabled_client()
    wrong = {"Authorization": "Bearer not-the-token-but-long-enough-to-try"}

    seen = [
        test_client.request(
            "DELETE", "/api/purge?target=forget.example.com", headers=wrong
        ).status_code
        for _ in range(7)
    ]

    # Five attempts are answered, the rest are refused without a comparison.
    assert seen[:5] == [401] * 5
    assert seen[5:] == [429, 429]


def test_the_throttle_counts_wrong_answers_and_not_erasures():
    """
    An operator working through a list of erasure requests must not be locked
    out by doing their job. Only a failure counts, so the right token stays
    usable however many times it is presented.
    """
    test_client = _enabled_client()

    for _ in range(8):
        response = test_client.request(
            "DELETE", "/api/purge?target=forget.example.com", headers=AUTH
        )
        assert response.status_code == 200, response.text


def test_a_purge_token_short_enough_to_guess_refuses_to_start():
    """
    The same stance `ensure_encryption_ready` takes: a deployment whose
    operator believes the endpoint is protected must not be served with a
    credential that is not protection. Unset stays perfectly valid - that
    answers 404 and deploys nothing.
    """
    from webapp.purge import MIN_TOKEN_LENGTH, ensure_purge_token_ready

    ensure_purge_token_ready(None)
    ensure_purge_token_ready("a" * MIN_TOKEN_LENGTH)

    with pytest.raises(ValueError, match="at least"):
        ensure_purge_token_ready("hunter2")


def test_two_processes_sharing_a_salt_share_one_rate_limit_counter():
    """
    The pepper is per-process by default, so two web processes derive two
    different Redis keys for the same address - a client silently gets one
    allowance each and the limit stops being one. A configured salt is what
    makes them count together, and nothing in a log would have said otherwise.
    """
    from webapp.ratelimit import client_key

    # Two processes, same salt: one key, so one counter.
    assert client_key("203.0.113.10", "shared") == client_key("203.0.113.10", "shared")
    # The negative half - which is the bug, and the default.
    assert client_key("203.0.113.10", "one") != client_key("203.0.113.10", "two")
    assert client_key("203.0.113.10", "shared") != client_key("203.0.113.10")
    # And a salt still separates different clients rather than collapsing them.
    assert client_key("203.0.113.10", "shared") != client_key("203.0.113.11", "shared")
