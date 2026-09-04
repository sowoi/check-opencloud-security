"""
The DNSSEC check, against a real UDP responder on loopback.

The hard part of this check is not reading the AD bit - it is refusing to
answer when the resolver could not have told us. A resolver that strips EDNS0
produces the same silence an unsigned zone does, and reporting that silence
would fail every scan run from behind such a resolver for a reason that has
nothing to do with the instance being scanned. Half of these tests are about
that distinction.
"""

from __future__ import annotations

import socket
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencloud_local_scan import dnssec, hardening

TIMEOUT = 2.0


def _header(
    query_id: int,
    *,
    ancount: int = 0,
    nscount: int = 0,
    arcount: int = 0,
    authentic_data: bool = False,
) -> bytes:
    return (
        query_id.to_bytes(2, "big")
        + bytes([0x80, 0x80 | (0x20 if authentic_data else 0)])
        + (1).to_bytes(2, "big")  # QDCOUNT
        + ancount.to_bytes(2, "big")
        + nscount.to_bytes(2, "big")
        + arcount.to_bytes(2, "big")
    )


def _record(rtype: int, *, ttl: int = 300, rdata: bytes = b"\x00") -> bytes:
    """One resource record whose NAME is a pointer back to the question."""
    return (
        bytes([0xC0, 0x0C])
        + rtype.to_bytes(2, "big")
        + (1).to_bytes(2, "big")  # CLASS = IN
        + ttl.to_bytes(4, "big")
        + len(rdata).to_bytes(2, "big")
        + rdata
    )


def _opt(*, dnssec_ok: bool = True) -> bytes:
    """The resolver's own OPT record, echoing whether it understood the DO bit."""
    return (
        b"\x00"  # root name
        + (41).to_bytes(2, "big")
        + (1232).to_bytes(2, "big")  # class: UDP payload size
        + (0x8000 if dnssec_ok else 0x0000).to_bytes(4, "big")
        + b"\x00\x00"
    )


def _answer(
    query_id: int,
    question: bytes,
    *,
    authentic_data: bool = False,
    signed: bool = False,
    signed_in_authority: bool = False,
    opt: bytes | None = None,
) -> bytes:
    answers = _record(1, rdata=b"\xc0\x00\x02\x01")  # one A record
    if signed:
        answers += _record(46, rdata=b"\x00" * 20)  # RRSIG beside it
    authority = _record(46, rdata=b"\x00" * 20) if signed_in_authority else b""
    additional = _opt() if opt is None else opt
    return (
        _header(
            query_id,
            ancount=2 if signed else 1,
            nscount=1 if signed_in_authority else 0,
            arcount=1 if additional else 0,
            authentic_data=authentic_data,
        )
        + question
        + answers
        + authority
        + additional
    )


@contextmanager
def _fake_resolver(build_response):
    """Serve exactly one DNS query on loopback UDP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(TIMEOUT + 1)
    port = sock.getsockname()[1]

    def _serve():
        try:
            data, addr = sock.recvfrom(4096)
        except OSError:  # pragma: no cover - the query always arrives
            return
        response = build_response(int.from_bytes(data[0:2], "big"), data)
        if response is not None:
            sock.sendto(response, addr)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        thread.join(timeout=TIMEOUT + 1)
        sock.close()


def _question(request: bytes) -> bytes:
    """The question section of a request, to echo back in the answer."""
    return request[12 : 12 + len(b"\x07example\x03com\x00") + 4]


def _check(build_response, monkeypatch, timeout: float = TIMEOUT):
    with _fake_resolver(build_response) as port:
        monkeypatch.setattr(dnssec, "system_nameservers", lambda: ["127.0.0.1"])
        return dnssec.check_dnssec("example.com", timeout, port=port)


def test_a_validated_answer_passes(monkeypatch):
    """The AD bit is the resolver saying it checked the signatures itself,
    which is the strongest thing this scan can learn about the zone."""
    result = _check(
        lambda qid, req: _answer(qid, _question(req), authentic_data=True, signed=True),
        monkeypatch,
    )
    assert result is not None
    assert result.identifier == "tlsDnssec"
    assert result.severity == "low"
    assert result.passed is True
    assert "validated" in result.detail.lower()


def test_signatures_without_validation_still_pass(monkeypatch):
    """
    Whether the operator signed the zone is the part this scan is entitled to
    judge; whether the machine running the scan validates is a fact about that
    machine. A signed zone read through a non-validating resolver must not be
    reported as the operator's failure.
    """
    result = _check(
        lambda qid, req: _answer(qid, _question(req), authentic_data=False, signed=True),
        monkeypatch,
    )
    assert result is not None
    assert result.passed is True
    assert "did not validate" in result.detail.lower()


def test_a_signature_in_the_authority_section_counts(monkeypatch):
    """
    A name with no record of the type asked for is proved by a signed denial
    in the authority section, not the answer. Reading only the answer section
    reported every IPv6-only instance's signed zone as unsigned.
    """
    result = _check(
        lambda qid, req: _answer(qid, _question(req), signed_in_authority=True),
        monkeypatch,
    )
    assert result is not None
    assert result.passed is True


def test_an_unsigned_zone_fails(monkeypatch):
    """The negative case: a DNSSEC-capable resolver that returned neither a
    verdict nor a signature has told us the zone is not signed."""
    result = _check(
        lambda qid, req: _answer(qid, _question(req), authentic_data=False, signed=False),
        monkeypatch,
    )
    assert result is not None
    assert result.passed is False
    assert "not signed" in result.detail.lower()


def test_a_resolver_that_strips_edns_leaves_the_finding_absent(monkeypatch):
    """
    The distinction the whole check turns on. Without the OPT record echoing
    the DO bit, an unsigned zone and a resolver that would never have said are
    the same bytes - and reporting the second as the first fails every scan
    run from behind such a resolver.
    """
    assert (
        _check(lambda qid, req: _answer(qid, _question(req), opt=b""), monkeypatch)
        is None
    )


def test_a_resolver_that_answers_without_the_do_bit_leaves_it_absent(monkeypatch):
    """An OPT record alone is EDNS0, not DNSSEC: a resolver can support the
    first and drop signatures for the second."""
    assert (
        _check(
            lambda qid, req: _answer(qid, _question(req), opt=_opt(dnssec_ok=False)),
            monkeypatch,
        )
        is None
    )


def test_an_ip_literal_is_never_queried():
    """There is no zone to ask about, and asking would send an address to the
    resolver for no finding at all."""

    def _fail(*_args, **_kwargs):
        raise AssertionError("an IP literal must never reach the resolver")

    import pytest

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(dnssec, "system_nameservers", _fail)
        assert dnssec.check_dnssec("203.0.113.5", TIMEOUT) is None
        assert dnssec.check_dnssec("[::1]", TIMEOUT) is None


def test_no_resolver_leaves_the_finding_absent(monkeypatch):
    monkeypatch.setattr(dnssec, "system_nameservers", list)
    assert dnssec.check_dnssec("example.com", TIMEOUT) is None


def test_a_resolver_that_never_answers_leaves_it_absent(monkeypatch):
    assert _check(lambda *_: None, monkeypatch, timeout=0.3) is None


def test_a_failed_lookup_is_never_an_unsigned_zone(monkeypatch):
    """NXDOMAIN, SERVFAIL and a truncated answer are all unknowns. Parsing one
    into a finding would report a name that does not resolve as insecure."""

    def _servfail(query_id, request):
        return (
            query_id.to_bytes(2, "big")
            + bytes([0x80, 0x82])  # SERVFAIL
            + (1).to_bytes(2, "big")
            + b"\x00\x00\x00\x00\x00\x00"
            + _question(request)
        )

    assert _check(_servfail, monkeypatch) is None


def test_an_answer_from_somewhere_other_than_the_resolver_is_ignored(monkeypatch):
    """
    The same off-path forgery the CAA lookup refuses. A validated-looking
    answer arriving from another port must not become a passing finding -
    which would tell an operator their unsigned zone is signed.
    """
    resolver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    resolver.bind(("127.0.0.1", 0))
    resolver.settimeout(TIMEOUT + 1)
    port = resolver.getsockname()[1]
    forger = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    forger.bind(("127.0.0.1", 0))

    def _serve():
        try:
            data, addr = resolver.recvfrom(4096)
        except OSError:  # pragma: no cover - the query always arrives
            return
        query_id = int.from_bytes(data[0:2], "big")
        forger.sendto(
            _answer(query_id, _question(data), authentic_data=True, signed=True), addr
        )

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    monkeypatch.setattr(dnssec, "system_nameservers", lambda: ["127.0.0.1"])
    try:
        result = dnssec.check_dnssec("example.com", 0.5, port=port)
    finally:
        thread.join(timeout=TIMEOUT + 1)
        resolver.close()
        forger.close()

    assert result is None


def test_the_finding_is_registered_in_the_hardening_catalogue():
    """An identifier the catalogue cannot explain reaches an operator as a
    bare string with no remediation."""
    described = hardening.describe("tlsDnssec")
    assert described.id == "tlsDnssec"
    assert described.category == "transport"
    assert described.remediation
