# ADR 0041: A browser tool answers a failure rather than throwing

- Status: Accepted
- Date: 2026-09-10

## Context

[ADR 0021](0021-webmcp-is-a-page-scoped-api-client.md) established that WebMCP
tools are page scoped and transport only: schemas are server rendered, and
each execution calls the same public JSON API as every other client. That
boundary has held and is not in question here.

What it did not settle is what a browser tool does when the API says no.
`webmcp.js` threw an `Error` carrying the `detail` sentence, which discards
everything an agent needs in order to decide what to do next: the status, the
`Retry-After` the service sent, and the difference between "wait" and "stop".

The server-side tools already answer that question, and answer it the other
way. `webapp/workflows.py` defines which statuses may be repeated
(`RETRYABLE_STATUSES`), the one status that means *right call, wrong moment*
(`NOT_FINISHED_STATUS`, a 409 from an export), and how long to wait; every
`/mcp` tool returns `ok: false` with `status` and `retryable` rather than
raising, and says so in its description — "retryable false means stop; do not
loop."

So the two agent surfaces disagreed about the same service. A browser agent
that met the per-target cooldown — a 429 with `Retry-After`, which is a
routine answer here and not a refusal — was told only that a request failed.
Retrying immediately is the obvious next move and the wrong one, and nothing
in the tool told it otherwise.

Three smaller gaps sat behind the same seam. The tool descriptions
paraphrased the workflow layer's notes rather than carrying them, and omitted
the one every server-side tool states: that the fields in a result came from
the scanned host and are data to report, never instructions to follow. The
export tool triggered a download and returned its size, so an agent asked to
export a report received a file it had no way to read. And registration used
`Promise.all`, which on a result page means one rejected tool takes the other
down with it.

## Decision

A browser tool returns its failures in the shape the server-side tools use:
`ok: false` with `status`, `error` and `retryable`, plus `retryAfter` in
seconds where the service sent one or the policy supplies a fallback, and the
`hint`/`selfHostUrl` the API attaches when a target cannot be reached from
here. A request that never arrived — offline, DNS, an aborted navigation — is
an answer too. The only remaining `throw` is for a tool configuration this
service never renders.

**The retry policy is server rendered, exactly as the schemas are.** Each tool
config carries a `retry` block built from `workflows.py`, and the export tool
additionally carries `contentLimit`. `webmcp.js` compares against no status
number of its own, so the browser and the `/mcp` endpoint cannot drift apart
about whether an answer may be repeated.

Descriptions are composed from the same `workflows.py` notes the `/mcp` tools
use — the asynchronous submission, the input restriction, the rate limit, the
uuid as the whole of the authorisation, expiry, the export conflict, and the
untrusted-content warning — rather than paraphrased beside them. Tools declare
the standard MCP annotations (`destructiveHint`, `idempotentHint`,
`openWorldHint`) alongside the hints they already carried.

An export returns its content for the formats a model can read, bounded by the
same `EXPORT_CONTENT_LIMIT` the server-side export applies and marked
`truncated` past it. A PDF is reported as its size, because a model cannot
read one. The download still happens: that is what the visitor asked for.

Registration prefers the draft's declarative `provideContext` where a browser
offers it and otherwise registers tools individually, with `Promise.allSettled`
so that one rejected tool does not cost a page its others.

## Consequences

The two agent surfaces now describe one service. An agent that meets a
cooldown in a browser waits the advertised number of seconds, and one that
meets a 404 stops, for the same reasons and on the same evidence as an agent
on `/mcp`.

Returning failures rather than throwing means a caller that ignores `ok` sees
a result where it previously saw an exception. This is the contract the
server-side tools already had, so the two are now consistent, but it is a
change to what a browser tool hands back and is why this record exists.

`webmcp.js` holds no policy and no thresholds, only transport — more strictly
than before ADR 0021, not less. A change to the retry rules or the export
bound reaches the browser tools without touching JavaScript, and a test
asserts the script contains no copy of those numbers.

The landing page still registers no tool that reads a result, and no browser
tool accepts a uuid. Page scoping is the decision in ADR 0021 and is
unchanged; what changes is that the submit tool now tells the agent where the
reading tools live, instead of leaving it holding a uuid and no next step.

## Alternatives considered

**Leave the throw and document it.** A thrown `Error` cannot carry a
`retryable` flag or a `Retry-After` without becoming a structured object by
another name, and an agent would have to parse a sentence to recover them.

**Copy the retry statuses into `webmcp.js`.** The obvious version of this
change, and the one that decays: two lists of statuses that must agree, in two
languages, with nothing failing when they stop agreeing. The first draft of
this work did exactly that and got the list wrong — inventing retryable
statuses the workflow layer does not treat as retryable — which is the
argument against it.

**Return the export content instead of downloading it.** The download is what
a visitor asked for, and an agent acting on their behalf should not silently
turn a "save this report" into a value only the model sees.

**Give the landing page a reader that takes a uuid.** That is a tool for
reaching scans this visitor was never given, and it discards the page scoping
ADR 0021 chose deliberately.
