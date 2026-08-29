"""
--format json/sarif/junit: the real CLI, over real HTTP, against a fake
OpenCloud - the same harness test_e2e_cli.py uses, because the point of
these formats is that they combine correctly across one AND several hosts,
which only the real host-worker code path exercises.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from tests.fake_opencloud import DEFAULT_CSP_UNSAFE, FakeOpenCloud, InstanceBehaviour
from tests.test_e2e_cli import (  # noqa: F401
    CRITICAL,
    OK,
    UNKNOWN,
    WARNING,
    healthy,
    run_plugin,
)


def test_json_format_is_an_array_of_the_webhook_payload_shape():
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host, "--format", "json")

    assert result.returncode == WARNING, result.stdout
    documents = json.loads(result.stdout)
    assert isinstance(documents, list) and len(documents) == 1
    document = documents[0]
    assert document["host"] == instance.host
    assert document["status"] == "WARNING"
    assert "exposed:/opencloud.yaml" in document["failed_extra_checks"]


def test_json_format_is_always_an_array_even_for_one_host():
    """Documented behaviour: consistent tooling regardless of host count."""
    with FakeOpenCloud() as instance:
        result = run_plugin("-H", instance.host, "--format", "json")

    documents = json.loads(result.stdout)
    assert isinstance(documents, list)


def test_json_format_combines_several_hosts_into_one_array():
    healthy = InstanceBehaviour()
    broken = InstanceBehaviour()
    broken.status_payload["productversion"] = "2.0.0"
    with FakeOpenCloud(healthy) as good, FakeOpenCloud(broken) as bad:
        result = run_plugin("-H", f"{good.host},{bad.host}", "--format", "json")

    assert result.returncode == CRITICAL, result.stdout
    documents = json.loads(result.stdout)
    assert {document["host"] for document in documents} == {good.host, bad.host}
    statuses = {document["host"]: document["status"] for document in documents}
    assert statuses[bad.host] == "CRITICAL"


def test_json_format_reports_a_scan_that_failed_outright():
    with FakeOpenCloud() as instance:
        port = instance.port
    result = run_plugin("-H", f"127.0.0.1:{port}", "--format", "json")

    assert result.returncode == UNKNOWN, result.stdout
    documents = json.loads(result.stdout)
    assert documents[0]["status"] == "UNKNOWN"
    # The failure-shaped payload carries only the common fields.
    assert "rating" not in documents[0]


def test_sarif_format_is_valid_sarif_and_lists_findings():
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = DEFAULT_CSP_UNSAFE
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host, "--format", "sarif", "--check-hardening")

    assert result.returncode == WARNING, result.stdout
    document = json.loads(result.stdout)
    assert document["version"] == "2.1.0"
    run = document["runs"][0]
    assert run["tool"]["driver"]["name"] == "check-opencloud-security"
    rule_ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    assert "cspWithoutUnsafeInline" in rule_ids
    result_ids = {result["ruleId"] for result in run["results"]}
    assert "cspWithoutUnsafeInline" in result_ids
    assert all(result["properties"]["host"] == instance.host for result in run["results"])


def test_sarif_format_flags_an_end_of_life_release():
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = "2.0.0"
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host, "--format", "sarif")

    assert result.returncode == CRITICAL, result.stdout
    document = json.loads(result.stdout)
    results = document["runs"][0]["results"]
    assert any(entry["ruleId"] == "eol" and entry["level"] == "error" for entry in results)


def test_sarif_format_combines_several_hosts_into_one_run():
    with FakeOpenCloud() as first, FakeOpenCloud(InstanceBehaviour(exposed_paths={"/opencloud.yaml"})) as second:
        result = run_plugin("-H", f"{first.host},{second.host}", "--format", "sarif")

    document = json.loads(result.stdout)
    assert len(document["runs"]) == 1
    hosts = {entry["properties"]["host"] for entry in document["runs"][0]["results"]}
    assert second.host in hosts


def test_junit_format_is_valid_xml_with_one_testsuite_per_host():
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host, "--format", "junit")

    assert result.returncode == WARNING, result.stdout
    root = ET.fromstring(result.stdout)
    assert root.tag == "testsuites"
    suites = root.findall("testsuite")
    assert len(suites) == 1
    assert suites[0].get("name") == instance.host
    assert int(suites[0].get("failures")) >= 1
    case_names = {case.get("name") for case in suites[0].findall("testcase")}
    assert "exposed:/opencloud.yaml" in case_names
    assert "rating" in case_names


def test_junit_format_a_healthy_host_still_reports_a_rating_testcase():
    with FakeOpenCloud() as instance:
        result = run_plugin("-H", instance.host, "--format", "junit")

    root = ET.fromstring(result.stdout)
    suite = root.find("testsuite")
    assert suite.get("name") == instance.host
    rating_case = next(c for c in suite.findall("testcase") if c.get("name") == "rating")
    assert rating_case.find("failure") is None


def test_junit_format_combines_several_hosts():
    with FakeOpenCloud() as first, FakeOpenCloud() as second:
        result = run_plugin("-H", f"{first.host},{second.host}", "--format", "junit")

    assert result.returncode == OK, result.stdout
    root = ET.fromstring(result.stdout)
    names = {suite.get("name") for suite in root.findall("testsuite")}
    assert names == {first.host, second.host}


def test_exit_code_keeps_its_nagios_meaning_under_every_machine_format(healthy):
    for fmt in ("json", "sarif", "junit"):
        result = run_plugin("-H", healthy.host, "--format", fmt)
        assert result.returncode == OK, (fmt, result.stdout)


def test_webhook_still_fires_alongside_a_machine_format(monkeypatch):
    """Choosing a machine-readable stdout format must not disable notifications."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received: list[bytes] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            received.append(self.rfile.read(length))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
        with FakeOpenCloud(behaviour) as instance:
            result = run_plugin(
                "-H",
                instance.host,
                "--format",
                "sarif",
                "--webhook-url",
                f"http://127.0.0.1:{server.server_port}/",
                "--webhook-on",
                "always",
                "--allow-private-webhooks",
            )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result.returncode == WARNING, result.stdout
    json.loads(result.stdout)  # stdout is still clean SARIF
    assert len(received) == 1
    posted = json.loads(received[0])
    assert posted["host"] == instance.host
