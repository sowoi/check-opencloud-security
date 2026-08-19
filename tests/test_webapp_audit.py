"""
The audit trail: what it records when an operator asks for it, and what it
still refuses to record when they do.

An audit log of a public scan service is a list of who scanned what, so every
test here asserts the negative as well as the positive: the records exist,
and the address and the target inside them are pseudonyms unless the operator
deliberately turned that off.
"""

from __future__ import annotations

import json
import logging

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.audit import (
    EVENT_RATE_LIMITED,
    EVENT_SCAN_REQUESTED,
    EVENT_SUBMISSION_REJECTED,
    REASON_RATE_LIMIT_CLIENT,
    REASON_RATE_LIMIT_TARGET,
    REASON_TARGET_REJECTED,
    REASON_UNSUPPORTED_FIELDS,
    AuditLog,
)

TARGET = "https://opencloud.example.com"


@pytest.fixture
def audit_records(caplog):
    """Every audit record emitted during one test, already parsed."""
    caplog.set_level(logging.INFO, logger="check_opencloud.web.audit")

    def records(event: str | None = None) -> list[dict]:
        parsed = [
            json.loads(item.message)
            for item in caplog.records
            if item.name == "check_opencloud.web.audit"
        ]
        return [item for item in parsed if event is None or item["event"] == event]

    return records


def _create(test_client, target: str = TARGET, **body):
    payload = {"target_url": target}
    payload.update(body)
    return test_client.post("/api/scans", json=payload)


def test_an_accepted_scan_is_audited_with_its_uuid_and_a_timestamp(audit_records):
    """The record has to name the scan and when it happened, or it answers nothing."""
    test_client = client(audit_log=True)

    response = _create(test_client)

    assert response.status_code == 202
    requested = audit_records(EVENT_SCAN_REQUESTED)
    assert len(requested) == 1
    assert requested[0]["uuid"] == response.json()["uuid"]
    assert requested[0]["timestamp"]
    assert requested[0]["outputFormat"] == "dashboard"


def test_nothing_is_audited_while_the_audit_log_is_off(audit_records):
    """The default deployment keeps its promise: lifecycle markers and uuids only."""
    response = _create(client())

    assert response.status_code == 202
    assert audit_records() == []


def test_the_audited_client_and_target_are_pseudonyms_by_default(audit_records):
    """A record naming an address and a host is the database this must not become."""
    _create(client(audit_log=True))

    record = audit_records(EVENT_SCAN_REQUESTED)[0]
    assert "opencloud.example.com" not in json.dumps(record)
    assert record["target"] != "opencloud.example.com"
    assert "testclient" not in json.dumps(record)
    # A pseudonym is still useful: it is a fixed-length fingerprint, not a
    # placeholder that makes every request look the same.
    assert len(record["target"]) == 16
    assert record["client"] != record["target"]


def test_an_operator_can_opt_into_recording_the_target_in_the_clear(audit_records):
    """A private deployment scanning its own estate needs the hostname itself."""
    _create(client(audit_log=True, audit_log_targets=True))

    record = audit_records(EVENT_SCAN_REQUESTED)[0]
    assert record["target"] == "opencloud.example.com"
    # The client address is not covered by that switch and never becomes one.
    assert "testclient" not in json.dumps(record)


def test_the_client_address_stays_a_pseudonym_even_with_targets_in_the_clear():
    """There is no setting that writes a requester's address, and that is the point."""
    log = AuditLog(enabled=True, record_targets=True, salt=b"salt")

    assert log.fingerprint("203.0.113.10") != "203.0.113.10"
    assert len(log.fingerprint("203.0.113.10")) == 16


def test_the_same_client_keeps_one_fingerprint_across_requests(audit_records):
    """Correlating repeated requests is the whole reason an audit trail exists."""
    test_client = client(audit_log=True)

    _create(test_client)
    _create(test_client, target="https://other.example.org")

    requested = audit_records(EVENT_SCAN_REQUESTED)
    assert len(requested) == 2
    assert requested[0]["client"] == requested[1]["client"]
    assert requested[0]["target"] != requested[1]["target"]


def test_a_fingerprint_does_not_survive_a_restart_without_a_configured_salt():
    """A random salt per process is what keeps the trail from becoming history."""
    first = AuditLog.from_settings(settings(audit_log=True))
    second = AuditLog.from_settings(settings(audit_log=True))

    assert first.fingerprint("203.0.113.10") != second.fingerprint("203.0.113.10")

    pinned_a = AuditLog.from_settings(settings(audit_log=True, audit_salt="pepper"))
    pinned_b = AuditLog.from_settings(settings(audit_log=True, audit_salt="pepper"))
    assert pinned_a.fingerprint("203.0.113.10") == pinned_b.fingerprint("203.0.113.10")


def test_a_submission_carrying_an_unsupported_field_is_audited(audit_records):
    """Somebody probing for a concurrency knob is exactly what an audit is for."""
    response = _create(client(audit_log=True), workers=99)

    assert response.status_code == 422
    record = audit_records(EVENT_SUBMISSION_REJECTED)[0]
    assert record["reason"] == REASON_UNSUPPORTED_FIELDS
    assert record["status"] == 422
    assert record["fields"] == ["workers"]


def test_a_rejected_target_is_audited_without_naming_the_target(audit_records):
    """The attempt matters; recording the address somebody tried does not."""
    response = _create(client(audit_log=True), target="http://127.0.0.1:9200")

    assert response.status_code == 400
    record = audit_records(EVENT_SUBMISSION_REJECTED)[0]
    assert record["reason"] == REASON_TARGET_REJECTED
    assert "127.0.0.1" not in json.dumps(record)
    assert audit_records(EVENT_SCAN_REQUESTED) == []


def test_a_triggered_client_limit_is_audited_with_its_cooldown(audit_records):
    """A limit nobody can see triggering is a limit nobody can tune."""
    test_client = client(audit_log=True, ip_rate_limit=1, ip_rate_window=60)

    assert _create(test_client).status_code == 202
    assert _create(test_client, target="https://other.example.org").status_code == 429

    record = audit_records(EVENT_RATE_LIMITED)[0]
    assert record["scope"] == REASON_RATE_LIMIT_CLIENT
    assert record["retryAfter"] > 0


def test_a_triggered_target_cooldown_is_audited_as_its_own_scope(audit_records):
    """The two limits protect different people, so a trail must tell them apart."""
    test_client = client(audit_log=True, target_cooldown=300)

    assert _create(test_client).status_code == 202
    assert _create(test_client).status_code == 429

    record = audit_records(EVENT_RATE_LIMITED)[0]
    assert record["scope"] == REASON_RATE_LIMIT_TARGET
    assert record["target"]
    assert "opencloud.example.com" not in json.dumps(record)


def test_a_submitted_field_name_cannot_forge_a_second_audit_record(audit_records):
    """One record per event: a newline in a stranger's field name is not a new line."""
    test_client = client(audit_log=True)

    response = test_client.post(
        "/api/scans",
        json={"target_url": TARGET, "evil\nevent=scan_requested": 1},
    )

    assert response.status_code == 422
    records = audit_records()
    assert len(records) == 1
    assert records[0]["event"] == EVENT_SUBMISSION_REJECTED
    # The name is kept, because the attempt is the interesting part - but the
    # newline that would have started a second record is gone.
    assert records[0]["fields"] == ["evilevent=scan_requested"]
