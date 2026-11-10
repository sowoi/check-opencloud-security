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
import io
import itertools
import json
import os
import stat
import subprocess  # nosec B404 - runs the command the wizard prints
import sys
import uuid
from pathlib import Path
from typing import Any

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


# The real ones, before the fixture below stands them in for every test.
REAL_CHOOSE_MODE = wizard_module.Wizard.choose_mode
REAL_CHECK_HOST = wizard_module.check_host
REAL_OFFER_TO_START = wizard_module.offer_to_start


@pytest.fixture(autouse=True)
def _the_host_stays_out_of_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the machine running the tests out of the wizard's behaviour.

    A full walk is what almost every test here drives, so the mode question
    answers "full"; the checks against Docker, the port and the certificates
    say nothing; and nothing is started. The tests for those three undo this
    for themselves.
    """
    monkeypatch.setattr(wizard_module.Wizard, "choose_mode", lambda self, **_: "full")
    monkeypatch.setattr(wizard_module, "check_host", lambda setup: [])
    monkeypatch.setattr(wizard_module, "offer_to_start", lambda *args, **kwargs: None)


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


def test_existing_env_permissions_are_restricted_before_writing(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# previous configuration\n")
    path.chmod(0o644)
    original = os.fdopen
    checked = []

    class Writer:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def write(self, content):
            checked.append(stat.S_IMODE(os.fstat(self.fileno()).st_mode))
            assert checked[-1] == 0o600
            return self.handle.write(content)

    def checked_writer(descriptor, *args, **kwargs):
        return Writer(original(descriptor, *args, **kwargs))

    monkeypatch.setattr(wizard_module.os, "fdopen", checked_writer)
    assert _run(tmp_path, "--force") == 0
    assert checked


def test_the_public_preset_refuses_private_targets_and_runs_no_port_scan(
    tmp_path: Path,
) -> None:
    """The default deployment is one a stranger may use, so it must reach no further."""
    assert _run(tmp_path) == 0

    worker = _compose(tmp_path)["services"]["arq_worker"]["environment"]
    assert worker["COS_WEB_ALLOW_PRIVATE_TARGETS"] == "false"
    assert worker["COS_WEB_CHECK_DEBUG_PORTS"] == "false"
    # Docker's default network has no IPv6 route unless both the host and
    # this stack were set up for it, which most installs are not: answering
    # yes without checking would trade one wrong answer for another.
    assert worker["COS_WEB_IPV6_ENABLED"] == "false"

    web = _compose(tmp_path)["services"]["web_app"]["environment"]
    assert web["COS_WEB_AUDIT_LOG"] == "false"
    assert web["COS_WEB_ALLOW_INDEXING"] == "true"


def test_ipv6_connectivity_is_declared_rather_than_assumed(tmp_path: Path) -> None:
    """An operator who has confirmed IPv6 works can turn the parity check back on."""
    setup = wizard_module.Setup(ipv6_enabled=True)
    compose = wizard_module.render_compose_file(setup, "compose.yml")

    document = yaml.safe_load(compose)
    worker = document["services"]["arq_worker"]["environment"]
    assert worker["COS_WEB_IPV6_ENABLED"] == "true"


def test_confirming_ipv6_also_turns_it_on_for_the_networks_that_need_it(
    tmp_path: Path,
) -> None:
    """The env var alone is not enough: Compose needs enable_ipv6 on each network.

    Without it, an operator's confirmed IPv6 connectivity still would not
    reach a container, because Compose does not turn IPv6 on for a network
    just because the daemon supports it.
    """
    off = wizard_module.render_compose_file(wizard_module.Setup(ipv6_enabled=False), "compose.yml")
    on = wizard_module.render_compose_file(wizard_module.Setup(ipv6_enabled=True), "compose.yml")

    assert "enable_ipv6" not in off

    document = yaml.safe_load(on)
    networks = document["networks"]
    assert networks["default"]["enable_ipv6"] is True
    assert networks["scanner_internal"]["internal"] is True
    assert networks["scanner_internal"]["enable_ipv6"] is True


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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The next git pull would take a hand-made deployment with it."""
    shipped = wizard_module.SCRIPT_DIR / "docker-compose.yml"
    before = shipped.read_bytes()

    exit_code = wizard_module.main(
        ["--output-dir", str(wizard_module.SCRIPT_DIR), "--non-interactive"]
    )

    assert exit_code == 2
    assert shipped.read_bytes() == before
    # And it says how to do it anyway, rather than only that it will not.
    assert "--force" in capsys.readouterr().err


def test_force_replaces_a_shipped_compose_file_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    Reconfiguring the stack a checkout already runs should not mean moving it.

    Somebody who started with `docker compose up` in docker/ has a live
    deployment there; --force replaces its compose file where it is, and says
    on stderr - which an unattended run still shows - that the checkout now
    carries a modified tracked file.
    """
    checkout = tmp_path / "docker"
    checkout.mkdir()
    (checkout / "docker-compose.yml").write_text("# shipped\n", encoding="utf-8")
    monkeypatch.setattr(wizard_module, "SCRIPT_DIR", checkout.resolve())

    assert _run(checkout) == 2
    assert (checkout / "docker-compose.yml").read_text(encoding="utf-8") == "# shipped\n"
    capsys.readouterr()

    assert _run(checkout, "--force") == 0
    assert "services:" in (checkout / "docker-compose.yml").read_text(encoding="utf-8")
    assert (checkout / ".env").is_file()
    assert "git checkout -- docker/docker-compose.yml" in capsys.readouterr().err

    # A file that does not ship there is no reason to mention the checkout.
    elsewhere = tmp_path / "elsewhere"
    assert _run(elsewhere, "--force") == 0
    assert "ships with the project" not in capsys.readouterr().err


def test_an_existing_file_is_kept_when_the_operator_declines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overwriting a live deployment's secrets has to take a deliberate yes."""
    (tmp_path / "docker-compose.yml").write_text("# mine\n", encoding="utf-8")
    monkeypatch.setattr(wizard_module.Wizard, "ask", lambda self, question, **_: None)
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


def test_the_published_image_is_the_default_and_carries_no_build_section(
    tmp_path: Path,
) -> None:
    """
    The wizard is one file meant for a host with nothing but Docker on it.

    A build needs a checkout such a host does not have, so the default pulls
    the published image - and the build context is not left beside it.
    """
    assert wizard_module.Setup().image_source == "dockerhub"
    assert _run(tmp_path) == 0

    web = _compose(tmp_path)["services"]["web_app"]
    assert web["image"] == wizard_module.DOCKERHUB_IMAGE
    assert "build" not in web

    # And a checkout can still ask for its own code without being asked.
    local = tmp_path / "local"
    assert _run(local, "--image-source", "build") == 0
    assert "build" in _compose(local)["services"]["web_app"]


def test_the_local_build_points_at_the_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both images need webapp/ and frontend/, which live above docker/."""
    answers = iter(["build"])
    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: next(answers, ""))
    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    web = _compose(tmp_path)["services"]["web_app"]
    assert web.get("image") != wizard_module.DOCKERHUB_IMAGE
    build = web["build"]
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

    def ask(self, question, **_):
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
    assert wizard_module._relevant("image_ref", setup)
    assert not wizard_module._relevant("build_context", setup)
    setup.image_source = "build"
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
    def ask(self, question, **_):
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

    # Without escapes: the embedded blueprints carry redirect URIs as regular
    # expressions, and `127\.0\.0\.1` is still the loopback address.
    source = WIZARD_PATH.read_text(encoding="utf-8").replace("\\", "")
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


def test_a_wizard_downloaded_on_its_own_still_writes_every_blueprint(
    tmp_path: Path,
) -> None:
    """The README says to curl the one file; the blueprints must not need a checkout."""
    download = tmp_path / "download"
    download.mkdir()
    lone_wizard = download / "setup-wizard.py"
    lone_wizard.write_bytes(WIZARD_PATH.read_bytes())
    assert not (tmp_path / "authentik").exists()

    spec = importlib.util.spec_from_file_location("lone_setup_wizard", lone_wizard)
    assert spec and spec.loader
    lone = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = lone
    try:
        spec.loader.exec_module(lone)
        setup = lone.Setup(
            enable_mcp=True,
            mcp_auth_enabled=True,
            admin_enabled=True,
            admin_users="okko",
            deploy_authentik=True,
            public_base_url="https://scan.example.com",
        )
        lone._generate_unattended(setup)
        lone._finalise(setup)
        output = tmp_path / "deployment"
        written = lone.write_files(
            setup, output / "docker-compose.yml", output / ".env"
        )
    finally:
        del sys.modules[spec.name]

    repository_blueprints = WIZARD_PATH.parent.parent / "authentik" / "blueprints"
    blueprints = output / "authentik" / "blueprints"
    names = sorted(path.name for path in blueprints.iterdir())
    assert names == [
        "opencloud-admin.yaml",
        "opencloud-enrollment.yaml",
        "opencloud-mfa.yaml",
        "opencloud-scanner.yaml",
    ]
    for name in names:
        assert (blueprints / name).read_text(encoding="utf-8") == (
            repository_blueprints / name
        ).read_text(encoding="utf-8")
        assert any(item.endswith(name) for item in written)
    # Nothing was read from, or written to, where a checkout would have been.
    assert not (tmp_path / "authentik").exists()


def test_the_embedded_blueprints_are_the_ones_in_the_repository() -> None:
    """A blueprint edited without re-embedding would ship the old one to every download."""
    spec = importlib.util.spec_from_file_location(
        "embed_wizard_blueprints",
        WIZARD_PATH.parent.parent / "scripts" / "embed_wizard_blueprints.py",
    )
    assert spec and spec.loader
    embed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(embed)

    assert embed.is_current(), "run python scripts/embed_wizard_blueprints.py"

    # And the check does notice a block that has fallen behind: an edit inside
    # it is what regenerating puts right, and nothing outside it is touched.
    source = WIZARD_PATH.read_text(encoding="utf-8")
    block_start = source.index(embed.START_MARKER)
    stale = source[:block_start] + source[block_start:].replace(
        "authentik_", "stale_", 1
    )
    assert stale != source
    assert embed.render_wizard(stale) == source
    assert set(wizard_module.EMBEDDED_BLUEPRINTS) == set(embed.BLUEPRINT_NAMES)


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
    setup.smtp_username = "authentik@example.com"
    setup.smtp_password = "an-app-password"  # nosec B105 - a placeholder, not a secret
    assert not any("mail" in warning.lower() for warning in wizard_module.check_consistency(setup))

    # Half a credential is its own warning: authentik reads an empty username
    # as "do not authenticate", so a server that wanted one refuses every
    # message and the first thing anybody notices is a password reset that
    # never arrives.
    half = wizard_module.Setup(
        enable_mcp=True,
        mcp_auth_enabled=True,
        deploy_authentik=True,
        smtp_host="smtp.example.com",
        smtp_from="authentik@example.com",
    )
    assert any(
        "username" in warning for warning in wizard_module.check_consistency(half)
    )
    half.smtp_auth = False
    assert not any(
        "username" in warning for warning in wizard_module.check_consistency(half)
    )


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
    # Not the archived image, which speaks API 1.25 and panics on Docker 29 -
    # and no pinned API version, which the fork negotiates instead.
    assert not watchtower["image"].startswith("containrrr/")
    assert "DOCKER_API_VERSION" not in watchtower["environment"]
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
    warnings = wizard_module.check_consistency(
        wizard_module.Setup(auto_updates=True, image_source="build")
    )
    assert any("build" in warning.lower() for warning in warnings)

    pulled = wizard_module.Setup(auto_updates=True, image_source="dockerhub")
    assert not any("build" in w.lower() for w in wizard_module.check_consistency(pulled))


# --- what a deployment keeps ------------------------------------------------
def test_by_default_the_stack_keeps_nothing_on_a_disk() -> None:
    """
    The public shape is the one that can say nothing here survives it.

    Redis writes no dump file and the audit trail - when there is one at all -
    goes to the container's output. A volume appearing in this file without
    somebody asking for it would be a copy of everybody's scans nobody chose
    to keep.
    """
    setup = wizard_module.Setup()
    wizard_module._finalise(setup)

    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))

    assert "volumes" not in document
    for service in document["services"].values():
        assert "volumes" not in service
    assert '--appendonly no' in document["services"]["redis"]["command"]
    assert "COS_WEB_AUDIT_LOG_FILE" not in document["services"]["web_app"]["environment"]


def test_an_audit_trail_can_outlive_the_container_in_a_named_volume() -> None:
    """A trail a `docker compose down` erases answers nothing three months later."""
    setup = wizard_module.Setup(audit_log=True, audit_storage="volume")
    wizard_module._finalise(setup)

    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))

    web = document["services"]["web_app"]
    assert web["volumes"] == [
        f"{wizard_module.AUDIT_VOLUME}:{wizard_module.AUDIT_LOG_DIRECTORY}"
    ]
    assert web["environment"]["COS_WEB_AUDIT_LOG_FILE"] == (
        f"{wizard_module.AUDIT_LOG_DIRECTORY}/{wizard_module.AUDIT_LOG_FILENAME}"
    )
    # Declared, or Compose has a mount naming a volume that does not exist.
    assert wizard_module.AUDIT_VOLUME in document["volumes"]
    # Rotation travels with it: a log nobody rotates fills the volume and
    # takes the service down with it.
    assert web["environment"]["COS_WEB_AUDIT_LOG_MAX_BYTES"]
    assert web["environment"]["COS_WEB_AUDIT_LOG_BACKUPS"]
    # Redis is untouched by the audit question.
    assert "volumes" not in document["services"]["redis"]


def test_an_audit_trail_can_go_to_a_directory_on_the_host_instead() -> None:
    """Existing log shipping and backups work on files, not on Docker volumes."""
    setup = wizard_module.Setup(
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path="/srv/opencloud-scan/audit",
    )
    wizard_module._finalise(setup)

    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))

    assert document["services"]["web_app"]["volumes"] == [
        f"/srv/opencloud-scan/audit:{wizard_module.AUDIT_LOG_DIRECTORY}"
    ]
    # A bind mount names a directory that already exists, so there is nothing
    # for Docker to declare - and the operator is told to create it.
    assert "volumes" not in document
    assert any(
        "chown" in warning and str(wizard_module.WEB_IMAGE_UID) in warning
        for warning in wizard_module.check_consistency(setup)
    )


def test_the_audit_trail_is_only_kept_when_there_is_one_to_keep() -> None:
    """Storage for a log nobody turned on is a mount point with nothing in it."""
    setup = wizard_module.Setup(audit_log=False, audit_storage="volume")

    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))

    assert "volumes" not in document
    assert "volumes" not in document["services"]["web_app"]
    assert document["services"]["web_app"]["environment"]["COS_WEB_AUDIT_LOG"] == "false"

    # And the question is not asked either.
    assert not wizard_module._relevant("audit_storage", setup)
    assert not wizard_module._relevant("audit_log_path", setup)
    setup.audit_log = True
    assert wizard_module._relevant("audit_storage", setup)
    # The host directory is only asked for when it is the answer.
    assert not wizard_module._relevant("audit_log_path", setup)
    setup.audit_storage = "filesystem"
    assert wizard_module._relevant("audit_log_path", setup)


def test_redis_persists_only_when_asked_and_says_what_that_costs() -> None:
    """
    Turning the cache into a database puts everybody's scans on a disk.

    The compose file is what an operator reads six months later, so the
    comment above the command has to stop claiming the opposite.
    """
    setup = wizard_module.Setup(redis_persistence="volume")
    wizard_module._finalise(setup)

    rendered = wizard_module.render_compose_file(setup, "compose.yml")
    document = yaml.safe_load(rendered)

    redis = document["services"]["redis"]
    assert redis["volumes"] == [f"{wizard_module.REDIS_VOLUME}:{wizard_module.REDIS_DATA_DIRECTORY}"]
    assert wizard_module.REDIS_VOLUME in document["volumes"]
    command = " ".join(redis["command"].split())
    assert "--appendonly yes" in command
    assert f"--dir {wizard_module.REDIS_DATA_DIRECTORY}" in command
    # `--save "900 1"` would reach valkey-server as one quoted value and be
    # refused; the option takes two arguments.
    assert "--save 900 1" in command
    assert "--appendonly no" not in command
    assert "It writes nothing to disk" not in rendered

    # The claim is still there for the deployment where it is true.
    assert "It writes nothing to disk" in wizard_module.render_compose_file(
        wizard_module.Setup(), "compose.yml"
    )


def test_persisting_redis_without_encryption_is_pointed_out() -> None:
    """Results on a disk in the clear is the thing this service otherwise never does."""
    warnings = wizard_module.check_consistency(
        wizard_module.Setup(redis_persistence="volume")
    )
    assert any("ENCRYPT" in warning for warning in warnings)

    encrypted = wizard_module.Setup(redis_persistence="volume", encrypt_results=True)
    assert not any("ENCRYPT" in w for w in wizard_module.check_consistency(encrypted))


def test_a_storage_directory_has_to_be_one_compose_can_resolve() -> None:
    """A relative bind mount is relative to the compose file, not to the operator."""
    assert wizard_module._host_directory("srv/audit")
    assert wizard_module._host_directory("/srv/audit:ro")
    assert wizard_module._host_directory("/srv/opencloud-scan/audit") is None


def test_the_private_preset_keeps_the_trail_it_turns_on(tmp_path: Path) -> None:
    """An estate that audits its own scans audits them past the next update."""
    assert _run(tmp_path, "--preset", "private") == 0

    document = _compose(tmp_path)
    web = document["services"]["web_app"]
    assert web["environment"]["COS_WEB_AUDIT_LOG"] == "true"
    assert web["environment"]["COS_WEB_AUDIT_LOG_FILE"]
    assert wizard_module.AUDIT_VOLUME in document["volumes"]
    # Keeping the trail is not the same decision as keeping the scans.
    assert "volumes" not in document["services"]["redis"]


def test_a_yes_or_no_question_takes_true_and_false_as_well(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The words an operator reaches for at a compose-file question are these four."""
    setup = wizard_module.Setup()
    wizard = wizard_module.Wizard(setup)
    question = wizard_module.Question(
        key="audit_log", prompt="p", explain="e", example="no", kind="bool"
    )

    for answer, expected in (("true", True), ("false", False), ("yes", True), ("no", False)):
        monkeypatch.setattr(
            wizard_module.Wizard, "_read", lambda self, prompt, typed=answer: typed
        )
        wizard.ask(question)
        assert setup.audit_log is expected, answer

    # And the prompt says so, rather than leaving it to be discovered.
    said: list[str] = []
    monkeypatch.setattr(wizard_module.Wizard, "say", lambda self, text="": said.append(text))
    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: "yes")
    wizard.ask(question)
    assert any("true and false" in line for line in said)


# --- rotating the trail on the host -----------------------------------------
def test_the_service_rotates_its_own_trail_unless_the_host_is_asked_to() -> None:
    """Something has to bound the file, and exactly one thing may."""
    setup = wizard_module.Setup(
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path="/srv/opencloud-scan/audit",
    )
    wizard_module._finalise(setup)

    web = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))[
        "services"
    ]["web_app"]["environment"]

    assert web["COS_WEB_AUDIT_LOG_MAX_BYTES"]
    assert web["COS_WEB_AUDIT_LOG_BACKUPS"]
    assert "COS_WEB_AUDIT_LOG_ROTATION" not in web


def test_handing_the_trail_to_logrotate_turns_the_services_own_rotation_off() -> None:
    """Two rotators on one file is how a trail loses records."""
    setup = wizard_module.Setup(
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path="/srv/opencloud-scan/audit",
        audit_rotation="logrotate",
    )
    wizard_module._finalise(setup)

    web = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))[
        "services"
    ]["web_app"]["environment"]

    assert web["COS_WEB_AUDIT_LOG_ROTATION"] == wizard_module.EXTERNAL_ROTATION
    # The size-based rotation is not merely ignored, it is not written down:
    # a compose file carrying both says nothing about which one is in charge.
    assert "COS_WEB_AUDIT_LOG_MAX_BYTES" not in web
    assert "COS_WEB_AUDIT_LOG_BACKUPS" not in web


def test_the_generated_logrotate_policy_names_the_file_and_can_create_it(
    tmp_path: Path,
) -> None:
    """
    The policy has to agree with the container on the path and the uid.

    logrotate moves the file aside and makes the replacement itself, so a
    `create` line with the wrong owner leaves the service unable to write to
    the file it was told to keep - a trail that stops the first night the
    rotation runs.
    """
    setup = wizard_module.Setup(
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path="/srv/opencloud-scan/audit/",
        audit_rotation="logrotate",
        audit_retention_days=90,
    )
    wizard_module._finalise(setup)

    policy = wizard_module.render_logrotate_file(setup)

    assert policy.count("/srv/opencloud-scan/audit/audit.log {") == 1
    assert f"create 0600 {wizard_module.WEB_IMAGE_UID}" in policy
    assert "rotate 90" in policy
    assert "daily" in policy
    # copytruncate would truncate the file underneath a running writer and
    # lose whatever was written between the copy and the truncation. The
    # service reopens on a changed inode instead, which loses nothing. The
    # word appears in the comment explaining that; the directive must not.
    directives = [
        line.strip() for line in policy.splitlines() if not line.strip().startswith("#")
    ]
    assert not any(line.startswith("copytruncate") for line in directives)
    assert "/etc/logrotate.d" in policy

    # It is written beside the compose file, not into /etc: installing it
    # needs root, and a wizard that writes outside its output directory is one
    # nobody can run to see what it would do.
    written = wizard_module.write_files(
        setup, tmp_path / "docker-compose.yml", tmp_path / ".env"
    )
    name = wizard_module.logrotate_filename(setup)
    assert (tmp_path / name).read_text(encoding="utf-8") == policy
    assert any(name in item for item in written)
    assert stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o644


def test_no_logrotate_policy_is_written_for_a_deployment_that_did_not_ask(
    tmp_path: Path,
) -> None:
    """A named volume is a path under Docker's root; nothing else should name it."""
    assert _run(tmp_path) == 0
    assert not list(tmp_path.glob("*.logrotate"))

    volume = tmp_path / "on-a-volume"
    setup = wizard_module.Setup(audit_log=True, audit_storage="volume")
    wizard_module._finalise(setup)
    wizard_module.write_files(setup, volume / "docker-compose.yml", volume / ".env")
    assert not list(volume.glob("*.logrotate"))

    # And the question is not asked either, because there is no host path for
    # a policy to name.
    assert not wizard_module._relevant("audit_rotation", setup)
    assert not wizard_module._relevant("audit_retention_days", setup)
    setup.audit_storage = "filesystem"
    assert wizard_module._relevant("audit_rotation", setup)
    # Retention is a logrotate setting; the service's own rotation is by size.
    assert not wizard_module._relevant("audit_retention_days", setup)
    setup.audit_rotation = "logrotate"
    assert wizard_module._relevant("audit_retention_days", setup)


def test_a_policy_nobody_installs_rotates_nothing_and_the_wizard_says_so() -> None:
    """The one step the wizard cannot take for you is the one that needs root."""
    setup = wizard_module.Setup(
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path="/srv/opencloud-scan/audit",
        audit_rotation="logrotate",
    )

    assert any(
        "/etc/logrotate.d" in warning
        for warning in wizard_module.check_consistency(setup)
    )

    setup.audit_rotation = "service"
    assert not any(
        "/etc/logrotate.d" in warning
        for warning in wizard_module.check_consistency(setup)
    )


def _questions_asked(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, object]
) -> list[str]:
    """Run the questions, answering only what is named, and record the order.

    The wizard is driven through ``Wizard.ask`` rather than through ``_read``
    because the prompt a question is read with says nothing about which
    question it is - and what these tests are about is precisely *which*
    questions a set of answers brings into play.
    """
    asked: list[str] = []

    def ask(self, question, **_) -> None:
        asked.append(question.key)
        if question.key in answers:
            setattr(self.setup, question.key, answers[question.key])

    monkeypatch.setattr(wizard_module.Wizard, "ask", ask)
    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: "")
    return asked


def test_naming_a_mail_server_brings_the_rest_of_the_session_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    An answer has to be able to open the questions that follow it.

    The mail questions are the case that made this visible: every one of them
    except the host is worth asking only once there is a host, so a section
    whose question list was filtered once, before the section began, could
    only ever ask for the server name - and a deployment left with a host and
    no port, no transport security and no credentials fails at the first
    password recovery, which is the worst moment available.
    """
    asked = _questions_asked(
        monkeypatch,
        {
            "admin_enabled": False,
            "deploy_authentik": True,
            "smtp_host": "smtp.example.com",
        },
    )

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    for key in (
        "smtp_port",
        "smtp_security",
        "smtp_auth",
        "smtp_username",
        "smtp_password",
        "smtp_from",
        "smtp_timeout",
    ):
        assert key in asked, key
    # And the negative half: no host, nothing but the host is asked. In a
    # directory of its own, because the run above left its answers in this
    # one and they would supply the host all over again.
    silent = _questions_asked(monkeypatch, {"deploy_authentik": True})
    assert wizard_module.main(["--output-dir", str(tmp_path / "fresh")]) == 0
    assert "smtp_host" in silent
    assert "smtp_port" not in silent


def test_a_relay_that_wants_no_account_is_not_asked_for_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty username is how Authentik is told to submit without authenticating."""
    asked = _questions_asked(
        monkeypatch,
        {
            "deploy_authentik": True,
            "smtp_host": "smtp.example.com",
            "smtp_auth": False,
        },
    )

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    assert "smtp_auth" in asked
    assert "smtp_username" not in asked
    assert "smtp_password" not in asked

    # A credential typed before the answer changed is dropped rather than sent
    # to a relay that never asked for one.
    setup = wizard_module.Setup(
        enable_mcp=True,
        deploy_authentik=True,
        smtp_host="smtp.example.com",
        smtp_auth=False,
        smtp_username="left@example.com",
        smtp_password="left-over",  # nosec B106 - a placeholder, not a secret
    )
    wizard_module._finalise(setup)
    assert setup.smtp_username == ""
    assert setup.smtp_password == ""


def test_the_operators_area_can_be_the_only_reason_for_a_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Two different things here can want a sign-in, and only one of them is /mcp.

    The operator's area has no other way in at all - the service authenticates
    nobody - so a deployment that turns /mcp off and /admin on still has to be
    offered a provider, and asked for its address and its ports. It used to be
    asked for none of that, because every Authentik question hung off the MCP
    endpoint being enabled.
    """
    setup = wizard_module.Setup(enable_mcp=False, admin_enabled=True)

    assert wizard_module._relevant("deploy_authentik", setup)
    setup.deploy_authentik = True
    for key in ("authentik_url", "authentik_slug", "authentik_http_port"):
        assert wizard_module._relevant(key, setup), key

    # Nothing to guard, no provider: three containers and a database that
    # nothing in front of them consults are three containers to patch.
    nothing = wizard_module.Setup(
        enable_mcp=False, admin_enabled=False, deploy_authentik=True
    )
    assert not wizard_module._uses_authentik(nothing)
    assert "authentik_server" not in yaml.safe_load(
        wizard_module.render_compose_file(nothing, "compose.yml")
    )["services"]


def test_the_area_gets_the_blueprint_that_provisions_its_way_in(
    tmp_path: Path,
) -> None:
    """A proxy provider is a different thing from the one that issues /mcp tokens."""
    setup = wizard_module.Setup(
        enable_mcp=False,
        admin_enabled=True,
        admin_users="okko",
        deploy_authentik=True,
        public_base_url="https://scan.example.com",
    )
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)

    written = wizard_module.write_files(
        setup, tmp_path / "docker-compose.yml", tmp_path / ".env"
    )

    blueprints = tmp_path / "authentik" / "blueprints"
    assert (blueprints / "opencloud-admin.yaml").is_file()
    assert (blueprints / "opencloud-scanner.yaml").is_file()
    assert any("opencloud-admin.yaml" in item for item in written)

    # The proxy provider is bound to the origin it protects, which is the
    # address visitors use rather than the container's own.
    document = yaml.safe_load((tmp_path / "docker-compose.yml").read_text(encoding="utf-8"))
    server = document["services"]["authentik_server"]["environment"]
    assert server["COS_WEB_ADMIN_URL"] == "https://scan.example.com"
    # And where the embedded outpost sends a browser to sign in, for both
    # containers - the worker is the one that applies the blueprint.
    for name in ("authentik_server", "authentik_worker"):
        environment = document["services"][name]["environment"]
        assert environment["COS_AUTHENTIK_URL"] == setup.authentik_url
    assert "localhost" in setup.authentik_url

    # A deployment with no area gets no proxy provider to leave lying around.
    plain = wizard_module.Setup(enable_mcp=True, deploy_authentik=True)
    wizard_module._finalise(plain)
    elsewhere = tmp_path / "plain"
    wizard_module.write_files(
        plain, elsewhere / "docker-compose.yml", elsewhere / ".env"
    )
    assert not (elsewhere / "authentik" / "blueprints" / "opencloud-admin.yaml").exists()


def test_the_provider_can_be_moved_off_the_port_something_else_is_using(
    tmp_path: Path,
) -> None:
    """9000 is a popular port, and a deployment that cannot move is one that cannot run."""
    setup = wizard_module.Setup(
        enable_mcp=True,
        mcp_auth_enabled=True,
        admin_enabled=True,
        admin_users="okko",
        deploy_authentik=True,
        authentik_http_port=9500,
        authentik_https_port=9543,
        reverse_proxy="nginx",
        public_base_url="https://scan.example.com",
    )
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)

    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))
    assert document["services"]["authentik_server"]["ports"] == [
        "127.0.0.1:9500:9000",
        "127.0.0.1:9543:9443",
    ]

    # The proxy in front has to reach the same listener, or the forward auth
    # asks a port nothing answers on and /admin never opens.
    assert "http://127.0.0.1:9500" in wizard_module.render_proxy_file(setup)


def test_a_storage_directory_nobody_named_never_becomes_a_mount_compose_refuses(
    tmp_path: Path,
) -> None:
    """
    ``- :/data`` is not a mount. It is a stack that will not start.

    The wizard used to write exactly that whenever a host directory was asked
    for and none was given: an empty source, a colon, and a compose file
    Docker refuses to parse - over a question that was never answered, taking
    a working deployment with it. The answer now falls back to the named
    volume, which needs nothing from anybody and keeps the data.
    """
    setup = wizard_module.Setup(
        redis_persistence="filesystem",
        redis_data_path="",
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path="",
    )
    wizard_module._finalise(setup)

    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))

    redis = document["services"]["redis"]["volumes"]
    web = document["services"]["web_app"]["volumes"]
    assert redis == [f"{wizard_module.REDIS_VOLUME}:{wizard_module.REDIS_DATA_DIRECTORY}"]
    assert web == [f"{wizard_module.AUDIT_VOLUME}:{wizard_module.AUDIT_LOG_DIRECTORY}"]
    # Declared, or the mount names a volume that does not exist.
    assert wizard_module.REDIS_VOLUME in document["volumes"]
    assert wizard_module.AUDIT_VOLUME in document["volumes"]
    for service in document["services"].values():
        for mount in service.get("volumes", []):
            assert not mount.startswith(":"), mount

    # And it says so, rather than quietly putting the data somewhere else.
    warnings = wizard_module.check_consistency(setup)
    assert any(wizard_module.REDIS_VOLUME in warning for warning in warnings)
    assert any(wizard_module.AUDIT_VOLUME in warning for warning in warnings)


def test_the_directory_a_volume_maps_to_is_asked_for_and_defaults_beside_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default has to be somewhere an operator can find without being told."""
    assert wizard_module.Setup().redis_data_path == "./data"
    assert wizard_module.Setup().audit_log_path == "./audit"

    asked = _questions_asked(
        monkeypatch, {"audit_log": True, "audit_storage": "filesystem"}
    )
    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0
    assert "audit_log_path" in asked

    setup = wizard_module.Setup(redis_persistence="filesystem")
    wizard_module._finalise(setup)
    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))
    assert document["services"]["redis"]["volumes"] == [
        f"./data:{wizard_module.REDIS_DATA_DIRECTORY}"
    ]
    # A bind mount declares nothing: the directory is the operator's to make,
    # and they are told to, before the first `up` invents it owned by root.
    assert "volumes" not in document
    assert any(
        "chown" in warning and "./data" in warning
        for warning in wizard_module.check_consistency(setup)
    )


def test_a_relative_storage_directory_has_to_say_that_it_is_one() -> None:
    """
    ``data:/data`` is a named volume; ``./data:/data`` is a directory.

    One character apart, and the difference between a path an operator can
    back up and one Docker invented somewhere under its own root. So a bare
    name is refused rather than accepted as either.
    """
    assert wizard_module._host_directory("./data") is None
    assert wizard_module._host_directory("../shared/data") is None
    assert wizard_module._host_directory("/srv/opencloud-scan/data") is None

    assert wizard_module._host_directory("data")
    assert wizard_module._host_directory("srv/audit")
    assert wizard_module._host_directory("/srv/audit:ro")
    # The empty answer is the one that used to produce ':/data'.
    assert wizard_module._host_directory("")


def test_the_proxy_named_is_the_proxy_written(tmp_path: Path) -> None:
    """A configuration for a server you do not run is a file you cannot install."""
    for flavour, expected in (
        ("nginx", "opencloud-scan-nginx.conf"),
        ("apache", "opencloud-scan-apache.conf"),
        ("caddy", "opencloud-scan-caddyfile"),
        ("traefik", "opencloud-scan-traefik.yml"),
    ):
        setup = wizard_module.Setup(
            reverse_proxy=flavour, public_base_url="https://scan.example.com"
        )
        wizard_module._finalise(setup)
        directory = tmp_path / flavour
        wizard_module.write_files(
            setup, directory / "docker-compose.yml", directory / ".env"
        )

        written = directory / expected
        assert written.is_file(), flavour
        content = written.read_text(encoding="utf-8")
        # It has to name the host it answers to and the address it proxies to,
        # or it is a template rather than a configuration.
        assert "scan.example.com" in content
        assert "127.0.0.1:8811" in content

    # 'none' is the default, and it writes no proxy configuration at all.
    plain = tmp_path / "plain"
    assert _run(plain) == 0
    names = sorted(item.name for item in plain.iterdir())
    assert "docker-compose.yml" in names
    assert not any(
        name.endswith(("nginx.conf", "apache.conf", "caddyfile", "traefik.yml"))
        for name in names
    )


def test_a_generated_proxy_answers_at_the_name_the_service_publishes(
    tmp_path: Path,
) -> None:
    """Three places naming three hosts is a deployment that works until it does not."""
    setup = wizard_module.Setup(
        reverse_proxy="nginx", public_base_url="https://scan.example.com"
    )
    wizard_module._finalise(setup)

    assert setup.reverse_proxy_hostname == "scan.example.com"
    assert "server_name scan.example.com;" in wizard_module.render_proxy_file(setup)

    # Asked for explicitly, it wins - and the scheme follows the certificate.
    named = wizard_module.Setup(
        reverse_proxy="nginx",
        reverse_proxy_hostname="files.example.com",
        public_base_url="https://scan.example.com",
    )
    wizard_module._finalise(named)
    assert "server_name files.example.com;" in wizard_module.render_proxy_file(named)

    # A deployment that never named itself gets a configuration for localhost,
    # and is told that is all it is.
    local = wizard_module.Setup(reverse_proxy="caddy")
    wizard_module._finalise(local)
    assert any(
        "localhost" in warning for warning in wizard_module.check_consistency(local)
    )


def test_the_generated_proxy_never_buffers_the_endpoints_that_stream(
    tmp_path: Path,
) -> None:
    """A buffered event stream is an agent session that waits for ever."""
    expected = {
        "nginx": "proxy_buffering off;",
        "apache": "flushpackets=on",
        "caddy": "flush_interval -1",
        "traefik": "flushInterval: 1ms",
    }
    for flavour, directive in expected.items():
        setup = wizard_module.Setup(
            reverse_proxy=flavour,
            enable_mcp=True,
            public_base_url="https://scan.example.com",
        )
        wizard_module._finalise(setup)
        assert directive in wizard_module.render_proxy_file(setup), flavour

    # With the endpoint off there is no /mcp block to get wrong.
    without = wizard_module.Setup(
        reverse_proxy="nginx", enable_mcp=False, public_base_url="https://scan.example.com"
    )
    wizard_module._finalise(without)
    assert "location /mcp" not in wizard_module.render_proxy_file(without)


def _admin_setup(flavour: str) -> Any:
    setup = wizard_module.Setup(
        reverse_proxy=flavour,
        admin_enabled=True,
        admin_users="okko",
        deploy_authentik=True,
        trust_forwarded_for=True,
        public_base_url="https://scan.example.com",
    )
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)
    return setup


def test_only_a_proxy_that_can_ask_the_outpost_is_given_an_admin_block(
    tmp_path: Path,
) -> None:
    """
    A generated /admin block that authenticated nobody would be the worst
    file this script could write.

    Three of the four can ask an outpost whether a request may pass before
    passing it on. Apache cannot, so it gets no block for the area at all -
    the catch-all proxies it without the shared secret, the service answers
    404, and the comment in the file says why rather than leaving somebody to
    find out.
    """
    for flavour in ("nginx", "caddy", "traefik"):
        setup = _admin_setup(flavour)
        content = wizard_module.render_proxy_file(setup)
        assert wizard_module.AUTHENTIK_OUTPOST_PREFIX in content, flavour
        assert wizard_module.ADMIN_PATH in content, flavour
        # The header itself: written inline where the proxy can read a value
        # from its environment, and included from a file where it cannot.
        carrier = (
            wizard_module.render_admin_secret_file(setup)
            if flavour == "nginx"
            else content
        )
        assert wizard_module.ADMIN_PROXY_HEADER in carrier, flavour
        for header in wizard_module.ADMIN_IDENTITY_HEADERS:
            assert header in content, (flavour, header)

    # authentik's cookie and identity headers outgrow nginx's default buffers.
    nginx = wizard_module.render_proxy_file(_admin_setup("nginx"))
    assert nginx.count("proxy_buffer_size 32k;") == 2

    apache = _admin_setup("apache")
    content = wizard_module.render_proxy_file(apache)
    assert "forward" in content.lower()
    assert f"RequestHeader unset {wizard_module.ADMIN_PROXY_HEADER}" in content
    # Nothing Apache actually executes adds the header. The comment explaining
    # how to add it yourself mentions the directive, so only live lines count.
    directives = [
        line.strip() for line in content.splitlines() if not line.strip().startswith("#")
    ]
    assert not any(
        line.startswith(f"RequestHeader set {wizard_module.ADMIN_PROXY_HEADER}")
        for line in directives
    )
    assert apache.admin_proxy_secret not in content
    assert any(
        "404" in warning for warning in wizard_module.check_consistency(apache)
    )


def test_the_proxys_admin_secret_stays_out_of_the_file_meant_to_be_committed(
    tmp_path: Path,
) -> None:
    """
    A proxy configuration is pasted into tickets and copied between hosts.

    So the shared secret is not in it, for the same reason it is not in the
    compose file: nginx gets a one-line include, owner-readable, and the two
    that can read their own environment are told to.
    """
    setup = _admin_setup("nginx")
    written = wizard_module.write_files(
        setup, tmp_path / "docker-compose.yml", tmp_path / ".env"
    )

    configuration = tmp_path / wizard_module.proxy_filename(setup)
    secret_file = tmp_path / wizard_module.admin_secret_filename(setup)
    assert setup.admin_proxy_secret
    assert setup.admin_proxy_secret not in configuration.read_text(encoding="utf-8")
    assert setup.admin_proxy_secret in secret_file.read_text(encoding="utf-8")
    assert stat.S_IMODE(secret_file.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR
    assert any(str(secret_file) in item for item in written)
    # The include is what carries it, so removing the file closes the area
    # rather than opening it.
    assert (
        f"include {wizard_module.admin_secret_path(setup)};"
        in configuration.read_text(encoding="utf-8")
    )
    # Deliberately not a .conf: everything called that under conf.d is
    # included into the http block, and this belongs to one location.
    assert not secret_file.name.endswith(".conf")

    for flavour in ("caddy", "traefik"):
        other = _admin_setup(flavour)
        content = wizard_module.render_proxy_file(other)
        assert other.admin_proxy_secret not in content, flavour
        assert "COS_WEB_ADMIN_PROXY_SECRET" in content, flavour


def test_a_proxy_whose_client_address_nobody_reads_is_pointed_out() -> None:
    """Untrusted, every visitor shares one rate-limit bucket with the whole internet."""
    setup = wizard_module.Setup(
        reverse_proxy="nginx",
        trust_forwarded_for=False,
        public_base_url="https://scan.example.com",
    )
    wizard_module._finalise(setup)

    assert any(
        "COS_WEB_TRUST_FORWARDED_FOR" in warning
        for warning in wizard_module.check_consistency(setup)
    )

    setup.trust_forwarded_for = True
    assert not any(
        "COS_WEB_TRUST_FORWARDED_FOR" in warning
        for warning in wizard_module.check_consistency(setup)
    )
    # And a deployment with no generated proxy is not nagged about a header
    # nothing in front of it writes.
    assert not any(
        "COS_WEB_TRUST_FORWARDED_FOR" in warning
        for warning in wizard_module.check_consistency(wizard_module.Setup())
    )


def test_the_proxy_reaches_the_service_even_when_it_listens_on_every_interface(
    tmp_path: Path,
) -> None:
    """0.0.0.0 means listen everywhere; nothing *connects* to it."""
    setup = wizard_module.Setup(
        reverse_proxy="nginx",
        bind_address="0.0.0.0",  # nosec B104
        host_port=9000,
        public_base_url="https://scan.example.com",
    )
    wizard_module._finalise(setup)

    content = wizard_module.render_proxy_file(setup)
    assert "proxy_pass http://127.0.0.1:9000;" in content
    assert "0.0.0.0:9000" not in content  # nosec B104


def test_a_provider_only_this_host_can_reach_is_pointed_out() -> None:
    """
    The forward auth redirects a browser to the provider, not to the outpost.

    The generated proxy routes the outpost's own endpoints and nothing else,
    so an Authentik left on its default `localhost` address signs nobody in
    from anywhere but this machine - and the failure looks like a broken
    redirect rather than a setting.
    """
    setup = _admin_setup("nginx")

    assert "localhost" in setup.authentik_url
    assert any(
        "browser can reach" in warning
        for warning in wizard_module.check_consistency(setup)
    )

    setup.authentik_url = "https://sso.example.com"
    assert not any(
        "browser can reach" in warning
        for warning in wizard_module.check_consistency(setup)
    )


def test_the_generated_proxy_serves_authentik_at_its_public_address() -> None:
    """
    Every sign-in sends a browser to Authentik's public address.

    A stack that brings the provider but a proxy configuration that only
    serves the scanner leaves that redirect arriving nowhere, so the same file
    carries a site for Authentik - one that proxies to its published port and
    carries the WebSocket its interface keeps open.
    """
    expected = {
        "nginx": "server_name sso.example.com;",
        "apache": "ServerName sso.example.com",
        "caddy": "sso.example.com {",
        "traefik": "Host(`sso.example.com`)",
    }
    for flavour, site in expected.items():
        # Without /admin as well: the provider needs a site whether or not
        # there is an area for it to guard.
        setup = wizard_module.Setup(
            reverse_proxy=flavour,
            deploy_authentik=True,
            public_base_url="https://scan.example.com",
            authentik_url="https://sso.example.com",
        )
        wizard_module._finalise(setup)
        content = wizard_module.render_proxy_file(setup)
        assert site in content, flavour
        assert "127.0.0.1:9000" in content, flavour
        assert not any(
            "browser can reach" in warning
            for warning in wizard_module.check_consistency(setup)
        ), flavour

    websocket = {"nginx": "Upgrade", "apache": "upgrade=websocket"}
    for flavour, directive in websocket.items():
        setup = wizard_module.Setup(
            reverse_proxy=flavour,
            deploy_authentik=True,
            public_base_url="https://scan.example.com",
            authentik_url="https://sso.example.com",
        )
        wizard_module._finalise(setup)
        site = wizard_module.render_proxy_file(setup).split("sso.example.com", 1)[1]
        assert directive in site, flavour

    # No provider in the stack, no site for one.
    plain = wizard_module.Setup(
        reverse_proxy="nginx",
        public_base_url="https://scan.example.com",
        authentik_url="https://sso.example.com",
    )
    wizard_module._finalise(plain)
    assert "sso.example.com" not in wizard_module.render_proxy_file(plain)


def test_authentik_without_a_name_of_its_own_gets_no_site_and_a_warning() -> None:
    """
    A site for localhost, or a second one for the scanner's own name, would
    be a configuration that installs cleanly and signs nobody in.
    """
    for address in ("", "http://localhost:9000", "https://scan.example.com", "http://10.0.0.5"):
        setup = wizard_module.Setup(
            reverse_proxy="nginx",
            deploy_authentik=True,
            public_base_url="https://scan.example.com",
            authentik_url=address,
        )
        wizard_module._finalise(setup)
        content = wizard_module.render_proxy_file(setup)
        assert content.count("server_name ") == 2, address  # redirect + scanner
        assert "127.0.0.1:9000;" not in content, address
        assert any(
            "browser can reach" in warning
            for warning in wizard_module.check_consistency(setup)
        ), address


def test_authentiks_certificate_is_asked_for_only_where_the_proxy_needs_one() -> None:
    """Caddy and Traefik fetch their own; nginx and Apache have to be told."""
    questions = ("reverse_proxy_authentik_certificate", "reverse_proxy_authentik_private_key")

    def setup_for(**overrides: Any) -> Any:
        values: dict[str, Any] = {
            "reverse_proxy": "nginx",
            "deploy_authentik": True,
            "public_base_url": "https://scan.example.com",
            "authentik_url": "https://sso.example.com",
        }
        values.update(overrides)
        return wizard_module.Setup(**values)

    for key in questions:
        assert wizard_module._relevant(key, setup_for())
        assert wizard_module._relevant(key, setup_for(reverse_proxy="apache"))
        assert not wizard_module._relevant(key, setup_for(reverse_proxy="caddy"))
        assert not wizard_module._relevant(key, setup_for(reverse_proxy_tls=False))
        assert not wizard_module._relevant(key, setup_for(deploy_authentik=False))
        assert not wizard_module._relevant(key, setup_for(authentik_url=""))

    chosen = setup_for(
        reverse_proxy_authentik_certificate="/etc/letsencrypt/live/sso/fullchain.pem",
        reverse_proxy_authentik_private_key="/etc/letsencrypt/live/sso/privkey.pem",
        reverse_proxy_certificate="/etc/letsencrypt/live/scan/fullchain.pem",
    )
    wizard_module._finalise(chosen)
    content = wizard_module.render_proxy_file(chosen)
    scanner, authentik = content.split("server_name sso.example.com;", 1)
    assert "/etc/letsencrypt/live/scan/fullchain.pem" in scanner
    assert "/etc/letsencrypt/live/sso/fullchain.pem" in authentik
    assert "/etc/letsencrypt/live/sso/fullchain.pem" not in scanner


def test_turning_the_operators_area_on_prints_what_to_do_next() -> None:
    """
    /admin refuses rather than asking, so the steps have to be written down.

    There is no login page to arrive at and no password prompt to get wrong:
    a request missing any part of the arrangement gets the same 404 as any
    unknown path. That is the right answer to give a stranger and a miserable
    one to debug against, so the wizard ends with the order to do things in
    and what each failure means.
    """
    setup = _admin_setup("nginx")
    setup.authentik_url = "https://sso.example.com"
    setup.admin_users = "okko"

    walkthrough = "\n".join(wizard_module.admin_walkthrough(setup))

    # Every step somebody has to take in a browser or as root, in order.
    assert "enrollment link" in walkthrough
    assert wizard_module.AUTHENTIK_OPERATOR_GROUP in walkthrough
    # Joining the group is done by the enrollment flow, not by a click.
    assert "Directory > Groups" not in walkthrough
    assert "COS_WEB_ADMIN_USERS" in walkthrough
    assert "https://scan.example.com/admin" in walkthrough
    # And what the 404 it may answer with actually means.
    assert wizard_module.ADMIN_PROXY_HEADER in walkthrough
    assert "404" in walkthrough
    assert [line for line in walkthrough.splitlines() if line.strip().startswith("5.")]
    assert not [line for line in walkthrough.splitlines() if line.strip().startswith("6.")]

    # An area nobody turned on has nothing to explain.
    assert wizard_module.admin_walkthrough(wizard_module.Setup()) == []


def test_the_walkthrough_describes_the_deployment_it_was_written_for() -> None:
    """
    Generic advice would be the documentation, which the operator already has.

    Against somebody else's provider there is no Authentik password to set and
    no group to join - there is a header contract to meet - and the sign-out
    link the bundled stack configures for itself has to be named by hand.
    """
    own = wizard_module.Setup(
        admin_enabled=True,
        admin_users="okko",
        public_base_url="https://scan.example.com",
    )
    wizard_module._generate_unattended(own)
    wizard_module._finalise(own)

    walkthrough = "\n".join(wizard_module.admin_walkthrough(own))

    assert wizard_module.AUTHENTIK_OPERATOR_GROUP not in walkthrough
    assert "enrollment link" not in walkthrough
    assert wizard_module.ADMIN_IDENTITY_HEADERS[0] in walkthrough
    assert "COS_WEB_ADMIN_SIGN_OUT_URL" in walkthrough

    # The bundled stack sets the exit itself, so it is not asked for twice.
    bundled = "\n".join(wizard_module.admin_walkthrough(_admin_setup("nginx")))
    assert "COS_WEB_ADMIN_SIGN_OUT_URL" not in bundled


def test_the_walkthrough_names_the_step_an_installed_config_is_not_enough_for() -> None:
    """
    Caddy and Traefik read the shared secret at run time rather than hold it.

    So installing their configuration is not the last step: without the value
    in the proxy's own environment the header goes out empty and the area
    stays shut, with an installed, correct-looking file sitting in front of
    it. nginx carries the secret in the include the wizard writes, and has no
    equivalent step to miss.
    """
    for flavour in ("caddy", "traefik"):
        walkthrough = "\n".join(wizard_module.admin_walkthrough(_admin_setup(flavour)))
        assert f"systemctl edit {flavour}" in walkthrough, flavour
        assert "COS_WEB_ADMIN_PROXY_SECRET" in walkthrough, flavour

    nginx = "\n".join(wizard_module.admin_walkthrough(_admin_setup("nginx")))
    assert "systemctl edit" not in nginx


# --- moving around the questions --------------------------------------------
def _typed(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> list[str]:
    """Feed the wizard typed answers, and collect everything it printed.

    A run that types past the end of the list keeps answering with an empty
    line, which is how an operator accepts the rest of the defaults - so a
    test only has to script the part it is about.
    """
    printed: list[str] = []
    stream = iter(answers)
    monkeypatch.setattr(
        wizard_module.Wizard, "say", lambda self, text="": printed.append(text)
    )
    monkeypatch.setattr(
        wizard_module.Wizard, "_read", lambda self, prompt: next(stream, "")
    )
    return printed


def test_a_choice_can_be_answered_with_the_number_beside_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Typing 'dockerhub' correctly is a tax paid at every one of these."""
    setup = wizard_module.Setup()
    printed = _typed(monkeypatch, ["2", "rest"])

    wizard_module.run_questions(wizard_module.Wizard(setup))

    assert setup.image_source == "build"
    # The options are listed with their numbers, and the current one marked.
    assert any(line.strip() == "* 1) dockerhub" for line in printed)
    assert any(line.strip() == "2) build" for line in printed)

    # The word still works, and a number outside the list is refused rather
    # than quietly taken as something.
    other = wizard_module.Setup()
    _typed(monkeypatch, ["9", "build", "rest"])
    wizard_module.run_questions(wizard_module.Wizard(other))
    assert other.image_source == "build"


def test_an_answer_already_given_can_be_gone_back_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Noticing a typo one question too late used to mean starting over.

    There are forty-odd questions here and no way back through a file that is
    not written yet, so the only remedy was to abandon the run - or to answer
    the rest of them knowing the compose file would need editing anyway.
    """
    setup = wizard_module.Setup()
    printed = _typed(monkeypatch, ["dockerhub", "b", "build", "rest"])

    wizard_module.run_questions(wizard_module.Wizard(setup))

    assert setup.image_source == "build"
    # The question it went back to was asked again, not skipped over.
    asked = [line for line in printed if "Pull the published image, or build it here?" in line]
    assert len(asked) == 2

    # There is nothing behind the first question, and saying so beats
    # pretending the answer was accepted.
    first = wizard_module.Setup()
    said = _typed(monkeypatch, ["b", "dockerhub", "rest"])
    wizard_module.run_questions(wizard_module.Wizard(first))
    assert first.image_source == "dockerhub"
    assert any("nothing behind it" in line for line in said)


def test_the_remaining_defaults_can_be_taken_in_one_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Somebody who wants the defaults should not have to press Enter forty times."""
    setup = wizard_module.Setup()
    printed = _typed(monkeypatch, ["rest"])

    wizard_module.run_questions(wizard_module.Wizard(setup))

    # Nothing after the first question was asked at all.
    assert not any("The reverse proxy" in line for line in printed)
    assert not any("Port on the host" in line for line in printed)
    # And the defaults are intact, to be reviewed in the summary.
    assert setup.host_port == 8811
    assert setup.reverse_proxy == "none"


def test_a_setting_that_has_a_value_can_be_emptied_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    An empty line keeps the default, so nothing could ever be cleared.

    That is fine until a `.env` from an earlier run supplies the default, or
    a preset does: the answer offered back is one an operator may specifically
    want gone, and 'the same as before' was the only thing they could say.
    """
    setup = wizard_module.Setup(allowed_hosts="opencloud.example.com")
    wizard = wizard_module.Wizard(setup)
    question = wizard_module.Question(
        key="allowed_hosts",
        prompt="p",
        explain="e",
        example="x",
        validate=wizard_module._hostname_list,
    )

    _typed(monkeypatch, ["-"])
    wizard.ask(question)
    assert setup.allowed_hosts == ""

    # Not a way around a validator: a directory that may not be empty is
    # refused the same way any other bad answer is.
    directory = wizard_module.Setup(redis_data_path="./data")
    wizard = wizard_module.Wizard(directory)
    path_question = wizard_module.Question(
        key="redis_data_path",
        prompt="p",
        explain="e",
        example="./data",
        validate=wizard_module._host_directory,
    )
    said = _typed(monkeypatch, ["-", "./elsewhere"])
    wizard.ask(path_question)
    assert directory.redis_data_path == "./elsewhere"
    assert any("compose refuses" in line.lower() for line in said)


def test_the_summary_is_grouped_the_way_the_questions_were_asked() -> None:
    """Sixty field names in a flat list is a thing an operator scrolls past."""
    setup = wizard_module.Setup()
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)

    lines = wizard_module.summarise(setup)

    assert "  Images" in lines
    assert "  Reachability" in lines
    assert "  The reverse proxy" in lines
    # The answers sit under their heading, indented past it.
    images = lines.index("  Images")
    assert lines[images + 1].endswith("[image_source]")
    # Labelled with the question's own words, cut to the column.
    assert lines[images + 1].strip().startswith("Pull the published image")
    # What nobody was asked for is listed apart from what they decided.
    assert "  Derived, and generated for you" in lines
    assert any("redis_password" in line for line in lines)


def test_a_mistake_spotted_in_the_summary_can_be_fixed_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The summary is where a mistake is noticed, and it used to be a dead end.

    Yes wrote the wrong thing; no threw away every other answer to fix one of
    them. Naming a setting re-asks that one question and comes back here.
    """
    printed = _typed(
        monkeypatch,
        [
            "rest",             # take the defaults, go to the summary
            "host_port", "9443",  # fix one by name
            "admin", "yes",       # and one by enough of a name
            "nonsense",           # which is not a setting
            "y",                  # write it
        ],
    )

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    document = _compose(tmp_path)
    assert document["services"]["web_app"]["ports"] == ["127.0.0.1:9443:8811"]
    assert document["services"]["web_app"]["environment"]["COS_WEB_ADMIN_ENABLED"] == "true"
    assert any("Nothing called 'nonsense'" in line for line in printed)

    # Turning the area on at the summary generates what it needs, rather than
    # writing a deployment that refuses to start.
    assert len(_env(tmp_path)["COS_WEB_ADMIN_PROXY_SECRET"]) >= 32


def test_declining_at_the_summary_still_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last question is a question, and no has to mean no."""
    _typed(monkeypatch, ["rest", "n"])

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 1
    assert not (tmp_path / "docker-compose.yml").exists()
    assert not (tmp_path / ".env").exists()


def test_running_the_wizard_again_offers_back_what_it_was_told_last_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The script promised that a second run edits a deployment. Half of it did.

    Every credential was read back out of `.env`, so nothing was regenerated -
    and every other answer was gone. Changing the port on a live deployment
    meant retyping the limits, the paths, the proxy and the sign-in around it,
    or editing the compose file by hand and leaving the wizard behind.
    """
    _typed(monkeypatch, ["rest", "host_port", "9443", "reverse_proxy", "nginx", "y"])
    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    # A second run, answering nothing at all.
    printed = _typed(monkeypatch, ["rest", "y"])
    assert wizard_module.main(["--output-dir", str(tmp_path), "--force"]) == 0

    document = _compose(tmp_path)
    assert document["services"]["web_app"]["ports"] == ["127.0.0.1:9443:8811"]
    assert (tmp_path / "opencloud-scan-nginx.conf").is_file()
    assert any("this is an edit of it" in line for line in printed)


def test_the_remembered_answers_hold_no_credential(tmp_path: Path) -> None:
    """
    Two files to protect, one of them a surprise, is one too many.

    The notebook is an ordinary readable file beside the compose file; every
    secret stays in `.env`, which is created owner-readable and is where the
    next run reads them back from.
    """
    assert _run(tmp_path, "--preset", "private") == 0

    notebook = tmp_path / wizard_module.answers_filename("docker-compose.yml")
    stored = json.loads(notebook.read_text(encoding="utf-8"))

    assert stored["audit_log"] is True  # the preset's answers are remembered
    for key in wizard_module.SECRET_VARIABLES:
        assert key not in stored, key
    values = _env(tmp_path)
    text = notebook.read_text(encoding="utf-8")
    for secret in values.values():
        assert secret not in text


def test_a_notebook_nobody_can_read_is_one_nobody_wrote(tmp_path: Path) -> None:
    """
    It is an editable file, and a wizard that trips over one is worse than
    one that starts from the defaults.

    The type check is exact rather than an isinstance: a bool is an int in
    Python, so `host_port: true` would otherwise be accepted as a port.
    """
    setup = wizard_module.Setup()
    notebook = tmp_path / "answers.json"

    notebook.write_text("{ this is not json", encoding="utf-8")
    assert wizard_module._read_previous_answers(setup, notebook) == 0

    notebook.write_text('["a list, not an object"]', encoding="utf-8")
    assert wizard_module._read_previous_answers(setup, notebook) == 0

    notebook.write_text(
        json.dumps(
            {
                "host_port": True,
                "audit_log": 8811,
                "gone_in_this_version": "x",
                "COS_WEB_PURGE_TOKEN": "not read from here",
                "project_name": "kept",
            }
        ),
        encoding="utf-8",
    )
    assert wizard_module._read_previous_answers(setup, notebook) == 1
    assert setup.host_port == 8811
    assert setup.audit_log is False
    assert setup.project_name == "kept"


def test_a_preset_named_now_beats_one_remembered_from_before(
    tmp_path: Path,
) -> None:
    """A decision made on this command line is a decision made now."""
    assert _run(tmp_path, "--preset", "private") == 0
    assert _compose(tmp_path)["services"]["arq_worker"]["environment"][
        "COS_WEB_ALLOW_PRIVATE_TARGETS"
    ] == "true"

    assert _run(tmp_path, "--force") == 0
    worker = _compose(tmp_path)["services"]["arq_worker"]["environment"]
    assert worker["COS_WEB_ALLOW_PRIVATE_TARGETS"] == "true", "remembered"

    assert _run(tmp_path, "--preset", "public", "--force") == 0
    worker = _compose(tmp_path)["services"]["arq_worker"]["environment"]
    assert worker["COS_WEB_ALLOW_PRIVATE_TARGETS"] == "false", "named now"


def test_a_derived_value_named_at_the_summary_says_it_is_derived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The summary lists what was generated as well as what was decided.

    Answering "no such thing" at a name somebody is reading off the screen is
    the kind of reply that makes people distrust the whole screen.
    """
    printed = _typed(monkeypatch, ["rest", "redis_password", "nonsense", "n"])

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 1

    assert any("is derived from the answers above" in line for line in printed)
    assert any("Nothing called 'nonsense'" in line for line in printed)


def _both_on_the_filesystem(audit: str, redis: str) -> Any:
    return wizard_module.Setup(
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path=audit,
        redis_persistence="filesystem",
        redis_data_path=redis,
    )


def test_the_audit_trail_and_redis_never_share_a_host_directory(tmp_path: Path) -> None:
    """
    The web image writes as uid 10001 and Redis as uid 999.

    A directory has one owner, so whichever chown ran last would decide which
    of the two containers can write - and one directory inside the other fails
    the same way one level down. Spelling the same directory two ways is still
    the same directory.
    """
    for audit, redis in (
        ("./data", "./data"),
        ("./data/", "./data"),
        ("./storage", "./storage/redis"),
        ("./storage/audit", "./storage"),
        (str(tmp_path / "shared"), "./shared"),
    ):
        setup = _both_on_the_filesystem(audit, redis)
        errors = wizard_module.check_errors(setup, tmp_path)
        assert len(errors) == 1, (audit, redis)
        assert str(wizard_module.WEB_IMAGE_UID) in errors[0]
        assert str(wizard_module.REDIS_IMAGE_UID) in errors[0]

    # Side by side is what the defaults already are, and is fine.
    assert not wizard_module.check_errors(_both_on_the_filesystem("./audit", "./data"), tmp_path)
    assert not wizard_module.check_errors(
        _both_on_the_filesystem("./storage/audit", "./storage/redis"), tmp_path
    )
    # A named volume on either side is no host directory to collide with.
    volume = _both_on_the_filesystem("./data", "./data")
    volume.redis_persistence = "volume"
    assert not wizard_module.check_errors(volume, tmp_path)


def test_a_shared_directory_is_refused_when_it_is_typed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Said at the question, where it can be fixed, rather than after an `up`."""
    setup = _both_on_the_filesystem("./data", "./redis")
    wizard = wizard_module.Wizard(setup, base_dir=tmp_path)
    question = next(
        item
        for section in wizard_module.build_sections(setup)
        for item in section.questions
        if item.key == "redis_data_path"
    )

    said = _typed(monkeypatch, ["./data", "./data/redis", "./redis-data"])
    wizard.ask(question)

    assert setup.redis_data_path == "./redis-data"
    # Once for the same directory, once for one inside the other.
    assert any("would both be kept in" in line for line in said)
    assert any("is inside" in line for line in said)


def test_an_unattended_run_writes_nothing_for_a_shared_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that asks nothing must not quietly write a stack that cannot start."""
    answers = tmp_path / wizard_module.answers_filename("docker-compose.yml")
    answers.write_text(
        json.dumps(
            {
                "audit_log": True,
                "audit_storage": "filesystem",
                "audit_log_path": "./data",
                "redis_persistence": "filesystem",
                "redis_data_path": "./data",
            }
        ),
        encoding="utf-8",
    )

    assert _run(tmp_path) == 1
    assert not (tmp_path / "docker-compose.yml").exists()
    assert "different users" in capsys.readouterr().err


def test_a_rootless_daemon_is_recognised_by_its_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rootless Docker serves its socket from the user's runtime directory."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert wizard_module.detect_docker_mode("/run/user/1000/docker.sock") == "rootless"
    assert wizard_module.detect_docker_mode("/var/run/docker.sock") == "rootful"

    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/runtime-okko")
    assert wizard_module.detect_docker_mode("/tmp/runtime-okko/docker.sock") == "rootless"
    # A prefix of the runtime directory's name is not inside it.
    assert wizard_module.detect_docker_mode("/tmp/runtime-okko2/docker.sock") == "rootful"


def test_a_rootless_daemon_is_handed_its_directories_without_sudo() -> None:
    """
    On a rootless daemon, uid 10001 in a container is not uid 10001 on the host.

    `sudo chown 10001` would hand the directory to a host account the container
    never runs as. The chown runs inside a container instead, as the user
    namespace's root - which is the user themself, and needs no sudo.
    """
    rootless = _both_on_the_filesystem("./audit", "./data")
    rootless.docker_mode = "rootless"
    rootful = _both_on_the_filesystem("./audit", "./data")
    wizard_module._finalise(rootful)
    assert rootful.docker_mode == "rootful"

    for uid, path in (
        (wizard_module.WEB_IMAGE_UID, "./audit"),
        (wizard_module.REDIS_IMAGE_UID, "./data"),
    ):
        command = wizard_module._ownership_command(rootless, path, uid)
        assert "sudo" not in command
        assert "docker run --rm --user 0 --entrypoint chown" in command
        assert f'"$(realpath {path})":/target {wizard_module.REDIS_IMAGE} {uid} /target' in command

        plain = wizard_module._ownership_command(rootful, path, uid)
        assert plain == f"mkdir -p {path} && sudo chown {uid} {path}"

    warnings = wizard_module.check_consistency(rootless)
    assert any("docker run --rm --user 0" in warning for warning in warnings)
    assert not any("sudo chown" in warning for warning in warnings)
    assert not any(
        "docker run --rm --user 0" in warning
        for warning in wizard_module.check_consistency(rootful)
    )


def test_a_rootless_logrotate_policy_creates_the_file_as_the_mapped_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    logrotate runs on the host and creates the replacement file itself.

    On a rootless daemon it has to name the host ids the container's uid maps
    to, or the service cannot write to the file the first night it rotates -
    and the path has to be absolute, because cron does not run logrotate from
    the directory the compose file is in.
    """
    subuid = tmp_path / "subuid"
    subgid = tmp_path / "subgid"
    subuid.write_text("someone:100000:65536\nokko:165536:65536\n", encoding="utf-8")
    subgid.write_text("okko:231072:65536\n", encoding="utf-8")
    monkeypatch.setattr(wizard_module, "SUBUID_FILE", subuid)
    monkeypatch.setattr(wizard_module, "SUBGID_FILE", subgid)
    monkeypatch.setenv("USER", "okko")

    setup = wizard_module.Setup(
        audit_log=True,
        audit_storage="filesystem",
        audit_log_path="./audit",
        audit_rotation="logrotate",
        docker_mode="rootless",
    )
    policy = wizard_module.render_logrotate_file(setup, tmp_path)

    uid = 165536 + wizard_module.WEB_IMAGE_UID - 1
    gid = 231072 + wizard_module.WEB_IMAGE_UID - 1
    assert f"create 0600 {uid} {gid}" in policy
    assert f"{os.path.realpath(tmp_path)}/audit/audit.log {{" in policy
    assert "./audit/audit.log {" not in policy
    assert not any(
        str(subuid) in warning for warning in wizard_module.check_consistency(setup)
    )

    # A user with no range is told, rather than handed a policy that
    # silently names the wrong owner.
    monkeypatch.setenv("USER", "nobody-here")
    monkeypatch.setenv("LOGNAME", "nobody-here")
    monkeypatch.setattr(os, "getuid", lambda: 4242)
    assert any(str(subuid) in warning for warning in wizard_module.check_consistency(setup))

    setup.docker_mode = "rootful"
    assert f"create 0600 {wizard_module.WEB_IMAGE_UID} {wizard_module.WEB_IMAGE_UID}" in (
        wizard_module.render_logrotate_file(setup, tmp_path)
    )


def test_a_rootless_port_that_hides_the_client_address_is_pointed_out() -> None:
    """The default rootless port driver makes every visitor the same address."""
    exposed = wizard_module.Setup(docker_mode="rootless", bind_address="0.0.0.0")  # nosec B104
    assert any(
        "slirp4netns" in warning for warning in wizard_module.check_consistency(exposed)
    )
    # Behind a proxy on the host that sets X-Forwarded-For, nothing is lost.
    local = wizard_module.Setup(docker_mode="rootless", bind_address="127.0.0.1")
    assert not any("slirp4netns" in warning for warning in wizard_module.check_consistency(local))
    rootful = wizard_module.Setup(docker_mode="rootful", bind_address="0.0.0.0")  # nosec B104
    assert not any(
        "slirp4netns" in warning for warning in wizard_module.check_consistency(rootful)
    )


def test_a_rerun_moves_a_remembered_authentik_pin_to_the_newer_patch(tmp_path: Path) -> None:
    """
    The pin is remembered like every other answer, and a patch is not a decision.

    Re-running a newer wizard against an existing deployment used to keep
    writing the Authentik release it was first set up with, security fixes
    and all. A newer patch of the same series is taken; a newer series is
    only pointed out, because it can carry migrations worth reading first.
    """
    year, month, patch = wizard_module._authentik_release(wizard_module.AUTHENTIK_TAG)
    answers = tmp_path / wizard_module.answers_filename("docker-compose.yml")

    if patch:
        older_patch = f"{year}.{month}.{patch - 1}"
        answers.write_text(
            json.dumps({"deploy_authentik": True, "authentik_tag": older_patch}),
            encoding="utf-8",
        )
        assert _run(tmp_path, "--force") == 0
        server = _compose(tmp_path)["services"]["authentik_server"]
        assert server["image"].endswith(f":{wizard_module.AUTHENTIK_TAG}")

    older_series = f"{year}.{month - 1 if month > 1 else 12}.5"
    setup = wizard_module.Setup(deploy_authentik=True, authentik_tag=older_series)
    assert wizard_module.follow_authentik_patch(setup) is None
    assert setup.authentik_tag == older_series
    assert any(older_series in warning for warning in wizard_module.check_consistency(setup))

    # A pin somebody moved *ahead* of the wizard, or named oddly, is theirs.
    for tag in (f"{year}.{month}.{patch + 1}", "latest"):
        ahead = wizard_module.Setup(deploy_authentik=True, authentik_tag=tag)
        assert wizard_module.follow_authentik_patch(ahead) is None
        assert ahead.authentik_tag == tag


def test_the_bundled_provider_leaves_a_person_only_a_password_and_a_second_factor_to_choose(
    tmp_path: Path,
) -> None:
    """
    Nothing about the bundled Authentik is set up by clicking in its interface.

    It used to end in instructions: set akadmin's password at the initial-setup
    flow - which whoever reached it first could do instead - create each
    account, put the operator in the right group, and turn on a second factor
    by editing a flow. The wizard now closes the initial-setup flow with a
    generated bootstrap password, copies the blueprints that require a second
    factor and provide an invitation-only enrollment flow, and prints the link
    each listed person opens to choose a password and enrol an authenticator.
    """
    setup = wizard_module.Setup(
        enable_mcp=True,
        mcp_auth_enabled=True,
        admin_enabled=True,
        admin_users="okko",
        authentik_accounts="alice;okko",
        deploy_authentik=True,
        public_base_url="https://scan.example.com",
    )
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)
    wizard_module.write_files(setup, tmp_path / "docker-compose.yml", tmp_path / ".env")

    blueprints = tmp_path / "authentik" / "blueprints"
    assert (blueprints / "opencloud-mfa.yaml").is_file()
    assert (blueprints / "opencloud-enrollment.yaml").is_file()

    env = _env(tmp_path)
    token = env["AUTHENTIK_ENROLLMENT_TOKEN"]
    assert str(uuid.UUID(token)) == token
    assert len(env["AUTHENTIK_BOOTSTRAP_PASSWORD"]) >= 32

    compose_text = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    # Both credentials by reference only.
    assert token not in compose_text
    assert env["AUTHENTIK_BOOTSTRAP_PASSWORD"] not in compose_text
    assert "/if/flow/initial-setup/" not in compose_text

    document = yaml.safe_load(compose_text)
    for name in ("authentik_server", "authentik_worker"):
        environment = document["services"][name]["environment"]
        assert environment["COS_AUTHENTIK_ENROLLMENT_TOKEN"] == "${AUTHENTIK_ENROLLMENT_TOKEN:-}"
        assert environment["AUTHENTIK_BOOTSTRAP_PASSWORD"] == "${AUTHENTIK_BOOTSTRAP_PASSWORD:-}"
        assert environment["COS_AUTHENTIK_ACCOUNTS"] == "alice;okko"
        # What puts an enrolled operator into the group /admin is bound to.
        assert environment["COS_WEB_ADMIN_USERS"] == "okko"

    lines = wizard_module.enrollment_instructions(setup)
    instructions = "\n".join(lines)
    # The token is a credential: printed, it outlives the run in scrollback
    # and CI logs. What is printed assembles the link from .env instead.
    assert token not in instructions
    assert "?itoken=<AUTHENTIK_ENROLLMENT_TOKEN>" in instructions
    command = next(line.strip() for line in lines if "sed -n" in line)
    link = subprocess.run(  # nosec B602 - the command the wizard prints, run as printed
        command, shell=True, cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert link == (
        f"{setup.authentik_url.rstrip('/')}{wizard_module.AUTHENTIK_ENROLLMENT_PATH}?itoken={token}"
    )
    assert "second factor" in instructions
    assert "alice" in instructions and "okko" in instructions

    # A re-run is an edit: the link that was already sent keeps working.
    assert _run(tmp_path, "--force") == 0
    assert _env(tmp_path)["AUTHENTIK_ENROLLMENT_TOKEN"] == token

    # A deployment without Authentik carries none of it.
    plain = wizard_module.Setup(enable_mcp=True)
    wizard_module._generate_unattended(plain)
    wizard_module._finalise(plain)
    assert plain.authentik_enrollment_token == ""
    assert plain.authentik_bootstrap_password == ""
    assert wizard_module.enrollment_instructions(plain) == []
    elsewhere = tmp_path / "plain"
    wizard_module.write_files(plain, elsewhere / "docker-compose.yml", elsewhere / ".env")
    assert not (elsewhere / "authentik").exists()
    assert "AUTHENTIK_ENROLLMENT_TOKEN" not in (elsewhere / ".env").read_text(encoding="utf-8")


def test_the_enrollment_link_stands_apart_and_reads_right_for_one_name() -> None:
    """It is the output that has to reach somebody else, and was scrolled past."""
    one = wizard_module.Setup(
        enable_mcp=True, deploy_authentik=True, authentik_accounts="scanokko"
    )
    wizard_module._generate_unattended(one)
    wizard_module._finalise(one)
    lines = wizard_module.enrollment_instructions(one)
    text = " ".join(line.strip() for line in lines)

    assert any("ENROLLMENT LINK" in line for line in lines)
    # Set between two rules: one carrying the title, one closing the block.
    assert sum(1 for line in lines if "\u2501\u2501\u2501\u2501" in line) == 2
    # The command comes before the placeholder it replaces.
    command = next(i for i, line in enumerate(lines) if "sed -n" in line)
    placeholder = next(i for i, line in enumerate(lines) if "<AUTHENTIK_ENROLLMENT_TOKEN>" in line)
    assert command < placeholder
    assert "Send it to scanokko. It asks for that username" in text
    assert "each of" not in text
    assert "one of those usernames" not in text

    several = wizard_module.Setup(
        enable_mcp=True, deploy_authentik=True, authentik_accounts="alice;sam;okko"
    )
    wizard_module._generate_unattended(several)
    wizard_module._finalise(several)
    text = " ".join(
        line.strip() for line in wizard_module.enrollment_instructions(several)
    )
    assert "Send it to alice, sam and okko. It asks for one of those usernames" in text
    assert "Each name can be claimed once" in text


def test_an_operator_is_always_someone_who_can_enrol() -> None:
    """
    The guest list for /admin is useless to a name the enrollment link refuses.

    Everybody on COS_WEB_ADMIN_USERS is added to the accounts that may enrol,
    once, so the two lists cannot disagree in the direction that locks an
    operator out. A token that is no UUID - it becomes an invitation's primary
    key - is replaced rather than failing the whole blueprint, and a stack that
    names nobody is warned about.
    """
    setup = wizard_module.Setup(
        admin_enabled=True,
        admin_users="okko;carol",
        authentik_accounts="alice;okko",
        deploy_authentik=True,
        authentik_enrollment_token="not-a-uuid",
    )
    wizard_module._finalise(setup)
    assert setup.authentik_accounts == "alice;okko;carol"
    assert str(uuid.UUID(setup.authentik_enrollment_token)) == setup.authentik_enrollment_token
    assert not any("admits nobody" in w for w in wizard_module.check_consistency(setup))

    # Only an area that exists contributes its guest list.
    no_area = wizard_module.Setup(
        enable_mcp=True, admin_users="okko", deploy_authentik=True
    )
    wizard_module._finalise(no_area)
    assert no_area.authentik_accounts == ""
    assert any("admits nobody" in w for w in wizard_module.check_consistency(no_area))

    assert wizard_module._usernames("alice; bob.smith@example.com") is None
    assert wizard_module._usernames("alice bob") is not None
    assert wizard_module._usernames("alice;'); drop") is not None


# --- the bundled provider follows the sign-in -------------------------------
def _provider_default_when_asked(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, object]
) -> list[bool]:
    """Answer only what is named, and record what the provider question offered."""
    offered: list[bool] = []

    def ask(self, question, **_) -> None:
        if question.key == "deploy_authentik":
            offered.append(self.setup.deploy_authentik)
        if question.key in answers:
            setattr(self.setup, question.key, answers[question.key])

    monkeypatch.setattr(wizard_module.Wizard, "ask", ask)
    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: "")
    return offered


@pytest.mark.parametrize("switched_on", ["admin_enabled", "mcp_auth_enabled"])
def test_switching_on_a_sign_in_offers_the_bundled_provider_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, switched_on: str
) -> None:
    """Most deployments asking for /admin or a sign-in on /mcp have no provider yet."""
    offered = _provider_default_when_asked(
        monkeypatch, {switched_on: True, "admin_users": "okko"}
    )

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    assert offered == [True]
    assert [name for name in _compose(tmp_path)["services"] if name.startswith("authentik")]


def test_no_sign_in_leaves_the_provider_question_at_no(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two containers and a database are not a default for a stack nobody signs in to."""
    offered = _provider_default_when_asked(monkeypatch, {})

    assert wizard_module.main(["--output-dir", str(tmp_path)]) == 0

    assert offered == [False]
    assert not [name for name in _compose(tmp_path)["services"] if name.startswith("authentik")]


def test_an_earlier_no_to_the_provider_is_not_overturned_by_an_unchanged_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running over a deployment with its own provider must not add Authentik to it."""
    (tmp_path / wizard_module.answers_filename("docker-compose.yml")).write_text(
        json.dumps({"admin_enabled": True, "admin_users": "okko", "deploy_authentik": False}),
        encoding="utf-8",
    )
    offered = _provider_default_when_asked(monkeypatch, {})

    wizard_module.main(["--output-dir", str(tmp_path), "--force"])

    assert offered == [False]

    # And the positive half: the same area switched on in this run does.
    setup = wizard_module.Setup()
    assert wizard_module._offer_authentik(setup, before=False) is False
    setup.admin_enabled = True
    assert wizard_module._offer_authentik(setup, before=False) is True
    assert setup.deploy_authentik


# --- presentation -----------------------------------------------------------
def test_no_escape_reaches_a_pipe_a_log_or_a_no_color_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A captured run is read by tests and grep, which compare the plain text."""

    class Terminal:
        def isatty(self) -> bool:
            return True

    class Pipe:
        def isatty(self) -> bool:
            return False

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(wizard_module.os, "name", "posix")

    assert wizard_module._colour_wanted(Terminal())
    assert not wizard_module._colour_wanted(Pipe())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not wizard_module._colour_wanted(Terminal())
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    assert not wizard_module._colour_wanted(Terminal())

    plain = wizard_module.Style(enabled=False)
    painted = wizard_module.Style(enabled=True)
    assert plain.bold("Images") == "Images"
    assert painted.bold("Images") == "\033[1mImages\033[0m"
    for line in wizard_module.banner("Title", "A subtitle.", plain):
        assert "\033" not in line


def test_a_section_heading_shows_how_far_through_the_walk_it_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A long walk that says nothing about how much is left is abandoned halfway."""
    printed = _typed(monkeypatch, ["rest"])
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))
    section = wizard_module.build_sections(wizard.setup)[2]

    wizard.heading(section, 3, 12)

    assert any(section.title in line for line in printed)
    assert any("Step 3 of 12" in line for line in printed)
    assert wizard_module.progress_bar(0, 12).endswith("  0%")
    assert wizard_module.progress_bar(12, 12).endswith("100%")
    assert wizard_module.progress_bar(6, 12, width=10).startswith("█" * 5 + "░" * 5)


# --- motion -----------------------------------------------------------------
class _Screen(io.StringIO):
    """A stream that admits to being a terminal, so the effects run."""

    def isatty(self) -> bool:
        return True


def test_an_unpainted_run_writes_no_frame_and_no_carriage_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The effects are decoration; the text a pipe reads is the text it always was."""
    plain = wizard_module.Style(enabled=False)
    screen = _Screen()

    wizard_module.sweep_rule("Images", plain, stream=screen)
    throbber = wizard_module.Throbber("Waiting ", plain, stream=screen)
    for _ in range(5):
        throbber.tick()
    throbber.finish(True, "The service is up.")

    written = screen.getvalue()
    assert "\033" not in written
    assert "\r" not in written
    # The rule settles into exactly the line that would have been printed.
    assert written.splitlines()[0] == wizard_module.rule("Images", plain)
    # Five ticks drew nothing: the verdict is the only line the wait leaves.
    assert written.splitlines()[1:] == ["  ✔ The service is up."]


def test_a_section_rule_settles_into_the_rule_it_would_have_printed() -> None:
    """A heading that moves is where the eye lands; it must still be the same heading."""
    painted = wizard_module.Style(enabled=True)
    screen = _Screen()

    wizard_module.sweep_rule("Reachability", painted, stream=screen)

    written = screen.getvalue()
    assert written.count("\r") > 1, "the sweep is drawn over itself, not down the page"
    assert written.endswith("\n") and written.count("\n") == 1
    # Whatever the sweep did, the line left behind is the ordinary rule.
    assert written.rsplit("\r", 1)[-1] == wizard_module.rule("Reachability", painted) + "\n"


def test_the_spinner_turns_into_its_verdict_rather_than_vanishing() -> None:
    """A spinner that stops leaves nothing to read; the line that spun says how it went."""
    painted = wizard_module.Style(enabled=True)
    screen = _Screen()

    throbber = wizard_module.Throbber("Waiting for the stack ", painted, stream=screen)
    for _ in range(3):
        throbber.tick()
    throbber.finish(True, "The service is up.")
    frames = [frame for frame in screen.getvalue().split("\r") if frame.strip()]

    assert any("⠋" in frame for frame in frames)
    assert any("⠙" in frame for frame in frames)
    assert "✔" in frames[-1] and "The service is up." in frames[-1]
    # The tick replaces the last frame in place instead of printing under it.
    assert "⠹" not in frames[-1]

    failed = _Screen()
    beaten = wizard_module.Throbber("Waiting ", painted, stream=failed)
    beaten.tick()
    beaten.finish(False, "No answer yet.")
    assert "✘" in failed.getvalue().split("\r")[-1]


def test_the_spinner_is_redrawn_between_polls_not_once_per_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A three second gap between frames reads as a hung spinner, not a working one."""
    ticks: list[int] = []
    clock = iter([0.0] + [step * 0.05 for step in range(400)])
    monkeypatch.setattr(wizard_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(wizard_module.time, "sleep", lambda seconds: None)

    def refuse(url: str, timeout: float = 0) -> Any:
        raise OSError("not up yet")

    monkeypatch.setattr(wizard_module.urllib.request, "urlopen", refuse)

    assert not wizard_module._wait_until_healthy(
        "http://127.0.0.1:8080/healthz", timeout=6, interval=3, on_wait=lambda: ticks.append(1)
    )
    assert len(ticks) > 6, "the wait is redrawn many times inside one poll interval"


def test_the_summary_is_carded_on_a_terminal_and_listed_everywhere_else() -> None:
    """The plain list is what a pipe and every test reads; the card is for the eye."""
    setup = wizard_module.Setup()
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)
    painted = wizard_module.Style(enabled=True)

    cards = wizard_module.summary_cards(setup, painted, width=100)

    assert cards is not None
    # Every border and row is the same width, or the box has corners hanging off.
    assert len({wizard_module._visible(line) for line in cards}) == 1
    assert any("╭─ Images " in line for line in cards)
    assert any("[image_source]" in line for line in cards)
    # A pane too narrow for a row gets the list rather than a broken box.
    assert wizard_module.summary_cards(setup, painted, width=30) is None


def test_a_card_narrows_its_labels_before_it_gives_up_on_the_card() -> None:
    """Eighty columns is the common terminal, not a reason to never show a card."""
    setup = wizard_module.Setup()
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)
    painted = wizard_module.Style(enabled=True)

    cards = wizard_module.summary_cards(setup, painted, width=80)

    assert cards is not None
    assert max(wizard_module._visible(line) for line in cards) <= 80


def test_the_line_gauge_reads_the_same_numbers_as_the_bar_it_replaces() -> None:
    """It is the block bar on one row, not a different measurement."""
    assert wizard_module.line_gauge(0, 12).endswith("  0%")
    assert wizard_module.line_gauge(12, 12).endswith("100%")
    assert wizard_module.line_gauge(6, 12, width=10).startswith("━" * 5 + "╌" * 5)
    # Out of range on either side is clamped rather than drawn past the track.
    assert wizard_module.line_gauge(-4, 12).endswith("  0%")
    assert wizard_module.line_gauge(99, 12).endswith("100%")


# --- credentials offered back ------------------------------------------------
def _question(key: str):
    setup = wizard_module.Setup()
    return next(
        question
        for section in wizard_module.build_sections(setup)
        for question in section.questions
        if question.key == key
    )


def test_a_second_run_offers_the_smtp_password_back_masked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running reads .env back, and a screen share must not show what it holds."""
    password = "correct-horse-battery-staple"
    (tmp_path / ".env").write_text(f"AUTHENTIK_EMAIL_PASSWORD={password}\n", encoding="utf-8")
    setup = wizard_module.Setup()
    wizard_module._read_existing_env(setup, tmp_path / ".env")
    printed: list[str] = []
    prompts: list[str] = []
    monkeypatch.setattr(wizard_module.Wizard, "say", lambda self, text="": printed.append(text))

    def read(self, prompt: str) -> str:
        prompts.append(prompt)
        return ""

    monkeypatch.setattr(wizard_module.Wizard, "_read", read)
    wizard = wizard_module.Wizard(setup, style=wizard_module.Style(False))

    wizard.ask(_question("smtp_password"))

    assert not any(password in line for line in printed + prompts)
    assert wizard_module.MASKED in prompts[0]
    # Enter keeps the credential it could not see.
    assert setup.smtp_password == password

    # And typing replaces it, still without the new one being repeated.
    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: "a-new-app-password")
    wizard.ask(_question("smtp_password"))
    assert setup.smtp_password == "a-new-app-password"
    assert not any("a-new-app-password" in line for line in printed)


def test_every_credential_is_masked_and_nothing_that_is_not_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An issuer URL hidden behind a mask is one nobody can check before writing it."""
    prompts: list[str] = []

    def read(self, prompt: str) -> str:
        prompts.append(prompt)
        return ""

    monkeypatch.setattr(wizard_module.Wizard, "say", lambda self, text="": None)
    monkeypatch.setattr(wizard_module.Wizard, "_read", read)
    for key in ("smtp_password", "purge_token", "encryption_key", "admin_proxy_secret"):
        assert key in wizard_module.CREDENTIALS
    assert "mcp_auth_issuer" not in wizard_module.CREDENTIALS

    setup = wizard_module.Setup(
        purge_token="f" * 64, mcp_auth_issuer="https://sso.example.com/application/o/scan/"
    )
    wizard = wizard_module.Wizard(setup, style=wizard_module.Style(False))
    wizard.ask(_question("purge_token"))
    wizard.ask(_question("mcp_auth_issuer"))

    assert "f" * 64 not in prompts[0] and wizard_module.MASKED in prompts[0]
    assert "https://sso.example.com/application/o/scan/" in prompts[1]
    # Nothing set yet is nothing to hide: the prompt still says so.
    empty = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))
    empty.ask(_question("smtp_password"))
    assert "[unset]" in prompts[2]


def test_a_credential_is_typed_without_an_echo_at_a_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What is typed at a password prompt lands in the scrollback otherwise."""
    hidden: list[str] = []
    monkeypatch.setattr(wizard_module.sys.stdin, "isatty", lambda: True, raising=False)

    def getpass(prompt: str) -> str:
        hidden.append(prompt)
        return "typed"

    monkeypatch.setattr(wizard_module.getpass, "getpass", getpass)
    monkeypatch.setattr(
        wizard_module.Wizard, "_read", lambda self, prompt: pytest.fail("echoed read")
    )
    monkeypatch.setattr(wizard_module.Wizard, "say", lambda self, text="": None)
    setup = wizard_module.Setup()
    wizard = wizard_module.Wizard(setup, style=wizard_module.Style(False))

    wizard.ask(_question("smtp_password"))

    assert hidden and setup.smtp_password == "typed"



# --- how much is asked --------------------------------------------------------
def test_a_quick_setup_asks_only_what_a_deployment_cannot_be_right_without(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fifty questions is where people give up; the summary still reaches the rest."""
    asked = _questions_asked(monkeypatch, {"admin_enabled": True, "admin_users": "okko"})

    assert wizard_module.main(["--output-dir", str(tmp_path), "--mode", "quick"]) == 0

    assert {"host_port", "public_base_url", "admin_enabled", "reverse_proxy"} <= set(asked)
    # What the answers bring into play still comes with them.
    assert "authentik_accounts" in asked
    for key in ("result_ttl", "max_workers", "allow_indexing", "audit_log", "redis_maxmemory"):
        assert key not in asked, key


def test_a_private_setup_starts_from_the_private_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The estate scanning its own network should not have to find six settings by name."""
    asked = _questions_asked(monkeypatch, {})

    assert wizard_module.main(["--output-dir", str(tmp_path), "--mode", "private"]) == 0

    worker = _compose(tmp_path)["services"]["arq_worker"]["environment"]
    assert worker["COS_WEB_ALLOW_PRIVATE_TARGETS"] == "true"
    assert "allow_private_targets" not in asked

    public = tmp_path / "public"
    _questions_asked(monkeypatch, {})
    assert wizard_module.main(["--output-dir", str(public), "--mode", "quick"]) == 0
    assert _compose(public)["services"]["arq_worker"]["environment"][
        "COS_WEB_ALLOW_PRIVATE_TARGETS"
    ] == "false"


def test_the_first_run_defaults_to_quick_and_an_edit_to_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Somebody re-running over a deployment came to change something off the short list."""
    answers = iter(["", "", "3", "nonsense", "private"])
    printed: list[str] = []
    monkeypatch.setattr(wizard_module.Wizard, "_read", lambda self, prompt: next(answers))
    monkeypatch.setattr(wizard_module.Wizard, "say", lambda self, text="": printed.append(text))
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))

    assert REAL_CHOOSE_MODE(wizard) == "quick"
    assert REAL_CHOOSE_MODE(wizard, editing=True) == "full"
    assert REAL_CHOOSE_MODE(wizard) == "full"
    assert REAL_CHOOSE_MODE(wizard) == "private"
    assert any("Answer with the number or the word" in line for line in printed)
    assert wizard_module.Wizard(wizard_module.Setup(), interactive=False).choose_mode() == "full"


def test_a_section_nothing_needs_is_named_as_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A step counter that jumps from 10 to 12 leaves the operator wondering what they missed."""
    printed = _typed(monkeypatch, [])
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))

    wizard_module.run_questions(wizard)

    skipped = [line for line in printed if "Skipped" in line]
    assert any("Mail" in line for line in skipped)
    assert any("Step 12 of 13" in line for line in printed)
    assert not any("Step 11 of 13" in line for line in printed)
    # A section that was asked is never reported as skipped.
    assert not any("Images" in line for line in skipped)


# --- reading a question -------------------------------------------------------
def test_a_question_opens_with_one_sentence_and_the_rest_is_a_question_mark_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paragraph under every question is a wall; the one who wants it types '?'."""
    printed = _typed(monkeypatch, ["?", ""])
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))
    question = next(
        q for section in wizard_module.build_sections(wizard.setup)
        for q in section.questions if q.key == "smtp_password"
    )
    _, more = wizard_module._first_sentence(question.explain)
    assert more

    wizard.ask(question)

    first_explanation = printed.index(next(line for line in printed if "Password" in line)) + 1
    assert more.split()[-1] not in printed[first_explanation]
    assert any("'?' explains more" in line for line in printed)
    text = " ".join(line.strip() for line in printed)
    assert more.split()[-1] in text
    assert any("docs/authentik.md" in line for line in printed)


def test_a_setting_is_documented_on_the_page_that_explains_it() -> None:
    """A link to the wrong page is a second search the operator did not ask for."""
    assert wizard_module.docs_for("smtp_host").endswith("docs/authentik.md")
    assert wizard_module.docs_for("reverse_proxy_tls").endswith("docs/reverse-proxy.md")
    assert wizard_module.docs_for("redis_password").endswith("docs/redis.md")
    assert wizard_module.docs_for("result_ttl").endswith("docs/webapp.md")
    assert f"/blob/v{wizard_module.wizard_version()}/" in wizard_module.docs_for("result_ttl")


def test_text_is_wrapped_to_a_narrow_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text wrapped for 80 columns re-wraps into a staircase in a 50-column pane."""
    monkeypatch.setattr(
        wizard_module.shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((50, 24))
    )
    printed = _typed(monkeypatch, ["?", ""])
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))
    question = wizard_module.build_sections(wizard.setup)[0].questions[0]

    wizard.ask(question)
    wizard_module.Wizard.heading(wizard, wizard_module.build_sections(wizard.setup)[0], 1, 12)

    assert all(len(line) <= 50 for line in printed if "http" not in line)
    monkeypatch.setattr(
        wizard_module.shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((200, 24))
    )
    assert wizard_module.text_width() == 72
    assert wizard_module.frame_width() == 66


# --- the summary ----------------------------------------------------------------
def test_the_summary_marks_what_differs_from_the_default() -> None:
    """Those are the decisions this deployment made, and the ones worth a second look."""
    setup = wizard_module.Setup(host_port=9443, docker_mode="rootful")
    wizard_module._generate_unattended(setup)
    wizard_module._finalise(setup)

    lines = wizard_module.summarise(setup)
    port = next(line for line in lines if "[host_port]" in line)
    bind = next(line for line in lines if "[bind_address]" in line)
    token = next(line for line in lines if "redis_password" in line)

    assert port.startswith("  * ")
    assert not bind.startswith("  * ")
    # Detected on this host rather than chosen.
    mode = next(line for line in lines if "[docker_mode]" in line)
    assert not mode.startswith("  * ")
    # A generated credential is not a decision, and its value is never shown.
    assert not token.startswith("  * ")
    assert setup.redis_password not in token


# --- before writing -------------------------------------------------------------
def test_a_rerun_shows_what_would_change_and_never_a_credential(tmp_path: Path) -> None:
    """'Overwrite it?' is only answerable by somebody who can see what would change."""
    assert _run(tmp_path) == 0
    compose = tmp_path / "docker-compose.yml"
    setup = wizard_module.Setup()
    wizard_module._read_previous_answers(setup, tmp_path / ".docker-compose.yml.answers.json")
    wizard_module._read_existing_env(setup, tmp_path / ".env")
    wizard_module._finalise(setup)

    assert any("unchanged" in line for line in wizard_module.render_diffs(setup, compose))

    setup.host_port = 9443
    diff = wizard_module.render_diffs(setup, compose)
    assert any(line.strip().startswith("+") and "9443" in line for line in diff)
    assert any(line.strip().startswith("-") and "8811" in line for line in diff)
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    for line in env.splitlines():
        if "=" in line and not line.startswith("#"):
            value = line.split("=", 1)[1]
            assert not any(value in shown for shown in diff)


def test_every_replaced_file_is_kept_and_a_credential_stays_private(tmp_path: Path) -> None:
    """A re-run that goes wrong must be one `mv` away from the deployment that worked."""
    setup = wizard_module.Setup()
    compose, env = tmp_path / "docker-compose.yml", tmp_path / ".env"
    assert wizard_module.backup_existing(setup, compose, env, "first") == []

    assert _run(tmp_path) == 0
    before = env.read_text(encoding="utf-8")
    saved = wizard_module.backup_existing(setup, compose, env, "20260913-120000")

    names = {Path(path).name for path in saved}
    assert "docker-compose.yml.20260913-120000.bak" in names
    assert ".env.20260913-120000.bak" in names
    backup = tmp_path / ".env.20260913-120000.bak"
    assert backup.read_text(encoding="utf-8") == before
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600

    # And the command does it on its own, before replacing anything.
    assert _run(tmp_path, "--force") == 0
    assert list(tmp_path.glob("docker-compose.yml.*.bak"))


# --- the host -------------------------------------------------------------------
def test_a_port_already_in_use_is_pointed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stack that cannot publish its port fails at `up`, long after the questions."""
    import socket

    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    try:
        port = held.getsockname()[1]
        busy = wizard_module.Setup(bind_address="127.0.0.1", host_port=port)
        assert "already in use" in (wizard_module._port_problem(busy) or "")
    finally:
        held.close()

    free = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()
    assert wizard_module._port_problem(wizard_module.Setup(host_port=port)) is None

    monkeypatch.setattr(wizard_module, "_docker_problem", lambda: "no docker")
    busy_host = REAL_CHECK_HOST(wizard_module.Setup(host_port=port))
    assert busy_host == ["no docker"]


def test_the_port_probe_never_binds_every_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checking a port must not open it on all interfaces, even for a moment."""
    import socket

    bound: list[tuple[str, int]] = []
    real_socket = socket.socket

    class RecordingSocket(real_socket):  # type: ignore[misc,valid-type]
        def bind(self, address):  # type: ignore[no-untyped-def]
            bound.append(address)
            return super().bind(address)

    held = real_socket(socket.AF_INET, socket.SOCK_STREAM)
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    try:
        port = held.getsockname()[1]
        monkeypatch.setattr(wizard_module.socket, "socket", RecordingSocket)
        wildcard = wizard_module.Setup(bind_address="0.0.0.0", host_port=port)  # nosec B104
        assert "already in use" in (wizard_module._port_problem(wildcard) or "")
    finally:
        held.close()

    assert bound == [("127.0.0.1", port)]
    assert ("0.0.0.0", port) not in bound  # nosec B104


def test_a_missing_docker_or_compose_plugin_is_pointed_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The files are still worth writing; the operator should know `up` will not run."""
    monkeypatch.setattr(wizard_module.shutil, "which", lambda name: None)
    assert "not installed" in (wizard_module._docker_problem() or "")

    monkeypatch.setattr(wizard_module.shutil, "which", lambda name: "/usr/bin/docker")

    class Result:
        def __init__(self, code: int) -> None:
            self.returncode = code

    monkeypatch.setattr(wizard_module.subprocess, "run", lambda *a, **k: Result(1))
    assert "Compose plugin" in (wizard_module._docker_problem() or "")
    monkeypatch.setattr(wizard_module.subprocess, "run", lambda *a, **k: Result(0))
    assert wizard_module._docker_problem() is None


def test_a_certificate_that_is_not_there_is_pointed_out(tmp_path: Path) -> None:
    """The proxy refuses to start without it, and says so far from the wizard."""
    present = tmp_path / "fullchain.pem"
    present.write_text("certificate", encoding="utf-8")
    setup = wizard_module.Setup(
        reverse_proxy="nginx",
        reverse_proxy_hostname="scan.example.com",
        reverse_proxy_tls=True,
        reverse_proxy_certificate=str(present),
        reverse_proxy_private_key=str(tmp_path / "missing.pem"),
    )

    problems = wizard_module._certificate_problems(setup)

    assert len(problems) == 1
    assert "missing.pem" in problems[0]
    assert str(present) not in problems[0]


# --- after writing --------------------------------------------------------------
class _Compose:
    """Stands in for `docker compose`, recording what it was asked to do."""

    def __init__(self, config_code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.config_code = config_code

    def __call__(self, command, **_):
        self.calls.append(list(command))

        class Result:
            returncode = self.config_code if "config" in command else 0
            stdout = ""
            stderr = "services.web_app: invalid" if "config" in command else ""

        return Result()


def _start_offer(monkeypatch: pytest.MonkeyPatch, answers: list[str], compose: _Compose) -> list[str]:
    printed = _typed(monkeypatch, answers)
    monkeypatch.setattr(wizard_module.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(wizard_module.subprocess, "run", compose)
    monkeypatch.setattr(wizard_module, "_wait_until_healthy", lambda url, **_: True)
    return printed


def test_the_written_stack_is_checked_and_started_only_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starting containers is the first thing done outside the directory it was given."""
    compose = _Compose()
    printed = _start_offer(monkeypatch, ["y", "y"], compose)
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))

    REAL_OFFER_TO_START(wizard, wizard.setup, tmp_path / "docker-compose.yml")

    assert any("config" in call for call in compose.calls)
    assert any("up" in call for call in compose.calls)
    assert any("The service is up" in line for line in printed)

    declined = _Compose()
    _start_offer(monkeypatch, ["y", ""], declined)
    REAL_OFFER_TO_START(wizard, wizard.setup, tmp_path / "docker-compose.yml")
    assert not any("up" in call for call in declined.calls)


def test_a_rejected_file_or_a_pending_step_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stack started before its bind mount is handed over fails on its first write."""
    rejected = _Compose(config_code=1)
    printed = _start_offer(monkeypatch, ["y", "y"], rejected)
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))
    REAL_OFFER_TO_START(wizard, wizard.setup, tmp_path / "docker-compose.yml")
    assert not any("up" in call for call in rejected.calls)
    assert any("invalid" in line for line in printed)

    waiting = _Compose()
    printed = _start_offer(monkeypatch, ["y", "y"], waiting)
    bound = wizard_module.Setup(redis_persistence="filesystem")
    REAL_OFFER_TO_START(
        wizard_module.Wizard(bound, style=wizard_module.Style(False)),
        bound,
        tmp_path / "docker-compose.yml",
    )
    assert not any("up" in call for call in waiting.calls)
    assert any("ownership commands" in line for line in printed)

    silent = _Compose()
    _start_offer(monkeypatch, ["y", "y"], silent)
    unattended = wizard_module.Wizard(wizard_module.Setup(), interactive=False)
    REAL_OFFER_TO_START(unattended, unattended.setup, tmp_path / "docker-compose.yml")
    assert silent.calls == []


# --- answers carried between hosts ------------------------------------------------
def test_answers_printed_on_one_host_reproduce_the_deployment_on_another(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same deployment twice should not mean answering fifty questions twice."""
    first = tmp_path / "first"
    assert _run(first, "--reverse-proxy", "caddy", "--proxy-hostname", "scan.example.com") == 0
    capsys.readouterr()

    assert wizard_module.main(["--output-dir", str(first), "--print-answers"]) == 0
    printed = capsys.readouterr().out
    answers = json.loads(printed)
    assert answers["reverse_proxy"] == "caddy"
    assert not set(answers) & set(wizard_module.SECRET_VARIABLES)
    env = (first / ".env").read_text(encoding="utf-8")
    for line in env.splitlines():
        if "=" in line and not line.startswith("#"):
            assert line.split("=", 1)[1] not in printed

    exported = tmp_path / "answers.json"
    exported.write_text(printed, encoding="utf-8")
    second = tmp_path / "second"
    assert _run(second, "--answers", str(exported)) == 0
    assert _compose(second)["services"]["web_app"]["ports"] == _compose(first)["services"]["web_app"]["ports"]
    assert (second / "opencloud-scan-caddyfile").is_file() or list(second.glob("*caddy*"))

    # Printing writes nothing at all.
    empty = tmp_path / "empty"
    assert wizard_module.main(["--output-dir", str(empty), "--print-answers"]) == 0
    assert not empty.exists()


def test_an_answers_file_with_nothing_in_it_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A typo in the path would otherwise start quietly from the defaults."""
    assert _run(tmp_path, "--answers", str(tmp_path / "missing.json")) == 2
    assert "Nothing usable" in capsys.readouterr().err
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"not_a_setting": 1, "host_port": true}', encoding="utf-8")
    assert _run(tmp_path, "--answers", str(foreign)) == 2
    assert not (tmp_path / "docker-compose.yml").exists()


# --- the version ------------------------------------------------------------------
def test_a_checkout_reports_the_version_in_its_pyproject(tmp_path: Path) -> None:
    """The version has one source; a checkout and the web bundle both carry it."""
    import re

    text = (WIZARD_PATH.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    expected = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert expected
    assert wizard_module.wizard_version() == expected.group(1)
    assert wizard_module.version_line() == f"setup-wizard.py {expected.group(1)}"

    # Somebody else's project beside a copied wizard is not this one's version.
    foreign = tmp_path / "pyproject.toml"
    foreign.write_text('[project]\nname = "other"\nversion = "9.9.9"\n', encoding="utf-8")
    assert wizard_module._pyproject_version(foreign) == ""
    assert wizard_module._pyproject_version(tmp_path / "absent.toml") == ""


# ------------------------------------------------------------ abuse protection


def _environments(setup) -> tuple[dict, dict]:
    document = yaml.safe_load(wizard_module.render_compose_file(setup, "compose.yml"))
    services = document["services"]
    return services["web_app"]["environment"], services["arq_worker"]["environment"]


def test_the_abuse_limits_the_operator_chose_reach_both_containers() -> None:
    """The worker imposes the block and the web service reads it; they must agree."""
    setup = wizard_module.Setup(
        probe_limit=3, probe_window=120, probe_block=600, probe_block_max=7200,
        probe_repeat_window=3600, daily_scan_limit=20, probe_ipv4_prefix=32,
    )

    web, worker = _environments(setup)

    for environment in (web, worker):
        assert environment["COS_WEB_PROBE_LIMIT"] == "3"
        assert environment["COS_WEB_PROBE_WINDOW"] == "120"
        assert environment["COS_WEB_PROBE_BLOCK"] == "600"
        assert environment["COS_WEB_PROBE_BLOCK_MAX"] == "7200"
        assert environment["COS_WEB_PROBE_REPEAT_WINDOW"] == "3600"
    assert web["COS_WEB_DAILY_SCAN_LIMIT"] == "20"
    assert web["COS_WEB_PROBE_IPV4_PREFIX"] == "32"
    assert web["COS_WEB_DNS_CONSISTENCY_CHECK"] == "true"
    # What only the submission reads stays out of the worker.
    assert "COS_WEB_DAILY_SCAN_LIMIT" not in worker


def test_the_approved_list_is_written_only_for_a_deployment_that_requires_approval() -> None:
    """A list with no approval mode behind it would read as protection that is not there."""
    off_web, _ = _environments(wizard_module.Setup(approved_targets="opencloud.example.com"))
    on_web, _ = _environments(
        wizard_module.Setup(require_approval=True, approved_targets="opencloud.example.com;.example.org")
    )

    assert off_web["COS_WEB_REQUIRE_APPROVAL"] == "false"
    assert "COS_WEB_APPROVED_TARGETS" not in off_web
    assert on_web["COS_WEB_REQUIRE_APPROVAL"] == "true"
    assert on_web["COS_WEB_APPROVED_TARGETS"] == "opencloud.example.com;.example.org"
    assert on_web["COS_WEB_APPROVAL_DNS"] == "true"


def test_the_block_details_are_only_asked_while_there_is_a_block() -> None:
    """With the block off its window and length are questions with no consequence."""
    assert wizard_module._relevant("probe_block", wizard_module.Setup(probe_limit=5))
    assert not wizard_module._relevant("probe_block", wizard_module.Setup(probe_limit=0))
    assert not wizard_module._relevant("approved_targets", wizard_module.Setup())
    assert wizard_module._relevant("approved_targets", wizard_module.Setup(require_approval=True))


def test_an_approved_entry_that_is_not_a_target_is_refused_when_typed() -> None:
    """The service refuses to start on such an entry; the wizard should say so first."""
    assert wizard_module._target_list("opencloud.example.com;.example.org;*.example.net") is None
    assert wizard_module._target_list("203.0.113.0/24;2001:db8::/32") is None
    assert wizard_module._target_list("not a host") is not None
    assert wizard_module._target_list("bad!name.example.com") is not None


def test_an_approval_mode_that_could_approve_nothing_is_warned_about() -> None:
    """Better a warning before writing than a container that exits at startup."""
    stuck = wizard_module.Setup(require_approval=True, approval_dns=False)
    fine = wizard_module.Setup(
        require_approval=True, approval_dns=False, approved_targets="opencloud.example.com"
    )

    assert any("nothing could ever be scanned" in w for w in wizard_module.check_consistency(stuck))
    assert not any("nothing could ever be scanned" in w for w in wizard_module.check_consistency(fine))


def test_the_section_card_lists_every_step_and_marks_the_current_one() -> None:
    """The right column is the whole walk; the operator's place in it is the one that stands out."""
    style = wizard_module.Style(True)
    sections = wizard_module.build_sections(wizard_module.Setup())

    card = wizard_module.step_card(sections[3], sections, 4, {2}, style, width=66)

    assert card is not None
    plain = [wizard_module._ANSI_ESCAPE.sub("", line) for line in card]
    assert len({len(line) for line in plain}) == 1, "every row closes on the same border"
    assert "Step 4 of 13" in plain[1]
    for section in sections:
        assert any(section.title in line for line in plain)
    assert any(f"› {sections[3].title}" in line for line in plain)
    assert any(f"✔ {sections[0].title}" in line for line in plain)
    assert any(f"– {sections[1].title}" in line for line in plain)
    assert any(f"· {sections[4].title}" in line for line in plain)
    assert style.paint(f"› {sections[3].title}", "cyan", "bold") in "".join(card)


def test_the_section_card_gives_way_to_plain_lines_in_a_narrow_terminal() -> None:
    """Two columns in 50 characters would wrap their borders into a mess."""
    sections = wizard_module.build_sections(wizard_module.Setup())

    assert wizard_module.step_card(sections[0], sections, 1, (), wizard_module.Style(True), 50) is None


def test_a_heading_draws_the_card_only_on_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Piped or under a test the heading stays the plain lines anybody greps a log for."""
    printed = _typed(monkeypatch, [])
    sections = wizard_module.build_sections(wizard_module.Setup())
    plain = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))

    plain.heading(sections[0], 1, len(sections), sections=sections)

    assert not any("┬" in line for line in printed)
    assert any("Step 1 of" in line for line in printed)


@pytest.mark.parametrize("number", [0, -1, 14, 99])
def test_the_section_card_refuses_a_step_outside_the_walk(number: int) -> None:
    """A position the list cannot highlight falls back to the plain lines, not a wrong card."""
    sections = wizard_module.build_sections(wizard_module.Setup())

    assert wizard_module.step_card(sections[0], sections, number, (), wizard_module.Style(True), 66) is None


def test_the_section_card_with_no_sections_does_not_raise() -> None:
    """An empty walk is None rather than max() of an empty sequence."""
    section = wizard_module.build_sections(wizard_module.Setup())[0]

    assert wizard_module.step_card(section, [], 1, (), wizard_module.Style(True), 66) is None


def test_the_last_step_marks_every_earlier_one_done() -> None:
    """At the final section nothing is still ahead."""
    sections = wizard_module.build_sections(wizard_module.Setup())
    card = wizard_module.step_card(
        sections[-1], sections, len(sections), (), wizard_module.Style(False), 66
    )

    assert card is not None
    assert not any(" · " in line for line in card)
    assert sum("✔" in line for line in card) == len(sections) - 1


def test_the_current_step_is_highlighted_even_when_it_was_once_skipped() -> None:
    """Going back into a section passed over earlier shows it as current, not skipped."""
    sections = wizard_module.build_sections(wizard_module.Setup())
    card = wizard_module.step_card(sections[1], sections, 2, {2}, wizard_module.Style(False), 66)

    assert card is not None
    assert any(f"› {sections[1].title}" in line for line in card)
    assert not any(f"– {sections[1].title}" in line for line in card)


def test_a_long_summary_wraps_inside_the_card_and_keeps_every_border() -> None:
    """A summary longer than the column wraps; no row runs past the right border."""
    sections = wizard_module.build_sections(wizard_module.Setup())
    section = wizard_module.Section(title=sections[0].title, summary="word " * 80)
    card = wizard_module.step_card(section, sections, 1, (), wizard_module.Style(False), 66)

    assert card is not None
    assert len(card) > len(sections) + 2, "the summary made the card taller than the list"
    assert len({len(line) for line in card}) == 1


def test_the_card_appears_at_the_narrowest_width_it_fits() -> None:
    """The fallback is for terminals that truly cannot hold it, not a generous margin."""
    sections = wizard_module.build_sections(wizard_module.Setup())
    right = max(len(section.title) for section in sections) + 2
    fits = right + 7 + wizard_module._STEP_CARD_LEFT_FLOOR
    style = wizard_module.Style(False)

    assert wizard_module.step_card(sections[0], sections, 1, (), style, fits) is not None
    assert wizard_module.step_card(sections[0], sections, 1, (), style, fits - 1) is None
    # Plus the two-space indent, as banner() draws it: frame_width() already
    # leaves the terminal four columns of slack for that.
    card = wizard_module.step_card(sections[0], sections, 1, (), style, fits)
    assert {len(line) for line in card} == {fits + 2}


def test_a_quick_walk_marks_its_skipped_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_questions hands the heading the sections it passed over, so the card can mark them."""
    seen: list[set[int]] = []
    monkeypatch.setattr(
        wizard_module.Wizard,
        "heading",
        lambda self, section, number=0, total=0, *, sections=(), skipped=(): seen.append(set(skipped)),
    )
    _typed(monkeypatch, [])
    wizard = wizard_module.Wizard(wizard_module.Setup(), style=wizard_module.Style(False))

    wizard_module.run_questions(wizard, "quick")

    assert seen, "a quick walk still shows at least one heading"
    assert seen[-1], "a quick walk passes over some sections"
    assert all(earlier <= later for earlier, later in itertools.pairwise(seen)), "skips only accumulate"


def test_an_operator_area_gets_the_in_place_update_and_nothing_else_does() -> None:
    """
    The area's update button needs a tmpfs and the same directory on the web
    service and every worker (ADR 0070); a stack without the area has no
    button, so it gets neither.
    """
    directory = wizard_module.UPDATE_DIRECTORY
    with_area = yaml.safe_load(
        wizard_module.render_compose_file(_admin_setup("nginx"), "compose.yml")
    )
    for service in ("web_app", "arq_worker"):
        definition = with_area["services"][service]
        assert definition["environment"]["COS_WEB_ADMIN_UPDATE_DIR"] == directory
        assert any(mount.startswith(f"{directory}:") for mount in definition["tmpfs"])
    assert with_area["services"]["web_app"]["environment"]["COS_WEB_UPDATE_CHECK"] == "true"

    without = yaml.safe_load(
        wizard_module.render_compose_file(wizard_module.Setup(), "compose.yml")
    )
    for service in ("web_app", "arq_worker"):
        definition = without["services"][service]
        assert "COS_WEB_ADMIN_UPDATE_DIR" not in definition["environment"]
        assert definition["tmpfs"] == ["/tmp:size=16m"]
