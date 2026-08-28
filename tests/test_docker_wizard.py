"""
The standalone Docker setup wizard in ``docker/setup-wizard.py``.

What these tests protect is the promise the script makes: that the compose
file it writes is a valid compose file, that every credential it generates
ends up in ``.env`` and nowhere else, and that it cannot quietly overwrite
either an existing deployment or the compose files that ship with the
project. Each of those failing is a deployment that either does not start or
leaks a token into something an operator commits.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest
import yaml

WIZARD_PATH = Path(__file__).resolve().parent.parent / "docker" / "setup-wizard.py"


def _load_wizard():
    """Import the script by path: it is standalone, not part of a package."""
    spec = importlib.util.spec_from_file_location("docker_setup_wizard", WIZARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wizard_module = _load_wizard()


def _run(tmp_path: Path, *extra: str) -> int:
    return wizard_module.main(["--output-dir", str(tmp_path), "--non-interactive", *extra])


def _compose(tmp_path: Path) -> dict:
    return yaml.safe_load((tmp_path / "docker-compose.yml").read_text(encoding="utf-8"))


def _env(tmp_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (tmp_path / ".env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


def test_the_wizard_writes_a_compose_file_docker_can_parse(tmp_path: Path) -> None:
    """A generated file that is not valid YAML is a deployment that never starts."""
    assert _run(tmp_path) == 0

    document = _compose(tmp_path)
    assert sorted(document["services"]) == ["arq_worker", "redis", "web_app"]
    assert document["services"]["arq_worker"]["command"] == ["python", "-m", "webapp.tasks"]
    assert document["services"]["web_app"]["ports"] == ["127.0.0.1:8811:8811"]


def test_a_generated_credential_is_written_to_the_env_file_and_never_to_the_compose_file(
    tmp_path: Path,
) -> None:
    """The split is the point of the wizard: a compose file may be committed."""
    assert _run(tmp_path) == 0

    values = _env(tmp_path)
    token = values["COS_WEB_PURGE_TOKEN"]
    assert len(token) == 64

    compose_text = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    assert token not in compose_text
    assert values["COS_WEB_PURGE_SIGNING_KEY"] not in compose_text
    # The compose file refers to the name rather than carrying the value.
    assert "${COS_WEB_PURGE_TOKEN:-}" in compose_text


def test_the_env_file_is_readable_by_its_owner_only(tmp_path: Path) -> None:
    """A secret that was world-readable for a moment was world-readable."""
    assert _run(tmp_path) == 0

    mode = stat.S_IMODE((tmp_path / ".env").stat().st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR
    assert not mode & (stat.S_IRGRP | stat.S_IROTH)


def test_the_public_preset_refuses_private_targets_and_runs_no_port_scan(
    tmp_path: Path,
) -> None:
    """The default deployment is one a stranger may use, so it must reach no further."""
    assert _run(tmp_path) == 0

    worker = _compose(tmp_path)["services"]["arq_worker"]["environment"]
    assert worker["COS_WEB_ALLOW_PRIVATE_TARGETS"] == "false"
    assert worker["COS_WEB_CHECK_DEBUG_PORTS"] == "false"

    web = _compose(tmp_path)["services"]["web_app"]["environment"]
    assert web["COS_WEB_AUDIT_LOG"] == "false"
    assert web["COS_WEB_ALLOW_INDEXING"] == "true"


def test_the_private_preset_scans_its_own_network_and_stays_out_of_search_engines(
    tmp_path: Path,
) -> None:
    """The two presets have to actually differ, or choosing one means nothing."""
    assert _run(tmp_path, "--preset", "private") == 0

    document = _compose(tmp_path)
    worker = document["services"]["arq_worker"]["environment"]
    web = document["services"]["web_app"]["environment"]

    assert worker["COS_WEB_ALLOW_PRIVATE_TARGETS"] == "true"
    assert worker["COS_WEB_CHECK_DEBUG_PORTS"] == "true"
    assert web["COS_WEB_ALLOW_INDEXING"] == "false"
    assert web["COS_WEB_AUDIT_LOG"] == "true"
    assert web["COS_WEB_AUDIT_LOG_TARGETS"] == "true"


def test_an_audit_salt_is_generated_only_when_the_audit_log_is_on(tmp_path: Path) -> None:
    """An unused salt in .env invites somebody to switch the log on without one."""
    assert _run(tmp_path) == 0
    assert "COS_WEB_AUDIT_SALT" not in _env(tmp_path)

    assert _run(tmp_path, "--preset", "private", "--force") == 0
    assert len(_env(tmp_path)["COS_WEB_AUDIT_SALT"]) == 32


def test_the_wizard_refuses_to_overwrite_a_compose_file_that_ships_with_the_project(
    tmp_path: Path,
) -> None:
    """The next git pull would take a hand-made deployment with it."""
    shipped = wizard_module.SCRIPT_DIR / "docker-compose.yml"
    before = shipped.read_bytes()

    exit_code = wizard_module.main(
        [
            "--output-dir",
            str(wizard_module.SCRIPT_DIR),
            "--non-interactive",
            "--force",
        ]
    )

    assert exit_code == 2
    assert shipped.read_bytes() == before


def test_an_existing_file_is_kept_when_the_operator_declines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overwriting a live deployment's secrets has to take a deliberate yes."""
    (tmp_path / "docker-compose.yml").write_text("# mine\n", encoding="utf-8")
    monkeypatch.setattr(wizard_module.Wizard, "ask", lambda self, question: None)
    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: "no")

    exit_code = wizard_module.main(["--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert (tmp_path / "docker-compose.yml").read_text(encoding="utf-8") == "# mine\n"
    assert not (tmp_path / ".env").exists()


def test_force_overwrites_without_asking(tmp_path: Path) -> None:
    """An unattended reinstall must not hang on a question nobody can answer."""
    (tmp_path / "docker-compose.yml").write_text("# mine\n", encoding="utf-8")

    assert _run(tmp_path, "--force") == 0
    assert "services:" in (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")


def test_the_published_image_replaces_the_build_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answering 'dockerhub' has to remove the build context, not sit beside it."""
    answers = iter(["dockerhub"])

    def read(self, prompt: str) -> str:
        return next(answers, "")

    monkeypatch.setattr(wizard_module.Wizard, "_read", read)

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    web = _compose(tmp_path)["services"]["web_app"]
    assert web["image"] == wizard_module.DOCKERHUB_IMAGE
    assert "build" not in web


def test_the_local_build_points_at_the_repository_root(tmp_path: Path) -> None:
    """Both images need webapp/ and frontend/, which live above docker/."""
    assert _run(tmp_path) == 0

    build = _compose(tmp_path)["services"]["web_app"]["build"]
    assert build["dockerfile"] == "docker/Dockerfile.web"
    context = (tmp_path / build["context"]).resolve()
    assert (context / "webapp").is_dir()
    assert (context / "frontend").is_dir()


def test_an_answer_typed_at_a_prompt_reaches_the_generated_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wizard whose answers are ignored is a slower way of taking defaults."""
    typed = {
        "Port on the host": "9443",
        "Address to publish the port on": "0.0.0.0",  # nosec B104
        "Public address of this service": "https://scan.example.com",
        "Scans running at once": "2",
    }

    def read(self, prompt: str) -> str:
        return ""

    def ask(self, question):
        for text, answer in typed.items():
            if question.prompt == text:
                value = int(answer) if question.kind == "int" else answer
                setattr(self.setup, question.key, value)
                return

    monkeypatch.setattr(wizard_module.Wizard, "_read", read)
    monkeypatch.setattr(wizard_module.Wizard, "ask", ask)

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    document = _compose(tmp_path)
    assert document["services"]["web_app"]["ports"] == ["0.0.0.0:9443:8811"]
    assert (
        document["services"]["web_app"]["environment"]["COS_WEB_PUBLIC_BASE_URL"]
        == "https://scan.example.com"
    )
    assert document["services"]["arq_worker"]["environment"]["COS_WEB_MAX_WORKERS"] == "2"


def test_a_question_that_no_longer_applies_is_not_asked(tmp_path: Path) -> None:
    """Asking for an issuer with the sign-in off is a quiz rather than a setup."""
    setup = wizard_module.Setup(enable_mcp=False)

    assert not wizard_module._relevant("mcp_auth_issuer", setup)
    assert not wizard_module._relevant("deploy_authentik", setup)
    assert not wizard_module._relevant("authentik_slug", setup)
    assert not wizard_module._relevant("image_ref", setup)
    assert wizard_module._relevant("build_context", setup)

    setup.enable_mcp = True
    setup.mcp_auth_enabled = True
    # A sign-in on its own is checked against a provider somebody else runs.
    assert wizard_module._relevant("deploy_authentik", setup)
    assert wizard_module._relevant("mcp_auth_issuer", setup)
    assert not wizard_module._relevant("authentik_slug", setup)

    # Bringing one along answers the issuer itself, so the question goes away.
    setup.deploy_authentik = True
    assert wizard_module._relevant("authentik_slug", setup)
    assert not wizard_module._relevant("mcp_auth_issuer", setup)

    setup.enable_mcp = False
    assert not wizard_module._relevant("mcp_auth_issuer", setup)
    assert not wizard_module._relevant("deploy_authentik", setup)
    assert not wizard_module._relevant("authentik_slug", setup)


def test_encryption_writes_a_key_the_worker_and_the_web_process_share(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker writes the document and the web process reads it back."""
    def ask(self, question):
        if question.key == "encrypt_results":
            self.setup.encrypt_results = True

    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: "")
    monkeypatch.setattr(wizard_module.Wizard, "ask", ask)

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    document = _compose(tmp_path)
    for service in ("web_app", "arq_worker"):
        environment = document["services"][service]["environment"]
        assert environment["COS_WEB_ENCRYPT_RESULTS"] == "true"
        assert environment["COS_WEB_ENCRYPTION_KEY_1"] == "${COS_WEB_ENCRYPTION_KEY_1:-}"

    key = _env(tmp_path)["COS_WEB_ENCRYPTION_KEY_1"]
    assert len(key) == 64
    assert key not in (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")


def test_a_sign_in_without_an_issuer_is_reported_before_the_stack_is_started(
    tmp_path: Path,
) -> None:
    """The service refuses to start on this; saying so now costs less than a restart."""
    setup = wizard_module.Setup(mcp_auth_enabled=True)

    warnings = wizard_module.check_consistency(setup)

    assert any("issuer" in warning for warning in warnings)
    assert not wizard_module.check_consistency(
        wizard_module.Setup(
            mcp_auth_enabled=True,
            mcp_auth_issuer="https://sso.example.com/application/o/scan/",
            mcp_auth_audience="opencloud-scanner",
            public_base_url="https://scan.example.com",
        )
    )


def test_a_sign_in_without_an_audience_is_reported_the_same_way(
    tmp_path: Path,
) -> None:
    """
    An unchecked audience is the quiet half of a misconfigured sign-in: the
    stack comes up, tokens are accepted, and every one the provider ever
    minted for another application is accepted too. The service refuses to
    start on it, and an empty answer here is rejected rather than accepted.
    """
    setup = wizard_module.Setup(
        mcp_auth_enabled=True,
        mcp_auth_issuer="https://sso.example.com/application/o/scan/",
        public_base_url="https://scan.example.com",
    )

    assert any(
        "audience" in warning for warning in wizard_module.check_consistency(setup)
    )
    assert wizard_module._audience("") is not None
    # The negative half: a provisioned Authentik answers the audience itself,
    # so it must not be nagged about one, and a real answer passes.
    assert wizard_module._audience("opencloud-scanner") is None
    assert not any(
        "audience" in warning
        for warning in wizard_module.check_consistency(
            wizard_module.Setup(
                mcp_auth_enabled=True, deploy_authentik=True,
                public_base_url="https://scan.example.com",
            )
        )
    )


def test_a_setup_with_nothing_to_hide_still_gets_an_env_file(tmp_path: Path) -> None:
    """Adding a secret later should be an edit, not a discovery."""
    setup = wizard_module.Setup()

    content = wizard_module.render_env_file(setup)

    assert "COS_WEB_PURGE_TOKEN" in content
    assert not any(
        line.startswith("COS_WEB_") for line in content.splitlines() if line.strip()
    )


def test_the_wizard_names_no_real_host(tmp_path: Path) -> None:
    """Placeholders only, in the questions as well as in the generated files."""
    import re

    source = WIZARD_PATH.read_text(encoding="utf-8")
    allowed = {
        "127.0.0.1",
        "0.0.0.0",
        "localhost",
        "authentik-server",
        "github.com",
        "sso.example.com",
        "scan.example.com",
    }

    hosts = set(re.findall(r"https?://([A-Za-z0-9][A-Za-z0-9._-]*)", source))

    assert hosts, "the check itself has to find something, or it protects nothing"
    for host in hosts:
        assert host in allowed or host.endswith("example.com"), host


def test_the_script_runs_without_the_projects_dependencies() -> None:
    """It is meant for a host that has Docker and nothing else installed yet."""
    source = WIZARD_PATH.read_text(encoding="utf-8")

    for forbidden in ("import yaml", "import requests", "from webapp", "opencloud_local_scan"):
        assert forbidden not in source

    assert os.access(WIZARD_PATH, os.X_OK)


def test_a_sign_in_alone_adds_no_identity_provider_to_the_stack(tmp_path: Path) -> None:
    """Most estates that want a sign-in already have somewhere to sign in to."""
    assert _run(tmp_path, "--sign-in") == 0

    document = _compose(tmp_path)

    assert not [name for name in document["services"] if name.startswith("authentik")]
    assert "volumes" not in document
    assert not (tmp_path / "authentik").exists()
    assert not [name for name in _env(tmp_path) if name.startswith("AUTHENTIK")]

    # The sign-in is still on, and the settings it needs are asked for.
    web = document["services"]["web_app"]["environment"]
    assert web["COS_WEB_MCP_AUTH_ENABLED"] == "true"
    assert web["COS_WEB_MCP_AUTH_ISSUER"] == "${COS_WEB_MCP_AUTH_ISSUER:-}"


def test_asking_for_authentik_provisions_it_rather_than_a_form_to_fill_in(
    tmp_path: Path,
) -> None:
    """An operator who asks for a provider should get one, not OAuth homework."""
    assert _run(tmp_path, "--with-authentik") == 0

    document = _compose(tmp_path)
    services = document["services"]

    assert {"authentik_postgresql", "authentik_server", "authentik_worker"} <= set(services)
    assert {"authentik_database", "authentik_media", "authentik_certs"} <= set(
        document["volumes"]
    )

    web = services["web_app"]["environment"]
    # Derived from the answers, never asked for and never left blank - and
    # written whether or not the guard is on, so switching it on is one line.
    assert web["COS_WEB_MCP_AUTH_ISSUER"].endswith("/application/o/opencloud-scanner/")
    assert "${" not in web["COS_WEB_MCP_AUTH_ISSUER"]
    assert web["COS_WEB_MCP_AUTH_AUDIENCE"] == "${AUTHENTIK_CLIENT_ID:-}"


def test_provisioning_a_provider_does_not_close_the_endpoint_by_itself(
    tmp_path: Path,
) -> None:
    """A flag that quietly required a token would shut out an agent that worked yesterday."""
    assert _run(tmp_path, "--with-authentik") == 0

    web = _compose(tmp_path)["services"]["web_app"]["environment"]

    assert web["COS_WEB_MCP_AUTH_ENABLED"] == "false"
    assert web["COS_WEB_ENABLE_MCP"] == "true"

    # Asking for both is what turns it on, and the two combine rather than
    # cancelling: the provider is still provisioned.
    both = tmp_path / "both"
    assert _run(both, "--with-authentik", "--sign-in") == 0
    document = _compose(both)
    assert document["services"]["web_app"]["environment"]["COS_WEB_MCP_AUTH_ENABLED"] == "true"
    assert "authentik_server" in document["services"]

    warnings = wizard_module.check_consistency(
        wizard_module.Setup(enable_mcp=True, deploy_authentik=True)
    )
    assert any("guards nothing" in warning for warning in warnings)


def test_the_container_reaches_the_keys_over_the_network_it_shares(tmp_path: Path) -> None:
    """The published issuer is unreachable from inside; a wrong JWKS URL fails every token."""
    assert _run(tmp_path, "--with-authentik") == 0

    document = _compose(tmp_path)
    jwks = document["services"]["web_app"]["environment"]["COS_WEB_MCP_AUTH_JWKS_URL"]

    assert jwks.startswith("http://authentik-server:9000/")
    assert jwks.endswith("/jwks/")
    # The hyphen is load-bearing: authentik_server as a Host header is a 404.
    aliases = document["services"]["authentik_server"]["networks"]["default"]["aliases"]
    assert "authentik-server" in aliases


def test_the_identity_providers_own_credentials_live_only_in_the_env_file(
    tmp_path: Path,
) -> None:
    """A signing key or a client secret in the compose file is a secret in git."""
    assert _run(tmp_path, "--with-authentik") == 0

    values = _env(tmp_path)
    generated = ("AUTHENTIK_SECRET_KEY", "AUTHENTIK_PG_PASS", "AUTHENTIK_CLIENT_SECRET")
    compose_text = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")

    for name in generated:
        assert len(values[name]) >= 32
        assert values[name] not in compose_text

    # And nothing of Authentik's is written when no sign-in was asked for.
    plain = tmp_path / "plain"
    assert _run(plain) == 0
    assert not [name for name in _env(plain) if name.startswith("AUTHENTIK")]


def test_the_blueprint_travels_beside_the_compose_file_that_mounts_it(
    tmp_path: Path,
) -> None:
    """The stack mounts ./authentik/blueprints; without it there is no OAuth provider."""
    assert _run(tmp_path, "--with-authentik") == 0

    blueprint = tmp_path / "authentik" / "blueprints" / "opencloud-scanner.yaml"

    assert blueprint.is_file()
    assert "opencloud-scanner" in blueprint.read_text(encoding="utf-8")

    mounts = _compose(tmp_path)["services"]["authentik_server"]["volumes"]
    assert any(mount.startswith("./authentik/blueprints:") for mount in mounts)

    assert _run(tmp_path / "plain") == 0
    assert not (tmp_path / "plain" / "authentik").exists()


def test_a_mail_server_is_configured_without_its_password_reaching_the_compose_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without mail nobody recovers a lost password; with a leaked one, anybody does."""
    monkeypatch.setenv("AUTHENTIK_EMAIL_PASSWORD", "s3cret-in-the-environment")

    assert (
        _run(
            tmp_path,
            "--with-authentik",
            "--smtp-host",
            "smtp.example.com",
            "--smtp-username",
            "authentik@example.com",
            "--smtp-from",
            "authentik@example.com",
        )
        == 0
    )

    worker = _compose(tmp_path)["services"]["authentik_worker"]["environment"]
    assert worker["AUTHENTIK_EMAIL__HOST"] == "smtp.example.com"
    assert worker["AUTHENTIK_EMAIL__FROM"] == "authentik@example.com"
    assert worker["AUTHENTIK_EMAIL__PASSWORD"] == "${AUTHENTIK_EMAIL_PASSWORD:-}"

    compose_text = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    assert "s3cret-in-the-environment" not in compose_text
    assert _env(tmp_path)["AUTHENTIK_EMAIL_PASSWORD"] == "s3cret-in-the-environment"

    assert "--smtp-password" not in WIZARD_PATH.read_text(encoding="utf-8")


def test_the_two_ways_of_encrypting_a_mail_session_stay_mutually_exclusive(
    tmp_path: Path,
) -> None:
    """Authentik reads USE_TLS and USE_SSL separately; both true is a broken session."""
    starttls = wizard_module.Setup(
        mcp_auth_enabled=True, smtp_host="smtp.example.com", smtp_security="starttls"
    )
    implicit = wizard_module.Setup(
        mcp_auth_enabled=True, smtp_host="smtp.example.com", smtp_security="ssl"
    )
    plain = wizard_module.Setup(
        mcp_auth_enabled=True, smtp_host="smtp.example.com", smtp_security="none"
    )

    def flags(setup) -> tuple[str, str]:
        rendered = {
            entry.name: entry.value.strip('"')
            for entry in wizard_module._mail_environment(setup)
        }
        return rendered["AUTHENTIK_EMAIL__USE_TLS"], rendered["AUTHENTIK_EMAIL__USE_SSL"]

    assert flags(starttls) == ("true", "false")
    assert flags(implicit) == ("false", "true")
    assert flags(plain) == ("false", "false")

    # No mail server leaves an empty host and an explanation, not half a session.
    without = wizard_module._mail_environment(wizard_module.Setup(mcp_auth_enabled=True))
    assert [entry.name for entry in without] == ["AUTHENTIK_EMAIL__HOST"]
    assert without[0].value == '""'


def test_a_sign_in_without_a_way_to_send_mail_is_pointed_out(tmp_path: Path) -> None:
    """A locked-out administrator with no SMTP server has no way back in."""
    setup = wizard_module.Setup(enable_mcp=True, mcp_auth_enabled=True, deploy_authentik=True)

    warnings = wizard_module.check_consistency(setup)

    assert any("mail" in warning.lower() for warning in warnings)

    # A sign-in against somebody else's provider is not this stack's problem.
    elsewhere = wizard_module.Setup(enable_mcp=True, mcp_auth_enabled=True)
    assert not any("mail" in w.lower() for w in wizard_module.check_consistency(elsewhere))

    setup.smtp_host = "smtp.example.com"
    setup.smtp_from = "authentik@example.com"
    assert not any("mail" in warning.lower() for warning in wizard_module.check_consistency(setup))


def test_the_generated_redis_asks_for_a_password_that_only_the_env_file_holds() -> None:
    """
    Redis holds every live scan and every result still inside its TTL.

    Left open it answers whoever reaches it, which turns one stray container
    on the same network into a readable copy of everybody's scans. The
    password is generated rather than asked for, and it reaches the compose
    file the same way every other secret does: by reference.
    """
    setup = wizard_module.Setup()
    wizard_module._finalise(setup)

    compose = wizard_module.render_compose_file(setup, "compose.yml")
    env_file = wizard_module.render_env_file(setup)

    assert setup.redis_password
    assert '--requirepass "${COS_REDIS_PASSWORD:-}"' in compose
    assert 'COS_WEB_REDIS_URL: "redis://:${COS_REDIS_PASSWORD:-}@redis:6379/0"' in compose
    # The value itself is in .env and nowhere else.
    assert f"COS_REDIS_PASSWORD={setup.redis_password}" in env_file
    assert setup.redis_password not in compose

    # A second deployment does not get the first one's password.
    other = wizard_module.Setup()
    wizard_module._finalise(other)
    assert other.redis_password != setup.redis_password


def test_the_generated_redis_sits_on_a_network_with_no_route_off_the_host() -> None:
    """
    The password and the network are two halves of the same argument.

    A scan is an outbound request and the web service is published, so those
    containers keep the default network; Redis has no reason to reach anything
    or be reached, and an `internal` network is what says so.
    """
    setup = wizard_module.Setup()
    wizard_module._finalise(setup)

    compose = wizard_module.render_compose_file(setup, "compose.yml")

    redis_block = compose.split("\n  redis:\n", 1)[1].split("\nnetworks:", 1)[0]
    assert "scanner_internal" in redis_block
    assert "ports:" not in redis_block
    assert "\n  scanner_internal:\n    internal: true\n" in compose
    # The application containers need both, or a published port and an
    # outbound scan would stop working.
    assert compose.count("      - default\n      - scanner_internal\n") == 2


def test_asking_for_automatic_updates_adds_watchtower_scoped_to_this_stack(
    tmp_path: Path,
) -> None:
    """Watchtower without the label scope would update every container on the host."""
    assert _run(tmp_path, "--auto-updates") == 0

    document = _compose(tmp_path)
    watchtower = document["services"]["watchtower"]
    assert watchtower["image"] == wizard_module.WATCHTOWER_IMAGE
    assert watchtower["environment"]["WATCHTOWER_LABEL_ENABLE"] == "true"
    mount = watchtower["volumes"][0]
    assert mount.endswith(":/var/run/docker.sock")
    assert mount.startswith("/")

    # Every other service of the stack opts in, watchtower itself included or
    # not - and nothing outside the stack carries the label it looks for.
    for name, service in document["services"].items():
        if name == "watchtower":
            continue
        assert service["labels"]["com.centurylinklabs.watchtower.enable"] == "true", name

    # The identity provider's containers are part of the stack, so they are
    # updated with it rather than left behind on an old image.
    signed = tmp_path / "signed"
    assert _run(signed, "--auto-updates", "--with-authentik") == 0
    for name, service in _compose(signed)["services"].items():
        if name == "watchtower":
            continue
        assert service["labels"]["com.centurylinklabs.watchtower.enable"] == "true", name


def test_a_deployment_without_automatic_updates_gets_no_watchtower(tmp_path: Path) -> None:
    """The daemon socket is the host; no container gets it that did not ask for it."""
    assert _run(tmp_path) == 0

    document = _compose(tmp_path)
    assert "watchtower" not in document["services"]
    for service in document["services"].values():
        assert "labels" not in service


def test_the_rootless_socket_is_detected_for_the_user_running_the_wizard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rootless Docker serves its socket under the user's runtime directory."""
    runtime = tmp_path / "run"
    runtime.mkdir()
    (runtime / "docker.sock").touch()

    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(os, "getuid", lambda: 1000)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    assert wizard_module.detect_docker_socket() == str(runtime / "docker.sock")

    # DOCKER_HOST is the socket every other Docker command here already uses.
    monkeypatch.setenv("DOCKER_HOST", "unix:///elsewhere/docker.sock")
    assert wizard_module.detect_docker_socket() == "/elsewhere/docker.sock"


def test_the_socket_question_only_applies_when_updates_do() -> None:
    """Asking for a socket with no Watchtower to use it is a quiz, not a setup."""
    assert not wizard_module._relevant("watchtower_socket", wizard_module.Setup())
    assert wizard_module._relevant(
        "watchtower_socket", wizard_module.Setup(auto_updates=True)
    )


def test_automatic_updates_with_a_local_build_are_pointed_out() -> None:
    """Watchtower pulls; it cannot rebuild an image the stack builds itself."""
    warnings = wizard_module.check_consistency(wizard_module.Setup(auto_updates=True))
    assert any("build" in warning.lower() for warning in warnings)

    pulled = wizard_module.Setup(auto_updates=True, image_source="dockerhub")
    assert not any("build" in w.lower() for w in wizard_module.check_consistency(pulled))
