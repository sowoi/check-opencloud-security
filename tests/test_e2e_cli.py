"""
End-to-end tests: the real CLI, over real HTTP, against a fake OpenCloud.

Nothing is mocked here except the instance itself. Both entry points are
exercised as a monitoring system would run them - as a subprocess, checked
by exit code and stdout.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from tests.fake_opencloud import DEFAULT_CSP_UNSAFE, FakeOpenCloud, InstanceBehaviour

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "check_opencloud_security.py"

OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def run_plugin(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the plugin exactly the way a monitoring daemon would."""
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT),
        # Nothing in an end-to-end test may reach out to GitHub.
        "COS_UPDATE_SOURCE": "off",
        "COS_SCANNER_SCHEME": "http",
        "COS_SCANNER_CHECK_DEBUG_PORTS": "false",
        **(env or {}),
    }
    return subprocess.run(
        [sys.executable, str(PLUGIN), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
        check=False,
    )


def run_scanner(*args: str) -> subprocess.CompletedProcess:
    """Run the bundled scanner CLI."""
    return subprocess.run(
        [sys.executable, "-m", "opencloud_local_scan.cli", *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT)},
        check=False,
    )


@pytest.fixture
def healthy():
    """A stock, well configured OpenCloud instance."""
    behaviour = InstanceBehaviour()
    with FakeOpenCloud(behaviour) as instance:
        yield instance


def test_healthy_instance_is_ok(healthy):
    """The happy path has to work end to end, or nothing else matters."""
    result = run_plugin("-H", healthy.host)

    assert result.returncode == OK, result.stdout + result.stderr
    assert "OK:" in result.stdout
    assert "OpenCloud 7.2.3" in result.stdout
    assert "| rating=5" in result.stdout


def test_exposed_configuration_caps_the_rating():
    """
    A published opencloud.yaml caps the rating at D.

    D is above the default critical threshold (E), so the check warns; a site
    that wants to be paged for this runs with '-c 2'.
    """
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host)
        strict = run_plugin("-H", instance.host, "-c", "2")

    assert result.returncode == WARNING, result.stdout
    assert "exposed:/opencloud.yaml" in result.stdout
    assert "rating=2" in result.stdout
    assert strict.returncode == CRITICAL, strict.stdout


def test_end_of_life_release_is_critical():
    """An unmaintained release is the loudest thing this check reports."""
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = "2.0.0"
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host)

    assert result.returncode == CRITICAL, result.stdout
    assert "end-of-life" in result.stdout


def test_check_hardening_turns_a_weak_csp_into_a_warning():
    """OpenCloud's default CSP allows inline scripts."""
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = DEFAULT_CSP_UNSAFE
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host, "--check-hardening")

    assert result.returncode == WARNING, result.stdout
    assert "cspWithoutUnsafeInline" in result.stdout


def test_unreachable_instance_is_unknown():
    """A scan that could not happen is UNKNOWN, never OK and never CRITICAL."""
    with FakeOpenCloud() as instance:
        port = instance.port

    result = run_plugin("-H", f"127.0.0.1:{port}")

    assert result.returncode == UNKNOWN, result.stdout
    assert "UNKNOWN:" in result.stdout


def test_host_accepts_a_full_url(healthy):
    """Pasting the URL from a browser has to work."""
    result = run_plugin("-H", f"http://{healthy.host}/files/spaces")

    assert result.returncode == OK, result.stdout


def test_host_can_come_from_the_environment(healthy):
    """The deployment style most monitoring systems use."""
    result = run_plugin(env={"COS_HOST": healthy.host})

    assert result.returncode == OK, result.stdout


def test_multiple_hosts_are_summarised(healthy):
    """One command, one summary line, one block per host."""
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = "2.0.0"
    with FakeOpenCloud(behaviour) as bad:
        result = run_plugin("-H", f"{healthy.host},{bad.host}")

    assert result.returncode == CRITICAL, result.stdout
    assert "Checked 2 host(s): overall CRITICAL" in result.stdout
    assert f"[{healthy.host}]" in result.stdout
    assert f"[{bad.host}]" in result.stdout


def test_thresholds_can_be_tightened(healthy):
    """An operator who demands A+ gets to say so."""
    result = run_plugin("-H", healthy.host, "-w", "5", "-c", "4")

    assert result.returncode == WARNING, result.stdout


def test_config_file_is_honoured(healthy, tmp_path):
    """The YAML file is a first-class way to run the check."""
    config = tmp_path / "config.yml"
    config.write_text(
        f"host: {healthy.host}\ncheck_hardening: true\n"
        "scanner:\n  scheme: http\n  check_debug_ports: false\n"
        "releases:\n  mode: 'off'\n",
        encoding="utf-8",
    )

    result = run_plugin("--config", str(config))

    # The fake instance speaks plain HTTP, so 'httpsEnforced' is genuinely
    # missing - which is exactly what the file-configured flag should catch.
    assert result.returncode == WARNING, result.stdout
    assert "Missing hardening: httpsEnforced" in result.stdout


def test_version_flag_reports_the_plugin_version():
    """Packagers and bug reports depend on this."""
    result = run_plugin("--version")

    assert result.returncode == 0
    assert "check_opencloud_security" in result.stdout


def test_help_mentions_that_no_api_is_used():
    """A literal address is a perfectly normal target for the scanner."""
    result = run_plugin("--help")
    text = " ".join(result.stdout.split())

    assert result.returncode == 0
    assert "OpenCloud offers no public scan API" in text
    assert "every check runs locally" in text


def test_no_extra_checks_still_rates_the_instance():
    """The reduced mode must remain useful."""
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host, "--no-extra-checks")

    assert result.returncode == OK, result.stdout
    assert "OpenCloud 7.2.3" in result.stdout


# --- the scanner CLI ---
def test_scanner_cli_prints_a_json_document(healthy):
    """'check-opencloud-scanner scan' is the ad-hoc entry point."""
    result = run_scanner(
        "scan", healthy.host, "--scheme", "http", "--no-debug-ports", "--no-update-check"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(result.stdout)
    assert document["product"] == "OpenCloud"
    assert document["version"] == "7.2.3"
    assert document["rating"] == 5


def test_scanner_cli_scans_several_hosts(healthy):
    """Several hosts produce a JSON list, one entry each."""
    with FakeOpenCloud() as other:
        result = run_scanner(
            "scan",
            healthy.host,
            other.host,
            "--scheme",
            "http",
            "--no-debug-ports",
            "--no-update-check",
        )

    documents = json.loads(result.stdout)
    assert isinstance(documents, list)
    assert len(documents) == 2


def test_scanner_cli_reports_a_failed_scan_in_its_exit_code():
    """A CLI that exits 0 on failure is useless in a cron job."""
    with FakeOpenCloud() as instance:
        port = instance.port

    result = run_scanner("scan", f"127.0.0.1:{port}", "--scheme", "http")

    assert result.returncode == 1
    assert "error" in json.loads(result.stdout)


def test_scanner_cli_help_lists_both_subcommands():
    """'scan' and 'serve' are the whole interface."""
    result = run_scanner("--help")

    assert result.returncode == 0
    assert "scan" in result.stdout
    assert "serve" in result.stdout
