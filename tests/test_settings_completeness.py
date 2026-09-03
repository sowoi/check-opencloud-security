"""
A setting exists in more than one place, and this is what notices when it does not.

Adding one tunable touches the settings dataclass, ``factory.py``, the
example configuration file and the flag or subcommand that overrides it. Every
one of those is a separate edit, and the failure when one is missed is silent
in both directions: a field nothing builds keeps its default for ever and
looks like a setting that does not work, and a key documented in the example
file that nothing reads is advice an operator will follow and then wonder
about. Neither shows up in a test of the scanner, because the scanner is
perfectly happy either way.

So these tests derive the three lists rather than keeping one:

* every field of :class:`ScannerSettings` and :class:`ReleaseSettings`, read
  from the dataclass;
* every configuration name the code actually reads, parsed out of the calls
  that read them;
* every key ``config/check-opencloud-security.example.yml`` documents,
  including the commented-out ones, which are documentation as much as the
  live ones are.

A name is honoured under its own name or under the shared one it falls back
to - ``factory.py`` reads ``SCANNER_PROXY`` or ``PROXY``, and the example
file documents the second - so both directions accept either, exactly as the
code does.
"""

from __future__ import annotations

import ast
import re
from dataclasses import fields
from pathlib import Path

from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import ScannerSettings

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_FILE = ROOT / "config" / "check-opencloud-security.example.yml"
FACTORY = ROOT / "opencloud_local_scan" / "factory.py"

# Every module that turns a configuration name into a value.
READING_MODULES = (
    ROOT / "check_opencloud_security.py",
    FACTORY,
    ROOT / "opencloud_local_scan" / "cli.py",
    ROOT / "opencloud_local_scan" / "config.py",
)

# Configuration names are shouted; the dictionary keys these same helpers are
# called with elsewhere in the plugin are not. That is the whole discriminator
# needed to tell 'HOST' from 'productversion'.
CONFIGURATION_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Fields that are set by a caller in this process rather than by anybody's
# configuration, with the reason each one is not a setting. A field added to
# the dataclass and forgotten in 'factory.py' would otherwise look exactly
# like one of these, which is what makes writing the reason down the point.
PROGRAMMATIC_ONLY: dict[str, str] = {
    "ipv6_enabled": (
        "a fact about the host running the scan, not about the instance. The "
        "web application sets it from COS_WEB_IPV6_ENABLED; the plugin runs "
        "where the operator does and has no reason to ask."
    ),
    "max_response_bytes": (
        "a ceiling on what a hostile target can make this process read. An "
        "operator raising it gains nothing and lowering it breaks the scan."
    ),
    "redirect_guard": (
        "a callable, and one only the web application passes: scanning a host "
        "a stranger named is where a redirect has to be asked about."
    ),
    "redirect_pinner": (
        "a callable, for the same reason - it revalidates each hop before it "
        "is followed."
    ),
    "pinned_addresses": (
        "the addresses the web application already validated, handed to the "
        "scan so it dials those and not whatever DNS answers the second time."
    ),
}


def _configuration_names(path: Path) -> set[str]:
    """Every shouted string literal in one module, as a configuration name."""
    return {
        node.value
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and CONFIGURATION_NAME.match(node.value)
    }


def _factory_fields(function: str) -> set[str]:
    """The settings fields one factory function actually builds."""
    tree = ast.parse(FACTORY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            return {
                keyword.arg
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call)
                for keyword in inner.keywords
                if keyword.arg
            }
    raise AssertionError(f"{function} is gone from factory.py")


# A key at the left margin whose value is empty opens a section; anything
# further in belongs to it. A '#' before the key is deliberately allowed: a
# commented-out setting in this file is documentation, not dead text.
_KEY = re.compile(r"^(?P<indent>\s*)(?:#\s*)?(?P<key>[a-z][a-z0-9_]*):(?P<rest>.*)$")


def _documented_names() -> set[str]:
    """Every configuration name the example file documents."""
    names: set[str] = set()
    section: str | None = None
    for line in EXAMPLE_FILE.read_text(encoding="utf-8").splitlines():
        match = _KEY.match(line)
        if not match:
            continue
        rest = match.group("rest").strip()
        # 'secret://name' in the header prose is not a key called 'secret'.
        if rest.startswith("//"):
            continue
        key = match.group("key").upper()
        if not match.group("indent"):
            if not rest:
                section = key
                continue
            section = None
            names.add(key)
        else:
            names.add(f"{section}_{key}" if section else key)
    return names


def _fallback(name: str) -> str:
    """The shared name a section-scoped one falls back to."""
    return name.split("_", 1)[1] if "_" in name else name


def test_every_setting_is_either_configurable_or_named_as_programmatic():
    """
    A field nothing builds is a setting that silently does not work.

    It type-checks, it has a default, and every scan quietly uses that default
    however the operator writes the configuration file - so nothing fails
    except the expectation.
    """
    built = {
        ScannerSettings: _factory_fields("scanner_settings_from_config"),
        ReleaseSettings: _factory_fields("release_settings_from_config"),
    }

    for settings, keywords in built.items():
        for field in fields(settings):
            assert field.name in keywords or field.name in PROGRAMMATIC_ONLY, (
                f"{settings.__name__}.{field.name} is built from nothing: add it "
                "to factory.py, or to PROGRAMMATIC_ONLY with the reason it is "
                "not a setting"
            )


def test_nothing_claims_to_be_programmatic_that_the_factory_builds():
    """
    The list of exceptions has to shrink when a field stops being one.

    Left alone it becomes the place a missing setting hides: the assertion
    above passes for a field named here whether or not the reason is still
    true.
    """
    configurable = _factory_fields("scanner_settings_from_config") | _factory_fields(
        "release_settings_from_config"
    )
    known = {field.name for field in fields(ScannerSettings)} | {
        field.name for field in fields(ReleaseSettings)
    }

    for name, reason in PROGRAMMATIC_ONLY.items():
        assert name in known, f"{name} is no longer a settings field"
        assert name not in configurable, (
            f"{name} is built from configuration now - remove it from "
            "PROGRAMMATIC_ONLY"
        )
        assert reason.strip(), f"{name} needs a reason, not an empty string"


def test_every_configuration_name_the_factory_reads_is_documented():
    """
    A setting nobody documents is one only its author can find.

    The example file is where an operator looks for the name of a thing, and
    the environment variable is derived from it, so a key that never appears
    there has no discoverable spelling at all.
    """
    documented = _documented_names()

    for name in sorted(_configuration_names(FACTORY)):
        assert name in documented or _fallback(name) in documented, (
            f"factory.py reads {name} but "
            f"{EXAMPLE_FILE.name} documents neither it nor {_fallback(name)}"
        )


def test_the_example_file_documents_nothing_that_is_no_longer_read():
    """
    The other direction, and the one that rots quietly.

    A key that was renamed or dropped stays in the example file looking exactly
    like a working one, and an operator sets it and gets the default with no
    warning of any kind.
    """
    read: set[str] = set()
    for module in READING_MODULES:
        read |= _configuration_names(module)

    for name in sorted(_documented_names()):
        assert name in read or _fallback(name) in read, (
            f"{EXAMPLE_FILE.name} documents {name}, which nothing in "
            f"{', '.join(module.name for module in READING_MODULES)} reads"
        )
