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

from opencloud_local_scan import caa, hardening

TIMEOUT = 2.0


# --------------------------------------------------------------------------
# Wire format, tested directly against synthetic bytes - no networking.
# --------------------------------------------------------------------------


def test_build_query_encodes_labels_and_type():
    message = caa._build_query("example.com", query_id=0x1234)
    assert message[0:2] == b"\x12\x34"
    assert message[2:4] == b"\x01\x00"  # standard query, recursion desired
    assert message[4:6] == b"\x00\x01"  # QDCOUNT = 1
    question = message[12:]
    assert question == b"\x07example\x03com\x00" + (257).to_bytes(2, "big") + b"\x00\x01"


def test_build_query_rejects_a_label_that_is_too_long():
    with pytest.raises(ValueError):
        caa._build_query("a" * 64 + ".example.com", query_id=1)


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
    query = caa._build_query("example.com", query_id=42)
    question = query[12:]
    answer = _caa_answer("issue", b"letsencrypt.org")
    data = _response(42, question, ancount=1, answers=answer)
    records = caa._parse_caa_response(data)
    assert records == [caa._CaaRecord("issue", b"letsencrypt.org")]


def test_parse_caa_response_no_answers_is_a_clean_empty_result():
    query = caa._build_query("example.com", query_id=7)
    data = _response(7, query[12:], ancount=0)
    assert caa._parse_caa_response(data) == []


def test_parse_caa_response_rejects_truncated_flag():
    query = caa._build_query("example.com", query_id=7)
    data = _response(7, query[12:], ancount=0, truncated=True)
    with pytest.raises(ValueError):
        caa._parse_caa_response(data)


def test_parse_caa_response_rejects_error_rcode():
    query = caa._build_query("example.com", query_id=7)
    data = _response(7, query[12:], ancount=0, rcode=2)
    with pytest.raises(ValueError):
        caa._parse_caa_response(data)


def test_parse_caa_response_ignores_non_caa_records():
    query = caa._build_query("example.com", query_id=9)
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
        monkeypatch.setattr(caa, "_system_nameservers", _fail)
        assert caa.check_caa_record("203.0.113.5", TIMEOUT) is None
        assert caa.check_caa_record("[::1]", TIMEOUT) is None


def test_check_caa_record_no_resolver_is_unknown(monkeypatch):
    monkeypatch.setattr(caa, "_system_nameservers", list)
    assert caa.check_caa_record("example.com", TIMEOUT) is None


def test_check_caa_record_passes_with_an_issue_record(monkeypatch):
    def _build(query_id, request):
        question = request[12:]
        answer = _caa_answer("issue", b"letsencrypt.org")
        return _response(query_id, question, ancount=1, answers=answer)

    with _fake_resolver(_build) as port:
        monkeypatch.setattr(caa, "_system_nameservers", lambda: ["127.0.0.1"])
        result = caa.check_caa_record("example.com", TIMEOUT, port=port)

    assert result is not None
    assert result.identifier == "tlsCaaRecord"
    assert result.severity == "low"
    assert result.passed is True


def test_check_caa_record_fails_with_no_records(monkeypatch):
    def _build(query_id, request):
        return _response(query_id, request[12:], ancount=0)

    with _fake_resolver(_build) as port:
        monkeypatch.setattr(caa, "_system_nameservers", lambda: ["127.0.0.1"])
        result = caa.check_caa_record("example.com", TIMEOUT, port=port)

    assert result is not None
    assert result.passed is False
    assert "no ca" in result.detail.lower()


def test_check_caa_record_times_out_to_unknown(monkeypatch):
    with _fake_resolver(lambda *_: None) as port:
        monkeypatch.setattr(caa, "_system_nameservers", lambda: ["127.0.0.1"])
        result = caa.check_caa_record("example.com", 0.3, port=port)

    assert result is None


def test_check_caa_record_falls_through_to_the_next_resolver(monkeypatch):
    def _build(query_id, request):
        return _response(query_id, request[12:], ancount=0)

    with _fake_resolver(_build) as port:
        monkeypatch.setattr(
            caa, "_system_nameservers", lambda: ["203.0.113.1", "127.0.0.1"]
        )
        # The first resolver (a non-routable TEST-NET-3 address) never
        # answers within the timeout; the second one does.
        result = caa.check_caa_record("example.com", 0.5, port=port)

    assert result is not None
    assert result.passed is False


def test_system_nameservers_reads_resolv_conf(tmp_path, monkeypatch):
    resolv_conf = tmp_path / "resolv.conf"
    resolv_conf.write_text("# comment\nnameserver 127.0.0.53\nnameserver 8.8.8.8\n")
    monkeypatch.setattr(caa, "_RESOLV_CONF", resolv_conf)
    assert caa._system_nameservers() == ["127.0.0.53", "8.8.8.8"]


def test_system_nameservers_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(caa, "_RESOLV_CONF", tmp_path / "does-not-exist")
    assert caa._system_nameservers() == []


def test_tls_ca_record_is_registered_in_hardening_descriptions():
    described = hardening.describe("tlsCaaRecord")
    assert described.id == "tlsCaaRecord"
    assert described.remediation
