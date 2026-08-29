# ADR 0024: The CAA record check uses only the system's own resolver

- Status: Accepted
- Date: 2026-08-29

## Context

A CAA (Certification Authority Authorization) record answers a question the
TLS layer cannot: not "is the certificate presented to us adequate" (ADR
0013, ADR 0023), but "could anyone else's certificate have been presented
instead". A domain with no CAA record lets any publicly trusted CA issue for
it; one that names an authorized issuer narrows that down. It is worth
reporting for the same reason the cipher suite and certificate policy
findings are: it is measurable, actionable at a layer the operator controls,
and currently invisible.

The obstacle is the record type, not the concept. `socket.getaddrinfo` and
every other stdlib resolution helper answer A/AAAA lookups only; nothing in
the standard library can ask for `TYPE257`. The two ways to get one are a new
dependency (`dnspython`) or a resolver reachable some other way - and this
project's README promises that "nothing about your instance is ever sent to
a third party." A CAA check that silently queried a public resolver such as
1.1.1.1 or 8.8.8.8 would hand that resolver the one thing being scanned:
the target's hostname. That would make the claim false for this one check,
quietly, for every user who never reads this file.

## Decision

`opencloud_local_scan/caa.py` speaks just enough of the DNS wire format to
send one CAA query over UDP and parse one answer back, using nothing but
`socket`. The nameserver it queries is read from `/etc/resolv.conf` - the
same resolver every other lookup this process makes (including connecting to
the scanned host in the first place) already goes through. No public
resolver is ever hardcoded as a fallback.

When no local resolver can be found - most notably on native Windows, which
does not keep its configuration in `/etc/resolv.conf` - the finding is left
out of the result entirely, the same absent-not-guessed rule ADR 0023
established for OCSP and certificate policy. The same applies to a query
that times out, a response that fails to parse, or a target that is a bare
IP address rather than a name.

The finding (`tlsCaaRecord`, severity `low`) passes when at least one
`issue` or `issuewild` property is present for the exact name scanned. It
does not walk the RFC 8659 parent-domain fallback chain, and it does not
judge which CA a record names - only whether issuance has been restricted to
some set at all, which is the operator's decision to make, not this
project's to second-guess.

## Consequences

No new dependency, and no new outbound connection beyond the resolver every
scan already uses. The finding is unavailable on hosts without a readable
`/etc/resolv.conf`, which is an accepted gap rather than a defect - the same
trade-off ADR 0023 already made for a missing `openssl` binary.

Severity is deliberately `low`: the absence of a CAA record is a
defense-in-depth gap, not a vulnerability in the running instance, and rating
it any higher would put it ahead of findings that describe something
actually broken.

## Alternatives considered

**Add `dnspython`.** Solves the record-type problem in a handful of lines
instead of a hand-rolled parser, but it is a runtime dependency added for one
check, and this project has twice already (ADR 0006, ADR 0023) preferred a
few hundred dependency-free lines over a library pulled in for a single
feature.

**Query a public resolver (1.1.1.1, 8.8.8.8, ...).** Simplest to implement
and works even when `/etc/resolv.conf` cannot be read, but it means every
scan of a private or internal hostname leaks that hostname to a third party
the operator never chose to trust with it - directly contradicting the
project's core privacy claim.

**Shell out to `dig` or `host`.** Neither is a build dependency the way
`openssl` already is for this project (used for OCSP and certificate
parsing); requiring one for a `low`-severity finding is a worse trade than
parsing 60 bytes of wire format by hand.
