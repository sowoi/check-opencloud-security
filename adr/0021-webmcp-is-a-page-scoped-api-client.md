# ADR 0021: WebMCP is a page-scoped API client

- Status: Accepted
- Date: 2026-08-26

## Context

The service already supports agents through OpenAPI, Arazzo, and a
server-side MCP endpoint. A browser agent has one useful piece of context
those surfaces do not: the page the user is looking at. WebMCP can expose the
landing page's scan form and a result page's current UUID without asking the
agent to rediscover either.

Registering browser tools creates another execution surface. If those tools
called the store, queue, or scanner directly, they would bypass the SSRF
guard, limits, cooldown, and capability checks in the HTTP API. Tool schemas
can also drift from the options rendered in the form.

## Decision

WebMCP tools are page scoped and transport only. Jinja serializes each page's
tool definitions, including enums built from the release-track, waiver, and
export catalogues. A self-hosted script registers them after
`DOMContentLoaded`. It supports the earlier `navigator.modelContext` API and
the current `document.modelContext` draft through feature detection.

Each execution calls the same public JSON API used by other clients and sends
`Accept: application/json`. The landing page registers
`scan_opencloud_security`. A result page registers `get_scan_result` and
`export_scan_report` for its UUID. Other pages register nothing.
`COS_WEB_ENABLE_MCP` controls both these registrations and `/mcp`.

`/llms.txt` gives language-model clients a short map of the stable discovery,
API, workflow, MCP, and WebMCP surfaces. It contains no scan data and no
listing mechanism.

## Consequences

Browser agents inherit the API's SSRF checks, rate limits, cooldown, queue,
and result isolation. Tool arguments can choose what to scan but cannot set
timeouts, concurrency, or TLS policy. A page without WebMCP support behaves
exactly as before.

WebMCP remains a draft and browser implementations can differ. The small
compatibility branch is confined to one script. Schemas stay server rendered,
so a catalogue change reaches the form and browser tool together.

## Alternatives considered

**Call application internals from browser-specific endpoints.** This would
create a less protected route to the scanner and duplicate the API.

**Register every API operation on every page.** That would discard the page
context and expose actions unrelated to what the user is viewing.

**Use the server-side MCP endpoint from the browser tool.** This adds a
protocol translation and optional authentication dependency when the browser
can call the same JSON API directly.
