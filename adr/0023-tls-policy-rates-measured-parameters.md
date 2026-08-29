# ADR 0023: TLS policy rates only the cipher and certificate parameters measured

- Status: Accepted
- Date: 2026-08-28

## Context

ADR 0013 deliberately reported the negotiated cipher suite as evidence only.
That avoided maintaining a speculative catalogue of every suite an endpoint
could offer, but it also left an operator with no finding when the normal
connection itself used a legacy cipher. The certificate report likewise named
the issuer, dates and names but did not assess whether the key or signature
algorithm were still adequate.

Both concerns are actionable at the TLS terminator. They must not turn into a
claim that the scanner enumerated suites it did not probe, nor into a pass when
the local OpenSSL binary cannot inspect a certificate.

## Decision

The TLS layer adds two findings:

- `tlsCipherSuite` judges only the suite negotiated by the scan. It fails for
  NULL, RC4, DES/3DES, MD5, SHA-1, CCM-8 or non-forward-secret selections, and
  passes a measured TLS 1.3, ECDHE or DHE suite outside those categories. It
  says nothing about additional suites the endpoint may accept.
- `tlsCertificatePolicy` evaluates a measured certificate key and signature:
  RSA must be at least 2048 bits, EC at least 256 bits, and MD5/SHA-1
  signatures fail. The facts come from `openssl x509 -inform DER -noout -text`
  over the DER already obtained in the handshake. If OpenSSL is unavailable or
  cannot parse the certificate, the finding is absent.

The result document exposes the measured certificate key type, key size and
signature algorithm. As with every TLS measurement, an absent finding is an
unknown, never a pass.

## Consequences

The scanner performs one short local `openssl` process for the certificate
policy, in addition to the stapling process where that applies. It never sends
the certificate to another service and it has no new network connection.

This supersedes ADR 0013's alternative that cipher suites are never rated. Its
other measurement and uncertainty rules remain unchanged.

## Alternatives considered

**Enumerate every cipher suite.** That requires a changing candidate list and
many handshakes, yet still risks overlooking an uncommon suite. It would make
the result look exhaustive when it is not.

**Use a remote TLS rating service.** That conflicts with the project's local
scanner model and discloses an operator's target to another party.

**Add a general cryptography dependency.** The plugin deliberately keeps its
runtime dependency set small. The optional local OpenSSL command is already
used for OCSP inspection and has a safe failure mode.
