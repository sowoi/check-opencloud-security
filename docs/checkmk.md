# Checkmk

Checkmk speaks Nagios, and this is a Nagios plugin, so the two fit together
without an extension package. There are two ways round, and the difference is
not cosmetic - it decides which machine opens the connection to your instance:

| | [Active check](#1-an-active-check-on-the-checkmk-server) | [Local check](#2-a-local-check-on-an-agent-host) |
|:--|:--|:--|
| Runs on | the Checkmk server | a host with the Checkmk agent |
| Reaches the instance from | the monitoring network | wherever that host sits |
| Needs the plugin installed on | the Checkmk server | the agent host |
| Configured in | the web interface | a file the agent runs |
| Output format | `nagios` (the default) | `--format checkmk` |

Use the **active check** unless the instance is unreachable from the Checkmk
server. It is configured in one place, it needs nothing on any other machine,
and Checkmk parses the plugin's ordinary output itself.

Everything below uses `opencloud.example.com`. Substitute your own, and scan
only instances you are responsible for.

## 1. An active check on the Checkmk server

Install the plugin on the Checkmk server, as the site user:

```shell
pipx install check-opencloud-security
```

[Installing the plugin](installation.md) covers uv, pip and a checkout;
`check-opencloud-security --version` confirms which one you got.

Then, in the web interface: **Setup > Services > Other services > Integrate
Nagios plugins**, and create a rule with

- **Service description**: `OpenCloud security opencloud.example.com`
- **Command line**:
  `check-opencloud-security --host opencloud.example.com --check-hardening`

Assign it to the host you want the service to appear on. That host is a label
for where the *service* lives, not where the scan goes - the scan always goes
to `--host`.

Checkmk reads the state from the exit code, the summary from the first output
line, the rest of the output as the service's details, and everything after
the `|` as metrics. Nothing needs converting: the
[performance data](../README.md#performance-data) this plugin already writes -
`rating`, `vulnerabilities`, `hardenings_missing`, `extra_checks_failed`,
`update_available`, `support_days_left`, `cert_days_left`, `time` - is the
Nagios format Checkmk was built to read, thresholds and all.

One warning about scheduling: the default check interval is one minute, and a
scan makes around twenty HTTP requests and five TCP connects to the instance.
Set a sensible interval on the service - hourly is plenty for a rating that
moves when somebody changes a configuration file - under **Setup > Services >
Service monitoring rules > Normal check interval for service checks**.

## 2. A local check on an agent host

When the Checkmk server cannot reach the instance, the scan has to start
somewhere that can. A local check is a script the agent runs; its output
becomes a service on the agent's host.

`--format checkmk` writes exactly what the agent expects:

```shell
check-opencloud-security --host opencloud.example.com --format checkmk
```

```text
0 "OpenCloud_Security_opencloud.example.com" rating=5|vulnerabilities=0|hardenings_missing=0|extra_checks_failed=0|update_available=0|support_days_left=284|cert_days_left=67|execution_time=4.120 OK: Server is up to date. No known vulnerabilities.
```

Four fields, separated by single spaces: the state, the quoted service name,
the metrics, and the detail text. With several hosts in `--host` you get
several lines, which is several services - one per instance.

### Installing it

[`contrib/checkmk/opencloud_security`](../contrib/checkmk/opencloud_security)
is that call wrapped in a script, configured by the same `COS_` environment
variables as the [cron and systemd examples](scheduling.md) beside it, so it
needs no editing to point at your instance:

```shell
sudo install -m 0755 contrib/checkmk/opencloud_security \
    /usr/lib/check_mk_agent/local/3600/opencloud_security
```

**The `3600` is the important part.** A script in `local/` itself runs every
time the agent is called - once a minute - and that is a scan a minute against
somebody's production instance. The numeric subdirectory is the agent's cache
interval in seconds: the scan then runs at most hourly, and every call in
between is answered from the cached line. Pick the interval you actually want;
`3600` is a good default for a rating.

Installed from the `.deb` or `.rpm`, the same script is at
`/usr/share/doc/check-opencloud-security/checkmk-local-check.sh` - as an
example, deliberately not installed into the agent's directory by a package
that has no business writing there.

Set the target in the script, or in an environment file the agent reads:

```shell
COS_HOST=opencloud.example.com
# OpenCloud self-signs its certificate unless a proxy terminates TLS for it.
#COS_SCANNER_VERIFY_TLS=false
```

Then discover the new service on that host: **Setup > Hosts**, the host's
*Services* page, *Full service scan*.

### What the states mean

The state on the line is the plugin's, unchanged - the same `0`/`1`/`2`/`3`
the exit code carries, decided by the same
[rating thresholds](../README.md#rating-thresholds), waivers and
end-of-life rules as everywhere else. Checkmk is not asked to judge anything:

- `0` OK - the rating is above `--warning` and nothing new appeared
- `1` WARN - at or below `--warning`, or a finding is missing hardening
- `2` CRIT - at or below `--critical`, or a known vulnerability applies
- `3` UNKNOWN - the scan could not be completed at all

That last one is why the shipped script always prints a line, even when the
plugin is missing or was killed by the agent's timeout. A local check that
prints nothing does not go UNKNOWN - it *removes its service from the host*,
which reads like a check somebody deliberately switched off rather than one
that broke.

### The metrics

The same measurements the Nagios performance data carries, under the same
names, with two differences the format requires:

- **No thresholds.** A local check's levels are only evaluated when the state
  field is `P`, which hands the verdict to Checkmk. Deciding is this plugin's
  job, so it sends the state it reached and the metrics carry values alone.
- **No unit suffix.** Every value has to parse as a number, so the Nagios
  `time=4.120s` is `execution_time=4.120` here.

| Metric | What it is |
|:-------|:-----------|
| `rating` | `0`-`5`, where `5` is A+. Absent when no rating could be established |
| `vulnerabilities` | Known advisories matching the detected version |
| `hardenings_missing` | Measures the instance is missing. **Absent without `--check-hardening`**, because an empty list would otherwise be indistinguishable from a perfect one |
| `extra_checks_failed` | Failed additional checks - TLS, exposed paths, cookies, headers |
| `update_available` | `1` when a newer release exists. Absent when the update check is off |
| `support_days_left` | Days until the release line stops receiving fixes; negative once it has |
| `cert_days_left` | Days until the certificate expires; negative once it has |
| `execution_time` | How long the scan took, in seconds |

A metric that was not measured is left out rather than sent as a zero, so a
graph never shows a confident zero for something nobody looked at.

## Alerting on it

Both routes produce an ordinary Checkmk service, so notifications, downtimes
and acknowledgements work as they do for anything else. Two rules worth
setting up:

- Alert on **CRIT** immediately - a known vulnerability or an end-of-life
  release is not a tomorrow problem.
- Graph `support_days_left` and set a level on it. It is the one number that
  gets worse while nothing about the instance changes, and the day it goes
  negative the rating drops to F on its own.

`--baseline` and `--warn-on-new` ([Reporting only what
changed](baseline.md)) work under both routes and are worth having on a check
that runs unattended: the state then reflects what is *new* rather than
repeating a finding somebody has already decided to live with. An
end-of-life release and a rating that drops further are never forgiven by
that, so it cannot quieten the two findings that matter most.

## See also

- [Installing the plugin](installation.md) - and the Icinga2/Nagios object
  definitions, if Checkmk is not the only thing you run
- [Machine-readable output](output-formats.md) - every `--format` value
  compared
- [Scheduling](scheduling.md) - the systemd timer and cron drop-in the local
  check's environment variables come from
- [Prometheus and Grafana](prometheus.md) - the other pull-based route, if you
  would rather graph this outside Checkmk
