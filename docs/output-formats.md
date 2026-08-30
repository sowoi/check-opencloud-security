# Machine-readable output: `--format json`, `sarif`, `junit`

The scanner's default output is a single Nagios-style line, because that is
what a monitoring system expects. `--format` (`COS_FORMAT`) switches that
line for a document instead, when whatever consumes the result is not a
monitoring plugin but a script, a dashboard, or a CI pipeline.

`--format json`, `--format sarif`, or `--format junit` all print **one
combined document for every scanned host** - never one document per host,
even when `--host` names only one. That means the output is always valid
JSON, SARIF or XML regardless of how many addresses were passed, so nothing
downstream has to special-case a single-host run.

**The exit code keeps its Nagios meaning under every format** - `0`
(OK), `1` (WARNING), `2` (CRITICAL), `3` (UNKNOWN). A CI step gates on the
exit code exactly the way an Icinga check does; the document these flags
produce is a separate, additional artifact, not a replacement for it.

<!-- TOC -->
* [Machine-readable output: `--format json`, `sarif`, `junit`](#machine-readable-output---format-json-sarif-junit)
  * [`json`](#json)
  * [`sarif`](#sarif)
  * [`junit`](#junit)
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

## Choosing a format

| Format     | Use it when...                                                          |
|:-----------|:-------------------------------------------------------------------------|
| `nagios`   | Default. A monitoring system reads the exit code and the one-line output |
| `prometheus` | A scrape target or textfile collector wants metrics directly - see [Prometheus and Grafana](prometheus.md) |
| `json`     | Something else parses the result programmatically                        |
| `sarif`    | A code-scanning dashboard (GitHub, GitLab) should list the findings      |
| `junit`    | A CI system renders test results and should render findings the same way |

See [Running the check from CI](ci.md) for a fuller GitHub Actions and
GitLab CI walkthrough, including gating a pipeline on a field of the JSON
result rather than only the exit code.
