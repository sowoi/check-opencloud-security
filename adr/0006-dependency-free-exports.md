# ADR 0006: Exports rendered without a reporting dependency

- Status: Accepted
- Date: 2026-08-19

## Context

A result somebody reads on the dashboard is a result they want in a ticket, a
spreadsheet or a code-scanning tool. CSV and SARIF existed as an obscure side
effect of `output_format`, and a PDF - the format most often asked for when a
scan has to be attached to a review - did not exist at all.

A PDF normally means a reporting library. This service ships nothing to the
browser it did not write, keeps the web image small enough to audit, and
serves people scanning instances they are responsible for; a rendering engine
pulled in for one endpoint is a large amount of code to trust for a page of
text.

## Decision

`GET /api/scans/{uuid}/export/{format}` renders one finished scan as `json`,
`csv`, `sarif` or `pdf`, and the result page offers all four as plain download
links. Every renderer lives in `webapp/reports.py` and starts from
`catalog.summarise()`, the same regrouping the dashboard uses, so an export
cannot disagree with the page it was downloaded from and no export decides
anything.

The PDF is written by hand: page objects, a content stream per page, a
cross-reference table and Helvetica. It is a few hundred lines of primitives
with no dependency, and the tests check the file against the objects a reader
actually needs rather than against a golden copy.

Exports are produced on request and stored nowhere, so they inherit the scan's
TTL exactly. A scan that has not finished answers **409** rather than 404: it
exists, and a 404 would send a caller into a retry loop against the wrong
endpoint.

## Consequences

The web image gains no reporting dependency, and the export layer stays small
enough to read in one sitting. The PDF is plain: one type family, no cover
page, no charts, no embedded fonts, and text wrapped on a character count
rather than font metrics. That is the trade, and a richer document would mean
revisiting this decision rather than quietly adding a library.

Adding a fifth format means one function and one row in the format table.

## Alternatives considered

### 1. ReportLab, WeasyPrint or a headless browser

Each renders a better-looking document. Each is also a large dependency, and a
headless browser in a service that fetches URLs strangers supply is a new
class of problem entirely.

### 2. Keep using `output_format` for exports

It made the format a property of the scan rather than of the request that
reads it, so a dashboard scan could never be downloaded as a PDF and a caller
had to decide the format before the result existed.

### 3. Render the exports in the worker and store them

Three more Redis values per scan, each with the same TTL, to save a
sub-second rendering that most scans never ask for.
