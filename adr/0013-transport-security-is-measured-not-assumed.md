# ADR 0013: Transport security is measured, and what cannot be measured is absent

- Status: Accepted
- Date: 2026-08-21

## Context

The scanner's transport check was three questions long: did the handshake
succeed, did the certificate verify, when does it expire. That misses most of
what actually goes wrong with TLS on a self-hosted instance. A server that
still accepts TLS 1.0 alongside 1.3 negotiates 1.3 with our client and looks
perfect. A certificate issued for one name and installed on another verifies
against the wrong host without complaint if nobody checks the names. A chain
missing its intermediate works in the browser that happened to cache it and
fails in the next one. A ten-year certificate is a ten-year window for a
stolen key.

There was also a hole. `getpeercert()` returns `{}` when verification is off,
and the scanner turns verification off precisely because OpenCloud ships with
a self-signed certificate. So on the instances most likely to have an expired
certificate, the expiry check produced no finding at all - not a failure, not
a pass, nothing - and had done since it was written.

The tempting fix for each of these is a guess. Python exposes no API for OCSP
stapling; the chain a server presents is only reachable on 3.13 and later; a
certificate cannot be decoded through the standard library once verification
is off. Every one of those gaps has an easy default, and every easy default is
"assume it is fine".

## Decision

**A new layer, `opencloud_local_scan/tls.py`, measures transport security, and
a measurement that could not be taken is absent rather than passed.**

- `inspect(host, port, timeout)` returns a `TlsInspection`: the negotiated
  protocol and cipher, the certificate, the chain length, what a deprecated
  protocol probe found and whether an OCSP response was stapled. It emits
  `TlsCheck` tuples; `scanner.py` turns them into `Finding`s. The module knows
  nothing about findings, ratings or severities beyond the label it hands
  over, and imports nothing from `scanner.py`.
- **`None` means "not determined" everywhere**, in the dataclass and in the
  `tls` block of the result document, and a check whose input is `None` emits
  no finding. An older Python cannot read the chain, a build without an old
  protocol cannot probe for one, a host without `openssl` cannot see a
  stapled response - in each case the instance gets neither credit nor blame.
  A green tick nobody earned is worse than a gap somebody can see.
- The certificate is decoded from the presented chain whether or not it
  verified, so expiry, names, issuer and lifetime are reported on a
  self-signed instance exactly as on a trusted one. Trust is one finding;
  everything else about the certificate is independent of it.
- `trusted` is `bool | None`, and no `tlsTrusted` finding is emitted when a
  handshake failed for a reason that was not the certificate. Blaming the
  certificate for a protocol fault sends an operator to the wrong file.
- Chain completeness is read from OpenSSL's verify code rather than counted:
  self-signed says nothing about the chain and is left to `tlsTrusted`, an
  expiry or hostname failure proves the chain was walked, and only "unable to
  get issuer" is an incomplete chain.
- OCSP stapling is answered by `openssl s_client -status`, because the
  standard library has no equivalent and under TLS 1.3 the response is inside
  the encrypted handshake. It runs only when `openssl` is present, only when
  the certificate names a responder, and only when the host matches a strict
  pattern - `subprocess` with a fixed argument list, never a shell.

## Consequences

`tls` joins the result-document contract next to `setup`, and the five new
findings join the hardening catalogue with the same explanations and
documentation links every other finding has. The dashboard, the four exports,
the OpenAPI `TlsDetail` schema and the MCP result view all render the same
block; none of them measures anything itself.

The scan makes more connections than it did: a second handshake per deprecated
protocol probed, and one `openssl` process when stapling is checked. Both are
bounded by the scan timeout and both can be switched off at the call.

A certificate can now be reported as expired on an instance whose certificate
was never trusted in the first place. That is two findings about one file, and
it is correct: replacing an untrusted certificate and replacing an expired one
are the same job only by coincidence.

The decoder depends on `_ssl._test_decode_cert`, which is private. It exists
in every supported Python and is exercised by a test on each; if it ever goes
away, certificate detail disappears and the findings that depend on it stop
being emitted - which is the failure mode this ADR asks for.

## Alternatives considered

**Depend on `cryptography`.** The obvious way to parse a certificate, and a
compiled dependency on a monitoring host that currently needs none. It is
already available in the test group, where the cost does not apply.

**Report an unmeasurable check as passing.** Every gap closes, the result
document has no nulls in it, and the report begins to lie in the one direction
a security report must never lie.

**Report an unmeasurable check as failing.** Honest about the uncertainty and
useless in practice: an operator cannot fix their build of Python from the
OpenCloud configuration, and a finding nobody can act on trains people to
ignore findings.

**Rate the cipher suite.** Tempting, and a moving target that would need a
curated list maintained here and going quietly out of date, which is the exact
failure ADR 0012 avoids for remediation advice. The cipher is reported as a
fact; the protocol version is what carries a verdict.
