"""
Everything the scanner learns from the TLS layer itself.

The rest of the scan talks HTTP and reads what OpenCloud says about itself.
This module talks TLS and reads what the *server* says before a single byte of
HTTP is exchanged: which protocol version was negotiated, whether deprecated
ones are still accepted, whether the certificate is trusted, whether it
actually covers the name it was served for, how long it is still valid, how
long it was issued for, whether the chain reaches a trusted root without help,
whether a revocation answer is stapled to the handshake, whether the
certificate was published to a Certificate Transparency log, and whether the
session tickets it hands out invite a replayable 0-RTT flight.

Two design notes, because both are easy to get subtly wrong.

**A certificate that fails verification still has to be read.** OpenCloud
generates a self-signed certificate during ``opencloud init`` unless real ones
are configured, so on a large share of instances the certificate is untrusted -
and those are exactly the instances whose expiry date, name coverage and
issuing dates an operator most needs to see. CPython returns an *empty*
dictionary from :meth:`ssl.SSLSocket.getpeercert` when the peer was not
verified, so the certificate is fetched in DER form and decoded by loading it
into a throw-away trust store and reading it back with
:meth:`ssl.SSLContext.get_ca_certs`. That is public API, needs no third-party
dependency and costs no extra connection.

**Nothing here reports a pass it did not measure.** A build of OpenSSL that
refuses to speak TLS 1.0 cannot tell us whether the server would have, and an
``openssl`` binary that is not installed cannot tell us whether a stapled OCSP
response was offered. In both cases the check is left out of the result
entirely rather than recorded as passed: a silent gap is bad, but a green tick
for something nobody looked at is worse.
"""

from __future__ import annotations

import _ssl
import ipaddress
import logging
import os
import re
import shutil
import socket
import ssl
import subprocess  # nosec B404 - only ever `openssl s_client`, argv, no shell
import tempfile
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, NamedTuple

LOGGER = logging.getLogger("check_opencloud.tls")

# Anything below TLS 1.2 has been deprecated by RFC 8996 since 2021. The
# negotiated version alone does not answer the question: a server that speaks
# TLS 1.3 to us may still accept TLS 1.0 from a client that asks for it, and
# it is the oldest version on offer that decides what an attacker can force.
DEPRECATED_VERSIONS: tuple[tuple[str, str], ...] = (
    ("TLSv1", "TLSv1"),
    ("TLSv1.1", "TLSv1_1"),
)
MODERN_VERSIONS = frozenset({"TLSv1.2", "TLSv1.3"})

# The CA/Browser Forum caps publicly trusted certificates at 398 days, and
# every major browser enforces it. A longer one either predates the rule or
# comes from a private CA, and in both cases it stays valid long after a
# compromised key would have been rotated.
MAX_LIFETIME_DAYS = 398

# The scan judges only the suite it actually negotiated.  That is enough to
# catch a server whose normal configuration is weak, without pretending it has
# enumerated every suite the endpoint might offer.  TLS 1.3 names encode the
# authenticated encryption algorithm; its key exchange is always ephemeral.
_WEAK_CIPHER_MARKERS = ("NULL", "RC4", "3DES", "DES-", "MD5", "CCM_8")
_WEAK_CIPHER_SUFFIXES = ("-SHA", "_SHA")
_FORWARD_SECRET_CIPHER_MARKERS = ("ECDHE", "DHE", "TLS_")
_WEAK_SIGNATURE_MARKERS = ("MD5", "SHA1", "SHA-1")
_MIN_RSA_KEY_BITS = 2048
_MIN_EC_KEY_BITS = 256

# OpenSSL's verification result codes, which say considerably more than the
# message they come with. `X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT_LOCALLY` in
# particular is the fingerprint of a chain that stops before it reaches a root
# the client knows - the classic "works in my browser, fails on Android".
_SELF_SIGNED_CODES = frozenset({18, 19})
_MISSING_ISSUER_CODES = frozenset({2, 20})
_HOSTNAME_MISMATCH_CODE = 62
_EXPIRY_CODES = frozenset({9, 10})

# A hostname is only ever placed in an `openssl` argument list after passing
# this, so that no shell metacharacter, option-looking string or whitespace can
# reach the process even though no shell is involved.
_SAFE_HOST = re.compile(r"\A(?!-)[A-Za-z0-9._:\-\[\]]{1,253}\Z")


class TlsCheck(NamedTuple):
    """One TLS finding, in the shape :class:`scanner.Finding` is built from."""

    identifier: str
    severity: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Certificate:
    """The parts of a server certificate this scan has an opinion about."""

    subject: str = ""
    issuer: str = ""
    serial: str = ""
    not_before: str = ""
    not_after: str = ""
    days_remaining: int | None = None
    lifetime_days: int | None = None
    alt_names: tuple[str, ...] = ()
    ocsp_urls: tuple[str, ...] = ()
    self_signed: bool = False
    unparsable_dates: str = ""
    key_type: str = ""
    key_bits: int | None = None
    signature_algorithm: str = ""
    sct_count: int | None = None
    """Embedded signed certificate timestamps; ``None`` when nothing looked."""

    def as_dict(self) -> dict[str, Any]:
        """The certificate as the result document carries it."""
        return {
            "subject": self.subject,
            "issuer": self.issuer,
            "serialNumber": self.serial,
            "notBefore": self.not_before,
            "notAfter": self.not_after,
            "daysRemaining": self.days_remaining,
            "lifetimeDays": self.lifetime_days,
            "altNames": list(self.alt_names),
            "ocspResponders": list(self.ocsp_urls),
            "selfSigned": self.self_signed,
            "keyType": self.key_type,
            "keyBits": self.key_bits,
            "signatureAlgorithm": self.signature_algorithm,
            "sctCount": self.sct_count,
        }


@dataclass(frozen=True)
class TlsInspection:
    """What one TLS endpoint told us, and what that means."""

    host: str
    port: int
    reachable: bool = False
    error: str = ""
    protocol: str = ""
    cipher: str = ""
    cipher_bits: int | None = None
    trusted: bool | None = False
    verify_error: str = ""
    verify_code: int | None = None
    hostname_match: bool | None = None
    chain_complete: bool | None = None
    chain_length: int | None = None
    certificate: Certificate | None = None
    deprecated_accepted: tuple[str, ...] = ()
    deprecated_probed: tuple[str, ...] = ()
    ocsp_stapled: bool | None = None
    ocsp_note: str = ""
    max_early_data: int | None = None
    """The 0-RTT limit the server's session tickets advertise, if it said."""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        """The `tls` block of the result document, in camelCase like the rest."""
        return {
            "host": self.host,
            "port": self.port,
            "reachable": self.reachable,
            "error": self.error,
            "protocol": self.protocol,
            "cipher": self.cipher,
            "cipherBits": self.cipher_bits,
            "trusted": self.trusted,
            "verifyError": self.verify_error,
            "verifyCode": self.verify_code,
            "hostnameMatch": self.hostname_match,
            "chainComplete": self.chain_complete,
            "chainLength": self.chain_length,
            "certificate": self.certificate.as_dict() if self.certificate else None,
            "deprecatedProtocolsAccepted": list(self.deprecated_accepted),
            "deprecatedProtocolsProbed": list(self.deprecated_probed),
            "ocspStapled": self.ocsp_stapled,
            "ocspNote": self.ocsp_note,
            "maxEarlyData": self.max_early_data,
        }

    def checks(self, *, min_days: int, verification_required: bool = True) -> list[TlsCheck]:
        """
        Turn the observations into findings, worst first.

        `verification_required` is false when the operator passed `--insecure`:
        an untrusted certificate is then a deliberate choice and is reported
        without weighing on the rating. It never softens anything else - a
        certificate that expired last week is still a certificate that expired
        last week.
        """
        if not self.reachable:
            return [
                TlsCheck(
                    "tlsHandshake",
                    "high",
                    False,
                    f"TLS handshake with {self.host}:{self.port} failed: {self.error}",
                )
            ]

        checks = [
            TlsCheck("tlsHandshake", "high", True, f"TLS handshake succeeded ({self.protocol})"),
            self._protocol_check(),
        ]
        for candidate in (
            self._trusted_check(verification_required),
            self._deprecated_check(),
            self._hostname_check(),
            self._chain_check(),
            self._cipher_check(),
            *self._certificate_checks(min_days),
            self._ocsp_check(),
            self._transparency_check(),
            self._early_data_check(),
        ):
            if candidate is not None:
                checks.append(candidate)
        return checks

    def _trusted_check(self, verification_required: bool) -> TlsCheck | None:
        """
        Trust, when trust was actually established or actually refused.

        A handshake that never got as far as the certificate - an endpoint
        speaking only a protocol version a modern client will not offer -
        leaves the question open, and the protocol findings already say what
        went wrong. Reporting "untrusted" there would blame the certificate
        for something the certificate had no part in.
        """
        if self.trusted is None:
            return None
        issuer = self.certificate.issuer if self.certificate is not None else ""
        staging = "(staging)" in issuer.lower() or "fake le" in issuer.lower()
        if self.trusted:
            detail = "Certificate chain is trusted"
        elif staging:
            detail = (
                "Certificate was issued by the Let's Encrypt staging CA "
                f"({issuer}); clear TRAEFIK_ACME_CASERVER and issue a production "
                "certificate"
            )
        else:
            detail = (
                "Certificate is not trusted (self-signed or unknown CA): "
                f"{self.verify_error}"
            )
        return TlsCheck(
            "tlsTrusted",
            "high" if verification_required else "low",
            self.trusted or not verification_required,
            detail,
        )

    def _protocol_check(self) -> TlsCheck:
        modern = self.protocol in MODERN_VERSIONS
        suffix = "" if modern else " (TLS 1.2 or newer expected)"
        cipher = f", {self.cipher}" if self.cipher else ""
        return TlsCheck(
            "tlsProtocol", "high", modern, f"Negotiated {self.protocol}{cipher}{suffix}"
        )

    def _deprecated_check(self) -> TlsCheck | None:
        if not self.deprecated_probed:
            return None
        if not self.deprecated_accepted:
            return TlsCheck(
                "tlsDeprecatedProtocol",
                "high",
                True,
                "Refused " + " and ".join(self.deprecated_probed),
            )
        return TlsCheck(
            "tlsDeprecatedProtocol",
            "high",
            False,
            "Still accepts " + " and ".join(self.deprecated_accepted)
            + ", which RFC 8996 deprecated",
        )

    def _hostname_check(self) -> TlsCheck | None:
        if self.hostname_match is None:
            return None
        names = ", ".join((self.certificate.alt_names if self.certificate else ()) or ())
        detail = (
            f"Certificate covers {self.host}"
            if self.hostname_match
            else f"Certificate does not cover {self.host}"
            + (f" (valid for {names})" if names else "")
        )
        return TlsCheck("tlsHostname", "high", self.hostname_match, detail)

    def _chain_check(self) -> TlsCheck | None:
        if self.chain_complete is None:
            return None
        if self.chain_complete:
            return TlsCheck(
                "tlsChain", "medium", True, "The server sends a chain that reaches a trusted root"
            )
        return TlsCheck(
            "tlsChain",
            "medium",
            False,
            "The server does not send a chain reaching a trusted root - an "
            "intermediate certificate is missing, or the issuing CA is private",
        )

    def _cipher_check(self) -> TlsCheck | None:
        """Judge the cipher this connection used, never suites not probed."""
        if not self.cipher:
            return None
        cipher = self.cipher.upper()
        weak = any(marker in cipher for marker in _WEAK_CIPHER_MARKERS) or (
            cipher.endswith(_WEAK_CIPHER_SUFFIXES)
        )
        forward_secret = any(marker in cipher for marker in _FORWARD_SECRET_CIPHER_MARKERS)
        passed = not weak and forward_secret
        if passed:
            detail = f"Negotiated modern cipher suite {self.cipher}"
        elif weak:
            detail = f"Negotiated weak cipher suite {self.cipher}"
        else:
            detail = (
                f"Negotiated {self.cipher}, which does not provide forward secrecy"
            )
        return TlsCheck("tlsCipherSuite", "medium", passed, detail)

    def _certificate_checks(self, min_days: int) -> list[TlsCheck]:
        certificate = self.certificate
        if certificate is None:
            return []
        checks: list[TlsCheck] = []
        if certificate.unparsable_dates:
            checks.append(
                TlsCheck(
                    "tlsCertificate",
                    "medium",
                    False,
                    f"Unparsable certificate date {certificate.unparsable_dates!r}",
                )
            )
        elif certificate.days_remaining is not None:
            days = certificate.days_remaining
            when = (
                f"expired {abs(days)} day(s) ago"
                if days < 0
                else f"expires in {days} day(s)"
            )
            checks.append(
                TlsCheck(
                    "tlsCertificate",
                    "high" if days <= 0 else "medium",
                    days >= min_days,
                    f"Certificate {when} ({certificate.not_after})",
                )
            )
        if certificate.lifetime_days is not None:
            long_lived = certificate.lifetime_days > MAX_LIFETIME_DAYS
            checks.append(
                TlsCheck(
                    "tlsCertificateLifetime",
                    "low",
                    not long_lived,
                    f"Issued for {certificate.lifetime_days} day(s)"
                    + (
                        f", above the {MAX_LIFETIME_DAYS}-day maximum for publicly "
                        "trusted certificates"
                        if long_lived
                        else ""
                    ),
                )
            )
        policy = _certificate_policy(certificate)
        if policy is not None:
            passed, detail = policy
            checks.append(TlsCheck("tlsCertificatePolicy", "medium", passed, detail))
        return checks

    def _ocsp_check(self) -> TlsCheck | None:
        if self.ocsp_stapled is None:
            return None
        return TlsCheck(
            "tlsOcspStapling",
            "low",
            self.ocsp_stapled,
            "The handshake carries a stapled OCSP response"
            if self.ocsp_stapled
            else "No OCSP response is stapled, although the certificate names a "
            f"responder ({', '.join(self.certificate.ocsp_urls if self.certificate else ())})",
        )

    def _transparency_check(self) -> TlsCheck | None:
        """
        Certificate Transparency, but only where it is a fair thing to ask.

        A private or self-signed CA cannot publish to a log, and OpenCloud
        generates a self-signed certificate during ``opencloud init``, so on a
        large share of instances the honest answer is that the question does
        not apply. Asking it anyway would put a red mark next to the one thing
        those operators already know about their certificate. The check is
        therefore limited to a chain that actually reaches a public root -
        where a missing timestamp means Chrome and Safari will refuse the
        certificate outright.
        """
        certificate = self.certificate
        if certificate is None or certificate.sct_count is None:
            return None
        if not self.trusted or certificate.self_signed:
            return None
        count = certificate.sct_count
        return TlsCheck(
            "tlsCertificateTransparency",
            "medium",
            count > 0,
            f"Certificate embeds {count} signed certificate timestamp(s)"
            if count > 0
            else "Certificate embeds no signed certificate timestamps, so it was "
            "never published to a Certificate Transparency log",
        )

    def _early_data_check(self) -> TlsCheck | None:
        if self.max_early_data is None:
            return None
        accepted = self.max_early_data > 0
        return TlsCheck(
            "tlsEarlyData",
            "low",
            not accepted,
            f"Session tickets advertise up to {self.max_early_data} bytes of "
            "replayable 0-RTT early data"
            if accepted
            else "Session tickets permit no early data, so there is no 0-RTT "
            "flight to replay",
        )


class _Handshake(NamedTuple):
    """One completed or failed TLS connection."""

    ok: bool
    peercert: dict[str, Any]
    der: bytes | None
    protocol: str
    cipher: str
    cipher_bits: int | None
    chain_length: int | None
    error: Exception | None


def _connect(
    host: str,
    port: int,
    timeout: float,
    context: ssl.SSLContext,
    connect_host: str | None = None,
) -> _Handshake:
    """Open one TLS connection with the given context and describe the outcome."""
    try:
        raw = socket.create_connection((connect_host or host, port), timeout=timeout)
        with raw, context.wrap_socket(raw, server_hostname=host.strip("[]")) as tls:
            cipher = tls.cipher() or ("", "", None)
            # `get_unverified_chain` counts what the server actually sent
            # and exists only from Python 3.13 on; without it the chain
            # length simply stays unknown.
            unverified = getattr(tls, "get_unverified_chain", None)
            chain = None
            if callable(unverified):
                try:
                    chain = len(unverified() or ())
                except (ssl.SSLError, ValueError):  # pragma: no cover - defensive
                    chain = None
            return _Handshake(
                True,
                dict(tls.getpeercert() or {}),
                tls.getpeercert(binary_form=True),
                tls.version() or "unknown",
                str(cipher[0] or ""),
                cipher[2] if isinstance(cipher[2], int) else None,
                chain,
                None,
            )
    except (OSError, ssl.SSLError) as exc:
        return _Handshake(False, {}, None, "", "", None, None, exc)


def _insecure_context() -> ssl.SSLContext:
    """A context that completes the handshake without judging the certificate."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _decode(der: bytes | None) -> dict[str, Any]:
    """
    Decode a DER certificate into the dictionary `getpeercert` would return.

    CPython hands back an empty dictionary for an unverified peer, which would
    leave every self-signed instance - OpenCloud's own default - without an
    expiry date, a name list or an issuer, and those are the instances whose
    certificate an operator most needs to see.

    ``_ssl._test_decode_cert`` is the decoder ``getpeercert`` itself uses, so
    this produces exactly the same structure rather than a second, subtly
    different one. It is private, it has been there since Python 2.6, and it
    is present in every version this project supports - and if a future one
    drops it, the certificate detail disappears from the report instead of
    turning into a guess. It takes a path, so the certificate is written to a
    short-lived private temporary file and deleted immediately.
    """
    decoder = getattr(_ssl, "_test_decode_cert", None)
    if not der or not callable(decoder):
        return {}
    handle, path = tempfile.mkstemp(suffix=".pem", prefix="cos-cert-")
    try:
        with os.fdopen(handle, "w", encoding="ascii") as pem:
            pem.write(ssl.DER_cert_to_PEM_cert(der))
        return dict(decoder(path) or {})
    except (ssl.SSLError, ValueError, OSError, TypeError) as exc:
        LOGGER.debug("Could not decode the server certificate: %s", exc)
        return {}
    finally:
        try:
            os.unlink(path)
        except OSError:  # pragma: no cover - defensive
            pass


def _name(pairs: Any) -> str:
    """Render the nested tuples `getpeercert` uses for a subject or issuer."""
    parts: list[str] = []
    if isinstance(pairs, Sequence) and not isinstance(pairs, (str, bytes)):
        for relative in pairs:
            if isinstance(relative, Sequence) and not isinstance(relative, (str, bytes)):
                for attribute in relative:
                    if (
                        isinstance(attribute, Sequence)
                        and not isinstance(attribute, (str, bytes))
                        and len(attribute) == 2
                    ):
                        parts.append(f"{attribute[0]}={attribute[1]}")
    return ", ".join(parts)


def _parse_date(value: Any) -> datetime | None:
    """Parse the `'Sep 19 12:25:57 2026 GMT'` format certificates use."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _certificate(
    peercert: Mapping[str, Any], der: bytes | None = None, *, now: datetime | None = None
) -> Certificate | None:
    """Build the certificate view, or nothing when there is no certificate."""
    if not peercert:
        return None
    now = now or datetime.now(timezone.utc)
    not_before_raw = peercert.get("notBefore")
    not_after_raw = peercert.get("notAfter")
    not_before = _parse_date(not_before_raw)
    not_after = _parse_date(not_after_raw)

    unparsable = ""
    if isinstance(not_after_raw, str) and not_after is None:
        unparsable = not_after_raw

    lifetime = (not_after - not_before).days if not_before and not_after else None
    alt_names = tuple(
        str(value)
        for kind, value in peercert.get("subjectAltName", ())
        if isinstance(kind, str) and kind in {"DNS", "IP Address"}
    )
    subject = _name(peercert.get("subject"))
    issuer = _name(peercert.get("issuer"))
    certificate = Certificate(
        subject=subject,
        issuer=issuer,
        serial=str(peercert.get("serialNumber") or ""),
        not_before=str(not_before_raw or ""),
        not_after=str(not_after_raw or ""),
        # Truncated towards zero rather than floored, so a certificate that
        # went out of date ten days and one minute ago is ten days gone and
        # not eleven.
        days_remaining=(
            int((not_after - now).total_seconds() // 86400)
            if not_after and not_after >= now
            else (-int((now - not_after).total_seconds() // 86400) if not_after else None)
        ),
        lifetime_days=lifetime,
        alt_names=alt_names,
        ocsp_urls=tuple(str(url) for url in peercert.get("OCSP", ()) or ()),
        self_signed=bool(subject) and subject == issuer,
        unparsable_dates=unparsable,
    )
    details = _certificate_details(der)
    return replace(
        certificate,
        key_type=details.key_type,
        key_bits=details.key_bits,
        signature_algorithm=details.signature_algorithm,
        sct_count=details.sct_count,
    )


def _certificate_policy(certificate: Certificate) -> tuple[bool, str] | None:
    """Return an actionable key/signature verdict when both facts are known."""
    if not certificate.key_type or certificate.key_bits is None or not certificate.signature_algorithm:
        return None
    key_type = certificate.key_type.upper()
    signature = certificate.signature_algorithm.upper()
    weak_key = (key_type == "RSA" and certificate.key_bits < _MIN_RSA_KEY_BITS) or (
        key_type in {"EC", "ECDSA"} and certificate.key_bits < _MIN_EC_KEY_BITS
    )
    weak_signature = any(marker in signature for marker in _WEAK_SIGNATURE_MARKERS)
    if not weak_key and not weak_signature:
        return (
            True,
            (
                f"Certificate uses a {certificate.key_bits}-bit {certificate.key_type} key "
                f"and {certificate.signature_algorithm}"
            ),
        )
    problems: list[str] = []
    if weak_key:
        problems.append(f"{certificate.key_bits}-bit {certificate.key_type} key")
    if weak_signature:
        problems.append(f"{certificate.signature_algorithm} signature")
    return False, "Certificate uses weak " + " and ".join(problems)


class _CertificateDetails(NamedTuple):
    """What ``openssl x509 -text`` adds to what Python's ``ssl`` exposes."""

    key_type: str = ""
    key_bits: int | None = None
    signature_algorithm: str = ""
    sct_count: int | None = None


def _certificate_details(der: bytes | None) -> _CertificateDetails:
    """Read key, signature and transparency facts with OpenSSL, or leave them unknown.

    Python's ``ssl`` exposes the certificate fields needed for validity and
    hostname checks but not its public-key algorithm, its signature algorithm
    or its embedded signed certificate timestamps.  OpenSSL is already the
    optional mechanism used for OCSP stapling; if it is absent or cannot parse
    the DER, those checks are absent rather than green.
    """
    binary = shutil.which("openssl")
    if not der or binary is None:
        return _CertificateDetails()
    try:
        completed = subprocess.run(  # nosec B603 - fixed argv, DER on stdin
            [binary, "x509", "-inform", "DER", "-noout", "-text"],
            input=der,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.debug("Could not inspect certificate policy: %s", exc)
        return _CertificateDetails()
    if completed.returncode:
        return _CertificateDetails()
    text = completed.stdout.decode("utf-8", "replace")
    key_match = re.search(r"Public Key Algorithm:\s*([^\n]+)", text)
    bits_match = re.search(r"Public-Key:\s*\((\d+) bit\)", text)
    signature_match = re.search(r"Signature Algorithm:\s*([^\n]+)", text)
    raw_key_type = key_match.group(1).strip().lower() if key_match else ""
    key_type = (
        "RSA"
        if "rsa" in raw_key_type
        else "EC"
        if "ec" in raw_key_type
        else "Ed25519"
        if "ed25519" in raw_key_type
        else "Ed448"
        if "ed448" in raw_key_type
        else ""
    )
    return _CertificateDetails(
        key_type,
        int(bits_match.group(1)) if bits_match else None,
        signature_match.group(1).strip() if signature_match else "",
        _sct_count(text),
    )


# `openssl x509 -text` prints the CT extension under one of two names
# depending on whether the certificate is a precertificate, then one
# 'Signed Certificate Timestamp:' block per timestamp inside it.
_SCT_EXTENSION = re.compile(
    r"^\s*(?:CT Precertificate SCTs|CT Certificate SCTs):\s*$", re.MULTILINE
)
_SCT_ENTRY = re.compile(r"^\s*Signed Certificate Timestamp:\s*$", re.MULTILINE)
# Any other extension heading ends the CT block. Headings sit at a shallower
# indent than the entries they contain and always end in a colon.
_EXTENSION_HEADING = re.compile(r"^ {8}\S[^\n]*:\s*$", re.MULTILINE)


def _sct_count(text: str) -> int | None:
    """
    Count the signed certificate timestamps embedded in the certificate.

    ``None`` when this OpenSSL did not print a CT extension at all, which does
    not distinguish "no timestamps" from "this build does not decode them" -
    and a green tick for something nobody looked at is what this module exists
    not to produce. Zero is only ever reported for an extension that is
    present and empty.
    """
    extension = _SCT_EXTENSION.search(text)
    if extension is None:
        return None
    rest = text[extension.end():]
    following = _EXTENSION_HEADING.search(rest)
    block = rest[: following.start()] if following else rest
    return len(_SCT_ENTRY.findall(block))


def _matches(pattern: str, hostname: str) -> bool:
    """One certificate name against one hostname, wildcards included."""
    pattern = pattern.lower().rstrip(".")
    hostname = hostname.lower().rstrip(".")
    if not pattern:
        return False
    if not pattern.startswith("*."):
        return pattern == hostname
    # A wildcard covers exactly one label, and never the leftmost label of a
    # bare domain: `*.example.com` matches `a.example.com`, not `example.com`
    # and not `a.b.example.com`.
    suffix = pattern[1:]
    if not hostname.endswith(suffix):
        return False
    head = hostname[: -len(suffix)]
    return bool(head) and "." not in head


def covers_hostname(certificate: Certificate | None, hostname: str) -> bool | None:
    """
    Whether the certificate is valid for this name, or `None` if unknowable.

    Checked here rather than left to OpenSSL because the interesting case is
    the certificate that already failed verification for another reason: an
    untrusted chain stops the handshake before the name is ever compared, and
    "self-signed for localhost, served for a real domain" is worth saying out
    loud.
    """
    if certificate is None:
        return None
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        address = None  # type: ignore[assignment]
    names = certificate.alt_names
    if not names:
        # No subjectAltName at all. Every client has rejected common-name-only
        # certificates for years, so this is a mismatch rather than a fallback.
        return False
    if address is not None:
        return any(_same_address(name, address) for name in names)
    return any(_matches(name, hostname) for name in names)


def _same_address(name: str, address: Any) -> bool:
    """Compare a certificate entry with an IP literal, tolerating junk."""
    try:
        return ipaddress.ip_address(name) == address
    except ValueError:
        return False


def _legacy_context(version_name: str) -> ssl.SSLContext | None:
    """
    A context pinned to one deprecated TLS version, or nothing.

    Nothing means this OpenSSL build will not speak that version at all, in
    which case the server can never be asked and no conclusion may be drawn.
    """
    attribute = getattr(ssl.TLSVersion, version_name, None)
    if attribute is None:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with warnings.catch_warnings():
            # Referring to TLS 1.0 and 1.1 is deprecated in Python, which is
            # precisely why it is worth asking whether a server still offers them.
            warnings.simplefilter("ignore", DeprecationWarning)
            context.minimum_version = attribute
            context.maximum_version = attribute
        # Modern OpenSSL security levels refuse the old ciphers outright, and
        # a build without them cannot answer the question.
        context.set_ciphers("ALL:@SECLEVEL=0")
    except (ValueError, ssl.SSLError, OSError):
        return None
    return context


def _accepts(
    host: str,
    port: int,
    timeout: float,
    version_name: str,
    connect_host: str | None = None,
) -> bool | None:
    """Whether the server completes a handshake pinned to one old TLS version."""
    context = _legacy_context(version_name)
    if context is None:
        return None
    handshake = _connect(host, port, timeout, context, connect_host)
    if handshake.ok:
        return True
    if isinstance(handshake.error, ssl.SSLError):
        return False
    # A refused connection or a timeout says nothing about protocol support.
    return None


def _legacy_handshake(
    host: str, port: int, timeout: float, connect_host: str | None = None
) -> tuple[str, _Handshake] | None:
    """
    Reach a server that speaks nothing a modern client will offer.

    Python's default context starts at TLS 1.2, so an endpoint stuck on TLS
    1.0 looks identical to one that is down. Reporting it as unreachable would
    hide the worst configuration this module can find behind the mildest
    message it has, so the old versions are tried before giving up.
    """
    for label, attribute in DEPRECATED_VERSIONS:
        context = _legacy_context(attribute)
        if context is None:
            continue
        handshake = _connect(host, port, timeout, context, connect_host)
        if handshake.ok:
            return label, handshake
    return None


class _ClientProbe(NamedTuple):
    """What one `openssl s_client` handshake told us."""

    stapled: bool | None = None
    stapling_note: str = ""
    max_early_data: int | None = None


# `openssl s_client` prints the server's advertised 0-RTT limit in the
# SSL-Session block it dumps after the handshake. A TLS 1.2 server never
# mentions it, and neither does a TLS 1.3 one whose tickets forbid early data
# on some builds - in both cases the question stays unanswered rather than
# being answered optimistically.
_MAX_EARLY_DATA = re.compile(r"^\s*Max Early Data:\s*(\d+)\s*$", re.MULTILINE)


def _client_probe(
    host: str, port: int, timeout: float, connect_host: str | None = None
) -> _ClientProbe:
    """
    Ask `openssl s_client` what a real client sees: stapling, and early data.

    Python's `ssl` module exposes no way to request the `status_request`
    extension, and under TLS 1.3 the response travels inside the encrypted
    handshake, so no amount of socket parsing substitutes for a real client.
    The same handshake carries the session tickets whose `Max Early Data`
    limit says whether a 0-RTT flight would be accepted, so both facts come
    from one connection rather than two. Without the binary both checks are
    skipped rather than guessed.
    """
    binary = shutil.which("openssl")
    if binary is None:
        return _ClientProbe(
            None, "openssl is not installed, so stapling could not be checked"
        )
    if not _SAFE_HOST.match(host):
        return _ClientProbe(None, "hostname not in a form safe to hand to openssl")
    destination = connect_host or host
    if ":" in destination and not destination.startswith("["):
        destination = f"[{destination}]"
    command = [
        binary,
        "s_client",
        "-connect",
        f"{destination}:{port}",
        "-servername",
        host.strip("[]"),
        "-status",
    ]
    try:
        completed = subprocess.run(  # nosec B603 - fixed argv, no shell, validated host
            command,
            input=b"",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _ClientProbe(None, f"openssl could not be run: {exc}")
    output = completed.stdout.decode("utf-8", "replace")
    early = _MAX_EARLY_DATA.search(output)
    max_early_data = int(early.group(1)) if early else None
    if "OCSP response: no response sent" in output:
        return _ClientProbe(False, "", max_early_data)
    if "OCSP Response Status: successful" in output:
        return _ClientProbe(True, "", max_early_data)
    return _ClientProbe(None, "openssl gave no verdict on stapling", max_early_data)


def inspect(
    host: str,
    port: int,
    timeout: float,
    *,
    probe_deprecated: bool = True,
    check_stapling: bool = True,
    connect_host: str | None = None,
    ca_file: str | None = None,
) -> TlsInspection:
    """
    Look at one TLS endpoint and report everything worth reporting.

    One connection is enough when the certificate is trusted. An untrusted one
    costs a second, unverified, connection so that its dates and names can
    still be read, plus one short-lived connection per deprecated protocol
    version that is probed.

    ``check_stapling`` gates the ``openssl s_client`` handshake, which answers
    two questions rather than one: whether an OCSP response is stapled, and
    what early-data limit the server's session tickets advertise. The name is
    kept for the callers that already pass it.
    """
    try:
        verified_context = ssl.create_default_context(cafile=ca_file)
    except (OSError, ssl.SSLError) as exc:
        return TlsInspection(
            host=host, port=port, reachable=False, error=f"Could not load CA bundle: {exc}"
        )
    verified = _connect(host, port, timeout, verified_context, connect_host)
    handshake = verified
    trusted = verified.ok
    verify_error = ""
    verify_code: int | None = None
    forced = ""

    trusted_value: bool | None = trusted
    if not verified.ok:
        error = verified.error
        verify_error = str(error)
        if isinstance(error, ssl.SSLCertVerificationError):
            verify_code = error.verify_code
        else:
            # The handshake failed before the certificate was ever judged.
            trusted_value = None
        handshake = _connect(host, port, timeout, _insecure_context(), connect_host)
        if not handshake.ok:
            fallback = _legacy_handshake(host, port, timeout, connect_host)
            if fallback is None:
                return TlsInspection(
                    host=host, port=port, reachable=False, error=str(handshake.error or error)
                )
            forced, handshake = fallback

    peercert = handshake.peercert or _decode(handshake.der)
    certificate = _certificate(peercert, handshake.der)

    deprecated_probed: list[str] = []
    deprecated_accepted: list[str] = []
    if forced:
        # Already proved by the connection this inspection is standing on.
        deprecated_probed.append(forced)
        deprecated_accepted.append(forced)
    if probe_deprecated:
        for label, attribute in DEPRECATED_VERSIONS:
            if label in deprecated_probed:
                continue
            accepted = _accepts(host, port, timeout, attribute, connect_host)
            if accepted is None:
                continue
            deprecated_probed.append(label)
            if accepted:
                deprecated_accepted.append(label)

    stapled: bool | None = None
    note = ""
    max_early_data: int | None = None
    if check_stapling and certificate is not None:
        probe = _client_probe(host, port, timeout, connect_host)
        max_early_data = probe.max_early_data
        if certificate.ocsp_urls:
            stapled, note = probe.stapled, probe.stapling_note
        else:
            # Nothing to staple, but the same handshake still answered the
            # early-data question, which is why the probe ran at all.
            note = "The certificate names no OCSP responder, so there is nothing to staple"

    return TlsInspection(
        host=host,
        port=port,
        reachable=True,
        protocol=handshake.protocol,
        cipher=handshake.cipher,
        cipher_bits=handshake.cipher_bits,
        trusted=trusted_value,
        verify_error=verify_error,
        verify_code=verify_code,
        hostname_match=_hostname_verdict(trusted_value, verify_code, certificate, host),
        chain_complete=_chain_verdict(
            trusted_value, verify_code, certificate, handshake.chain_length
        ),
        chain_length=handshake.chain_length,
        certificate=certificate,
        deprecated_accepted=tuple(deprecated_accepted),
        deprecated_probed=tuple(deprecated_probed),
        ocsp_stapled=stapled,
        ocsp_note=note,
        max_early_data=max_early_data,
    )


def _hostname_verdict(
    trusted: bool | None, verify_code: int | None, certificate: Certificate | None, host: str
) -> bool | None:
    """A trusted handshake proves the name matched; otherwise compare ourselves."""
    if trusted:
        return True
    if verify_code == _HOSTNAME_MISMATCH_CODE:
        return False
    return covers_hostname(certificate, host)


def _chain_verdict(
    trusted: bool | None,
    verify_code: int | None,
    certificate: Certificate | None,
    chain_length: int | None,
) -> bool | None:
    """
    Whether the server sent enough certificates to reach a trusted root.

    A trusted handshake answers yes by definition - OpenSSL does not fetch
    missing intermediates. A self-signed certificate makes the question
    meaningless and is already reported by `tlsTrusted`, so it answers nothing
    rather than piling a second finding onto one misconfiguration.
    """
    if trusted:
        return True
    if trusted is None:
        return None
    if verify_code in _SELF_SIGNED_CODES:
        return None
    if certificate is not None and certificate.self_signed:
        return None
    if verify_code in _MISSING_ISSUER_CODES:
        return False
    if verify_code in _EXPIRY_CODES or verify_code == _HOSTNAME_MISMATCH_CODE:
        # The chain was walked to the end; something else about it was wrong.
        return True
    if chain_length is not None and chain_length <= 1:
        return False
    return None


__all__ = [
    "MAX_LIFETIME_DAYS",
    "Certificate",
    "TlsCheck",
    "TlsInspection",
    "covers_hostname",
    "inspect",
]
