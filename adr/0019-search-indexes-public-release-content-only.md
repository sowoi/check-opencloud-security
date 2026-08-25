# ADR 0019: Search indexes public release content only

- Status: Accepted
- Date: 2026-08-25

## Context

The frontend has enough operator guidance that navigation alone is no longer
an efficient way to find one setting or check. A runtime crawler would make
the search index change independently of a release and, worse, could acquire
access to the Redis-backed scan namespace whose UUIDs are capabilities.

## Decision

Browser search uses a checked-in JSON index built from an explicit manifest of
public, pre-scan templates. The release workflow rebuilds and commits it only
when publishing a new version. The browser fetches that same-origin file and
filters it locally.

The generator has no store, queue, API, result-template, or network input.
Result pages, exports, submitted addresses, and UUIDs therefore cannot enter
the index. Adding a searchable page requires adding it to the public manifest.

## Consequences

Search works without a database or search service and is identical for every
visitor to one release. Documentation changes intentionally do not appear in
search until the next release. The checked-in index must ship with the
frontend and the release workflow must refresh it before building artifacts.

## Alternatives considered

A runtime full-text index was rejected because it adds mutable state and risks
crossing the result-data boundary. A remote search provider was rejected
because it would disclose queries and violate the frontend's third-party rule.
Server-side filtering of the static file was rejected because the browser can
do the same work without adding an endpoint.
