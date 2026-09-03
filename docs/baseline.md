# Reporting only what changed

A check that runs every five minutes reports the same finding until somebody
fixes it, which is how people learn to acknowledge an alert and stop reading
it. `--baseline` writes the findings of each run to a file and compares the
next run against it, and `--warn-on-new` acts on the comparison.

The [main README](../README.md#reporting-only-what-changed) has the short
version. This page is the full behaviour: the diff formats, what counts as a
regression, and the rules that keep a baseline from hiding anything.

<!-- TOC -->
* [Reporting only what changed](#reporting-only-what-changed)
  * [Writing and comparing a baseline](#writing-and-comparing-a-baseline)
  * [What counts as a regression](#what-counts-as-a-regression)
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
