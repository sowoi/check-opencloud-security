# ADR 0037: Preload eligibility is measured, list membership is not

- Status: Accepted
- Date: 2026-09-04

## Context

`hstsPreload` has always answered one question: is the word `preload` in the
`Strict-Transport-Security` header. That is the operator's *intention*, and
it is not the same as the fact an operator believes they have. A host is
protected before its first request only if it is actually in the browser
preload list, and the directive alone never put it there - the domain has to
be submitted, and the submission has to be accepted.

The two diverge constantly, and always in the direction that flatters: a
header saying `preload` on a domain that was never submitted, or was
submitted and refused, or was removed. Reporting the directive as though it
were the state tells an operator they have a protection they do not have,
which is worse than reporting nothing.

Measuring actual membership means one of two things, and neither is
available:

- **Query hstspreload.org.** One HTTPS request, an authoritative answer - and
  it hands a third party the hostname being scanned, which is the one thing
  this project's README promises never to send anywhere. ADR 0024 already
  refused exactly this trade for the CAA lookup.
- **Bundle the list.** No third party, but Chromium's
  `transport_security_state_static.json` is tens of megabytes and roughly a
  hundred and fifty thousand entries. Even hashed down to a set of digests it
  is megabytes of data shipped in a wheel whose whole point is being small
  enough to sit on a monitoring host, refreshed on a cadence this project
  does not control, and stale between refreshes in a way that would produce
  confident wrong answers.

What *is* measurable locally is whether the submission would be accepted at
all. The list publishes its requirements, and every one of them is in the
header: `max-age` of at least one year, `includeSubDomains`, and `preload`.

## Decision

A second observation, `hstsPreloadEligible`, records whether the header this
instance sends meets the browser preload list's stated requirements. It never
claims to know whether the domain is on the list; it answers the question
that can be answered from the response, which is whether asking could
possibly work.

**It is an advisory check, not a hardening flag.** OpenCloud's own proxy
sends a ten-year `max-age` and `preload` but no `includeSubDomains`, so the
header on every stock instance asks for something the list refuses. That
makes the shortfall a fact about OpenCloud rather than about any one
deployment - the exact criterion ADR 0028 set for the response headers no
OpenCloud sends, and ADR 0034 for what is not a header. It is reported under
`setup.advisoryChecks`, explained by `--debug` and listed in the catalogue,
and it never reaches `_collect_missing_hardenings`, the alert line, the
`hardenings_missing` metric, the webhook, an exit code, or the waiver tick
boxes.

`hstsPreload` keeps its identifier and its meaning. The two are complementary
and the pair is the point: the directive is present, and it would not be
honoured.

## Consequences

No new dependency, no new outbound request, no bundled data, and nothing
about the instance leaves the machine running the scan - the check reads a
header the scan already fetched.

The finding is `False` on every stock OpenCloud, which would be unacceptable
noise as a hardening flag and is exactly what the advisory block is for. An
operator who adds `includeSubDomains` at the reverse proxy sees it flip to
`True`, which tells them the header is now worth submitting - and the check
still does not claim the submission happened.

A domain that meets every requirement and was never submitted reports `True`.
That is the honest limit of what a response header can prove, and the
catalogue entry says so rather than letting the reader assume otherwise.

## Alternatives considered

**Query hstspreload.org's API.** Authoritative, trivial to implement, and it
leaks the scanned hostname to a third party the operator never chose. Refused
for the same reason ADR 0024 refused a public DNS resolver.

**Bundle a hashed preload list, refreshed by `refresh-data`.** The
attestation machinery from ADR 0027 would carry it, so the mechanism exists.
The size does not fit a plugin that is meant to be small on a monitoring
host, the refresh cadence is somebody else's, and a stale copy answers
membership questions confidently and wrongly.

**Tighten `hstsPreload` itself to require all three directives.** One
identifier instead of two, and it silently changes what an existing waiver,
alert rule and graph mean - an instance that passed yesterday fails today
with no new evidence. Keeping the measured facts separate lets the old one go
on meaning what it always meant.

**Emit the check only for instances that ask to be preloaded.** Attractive -
nobody fails an application they never made - and it produces a key that is
sometimes absent, which a reader cannot tell from a scan that did not run.
Reporting it always, and never counting it, says the same thing without the
ambiguity.
