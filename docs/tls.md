# TLS and certificates: what this scanner checks, and why

Everything on this page happens before a single byte of HTTP is exchanged.
OpenCloud's proxy terminates TLS itself on port 9200 (or whatever sits in
front of it does), and this scanner reads what that transport actually
negotiated - protocol version, certificate, chain, cipher suite - the same
way a browser or a sync client would, without any special access.

<!-- TOC -->
* [TLS and certificates: what this scanner checks, and why](#tls-and-certificates-what-this-scanner-checks-and-why)
  * [1. Can a TLS connection be made at all: `tlsHandshake`, `httpsAvailable`](#1-can-a-tls-connection-be-made-at-all-tlshandshake-httpsavailable)
  * [2. Is the certificate trusted: `tlsTrusted`](#2-is-the-certificate-trusted-tlstrusted)
  * [3. Is the protocol current: `tlsProtocol`, `tlsDeprecatedProtocol`](#3-is-the-protocol-current-tlsprotocol-tlsdeprecatedprotocol)
  * [4. Does the certificate cover this name: `tlsHostname`](#4-does-the-certificate-cover-this-name-tlshostname)
  * [5. Is the chain complete: `tlsChain`](#5-is-the-chain-complete-tlschain)
  * [6. Is the certificate about to expire, or issued for too long](#6-is-the-certificate-about-to-expire-or-issued-for-too-long)
  * [7. Is the negotiated cipher suite and certificate policy sound](#7-is-the-negotiated-cipher-suite-and-certificate-policy-sound)
  * [8. Do IPv4 and IPv6 present the same service: `tlsAddressParity`](#8-do-ipv4-and-ipv6-present-the-same-service-tlsaddressparity)
  * [9. Is certificate issuance restricted: `tlsCaaRecord`](#9-is-certificate-issuance-restricted-tlscaarecord)
  * [10. Is revocation actually checkable: `tlsOcspStapling`](#10-is-revocation-actually-checkable-tlsocspstapling)
  * [11. Was the certificate published to a log: `tlsCertificateTransparency`](#11-was-the-certificate-published-to-a-log-tlscertificatetransparency)
  * [12. Is a replayable 0-RTT flight invited: `tlsEarlyData`](#12-is-a-replayable-0-rtt-flight-invited-tlsearlydata)
  * [What is deliberately left unmeasured](#what-is-deliberately-left-unmeasured)
  * [Self-signed instances](#self-signed-instances)
  * [Severity and rating impact](#severity-and-rating-impact)
  * [Reference](#reference)
<!-- TOC -->


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

Whether plain HTTP is *redirected* to HTTPS is a separate flag,
`httpsEnforced`, decided at the proxy rather than in the TLS layer - see
[Two findings decided here that are not
headers](reverse-proxy.md#two-findings-decided-here-that-are-not-headers).

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

## 11. Was the certificate published to a log: `tlsCertificateTransparency`

Certificate Transparency is the public, append-only record of every
certificate a public authority issues. It exists so that a domain owner can
find out that somebody else was issued a certificate for their name - a
mis-issuance that would otherwise be invisible until it was used.

A certificate participates by carrying **signed certificate timestamps**
(SCTs) embedded by the issuing authority. The scan counts them in the
certificate it already fetched, using the same `openssl x509 -text` call that
reads the key and signature algorithm - no extra connection and no extra
process.

Chrome and Safari refuse a publicly trusted certificate without SCTs
outright, so this is an outage waiting for the next browser release rather
than only a transparency gap, which is why it is a `medium` finding.

**The check only runs where the question is fair.** A private or self-signed
authority cannot publish to a log, and OpenCloud generates a self-signed
certificate during `opencloud init` - so on a large share of instances the
honest answer is that the question does not apply. `tlsCertificateTransparency`
is therefore withheld entirely unless the chain reaches a public root. It is
also withheld when the local OpenSSL does not decode the extension at all:
an absent finding is an unknown, never a pass.

**Fix:** reissue through a certificate authority that embeds SCTs. Every
public one has done so for years, Let's Encrypt included; a trusted
certificate without them was almost certainly issued by a private CA that is
nonetheless in the client trust store.

## 12. Is a replayable 0-RTT flight invited: `tlsEarlyData`

TLS 1.3 lets a resuming client send its first request in the same flight as
the handshake - "0-RTT", or early data. It saves a round trip and it has no
replay protection at the TLS layer, by design: anyone who can record that
flight can send it again, and the server cannot tell the copy from the
original.

For a file service that means a request to move, copy or delete replayed at a
moment of somebody else's choosing. A correct server restricts 0-RTT to
idempotent requests, but nothing on the wire proves that it does, which is
why this is a `low` finding rather than a higher one.

The scan reads the `Max Early Data` limit the server's own session tickets
advertise, from the same `openssl s_client` handshake that answers the
stapling question. A server that never mentions a limit - a TLS 1.2 server,
or one whose tickets forbid early data on some builds - is reported as
unknown rather than as accepting it.

**Fix:** switch early data off in whatever terminates TLS. nginx's
`ssl_early_data` is `off` by default; Caddy and Traefik do not enable it.
Leave it on only where a measured latency problem justifies it *and* the
application is known to reject replayed non-idempotent requests.

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
README](scanner-checks.md#what-the-scanner-checks) for the full severity list.

## Reference

[Reverse proxies](reverse-proxy.md) covers the headers a proxy in front of
OpenCloud should set; this page is only about the TLS layer underneath it.
