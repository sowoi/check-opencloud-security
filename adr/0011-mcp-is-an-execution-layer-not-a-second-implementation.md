# ADR 0011: MCP is an execution layer over the same API, not a second one

- Status: Accepted
- Date: 2026-08-21

## Context

The service now has three descriptions of itself and one implementation:
OpenAPI says what the operations are, Arazzo says how they combine into
workflows, and the frontend renders the same thing for a person. Adding a
Model Context Protocol endpoint so that an AI agent can *run* those workflows
raises the obvious risk: a fourth surface with its own idea of how a scan is
submitted, how long to poll, when a 429 is worth retrying and who may erase
data.

That risk is not hypothetical. The natural way to write an MCP tool is to
reach for the store and the queue directly - they are right there, in the same
process, and the HTTP layer looks like overhead. Every protection this service
has, though, lives in that HTTP layer: the SSRF guard on the submitted target,
the per-client rate limit, the per-target cooldown, the field allow-list that
answers 422, and the bearer credential on the purge endpoint. A tool that
skipped it would be a second front door with none of the locks.

The polling semantics carry the same risk in a quieter form. If the MCP tool
polls every second and the Arazzo document says three, the document is wrong
about the service it describes, and the agent that read it was misled by the
thing meant to inform it.

## Decision

**One implementation, three faces.** `webapp/workflows.py` holds every
workflow-level decision in one place: the poll interval and attempt ceiling,
the submit retry count, the export retry-after, which statuses are terminal
and which are worth waiting out, and the prose explaining each of those to an
agent. Nothing else defines them.

- `webapp/arazzo.py` renders those constants into the Arazzo document. A
  number in the published workflow is the number the code uses, because it is
  the same object.
- `webapp/mcp_server.py` executes them. The tools call `workflows.py`, which
  calls this application's own HTTP API through an in-process ASGI transport -
  so an MCP request goes through the routes, the guard, the limiter and the
  authorisation exactly as a browser's does.

The tools are **user-level tasks**, not one per endpoint: `scan_instance`,
`scan_instances`, `get_scan_result`, `plan_remediation`, `export_scan`,
`erase_instance_data`. An
agent asked to scan an instance calls one tool, which submits, polls, waits
and returns a rating. Making it orchestrate create-poll-poll-poll-fetch would
be exporting our internals as its problem, and every agent would solve the
retry semantics slightly differently.

Three resources expose the OpenAPI, Arazzo and discovery documents under
`spec://` URIs, so an agent can read the contracts inside the protocol rather
than being told to make an HTTP request.

On security, the rules are the API's rules:

- only `x-forwarded-for` and `x-real-ip` are carried from the agent's request
  into the API call, so a tool argument cannot become a header;
- `erase_instance_data` takes its `Authorization: Bearer` credential from the
  MCP request headers and never from a tool argument, so the secret is never a
  value the model has seen, and it is annotated as destructive;
- the endpoint is stateless, holds no per-agent state, and inherits the rate
  limits rather than being exempt from them.

`COS_WEB_ENABLE_MCP` turns the endpoint off, and it is simply not mounted when
the optional `mcp` extra is absent, so the plugin's dependency footprint is
unchanged.

## Consequences

An agent that finds the origin can discover the specifications and then
execute against them, with the same limits as everybody else. A change to how
a scan is polled is a change in one file, and both the published workflow and
the executed one follow it.

`workflows.py` deliberately depends on nothing but a small `ApiClient`
protocol - no httpx, no FastAPI - which keeps the logic unit-testable and
keeps an HTTP client out of a deployment that only serves the web pages. Only
`mcp_server.py` supplies a concrete client.

The in-process call is not free: an MCP tool pays request parsing and
serialisation to reach code in the same process. That is the price of having
one set of rules, and it is small next to a scan.

The MCP SDK is a dependency with its own release pace, and the endpoint is
tied to it. Confining it to `mcp_server.py` and an optional extra means a
breaking change there cannot reach the API, the worker or the plugin.

## Alternatives considered

**Call the store and the queue directly from the tools.** Faster, and wrong.
The SSRF guard, the limits and the purge authorisation are properties of the
HTTP layer, and reimplementing them for agents is how they end up differing.

**Generate MCP tools automatically from the OpenAPI document.** It would give
one tool per endpoint, which is the shape the user-level tasks exist to avoid,
and it would push the polling logic back into the agent - the exact thing
Arazzo was written to stop.

**Publish the specifications and leave execution to the agent.** Adequate for
an agent with a good HTTP client and a careful author, and a trap for
everything else: the failure mode is an agent hammering a 404 forever or
treating a 409 as a missing scan. The tools encode the answers.

**A separate MCP process alongside the web service.** Another deployment unit,
another configuration surface, and a network hop that would have to
reimplement the client-address handling to keep the rate limits honest.
