"""
The shipped Grafana dashboard and Prometheus rules must match the exporter.

A dashboard is not documentation: nobody reads it, they import it, and a panel
querying a metric that was renamed two releases ago renders an empty rectangle
rather than an error. These tests derive the metric names from the exporter
itself, so a rename breaks the suite instead of the operator's wall display.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from opencloud_local_scan.prometheus import render

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "contrib" / "grafana" / "dashboard.json"
ALERTS = ROOT / "contrib" / "prometheus" / "alerts.yml"

#: A result document that reaches every optional metric family. Written out
#: rather than scanned, because the point is the *union* of what the exporter
#: can emit - a real instance that happens to be healthy emits fewer families
#: and would let a stale panel through.
COMPLETE_RESULT = {
    "domain": "cloud.example.com",
    "product": "OpenCloud",
    "version": "7.2.0",
    "rating": 3,
    "EOL": True,
    "vulnerabilities": [{"id": "CVE-2026-0001", "severity": "high"}],
    "hardenings": {"hstsLongMaxAge": False},
    "extraChecks": [{"id": "tlsTrusted", "passed": False}],
    "lifecycle": {"daysRemaining": 42, "releaseType": "production"},
    "updates": {"available": True, "availableVersion": "7.4.0"},
}

# Deliberately requires the underscore: `opencloud` on its own is the tag, the
# uid and half the prose in both files, and is never a metric name.
_METRIC = re.compile(r"opencloud_[a-z0-9_]+")


def _emitted_metric_names() -> set[str]:
    """Every metric family the exporter declares, read from its own output."""
    exposition = render(
        "opencloud.example.com", COMPLETE_RESULT, duration_seconds=1.0, success=True
    )
    return {
        line.split()[2]
        for line in exposition.splitlines()
        if line.startswith("# HELP ")
    }


def _referenced_metric_names(text: str) -> set[str]:
    """Every OpenCloud metric name mentioned anywhere in a shipped file."""
    return set(_METRIC.findall(text))


def test_the_dashboard_only_queries_metrics_the_exporter_emits():
    """An imported panel that queries a renamed metric draws an empty box, not an error."""
    referenced = _referenced_metric_names(DASHBOARD.read_text(encoding="utf-8"))

    assert referenced, "the dashboard queries no OpenCloud metric at all"
    assert referenced <= _emitted_metric_names()


def test_the_alert_rules_only_match_metrics_the_exporter_emits():
    """An alert on a metric nobody publishes is an alert that never fires."""
    referenced = _referenced_metric_names(ALERTS.read_text(encoding="utf-8"))

    assert referenced, "the rules match no OpenCloud metric at all"
    assert referenced <= _emitted_metric_names()


def test_the_shipped_files_do_not_use_the_documented_jq_metric_names():
    """
    The negative case, and the easy mistake.

    docs/prometheus.md also shows a textfile-collector recipe whose `jq` shapes
    its own shorter names - `opencloud_security_rating`, `opencloud_scan_success`.
    Copying those rules into the shipped files would produce alerts that are
    silent against the native exporter and correct-looking in review.
    """
    shipped = DASHBOARD.read_text(encoding="utf-8") + ALERTS.read_text(encoding="utf-8")

    for jq_name in (
        "opencloud_scan_success",
        "opencloud_end_of_life",
        "opencloud_support_days_left",
        "opencloud_failed_checks",
        "opencloud_version_info",
    ):
        assert jq_name not in shipped


def test_the_alert_rules_parse_as_a_prometheus_rule_file():
    """Prometheus refuses to start on a malformed rule file, taking the alerting with it."""
    document = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))

    groups = document["groups"]
    assert groups
    for group in groups:
        assert group["name"]
        for rule in group["rules"]:
            assert rule["alert"] and rule["expr"]
            assert rule["annotations"]["summary"]
            assert rule["labels"]["severity"] in {"info", "warning", "critical"}


def test_every_dashboard_panel_reads_the_selected_data_source():
    """
    A panel pinned to somebody else's data source uid is empty on import.

    Grafana only rewires panels that reference the dashboard's own variable,
    so a hardcoded uid is the difference between an import that works and one
    that has to be repaired panel by panel.
    """
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))

    assert any(
        variable["name"] == "datasource" and variable["type"] == "datasource"
        for variable in dashboard["templating"]["list"]
    )
    for panel in dashboard["panels"]:
        assert panel["datasource"]["uid"] == "${datasource}", panel["title"]
        assert panel["targets"], panel["title"]
        for target in panel["targets"]:
            assert target["datasource"]["uid"] == "${datasource}", panel["title"]


def test_every_dashboard_panel_says_what_it_is_for():
    """
    A grade with no explanation beside it gets read as a score out of five.

    The panel description is where the reader learns that an empty support
    tile means 'not dated yet' rather than 'expires today'.
    """
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))

    for panel in dashboard["panels"]:
        assert panel["description"].strip(), panel["title"]
