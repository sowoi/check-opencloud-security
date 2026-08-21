"""Tests for the monitoring-host reference-data refresh command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencloud_local_scan import refresh_data
from opencloud_local_scan.refresh_data import RefreshError
from opencloud_local_scan.versions import RELEASE_SCHEDULE_FILE
from opencloud_local_scan.vulndb import BUNDLED_DB


def test_refresh_data_writes_both_documents_atomically(tmp_path: Path, monkeypatch):
    """A successful refresh gives systemd two complete files to configure."""
    schedule = json.loads(
        RELEASE_SCHEDULE_FILE.read_text()
    )
    advisories = json.loads(
        BUNDLED_DB.read_text()
    )
    monkeypatch.setattr(refresh_data, "fetch_schedule_document", lambda *a: schedule)
    monkeypatch.setattr(refresh_data, "fetch_advisory_document", lambda *a: advisories)

    paths = refresh_data.refresh_data(tmp_path)

    assert paths == (tmp_path / "release_schedule.json", tmp_path / "vulnerabilities.json")
    assert json.loads(paths[0].read_text()) == schedule
    assert json.loads(paths[1].read_text()) == advisories


def test_refresh_data_keeps_existing_files_when_schedule_is_unsafe(
    tmp_path: Path, monkeypatch
):
    """A truncated lifecycle page must not replace a known-good cache."""
    existing = tmp_path / "release_schedule.json"
    existing.write_text("previous\n")
    monkeypatch.setattr(refresh_data, "fetch_schedule_document", lambda *a: {"lines": []})

    with pytest.raises(RefreshError, match="lost a bundled line"):
        refresh_data.refresh_data(tmp_path)

    assert existing.read_text() == "previous\n"
