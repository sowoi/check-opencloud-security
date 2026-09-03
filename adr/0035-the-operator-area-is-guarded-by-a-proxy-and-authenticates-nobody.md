# ADR 0035: The operator's area is guarded by a proxy and authenticates nobody

- Status: Accepted
- Date: 2026-09-02

## Context

A deployment run for other people eventually needs an operator to be able to
see what it is doing and to act on it: whether the worker is alive, what the
limits are set to, when the release schedule and the advisory database were
last read, and - when something looks wrong - what the audit trail says. Until
now all of that meant a shell on the host.

Three things make this harder than an ordinary admin page.

The service has, deliberately, no notion of an account. [ADR
0015](0015-the-mcp-endpoint-may-require-a-sign-in.md) made `/mcp` an OAuth
resource server precisely so that this service would never issue, store or
check a credential of its own, and `webapp/mcp_auth.py` says so in its first
paragraph: no login page, no session, no consent screen. A browser-facing area
cannot use that - a bearer token is not something a person has - so it would
otherwise mean building the first login flow in the codebase: authorization
code, PKCE, state, nonce, a signed session cookie, CSRF on every action. That
is a large amount of new security-critical code in a project whose security
model is currently "we hold nothing".

The area is also the first surface that can *change* what the scanner knows,
by refreshing the two reference documents, and the first that can read the
audit trail - which is pseudonymised, but is still the record of who asked
this service to scan what.

And the obvious third button, "rebuild the search index", contradicts an
existing decision outright: the index is a release artefact, the generator is
not part of the deployed bundle, and the container filesystem is read-only.

## Decision

**The area exists only when an operator asks for it.** `COS_WEB_ADMIN_ENABLED`
is off by default, and off means the routes are never registered - `/admin`
answers the same 404 as any other unknown path. A deployment that does not use
the feature does not disclose that the feature exists.

**Authentication happens in front of the service, not in it.** An authentik
proxy provider signs the operator in and forwards the identity it established
as ordinary headers. This service adds no login page, no session and no cookie
of its own, and the rule from ADR 0015 holds unchanged: it never issues,
stores or accepts a credential it minted.

**The headers are believed because of a shared secret, not because they
arrived.** The proxy adds `COS_WEB_ADMIN_PROXY_SECRET` as `X-COS-Admin-Proxy`;
the service compares it in constant time and refuses everything without it. A
header alone is something anybody who can reach the container could send.

**Being signed in is not being an operator.** `COS_WEB_ADMIN_USERS` is the
guest list. An empty list with the area enabled is refused at startup rather
than read as "anybody the provider authenticated", because an identity
provider may exist to let strangers sign in to something else entirely.

**A deployment that cannot enforce any of that refuses to start**, in the same
way and for the same reason as a sign-in on `/mcp` that cannot be checked.

**Every refusal is the same 404.** No secret, a wrong secret, no name, a name
nobody listed - all indistinguishable, because the difference is only useful
to somebody finding out whether the area is there.

**The area reads state and borrows the worker's two refreshes, and does
nothing else.** The buttons call `refresh_schedule` and `refresh_advisories` -
the same functions with the same acceptance rules - behind a per-action
cooldown, so a button cannot be held down against somebody else's
documentation site. The statistics are counts and configured limits; no
target, uuid, result or client address is reachable from the module.

**The search index is reported, never rebuilt.** The area says whether the
shipped index still describes this build - by pages, by languages, and by the
release stamp the generator now writes into it - and names the release
workflow as the thing that fixes it.

**The audit view is a window on the log, not a second copy of it.** It streams
the records the audit log already wrote, from the file when
`COS_WEB_AUDIT_LOG_FILE` named one and otherwise from a bounded in-memory ring
that exists only when both the trail and the area are on. Nothing resolves a
fingerprint back to an address, because nothing can: the salt is one way and
there is no map.

**The area is never advertised.** `noindex, nofollow, noarchive`, absent from
the sitemap, from `llms.txt`, from `/openapi.json`, from the documentation
manifest and from the search index - and deliberately *not* in `robots.txt`,
because a `Disallow` line is a public file naming the path.

## Consequences

An operator gets a console without this service learning what an account is.
The blast radius of a mistake in the new code is bounded by the proxy in front
of it: a bug in the header check cannot be reached without first passing
authentik.

The cost is a deployment requirement. The area is unreachable unless something
in front adds the secret header, so a hand-rolled reverse proxy has to be
configured for it; `docker/setup-wizard.py` warns when the area is enabled
without the bundled Authentik, and `authentik/blueprints/opencloud-admin.yaml`
provisions the provider, the group and the outpost for the stack that has it.

Two limits are worth stating. The freshness check cannot compare page *body*
text, because the generator that extracts it is not deployed - it compares
pages, languages and the release stamp, which catches the case that actually
occurs. And the in-memory audit window is per-process: with more than one
replica, a reader sees the records of the replica they reached.

## Alternatives considered

**An OIDC authorization-code flow inside the service** was rejected for the
amount of security-critical code it adds - session storage, cookie signing and
rotation, PKCE, state and nonce handling, CSRF on every action - all of it
first-of-its-kind in this codebase, and all of it in front of the one surface
that can change what the scanner knows.

**Rebuilding the search index from the area** was rejected as a direct
contradiction of the release-artefact rule: it would put page text nobody
reviewed in front of every visitor's search, and the read-only container
cannot write it anyway.

**Writing audit records to Redis so the view survives a restart** was rejected
because it is new retention of exactly the data the service is careful not to
keep. A bounded in-process window shows what is happening now, which is what
the view is for.

**A `Disallow: /admin` line in `robots.txt`** was rejected because it would
publish the path to everybody who reads that file, which is the opposite of
what a rule intended to keep crawlers out should achieve.
