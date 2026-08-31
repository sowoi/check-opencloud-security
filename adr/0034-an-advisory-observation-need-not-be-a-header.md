# ADR 0034: An advisory observation need not be a header

- Status: Accepted
- Date: 2026-08-31

## Context

[ADR 0028](0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md)
settled what to do with a measurement that is worth publishing and wrong to
alert on: `Permissions-Policy` and the Cross-Origin policies are reported
under `setup.advisoryHeaders`, explained by `--debug` and the web catalogue,
and counted nowhere. The argument had nothing to do with headers. It was
about *what a missing thing means*: OpenCloud sends none of them on any
instance, so an absence describes the software rather than this deployment,
and turning it into a finding hands every `--check-hardening` user a WARNING
that no change to their instance clears.

That argument applies word for word to something that is not a header.
RFC 9116 asks a service to publish `/.well-known/security.txt` saying how to
report a vulnerability. OpenCloud publishes none, on any instance. Somebody
who finds a flaw and cannot find an address for it falls back to a public
issue tracker or to nothing, and a report that never arrives looks, from the
outside, exactly like a flaw nobody found.

`setup.advisoryHeaders` could not carry it. The key is named for headers, its
`{name: bool}` entries are header names, and every consumer that reads it -
the plugin's explanation, `webapp/catalog.py`, the tests - treats a key there
as something to look for in a response. A file path in that block would be a
lie about the shape of the data.

## Decision

The result document gains `setup.advisoryChecks`, a sibling of
`setup.advisoryHeaders` carrying the same `{id: bool}` shape and obeying the
same rule: **measured, explained, published, never counted.** Its first
member is `securityTxtPublished`.

Everything ADR 0028 decided about an advisory header holds unchanged for an
advisory check. It is absent from `_collect_missing_hardenings`, so it reaches
neither the alert line, the `hardenings_missing` metric, the webhook payload
nor the exit code. It does not participate in the rating. It is not offered
as a waiver, because nothing alerts on it and the tick box would say
otherwise. It **is** explained by `--debug`, under a heading that says plainly
it is not counted, and it **is** listed in the web catalogue through the same
`describe_hardening` as every other check.

Two things are specific to this block rather than inherited.

**An observation nobody made is not an observation that failed.** The block is
`{}` when a scan ran with `--no-extra-checks`, not a dictionary of `false`.
The advisory headers can afford `false` for an unread response because they
are read from a response the scan always fetches; this check costs a request
of its own, and a reader cannot tell "no policy published" from "never asked"
once both are written the same way.

**A status code is not an answer.** OpenCloud's frontend serves its own
single-page shell for every unknown path, so `GET /.well-known/security.txt`
returns 200 with HTML on a great many instances. The check reads the body and
requires the `Contact` field RFC 9116 makes mandatory - the only field that
tells a finder anything - and rejects a response served as markup. A check
that trusted the status code would report every OpenCloud behind a catch-all
route as publishing a policy it does not have, which is worse than not
checking: it is a confident wrong answer about where to send a vulnerability
report.

The explanations live in `hardening.ADVISORY_CHECKS`, deliberately not in
`HARDENINGS`. `webapp/catalog.py` builds its waiver tick boxes by iterating
`HARDENINGS`, so an entry placed there would become waivable - and offering
to waive something that never alerts tells a visitor it does.

## Consequences

The result document grows one key under `setup`. Consumers that iterate
`setup.headers` or `setup.advisoryHeaders` are unaffected, and the plugin
reads a document without the new key as having nothing to say, so a result
from an older scanner still explains correctly.

A scan with the extra checks on costs one more HTTP request. That is the
honest price of the check and the reason it is gated with the rest of them.

The block invites members that do not belong. "Reported but never counted" is
comfortable - nothing breaks, nobody is alerted - and a check that cannot
justify a finding is easier to add here than to argue for. The bar stays the
one ADR 0028 set: an observation belongs here when OpenCloud satisfies it on
no instance, so its absence describes the software. A finding that says
something about *this* deployment belongs in `extraChecks`, where it can
change a rating, or nowhere.

A member leaves this block the way an advisory header does: when OpenCloud
starts shipping the thing by default, at which point its absence becomes a
fact about the deployment and a countable finding again.

## Alternatives considered

**Put `securityTxtPublished` in `setup.advisoryHeaders`.** The least code and
a false statement about the data: consumers read those keys as header names.

**Make it an ordinary hardening flag.** It would alert every existing user
about the shipped state of OpenCloud rather than about their deployment - the
outcome ADR 0028 exists to prevent - and it would appear as a waiver tick box
in the web application, inviting a visitor to accept a finding nothing raises.

**Make it an `extraChecks` finding with severity `low`.** `low` still caps a
rating at 5 and still reaches `failed_extra_checks`, so it would show up in
the alert line. A severity that meant "never counted" would be a fourth
mechanism for the thing this block already is.

**Check the top-level `/security.txt` too.** RFC 9116 lists it only as a
legacy location for hosts that cannot serve `/.well-known/`. A second request
per scan to credit a deprecated path is not worth it, and the remediation
names the canonical one.

**Also report whether the file has expired.** RFC 9116 requires `Expires`, and
a lapsed policy is a real and common failure. It is a second observation with
a second bool, and it can be added to this block later without any of the
above changing - which is the point of the block being a block.

**Leave it unmeasured.** The status quo, and the reason the gap existed. It
keeps the report short by giving up an improvement an operator would act on
if told about it.
