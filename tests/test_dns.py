"""
The DNS wire format shared by the CAA and DNSSEC lookups.

These are the bytes both findings are built on: get the question wrong and
the resolver answers about the wrong name, get the OPT record wrong and a
signed zone looks unsigned. Everything here is synthetic bytes and no
networking - the lookups themselves are exercised against real loopback
resolvers in `test_caa.py` and `test_dnssec.py`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencloud_local_scan import caa, dns, dnssec


def test_build_query_encodes_labels_and_type():
    message = dns.build_query("example.com", dns.TYPE_CAA, 0x1234)
    assert message[0:2] == b"\x12\x34"
    assert message[2:4] == b"\x01\x00"  # standard query, recursion desired
    assert message[4:6] == b"\x00\x01"  # QDCOUNT = 1
    assert message[10:12] == b"\x00\x00"  # ARCOUNT = 0 without EDNS0
    question = message[12:]
    assert question == b"\x07example\x03com\x00" + (257).to_bytes(2, "big") + b"\x00\x01"


def test_build_query_rejects_a_label_that_is_too_long():
    with pytest.raises(ValueError):
        dns.build_query("a" * 64 + ".example.com", dns.TYPE_CAA, 1)


def test_a_query_without_dnssec_carries_no_additional_record():
    """
    The DO bit is opt-in, and a query that did not ask for it must be the
    plain query it always was - the CAA lookup shares this builder, and an
    OPT record appearing there would change what resolvers answer it with.
    """
    message = dns.build_query("example.com", dns.TYPE_CAA, 1)
    assert message[10:12] == b"\x00\x00"
    assert len(message) == 12 + len(b"\x07example\x03com\x00") + 4


def test_a_dnssec_query_appends_an_opt_record_with_the_do_bit():
    """
    DNSSEC is requested by a bit inside the OPT record's TTL, not by a header
    flag. Building it wrong asks an ordinary question, and every signed zone
    then comes back looking unsigned.
    """
    message = dns.build_query("example.com", dns.TYPE_A, 1, dnssec_ok=True)
    assert message[10:12] == b"\x00\x01"  # ARCOUNT = 1

    header = dns.read_header(b"\x00\x01\x80\x80" + message[4:12])
    records, _ = dns.read_records(message, dns.skip_questions(message, header), 1)
    assert len(records) == 1
    assert records[0].rtype == dns.TYPE_OPT
    assert records[0].dnssec_ok is True


def test_the_do_bit_is_read_back_only_from_an_opt_record():
    """An ordinary record whose TTL happens to have the high bit set is not a
    resolver telling us it speaks DNSSEC."""
    assert dns.Record(dns.TYPE_OPT, 0x8000, b"").dnssec_ok is True
    assert dns.Record(dns.TYPE_OPT, 0x0000, b"").dnssec_ok is False
    assert dns.Record(dns.TYPE_A, 0x8000, b"").dnssec_ok is False


def _header_bytes(*, flags_low: int = 0x80, ancount: int = 0, truncated: bool = False) -> bytes:
    return (
        b"\x00\x2a"
        + bytes([0x80 | (0x02 if truncated else 0), flags_low])
        + (1).to_bytes(2, "big")
        + ancount.to_bytes(2, "big")
        + b"\x00\x00\x00\x00"
    )


def test_read_header_reports_the_authentic_data_bit():
    """AD is the resolver saying it validated the answer, and it is the whole
    of the DNSSEC verdict - reading the wrong bit would invent one."""
    assert dns.read_header(_header_bytes(flags_low=0x80)).authentic_data is False
    assert dns.read_header(_header_bytes(flags_low=0xA0)).authentic_data is True


def test_read_header_rejects_a_truncated_or_failed_answer():
    """A lookup that did not work must raise rather than parse to an empty
    result, which the callers would report as an absent record."""
    with pytest.raises(ValueError):
        dns.read_header(_header_bytes(truncated=True))
    with pytest.raises(ValueError):
        dns.read_header(_header_bytes(flags_low=0x83))  # NXDOMAIN
    with pytest.raises(ValueError):
        dns.read_header(b"\x00" * 6)


def test_read_records_refuses_data_running_past_the_end():
    """A malformed answer is an unknown, never a finding, so the parser has to
    fail rather than return what it managed to read."""
    truncated = (
        _header_bytes(ancount=1)
        + b"\x07example\x03com\x00\x01\x01\x00\x01"
        + bytes([0xC0, 0x0C])
        + (1).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
        + (300).to_bytes(4, "big")
        + (99).to_bytes(2, "big")  # RDLENGTH promises far more than follows
        + b"\x01\x02"
    )
    header = dns.read_header(truncated)
    with pytest.raises(ValueError):
        dns.read_records(truncated, dns.skip_questions(truncated, header), header.ancount)


def test_is_ip_literal_covers_both_families_and_bracketed_forms():
    assert dns.is_ip_literal("203.0.113.5") is True
    assert dns.is_ip_literal("[::1]") is True
    assert dns.is_ip_literal("2001:db8::1") is True
    assert dns.is_ip_literal("example.com") is False
    assert dns.is_ip_literal("203.0.113.5.example.com") is False


def test_system_nameservers_reads_resolv_conf(tmp_path, monkeypatch):
    resolv_conf = tmp_path / "resolv.conf"
    resolv_conf.write_text("# comment\nnameserver 127.0.0.53\nnameserver 8.8.8.8\n")
    monkeypatch.setattr(dns, "RESOLV_CONF", resolv_conf)
    assert dns.system_nameservers() == ["127.0.0.53", "8.8.8.8"]


def test_system_nameservers_missing_file_returns_empty(tmp_path, monkeypatch):
    """No readable resolver configuration leaves both findings absent rather
    than reaching for a public resolver, which is the whole point of ADR 0024."""
    monkeypatch.setattr(dns, "RESOLV_CONF", tmp_path / "does-not-exist")
    assert dns.system_nameservers() == []


def test_no_public_resolver_is_hardcoded_in_any_dns_module():
    """
    The privacy claim this project makes rests on the scan never handing a
    scanned hostname to a resolver the operator did not choose (ADR 0024). A
    fallback added in a hurry - after a bug report from somebody whose
    /etc/resolv.conf could not be read - would be invisible until the next
    person read the source.

    String literals are compared exactly rather than searched for as
    substrings, so that the prose in these modules explaining *why* those
    resolvers are never used does not itself trip the check.
    """
    public_resolvers = {"1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9"}
    for module in (dns, caa, dnssec):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert not (literals & public_resolvers), module.__name__
