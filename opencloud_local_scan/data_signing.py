"""
Verify that a fetched reference-data file really came from this project's own
release pipeline, using Sigstore keyless attestation - never a private key
this project would have to hold and could leak.

``.github/workflows/attest-security-data.yml`` runs ``actions/attest-build-
provenance`` against ``opencloud_local_scan/data/vulnerabilities.json`` and
``release_schedule.json`` on every push to ``main`` that changes them - after
the same human review every data update already goes through via the PR each
of ``scripts/update_vulnerability_db.py``/``update_release_schedule.py``
opens. That attestation is published under GitHub's public attestations API,
keyed by the file's SHA-256 digest; this module fetches it back and verifies
it names *this* repository's own workflow as the signer, not merely some
GitHub Actions run anywhere.

``sigstore`` (the PyPI package) is an optional extra - ``pip install
check-opencloud-security[signing]`` - because it pulls in a dozen transitive
dependencies a monitoring host installing the plugin from cron has no other
use for. Every function here degrades to returning :class:`VerificationSkipped`
rather than raising when the extra is missing; the caller decides whether
that is acceptable (see :mod:`opencloud_local_scan.refresh_data`).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

LOGGER = logging.getLogger("check_opencloud.data_signing")

#: The GitHub Actions OIDC issuer every attestation must have been signed
#: under - anything else is not GitHub Actions at all.
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"

#: The one workflow, on the one ref, allowed to sign this project's data.
#: A reusable/matrix build would need more than a ref here; this project's
#: signing workflow is neither.
SIGNING_WORKFLOW_REF = "refs/heads/main"
SIGNING_WORKFLOW_PATH = ".github/workflows/attest-security-data.yml"

DEFAULT_TIMEOUT_SECONDS = 30


class SignatureInvalid(RuntimeError):
    """An attestation was found, but did not verify against the pinned identity."""


@dataclass(frozen=True)
class VerificationSkipped:
    """
    Verification was not attempted, for a reason that is not itself a sign of
    tampering - the caller falls back to structural-only checks and logs why.
    """

    reason: str


def is_available() -> bool:
    """Whether the `sigstore` extra is installed."""
    try:
        import sigstore.verify  # noqa: F401
    except ImportError:
        return False
    return True


def _expected_identity(owner: str, repo: str) -> str:
    """The certificate SAN this project's signing workflow always carries."""
    return (
        f"https://github.com/{owner}/{repo}/{SIGNING_WORKFLOW_PATH}"
        f"@{SIGNING_WORKFLOW_REF}"
    )


def _fetch_attestation_bundles(
    owner: str, repo: str, digest_hex: str, *, timeout: int
) -> list[dict[str, Any]]:
    """
    Fetch every attestation GitHub has published for this digest.

    Returns an empty list when none exist yet - not itself an error: a
    just-merged commit can be read back from raw.githubusercontent.com
    before the attestation for it has finished publishing.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/attestations/sha256:{digest_hex}"
    response = requests.get(
        url,
        headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        timeout=timeout,
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    document = response.json()
    bundles = document.get("attestations") or []
    return [entry["bundle"] for entry in bundles if isinstance(entry, dict) and "bundle" in entry]


def verify(
    content: bytes,
    *,
    owner: str,
    repo: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> VerificationSkipped | None:
    """
    Verify that ``content`` (the exact bytes fetched from
    ``raw.githubusercontent.com``) was attested by this repository's own
    signing workflow.

    Returns ``None`` on a verified match. Returns :class:`VerificationSkipped`
    when verification could not be attempted for a reason unrelated to
    tampering (extra missing, network/TUF error, no attestation published
    yet). Raises :class:`SignatureInvalid` only when an attestation was
    actually found and did not verify against the pinned identity - the one
    case that means something is actively wrong, not merely unverified.
    """
    if not is_available():
        return VerificationSkipped("the 'signing' extra (sigstore) is not installed")

    digest_hex = hashlib.sha256(content).hexdigest()
    try:
        bundles = _fetch_attestation_bundles(owner, repo, digest_hex, timeout=timeout)
    except (requests.exceptions.RequestException, ValueError) as exc:
        return VerificationSkipped(f"could not fetch the attestation: {exc}")

    if not bundles:
        return VerificationSkipped("no attestation has been published for this content yet")

    # Imported only once there is something to check: sigstore pulls in a
    # dozen transitive dependencies, and there is no reason to pay for that
    # on a refresh whose attestation has not been published yet.
    try:
        from sigstore.errors import Error as SigstoreError
        from sigstore.models import Bundle, InvalidBundle
        from sigstore.verify import Verifier
        from sigstore.verify.policy import Identity
    except ImportError as exc:  # is_available() lied - a broken partial install
        return VerificationSkipped(f"the 'signing' extra is not usable: {exc}")

    policy = Identity(
        identity=_expected_identity(owner, repo),
        issuer=GITHUB_ISSUER,
    )
    try:
        verifier = Verifier.production()
    except (SigstoreError, OSError) as exc:
        # A TUF refresh that could not reach or validate the trust root is a
        # network or cache problem, not evidence about this content.
        return VerificationSkipped(f"could not load the Sigstore trust root: {exc}")

    # actions/attest-build-provenance publishes a DSSE-wrapped in-toto
    # statement, not a plain message-signature bundle - verify_dsse is the
    # method for that shape. Several bundles can exist for one digest (this
    # project also attests an SBOM alongside build provenance); a malformed
    # one is skipped in favor of the next, but a *readable* bundle that fails
    # identity or subject-digest verification means something is actively
    # wrong and is reported immediately rather than silently skipped.
    skipped_all_malformed = True
    for raw_bundle in bundles:
        try:
            bundle = Bundle.from_json(json.dumps(raw_bundle))
        except (InvalidBundle, ValueError) as exc:
            LOGGER.debug("Skipping an unparseable attestation bundle: %s", exc)
            continue
        skipped_all_malformed = False
        if _verify_one_bundle(verifier, bundle, policy, digest_hex):
            return None

    if skipped_all_malformed:
        return VerificationSkipped("every published attestation bundle was unreadable")
    raise SignatureInvalid(
        f"an attestation for this content exists but did not verify against "
        f"{owner}/{repo}'s signing workflow"
    )


def _verify_one_bundle(verifier: Any, bundle: Any, policy: Any, digest_hex: str) -> bool:
    """
    Verify one DSSE-wrapped in-toto attestation bundle.

    ``verify_dsse`` only proves who signed the envelope - unlike
    ``verify_artifact``, it does not check what the envelope is about, so the
    statement's own subject digest is checked against ``digest_hex`` here.
    Querying GitHub's API by digest already scopes the response to this
    content, but that trusts the API's own indexing; checking the signed
    statement itself does not.
    """
    from sigstore.errors import VerificationError

    try:
        media_type, payload = verifier.verify_dsse(bundle, policy)
    except VerificationError:
        return False
    if media_type != "application/vnd.in-toto+json":
        return False
    statement = json.loads(payload)
    subjects = statement.get("subject") or []
    return any(
        isinstance(subject, dict) and subject.get("digest", {}).get("sha256") == digest_hex
        for subject in subjects
    )
