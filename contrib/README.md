# Ready-to-adapt operator files

Things that are better shipped as a file than printed in a document: nobody
retypes a dashboard.

- `systemd/` - a `.service` + `.timer` pair, plus an example environment file.
- `cron/` - a `cron.d` drop-in file.
- `prometheus/alerts.yml` - alerting rules for the plugin's own exporter.
- `grafana/dashboard.json` - a dashboard for the same metrics.

See the "Scheduling without Icinga2 / Nagios" section in the main
[README.md](../README.md) for the two scheduling examples, and
[Prometheus and Grafana](../docs/prometheus.md) for the other two.

The scheduling examples rely on the `COS_*` environment variables documented
in the main README instead of command-line flags, so the same plugin
binary/image can be reused unmodified.

## Prometheus and Grafana

```shell
# prometheus.yml
rule_files:
  - /etc/prometheus/rules/opencloud-security.yml
```

```shell
cp contrib/prometheus/alerts.yml /etc/prometheus/rules/opencloud-security.yml
promtool check rules /etc/prometheus/rules/opencloud-security.yml
```

Import `contrib/grafana/dashboard.json` in Grafana under **Dashboards - New -
Import**, then pick the Prometheus data source that scrapes the exporter. The
dashboard has an `Instance` selector, so one copy serves every host.

Both files read the metric names the **native exporter** publishes
(`--prometheus-listen-port`, or `--format=prometheus` for a batch job). The
textfile-collector and Pushgateway recipes in
[the Prometheus guide](../docs/prometheus.md) shape shorter names of their own
with `jq`; those are not what these files match.
`tests/test_contrib_assets.py` derives the metric names from the exporter
itself, so a rename fails the test suite rather than quietly emptying a panel.
