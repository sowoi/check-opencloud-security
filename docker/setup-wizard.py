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

Two things here can want somebody signed in: the MCP endpoint at ``/mcp``, and
the operator's area at ``/admin``, which has no other way in at all. Ask for
either and it asks for the issuer, the audience and the keys of the provider
you already run, which is what an estate that wants one usually has. Ask for
``--with-authentik`` as well and it provisions a provider instead: Authentik
and its database join the stack, those values are derived rather than asked
for, and the blueprints are written beside the compose file that mounts them -
the OAuth2 one that issues tokens for ``/mcp``, and, where there is an area to
guard, the proxy one that signs an operator into ``/admin``. Nothing of
Authentik appears in a deployment that did not ask for it. Its mail settings
are asked for when it does - the server, the port, the transport security,
whether it wants an account and which - because an identity provider that
cannot send a password recovery is one nobody can get back into.

Name a reverse proxy and it writes that configuration too: nginx, Apache,
Caddy or Traefik, in the directory beside the compose file, with TLS, the
unbuffered ``/mcp`` stream, an ``X-Forwarded-For`` the client cannot choose
and - for the three that can ask an outpost before serving a request - the
forward auth in front of ``/admin``. When the stack brings Authentik, the same
file carries a second site for it, at the host name of its public address,
because that is where every sign-in sends a browser.

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
the compose files that ship with this project are refused, because the next
``git pull`` would take a hand-made deployment with it - unless ``--force``
says to replace them in place, which reconfigures the stack a checkout already
runs without moving it to a directory of its own. A ``.env``
that is already there is read back instead: its values become the defaults
the questions offer, so re-running the wizard against a live deployment edits
it rather than regenerating every credential it holds.

Non-interactive use, for a test or an unattended install:

    ./setup-wizard.py --non-interactive --preset private --output-dir /srv/scan
"""

from __future__ import annotations

import argparse
import difflib
import getpass
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess  # nosec B404 - runs `docker compose`, only when the operator agrees
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

# The release this copy of the wizard was published with. Empty here, on
# purpose: pyproject.toml is the only place a version is written by hand, and
# scripts/build_wizard_release.py stamps this line into the copy a release
# attaches for download. A checkout or the web bundle has pyproject.toml beside
# it instead, and `--version` reads it from there.
RELEASE_VERSION = ""

PROJECT_URL = "https://github.com/sowoi/check-opencloud-security"
DOCKERHUB_IMAGE = "okxo/opencloud-scanner:latest"

# The identity provider this project ships a stack for, and the image tag
# `docker-compose.authentik.yml` pins. Keep the two together: a wizard that
# generates a different version from the file next to it is a support case.
AUTHENTIK_IMAGE = "ghcr.io/goauthentik/server"
AUTHENTIK_TAG = "2026.8.4"
BLUEPRINT_DIRECTORY = Path("authentik") / "blueprints"
BLUEPRINT_RELATIVE = BLUEPRINT_DIRECTORY / "opencloud-scanner.yaml"

# The second blueprint, and the only way into the operator's area. It
# provisions a *proxy* provider rather than an OAuth2 one, so it is written
# only for a deployment that asked for /admin - an unused provider in a
# directory is one more thing that can be bound to the wrong application.
ADMIN_BLUEPRINT_RELATIVE = BLUEPRINT_DIRECTORY / "opencloud-admin.yaml"

# The two that make the provider usable without its admin interface, written
# wherever the stack brings Authentik: a second factor required at every
# sign-in, and the invitation-only flow in which a listed person picks a
# password and enrols that factor.
MFA_BLUEPRINT_RELATIVE = BLUEPRINT_DIRECTORY / "opencloud-mfa.yaml"
ENROLLMENT_BLUEPRINT_RELATIVE = BLUEPRINT_DIRECTORY / "opencloud-enrollment.yaml"

# Where an outpost ends the session it started. A local path, because the
# reverse proxy that routes `/outpost.goauthentik.io/` for the forward auth is
# the same one serving /admin - a stack where this path does not answer is one
# where signing *in* did not work either.
AUTHENTIK_SIGN_OUT_PATH = "/outpost.goauthentik.io/sign_out"

# Where the outpost answers, and the prefix the reverse proxy has to route to
# it for the forward auth to work at all. Authentik's *embedded* outpost serves
# both on the server container's HTTP port, which is why this stack runs no
# outpost container of its own.
AUTHENTIK_OUTPOST_PREFIX = "/outpost.goauthentik.io"

# The header the proxy in front of /admin adds, and the ones the outpost
# answers with. The service believes the second group only because the first
# one arrived: see webapp/admin_auth.py, which refuses anything without it.
ADMIN_PROXY_HEADER = "X-COS-Admin-Proxy"
ADMIN_IDENTITY_HEADERS = (
    "X-authentik-username",
    "X-authentik-groups",
    "X-authentik-email",
)

# The path the operator's area lives at, as the proxy has to match it.
ADMIN_PATH = "/admin"

# The group the admin blueprint creates and binds the area's application to.
# Being in it is what gets somebody through the sign-in; COS_WEB_ADMIN_USERS
# is a second, separate list, and both have to name the same person.
AUTHENTIK_OPERATOR_GROUP = "opencloud-scanner-operators"

# Where a listed person creates their account, with the invitation token as
# `itoken`. The enrollment blueprint fixes the slug. The trailing slash
# matters: without it the flow interface answers 404.
AUTHENTIK_ENROLLMENT_PATH = "/if/flow/opencloud-scanner-enrollment/"

# The account Authentik bootstraps itself with. The wizard gives it a random
# password in .env, which closes the initial-setup flow - otherwise whoever
# reached it first would become the administrator - and leaves a way back in
# for somebody who lost their second factor.
AUTHENTIK_BOOTSTRAP_USER = "akadmin"

# The MCP endpoint, which is the one path here that answers with an event
# stream and therefore the one a proxy must not buffer.
MCP_PATH = "/mcp"

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

# The Redis image the stack runs. Named once because it is also what fixes the
# ownership of a bind mount on a rootless Docker: it is pulled anyway, so the
# command costs no download of an image nobody asked for.
REDIS_IMAGE = "redis:8.10-alpine"

# How the Docker daemon runs. It matters for exactly one thing here, and it is
# the thing that decides whether a bind mount is writable: on a rootless
# daemon, uid 10001 in a container is not uid 10001 on the host but the
# user's subordinate uid at that offset, so `chown 10001` on the host hands
# the directory to somebody the container never is.
DOCKER_MODES = ("rootful", "rootless")

# Where the host records which subordinate ids each user may map. Read, never
# written; module constants so a test can point them at a file of its own.
SUBUID_FILE = Path("/etc/subuid")
SUBGID_FILE = Path("/etc/subgid")

# Where a deployment keeps things, when it keeps them at all.
STORAGE_CHOICES = ("none", "volume", "filesystem")

# The directories a bind mount defaults to, beside the generated compose file.
# Relative on purpose, and relative with a `./` on purpose: Compose resolves a
# relative bind mount against the directory the compose file is in, while a
# source with no `./` in front of it is not a path at all - `data:/data` is a
# *named volume* called data. One character apart, and the difference between
# a directory an operator can back up and one Docker invented.
DEFAULT_REDIS_DATA_PATH = "./data"
DEFAULT_AUDIT_LOG_PATH = "./audit"

# The reverse proxies the wizard can write a working configuration for. They
# are the ones an estate already runs; anything else is served by the notes in
# docs/reverse-proxy.md, which this generator follows.
PROXY_CHOICES = ("none", "nginx", "apache", "caddy", "traefik")

# Which of them can ask an outpost about a request before passing it on. The
# operator's area needs that and nothing else will do, so a deployment that
# picks one of the others is told rather than handed a config that would serve
# /admin to whoever asked.
FORWARD_AUTH_PROXIES = ("nginx", "caddy", "traefik")

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
#
# The maintained fork, not containrrr/watchtower. That image was archived in
# December 2025 and always speaks Docker API 1.25, which Docker 29 refuses -
# 29.0 wants 1.44, 29.3 and later 1.40 - so it panics on start unless
# DOCKER_API_VERSION is pinned by hand. The fork negotiates the version with
# the daemon, which is why no version is pinned here either: a pin is correct
# for exactly the daemons that happen to accept it, until the next one raises
# the minimum again. Its variables and enable label are the same.
WATCHTOWER_IMAGE = "nickfedor/watchtower:latest"

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

# What an operator can type instead of an answer. Bare words rather than a
# punctuation prefix, because 'generate' was already one and a wizard with two
# conventions has neither.
BACK_WORDS = {"b", "back"}
REST_WORD = "rest"
CLEAR_WORD = "-"
HELP_WORD = "?"

#: Returned by :meth:`Wizard.ask` instead of an answer: go back one question,
#: or stop asking and take every remaining default.
BACK = "back"
REST = "rest"


# How every owner-readable file is opened. O_NOFOLLOW refuses a symlink in
# the file's place: without it a link left where `.env` belongs - dangling,
# so it did not even count as an existing file - carried every generated
# secret to wherever it pointed. Windows has no such flag and no such link.
PRIVATE_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)


class SetupAborted(RuntimeError):
    """Raised when the operator interrupts the wizard."""


# --- the version ------------------------------------------------------------
def _pyproject_version(path: Path) -> str:
    """The version of this project in a pyproject.toml, or ``""``.

    Read with a regular expression rather than tomllib, which Python 3.10 does
    not have - and only from the ``[project]`` table of a file that names this
    project, so a wizard copied into somebody else's repository does not
    report that repository's version as its own.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    table = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
    if not table:
        return ""
    body = table.group(1)
    name = re.search(r'^name\s*=\s*"([^"]+)"', body, re.MULTILINE)
    version = re.search(r'^version\s*=\s*"([^"]+)"', body, re.MULTILINE)
    if not (name and version) or name.group(1) != "check-opencloud-security":
        return ""
    return version.group(1)


def wizard_version() -> str:
    """The release this wizard came from, as ``--version`` prints it."""
    if RELEASE_VERSION:
        return RELEASE_VERSION
    return _pyproject_version(REPO_ROOT / "pyproject.toml")


def version_line() -> str:
    version = wizard_version()
    if version:
        return f"setup-wizard.py {version}"
    return (
        "setup-wizard.py (version unknown: not a release download, and no "
        "pyproject.toml of this project beside it)"
    )


# --- presentation -----------------------------------------------------------
# Colour and a little structure, written by hand. Rich, questionary, InquirerPy
# and prompt_toolkit all draw a nicer prompt than this, and every one of them
# is a package to install first - on a host that, by design, has Docker and a
# Python interpreter and nothing else. A wizard that begins with `pip install`
# has already failed the operator it exists for.
#
# So it is ANSI escapes, and only where they are wanted: a terminal on the
# other end, no NO_COLOR, no TERM=dumb. Piped, redirected or under a test, not
# one escape is written and every line is exactly the plain text it was
# before, which is what the tests and anybody grepping a log read.
_ANSI = {
    "reset": "0",
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
}

# The widest any drawn element or wrapped paragraph gets. Narrower when the
# terminal is: an SSH session in a split pane is often 60 columns, and text
# wrapped for 80 re-wraps into a staircase there.
_FRAME_WIDTH = 66
_TEXT_WIDTH = 72
_NARROWEST = 40


def _columns() -> int:
    """The terminal's width, or 80 when there is no terminal to ask."""
    return shutil.get_terminal_size((80, 24)).columns


def frame_width() -> int:
    return max(_NARROWEST, min(_FRAME_WIDTH, _columns() - 4))


def text_width(indent: int = 6) -> int:
    """How wide a paragraph indented by ``indent`` may be."""
    return max(_NARROWEST - indent, min(_TEXT_WIDTH, _columns() - indent - 2))


def _colour_wanted(stream: Any = None) -> bool:
    """Whether escapes would reach a terminal that renders them."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    stream = stream if stream is not None else sys.stdout
    isatty = getattr(stream, "isatty", None)
    if not (callable(isatty) and isatty()):
        return False
    # The classic Windows console prints the escapes as text; Windows
    # Terminal, which sets WT_SESSION, renders them.
    return os.name != "nt" or bool(os.environ.get("WT_SESSION"))


class Style:
    """Paints text when the terminal can show it, and leaves it alone otherwise."""

    def __init__(self, enabled: bool | None = None) -> None:
        self.enabled = _colour_wanted() if enabled is None else enabled

    def paint(self, text: str, *names: str) -> str:
        if not self.enabled or not text or not names:
            return text
        codes = ";".join(_ANSI[name] for name in names)
        return f"\033[{codes}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self.paint(text, "bold")

    def dim(self, text: str) -> str:
        return self.paint(text, "dim")

    def accent(self, text: str) -> str:
        return self.paint(text, "cyan")

    def good(self, text: str) -> str:
        return self.paint(text, "green")

    def warn(self, text: str) -> str:
        return self.paint(text, "yellow")

    def bad(self, text: str) -> str:
        return self.paint(text, "red", "bold")


# Box-drawing characters, named once. Not inside the f-strings below: a
# backslash in an f-string expression is a syntax error before Python 3.12.
_BAR_FULL = "█"
_BAR_EMPTY = "░"
_LIGHT = "─"
_HEAVY = "━"
_SIDE = "│"
_TOP_LEFT, _TOP_RIGHT = "╭", "╮"
_BOTTOM_LEFT, _BOTTOM_RIGHT = "╰", "╯"
_POINTER = "›"


def progress_bar(done: int, total: int, width: int = 24) -> str:
    """A bar of ``width`` cells, filled in proportion, and the percentage."""
    total = max(total, 1)
    done = min(max(done, 0), total)
    filled = round(width * done / total)
    percent = round(100 * done / total)
    return f"{_BAR_FULL * filled}{_BAR_EMPTY * (width - filled)} {percent:>3}%"


def banner(title: str, subtitle: str, style: Style, width: int = 0) -> list[str]:
    """A rounded frame around the wizard's name, for the top of the run."""
    inner = (width or frame_width()) - 2
    rows = [(title, style.bold)] + [(line, style.dim) for line in _wrap(subtitle, inner - 4)]
    lines = [style.accent(f"  {_TOP_LEFT}{_LIGHT * inner}{_TOP_RIGHT}")]
    for text, paint in rows:
        padding = " " * max(0, inner - 2 - len(text))
        lines.append(f"  {style.accent(_SIDE)}  {paint(text)}{padding}{style.accent(_SIDE)}")
    lines.append(style.accent(f"  {_BOTTOM_LEFT}{_LIGHT * inner}{_BOTTOM_RIGHT}"))
    return lines


def rule(title: str, style: Style, width: int = 0) -> str:
    """A heavy horizontal rule with a title set into it."""
    fill = _HEAVY * max(4, (width or frame_width()) - len(title) - 5)
    return f"  {style.accent(_HEAVY * 2)} {style.bold(title)} {style.accent(fill)}"


# --- motion, and the widgets that move -------------------------------------
# Borrowed in look, not in machinery, from ratatui's throbber, its LineGauge
# and its bordered Block. Ratatui redraws a whole screen every frame; this is
# a script that prints lines and must still be exactly the text it was when
# somebody pipes it into a file. So every effect here is decoration over
# output that is already complete without it, and every one of them is gated
# on the same `Style.enabled` that gates colour: no terminal, NO_COLOR,
# TERM=dumb or a test, and the static line is printed instead and not one
# escape is written.
#
# Nothing here sleeps for longer than a frame, so a wizard interrupted mid
# animation stops when it is asked to rather than after the effect finishes.
_THROBBER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_THROBBER_SECONDS = 0.08
_SETTLED, _FAILED = "✔", "✘"
_GAUGE_FULL, _GAUGE_EMPTY = "━", "╌"
# A sweep long enough to read as motion and short enough that nobody waits for
# it: a third of a second, whatever the terminal's width.
_SWEEP_WIDTH = 10
_SWEEP_FRAMES = 18
_SWEEP_SECONDS = 0.32
# Narrower than this and a card's labels are stubs; the plain list wins.
_CARD_LABEL_FLOOR = 18
_ANSI_ESCAPE = re.compile(r"\033\[[0-9;]*m")


def _visible(text: str) -> int:
    """How many columns a painted string takes, ignoring its escapes."""
    return len(_ANSI_ESCAPE.sub("", text))


def _emit(text: str, stream: Any = None) -> None:
    """Write a frame and flush it, with no newline of its own."""
    stream = stream if stream is not None else sys.stdout
    stream.write(text)
    stream.flush()


def line_gauge(done: int, total: int, width: int = 24) -> str:
    """Ratatui's LineGauge: one row of track, filled in proportion.

    The block bar `progress_bar` draws is two glyphs tall in effect - it
    carries its own weight down the page when every section prints one. This
    is the same number on a single hairline, for the counter that is redrawn
    in place rather than reprinted.
    """
    total = max(total, 1)
    done = min(max(done, 0), total)
    filled = round(width * done / total)
    percent = round(100 * done / total)
    return f"{_GAUGE_FULL * filled}{_GAUGE_EMPTY * (width - filled)} {percent:>3}%"


class Throbber:
    """A spinner for the one wait the wizard cannot make shorter.

    Ratatui's throbber-widgets-tui, with the ending it needs here: the frame
    is replaced by a tick or a cross rather than simply stopping, so the line
    that spun is the line that says how it went and the operator reads one
    result instead of a spinner that vanished.

    Prints nothing at all while it spins when the style is off; `finish` then
    writes the single plain line that run would have written before.
    """

    def __init__(
        self,
        label: str,
        style: Style,
        say: Callable[[str], None] | None = None,
        stream: Any = None,
        indent: int = 2,
    ) -> None:
        self.label = label
        self.style = style
        # Where the settled line goes when nothing is spinning. Frames are
        # written straight to the stream because they carry no newline and
        # overwrite each other; the one line that survives the wait belongs
        # on whatever the caller prints with.
        self.say = say
        self.stream = stream if stream is not None else sys.stdout
        self.indent = " " * indent
        self.frame = 0
        self.started = time.monotonic()
        self._drawn = 0

    def _clear(self) -> str:
        """Enough blanks to rub out the longest frame drawn so far."""
        return f"\r{' ' * self._drawn}\r" if self._drawn else "\r"

    def tick(self) -> None:
        """Advance one frame, over the top of the last one."""
        if not self.style.enabled:
            return
        glyph = _THROBBER_FRAMES[self.frame % len(_THROBBER_FRAMES)]
        self.frame += 1
        elapsed = f"{time.monotonic() - self.started:4.0f}s"
        line = f"{self.indent}{self.style.accent(glyph)} {self.label}{self.style.dim(elapsed)}"
        _emit(f"{self._clear()}{line}", self.stream)
        self._drawn = _visible(line)

    def finish(self, ok: bool, note: str = "") -> None:
        """Morph the spinner into its verdict and end the line."""
        mark = self.style.good(_SETTLED) if ok else self.style.warn(_FAILED)
        text = note or self.label.rstrip()
        line = f"{self.indent}{mark} {text}"
        if self.style.enabled:
            _emit(f"{self._clear()}{line}\n", self.stream)
        elif self.say is not None:
            self.say(line)
        else:
            _emit(f"{line}\n", self.stream)
        self._drawn = 0


def _sweep_run(text: str, bright: bool, style: Style) -> str:
    return style.paint(text, "cyan", "bold") if bright else style.paint(text, "cyan", "dim")


def _sweep_cells(text: str, offset: int, position: int, style: Style) -> str:
    """Paint one stretch of rule, brightening the window passing over it."""
    out: list[str] = []
    run: list[str] = []
    lit: bool | None = None
    for index, char in enumerate(text):
        bright = position <= offset + index < position + _SWEEP_WIDTH
        if lit is not None and bright is not lit:
            out.append(_sweep_run("".join(run), lit, style))
            run = []
        lit = bright
        run.append(char)
    if run and lit is not None:
        out.append(_sweep_run("".join(run), lit, style))
    return "".join(out)


def sweep_rule(title: str, style: Style, width: int = 0, stream: Any = None) -> None:
    """Draw `rule`, with one pass of light running along it first.

    A section heading that simply appears is one more line in a scroll; a
    heading that moves is where the eye lands, which is the whole job of a
    heading in a walk this long. It settles into exactly the rule that would
    have been printed anyway, so the effect costs the output nothing.
    """
    settled = rule(title, style, width)
    if not style.enabled:
        _emit(f"{settled}\n", stream)
        return
    lead = _HEAVY * 2
    fill = _HEAVY * max(4, (width or frame_width()) - len(title) - 5)
    cells = len(lead) + len(fill)
    span = cells + _SWEEP_WIDTH
    pause = _SWEEP_SECONDS / _SWEEP_FRAMES
    for frame in range(_SWEEP_FRAMES):
        position = round(-_SWEEP_WIDTH + span * frame / max(1, _SWEEP_FRAMES - 1))
        left = _sweep_cells(lead, 0, position, style)
        right = _sweep_cells(fill, len(lead), position, style)
        _emit(f"\r  {left} {style.bold(title)} {right}", stream)
        time.sleep(pause)
    _emit(f"\r{settled}\n", stream)


# --- what the wizard collects ----------------------------------------------
@dataclass
class Setup:
    """Every answer, with the default a public deployment would want.

    The defaults are the ones in ``docker-compose.yml``: a service open to
    anybody, refusing private targets, running no port scans and keeping no
    log of what was scanned. ``--preset private`` moves them to what an estate
    scanning its own instances needs instead.
    """

    # Where and how the images come from. The published image by default: the
    # wizard is one file meant to be downloaded onto a host with nothing but
    # Docker, and a build needs a checkout that such a host does not have.
    image_source: str = "dockerhub"
    image_ref: str = DOCKERHUB_IMAGE
    build_context: str = ".."
    project_name: str = "opencloud-scan"
    # Rootful or rootless. Empty until detected from the socket this user
    # talks to, which is the only reliable signal a standard-library script
    # has; a deployment built for one and run on the other gets containers
    # that cannot write to their own bind mounts.
    docker_mode: str = ""

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

    # Abuse protection: what it costs to use this service to find out what
    # answers where, rather than to check an OpenCloud instance.
    probe_limit: int = 5
    probe_window: int = 300
    probe_block: int = 3600
    probe_block_max: int = 86400
    probe_repeat_window: int = 86400
    probe_ipv4_prefix: int = 24
    client_ipv6_prefix: int = 64
    daily_scan_limit: int = 50
    dns_consistency_check: bool = True
    require_approval: bool = False
    approved_targets: str = ""
    approval_dns: bool = True

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

    # Whether the stack brings its own identity provider. Off until something
    # needs a sign-in: an interactive run turns it on the moment /admin or the
    # sign-in on /mcp is, because most deployments asking for either have no
    # provider of their own, and says so at the question that follows. The
    # flags do not - `--sign-in` alone still means "the provider I run". The
    # settings below are read only when it is on.
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
    # Who may create an account through the enrollment link, by username and
    # separated by semicolons. Everybody on the operator's guest list is on it
    # whether named here or not, because an operator without an account is a
    # guest list nobody can satisfy.
    authentik_accounts: str = ""
    # The bootstrap administrator's password, and the token the enrollment
    # link carries. Both generated, both in .env and nowhere else.
    authentik_bootstrap_password: str = ""
    authentik_enrollment_token: str = ""

    # Mail, which only Authentik sends: a password recovery, an invitation, an
    # expiring-password notice. The scan service itself sends none.
    smtp_host: str = ""
    smtp_port: int = 587
    # Whether the server wants an account at all. A relay on your own network
    # often authenticates by address instead, and offering the username and
    # password questions to a deployment that has neither is how half a
    # session ends up configured.
    smtp_auth: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"
    smtp_timeout: int = 10

    # The reverse proxy in front, and the configuration file written for it.
    # 'none' writes none - which is right when something else already
    # terminates TLS, and wrong in the quiet way if nothing does.
    reverse_proxy: str = "none"
    reverse_proxy_hostname: str = ""
    reverse_proxy_tls: bool = True
    reverse_proxy_certificate: str = ""
    reverse_proxy_private_key: str = ""
    reverse_proxy_acme_email: str = ""
    # The certificate for Authentik's own site, when the stack brings Authentik
    # and the proxy is one that is handed its certificates. Asked separately
    # because it is a different name: a certificate for scan.example.com is
    # refused by every browser that arrives at sso.example.com.
    reverse_proxy_authentik_certificate: str = ""
    reverse_proxy_authentik_private_key: str = ""

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
    audit_log_path: str = DEFAULT_AUDIT_LOG_PATH
    # Who rotates that file once it is on the host's filesystem: this service,
    # by size, or the logrotate the host already runs for every other log on
    # it. Only ever asked when the trail goes to a host directory - a named
    # volume lives somewhere under Docker's own root, which is not a path a
    # generated logrotate policy has any business naming.
    audit_rotation: str = "service"
    audit_retention_days: int = 30
    # The operator's area at /admin. Off unless asked for, and when it is on
    # it is authentik that guards it: this stack forwards a request through
    # the outpost, which signs the person in and adds the identity headers
    # the service then checks. The shared secret below is why those headers
    # are worth believing.
    admin_enabled: bool = False
    admin_users: str = ""
    admin_proxy_secret: str = ""

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
    redis_data_path: str = DEFAULT_REDIS_DATA_PATH


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

# The variable names the closing instructions print. Only names, never values,
# but they are plain constants rather than lookups in SECRET_VARIABLES below:
# code scanning takes anything read out of a mapping called that for the
# secret itself, and a false alarm on the output is one somebody eventually
# learns to dismiss - including the day it is real.
ENROLLMENT_LINK_VARIABLE = "AUTHENTIK_ENROLLMENT_TOKEN"
RECOVERY_ADMIN_VARIABLE = "AUTHENTIK_BOOTSTRAP_PASSWORD"
ADMIN_PROXY_VARIABLE = "COS_WEB_ADMIN_PROXY_SECRET"

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
    "admin_proxy_secret": ADMIN_PROXY_VARIABLE,
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
    "authentik_bootstrap_password": RECOVERY_ADMIN_VARIABLE,
    "authentik_enrollment_token": ENROLLMENT_LINK_VARIABLE,
    "smtp_password": "AUTHENTIK_EMAIL_PASSWORD",
}

# The ones that are credentials in the plain sense: shown by nobody, typed
# without an echo, and offered back on a re-run as a mask rather than as the
# value `.env` holds. The rest of the mapping lives in `.env` for another
# reason - an issuer URL or an audience both sides must agree on - and hiding
# those would only stop an operator checking them.
CREDENTIALS = frozenset(
    key
    for key in SECRET_VARIABLES
    if not key.startswith("mcp_auth_") and key != "authentik_client_id"
)

# What a prompt shows in brackets for a credential that is already set. It
# says nothing about the value - not its length, not its first characters -
# because a scrollback or a screen share is exactly where those end up.
MASKED = "set, hidden - Enter keeps it"


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
    conflicts: Callable[[Setup, Path], str | None] | None = None
    """Checked after an answer is taken, against the other answers: returns
    why it cannot stand, and the previous value is put back. For the
    checks a single value cannot fail on its own."""


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


def _usernames(value: str) -> str | None:
    for name in value.split(";"):
        if name.strip() and not re.fullmatch(r"[\w.@+-]+", name.strip()):
            return (
                f"'{name.strip()}' is not a username Authentik accepts. Letters, "
                "digits and . @ + - _ only; separate several with semicolons."
            )
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


def _between(minimum: int, maximum: int) -> Callable[[str], str | None]:
    def check(value: str) -> str | None:
        try:
            number = int(value)
        except ValueError:
            return f"Enter a whole number between {minimum} and {maximum}."
        if minimum <= number <= maximum:
            return None
        return f"Enter a whole number between {minimum} and {maximum}."

    return check


def _target_list(value: str) -> str | None:
    """Hostnames, .suffix domains, addresses and CIDR ranges, separated by ';'."""
    if not value.strip():
        return None
    for item in re.split(r"[;,]", value):
        entry = item.strip().lower().removeprefix("*")
        if not entry:
            continue
        if re.search(r"\s", entry):
            return "Separate several entries with ';', without spaces inside one."
        if not re.fullmatch(r"\.?[a-z0-9.:\[\]/-]+", entry):
            return (
                f"{item.strip()!r} is neither a hostname, a .suffix, an address "
                "nor a CIDR range."
            )
    return None


def _mail_address(value: str) -> str | None:
    if not value.strip():
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()):
        return "A From address looks like authentik@example.com."
    return None


def _host_directory(value: str) -> str | None:
    """A host directory to bind-mount into a container.

    Either absolute, or relative with a ``./`` in front of it. The leading dot
    is not decoration: Compose reads ``data:/data`` as a *named volume* called
    data and ``./data:/data`` as the directory beside the compose file, so a
    bare ``data`` would silently mount something else than the operator meant.
    An empty answer is refused outright, because the mount it produced -
    ``- :/data`` - is not a mount Compose can parse at all.
    """
    path = value.strip()
    if not path:
        return (
            "A directory is needed, or the generated mount reads ':/data' and "
            "Compose refuses the file. './data' keeps it beside the compose "
            "file; answer 'volume' at the question above to let Docker manage "
            "it instead."
        )
    if not path.startswith(("/", "./", "../")):
        return (
            "Give an absolute path, e.g. /srv/opencloud-scan/data, or a "
            f"relative one starting with './', e.g. {DEFAULT_REDIS_DATA_PATH}. "
            "Compose reads a source without a leading './' as the name of a "
            "named volume rather than as a directory."
        )
    if ":" in path:
        return "A ':' would be read as the start of the mount options."
    return None


def _single_hostname(value: str) -> str | None:
    """The one name the generated proxy answers to.

    A name rather than a URL: it is written into ``server_name``,
    ``ServerName`` and a Traefik ``Host()`` rule, none of which take a scheme.
    """
    name = value.strip()
    if not name:
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", name):
        return "A host name without the scheme, e.g. scan.example.com."
    if not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?", name):
        return "A host name looks like scan.example.com."
    return None


def _certificate_path(value: str) -> str | None:
    """Where the proxy reads a certificate or a key from, on the host."""
    path = value.strip()
    if not path:
        return None
    if not path.startswith("/"):
        return (
            "An absolute path, e.g. /etc/ssl/scan/fullchain.pem. A web server "
            "resolves a relative one against its own root rather than yours."
        )
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


# The steps column of the section card: a marker per section, so the whole
# walk and where the operator stands in it read at a glance.
_STEP_DONE, _STEP_SKIPPED, _STEP_PENDING = _SETTLED, "–", "·"
# Narrower than this and the left column cannot hold its gauge; the plain
# heading lines win.
_STEP_CARD_LEFT_FLOOR = 24


def step_card(
    section: Section,
    sections: Sequence[Section],
    number: int,
    skipped: Collection[int],
    style: Style,
    width: int = 0,
) -> list[str] | None:
    """A two-column card: this step on the left, every step on the right.

    The right column lists each section with a marker - done, skipped, the
    current one highlighted, or still ahead - so the operator sees the whole
    walk rather than a count. None when the terminal is too narrow for two
    columns, or when there is no step to place in the list, and the caller
    prints the plain heading lines instead.
    """
    if not sections or not 1 <= number <= len(sections):
        return None
    total = len(sections)
    right = max(len(item.title) for item in sections) + 2
    left = (width or frame_width()) - right - 7
    if left < _STEP_CARD_LEFT_FLOOR:
        return None
    gauge = line_gauge(number - 1, total, width=min(24, left - 5))
    left_rows = [style.accent(f"Step {number} of {total}"), style.dim(gauge), ""]
    left_rows += [style.dim(line) for line in _wrap(section.summary, left)]
    right_rows = []
    for position, item in enumerate(sections, start=1):
        if position == number:
            right_rows.append(style.paint(f"{_POINTER} {item.title}", "cyan", "bold"))
        elif position in skipped:
            right_rows.append(style.dim(f"{_STEP_SKIPPED} {item.title}"))
        elif position < number:
            right_rows.append(style.good(_STEP_DONE) + " " + style.dim(item.title))
        else:
            right_rows.append(style.dim(f"{_STEP_PENDING} {item.title}"))
    height = max(len(left_rows), len(right_rows))
    left_rows += [""] * (height - len(left_rows))
    right_rows += [""] * (height - len(right_rows))
    side = style.accent(_SIDE)
    lines = [style.accent(f"  {_TOP_LEFT}{_LIGHT * (left + 2)}┬{_LIGHT * (right + 2)}{_TOP_RIGHT}")]
    for text, step in zip(left_rows, right_rows, strict=True):
        pad_left = " " * max(0, left - _visible(text))
        pad_right = " " * max(0, right - _visible(step))
        lines.append(f"  {side} {text}{pad_left} {side} {step}{pad_right} {side}")
    lines.append(
        style.accent(f"  {_BOTTOM_LEFT}{_LIGHT * (left + 2)}┴{_LIGHT * (right + 2)}{_BOTTOM_RIGHT}")
    )
    return lines


class Wizard:
    """Asks the questions and remembers the answers."""

    def __init__(
        self,
        setup: Setup,
        *,
        interactive: bool = True,
        base_dir: Path | None = None,
        style: Style | None = None,
    ) -> None:
        self.setup = setup
        self.interactive = interactive
        # Where the compose file goes, which is what a relative host path in
        # an answer is relative to.
        self.base_dir = base_dir or Path(".")
        self.style = style or Style()

    def _conflict(self, question: Question, value: Any) -> str | None:
        """Take a value, unless it contradicts an answer already given."""
        previous = getattr(self.setup, question.key)
        setattr(self.setup, question.key, value)
        error = question.conflicts(self.setup, self.base_dir) if question.conflicts else None
        if error:
            setattr(self.setup, question.key, previous)
        return error

    # -- output ------------------------------------------------------------
    def say(self, text: str = "") -> None:
        if self.interactive:
            print(text)

    def rule(self, title: str) -> None:
        """A section rule, swept into place. Silent when nothing is being said."""
        if not self.interactive:
            return
        if self.style.enabled:
            sweep_rule(title, self.style)
        else:
            self.say(rule(title, self.style))

    def heading(
        self,
        section: Section,
        number: int = 0,
        total: int = 0,
        *,
        sections: Sequence[Section] = (),
        skipped: Collection[int] = (),
    ) -> None:
        """The section's title, and where it falls in the run.

        The position is worth the line it costs: this is a long walk, and a
        section heading that says nothing about how much is left is the reason
        somebody abandons one halfway through. The bar counts the sections
        already behind this one, so the first reads empty and the last does
        not yet read full - it fills when the summary arrives.
        """
        style = self.style
        self.say()
        self.rule(section.title)
        card = (
            step_card(section, sections, number, skipped, style)
            if style.enabled and sections and number
            else None
        )
        if card is not None:
            for line in card:
                self.say(line)
            return
        if total:
            step = style.accent(f"Step {number} of {total}")
            self.say(f"  {step}  {style.dim(line_gauge(number - 1, total))}")
        self.say(f"  {style.dim(section.summary)}")

    def skipped(self, sections: Sequence[Section], mode: str = "full") -> None:
        """Say which sections were passed over, so the step counter adds up.

        Without it the heading jumps from step 9 to step 11 and leaves the
        operator wondering what they missed.
        """
        if not sections:
            return
        reason = (
            "quick setup keeps their defaults"
            if mode != "full"
            else "nothing answered so far needs them"
        )
        names = ", ".join(section.title for section in sections)
        self.say()
        for line in _wrap(f"Skipped {names} - {reason}.", text_width(2)):
            self.say(f"  {self.style.dim(line)}")

    def choose_mode(self, *, editing: bool = False) -> str:
        """Ask how much of the walk to take, before the first question.

        A first run defaults to quick: five or six decisions and a summary is a
        deployment, and the summary still reaches every setting by name. An
        edit of an existing deployment defaults to full, because somebody
        re-running the wizard over one usually came to change something that
        is not among the essentials.
        """
        if not self.interactive:
            return "full"
        style = self.style
        default = "full" if editing else "quick"
        descriptions = {
            "quick": "only what a deployment cannot be right without - the address, "
            "the sign-in, the proxy - and defaults for the rest",
            "private": "the same few questions, starting from the answers an estate "
            "scanning its own network wants: private targets allowed, out of "
            "search engines, an audit trail kept",
            "full": "every question, section by section",
        }
        self.say()
        self.rule("How much to ask")
        for number, name in enumerate(MODES, start=1):
            marker = style.good("*") if name == default else " "
            lines = _wrap(descriptions[name], text_width(18))
            self.say(f"    {marker} {number}) {style.bold(f'{name:<8}')}  {lines[0]}")
            for line in lines[1:]:
                self.say(f"                   {line}")
        while True:
            answer = self._read(
                f"      {style.dim('[')}{style.accent(default)}{style.dim(']')} "
                f"{style.accent('>')} "
            ).strip().lower()
            if not answer:
                return default
            if answer in MODES:
                return answer
            if answer.isdigit() and 1 <= int(answer) <= len(MODES):
                return MODES[int(answer) - 1]
            self.notice(f"Answer with the number or the word: {', '.join(MODES)}")

    def notice(self, text: str, kind: str = "warn") -> None:
        """A line the operator has to act on: a refusal, or a correction."""
        marker = "!" if kind == "bad" else _POINTER
        paint = self.style.bad if kind == "bad" else self.style.warn
        self.say(f"      {paint(marker)} {paint(text) if kind == 'bad' else text}")

    # -- input -------------------------------------------------------------
    def _read(self, prompt: str) -> str:
        try:
            return input(prompt)
        except EOFError as error:  # piped input that ran out
            raise SetupAborted("No more input.") from error
        except KeyboardInterrupt as error:
            raise SetupAborted("Interrupted.") from error

    def _read_secret(self, prompt: str) -> str:
        """Read a credential without echoing it.

        Only at a terminal: ``getpass`` insists on one, and a credential piped
        in by an unattended run has no screen to be seen on anyway.
        """
        if not sys.stdin.isatty():
            return self._read(prompt)
        try:
            return getpass.getpass(prompt)
        except EOFError as error:
            raise SetupAborted("No more input.") from error
        except KeyboardInterrupt as error:
            raise SetupAborted("Interrupted.") from error

    def current(self, key: str) -> Any:
        return getattr(self.setup, key)

    def _chosen(self, question: Question, answer: str) -> str | None:
        """A choice, by its own name or by the number printed beside it.

        Typing `dockerhub` correctly is a small tax paid at every one of these
        questions, and a typo costs a whole re-read of the list.
        """
        if answer in question.choices:
            return answer
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(question.choices):
                return question.choices[index - 1]
        return None

    def ask(
        self,
        question: Question,
        *,
        can_go_back: bool = False,
        offer_rest: bool = True,
    ) -> str | None:
        """Ask one question and store the answer on the setup.

        Returns :data:`BACK` or :data:`REST` when the operator asked to move
        rather than to answer, and ``None`` when the question was settled -
        by an answer, or by an empty line accepting what is in brackets.
        """
        if not self.interactive:
            return None

        style = self.style
        current = self.current(question.key)
        secret = question.key in CREDENTIALS
        # A re-run reads `.env` back, so this is the real credential: never
        # printed, in the prompt or anywhere else.
        shown = MASKED if secret and current else _format_default(current)
        read = self._read_secret if secret else self._read
        self.say()
        self.say(f"  {style.accent(_POINTER)} {style.bold(question.prompt)}")
        brief, more = _first_sentence(question.explain)
        for line in _wrap(brief, text_width()):
            self.say(f"      {style.dim(line)}")
        if question.choices:
            for number, choice in enumerate(question.choices, start=1):
                if choice == current:
                    self.say(f"      {style.good('*')} {style.bold(f'{number}) {choice}')}")
                else:
                    self.say(f"        {number}) {choice}")
        else:
            self.say(f"      {style.dim('Example:')} {style.accent(question.example)}")
        if question.kind == "bool":
            self.say(style.dim("      Answer yes or no; true and false are accepted too."))
        if question.generate:
            self.say(
                style.dim("      Enter 'generate' and a strong random value is created for you.")
            )
        hints = self._hints(
            question, can_go_back=can_go_back, offer_rest=offer_rest, has_more=bool(more)
        )
        for line in _wrap(hints, text_width()) if hints else []:
            self.say(f"      {style.dim(line)}")

        while True:
            answer = read(
                f"      {style.dim('[')}{style.accent(shown)}{style.dim(']')} "
                f"{style.accent('>')} "
            ).strip()
            if not answer:
                return None
            lowered = answer.lower()
            if lowered == HELP_WORD:
                self.explain_in_full(question)
                continue
            if lowered in BACK_WORDS:
                if can_go_back:
                    return BACK
                self.notice("This is the first question - there is nothing behind it.")
                continue
            if lowered == REST_WORD:
                if offer_rest:
                    return REST
                self.notice("Every question has been asked; there is no rest.")
                continue
            if lowered == CLEAR_WORD:
                if question.kind != "str":
                    self.notice("Only a text setting can be emptied.")
                    continue
                # Validated like any other answer: some of these are refused
                # empty, and '-' must not be the way around that.
                error = question.validate("") or self._conflict(question, "")
                if error:
                    self.notice(error, "bad")
                    continue
                return None
            if question.generate and lowered == "generate":
                setattr(self.setup, question.key, secrets.token_hex(question.generate))
                self.say(
                    f"      {style.good('Generated')}, and written to .env rather than shown here."
                )
                return None
            if question.kind == "bool":
                if lowered in YES:
                    setattr(self.setup, question.key, True)
                    return None
                if lowered in NO:
                    setattr(self.setup, question.key, False)
                    return None
                self.notice("Answer yes or no - true and false work as well.")
                continue
            if question.kind == "int":
                error = question.validate(answer)
                if error:
                    self.notice(error, "bad")
                    continue
                setattr(self.setup, question.key, int(answer))
                return None
            if question.kind == "choice":
                choice = self._chosen(question, answer)
                if choice is None:
                    self.notice(
                        "Answer with the number or the word: "
                        f"{', '.join(question.choices)}"
                    )
                    continue
                setattr(self.setup, question.key, choice)
                return None
            error = question.validate(answer) or self._conflict(question, answer)
            if error:
                self.notice(error, "bad")
                continue
            return None

    def explain_in_full(self, question: Question) -> None:
        """The whole explanation, and where the setting is documented."""
        style = self.style
        self.say()
        for line in _wrap(question.explain, text_width()):
            self.say(f"      {line}")
        self.say(f"      {style.dim('Documented in')} {style.accent(docs_for(question.key))}")

    def _hints(
        self,
        question: Question,
        *,
        can_go_back: bool,
        offer_rest: bool,
        has_more: bool = False,
    ) -> str:
        """The one line that says what can be typed here besides an answer.

        On every question rather than once at the start, because the moment
        somebody wants to go back is the moment they are looking at a prompt,
        not at something they read four sections ago.
        """
        hints = []
        if has_more:
            hints.append("'?' explains more")
        if can_go_back:
            hints.append("'b' goes back")
        if question.kind == "str" and self.current(question.key):
            hints.append("'-' empties it")
        if offer_rest:
            hints.append("'rest' takes the remaining defaults")
        # No "Enter keeps ..." here: the prompt underneath already shows the
        # value in brackets, and repeating a long one wrapped this line onto
        # three.
        return " · ".join(hints)

    def confirm(self, prompt: str, *, default: bool = True) -> bool:
        if not self.interactive:
            return default
        shown = "Y/n" if default else "y/N"
        while True:
            answer = self._read(
                f"  {self.style.warn(_POINTER)} {prompt} {self.style.accent(f'[{shown}]')} "
            ).strip().lower()
            if not answer:
                return default
            if answer in YES:
                return True
            if answer in NO:
                return False
            # Saying so beats re-printing the same prompt at somebody who has
            # just typed something they thought was an answer.
            self.say("  Answer yes or no - true and false work as well.")


def _first_sentence(text: str) -> tuple[str, str]:
    """The opening sentence of an explanation, and whatever follows it.

    Shown on its own first, because a paragraph under every one of fifty
    questions is a wall people stop reading - and the one who wants the rest
    types '?'. A sentence ends at a full stop followed by a capital, so the
    'e.g.' and the quoted values inside one do not cut it short.
    """
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(text.split()), maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else ""


# Where each group of settings is written up in full. A prefix match, most
# specific first; everything else is in the web application's own reference.
_DOCUMENTATION = (
    (("authentik_", "smtp_", "mcp_auth_", "deploy_authentik", "admin_"), "docs/authentik.md"),
    (("reverse_proxy", "trust_forwarded_for"), "docs/reverse-proxy.md"),
    (("redis_",), "docs/redis.md"),
    (("image_", "build_context", "auto_updates", "watchtower_", "docker_mode"), "docker/README.md"),
)


def docs_for(key: str) -> str:
    """The page an operator reads for one setting, as a link that opens."""
    page = next(
        (page for prefixes, page in _DOCUMENTATION if key.startswith(prefixes)),
        "docs/webapp.md",
    )
    version = wizard_version()
    # The page as it was when this wizard was released: a setting described
    # on main may already have been renamed.
    ref = f"v{version}" if version else "main"
    return f"{PROJECT_URL}/blob/{ref}/{page}"


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
                    prompt="Pull the published image, or build it here?",
                    explain=(
                        "'dockerhub' - the default - pulls the published image and needs "
                        "no source at all, which is what a host that only has Docker "
                        "wants. 'build' builds both application services from a checkout "
                        "of this repository, which is what you want while changing the "
                        "code or when you would rather run something you compiled yourself."
                    ),
                    example="dockerhub",
                    kind="choice",
                    choices=("dockerhub", "build"),
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
                    key="docker_mode",
                    prompt="Does the Docker daemon run as root, or rootless?",
                    explain=(
                        "Detected from the socket this user talks to: a rootless "
                        "daemon serves one under /run/user/<uid>. It decides how a "
                        "host directory is handed to a container. On a rootless "
                        "daemon, uid 10001 inside a container is your subordinate "
                        "uid at that offset on the host, so the ownership commands "
                        "run through a container rather than as sudo, and a "
                        "logrotate policy names the mapped ids."
                    ),
                    example="rootless",
                    kind="choice",
                    choices=DOCKER_MODES,
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
            "Abuse protection",
            "What it costs to use this service to map other people's hosts.",
            [
                Question(
                    key="probe_limit",
                    prompt="Scans that find no OpenCloud before a network is blocked",
                    explain=(
                        "A scan whose host did not answer, answered with something else, "
                        "or a target the guard refused outright, counts as a strike - the "
                        "same host again counts again. This many strikes inside the window "
                        "below block the client's network. 0 turns the block off."
                    ),
                    example="5",
                    kind="int",
                    validate=_positive(0),
                ),
                Question(
                    key="probe_window",
                    prompt="Window those strikes are counted in, in seconds",
                    explain="Strikes further apart than this do not add up.",
                    example="300",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="probe_block",
                    prompt="How long the first block lasts, in seconds",
                    explain=(
                        "Answered with a friendly note and a pointer to running the "
                        "scanner locally, like every other limit."
                    ),
                    example="3600",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="probe_block_max",
                    prompt="Longest a repeated block may grow to, in seconds",
                    explain=(
                        "A network blocked again soon after its last block waits six "
                        "times longer each time - an hour, six hours, a day - up to this."
                    ),
                    example="86400",
                    kind="int",
                    validate=_positive(1),
                ),
                Question(
                    key="probe_repeat_window",
                    prompt="How long a block is remembered after it ends, in seconds",
                    explain=(
                        "A network that stays away this long starts again at the first "
                        "block's length. 0 never escalates."
                    ),
                    example="86400",
                    kind="int",
                    validate=_positive(0),
                ),
                Question(
                    key="probe_ipv4_prefix",
                    prompt="IPv4 network counted as one client by the block (prefix length)",
                    explain=(
                        "24 counts a /24 - usually one office or one hosting customer - so "
                        "the next address along does not step around a block. 32 counts "
                        "single addresses. The per-minute and daily limits always count "
                        "single IPv4 addresses."
                    ),
                    example="24",
                    kind="int",
                    validate=_between(8, 32),
                ),
                Question(
                    key="client_ipv6_prefix",
                    prompt="IPv6 network counted as one client by every limit (prefix length)",
                    explain=(
                        "One subscriber is handed a whole /64 and can rotate through it for "
                        "free, so counting single IPv6 addresses is no limit at all."
                    ),
                    example="64",
                    kind="int",
                    validate=_between(32, 128),
                ),
                Question(
                    key="daily_scan_limit",
                    prompt="Scans one client may submit per day",
                    explain=(
                        "On top of the per-minute limit, for the patient version of a "
                        "burst that stays just under it all night. 0 turns it off."
                    ),
                    example="50",
                    kind="int",
                    validate=_positive(0),
                ),
                Question(
                    key="dns_consistency_check",
                    prompt="Refuse hostnames that answer differently on every lookup?",
                    explain=(
                        "A submitted name is looked up twice; two answers that share no "
                        "address are the mark of a name built to rebind. Turn off only for "
                        "targets behind DNS pools that rotate whole address sets."
                    ),
                    example="yes",
                    kind="bool",
                ),
                Question(
                    key="require_approval",
                    prompt="Scan approved instances only?",
                    explain=(
                        "For a deployment that should not be a public scanner at all. An "
                        "instance is approved when it is listed below, or - if allowed - "
                        "when its own DNS publishes a TXT record approving this service."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="approved_targets",
                    prompt="Approved instances",
                    explain=(
                        "Hostnames, .suffix domains, addresses and CIDR ranges, separated "
                        "by ';'. A .suffix covers the domain and every name under it."
                    ),
                    example="opencloud.example.com;.example.org",
                    validate=_target_list,
                ),
                Question(
                    key="approval_dns",
                    prompt="Accept a DNS TXT record as approval?",
                    explain=(
                        "The owner of a name approves this service by publishing "
                        "_check-opencloud-security.<host> TXT "
                        "\"check-opencloud-security=<this service's hostname>\". Needs the "
                        "public base URL."
                    ),
                    example="yes",
                    kind="bool",
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
            ],
        ),
        Section(
            "The operator's area",
            "An optional console at /admin, behind the authentik sign-in.",
            [
                Question(
                    key="admin_enabled",
                    prompt="Serve the operator's area at /admin?",
                    explain=(
                        "A page showing this deployment's load, its limits and when "
                        "the release schedule and advisory database were last read, "
                        "with a button for each of those two refreshes and a live view "
                        "of the audit trail. Off by default, and off means the path "
                        "does not exist rather than asking for a password: a stranger "
                        "cannot tell whether this deployment has one. It is never "
                        "public - authentik signs the operator in before the request "
                        "reaches the service, and the service refuses to start if it "
                        "cannot check that."
                    ),
                    example="no",
                    kind="bool",
                ),
                Question(
                    key="admin_users",
                    prompt="Who may use it, by authentik username",
                    explain=(
                        "Separated by semicolons. This is the whole guest list: an "
                        "empty one is refused at startup rather than read as "
                        "'anybody the provider authenticated', which would hand the "
                        "console to every account in the directory. Signing in is "
                        "not the same as being an operator here."
                    ),
                    example="admin",
                ),
                Question(
                    key="admin_proxy_secret",
                    prompt="Shared secret between the outpost and the service",
                    explain=(
                        "The outpost adds this to every request it forwards, and it "
                        "is the only reason the identity headers are worth believing "
                        "- without it, anybody who can reach the container could send "
                        "the same headers and be whoever they liked. Generated, "
                        "kept in .env, and never written into the compose file."
                    ),
                    example="generate",
                    generate=32,
                ),
            ],
        ),
        Section(
            "The identity provider",
            "Who signs people in - for /mcp, for /admin, or for both.",
            [
                Question(
                    key="deploy_authentik",
                    prompt="Add Authentik to this stack as the provider?",
                    explain=(
                        "Two things above can want one: a sign-in on /mcp, and the "
                        "operator's area at /admin, which has no other way in. Say "
                        "yes and Authentik and its PostgreSQL join this compose "
                        "file and provision themselves, so those values are already "
                        "right and there is nothing to click - which is why yes is "
                        "the default once either of them is switched on. Say no and "
                        "each is checked against a provider you already run: you are "
                        "asked for the issuer, the audience and the keys, and you put "
                        "your own proxy in front of /admin. Yes costs two more "
                        "containers and a database to back up. This does not close /mcp on its own - the "
                        "sign-in question does that, and bringing the provider up "
                        "first is a good way to try a token before anybody is turned "
                        "away."
                    ),
                    example="yes",
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
                    key="authentik_accounts",
                    prompt="Who signs in, by username",
                    explain=(
                        "Separated by semicolons. Nobody has to create these in "
                        "Authentik: each person opens the enrollment link the wizard "
                        "prints at the end, types their username, chooses a password "
                        "and enrols an authenticator app or security key - a second "
                        "factor is required for every account. Only the names listed "
                        "here can be claimed, each exactly once. Everybody on the "
                        "operator's guest list is added whether or not you repeat "
                        "them, and joins the operator group on the way."
                    ),
                    example="alice;bob",
                    validate=_usernames,
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
                        "Where the sign-in and the enrollment link are reached, on "
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
                    key="smtp_auth",
                    prompt="Does the server require a username and password?",
                    explain=(
                        "Almost every hosted provider does. Say no for a relay on "
                        "your own network that authenticates by address instead - "
                        "an empty username is how Authentik is told to submit "
                        "without authenticating, and half a credential is refused "
                        "at the first message rather than at the first mistake."
                    ),
                    example="yes",
                    kind="bool",
                ),
                Question(
                    key="smtp_username",
                    prompt="Username",
                    explain=(
                        "The account Authentik authenticates as. Often the whole "
                        "mail address rather than the part before the @, and often "
                        "not the same as the From address below."
                    ),
                    example="authentik@example.com",
                ),
                Question(
                    key="smtp_password",
                    prompt="Password",
                    explain=(
                        "Written to .env, never into the compose file. It can also be "
                        "supplied without typing it here, by putting "
                        "AUTHENTIK_EMAIL_PASSWORD in the environment the wizard runs in. "
                        "An app password rather than the account's own is worth the "
                        "detour: this one sits on a disk on a host that sends mail."
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
                        "trail it cannot write. The default is "
                        f"{DEFAULT_AUDIT_LOG_PATH}, beside the generated compose "
                        "file, which is what Compose resolves a relative source "
                        "against; an absolute path works too, and a name with no "
                        "'./' in front of it would be read as a named volume "
                        "rather than a directory. A named volume needs none of "
                        "this, which is why it is the other answer. It cannot be "
                        "the Redis directory, or inside it, or around it: the two "
                        "containers run as different users, and one directory can "
                        "only be owned by one of them."
                    ),
                    example=DEFAULT_AUDIT_LOG_PATH,
                    validate=_host_directory,
                    conflicts=_storage_conflict,
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
                        "is the user the Redis image runs as. The default is "
                        f"{DEFAULT_REDIS_DATA_PATH}, the directory beside the "
                        "generated compose file - Compose resolves a relative "
                        "source against that file rather than against wherever "
                        "you ran it from. An absolute path works too; a name "
                        "with no './' in front of it does not, because Compose "
                        "would read it as a named volume. A named volume needs "
                        "none of this, which is the other answer above. It has "
                        "to be a different directory from the audit trail's, "
                        "and not one inside the other, because the two "
                        "containers write as different users."
                    ),
                    example=DEFAULT_REDIS_DATA_PATH,
                    validate=_host_directory,
                    conflicts=_storage_conflict,
                ),
            ],
        ),
        Section(
            "The reverse proxy",
            "What terminates TLS in front, and the configuration file for it.",
            [
                Question(
                    key="reverse_proxy",
                    prompt="Write a reverse proxy configuration as well?",
                    explain=(
                        "The stack publishes a plain HTTP port on the loopback "
                        "address and nothing else: something in front has to "
                        "terminate TLS, overwrite X-Forwarded-For so the rate limit "
                        "counts clients rather than the proxy, and leave the /mcp "
                        "event stream unbuffered. Name what you run and the file is "
                        "written beside the compose file, ready to install - "
                        "including the forward auth in front of /admin when this "
                        "deployment has one, and a site of its own for Authentik "
                        "when the stack brings it. 'none' writes nothing, which is right "
                        "when the proxy is already configured or lives on another "
                        "host."
                    ),
                    example="nginx",
                    kind="choice",
                    choices=PROXY_CHOICES,
                ),
                Question(
                    key="reverse_proxy_hostname",
                    prompt="Host name the proxy answers to",
                    explain=(
                        "The name in the certificate and in the address visitors "
                        "type, without a scheme. Taken from the public address of "
                        "this service when you leave it empty, because the two "
                        "disagreeing is how a canonical link points somewhere "
                        "nobody can reach."
                    ),
                    example="scan.example.com",
                    validate=_single_hostname,
                ),
                Question(
                    key="reverse_proxy_tls",
                    prompt="Should this configuration terminate TLS?",
                    explain=(
                        "Yes writes the HTTPS server and a redirect from port 80, "
                        "and asks for the certificate below. No writes a plain HTTP "
                        "server, which is only honest when something else in front "
                        "- a load balancer, a tunnel, a CDN - is already doing it. "
                        "Caddy and Traefik obtain their own certificates and are "
                        "never asked this."
                    ),
                    example="yes",
                    kind="bool",
                ),
                Question(
                    key="reverse_proxy_certificate",
                    prompt="Certificate chain file",
                    explain=(
                        "The full chain, as the proxy reads it from this host. A "
                        "certbot deployment names the file under "
                        "/etc/letsencrypt/live/<name>/fullchain.pem."
                    ),
                    example="/etc/ssl/scan/fullchain.pem",
                    validate=_certificate_path,
                ),
                Question(
                    key="reverse_proxy_private_key",
                    prompt="Private key file",
                    explain=(
                        "The key belonging to that certificate, readable by the "
                        "proxy and by nobody else."
                    ),
                    example="/etc/ssl/scan/privkey.pem",
                    validate=_certificate_path,
                ),
                Question(
                    key="reverse_proxy_authentik_certificate",
                    prompt="Certificate chain file for Authentik's site",
                    explain=(
                        "The generated configuration serves Authentik too, at the "
                        "host name of its public address, because that is where "
                        "every sign-in is sent and a provider nobody's browser can "
                        "reach signs nobody in. It is a second name, so it needs a "
                        "certificate that covers it - the same file as above works "
                        "if that one carries both names or a wildcard."
                    ),
                    example="/etc/ssl/sso/fullchain.pem",
                    validate=_certificate_path,
                ),
                Question(
                    key="reverse_proxy_authentik_private_key",
                    prompt="Private key file for Authentik's site",
                    explain="The key belonging to that certificate.",
                    example="/etc/ssl/sso/privkey.pem",
                    validate=_certificate_path,
                ),
                Question(
                    key="reverse_proxy_acme_email",
                    prompt="Address for the certificate authority",
                    explain=(
                        "Caddy and Traefik obtain and renew a certificate "
                        "themselves and register this address with the authority, "
                        "which is where a warning goes when a renewal has been "
                        "failing. Leave it empty and the certificate is still "
                        "issued - nobody is told when it stops being."
                    ),
                    example="ops@example.com",
                    validate=_mail_address,
                ),
            ],
        ),
    ]


def run_questions(wizard: Wizard, mode: str = "full") -> None:
    """Ask everything, skipping the questions the previous answers settled.

    Relevance is decided one question at a time, as the answers arrive, and
    never for the section as a whole. An answer routinely brings the next
    question into play - naming an SMTP server is what makes the port, the
    transport security and the credentials worth asking for, and asking for
    Authentik is what makes its address and its ports worth asking for. A list
    filtered once before the section starts can only ever *lose* questions,
    which is how a mail server used to be configured with nothing but a host
    name.

    In a quick setup only the questions in :data:`QUICK_QUESTIONS` are asked,
    under the same relevance rules; every other answer keeps its default, and
    the summary is still where any of them can be changed.
    """
    setup = wizard.setup
    sections = build_sections(setup)
    plan = [
        (number, section, question)
        for number, section in enumerate(sections, start=1)
        for question in section.questions
        if mode == "full" or _is_quick(question.key)
    ]
    # Where each answered question sat, so that 'b' can go back to the last
    # one actually asked rather than to the last one defined - the questions
    # in between were skipped for a reason that still holds.
    answered: list[int] = []
    heading_shown: Section | None = None
    # The section numbers passed over, for the steps column of the heading.
    passed_over: set[int] = set()
    last_number = 0
    position = 0
    while position < len(plan):
        number, section, question = plan[position]
        if not _relevant(question.key, setup):
            position += 1
            continue
        if section is not heading_shown:
            if number > last_number + 1:
                wizard.skipped(sections[last_number:number - 1], mode)
                passed_over.update(range(last_number + 1, number))
            wizard.heading(
                section, number, len(sections), sections=sections, skipped=passed_over
            )
            heading_shown = section
            # Lower again after a 'b' into an earlier section, so walking
            # forward from there reports the same skips it reported before.
            last_number = number
        before = _sign_in_wanted(setup)
        movement = wizard.ask(question, can_go_back=bool(answered))
        _offer_authentik(setup, before)
        if movement == REST:
            return
        if movement == BACK:
            # The heading reprints itself when this lands in an earlier
            # section, because the check above compares what was last shown.
            position = answered.pop()
            continue
        answered.append(position)
        position += 1
    if last_number < len(sections):
        wizard.skipped(sections[last_number:], mode)


# What a quick setup asks: the decisions a deployment cannot be right without,
# and whatever those answers bring into play. Where the service is reached,
# what signs people in, and what stands in front of it. Everything else - the
# limits, the load, the audit trail - has a default that suits a first run.
QUICK_QUESTIONS = (
    "image_source",
    "image_ref",
    "build_context",
    "host_port",
    "public_base_url",
    "enable_mcp",
    "mcp_auth_",
    "admin_enabled",
    "admin_users",
    "deploy_authentik",
    "authentik_url",
    "authentik_accounts",
    "smtp_",
    "reverse_proxy",
)

# How much the run asks, chosen before the first question.
MODES = ("quick", "private", "full")


def _is_quick(key: str) -> bool:
    return key.startswith(QUICK_QUESTIONS)


def _signs_in(setup: Setup) -> bool:
    """Whether this deployment asked for a sign-in on ``/mcp`` at all."""
    return setup.enable_mcp and setup.mcp_auth_enabled


def _sign_in_wanted(setup: Setup) -> bool:
    """Whether anything asked for so far needs somebody to sign in."""
    return _signs_in(setup) or setup.admin_enabled


def _offer_authentik(setup: Setup, before: bool) -> bool:
    """Make the bundled Authentik the default the moment a sign-in is wanted.

    Switching on ``/admin`` or the sign-in on ``/mcp`` is, for nearly every
    deployment that runs this wizard, also the moment it needs a provider -
    and one that already runs its own can say no at the very next question.
    The reverse is a default that sends the operator on to issuer, audience
    and key questions they have no answers for.

    Only on the change from nothing-to-sign-in-to to something, so that an
    earlier *no* - in this run, or remembered from the last one - is not
    overturned by walking past an answer that did not change.
    """
    if before or not _sign_in_wanted(setup) or setup.deploy_authentik:
        return False
    setup.deploy_authentik = True
    return True


def _wants_a_provider(setup: Setup) -> bool:
    """Whether anything in this deployment has a sign-in to offer.

    Two things can: the MCP endpoint, which may require a token, and the
    operator's area, which has no other way in at all. Either is reason enough
    to be asked about a provider; neither being present means the question has
    no answer worth giving.
    """
    return setup.enable_mcp or setup.admin_enabled


def _uses_authentik(setup: Setup) -> bool:
    """Whether the generated stack brings its own identity provider.

    Independent of whether ``/mcp`` requires a token. Deploying a provider is
    a decision about what runs; requiring a sign-in is a decision about who
    may ask, and neither one implies the other. A stack can be provisioned
    with the guard still off, which is how an operator tries the sign-in out
    before switching it on for everybody.

    It is not independent of there being something to guard, though: three
    containers and a database that nothing in front of them consults are three
    containers to patch for nothing.
    """
    return setup.deploy_authentik and _wants_a_provider(setup)


def _guards_the_admin_area(setup: Setup) -> bool:
    """Whether the bundled provider is what stands in front of ``/admin``."""
    return setup.admin_enabled and _uses_authentik(setup)


def _writes_proxy(setup: Setup) -> bool:
    """Whether a reverse proxy configuration is written beside the stack."""
    return setup.reverse_proxy in PROXY_CHOICES and setup.reverse_proxy != "none"


def _proxy_forwards_auth(setup: Setup) -> bool:
    """Whether the generated proxy asks the outpost before serving ``/admin``.

    Three conditions, and every one of them is load-bearing. There has to be
    an area to guard, a provider to ask, and a proxy that can ask - Apache
    has no forward-auth of its own, and a generated ``/admin`` block that
    quietly did not authenticate anybody is the single worst file this script
    could write.
    """
    return (
        _guards_the_admin_area(setup)
        and setup.reverse_proxy in FORWARD_AUTH_PROXIES
    )


def _authentik_proxy_hostname(setup: Setup) -> str:
    """The name Authentik's own site answers to, or ``""`` when there is none.

    Taken from the public address of Authentik, because that is the address
    every token names as its issuer and every sign-in redirects a browser to -
    a site answering to anything else is one the redirect never arrives at.
    Nothing is returned for an address that is no public name at all: the
    ``localhost`` the stack falls back to, a bare IP address, or the very name
    this service answers to, which Authentik cannot share without being moved
    to a path of its own.
    """
    host = _url_hostname(setup.authentik_url)
    if not host or host == "localhost" or re.fullmatch(r"[0-9.]+|\[.*", host):
        return ""
    if host == _proxy_hostname(setup).lower():
        return ""
    return host


def _url_hostname(url: str) -> str:
    """The host part of a URL, lower-cased and without a port."""
    host = url.strip().split("://", 1)[-1].split("/", 1)[0].rsplit("@", 1)[-1]
    if host.startswith("["):  # an IPv6 literal keeps its brackets
        return host.split("]", 1)[0].lower() + "]"
    return host.split(":", 1)[0].lower()


def _proxy_serves_authentik(setup: Setup) -> bool:
    """Whether the generated proxy carries a site for Authentik's interface."""
    return (
        _writes_proxy(setup)
        and _uses_authentik(setup)
        and bool(_authentik_proxy_hostname(setup))
    )


def _relevant(key: str, setup: Setup) -> bool:
    """Whether a question still has a point, given the answers so far."""
    if key == "image_ref":
        return setup.image_source == "dockerhub"
    if key == "build_context":
        return setup.image_source == "build"
    if key == "watchtower_socket":
        return setup.auto_updates
    if key in {"probe_window", "probe_block", "probe_block_max", "probe_repeat_window",
               "probe_ipv4_prefix"}:
        return setup.probe_limit > 0
    if key in {"approved_targets", "approval_dns"}:
        return setup.require_approval
    if key == "releases_token":
        return setup.releases_mode != "off"
    if key in {"mcp_allowed_hosts", "mcp_max_concurrent_waits", "mcp_auth_enabled"}:
        return setup.enable_mcp
    if key in {"admin_users", "admin_proxy_secret"}:
        # A guest list and a shared secret for an area that does not exist are
        # an unused credential in .env and a question with no consequence.
        return setup.admin_enabled
    if key == "deploy_authentik":
        return _wants_a_provider(setup)
    if key.startswith("authentik_"):
        # Authentik answers the issuer, the audience and the keys itself, so
        # its own questions replace them rather than adding to them.
        return _uses_authentik(setup)
    if key.startswith("smtp_"):
        if not _uses_authentik(setup):
            return False
        if key == "smtp_host":
            return True
        if not setup.smtp_host:
            return False
        # An account is only worth asking about where the server wants one.
        return setup.smtp_auth or key not in {"smtp_username", "smtp_password"}
    if key.startswith("mcp_auth_"):
        if not _signs_in(setup):
            return False
        return key == "mcp_auth_scopes" or not _uses_authentik(setup)
    if key.startswith("reverse_proxy"):
        if key == "reverse_proxy":
            return True
        if setup.reverse_proxy == "none":
            return False
        if key == "reverse_proxy_acme_email":
            # Only the two that go and fetch a certificate themselves.
            return setup.reverse_proxy in {"caddy", "traefik"}
        if key in {
            "reverse_proxy_authentik_certificate",
            "reverse_proxy_authentik_private_key",
        }:
            return (
                setup.reverse_proxy in {"nginx", "apache"}
                and setup.reverse_proxy_tls
                and _proxy_serves_authentik(setup)
            )
        if key in {
            "reverse_proxy_tls",
            "reverse_proxy_certificate",
            "reverse_proxy_private_key",
        }:
            if setup.reverse_proxy not in {"nginx", "apache"}:
                return False
            return key == "reverse_proxy_tls" or setup.reverse_proxy_tls
        return True

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
        and _binds_a_directory(setup.audit_storage, setup.audit_log_path)
        and setup.audit_rotation == "logrotate"
    )


def _persists_redis(setup: Setup) -> bool:
    """Whether Redis writes its keyspace to disk."""
    return setup.redis_persistence != "none"


def _binds_a_directory(storage: str, host_path: str) -> bool:
    """Whether this storage answer names a directory on the host.

    An empty path with ``filesystem`` chosen is the one combination that can
    produce nothing to mount. It used to produce ``- :/data``, which Compose
    refuses to parse, taking the whole stack down over a question that was
    never asked - so it falls back to the named volume, which needs no answer
    from anybody and keeps the data.
    """
    return storage == "filesystem" and bool(host_path.strip())


def _mount_source(storage: str, host_path: str, volume: str) -> str:
    """The left-hand side of a bind or named-volume mount."""
    if _binds_a_directory(storage, host_path):
        return host_path.strip()
    return volume


def _host_path(path: str, base_dir: Path) -> Path:
    """A host directory as Compose will resolve it: relative to the compose file."""
    candidate = Path(path.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return Path(os.path.realpath(candidate))


def _storage_conflict(setup: Setup, base_dir: Path) -> str | None:
    """Why the audit trail and Redis cannot share the directories they were given.

    They write as different users - the web image as uid 10001, Redis as uid
    999 - and a directory has one owner. Whichever ``chown`` ran last would
    decide which of the two containers can write, and the other one would
    refuse to start or, worse for Redis, start and lose its append-only file.
    One directory inside the other fails the same way one level down, and
    hands the container that mounts the outer one the other's data as well.
    """
    if not (
        _keeps_audit_file(setup)
        and _binds_a_directory(setup.audit_storage, setup.audit_log_path)
        and _binds_a_directory(setup.redis_persistence, setup.redis_data_path)
    ):
        return None
    audit = _host_path(setup.audit_log_path, base_dir)
    redis = _host_path(setup.redis_data_path, base_dir)
    if audit == redis:
        return (
            f"The audit trail and Redis would both be kept in {audit}. They "
            f"write as different users - uid {WEB_IMAGE_UID} and uid "
            f"{REDIS_IMAGE_UID} - and one directory can only belong to one of "
            f"them. Give each its own, e.g. {DEFAULT_AUDIT_LOG_PATH} and "
            f"{DEFAULT_REDIS_DATA_PATH}."
        )
    if audit in redis.parents or redis in audit.parents:
        outer, inner = (audit, redis) if audit in redis.parents else (redis, audit)
        return (
            f"{inner} is inside {outer}. The audit trail and Redis write as "
            f"different users - uid {WEB_IMAGE_UID} and uid {REDIS_IMAGE_UID} - "
            "and the container mounting the outer directory would see the "
            "other one's data. Use two directories side by side, e.g. "
            f"{DEFAULT_AUDIT_LOG_PATH} and {DEFAULT_REDIS_DATA_PATH}."
        )
    return None


def check_errors(setup: Setup, base_dir: Path | None = None) -> list[str]:
    """What has to change before anything is written.

    Unlike :func:`check_consistency`, none of these is a matter of opinion:
    each one is a stack that cannot work as generated.
    """
    conflict = _storage_conflict(setup, base_dir or Path("."))
    return [conflict] if conflict else []


def _authentik_release(tag: str) -> tuple[int, int, int] | None:
    """``2026.8.4`` as a comparable tuple, or ``None`` for anything else."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", tag.strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def follow_authentik_patch(setup: Setup) -> str | None:
    """Move a remembered Authentik pin up to this wizard's patch release.

    The pin is remembered with every other answer, which is right for a
    decision and wrong for a patch: re-running a newer wizard against an
    existing deployment used to keep writing the release it was first set up
    with, security fixes and all. Within one ``YYYY.M`` series a newer patch
    is only fixes, so it is taken. A different series is not - Authentik
    upgrades across releases can carry migrations and breaking changes worth
    reading first - and :func:`check_consistency` says so instead.
    """
    remembered = _authentik_release(setup.authentik_tag)
    shipped = _authentik_release(AUTHENTIK_TAG)
    if not remembered or not shipped:
        return None
    if remembered[:2] == shipped[:2] and remembered < shipped:
        previous = setup.authentik_tag
        setup.authentik_tag = AUTHENTIK_TAG
        return (
            f"Authentik {previous} is moved to {AUTHENTIK_TAG}, the patch "
            "release this wizard ships."
        )
    return None


def _rootless(setup: Setup) -> bool:
    """Whether the stack is generated for a rootless Docker daemon."""
    return setup.docker_mode == "rootless"


def _ownership_command(setup: Setup, path: str, uid: int) -> str:
    """How to create a host directory and give it to a container's user.

    On a rootful daemon a container uid is the host uid, and ``sudo chown``
    is the whole job. On a rootless one it is not: uid 10001 in a container
    is the invoking user's subordinate uid at that offset, which only the
    user namespace the daemon runs in can name without arithmetic. So the
    chown runs *in* a container, as that namespace's root - which is the
    invoking user, owns the fresh directory, and needs no sudo at all.
    """
    path = path.strip()
    if not _rootless(setup):
        return f"mkdir -p {path} && sudo chown {uid} {path}"
    return (
        f"mkdir -p {path} && docker run --rm --user 0 --entrypoint chown "
        f'-v "$(realpath {path})":/target {REDIS_IMAGE} {uid} /target'
    )


def _as_the_container_sees_it(setup: Setup) -> str:
    """The qualifier a rootless uid needs, with its trailing space, or nothing."""
    return "as the container sees it " if _rootless(setup) else ""


def detect_docker_mode(socket: str | None = None) -> str:
    """``rootless`` when the socket this user talks to is a rootless daemon's.

    A rootless daemon serves its socket from the user's runtime directory,
    ``/run/user/<uid>`` on every distribution that has systemd, and a rootful
    one from ``/var/run``. That is a heuristic, which is why it only decides
    the default of a question rather than the answer.
    """
    socket = detect_docker_socket() if socket is None else socket
    runtime = os.environ.get("XDG_RUNTIME_DIR", "").rstrip("/")
    if socket.startswith("/run/user/") or (runtime and socket.startswith(runtime + "/")):
        return "rootless"
    return "rootful"


def _mapped_id(table: Path, container_id: int) -> int | None:
    """The host id a rootless daemon maps ``container_id`` to, if it can be read.

    Container id 0 is the user themself; ids from 1 onwards are taken from the
    first subordinate range ``/etc/subuid`` (or ``subgid``) grants them, so id
    *n* is ``start + n - 1`` - provided the range is long enough to hold it,
    which the default 65536 is.
    """
    names = set()
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        names.add(str(getuid()))
    names.update(filter(None, (os.environ.get("USER"), os.environ.get("LOGNAME"))))
    try:
        lines = table.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.strip().split(":")
        if len(parts) != 3 or parts[0] not in names:
            continue
        try:
            start, count = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if 1 <= container_id <= count:
            return start + container_id - 1
    return None


def check_consistency(setup: Setup) -> list[str]:
    """Warnings worth showing before anything is written.

    None of these is fatal here - the service itself refuses to start on the
    ones that matter - but saying so now is cheaper than a container that
    exits three seconds after ``up``.
    """
    warnings: list[str] = []
    if setup.require_approval and not setup.approved_targets.strip() and not setup.approval_dns:
        warnings.append(
            "Approval mode with no approved instances and the DNS proof off is "
            "refused at startup: nothing could ever be scanned. List an instance "
            "or accept the TXT record."
        )
    if setup.require_approval and setup.approval_dns and not setup.public_base_url:
        warnings.append(
            "Approval by DNS needs a public base URL: the TXT record approves "
            "this service by its hostname."
        )
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
    if setup.admin_enabled and not setup.admin_users.strip():
        warnings.append(
            "The operator's area is on but names nobody in COS_WEB_ADMIN_USERS. "
            "The service refuses to start rather than treat an empty list as "
            "everybody: add the authentik username that should reach /admin."
        )
    if setup.admin_enabled and not _uses_authentik(setup):
        warnings.append(
            "The operator's area is on without the bundled Authentik. Put a "
            "proxy provider in front of /admin yourself and have it send "
            "COS_WEB_ADMIN_PROXY_SECRET as X-COS-Admin-Proxy, or the area is "
            "unreachable - the service refuses a request that did not come "
            "through an outpost."
        )
    if _writes_proxy(setup) and not setup.trust_forwarded_for:
        warnings.append(
            "A reverse proxy configuration is being written, and the service "
            "is not reading the client address from it. Every request will "
            "look like it came from the proxy, so the per-client rate limit "
            "becomes one shared bucket for the whole internet. The generated "
            "config overwrites X-Forwarded-For rather than appending to it, "
            "which is what makes COS_WEB_TRUST_FORWARDED_FOR safe to turn on "
            "here."
        )
    if setup.admin_enabled and _writes_proxy(setup) and not _proxy_forwards_auth(setup):
        reason = (
            f"{setup.reverse_proxy} has no forward-auth of its own"
            if setup.reverse_proxy not in FORWARD_AUTH_PROXIES
            else "there is no bundled provider for it to ask"
        )
        warnings.append(
            f"The generated {setup.reverse_proxy} configuration routes "
            f"everything except {ADMIN_PATH}, because {reason}. The area is "
            "reachable only through something that signs the operator in and "
            f"adds {ADMIN_PROXY_HEADER}; until you write that yourself, "
            f"{ADMIN_PATH} answers 404 - which is the failure you want, and "
            "it will look like a bug."
        )
    if (
        _writes_proxy(setup)
        and _uses_authentik(setup)
        and not _authentik_proxy_hostname(setup)
    ):
        address = setup.authentik_url or "unset"
        host = _url_hostname(setup.authentik_url)
        reason = (
            "names the same host as this service, and Authentik wants a host "
            "name of its own"
            if host not in {"", "localhost"} and host == _proxy_hostname(setup).lower()
            else "is no name a browser anywhere else can reach"
        )
        warnings.append(
            f"The public address of Authentik ({address}) {reason}, so the "
            "generated proxy configuration carries no site for it - and every "
            "sign-in redirects a browser there. Give Authentik an address a "
            "browser can reach, such as https://sso.example.com, and the "
            "configuration serves it too."
        )
    if _writes_proxy(setup) and _proxy_hostname(setup) == "localhost":
        warnings.append(
            "The reverse proxy configuration answers to 'localhost', because "
            "that is all the public address of this service names. It will "
            "work on this machine and nowhere else - give the public address "
            "the name visitors type, or edit the generated file before "
            "installing it."
        )
    if (
        _writes_proxy(setup)
        and setup.reverse_proxy in {"nginx", "apache"}
        and not setup.reverse_proxy_tls
    ):
        warnings.append(
            "The generated proxy configuration terminates no TLS. That is "
            "only right if something else in front of it does: this service "
            "hands out result URLs whose uuid is the whole authorisation, and "
            "over plain HTTP they travel in the clear."
        )
    if setup.smtp_host and setup.smtp_auth and not setup.smtp_username:
        warnings.append(
            "The mail server was said to require an account but no username "
            "was given. Authentik reads an empty username as 'do not "
            "authenticate', and a server that wanted one refuses the "
            "submission."
        )

    if _uses_authentik(setup):
        pinned = _authentik_release(setup.authentik_tag)
        shipped = _authentik_release(AUTHENTIK_TAG)
        if pinned and shipped and pinned[:2] < shipped[:2]:
            warnings.append(
                f"Authentik is pinned to {setup.authentik_tag}, and this wizard "
                f"ships {AUTHENTIK_TAG}. Releases in a newer series can carry "
                "migrations and breaking changes, so it is not moved for you: "
                "read Authentik's release notes, then answer the image tag "
                "question with the newer release."
            )
    if _uses_authentik(setup) and not _merge_usernames(
        setup.authentik_accounts, setup.admin_users if setup.admin_enabled else ""
    ):
        warnings.append(
            "Authentik is in the stack but names nobody who signs in, so the "
            "enrollment link admits nobody and the only account is "
            f"{AUTHENTIK_BOOTSTRAP_USER}. Name the people who should get one "
            "under 'Who signs in'."
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
    if (
        _keeps_audit_file(setup)
        and setup.audit_storage == "filesystem"
        and not setup.audit_log_path.strip()
    ):
        warnings.append(
            "The audit trail was set to go to a host directory but none was "
            f"named, so it goes to the named volume {AUDIT_VOLUME} instead. "
            "That keeps the records; it just keeps them somewhere Docker "
            f"chose. Name a directory - {DEFAULT_AUDIT_LOG_PATH} is beside "
            "the compose file - to put them where your backups already look."
        )
    if _keeps_audit_file(setup) and _binds_a_directory(
        setup.audit_storage, setup.audit_log_path
    ):
        warnings.append(
            f"{setup.audit_log_path} has to exist and be owned by uid "
            f"{WEB_IMAGE_UID} {_as_the_container_sees_it(setup)}before the "
            "stack starts, or the web service refuses to come up rather than "
            "report an audit trail it cannot write. From the directory of the "
            "compose file:  "
            + _ownership_command(setup, setup.audit_log_path, WEB_IMAGE_UID)
        )
    if _uses_logrotate(setup):
        warnings.append(
            f"The generated {logrotate_filename(setup)} does nothing until it "
            "is installed into /etc/logrotate.d as root - and until it is, "
            "nothing rotates the audit trail, because the service was told "
            "the host would. The next steps print the command."
        )
    if (
        _uses_logrotate(setup)
        and _rootless(setup)
        and _mapped_id(SUBUID_FILE, WEB_IMAGE_UID) is None
    ):
        warnings.append(
            f"On a rootless Docker, uid {WEB_IMAGE_UID} in the container is a "
            f"subordinate uid on the host, and {SUBUID_FILE} names no range for "
            "the user running this wizard - so the generated logrotate policy "
            f"creates the new file as host uid {WEB_IMAGE_UID}, which the "
            "container cannot write to. Replace the ids on its 'create' line "
            "with <start of your subuid range> + "
            f"{WEB_IMAGE_UID - 1} before installing it."
        )
    if setup.redis_persistence == "filesystem" and not setup.redis_data_path.strip():
        warnings.append(
            "Redis persistence was set to a host directory but none was "
            f"named, so it uses the named volume {REDIS_VOLUME} instead. The "
            f"mount that would otherwise have been written - ':{REDIS_DATA_DIRECTORY}' "
            "- is not one Compose can parse, and the stack would not have "
            f"started at all. Name a directory, {DEFAULT_REDIS_DATA_PATH} for "
            "one beside the compose file, to choose where it goes."
        )
    if _binds_a_directory(setup.redis_persistence, setup.redis_data_path):
        warnings.append(
            f"{setup.redis_data_path} has to exist and be owned by uid "
            f"{REDIS_IMAGE_UID} {_as_the_container_sees_it(setup)}- the user "
            "the Redis image runs as. From the directory of the compose file:  "
            + _ownership_command(setup, setup.redis_data_path, REDIS_IMAGE_UID)
        )
    if _rootless(setup) and (
        _binds_a_directory(setup.redis_persistence, setup.redis_data_path)
        or (
            _keeps_audit_file(setup)
            and _binds_a_directory(setup.audit_storage, setup.audit_log_path)
        )
    ):
        warnings.append(
            "On a rootless Docker the host directories end up owned by your "
            "subordinate uids rather than by you, so your own account can no "
            "longer read or delete what is in them. That is the arrangement "
            "working, not a fault: read them through a container the same way "
            "the ownership was set, e.g. docker run --rm --user 0 -v "
            f'"$(realpath <dir>)":/target {REDIS_IMAGE} ls -l /target.'
        )
    if (
        _rootless(setup)
        and not setup.trust_forwarded_for
        and setup.bind_address.strip() not in {"127.0.0.1", "::1", "localhost"}
    ):
        warnings.append(
            "A rootless Docker's default port driver does not pass the client "
            "address on: every connection to a published port reaches the "
            "container from the daemon's own namespace, so the per-client "
            "rate limit counts the whole internet as one address. Put a "
            "reverse proxy on the host in front of 127.0.0.1 and trust the "
            "X-Forwarded-For it sets, or run the daemon with "
            "DOCKERD_ROOTLESS_ROOTLESSKIT_PORT_DRIVER=slirp4netns."
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


def _proxy_hostname(setup: Setup) -> str:
    """The one name the generated proxy configuration answers to.

    Taken from the public address when it was not asked for separately, so
    that the certificate, ``server_name`` and the canonical links the service
    publishes cannot drift apart - three places naming three hosts is a
    deployment that works until somebody uses the second one.
    """
    name = setup.reverse_proxy_hostname.strip()
    if name:
        return name
    host = setup.public_base_url.strip().split("://", 1)[-1]
    host = host.split("/", 1)[0].rsplit("@", 1)[-1]
    if host.startswith("["):  # an IPv6 literal keeps its brackets and its port
        return host
    return host.split(":", 1)[0] or "localhost"


def _proxy_scheme(setup: Setup) -> str:
    """http or https, as the generated configuration will actually serve it."""
    if setup.reverse_proxy in {"caddy", "traefik"}:
        return "https"  # both fetch a certificate themselves
    return "https" if setup.reverse_proxy_tls else "http"


def _proxy_public_url(setup: Setup) -> str:
    """The address the generated proxy publishes this service at."""
    return f"{_proxy_scheme(setup)}://{_proxy_hostname(setup)}"


def _authentik_host_url(setup: Setup) -> str:
    """Where the proxy on this host reaches Authentik's HTTP listener.

    The compose file publishes it on the loopback address, so this is a local
    address whatever the provider's public name turns out to be - the browser
    is redirected to :attr:`Setup.authentik_url`, and only the forward-auth
    subrequest comes here.
    """
    return f"http://127.0.0.1:{setup.authentik_http_port}"


def _finalise(setup: Setup) -> None:
    """Fill in what the answers imply rather than asking for it twice.

    Everything here is derivable: the issuer from the Authentik address and
    the slug, the redirect back from the address this service is reached at,
    the credentials from a random number generator. Asking would be a quiz.
    """
    if setup.docker_mode not in DOCKER_MODES:
        setup.docker_mode = "rootful"
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
        setup.authentik_bootstrap_password = (
            setup.authentik_bootstrap_password or secrets.token_urlsafe(30)
        )
        # The token becomes an invitation's primary key, so a value that is no
        # UUID - edited by hand, say - would fail the whole blueprint rather
        # than one field of it. Replaced, which retires whatever link it was.
        if not _is_uuid(setup.authentik_enrollment_token):
            setup.authentik_enrollment_token = str(uuid.uuid4())
        setup.authentik_accounts = _merge_usernames(
            setup.authentik_accounts, setup.admin_users if setup.admin_enabled else ""
        )
        if not setup.smtp_auth:
            # Said to need no account, so it keeps none. A username left over
            # from an earlier answer would make Authentik authenticate to a
            # relay that never asked it to, and fail at the first message.
            setup.smtp_username = ""
            setup.smtp_password = ""
        if setup.smtp_host and not setup.smtp_from:
            setup.smtp_from = setup.smtp_username or "authentik@localhost"
    else:
        # Answered and then made irrelevant: a leftover credential in .env for
        # a provider this deployment does not run is a secret nobody rotates.
        setup.authentik_secret_key = ""
        setup.authentik_pg_password = ""
        setup.authentik_client_id = ""
        setup.authentik_client_secret = ""
        setup.authentik_bootstrap_password = ""
        setup.authentik_enrollment_token = ""
        setup.smtp_host = ""
        setup.smtp_password = ""
    if _writes_proxy(setup) and not setup.reverse_proxy_hostname:
        # Recorded rather than recomputed at every use, so the summary shows
        # the name the file will actually carry.
        setup.reverse_proxy_hostname = _proxy_hostname(setup)


def _is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _merge_usernames(*lists: str) -> str:
    """Semicolon-separated names, each once, in the order first given."""
    names: list[str] = []
    for listed in lists:
        for name in listed.split(";"):
            if name.strip() and name.strip() not in names:
                names.append(name.strip())
    return ";".join(names)


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
        _entry(
            "AUTHENTIK_BOOTSTRAP_PASSWORD",
            f'"{_env_reference("authentik_bootstrap_password")}"',
            f"The password of {AUTHENTIK_BOOTSTRAP_USER}, applied on the very first start",
            "only. Setting it closes the initial-setup flow, which would otherwise",
            "make whoever reached it first the administrator. Kept for recovery:",
            "sign in as it to remove somebody's lost second factor.",
        ),
        _entry(
            "COS_AUTHENTIK_ENROLLMENT_TOKEN",
            f'"{_env_reference("authentik_enrollment_token")}"',
            "Read by the enrollment blueprint: the invitation behind the link",
            "each person below opens to choose a password and a second factor.",
        ),
        _entry(
            "COS_AUTHENTIK_ACCOUNTS",
            f'"{setup.authentik_accounts}"',
            "Who may create an account with that link, each name once. Anybody",
            "else is refused at the form.",
        ),
    ]
    if _guards_the_admin_area(setup):
        entries.append(
            _entry(
                "COS_WEB_ADMIN_URL",
                f'"{setup.public_base_url}"',
                "Read by the second blueprint, the one that provisions the proxy",
                "provider in front of /admin. A forward-auth provider is bound to",
                "the origin of the application it protects, so this is the address",
                "visitors use rather than the container's own.",
            )
        )
        entries.append(
            _entry(
                "COS_AUTHENTIK_URL",
                f'"{setup.authentik_url}"',
                "Read by the same blueprint, for the embedded outpost that answers",
                "the forward auth: it is where the outpost sends a browser to sign",
                "in. Left unset, that redirect goes to http://localhost instead.",
            )
        )
        entries.append(
            _entry(
                "COS_WEB_ADMIN_USERS",
                f'"{setup.admin_users}"',
                "Read by the enrollment flow: an account created under one of these",
                f"names joins {AUTHENTIK_OPERATOR_GROUP}, the group /admin is bound to.",
            )
        )
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
        if _binds_a_directory(setup.redis_persistence, setup.redis_data_path)
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
    if _keeps_audit_file(setup) and not _binds_a_directory(
        setup.audit_storage, setup.audit_log_path
    ):
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
    if _persists_redis(setup) and not _binds_a_directory(
        setup.redis_persistence, setup.redis_data_path
    ):
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


def render_logrotate_file(setup: Setup, base_dir: Path | None = None) -> str:
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
    # Absolute, whatever the answer was: Compose resolves `./audit` against
    # the compose file, logrotate resolves it against wherever cron happens to
    # run it from, which is `/`.
    path = f"{_host_path(setup.audit_log_path, base_dir or Path('.'))}/{AUDIT_LOG_FILENAME}"
    owner, group = WEB_IMAGE_UID, WEB_IMAGE_UID
    ownership_note = ""
    if _rootless(setup):
        owner = _mapped_id(SUBUID_FILE, WEB_IMAGE_UID) or WEB_IMAGE_UID
        group = _mapped_id(SUBGID_FILE, WEB_IMAGE_UID) or WEB_IMAGE_UID
        ownership_note = (
            "    #\n"
            "    # The Docker daemon is rootless, so these are the host ids that uid\n"
            f"    # and gid {WEB_IMAGE_UID} in the container map to: the start of this user's\n"
            f"    # range in {SUBUID_FILE} and {SUBGID_FILE}, plus {WEB_IMAGE_UID - 1}.\n"
        )
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
{ownership_note}    create 0600 {owner} {group}
}}
"""


# --- the reverse proxy ------------------------------------------------------
# The templates below are filled by replacing `@@name@@`, not by str.format or
# an f-string: every one of these languages is made of braces, and a config
# file whose every `{` has to be doubled to survive the generator is one
# nobody can read against the documentation it came from.
def _fill(template: str, **values: str) -> str:
    for name, value in values.items():
        template = template.replace(f"@@{name}@@", value)
    return template


def _indent(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else "" for line in text.splitlines())


def _upstream_address(setup: Setup) -> str:
    """Where the proxy connects, as ``host:port``.

    Not simply the published bind address: ``0.0.0.0`` means *listen on every
    interface*, and a proxy asked to *connect* to it reaches nothing on most
    systems. The loopback address is the one that is always right here,
    because the proxy runs on the host the port is published on.
    """
    host = setup.bind_address.strip()
    if host in {"", "0.0.0.0", "::", "[::]", "*"}:  # nosec B104
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{setup.host_port}"


def proxy_filename(setup: Setup) -> str:
    """What the generated proxy configuration is called, before it is installed."""
    suffix = {
        "nginx": "nginx.conf",
        "apache": "apache.conf",
        "caddy": "caddyfile",
        "traefik": "traefik.yml",
    }[setup.reverse_proxy]
    return f"{setup.project_name}-{suffix}"


def admin_secret_filename(setup: Setup) -> str:
    """The one line of nginx configuration that carries a credential.

    Kept out of the configuration file for the same reason the compose file
    carries no password: a proxy configuration is something an operator
    commits, pastes into a ticket and copies between hosts. Deliberately not
    named ``.conf``, because everything called that under ``conf.d`` is
    included into the *http* block, and this belongs to one location.
    """
    return f"{setup.project_name}-admin-proxy.secret"


def admin_secret_path(setup: Setup) -> str:
    """Where that file has to be installed for the ``include`` to find it."""
    return f"/etc/nginx/{admin_secret_filename(setup)}"


def render_admin_secret_file(setup: Setup) -> str:
    """The nginx snippet holding the shared secret, and nothing else."""
    return f"""# The secret the outpost's verdict is worth nothing without.
#
# Written by docker/setup-wizard.py and included from the {ADMIN_PATH} location
# in {proxy_filename(setup)}. It is the same value as
# COS_WEB_ADMIN_PROXY_SECRET in .env: the service compares the two in constant
# time and answers 404 to anything arriving without it, so a request that
# reaches the container by some other route gets no console.
#
# Owner-readable only. Install it as root:
#
#   sudo install -m 0600 -o root -g root {admin_secret_filename(setup)} \\
#     {admin_secret_path(setup)}
proxy_set_header {ADMIN_PROXY_HEADER} "{setup.admin_proxy_secret}";
"""


_NGINX_PROXY_HEADERS = """proxy_http_version 1.1;
proxy_set_header Host              $host;
proxy_set_header X-Forwarded-Proto $scheme;
# Set, never appended: the service counts scans per client address, and a
# header a client may add to is a rate limit a client may choose.
proxy_set_header X-Forwarded-For   $remote_addr;
proxy_set_header X-Real-IP         $remote_addr;"""


def _nginx_locations(setup: Setup, upstream: str) -> str:
    """Every ``location`` block, in the order nginx should be read in."""
    blocks = [
        _fill(
            """    location / {
@@headers@@
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $connection_upgrade;
        # A scan takes seconds to a minute and an export can take longer.
        proxy_read_timeout 300s;
        proxy_pass @@upstream@@;
    }""",
            headers=_indent(_NGINX_PROXY_HEADERS, "        "),
            upstream=upstream,
        )
    ]
    if setup.enable_mcp:
        blocks.append(
            _fill(
                """    # The MCP endpoint answers with an event stream. A proxy that buffers
    # one turns a working agent session into a client that waits for ever,
    # and a short read timeout ends one in the middle of an answer.
    location @@mcp@@ {
@@headers@@
        proxy_set_header Connection        "";
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        proxy_read_timeout 3600s;
        proxy_pass @@upstream@@;
    }""",
                headers=_indent(_NGINX_PROXY_HEADERS, "        "),
                upstream=upstream,
                mcp=MCP_PATH,
            )
        )
    if _proxy_forwards_auth(setup):
        blocks.append(
            _fill(
                """    # The operator's area. Every request is shown to the authentik outpost
    # first and only what it accepts is passed on - carrying the identity
    # the outpost established, and the shared secret that is the whole
    # reason those identity headers are worth believing. Take the include
    # away and the area stops answering, which is the correct direction for
    # this to fail in.
    location @@admin@@ {
        auth_request     @@outpost@@/auth/nginx;
        error_page 401 = @goauthentik_signin;

        auth_request_set $auth_cookie        $upstream_http_set_cookie;
        add_header       Set-Cookie          $auth_cookie;
        auth_request_set $authentik_username $upstream_http_x_authentik_username;
        auth_request_set $authentik_groups   $upstream_http_x_authentik_groups;
        auth_request_set $authentik_email    $upstream_http_x_authentik_email;

@@headers@@
        proxy_set_header @@user_header@@ $authentik_username;
        proxy_set_header @@groups_header@@   $authentik_groups;
        proxy_set_header @@email_header@@    $authentik_email;
        include @@secret_file@@;
        # The outpost answers with a session cookie and identity headers that
        # outgrow nginx's default buffers, which fails as "upstream sent too
        # big header" - a 502 for a sign-in that worked.
        proxy_buffers     8 16k;
        proxy_buffer_size 32k;
        # The audit view is an event stream too, so this block may no more be
        # buffered than /mcp may.
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_pass @@upstream@@;
    }

    # Where the outpost itself answers: the forward-auth subrequest above,
    # the sign-in it redirects to, and the sign-out link the area offers.
    location @@outpost@@ {
        proxy_pass @@authentik@@@@outpost@@;
        proxy_set_header Host           $host;
        proxy_set_header X-Original-URL $scheme://$http_host$request_uri;
        auth_request_set $auth_cookie   $upstream_http_set_cookie;
        add_header       Set-Cookie     $auth_cookie;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_buffers     8 16k;
        proxy_buffer_size 32k;
    }

    location @goauthentik_signin {
        internal;
        add_header Set-Cookie $auth_cookie;
        return 302 @@outpost@@/start?rd=$request_uri;
    }""",
                headers=_indent(_NGINX_PROXY_HEADERS, "        "),
                upstream=upstream,
                admin=ADMIN_PATH,
                outpost=AUTHENTIK_OUTPOST_PREFIX,
                authentik=_authentik_host_url(setup),
                secret_file=admin_secret_path(setup),
                user_header=ADMIN_IDENTITY_HEADERS[0],
                groups_header=ADMIN_IDENTITY_HEADERS[1],
                email_header=ADMIN_IDENTITY_HEADERS[2],
            )
        )
    return "\n\n".join(blocks)


def _nginx_redirect(setup: Setup, host: str) -> str:
    """The port-80 server that sends a visitor back over TLS, when there is TLS."""
    if not setup.reverse_proxy_tls:
        return ""
    return _fill(
        """server {
    listen 80;
    listen [::]:80;
    server_name @@host@@;

    # An ACME client answering on :80 keeps working; everything else is
    # told, permanently, to come back over TLS.
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    location / {
        return 308 https://$host$request_uri;
    }
}

""",
        host=host,
    )


def _nginx_listen(setup: Setup) -> str:
    if setup.reverse_proxy_tls:
        return """    listen 443 ssl;
    listen [::]:443 ssl;
    # nginx 1.25 and newer. On anything older, write the two lines above as
    # `listen 443 ssl http2;` and delete this one.
    http2 on;"""
    return """    listen 80;
    listen [::]:80;"""


def _nginx_tls(setup: Setup, certificate: str, private_key: str) -> str:
    if not setup.reverse_proxy_tls:
        return ""
    return _fill(
        """
    ssl_certificate     @@certificate@@;
    ssl_certificate_key @@private_key@@;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_prefer_server_ciphers off;
""",
        certificate=certificate,
        private_key=private_key,
    )


def _authentik_certificate(setup: Setup) -> tuple[str, str]:
    """The certificate and key Authentik's site is served with, on the proxy host."""
    return (
        setup.reverse_proxy_authentik_certificate or "/etc/ssl/sso/fullchain.pem",
        setup.reverse_proxy_authentik_private_key or "/etc/ssl/sso/privkey.pem",
    )


def _nginx_authentik_site(setup: Setup) -> str:
    """The server blocks for Authentik's own interface, or nothing."""
    if not _proxy_serves_authentik(setup):
        return ""
    host = _authentik_proxy_hostname(setup)
    certificate, private_key = _authentik_certificate(setup)
    return _fill(
        """

# Authentik's own interface, at the host name of its public address: where
# every sign-in is sent, and the address every token names as its issuer.
# Authentik keeps a WebSocket open from its interface, hence the upgrade, and
# believes X-Forwarded-For from the Docker network the published port arrives
# through - so it is set here, never appended, for the same reason as above.
@@redirect@@server {
@@listen@@
    server_name @@host@@;
@@tls@@
    location / {
@@headers@@
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $connection_upgrade;
        proxy_pass @@authentik@@;
    }
}""",
        redirect=_nginx_redirect(setup, host),
        listen=_nginx_listen(setup),
        host=host,
        tls=_nginx_tls(setup, certificate, private_key),
        headers=_indent(_NGINX_PROXY_HEADERS, "        "),
        authentik=_authentik_host_url(setup),
    )


def _render_nginx(setup: Setup) -> str:
    upstream = f"http://{_upstream_address(setup)}"
    redirect = _nginx_redirect(setup, _proxy_hostname(setup))
    listen = _nginx_listen(setup)
    tls = _nginx_tls(
        setup,
        setup.reverse_proxy_certificate or "/etc/ssl/scan/fullchain.pem",
        setup.reverse_proxy_private_key or "/etc/ssl/scan/privkey.pem",
    )
    return _fill(
        """# nginx for the check-opencloud-security web application.
#
# Written by docker/setup-wizard.py. Install it as root, once:
#
#   sudo install -m 0644 -o root -g root @@file@@ \\
#     /etc/nginx/conf.d/@@project@@.conf
#   sudo nginx -t && sudo systemctl reload nginx
#
# It proxies to @@upstream@@, which is where the generated compose file
# publishes the service - the containers stay on that address and are never
# reachable from the network themselves.
#
# Three things in here are load-bearing rather than decorative:
#
#   * X-Forwarded-For is *set*, not appended, so a client cannot choose the
#     address its rate limit is counted against. Set
#     COS_WEB_TRUST_FORWARDED_FOR=true, or the service goes on counting every
#     visitor as this proxy.
#   * /mcp is never buffered. It answers with an event stream.
#   * nothing under /.well-known/ is answered here except the ACME challenge.
#     The service serves /.well-known/ai.json itself, and an ACME setup that
#     claims the whole prefix claims that with it.
#
# No security headers are added: the application sends its own, and an
# `add_header` here would be one more place they can disagree.

map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

@@redirect@@server {
@@listen@@
    server_name @@host@@;
@@tls@@
@@locations@@
}@@authentik_site@@
""",
        file=proxy_filename(setup),
        project=setup.project_name,
        upstream=upstream,
        redirect=redirect,
        listen=listen,
        tls=tls,
        host=_proxy_hostname(setup),
        locations=_nginx_locations(setup, upstream),
        authentik_site=_nginx_authentik_site(setup),
    )


def _render_apache(setup: Setup) -> str:
    upstream = f"http://{_upstream_address(setup)}"
    mcp = (
        _fill(
            """
    # The MCP endpoint answers with an event stream, and this block has to
    # come before the catch-all below or the catch-all wins and buffers it.
    <Location "@@mcp@@">
        ProxyPass        @@upstream@@@@mcp@@ flushpackets=on timeout=3600
        ProxyPassReverse @@upstream@@@@mcp@@
        SetEnv proxy-sendchunked 1
        SetEnv no-gzip 1
    </Location>
""",
            upstream=upstream,
            mcp=MCP_PATH,
        )
        if setup.enable_mcp
        else ""
    )
    admin = (
        _fill(
            """
    # @@admin@@ gets no sign-in from this file. Apache has no forward-auth of
    # its own, so nothing here can ask the outpost whether a request may pass,
    # and a block that proxied the area without asking would serve an
    # unauthenticated console. It is proxied by the catch-all below like every
    # other path, without @@header@@ - so the service answers 404, which is the
    # right failure, and it will look like a bug.
    #
    # Two ways to give it one: mod_auth_openidc against the provider, adding
    # the header with `RequestHeader set @@header@@` inside the protected
    # <Location>; or an authentik proxy provider in full proxy mode in front.
    #
    # Until then these four headers are stripped on the way in. They are the
    # outpost's to write and a client's to be refused for sending.
    <Location "/">
        RequestHeader unset @@header@@
@@strip@@
    </Location>
""",
            admin=ADMIN_PATH,
            header=ADMIN_PROXY_HEADER,
            strip="\n".join(
                f"        RequestHeader unset {item}" for item in ADMIN_IDENTITY_HEADERS
            ),
        )
        if setup.admin_enabled
        else ""
    )
    redirect = _apache_redirect(setup, _proxy_hostname(setup))
    tls = _apache_tls(
        setup,
        setup.reverse_proxy_certificate or "/etc/ssl/scan/fullchain.pem",
        setup.reverse_proxy_private_key or "/etc/ssl/scan/privkey.pem",
    )
    return _fill(
        """# Apache httpd for the check-opencloud-security web application.
#
# Written by docker/setup-wizard.py. Install it as root, once:
#
#   sudo a2enmod proxy proxy_http headers rewrite ssl
#   sudo install -m 0644 -o root -g root @@file@@ \\
#     /etc/apache2/sites-available/@@project@@.conf
#   sudo a2ensite @@project@@ && sudo apachectl configtest
#   sudo systemctl reload apache2
#
# On a Red Hat derivative the file belongs in /etc/httpd/conf.d/ instead and
# the modules are loaded already.
#
# It proxies to @@upstream@@, where the generated compose
# file publishes the service. X-Forwarded-For is *set* rather than appended,
# so a client cannot choose the address its rate limit is counted against -
# set COS_WEB_TRUST_FORWARDED_FOR=true to have the service read it.

@@redirect@@<VirtualHost *:@@port@@>
    ServerName @@host@@
@@tls@@
    ProxyPreserveHost On
    ProxyRequests Off
    RequestHeader set X-Forwarded-Proto "@@scheme@@"
    # set, not add: the client does not get a vote on its own address.
    RequestHeader set X-Forwarded-For "%{REMOTE_ADDR}e"
@@mcp@@@@admin@@
    ProxyPass        / @@upstream@@/ timeout=300
    ProxyPassReverse / @@upstream@@/
</VirtualHost>@@authentik_site@@
""",
        file=proxy_filename(setup),
        project=setup.project_name,
        upstream=upstream,
        redirect=redirect,
        port="443" if setup.reverse_proxy_tls else "80",
        host=_proxy_hostname(setup),
        scheme=_proxy_scheme(setup),
        tls=tls,
        mcp=mcp,
        admin=admin,
        authentik_site=_apache_authentik_site(setup),
    )


def _apache_redirect(setup: Setup, host: str) -> str:
    """The port-80 virtual host that sends a visitor back over TLS."""
    if not setup.reverse_proxy_tls:
        return ""
    return _fill(
        """<VirtualHost *:80>
    ServerName @@host@@

    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/\\.well-known/acme-challenge/
    RewriteRule ^ https://%{SERVER_NAME}%{REQUEST_URI} [R=308,L]
</VirtualHost>

""",
        host=host,
    )


def _apache_tls(setup: Setup, certificate: str, private_key: str) -> str:
    if not setup.reverse_proxy_tls:
        return ""
    return _fill(
        """
    SSLEngine on
    SSLCertificateFile    @@certificate@@
    SSLCertificateKeyFile @@private_key@@
    SSLProtocol -all +TLSv1.2 +TLSv1.3
""",
        certificate=certificate,
        private_key=private_key,
    )


def _apache_authentik_site(setup: Setup) -> str:
    """The virtual hosts for Authentik's own interface, or nothing."""
    if not _proxy_serves_authentik(setup):
        return ""
    host = _authentik_proxy_hostname(setup)
    certificate, private_key = _authentik_certificate(setup)
    return _fill(
        """

# Authentik's own interface, at the host name of its public address: where
# every sign-in is sent, and the address every token names as its issuer.
# Authentik keeps a WebSocket open from its interface; `upgrade=websocket`
# is what carries it, and it needs Apache 2.4.47 or newer.
@@redirect@@<VirtualHost *:@@port@@>
    ServerName @@host@@
@@tls@@
    ProxyPreserveHost On
    ProxyRequests Off
    RequestHeader set X-Forwarded-Proto "@@scheme@@"
    RequestHeader set X-Forwarded-For "%{REMOTE_ADDR}e"

    ProxyPass        / @@authentik@@/ upgrade=websocket timeout=300
    ProxyPassReverse / @@authentik@@/
</VirtualHost>""",
        redirect=_apache_redirect(setup, host),
        port="443" if setup.reverse_proxy_tls else "80",
        host=host,
        tls=_apache_tls(setup, certificate, private_key),
        scheme=_proxy_scheme(setup),
        authentik=_authentik_host_url(setup),
    )


def _render_caddy(setup: Setup) -> str:
    upstream = _upstream_address(setup)
    authentik = f"127.0.0.1:{setup.authentik_http_port}"
    blocks = []
    if setup.reverse_proxy_acme_email:
        blocks.append(
            _fill(
                """	# Where the certificate authority writes when a renewal has been
	# failing. Caddy obtains and renews the certificate itself.
	tls @@email@@
""",
                email=setup.reverse_proxy_acme_email,
            )
        )
    blocks.append("\tencode zstd gzip\n")
    if _proxy_forwards_auth(setup):
        blocks.append(
            _fill(
                """	# The outpost's own endpoints: the forward-auth subrequest, the
	# sign-in it redirects to, and the sign-out link the area offers.
	handle @@outpost@@/* {
		reverse_proxy @@authentik@@
	}

	# The operator's area. Shown to the outpost first; only what it accepts
	# is passed on, carrying the identity it established and the shared
	# secret that makes those headers worth believing. Caddy reads the
	# secret from its own environment, so it is not in this file.
	handle @@admin@@* {
		forward_auth @@authentik@@ {
			uri @@outpost@@/auth/caddy
			copy_headers @@identity@@
		}
		reverse_proxy @@upstream@@ {
			header_up @@header@@ {env.@@variable@@}
			# The audit view is an event stream, like /mcp below.
			flush_interval -1
			transport http {
				read_timeout 1h
			}
		}
	}
""",
                outpost=AUTHENTIK_OUTPOST_PREFIX,
                authentik=authentik,
                admin=ADMIN_PATH,
                upstream=upstream,
                identity=" ".join(ADMIN_IDENTITY_HEADERS),
                header=ADMIN_PROXY_HEADER,
                variable=SECRET_VARIABLES["admin_proxy_secret"],
            )
        )
    if setup.enable_mcp:
        blocks.append(
            _fill(
                """	# The MCP endpoint answers with an event stream: flush_interval -1
	# is what stops Caddy buffering it into silence.
	handle @@mcp@@* {
		reverse_proxy @@upstream@@ {
			flush_interval -1
			transport http {
				read_timeout 1h
			}
		}
	}
""",
                mcp=MCP_PATH,
                upstream=upstream,
            )
        )
    blocks.append(
        _fill(
            """	handle {
		reverse_proxy @@upstream@@ {
			transport http {
				read_timeout 5m
			}
		}
	}
""",
            upstream=upstream,
        )
    )
    secret_note = (
        _fill(
            """#
# One value is read from the environment rather than written here: Caddy
# substitutes {env.@@variable@@} at request time, so give it to the service -
# `systemctl edit caddy` and an EnvironmentFile pointing at the generated
# .env is the usual way. Without it the header is empty and the area answers
# 404, which is the right direction for this to fail in.
""",
            variable=SECRET_VARIABLES["admin_proxy_secret"],
        )
        if _proxy_forwards_auth(setup)
        else ""
    )
    return _fill(
        """# Caddy for the check-opencloud-security web application.
#
# Written by docker/setup-wizard.py. Install it as root, once:
#
#   sudo install -m 0644 -o root -g root @@file@@ /etc/caddy/@@file@@
#   echo 'import @@file@@' | sudo tee -a /etc/caddy/Caddyfile
#   sudo caddy validate --config /etc/caddy/Caddyfile
#   sudo systemctl reload caddy
#
# Written to be imported, so it carries no global options block - the site's
# own `tls` line does the one thing such a block would have been for.
#
# Caddy obtains and renews the certificate itself, and writes X-Forwarded-For
# from the connection while dropping whatever the client sent, which is what
# makes COS_WEB_TRUST_FORWARDED_FOR=true safe here.
@@secret_note@@
@@host@@ {
@@blocks@@}
@@authentik_site@@""",
        file=proxy_filename(setup),
        secret_note=secret_note,
        host=_proxy_hostname(setup),
        blocks="\n".join(blocks),
        authentik_site=_caddy_authentik_site(setup),
    )


def _caddy_authentik_site(setup: Setup) -> str:
    """The site block for Authentik's own interface, or nothing."""
    if not _proxy_serves_authentik(setup):
        return ""
    tls = (
        f"\ttls {setup.reverse_proxy_acme_email}\n" if setup.reverse_proxy_acme_email else ""
    )
    return _fill(
        """
# Authentik's own interface, at the host name of its public address: where
# every sign-in is sent, and the address every token names as its issuer.
# Caddy carries the WebSocket Authentik's interface keeps open without being
# told, and sets X-Forwarded-For from the connection here as well.
@@host@@ {
@@tls@@	reverse_proxy @@authentik@@
}
""",
        host=_authentik_proxy_hostname(setup),
        tls=tls,
        authentik=f"127.0.0.1:{setup.authentik_http_port}",
    )


def _render_traefik(setup: Setup) -> str:
    upstream = f"http://{_upstream_address(setup)}"
    authentik = _authentik_host_url(setup)
    name = setup.project_name
    admin_routers = (
        _fill(
            """
    @@name@@-admin:
      # Higher than the router above, so the area is matched first and the
      # middlewares below are not skipped. They are the only thing between
      # the console and whoever asks for it.
      rule: "Host(`@@host@@`) && PathPrefix(`@@admin@@`)"
      priority: 20
      entryPoints:
        - websecure
      middlewares:
        - @@name@@-admin-auth
        - @@name@@-admin-secret
      service: @@name@@
      tls:
        certResolver: letsencrypt

    @@name@@-outpost:
      # The outpost's own endpoints, which have to reach authentik rather
      # than the scan service: the forward-auth subrequest, the sign-in it
      # redirects to, and the sign-out link the area offers.
      rule: "Host(`@@host@@`) && PathPrefix(`@@outpost@@`)"
      priority: 30
      entryPoints:
        - websecure
      service: @@name@@-authentik
      tls:
        certResolver: letsencrypt
""",
            name=name,
            host=_proxy_hostname(setup),
            admin=ADMIN_PATH,
            outpost=AUTHENTIK_OUTPOST_PREFIX,
        )
        if _proxy_forwards_auth(setup)
        else ""
    )
    authentik_routers = (
        _fill(
            """
    @@name@@-authentik:
      # Authentik's own interface, at the host name of its public address:
      # where every sign-in is sent, and the address every token names as its
      # issuer. Traefik carries the WebSocket it keeps open by default.
      rule: "Host(`@@authentik_host@@`)"
      priority: 10
      entryPoints:
        - websecure
      service: @@name@@-authentik
      tls:
        certResolver: letsencrypt
""",
            name=name,
            authentik_host=_authentik_proxy_hostname(setup),
        )
        if _proxy_serves_authentik(setup)
        else ""
    )
    admin_services = (
        _fill(
            """
    @@name@@-authentik:
      loadBalancer:
        servers:
          - url: "@@authentik@@"
""",
            name=name,
            authentik=authentik,
        )
        if _proxy_forwards_auth(setup) or _proxy_serves_authentik(setup)
        else ""
    )
    middlewares = (
        _fill(
            """
  middlewares:
    @@name@@-admin-auth:
      forwardAuth:
        address: "@@authentik@@@@outpost@@/auth/traefik"
        trustForwardHeader: true
        authResponseHeaders:
@@identity@@

    @@name@@-admin-secret:
      headers:
        customRequestHeaders:
          # Read from Traefik's own environment: a dynamic configuration file
          # is rendered as a Go template before it is parsed. If yours is not,
          # put the value from .env here instead and chmod 0600 this file.
          @@header@@: '{{ env "@@variable@@" }}'
""",
            name=name,
            authentik=authentik,
            outpost=AUTHENTIK_OUTPOST_PREFIX,
            identity="\n".join(f"          - {item}" for item in ADMIN_IDENTITY_HEADERS),
            header=ADMIN_PROXY_HEADER,
            variable=SECRET_VARIABLES["admin_proxy_secret"],
        )
        if _proxy_forwards_auth(setup)
        else ""
    )
    return _fill(
        """# Traefik dynamic configuration for the check-opencloud-security web
# application.
#
# Written by docker/setup-wizard.py. Install it as root, once:
#
#   sudo install -m 0644 -o root -g root @@file@@ \\
#     /etc/traefik/dynamic/@@name@@.yml
#
# and, in the static configuration, point the file provider at that directory
# and give the entrypoint timeouts long enough for a scan:
#
#   providers:
#     file:
#       directory: /etc/traefik/dynamic
#       watch: true
#   entryPoints:
#     websecure:
#       address: ":443"
#       transport:
#         respondingTimeouts:
#           readTimeout: 0
#           writeTimeout: 0
#           idleTimeout: 300s
#   certificatesResolvers:
#     letsencrypt:
#       acme:
#         email: @@email@@
#         storage: /etc/traefik/acme.json
#         httpChallenge:
#           entryPoint: web
#
# Traefik streams by default, so the MCP endpoint needs nothing beyond the
# flush interval below and those timeouts. It overwrites X-Real-Ip and
# *appends* to X-Forwarded-For; the service reads that header from the right,
# so COS_WEB_TRUST_FORWARDED_FOR=true with the default
# COS_WEB_TRUSTED_PROXY_HOPS=1 is correct here. Behind a CDN as well, count
# both and set 2.

http:
  routers:
    @@name@@:
      rule: "Host(`@@host@@`)"
      priority: 10
      entryPoints:
        - websecure
      service: @@name@@
      tls:
        certResolver: letsencrypt
@@admin_routers@@@@authentik_routers@@
  services:
    @@name@@:
      loadBalancer:
        servers:
          - url: "@@upstream@@"
        # Do not collect the event stream /mcp answers with into batches.
        responseForwarding:
          flushInterval: 1ms
@@admin_services@@@@middlewares@@""",
        file=proxy_filename(setup),
        name=name,
        host=_proxy_hostname(setup),
        upstream=upstream,
        email=setup.reverse_proxy_acme_email or "ops@example.com",
        admin_routers=admin_routers,
        authentik_routers=authentik_routers,
        admin_services=admin_services,
        middlewares=middlewares,
    )


def _proxy_install_commands(setup: Setup) -> list[str]:
    """How the generated proxy configuration gets installed, in order.

    Printed with the other next steps rather than run: every one of them needs
    root and touches a service this wizard was not pointed at. The same lines
    are in the header of the file itself, so an operator who finds it a year
    from now is not reading a file with no instructions.
    """
    if not _writes_proxy(setup):
        return []
    name = proxy_filename(setup)
    project = setup.project_name
    if setup.reverse_proxy == "nginx":
        commands = []
        if _proxy_forwards_auth(setup):
            commands.append(
                f"sudo install -m 0600 -o root -g root {admin_secret_filename(setup)} "
                f"{admin_secret_path(setup)}"
            )
        commands.append(
            f"sudo install -m 0644 -o root -g root {name} /etc/nginx/conf.d/{project}.conf"
        )
        commands.append("sudo nginx -t && sudo systemctl reload nginx")
        return commands
    if setup.reverse_proxy == "apache":
        return [
            "sudo a2enmod proxy proxy_http headers rewrite ssl",
            (
                f"sudo install -m 0644 -o root -g root {name} "
                f"/etc/apache2/sites-available/{project}.conf"
            ),
            f"sudo a2ensite {project} && sudo apachectl configtest",
            "sudo systemctl reload apache2",
        ]
    if setup.reverse_proxy == "caddy":
        return [
            f"sudo install -m 0644 -o root -g root {name} /etc/caddy/{name}",
            f"echo 'import {name}' | sudo tee -a /etc/caddy/Caddyfile",
            "sudo systemctl reload caddy",
        ]
    return [
        f"sudo install -m 0644 -o root -g root {name} /etc/traefik/dynamic/{project}.yml",
    ]


def render_proxy_file(setup: Setup) -> str:
    """The configuration for whichever reverse proxy was asked for."""
    return {
        "nginx": _render_nginx,
        "apache": _render_apache,
        "caddy": _render_caddy,
        "traefik": _render_traefik,
    }[setup.reverse_proxy](setup)


def _write_proxy_files(setup: Setup, output_dir: Path) -> list[str]:
    """The proxy configuration, and the one line of it that is a credential."""
    if not _writes_proxy(setup):
        return []
    written: list[str] = []
    path = output_dir / proxy_filename(setup)
    path.write_text(render_proxy_file(setup), encoding="utf-8")
    os.chmod(path, 0o644)
    written.append(f"{path} (install it into your {setup.reverse_proxy})")

    if _proxy_forwards_auth(setup) and setup.reverse_proxy == "nginx":
        # A path, not the credential, but named for what it is: code scanning
        # takes a variable called `secret` for the value itself, and this one
        # ends up in the list of written files the wizard prints.
        header_file = output_dir / admin_secret_filename(setup)
        descriptor = os.open(
            header_file, PRIVATE_FILE_FLAGS, stat.S_IRUSR | stat.S_IWUSR
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            handle.write(render_admin_secret_file(setup))
        os.chmod(header_file, stat.S_IRUSR | stat.S_IWUSR)
        written.append(f"{header_file} (owner-readable only)")
    return written


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
        *_abuse_environment(setup, web=True),
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
    if setup.admin_enabled:
        entries.append(
            _entry(
                "COS_WEB_ADMIN_ENABLED",
                '"true"',
                "The operator's area at /admin. With this off the routes are never",
                "registered, so the path answers the same 404 as any other unknown",
                "one - which is why turning it off protects it rather than hiding",
                "it.",
            )
        )
        entries.append(
            _entry(
                "COS_WEB_ADMIN_USERS",
                f'"{setup.admin_users}"',
                "Who may use it, by the username authentik signs them in as. An",
                "empty list is refused at startup rather than read as 'anybody the",
                "provider authenticated'.",
            )
        )
        entries.append(
            _entry(
                "COS_WEB_ADMIN_PROXY_SECRET",
                f'"{_env_reference("admin_proxy_secret")}"',
                "What makes the outpost's identity headers believable. Without it",
                "they are headers anybody who can reach this container could send,",
                "so a request that does not carry it is refused.",
            )
        )
        if _uses_authentik(setup):
            entries.append(
                _entry(
                    "COS_WEB_ADMIN_SIGN_OUT_URL",
                    f'"{AUTHENTIK_SIGN_OUT_PATH}"',
                    "Where the area's sign-out link goes. The service has no session",
                    "of its own to end - the sign-in belongs to the outpost - and the",
                    "same reverse proxy that routes /outpost.goauthentik.io/ for the",
                    "forward auth serves this path. Without the bundled Authentik,",
                    "name your own provider's exit here or leave it unset and the",
                    "band offers no way out.",
                )
            )
    if _installs_updates(setup):
        entries.append(
            _entry(
                "COS_WEB_UPDATE_CHECK",
                '"true"',
                "The operator's area says when a newer release is on GitHub: one",
                "cached lookup every six hours, for the area only.",
            )
        )
        entries.append(
            _entry(
                "COS_WEB_ADMIN_UPDATE_DIR",
                f'"{UPDATE_DIRECTORY}"',
                "And installs it from a button: the release's web bundle, verified",
                "against its GitHub build attestation, unpacked on the tmpfs below",
                "and run in place of the image's code - a short downtime, lasting",
                "until the containers restart (ADR 0070). Remove this line to only",
                "be told.",
            )
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
        *_abuse_environment(setup, web=False),
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
    if _installs_updates(setup):
        entries.append(
            _entry(
                "COS_WEB_ADMIN_UPDATE_DIR",
                f'"{UPDATE_DIRECTORY}"',
                "Follows a release the operator's area installed, verifying it",
                "for itself, within a minute.",
            )
        )
    return entries


def _abuse_environment(setup: Setup, *, web: bool) -> list[EnvEntry]:
    """
    The abuse guards, for one container.

    The worker learns whether a host was OpenCloud and imposes the block, so
    it reads the block's own numbers; only the web service reads the rest,
    because only it sees the client and the submitted name.
    """
    entries = [
        _entry(
            "COS_WEB_PROBE_LIMIT",
            f'"{setup.probe_limit}"',
            "Scans from one client network that find no OpenCloud - or targets",
            "the guard refused - inside the window before that network is",
            "blocked. The same host again counts again. Both containers read",
            "these; 0 turns the block off.",
        ),
        _entry("COS_WEB_PROBE_WINDOW", f'"{setup.probe_window}"'),
        _entry(
            "COS_WEB_PROBE_BLOCK",
            f'"{setup.probe_block}"',
            "The first block, and the longest a block repeated inside the",
            "remembered window may grow to, six times longer each time.",
        ),
        _entry("COS_WEB_PROBE_BLOCK_MAX", f'"{setup.probe_block_max}"'),
        _entry("COS_WEB_PROBE_REPEAT_WINDOW", f'"{setup.probe_repeat_window}"'),
    ]
    if not web:
        return entries
    entries.extend(
        [
            _entry(
                "COS_WEB_PROBE_IPV4_PREFIX",
                f'"{setup.probe_ipv4_prefix}"',
                "How much of an address counts as one client: the IPv4 network",
                "the block covers, and the IPv6 network every limit covers.",
            ),
            _entry("COS_WEB_CLIENT_IPV6_PREFIX", f'"{setup.client_ipv6_prefix}"'),
            _entry(
                "COS_WEB_DAILY_SCAN_LIMIT",
                f'"{setup.daily_scan_limit}"',
                "Scans one client may submit per day, on top of the per-minute",
                "limit. 0 turns it off.",
            ),
            _entry(
                "COS_WEB_DNS_CONSISTENCY_CHECK",
                f'"{_bool(setup.dns_consistency_check)}"',
                "Refuse a name whose two lookups share no address.",
            ),
            _entry(
                "COS_WEB_REQUIRE_APPROVAL",
                f'"{_bool(setup.require_approval)}"',
                "Scan approved instances only: listed ones, or ones whose DNS",
                "publishes a TXT record approving this service.",
            ),
        ]
    )
    if setup.require_approval:
        entries.append(_entry("COS_WEB_APPROVED_TARGETS", f'"{setup.approved_targets}"'))
        entries.append(_entry("COS_WEB_APPROVAL_DNS", f'"{_bool(setup.approval_dns)}"'))
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


#: The tmpfs a release installed from the operator's area is unpacked onto.
UPDATE_DIRECTORY = "/var/lib/opencloud-scan/update"


def _installs_updates(setup: Setup) -> bool:
    """Whether the operator's area can install a newer release (ADR 0070)."""
    return setup.admin_enabled


def _update_tmpfs(setup: Setup) -> str:
    """The writable place an installed release lives until the next restart."""
    if not _installs_updates(setup):
        return ""
    return f"      - {UPDATE_DIRECTORY}:size=64m,uid=10001,gid=10001,mode=0700\n"


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
            "# Nobody is created in Authentik's interface. Every sign-in requires a\n"
            "# second factor, and each name in COS_AUTHENTIK_ACCOUNTS creates its own\n"
            "# account - password and authenticator - at the enrollment link the\n"
            "# wizard printed, which carries AUTHENTIK_ENROLLMENT_TOKEN from .env:\n"
            "#\n"
            f"#   {setup.authentik_url.rstrip('/')}{AUTHENTIK_ENROLLMENT_PATH}?itoken=<token>\n"
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
{_update_tmpfs(setup)}    security_opt:
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
{_update_tmpfs(setup)}    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
{_update_label(setup)}
  redis:
    image: {REDIS_IMAGE}
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
        env_path, PRIVATE_FILE_FLAGS, stat.S_IRUSR | stat.S_IWUSR
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), stat.S_IRUSR | stat.S_IWUSR)
        handle.write(render_env_file(setup))
    os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
    written.append(f"{env_path} (owner-readable only)")

    # Beside the compose file rather than in /etc/logrotate.d: installing it
    # needs root, and a wizard that writes outside the directory it was given
    # is one an operator cannot run to see what it would do.
    if _uses_logrotate(setup):
        policy = compose_path.parent / logrotate_filename(setup)
        policy.write_text(
            render_logrotate_file(setup, compose_path.parent), encoding="utf-8"
        )
        os.chmod(policy, 0o644)
        written.append(f"{policy} (install it into /etc/logrotate.d)")

    # The wizard's own notebook, so that the next run against this deployment
    # is an edit rather than a re-description. Not announced with the rest:
    # nobody has to do anything with it, and a list of files to act on is
    # worth less for every line on it that needs no action.
    answers = compose_path.parent / answers_filename(compose_path.name)
    answers.write_text(render_answers_file(setup), encoding="utf-8")
    os.chmod(answers, 0o644)

    written.extend(_write_proxy_files(setup, compose_path.parent))
    written.extend(_copy_blueprints(setup, compose_path.parent))
    return written


def _copy_blueprints(setup: Setup, output_dir: Path) -> list[str]:
    """Put the provisioning blueprints next to the compose file that mounts them.

    The generated stack mounts a relative path, so they have to travel with it
    - a deployment directory somewhere else on the host cannot reach back into
    a checkout, and a stack whose blueprint is missing starts and then refuses
    every token with nothing in the log to say why.

    The OAuth2 provider that issues the tokens ``/mcp`` verifies; the second
    factor every sign-in requires; the enrollment flow that lets a listed
    person create their own account; and, only where there is an area to
    guard, the proxy provider that signs an operator in before ``/admin``.

    The content comes from ``EMBEDDED_BLUEPRINTS``, never from a checkout
    beside the script: the wizard is documented as one file to ``curl``, and
    reading them from disk used to leave that operator an empty directory -
    Authentik with no provider, and a 500 for every request to ``/admin``.
    """
    if not _uses_authentik(setup):
        return []
    wanted = [BLUEPRINT_RELATIVE, MFA_BLUEPRINT_RELATIVE, ENROLLMENT_BLUEPRINT_RELATIVE]
    if _guards_the_admin_area(setup):
        wanted.append(ADMIN_BLUEPRINT_RELATIVE)

    copied: list[str] = []
    for relative in wanted:
        destination = output_dir / relative
        # Generating into the checkout itself: the file there is the source
        # the embedded copy was made from, and may be mid-edit.
        if destination.resolve() == (REPO_ROOT / relative).resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(EMBEDDED_BLUEPRINTS[relative.name], encoding="utf-8")
        os.chmod(destination, 0o644)
        copied.append(str(destination))
    return copied


# --- what to do once the area is on -----------------------------------------
def _step(index: int, text: str, *commands: str) -> list[str]:
    """One numbered step, wrapped, with its commands under it."""
    wrapped = _wrap(text, 64)
    lines = [f"    {index}. {wrapped[0]}"]
    lines += [f"       {line}" for line in wrapped[1:]]
    lines += [f"         {command}" for command in commands]
    return lines


def enrollment_instructions(
    setup: Setup, env_file: str = ".env", style: Style | None = None
) -> list[str]:
    """How the people named get in: one link, and nothing in the admin UI.

    The link carries the invitation token, which is a credential: it is
    neither written into the compose file nor printed here, where it would
    outlive the run in scrollback and CI logs. What is printed is the command
    that assembles the link from the secrets file.
    """
    if not _uses_authentik(setup):
        return []
    # Set apart from the rest of the closing output: it is the one thing on
    # the screen that has to reach somebody else, and between the proxy
    # commands and the /admin steps it used to be scrolled past.
    style = style or Style(enabled=False)
    closing = style.accent("  " + _HEAVY * (frame_width() - 2))
    lines = [
        "",
        rule("ENROLLMENT LINK", style),
        f"  {style.bold('How everybody who signs in gets an account')}",
        "",
    ]
    names = [name.strip() for name in setup.authentik_accounts.split(";") if name.strip()]
    if names:
        variable = ENROLLMENT_LINK_VARIABLE
        base = f"{setup.authentik_url.rstrip('/')}{AUTHENTIK_ENROLLMENT_PATH}"
        lines.append(f"  Build it from {env_file} - the token is not printed here:")
        lines.append("")
        lines.append(
            "    "
            + style.accent(f"echo \"{base}?itoken=$(sed -n 's/^{variable}=//p' {env_file})\"")
        )
        lines.append("")
        lines.append("  It looks like this, with the token in place of the placeholder:")
        lines.append("")
        lines.append(f"    {base}?itoken=<{variable}>")
        lines.append("")
        if len(names) == 1:
            recipients = f"Send it to {names[0]}. It asks for that username"
            claimed = "The name can be claimed once, and no other name at all."
            until = "until it has been used."
        else:
            recipients = (
                f"Send it to {', '.join(names[:-1])} and {names[-1]}. It asks "
                "for one of those usernames"
            )
            claimed = "Each name can be claimed once, and no other name at all."
            until = "until everybody has used it."
        for text in _wrap(
            f"{recipients}, an email address and a password, and then for a "
            "second factor - an authenticator app or a security key - which "
            f"every sign-in requires from then on. {claimed} Treat the link "
            f"like a password {until}",
            64,
        ):
            lines.append(f"  {text}")
    else:
        for text in _wrap(
            "Nobody is listed yet, so the enrollment link admits nobody. Run "
            "the wizard again and name who signs in.",
            64,
        ):
            lines.append(f"  {text}")
    lines.append(closing)
    lines.append("")
    for text in _wrap(
        f"Authentik's own administrator is {AUTHENTIK_BOOTSTRAP_USER}; its password "
        f"is {RECOVERY_ADMIN_VARIABLE} in .env. "
        "Keep it for recovery - it is how a lost second factor is removed.",
        64,
    ):
        lines.append(f"  {text}")
    return lines


def admin_walkthrough(setup: Setup) -> list[str]:
    """The steps between a stack that is running and an area that opens.

    Printed rather than performed: every one of them happens in a browser, in
    a directory this wizard does not administer, or as root.

    It is worth spelling out because ``/admin`` is the one surface here that
    *refuses* rather than asking. There is no login page to arrive at and no
    password prompt to get wrong - a request that is missing any part of the
    arrangement gets the same 404 as any unknown path, which is exactly the
    right answer to give a stranger and a miserable one to debug against. So
    the last section says what that 404 can mean, in the order it is worth
    checking.
    """
    if not setup.admin_enabled:
        return []

    address = setup.public_base_url.rstrip("/") + ADMIN_PATH
    lines = [
        "",
        f"  Opening the operator's area at {ADMIN_PATH}:",
        "",
    ]
    index = 1
    if _uses_authentik(setup):
        lines += _step(
            index,
            "Create your account at the enrollment link printed above: your "
            "username from the guest list, a password and a second factor. "
            f"It joins {AUTHENTIK_OPERATOR_GROUP}, the only group the area's "
            "application is bound to, on the way - there is nothing to click "
            "in Authentik.",
        )
        index += 1
    else:
        lines += _step(
            index,
            "Put a sign-in in front of the area. This service authenticates "
            "nobody - it has no login page, no session and no password to "
            "check - so something in front has to establish who is asking "
            "and pass that on as "
            f"{ADMIN_IDENTITY_HEADERS[0]}.",
        )
        index += 1
        lines += _step(
            index,
            "Have that same thing add the shared secret as "
            f"{ADMIN_PROXY_HEADER}, with the value of {ADMIN_PROXY_VARIABLE} "
            "from the generated .env. It is the only reason the identity "
            "header above is worth believing, and the service refuses "
            "anything arriving without it.",
        )
        index += 1

    if _proxy_forwards_auth(setup):
        lines += _step(
            index,
            f"Install the generated {setup.reverse_proxy} configuration - the "
            "commands are in the list above. It is the piece that shows each "
            "request to the outpost first and adds the shared secret to what "
            "the outpost accepts; until it is in place the area answers 404 "
            "to everybody, including you.",
        )
        index += 1
        if setup.reverse_proxy in {"caddy", "traefik"}:
            # These two read the value at run time instead of carrying it, so
            # an installed config alone still sends an empty header.
            lines += _step(
                index,
                f"Give {setup.reverse_proxy} the shared secret in its own "
                f"environment: it reads {ADMIN_PROXY_VARIABLE} from there rather "
                "than holding it in a file you might commit. An "
                "EnvironmentFile pointing at the generated .env is the usual "
                "way, and without it the header goes out empty and the area "
                "stays shut.",
                f"sudo systemctl edit {setup.reverse_proxy}",
            )
            index += 1
        lines += _step(
            index,
            f"Make sure a browser can reach Authentik itself at "
            f"{setup.authentik_url}. The sign-in redirect goes there rather "
            "than through the outpost, so an address only this host resolves "
            "signs nobody in from anywhere else.",
        )
        index += 1
    elif _writes_proxy(setup):
        lines += _step(
            index,
            f"Add that to the generated {setup.reverse_proxy} configuration "
            f"yourself. It routes everything except {ADMIN_PATH}, and the "
            "comment where the area would have been says what has to go "
            "there.",
        )
        index += 1

    lines += _step(
        index,
        "Check the second guest list. COS_WEB_ADMIN_USERS in the generated "
        f"compose file names: {setup.admin_users or '(nobody yet)'}. Signing "
        "in proves the directory knows you; this decides whether this "
        "deployment calls you an operator, and an empty list is refused at "
        "startup rather than read as everybody.",
    )
    index += 1
    lines += _step(index, "Open the area.", f"open {address}")

    provider = "Authentik's" if _uses_authentik(setup) else "your provider's"
    lines += [
        "",
        "  If it does not open, the 404 is telling you which step is missing:",
        "",
        f"    - no sign-in at all, just 404   the {ADMIN_PROXY_HEADER} header",
        "                                    never arrived - the proxy in",
        "                                    front is not adding it",
        "    - signed in, then 404           that account is not in",
        "                                    COS_WEB_ADMIN_USERS",
        f"    - the sign-in loops             {provider} public address is",
        "                                    not the one the browser used",
    ]
    if not _uses_authentik(setup):
        # The bundled stack has this set already; nobody else's exit is
        # guessable, and an area with no way out is what unset leaves.
        lines += [
            "",
            "  The area's Sign out link appears only once",
            "  COS_WEB_ADMIN_SIGN_OUT_URL names where your provider ends a",
            "  session. Unset, the band names the operator and offers no way",
            "  out, which beats a control that appears to sign somebody out",
            "  and does not.",
        ]
    return lines


@dataclass
class SummaryRow:
    """One setting as the summary shows it."""

    label: str
    value: str
    key: str = ""
    """The name to type to change it; empty for a derived value."""
    changed: bool = False
    secret: bool = False


# How wide the label column is. Long prompts are cut rather than wrapped: the
# setting's name at the end of the line is what identifies it, and a summary
# that takes two lines per setting is one nobody reads to the end.
_LABEL_WIDTH = 36


def _summary_value(setup: Setup, name: str) -> tuple[str, bool]:
    value = getattr(setup, name)
    if name in SECRET_VARIABLES and value:
        return "set (written to .env)", True
    return _format_default(value), False


def _label(question: Question) -> str:
    label = question.prompt.rstrip("?").strip()
    if len(label) > _LABEL_WIDTH:
        label = label[: _LABEL_WIDTH - 3].rstrip() + "..."
    return label


def summary_rows(setup: Setup) -> list[tuple[str, list[SummaryRow]]]:
    """The answers grouped under the headings they were asked under.

    Each asked setting carries its question's wording, which is what an
    operator recognises, and its name, which is what they type to change it.
    A setting that differs from the default is marked: those are the
    decisions this deployment made, and the ones worth a second look.
    """
    # The default as this host would have it: detected and derived the same
    # way, so the Docker mode found on the socket or the public URL that
    # follows the port is not marked as somebody's decision.
    defaults = Setup(
        docker_mode=setup.docker_mode,
        watchtower_socket=setup.watchtower_socket,
        build_context=setup.build_context,
    )
    _finalise(defaults)
    groups: list[tuple[str, list[SummaryRow]]] = []
    asked: set[str] = set()
    for section in build_sections(setup):
        rows = []
        for question in section.questions:
            if not _relevant(question.key, setup):
                continue
            value, secret = _summary_value(setup, question.key)
            changed = not secret and getattr(setup, question.key) != getattr(
                defaults, question.key
            )
            rows.append(SummaryRow(_label(question), value, question.key, changed, secret))
        if rows:
            groups.append((section.title, rows))
        asked.update(question.key for question in section.questions)

    # What nobody was asked for: the credentials and the URLs the answers
    # imply. They still belong in the summary - they are what the deployment
    # will hold - but not among the decisions somebody made.
    derived = []
    for item in fields(setup):
        if (
            item.name in asked
            or not _relevant(item.name, setup)
            or getattr(setup, item.name) in ("", False)
        ):
            continue
        value, secret = _summary_value(setup, item.name)
        derived.append(SummaryRow(item.name, value, secret=secret))
    if derived:
        groups.append(("Derived, and generated for you", derived))
    return groups


def _row_body(row: SummaryRow, style: Style, label_width: int = 0) -> str:
    """One summary row without its indent, so a card can put an edge on it."""
    label_width = label_width or _LABEL_WIDTH
    marker = style.warn("*") if row.changed else " "
    if row.secret:
        value = style.good(row.value)
    elif row.value in {"no", "unset", "none"}:
        value = style.dim(row.value)
    else:
        value = style.bold(row.value)
    handle = f"  {style.dim(f'[{row.key}]')}" if row.key else ""
    label = row.label
    if len(label) > label_width:
        label = label[: label_width - 3].rstrip() + "..."
    padding = " " * max(1, label_width + 1 - len(label))
    return f"{marker} {label}{padding}{value}{handle}"


def _render_row(row: SummaryRow, style: Style) -> str:
    return f"  {_row_body(row, style)}"


def summarise(setup: Setup, style: Style | None = None) -> list[str]:
    """The answers, for the confirmation before anything is written.

    Grouped under the headings they were asked under. A flat list of sixty
    field names is a thing an operator scrolls past rather than reads, and
    this is the last chance anybody has to notice that the audit trail is
    going somewhere they did not mean. Plain text unless a style is given.
    """
    style = style or Style(enabled=False)
    lines: list[str] = []
    for title, rows in summary_rows(setup):
        lines.append(f"  {style.accent(style.bold(title))}")
        lines.extend(_render_row(row, style) for row in rows)
    return lines


def summary_cards(setup: Setup, style: Style, width: int = 0) -> list[str] | None:
    """The summary as one bordered card per group, ratatui's Block.

    The flat list `summarise` returns is what a pipe and every test reads, and
    it stays exactly that. On a terminal the same rows get an edge around each
    heading, because the thing an operator is hunting on this screen is one
    setting inside one group and a border is what makes a group findable.

    `None` where the rows will not fit between two borders - a narrow pane
    gets the plain list rather than a card whose corners have wrapped.
    """
    grouped = summary_rows(setup)
    available = (width or _columns()) - 8
    headings = [len(title) for title, _ in grouped]
    # The label column is what makes a row too wide, so narrow it until the
    # rows fit between two borders rather than giving up on the card at the
    # first terminal that is not generous. Below _CARD_LABEL_FLOOR the labels
    # are stubs and the plain list reads better than a cramped box.
    for label_width in range(_LABEL_WIDTH, _CARD_LABEL_FLOOR - 1, -1):
        groups = [
            (title, [_row_body(row, style, label_width) for row in rows])
            for title, rows in grouped
        ]
        needed = max([_visible(body) for _, bodies in groups for body in bodies] + headings)
        if needed <= available:
            break
    else:
        return None
    lines: list[str] = []
    for title, bodies in groups:
        head = f"{_LIGHT} {title} "
        lines.append(
            style.accent(f"  {_TOP_LEFT}{head}{_LIGHT * (needed + 2 - len(head))}{_TOP_RIGHT}")
        )
        for body in bodies:
            padding = " " * max(0, needed - _visible(body))
            lines.append(f"  {style.accent(_SIDE)} {body}{padding} {style.accent(_SIDE)}")
        lines.append(style.accent(f"  {_BOTTOM_LEFT}{_LIGHT * (needed + 2)}{_BOTTOM_RIGHT}"))
    return lines


def _editable(setup: Setup) -> dict[str, Question]:
    """The questions the summary is showing, by the name it shows them under."""
    return {
        question.key: question
        for section in build_sections(setup)
        for question in section.questions
        if _relevant(question.key, setup)
    }


def _as_key(typed: str) -> str:
    """What somebody typed at the summary, as the name it is listed under."""
    return typed.strip().lower().replace("-", "_").replace(" ", "_")


def _named(questions: dict[str, Question], typed: str) -> Question | None:
    """The setting an operator meant, by name or by an unambiguous start of one."""
    key = _as_key(typed)
    if key in questions:
        return questions[key]
    matches = [name for name in questions if name.startswith(key)]
    return questions[matches[0]] if len(matches) == 1 else None


def review(wizard: Wizard, setup: Setup) -> bool:
    """Show what would be written, and let one answer be changed.

    The summary is where a mistake is noticed, and it used to be a dead end:
    *yes* wrote the wrong thing and *no* threw away forty answers to fix one
    of them. Naming a setting re-asks that question and comes straight back
    here, so the last screen is somewhere you can work rather than a verdict.
    """
    questions = _editable(setup)
    while True:
        style = wizard.style
        wizard.say()
        wizard.rule("Summary")
        total = len(build_sections(setup))
        wizard.say(
            f"  {style.accent('Ready to write')}  {style.dim(line_gauge(total, total))}"
        )
        cards = summary_cards(setup, style) if style.enabled else None
        for line in cards if cards is not None else summarise(setup, style):
            wizard.say(line)
        wizard.say(
            f"  {style.warn('*')} {style.dim('differs from the default; type a [name] to change it')}"
        )

        warnings = check_consistency(setup)
        if warnings:
            wizard.say()
            wizard.say(f"  {style.warn(style.bold('Worth a second look:'))}")
            for warning in warnings:
                for index, line in enumerate(_wrap(warning, 68)):
                    wizard.say(f"    {style.warn('-') if index == 0 else ' '} {line}")

        if wizard.interactive:
            host = check_host(setup)
            if host:
                wizard.say()
                wizard.say(f"  {style.warn(style.bold('On this host:'))}")
                for problem in host:
                    for index, line in enumerate(_wrap(problem, text_width(6))):
                        wizard.say(f"    {style.warn('-') if index == 0 else ' '} {line}")

        errors = check_errors(setup, wizard.base_dir)
        if errors:
            wizard.say()
            wizard.say(f"  {style.bad('Has to change before anything is written:')}")
            for error in errors:
                for index, line in enumerate(_wrap(error, 68)):
                    wizard.say(f"    {style.bad('!') if index == 0 else ' '} {line}")

        if not wizard.interactive:
            # Nothing was printed above, and this is the one thing a run that
            # asks nothing must not keep to itself.
            for error in errors:
                print(error, file=sys.stderr)
            return not errors

        wizard.say()
        answer = wizard._read(
            f"  {style.accent(_POINTER)} Write it all out now? {style.accent('[Y/n]')}, "
            f"or name a setting to change {style.accent('>')} "
        ).strip()
        if not answer or answer.lower() in YES:
            if errors:
                wizard.say("  Not with the problem above: name the setting to change.")
                continue
            return True
        if answer.lower() in NO:
            return False

        question = _named(questions, answer)
        if question is None:
            if any(item.name == _as_key(answer) for item in fields(setup)):
                # It is in the summary, under "Derived": saying "no such
                # thing" at a name somebody is reading off the screen is the
                # kind of answer that makes people distrust the whole screen.
                wizard.say(
                    f"  '{answer}' is derived from the answers above rather "
                    "than asked for."
                )
                wizard.say("  Change what it is derived from and it follows.")
            else:
                wizard.say(f"  Nothing called '{answer}' is in the summary above.")
                wizard.say("  Type a name exactly as it is listed, or enough of one.")
            continue
        before = _sign_in_wanted(setup)
        wizard.ask(question, offer_rest=False)
        if _offer_authentik(setup, before):
            # Said, because nobody was asked: the summary below now carries a
            # provider this question did not mention.
            wizard.say(
                "  Authentik joins the stack as the provider for that sign-in; "
                "name deploy_authentik to change it."
            )
        # An answer changed here can imply the rest all over again: a provider
        # that now needs credentials, a URL that no longer has one.
        _generate_unattended(setup)
        _finalise(setup)
        questions = _editable(setup)


# --- the host this runs on -------------------------------------------------
def _docker_problem() -> str | None:
    """Why ``docker compose`` will not run here, or ``None`` when it will."""
    docker = shutil.which("docker")
    if docker is None:
        return (
            "Docker is not installed, or not on the PATH of the user running "
            "this wizard. The files are written anyway; `docker compose up` "
            "needs it."
        )
    try:
        result = subprocess.run(  # nosec B603 - fixed arguments, no shell
            [docker, "compose", "version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "`docker compose version` did not answer, so Compose could not be checked."
    if result.returncode != 0:
        return (
            "Docker is here but the Compose plugin is not: `docker compose "
            "version` failed. The generated file needs Compose v2 - the "
            "docker-compose-plugin package on most distributions."
        )
    return None


def _port_problem(setup: Setup) -> str | None:
    """Whether the host port is already taken, or not an address of this host."""
    address = setup.bind_address.strip("[]")
    # The probe never binds every interface itself: a port published on all of
    # them is taken on loopback too, so loopback stands in for the wildcard.
    if address in {"", "0.0.0.0", "*"}:  # nosec B104 - compared, never bound
        address = "127.0.0.1"
    elif address == "::":
        address = "::1"
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.bind((address, setup.host_port))
    except PermissionError:
        return None  # a privileged port: Docker binds it, this user cannot
    except OSError as error:
        if error.errno in {98, 48, 10048}:  # EADDRINUSE on Linux, macOS, Windows
            return (
                f"Port {setup.host_port} on {setup.bind_address} is already in use - "
                "by this stack, if it is running, and otherwise `docker compose up` "
                "will fail to publish it. Choose another with host_port."
            )
        return (
            f"{setup.bind_address} is not an address of this host, so the port "
            "cannot be published on it. Change bind_address."
        )
    finally:
        probe.close()
    return None


def _certificate_problems(setup: Setup) -> list[str]:
    """Certificates the generated proxy configuration names that are not there.

    Only a file that is definitely missing is reported. One this user may not
    look at - /etc/letsencrypt/live is root's - is the normal case and says
    nothing either way.
    """
    wanted = [
        key
        for key in (
            "reverse_proxy_certificate",
            "reverse_proxy_private_key",
            "reverse_proxy_authentik_certificate",
            "reverse_proxy_authentik_private_key",
        )
        if _relevant(key, setup) and getattr(setup, key)
    ]
    problems = []
    for key in wanted:
        path = getattr(setup, key)
        try:
            Path(path).stat()
        except FileNotFoundError:
            problems.append(
                f"{path} does not exist yet ({key}). The proxy refuses to start "
                "without it - fine if the certificate is issued before then."
            )
        except OSError:
            continue
    return problems


def check_host(setup: Setup) -> list[str]:
    """What this host says about the answers: Docker, the port, the certificates.

    Kept apart from :func:`check_consistency`, which judges the answers
    alone and gives the same verdict on every machine. These depend on where
    the wizard happens to run - which is usually, but not always, where the
    stack will.
    """
    problems = [_docker_problem(), _port_problem(setup)]
    return [problem for problem in problems if problem] + _certificate_problems(setup)


# --- before and after writing -----------------------------------------------
def _plain_files(setup: Setup, compose_path: Path) -> list[tuple[Path, str]]:
    """The generated files that hold no credential, with what they would contain."""
    files = [(compose_path, render_compose_file(setup, compose_path.name))]
    if _uses_logrotate(setup):
        files.append(
            (
                compose_path.parent / logrotate_filename(setup),
                render_logrotate_file(setup, compose_path.parent),
            )
        )
    if _writes_proxy(setup):
        files.append((compose_path.parent / proxy_filename(setup), render_proxy_file(setup)))
    return files


# A diff longer than this is a rewrite, and the summary already said what
# changed; the rest is elided rather than scrolled past.
_DIFF_LINES = 80


def render_diffs(setup: Setup, compose_path: Path, style: Style | None = None) -> list[str]:
    """What writing would change in the files already there.

    The credentials are never diffed: `.env` and the proxy's secret include
    would put the old value and the new one side by side on the screen.
    """
    style = style or Style(enabled=False)
    lines: list[str] = []
    for path, content in _plain_files(setup, compose_path):
        try:
            before = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if before == content:
            lines.append(f"  {style.dim(f'{path.name}: unchanged')}")
            continue
        diff = list(
            difflib.unified_diff(
                before.splitlines(),
                content.splitlines(),
                fromfile=f"{path.name} (now)",
                tofile=f"{path.name} (after writing)",
                lineterm="",
            )
        )
        for line in diff[:_DIFF_LINES]:
            if line.startswith(("+++", "---")):
                lines.append(f"  {style.bold(line)}")
            elif line.startswith("+"):
                lines.append(f"  {style.good(line)}")
            elif line.startswith("-"):
                lines.append(f"  {style.paint(line, 'red')}")
            elif line.startswith("@@"):
                lines.append(f"  {style.accent(line)}")
            else:
                lines.append(f"  {line}")
        if len(diff) > _DIFF_LINES:
            lines.append(f"  {style.dim(f'... {len(diff) - _DIFF_LINES} more lines')}")
    return lines


def backup_existing(
    setup: Setup, compose_path: Path, env_path: Path, stamp: str | None = None
) -> list[str]:
    """Copy every file about to be replaced to ``<name>.<time>.bak`` beside it.

    Timestamped rather than a single ``.bak``, so two runs in a row do not
    replace the only copy of what was there before the first. A backup of a
    credential file is created owner-readable only, exactly as the original.
    """
    # UTC, and said so in the name: a backup read on another host, or after a
    # clock change, should not be an hour out of order. timezone.utc, not
    # datetime.UTC: the wizard runs on the Docker host's own python3, which
    # can be older than the plugin's floor (Ubuntu 22.04 answers 3.10).
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017
    directory = compose_path.parent
    candidates = [(path, False) for path, _ in _plain_files(setup, compose_path)]
    candidates.append((env_path, True))
    candidates.append((directory / answers_filename(compose_path.name), False))
    if _proxy_forwards_auth(setup) and setup.reverse_proxy == "nginx":
        candidates.append((directory / admin_secret_filename(setup), True))

    saved: list[str] = []
    for path, secret in candidates:
        if not path.is_file():
            continue
        backup = path.with_name(f"{path.name}.{stamp}.bak")
        if secret:
            descriptor = os.open(
                backup, PRIVATE_FILE_FLAGS, stat.S_IRUSR | stat.S_IWUSR
            )
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), stat.S_IRUSR | stat.S_IWUSR)
                handle.write(path.read_bytes())
            os.chmod(backup, stat.S_IRUSR | stat.S_IWUSR)
        else:
            shutil.copy2(path, backup)
        saved.append(str(backup))
    return saved


def _waits_for_steps(setup: Setup) -> bool:
    """Whether something has to happen as root before the stack can start."""
    return (
        (_keeps_audit_file(setup) and _binds_a_directory(setup.audit_storage, setup.audit_log_path))
        or _binds_a_directory(setup.redis_persistence, setup.redis_data_path)
    )


def _health_url(setup: Setup) -> str:
    address = setup.bind_address
    if address in {"0.0.0.0", "", "::", "[::]"}:  # nosec B104 - a URL to ask, not a bind
        address = "127.0.0.1"
    return f"http://{address}:{setup.host_port}/healthz"


def _wait_until_healthy(
    url: str,
    timeout: float = 90,
    interval: float = 3,
    on_wait: Callable[[], None] | None = None,
) -> bool:
    """Poll until the stack answers, or the deadline passes.

    `on_wait` is called repeatedly between polls rather than once per poll:
    the gap is three seconds and a spinner that moved every three seconds
    would read as a hung one. The poll itself keeps its own pace - the
    callback only decides how often the waiting is redrawn.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310 - http to this host
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        if on_wait is None:
            time.sleep(interval)
            continue
        until = time.monotonic() + interval
        while time.monotonic() < until:
            on_wait()
            time.sleep(max(0.0, min(_THROBBER_SECONDS, until - time.monotonic())))
    return False


def offer_to_start(wizard: Wizard, setup: Setup, compose_path: Path) -> None:
    """Check the written stack with Compose, and start it if the operator says so.

    Asked, never assumed: starting containers and binding a port is the first
    thing this wizard does outside the directory it was given. Nothing is
    offered where Docker is missing, and `up` is not offered where a
    directory has to be handed to the container's user first - a stack
    started before that is one that fails on its first write.
    """
    if not wizard.interactive:
        return
    docker = shutil.which("docker")
    if docker is None:
        return
    style = wizard.style
    directory = compose_path.parent
    command = [docker, "compose", "-f", compose_path.name]
    wizard.say()
    if not wizard.confirm("Check the written files with `docker compose config` now?"):
        return
    result = subprocess.run(  # nosec B603 - fixed arguments, no shell
        [*command, "config", "--quiet"],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        wizard.say(f"  {style.bad('!')} Compose rejected the file:")
        for line in (result.stderr or result.stdout).strip().splitlines()[:20]:
            wizard.say(f"      {line}")
        return
    wizard.say(f"  {style.good('+')} Compose accepts the file.")

    if _waits_for_steps(setup):
        wizard.say("  Start it once the ownership commands under Next have run.")
        return
    if _writes_proxy(setup):
        wizard.say(
            f"  {style.dim('The proxy configuration still has to be installed - see Next.')}"
        )
    build = ["--build"] if setup.image_source == "build" else []
    if not wizard.confirm("Start the stack now with `docker compose up -d`?", default=False):
        return
    started = subprocess.run(  # nosec B603 - fixed arguments, no shell
        [*command, "up", "-d", *build], cwd=directory, check=False
    )
    if started.returncode != 0:
        wizard.say(f"  {style.bad('!')} `docker compose up -d` failed; its output is above.")
        return
    url = _health_url(setup)
    # The one wait in the run with nothing to show for it: a first start
    # pulls images and can sit here for a minute and a half. A spinner that
    # turns into a tick is the difference between waiting and wondering.
    throbber = Throbber(f"Waiting for {url} to answer ", style, say=wizard.say)
    healthy = _wait_until_healthy(url, on_wait=throbber.tick)
    if healthy:
        throbber.finish(True, "The service is up.")
    else:
        throbber.finish(False, "No answer yet.")
        for line in _wrap(
            "`docker compose logs web_app` says why - a first start that "
            "pulls images can take a while.",
            text_width(4),
        ):
            wizard.say(f"    {style.dim(line)}")


# --- the command ------------------------------------------------------------
def _refuse_shipped(path: Path) -> str | None:
    """Whether the target is one of the project's own compose files."""
    if path.parent.resolve() == SCRIPT_DIR and path.name in SHIPPED_COMPOSE_FILES:
        return (
            f"{path.name} in {SCRIPT_DIR} ships with the project, and the next "
            "update would overwrite your deployment. Choose another name with "
            "--compose-file, or another directory with --output-dir - or pass "
            "--force to replace it in place anyway."
        )
    return None


def _shipped_overwrite_note(path: Path) -> str:
    """What replacing a shipped compose file in place costs, said once.

    Printed to stderr rather than through the wizard, so an unattended run
    that asked for it hears it too: the checkout now carries a modified
    tracked file, and it is the operator's to keep out of the next pull.
    """
    return (
        f"Replacing {path.name} in {SCRIPT_DIR}, which ships with the project, "
        "because --force was given. The checkout now has a modified tracked "
        "file: a `git pull` that changes it stops with a conflict rather than "
        "taking your deployment with it, `git stash` carries it across one, and "
        f"`git checkout -- docker/{path.name}` puts the shipped file back."
    )


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
        "--version",
        action="version",
        version=version_line(),
        help="Print the release this wizard came from, and exit.",
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
        default=None,
        help=(
            "Starting answers. 'public' - the default - is a service open to "
            "anybody that refuses private targets; 'private' scans its own "
            "network, stays out of search engines and keeps an audit log. "
            "Naming one overrides what a previous run in this directory "
            "answered."
        ),
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Ask nothing and take every default, generating the credentials.",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default=None,
        help=(
            "How much to ask, instead of asking that first. 'quick' asks only "
            "what a deployment cannot be right without; 'private' asks the same "
            "starting from the private preset; 'full' asks everything."
        ),
    )
    parser.add_argument(
        "--answers",
        metavar="FILE",
        default=None,
        help=(
            "Start from the answers in this JSON file - one written by "
            "--print-answers, or the .<compose-file>.answers.json of another "
            "deployment. Read as untrusted: unknown names and values of the "
            "wrong type are ignored, and it never holds a credential."
        ),
    )
    parser.add_argument(
        "--print-answers",
        action="store_true",
        help=(
            "Print the answers this run starts from as JSON, and exit without "
            "asking or writing anything. No credentials are included."
        ),
    )
    parser.add_argument(
        "--image-source",
        choices=("dockerhub", "build"),
        default=None,
        help=(
            "'dockerhub' - the default - pulls the published image; 'build' "
            "builds it from this checkout, for running the code in front of you."
        ),
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
        help=(
            "Overwrite existing files without asking - including a compose "
            "file that ships in docker/, which is otherwise refused."
        ),
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

    proxy = parser.add_argument_group(
        "reverse proxy",
        "The proxy in front, which is what terminates TLS, overwrites "
        "X-Forwarded-For so the rate limit counts clients rather than itself, "
        "and leaves the /mcp event stream unbuffered. Name one and a working "
        "configuration file is written beside the compose file, including the "
        "forward auth in front of /admin where the stack can provide it, and a "
        "site for Authentik's public address when --with-authentik adds it.",
    )
    proxy.add_argument(
        "--reverse-proxy",
        choices=PROXY_CHOICES,
        default=None,
        help="Write a configuration for this proxy. Default: none.",
    )
    proxy.add_argument(
        "--proxy-hostname",
        default=None,
        help=(
            "The name it answers to. Taken from the public base URL when it "
            "is not given."
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
        ("image_source", "image_source"),
        ("reverse_proxy", "reverse_proxy"),
        ("proxy_hostname", "reverse_proxy_hostname"),
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


def _apply_preset(setup: Setup, preset: str | None) -> None:
    """The starting answers a named preset decides.

    Symmetric, and that is the point: naming ``public`` puts the keys the
    private preset moves back where they started, so a preset given on this
    command line overrides what a previous run in this directory remembered.
    Naming none changes nothing, which is what leaves those answers in place.
    """
    if preset is None:
        return
    defaults = Setup()
    for key, private in PRIVATE_PRESET.items():
        setattr(setup, key, private if preset == "private" else getattr(defaults, key))


def _generate_unattended(setup: Setup) -> None:
    """Credentials for a run that asks nothing.

    An unattended install still gets an erasure credential and a signing key,
    because the alternative is a deployment where nobody can ask for a
    deletion until somebody notices.
    """
    if setup.admin_enabled:
        setup.admin_proxy_secret = setup.admin_proxy_secret or secrets.token_hex(32)
    setup.purge_token = setup.purge_token or secrets.token_hex(32)
    setup.redis_password = setup.redis_password or secrets.token_urlsafe(32)
    setup.purge_signing_key = setup.purge_signing_key or secrets.token_hex(32)
    setup.export_signing_key = setup.export_signing_key or secrets.token_hex(32)
    if setup.audit_log and not setup.audit_salt:
        setup.audit_salt = secrets.token_hex(16)
    if setup.encrypt_results and not setup.encryption_key:
        setup.encryption_key = secrets.token_hex(32)


def answers_filename(compose_name: str) -> str:
    """Where the wizard remembers what it was told, for the next run.

    Named after the compose file it belongs to, so two deployments sharing a
    directory keep their own answers, and hidden because nobody should have
    to think about it: it is the wizard's notebook, not part of the
    deployment. Delete it and the next run simply starts from the defaults.
    """
    return f".{compose_name}.answers.json"


def render_answers_file(setup: Setup) -> str:
    """Every answer that is not a credential, as JSON.

    **No secrets.** They live in ``.env``, which is owner-readable and read
    back from separately - copying them here would mean two files to protect
    and one of them a surprise.
    """
    remembered: dict[str, Any] = {
        "_README": (
            "What docker/setup-wizard.py was told, so that running it again "
            "offers these back as the defaults. No credentials: those are in "
            ".env. Safe to delete - the next run then starts from the "
            "defaults."
        )
    }
    remembered.update(
        {
            item.name: getattr(setup, item.name)
            for item in fields(setup)
            if item.name not in SECRET_VARIABLES
        }
    )
    return json.dumps(remembered, indent=2, sort_keys=True) + "\n"


def _read_previous_answers(setup: Setup, path: Path) -> int:
    """The answers the last run wrote, as this run's defaults.

    Everything here is untrusted input - the file is editable and may have
    been written by an older wizard - so a value is taken only when the field
    still exists and the type still matches exactly. ``type(...) is not`` and
    not ``isinstance``: a bool is an int in Python, and ``host_port: true``
    would otherwise become a port.
    """
    if not path.is_file():
        return 0
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A notebook nobody can read is one nobody wrote. Starting from the
        # defaults is a worse run, not a broken one.
        return 0
    if not isinstance(stored, dict):
        return 0

    known = {item.name for item in fields(setup)}
    # The same checks an answer typed at the prompt meets. The values go into
    # the compose file verbatim, so a newline in one - typed by nobody, since
    # a prompt cannot take it - rewrote the YAML around it.
    questions = {
        question.key: question
        for section in build_sections(Setup())
        for question in section.questions
    }
    loaded = 0
    for name, value in stored.items():
        if name not in known or name in SECRET_VARIABLES:
            continue
        if type(value) is not type(getattr(setup, name)):
            continue
        if isinstance(value, str) and not _acceptable_answer(questions.get(name), value):
            continue
        setattr(setup, name, value)
        loaded += 1
    return loaded


def _acceptable_answer(question: Question | None, value: str) -> bool:
    """Whether a remembered string could have been typed as this answer."""
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        return False
    if question is None:
        return True
    if question.choices:
        return value in question.choices
    return question.validate(value) is None


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

    refusal = None if args.print_answers else _refuse_shipped(compose_path)
    if refusal and not args.force:
        print(f"Refusing to write it: {refusal}", file=sys.stderr)
        return 2
    if refusal:
        # Replacing the stack this checkout already runs, deliberately: an
        # operator who started from `docker compose up` in docker/ should not
        # have to move a live deployment to another directory to reconfigure it.
        print(_shipped_overwrite_note(compose_path), file=sys.stderr)

    setup = Setup()
    # Weakest first: what the last run answered, then a preset if one was
    # named now, then the credentials that already exist, then the flags.
    # A decision made on this command line wins over one remembered from the
    # last.
    remembered = _read_previous_answers(
        setup, compose_path.parent / answers_filename(compose_path.name)
    )
    # Another deployment's answers, named on purpose, outrank this directory's
    # notebook - and are refused loudly when there is nothing in them, because
    # a typo in the path would otherwise quietly start from the defaults.
    imported = 0
    if args.answers:
        answers_path = Path(args.answers).expanduser()
        imported = _read_previous_answers(setup, answers_path)
        if not imported:
            print(
                f"Nothing usable in {answers_path}: it is missing, is not a JSON "
                "object, or names no setting this wizard knows.",
                file=sys.stderr,
            )
            return 2
    _apply_preset(setup, args.preset)
    upgraded = follow_authentik_patch(setup) if remembered else None
    try:
        reused = _read_existing_env(setup, env_path)
    except (OSError, UnicodeDecodeError) as error:
        # Not a reason to start over: generating fresh credentials would
        # replace the ones a running deployment depends on.
        print(
            f"{env_path} cannot be read ({error}). Nothing written: fix or move"
            " it, then run the wizard again.",
            file=sys.stderr,
        )
        return 2
    _apply_flags(setup, args)
    setup.build_context = _default_build_context(output_dir)
    setup.watchtower_socket = setup.watchtower_socket or detect_docker_socket()
    setup.docker_mode = setup.docker_mode or detect_docker_mode()

    if args.print_answers:
        print(render_answers_file(setup), end="")
        return 0

    wizard = Wizard(setup, interactive=not args.non_interactive, base_dir=output_dir)
    style = wizard.style
    version = wizard_version()
    wizard.say()
    for line in banner(
        f"check-opencloud-security  -  Docker setup {version}".rstrip(),
        "A container deployment of the web application: the stack, its "
        "secrets, and whatever you ask for in front of it.",
        style,
    ):
        wizard.say(line)
    wizard.say()
    for line in _wrap(
        "This writes a compose file with the whole stack and a .env holding the "
        "credentials it refers to - and, if you ask for them, the blueprints that "
        "provision an identity provider and the configuration for the reverse proxy "
        "in front. Every question explains what it does and shows an example, and "
        "nothing is written until you confirm at the end - where you can still "
        "change any answer."
    ):
        wizard.say(f"  {line}")
    wizard.say()
    wizard.say(f"  {style.dim('Compose file:')} {style.accent(str(compose_path))}")
    wizard.say(f"  {style.dim('Secrets file:')} {style.accent(str(env_path))}")
    wizard.say(f"  {style.dim('Preset:      ')} {style.accent(args.preset or 'public')}")
    wizard.say()
    # The whole walk up front, so the step counter on every heading has
    # something to count against.
    wizard.say(f"  {style.bold('The steps ahead')}")
    titles = [section.title for section in build_sections(setup)]
    for index, title in enumerate(titles, start=1):
        wizard.say(f"    {style.accent(f'{index:>2}')}  {title}")
    wizard.say()
    wizard.say(f"  {style.bold('At any question')}")
    for key, meaning in (
        ("Enter", "takes the value in brackets"),
        ("b", "goes back one question"),
        ("-", "empties a text setting"),
        ("rest", "accepts every remaining default"),
        ("?", "explains the question in full"),
    ):
        wizard.say(f"    {style.accent(f'{key:<6}')} {meaning}")
    wizard.say("  You can change any answer at the summary, by name, before")
    wizard.say("  anything is written.")
    if remembered or reused:
        wizard.say()
        wizard.say("  This deployment is already here, so this is an edit of it:")
        if remembered:
            wizard.say(
                f"  the {remembered} answers the last run wrote are the defaults below,"
            )
        if reused:
            wizard.say(
                f"  and {env_path} keeps the credentials it already holds"
            )
            wizard.say("  rather than generating them anew.")
        if upgraded:
            for line in _wrap(upgraded, 68):
                wizard.say(f"  {line}")
    wizard.say()
    wizard.say(
        "  This is not the plugin's --configure wizard, which sets up a"
    )
    wizard.say("  monitoring check against one instance.")

    try:
        mode = args.mode or wizard.choose_mode(editing=bool(remembered or reused or imported))
        if mode == "private":
            _apply_preset(setup, "private")
        run_questions(wizard, mode)
        _generate_unattended(setup)
        _finalise(setup)

        if not review(wizard, setup):
            print("Nothing written.", file=sys.stderr)
            return 1

        wizard.say()
        if compose_path.exists():
            # Before the question, not after: "overwrite it?" is only an
            # answerable question for somebody who can see what would change.
            diff = render_diffs(setup, compose_path, style)
            if diff:
                wizard.rule("What writing changes")
                for line in diff:
                    wizard.say(line)
                wizard.say()
        for path in (compose_path, env_path):
            # Before the overwrite question and whatever --force says: a link
            # is not "the file", and writing through it puts the compose file
            # or the credentials somewhere nobody named.
            if path.is_symlink():
                print(
                    f"{path} is a symbolic link. Nothing written: remove it, or"
                    " point --output-dir at the directory it leads to.",
                    file=sys.stderr,
                )
                return 1
            if path.exists() and not args.force and not wizard.confirm(
                f"{path} exists. Overwrite it?", default=False
            ):
                print("Nothing written.", file=sys.stderr)
                return 1
    except SetupAborted as error:
        print(f"\nSetup aborted: {error}", file=sys.stderr)
        return 1

    saved = backup_existing(setup, compose_path, env_path)
    written = write_files(setup, compose_path, env_path)

    wizard.say()
    wizard.rule("Written")
    for path in saved:
        wizard.say(f"  {style.dim('~')} Kept the previous file as {path}")
    for path in written:
        wizard.say(f"  {style.good('+')} Wrote {path}")
    offer_to_start(wizard, setup, compose_path)
    wizard.say()
    wizard.rule("Next")
    wizard.say(f"    cd {output_dir}")
    # Before `up`, not after: a bind mount Docker has to invent is created
    # owned by root, and the container that then cannot write to it is the
    # one keeping the audit trail.
    if _keeps_audit_file(setup) and _binds_a_directory(
        setup.audit_storage, setup.audit_log_path
    ):
        wizard.say(
            f"    {_ownership_command(setup, setup.audit_log_path, WEB_IMAGE_UID)}"
        )
    if _binds_a_directory(setup.redis_persistence, setup.redis_data_path):
        wizard.say(
            f"    {_ownership_command(setup, setup.redis_data_path, REDIS_IMAGE_UID)}"
        )
    if _uses_logrotate(setup):
        name = logrotate_filename(setup)
        wizard.say(
            f"    sudo install -m 0644 -o root -g root {name} "
            f"/etc/logrotate.d/{setup.project_name}-audit"
        )
    for line in _proxy_install_commands(setup):
        wizard.say(f"    {line}")
    build = " --build" if setup.image_source == "build" else ""
    wizard.say(f"    {style.accent(f'docker compose -f {args.compose_file} up -d{build}')}")
    wizard.say(f"    {style.accent(f'open http://{setup.bind_address}:{setup.host_port}')}")
    for line in enrollment_instructions(setup, args.env_file, style):
        wizard.say(line)
    for line in admin_walkthrough(setup):
        wizard.say(line)
    if _uses_authentik(setup) and not setup.smtp_host:
        wizard.say()
        wizard.say("  No SMTP server was configured, so a password recovery will")
        wizard.say("  not arrive. AUTHENTIK_EMAIL_* in the generated file is where")
        wizard.say("  that goes; docs/authentik.md explains it.")
    wizard.say()
    wizard.say(f"  Every setting is documented in {PROJECT_URL}#readme,")
    wizard.say("  and in docs/webapp.md in full.")
    return 0


# --- the blueprints the generated stack mounts ------------------------------
# Carried here rather than read from a checkout, because this script is one
# file an operator downloads on its own. Last in the file so it is out of the
# way of the code that reads it.
# --- embedded-blueprints:start ---
# Generated by scripts/embed_wizard_blueprints.py from
# authentik/blueprints/ - edit those files and re-run it, never this block.
EMBEDDED_BLUEPRINTS: dict[str, str] = {
    "opencloud-scanner.yaml": """\
# The OAuth2 provider that guards the MCP endpoint, provisioned rather than
# clicked.
#
# `docker/docker-compose.authentik.yml` mounts this directory at
# /blueprints/custom in both Authentik containers, and the worker applies
# every file it finds under /blueprints on start. The result is that a stack
# brought up for the first time already has the provider and the application
# the scanner is configured against - no admin interface, no client ID to
# copy across, no step between `up -d` and an agent signing in.
#
# The client ID and secret come from `docker/.env`, written by
# `docker/authentik-env.sh`. That is the whole reason they are generated
# outside Authentik: both sides have to agree on them, and the value in
# COS_WEB_MCP_AUTH_AUDIENCE is the one a token is checked against.
#
# `state: created` throughout, so this provisions once and then leaves the
# operator alone. Change something in the admin interface afterwards - a
# redirect URI, the flows, the scopes - and it stays changed; this file will
# not put it back on the next start.
#
# Nothing here is secret. The client ID is published in every token it issues,
# and the secret is a reference to an environment variable rather than a
# value.

version: 1

metadata:
  name: check-opencloud-security - MCP endpoint
  labels:
    blueprints.goauthentik.io/instantiate: "true"
    blueprints.goauthentik.io/description: >-
      The OAuth2 provider and application the scan service checks tokens
      against on /mcp.

entries:
  # The scope mappings below are created by a system blueprint, and the order
  # blueprints run in is not guaranteed. Declaring the dependency is the
  # documented way to stop a first start from failing on a lookup that would
  # have succeeded a second later.
  - model: authentik_blueprints.metaapplyblueprint
    attrs:
      identifiers:
        path: system/providers-oauth2.yaml
      required: true

  - model: authentik_providers_oauth2.oauth2provider
    id: scanner-provider
    state: created
    identifiers:
      name: check-opencloud-security
    attrs:
      client_id: !Env [AUTHENTIK_SCANNER_CLIENT_ID, opencloud-scanner]
      client_secret: !Env AUTHENTIK_SCANNER_CLIENT_SECRET
      client_type: confidential

      # authorization_code for a person at a keyboard, whose client takes them
      # through the browser; client_credentials for a headless agent, which
      # Authentik answers by minting a service account of its own the first
      # time it is asked. refresh_token so a long-running agent does not have
      # to hold the client secret in memory for a week.
      grant_types:
        - authorization_code
        - refresh_token
        - client_credentials

      authorization_flow: !Find [
        authentik_flows.flow,
        [slug, default-provider-authorization-implicit-consent],
      ]
      invalidation_flow: !Find [
        authentik_flows.flow,
        [slug, default-provider-invalidation-flow],
      ]

      # The single most important line in this file. With a signing key the
      # tokens are signed asymmetrically and anybody can verify one against
      # the published JWKS, which is what the scanner does. Without one
      # Authentik falls back to signing with the client secret, and a resource
      # server could only verify a token by being handed that secret - which
      # is why the scanner refuses such a token outright.
      signing_key: !Find [
        authentik_crypto.certificatekeypair,
        [name, "authentik Self-signed Certificate"],
      ]

      property_mappings:
        - !Find [
          authentik_providers_oauth2.scopemapping,
          [managed, "goauthentik.io/providers/oauth2/scope-openid"],
        ]
        - !Find [
          authentik_providers_oauth2.scopemapping,
          [managed, "goauthentik.io/providers/oauth2/scope-profile"],
        ]
        - !Find [
          authentik_providers_oauth2.scopemapping,
          [managed, "goauthentik.io/providers/oauth2/scope-email"],
        ]
        - !Find [
          authentik_providers_oauth2.scopemapping,
          [managed, "goauthentik.io/providers/oauth2/scope-offline_access"],
        ]

      redirect_uris:
        - matching_mode: strict
          url: !Env [AUTHENTIK_SCANNER_REDIRECT_URI, "http://localhost:8811/"]
        # The loopback callback an MCP client running on somebody's laptop
        # opens. The port is chosen per run, so this one is a pattern rather
        # than an address - and it is a pattern for 127.0.0.1 only, which is
        # the one host a redirect cannot be stolen from.
        - matching_mode: regex
          url: "http://127\\\\.0\\\\.0\\\\.1:[0-9]{1,5}/.*"

      # Per-provider, which is the default and what makes the issuer
      # <authentik>/application/o/<application slug>/ - the value the scanner
      # is configured with, built from the slug of the application below.
      issuer_mode: per_provider

  - model: authentik_core.application
    state: created
    identifiers:
      slug: !Env [AUTHENTIK_SCANNER_SLUG, opencloud-scanner]
    attrs:
      name: OpenCloud security scanner
      provider: !KeyOf scanner-provider
      meta_description: >-
        The MCP endpoint of check-opencloud-security. Signing in decides who
        may ask for a scan; it does not change any rate limit.
      meta_publisher: check-opencloud-security
""",
    "opencloud-admin.yaml": """\
# The proxy provider that guards the operator's area at /admin.
#
# Applied the same way `opencloud-scanner.yaml` is - the compose file mounts
# this directory into both Authentik containers and the worker applies every
# blueprint it finds - but it provisions a *proxy* provider rather than an
# OAuth2 one, because the thing it protects is a page a person opens rather
# than an endpoint an agent holds a token for.
#
# The split matters. The scan service authenticates nobody: it has no login
# page, no session and no password to check, on /mcp or here. What reaches it
# on /admin is the outpost's account of who signed in, in ordinary headers -
# `X-authentik-username` and its neighbours - and headers are worth exactly
# what the certainty that they came from the outpost is worth.
#
# That certainty is `COS_WEB_ADMIN_PROXY_SECRET`, which the proxy in front
# adds as `X-COS-Admin-Proxy` on every request it forwards. The service
# compares it in constant time and refuses anything without it, so reaching
# the container directly - from another container on the same network, say -
# gets a 404 rather than a console. Authentik does not invent that header:
# the reverse proxy doing the forward-auth does, from the same value in
# `docker/.env`. `docs/authentik.md` has the nginx and Traefik forms.
#
# Being on the guest list is a second, separate question. Signing in here
# only proves the directory knows you; `COS_WEB_ADMIN_USERS` decides whether
# you are an operator of *this* deployment, and an empty list is refused at
# startup rather than read as everybody.
#
# `state: created` throughout: this provisions once and then leaves the
# operator alone.

version: 1

metadata:
  name: check-opencloud-security - operator area
  labels:
    blueprints.goauthentik.io/instantiate: "true"
    blueprints.goauthentik.io/description: >-
      The proxy provider and application that put a sign-in in front of the
      scan service's /admin area.

entries:
  # A group to put operators in, so the guest list is managed in one place
  # rather than as a binding per person.
  - model: authentik_core.group
    id: admin-group
    state: created
    identifiers:
      name: !Env [AUTHENTIK_ADMIN_GROUP, opencloud-scanner-operators]
    attrs:
      name: !Env [AUTHENTIK_ADMIN_GROUP, opencloud-scanner-operators]

  - model: authentik_providers_proxy.proxyprovider
    id: admin-provider
    state: created
    identifiers:
      name: check-opencloud-security - admin
    attrs:
      name: check-opencloud-security - admin
      # Forward auth for a single application: the proxy in front asks
      # authentik about each request rather than authentik proxying the
      # traffic itself, which keeps the scan service reachable on its own
      # address for the health check and the worker.
      mode: forward_single
      external_host: !Env [COS_WEB_ADMIN_URL, "http://localhost:8811"]
      # Nothing here needs to be long-lived: the area is a console somebody
      # opens, does something in and leaves.
      access_token_validity: hours=8
      authorization_flow:
        !Find [
          authentik_flows.flow,
          [slug, default-provider-authorization-implicit-consent],
        ]
      invalidation_flow:
        !Find [
          authentik_flows.flow,
          [slug, default-provider-invalidation-flow],
        ]

  - model: authentik_core.application
    state: created
    identifiers:
      slug: !Env [AUTHENTIK_ADMIN_SLUG, opencloud-scanner-admin]
    attrs:
      name: OpenCloud scanner - operator area
      slug: !Env [AUTHENTIK_ADMIN_SLUG, opencloud-scanner-admin]
      provider: !KeyOf admin-provider
      meta_description: >-
        Service state, reference data and the audit trail of the OpenCloud
        security scanner.

  # Only the group may reach the application. Without a binding an authentik
  # application is open to every account in the directory, which is precisely
  # the mistake COS_WEB_ADMIN_USERS exists to catch on the other side.
  - model: authentik_policies.policybinding
    state: created
    identifiers:
      target:
        !Find [
          authentik_core.application,
          [slug, !Env [AUTHENTIK_ADMIN_SLUG, opencloud-scanner-admin]],
        ]
      group: !KeyOf admin-group
      order: 0
    attrs:
      enabled: true

  # The outpost that answers the forward-auth subrequest: authentik's own
  # embedded one, which listens on the server's port 9000 - the address the
  # generated reverse proxy sends `/outpost.goauthentik.io/` to - and routes a
  # request there only for a host belonging to a provider assigned to it.
  # Without this entry the core answers that path with 404, and nginx turns
  # a 404 from `auth_request` into a 500 for every request to /admin.
  #
  # `state: present`, and that has a cost worth knowing: blueprints are
  # re-applied every hour, and `providers` is replaced rather than merged, so
  # a provider assigned to the embedded outpost by hand is taken off it again.
  # This authentik is the one this stack brings; give any other application a
  # blueprint of its own that lists every provider, or an outpost of its own.
  #
  # An earlier version created a separate proxy outpost here instead. Nothing
  # in this stack runs one, and the entry itself was invalid - it named no
  # `config`, so authentik refused it and, a blueprint being applied as a
  # whole, rolled back the provider, application and binding above with it.
  - model: authentik_outposts.outpost
    state: present
    identifiers:
      managed: goauthentik.io/outposts/embedded
    attrs:
      providers:
        - !KeyOf admin-provider
      # Where the outpost sends a browser to sign in. Left empty, the embedded
      # outpost redirects to http://localhost/application/o/authorize/, which
      # is nowhere a visitor can reach. A full URL - a bare host name is not
      # accepted. This replaces the whole outpost configuration on every
      # apply; unnamed keys keep their defaults.
      config:
        authentik_host: !Env [COS_AUTHENTIK_URL, "http://localhost:9000"]

  # Removed again where that earlier version did manage to create it.
  - model: authentik_outposts.outpost
    state: absent
    identifiers:
      name: check-opencloud-security - admin outpost
""",
    "opencloud-mfa.yaml": """\
# A second factor for every account that signs in, from the first sign-in.
#
# Authentik's default authentication flow already has a stage that checks a
# second factor - `default-authentication-mfa-validation` - but it ships
# configured to *skip* anybody who has none, which on a fresh directory is
# everybody. This changes that one stage to *configure* instead: an account
# without an authenticator is taken through enrolling one, TOTP or WebAuthn,
# before the sign-in completes, and asked for it on every sign-in after that.
#
# It is the default flow's own stage that changes, rather than a second one
# bound beside it, so an account with an authenticator is asked once and not
# twice - and the enrollment flow in `opencloud-enrollment.yaml` binds the
# same stage, so an account created there has a second factor before it has
# a session.
#
# `state: present`, deliberately. Blueprints are re-applied every hour, so the
# requirement cannot quietly be switched off in the admin interface and
# forgotten. To lift it, remove this file from the blueprint directory; the
# stage keeps its last setting until somebody changes it.
#
# What it does not reach: an agent using the client_credentials grant signs in
# with an app password and never runs a flow, which is correct - a cron job
# has no phone to read a code from. Recovery when a person loses their
# authenticator is the `akadmin` account, whose password the setup wizard
# writes into `.env` as AUTHENTIK_BOOTSTRAP_PASSWORD: sign in as it (it is
# asked to enrol a factor too) and delete the lost device under
# Directory > Users.

version: 1

metadata:
  name: check-opencloud-security - multi-factor authentication
  labels:
    blueprints.goauthentik.io/instantiate: "true"
    blueprints.goauthentik.io/description: >-
      Requires every account to enrol and use a second factor when it signs
      in.

entries:
  # The stage and the two setup stages below are Authentik's own, and the
  # order blueprints are applied in is not guaranteed. Without these a first
  # start could look the setup stages up a moment before they exist.
  - model: authentik_blueprints.metaapplyblueprint
    attrs:
      identifiers:
        name: Default - Authentication flow
      required: true
  - model: authentik_blueprints.metaapplyblueprint
    attrs:
      identifiers:
        name: Default - TOTP MFA setup flow
      required: true
  - model: authentik_blueprints.metaapplyblueprint
    attrs:
      identifiers:
        name: Default - WebAuthn MFA setup flow
      required: true

  - model: authentik_stages_authenticator_validate.authenticatorvalidatestage
    state: present
    identifiers:
      name: default-authentication-mfa-validation
    attrs:
      # Enrol rather than skip, and deny nobody for lacking one yet: the
      # person is shown the choice below and completes the sign-in afterwards.
      not_configured_action: configure
      # Offered in this order. An authenticator app works everywhere; a
      # security key or passkey is the stronger of the two.
      configuration_stages:
        - !Find [
          authentik_stages_authenticator_totp.authenticatortotpstage,
          [name, default-authenticator-totp-setup],
        ]
        - !Find [
          authentik_stages_authenticator_webauthn.authenticatorwebauthnstage,
          [name, default-authenticator-webauthn-setup],
        ]
      # What counts as a second factor once enrolled. Static recovery codes
      # are accepted because a person can create them from their own settings
      # as a fallback; nothing here can enrol SMS, Duo or email, so they are
      # left out rather than advertised.
      device_classes:
        - totp
        - webauthn
        - static
""",
    "opencloud-enrollment.yaml": """\
# The one link a person needs: choose a password, enrol a second factor, done.
#
# The Docker setup wizard asks who signs in to this stack, by username, and
# generates a secret invitation token into `.env`. This blueprint turns those
# two into an enrollment flow behind that token:
#
#   <authentik>/if/flow/opencloud-scanner-enrollment/?itoken=<token>
#
# The person opening it types one of the listed usernames, an email address
# and a password, enrols an authenticator app or a security key - the same
# stage `opencloud-mfa.yaml` puts in front of every sign-in - and is signed
# in. Somebody who is also on the operator's guest list lands in the operator
# group the `/admin` application is bound to. Nothing is clicked in the admin
# interface, by anybody.
#
# Three things keep the link from being a way in for whoever reads it:
#
# - **Only the listed names.** COS_AUTHENTIK_ACCOUNTS is the whole list, and a
#   username not on it is refused at the form. An empty list admits nobody.
# - **Only once per name.** The username field refuses a name that already
#   exists, so a name that has enrolled cannot be claimed a second time, and
#   the link stops being useful the moment everybody on the list has used it.
# - **Only with the token.** It is a random UUID from `.env`, and a flow
#   without it answers "Invalid invite" before showing a single field.
#
# The invitation is re-applied with the token in `.env`, so rotating
# AUTHENTIK_ENROLLMENT_TOKEN there and restarting retires the old link. On a
# stack started without a token - `docker-compose.authentik.yml` run by hand -
# no invitation is created, and the flow is unreachable.
#
# No secret is written here: the token and both lists are read from the
# environment when the blueprint is applied or the flow runs.

version: 1

metadata:
  name: check-opencloud-security - enrollment
  labels:
    blueprints.goauthentik.io/instantiate: "true"
    blueprints.goauthentik.io/description: >-
      An invitation-only enrollment flow for the accounts the setup wizard
      named, with a second factor enrolled before the first session.

entries:
  - model: authentik_blueprints.metaapplyblueprint
    attrs:
      identifiers:
        name: check-opencloud-security - multi-factor authentication
      required: true

  - model: authentik_flows.flow
    id: flow
    identifiers:
      slug: opencloud-scanner-enrollment
    attrs:
      name: OpenCloud scanner - enrollment
      title: Set up your account
      designation: enrollment
      # Somebody already signed in has an account, and a flow that attached a
      # new password to *that* session is not one to offer.
      authentication: require_unauthenticated

  - model: authentik_stages_invitation.invitationstage
    id: invitation-stage
    identifiers:
      name: opencloud-scanner-enrollment-invitation
    attrs:
      continue_flow_without_invitation: false

  - model: authentik_stages_invitation.invitation
    state: present
    conditions:
      - !If [!Env [COS_AUTHENTIK_ENROLLMENT_TOKEN, ""]]
    identifiers:
      pk: !Env [COS_AUTHENTIK_ENROLLMENT_TOKEN, ""]
    attrs:
      name: opencloud-scanner-enrollment
      flow: !KeyOf flow
      # Used once per *name*, which the username field enforces; deleting the
      # invitation after the first person would leave everybody else on the
      # list without a way in.
      single_use: false
      fixed_data: {}

  - model: authentik_stages_prompt.prompt
    id: field-username
    identifiers:
      name: opencloud-scanner-enrollment-username
    attrs:
      field_key: username
      label: Username
      # `username` rather than `text`: Authentik refuses a name that already
      # exists, which is what makes each name claimable exactly once.
      type: username
      required: true
      placeholder: The username you were given
      placeholder_expression: false
      order: 0

  - model: authentik_stages_prompt.prompt
    id: field-email
    identifiers:
      name: opencloud-scanner-enrollment-email
    attrs:
      field_key: email
      label: Email
      type: email
      required: true
      placeholder: Where a password recovery is sent
      placeholder_expression: false
      order: 1

  - model: authentik_stages_prompt.prompt
    id: field-password
    identifiers:
      name: opencloud-scanner-enrollment-password
    attrs:
      field_key: password
      label: Password
      type: password
      required: true
      placeholder: Password
      placeholder_expression: false
      order: 2

  - model: authentik_stages_prompt.prompt
    id: field-password-repeat
    identifiers:
      name: opencloud-scanner-enrollment-password-repeat
    attrs:
      field_key: password_repeat
      label: Password (repeat)
      type: password
      required: true
      placeholder: Password (repeat)
      placeholder_expression: false
      order: 3

  - model: authentik_policies_expression.expressionpolicy
    id: policy-listed-username
    identifiers:
      name: opencloud-scanner-enrollment-listed-username
    attrs:
      expression: |
        # Read when the form is submitted rather than baked in when the
        # blueprint is applied, so a username never becomes Python source.
        import os

        listed = {
            name.strip()
            for name in os.environ.get("COS_AUTHENTIK_ACCOUNTS", "").split(";")
            if name.strip()
        }
        username = (request.context.get("prompt_data") or {}).get("username", "")
        if username in listed:
            return True
        ak_message("This username is not one this invitation was issued for.")
        return False

  - model: authentik_stages_prompt.promptstage
    id: prompt-stage
    identifiers:
      name: opencloud-scanner-enrollment-prompt
    attrs:
      fields:
        - !KeyOf field-username
        - !KeyOf field-email
        - !KeyOf field-password
        - !KeyOf field-password-repeat
      validation_policies:
        - !KeyOf policy-listed-username

  - model: authentik_policies_expression.expressionpolicy
    id: policy-operator-group
    identifiers:
      name: opencloud-scanner-enrollment-operator-group
    attrs:
      expression: |
        # Somebody on the operator's guest list joins the group the /admin
        # application is bound to. The user write stage adds whatever groups
        # the plan carries under "groups" once the account is saved.
        import os

        from authentik.core.models import Group

        operators = {
            name.strip()
            for name in os.environ.get("COS_WEB_ADMIN_USERS", "").split(";")
            if name.strip()
        }
        plan = request.context.get("flow_plan")
        if not plan:
            return True
        username = (plan.context.get("prompt_data") or {}).get("username", "")
        name = os.environ.get("AUTHENTIK_ADMIN_GROUP", "opencloud-scanner-operators")
        group = Group.objects.filter(name=name).first()
        if username in operators and group is not None:
            plan.context.setdefault("groups", []).append(group)
        return True

  - model: authentik_stages_user_write.userwritestage
    id: write-stage
    identifiers:
      name: opencloud-scanner-enrollment-write
    attrs:
      user_creation_mode: always_create
      user_type: internal
      create_users_as_inactive: false

  - model: authentik_flows.flowstagebinding
    identifiers:
      target: !KeyOf flow
      stage: !KeyOf invitation-stage
      order: 0
    attrs:
      evaluate_on_plan: true
      re_evaluate_policies: false

  - model: authentik_flows.flowstagebinding
    identifiers:
      target: !KeyOf flow
      stage: !KeyOf prompt-stage
      order: 10

  - model: authentik_flows.flowstagebinding
    id: write-binding
    identifiers:
      target: !KeyOf flow
      stage: !KeyOf write-stage
      order: 20
    attrs:
      # Evaluated when the stage is reached, after the form, so the policy
      # below sees the username that was typed.
      evaluate_on_plan: false
      re_evaluate_policies: true

  - model: authentik_policies.policybinding
    identifiers:
      target: !KeyOf write-binding
      policy: !KeyOf policy-operator-group
      order: 0
    attrs:
      failure_result: true

  # The second factor, before there is a session: the default flow's own
  # validation stage, which `opencloud-mfa.yaml` sets to enrol an account that
  # has none.
  - model: authentik_flows.flowstagebinding
    identifiers:
      target: !KeyOf flow
      stage: !Find [
        authentik_stages_authenticator_validate.authenticatorvalidatestage,
        [name, default-authentication-mfa-validation],
      ]
      order: 30

  - model: authentik_flows.flowstagebinding
    identifiers:
      target: !KeyOf flow
      stage: !Find [
        authentik_stages_user_login.userloginstage,
        [name, default-authentication-login],
      ]
      order: 100
""",
}
# --- embedded-blueprints:end ---


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
