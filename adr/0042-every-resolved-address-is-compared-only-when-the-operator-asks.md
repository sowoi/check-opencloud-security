# ADR 0042: Every resolved address is compared only when the operator asks

- Status: Accepted
- Date: 2026-09-13

## Context

A scan dials the name it was given once, and whichever address the resolver
put first is the whole of what it sees. For most deployments that is the whole
deployment. For a name behind a pool - round-robin DNS in front of four nodes,
say - it is a quarter of it.

The failure that matters there is the ordinary one: a configuration rollout
that reached three nodes out of four. The fourth still sends no HSTS, still
lets the documented demo accounts sign in, still runs the previous release.
Every fourth visitor gets that node, and the scan, having reached one of the
other three, reports the deployment clean. A five-minute monitoring check is
precisely what should catch this, and it could not.

`tlsAddressParity` does not help. It compares the TLS identity of the IPv4
and the IPv6 endpoint - one address per family - and four nodes behind one
certificate present the same identity whatever they serve. The other resolved
addresses were listed under `addresses` in the result document and never
dialled.

Two rules bound any answer. A probe is only ever aimed where the scan was
pointed (ADR 0036), never at an address the target chose. And the web
application's SSRF guard resolves a submitted URL, vets the addresses and pins
the scan to them; nothing the scanner does may widen that.

## Decision

`ScannerSettings.check_all_addresses` - `--all-addresses` on the plugin and
the `scan` subcommand, `scanner.check_all_addresses` in the file - repeats the
node-dependent part of the scan against each resolved address in turn and
reports `addressParity`. It is **off by default**.

**The node-dependent part** is what a rollout changes: the release in
`status.php`, the graded headers as pass/fail, the measures
`derive_hardenings` reads from the root page, capabilities, authentication
challenge and identity provider, and whether the demo accounts sign in. What
every node shares - the certificate chain, the DNS records - is not asked
again. Headers are compared by verdict rather than value, so two nodes whose
CSP differs only in a nonce are the same.

**The addresses come from the resolver's answer for the scanned name, or from
the caller's pin when there is one.** Each request still carries that name in
`Host` and SNI; only the address the connection goes to changes, through the
same pinned pool the web application already uses. Nothing the instance says
can add an address, and a pinned scan never asks the resolver at all. IPv6
addresses are left out when `ipv6_enabled` is false, for the reason that
setting exists.

**The first address is the reference**, not a majority: with two nodes there
is no majority, and "these disagree" is the finding either way. Which node is
wrong is for whoever runs them. An address that resolves but does not answer
is a failure too - it is a node every n-th visitor fails on.

**The severity follows the worst difference**, because the scan's own rating
was built from whichever node answered first and that may be the healthy one:
a node where the demo accounts sign in carries that finding's severity, a
node on another release is `high`, any other drift is `medium`. A header or
check the operator waived is left out of the comparison.

**One address means no finding at all** - an absence, not a pass, and no
second round of requests.

**The web application never turns it on.** `scanner_settings_for` sets it to
`False` explicitly, it is not a request field, and it has no `COS_WEB_*`
equivalent. A request chooses what to scan, never how hard, and this option is
exactly "how hard": a stranger's URL would buy a dozen requests and a demo
sign-in per node of somebody else's pool.

## Consequences

An operator who runs a pool can have the check that catches a half-finished
rollout, at about a dozen requests per address. The first address is dialled
twice - once by the scan, once as the reference - which keeps the comparison
a single code path at the cost of one address's worth of requests.

It sees what DNS sees, and no further. A pool behind a single load-balancer
address has one address and gets no finding; a resolver that returns a
rotating subset of a larger pool compares that subset; GeoDNS answers for the
monitoring host's location. These are limits of asking from outside, and the
documentation says so rather than implying coverage.

`addressObservations` joins the result document, empty unless the option ran,
so a consumer can see per node what was compared.

## Alternatives considered

**Turn it on by default.** Most deployments have one address and gain
nothing, and on those that do not, every scan would multiply its requests -
demo sign-ins included - against production nodes nobody asked it to visit
individually. The default stays what an operator agreed to by pointing the
plugin at a name.

**Widen `tlsAddressParity` to every address.** It would still compare only
TLS identity, which is the one thing a pool behind one certificate never
differs in. The rollout failure lives in headers, configuration and release.

**Repeat the entire scan per address.** Debug ports, CAA, DNSSEC and the
certificate chain are properties of the name or the shared front, not of one
node, and the lifecycle verdict follows from the version already compared.
Running them per address costs several times the requests to report the same
answer n times.

**Rate each node separately and report the worst.** Honest, but it makes one
check invocation produce several ratings, and the plugin's thresholds, perfdata
and baseline all assume one per host. A single finding whose severity follows
the worst difference caps the rating the same way and keeps one verdict.

**Offer it in the web application for addresses the guard already pinned.**
The pin makes it safe from SSRF, not proportionate: the cost lands on a
deployment whose owner never asked, and the service's rate limit counts
submissions rather than the requests each one fans out to.
