"""
The shipped Grafana dashboard and Prometheus rules must match the exporter.

A dashboard is not documentation: nobody reads it, they import it, and a panel
querying a metric that was renamed two releases ago renders an empty rectangle
rather than an error. These tests derive the metric names from the exporter
itself, so a rename breaks the suite instead of the operator's wall display.

The Checkmk local check is the same bargain in the other direction: it is
copied to an agent host and never read again, so it is run here - against a
fake instance, and with the plugin taken away - rather than reviewed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from opencloud_local_scan.prometheus import render
from tests.fake_opencloud import FakeOpenCloud
from tests.test_e2e_cli import PLUGIN, coverage_environment

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "contrib" / "grafana" / "dashboard.json"
ALERTS = ROOT / "contrib" / "prometheus" / "alerts.yml"
LOCAL_CHECK = ROOT / "contrib" / "checkmk" / "opencloud_security"

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


def _run_local_check(**environment: str) -> subprocess.CompletedProcess:
    """Run the shipped local check the way the Checkmk agent runs it."""
    return subprocess.run(
        ["/bin/sh", str(LOCAL_CHECK)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(ROOT),
            "COS_UPDATE_SOURCE": "off",
            "COS_SCANNER_SCHEME": "http",
            "COS_SCANNER_CHECK_DEBUG_PORTS": "false",
            **coverage_environment(),
            **environment,
        },
    )


def _plugin_shim(tmp_path: Path) -> str:
    """The plugin as an executable on PATH, which is how the agent host has it."""
    shim = tmp_path / "check-opencloud-security"
    shim.write_text(f'#!/bin/sh\nexec {sys.executable} {PLUGIN} "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return str(shim)


def test_the_checkmk_local_check_prints_one_line_the_agent_can_parse(tmp_path):
    """
    The shipped script is copied to an agent host and never read again.

    Checkmk drops a local check line it cannot split into state, quoted
    service name, metrics and detail - silently, as a service that never
    appears - so the shape is asserted here rather than discovered there.
    """
    with FakeOpenCloud() as instance:
        result = _run_local_check(
            COS_HOST=instance.host, COS_PLUGIN=_plugin_shim(tmp_path)
        )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    state, rest = lines[0].split(" ", 1)
    assert state in {"0", "1", "2", "3"}
    service, rest = rest[1:].split('"', 1)
    assert service.startswith("OpenCloud_Security_")
    metrics, detail = rest.lstrip(" ").split(" ", 1)
    names = dict(metric.split("=", 1) for metric in metrics.split("|"))
    assert names["rating"] == "5"
    # The script's own COS_CHECK_HARDENING default has to reach the plugin:
    # without it the scan runs but reports none of the measures an instance
    # is missing, and the metric is left out entirely.
    assert "hardenings_missing" in names
    assert detail


def test_the_checkmk_local_check_reports_a_missing_plugin_as_unknown(tmp_path):
    """
    The negative case, and the one an agent host actually hits.

    A local check that prints nothing removes its service from the host
    instead of alerting, so an uninstalled plugin would look like a check
    somebody had deliberately switched off.
    """
    result = _run_local_check(
        COS_HOST="opencloud.example.com", COS_PLUGIN=str(tmp_path / "absent")
    )

    assert result.returncode == 0, result.stderr
    line = result.stdout.strip()
    assert line.startswith('3 "OpenCloud_Security" - UNKNOWN:')


def test_the_checkmk_local_check_is_executable():
    """It is installed with `install -m 0755`; a mode of 644 is a service that never runs."""
    assert os.access(LOCAL_CHECK, os.X_OK)
