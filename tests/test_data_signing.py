"""
Tests for the Sigstore attestation check over refreshed reference data.

`sigstore` is an optional extra and is deliberately absent from the test
dependency group - the plugin has to keep working without it, which is what
most of these assert. The tests that need the real verifier skip themselves
when it is not installed.
"""

from __future__ import annotations

import hashlib

import pytest
import requests

from opencloud_local_scan import data_signing

needs_sigstore = pytest.mark.skipif(
    not data_signing.is_available(), reason="the 'signing' extra is not installed"
)


class _Response:
    def __init__(self, status_code: int, document: dict | None = None) -> None:
        self.status_code = status_code
        self._document = document or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}")

    def json(self) -> dict:
        return self._document


def test_the_expected_identity_pins_workflow_and_ref():
    """
    The SAN pin is what makes the check mean anything.

    Without it any valid GitHub Actions signature, from any workflow in any
    repository on the platform, would satisfy the verifier.
    """
    identity = data_signing._expected_identity("sowoi", "check-opencloud-security")

    assert identity == (
        "https://github.com/sowoi/check-opencloud-security"
        "/.github/workflows/attest-security-data.yml@refs/heads/main"
    )


def test_verification_is_skipped_without_the_extra(monkeypatch):
    """A monitoring host without the extra keeps refreshing, unverified."""
    monkeypatch.setattr(data_signing, "is_available", lambda: False)

    outcome = data_signing.verify(b"x", owner="sowoi", repo="check-opencloud-security")

    assert isinstance(outcome, data_signing.VerificationSkipped)
    assert "sigstore" in outcome.reason


def test_a_missing_attestation_is_skipped_not_fatal(monkeypatch):
    """
    Content GitHub has no attestation for is unverified, not condemned.

    A commit can be readable from raw.githubusercontent.com before the
    attestation workflow for it has finished publishing.
    """
    monkeypatch.setattr(data_signing, "is_available", lambda: True)
    monkeypatch.setattr(
        data_signing.requests, "get", lambda *_a, **_k: _Response(404)
    )

    outcome = data_signing.verify(b"x", owner="sowoi", repo="check-opencloud-security")

    assert isinstance(outcome, data_signing.VerificationSkipped)
    assert "no attestation" in outcome.reason


def test_an_unreachable_attestation_api_is_skipped_not_fatal(monkeypatch):
    """GitHub being down must not stop a refresh that is otherwise sound."""
    monkeypatch.setattr(data_signing, "is_available", lambda: True)

    def _boom(*_a, **_k):
        raise requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(data_signing.requests, "get", _boom)

    outcome = data_signing.verify(b"x", owner="sowoi", repo="check-opencloud-security")

    assert isinstance(outcome, data_signing.VerificationSkipped)
    assert "could not fetch the attestation" in outcome.reason


def test_the_attestation_is_requested_by_the_content_digest(monkeypatch):
    """The API is keyed by digest; asking for the wrong one proves nothing."""
    monkeypatch.setattr(data_signing, "is_available", lambda: True)
    asked: list[str] = []

    def _get(url, **_kwargs):
        asked.append(url)
        return _Response(404)

    monkeypatch.setattr(data_signing.requests, "get", _get)
    content = b"the exact bytes that were fetched"

    data_signing.verify(content, owner="sowoi", repo="check-opencloud-security")

    expected = (
        "https://api.github.com/repos/sowoi/check-opencloud-security"
        f"/attestations/sha256:{hashlib.sha256(content).hexdigest()}"
    )
    assert asked == [expected]


@needs_sigstore
def test_unreadable_bundles_are_skipped_not_condemned(monkeypatch):
    """A bundle this version cannot parse is not evidence of tampering."""
    monkeypatch.setattr(data_signing, "is_available", lambda: True)
    monkeypatch.setattr(
        data_signing.requests,
        "get",
        lambda *_a, **_k: _Response(200, {"attestations": [{"bundle": {"nonsense": True}}]}),
    )

    outcome = data_signing.verify(b"x", owner="sowoi", repo="check-opencloud-security")

    assert isinstance(outcome, data_signing.VerificationSkipped)
    assert "unreadable" in outcome.reason


@needs_sigstore
def test_a_readable_bundle_that_does_not_verify_is_fatal(monkeypatch):
    """
    A real, parseable attestation that fails the identity pin must raise.

    This is the case that separates "not verified" from "verified as wrong",
    and only the latter is allowed to stop a refresh.
    """
    from sigstore.models import Bundle

    monkeypatch.setattr(data_signing, "is_available", lambda: True)
    monkeypatch.setattr(
        data_signing.requests,
        "get",
        lambda *_a, **_k: _Response(200, {"attestations": [{"bundle": {"stub": True}}]}),
    )
    monkeypatch.setattr(Bundle, "from_json", classmethod(lambda _cls, _raw: object()))
    monkeypatch.setattr(data_signing, "_verify_one_bundle", lambda *_a, **_k: False)

    with pytest.raises(data_signing.SignatureInvalid, match="did not verify"):
        data_signing.verify(b"x", owner="sowoi", repo="check-opencloud-security")
