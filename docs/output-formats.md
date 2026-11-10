# Machine-readable output: `--format json`, `sarif`, `junit`

The plugin’s default output is a Nagios status line with performance data. Use
`--format` (`COS_FORMAT`) to choose a document or metrics format for scripts, dashboards
and CI pipelines.

`--format json`, `--format sarif`, or `--format junit` all print **one
combined document for every scanned host** - never one document per host,
even when `--host` names only one. That means the output is always valid
JSON, SARIF or XML regardless of how many addresses were passed, so nothing
downstream has to special-case a single-host run.

**The exit code keeps its Nagios meaning under every format** - `0`
(OK), `1` (WARNING), `2` (CRITICAL), `3` (UNKNOWN). A CI step gates on the
exit code the way an Icinga check does; the document these flags
produce is an additional artifact and does not replace it. The two
metric formats, `prometheus` and `otlp`, are the exception: they report a
scan rather than judging it, so a finding travels as a sample and the process
exits `0`.

<!-- TOC -->
* [Machine-readable output: `--format json`, `sarif`, `junit`](#machine-readable-output---format-json-sarif-junit)
  * [`json`](#json)
  * [`sarif`](#sarif)
  * [`junit`](#junit)
  * [`checkmk`](#checkmk)
  * [`otlp`](#otlp)
  * [Choosing a format](#choosing-a-format)
<!-- TOC -->


## `json`

A JSON array of the same result document described in [Webhook
notifications](../README.md#webhook-notifications) - one object per host,
always an array even for a single host. This is the format to reach for when
something else is going to parse the result programmatically: a script, a
dashboard backend, or a second monitoring system this plugin does not speak
to natively.

```shell
check-opencloud-security --host opencloud.example.com --format json
```

## `sarif`

[SARIF](https://sarifweb.azurewebsites.net/) 2.1.0, for a code-scanning
dashboard - GitHub's included. Findings come from the same
missing-hardening, failed-extra-check, vulnerability and end-of-life facts as
the plugin's own text output: a SARIF result never says anything the Nagios
line would not, it is only reshaped for a scanning dashboard to render.

```shell
check-opencloud-security --host opencloud.example.com --format sarif \
  > opencloud-security.sarif
```

Each finding carries what a dashboard needs to act on it without a second
lookup:

| In the SARIF | What it holds |
|:-------------|:--------------|
| `rule.help` / `rule.helpUri` | The catalogue's remediation sentence and the official documentation page for the setting |
| `rule.properties.security-severity` | The numeric score GitHub code scanning sorts and filters alerts on (`9.5` critical to `1.0` info) |
| `rule.properties.problem.severity` | `error`, `warning` or `recommendation`, the dashboard's own scale |
| `rule.properties.catalogueId` | The catalogue entry that explains the finding - `exposed` for `exposed:/opencloud.yaml` |
| `rule.properties.tags` | `security`, plus `severity/…`, `category/…` and `kind/…` to filter on |
| `result.properties` | The host, severity, category, remediation, documentation link, and for an advisory `fixedIn` and `affectedRanges` |
| `result.partialFingerprints` | A stable identity per host and rule, so the same finding stays one alert with a history rather than a new one each night |
| `run.properties.hosts` | The rating, label, product version and end-of-life state per scanned host |

`affectedRanges` names the release window an advisory covers - `>= 1.0.0, <
4.0.8` - rather than only the release that ends it, so a reader can tell
whether an older release was ever affected.

In GitHub Actions, upload it to code scanning. `continue-on-error: true` on
the scan step keeps a non-zero exit from failing the job before the upload
step runs - the point of scanning in CI is usually to see the findings even
when the scan itself reports a bad rating:

```yaml
- name: Scan OpenCloud
  run: |
    check-opencloud-security --host opencloud.example.com --format sarif \
      > opencloud-security.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: opencloud-security.sarif
```

## `junit`

JUnit XML with one `<testsuite>` per scanned host and one `<testcase>` per
finding, plus an **always-present `rating` case** - so a clean host still
shows up in the report rather than contributing zero test cases, which most
JUnit-reading tools treat as "nothing ran" rather than "nothing failed".

```shell
check-opencloud-security --host opencloud.example.com --format junit \
  > opencloud-security.xml
```

The same pattern works for any CI system that turns a JUnit file into a
check-run summary - the step just needs to point its JUnit reporter at the
file this command produces.

## `checkmk`

One [Checkmk local check](checkmk.md) line per scanned host, for the agent to
read: the state, the quoted service name, the metrics and the detail text.

```shell
check-opencloud-security --host opencloud.example.com --format checkmk
```

This is the one format that is *not* a single combined document, because the
protocol it writes is a line per service - several hosts are several
services. It is also only needed for the agent-side route: a Checkmk server
running the plugin as an active check reads the default `nagios` output
natively. [Checkmk](checkmk.md) has both, and the metric table.

## `otlp`

The metrics the Prometheus exposition publishes, rendered as OTLP/JSON: one
`ExportMetricsServiceRequest` holding every scanned host, which is the body an
OpenTelemetry collector accepts at `POST /v1/metrics` over OTLP/HTTP.

```shell
check-opencloud-security --host opencloud.example.com --format otlp \
  | curl -sf -X POST http://collector.example.com:4318/v1/metrics \
      -H 'Content-Type: application/json' --data-binary @-
```

The plugin prints the document and never dials the collector itself: where
the metrics go, through which proxy and with which credential is the
collector's configuration, not a scan's. Piping it at `curl` from the same
timer that already runs the check keeps that split, and keeps the plugin free
of an instrumentation stack a monitoring host never asked for.

Several hosts become several data points on the same metrics, distinguished
by their `host` attribute, exactly as they become repeated samples in a
scrape. Every metric is a gauge - the current reading of something - and the
names, attributes and values are the exposition's, so one dashboard query
works against either pipeline. [Prometheus and Grafana](prometheus.md#what-the-exporter-publishes)
has the metric table both formats share.

Like `--format prometheus`, **this format exits `0` even for an instance that
would have alerted**, and reports a failed scan as
`opencloud_security_scrape_success 0` rather than as an exit code. A metrics
pipeline has no other way to tell an unreachable instance from a scan that
stopped running; where you need the exit code, use `nagios`, `json`,
`sarif` or `junit`.

## Choosing a format

| Format     | Use it when...                                                          |
|:-----------|:-------------------------------------------------------------------------|
| `nagios`   | Default. A monitoring system reads the exit code and the one-line output |
| `prometheus` | A scrape target or textfile collector wants metrics directly - see [Prometheus and Grafana](prometheus.md) |
| `otlp`     | An OpenTelemetry collector should receive those same metrics at `/v1/metrics` |
| `json`     | Something else parses the result programmatically                        |
| `sarif`    | A code-scanning dashboard (GitHub, GitLab) should list the findings      |
| `junit`    | A CI system renders test results and should render findings the same way |
| `checkmk`  | A Checkmk agent runs the plugin as a local check - see [Checkmk](checkmk.md) |

See [Running the check from CI](ci.md) for a fuller GitHub Actions and
GitLab CI walkthrough, including gating a pipeline on a field of the JSON
result rather than only the exit code.
