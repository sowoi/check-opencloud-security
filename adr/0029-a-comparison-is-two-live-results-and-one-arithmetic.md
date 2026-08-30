# ADR 0029: A comparison is two live results, judged by the plugin's own arithmetic

- Status: Accepted
- Date: 2026-08-30

## Context

An agent that audits an instance and hands back a remediation plan is asked
the obvious next question a week later: *did any of that help?* Until now
there was no way to answer it. The plan says what each fix would be worth
(ADR 0012), but nothing compares what the instance looked like before with
what it looks like now.

Two temptations follow, and both are wrong in the same way.

The first is to **store scan history**. A comparison looks like it needs one:
keep a row per scan per target, and "what changed since March" becomes a
query. This service deliberately keeps no scan history ([ADR 0002](0002-no-scan-result-caching.md))
and a uuid is a capability with a TTL ([ADR 0007](0007-erasure-on-request.md)).
A history table is a scan result under another name, outliving the result it
describes, listable by a key nobody was given, and exempt from the erasure
that the rest of the service honours.

The second is to **work out what changed in the workflow layer**. Two result
documents, a set difference over their findings, done. Except that the plugin
already answers this question - `--baseline` spends it on staying quiet
between runs, and it has rules that are not obvious: end of life is never
forgiven no matter how long it has been true, a waived finding is not news,
and a non-actionable flag cannot become news at all. A second implementation
would produce an agent that tells an operator "this improved" about the same
two scans their monitoring is calling a regression.

## Decision

**A comparison is computed from two results that both still exist, with
`opencloud_local_scan.baseline`'s arithmetic, and stored nowhere.**

- `webapp/workflows.py` gains `compare_scans(client, baseline, current)`. It
  reads both documents through the ordinary HTTP API in-process, as every
  other workflow does ([ADR 0011](0011-mcp-is-an-execution-layer-not-a-second-implementation.md)),
  and hands them to `Baseline.compare` - the same call the plugin makes.
- It reads the **JSON export** rather than the summary, and deliberately not
  through `export_scan`. That function drops a document past its inline size
  limit, because an export is something handed to a model; a comparison is
  arithmetic, and findings that vanished past a size limit look exactly like
  findings that were fixed.
- Both uuids must resolve. An expired one answers 404 naming which of the two
  is gone, and that is final: there is nothing to look it up in.
- The **same uuid twice is refused** with 422. An empty diff of a scan against
  itself reads as "nothing is wrong".
- Two documents describing **different instances are compared, not refused**,
  and the answer carries `sameTarget: false`. Comparing staging with
  production is a fair question; answering it silently is not.
- The MCP tool `compare_scans` and the prompt `verify_remediation` bind it to
  the protocol. The prompt tells the model to rescan and then call the tool,
  never to derive the difference itself.

The same arithmetic now has three surfaces and one definition: the plugin's
`--baseline`, `check-opencloud-scanner diff` for two archived documents, and
`compare_scans` for two live results.

## Consequences

- An operator and an agent looking at the same two scans cannot reach
  different verdicts about what is new.
- A comparison is only possible **inside the retention window**. That is a
  real limitation and the tool says so rather than hiding it: the way to keep
  a long-term record is to archive the JSON exports and use
  `check-opencloud-scanner diff`, which has no window at all.
- `webapp/workflows.py` now imports from `opencloud_local_scan`. This is the
  one place the workflow layer borrows arithmetic rather than driving the API,
  and it borrows rather than reimplements precisely to keep the layer boundary
  meaningful.
- A grade that does not move is a normal outcome of real progress, because
  findings of one severity share a cap. The tool description and the prompt
  both say so; without that, an unchanged letter reads as a failed
  remediation.
- Anything that changes what `baseline.py` counts as a finding now changes
  three surfaces at once. That is the point, and it is why the tests for the
  arithmetic live with the baseline rather than with any one of them.

## Alternatives considered

**Store a scan history keyed by target.** Rejected: it is ADR 0002 reversed,
it creates a listable record of who scanned what, and it would have to be
erasable to keep ADR 0007 honest - at which point the history nobody erased is
the one that matters.

**Let the model compare two `get_scan_result` answers itself.** Rejected: the
summary does not carry every finding, and a model deriving "what is new" from
two documents will disagree with the operator's monitoring sooner or later,
confidently and without either side knowing why.

**A `/api/scans/{a}/compare/{b}` endpoint.** Rejected for now: it would be a
public endpoint taking two capabilities at once, and the comparison is derived
from documents the API already serves. Following ADR 0012, a derived answer
gets a workflow rather than a route.
