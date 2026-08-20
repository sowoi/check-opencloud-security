# ADR 0010: The machine-readable descriptions are always public

- Status: Accepted
- Date: 2026-08-21

## Context

`/openapi.json` and `/arazzo.json` were served only when
`COS_WEB_ENABLE_DOCS` was set, on the reasoning that a public deployment has
no reason to advertise endpoints already documented in prose. The original
concrete reason was narrower than that: FastAPI's Swagger UI loaded its
bundle from jsDelivr, and the switch kept a third-party script off a public
page.

Two things changed. Swagger UI and ReDoc are now vendored under
`/static/vendor/`, so nothing about serving them reaches another origin; and
the audience for the schema is no longer only a developer reading it. An AI
agent that arrives at the origin with no other knowledge has exactly one way
to learn what the service does, and a document behind an environment variable
it cannot see is a document that does not exist.

The switch also protected nothing. Every endpoint it described is reachable
whether or not the schema is served, the SSRF guard, the rate limits and the
purge authorisation are enforced in the handlers, and a scan uuid is
unguessable regardless. Hiding the description hid it from honest clients
only.

## Decision

`/openapi.json`, `/arazzo.json` and `/.well-known/ai.json` are served
unconditionally, without authentication, at stable paths.

`COS_WEB_ENABLE_DOCS` continues to exist and governs exactly what it is
useful for: the two *browsable* pages, `/docs` and `/redoc`. Those still
relax the content policy on their own paths to render, which is a real change
to a page a browser executes and worth an operator's decision. A JSON
document is not.

The OpenAPI document is written by hand in `webapp/openapi.py` rather than
inferred by FastAPI. The inferred one described a form body where the API
takes JSON, a 200 where the API answers 202, and `{}` where a client needed
the shape of a result - accurate enough for a human with the source open, and
actively misleading to anything else. `tests/test_webapp_openapi.py` drives
the real endpoints and compares.

`webapp/seo.py` keeps the three documents out of the crawler's `Disallow`
list and exempt from the `X-Robots-Tag` header, because being found is now
the point.

## Consequences

An agent, a client generator or a person can fetch a complete and accurate
description of the API from any deployment, with no configuration and no
credential. The discovery document, the `<link>` hints in `base.html` and the
"For AI agents" section on `/api` all point at addresses that are reliably
there.

The cost is a maintenance obligation. The schema is now a published contract
rather than a development convenience, so an endpoint that changes shape
without `webapp/openapi.py` changing with it is a bug, and the test suite is
what makes that fail rather than mislead.

An operator who genuinely does not want the description public has no switch
for it any more. That is deliberate: the alternative was a setting whose only
effect is to make the service harder to use correctly.

## Alternatives considered

**Keep the switch and default it on.** A default is not a guarantee, and an
agent cannot tell whether it is looking at a deployment that turned the
document off or one that does not have it. The value of a discovery
mechanism is that it is unconditional.

**Serve the documents but keep them out of the sitemap and `robots.txt`.**
Half the change. A crawler is not the reader that matters here, and the paths
are named in the discovery document anyway.

**Keep FastAPI's generated schema and correct it with `openapi_extra`.** The
mismatches were not decorations - the content type, the status code and every
response body were wrong. Patching an inferred document into shape leaves the
next inferred field wrong by default, whereas a written document is wrong only
where somebody wrote it wrong, and a test can hold it to the implementation.
