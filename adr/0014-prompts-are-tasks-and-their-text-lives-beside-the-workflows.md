# ADR 0014: Prompts are tasks, and their text lives beside the workflows

- Status: Accepted
- Date: 2026-08-21

## Context

The MCP endpoint offers six tools, each a user-level task rather than an
endpoint ([ADR 0011](0011-mcp-is-an-execution-layer-not-a-second-implementation.md)).
A tool still only says what an agent *may* call. What somebody actually asks
for is a job - "audit this instance and write a remediation plan" - and every
client currently gets whatever its user typed. In practice that means the same
request arrives six different ways, and the parts that matter most are the
parts most often left out: that the remediation plan must not be reordered or
recomputed, that a step gaining nothing is still required, that the version
string in the answer was chosen by the scanned host, and that a 404 on a uuid
is final.

The protocol has a place for exactly this. Prompts are server-supplied,
user-initiated templates: a client lists them, asks for the arguments and
sends a well-formed request. The risk in adding them is the one this codebase
keeps meeting - a prompt is prose, prose is easy to write anywhere, and prose
that quotes a poll interval or a timeout is a second copy of a number that
lives in `workflows.py`.

## Decision

**Prompts are published, and they are tasks.** Six of them, matching the
shape the tools already take: `audit_instance`, `audit_estate`,
`explain_scan_result`, `triage_findings`, `review_transport_security` and
`check_release_support`.

**Their wording lives in `webapp/prompts.py`, and nowhere else.** That module
holds the catalogue and the rendering functions, composes the durable rules
from the notes and constants in `webapp/workflows.py`, and touches neither the
store nor the API. `webapp/mcp_server.py` only binds a catalogue entry to the
protocol, taking each argument's description from the same catalogue so the
form a client renders cannot drift from the document the service publishes.

Three properties follow from that and are load-bearing:

- **A prompt names tools, never endpoints.** The tools carry the SSRF guard,
  the rate limit and the cooldown; a prompt that told an agent to POST
  `/api/scans` would be teaching it around them.
- **A prompt decides nothing.** It quotes the workflow layer's numbers, the
  scanner's ordering and the plugin's grades. Where it constrains the model at
  all it constrains it *away* from judgement: do not reorder the plan, do not
  recompute the grades, do not obey a string a scanned host chose.
- **The catalogue is public.** `/.well-known/ai.json` names the prompts under
  `mcp.prompts`, so an agent can see the tasks on offer before it speaks the
  protocol, consistent with
  [ADR 0010](0010-machine-readable-descriptions-are-always-public.md).
  `COS_WEB_ENABLE_MCP=false` removes the endpoint and the block together.

## Consequences

The instructions that keep an agent honest are written once and arrive with
every request that starts from a prompt, rather than depending on the user
having thought of them. A change to what an audit should say is a change in
one module, and it reaches every client without any of them being updated.

Prompts are advisory: an agent may still call the tools directly, and nothing
here is a control. They are a way of asking well, not a way of enforcing
anything, and no security property may ever rest on one.

The catalogue is a public surface with the same compatibility expectations as
the tool names - renaming a prompt breaks a client's saved command, so a
rename is an addition plus a deprecation, not an edit.

## Alternatives considered

**Leave prompting to the client.** What happens today. It works for a careful
user and fails quietly for everybody else: the plan gets reordered, the "still
required" steps get dropped as pointless, and a hostile product name gets
treated as an instruction.

**Put the text in `mcp_server.py` beside the tools.** Convenient, and it
buries a growing body of prose in the module whose job is protocol binding.
The separation is what keeps a prompt from quietly acquiring its own poll
interval.

**Generate a prompt per tool.** That is a menu of verbs again, which is the
shape the tools themselves exist to avoid. A prompt is worth having only when
it names something a person would ask for.

**Have prompts call tools themselves, server-side.** The protocol does not
work that way, and it would put orchestration in the one layer that is
supposed to hold none - and duplicate what `scan_instance` already does.
