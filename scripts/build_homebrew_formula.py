#!/usr/bin/env python3
"""
Generate the Homebrew formula from what PyPI actually published.

The plugin already arrives through ``apt`` and ``dnf`` on the monitoring hosts
it was written for (see ``adr/0039``). Homebrew is the same argument one
platform over: on macOS, and on the Linux workstations that use it, ``brew``
is the package database, and a ``pip install --user`` is absent from it,
invisible to ``brew outdated``, and unanswerable to whoever inherits the
machine. This is the workstation half of that story - somebody trying an
instance from their laptop before wiring the check into Icinga.

A formula pins a *published* artifact by digest, so this reads PyPI rather
than the working tree: the version, the sdist URL and the sha256 of every
runtime dependency all come from the index, and none of them can be known for
a release that has not gone out yet. That is why the default version is the
newest one PyPI has and not the one in ``pyproject.toml`` - a formula for an
unreleased version would name a URL that answers 404.

    python scripts/build_homebrew_formula.py              # newest on PyPI
    python scripts/build_homebrew_formula.py --version 1.20.0
    python scripts/build_homebrew_formula.py --check      # did a release get missed?

``--check`` asks one question - does the committed formula pin the newest
release PyPI has - and deliberately not "would a regeneration produce this
file byte for byte". The second question answers *no* the moment any of the
six dependencies publishes anything, which has nothing to do with this project
and would turn an unrelated upstream release into a failing pull request. The
resource pins move when the formula is regenerated, which is on purpose.

The formula is not Homebrew core's; it belongs in a tap. See
``packaging/README.md`` for what to do with the file this writes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMULA_PATH = ROOT / "packaging" / "homebrew" / "check-opencloud-security.rb"

PACKAGE = "check-opencloud-security"
#: The Ruby class name Homebrew derives from the file name, which it requires
#: to match: hyphens drop out and each word is capitalised.
FORMULA_CLASS = "CheckOpencloudSecurity"

#: The runtime imports, and what those pull in themselves. Deliberately
#: hand-written rather than resolved from the wheel's metadata: `types-requests`
#: is in that metadata and is a stub package with nothing to import, exactly as
#: `packaging/nfpm.yaml` explains for the .deb and the .rpm. Order is the order
#: `brew update-python-resources` would write, which is alphabetical, so a
#: regenerated file stays diffable.
RESOURCES = (
    "certifi",
    "charset-normalizer",
    "idna",
    "PyYAML",
    "requests",
    "urllib3",
)

PYPI_JSON = "https://pypi.org/pypi/{name}/json"
PYPI_JSON_VERSION = "https://pypi.org/pypi/{name}/{version}/json"

#: Homebrew builds a formula's virtualenv against whatever `python@3.x` the
#: formula depends on. Pinned to a version Homebrew ships as a keg rather than
#: to `python3`, which is not a formula name; `requires-python` in
#: `pyproject.toml` is the floor this has to stay above.
PYTHON_FORMULA = "python@3.13"

TIMEOUT_SECONDS = 30


class BuildError(RuntimeError):
    """Raised when the formula cannot be generated from what PyPI answered."""


def _fetch_json(url: str) -> dict:
    """Read one PyPI JSON document."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": f"{PACKAGE}-formula"}
    )
    try:
        # nosec B310 - PYPI_JSON is a constant https URL and `name` only ever
        # comes from RESOURCES or the package name, never from user input.
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise BuildError(f"PyPI answered {exc.code} for {url}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BuildError(f"Could not read {url}: {exc}") from exc


def _sdist(document: dict, name: str, version: str) -> tuple[str, str]:
    """
    The source distribution's URL and sha256 for one release.

    A formula builds from source, so the sdist is the artifact - a wheel would
    hide the build from Homebrew's audit and pin one platform's tag into a
    file that has to work on both macOS and Linux.
    """
    for entry in document.get("urls", []):
        if entry.get("packagetype") == "sdist":
            digest = (entry.get("digests") or {}).get("sha256")
            url = entry.get("url")
            if not digest or not url:
                raise BuildError(f"{name} {version}: the sdist entry has no url or sha256.")
            return url, digest
    raise BuildError(
        f"{name} {version} publishes no source distribution, so a formula "
        "cannot build it from source."
    )


def _release(name: str, version: str | None) -> tuple[str, str, str]:
    """Resolve one package to (version, sdist url, sha256)."""
    if version is None:
        document = _fetch_json(PYPI_JSON.format(name=name))
        version = str((document.get("info") or {}).get("version") or "")
        if not version:
            raise BuildError(f"PyPI named no current version for {name}.")
    else:
        document = _fetch_json(PYPI_JSON_VERSION.format(name=name, version=version))
    url, digest = _sdist(document, name, version)
    return version, url, digest


def _resource_block(name: str, url: str, digest: str) -> str:
    return (
        f'  resource "{name}" do\n'
        f'    url "{url}"\n'
        f'    sha256 "{digest}"\n'
        f"  end\n"
    )


def _description() -> str:
    """
    The one-line summary, from the single place the project writes it.

    Homebrew's audit rejects a `desc` that opens with the formula's own name or
    with an article, and caps it at 80 characters, so the description in
    `pyproject.toml` is trimmed to its first clause rather than reused whole.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^description\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise BuildError("pyproject.toml has no description to build the formula's desc from.")
    return match.group(1).split(" - ")[0].strip()


def render_formula(version: str | None = None) -> str:
    """Build the formula text for one release of the plugin."""
    resolved, url, digest = _release(PACKAGE, version)
    resources = "\n".join(
        _resource_block(name, *_release(name, None)[1:]) for name in RESOURCES
    )
    return f"""# Generated by scripts/build_homebrew_formula.py - do not edit by hand.
#
# Regenerate after every release: the version, the URLs and every sha256 here
# describe artifacts PyPI has already published, and a hand-edit that gets one
# digest wrong fails at `brew install` on somebody else's machine.
class {FORMULA_CLASS} < Formula
  include Language::Python::Virtualenv

  desc "{_description()}"
  homepage "https://github.com/sowoi/{PACKAGE}"
  url "{url}"
  sha256 "{digest}"
  license "GPL-3.0-or-later"

  depends_on "{PYTHON_FORMULA}"

{resources}
  def install
    virtualenv_install_with_resources
  end

  test do
    # Two assertions, because either alone passes for the wrong reason: the
    # first proves the entry point runs at all, the second that the version it
    # reports is the one this formula built rather than another copy on PATH.
    assert_match "{resolved}", shell_output("#{{bin}}/{PACKAGE} --version")

    # A check that cannot reach its instance must still be a check: it exits 3
    # (UNKNOWN), the Nagios code for "measured nothing", rather than crashing
    # or inventing a verdict. `.invalid` is reserved by RFC 2606 and resolves
    # nowhere, so this makes no request to anybody's server during the test.
    output = shell_output(
      "#{{bin}}/{PACKAGE} --host opencloud.invalid --timeout 5 2>&1", 3
    )
    assert_match "UNKNOWN", output
  end
end
"""


def pinned_version() -> str | None:
    """The release the committed formula names, read from its own sdist URL."""
    if not FORMULA_PATH.is_file():
        return None
    match = re.search(
        r"check_opencloud_security-([^/\"]+)\.tar\.gz",
        FORMULA_PATH.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def _check(version: str | None) -> int:
    """Report whether the committed formula is still the newest release."""
    pinned = pinned_version()
    if pinned is None:
        print(
            f"error: {FORMULA_PATH.relative_to(ROOT)} is missing or names no release. "
            "Run: python scripts/build_homebrew_formula.py",
            file=sys.stderr,
        )
        return 1

    latest = version or _release(PACKAGE, None)[0]
    if pinned != latest:
        print(
            f"error: the formula pins {pinned}, but {latest} is published. "
            "Run: python scripts/build_homebrew_formula.py",
            file=sys.stderr,
        )
        return 1

    print(f"{FORMULA_PATH.relative_to(ROOT)} pins {pinned}, the newest release.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=None,
        help="Release to pin. Default: the newest version published on PyPI.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed formula pins an older release than PyPI's newest.",
    )
    args = parser.parse_args(argv)

    if args.check:
        try:
            return _check(args.version)
        except BuildError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    try:
        formula = render_formula(args.version)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    FORMULA_PATH.parent.mkdir(parents=True, exist_ok=True)
    FORMULA_PATH.write_text(formula, encoding="utf-8")
    print(f"Wrote {FORMULA_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
