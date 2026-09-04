"""
Just enough of the DNS wire format to ask one question and read one answer.

Two of this scanner's findings are facts about the zone rather than about the
instance: whether a CAA record restricts certificate issuance (:mod:`caa`)
and whether the zone is signed (:mod:`dnssec`). Neither record type can be
asked for through ``socket.getaddrinfo``, which answers address lookups only,
so this module speaks the protocol directly over UDP using nothing but
``socket``.

**Every query goes to the resolver this machine is already configured to
use**, read from ``/etc/resolv.conf``, never to a hardcoded public resolver
such as 1.1.1.1 or 8.8.8.8. Reaching out to a resolver the operator did not
already choose would hand a third party the one thing this project's README
promises never to send anywhere: the address being scanned. When no local
resolver can be found - most notably on Windows, which keeps its
configuration elsewhere - the caller reports no finding at all rather than
guessing at one.

Nothing here interprets a record. Parsing stops at "this is a resource record
of this type, and these are its bytes"; what a CAA property or an RRSIG means
belongs to the module that asked for it. Every malformed, truncated or error
response raises :class:`ValueError`, because a lookup that did not work is an
unknown, never a finding. See ADR 0024 and ADR 0038.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from typing import NamedTuple

__all__ = [
    "IN_CLASS",
    "TYPE_A",
    "TYPE_CAA",
    "TYPE_OPT",
    "TYPE_RRSIG",
    "Header",
    "Record",
    "ask",
    "build_query",
    "encode_name",
    "is_ip_literal",
    "read_header",
    "read_records",
    "skip_name",
    "skip_questions",
    "system_nameservers",
]

IN_CLASS = 1

TYPE_A = 1
TYPE_OPT = 41
TYPE_RRSIG = 46
TYPE_CAA = 257

# The advertised UDP payload size of an EDNS0 query. 1232 is the figure the
# DNS Flag Day 2020 consensus settled on: large enough for a signed answer,
# small enough to stay under the IPv6 minimum MTU and out of fragmentation,
# which is where EDNS0 responses go missing in practice.
_EDNS_PAYLOAD_SIZE = 1232

# The DO ("DNSSEC OK") bit, RFC 3225. It lives in the OPT record's TTL field
# rather than its data, which is why a query that wants signatures has to
# build the record rather than set a header flag.
_EDNS_DNSSEC_OK = 0x8000

RESOLV_CONF = Path("/etc/resolv.conf")


class Header(NamedTuple):
    """The twelve bytes every DNS message starts with."""

    flags_high: int
    flags_low: int
    qdcount: int
    ancount: int
    nscount: int
    arcount: int

    @property
    def truncated(self) -> bool:
        """The TC bit: the answer did not fit and this is only part of it."""
        return bool(self.flags_high & 0x02)

    @property
    def authentic_data(self) -> bool:
        """
        The AD bit: the resolver validated this answer against DNSSEC.

        It says something about the resolver as much as about the zone - a
        resolver that does not validate never sets it, however well signed
        the zone is. :mod:`dnssec` is what draws that distinction.
        """
        return bool(self.flags_low & 0x20)

    @property
    def rcode(self) -> int:
        return self.flags_low & 0x0F


class Record(NamedTuple):
    """One resource record, unparsed beyond its type, TTL and data."""

    rtype: int
    ttl: int
    rdata: bytes

    @property
    def dnssec_ok(self) -> bool:
        """
        For an OPT record, whether the DO bit is set.

        In a response this is the resolver echoing back that it understood a
        request for signatures, which is the difference between "this zone is
        unsigned" and "this resolver would not have told us either way".
        """
        return self.rtype == TYPE_OPT and bool(self.ttl & _EDNS_DNSSEC_OK)


def system_nameservers() -> list[str]:
    """
    The resolver addresses this machine is already configured to use.

    Every other lookup this process makes (connecting to the scanned host at
    all) already goes through one of these, so asking it for another record
    type introduces no new party to the scan.
    """
    try:
        text = RESOLV_CONF.read_text(encoding="utf-8")
    except OSError:
        return []
    servers = []
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            servers.append(parts[1])
    return servers


def is_ip_literal(hostname: str) -> bool:
    """Whether the target is an address rather than a name worth looking up."""
    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return True


def encode_name(hostname: str) -> bytes:
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


def build_query(
    hostname: str, qtype: int, query_id: int, *, dnssec_ok: bool = False
) -> bytes:
    """
    One standard recursive query for one name and type.

    ``dnssec_ok`` appends the EDNS0 OPT record that asks the resolver for
    signatures and for its validation verdict. It is a separate record rather
    than a header flag, so a query without it is byte-for-byte the plain
    query it always was.
    """
    additional = _opt_record() if dnssec_ok else b""
    header = (
        query_id.to_bytes(2, "big")
        + b"\x01\x00"  # standard query, recursion desired
        + b"\x00\x01"  # QDCOUNT = 1
        + b"\x00\x00"  # ANCOUNT = 0
        + b"\x00\x00"  # NSCOUNT = 0
        + (b"\x00\x01" if dnssec_ok else b"\x00\x00")  # ARCOUNT
    )
    question = (
        encode_name(hostname) + qtype.to_bytes(2, "big") + IN_CLASS.to_bytes(2, "big")
    )
    return header + question + additional


def _opt_record() -> bytes:
    """The EDNS0 pseudo-record carrying the DO bit, RFC 6891 section 6.1.2."""
    return (
        b"\x00"  # empty (root) name
        + TYPE_OPT.to_bytes(2, "big")
        + _EDNS_PAYLOAD_SIZE.to_bytes(2, "big")  # class: UDP payload size
        + (_EDNS_DNSSEC_OK).to_bytes(4, "big")  # TTL: extended rcode, version, DO
        + b"\x00\x00"  # RDLENGTH = 0
    )


def skip_name(data: bytes, offset: int) -> int:
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


def read_header(data: bytes) -> Header:
    """
    Parse and vet the message header.

    Raises ``ValueError`` for anything the caller must not turn into a
    finding: a runt message, a truncated answer, or a non-zero response code.
    """
    if len(data) < 12:
        raise ValueError("response shorter than a DNS header")
    header = Header(
        flags_high=data[2],
        flags_low=data[3],
        qdcount=int.from_bytes(data[4:6], "big"),
        ancount=int.from_bytes(data[6:8], "big"),
        nscount=int.from_bytes(data[8:10], "big"),
        arcount=int.from_bytes(data[10:12], "big"),
    )
    if header.truncated:
        raise ValueError("response was truncated (TC flag set)")
    if header.rcode != 0:
        raise ValueError(f"DNS response code {header.rcode}")
    return header


def skip_questions(data: bytes, header: Header) -> int:
    """Return the offset of the first resource record."""
    offset = 12
    for _ in range(header.qdcount):
        offset = skip_name(data, offset) + 4  # QTYPE + QCLASS
    return offset


def read_records(data: bytes, offset: int, count: int) -> tuple[list[Record], int]:
    """
    Read ``count`` resource records, and say where they ended.

    The offset comes back so a caller can walk one section at a time - which
    section a record arrived in is the difference between an answer and the
    negative proof of one.
    """
    records: list[Record] = []
    for _ in range(count):
        offset = skip_name(data, offset)
        if offset + 10 > len(data):
            raise ValueError("resource record header runs past the end of the message")
        rtype = int.from_bytes(data[offset : offset + 2], "big")
        ttl = int.from_bytes(data[offset + 4 : offset + 8], "big")
        rdlength = int.from_bytes(data[offset + 8 : offset + 10], "big")
        offset += 10
        rdata = data[offset : offset + rdlength]
        if len(rdata) != rdlength:
            raise ValueError("resource record data runs past the end of the message")
        records.append(Record(rtype, ttl, rdata))
        offset += rdlength
    return records, offset


def ask(
    hostname: str,
    qtype: int,
    nameserver: str,
    timeout: float,
    *,
    port: int = 53,
    dnssec_ok: bool = False,
) -> bytes:
    """
    Send one query and return the raw response, having checked its id.

    ``port`` defaults to the standard DNS port and exists so tests can point
    this at a loopback server instead; nothing in the scanner ever overrides
    it.
    """
    family = socket.AF_INET6 if ":" in nameserver else socket.AF_INET
    query_id = int.from_bytes(os.urandom(2), "big")
    message = build_query(hostname, qtype, query_id, dnssec_ok=dnssec_ok)
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        # Connected, not merely sent to. An unconnected UDP socket accepts a
        # datagram from anybody who can reach the port it happens to be bound
        # to, so a forged answer would only have to arrive before the
        # resolver's and guess the request id - two bytes - rather than also
        # come from the resolver. Connecting has the kernel drop everything
        # from any other address or port, which is what every resolver library
        # does and what makes the id a second check rather than the only one.
        sock.connect((nameserver, port))
        sock.send(message)
        data = sock.recv(4096)
    if len(data) < 2 or data[0:2] != query_id.to_bytes(2, "big"):
        raise ValueError("response id does not match the query")
    return data
