# Prometheus and Grafana

The plugin has a native Prometheus exporter. Run it with
`--prometheus-listen-port 9102` to serve `/metrics`; it caches a scan for
`--scrape-interval` seconds (60 by default), so normal scrapes do not trigger
another scan; set it to `0` only when every scrape should. It binds to
`127.0.0.1` by default; set `--prometheus-listen-addr 0.0.0.0` only when a
firewall or network policy restricts remote scrapers - which is also what a
container needs, alongside publishing the port:

```shell
docker run --rm -p 9102:9102 check-opencloud-security \
  --host opencloud.example.com --prometheus-listen-port 9102 \
  --prometheus-listen-addr 0.0.0.0
```

For a batch job, `--format=prometheus` prints one text exposition payload and
exits. Both modes require no extra dependency.

The textfile collector and Pushgateway patterns below remain useful when a
scheduled scan is a better fit than a long-running exporter.

If you already run Icinga2, you do not need any of this: the
[performance data](../README.md#performance-data) the plugin prints is picked
up by Icinga2's Graphite/InfluxDB writers directly.

<!-- TOC -->
* [Prometheus and Grafana](#prometheus-and-grafana)
  * [The files to copy](#the-files-to-copy)
  * [What the exporter publishes](#what-the-exporter-publishes)
  * [What there is to graph](#what-there-is-to-graph)
  * [node_exporter textfile collector](#node_exporter-textfile-collector)
  * [Pushgateway](#pushgateway)
  * [Alerting rules](#alerting-rules)
  * [Grafana](#grafana)
<!-- TOC -->


## The files to copy

Two of them, both in [`contrib/`](../contrib/README.md), both reading the
metric names the native exporter publishes:

| File | What to do with it |
|:--|:--|
| [`contrib/prometheus/alerts.yml`](../contrib/prometheus/alerts.yml) | Copy into `/etc/prometheus/rules/` and add it to `rule_files:` |
| [`contrib/grafana/dashboard.json`](../contrib/grafana/dashboard.json) | Grafana - Dashboards - New - Import, then pick the data source |

```shell
cp contrib/prometheus/alerts.yml /etc/prometheus/rules/opencloud-security.yml
promtool check rules /etc/prometheus/rules/opencloud-security.yml
```

The dashboard has an `Instance` selector, so one copy serves every host you
scrape. The rules assume a scrape of a cached scan every minute or so; with a
scan scheduled once a day, shorten every `for:` - a one-hour `for:` never
becomes true when the value only changes once between long gaps of the same
reading.

The sections after the next one are the *other* way to do this: a scheduled
scan whose JSON is reshaped by `jq` into metric names of your own. Those names
are shorter and deliberately different, and the two shipped files above do not
match them.


## What the exporter publishes

| Metric | Labels | Meaning |
|:--|:--|:--|
| `opencloud_security_rating_score` | `host`, `domain`, `product`, `version` | The grade, `0`-`5`, `5` best |
| `opencloud_security_end_of_life` | `host`, `release_type` | `1` once the release receives no more fixes |
| `opencloud_security_support_days_remaining` | `host`, `release_type` | Days of support left; **no sample at all** when the end of life is not dated yet |
| `opencloud_security_vulnerabilities_total` | `host`, `severity` | Advisories matching the reported version |
| `opencloud_security_hardenings_missing_total` | `host` | Missing hardening measures |
| `opencloud_security_failed_extra_checks_total` | `host` | Failed additional checks |
| `opencloud_security_update_available` | `host`, `target_version` | `1` when a newer release exists |
| `opencloud_security_scan_duration_seconds` | `host` | How long the scan took |
| `opencloud_security_scrape_success` | `host` | `0` when the scan behind the numbers failed |

A failed scan publishes only the last two. Findings from before the failure
are **not** re-published, so an instance whose scan is broken has no verdict
rather than a stale one - which is why `opencloud_security_scrape_success` is
the first thing the dashboard shows.

`opencloud_security_end_of_life` is a separate family rather than a negative
day count on purpose. A rolling or production release whose end of life has
not been announced reports no days at all, and "unknown" must not read as
"expiring today" in the one alert nobody may miss.


## What there is to graph

Every run prints performance data after a `|`:

```
rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.234s;;;0;
```

| Metric | Meaning |
|:-------|:--------|
| `rating` | `0`-`5`, `5` is A+ and `0` is F; `U` when the scan failed |
| `vulnerabilities` | Known vulnerabilities for the installed version |
| `time` | Seconds the scan took |
| `hardenings_missing` | Missing hardening measures, only with `--check-hardening` |
| `extra_checks_failed` | Failed additional checks |
| `update_available` | `1` when a newer release exists |
| `support_days_left` | Days of support left; negative once overdue |

`support_days_left` is the one worth alerting on. It goes negative *before*
anyone notices the instance stopped receiving fixes.

## node_exporter textfile collector

The scanner's JSON is easier to consume than the perfdata line, so this
uses `check-opencloud-scanner` rather than the plugin, and `jq` to shape it.
Write to a temporary file and rename, or node_exporter will occasionally read
a half-written file.

```shell
#!/bin/sh
# /usr/local/bin/opencloud-metrics - run from a systemd timer, see scheduling.md
set -eu

HOST="opencloud.example.com"
OUT="/var/lib/node_exporter/textfile_collector/opencloud_security.prom"
TMP="$(mktemp "${OUT}.XXXXXX")"

check-opencloud-scanner scan --compact "$HOST" > /tmp/opencloud-scan.json || true

jq -r --arg host "$HOST" '
  if .error then
    "opencloud_scan_success{host=\"\($host)\"} 0"
  else
    "opencloud_scan_success{host=\"\($host)\"} 1",
    "opencloud_security_rating{host=\"\($host)\"} \(.rating)",
    "opencloud_end_of_life{host=\"\($host)\"} \(if .EOL then 1 else 0 end)",
    "opencloud_vulnerabilities{host=\"\($host)\"} \(.vulnerabilities | length)",
    "opencloud_update_available{host=\"\($host)\"} \(if .updates.available then 1 else 0 end)",
    "opencloud_support_days_left{host=\"\($host)\"} \(.lifecycle.daysRemaining // 0)",
    "opencloud_failed_checks{host=\"\($host)\"} \([.extraChecks[] | select(.passed == false and .ignored == false)] | length)",
    "opencloud_version_info{host=\"\($host)\",version=\"\(.version)\",track=\"\(.releaseType)\"} 1"
  end' /tmp/opencloud-scan.json > "$TMP"

mv "$TMP" "$OUT"
chmod 644 "$OUT"
```

`opencloud_scan_success` is not decoration. Without it a failed scan looks
exactly like a healthy instance, because the other metrics simply keep their
last value until the file is overwritten.

`lifecycle.daysRemaining` is `null` for a release whose end of life is not
dated yet - a current rolling or production release, which expires when its
successor ships rather than on a date. The `// 0` above turns that into `0`;
if that reads as "expiring today" in your alerts, drop the line instead with
`select(.lifecycle.daysRemaining != null)`.

## Pushgateway

Same JSON, different sink. Use one grouping key per host so a scan that stops
running leaves its last value visible rather than mixing hosts together.

```shell
check-opencloud-scanner scan --compact opencloud.example.com \
  | jq -r '
      "# TYPE opencloud_security_rating gauge",
      "opencloud_security_rating \(.rating)",
      "# TYPE opencloud_support_days_left gauge",
      "opencloud_support_days_left \(.lifecycle.daysRemaining // 0)"' \
  | curl -sS --data-binary @- \
      http://pushgateway.example.com:9091/metrics/job/opencloud_security/instance/opencloud.example.com
```

Pushgateway never forgets a metric. Delete the group when you retire an
instance, or it will be alerting on a server that no longer exists:

```shell
curl -X DELETE http://pushgateway.example.com:9091/metrics/job/opencloud_security/instance/opencloud.example.com
```

## Alerting rules

For the native exporter, copy
[`contrib/prometheus/alerts.yml`](../contrib/prometheus/alerts.yml) rather
than the block below - it is maintained against the real metric names and
tested against them.

The rules below match the **`jq`-shaped** names from the two recipes above,
which are shorter and different:

```yaml
groups:
  - name: opencloud-security
    rules:
      - alert: OpenCloudEndOfLife
        expr: opencloud_end_of_life == 1
        for: 1h
        labels: {severity: critical}
        annotations:
          summary: "{{ $labels.host }} runs an OpenCloud release with no security fixes"

      - alert: OpenCloudSupportRunningOut
        expr: opencloud_support_days_left < 30 and opencloud_support_days_left > 0
        for: 6h
        labels: {severity: warning}
        annotations:
          summary: "{{ $labels.host }} loses support in {{ $value }} days"

      - alert: OpenCloudRatingDropped
        expr: opencloud_security_rating <= 3
        for: 1h
        labels: {severity: warning}
        annotations:
          summary: "{{ $labels.host }} is rated {{ $value }}/5"

      - alert: OpenCloudScanFailing
        # A scan that no longer runs is the failure mode that hides all others.
        expr: opencloud_scan_success == 0 or absent(opencloud_scan_success)
        for: 2h
        labels: {severity: warning}
        annotations:
          summary: "The OpenCloud security scan has not produced a result"
```

Match `for:` to your scan interval. With a daily scan a `for: 5m` fires on the
first scrape after a bad result, which is the same thing as no `for:` at all.

## Grafana

Import [`contrib/grafana/dashboard.json`](../contrib/grafana/dashboard.json)
and pick your Prometheus data source. It draws the scan-health tile first, the
grade and the lifecycle beside it, then the grade over time, the open
findings, the advisories by severity, and a table of what is running where.

If you would rather build your own: the rating is a `0`-`5` score where higher
is better, so a stat panel with thresholds at `3` (yellow) and `1` (red)
mirrors the plugin's own defaults. Map the values to the letters the rest of
the output uses: `5 → A+`, `4 → A`, `3 → C`, `2 → D`, `1 → E`, `0 → F` - a
grade with no letter beside it gets read as a score out of five.

Put the version in a table panel next to it. The rating tells you that
something is wrong; the version is what tells you whether an upgrade is the
answer.

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
