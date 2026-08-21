"""Refresh the reference data used by a monitoring installation."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .advisory_source import OSV_QUERY_URL, fetch_advisory_document
from .schedule_source import LIFECYCLE_URL, fetch_schedule_document
from .versions import RELEASE_SCHEDULE_FILE, schedule_from_document
from .vulndb import BUNDLED_DB, parse_document


class RefreshError(RuntimeError):
    """The remote data was unavailable or failed validation."""


def _write_json(path: Path, document: dict[str, Any]) -> None:
    """Atomically replace a JSON cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def refresh_data(
    output_dir: Path,
    *,
    schedule_url: str | None = None,
    advisory_url: str | None = None,
    timeout: int = 30,
) -> tuple[Path, Path]:
    """Fetch and validate both reference documents into ``output_dir``."""
    try:
        schedule = fetch_schedule_document(schedule_url or LIFECYCLE_URL, timeout)
        bundled_schedule = json.loads(RELEASE_SCHEDULE_FILE.read_text(encoding="utf-8"))
        candidate = schedule_from_document(schedule)
        bundled = schedule_from_document(bundled_schedule)
        if not set(bundled.lines).issubset(candidate.lines):
            raise RefreshError("the fetched release schedule lost a bundled line")

        bundled_advisories = json.loads(BUNDLED_DB.read_text(encoding="utf-8"))
        advisories = fetch_advisory_document(
            advisory_url or OSV_QUERY_URL, bundled_advisories, timeout
        )
        parsed = parse_document(advisories)
        if not parsed or not all(
            any(introduced or fixed for introduced, fixed in advisory.all_ranges())
            for advisory in parsed
        ):
            raise RefreshError("the fetched advisory database has no usable bounded entries")
    except RefreshError:
        raise
    except Exception as exc:
        raise RefreshError(f"reference-data refresh failed: {exc}") from exc

    schedule_path = output_dir / "release_schedule.json"
    advisory_path = output_dir / "vulnerabilities.json"
    _write_json(schedule_path, schedule)
    _write_json(advisory_path, advisories)
    return schedule_path, advisory_path
