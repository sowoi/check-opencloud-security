"""
What the scanner is allowed to be pointed at.

A public scan service is a request forwarder by definition, so the target has
to be checked before anything connects to it. The rules:

- the scheme is ``http`` or ``https`` and nothing else - no ``file://``,
  ``gopher://`` or ``redis://``;
- the hostname resolves, and *every* address it resolves to is a public
  unicast address. One private answer among several rejects the target, which
  is what makes a split-horizon or multi-A record trick pointless;
- the cloud metadata addresses are refused by name as well, because they are
  the one target where a single successful request is already a breach.

DNS rebinding is answered by resolving twice: once when the request is
accepted, and again in the worker immediately before the scan. That closes the
long window between the two, which is the one an attacker can actually aim at.
The residual window is a single TTL flip inside one scan, and it cannot be
widened from outside because the request cannot influence timing.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("https", "http")
DEFAULT_PORTS = {"https": 443, "http": 80}
MAX_TARGET_LENGTH = 253

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


@dataclass(frozen=True)
class Target:
    """A validated target, split into what the scanner needs."""

    hostname: str
    port: int
    scheme: str
    addresses: tuple[str, ...]

    @property
    def display(self) -> str:
        """How the target is shown back to the visitor who submitted it."""
        if self.port == DEFAULT_PORTS[self.scheme]:
            return f"{self.scheme}://{self.hostname}"
        return f"{self.scheme}://{self.hostname}:{self.port}"

    @property
    def scan_host(self) -> str:
        """The host argument for ``opencloud_local_scan.scan``."""
        return self.hostname


def _reject(reason: str) -> TargetRejected:
    return TargetRejected(reason)


def _split(raw: str) -> tuple[str, str, int | None]:
    candidate = raw.strip()
    if not candidate:
        raise _reject("Enter the address of the OpenCloud instance to scan.")
    if len(candidate) > 2048:
        raise _reject("That address is too long to be a hostname.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:  # malformed IPv6 literal, and anything like it
        raise _reject("That address could not be parsed.") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise _reject("Only http:// and https:// targets can be scanned.")
    if parts.username or parts.password:
        raise _reject("Credentials in the address are not accepted.")

    try:
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:  # malformed port
        raise _reject("That address has an invalid port.") from exc
    if not hostname:
        raise _reject("That address has no hostname.")
    return scheme, hostname.lower().rstrip("."), port


def _hostname_allowed(hostname: str, allowed: tuple[str, ...]) -> bool:
    return hostname in {entry.lower() for entry in allowed}


def _resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise _reject("That hostname does not resolve.") from exc
    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:  # pragma: no cover - getaddrinfo returned nonsense
            continue
    if not addresses:
        raise _reject("That hostname does not resolve.")
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
) -> Target:
    """
    Turn what the visitor typed into a target that is safe to connect to.

    Raises :class:`TargetRejected` with a message written for a person, since
    it is shown next to the input field.
    """
    scheme, hostname, port = _split(raw)
    exempt = _hostname_allowed(hostname, allowed_hosts)

    if len(hostname) > MAX_TARGET_LENGTH and not hostname.startswith("["):
        raise _reject("That hostname is too long.")

    if not (allow_private or exempt) and (
        hostname in BLOCKED_HOSTNAMES or hostname.endswith(BLOCKED_SUFFIXES)
    ):
        raise _reject("Local and internal addresses cannot be scanned.")

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
                    "link-local network, which this service will not scan."
                )

    return Target(
        hostname=hostname,
        port=port or DEFAULT_PORTS[scheme],
        scheme=scheme,
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
                url, allow_private=allow_private, allowed_hosts=allowed_hosts
            )
        except TargetRejected:
            return False
        return True

    return _allowed
