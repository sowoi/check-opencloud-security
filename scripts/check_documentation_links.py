#!/usr/bin/env python3
"""Verify that the OpenCloud links this repository documents still work.

Almost everything this project knows about OpenCloud is anchored in a handful
of links: the release lifecycle page the schedule is generated from, the
security advisories, the source files that prove a hardening flag is
hardcoded, the installation guides the deployment documentation points at.
None of that is under our control. When OpenCloud reorganises its
documentation those links rot silently, and a plugin that explains a finding
with a dead link is a plugin nobody can act on.

So the links are checked on every merge into ``main``:

    python scripts/check_documentation_links.py            # check and fail
    python scripts/check_documentation_links.py --warn-only # report only
    python scripts/check_documentation_links.py --list      # no network

Only OpenCloud's own hosts are checked (see :data:`OPENCLOUD_HOSTS`), because
those are the ones whose accuracy this project is responsible for. A link is
out of date when it is broken: a 4xx, a 5xx or a transport error that
survives the retries. A
temporary redirect is normal and passes.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

REPO_ROOT = Path(__file__).resolve().parent.parent

USER_AGENT = "check-opencloud-security link checker (+https://github.com/sowoi/check-opencloud-security)"

DEFAULT_TIMEOUT = 20
DEFAULT_ATTEMPTS = 3

# The hosts this project documents and therefore has to keep accurate. A link
# to any other site is somebody else's business and is left alone, which also
# keeps the run short enough to sit in front of a merge.
OPENCLOUD_HOSTS: tuple[str, ...] = (
    "opencloud.eu",
    "docs.opencloud.eu",
    "github.com/opencloud-eu",
    "raw.githubusercontent.com/opencloud-eu",
    "hub.docker.com/r/opencloudeu",
    "api.github.com/repos/opencloud-eu",
)

# Not documentation. The webfinger namespace URIs OpenCloud puts in its
# responses are identifiers that happen to look like addresses, and a
# placeholder ending in '...' is an example of a shape, not a page.
EXCLUDED_HOSTS: frozenset[str] = frozenset({"webfinger.opencloud.eu"})

# Where documentation and configuration live. Binary files and the virtual
# environment are not walked at all.
SEARCHED_SUFFIXES: frozenset[str] = frozenset(
    {".md", ".py", ".yml", ".yaml", ".json", ".toml", ".html", ".css", ".js", ".cfg", ".txt"}
)

# The test suite is full of addresses that only look like documentation: a
# fixture's payload, a deliberately dead URL asserted against. None of it is
# published, so none of it is checked.
SKIPPED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        "tests",
    }
)

# Answers that say "not to you, not right now" rather than "not here": an
# anonymous GitHub API call is rate limited, and bot protection answers 403 to
# anything without a browser. Neither means the link rotted, and failing a
# merge over one would teach everybody to ignore this check.
INCONCLUSIVE_STATUS: frozenset[int] = frozenset({401, 403, 429})

_URL = re.compile(r"https?://[^\s\"'`<>)\]}\\]+")

# Trailing characters that belong to the prose, not to the address.
_TRAILING = ".,;:!?*_"


@dataclass(frozen=True)
class Link:
    """One URL, and where it is written down."""

    url: str
    source: str

    def __str__(self) -> str:
        return f"{self.url} ({self.source})"


@dataclass(frozen=True)
class Problem:
    """One link that is not quite what the documentation says it is."""

    link: Link
    detail: str
    broken: bool
    """Broken fails the run; a redirect is only worth mentioning.

    OpenCloud's front page redirects to a language version, so treating every
    redirect as an error would fail the workflow for a link that is perfectly
    current - and a workflow that always fails is a workflow nobody reads.
    """


def is_opencloud_link(url: str) -> bool:
    """Whether a URL points at something OpenCloud publishes."""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        # Something that only looks like a URL - a placeholder in an example,
        # a fragment of a regular expression - is not a documented link.
        return False
    host = parsed.netloc.lower()
    host = host.removeprefix("www.")
    if host in EXCLUDED_HOSTS:
        return False
    location = f"{host}{parsed.path}"
    return any(
        host == entry or host.endswith("." + entry) or location.startswith(entry + "/")
        for entry in OPENCLOUD_HOSTS
    )


def clean(url: str) -> str:
    """Strip the punctuation a URL picks up from the sentence around it."""
    cleaned = url.rstrip(_TRAILING)
    # Markdown wraps links in parentheses, so a closing one that has no
    # opening partner inside the URL belongs to the markup.
    while cleaned.endswith(")") and cleaned.count("(") < cleaned.count(")"):
        cleaned = cleaned[:-1].rstrip(_TRAILING)
    return cleaned


def _files(root: Path) -> Iterator[Path]:
    """Every text file worth searching, in a stable order."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SEARCHED_SUFFIXES:
            continue
        if any(part in SKIPPED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        yield path


def collect_links(root: Path = REPO_ROOT) -> list[Link]:
    """Find every documented OpenCloud link, deduplicated by URL."""
    found: dict[str, Link] = {}
    for path in _files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _URL.findall(text):
            if match.endswith("..."):
                # A placeholder showing the shape of an address, not one.
                continue
            url = clean(match)
            if url and is_opencloud_link(url) and url not in found:
                found[url] = Link(url=url, source=str(path.relative_to(root)))
    return [found[url] for url in sorted(found)]


def check(
    link: Link, *, timeout: int = DEFAULT_TIMEOUT, attempts: int = DEFAULT_ATTEMPTS
) -> Problem | None:
    """Return what is wrong with a link, or None when it is fine.

    A transport error is retried, because a workflow that cries wolf whenever
    the network hiccups gets muted, and a muted check protects nothing. An
    HTTP status is an answer and is not retried.
    """
    detail: str | None = None
    for attempt in range(max(attempts, 1)):
        detail, broken = _check_once(link.url, timeout=timeout)
        if detail is None:
            return None
        if not broken or detail.startswith("HTTP ") or attempt + 1 == max(attempts, 1):
            return Problem(link=link, detail=detail, broken=broken)
    return Problem(link=link, detail=detail or "unknown", broken=True)


def _check_once(url: str, *, timeout: int) -> tuple[str | None, bool]:
    """One request, without retries: (what is wrong, is it broken)."""
    if not url.startswith(("http://", "https://")):
        return "not an HTTP URL", True
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        # GET rather than HEAD: several documentation hosts answer HEAD with
        # 403 or 405 while serving the page perfectly well.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - scheme validated above
            final = response.geturl()
    except urllib.error.HTTPError as exc:
        if exc.code in INCONCLUSIVE_STATUS:
            return f"HTTP {exc.code}, which says nothing about the link", False
        return f"HTTP {exc.code}", True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"unreachable: {exc}", True
    moved = _redirect_problem(url, final)
    return (moved, False) if moved else (None, False)


def _redirect_problem(url: str, final: str) -> str | None:
    """Describe a redirect that changed where the content lives.

    urllib follows redirects transparently, so the evidence is the address it
    ended up at. A change of scheme, host or path means the documentation
    names an address that is no longer the real one; a trailing slash or a
    query string added along the way does not.
    """
    if not final or final == url:
        return None
    left = urllib.parse.urlsplit(url)
    right = urllib.parse.urlsplit(final)
    if (left.scheme, left.netloc, left.path.rstrip("/")) == (
        right.scheme,
        right.netloc,
        right.path.rstrip("/"),
    ):
        return None
    return f"redirected to {final}"


def report(problems: Iterable[Problem], stream: TextIO | None = None) -> None:
    """Print the links that need attention, one per line."""
    target = stream if stream is not None else sys.stderr
    for problem in problems:
        print(f"  {problem.link.url}", file=target)
        print(f"      {problem.detail} - documented in {problem.link.source}", file=target)


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository to search.")
    parser.add_argument(
        "--list", action="store_true", help="List the links that would be checked and stop."
    )
    parser.add_argument(
        "--warn-only", action="store_true", help="Report problems but exit successfully."
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat a redirect as out of date as well."
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    args = parser.parse_args(argv)

    links = collect_links(args.root)
    if args.list:
        for link in links:
            print(link)
        return 0

    print(f"Checking {len(links)} documented OpenCloud links")
    problems = [
        problem
        for link in links
        if (problem := check(link, timeout=args.timeout, attempts=args.attempts)) is not None
    ]
    broken = [problem for problem in problems if problem.broken or args.strict]
    moved = [problem for problem in problems if not problem.broken and not args.strict]

    if moved:
        print(f"{len(moved)} documented OpenCloud link(s) need a second look:")
        report(moved, sys.stdout)

    if not broken:
        print("Every documented OpenCloud link still resolves.")
        return 0

    print(f"{len(broken)} documented OpenCloud link(s) are out of date:", file=sys.stderr)
    report(broken)
    return 0 if args.warn_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
