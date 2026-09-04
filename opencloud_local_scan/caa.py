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
used everywhere else in this project) cannot ask for, so :mod:`dns` speaks
just enough of the DNS wire format over UDP to send one query and read one
answer back, and this module reads the CAA records out of the result.

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

import logging
from typing import NamedTuple

from .dns import (
    TYPE_CAA,
    ask,
    is_ip_literal,
    read_header,
    read_records,
    skip_questions,
    system_nameservers,
)
from .tls import TlsCheck

LOGGER = logging.getLogger("check_opencloud.caa")

# RFC 8659 section 4.1 makes the property tag case insensitive, so these are
# the canonical lowercase spellings and every parsed tag is folded to match.
# A zone that publishes `Issue "letsencrypt.org"` restricts issuance exactly
# as much as one that publishes `issue`, and must not be reported as unrestricted.
_AUTHORIZING_TAGS = ("issue", "issuewild")


class _CaaRecord(NamedTuple):
    tag: str
    value: bytes


def _parse_caa_response(data: bytes) -> list[_CaaRecord]:
    """
    Parse a raw DNS response for CAA resource records.

    Raises ``ValueError`` on anything that does not parse cleanly - a
    truncated, malformed or error response is never turned into a guess, it
    is left for the caller to treat as an absent finding.
    """
    header = read_header(data)
    answers, _ = read_records(data, skip_questions(data, header), header.ancount)

    records: list[_CaaRecord] = []
    for answer in answers:
        if answer.rtype != TYPE_CAA or len(answer.rdata) < 2:
            continue
        tag_length = answer.rdata[1]
        # Folded here rather than at every comparison: the tag is case
        # insensitive per RFC 8659, so the lowercase spelling is the only
        # one the rest of this module ever has to think about.
        tag = answer.rdata[2 : 2 + tag_length].decode("ascii", errors="replace").lower()
        records.append(_CaaRecord(tag, answer.rdata[2 + tag_length :]))
    return records


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
    if is_ip_literal(candidate):
        return None

    nameservers = system_nameservers()
    if not nameservers:
        LOGGER.debug("No system resolver found; CAA record left unmeasured")
        return None

    for nameserver in nameservers:
        try:
            records = _parse_caa_response(
                ask(candidate, TYPE_CAA, nameserver, timeout, port=port)
            )
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
