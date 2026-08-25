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
import time

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


def test_instance_strings_cannot_inject_plugin_lines_or_perfdata():
    """A monitored host may supply text, but not Nagios framing characters."""
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productname"] = "OpenCloud\nforged status"
    behaviour.status_payload["productversion"] = "7.2.3 | forged_metric=999"

    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin("-H", instance.host)

    assert result.returncode == OK
    assert "\nforged status" not in result.stdout
    assert " | forged_metric=999" not in result.stdout
    assert result.stdout.count(" | ") == 1
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


def test_help_mentions_the_built_in_scanner():
    """Operators must be able to see from --help alone where the verdict comes from."""
    result = run_plugin("--help")
    text = " ".join(result.stdout.split())

    assert result.returncode == 0
    assert "built-in scanner" in text
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


def test_configure_and_upgrade_self_do_not_require_a_host():
    """Both modes are for a host that has not been configured yet."""
    upgrade = run_plugin("--upgrade-self=check")
    configure = run_plugin("--configure", env={"COS_HOST": ""})

    for result in (upgrade, configure):
        assert "the following arguments are required" not in result.stderr
        assert "--host" not in result.stderr


def test_upgrade_self_refuses_to_install_over_this_checkout():
    """Running it in a working copy must be reported, not silently attempted."""
    result = run_plugin("--upgrade-self=check")

    assert result.returncode == UNKNOWN
    assert "source checkout" in result.stdout
    assert "git pull" in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["--upgrade-self"],
        ["--upgrade-self", "run"],
        ["--upgrade-self", "check"],
        ["--upgrade-self=check"],
    ],
)
def test_upgrade_self_accepts_its_two_values_in_every_spelling(args):
    """`--upgrade-self`, `--upgrade-self check` and `--upgrade-self=check` are one flag."""
    result = run_plugin(*args)

    assert result.returncode == UNKNOWN, result.stderr
    assert "invalid choice" not in result.stderr
    # It got as far as the checkout refusal, so the value parsed.
    assert "source checkout" in result.stdout


def test_upgrade_self_rejects_a_value_it_does_not_know():
    """A typo like --upgrade-self=dry must not be read as 'go ahead and upgrade'."""
    result = run_plugin("--upgrade-self=dry")

    assert result.returncode != 0
    assert "invalid choice" in result.stderr
    assert "source checkout" not in result.stdout


def test_the_old_dry_run_flag_is_rejected_rather_than_ignored():
    """
    It used to be accepted and silently do nothing on its own; a flag promising
    'this changes nothing' has to fail loudly once it no longer exists.
    """
    alone = run_plugin("--dry-run", env={"COS_HOST": "opencloud.example.com"})
    combined = run_plugin("--upgrade-self", "--dry-run")

    for result in (alone, combined):
        assert result.returncode != 0
        assert "--dry-run" in result.stderr


def test_configure_writes_a_file_the_next_run_finds(tmp_path):
    """The whole point of --configure is that afterwards no arguments are needed."""
    target = tmp_path / ".env.json"
    # host, no optional settings, no test scan (there is no instance to reach).
    answers = "opencloud.example.com\nn\nn\n"

    written = subprocess.run(
        [sys.executable, str(PLUGIN), "--configure", "--config", str(target)],
        input=answers,
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT)},
        check=False,
    )

    assert written.returncode == 0, written.stderr
    assert json.loads(target.read_text()) == {"host": "opencloud.example.com"}
    assert "Example:" in written.stdout

    used = run_plugin("--config", str(target), "--timeout", "1")
    assert "the following arguments are required" not in used.stderr


def test_help_documents_the_new_modes():
    """An option nobody can discover from --help may as well not exist."""
    text = " ".join(run_plugin("--help").stdout.split())

    assert "--configure" in text
    assert "--upgrade-self" in text
    assert "--baseline" in text
    assert "--warn-on-new" in text
    assert "--self-update-check" in text


# --- Baseline: reporting only what changed ---


def test_the_first_run_records_a_baseline_and_still_reports_normally(tmp_path):
    """Starting to use --baseline must not blind the very first check."""
    baseline = tmp_path / "baseline.json"
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    with FakeOpenCloud(behaviour) as instance:
        result = run_plugin(
            "-H", instance.host, "--baseline", str(baseline), "--warn-on-new"
        )

    assert result.returncode == WARNING, result.stdout
    assert "becomes the baseline" in result.stdout
    stored = json.loads(baseline.read_text())["hosts"][instance.host]
    assert "check:exposed:/opencloud.yaml" in stored["findings"]


def test_warn_on_new_stays_quiet_while_nothing_changes(tmp_path):
    """A problem someone is already working on must not page anyone twice."""
    baseline = tmp_path / "baseline.json"
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    with FakeOpenCloud(behaviour) as instance:
        first = run_plugin("-H", instance.host, "--baseline", str(baseline), "--warn-on-new")
        second = run_plugin("-H", instance.host, "--baseline", str(baseline), "--warn-on-new")
        without = run_plugin("-H", instance.host)

    assert first.returncode == WARNING, first.stdout
    assert second.returncode == OK, second.stdout
    assert "nothing new since the last run" in second.stdout
    # The state itself is still reported, only the alert is suppressed.
    assert "exposed:/opencloud.yaml" in second.stdout
    assert "would otherwise be WARNING" in second.stdout
    # And without the flag the same instance still alerts.
    assert without.returncode == WARNING


def test_a_new_problem_alerts_even_with_a_baseline(tmp_path):
    """Suppressing what is known must never suppress what is new."""
    baseline = tmp_path / "baseline.json"
    with FakeOpenCloud(InstanceBehaviour(exposed_paths={"/opencloud.yaml"})) as instance:
        run_plugin("-H", instance.host, "--baseline", str(baseline), "--warn-on-new")

    worse = InstanceBehaviour(exposed_paths={"/opencloud.yaml", "/.env"})
    with FakeOpenCloud(worse) as instance2:
        # Same host name, different port, so rewrite the stored key.
        stored = json.loads(baseline.read_text())
        stored["hosts"][instance2.host] = next(iter(stored["hosts"].values()))
        baseline.write_text(json.dumps(stored))
        result = run_plugin(
            "-H", instance2.host, "--baseline", str(baseline), "--warn-on-new"
        )

    assert result.returncode != OK, result.stdout
    assert "New since last run" in result.stdout
    assert "exposed:/.env" in result.stdout


def test_an_end_of_life_release_is_never_grandfathered_in(tmp_path):
    """A release that gets no security fixes must alert on every single run."""
    baseline = tmp_path / "baseline.json"
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = "2.0.0"
    with FakeOpenCloud(behaviour) as instance:
        first = run_plugin("-H", instance.host, "--baseline", str(baseline), "--warn-on-new")
        second = run_plugin("-H", instance.host, "--baseline", str(baseline), "--warn-on-new")

    assert first.returncode == CRITICAL, first.stdout
    assert second.returncode == CRITICAL, second.stdout
    assert "end of life" in second.stdout


def test_warn_on_new_without_a_baseline_is_rejected():
    """Without somewhere to remember the last run it would report 'nothing new' forever."""
    result = run_plugin("-H", "opencloud.example.com", "--warn-on-new")

    assert result.returncode == 2
    assert "--warn-on-new needs --baseline" in result.stderr


def test_a_baseline_that_cannot_be_written_does_not_change_the_verdict(tmp_path, healthy):
    """Bookkeeping must never decide whether an instance is healthy."""
    unwritable = tmp_path / "nope"
    unwritable.write_text("not a directory")

    result = run_plugin("-H", healthy.host, "--baseline", str(unwritable / "b.json"))

    assert result.returncode == OK, result.stdout
    assert "Baseline could not be written" in result.stdout


def test_check_only_is_only_accepted_together_with_upgrade_self():
    """A flag that means nothing on its own has to say so instead of being ignored."""
    paired = run_plugin("--upgrade-self", "--check-only")
    alone = run_plugin("--check-only", "-H", "opencloud.example.com")

    assert paired.returncode == UNKNOWN
    assert "source checkout" in paired.stdout
    assert "upgraded" not in paired.stdout
    assert alone.returncode == 2
    assert "--check-only is only meaningful" in alone.stderr


def test_a_plugin_update_is_a_note_and_never_the_verdict(tmp_path, healthy):
    """PyPI being reachable says nothing about the instance being monitored."""
    cache = tmp_path / "check-opencloud-security"
    cache.mkdir()
    (cache / "pypi-version.json").write_text(
        json.dumps({"version": "99.0.0", "checkedAt": time.time()})
    )

    result = run_plugin(
        "-H",
        healthy.host,
        "--self-update-check",
        env={"XDG_CACHE_HOME": str(tmp_path)},
    )
    without = run_plugin("-H", healthy.host, env={"XDG_CACHE_HOME": str(tmp_path)})

    assert result.returncode == OK, result.stdout
    assert "Plugin update available: check-opencloud-security 99.0.0" in result.stdout
    assert "99.0.0" not in without.stdout, "the check must be off by default"
