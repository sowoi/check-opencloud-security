#!/usr/bin/env python3
"""
Interactive Docker setup for the check-opencloud-security web application.

    cd docker
    ./setup-wizard.py

It asks, one question at a time, for the settings a deployment of the web
application actually has to decide - what the service is reachable at, how
hard it is allowed to scan, who may erase results, whether an AI agent may
use it, whether the images update themselves - explains what each one does
and shows an example answer, and then writes two files:

* ``docker-compose.yml`` - the stack, with every non-secret answer inline and
  commented, so the file explains itself to whoever reads it next;
* ``.env`` - the secrets, owner-readable only, referenced from the compose
  file as ``${NAME}`` and never written into it.

Ask for a sign-in on ``/mcp`` and it asks for the issuer, the audience and the
keys of the provider you already run, which is what an estate that wants one
usually has. Ask for ``--with-authentik`` as well and it provisions a provider
instead: Authentik and its database join the stack, those three values are
derived rather than asked for, and a third file is written - the blueprint,
beside the compose file that mounts it. Nothing of Authentik appears in a
deployment that did not ask for it. Its mail settings are asked for when it
does, because an identity provider that cannot send a password recovery is one
nobody can get back into.

That split is the whole point of the wizard. A compose file is something an
operator commits, pastes into a ticket and copies between hosts; a purge token
and an encryption key are none of those things.

Ask for the audit trail to be kept in a directory on this host and rotated by
the host's own logrotate, and it writes that policy too - beside the compose
file, not into ``/etc/logrotate.d``, because installing it needs root and a
wizard that writes outside the directory it was pointed at is one nobody can
run to see what it would do.

**This is not the plugin's wizard.** ``check-opencloud-security --configure``
sets up a monitoring check against one instance and writes a scanner
configuration file. This script configures a *container deployment* of the web
service and shares nothing with it - no imports, no configuration file, no
settings. It deliberately uses the standard library only, so it runs on a
freshly installed host that has Docker and nothing else.

Nothing is overwritten by surprise: an existing file has to be confirmed, and
the compose files that ship with this project are refused outright, because
the next ``git pull`` would take a hand-made deployment with it. A ``.env``
that is already there is read back instead: its values become the defaults
the questions offer, so re-running the wizard against a live deployment edits
it rather than regenerating every credential it holds.

Non-interactive use, for a test or an unattended install:

    ./setup-wizard.py --non-interactive --preset private --output-dir /srv/scan
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

PROJECT_URL = "https://github.com/sowoi/check-opencloud-security"
DOCKERHUB_IMAGE = "okxo/opencloud-scanner:latest"

# The identity provider this project ships a stack for, and the image tag
# `docker-compose.authentik.yml` pins. Keep the two together: a wizard that
# generates a different version from the file next to it is a support case.
AUTHENTIK_IMAGE = "ghcr.io/goauthentik/server"
AUTHENTIK_TAG = "2026.8.0"
BLUEPRINT_SOURCE = REPO_ROOT / "authentik" / "blueprints" / "opencloud-scanner.yaml"
BLUEPRINT_RELATIVE = Path("authentik") / "blueprints" / "opencloud-scanner.yaml"

# Where the two things a deployment can choose to keep live *inside* the
# containers. Both are mount points rather than paths in an image layer: a
# read-only container cannot write to either without one, which is the whole
# reason these are the only two writable places in the stack.
AUDIT_LOG_DIRECTORY = "/var/log/opencloud-scan"
AUDIT_LOG_FILENAME = "audit.log"
REDIS_DATA_DIRECTORY = "/data"

# The named volumes, before Compose prefixes them with the project name.
AUDIT_VOLUME = "audit_log"
REDIS_VOLUME = "redis_data"

# Who has to own a host directory for the container to write to it. Docker
# copies a mount point's ownership into a *named* volume, so only a bind mount
# needs the operator to do anything - and a bind mount owned by root is the
# single most common reason a hardened container will not start.
WEB_IMAGE_UID = 10001
REDIS_IMAGE_UID = 999

# Where a deployment keeps things, when it keeps them at all.
STORAGE_CHOICES = ("none", "volume", "filesystem")

# Who rotates the audit file. "service" is this application, by size, and needs
# nothing installed; "logrotate" is the host's own, which is what an estate
# with a retention policy, a compression setting and a backup already has.
ROTATION_CHOICES = ("service", "logrotate")
# The value COS_WEB_AUDIT_LOG_ROTATION takes for the second one. The service
# does not care *which* tool moves the file aside, only that something else
# does and it has to reopen; the wizard asks in terms of the thing an operator
# actually installs.
EXTERNAL_ROTATION = "external"

# The updater a deployment gets when it asks for automatic updates. Unlike
# the identity provider it follows 'latest': the thing that applies updates
# should not be the one thing that never receives one.
WATCHTOWER_IMAGE = "containrrr/watchtower:latest"

# Compose files that ship with the project. Writing over one of them would put
# a deployment's own settings in the way of the next update, so the wizard
# refuses rather than asking.
SHIPPED_COMPOSE_FILES = {
    "docker-compose.yml",
    "docker-compose.dockerhub.yml",
    "docker-compose.authentik.yml",
    "docker-compose.monitoring.yml",
}

YES = {"y", "yes", "j", "ja", "1", "true", "on"}
NO = {"n", "no", "nein", "0", "false", "off"}


class SetupAborted(RuntimeError):
    """Raised when the operator interrupts the wizard."""


# --- what the wizard collects ----------------------------------------------
@dataclass
class Setup:
    """Every answer, with the default a public deployment would want.

    The defaults are the ones in ``docker-compose.yml``: a service open to
    anybody, refusing private targets, running no port scans and keeping no
    log of what was scanned. ``--preset private`` moves them to what an estate
    scanning its own instances needs instead.
    """

    # Where and how the images come from.
    image_source: str = "build"
    image_ref: str = DOCKERHUB_IMAGE
    build_context: str = ".."
    project_name: str = "opencloud-scan"

    # Automatic updates of the pulled images. On, and Watchtower joins the
    # stack; the socket is detected for the user running the wizard, because
    # a rootless Docker serves it somewhere else than /var/run.
    auto_updates: bool = False
    watchtower_socket: str = ""

    # How the service is reached.
    bind_address: str = "127.0.0.1"
    host_port: int = 8811
    public_base_url: str = ""
    trust_forwarded_for: bool = False

    # How long a result lives, and how often somebody may ask for one.
    result_ttl: int = 3600
    ip_rate_limit: int = 10
    ip_rate_window: int = 60
    target_cooldown: int = 300
    max_batch_targets: int = 10

    # The service's whole load on other people's servers.
    max_workers: int = 5
    scan_concurrency: int = 4
    scan_timeout: int = 15
    job_timeout: int = 180

    # What may be scanned.
    allow_private_targets: bool = False
    check_debug_ports: bool = False
    allowed_hosts: str = ""
    ipv6_enabled: bool = False

    # The public face.
    allow_indexing: bool = True
    enable_docs: bool = True
    releases_mode: str = "off"
    releases_token: str = ""

    # The agent-facing endpoint.
    enable_mcp: bool = True
    mcp_allowed_hosts: str = ""
    mcp_max_concurrent_waits: int = 8
    mcp_auth_enabled: bool = False
    mcp_auth_issuer: str = ""
    mcp_auth_audience: str = ""
    mcp_auth_jwks_url: str = ""
    mcp_auth_resource_url: str = ""
    mcp_auth_scopes: str = ""
    mcp_auth_client_secret: str = ""

    # Whether the stack brings its own identity provider. Off: a sign-in is
    # normally checked against one an estate already runs, and two extra
    # containers plus a database to back up is a decision rather than a
    # default. The settings below are read only when it is on.
    deploy_authentik: bool = False
    authentik_url: str = ""
    authentik_slug: str = "opencloud-scanner"
    authentik_tag: str = AUTHENTIK_TAG
    authentik_http_port: int = 9000
    authentik_https_port: int = 9443
    authentik_redirect_uri: str = ""
    authentik_secret_key: str = ""
    authentik_pg_password: str = ""
    authentik_client_id: str = ""
    authentik_client_secret: str = ""

    # Mail, which only Authentik sends: a password recovery, an invitation, an
    # expiring-password notice. The scan service itself sends none.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"
    smtp_timeout: int = 10

    # What is kept, and who may delete it.
    audit_log: bool = False
    audit_log_targets: bool = False
    audit_salt: str = ""
    # Where the audit trail is written. 'none' leaves it on the container's
    # output, which a `docker compose down` takes with it; the other two mount
    # something that outlives the container and point the service at a file in
    # it. An audit trail is the one thing here an operator is asked for months
    # after the fact, so it is the one thing worth surviving.
    audit_storage: str = "none"
    audit_log_path: str = ""
    # Who rotates that file once it is on the host's filesystem: this service,
    # by size, or the logrotate the host already runs for every other log on
    # it. Only ever asked when the trail goes to a host directory - a named
    # volume lives somewhere under Docker's own root, which is not a path a
    # generated logrotate policy has any business naming.
    audit_rotation: str = "service"
    audit_retention_days: int = 30
    purge_token: str = ""
    purge_signing_key: str = ""
    export_signing_key: str = ""
    encrypt_results: bool = False
    encryption_key: str = ""

    redis_maxmemory: str = "256mb"
    redis_password: str = ""
    # Whether Redis writes its keyspace to disk. Off, and it is the cache the
    # rest of the design assumes: every key has a TTL and a restart loses only
    # results that were about to expire. On, and the queue and any scan in
    # flight survive a restart - at the price of a copy of what it holds
    # sitting on a disk.
    redis_persistence: str = "none"
    redis_data_path: str = ""


# Answers a private deployment wants instead: it scans its own network, it is
# not meant to be found, and a log of its own targets is an asset rather than
# a liability.
PRIVATE_PRESET: dict[str, Any] = {
    "allow_private_targets": True,
    "check_debug_ports": True,
    "allow_indexing": False,
    "audit_log": True,
    "audit_log_targets": True,
    # An estate that keeps an audit trail keeps it across a restart, or it has
    # a log that answers questions only until the next update.
    "audit_storage": "volume",
    "ip_rate_limit": 60,
    "target_cooldown": 60,
}

# Which answers are secrets: they go to `.env` and are referenced from the
# compose file, never written into it. The value is the environment variable
# name both files agree on.
SECRET_VARIABLES: dict[str, str] = {
    # Redis holds every live scan and every result still inside its TTL. It is
    # reachable by name from anything that lands on the same Compose network,
    # so it asks for a password as well as sitting on a network of its own -
    # an unauthenticated Redis is one misplaced container away from being a
    # readable copy of everybody's scans.
    "redis_password": "COS_REDIS_PASSWORD",
    "releases_token": "COS_WEB_RELEASES_TOKEN",
    "purge_token": "COS_WEB_PURGE_TOKEN",
    "purge_signing_key": "COS_WEB_PURGE_SIGNING_KEY",
    "export_signing_key": "COS_WEB_EXPORT_SIGNING_KEY",
    "audit_salt": "COS_WEB_AUDIT_SALT",
    "encryption_key": "COS_WEB_ENCRYPTION_KEY_1",
    "mcp_auth_issuer": "COS_WEB_MCP_AUTH_ISSUER",
    "mcp_auth_audience": "COS_WEB_MCP_AUTH_AUDIENCE",
    "mcp_auth_jwks_url": "COS_WEB_MCP_AUTH_JWKS_URL",
    "mcp_auth_resource_url": "COS_WEB_MCP_AUTH_RESOURCE_URL",
    "mcp_auth_scopes": "COS_WEB_MCP_AUTH_SCOPES",
    # Authentik's own. The client ID is not strictly a secret - it is the
    # audience, and every token carries it - but both sides have to agree on
    # it, so it lives beside the secret rather than in two places.
    "authentik_secret_key": "AUTHENTIK_SECRET_KEY",
    "authentik_pg_password": "AUTHENTIK_PG_PASS",
    "authentik_client_id": "AUTHENTIK_CLIENT_ID",
    "authentik_client_secret": "AUTHENTIK_CLIENT_SECRET",
    "smtp_password": "AUTHENTIK_EMAIL_PASSWORD",
}


# --- prompting --------------------------------------------------------------
@dataclass
class Question:
    """One prompt: what it configures, why it matters, and an example answer."""

    key: str
    prompt: str
    explain: str
    example: str
    kind: str = "str"
    """One of ``str``, ``int``, ``bool``, ``choice``."""
    choices: Sequence[str] = ()
    validate: Callable[[str], str | None] = lambda value: None
    generate: int = 0
    """Offer to generate a value of this many random bytes instead of typing
    one. Used for the credentials nobody should invent by hand."""


@dataclass
class Section:
    """A group of questions with a heading and a sentence saying why."""

    title: str
    summary: str
    questions: list[Question] = field(default_factory=list)


def _port(value: str) -> str | None:
    try:
        number = int(value)
    except ValueError:
        return "Enter a whole number, e.g. 8811."
    return None if 1 <= number <= 65535 else "A port must be between 1 and 65535."


def _positive(minimum: int) -> Callable[[str], str | None]:
    def check(value: str) -> str | None:
        try:
            number = int(value)
        except ValueError:
            return f"Enter a whole number, at least {minimum}."
        return None if number >= minimum else f"The smallest useful value is {minimum}."

    return check


def _optional_url(value: str) -> str | None:
    if not value.strip():
        return None
    if not value.startswith(("http://", "https://")):
        return "A URL starts with http:// or https://."
    return None


def _issuer(value: str) -> str | None:
    if not value.strip():
        return None
    if not value.startswith(("http://", "https://")):
        return "An issuer is a URL, e.g. https://sso.example.com/application/o/scan/"
    return None


def _audience(value: str) -> str | None:
    if value.strip():
        return None
    return (
        "An audience is required. Without one, any token the issuer minted "
        "for any other application would open /mcp, and the service refuses "
        "to start rather than serve it that way."
    )


def _memory(value: str) -> str | None:
    return (
        None
        if re.fullmatch(r"\d+(b|k|kb|m|mb|g|gb)?", value.strip(), re.IGNORECASE)
        else "A Redis memory limit looks like 256mb or 1gb."
    )


def _hostname_list(value: str) -> str | None:
    if not value.strip():
        return None
    for item in re.split(r"[;,]", value):
        if item.strip() and re.search(r"\s", item.strip()):
            return "Separate several names with ';', without spaces inside a name."
    return None


def _mail_address(value: str) -> str | None:
    if not value.strip():
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()):
        return "A From address looks like authentik@example.com."
    return None


def _host_directory(value: str) -> str | None:
    """A host directory to bind-mount into a container.

    Absolute, because Compose reads a relative path as being relative to the
    compose file rather than to wherever ``docker compose`` was run, and a
    deployment that keeps its audit trail in a directory nobody can name twice
    keeps it by accident.
    """
    path = value.strip()
    if not path.startswith("/"):
        return "A host directory is absolute, e.g. /srv/opencloud-scan/audit."
    if ":" in path:
        return "A ':' would be read as the start of the mount options."
    return None


def _socket_path(value: str) -> str | None:
    if not value.startswith("/"):
        return "A socket path is absolute, e.g. /var/run/docker.sock."
    return None


def _hex_key(value: str) -> str | None:
    if not value.strip():
        return None
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value.strip()):
        return "An encryption key is exactly 64 hex characters (32 bytes)."
    return None


class Wizard:
    """Asks the questions and remembers the answers."""

    def __init__(self, setup: Setup, *, interactive: bool = True) -> None:
        self.setup = setup
        self.interactive = interactive

    # -- output ------------------------------------------------------------
    def say(self, text: str = "") -> None:
        if self.interactive:
            print(text)

    def heading(self, section: Section) -> None:
        self.say()
        self.say(f"\u2500\u2500 {section.title} " + "\u2500" * max(4, 60 - len(section.title)))
        self.say(f"   {section.summary}")

    # -- input -------------------------------------------------------------
    def _read(self, prompt: str) -> str:
        try:
            return input(prompt)
        except EOFError as error:  # piped input that ran out
            raise SetupAborted("No more input.") from error
        except KeyboardInterrupt as error:
            raise SetupAborted("Interrupted.") from error

    def current(self, key: str) -> Any:
        return getattr(self.setup, key)

    def ask(self, question: Question) -> None:
        """Ask one question and store the answer on the setup."""
        if not self.interactive:
            return

        shown = _format_default(self.current(question.key))
        self.say()
        self.say(f"  {question.prompt}")
        for line in _wrap(question.explain):
            self.say(f"      {line}")
        self.say(f"      Example: {question.example}")
        if question.kind == "bool":
            self.say("      Answer yes or no; true and false are accepted too.")
        if question.choices:
            self.say(f"      One of: {', '.join(question.choices)}")
        if question.generate:
            self.say("      Enter 'generate' and a strong random value is created for you.")

        while True:
            answer = self._read(f"      [{shown}] > ").strip()
            if not answer:
                return
            if question.generate and answer.lower() == "generate":
                setattr(self.setup, question.key, secrets.token_hex(question.generate))
                self.say("      Generated, and written to .env rather than shown here.")
                return
            if question.kind == "bool":
                lowered = answer.lower()
                if lowered in YES:
                    setattr(self.setup, question.key, True)
                    return
                if lowered in NO:
                    setattr(self.setup, question.key, False)
                    return
                self.say("      Answer yes or no - true and false work as well.")
                continue
            if question.kind == "int":
                error = question.validate(answer)
                if error:
                    self.say(f"      {error}")
                    continue
                setattr(self.setup, question.key, int(answer))
                return
            if question.kind == "choice" and answer not in question.choices:
                self.say(f"      Answer one of: {', '.join(question.choices)}")
                continue
            error = question.validate(answer)
            if error:
                self.say(f"      {error}")
                continue
            setattr(self.setup, question.key, answer)
            return

    def confirm(self, prompt: str, *, default: bool = True) -> bool:
        if not self.interactive:
            return default
        shown = "Y/n" if default else "y/N"
        while True:
            answer = self._read(f"  {prompt} [{shown}] ").strip().lower()
            if not answer:
                return default
            if answer in YES:
                return True
            if answer in NO:
                return False
            # Saying so beats re-printing the same prompt at somebody who has
            # just typed something they thought was an answer.
            self.say("  Answer yes or no - true and false work as well.")


def _format_default(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value == "":
        return "unset"
    return str(value)


def _wrap(text: str, width: int = 72) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        if line and len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


# --- the questions ----------------------------------------------------------
def build_sections(setup: Setup) -> list[Section]:
    """The questions, in the order somebody setting this up thinks of them."""
    return [
        Section(
            "Images",
            "Where the two application containers come from.",
            [
                Question(
                    key="image_source",
                    prompt="Build the image here, or pull the published one?",
                    explain=(
                        "'build' builds both application services from this checkout, "
                        "which is what you want while changing the code or when you "
                        "would rather run something you compiled yourself. "
                        "'dockerhub' pulls the published image and needs no source at all."
                    ),
                    example="dockerhub",
                    kind="choice",
                    choices=("build", "dockerhub"),
                ),
                Question(
                    key="image_ref",
                    prompt="Which published image?",
                    explain=(
                        "Only asked for 'dockerhub'. Pin a version tag for a deployment "
                        "you want to stay put; 'latest' follows every release."
                    ),
                    example=DOCKERHUB_IMAGE,
                ),
                Question(
                    key="build_context",
                    prompt="Path to the repository root, relative to the generated file",
                    explain=(
                        "Only asked for 'build'. Both images need webapp/ and frontend/, "
                        "which live above the docker directory, so the build context is "
                        "the repository root rather than the directory the file is in."
                    ),
                    example="..",
                ),
                Question(
                    key="project_name",
                    prompt="Compose project name",
                    explain=(
                        "Prefixes the containers, the network and the volumes, so two "
                        "deployments on one host stay out of each other's way."
                    ),
                    example="opencloud-scan",
                ),
                Question(
                    key="auto_updates",
                    prompt="Keep the pulled images up to date automatically?",
                    explain=(
                        "Adds Watchtower to the stack: once a day it asks the registry "
                        "whether an image this stack runs has moved, pulls the new one "
                        "and restarts the container. Only containers carrying its label "
                        "are touched, so other projects on the same host are left alone, "
                        "and a locally built image is skipped rather than replaced."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="watchtower_socket",
                    prompt="Docker socket Watchtower reaches the daemon through",
                    explain=(
                        "Detected for the user running this wizard. A rootless Docker "
                        "serves its socket under /run/user/<uid> rather than /var/run, "
                        "and Watchtower must talk to the same daemon the containers "
                        "run on or it sees nothing to update."
                    ),
                    example="/run/user/1000/docker.sock",
                    validate=_socket_path,
                ),
            ],
        ),
        Section(
            "Reachability",
            "What the service listens on, and what address it tells the world.",
            [
                Question(
                    key="bind_address",
                    prompt="Address to publish the port on",
                    explain=(
                        "127.0.0.1 keeps the service on the host, which is right when a "
                        "reverse proxy terminates TLS in front of it. 0.0.0.0 exposes it "
                        "to the network directly - only do that if nothing else can."
                    ),
                    example="127.0.0.1",
                ),
                Question(
                    key="host_port",
                    prompt="Port on the host",
                    explain=(
                        "The port inside the container is always 8811; this is only "
                        "which host port maps onto it."
                    ),
                    example="8811",
                    kind="int",
                    validate=_port,
                ),
                Question(
                    key="public_base_url",
                    prompt="Public address of this service",
                    explain=(
                        "The URL visitors actually use. Behind a proxy the service only "
                        "ever sees its own address, and the canonical links, the sitemap "
                        "and the OAuth metadata would otherwise publish URLs nobody can "
                        "reach. It is required even for a direct deployment so an "
                        "incoming Host header cannot choose those public URLs."
                    ),
                    example="https://scan.example.com",
                    validate=_optional_url,
                ),
                Question(
                    key="trust_forwarded_for",
                    prompt="Read the client address from X-Forwarded-For?",
                    explain=(
                        "Say yes only when the proxy in front *overwrites* that header. "
                        "Trusting a header a client can send makes the per-client rate "
                        "limit decorative."
                    ),
                    example="no",
                    kind="bool",
                ),
            ],
        ),
        Section(
            "Results and limits",
            "How long an answer lives, and how often one may be asked for.",
            [
                Question(
                    key="result_ttl",
                    prompt="How long a result stays readable, in seconds",
                    explain=(
                        "Also the lifetime of every key the scan writes. When it runs "
                        "out the result is gone, and its URL answers 404 like any "
                        "unknown one."
                    ),
                    example="3600",
                    kind="int",
                    validate=_positive(30),
                ),
                Question(
                    key="ip_rate_limit",
                    prompt="Scans one client may submit per window",
                    explain=(
                        "Reaching it is answered with a friendly note pointing at the "
                        "project, because the whole check is open source and runs on "
                        "the visitor's own machine with no limit at all."
                    ),
                    example="10",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="ip_rate_window",
                    prompt="Length of that window, in seconds",
                    explain="The window the count above applies to.",
                    example="60",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="target_cooldown",
                    prompt="Cooldown per scanned instance, in seconds",
                    explain=(
                        "How long the same target is left alone after a scan, whoever "
                        "asks. This one protects the instance on the other end rather "
                        "than this service."
                    ),
                    example="300",
                    kind="int",
                    validate=_positive(0),
                ),
                Question(
                    key="max_batch_targets",
                    prompt="Targets one batch submission may carry",
                    explain=(
                        "A batch is a convenience, not a discount: every target still "
                        "counts against the client limit and still claims its own "
                        "cooldown."
                    ),
                    example="10",
                    kind="int",
                    validate=_positive(1),
                ),
            ],
        ),
        Section(
            "Scanning load",
            "The whole of this deployment's load on other people's servers.",
            [
                Question(
                    key="max_workers",
                    prompt="Scans running at once",
                    explain=(
                        "Submissions past this queue in order with their position shown "
                        "- a valid submission is never refused for being busy."
                    ),
                    example="5",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="scan_concurrency",
                    prompt="Probes in flight within one scan",
                    explain=(
                        "Multiplies with the number above: five scans at four probes is "
                        "twenty connections to somebody's instances."
                    ),
                    example="4",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="scan_timeout",
                    prompt="Timeout for a single HTTP probe, in seconds",
                    explain="How long one request to the scanned instance may take.",
                    example="15",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="job_timeout",
                    prompt="Timeout for a whole scan, in seconds",
                    explain="After this the job is abandoned and the result says so.",
                    example="180",
                    kind="int",
                    validate=_positive(10),
                ),
                Question(
                    key="redis_maxmemory",
                    prompt="Redis memory cap",
                    explain=(
                        "Redis here is a cache with no persistence: it evicts rather "
                        "than growing, and every key has a TTL anyway."
                    ),
                    example="256mb",
                    validate=_memory,
                ),
            ],
        ),
        Section(
            "What may be scanned",
            "The SSRF guard, and how far this deployment is allowed to reach.",
            [
                Question(
                    key="allow_private_targets",
                    prompt="Allow private, loopback and link-local targets?",
                    explain=(
                        "Yes turns this into a scanner for your own network. Never say "
                        "yes for a deployment a stranger can reach: it would let them "
                        "probe hosts behind your firewall."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="check_debug_ports",
                    prompt="Probe the extra debug ports?",
                    explain=(
                        "Connecting to further ports on a host somebody else submitted "
                        "is a port scan. Fine when the targets are yours."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="allowed_hosts",
                    prompt="Hostnames exempt from the SSRF guard",
                    explain=(
                        "Separate several with ';'. For an on-premise instance the guard "
                        "would otherwise refuse because its name resolves to a private "
                        "address."
                    ),
                    example="opencloud.example.com;files.example.com",
                    validate=_hostname_list,
                ),
                Question(
                    key="ipv6_enabled",
                    prompt="Does this container have outbound IPv6 connectivity?",
                    explain=(
                        "Docker's default network is IPv4 only unless the host and this "
                        "stack were both set up for IPv6, which most installs are not. "
                        "Say yes only once you have confirmed the container can actually "
                        "reach an IPv6 address - answering yes without that just trades "
                        "one wrong answer for another. Left at 'no', a scan still lists "
                        "an instance's IPv6 addresses, it just does not dial them: the "
                        "IPv4/IPv6 TLS-parity check is skipped and the result notes why, "
                        "rather than reporting the instance's IPv6 side as unreachable "
                        "for a limitation of this deployment."
                    ),
                    example="no",
                    kind="bool",
                ),
            ],
        ),
        Section(
            "The public face",
            "Indexing, the browsable API pages and the update check.",
            [
                Question(
                    key="allow_indexing",
                    prompt="Let search engines index the public pages?",
                    explain=(
                        "Result pages carry noindex whatever this says - their uuid is "
                        "the whole of the authorisation. Say no for a deployment nobody "
                        "should stumble upon."
                    ),
                    example="yes",
                    kind="bool",
                ),
                Question(
                    key="enable_docs",
                    prompt="Serve the browsable Swagger UI and ReDoc pages?",
                    explain=(
                        "/docs and /redoc, a convenience for an operator. The machine "
                        "readable documents - /openapi.json, /arazzo.json and "
                        "/.well-known/ai.json - are public whatever this says."
                    ),
                    example="yes",
                    kind="bool",
                ),
                Question(
                    key="releases_mode",
                    prompt="Update check against the OpenCloud release feed",
                    explain=(
                        "'off' never queries it, which is right for a public deployment "
                        "that would otherwise hit the feed once per visitor. 'auto' "
                        "queries it and wants a token."
                    ),
                    example="off",
                    kind="choice",
                    choices=("off", "auto", "github", "schedule"),
                ),
                Question(
                    key="releases_token",
                    prompt="Token for the release feed",
                    explain=(
                        "A GitHub token raises the rate limit on the feed. Written to "
                        ".env, never into the compose file."
                    ),
                    example="github_pat_...",
                ),
            ],
        ),
        Section(
            "The agent endpoint",
            "The MCP endpoint at /mcp, and the optional sign-in in front of it.",
            [
                Question(
                    key="enable_mcp",
                    prompt="Serve the MCP endpoint at /mcp?",
                    explain=(
                        "It lets an AI agent run the same workflows through the same "
                        "rate limits, cooldown and SSRF guard a browser meets - it calls "
                        "this service's own HTTP API, so it cannot reach a code path a "
                        "visitor could not."
                    ),
                    example="yes",
                    kind="bool",
                ),
                Question(
                    key="mcp_allowed_hosts",
                    prompt="Host header values /mcp accepts",
                    explain=(
                        "DNS-rebinding protection. Name the public hostname when the "
                        "endpoint is reachable from a browser; leave it empty behind a "
                        "proxy that already fixes the Host header."
                    ),
                    example="scan.example.com",
                    validate=_hostname_list,
                ),
                Question(
                    key="mcp_max_concurrent_waits",
                    prompt="MCP tool calls that may wait for a scan at once",
                    explain=(
                        "Reaching it refuses nothing: the scan is submitted and the uuid "
                        "comes back with a note to poll."
                    ),
                    example="8",
                    kind="int",
                    validate=_positive(0),
                ),
                Question(
                    key="mcp_auth_enabled",
                    prompt="Require a sign-in on /mcp?",
                    explain=(
                        "This service then verifies an OpenID Connect token against the "
                        "provider's published keys, and issues, stores and sees no "
                        "credential of its own. Authentication decides who may ask, "
                        "never how hard - an agent that signed in meets the same limits. "
                        "A deployment that turns this on without an issuer and a public "
                        "base URL refuses to start."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="deploy_authentik",
                    prompt="Add Authentik to this stack as the provider?",
                    explain=(
                        "Say no - the default - and a sign-in, if you asked for one, "
                        "is checked against a provider you already run: you are asked "
                        "for its issuer, its audience and its keys. Say yes and "
                        "Authentik and its PostgreSQL are added to this compose file "
                        "and provision the OAuth2 provider themselves, so those three "
                        "are already right and there is nothing to click. Two more "
                        "containers and a database to back up, for an estate that has "
                        "no identity provider yet. This does not close /mcp on its "
                        "own: the answer above does that, and bringing the provider "
                        "up first is a good way to try a token before anybody is "
                        "turned away."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="authentik_url",
                    prompt="Public address of Authentik",
                    explain=(
                        "The address a person or an agent signs in at, which is what "
                        "Authentik puts in a token's 'iss' claim. This service compares "
                        "it as a string and fetches the keys over the Compose network, "
                        "so the two need not be reachable from the same place. Leave it "
                        "unset for a stack on your own machine."
                    ),
                    example="https://sso.example.com",
                    validate=_optional_url,
                ),
                Question(
                    key="authentik_slug",
                    prompt="Application slug in Authentik",
                    explain=(
                        "The last part of the issuer URL. The bundled blueprint creates "
                        "the application under this name; change it only if something "
                        "else in your Authentik already uses it."
                    ),
                    example="opencloud-scanner",
                ),
                Question(
                    key="authentik_tag",
                    prompt="Authentik image tag",
                    explain=(
                        "Pinned rather than 'latest': an identity provider that "
                        "upgrades itself on restart is one that can lock everybody out "
                        "at three in the morning."
                    ),
                    example=AUTHENTIK_TAG,
                ),
                Question(
                    key="authentik_http_port",
                    prompt="Host port for Authentik's HTTP listener",
                    explain=(
                        "Where the sign-in and the initial-setup flow are reached, on "
                        "the loopback address. Behind a reverse proxy this is the port "
                        "it forwards to."
                    ),
                    example="9000",
                    kind="int",
                    validate=_port,
                ),
                Question(
                    key="authentik_https_port",
                    prompt="Host port for Authentik's HTTPS listener",
                    explain="The same thing with Authentik's own certificate in front.",
                    example="9443",
                    kind="int",
                    validate=_port,
                ),
                Question(
                    key="mcp_auth_issuer",
                    prompt="Token issuer",
                    explain=(
                        "Exactly as the token's 'iss' claim spells it. For Authentik "
                        "that is the per-application form, trailing slash included."
                    ),
                    example="https://sso.example.com/application/o/opencloud-scan/",
                    validate=_issuer,
                ),
                Question(
                    key="mcp_auth_audience",
                    prompt="Audience a token must carry",
                    explain=(
                        "Normally the client ID the agent authenticated as, which is "
                        "what the provider puts in the 'aud' claim. Required: a "
                        "provider that serves other applications mints tokens for "
                        "them too, and an audience nobody compares makes every one "
                        "of those a key to this endpoint."
                    ),
                    example="opencloud-scanner",
                    validate=_audience,
                ),
                Question(
                    key="mcp_auth_scopes",
                    prompt="Scopes a token must carry",
                    explain=(
                        "Separate several with ';'. Empty means any valid token from "
                        "that issuer is enough."
                    ),
                    example="openid;profile",
                    validate=_hostname_list,
                ),
                Question(
                    key="mcp_auth_jwks_url",
                    prompt="Where the provider publishes its signing keys",
                    explain=(
                        "Only when it is not <issuer>/jwks/, which is what Authentik and "
                        "most others serve."
                    ),
                    example="https://sso.example.com/application/o/opencloud-scan/jwks/",
                    validate=_optional_url,
                ),
                Question(
                    key="mcp_auth_resource_url",
                    prompt="The URL agents reach /mcp at",
                    explain=(
                        "The OAuth resource identifier. Only when it is not the public "
                        "base URL with /mcp on the end."
                    ),
                    example="https://scan.example.com/mcp",
                    validate=_optional_url,
                ),
            ],
        ),
        Section(
            "Mail",
            "How Authentik sends a password recovery or an invitation.",
            [
                Question(
                    key="smtp_host",
                    prompt="SMTP server",
                    explain=(
                        "Leave it unset and Authentik keeps its built-in local "
                        "delivery, which is fine while the only account is the one you "
                        "create at first start - but a password recovery then shows "
                        "'check your inbox' for a mail that never arrives. The scan "
                        "service itself sends no mail at all; this is Authentik's."
                    ),
                    example="smtp.example.com",
                ),
                Question(
                    key="smtp_port",
                    prompt="Port",
                    explain=(
                        "587 for STARTTLS, 465 for implicit TLS, 25 for a relay on your "
                        "own network that wants neither."
                    ),
                    example="587",
                    kind="int",
                    validate=_port,
                ),
                Question(
                    key="smtp_security",
                    prompt="Transport security",
                    explain=(
                        "'starttls' upgrades a plain connection and goes with port 587; "
                        "'ssl' is implicit TLS on port 465; 'none' sends credentials in "
                        "the clear and belongs only on a relay you can already trust. "
                        "The two TLS modes are mutually exclusive - asking for both is "
                        "how a submission hangs until the timeout."
                    ),
                    example="starttls",
                    kind="choice",
                    choices=("starttls", "ssl", "none"),
                ),
                Question(
                    key="smtp_username",
                    prompt="Username",
                    explain=(
                        "Leave unset for a relay that authenticates by address rather "
                        "than by account."
                    ),
                    example="authentik@example.com",
                ),
                Question(
                    key="smtp_password",
                    prompt="Password",
                    explain=(
                        "Written to .env, never into the compose file. It can also be "
                        "supplied without typing it here, by putting "
                        "AUTHENTIK_EMAIL_PASSWORD in the environment the wizard runs in."
                    ),
                    example="an app password from your provider",
                ),
                Question(
                    key="smtp_from",
                    prompt="From address",
                    explain=(
                        "What the recipient sees. A provider that refuses to relay for "
                        "an address it does not own will reject every message until "
                        "this matches one it does."
                    ),
                    example="authentik@example.com",
                    validate=_mail_address,
                ),
                Question(
                    key="smtp_timeout",
                    prompt="Connection timeout, in seconds",
                    explain=(
                        "How long a submission may take before Authentik gives up on "
                        "it and logs the failure."
                    ),
                    example="10",
                    kind="int",
                    validate=_positive(1),
                ),
            ],
        ),
        Section(
            "Keeping and erasing",
            "The audit log, erasure on request, and encryption at rest.",
            [
                Question(
                    key="audit_log",
                    prompt="Write an audit record for every request?",
                    explain=(
                        "One JSON object per line for every scan, rejection and "
                        "triggered limit. Off means the ordinary log keeps lifecycle "
                        "markers and uuids only - never a target, an address or a "
                        "result."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="audit_log_targets",
                    prompt="Record the scanned hostname in the clear?",
                    explain=(
                        "Otherwise a target becomes a fingerprint like an address does. "
                        "Reasonable for your own estate; for a public deployment a log "
                        "of targets is a log of who scanned what."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="audit_salt",
                    prompt="Salt for those fingerprints",
                    explain=(
                        "Unset means a random one per process, so nothing correlates "
                        "across a restart. Setting one makes correlation possible, and "
                        "the salt is then a secret: the address space is small enough to "
                        "hash exhaustively without it."
                    ),
                    example="generate",
                    generate=16,
                ),
                Question(
                    key="audit_storage",
                    prompt="Where should the audit trail be kept?",
                    explain=(
                        "'none' leaves it on the container's output, which "
                        "'docker compose down' takes with it - the records are "
                        "gone exactly when somebody asks for them. 'volume' "
                        "writes it to a named Docker volume the stack manages; "
                        "'filesystem' writes it to a directory on this host, "
                        "which is what a deployment with existing log shipping "
                        "or backups wants. Either way it is a rotating file, "
                        "so it cannot fill the disk it sits on."
                    ),
                    example="volume",
                    kind="choice",
                    choices=STORAGE_CHOICES,
                ),
                Question(
                    key="audit_log_path",
                    prompt="Host directory for the audit file",
                    explain=(
                        f"Bind-mounted at {AUDIT_LOG_DIRECTORY} in the container. "
                        f"It has to exist and be owned by uid {WEB_IMAGE_UID}, "
                        "which is the unprivileged user the image runs as - "
                        "the service refuses to start rather than report a "
                        "trail it cannot write. A named volume needs none of "
                        "that, which is why it is the other answer."
                    ),
                    example="/srv/opencloud-scan/audit",
                    validate=_host_directory,
                ),
                Question(
                    key="audit_rotation",
                    prompt="What should rotate that file?",
                    explain=(
                        "'service' rotates it by size from inside the "
                        "container and needs nothing installed on the host. "
                        "'logrotate' hands the job to the host's own, with a "
                        "policy file written next to the compose file for you "
                        "to install - daily, dated, compressed, and kept for "
                        "as long as you say below. Pick one: two things "
                        "rotating one file is how a trail loses records."
                    ),
                    example="logrotate",
                    kind="choice",
                    choices=ROTATION_CHOICES,
                ),
                Question(
                    key="audit_retention_days",
                    prompt="Days of audit trail to keep",
                    explain=(
                        "How many daily generations logrotate keeps before "
                        "deleting the oldest. This is a retention decision "
                        "rather than a disk one: keeping records longer than "
                        "you can justify is its own liability, and keeping "
                        "them shorter than you are asked about them defeats "
                        "the trail."
                    ),
                    example="30",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="purge_token",
                    prompt="Credential for DELETE /api/purge",
                    explain=(
                        "Unset means the erasure endpoint does not exist: the call "
                        "deletes results belonging to whoever is reading them, so it "
                        "belongs to the operator rather than to anybody who can type a "
                        "hostname."
                    ),
                    example="generate",
                    generate=32,
                ),
                Question(
                    key="purge_signing_key",
                    prompt="Signing key for the proof of deletion",
                    explain=(
                        "Makes the receipt checkable long after the data is gone. Unset "
                        "still returns a receipt, just an unsigned one."
                    ),
                    example="generate",
                    generate=32,
                ),
                Question(
                    key="export_signing_key",
                    prompt="Signing key for downloaded reports",
                    explain=(
                        "Adds a verifiable HMAC-SHA256 header over the exact PDF, "
                        "SARIF, JSON or CSV bytes. Keep the key in the generated "
                        ".env and give it only to systems that verify reports."
                    ),
                    example="generate",
                    generate=32,
                ),
                Question(
                    key="encrypt_results",
                    prompt="Encrypt stored results with AES-256-GCM?",
                    explain=(
                        "The web process and the worker must agree and need the same "
                        "key, because the worker writes the document and the web process "
                        "reads it back. A process asked to encrypt without a usable key "
                        "refuses to start rather than store plaintext."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="encryption_key",
                    prompt="Encryption key, 64 hex characters",
                    explain=(
                        "Version 1. The highest version encrypts and lower ones still "
                        "decrypt, which is how a key is rotated later."
                    ),
                    example="generate",
                    generate=32,
                    validate=_hex_key,
                ),
                Question(
                    key="redis_persistence",
                    prompt="Should Redis keep its data across a restart?",
                    explain=(
                        "'none' is the default the rest of the design assumes: "
                        "a cache, writing nothing to disk, where every key has "
                        "a TTL anyway and a restart loses only results that "
                        "were about to expire. 'volume' and 'filesystem' turn "
                        "on the append-only file so a queued scan and a live "
                        "result survive - and put a copy of every result "
                        "inside its TTL on a disk, which is the thing a public "
                        "deployment is otherwise able to say it never does."
                    ),
                    example="none",
                    kind="choice",
                    choices=STORAGE_CHOICES,
                ),
                Question(
                    key="redis_data_path",
                    prompt="Host directory for the Redis data",
                    explain=(
                        f"Bind-mounted at {REDIS_DATA_DIRECTORY} in the "
                        f"container, and owned by uid {REDIS_IMAGE_UID}, which "
                        "is the user the Redis image runs as. A named volume "
                        "needs none of that."
                    ),
                    example="/srv/opencloud-scan/redis",
                    validate=_host_directory,
                ),
            ],
        ),
    ]


def run_questions(wizard: Wizard) -> None:
    """Ask everything, skipping the questions the previous answers settled."""
    setup = wizard.setup
    for section in build_sections(setup):
        questions = [item for item in section.questions if _relevant(item.key, setup)]
        if not questions:
            continue
        wizard.heading(section)
        for question in questions:
            # Re-checked, because an answer given a moment ago can settle a
            # later question in the same section.
            if _relevant(question.key, setup):
                wizard.ask(question)


def _signs_in(setup: Setup) -> bool:
    """Whether this deployment asked for a sign-in on ``/mcp`` at all."""
    return setup.enable_mcp and setup.mcp_auth_enabled


def _uses_authentik(setup: Setup) -> bool:
    """Whether the generated stack brings its own identity provider.

    Independent of whether ``/mcp`` requires a token. Deploying a provider is
    a decision about what runs; requiring a sign-in is a decision about who
    may ask, and neither one implies the other. A stack can be provisioned
    with the guard still off, which is how an operator tries the sign-in out
    before switching it on for everybody.
    """
    return setup.deploy_authentik


def _relevant(key: str, setup: Setup) -> bool:
    """Whether a question still has a point, given the answers so far."""
    if key == "image_ref":
        return setup.image_source == "dockerhub"
    if key == "build_context":
        return setup.image_source == "build"
    if key == "watchtower_socket":
        return setup.auto_updates
    if key == "releases_token":
        return setup.releases_mode != "off"
    if key in {"mcp_allowed_hosts", "mcp_max_concurrent_waits", "mcp_auth_enabled"}:
        return setup.enable_mcp
    if key == "deploy_authentik" or key.startswith("authentik_"):
        # Authentik answers the issuer, the audience and the keys itself, so
        # its own questions replace them rather than adding to them.
        return setup.enable_mcp and (key == "deploy_authentik" or _uses_authentik(setup))
    if key.startswith("smtp_"):
        if not _uses_authentik(setup):
            return False
        return key == "smtp_host" or bool(setup.smtp_host)
    if key.startswith("mcp_auth_"):
        if not _signs_in(setup):
            return False
        return key == "mcp_auth_scopes" or not _uses_authentik(setup)

    if key in {"audit_log_targets", "audit_salt", "audit_storage"}:
        return setup.audit_log
    if key in {"audit_log_path", "audit_rotation"}:
        # Only a host directory can be handed to the host's logrotate: a named
        # volume is a path under Docker's root that nothing else should name.
        return setup.audit_log and setup.audit_storage == "filesystem"
    if key == "audit_retention_days":
        return _uses_logrotate(setup)
    if key == "redis_data_path":
        return setup.redis_persistence == "filesystem"
    if key == "encryption_key":
        return setup.encrypt_results
    return True


def _keeps_audit_file(setup: Setup) -> bool:
    """Whether the audit trail is written to something that outlives the stack."""
    return setup.audit_log and setup.audit_storage != "none"


def _uses_logrotate(setup: Setup) -> bool:
    """Whether the host's logrotate is the thing keeping the trail in bounds."""
    return (
        _keeps_audit_file(setup)
        and setup.audit_storage == "filesystem"
        and setup.audit_rotation == "logrotate"
    )


def _persists_redis(setup: Setup) -> bool:
    """Whether Redis writes its keyspace to disk."""
    return setup.redis_persistence != "none"


def _mount_source(storage: str, host_path: str, volume: str) -> str:
    """The left-hand side of a bind or named-volume mount."""
    return host_path.strip() if storage == "filesystem" else volume


def check_consistency(setup: Setup) -> list[str]:
    """Warnings worth showing before anything is written.

    None of these is fatal here - the service itself refuses to start on the
    ones that matter - but saying so now is cheaper than a container that
    exits three seconds after ``up``.
    """
    warnings: list[str] = []
    if _signs_in(setup) and not _uses_authentik(setup) and not setup.mcp_auth_issuer:
        warnings.append(
            "A sign-in on /mcp without an issuer is refused at startup. "
            "Set one, add the bundled Authentik with --with-authentik, or "
            "turn the sign-in off."
        )
    if _signs_in(setup) and not _uses_authentik(setup) and not setup.mcp_auth_audience:
        warnings.append(
            "A sign-in on /mcp without an audience is refused at startup. "
            "Without one, any unexpired token the issuer minted for any other "
            "application would open the endpoint; set it to the client ID "
            "agents authenticate as."
        )
    if setup.mcp_auth_enabled and not (setup.public_base_url or setup.mcp_auth_resource_url):
        warnings.append(
            "A sign-in on /mcp needs a public base URL or a resource URL, "
            "because the RFC 9728 metadata has to name the address agents use."
        )
    if _uses_authentik(setup) and not setup.mcp_auth_enabled:
        warnings.append(
            "Authentik is in the stack but /mcp does not require a token, so "
            "the provider guards nothing yet. That is a fine way to bring it "
            "up first; set COS_WEB_MCP_AUTH_ENABLED to true when you are ready."
        )
    if _uses_authentik(setup) and not setup.smtp_host:
        warnings.append(
            "Authentik has no mail server, so a password recovery or an "
            "invitation will not arrive. That is fine while the only account "
            "is the one you are about to create; set an SMTP server before "
            "there is a second one."
        )
    if setup.smtp_host and setup.smtp_security == "none":
        warnings.append(
            "The SMTP connection has no transport security, so the mail "
            "password travels in the clear. Only do that on a relay inside "
            "your own network."
        )
    if setup.smtp_host and setup.smtp_username and not setup.smtp_password:
        warnings.append(
            "An SMTP username without a password. Set AUTHENTIK_EMAIL_PASSWORD "
            "in the generated .env before starting the stack, or the "
            "submission is refused."
        )
    if setup.encrypt_results and not setup.encryption_key:
        warnings.append(
            "Encryption without a key is refused at startup rather than "
            "storing plaintext. Answer 'generate' at the key question."
        )
    if setup.auto_updates and setup.image_source == "build":
        warnings.append(
            "Automatic updates follow pulled images, and the application "
            "containers here are built locally - Watchtower will keep Redis "
            "and the rest current but cannot rebuild those. Update them with "
            "'docker compose up -d --build', or answer 'dockerhub' at the "
            "image question."
        )
    if setup.allow_private_targets and setup.bind_address == "0.0.0.0":  # nosec B104
        warnings.append(
            "Private targets are allowed and the port is published on every "
            "interface. Anybody who reaches this service can probe hosts "
            "behind your firewall with it."
        )
    if setup.trust_forwarded_for and setup.bind_address == "0.0.0.0":  # nosec B104
        warnings.append(
            "X-Forwarded-For is trusted and the port is not restricted to the "
            "host. A client that reaches the service directly can then send "
            "any address it likes and the rate limit stops counting."
        )
    if _keeps_audit_file(setup) and setup.audit_storage == "filesystem" and not setup.audit_log_path:
        warnings.append(
            "The audit trail is set to go to a host directory but none was "
            "named. Give one, or answer 'volume' and let Docker manage it."
        )
    if setup.audit_storage == "filesystem" and setup.audit_log_path:
        warnings.append(
            f"{setup.audit_log_path} has to exist and be owned by uid "
            f"{WEB_IMAGE_UID} before the stack starts, or the web service "
            "refuses to come up rather than report an audit trail it cannot "
            f"write:  mkdir -p {setup.audit_log_path} && chown "
            f"{WEB_IMAGE_UID} {setup.audit_log_path}"
        )
    if _uses_logrotate(setup):
        warnings.append(
            f"The generated {logrotate_filename(setup)} does nothing until it "
            "is installed into /etc/logrotate.d as root - and until it is, "
            "nothing rotates the audit trail, because the service was told "
            "the host would. The next steps print the command."
        )
    if setup.redis_persistence == "filesystem" and not setup.redis_data_path:
        warnings.append(
            "Redis persistence is set to a host directory but none was named. "
            "Give one, or answer 'volume' and let Docker manage it."
        )
    if setup.redis_persistence == "filesystem" and setup.redis_data_path:
        warnings.append(
            f"{setup.redis_data_path} has to exist and be owned by uid "
            f"{REDIS_IMAGE_UID}, the user the Redis image runs as:  mkdir -p "
            f"{setup.redis_data_path} && chown {REDIS_IMAGE_UID} "
            f"{setup.redis_data_path}"
        )
    if _persists_redis(setup) and not setup.encrypt_results:
        warnings.append(
            "Redis now writes its keyspace to disk, so every result still "
            "inside its TTL exists as a file somebody can read - which is the "
            "one thing this service can otherwise say it never does. Turn on "
            "COS_WEB_ENCRYPT_RESULTS, or leave the persistence off unless a "
            "restart really must not lose a queued scan."
        )
    if _persists_redis(setup) and setup.allow_indexing:
        warnings.append(
            "A deployment strangers can find, keeping its scans on disk. The "
            "TTL still expires them, but a backup of that disk does not."
        )
    if setup.audit_log_targets and setup.allow_indexing:
        warnings.append(
            "Targets are logged in the clear on a deployment search engines "
            "may index. That is a public service keeping a list of who "
            "scanned what."
        )
    return warnings


# --- writing the files ------------------------------------------------------
def _bool(value: bool) -> str:
    return "true" if value else "false"


def _env_reference(key: str) -> str:
    return "${" + SECRET_VARIABLES[key] + ":-}"


def _authentik_issuer(setup: Setup) -> str:
    """The ``iss`` claim Authentik will mint, as a string to compare against."""
    base = (setup.authentik_url or f"http://localhost:{setup.authentik_http_port}").rstrip("/")
    return f"{base}/application/o/{setup.authentik_slug}/"


def _authentik_jwks_url(setup: Setup) -> str:
    """Where *this container* fetches the keys, which is not where a browser goes."""
    return f"http://authentik-server:9000/application/o/{setup.authentik_slug}/jwks/"


def _finalise(setup: Setup) -> None:
    """Fill in what the answers imply rather than asking for it twice.

    Everything here is derivable: the issuer from the Authentik address and
    the slug, the redirect back from the address this service is reached at,
    the credentials from a random number generator. Asking would be a quiz.
    """
    if not setup.public_base_url:
        setup.public_base_url = f"http://localhost:{setup.host_port}"
    # No question for this one: there is no answer an operator could give that
    # is better than a random string neither of us has to remember. The URL
    # both application containers use carries it by reference.
    if not setup.redis_password:
        setup.redis_password = secrets.token_urlsafe(32)
    if _uses_authentik(setup):
        if not setup.authentik_url:
            setup.authentik_url = f"http://localhost:{setup.authentik_http_port}"
        if not setup.authentik_redirect_uri:
            setup.authentik_redirect_uri = setup.public_base_url.rstrip("/") + "/"
        setup.authentik_secret_key = setup.authentik_secret_key or secrets.token_urlsafe(48)
        setup.authentik_pg_password = setup.authentik_pg_password or secrets.token_urlsafe(30)
        setup.authentik_client_id = (
            setup.authentik_client_id or f"opencloud-scanner-{secrets.token_hex(10)}"
        )
        setup.authentik_client_secret = (
            setup.authentik_client_secret or secrets.token_urlsafe(30)
        )
        if setup.smtp_host and not setup.smtp_from:
            setup.smtp_from = setup.smtp_username or "authentik@localhost"
    else:
        # Answered and then made irrelevant: a leftover credential in .env for
        # a provider this deployment does not run is a secret nobody rotates.
        setup.authentik_secret_key = ""
        setup.authentik_pg_password = ""
        setup.authentik_client_id = ""
        setup.authentik_client_secret = ""
        setup.smtp_host = ""
        setup.smtp_password = ""


def _authentik_environment(setup: Setup) -> list[EnvEntry]:
    """What both Authentik containers read. The worker is what sends mail."""
    entries = [
        _entry("AUTHENTIK_SECRET_KEY", f'"{_env_reference("authentik_secret_key")}"'),
        _entry("AUTHENTIK_POSTGRESQL__HOST", '"authentik_postgresql"'),
        _entry("AUTHENTIK_POSTGRESQL__NAME", '"authentik"'),
        _entry("AUTHENTIK_POSTGRESQL__USER", '"authentik"'),
        _entry(
            "AUTHENTIK_POSTGRESQL__PASSWORD",
            f'"{_env_reference("authentik_pg_password")}"',
        ),
        _entry("AUTHENTIK_ERROR_REPORTING__ENABLED", '"false"'),
        _entry(
            "AUTHENTIK_LISTEN__HTTP",
            '"0.0.0.0:9000"',
            "Authentik binds [::] by default and dies on a host whose kernel has",
            "IPv6 disabled, which a container host quite often does.",
        ),
        _entry("AUTHENTIK_LISTEN__HTTPS", '"0.0.0.0:9443"'),
        _entry("AUTHENTIK_LISTEN__METRICS", '"0.0.0.0:9300"'),
        _entry(
            "AUTHENTIK_SCANNER_SLUG",
            f'"{setup.authentik_slug}"',
            "Read by the blueprint, so the provider is created with the same",
            "client ID the scanner checks a token's audience against.",
        ),
        _entry("AUTHENTIK_SCANNER_CLIENT_ID", f'"{_env_reference("authentik_client_id")}"'),
        _entry(
            "AUTHENTIK_SCANNER_CLIENT_SECRET",
            f'"{_env_reference("authentik_client_secret")}"',
        ),
        _entry("AUTHENTIK_SCANNER_REDIRECT_URI", f'"{setup.authentik_redirect_uri}"'),
    ]
    entries.extend(_mail_environment(setup))
    return entries


def _mail_environment(setup: Setup) -> list[EnvEntry]:
    """SMTP, or the absence of it.

    An empty host leaves Authentik on its built-in local delivery, which is
    the honest default: a half-configured mail server fails at the moment
    somebody needs a password reset, which is the worst moment available.
    """
    if not setup.smtp_host:
        return [
            _entry(
                "AUTHENTIK_EMAIL__HOST",
                '""',
                "No mail server, so Authentik keeps its built-in local delivery.",
                "A password recovery or an invitation will not arrive; set a host",
                "here before there is a second account.",
            )
        ]
    return [
        _entry(
            "AUTHENTIK_EMAIL__HOST",
            f'"{setup.smtp_host}"',
            "Mail. Only Authentik sends any: a password recovery, an invitation,",
            "an expiring-password notice. The password is in .env, like every",
            "other credential in this file.",
        ),
        _entry("AUTHENTIK_EMAIL__PORT", f'"{setup.smtp_port}"'),
        _entry("AUTHENTIK_EMAIL__USERNAME", f'"{setup.smtp_username}"'),
        _entry("AUTHENTIK_EMAIL__PASSWORD", f'"{_env_reference("smtp_password")}"'),
        _entry(
            "AUTHENTIK_EMAIL__USE_TLS",
            f'"{_bool(setup.smtp_security == "starttls")}"',
            "STARTTLS on 587, implicit TLS on 465. Exactly one of these, ever:",
            "asking for both is how a submission hangs until the timeout.",
        ),
        _entry("AUTHENTIK_EMAIL__USE_SSL", f'"{_bool(setup.smtp_security == "ssl")}"'),
        _entry("AUTHENTIK_EMAIL__TIMEOUT", f'"{setup.smtp_timeout}"'),
        _entry(
            "AUTHENTIK_EMAIL__FROM",
            f'"{setup.smtp_from}"',
            "What the recipient sees. A provider that will not relay for an",
            "address it does not own rejects everything until this matches.",
        ),
    ]


def _authentik_services(setup: Setup) -> str:
    """The identity provider, its database, and the volumes they need."""
    if not _uses_authentik(setup):
        return ""
    image = f"{AUTHENTIK_IMAGE}:{setup.authentik_tag}"
    environment = _render_environment(_authentik_environment(setup), "      ")
    blueprints = f"./{BLUEPRINT_RELATIVE.parent.as_posix()}:/blueprints/custom:ro"
    label = _update_label(setup)
    return f"""
  # Authentik, which is what makes the sign-in above enforceable. It
  # provisions itself: `{BLUEPRINT_RELATIVE.as_posix()}` is mounted into
  # both containers and the worker applies it on the first start, creating the
  # OAuth2 provider, its signing key, the scopes and the application whose slug
  # is part of the issuer. Nothing to click, and no value to copy between the
  # two halves of this file.
  #
  # Authentik keeps sessions, caching and its task queue in PostgreSQL and
  # needs no Redis of its own. The scanner's Redis above is a cache with no
  # persistence and an eviction policy, and is not a substitute for a database.
  authentik_postgresql:
    image: docker.io/library/postgres:18.6-alpine
    container_name: {setup.project_name}-authentik-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: "authentik"
      POSTGRES_USER: "authentik"
      POSTGRES_PASSWORD: "{_env_reference("authentik_pg_password")}"
    volumes:
      # PostgreSQL 18 moved the mount point up one level: a volume at the old
      # /var/lib/postgresql/data is refused with an explanation.
      - authentik_database:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -d $${{POSTGRES_DB}} -U $${{POSTGRES_USER}}"]
      start_period: 20s
      interval: 30s
      timeout: 5s
      retries: 5
    security_opt:
      - no-new-privileges:true
{label}
  authentik_server:
    image: "{image}"
    container_name: {setup.project_name}-authentik
    restart: unless-stopped
    command: server
    depends_on:
      authentik_postgresql:
        condition: service_healthy
    environment:
{environment}
    ports:
      - "127.0.0.1:{setup.authentik_http_port}:9000"
      - "127.0.0.1:{setup.authentik_https_port}:9443"
    networks:
      # A hyphenated alias for the same container: the Compose service name has
      # an underscore, a Host header carrying one is not a legal host name, and
      # Authentik answers such a request with a 404. This alias is what makes
      # the JWKS URL above both resolvable and answered.
      default:
        aliases:
          - authentik-server
    shm_size: 512mb
    volumes:
      - {blueprints}
      - authentik_media:/media
      - authentik_templates:/templates
    security_opt:
      - no-new-privileges:true
{label}
  authentik_worker:
    image: "{image}"
    container_name: {setup.project_name}-authentik-worker
    restart: unless-stopped
    command: worker
    depends_on:
      authentik_postgresql:
        condition: service_healthy
    environment:
{environment}
    # The upstream compose file gives this container the Docker socket so it
    # can manage outpost containers. This stack runs none, so it does not:
    # handing a container the daemon socket is handing it the host.
    shm_size: 512mb
    volumes:
      - {blueprints}
      - authentik_certs:/certs
      - authentik_media:/media
      - authentik_templates:/templates
    security_opt:
      - no-new-privileges:true
{label}"""


def _audit_mount(setup: Setup) -> str:
    """The audit volume on the web service, for a deployment that keeps one."""
    if not _keeps_audit_file(setup):
        return ""
    source = _mount_source(setup.audit_storage, setup.audit_log_path, AUDIT_VOLUME)
    return (
        "    # The one writable path in this container, and the reason the audit\n"
        "    # trail outlives it. Everything else is read-only on purpose.\n"
        "    volumes:\n"
        f"      - {source}:{AUDIT_LOG_DIRECTORY}\n"
    )


def _redis_mount(setup: Setup) -> str:
    """The data volume on Redis, for a deployment that asked it to persist."""
    if not _persists_redis(setup):
        return ""
    source = _mount_source(setup.redis_persistence, setup.redis_data_path, REDIS_VOLUME)
    return "    volumes:\n" f"      - {source}:{REDIS_DATA_DIRECTORY}\n"


def _redis_storage_command(setup: Setup) -> str:
    """The two Redis options that decide whether anything reaches a disk."""
    if not _persists_redis(setup):
        return '      --save ""\n      --appendonly no\n'
    return (
        f"      --dir {REDIS_DATA_DIRECTORY}\n"
        "      --appendonly yes\n"
        "      --appendfsync everysec\n"
        # Unquoted on purpose: redis-server reads its arguments as a config
        # line, so `--save "900 1"` arrives as one quoted value and is
        # rejected, while `--save 900 1` is the two the option takes.
        "      --save 900 1\n"
    )


def _redis_storage_comment(setup: Setup) -> str:
    """The paragraph above that command, which has to say what it does."""
    if not _persists_redis(setup):
        return (
            "    # No persistence: nothing here is worth surviving a restart, and a dump\n"
            "    # file would be a copy of everybody's scans sitting on a disk.\n"
        )
    where = (
        f"the host directory {setup.redis_data_path}"
        if setup.redis_persistence == "filesystem"
        else f"the named volume {REDIS_VOLUME}"
    )
    return (
        f"    # Persistent, at this deployment's request: the keyspace is written to\n"
        f"    # {where}, so a queued scan and a live result\n"
        "    # survive a restart. That also means a copy of every result still inside\n"
        "    # its TTL exists as a file - back it up, or do not, but know which. Turn\n"
        "    # COS_WEB_ENCRYPT_RESULTS on and what lands there is ciphertext.\n"
    )


def _volumes_block(setup: Setup) -> str:
    """The bottom-level ``volumes:`` section, or nothing when the stack keeps nothing.

    Only *named* volumes are declared here. A bind mount names a directory
    that already exists on the host and needs no declaration - which is also
    why a deployment using one has to create it itself.
    """
    named: list[tuple[str, str]] = []
    if _keeps_audit_file(setup) and setup.audit_storage == "volume":
        named.append(
            (
                AUDIT_VOLUME,
                (
                    "The audit trail. The one part of this stack that is asked "
                    "about long after the fact, so it is the one part that "
                    "outlives it."
                ),
            )
        )
    if setup.redis_persistence == "volume":
        named.append(
            (
                REDIS_VOLUME,
                (
                    "Redis's keyspace: every live scan and every result still "
                    "inside its TTL. Treat a backup of it as a copy of what "
                    "people scanned."
                ),
            )
        )
    if _uses_authentik(setup):
        named.append(
            (
                "authentik_database",
                (
                    "Authentik's own, and all of it matters: the database holds "
                    "every user, flow, provider and signing key, and none of it "
                    "is recoverable without AUTHENTIK_SECRET_KEY from .env. Back "
                    "the database and that file up together."
                ),
            )
        )
        named.extend(
            (name, "")
            for name in ("authentik_media", "authentik_templates", "authentik_certs")
        )
    if not named:
        return ""
    lines = ["", "volumes:"]
    for name, comment in named:
        for line in _wrap(comment, 74) if comment else []:
            lines.append(f"  # {line}")
        lines.append(f"  {name}:")
    return "\n".join(lines) + "\n"


def logrotate_filename(setup: Setup) -> str:
    """What the generated policy is called, before it is installed."""
    return f"{setup.project_name}-audit.logrotate"


def render_logrotate_file(setup: Setup) -> str:
    """
    A logrotate policy for the audit trail, for the host to install.

    Written rather than applied: dropping a file into /etc/logrotate.d needs
    root, and a setup wizard that writes outside the directory it was pointed
    at is one nobody can run twice safely. The install command is in the next
    steps and in the header here.

    Two lines carry the whole arrangement:

    * ``create 0600 <uid> <gid>`` - logrotate renames the file and makes the
      replacement itself, so the replacement has to be writable by the
      container's unprivileged user and readable by nobody else.
    * ``notifempty`` with no ``copytruncate`` - the service reopens the file
      when it notices the inode changed, which loses no record. Truncating
      underneath a writer instead trades that for a race, and this is a file
      whose entire purpose is to be complete.
    """
    path = f"{setup.audit_log_path.rstrip('/')}/{AUDIT_LOG_FILENAME}"
    return f"""# Audit trail of the check-opencloud-security web application.
#
# Written by docker/setup-wizard.py. Install it as root, once:
#
#   sudo install -m 0644 -o root -g root \\
#     {logrotate_filename(setup)} /etc/logrotate.d/{setup.project_name}-audit
#   sudo logrotate --debug /etc/logrotate.d/{setup.project_name}-audit
#
# The --debug run changes nothing and prints what a real one would do, which
# is the cheapest way to find out that the path is wrong.
#
# The service writes {path} as uid {WEB_IMAGE_UID}
# from inside its container, and does not rotate the file itself - the
# compose file sets COS_WEB_AUDIT_LOG_ROTATION to "{EXTERNAL_ROTATION}", which
# says this policy owns it. Removing this file without changing that setting
# leaves nothing rotating the trail at all.
{path} {{
    # One file a day, named for the day it covers, kept for {setup.audit_retention_days} days.
    # An audit question is asked in weeks and months, so that number is worth
    # deciding rather than inheriting: too short and the trail cannot answer,
    # too long and it is a record you have to justify keeping.
    daily
    rotate {setup.audit_retention_days}
    dateext
    missingok
    notifempty
    compress
    delaycompress
    # logrotate renames the file and creates the replacement, and the
    # container has to be able to write to it. The service notices the inode
    # changed and reopens - no signal, no restart, no copytruncate, and no
    # record written to a file nobody can find any more.
    create 0600 {WEB_IMAGE_UID} {WEB_IMAGE_UID}
}}
"""


def render_env_file(setup: Setup) -> str:
    """The `.env` file: the secrets, and nothing that is not one."""
    lines = [
        "# Secrets for the check-opencloud-security web stack.",
        "#",
        "# Written by docker/setup-wizard.py. Compose reads this file from the",
        "# directory it runs in, and the compose file refers to these names",
        "# rather than carrying the values, so the compose file stays something",
        "# you can commit and paste.",
        "#",
        "# Owner-readable only. Back it up somewhere that is too: losing",
        "# COS_WEB_ENCRYPTION_KEY_1 makes every stored result unreadable, and",
        "# losing COS_WEB_PURGE_TOKEN means nobody can ask for an erasure.",
        "",
    ]
    written = 0
    for key, variable in SECRET_VARIABLES.items():
        if not _relevant(key, setup):
            continue
        value = getattr(setup, key)
        if not value:
            continue
        lines.append(f"{variable}={value}")
        written += 1
    if not written:
        lines.append("# Nothing needed a secret. The wizard writes this file anyway, so")
        lines.append("# that adding one later is an edit rather than a discovery.")
    lines.append("")
    return "\n".join(lines)



@dataclass
class EnvEntry:
    """One environment line in the generated compose file.

    The comment travels with the setting rather than being written beside it,
    because the file this produces is the one an operator reads six months
    later when wondering why a limit is where it is.
    """

    name: str
    value: str
    comment: str = ""


def _entry(name: str, value: str, *comment: str) -> EnvEntry:
    return EnvEntry(name=name, value=value, comment=" ".join(comment))


def _web_environment(setup: Setup) -> list[EnvEntry]:
    """What the web service reads, in the order it makes sense to read it."""
    entries: list[EnvEntry] = [
        _entry(
            "COS_WEB_REDIS_URL",
            f'"redis://:{_env_reference("redis_password")}@redis:6379/0"',
            "Redis requires a password and sits on a network of its own.",
            "The value lives in .env, never here.",
        ),
        _entry(
            "COS_WEB_RESULT_TTL",
            f'"{setup.result_ttl}"',
            "How long a result stays readable. Also the lifetime of every key.",
        ),
        _entry(
            "COS_WEB_IP_RATE_LIMIT",
            f'"{setup.ip_rate_limit}"',
            "Rate limits: per client address, and per target instance.",
            "Reaching one is answered with a pointer to the project, which runs",
            "on the visitor's own machine with no limit at all.",
        ),
        _entry("COS_WEB_IP_RATE_WINDOW", f'"{setup.ip_rate_window}"'),
        _entry("COS_WEB_TARGET_COOLDOWN", f'"{setup.target_cooldown}"'),
        _entry(
            "COS_WEB_MAX_BATCH_TARGETS",
            f'"{setup.max_batch_targets}"',
            "Targets one POST /api/scans/batch may carry. A batch is a",
            "convenience, not a discount: every target still counts against the",
            "client limit and still claims its own cooldown.",
        ),
        _entry(
            "COS_WEB_TRUST_FORWARDED_FOR",
            f'"{_bool(setup.trust_forwarded_for)}"',
            "Only true behind a proxy that *overwrites* X-Forwarded-For.",
            "Trusting a header a client can send makes the rate limit decorative.",
        ),
    ]
    if setup.public_base_url:
        entries.append(
            _entry(
                "COS_WEB_PUBLIC_BASE_URL",
                f'"{setup.public_base_url}"',
                "The address this service is reached at from outside. Behind a",
                "proxy it only ever sees its own.",
            )
        )
    entries.append(
        _entry(
            "COS_WEB_ALLOW_INDEXING",
            f'"{_bool(setup.allow_indexing)}"',
            "Let search engines index the public pages. A result page carries",
            "noindex whatever this says: its uuid is the whole authorisation.",
        )
    )
    entries.append(_entry("COS_WEB_RELEASES_MODE", f'"{setup.releases_mode}"'))
    if setup.releases_mode != "off" and setup.releases_token:
        entries.append(
            _entry("COS_WEB_RELEASES_TOKEN", f'"{_env_reference("releases_token")}"')
        )
    entries.append(
        _entry(
            "COS_WEB_ENABLE_DOCS",
            f'"{_bool(setup.enable_docs)}"',
            "The browsable /docs and /redoc pages. The machine-readable",
            "documents - /openapi.json, /arazzo.json and /.well-known/ai.json -",
            "are public whatever this says.",
        )
    )
    entries.append(
        _entry(
            "COS_WEB_ENABLE_MCP",
            f'"{_bool(setup.enable_mcp)}"',
            "The MCP endpoint at /mcp: the same workflows, for an agent, through",
            "the same limits a browser meets.",
        )
    )
    if setup.enable_mcp:
        entries.append(
            _entry(
                "COS_WEB_MCP_ALLOWED_HOSTS",
                f'"{setup.mcp_allowed_hosts}"',
                "DNS-rebinding protection. Empty accepts any Host header, which is",
                "right behind a proxy that already decides which names arrive.",
            )
        )
        entries.append(
            _entry(
                "COS_WEB_MCP_MAX_CONCURRENT_WAITS",
                f'"{setup.mcp_max_concurrent_waits}"',
                "Waiting tool calls. Reaching it refuses nothing: the uuid comes",
                "back with a note to poll.",
            )
        )
        auth_notes = [
            "A token verified against the provider's published keys, never one",
            "issued here. Authentication decides who may ask, never how hard:",
            "the limits above are identical for an agent that signed in.",
        ]
        if _uses_authentik(setup) and not setup.mcp_auth_enabled:
            auth_notes += [
                "Off, though the provider below is running and provisioned:",
                "everything the guard needs is already set, so turning this to",
                "true and restarting is the whole of switching it on.",
            ]
        entries.append(
            _entry(
                "COS_WEB_MCP_AUTH_ENABLED",
                f'"{_bool(setup.mcp_auth_enabled)}"',
                *auth_notes,
            )
        )
        if _uses_authentik(setup):
            entries.append(
                _entry(
                    "COS_WEB_MCP_AUTH_ISSUER",
                    f'"{_authentik_issuer(setup)}"',
                    "Authentik builds the issuer from the address the *client* used,",
                    "so this is the public one rather than a container name. The",
                    "blueprint fixes the slug, so there is nothing to look up.",
                )
            )
            entries.append(
                _entry(
                    "COS_WEB_MCP_AUTH_JWKS_URL",
                    f'"{_authentik_jwks_url(setup)}"',
                    "The keys, on the other hand, are fetched by this container,",
                    "which cannot reach the address the browser used. The issuer is",
                    "compared as a string; only this has to resolve from in here.",
                    "`authentik-server` is a network alias, and the hyphen is the",
                    "point of it: a Host header may not carry an underscore.",
                )
            )
            entries.append(
                _entry(
                    "COS_WEB_MCP_AUTH_AUDIENCE",
                    f'"{_env_reference("authentik_client_id")}"',
                    "Authentik puts the provider's client ID in `aud`. Empty would",
                    "accept a token minted for any other application behind the",
                    "same provider.",
                )
            )
            entries.append(
                _entry("COS_WEB_MCP_AUTH_SCOPES", f'"{setup.mcp_auth_scopes}"')
            )
        elif setup.mcp_auth_enabled:
            for key in (
                "mcp_auth_issuer",
                "mcp_auth_audience",
                "mcp_auth_scopes",
                "mcp_auth_jwks_url",
                "mcp_auth_resource_url",
            ):
                entries.append(
                    _entry(SECRET_VARIABLES[key], f'"{_env_reference(key)}"')
                )
    entries.append(
        _entry(
            "COS_WEB_AUDIT_LOG",
            f'"{_bool(setup.audit_log)}"',
            "An audit record per request, as one JSON object per line. Off keeps",
            "the ordinary log to lifecycle markers and uuids.",
        )
    )
    if setup.audit_log:
        entries.append(
            _entry(
                "COS_WEB_AUDIT_LOG_TARGETS",
                f'"{_bool(setup.audit_log_targets)}"',
                "Record the target in the clear rather than as a fingerprint.",
            )
        )
        if setup.audit_salt:
            entries.append(
                _entry("COS_WEB_AUDIT_SALT", f'"{_env_reference("audit_salt")}"')
            )
        if _keeps_audit_file(setup):
            entries.append(
                _entry(
                    "COS_WEB_AUDIT_LOG_FILE",
                    f'"{AUDIT_LOG_DIRECTORY}/{AUDIT_LOG_FILENAME}"',
                    "The audit trail goes to this file on the volume mounted",
                    "below rather than to the container's output, which a",
                    "'docker compose down' would take with it. The file is",
                    "owner-readable only, and the ordinary log stays free of",
                    "audit records rather than carrying a second copy.",
                )
            )
        if _uses_logrotate(setup):
            entries.append(
                _entry(
                    "COS_WEB_AUDIT_LOG_ROTATION",
                    f'"{EXTERNAL_ROTATION}"',
                    "The host's logrotate owns this file - see the .logrotate",
                    "policy written beside this file. All this service does is",
                    "notice that the file it holds was moved aside and reopen",
                    "the new one, so nothing keeps writing to a file nobody",
                    "can find. Two rotators would be one too many, so no",
                    "size-based rotation is set here.",
                )
            )
        elif _keeps_audit_file(setup):
            entries.append(
                _entry(
                    "COS_WEB_AUDIT_LOG_MAX_BYTES",
                    '"10000000"',
                    "Rotated at this size, keeping this many older generations.",
                    "The two together are the most the trail can ever occupy:",
                    "a log nobody rotates fills the volume and takes the",
                    "service down with it.",
                )
            )
            entries.append(_entry("COS_WEB_AUDIT_LOG_BACKUPS", '"5"'))
    entries.append(
        _entry(
            "COS_WEB_PURGE_TOKEN",
            f'"{_env_reference("purge_token")}"',
            "Erasure on request. DELETE /api/purge answers 404 until a credential",
            "is set, because the call deletes results belonging to whoever is",
            "currently reading them.",
        )
    )
    entries.append(
        _entry(
            "COS_WEB_PURGE_SIGNING_KEY",
            f'"{_env_reference("purge_signing_key")}"',
            "Makes the proof of deletion verifiable after the data is gone.",
        )
    )
    entries.append(
        _entry(
            "COS_WEB_EXPORT_SIGNING_KEY",
            f'"{_env_reference("export_signing_key")}"',
            "HMAC-SHA256 over the exact bytes of every downloaded report.",
        )
    )
    entries.extend(_encryption_environment(setup))
    return entries


def _encryption_environment(setup: Setup) -> list[EnvEntry]:
    """The two services have to agree on this, so it is built once."""
    entries = [
        _entry(
            "COS_WEB_ENCRYPT_RESULTS",
            f'"{_bool(setup.encrypt_results)}"',
            "AES-256-GCM on the stored document. The web process and the worker",
            "must agree and need the same key: the worker writes the document",
            "and the web process reads it back. A process asked to encrypt",
            "without a usable key refuses to start rather than store plaintext.",
        )
    ]
    if setup.encrypt_results:
        entries.append(
            _entry("COS_WEB_ENCRYPTION_KEY_1", f'"{_env_reference("encryption_key")}"')
        )
    return entries


def _worker_environment(setup: Setup) -> list[EnvEntry]:
    """What the worker reads. This is where the load on other hosts is set."""
    entries: list[EnvEntry] = [
        _entry(
            "COS_WEB_REDIS_URL",
            f'"redis://:{_env_reference("redis_password")}@redis:6379/0"',
            "Redis requires a password and sits on a network of its own.",
            "The value lives in .env, never here.",
        ),
        _entry("COS_WEB_RESULT_TTL", f'"{setup.result_ttl}"'),
        _entry(
            "COS_WEB_MAX_WORKERS",
            f'"{setup.max_workers}"',
            "Scans running at once, and probes in flight within one scan. These",
            "two numbers are the whole of this service's load on the outside",
            "world, and they are only ever set here - no request can raise them.",
        ),
        _entry("COS_WEB_SCAN_CONCURRENCY", f'"{setup.scan_concurrency}"'),
        _entry("COS_WEB_SCAN_TIMEOUT", f'"{setup.scan_timeout}"'),
        _entry("COS_WEB_JOB_TIMEOUT", f'"{setup.job_timeout}"'),
        _entry(
            "COS_WEB_ALLOW_PRIVATE_TARGETS",
            f'"{_bool(setup.allow_private_targets)}"',
            "Refuse private, loopback and link-local targets. True only for a",
            "deployment meant to scan its own network.",
        ),
        _entry(
            "COS_WEB_CHECK_DEBUG_PORTS",
            f'"{_bool(setup.check_debug_ports)}"',
            "Connecting to extra ports on a host somebody submitted is a port",
            "scan. Off unless the targets are your own.",
        ),
        _entry(
            "COS_WEB_IPV6_ENABLED",
            f'"{_bool(setup.ipv6_enabled)}"',
            "Whether this container can dial an IPv6 address at all. False -",
            "the default - skips the IPv4/IPv6 TLS-parity check and notes why",
            "instead of reporting an instance's IPv6 side as unreachable for a",
            "limitation of this deployment rather than of the instance.",
        ),
        _entry("COS_WEB_RELEASES_MODE", f'"{setup.releases_mode}"'),
    ]
    if setup.releases_mode != "off" and setup.releases_token:
        entries.append(
            _entry("COS_WEB_RELEASES_TOKEN", f'"{_env_reference("releases_token")}"')
        )
    if setup.allowed_hosts:
        entries.append(
            _entry(
                "COS_WEB_ALLOWED_HOSTS",
                f'"{setup.allowed_hosts}"',
                "Hostnames exempt from the SSRF guard, for an on-premise instance",
                "whose name resolves to a private address.",
            )
        )
    entries.extend(_encryption_environment(setup))
    return entries


def _render_environment(entries: Sequence[EnvEntry], indent: str) -> str:
    lines: list[str] = []
    for entry in entries:
        for line in _wrap(entry.comment, 66) if entry.comment else []:
            lines.append(f"{indent}# {line}")
        lines.append(f"{indent}{entry.name}: {entry.value}")
    return "\n".join(lines)


def _image_block(setup: Setup, container: str) -> str:
    if setup.image_source == "dockerhub":
        return (
            f"    image: {setup.image_ref}\n"
            "    pull_policy: always\n"
            f"    container_name: {setup.project_name}-{container}\n"
        )
    return (
        "    build:\n"
        f"      context: {setup.build_context}\n"
        "      dockerfile: docker/Dockerfile.web\n"
        "    image: check-opencloud-security-web:latest\n"
        f"    container_name: {setup.project_name}-{container}\n"
    )


def _update_label(setup: Setup) -> str:
    """The label Watchtower watches for, or nothing when updates are manual.

    The label is what keeps Watchtower inside this stack: without it, every
    container on the host would be fair game for a restart.
    """
    if not setup.auto_updates:
        return ""
    return '    labels:\n      com.centurylinklabs.watchtower.enable: "true"\n'


def _networks_block(setup: Setup) -> str:
    """The bottom-level ``networks:`` section.

    Compose does not turn IPv6 on for a network just because the daemon
    supports it - ``enable_ipv6`` has to be set on each one. An operator who
    confirmed outbound IPv6 connectivity needs it on both networks the stack
    uses: ``default``, where the two application containers sit, and
    ``scanner_internal``, where Redis sits.
    """
    if not setup.ipv6_enabled:
        return """networks:
  # The two application containers keep the default network, because a scan is
  # an outbound HTTP request and the web service is published on a port. Redis
  # is only on this one, which has no gateway at all.
  scanner_internal:
    internal: true
"""
    return """networks:
  default:
    enable_ipv6: true
  # The two application containers keep the default network, because a scan is
  # an outbound HTTP request and the web service is published on a port. Redis
  # is only on this one, which has no gateway at all.
  scanner_internal:
    internal: true
    enable_ipv6: true
"""


def _watchtower_service(setup: Setup) -> str:
    """Automatic updates, for the deployment that asked for them."""
    if not setup.auto_updates:
        return ""
    return f"""
  # Watchtower, which is what makes the updates above automatic. Once a day
  # it asks the registry whether an image this stack runs has moved, pulls the
  # new one and restarts the container. Only containers carrying the enable
  # label are touched - without WATCHTOWER_LABEL_ENABLE it would update every
  # container on the host - and a locally built image is skipped rather than
  # replaced, because Watchtower cannot build anything.
  #
  # The Docker socket is the whole of its authority, and handing a container
  # the daemon socket is handing it the host. It is mounted read-write because
  # restarting containers *is* writing. A rootless Docker serves its socket
  # under /run/user/<uid>; the wizard detected {setup.watchtower_socket} for
  # the user that ran it.
  watchtower:
    image: {WATCHTOWER_IMAGE}
    container_name: {setup.project_name}-watchtower
    restart: unless-stopped
    volumes:
      - {setup.watchtower_socket}:/var/run/docker.sock
    environment:
      # Six-field cron: 4am every day. A failed check tries again tomorrow.
      WATCHTOWER_SCHEDULE: "0 0 4 * * *"
      # Delete the superseded image, or the disk fills one layer per update.
      WATCHTOWER_CLEANUP: "true"
      WATCHTOWER_LABEL_ENABLE: "true"
    security_opt:
      - no-new-privileges:true
"""


def render_compose_file(setup: Setup, name: str = "docker-compose.yml") -> str:
    """The compose file: every non-secret answer, inline and explained.

    ``name`` is only used in the comment at the top, so that the command the
    file suggests is the one that actually starts it.
    """
    secrets_note = (
        "# Secrets live in .env next to this file and are referenced as ${NAME}\n"
        "# below, so this file carries no credential and can be committed.\n"
    )
    header = (
        "# The check-opencloud-security web application: frontend, worker and Redis.\n"
        "#\n"
        f"#   docker compose -f {name} up -d\n"
        f"#   open http://{setup.bind_address}:{setup.host_port}\n"
        "#\n"
        "# Written by docker/setup-wizard.py. Edit it freely - it is a plain\n"
        "# compose file - or run the wizard again to start from a clean one.\n"
        "#\n"
        f"{secrets_note}"
        "#\n"
        "# `web_app` serves the pages and the API; `arq_worker` runs the scans.\n"
        "# Both run the same image and differ only in the command, which is what\n"
        "# keeps the code describing a result and the code producing it together.\n"
        "#\n"
        "# Two rules this file exists to enforce:\n"
        "#\n"
        "# - concurrency is set here and nowhere else. Nothing a visitor sends can\n"
        "#   change COS_WEB_MAX_WORKERS or COS_WEB_SCAN_CONCURRENCY, and when every\n"
        "#   worker is busy the next submission queues rather than being refused;\n"
    )
    if _persists_redis(setup):
        header += (
            "# - Redis is capped and evicts rather than growing, but this deployment\n"
            "#   asked it to persist: unlike the default stack, what it holds is\n"
            "#   also on a disk. See the comment on the service itself.\n"
        )
    else:
        header += (
            "# - Redis is a cache, not a database. It writes nothing to disk, it is\n"
            "#   capped, and it evicts rather than growing.\n"
        )
    if _keeps_audit_file(setup):
        header += (
            "#\n"
            "# The audit trail is the one thing here that outlives the containers:\n"
            f"# it is written to {AUDIT_LOG_DIRECTORY}/{AUDIT_LOG_FILENAME} on the mount\n"
            "# declared under the web service, rotated so it cannot fill the disk.\n"
        )
    if _uses_authentik(setup):
        header += (
            "#\n"
            "# This stack brings its own identity provider. Authentik guards /mcp,\n"
            "# and this service only ever *verifies* the tokens it issues: the\n"
            "# signature against Authentik's published keys, the issuer, the\n"
            "# audience and the expiry. It holds no account, session or client\n"
            "# secret, and the sign-in changes who may ask, never how hard - the\n"
            "# rate limits, the cooldown and the SSRF guard are identical for an\n"
            "# agent that signed in.\n"
            "#\n"
            f"#   open {setup.authentik_url}/if/flow/initial-setup/"
            "   (the trailing slash matters)\n"
        )
    return f"""{header}
name: {setup.project_name}

services:
  web_app:
{_image_block(setup, "web")}    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
    ports:
      - "{setup.bind_address}:{setup.host_port}:8811"
    environment:
{_render_environment(_web_environment(setup), "      ")}
    networks:
      - default
      - scanner_internal
{_audit_mount(setup)}    read_only: true
    tmpfs:
      - /tmp:size=16m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
{_update_label(setup)}
  arq_worker:
{_image_block(setup, "worker")}    restart: unless-stopped
    command: ["python", "-m", "webapp.tasks"]
    depends_on:
      redis:
        condition: service_healthy
    environment:
{_render_environment(_worker_environment(setup), "      ")}
    networks:
      - default
      - scanner_internal
    # The image health check probes the web server. The worker has no HTTP
    # listener, so verify its PID and the Redis connection it needs instead.
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import os; from redis import Redis; os.kill(1, 0); Redis.from_url(os.environ['COS_WEB_REDIS_URL']).ping()",
        ]
      interval: 30s
      timeout: 5s
      start_period: 10s
      retries: 3
    read_only: true
    tmpfs:
      - /tmp:size=16m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
{_update_label(setup)}
  redis:
    image: redis:8.10-alpine
    container_name: {setup.project_name}-redis
    restart: unless-stopped
{_redis_storage_comment(setup)}    #
    # It also asks for a password. Redis answers whoever reaches it, and what
    # it holds is every live scan and every result still inside its TTL, so
    # "nothing else is on this network" is an assumption rather than a
    # control. The password comes from .env; the network below is the second
    # half of the same argument.
    command: >
      redis-server
{_redis_storage_command(setup)}      --maxmemory {setup.redis_maxmemory}
      --maxmemory-policy allkeys-lru
      --requirepass "{_env_reference("redis_password")}"
    environment:
      # redis-cli reads this, so the health check authenticates without the
      # password appearing in its own command line.
      REDISCLI_AUTH: "{_env_reference("redis_password")}"
    # No `ports`: nothing outside this stack has any business connecting, and
    # `internal` means the network has no route off the host either.
    networks:
      - scanner_internal
{_redis_mount(setup)}    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    security_opt:
      - no-new-privileges:true
{_update_label(setup)}{_watchtower_service(setup)}{_authentik_services(setup)}
{_networks_block(setup)}{_volumes_block(setup)}"""


def write_files(
    setup: Setup,
    compose_path: Path,
    env_path: Path,
) -> list[str]:
    """Write the files, the `.env` owner-readable only.

    Returns what was written, so the wizard can tell the operator rather than
    leaving them to find a blueprint they did not ask for.
    """
    compose_path.parent.mkdir(parents=True, exist_ok=True)
    compose_path.write_text(
        render_compose_file(setup, compose_path.name), encoding="utf-8"
    )
    written = [str(compose_path)]

    # Create with the right mode rather than fixing it afterwards: a secret
    # that was world-readable for a millisecond was world-readable.
    descriptor = os.open(
        env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(render_env_file(setup))
    os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
    written.append(f"{env_path} (owner-readable only)")

    # Beside the compose file rather than in /etc/logrotate.d: installing it
    # needs root, and a wizard that writes outside the directory it was given
    # is one an operator cannot run to see what it would do.
    if _uses_logrotate(setup):
        policy = compose_path.parent / logrotate_filename(setup)
        policy.write_text(render_logrotate_file(setup), encoding="utf-8")
        os.chmod(policy, 0o644)
        written.append(f"{policy} (install it into /etc/logrotate.d)")

    blueprint = _copy_blueprint(setup, compose_path.parent)
    if blueprint:
        written.append(blueprint)
    return written


def _copy_blueprint(setup: Setup, output_dir: Path) -> str | None:
    """Put the provisioning blueprint next to the compose file that mounts it.

    The generated stack mounts a relative path, so the blueprint has to travel
    with it - a deployment directory somewhere else on the host cannot reach
    back into a checkout, and a stack whose blueprint is missing starts and
    then refuses every token with nothing in the log to say why.
    """
    if not _uses_authentik(setup) or not BLUEPRINT_SOURCE.is_file():
        return None
    destination = output_dir / BLUEPRINT_RELATIVE
    if destination.resolve() == BLUEPRINT_SOURCE.resolve():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(BLUEPRINT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(destination, 0o644)
    return str(destination)


def summarise(setup: Setup) -> list[str]:
    """The answers, for the confirmation before anything is written."""
    lines = []
    for item in fields(setup):
        if not _relevant(item.name, setup):
            continue
        value = getattr(setup, item.name)
        if item.name in SECRET_VARIABLES and value:
            value = "set (written to .env)"
        lines.append(f"    {item.name:<26} {_format_default(value)}")
    return lines


# --- the command ------------------------------------------------------------
def _refuse_shipped(path: Path) -> str | None:
    """Whether the target is one of the project's own compose files."""
    if path.parent.resolve() == SCRIPT_DIR and path.name in SHIPPED_COMPOSE_FILES:
        return (
            f"{path.name} in {SCRIPT_DIR} ships with the project, and the next "
            "update would overwrite your deployment. Choose another name with "
            "--compose-file, or another directory with --output-dir."
        )
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setup-wizard.py",
        description=(
            "Set up a Docker deployment of the check-opencloud-security web "
            "application: writes a docker-compose.yml and a .env holding the "
            "secrets it refers to. Unrelated to the plugin's own "
            "--configure wizard, which sets up a monitoring check."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Where to write both files. Default: the current directory.",
    )
    parser.add_argument(
        "--compose-file",
        default="docker-compose.yml",
        help="Name of the generated compose file.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Name of the generated secrets file.",
    )
    parser.add_argument(
        "--preset",
        choices=("public", "private"),
        default="public",
        help=(
            "Starting answers. 'public' is a service open to anybody that "
            "refuses private targets; 'private' scans its own network, stays "
            "out of search engines and keeps an audit log."
        ),
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Ask nothing and take every default, generating the credentials.",
    )
    parser.add_argument(
        "--auto-updates",
        action="store_true",
        help=(
            "Add Watchtower to the generated stack so the pulled images are "
            "updated automatically, scoped to this stack's own containers."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files without asking.",
    )

    sign_in = parser.add_argument_group(
        "sign-in",
        "The optional sign-in on /mcp. Off unless asked for, and it changes "
        "who may ask, never how hard: an authenticated agent meets the same "
        "rate limits, cooldown and SSRF guard as a browser.",
    )
    sign_in.add_argument(
        "--sign-in",
        action="store_true",
        help=(
            "Require a token on /mcp. The provider is one you already run, "
            "unless --with-authentik adds one."
        ),
    )
    sign_in.add_argument(
        "--with-authentik",
        action="store_true",
        help=(
            "Add Authentik and its database to the generated stack, "
            "provisioned to issue those tokens. Does not turn the sign-in on "
            "by itself: add --sign-in for that, or switch it on later once "
            "the provider is up. Left out, nothing of Authentik is written."
        ),
    )

    mail = parser.add_argument_group(
        "mail",
        "SMTP for Authentik, which is the only part of this stack that sends "
        "any: a password recovery, an invitation, an expiring-password notice. "
        "Leave the host unset and Authentik keeps its built-in local delivery. "
        "The password is never a flag - it is read from AUTHENTIK_EMAIL_PASSWORD "
        "in the environment, because a command line is visible in `ps` and ends "
        "up in a shell history.",
    )
    mail.add_argument("--smtp-host", default=None, help="SMTP server, e.g. smtp.example.com.")
    mail.add_argument("--smtp-port", type=int, default=None, help="587 for STARTTLS, 465 for TLS.")
    mail.add_argument("--smtp-username", default=None, help="Account to authenticate as.")
    mail.add_argument("--smtp-from", default=None, help="From address the recipient sees.")
    mail.add_argument(
        "--smtp-security",
        choices=("starttls", "ssl", "none"),
        default=None,
        help="STARTTLS (default), implicit TLS, or neither on a trusted relay.",
    )
    mail.add_argument(
        "--smtp-timeout",
        type=int,
        default=None,
        help="Seconds a submission may take before Authentik gives up.",
    )
    return parser


def _apply_flags(setup: Setup, args: argparse.Namespace) -> None:
    """Answers given on the command line, which the prompts then offer back.

    A flag is a default rather than a decision: an interactive run shows it in
    brackets and Enter keeps it, so `--smtp-host` and a walk through the
    questions do not contradict each other.
    """
    if args.sign_in:
        setup.enable_mcp = True
        setup.mcp_auth_enabled = True
    if args.auto_updates:
        setup.auto_updates = True
    # Deliberately does not turn the sign-in on. Provisioning a provider and
    # requiring a token are separate decisions, and a flag that quietly made
    # the second one would be a flag that closed an endpoint somebody meant
    # to leave open.
    if args.with_authentik:
        setup.enable_mcp = True
        setup.deploy_authentik = True

    for flag, key in (
        ("smtp_host", "smtp_host"),
        ("smtp_port", "smtp_port"),
        ("smtp_username", "smtp_username"),
        ("smtp_from", "smtp_from"),
        ("smtp_security", "smtp_security"),
        ("smtp_timeout", "smtp_timeout"),
    ):
        value = getattr(args, flag)
        if value is not None:
            setattr(setup, key, value)

    # Never a flag: a command line is visible to every process on the host.
    password = os.environ.get("AUTHENTIK_EMAIL_PASSWORD", "").strip()
    if password:
        setup.smtp_password = password


def detect_docker_socket() -> str:
    """The Docker socket of the user running this wizard.

    Watchtower has to reach the same daemon the containers run on. A rootless
    Docker serves its socket under the user's runtime directory rather than
    /var/run, so which path answers is a fact about the installation, not a
    preference. ``DOCKER_HOST`` wins when it is set, because that is the
    socket every other Docker command in this shell is already using.
    """
    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host.startswith("unix://"):
        return docker_host[len("unix://"):]
    getuid = getattr(os, "getuid", None)
    if getuid is not None and getuid() != 0:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{getuid()}"
        rootless = Path(runtime_dir) / "docker.sock"
        if rootless.exists():
            return str(rootless)
    return "/var/run/docker.sock"


def _default_build_context(output_dir: Path) -> str:
    """The path from the generated file back to the repository root.

    Relative while that stays readable - a file written into ``docker/`` says
    ``..``, which is what the shipped compose files say - and absolute once
    the relative form would be a walk up out of the filesystem and back down
    again, which nobody can check by eye.
    """
    try:
        relative = os.path.relpath(REPO_ROOT, output_dir.resolve())
    except ValueError:  # a different drive on Windows
        return str(REPO_ROOT)
    return relative if not relative.startswith(os.path.join("..", "..")) else str(REPO_ROOT)


def _apply_preset(setup: Setup, preset: str) -> None:
    if preset == "private":
        for key, value in PRIVATE_PRESET.items():
            setattr(setup, key, value)


def _generate_unattended(setup: Setup) -> None:
    """Credentials for a run that asks nothing.

    An unattended install still gets an erasure credential and a signing key,
    because the alternative is a deployment where nobody can ask for a
    deletion until somebody notices.
    """
    setup.purge_token = setup.purge_token or secrets.token_hex(32)
    setup.redis_password = setup.redis_password or secrets.token_urlsafe(32)
    setup.purge_signing_key = setup.purge_signing_key or secrets.token_hex(32)
    setup.export_signing_key = setup.export_signing_key or secrets.token_hex(32)
    if setup.audit_log and not setup.audit_salt:
        setup.audit_salt = secrets.token_hex(16)
    if setup.encrypt_results and not setup.encryption_key:
        setup.encryption_key = secrets.token_hex(32)


def _read_existing_env(setup: Setup, env_path: Path) -> int:
    """Values from a `.env` that is already there, as the defaults.

    Re-running the wizard against an existing deployment should feel like
    editing it, not like starting over: every credential it already holds is
    offered back rather than regenerated, so a token something else depends
    on survives the second run. Command-line flags are applied afterwards
    and still win.
    """
    if not env_path.is_file():
        return 0
    variables = {variable: key for key, variable in SECRET_VARIABLES.items()}
    loaded = 0
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if not separator:
            continue
        key = variables.get(name.strip())
        value = value.strip()
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        if key and value:
            setattr(setup, key, value)
            loaded += 1
    return loaded


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    output_dir = Path(args.output_dir).expanduser()
    compose_path = output_dir / args.compose_file
    env_path = output_dir / args.env_file

    refusal = _refuse_shipped(compose_path)
    if refusal:
        print(f"Refusing to write it: {refusal}", file=sys.stderr)
        return 2

    setup = Setup()
    _apply_preset(setup, args.preset)
    reused = _read_existing_env(setup, env_path)
    _apply_flags(setup, args)
    setup.build_context = _default_build_context(output_dir)
    setup.watchtower_socket = setup.watchtower_socket or detect_docker_socket()

    wizard = Wizard(setup, interactive=not args.non_interactive)
    wizard.say("Docker setup for the check-opencloud-security web application")
    wizard.say()
    for line in _wrap(
        "This writes a compose file with the whole stack and a .env holding the "
        "credentials it refers to - and, if you ask it to bring an identity "
        "provider, the blueprint that provisions one. Press Enter to accept the value "
        "in brackets; every question explains what it does and shows an example. "
        "Nothing is written until you confirm at the end."
    ):
        wizard.say(f"  {line}")
    wizard.say()
    wizard.say(f"  Compose file: {compose_path}")
    wizard.say(f"  Secrets file: {env_path}")
    wizard.say(f"  Preset:       {args.preset}")
    if reused:
        wizard.say()
        wizard.say(
            f"  {env_path} is already there: its values are the defaults below,"
        )
        wizard.say("  so nothing you configured before is generated anew.")
    wizard.say()
    wizard.say(
        "  This is not the plugin's --configure wizard, which sets up a"
    )
    wizard.say("  monitoring check against one instance.")

    try:
        run_questions(wizard)
        _generate_unattended(setup)
        _finalise(setup)

        wizard.say()
        wizard.say("\u2500\u2500 Summary " + "\u2500" * 57)
        for line in summarise(setup):
            wizard.say(line)

        warnings = check_consistency(setup)
        if warnings:
            wizard.say()
            wizard.say("  Worth a second look:")
            for warning in warnings:
                for index, line in enumerate(_wrap(warning, 68)):
                    wizard.say(f"    {'-' if index == 0 else ' '} {line}")

        wizard.say()
        for path in (compose_path, env_path):
            if path.exists() and not args.force and not wizard.confirm(
                f"{path} exists. Overwrite it?", default=False
            ):
                print("Nothing written.", file=sys.stderr)
                return 1
        if not wizard.confirm("Write it all out now?", default=True):
            print("Nothing written.", file=sys.stderr)
            return 1
    except SetupAborted as error:
        print(f"\nSetup aborted: {error}", file=sys.stderr)
        return 1

    written = write_files(setup, compose_path, env_path)

    wizard.say()
    for path in written:
        wizard.say(f"  Wrote {path}")
    wizard.say()
    wizard.say("  Next:")
    wizard.say(f"    cd {output_dir}")
    # Before `up`, not after: a bind mount Docker has to invent is created
    # owned by root, and the container that then cannot write to it is the
    # one keeping the audit trail.
    if setup.audit_storage == "filesystem" and setup.audit_log_path:
        wizard.say(
            f"    mkdir -p {setup.audit_log_path} && "
            f"sudo chown {WEB_IMAGE_UID} {setup.audit_log_path}"
        )
    if setup.redis_persistence == "filesystem" and setup.redis_data_path:
        wizard.say(
            f"    mkdir -p {setup.redis_data_path} && "
            f"sudo chown {REDIS_IMAGE_UID} {setup.redis_data_path}"
        )
    if _uses_logrotate(setup):
        name = logrotate_filename(setup)
        wizard.say(
            f"    sudo install -m 0644 -o root -g root {name} "
            f"/etc/logrotate.d/{setup.project_name}-audit"
        )
    build = " --build" if setup.image_source == "build" else ""
    wizard.say(f"    docker compose -f {args.compose_file} up -d{build}")
    wizard.say(f"    open http://{setup.bind_address}:{setup.host_port}")
    if _uses_authentik(setup):
        wizard.say()
        wizard.say("  Then set the first Authentik password, which is the one")
        wizard.say("  account it starts with - the OAuth2 provider is already there:")
        wizard.say(f"    open {setup.authentik_url}/if/flow/initial-setup/")
        if not setup.smtp_host:
            wizard.say()
            wizard.say("  No SMTP server was configured, so a password recovery will")
            wizard.say("  not arrive. AUTHENTIK_EMAIL_* in the generated file is where")
            wizard.say("  that goes; docs/authentik.md explains it.")
    wizard.say()
    wizard.say(f"  Every setting is documented in {PROJECT_URL}#readme,")
    wizard.say("  and in docs/webapp.md in full.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
