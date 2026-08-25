# ADR 0020: Frontend language is request scoped

- Status: Accepted
- Date: 2026-08-25

## Context

The public frontend needs to follow a visitor's browser language and let that
visitor choose another language without duplicating every template or changing
the stable addresses of pages and scan results. Result evidence and
machine-readable contracts must not be translated: their exact values and
wording are consumed by operators and software.

## Decision

Hand-written frontend text uses stable identifiers in server-side string
catalogues for English, German, Spanish and French. English is the source and
fallback. Each request chooses a locale from a validated preference cookie,
then the weighted `Accept-Language` header, then English. A same-origin POST
switcher stores an `HttpOnly`, `SameSite=Lax` cookie and returns only to a
validated local path.

Templates remain shared. The locale, translator and language choices are
injected into their common context, and pages set the matching `lang`
attribute. JavaScript reads translated phrases from rendered `data-*`
attributes rather than carrying a second catalogue. OpenAPI, Arazzo, MCP,
discovery documents, exports and measured scan evidence remain English or
verbatim. Generated operator-guide bodies remain English and say so in
localized chrome; their titles, summaries and navigation are translated.

## Consequences

One route keeps one URL in every language, including capability-bearing result
pages. Responses vary on both `Accept-Language` and the language cookie, so
caches must respect the `Vary` header. Every catalogue must keep exact key,
placeholder and markup parity with English, enforced by tests.

Adding hand-written frontend copy now means adding a stable English key and
all three translations. Static search ships one release-built index per
locale. The switcher works without JavaScript, and scripts may enhance it but
cannot own locale selection.

## Alternatives considered

Separate translated templates were rejected because their structure would
drift. Locale path prefixes and query parameters were rejected because they
would multiply public and capability URLs. Browser-only translation was
rejected because it fails without JavaScript, duplicates strings in scripts
and initially serves incorrect metadata. External translation services were
rejected because they disclose page use and violate the same-origin rule.
