"""
Whether the scanned domain restricts who may issue it a certificate.

A CAA (Certification Authority Authorization) record is a DNS resource
record, not a TLS one, but it answers the same question the rest of
:mod:`tls` asks about the certificate itself: can anyone with a working CA
account mint a certificate for this name, or has the operator narrowed that
down. RFC 8659 defines the record; this module only checks whether one
exists for the exact name scanned and, if so, whether it authorizes at least
one issuer - it does not judge *which* issuer is named, because that is an
operator's choice, not a finding.

No dependency is added for this. A CAA lookup needs a resource record type
(``TYPE257``) the standard library's own name resolution (``socket.getaddrinfo``,
used everywhere else in this project) cannot ask for, so this module speaks
just enough of the DNS wire format over UDP to send one query and read one
answer back.

**The query goes to the resolver this machine is already configured to use**
(read from ``/etc/resolv.conf``), never to a hardcoded public resolver such
as 1.1.1.1 or 8.8.8.8. Reaching out to a resolver the operator did not
already choose would hand a third party the one thing this project's README
promises never to send anywhere: the address being scanned. When no local
resolver can be found - most notably on Windows, which keeps its
configuration elsewhere - the finding is simply absent, the same way an
unavailable ``openssl`` binary leaves the certificate-policy finding out
of the result rather than guessing at it.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from pathlib import Path
from typing import NamedTuple

from .tls import TlsCheck

LOGGER = logging.getLogger("check_opencloud.caa")

_CAA_RECORD_TYPE = 257
_IN_CLASS = 1
# RFC 8659 section 4.1 makes the property tag case insensitive, so these are
# the canonical lowercase spellings and every parsed tag is folded to match.
# A zone that publishes `Issue "letsencrypt.org"` restricts issuance exactly
# as much as one that publishes `issue`, and must not be reported as unrestricted.
_AUTHORIZING_TAGS = ("issue", "issuewild")
_RESOLV_CONF = Path("/etc/resolv.conf")


class _CaaRecord(NamedTuple):
    tag: str
    value: bytes


def _system_nameservers() -> list[str]:
    """
    The resolver addresses this machine is already configured to use.

    Every other lookup this process makes (connecting to the scanned host at
    all) already goes through one of these, so asking it for a CAA record
    too introduces no new party to the scan.
    """
    try:
        text = _RESOLV_CONF.read_text(encoding="utf-8")
    except OSError:
        return []
    servers = []
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            servers.append(parts[1])
    return servers


def _encode_name(hostname: str) -> bytes:
    """DNS QNAME wire encoding: length-prefixed labels, terminated by a zero byte."""
    encoded = bytearray()
    for label in hostname.rstrip(".").split("."):
        if not label:
            continue
        raw = label.encode("ascii")
        if not 0 < len(raw) <= 63:
            raise ValueError(f"label {label!r} is not a valid DNS label")
        encoded.append(len(raw))
        encoded.extend(raw)
    encoded.append(0)
    return bytes(encoded)


def _build_query(hostname: str, query_id: int) -> bytes:
    header = (
        query_id.to_bytes(2, "big")
        + b"\x01\x00"  # standard query, recursion desired
        + b"\x00\x01"  # QDCOUNT = 1
        + b"\x00\x00\x00\x00\x00\x00"  # ANCOUNT / NSCOUNT / ARCOUNT = 0
    )
    question = (
        _encode_name(hostname)
        + _CAA_RECORD_TYPE.to_bytes(2, "big")
        + _IN_CLASS.to_bytes(2, "big")
    )
    return header + question


def _skip_name(data: bytes, offset: int) -> int:
    """
    Return the offset just past one (possibly compressed) DNS name.

    A compression pointer is always exactly two bytes at the point it
    appears, no matter what it points back to, so resolving the name it
    references is unnecessary just to move the cursor past it.
    """
    while True:
        if offset >= len(data):
            raise ValueError("name runs past the end of the message")
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def _parse_caa_response(data: bytes) -> list[_CaaRecord]:
    """
    Parse a raw DNS response for CAA resource records.

    Raises ``ValueError`` on anything that does not parse cleanly - a
    truncated, malformed or error response is never turned into a guess, it
    is left for the caller to treat as an absent finding.
    """
    if len(data) < 12:
        raise ValueError("response shorter than a DNS header")
    flags = data[2]
    rcode = data[3] & 0x0F
    if flags & 0x02:
        raise ValueError("response was truncated (TC flag set)")
    if rcode != 0:
        raise ValueError(f"DNS response code {rcode}")

    qdcount = int.from_bytes(data[4:6], "big")
    ancount = int.from_bytes(data[6:8], "big")

    offset = 12
    for _ in range(qdcount):
        offset = _skip_name(data, offset) + 4  # QTYPE + QCLASS

    records: list[_CaaRecord] = []
    for _ in range(ancount):
        offset = _skip_name(data, offset)
        if offset + 10 > len(data):
            raise ValueError("resource record header runs past the end of the message")
        rtype = int.from_bytes(data[offset : offset + 2], "big")
        rdlength = int.from_bytes(data[offset + 8 : offset + 10], "big")
        offset += 10
        rdata = data[offset : offset + rdlength]
        if len(rdata) != rdlength:
            raise ValueError("resource record data runs past the end of the message")
        if rtype == _CAA_RECORD_TYPE and len(rdata) >= 2:
            tag_length = rdata[1]
            # Folded here rather than at every comparison: the tag is case
            # insensitive per RFC 8659, so the lowercase spelling is the only
            # one the rest of this module ever has to think about.
            tag = rdata[2 : 2 + tag_length].decode("ascii", errors="replace").lower()
            value = rdata[2 + tag_length :]
            records.append(_CaaRecord(tag, value))
        offset += rdlength
    return records


def _query_caa(
    hostname: str, nameserver: str, timeout: float, *, port: int = 53
) -> list[_CaaRecord]:
    family = socket.AF_INET6 if ":" in nameserver else socket.AF_INET
    query_id = int.from_bytes(os.urandom(2), "big")
    message = _build_query(hostname, query_id)
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(message, (nameserver, port))
        data, _ = sock.recvfrom(4096)
    if len(data) < 2 or data[0:2] != query_id.to_bytes(2, "big"):
        raise ValueError("response id does not match the query")
    return _parse_caa_response(data)


def check_caa_record(hostname: str, timeout: float, *, port: int = 53) -> TlsCheck | None:
    """
    Whether the exact name scanned has a CAA record authorizing an issuer.

    Passes when at least one ``issue`` or ``issuewild`` property is present -
    this only measures that certificate issuance has been restricted to
    *some* set of CAs, never which one, and only for the name as scanned
    rather than walking the RFC 6844/8659 parent-domain fallback chain.
    Returns ``None`` (an unknown, never a pass) for a bare IP address, when
    no local resolver can be found, or when every resolver tried failed to
    answer or answered something this parser could not make sense of.

    ``port`` defaults to the standard DNS port and exists so tests can point
    this at a loopback server instead; nothing in the scanner itself ever
    overrides it.
    """
    candidate = hostname.strip("[]")
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        return None

    nameservers = _system_nameservers()
    if not nameservers:
        LOGGER.debug("No system resolver found; CAA record left unmeasured")
        return None

    for nameserver in nameservers:
        try:
            records = _query_caa(candidate, nameserver, timeout, port=port)
        except (OSError, ValueError, UnicodeError) as exc:
            LOGGER.debug("CAA query to %s via %s failed: %s", candidate, nameserver, exc)
            continue

        authorizing = [record for record in records if record.tag in _AUTHORIZING_TAGS]
        if authorizing:
            plural = "y" if len(authorizing) == 1 else "ies"
            detail = (
                f"CAA record restricts certificate issuance "
                f"({len(authorizing)} entr{plural})"
            )
        else:
            detail = (
                "No CAA record for this name: any publicly trusted CA can "
                "issue a certificate for it"
            )
        return TlsCheck("tlsCaaRecord", "low", bool(authorizing), detail)

    return None
