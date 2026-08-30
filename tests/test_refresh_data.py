"""Tests for the monitoring-host reference-data refresh command."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from opencloud_local_scan import data_signing, refresh_data
from opencloud_local_scan.refresh_data import RefreshError
from opencloud_local_scan.versions import RELEASE_SCHEDULE_FILE
from opencloud_local_scan.vulndb import BUNDLED_DB


@pytest.fixture
def bundled_schedule() -> dict:
    return json.loads(RELEASE_SCHEDULE_FILE.read_text())


@pytest.fixture
def bundled_advisories() -> dict:
    return json.loads(BUNDLED_DB.read_text())


class _Response:
    """The parts of a requests response the refresh actually reads."""

    def __init__(self, document: dict) -> None:
        self.content = json.dumps(document).encode()

    def raise_for_status(self) -> None:
        pass


@pytest.fixture
def served(monkeypatch, bundled_schedule, bundled_advisories):
    """Serve the bundled documents over the attested (default) path."""
    documents = {
        refresh_data.SIGNED_SCHEDULE_URL: bundled_schedule,
        refresh_data.SIGNED_ADVISORY_URL: bundled_advisories,
    }

    def _get(url, **_kwargs):
        return _Response(documents[url])

    monkeypatch.setattr(refresh_data.requests, "get", _get)
    return documents


def _verifies(monkeypatch, outcome=None):
    """Make signature verification return a fixed outcome."""
    monkeypatch.setattr(
        refresh_data.data_signing, "verify", lambda *_a, **_k: outcome
    )


# --- the attested default path ---
def test_refresh_data_writes_both_documents_atomically(
    tmp_path: Path, monkeypatch, served, bundled_schedule, bundled_advisories
):
    """A successful refresh gives systemd two complete files to configure."""
    _verifies(monkeypatch)

    paths = refresh_data.refresh_data(tmp_path)

    assert paths == (tmp_path / "release_schedule.json", tmp_path / "vulnerabilities.json")
    assert json.loads(paths[0].read_text()) == bundled_schedule
    assert json.loads(paths[1].read_text()) == bundled_advisories


def test_a_bad_signature_changes_nothing(tmp_path: Path, monkeypatch, served):
    """
    A present-but-wrong signature is the one outcome that means tampering.

    ADR 0016/0017's rule is that a failed refresh leaves the previous data
    exactly where it was, so the existing file must survive untouched.
    """
    existing = tmp_path / "release_schedule.json"
    existing.write_text("previous\n")

    def _raise(*_a, **_k):
        raise data_signing.SignatureInvalid("signed by somebody else")

    monkeypatch.setattr(refresh_data.data_signing, "verify", _raise)

    with pytest.raises(RefreshError, match="failed signature verification"):
        refresh_data.refresh_data(tmp_path)

    assert existing.read_text() == "previous\n"


def test_a_missing_signing_extra_degrades_to_a_warning(
    tmp_path: Path, monkeypatch, served, caplog
):
    """Without the extra the refresh still works, loudly, as it did before."""
    _verifies(
        monkeypatch,
        data_signing.VerificationSkipped("the 'signing' extra (sigstore) is not installed"),
    )

    with caplog.at_level(logging.WARNING):
        paths = refresh_data.refresh_data(tmp_path)

    assert paths[0].exists() and paths[1].exists()
    assert "without verifying its signature" in caplog.text
    assert "sigstore" in caplog.text


def test_the_bundled_line_guard_still_applies_to_verified_data(
    tmp_path: Path, monkeypatch, served, bundled_advisories
):
    """
    Verified provenance says who published a document, not that it is sane.

    A schedule that lost a release line is refused even when its signature
    checks out, because a released line silently disappearing would turn an
    end-of-life instance into an unknown one.
    """
    _verifies(monkeypatch)
    served[refresh_data.SIGNED_SCHEDULE_URL] = {"lines": []}

    with pytest.raises(RefreshError, match="lost a bundled line"):
        refresh_data.refresh_data(tmp_path)


def test_a_non_json_answer_is_refused(tmp_path: Path, monkeypatch, served):
    """A proxy's HTML error page must not become the release schedule."""
    _verifies(monkeypatch)

    class _Html:
        content = b"<html>404</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(refresh_data.requests, "get", lambda *_a, **_k: _Html())

    with pytest.raises(RefreshError, match="did not answer with JSON"):
        refresh_data.refresh_data(tmp_path)


# --- the explicit-URL override path ---
def test_an_explicit_url_is_fetched_live_and_warns(
    tmp_path: Path, monkeypatch, caplog, bundled_schedule, bundled_advisories
):
    """A mirror or fork keeps working, with the loss of assurance stated."""
    monkeypatch.setattr(
        refresh_data, "fetch_schedule_document", lambda *_a: bundled_schedule
    )
    monkeypatch.setattr(
        refresh_data, "fetch_advisory_document", lambda *_a: bundled_advisories
    )

    with caplog.at_level(logging.WARNING):
        paths = refresh_data.refresh_data(
            tmp_path,
            schedule_url="https://mirror.example.com/lifecycle",
            advisory_url="https://mirror.example.com/osv",
        )

    assert paths[0].exists() and paths[1].exists()
    assert "carries no signature this package can verify" in caplog.text
    assert "https://mirror.example.com/lifecycle" in caplog.text
    assert "https://mirror.example.com/osv" in caplog.text


def test_an_explicit_schedule_url_keeps_the_bundled_line_guard(
    tmp_path: Path, monkeypatch
):
    """A truncated lifecycle page must not replace a known-good cache."""
    existing = tmp_path / "release_schedule.json"
    existing.write_text("previous\n")
    monkeypatch.setattr(refresh_data, "fetch_schedule_document", lambda *_a: {"lines": []})

    with pytest.raises(RefreshError, match="lost a bundled line"):
        refresh_data.refresh_data(tmp_path, schedule_url="https://mirror.example.com/x")

    assert existing.read_text() == "previous\n"
