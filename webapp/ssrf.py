"""
What the scanner is allowed to be pointed at.

A public scan service is a request forwarder by definition, so the target has
to be checked before anything connects to it. The rules:

- the scheme is ``http`` or ``https`` and nothing else - no ``file://``,
  ``gopher://`` or ``redis://``;
- what is submitted is an instance base address: a hostname, optional scheme
  and port, and an optional plain subfolder path. Queries, fragments,
  credentials, path parameters, escapes and traversal segments are refused,
  so a visitor can locate an installation without describing a request;
- the hostname resolves, and *every* address it resolves to is a public
  unicast address. One private answer among several rejects the target, which
  is what makes a split-horizon or multi-A record trick pointless;
- the cloud metadata addresses are refused by name as well, because they are
  the one target where a single successful request is already a breach.

The scanner appends only paths it knows to that base address and takes no
instruction from the submission about *what* to request.

DNS rebinding is answered by resolving twice: once when the request is
accepted, and again in the worker immediately before the scan. That closes the
long window between the two, which is the one an attacker can actually aim at.
The residual window is a single TTL flip inside one scan, and it cannot be
widened from outside because the request cannot influence timing.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("https", "http")
DEFAULT_PORTS = {"https": 443, "http": 80}
MAX_TARGET_LENGTH = 253

# A submission is an address, so it is spelled the way an address is: labels
# of letters, digits and hyphens, separated by dots. Anything else - a space,
# a backslash, a percent escape, a control character, a label starting or
# ending in a hyphen - is not a hostname somebody typed by mistake, it is an
# attempt at something. IP literals are handled separately.
HOSTNAME_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

PATH_SEGMENT = re.compile(r"^[a-zA-Z0-9._~-]+$")

# Refused by name as well as by address: a resolver that answers these with a
# public address is either misconfigured or lying.
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
        "instance-data.ec2.internal",
    }
)

BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")

# Link-local already covers 169.254.169.254, but naming the metadata endpoints
# makes the refusal message useful and survives a future carve-out.
BLOCKED_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)

# Ranges `ipaddress` does not classify as private but which are still not
# somewhere a public service should be talking to. Carrier-grade NAT is the
# one that matters: a deployment behind it shares 100.64.0.0/10 with every
# other subscriber on that carrier.
BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("2002::/16"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)


class TargetRejected(ValueError):
    """The target is not something this service may connect to."""

    def __init__(self, reason: str, key: str = "error.target.invalid") -> None:
        super().__init__(reason)
        # The sentence is what the API answers and what a log would show; the
        # identifier is how the page says the same thing in the visitor's
        # language. Neither is derived from the other.
        self.key = key


@dataclass(frozen=True)
class Target:
    """A validated target, split into what the scanner needs."""

    hostname: str
    port: int
    scheme: str
    path: str
    addresses: tuple[str, ...]

    @property
    def display(self) -> str:
        """How the target is shown back to the visitor who submitted it."""
        hostname = f"[{self.hostname}]" if ":" in self.hostname else self.hostname
        port = "" if self.port == DEFAULT_PORTS[self.scheme] else f":{self.port}"
        return f"{self.scheme}://{hostname}{port}{self.path}"

    @property
    def scan_host(self) -> str:
        """The host argument for ``opencloud_local_scan.scan``."""
        return self.display


def _reject(reason: str, key: str = "error.target.invalid") -> TargetRejected:
    return TargetRejected(reason, key)


ADDRESS_ONLY = (
    "Enter the instance base address only. A plain subfolder is accepted, "
    "but queries, fragments, parameters and path traversal are not."
)


def _hostname_shaped(hostname: str) -> bool:
    """Whether this is spelled like a hostname rather than like an attack."""
    try:  # an IP literal is an address, checked as one further down
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        pass
    else:
        return True
    labels = hostname.split(".")
    return all(HOSTNAME_LABEL.match(label) for label in labels)


def _split(raw: str, *, address_only: bool = True) -> tuple[str, str, int | None, str]:
    candidate = raw.strip()
    if not candidate:
        raise _reject(
            "Enter the address of the OpenCloud instance to scan.",
            "error.target.empty",
        )
    if len(candidate) > 2048:
        raise _reject("That address is too long.", "error.target.too_long")
    # A tab, a newline or a stray control character never belongs in an
    # address, and every one of them is a request-splitting attempt somewhere.
    if any(character in candidate for character in ("\\", " ")) or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in candidate
    ):
        raise _reject(
            "That address contains characters a hostname cannot have.",
            "error.target.characters",
        )
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:  # malformed IPv6 literal, and anything like it
        raise _reject("That address could not be parsed.", "error.target.unparsed") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise _reject(
            "Only http:// and https:// targets can be scanned.",
            "error.target.scheme",
        )
    if parts.username or parts.password:
        raise _reject(
            "Credentials in the address are not accepted.",
            "error.target.credentials",
        )

    path = parts.path.rstrip("/")
    if address_only:
        if parts.query or parts.fragment:
            raise _reject(ADDRESS_ONLY, "error.target.address_only")
        segments = path.split("/")[1:] if path.startswith("/") else []
        if (
            (path and not path.startswith("/"))
            or any(
                not segment
                or segment in {".", ".."}
                or PATH_SEGMENT.fullmatch(segment) is None
                for segment in segments
            )
        ):
            raise _reject(ADDRESS_ONLY, "error.target.address_only")

    try:
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:  # malformed port
        raise _reject("That address has an invalid port.", "error.target.port") from exc
    if not hostname:
        raise _reject("That address has no hostname.", "error.target.no_host")
    hostname = hostname.lower().rstrip(".")
    # An international name is a hostname too; it is simply spelled in a
    # different alphabet until DNS sees it. Convert it the way a browser
    # would, then hold the result to the same rule as everything else.
    if not hostname.isascii():
        try:
            hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise _reject(
            "That is not a hostname this service can scan.",
            "error.target.hostname_shape",
        ) from exc
    if not _hostname_shaped(hostname):
        raise _reject(
            "That is not a hostname this service can scan.",
            "error.target.hostname_shape",
        )
    return scheme, hostname, port, path


def _hostname_allowed(hostname: str, allowed: tuple[str, ...]) -> bool:
    return hostname in {entry.lower() for entry in allowed}


def _resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise _reject("That hostname does not resolve.", "error.target.unresolved") from exc
    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:  # pragma: no cover - getaddrinfo returned nonsense
            continue
    if not addresses:
        raise _reject("That hostname does not resolve.", "error.target.unresolved")
    return addresses


def _address_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address in BLOCKED_ADDRESSES:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return _address_public(address.ipv4_mapped)
        if address.sixtofour is not None:
            return _address_public(address.sixtofour)
    if any(address in network for network in BLOCKED_NETWORKS if network.version == address.version):
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_target(
    raw: str,
    *,
    allow_private: bool = False,
    allowed_hosts: tuple[str, ...] = (),
    address_only: bool = True,
) -> Target:
    """
    Turn what the visitor typed into a target that is safe to connect to.

    Raises :class:`TargetRejected` with a message written for a person, since
    it is shown next to the input field.

    ``address_only`` is what a submission is held to: an address, a scheme and
    a port, and nothing appended to them. A redirect the scanned instance
    answers with is checked with it off, because that URL is the instance
    talking, not the visitor.
    """
    scheme, hostname, port, path = _split(raw, address_only=address_only)
    exempt = _hostname_allowed(hostname, allowed_hosts)

    if len(hostname) > MAX_TARGET_LENGTH and not hostname.startswith("["):
        raise _reject("That hostname is too long.", "error.target.hostname_long")

    if not (allow_private or exempt) and (
        hostname in BLOCKED_HOSTNAMES or hostname.endswith(BLOCKED_SUFFIXES)
    ):
        raise _reject(
            "Local and internal addresses cannot be scanned.",
            "error.target.internal",
        )

    try:
        literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None = (
            ipaddress.ip_address(hostname.strip("[]"))
        )
    except ValueError:
        literal = None

    if literal is not None:
        addresses = [literal]
    else:
        addresses = _resolve(hostname)

    if not (allow_private or exempt):
        for address in addresses:
            if not _address_public(address):
                raise _reject(
                    "That address points into a private, loopback or "
                    "link-local network, which this service will not scan.",
                    "error.target.private",
                )

    return Target(
        hostname=hostname,
        port=port or DEFAULT_PORTS[scheme],
        scheme=scheme,
        path=path,
        addresses=tuple(str(address) for address in addresses),
    )


def revalidate(target: Target, *, allow_private: bool = False,
               allowed_hosts: tuple[str, ...] = ()) -> Target:
    """
    Check the target again, in the worker, right before the scan.

    Called from the job so that a DNS answer which changed since the request
    was accepted is caught rather than trusted.
    """
    return validate_target(
        target.display,
        allow_private=allow_private,
        allowed_hosts=allowed_hosts,
    )


def redirect_guard(
    *,
    allow_private: bool = False,
    allowed_hosts: tuple[str, ...] = (),
) -> Callable[[str], bool]:
    """
    Build the check the scanner asks before following one redirect.

    The address a visitor submitted is only the *first* one the scan connects
    to. A target that answers ``302 Location: http://127.0.0.1:8500/`` would
    otherwise have the scan read the scanning host's own network and report
    the answer back under the visitor's uuid, which is the same SSRF the
    submission guard exists to prevent - one hop later.

    Every hop is resolved and checked exactly like the original target, so a
    chain cannot walk out of the rules one redirect at a time.
    """

    def _allowed(url: str) -> bool:
        try:
            validate_target(
                url,
                allow_private=allow_private,
                allowed_hosts=allowed_hosts,
                address_only=False,
            )
        except TargetRejected:
            return False
        return True

    return _allowed


def redirect_pinner(
    *,
    allow_private: bool = False,
    allowed_hosts: tuple[str, ...] = (),
) -> Callable[[str], tuple[str, ...] | None]:
    """Validate a redirect and return the exact addresses it may use."""

    def _pin(url: str) -> tuple[str, ...] | None:
        try:
            return validate_target(
                url,
                allow_private=allow_private,
                allowed_hosts=allowed_hosts,
                address_only=False,
            ).addresses
        except TargetRejected:
            return None

    return _pin
