# TLS and certificates: what this scanner checks, and why

Everything on this page happens before a single byte of HTTP is exchanged.
OpenCloud's proxy terminates TLS itself on port 9200 (or whatever sits in
front of it does), and this scanner reads what that transport actually
negotiated - protocol version, certificate, chain, cipher suite - the same
way a browser or a sync client would, without any special access.

## 1. Can a TLS connection be made at all: `tlsHandshake`, `httpsAvailable`

Before anything else, the scan tries to connect. Two ways to fail:

- **`httpsAvailable`** (critical) - HTTPS could not be used at all, and the
  scan fell back to plain `http://`. Credentials, session cookies and every
  file travel unencrypted and can be read or altered by anything on the path.
  Nothing else on this page matters as much.
- **`tlsHandshake`** - a TLS port answered, but no connection could be
  established, even with certificate verification switched off. Every other
  TLS finding below rests on a connection that was made, so this one caps the
  scan: the instance is either not serving TLS on this port, or is serving
  something the client could not negotiate at all.

## 2. Is the certificate trusted: `tlsTrusted`

`opencloud init` generates a **self-signed certificate** unless real ones are
configured, so an untrusted chain is the single most common TLS finding on a
fresh instance - not evidence of a broken deployment by itself. See
[Self-signed instances](#self-signed-instances) for how the scanner handles
this without needing to be told which case it is looking at.

## 3. Is the protocol current: `tlsProtocol`, `tlsDeprecatedProtocol`

RFC 8996 deprecated TLS 1.0 and 1.1 in 2021; current browsers refuse them
outright.

- **`tlsProtocol`** fails when the connection this scan made came up on
  anything older than TLS 1.2.
- **`tlsDeprecatedProtocol`** is a second, independent question: after the
  normal handshake, the scan opens one short-lived connection *pinned* to
  each deprecated version and sees whether the server still accepts it. A
  server that negotiates TLS 1.3 with a modern client can still leave 1.0 and
  1.1 on offer for a client that asks for them - and it is the **oldest**
  version accepted, not the one this scan happened to get, that decides what
  an attacker can force. Fixing this means removing old versions from the
  offered set, not just preferring the new one.

## 4. Does the certificate cover this name: `tlsHostname`

No subject alternative name in the certificate matches the host that was
scanned - wrong domain, `localhost`, or no alternative names at all (which
every client has rejected for years, common name alone is not enough).
Clients cannot tell this apart from interception, so they are right to
refuse the connection.

## 5. Is the chain complete: `tlsChain`

The certificates the server sent do not reach a root in the public trust
store on their own - typically a missing intermediate. This is the classic
finding that looks fine in a desktop browser (which caches and fetches
intermediates it has seen before) and fails on mobile clients, command-line
tools, and anything doing machine-to-machine calls that does not have that
cache. The fix is to serve the full chain - leaf followed by every
intermediate, without the root - which is what most issuers publish as a
`fullchain` file.

## 6. Is the certificate about to expire, or issued for too long

Two independent checks, both about time, in opposite directions:

- **`tlsCertificate`** - remaining validity is below `--tls-min-days` (14 by
  default). Unlike most findings, this one has a date on it: it will fail
  whether or not anybody acts, so the usual cause is worth checking directly
  - an automated issuer that stopped renewing, or a reload that never reaches
  the process actually serving TLS.
- **`tlsCertificateLifetime`** (low) - the certificate's validity period is
  *longer* than the 398 days the CA/Browser Forum caps publicly trusted
  certificates at. That points at a private authority or a hand-issued
  certificate, and the risk is the key: a certificate valid for years stays
  valid for years after the key behind it leaks, with nothing forcing the
  rotation that a short-lived certificate does on its own.

## 7. Is the negotiated cipher suite and certificate policy sound

- **`tlsCipherSuite`** judges the suite this specific scan negotiated - it
  does not claim to enumerate every suite the server might offer to a
  different client. It fails on a legacy primitive (`NULL`, `RC4`,
  `3DES`/`DES-`, `MD5`, `CCM_8`) or on a suite that provides no forward
  secrecy.
- **`tlsCertificatePolicy`** fails when the certificate itself carries a weak
  key (RSA below 2048 bits, EC below 256 bits) or an MD5/SHA-1 signature -
  parameters that are inadequate even on a certificate that has not expired.

## 8. Do IPv4 and IPv6 present the same service: `tlsAddressParity`

When a hostname publishes both address families, the scan checks that their
TLS endpoints agree. Visitors may reach either address, so a stale IPv6
listener - an old certificate, a forgotten reverse-proxy config, or nothing
answering at all - can bypass whatever TLS configuration is actually
maintained on IPv4.

## 9. Is certificate issuance restricted: `tlsCaaRecord`

A DNS **CAA** (Certification Authority Authorization) record names which
certificate authorities may issue for a domain at all. Without one, any
publicly trusted CA can be asked to issue a certificate for the name -
not just the one actually in use. This is a low finding, checks only the
exact name scanned (not the RFC 8659 parent-domain fallback chain), and it
is a DNS change at the zone, never an OpenCloud setting:

```
example.com. CAA 0 issue "letsencrypt.org"
```

## 10. Is revocation actually checkable: `tlsOcspStapling`

The certificate names an OCSP responder, but the server does not attach the
revocation answer to the handshake - so every client has to ask the
authority itself, which tells that authority who is visiting, and is usually
skipped rather than treated as a failure when the responder is slow. This is
a low finding for a reason: most current authorities, Let's Encrypt among
them, no longer publish a responder at all, and the check simply does not
apply to those certificates.

## What is deliberately left unmeasured

**Nothing here reports a pass it did not measure.** A build of OpenSSL that
refuses to speak TLS 1.0 at all cannot tell the scanner whether the *server*
would have accepted it, and a missing `openssl` binary means OCSP stapling
cannot be probed. In both cases the check is left out of the result entirely
rather than recorded as passed - a gap in the output is honest; a green tick
for something nobody looked at is not.

**A certificate that fails verification is still read.** `getpeercert()`
returns nothing for an unverified peer, so on the self-signed instances this
matters most for, the scanner fetches the certificate in DER form and decodes
it independently - the same expiry date, name coverage and issuer a trusted
certificate would report, whether or not the chain validates.

## Self-signed instances

The scanner handles a self-signed or otherwise untrusted certificate without
needing to be told which case it is looking at:

1. HTTPS with certificate verification. If that works, everything above is
   evaluated normally.
2. HTTPS without verification. The scan continues and reports `tlsTrusted`
   as a failed check - the full result still comes back, plus the fact that
   the chain is not trusted.
3. Plain HTTP - `httpsAvailable` (critical).

`--insecure` (`COS_INSECURE`) skips step 1's verification requirement. The
untrusted chain is still listed in the output; it simply stops counting
against the rating. Use it for an instance you know is self-signed, so that a
*genuinely* broken certificate elsewhere still stands out rather than being
lost in an expected finding.

## Severity and rating impact

Every check on this page is an `extraChecks` entry, so a failure caps the
rating the way any failed extra check does (critical -> `D`, high -> `C`,
medium -> `A`, low -> `A+`) - see [Hardening
checks](../README.md#hardening-checks) for how that differs from a plain
hardening flag, and the extra-checks table in [the main
README](../README.md#what-the-scanner-checks) for the full severity list.

## Reference

[Reverse proxies](reverse-proxy.md) covers the headers a proxy in front of
OpenCloud should set; this page is only about the TLS layer underneath it.
