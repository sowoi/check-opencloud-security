"""
What the scanner learns from the TLS layer, and what it refuses to claim.

Every test here runs against a real TLS server on a loopback port with a
certificate generated for the occasion, rather than against a mock of the
`ssl` module: the whole point of these checks is what a server actually does
during a handshake, and a mock would only ever confirm what we already
believed.
"""

from __future__ import annotations

import socket
import ssl
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencloud_local_scan import hardening, tls

TIMEOUT = 5


def _certificate(
    tmp_path: Path,
    *,
    common_name: str = "localhost",
    alt_names: tuple[str, ...] = ("localhost",),
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> tuple[Path, Path]:
    """Write a self-signed certificate and key, and return their paths."""
    now = datetime.now(timezone.utc)
    not_before = not_before or now - timedelta(days=1)
    not_after = not_after or now + timedelta(days=89)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if alt_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(n) for n in alt_names]),
            critical=False,
        )
    certificate = builder.sign(key, hashes.SHA256())

    certificate_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, key_path


@contextmanager
def _server(certificate_path: Path, key_path: Path):
    """A loopback TLS endpoint that completes handshakes and says nothing."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(certificate_path), str(key_path))
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.settimeout(0.2)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                raw, _ = listener.accept()
            except (TimeoutError, OSError):
                continue
            try:
                with context.wrap_socket(raw, server_side=True) as connection:
                    connection.recv(1)
            except (OSError, ssl.SSLError):
                pass
            finally:
                raw.close()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stop.set()
        worker.join(timeout=5)
        listener.close()


def _ids(inspection: tls.TlsInspection) -> dict[str, bool]:
    """Every check the inspection produced, by identifier."""
    return {
        check.identifier: check.passed
        for check in inspection.checks(min_days=14)
    }


def test_a_self_signed_certificate_is_untrusted_but_still_read(tmp_path):
    """OpenCloud generates one by default, so its dates must survive the failure."""
    certificate_path, key_path = _certificate(tmp_path)
    with _server(certificate_path, key_path) as port:
        inspection = tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )

    assert inspection.reachable is True
    assert inspection.trusted is False
    # The point of the test: an unverified peer returns an empty certificate
    # from CPython, so without the fallback decoder there would be no expiry
    # date at all - the finding below would simply be missing.
    assert inspection.certificate is not None
    assert inspection.certificate.days_remaining == 88
    assert "tlsCertificate" in _ids(inspection)
    assert _ids(inspection)["tlsTrusted"] is False


def test_a_certificate_for_another_name_fails_the_hostname_check(tmp_path):
    """A certificate that does not cover the host is an interception to a client."""
    (tmp_path / "match").mkdir()
    matching = _certificate(tmp_path / "match", alt_names=("localhost",))
    other = _certificate(tmp_path, alt_names=("opencloud.example.com",))

    with _server(*other) as port:
        mismatch = tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )
    assert mismatch.hostname_match is False
    assert _ids(mismatch)["tlsHostname"] is False

    with _server(*matching) as port:
        match = tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )
    assert match.hostname_match is True
    assert _ids(match)["tlsHostname"] is True


def test_an_expired_certificate_says_expired_rather_than_a_negative_countdown(tmp_path):
    """"Expires in -4148 days" is a number; "expired 4148 days ago" is an answer."""
    now = datetime.now(timezone.utc)
    certificate_path, key_path = _certificate(
        tmp_path, not_before=now - timedelta(days=40), not_after=now - timedelta(days=10)
    )
    with _server(certificate_path, key_path) as port:
        inspection = tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )

    detail = next(
        check.detail
        for check in inspection.checks(min_days=14)
        if check.identifier == "tlsCertificate"
    )
    assert "expired 10 day(s) ago" in detail
    assert "expires in" not in detail
    assert _ids(inspection)["tlsCertificate"] is False


def test_a_certificate_issued_for_longer_than_the_public_maximum_is_flagged(tmp_path):
    """A key that stays valid for years stays compromised for years."""
    now = datetime.now(timezone.utc)
    long_lived = _certificate(
        tmp_path, not_before=now - timedelta(days=1), not_after=now + timedelta(days=800)
    )
    with _server(*long_lived) as port:
        inspection = tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )
    assert inspection.certificate is not None
    assert inspection.certificate.lifetime_days == 801
    assert _ids(inspection)["tlsCertificateLifetime"] is False

    short = tmp_path / "short"
    short.mkdir()
    with _server(*_certificate(short)) as port:
        ordinary = tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )
    assert _ids(ordinary)["tlsCertificateLifetime"] is True


def test_a_modern_server_refuses_the_deprecated_protocol_versions(tmp_path):
    """The negotiated version says nothing about what else is still on offer."""
    with _server(*_certificate(tmp_path)) as port:
        inspection = tls.inspect("localhost", port, TIMEOUT, check_stapling=False)

    assert inspection.deprecated_probed, "the probe must actually have run"
    assert inspection.deprecated_accepted == ()
    assert _ids(inspection)["tlsDeprecatedProtocol"] is True


def test_a_version_that_could_not_be_probed_is_never_reported_as_refused():
    """A build of OpenSSL that will not speak TLS 1.0 cannot clear a server of it."""
    unprobed = tls.TlsInspection(host="opencloud.example.com", port=443, reachable=True)
    assert "tlsDeprecatedProtocol" not in _ids(unprobed)

    probed = tls.TlsInspection(
        host="opencloud.example.com",
        port=443,
        reachable=True,
        deprecated_probed=("TLSv1",),
        deprecated_accepted=("TLSv1",),
    )
    assert _ids(probed)["tlsDeprecatedProtocol"] is False


def test_trust_that_was_never_established_is_not_reported_as_untrusted():
    """An endpoint too old to negotiate with is a protocol fault, not a bad certificate."""
    unknown = tls.TlsInspection(
        host="opencloud.example.com", port=443, reachable=True, trusted=None, protocol="TLSv1"
    )
    checks = _ids(unknown)
    assert "tlsTrusted" not in checks
    assert checks["tlsProtocol"] is False

    refused = tls.TlsInspection(host="opencloud.example.com", port=443, reachable=True)
    assert refused.checks(min_days=14) and _ids(refused)["tlsTrusted"] is False


def test_an_unreachable_endpoint_reports_the_handshake_and_nothing_else():
    """Findings about a connection that was never made would all be invented."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    inspection = tls.inspect(
        "127.0.0.1", port, 2, probe_deprecated=False, check_stapling=False
    )

    assert inspection.reachable is False
    checks = inspection.checks(min_days=14)
    assert [check.identifier for check in checks] == ["tlsHandshake"]
    assert checks[0].passed is False


def test_ocsp_is_not_reported_when_the_certificate_names_no_responder(tmp_path):
    """Most authorities publish none any more; failing them all would be noise."""
    with _server(*_certificate(tmp_path)) as port:
        inspection = tls.inspect("localhost", port, TIMEOUT, probe_deprecated=False)

    assert inspection.ocsp_stapled is None
    assert "tlsOcspStapling" not in _ids(inspection)
    assert "nothing to staple" in inspection.ocsp_note

    stapling = tls.TlsInspection(
        host="opencloud.example.com",
        port=443,
        reachable=True,
        ocsp_stapled=False,
        certificate=tls.Certificate(ocsp_urls=("http://ocsp.example.com",)),
    )
    assert _ids(stapling)["tlsOcspStapling"] is False


@pytest.mark.parametrize(
    ("pattern", "hostname", "expected"),
    [
        ("*.example.com", "cloud.example.com", True),
        ("*.example.com", "example.com", False),
        ("*.example.com", "a.b.example.com", False),
        ("cloud.example.com", "CLOUD.EXAMPLE.COM", True),
        ("cloud.example.com", "other.example.com", False),
    ],
)
def test_a_wildcard_name_covers_one_label_and_no_more(pattern, hostname, expected):
    """`*.example.com` is not a licence for the bare domain or a sub-subdomain."""
    certificate = tls.Certificate(alt_names=(pattern,))
    assert tls.covers_hostname(certificate, hostname) is expected


def test_a_certificate_with_no_alternative_names_does_not_cover_anything():
    """Common-name-only certificates have been rejected by clients for years."""
    assert tls.covers_hostname(tls.Certificate(alt_names=()), "opencloud.example.com") is False
    assert (
        tls.covers_hostname(
            tls.Certificate(alt_names=("opencloud.example.com",)), "opencloud.example.com"
        )
        is True
    )


def test_a_chain_verdict_is_withheld_for_a_self_signed_certificate():
    """`tlsTrusted` already reports it; a second finding would double the penalty."""
    self_signed = tls.Certificate(subject="CN=a", issuer="CN=a", self_signed=True)
    assert tls._chain_verdict(False, 18, self_signed, None) is None

    issued = tls.Certificate(subject="CN=a", issuer="CN=Some CA")
    assert tls._chain_verdict(False, 20, issued, None) is False
    assert tls._chain_verdict(True, None, issued, None) is True


def test_every_tls_check_the_scanner_can_report_is_explained(tmp_path):
    """A finding that caps a rating without saying what to do about it is half a report."""
    with _server(*_certificate(tmp_path)) as port:
        reported = set(_ids(tls.inspect("localhost", port, TIMEOUT, check_stapling=False)))
    reported |= {"tlsOcspStapling", "tlsHostname", "tlsChain", "tlsDeprecatedProtocol"}

    for identifier in sorted(reported):
        described = hardening.describe(identifier)
        assert described.title, identifier
        assert "No description is available" not in described.meaning, identifier
        assert described.remediation, identifier


def test_the_hostname_is_checked_before_it_reaches_openssl():
    """Nothing shaped like an option or a shell word may become an argv element."""
    for hostile in ("-connect", "a b", "host;rm -rf /", "host$(id)", "", "x" * 300):
        assert tls._SAFE_HOST.match(hostile) is None, hostile
    for ordinary in ("opencloud.example.com", "127.0.0.1", "[::1]", "host-1.example"):
        assert tls._SAFE_HOST.match(ordinary) is not None, ordinary
