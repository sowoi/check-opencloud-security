# ADR 0038: A DNSSEC answer nobody could have given is not a finding

- Status: Accepted
- Date: 2026-09-04

## Context

Everything the scan concludes about the transport starts from an address a
resolver handed over. ADR 0023 rates the parameters of the connection that
was made, and ADR 0024 added the CAA record so the scan could say who is
allowed to issue a certificate for the name. Both rest on having reached the
right host.

In an unsigned zone that is a matter of trust in the path. An answer forged
on the way to the resolver is indistinguishable from the real one, and the
CAA record guarding certificate issuance can be forged along with the address
it protects - the restriction and the thing it restricts arrive over the same
unauthenticated channel. Whether the zone is signed is measurable, it is the
operator's own decision, and it is currently invisible.

The wire format is not the obstacle; ADR 0024 already put a hand-rolled DNS
query in the tree, and this needs the same one with the EDNS0 DO bit set.
The obstacle is that **silence has two causes and they look identical**:

- the zone is not signed, or
- the resolver this machine uses does not speak DNSSEC, or strips EDNS0, or
  never validates.

A check that read the second as the first would fail every scan run from
behind such a resolver, and the failure would describe the machine running
the scan rather than the instance being scanned. On a monitoring host that is
a permanent finding no change to the instance can clear.

## Decision

`opencloud_local_scan/dnssec.py` asks the resolver from `/etc/resolv.conf` -
never a public one, exactly as ADR 0024 requires - for the scanned name's
address record, with an EDNS0 OPT record carrying the DO bit. It reads three
things out of the answer:

- **the AD bit**, the resolver saying it validated the answer itself;
- **RRSIG records**, in the answer *and* authority sections, meaning the zone
  is signed whether or not this resolver checked the signatures. The
  authority section matters: a name with no record of the type asked for is
  proved by a signed denial that lives there, so reading only the answer
  would report an IPv6-only instance's signed zone as unsigned;
- **the OPT record the resolver echoes**, and whether the DO bit survived in
  it.

The verdict follows from those:

| Observed | `tlsDnssec` |
|:---------|:------------|
| AD set | passes - signed and validated |
| RRSIG present, AD unset | passes - signed, this resolver did not validate |
| Neither, DO echoed | **fails** - the zone is not signed |
| No OPT record, or DO not echoed | **absent** - unmeasured |
| IP literal, no resolver, timeout, unparsable answer | **absent** - unmeasured |

The last two rows are the decision. A resolver that did not echo the DO bit
would not have forwarded signatures or set AD either, so its silence proves
nothing and the finding is left out of the result entirely - the same
absent-not-guessed rule ADR 0023 established for a missing `openssl` binary
and ADR 0024 for an unreadable `resolv.conf`.

A zone that is signed but read through a non-validating resolver **passes**.
Whether the operator signed their zone is the part this scan is entitled to
judge; whether the scanning machine validates is a fact about that machine,
and holding it against the target would be the same category error the
paragraph above avoids.

Severity is `low`, matching `tlsCaaRecord` for the same reason: an unsigned
zone is a defense-in-depth gap, not something broken in the running instance,
and rating it higher would put it ahead of findings that describe an actual
fault. It is gated with the other transport findings and reported beside
them, and the wire-format primitives both lookups need now live in
`opencloud_local_scan/dns.py` rather than being written twice.

## Consequences

No new dependency and no new outbound party - one more UDP query to the
resolver the scan already uses. The two DNS lookups run sequentially rather
than in a pool, because a pool opened at that call site would nest inside the
one the extra-check pass opens later.

The finding is unavailable behind a resolver that does not speak DNSSEC,
which is a large share of default installations and an accepted gap rather
than a defect. An operator who wants the finding can point the host at a
validating resolver, which is a change on the monitoring host and visible as
one.

`--debug` explains the difference between the two passing details, so an
operator can tell "signed and validated" from "signed, not validated here"
without reading this file.

## Alternatives considered

**Query a public validating resolver (1.1.1.1, 9.9.9.9).** Removes the
unmeasured case entirely, since those resolvers always validate - and leaks
the scanned hostname to a third party the operator never chose. ADR 0024
refused this for CAA and nothing about DNSSEC changes the trade.

**Report the unmeasured case as a failure anyway.** Simpler code and one
fewer state to explain. It also produces a permanent finding on every
monitoring host with a non-validating resolver, describing the wrong machine,
which is how operators learn to ignore a line.

**Ask for DNSKEY at the zone apex instead.** Direct evidence of signing, but
it requires knowing where the apex is - the scan has a hostname, not a zone
cut, and walking up to find one is several more queries and a guess at each
step. The DO-bit query answers the question for the exact name scanned, which
is the name everything else in the result is about.

**Add `dnspython`.** Handles all of this properly in a few lines. It remains
a runtime dependency added for findings that are `low` severity, and this
project has three times now (ADR 0006, ADR 0023, ADR 0024) preferred a few
hundred dependency-free lines to a library pulled in for one feature.
