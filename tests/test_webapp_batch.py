"""
Batch submission: many targets in one request, and the limits that still apply.

A batch is the obvious place for the limits to quietly stop applying, so most
of what is asserted here is that they do not - per target, in order, exactly
as if each had been submitted on its own.
"""

from __future__ import annotations

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    backend,
    client,
    settings,
)


def _batch(test_client, targets, **body):
    payload = {"targets": targets}
    payload.update(body)
    return test_client.post("/api/scans/batch", json=payload)


def test_a_batch_queues_every_target_and_returns_a_uuid_for_each():
    """One request, several instances: the point of the endpoint."""
    test_client = client()

    response = _batch(
        test_client,
        [
            "https://one.example.com",
            "https://two.example.com",
            "https://three.example.org",
        ],
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["counts"] == {"submitted": 3, "accepted": 3, "rejected": 0}
    uuids = [entry["uuid"] for entry in payload["accepted"]]
    assert len(set(uuids)) == 3
    for identifier in uuids:
        assert test_client.get(f"/api/scans/{identifier}").json()["state"] == "queued"


def test_every_target_in_a_batch_counts_against_the_client_limit():
    """A batch must not be a way to buy ten scans for the price of one."""
    test_client = client(ip_rate_limit=2, ip_rate_window=60)

    response = _batch(
        test_client,
        [
            "https://one.example.com",
            "https://two.example.com",
            "https://three.example.org",
        ],
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["counts"]["accepted"] == 2
    assert payload["counts"]["rejected"] == 1
    refused = payload["rejected"][0]
    assert refused["target"] == "https://three.example.org"
    assert refused["status"] == 429
    assert refused["retryAfter"] > 0
    assert response.headers["retry-after"] == str(refused["retryAfter"])


def test_a_batch_of_one_target_still_spends_one_scan_from_the_window():
    """The limit is counted where it is spent, so a single request follows on."""
    test_client = client(ip_rate_limit=1, ip_rate_window=60)

    assert _batch(test_client, ["https://one.example.com"]).status_code == 202
    followed = test_client.post(
        "/api/scans", json={"target_url": "https://two.example.com"}
    )

    assert followed.status_code == 429


def test_a_batch_where_nothing_started_answers_429_and_offers_self_hosting():
    """A refusal is an invitation, in a batch exactly as in a single scan."""
    test_client = client(ip_rate_limit=1, ip_rate_window=60)
    assert _batch(test_client, ["https://one.example.com"]).status_code == 202

    response = _batch(test_client, ["https://two.example.com"])

    assert response.status_code == 429
    payload = response.json()
    assert payload["accepted"] == []
    assert payload["selfHostUrl"] == "https://github.com/sowoi/check-opencloud-security"
    assert "open source" in payload["hint"]
    assert response.headers["retry-after"]


def test_the_target_cooldown_applies_within_one_batch():
    """The cooldown protects an instance from this service, batch or not."""
    test_client = client(target_cooldown=300)

    response = _batch(
        test_client, ["https://one.example.com", "https://one.example.com"]
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["counts"] == {"submitted": 2, "accepted": 1, "rejected": 1}
    assert payload["rejected"][0]["status"] == 429
    assert payload["rejected"][0]["retryAfter"] > 0


def test_a_batch_larger_than_the_limit_is_refused_before_anything_is_queued():
    """A cap nobody enforces before the work starts is not a cap."""
    test_client = client(max_batch_targets=2)

    response = _batch(
        test_client,
        [
            "https://one.example.com",
            "https://two.example.com",
            "https://three.example.org",
        ],
    )

    assert response.status_code == 422
    assert response.json()["maxTargets"] == 2
    # Nothing ran: the queue is empty, so no target paid a cooldown either.
    assert _batch(test_client, ["https://one.example.com"]).status_code == 202


def test_a_batch_refuses_a_field_that_would_change_how_hard_it_scans():
    """The prohibition is about load, and a batch is where load would be bought."""
    test_client = client()

    response = test_client.post(
        "/api/scans/batch",
        json={"targets": ["https://one.example.com"], "workers": 40},
    )

    assert response.status_code == 422
    assert "workers" in response.json()["detail"]


def test_a_batch_without_targets_says_so_rather_than_scanning_nothing():
    """An empty batch is a mistake worth naming, not a successful no-op."""
    test_client = client()

    assert test_client.post("/api/scans/batch", json={}).status_code == 422
    assert _batch(test_client, []).status_code == 422
    assert test_client.post(
        "/api/scans/batch", json={"targets": "https://one.example.com"}
    ).status_code == 422


def test_one_unusable_target_does_not_stop_the_rest_of_the_batch():
    """A typo in the third line should not cost somebody the other nine scans."""
    test_client = client()

    response = _batch(
        test_client,
        ["https://one.example.com", "http://127.0.0.1:9200", "https://two.example.com"],
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["counts"] == {"submitted": 3, "accepted": 2, "rejected": 1}
    assert payload["rejected"][0]["status"] == 400
    assert payload["rejected"][0]["target"] == "http://127.0.0.1:9200"


def test_a_batch_scan_is_reachable_only_by_its_own_uuid():
    """Batching must not create a handle that reaches more than one scan."""
    test_client = client()

    payload = _batch(
        test_client, ["https://alpha.example.com", "https://beta.example.com"]
    ).json()
    first, second = (entry["uuid"] for entry in payload["accepted"])

    alpha = test_client.get(f"/api/scans/{first}").json()
    assert alpha["target"] == "https://alpha.example.com"
    assert second not in str(alpha)
    assert "beta.example.com" not in str(alpha)
    # And there is still no way to ask for the batch as a whole.
    assert test_client.get("/api/scans").status_code in {200, 303}
