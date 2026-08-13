"""
Tests for the COS_ environment variables and the config file as argparse defaults.

The plugin is normally invoked by a monitoring daemon, where flags are
awkward and environment variables (or a config file) are the natural place
for hosts, tokens and thresholds.
"""

import pytest

import check_opencloud_security as plugin


@pytest.fixture
def reload_plugin(monkeypatch):
    """
    Reload the plugin configuration so argparse defaults see the environment.

    Defaults are evaluated when the parser is built, which happens after
    main() has installed the merged configuration - this fixture does the
    same thing without running the whole check.
    """
    original = plugin._CONFIG

    def _reload():
        plugin._set_configuration(plugin._preparse_config([]))
        return plugin

    yield _reload
    plugin._set_configuration(original)


def test_host_can_come_from_the_environment(monkeypatch, reload_plugin):
    """COS_HOST removes the need for -H in the monitoring command."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")

    module = reload_plugin()
    args = module.build_arg_parser().parse_args([])

    assert args.host == "cloud.example.com"


def test_host_flag_beats_the_environment(monkeypatch, reload_plugin):
    """An explicit flag must always win."""
    monkeypatch.setenv("COS_HOST", "from-env.example.com")

    module = reload_plugin()
    args = module.build_arg_parser().parse_args(["-H", "from-flag.example.com"])

    assert args.host == "from-flag.example.com"


def test_host_is_required_without_the_environment(reload_plugin, capsys):
    """Without a target there is nothing to check."""
    module = reload_plugin()

    with pytest.raises(SystemExit):
        module.build_arg_parser().parse_args([])

    assert "host" in capsys.readouterr().err


def test_boolean_flags_are_read_from_the_environment(monkeypatch, reload_plugin):
    """Switches follow the same convention as the value options."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_CHECK_HARDENING", "true")
    monkeypatch.setenv("COS_INSECURE", "yes")
    monkeypatch.setenv("COS_UPDATE_WARNING", "1")
    monkeypatch.setenv("COS_NO_DEBUG_PORTS", "on")
    monkeypatch.setenv("COS_ALLOW_PRIVATE_WEBHOOKS", "true")

    module = reload_plugin()
    args = module.build_arg_parser().parse_args([])

    assert args.check_hardening is True
    assert args.insecure is True
    assert args.update_warning is True
    assert args.no_debug_ports is True
    assert args.allow_private_webhooks is True


@pytest.mark.parametrize("value", ["false", "no", "0", "off", ""])
def test_falsey_environment_values_stay_off(monkeypatch, reload_plugin, value):
    """"COS_DEBUG=false" must not enable debug mode."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_DEBUG", value)

    module = reload_plugin()

    assert module.build_arg_parser().parse_args([]).debug is False


def test_numeric_options_are_read_from_the_environment(monkeypatch, reload_plugin):
    """Thresholds and timeouts are the values most often tuned per site."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_WARNING", "4")
    monkeypatch.setenv("COS_CRITICAL", "2")
    monkeypatch.setenv("COS_TIMEOUT", "30")
    monkeypatch.setenv("COS_RETRIES", "5")
    monkeypatch.setenv("COS_BACKOFF_FACTOR", "1.5")

    module = reload_plugin()
    args = module.build_arg_parser().parse_args([])

    assert (args.warning, args.critical) == (4, 2)
    assert args.retries == 5
    assert args.backoff_factor == 1.5
    # --timeout has no argparse default, so that a more specific
    # 'scanner.timeout:' is not overruled; it is resolved in the context.
    assert module._build_context("cloud.example.com", args).timeout == 30


def test_invalid_numeric_environment_value_falls_back(monkeypatch, reload_plugin):
    """A typo in the environment must not crash the monitoring daemon."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_TIMEOUT", "soon")

    module = reload_plugin()
    args = module.build_arg_parser().parse_args([])

    assert module._build_context("cloud.example.com", args).timeout == 10


def test_webhook_headers_come_from_a_semicolon_list(monkeypatch, reload_plugin):
    """One variable has to carry what --webhook-header does repeatedly."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_WEBHOOK_HEADERS", "X-Token: abc; X-Other: def")

    module = reload_plugin()

    assert module._parse_webhook_headers(None) == (("X-Token", "abc"), ("X-Other", "def"))


def test_update_source_comes_from_the_environment(monkeypatch, reload_plugin):
    """The update source is a per-site decision (air-gapped or not)."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_UPDATE_SOURCE", "bundled")

    module = reload_plugin()
    args = module.build_arg_parser().parse_args([])

    assert args.update_source == "bundled"
    assert module._build_context("cloud.example.com", args).release_settings.mode == "bundled"


def test_token_can_come_from_a_file(monkeypatch, reload_plugin, tmp_path):
    """A '*_FILE' variable keeps the token out of the process environment."""
    secret = tmp_path / "token"
    secret.write_text("gh-token\n", encoding="utf-8")
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_RELEASES_TOKEN_FILE", str(secret))

    module = reload_plugin()
    args = module.build_arg_parser().parse_args([])

    assert module._build_context("cloud.example.com", args).release_settings.token == "gh-token"


def test_config_file_supplies_defaults(monkeypatch, reload_plugin, tmp_path):
    """A YAML file is the readable alternative to a wall of variables."""
    config = tmp_path / "config.yml"
    config.write_text(
        "host: cloud.example.com\n"
        "warning: 4\n"
        "check_hardening: true\n"
        "webhook:\n"
        "  allow_private_webhooks: true\n"
        "scanner:\n"
        "  timeout: 25\n"
        "releases:\n"
        "  mode: bundled\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COS_CONFIG_FILE", str(config))

    module = reload_plugin()
    args = module.build_arg_parser().parse_args([])

    assert args.host == "cloud.example.com"
    assert args.warning == 4
    assert args.check_hardening is True
    context = module._build_context("cloud.example.com", args)
    assert context.scanner_settings.timeout == 25
    assert context.release_settings.mode == "bundled"
    assert context.allow_private_webhooks is True


def test_environment_beats_the_config_file(monkeypatch, reload_plugin, tmp_path):
    """The layering order is file < environment < flags."""
    config = tmp_path / "config.yml"
    config.write_text("host: from-file.example.com\n", encoding="utf-8")
    monkeypatch.setenv("COS_CONFIG_FILE", str(config))
    monkeypatch.setenv("COS_HOST", "from-env.example.com")

    module = reload_plugin()

    assert module.build_arg_parser().parse_args([]).host == "from-env.example.com"


def test_flags_override_the_scanner_configuration(monkeypatch, reload_plugin):
    """--insecure and friends must beat whatever the config says."""
    monkeypatch.setenv("COS_HOST", "cloud.example.com")
    monkeypatch.setenv("COS_SCANNER_VERIFY_TLS", "true")

    module = reload_plugin()
    args = module.build_arg_parser().parse_args(["--insecure", "--no-extra-checks"])
    context = module._build_context("cloud.example.com", args)

    assert context.scanner_settings.verify_tls is False
    assert context.scanner_settings.extra_checks is False


def test_no_update_check_switches_the_release_lookup_off(reload_plugin):
    """The flag must reach the release settings, not just the context."""
    module = reload_plugin()
    args = module.build_arg_parser().parse_args(["-H", "cloud.example.com", "--no-update-check"])
    context = module._build_context("cloud.example.com", args)

    assert context.update_check is False
    assert context.release_settings.mode == "off"


def test_latest_version_implies_pinned_mode(reload_plugin):
    """Naming the expected release is enough; no extra flag needed."""
    module = reload_plugin()
    args = module.build_arg_parser().parse_args(
        ["-H", "cloud.example.com", "--latest-version", "7.4.0"]
    )
    context = module._build_context("cloud.example.com", args)

    assert context.release_settings.effective_mode() == "pinned"
    assert context.release_settings.latest_version == "7.4.0"


def test_port_and_scheme_flags_reach_the_scanner(reload_plugin):
    """OpenCloud's own proxy listens on 9200, so these matter in practice."""
    module = reload_plugin()
    args = module.build_arg_parser().parse_args(
        ["-H", "cloud.example.com", "--port", "9200", "--scheme", "http"]
    )
    context = module._build_context("cloud.example.com", args)

    assert context.scanner_settings.port == 9200
    assert context.scanner_settings.scheme == "http"


def test_broken_config_file_is_a_clean_unknown(monkeypatch, capsys):
    """A syntax error must produce a Nagios UNKNOWN, not a traceback."""
    monkeypatch.setenv("COS_CONFIG_FILE", "/nope/does-not-exist.yml")
    monkeypatch.setattr("sys.argv", ["check_opencloud_security"])

    with pytest.raises(SystemExit) as excinfo:
        plugin.main()

    assert excinfo.value.code == 3
    assert "UNKNOWN" in capsys.readouterr().out
