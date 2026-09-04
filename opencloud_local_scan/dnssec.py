"""
Whether the zone that answers for this instance is signed.

Everything else the scan concludes about the transport starts from an
address the resolver handed over. A CAA record narrows who may issue a
certificate for the name (:mod:`caa`), and the TLS layer decides whether the
certificate presented is adequate (:mod:`tls`) - but both rest on having
reached the right host in the first place. In an unsigned zone that
assumption is a matter of trust in the path: an answer forged on the way to
the resolver is indistinguishable from the real one, and the CAA record
guarding certificate issuance can be forged along with the address it
protects.

This module asks the same resolver :mod:`caa` does for the instance's own
address record, with the EDNS0 DO bit set, and reads three things out of the
answer: whether the resolver validated it, whether the answer carried
signatures, and whether the resolver understood the question at all.

**The third one is what keeps this honest.** A resolver that strips EDNS0 -
or one that never validates - produces exactly the same silence as an
unsigned zone. Reporting that silence as a finding would fail every scan run
from behind such a resolver, and the failure would be about the machine
running the scan rather than about the instance. So the finding is left out
of the result entirely unless the answer proves the resolver was capable of
telling us. See ADR 0038, and ADR 0024 for why the query never leaves the
resolver this machine already uses.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from .dns import (
    TYPE_A,
    TYPE_OPT,
    TYPE_RRSIG,
    ask,
    is_ip_literal,
    read_header,
    read_records,
    skip_questions,
    system_nameservers,
)
from .tls import TlsCheck

LOGGER = logging.getLogger("check_opencloud.dnssec")


class _Answer(NamedTuple):
    """What one DNSSEC-aware lookup established about the zone."""

    validated: bool
    signed: bool
    resolver_aware: bool


def _parse_dnssec_response(data: bytes) -> _Answer:
    """
    Read the DNSSEC verdict out of a raw response.

    Raises ``ValueError`` on anything that does not parse cleanly, which the
    caller treats as an unknown rather than as an unsigned zone.

    Signatures are looked for in the authority section as well as the answer,
    because a name with no record of the type asked for is proved by a signed
    denial that lives there. Reading only the answer section would report a
    signed zone as unsigned whenever the instance publishes an AAAA record
    and no A record.
    """
    header = read_header(data)
    offset = skip_questions(data, header)
    records, offset = read_records(data, offset, header.ancount + header.nscount)
    additional, _ = read_records(data, offset, header.arcount)

    return _Answer(
        validated=header.authentic_data,
        signed=any(record.rtype == TYPE_RRSIG for record in records),
        # The resolver echoing an OPT record with DO set is what separates
        # "this zone is unsigned" from "this resolver would never have said".
        resolver_aware=any(
            record.rtype == TYPE_OPT and record.dnssec_ok for record in additional
        ),
    )


def check_dnssec(hostname: str, timeout: float, *, port: int = 53) -> TlsCheck | None:
    """
    Whether the name scanned is protected by DNSSEC.

    Passes when the answer was DNSSEC-validated by this machine's resolver,
    or when it carried signatures the resolver forwarded without validating
    them - both mean the operator signed the zone, which is the part this
    scan is entitled to judge. Fails only when a resolver that demonstrably
    understood the question returned neither.

    Returns ``None`` - an unknown, never a pass and never a failure - for a
    bare IP address, when no local resolver can be found, when every resolver
    tried failed to answer or answered something this parser could not make
    sense of, and when the answer shows the resolver does not speak DNSSEC.

    ``port`` defaults to the standard DNS port and exists so tests can point
    this at a loopback server instead; nothing in the scanner itself ever
    overrides it.
    """
    candidate = hostname.strip("[]")
    if is_ip_literal(candidate):
        return None

    nameservers = system_nameservers()
    if not nameservers:
        LOGGER.debug("No system resolver found; DNSSEC left unmeasured")
        return None

    for nameserver in nameservers:
        try:
            answer = _parse_dnssec_response(
                ask(candidate, TYPE_A, nameserver, timeout, port=port, dnssec_ok=True)
            )
        except (OSError, ValueError, UnicodeError) as exc:
            LOGGER.debug(
                "DNSSEC query for %s via %s failed: %s", candidate, nameserver, exc
            )
            continue

        if not answer.resolver_aware:
            LOGGER.debug(
                "Resolver %s did not answer with DNSSEC OK set; DNSSEC left unmeasured",
                nameserver,
            )
            continue

        if answer.validated:
            detail = "Zone is signed and this machine's resolver validated the answer"
        elif answer.signed:
            detail = (
                "Zone is signed, but this machine's resolver did not validate "
                "the answer"
            )
        else:
            detail = (
                "Zone is not signed: a forged answer for this name cannot be "
                "told apart from the real one"
            )
        return TlsCheck(
            "tlsDnssec", "low", answer.validated or answer.signed, detail
        )

    return None
