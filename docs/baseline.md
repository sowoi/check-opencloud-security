# Reporting only what changed

Use `--baseline` to save each scan’s findings and compare them with the next run. Add
`--warn-on-new` to alert only when findings are new or have become worse. Existing
problems remain visible in the report.

The [main README](../README.md#reporting-only-what-changed) has the short
version. This page is the full behaviour: the diff formats, what counts as a
regression, and the rules that keep a baseline from hiding anything.

<!-- TOC -->
* [Reporting only what changed](#reporting-only-what-changed)
  * [Writing and comparing a baseline](#writing-and-comparing-a-baseline)
  * [What counts as a regression](#what-counts-as-a-regression)
  * [Coverage regressions](#coverage-regressions)
  * [Points worth knowing](#points-worth-knowing)
<!-- TOC -->


## Writing and comparing a baseline

`--baseline` names the file the findings of each run are written to, and the
file the next run is compared against:

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json
```

On its own this only adds a line to the output (`Baseline: ...`). Add
`--warn-on-new` to act on it:

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json \
    --warn-on-new
```

The check then reports `OK` while the picture is unchanged, and its normal
status as soon as anything is new or worse. The full state is still printed
either way - only the alert is suppressed, never the evidence:

```
OK: nothing new since the last run (WARNING state unchanged).
OpenCloud 7.2.3 on opencloud.example.com, rating: C, last scanned: 2026-01-14
Missing hardening: cspWithoutUnsafeInline (run with --debug for what each means and how to fix it)
Baseline: No new findings since 2026-01-14T09:00:00+00:00 (1 known issue(s) unchanged)
Suppressed by --warn-on-new: this run would otherwise be WARNING (WARNING: 1 hardening measure(s) missing, but no known vulnerabilities.)
```

Every comparison also lists added and resolved CVEs, hardening and additional
check changes, rating/EOL/support-horizon changes, and installed or target
version shifts. `text` is the default for logs. For a GitHub Actions step
summary or pull-request comment, select Markdown:

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format markdown >> "$GITHUB_STEP_SUMMARY"
```

Use `--diff-format slack` (or `json`) for Slack Block Kit JSON. When a webhook
is configured, every baseline comparison is included as `baseline_diff`; Slack
format additionally puts the blocks and color banner at the top level for
incoming webhooks:

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format slack --webhook-url 'https://hooks.slack.com/services/<token>' \
  --webhook-on always
```


## What counts as a regression


- a finding that was not there last time - a new advisory, a hardening measure
  that has regressed, an additional check that started failing, a newly
  available update;
- a rating lower than the one recorded;
- **a release past its end of life, always.** It receives no security fixes,
  so it gets worse every day it stays in production and can never be
  grandfathered in by a baseline.

## Configuration drift


A baseline also stores the scan's **configuration fingerprint**: hashes that
represent the transport, header, sharing, authentication and proxy configuration.
The hashes detect changes without storing the configuration values.
The report identifies changed groups even when the grade and findings stay the same:

```text
Baseline: No new findings since 2026-09-14T06:00:00Z, but the configuration changed (headers, proxy)
```

The report names the groups whose configuration changed. The baseline file,
output and webhook contain hashes, without the underlying configuration values.

Drift is reported, never judged: it does not create a finding, it does not
make a run regress, and it never changes the exit code. A baseline written
before fingerprints existed cannot detect configuration drift because it has
no fingerprints to compare. It therefore reports no drift; this does not
establish that the configuration is unchanged.

## Coverage regressions


A baseline also remembers which checks the scan **reached a conclusion on**.
When a check that was measured before is `inconclusive` now - it ran and could
not tell, for example because a DNS query timed out or the instance returned no
page to read - the run says so, even when the grade has not moved:

```text
WARNING: 1 previously measured check(s) are now inconclusive; the rating is unchanged (Server is up to date. No known vulnerabilities.)
Baseline: No new findings since 2026-09-14T06:00:00Z
Coverage regressed (1): previously measured, now inconclusive: caaRecord (timeout) - the rating is unaffected.
```

This is kept separate from the security rating. The rating, its
perfdata and the findings stay what the evidence gave; only the alert state
moves, and only from `OK` to `WARNING` - a run that is already `WARNING` or
`CRITICAL` keeps its own message and gets the coverage line beside it.
`--warn-on-new` does not suppress it, because a scan that suddenly sees less
is news.

- Only `inconclusive` counts. A check that became `not_checked` - a probe
  you turned off, or one that no longer applies, such as TLS on an instance
  now served over plain HTTP - is not a regression of the scan.
- A lost check stays "previously measured" until a later run measures it
  again, so the warning holds for as long as the gap does rather than for a
  single interval.
- The webhook's `baseline_diff` carries the lost checks and their reasons as
  `coverage_regressed`, and every diff format lists them under `Coverage`.
  The two-document comparison (`check-opencloud-scanner diff` and `explain`, and the web
  comparison) reports the same loss as a `coverageRegressed` scanner change.
- A baseline written before this existed records no coverage, so the first
  run after an upgrade cannot report a loss; it records what it measured for
  the next one.

## Checks only one run made

A finding is only called new if the previous run could have reported it. When
the scanner gains a check - after an upgrade, or because you turned the extra
checks on - a failure it now finds was *not checked* last time, not passing,
and the run says so:

```text
Baseline: Newly measured (1): hardening:basicAuthDisabled - the last run did not check these
Hardening: + basicAuthDisabled (not checked before)
```

It still alerts, and `--warn-on-new` does not suppress it: nobody has been
told about that failure yet. The next run knows the check and treats the
failure like any other known one. The other way round, a failure the current
run no longer checks is listed as `(not checked now)` rather than as
resolved, because nobody fixed it.

- What a run could have reported comes from its coverage block, never from a
  missing key. A report that does not list its checks - one written before
  coverage existed, or an uploaded report in the web comparison - is compared
  as before, so a real regression is never renamed.
- The webhook's `baseline_diff` carries both lists as `newly_measured` and
  `no_longer_measured`; the web comparison as `newlyMeasured` and
  `noLongerMeasured`; and the two-document explanation as the scanner changes
  `checksNewlyMeasured` and `checksNoLongerMeasured`. See
  [ADR 0079](../adr/0079-a-finding-is-new-only-if-the-earlier-scan-could-have-reported-it.md).
- A baseline written before this existed cannot say what it checked, so the
  first run after an upgrade compares as before.

## Points worth knowing


- The first run has nothing to compare against, so it reports normally and
  becomes the baseline. Starting to use the flag never hides anything.
- One file holds one entry per host, so a comma-separated `--host` list can
  share it.
- Findings that are waived with `--ignore-hardening`, and measures OpenCloud
  hardcodes, are left out - exactly as they are left out of the alert line.
- `--warn-on-new` without `--baseline` is rejected: with nowhere to remember
  the last run it would report "nothing new" forever.
- A baseline that cannot be written is reported as a line of output and
  nothing more. Bookkeeping never decides the verdict on an instance.
- The file is written atomically with owner-only permissions. Put it somewhere
  the monitoring user owns, e.g. `/var/lib/check_opencloud/`.
