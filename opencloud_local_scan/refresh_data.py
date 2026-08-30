"""
Refresh the reference data used by a monitoring installation.

By default this reads the two documents from *this project's own repository*
rather than querying OSV and the OpenCloud lifecycle page live, and verifies
a Sigstore attestation over what it read before believing any of it (see
:mod:`opencloud_local_scan.data_signing` and ADR 0027). The files on ``main``
are the ones a human already reviewed and merged - the PRs opened by
``scripts/update_vulnerability_db.py`` and ``scripts/update_release_schedule.py``
- so this closes the gap ADR 0016 and ADR 0017 both name outright: a live
refresh believes whatever the upstream page says, with no review and nothing
to check it against.

Passing ``--schedule-url``/``--advisory-url`` still queries an arbitrary
source the old way, for an air-gapped mirror or a fork. Nothing signs those,
so the structural guards are all that stands behind them and a warning says
so.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import requests

from . import data_signing
from .advisory_source import fetch_advisory_document
from .schedule_source import fetch_schedule_document
from .versions import RELEASE_SCHEDULE_FILE, schedule_from_document
from .vulndb import BUNDLED_DB, parse_document

LOGGER = logging.getLogger("check_opencloud.refresh_data")

#: The repository whose reviewed, attested data this refreshes from.
GITHUB_OWNER = "sowoi"
GITHUB_REPO = "check-opencloud-security"

_RAW_BASE = (
    f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
    "/main/opencloud_local_scan/data"
)
SIGNED_SCHEDULE_URL = f"{_RAW_BASE}/release_schedule.json"
SIGNED_ADVISORY_URL = f"{_RAW_BASE}/vulnerabilities.json"


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


def _fetch_attested_document(url: str, label: str, timeout: int) -> dict[str, Any]:
    """
    Read one reference document from this project's repository, verified.

    A signature that is *present and wrong* is fatal: it is the one outcome
    that means something is actively tampering rather than merely absent, and
    ADR 0016/0017's "a failure changes nothing" rule then leaves the previous
    file exactly where it was. Verification that could not be attempted at
    all - the ``signing`` extra is not installed, the trust root or the
    attestation could not be fetched, nothing is published for this content
    yet - degrades to a warning and the same structural guards that were the
    only check before this existed.
    """
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    content = response.content

    try:
        outcome = data_signing.verify(
            content, owner=GITHUB_OWNER, repo=GITHUB_REPO, timeout=timeout
        )
    except data_signing.SignatureInvalid as exc:
        raise RefreshError(f"the fetched {label} failed signature verification: {exc}") from exc

    if outcome is None:
        LOGGER.debug("Signature verified for the fetched %s", label)
    else:
        LOGGER.warning(
            "Refreshing the %s without verifying its signature: %s. "
            "Install the 'signing' extra (pip install "
            "check-opencloud-security[signing]) to verify it.",
            label,
            outcome.reason,
        )

    try:
        document = json.loads(content)
    except ValueError as exc:
        raise RefreshError(f"{url} did not answer with JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise RefreshError(f"{url} answered with {type(document).__name__}, not an object")
    return document


def refresh_data(
    output_dir: Path,
    *,
    schedule_url: str | None = None,
    advisory_url: str | None = None,
    timeout: int = 30,
) -> tuple[Path, Path]:
    """
    Fetch and validate both reference documents into ``output_dir``.

    With no URL given, each document comes from this project's own repository
    and its Sigstore attestation is verified first. An explicit
    ``schedule_url``/``advisory_url`` queries that source live the way this
    always did - unsigned, and warned about - so an air-gapped mirror or a
    fork keeps working.
    """
    try:
        if schedule_url is None:
            schedule = _fetch_attested_document(
                SIGNED_SCHEDULE_URL, "release schedule", timeout
            )
        else:
            LOGGER.warning(
                "Refreshing the release schedule from %s, which carries no "
                "signature this package can verify; only the structural "
                "guards apply.",
                schedule_url,
            )
            schedule = fetch_schedule_document(schedule_url, timeout)

        # Applied to both paths. Verified provenance says the document is the
        # one this project published; it does not say the document is sane,
        # and ADR 0016's rule that a refresh may never lose a known release
        # line is cheap enough to keep enforcing either way.
        bundled_schedule = json.loads(RELEASE_SCHEDULE_FILE.read_text(encoding="utf-8"))
        candidate = schedule_from_document(schedule)
        bundled = schedule_from_document(bundled_schedule)
        if not set(bundled.lines).issubset(candidate.lines):
            raise RefreshError("the fetched release schedule lost a bundled line")

        if advisory_url is None:
            # The attested document is the complete, reviewed database - not
            # a feed answer to fold into the local one - so it replaces the
            # file wholesale rather than going through merge_document. The
            # merge-only rule that protects a live OSV query from losing an
            # advisory is enforced upstream, in the PR that produced this
            # file, where a human can see what changed.
            advisories = _fetch_attested_document(
                SIGNED_ADVISORY_URL, "advisory database", timeout
            )
        else:
            LOGGER.warning(
                "Refreshing the advisory database from %s, which carries no "
                "signature this package can verify; only the structural "
                "guards apply.",
                advisory_url,
            )
            bundled_advisories = json.loads(BUNDLED_DB.read_text(encoding="utf-8"))
            advisories = fetch_advisory_document(advisory_url, bundled_advisories, timeout)

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
