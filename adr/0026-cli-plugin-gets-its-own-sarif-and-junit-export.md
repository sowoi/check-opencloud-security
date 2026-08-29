# ADR 0026: The CLI plugin gets its own SARIF/JUnit export, independent of the webapp's

- Status: Accepted
- Date: 2026-08-29

## Context

`check_opencloud_security.py` had two output formats: `nagios` (the default,
human text plus perfdata) and `prometheus`. Neither works for a CI pipeline
that wants to gate on findings and hand them to a dashboard - a step
scanning an OpenCloud instance under test needs a document, not a line
Icinga was designed to parse.

ADR 0006 already added SARIF (plus CSV and PDF) to the *web application*,
exported per finished scan through `GET /api/scans/{uuid}/export/{format}`
and implemented in `webapp/reports.py`. That module cannot be imported here:
`pyproject.toml`'s wheel build explicitly excludes `webapp/` and `frontend/`
from the PyPI package, and the plugin's whole reason for being a single
dependency-free file is that a monitoring host can install it without
pulling in a web application's dependencies. Reusing the webapp's renderer
would mean either vendoring `webapp/` into the plugin's wheel (reversing
that boundary) or making the plugin depend on `webapp` at import time
(same problem from the other direction).

## Decision

`check_opencloud_security.py` gets its own SARIF and JUnit renderers,
deliberately following the same conventions `webapp/reports.py` already
established rather than inventing new ones: the same `$schema` URL, the same
four-level severity mapping (`critical`/`high` -> `error`, `medium` ->
`warning`, `low`/`info` -> `note`), and hardening/header findings reported at
`note` the way the webapp's export already does. A user comparing a CLI scan
against the same instance's webapp scan should see matching rule ids and
severities, even though the two files that produce them share no code.

Findings are taken from the same `missing_hardenings`, `failed_extra_checks`,
`vulnerabilities` and `eol` facts the plugin's own Nagios text and webhook
payload already compute - not from `opencloud_local_scan.remediation`'s
plan, which is deliberately only the subset of findings that would move the
rating (ADR-adjacent: see that module's own docstring) and so under-reports
findings that cannot raise the rating further, such as a hardening measure
on an already-critical instance.

`json`, `sarif` and `junit` always print one combined document for the whole
run - never one block per host the way the `nagios` text format does -
because concatenating several independent JSON/SARIF/XML documents does not
parse as one. This meant a new host-worker path (`_run_machine_format_checks`)
separate from the existing `_run_multi_host_checks`, but it reuses
`check_vulnerabilities` and every flag it already understands (baseline
diffing, webhooks, `--warn-on-new`) unchanged, by capturing the same
structured document a new `_RESULT_PAYLOAD` contextvar carries rather than
by changing what `check_vulnerabilities` decides.

The process exit code keeps its Nagios meaning (`0`-`3`) under every format,
matching how `prometheus` already behaves: the machine-readable body is a
separate artifact from the pass/fail signal a CI step gates on.

## Consequences

No new dependency: `xml.etree.ElementTree` is standard library, matching the
dependency-free philosophy ADR 0006 already established for exports.

Two independent SARIF renderers now exist in this repository, one per
artifact, and nothing enforces that they stay in convention-sync beyond this
record and code review - a real cost, accepted because the alternative was
either the packaging boundary or the plugin's dependency-free property.

## Alternatives considered

**Extract a shared SARIF module both `webapp/` and the plugin import.**
Solves the duplication but requires deciding which of the two ships it - if
`opencloud_local_scan`, then every install of the plugin - the common case,
a monitoring host - carries webapp-shaped conventions it never asked for; if
`webapp`, back to the import problem above.

**Only add SARIF, not JUnit.** SARIF is the format with existing prior art
in this project; JUnit has none. It was added anyway because it is the
format most CI systems already render into a check-run summary without a
separate action, and the finding data needed for it is identical to SARIF's -
one small renderer, not a second research problem.

**Print one document per host and let the caller concatenate.** Simpler to
implement, but produces invalid JSON/XML for more than one host, which is
exactly the case a CI pipeline scanning several environments would hit.
