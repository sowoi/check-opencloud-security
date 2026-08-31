# ADR 0031: A response is uncacheable until a route opts in

- Status: Accepted
- Date: 2026-08-31

## Context

[ADR 0002](0002-no-scan-result-caching.md) settled what *this service* keeps
between requests: nothing. Every submission gets its own uuid and its own
scan, and no result is ever handed to a second caller. That decision governs
the process. It says nothing at all about what sits **between** this service
and the browser.

That gap matters here more than it would elsewhere, because a result page's
entire authorisation is the uuid in its URL ([ADR 0007](0007-erasure-on-request.md)).
The URL *is* the credential. A shared forward proxy, a corporate cache or a
CDN that stored one response and replayed it would hand somebody's security
report to whoever asked for that URL next, and would keep doing so after the
Redis TTL had expired the result this service promises to forget. A scan
result outliving its own erasure inside an intermediary nobody in this project
operates is the precise failure ADR 0002 and ADR 0007 exist to prevent, and
neither of them reaches it.

[ADR 0009](0009-public-pages-indexable-results-never.md) already met the same
problem in the crawler channel and drew the conclusion that shapes this one:
the two kinds of page have to be separated **by construction rather than by
remembering to add a tag**. A rule that depends on every future route author
thinking about caching fails the first time somebody adds a route while
thinking about something else.

## Decision

**`Cache-Control: no-store` is the default for every response, and a route
that wants to be cached has to say so.**

- `no-store` is a member of `SECURITY_HEADERS` (`webapp/app.py:214`), applied
  by the `_security_headers` middleware to every response of every route -
  HTML, JSON, exports, redirects and errors alike, including the routes that
  render no template and so were never covered by anything in a base
  template.
- The middleware uses `response.headers.setdefault`, **not** assignment. The
  default is what a route receives by having no opinion, and a route with an
  opinion keeps it. This is the whole of the mechanism, and the direction of
  the fallback is the point: forgetting to think about caching yields
  `no-store`, never a cacheable scan result.
- Opting in is a single line beside the route, and the opt-ins are a closed,
  greppable list. Exactly eleven routes set `public, max-age`, and every one
  of them publishes metadata **about this service** rather than about
  anybody's instance: the OpenAPI, Arazzo, discovery and protected-resource
  documents, `robots.txt`, `agents.txt`, `agents.json`, `security.txt`,
  `llms.txt`, `llms-full.txt` and `sitemap.xml`.
- **No route that opts in is translated.** The frontend's language is chosen
  per request ([ADR 0020](0020-frontend-language-is-request-scoped.md)), so a
  publicly cached translated page would serve one visitor's language to the
  next. No opt-in route calls a translator, so none needs a `Vary`.
- `Cache-Control` is therefore a header this service **sends**. It is
  deliberately not a header this service **measures** on a scanned instance;
  see the alternatives.

## Consequences

The capability model now holds in three independent channels rather than two:
this service reuses no result ([ADR 0002](0002-no-scan-result-caching.md)), no
crawler indexes one ([ADR 0009](0009-public-pages-indexable-results-never.md)),
and nothing downstream retains one.

A new route is uncacheable by omission. Adding one that shows anything about a
scan is safe without its author having considered caching at all, which is the
same property ADR 0009 bought for indexing and for the same reason.

A route that genuinely should be cached declares it in one line next to
itself, and those lines are the review surface: eleven sites, all findable
with `grep -n "Cache-Control" webapp/app.py`, all publishing service metadata.
A twelfth appearing in a diff is a question worth asking, and any opt-in
naming a `/scan/` or `/api/scans/` path is simply wrong.

Making a translated page publicly cacheable becomes a bug requiring `Vary`.
This is recorded because the invariant currently holds through *which* routes
happened to opt in rather than through anything enforcing it - the eleven are
machine-readable documents that were never going to be translated. Nothing
stops a future opt-in from being a rendered page.

A deployment that puts its own CDN in front of this service still has to
configure that CDN to honour `no-store`. A cache that ignores the header is
outside what this service can enforce, and the header is the whole of what it
can do.

## Alternatives considered

**Set the header on each route that needs it.** Rejected for ADR 0009's
reason: it is correct exactly as long as everyone remembers, and the cost of
one lapse is a replayed scan result rather than a cosmetic defect.

**Assign rather than `setdefault`, making `no-store` unconditional.** This
would be stronger - no route could weaken it even deliberately. Rejected
because the machine-readable documents are fetched repeatedly by agents,
crawlers and OpenAPI clients that have no business refetching an unchanged
`sitemap.xml` on every request, and the opt-in list is small enough to audit
by eye. The strength gained is over a list of eleven documents that contain
nothing about anybody.

**Add `Pragma: no-cache` and `Expires: 0` beside it.** The HTTP/1.0
belt-and-braces. Rejected: every cache this service can plausibly sit behind
understands `no-store`, and two more headers on every response buys
compatibility with intermediaries that have not existed for two decades.

**Measure `Cache-Control` on the scanned instance as a hardening flag.**
Rejected, and worth writing down so it is not re-derived. Verified against
`services/proxy/pkg/middleware/security.go` in
[opencloud-eu/opencloud](https://github.com/opencloud-eu/opencloud): the
proxy's `Security` middleware sets CSP, `X-Content-Type-Options`,
`SAMEORIGIN`, a referrer policy, ten-year HSTS with preload, permitted
cross-domain policies and a robots tag - and no `Cache-Control` whatsoever. A
header no OpenCloud sends could only ever be advisory
([ADR 0028](0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md)).
But the three advisory headers are presence checks, where having the header is
good and lacking it is neutral, and `Cache-Control` is not that shape: its
correct value depends on what the response *is*, and a static asset should
carry `public, max-age=...`. The scanner only ever sees unauthenticated
responses - the landing page, and the 401s from `PROTECTED_ENDPOINTS` - which
is exactly where `no-store` is *not* the right answer. A flag preferring it
would advise something wrong on a correctly configured instance, which is the
bar `docs/sharing.md` already uses to reject `federation.incoming`.
