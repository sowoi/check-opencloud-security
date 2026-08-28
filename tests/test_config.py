"""Tests for the layered configuration and the secret providers."""

import json
import os

import pytest

from opencloud_local_scan.config import ConfigurationError, load_configuration
from opencloud_local_scan.factory import (
    release_settings_from_config,
    scanner_settings_from_config,
)
from opencloud_local_scan.secrets import SecretProvider, SecretResolutionError


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_yaml_values_are_flattened_to_env_style_names(tmp_path):
    """Nested YAML keys map onto the same names as the environment variables."""
    config_file = _write(
        tmp_path,
        "config.yml",
        """
        host: cloud.example.com
        webhook:
          url: https://hooks.example.com/opencloud
        scanner:
          timeout: 25
          extra_checks: false
        releases:
          mode: bundled
        """,
    )

    config = load_configuration(str(config_file), environ={})

    assert config.get("HOST") == "cloud.example.com"
    assert config.get("WEBHOOK_URL") == "https://hooks.example.com/opencloud"
    assert config.get("RELEASES_MODE") == "bundled"
    assert config.get_int("SCANNER_TIMEOUT", 10) == 25
    assert config.get_bool("SCANNER_EXTRA_CHECKS", True) is False


def test_environment_variables_take_precedence_over_the_file(tmp_path):
    """An environment variable always wins over the configuration file."""
    config_file = _write(tmp_path, "config.yml", "host: from-file.example.com\n")

    config = load_configuration(str(config_file), environ={"COS_HOST": "from-env.example.com"})

    assert config.get("HOST") == "from-env.example.com"


def test_missing_explicit_config_file_is_an_error(tmp_path):
    """A configuration file requested by the user must exist."""
    with pytest.raises(ConfigurationError):
        load_configuration(str(tmp_path / "does-not-exist.yml"), environ={})


def test_lists_are_joined_with_semicolons(tmp_path):
    """YAML lists use the same separator as the environment variable form."""
    config_file = _write(
        tmp_path,
        "config.yml",
        "scanner:\n  vulnerability_db:\n    - /a.json\n    - /b.json\n",
    )

    config = load_configuration(str(config_file), environ={})

    assert config.get_list("SCANNER_VULNERABILITY_DB") == ["/a.json", "/b.json"]


def test_secret_reference_in_yaml_is_resolved_from_the_secrets_dir(tmp_path):
    """'secret://name' reads <secrets_dir>/name."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "release_token").write_text("s3cr3t\n", encoding="utf-8")
    config_file = _write(
        tmp_path,
        "config.yml",
        f"secrets:\n  dir: {secrets_dir}\nreleases:\n  token: secret://release_token\n",
    )

    config = load_configuration(str(config_file), environ={})

    assert config.get("RELEASES_TOKEN") == "s3cr3t"


def test_file_suffix_convention_reads_the_value_from_disk(tmp_path):
    """COS_<NAME>_FILE supplies the value of COS_<NAME>."""
    secret_file = _write(tmp_path, "token", "hunter2\n")

    config = load_configuration(None, environ={"COS_SERVICE_TOKEN_FILE": str(secret_file)})

    assert config.get("SERVICE_TOKEN") == "hunter2"


def test_unreadable_secret_raises_configuration_error():
    """A broken secret reference is reported instead of silently ignored."""
    config = load_configuration(None, environ={"COS_RELEASES_TOKEN": "file:///nope/missing"})

    with pytest.raises(ConfigurationError):
        config.get("RELEASES_TOKEN")


def test_env_scheme_reads_environment_variables():
    """'env://VAR' resolves through the process environment."""
    provider = SecretProvider()

    os.environ["COS_TEST_SECRET"] = "value-from-env"
    try:
        assert provider.resolve("env://COS_TEST_SECRET") == "value-from-env"
    finally:
        del os.environ["COS_TEST_SECRET"]


def test_exec_scheme_is_disabled_by_default():
    """Command execution must be opted into explicitly."""
    provider = SecretProvider()

    with pytest.raises(SecretResolutionError, match="disabled"):
        provider.resolve("exec://echo hello")


def test_exec_scheme_runs_the_command_when_allowed():
    """With allow_exec the command output becomes the value."""
    provider = SecretProvider(allow_exec=True)

    assert provider.resolve("exec://echo hello") == "hello"


def test_plain_values_pass_through_unchanged():
    """Values without a known scheme are never touched."""
    provider = SecretProvider()

    assert provider.resolve("just-a-password") == "just-a-password"
    assert provider.resolve(42) == 42


# --- factory ---
def test_scanner_settings_are_built_from_the_configuration(tmp_path):
    """Everything the scanner needs can be expressed in the config file."""
    config_file = _write(
        tmp_path,
        "config.yml",
        """
        scanner:
          timeout: 20
          verify_tls: false
          tls_ca_file: /etc/ssl/opencloud-ca.pem
          scheme: http
          target_port: 9200
          tls_min_days: 30
          check_debug_ports: false
          debug_ports: "9205,9141"
          concurrency: 8
          user_agent: custom-agent
        """,
    )

    settings = scanner_settings_from_config(load_configuration(str(config_file), environ={}))

    assert settings.timeout == 20
    assert settings.verify_tls is False
    assert settings.tls_ca_file == "/etc/ssl/opencloud-ca.pem"
    assert settings.scheme == "http"
    assert settings.port == 9200
    assert settings.tls_min_days == 30
    assert settings.check_debug_ports is False
    assert settings.debug_ports == (9141, 9205)
    assert settings.concurrency == 8
    assert settings.user_agent == "custom-agent"


def test_scanning_stays_single_threaded_unless_asked(tmp_path):
    """An operator who says nothing about concurrency must get none."""
    config_file = _write(tmp_path, "config.yml", "scanner:\n  timeout: 20\n")

    settings = scanner_settings_from_config(load_configuration(str(config_file), environ={}))

    assert settings.concurrency == 1
    assert (
        scanner_settings_from_config(
            load_configuration(str(config_file), environ={"COS_SCANNER_CONCURRENCY": "6"})
        ).concurrency
        == 6
    )


def test_scanner_overrides_win_over_the_configuration(tmp_path):
    """Command line flags are passed in as overrides and must take precedence."""
    config_file = _write(tmp_path, "config.yml", "scanner:\n  timeout: 20\n")
    config = load_configuration(str(config_file), environ={})

    settings = scanner_settings_from_config(config, timeout=5, extra_checks=False)

    assert settings.timeout == 5
    assert settings.extra_checks is False


def test_none_overrides_are_ignored(tmp_path):
    """A flag that was not given must not blank out the configured value."""
    config_file = _write(tmp_path, "config.yml", "scanner:\n  timeout: 20\n")
    config = load_configuration(str(config_file), environ={})

    assert scanner_settings_from_config(config, timeout=None).timeout == 20


def test_generic_timeout_and_proxy_are_shared(tmp_path):
    """A single 'timeout:' / 'proxy:' applies to scanner and release check alike."""
    config_file = _write(
        tmp_path, "config.yml", "timeout: 42\nproxy: http://proxy.example.com:3128\n"
    )
    config = load_configuration(str(config_file), environ={})

    scanner = scanner_settings_from_config(config)
    release = release_settings_from_config(config)

    assert scanner.timeout == 42
    assert release.timeout == 42
    assert scanner.proxies == {
        "http": "http://proxy.example.com:3128",
        "https": "http://proxy.example.com:3128",
    }
    assert release.proxy == "http://proxy.example.com:3128"


def test_release_settings_are_built_from_the_configuration(tmp_path):
    """The update check is configured the same way as everything else."""
    config_file = _write(
        tmp_path,
        "config.yml",
        """
        releases:
          mode: pinned
          latest_version: "7.4.0"
          feed_url: https://mirror.example.com/releases.json
          verify_tls: false
        """,
    )

    settings = release_settings_from_config(load_configuration(str(config_file), environ={}))

    assert settings.mode == "pinned"
    assert settings.latest_version == "7.4.0"
    assert settings.feed_url == "https://mirror.example.com/releases.json"
    assert settings.verify_tls is False


def test_unknown_release_mode_falls_back_to_auto(tmp_path):
    """A typo in the config must not break the check."""
    config_file = _write(tmp_path, "config.yml", "releases:\n  mode: nonsense\n")

    settings = release_settings_from_config(load_configuration(str(config_file), environ={}))

    assert settings.mode == "auto"


def test_configuration_without_a_file_still_reads_the_environment():
    """Running without a config file is the normal Nagios deployment."""
    config = load_configuration(None, environ={"COS_HOST": "cloud.example.com"})

    assert config.get("HOST") == "cloud.example.com"
    assert config.source is None


def test_a_custom_release_schedule_can_be_configured(tmp_path):
    """A site that mirrors the OpenCloud docs can point the check at its own.

    The same hook serves an operator whose vendor has committed to a support
    window that differs from the public one.
    """
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_text(
        json.dumps(
            {
                "latest_release": {"lts": "9.0.1"},
                "lines": [
                    {
                        "line": "9.0",
                        "tracks": ["lts"],
                        "released": "2026-01-01",
                        "latest": "9.0.1",
                    }
                ],
            }
        )
    )
    config_file = _write(
        tmp_path,
        "config.yml",
        f"""
        scanner:
          release_schedule: {schedule_file}
        """,
    )

    settings = scanner_settings_from_config(load_configuration(str(config_file), environ={}))

    assert settings.release_schedule is not None
    assert settings.release_schedule.latest_for("lts") == "9.0.1"


def test_no_release_schedule_key_means_the_bundled_one(tmp_path):
    """The default has to keep working without any configuration at all."""
    config_file = _write(tmp_path, "config.yml", "scanner:\n  timeout: 5\n")

    settings = scanner_settings_from_config(load_configuration(str(config_file), environ={}))

    assert settings.release_schedule is None


def test_a_json_file_is_read_the_same_way_as_yaml(tmp_path):
    """The wizard writes JSON, so it has to reach the settings unchanged."""
    document = {
        "host": "cloud.example.com",
        "webhook": {"url": "https://hooks.example.com/opencloud"},
        "scanner": {"timeout": 25, "extra_checks": False, "concurrency": 4},
        "releases": {"mode": "bundled"},
    }
    config_file = _write(tmp_path, ".env.json", json.dumps(document))

    config = load_configuration(str(config_file), environ={})

    assert config.get("HOST") == "cloud.example.com"
    assert config.get("WEBHOOK_URL") == "https://hooks.example.com/opencloud"
    assert config.get("RELEASES_MODE") == "bundled"
    assert config.get_int("SCANNER_TIMEOUT", 10) == 25
    assert config.get_bool("SCANNER_EXTRA_CHECKS", True) is False
    assert scanner_settings_from_config(config).concurrency == 4


def test_the_format_follows_the_suffix_not_the_content(tmp_path):
    """JSON is valid YAML, but a .json file must never depend on PyYAML."""
    from opencloud_local_scan.config import load_config_file

    as_json = _write(tmp_path, "settings.json", '{"host": "a.example.com"}')
    as_yaml = _write(tmp_path, "settings.yml", "host: b.example.com\n")

    assert load_config_file(as_json) == {"host": "a.example.com"}
    assert load_config_file(as_yaml) == {"host": "b.example.com"}

    broken = _write(tmp_path, "broken.json", "host: not-json\n")
    with pytest.raises(ConfigurationError):
        load_config_file(broken)


def test_env_json_in_the_working_directory_is_found_automatically(tmp_path, monkeypatch):
    """After --configure the check must run with no arguments at all."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.json").write_text('{"host": "found.example.com"}')

    assert load_configuration(None, environ={}).get("HOST") == "found.example.com"

    (tmp_path / ".env.json").unlink()
    assert load_configuration(None, environ={}).get("HOST") is None


def test_an_explicit_file_still_wins_over_the_discovered_one(tmp_path, monkeypatch):
    """--config must not be quietly overridden by a stray .env.json in the cwd."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.json").write_text('{"host": "discovered.example.com"}')
    explicit = _write(tmp_path, "explicit.json", '{"host": "explicit.example.com"}')

    config = load_configuration(str(explicit), environ={})

    assert config.get("HOST") == "explicit.example.com"
