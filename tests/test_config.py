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


def test_every_secret_in_a_nested_document_is_resolved(tmp_path):
    """
    Configuration is a tree, and a reference is legal wherever a value is.

    A reference that survives resolution is not an error anybody sees: it is
    the literal string 'secret://token' arriving at whatever the setting
    feeds - a header, a URL, a command line - where it either fails
    confusingly or gets logged.
    """
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "token").write_text("s3cr3t\n", encoding="utf-8")
    provider = SecretProvider(secrets_dir=str(secrets_dir))

    resolved = provider.resolve_tree(
        {
            "releases": {"token": "secret://token"},
            "targets": ["secret://token", "plain", 42],
            "port": 9200,
            "enabled": True,
        }
    )

    assert resolved == {
        "releases": {"token": "s3cr3t"},
        "targets": ["s3cr3t", "plain", 42],
        "port": 9200,
        "enabled": True,
    }
    # The negative half: nothing that was not a reference was rewritten, and
    # non-string leaves keep their type rather than becoming strings.
    assert resolved["port"] == 9200 and isinstance(resolved["port"], int)
    assert resolved["enabled"] is True


def test_a_reference_that_cannot_be_resolved_stops_the_whole_tree(tmp_path):
    """
    Half a resolved configuration is the worst outcome available.

    Continuing past a broken reference would start the service with the
    literal 'secret://...' in place of a credential, which reads as an
    authentication failure somewhere far away from the mistake.
    """
    provider = SecretProvider(secrets_dir=str(tmp_path))

    with pytest.raises(SecretResolutionError):
        provider.resolve_tree({"releases": {"token": "secret://absent"}})


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("secret://", "Empty secret reference"),
        ("env://", "Empty secret reference"),
        ("env://COS_DEFINITELY_NOT_SET", "is not set"),
    ],
)
def test_a_reference_that_names_nothing_is_refused_rather_than_read_as_empty(
    reference, expected
):
    """An empty credential is a credential the service would happily start without."""
    with pytest.raises(SecretResolutionError, match=expected):
        SecretProvider().resolve(reference)


def test_an_unset_variable_is_told_apart_from_one_set_to_nothing():
    """
    The negative half: 'env://VAR' where VAR is empty resolves to empty.

    That is the operator's choice and not this layer's to second-guess - only
    a variable that was never set is a mistake it can be sure of.
    """
    os.environ["COS_TEST_EMPTY_SECRET"] = ""
    try:
        assert SecretProvider().resolve("env://COS_TEST_EMPTY_SECRET") == ""
    finally:
        del os.environ["COS_TEST_EMPTY_SECRET"]


def test_every_scheme_this_layer_advertises_is_one_it_can_actually_resolve():
    """
    The list of schemes and the code that dispatches them are two things that must agree.

    ``SECRET_SCHEMES`` is the gate: a value is a reference only because its
    prefix is in that tuple. Adding one there without wiring up the branch
    behind it would turn every use of the new scheme into the unsupported
    error rather than a resolved secret, and the tuple is the part somebody
    edits first.
    """
    from opencloud_local_scan.secrets import SECRET_SCHEMES

    provider = SecretProvider()

    for scheme in SECRET_SCHEMES:
        with pytest.raises(SecretResolutionError) as raised:
            provider.resolve(scheme)
        # Empty remainder, not an unhandled scheme: the branch exists.
        assert "Empty secret reference" in str(raised.value)


def test_a_scheme_this_layer_does_not_know_is_a_plain_value(tmp_path):
    """
    The negative half, and a deliberate boundary rather than an oversight.

    Only the four listed prefixes mean 'go and fetch this'. Anything else
    that happens to contain '://' - a URL in a setting, a DSN, a password
    with punctuation in it - is the value itself, and treating it as a
    reference would break configurations that are entirely correct.
    """
    provider = SecretProvider(secrets_dir=str(tmp_path))

    assert provider.resolve("vault://secret/token") == "vault://secret/token"
    assert provider.resolve("redis://cache:6379/0") == "redis://cache:6379/0"


def test_a_value_is_only_a_reference_when_a_known_scheme_starts_it():
    """A password that contains '://' is a password, not a reference."""
    provider = SecretProvider()

    assert provider.is_reference("secret://token") is True
    assert provider.is_reference("exec://id") is True
    assert provider.is_reference("https://example.com/token") is False
    assert provider.is_reference("p@ss://word") is False
    assert provider.is_reference(42) is False


def test_a_command_that_fails_is_an_error_rather_than_an_empty_secret():
    """
    Taking a failed command's output would hand the caller an empty credential.

    ``check=True`` is what makes this an exception, and nothing else in the
    resolve path would notice the difference.
    """
    provider = SecretProvider(allow_exec=True)

    with pytest.raises(SecretResolutionError, match="failed"):
        provider.resolve("exec://false")

    with pytest.raises(SecretResolutionError, match="failed"):
        provider.resolve("exec://cos-no-such-command-exists")


def test_an_exec_reference_with_no_command_in_it_is_refused_before_anything_runs():
    """
    'exec://' followed by whitespace names no command, and never reaches one.

    It is rejected as an empty reference rather than as a failed command,
    which is worth pinning down: the remainder is stripped before the scheme
    is dispatched, so this never becomes an argv at all.
    """
    provider = SecretProvider(allow_exec=True)

    with pytest.raises(SecretResolutionError, match="Empty secret reference"):
        provider.resolve("exec://   ")


def test_a_command_is_run_without_a_shell():
    """
    A reference is configuration, and configuration is not always the operator's.

    Splitting with shlex and running the argv directly is what keeps a shell
    metacharacter in a reference from being a second command; if this ever
    goes through a shell, the file below gets created.
    """
    import tempfile
    from pathlib import Path

    marker = Path(tempfile.mkdtemp()) / "ran"
    provider = SecretProvider(allow_exec=True)

    assert provider.resolve(f"exec://echo safe; touch {marker}") == f"safe; touch {marker}"
    assert not marker.exists()


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
