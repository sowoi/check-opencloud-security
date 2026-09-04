"""
The CAA record check: wire-format parsing on its own, then the full lookup
against a real UDP server on loopback rather than a mock of `socket` - the
point of this check is what a resolver actually answers, and a mock would
only confirm what the code already assumes.
"""

from __future__ import annotations

import socket
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencloud_local_scan import caa, dns, hardening

TIMEOUT = 2.0


# --------------------------------------------------------------------------
# Wire format, tested directly against synthetic bytes - no networking. The
# query building and the resolver discovery underneath these belong to
# `opencloud_local_scan.dns` and are tested in `test_dns.py`.
# --------------------------------------------------------------------------


def _header(query_id: int, *, ancount: int, rcode: int = 0, truncated: bool = False) -> bytes:
    flags_hi = 0x80 | (0x02 if truncated else 0)
    flags_lo = 0x80 | (rcode & 0x0F)
    return (
        query_id.to_bytes(2, "big")
        + bytes([flags_hi, flags_lo])
        + (1).to_bytes(2, "big")  # QDCOUNT
        + ancount.to_bytes(2, "big")
        + b"\x00\x00\x00\x00"  # NSCOUNT / ARCOUNT
    )


def _caa_answer(tag: str, value: bytes, *, flag: int = 0, name_pointer: int = 0x0C) -> bytes:
    """One answer RR, with its NAME compressed as a pointer back to the question."""
    rdata = bytes([flag, len(tag)]) + tag.encode("ascii") + value
    return (
        bytes([0xC0, name_pointer])
        + (257).to_bytes(2, "big")  # TYPE = CAA
        + (1).to_bytes(2, "big")  # CLASS = IN
        + (300).to_bytes(4, "big")  # TTL
        + len(rdata).to_bytes(2, "big")
        + rdata
    )


def _response(query_id: int, question: bytes, *, ancount: int, answers: bytes = b"", **header_kwargs) -> bytes:
    return _header(query_id, ancount=ancount, **header_kwargs) + question + answers


def test_parse_caa_response_reads_authorizing_records():
    query = dns.build_query("example.com", dns.TYPE_CAA, 42)
    question = query[12:]
    answer = _caa_answer("issue", b"letsencrypt.org")
    data = _response(42, question, ancount=1, answers=answer)
    records = caa._parse_caa_response(data)
    assert records == [caa._CaaRecord("issue", b"letsencrypt.org")]


def test_parse_caa_response_folds_the_tag_to_lower_case():
    """
    RFC 8659 makes the property tag case insensitive, so 'Issue' authorizes too.

    A zone publishing `Issue "letsencrypt.org"` has restricted issuance exactly
    as much as one publishing `issue`. Matching the spelling literally reported
    it as having no CAA record at all - a finding against a domain that had
    done the right thing.
    """
    query = dns.build_query("example.com", dns.TYPE_CAA, 42)
    question = query[12:]

    for spelling, folded in (
        ("Issue", "issue"),
        ("ISSUE", "issue"),
        ("IssueWild", "issuewild"),
    ):
        data = _response(
            42, question, ancount=1, answers=_caa_answer(spelling, b"letsencrypt.org")
        )
        records = caa._parse_caa_response(data)
        assert records == [caa._CaaRecord(folded, b"letsencrypt.org")]
        assert any(record.tag in caa._AUTHORIZING_TAGS for record in records)

    # The negative half: folding case must not turn a non-authorizing property
    # such as 'iodef' into one that restricts issuance.
    data = _response(42, question, ancount=1, answers=_caa_answer("IODEF", b"mailto:a@b"))
    records = caa._parse_caa_response(data)
    assert records == [caa._CaaRecord("iodef", b"mailto:a@b")]
    assert not any(record.tag in caa._AUTHORIZING_TAGS for record in records)


def test_parse_caa_response_no_answers_is_a_clean_empty_result():
    query = dns.build_query("example.com", dns.TYPE_CAA, 7)
    data = _response(7, query[12:], ancount=0)
    assert caa._parse_caa_response(data) == []


def test_parse_caa_response_rejects_truncated_flag():
    query = dns.build_query("example.com", dns.TYPE_CAA, 7)
    data = _response(7, query[12:], ancount=0, truncated=True)
    with pytest.raises(ValueError):
        caa._parse_caa_response(data)


def test_parse_caa_response_rejects_error_rcode():
    query = dns.build_query("example.com", dns.TYPE_CAA, 7)
    data = _response(7, query[12:], ancount=0, rcode=2)
    with pytest.raises(ValueError):
        caa._parse_caa_response(data)


def test_parse_caa_response_ignores_non_caa_records():
    query = dns.build_query("example.com", dns.TYPE_CAA, 9)
    question = query[12:]
    # A CNAME-shaped record ahead of the CAA one, to prove the walk keeps going.
    cname_rdata = b"\x03www\x07example\x03com\x00"
    cname = (
        bytes([0xC0, 0x0C])
        + (5).to_bytes(2, "big")  # TYPE = CNAME
        + (1).to_bytes(2, "big")
        + (300).to_bytes(4, "big")
        + len(cname_rdata).to_bytes(2, "big")
        + cname_rdata
    )
    caa_rr = _caa_answer("issuewild", b";")
    data = _response(9, question, ancount=2, answers=cname + caa_rr)
    records = caa._parse_caa_response(data)
    assert records == [caa._CaaRecord("issuewild", b";")]


def test_parse_caa_response_rejects_truncated_message():
    with pytest.raises(ValueError):
        caa._parse_caa_response(b"\x00" * 6)


# --------------------------------------------------------------------------
# The full lookup, against a real loopback UDP responder.
# --------------------------------------------------------------------------


@contextmanager
def _fake_resolver(build_response):
    """
    Serve exactly one DNS query on loopback UDP.

    ``build_response(query_id, request_bytes) -> bytes | None`` returns the
    raw response to send back, or None to simulate a resolver that never
    answers.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(TIMEOUT + 1)
    port = sock.getsockname()[1]

    def _serve():
        try:
            data, addr = sock.recvfrom(4096)
        except OSError:
            return
        query_id = int.from_bytes(data[0:2], "big")
        response = build_response(query_id, data)
        if response is not None:
            sock.sendto(response, addr)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        thread.join(timeout=TIMEOUT + 1)
        sock.close()


def test_check_caa_record_ip_literal_is_never_queried():
    def _fail(*_args, **_kwargs):
        raise AssertionError("an IP literal must never reach the resolver")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(caa, "system_nameservers", _fail)
        assert caa.check_caa_record("203.0.113.5", TIMEOUT) is None
        assert caa.check_caa_record("[::1]", TIMEOUT) is None


def test_check_caa_record_no_resolver_is_unknown(monkeypatch):
    monkeypatch.setattr(caa, "system_nameservers", list)
    assert caa.check_caa_record("example.com", TIMEOUT) is None


def test_check_caa_record_passes_with_an_issue_record(monkeypatch):
    def _build(query_id, request):
        question = request[12:]
        answer = _caa_answer("issue", b"letsencrypt.org")
        return _response(query_id, question, ancount=1, answers=answer)

    with _fake_resolver(_build) as port:
        monkeypatch.setattr(caa, "system_nameservers", lambda: ["127.0.0.1"])
        result = caa.check_caa_record("example.com", TIMEOUT, port=port)

    assert result is not None
    assert result.identifier == "tlsCaaRecord"
    assert result.severity == "low"
    assert result.passed is True


def test_check_caa_record_fails_with_no_records(monkeypatch):
    def _build(query_id, request):
        return _response(query_id, request[12:], ancount=0)

    with _fake_resolver(_build) as port:
        monkeypatch.setattr(caa, "system_nameservers", lambda: ["127.0.0.1"])
        result = caa.check_caa_record("example.com", TIMEOUT, port=port)

    assert result is not None
    assert result.passed is False
    assert "no ca" in result.detail.lower()


def test_check_caa_record_times_out_to_unknown(monkeypatch):
    with _fake_resolver(lambda *_: None) as port:
        monkeypatch.setattr(caa, "system_nameservers", lambda: ["127.0.0.1"])
        result = caa.check_caa_record("example.com", 0.3, port=port)

    assert result is None


def test_check_caa_record_falls_through_to_the_next_resolver(monkeypatch):
    def _build(query_id, request):
        return _response(query_id, request[12:], ancount=0)

    with _fake_resolver(_build) as port:
        monkeypatch.setattr(
            caa, "system_nameservers", lambda: ["203.0.113.1", "127.0.0.1"]
        )
        # The first resolver (a non-routable TEST-NET-3 address) never
        # answers within the timeout; the second one does.
        result = caa.check_caa_record("example.com", 0.5, port=port)

    assert result is not None
    assert result.passed is False


def test_tls_ca_record_is_registered_in_hardening_descriptions():
    described = hardening.describe("tlsCaaRecord")
    assert described.id == "tlsCaaRecord"
    assert described.remediation


def test_an_answer_from_somewhere_other_than_the_resolver_is_ignored(monkeypatch):
    """A CAA answer has to come from the resolver it was asked of.

    An unconnected UDP socket accepts a datagram from anybody who can reach
    the port it happens to be bound to, so a forged answer would only have to
    arrive before the resolver's and carry the right request id - two bytes -
    rather than also come from the resolver. Connecting the socket has the
    kernel drop everything else, which is what makes the id a second check
    rather than the only one.

    Here the resolver stays silent and a well-formed answer with the right id
    arrives from another port on the same machine, which is what an off-path
    forgery looks like from the socket's point of view. It must not become a
    finding - and the passing case above proves this is not simply refusing
    every answer.
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
        answer = _caa_answer("issue", b"attacker.example")
        forger.sendto(
            _response(query_id, data[12:], ancount=1, answers=answer), addr
        )

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    monkeypatch.setattr(caa, "system_nameservers", lambda: ["127.0.0.1"])
    try:
        result = caa.check_caa_record("example.com", 0.5, port=port)
    finally:
        thread.join(timeout=TIMEOUT + 1)
        resolver.close()
        forger.close()

    assert result is None
