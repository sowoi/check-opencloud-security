"""
The fixes a report names, in the syntax the file that has to change uses.

``hardening.py`` answers "what should this be" in a sentence: *Set
PROXY_ENABLE_BASIC_AUTH=false*. An operator then translates eleven of those
sentences into one Compose file or one nginx server block, by hand, and the
translation is where the mistakes are. This module does that step: given the
identifiers a scan reported, it writes the fragment.

**It renders, it does not decide.** Every name and value here comes from
``Hardening.env_fix`` and ``Hardening.header_fix`` in the catalogue - this
module owns no configuration knowledge of its own and adds no value the
catalogue did not already state. Which findings to feed it is the caller's
question; whether a finding is acceptable is the plugin's.

**A fragment is complete or it says so.** A check whose right value depends on
the deployment - an origin, a path to a CSP file - carries no mechanical fix
in the catalogue, and is reported in :attr:`Fragment.undecided` rather than
guessed at with a placeholder. A fragment that has to be edited before it is
pasted is worse than the sentence it replaced, because it looks finished.

**A flavour expresses one kind of fix.** Environment assignments go on the
OpenCloud instance; response headers go on whatever terminates TLS in front
of it. These are different files, usually on different machines, so no
flavour renders both: asking for nginx and being handed OpenCloud environment
variables would produce a file that silently does nothing. What the chosen
flavour cannot express is named in :attr:`Fragment.elsewhere` instead, with
the flavours that can.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .hardening import describe

#: An environment assignment on the OpenCloud instance itself.
KIND_ENV = "env"

#: A response header, set by whatever terminates TLS in front of it.
KIND_HEADER = "header"


@dataclass(frozen=True)
class Flavour:
    """One way of writing configuration down."""

    id: str
    label: str
    """What to call it in a picker. Not translated: these are product names."""

    kind: str
    """:data:`KIND_ENV` or :data:`KIND_HEADER` - which fixes it can express."""

    filename: str
    """The file this fragment belongs in, shown above the code block."""


FLAVOURS: tuple[Flavour, ...] = (
    Flavour("compose", "Docker Compose", KIND_ENV, "docker-compose.yml"),
    Flavour("env", ".env", KIND_ENV, ".env"),
    Flavour("nginx", "nginx", KIND_HEADER, "nginx.conf"),
    Flavour("caddy", "Caddy", KIND_HEADER, "Caddyfile"),
    Flavour("traefik", "Traefik", KIND_HEADER, "traefik-dynamic.yml"),
)

#: The flavour a picker starts on, and the one a stored choice falls back to.
DEFAULT_FLAVOUR = "compose"

_BY_ID: dict[str, Flavour] = {flavour.id: flavour for flavour in FLAVOURS}


def flavour(identifier: str) -> Flavour:
    """The named flavour, or the default for anything unrecognised."""
    return _BY_ID.get(identifier, _BY_ID[DEFAULT_FLAVOUR])


def flavours_for(kind: str) -> tuple[str, ...]:
    """The labels of every flavour that can express this kind of fix."""
    return tuple(entry.label for entry in FLAVOURS if entry.kind == kind)


@dataclass(frozen=True)
class Fragment:
    """One rendered configuration fragment, and what it left out."""

    flavour: Flavour
    text: str
    """The fragment itself, or empty when this flavour had nothing to write."""

    covered: tuple[str, ...]
    """The identifiers this fragment fixes."""

    elsewhere: tuple[str, ...]
    """
    Identifiers with a mechanical fix that this flavour cannot express.

    They are not unfixable - they belong in the other kind of file, and
    :func:`flavours_for` names the flavours that write it.
    """

    undecided: tuple[str, ...]
    """
    Identifiers the catalogue deliberately leaves to prose.

    The right value is a decision about this deployment, so the finding's own
    Fix line is the whole answer and there is nothing to paste.
    """

    @property
    def empty(self) -> bool:
        """Whether this flavour had nothing at all to write."""
        return not self.text


def _pairs(names: Iterable[str], kind: str) -> tuple[
    list[tuple[str, str]], list[str], list[str], list[str]
]:
    """
    Sort the identifiers into what this kind of fix covers and what it does not.

    Returns the assignments to render, the identifiers they came from, the
    identifiers whose fix is the *other* kind, and the identifiers with no
    mechanical fix at all.
    """
    assignments: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    covered: list[str] = []
    elsewhere: list[str] = []
    undecided: list[str] = []
    for name in names:
        entry = describe(name)
        mine = entry.env_fix if kind == KIND_ENV else entry.header_fix
        theirs = entry.header_fix if kind == KIND_ENV else entry.env_fix
        if mine:
            covered.append(name)
            for pair in mine:
                # Two findings can want the same assignment - debugEndpoint
                # and debugPort are one OC_DEBUG_ADDR between them - and a
                # fragment that sets it twice is a fragment somebody has to
                # read twice.
                if pair not in seen:
                    seen.add(pair)
                    assignments.append(pair)
        elif theirs:
            elsewhere.append(name)
        else:
            undecided.append(name)
    return assignments, covered, elsewhere, undecided


def _compose(assignments: list[tuple[str, str]]) -> str:
    """A Compose service's environment block, in the mapping form."""
    lines = ["services:", "  opencloud:", "    environment:"]
    lines += [f'      {name}: "{value}"' for name, value in assignments]
    return "\n".join(lines)


def _env(assignments: list[tuple[str, str]]) -> str:
    """Plain assignments, for an env file or a shell."""
    return "\n".join(f"{name}={value}" for name, value in assignments)


def _nginx(assignments: list[tuple[str, str]]) -> str:
    """
    nginx `add_header` directives.

    ``always`` is not optional here: without it nginx omits the header on
    error responses, and an error page served without a Content-Security-Policy
    is exactly the page that needs one.
    """
    return "\n".join(
        f'add_header {name} "{value}" always;' for name, value in assignments
    )


def _caddy(assignments: list[tuple[str, str]]) -> str:
    """A Caddy header block."""
    lines = ["header {"]
    lines += [f'\t{name} "{value}"' for name, value in assignments]
    lines.append("}")
    return "\n".join(lines)


def _traefik(assignments: list[tuple[str, str]]) -> str:
    """
    A Traefik dynamic-configuration middleware.

    ``customResponseHeaders`` rather than the typed fields Traefik also has
    for some of these: one mechanism for every header keeps the fragment
    uniform, and the typed fields cover only a few of them.
    """
    lines = [
        "http:",
        "  middlewares:",
        "    opencloud-security-headers:",
        "      headers:",
        "        customResponseHeaders:",
    ]
    lines += [f'          {name}: "{value}"' for name, value in assignments]
    return "\n".join(lines)


_RENDERERS = {
    "compose": _compose,
    "env": _env,
    "nginx": _nginx,
    "caddy": _caddy,
    "traefik": _traefik,
}


def fragment(names: Iterable[str], flavour_id: str = DEFAULT_FLAVOUR) -> Fragment:
    """
    Render the fixes for these identifiers in one flavour.

    ``names`` is whatever the caller considers open - failed checks, missing
    hardenings, missing headers, in the order they should be read. Order is
    preserved so that a fragment reads in the same order as the report above
    it, and an identifier this build cannot explain simply contributes
    nothing.
    """
    chosen = flavour(flavour_id)
    assignments, covered, elsewhere, undecided = _pairs(names, chosen.kind)
    return Fragment(
        flavour=chosen,
        text=_RENDERERS[chosen.id](assignments) if assignments else "",
        covered=tuple(covered),
        elsewhere=tuple(elsewhere),
        undecided=tuple(undecided),
    )
