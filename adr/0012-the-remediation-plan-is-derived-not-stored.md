# ADR 0012: The remediation plan is derived from the rating, not a second model of it

- Status: Accepted
- Date: 2026-08-21

## Context

A report tells an operator that an instance rates 3/5 and lists what failed.
The question that follows is not answered anywhere: *which of these do I fix,
in what order, and where does it get me?* Two medium findings share one
ceiling, so fixing the first changes nothing; an update can be worth more than
any single finding, or nothing at all while a critical finding stands open.
Working that out by hand from a list of findings is exactly the kind of
arithmetic people get wrong, and it is arithmetic the rating code already
performs.

The obvious implementation is a table: severity → advice → predicted grade,
written next to the findings. It is also the implementation that goes stale
the first time `SEVERITY_RATING_CAP` or the base-rating rules move, and it
goes stale silently, because nothing compares the promise against the rating.

There is a second temptation. A plan looks like state - it is about the
future, it reads like a to-do list - so it looks like something to store, to
version, to diff across scans. This service deliberately keeps no scan
history (ADR 0002), and a stored plan would be a scan result under another
name, outliving the result it describes.

## Decision

**The plan is a replay of the rating, computed on the document that already
exists.** `opencloud_local_scan/remediation.py` reads
`ratingExplanation.caps` - the caps the rating itself recorded - removes one
finding at a time and asks the same cap arithmetic what the rating would be.
It is attached to the scan result as `remediationPlan` and stored nowhere
else.

- `SEVERITY_RATING_CAP` moves into `remediation.py` and `scanner.py`
  re-exports it, so the planner and the rating cannot hold two copies of the
  table that decides both.
- The plan carries **numbers only**. `A+` and `F` are applied by
  `check_opencloud_security.py` for the plugin and by `webapp/catalog.py` for
  the dashboard, because turning a rating into a grade is a judgement and
  judgements do not belong in the measuring layer.
- Ordering is `(cap, severity, identifier)` - never iteration order - matching
  the invariant the rating explanation already has.
- Steps that gain nothing stay in the list with `ratingGain: 0`. Hiding them
  would read as "skippable", when they are the opposite: findings that share a
  ceiling all have to go before any of them pays.
- The update is a step in the same list, inserted at the first position where
  it changes the outcome. A plan is a sequence of actions, and an operator who
  must upgrade should see it among the things to do rather than beside them.
- `actionable: false` findings - the flags OpenCloud hardcodes - go to
  `blocked` and remain in every simulated remainder. They are what makes
  `achievableRating` honest rather than aspirational.
- Every surface renders the same plan: the dashboard, the JSON, CSV, SARIF and
  PDF exports, the plugin's `--debug` output, the `planRemediation` Arazzo
  workflow and the `plan_remediation` MCP tool. None of them recomputes it.

## Consequences

`remediationPlan` is part of the result-document contract now, and removing a
key from it is a breaking change like any other.

A change to the rating rules changes the plan automatically, and a change that
breaks the plan breaks it visibly, in tests that scan a real fake instance
rather than in a table nobody re-reads.

The planner needed something that did not exist: remediation text for the
findings the extra-check pass reports. `describe_hardening()` explained the
hardening flags and the headers and answered "No description is available" for
`tlsTrusted`, `directoryListing`, the `exposed:` family and the rest - the
findings that actually cap ratings. Those entries were written as part of this
work, and a test now fails if a check a real scan can report has no fix to
offer.

One case does not fit the replay. An end-of-life release short-circuits the
rating to `0` and records no caps at all, so the planner rebuilds them from
`extraChecks` in that case only. Without it the plan would promise 5/5 after
an upgrade while a critical finding stood open.

## Alternatives considered

**A static advice table keyed by severity.** Simpler to read and unable to
stay correct: it cannot know that two medium findings share a ceiling, and
nothing would catch it disagreeing with the rating.

**Compute the plan in the web layer.** It would give the dashboard what it
needs and leave the plugin, the exports and the MCP tool without it, or with
three implementations. The plan is a property of the result, so it belongs
where the result is made.

**Store plans and diff them between scans.** A history feature wearing a
planning hat. ADR 0002 settled that this service keeps no scan history, and a
stored plan is a stored scan.

**Emit letters directly from the scanner.** Convenient, and a hole in the
layer boundary: the scanner measures, and `RATE_MAP` belongs to the layer that
judges.
