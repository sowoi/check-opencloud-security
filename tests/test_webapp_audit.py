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
import stat

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.audit import (
    AUDIT_LOGGER,
    EVENT_RATE_LIMITED,
    EVENT_SCAN_REQUESTED,
    EVENT_SUBMISSION_REJECTED,
    REASON_RATE_LIMIT_CLIENT,
    REASON_RATE_LIMIT_TARGET,
    REASON_TARGET_REJECTED,
    REASON_UNSUPPORTED_FIELDS,
    AuditLog,
    configure_audit_file,
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


@pytest.fixture(autouse=True)
def _restore_audit_logger():
    """
    Put the audit logger back the way it was found.

    Pointing it at a file is a process-wide side effect - a handler and a
    propagation flag - and a test that left one behind would send another
    test's records into a file in a temporary directory that no longer exists.
    """
    yield
    configure_audit_file(settings(audit_log=False))


def _lines(path) -> list[dict]:
    """The audit file, as the JSON objects it is supposed to be one per line."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


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


# --- keeping the trail past the container -----------------------------------
def test_the_trail_can_be_written_to_a_file_that_outlives_the_container(tmp_path):
    """A container's output ends with the container; an audit question does not."""
    path = tmp_path / "audit.log"
    test_client = client(audit_log=True, audit_log_file=str(path))

    response = _create(test_client)

    assert response.status_code == 202
    records = _lines(path)
    assert [item["event"] for item in records] == [EVENT_SCAN_REQUESTED]
    assert records[0]["uuid"] == response.json()["uuid"]
    # Still pseudonyms: writing the trail down does not change what is in it.
    assert "opencloud.example.com" not in path.read_text(encoding="utf-8")


def test_no_file_is_written_while_the_audit_log_is_off(tmp_path):
    """A path is where the records would go, never a reason to start keeping them."""
    path = tmp_path / "audit.log"

    _create(client(audit_log=False, audit_log_file=str(path)))

    assert not path.exists()


def test_the_ordinary_log_carries_no_second_copy_of_the_audit_trail(tmp_path, audit_records):
    """The lifecycle log is the one place kept free of targets and addresses."""
    path = tmp_path / "audit.log"

    _create(client(audit_log=True, audit_log_file=str(path)))

    assert _lines(path)
    # The records went to the file *instead of*, not as well as - or a
    # deployment shipping its ordinary log somewhere would ship the trail too.
    assert audit_records() == []


def test_an_audit_file_is_readable_by_its_owner_only(tmp_path):
    """A mounted volume is readable by whoever reaches the host it sits on."""
    path = tmp_path / "audit.log"

    _create(client(audit_log=True, audit_log_file=str(path)))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_trail_that_cannot_be_written_stops_the_service_starting(tmp_path):
    """Reporting an audit trail that goes nowhere is worse than keeping none."""
    missing = tmp_path / "not-mounted" / "audit.log"

    with pytest.raises(ValueError) as error:
        client(audit_log=True, audit_log_file=str(missing))

    assert "COS_WEB_AUDIT_LOG_FILE" in str(error.value)
    # And the reverse: the same path works once the mount is there.
    missing.parent.mkdir()
    _create(client(audit_log=True, audit_log_file=str(missing)))
    assert _lines(missing)


def test_the_trail_is_rotated_so_it_cannot_fill_the_volume_it_sits_on(tmp_path):
    """An audit log that grows without limit takes the service down with it."""
    path = tmp_path / "audit.log"
    test_client = client(
        audit_log=True,
        audit_log_file=str(path),
        audit_log_max_bytes=200,
        audit_log_backups=1,
    )

    for index in range(8):
        _create(test_client, target=f"https://host{index}.example.com")

    assert path.exists()
    assert (tmp_path / "audit.log.1").exists()
    # One generation was asked for, so that is all that is kept - the older
    # ones are gone rather than accumulating under a different name.
    assert not (tmp_path / "audit.log.2").exists()


def test_configuring_a_file_twice_does_not_record_everything_twice(tmp_path):
    """Two applications in one process are one trail, not a duplicated one."""
    path = tmp_path / "audit.log"
    client(audit_log=True, audit_log_file=str(path))
    test_client = client(audit_log=True, audit_log_file=str(path))

    _create(test_client)

    assert len(_lines(path)) == 1


def test_turning_the_file_off_again_leaves_the_logger_as_it_found_it(tmp_path):
    """The handler is removed, or a later run writes into a directory that went."""
    path = tmp_path / "audit.log"
    client(audit_log=True, audit_log_file=str(path))

    configure_audit_file(settings(audit_log=True))

    assert AUDIT_LOGGER.propagate
    assert not AUDIT_LOGGER.handlers


def test_an_externally_rotated_trail_follows_the_file_logrotate_creates(tmp_path):
    """
    logrotate renames the file and makes a new one; the writer has to follow.

    A process holding the old descriptor would go on filling a file nobody
    can find any more, and the trail would appear to stop the first night the
    rotation ran - which is exactly when an operator stops looking at it.
    """
    path = tmp_path / "audit.log"
    test_client = client(
        audit_log=True,
        audit_log_file=str(path),
        audit_log_rotation="external",
    )
    _create(test_client)
    assert len(_lines(path)) == 1

    # What logrotate does: move it aside, leave a fresh one in its place.
    path.rename(tmp_path / "audit.log.1")
    _create(test_client, target="https://other.example.org")

    assert len(_lines(tmp_path / "audit.log.1")) == 1
    assert len(_lines(path)) == 1
    # The service rotates nothing itself in this mode, so a size limit that
    # would have rolled the file over is not what created the second file.
    assert not (tmp_path / "audit.log.2").exists()


def test_the_service_does_not_also_rotate_a_trail_it_handed_over(tmp_path):
    """Two rotators on one file is how a trail loses records."""
    path = tmp_path / "audit.log"
    test_client = client(
        audit_log=True,
        audit_log_file=str(path),
        audit_log_rotation="external",
        # Small enough that the service's own rotation would have fired many
        # times over, had it been the thing in charge.
        audit_log_max_bytes=100,
        audit_log_backups=1,
    )

    for index in range(8):
        _create(test_client, target=f"https://host{index}.example.com")

    assert len(_lines(path)) == 8
    assert not (tmp_path / "audit.log.1").exists()


def test_an_unrecognised_rotation_setting_stops_the_service_starting(tmp_path):
    """A typo here means either two rotators or none, and neither announces itself."""
    with pytest.raises(ValueError) as error:
        client(
            audit_log=True,
            audit_log_file=str(tmp_path / "audit.log"),
            audit_log_rotation="logrotate",
        )

    assert "COS_WEB_AUDIT_LOG_ROTATION" in str(error.value)
    # The two that are accepted still are.
    for value in ("service", "external"):
        _create(client(audit_log=True, audit_log_file=str(tmp_path / "audit.log"), audit_log_rotation=value))


def test_a_file_created_by_logrotate_is_still_owner_only(tmp_path):
    """The trail's permissions cannot depend on which generation you look at."""
    path = tmp_path / "audit.log"
    test_client = client(
        audit_log=True, audit_log_file=str(path), audit_log_rotation="external"
    )
    _create(test_client)

    path.rename(tmp_path / "audit.log.1")
    _create(test_client, target="https://other.example.org")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
