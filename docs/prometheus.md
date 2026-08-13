# Prometheus and Grafana

The plugin is a Nagios plugin, not an exporter, and it stays one - a scan
takes seconds and hits a real instance, so it must not run on a scrape. The
two workable shapes are both *push*: write the metrics to a file that
node_exporter serves, or push them once per scan to a Pushgateway.

If you already run Icinga2, you do not need any of this: the
[performance data](../README.md#performance-data) the plugin prints is picked
up by Icinga2's Graphite/InfluxDB writers directly.

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

`opencloud_security_rating` is a `0`-`5` score where higher is better; a stat
panel with thresholds at `3` (yellow) and `1` (red) mirrors the plugin's own
defaults. Map the values to the letters the rest of the output uses with a
value mapping: `5 → A+`, `4 → A`, `3 → C`, `2 → D`, `1 → E`, `0 → F`.

Put `opencloud_version_info` in a table panel next to it. The rating tells you
that something is wrong; the version label is what tells you what to do about
it.

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
