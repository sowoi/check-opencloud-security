# PYTHON_ARGCOMPLETE_OK
"""
Command line entry point of the bundled scanner.

``check-opencloud-scanner`` has two sub-commands:

``scan``
    Scan one or more hosts and print the result documents as JSON. Useful
    for ad-hoc inspection and for cron jobs that archive scan results.

``serve``
    Run the HTTP scan service. The plugin never talks to it - it always scans
    in process - but the service lets several consumers share one cached
    result, or lets scans run from a host closer to the instance.

``diff``
    Compare two result documents that were archived earlier and say what
    changed between them. The plugin's ``--baseline`` spends the same
    comparison on staying quiet; this spends it on telling somebody what
    happened, which is the question after a change rather than during one.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from .baseline import Baseline, Comparison, Snapshot, snapshot_of
from .completion import enable as enable_completion
from .config import ConfigurationError, load_configuration
from .factory import release_settings_from_config, scanner_settings_from_config
from .refresh_data import RefreshError, refresh_data
from .scanner import ScanError, scan
from .service import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_LISTEN,
    DEFAULT_PORT,
    ScanStore,
    serve,
)
from .wizard import run as run_setup

LOGGER = logging.getLogger("check_opencloud.cli")


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the argument parser for ``check-opencloud-scanner``."""
    parser = argparse.ArgumentParser(
        prog="check-opencloud-scanner",
        description=(
            "Scan OpenCloud instances and print the result as JSON, or run the "
            "scan service that shares one cached result between several "
            "monitoring consumers."
        ),
    )
    parser.add_argument("-c", "--config", help="Path to a configuration file.")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase log verbosity."
    )

    sub = parser.add_subparsers(dest="command", required=True)

    scan_parser = sub.add_parser("scan", help="Scan hosts and print JSON results.")
    scan_parser.add_argument("hosts", nargs="+", help="Hostnames or URLs to scan.")
    scan_parser.add_argument(
        "--timeout", type=int, help="HTTP timeout per request in seconds."
    )
    scan_parser.add_argument(
        "--insecure",
        dest="verify_tls",
        action="store_false",
        default=None,
        help="Do not verify TLS certificates (OpenCloud self-signs by default).",
    )
    scan_parser.add_argument(
        "--ca-file", help="PEM CA bundle used to verify an internal TLS certificate."
    )
    scan_parser.add_argument(
        "--no-extra-checks",
        dest="extra_checks",
        action="store_false",
        default=None,
        help="Only check product, version and headers.",
    )
    scan_parser.add_argument(
        "--no-debug-ports",
        dest="check_debug_ports",
        action="store_false",
        default=None,
        help="Skip probing the OpenCloud debug ports.",
    )
    scan_parser.add_argument("--port", type=int, help="Override the target port.")
    scan_parser.add_argument(
        "--concurrency",
        type=int,
        help="Number of probes to run in parallel (default 1, no multithreading).",
    )
    scan_parser.add_argument(
        "--scheme", choices=("https", "http"), help="Scheme used to reach the instance."
    )
    scan_parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="Do not look up the newest OpenCloud release.",
    )
    scan_parser.add_argument(
        "--compact", action="store_true", help="Print compact instead of indented JSON."
    )

    serve_parser = sub.add_parser("serve", help="Run the HTTP scan service.")
    serve_parser.add_argument("--listen", help=f"Bind address (default {DEFAULT_LISTEN}).")
    serve_parser.add_argument("--port", type=int, help=f"Port (default {DEFAULT_PORT}).")
    serve_parser.add_argument(
        "--cache-ttl", type=int, help="Seconds a scan result is reused."
    )
    serve_parser.add_argument("--token", help="Require this token on API requests.")
    serve_parser.add_argument(
        "--concurrency",
        type=int,
        help="Number of probes to run in parallel per scan (default 1).",
    )
    serve_parser.add_argument(
        "--insecure",
        dest="verify_tls",
        action="store_false",
        default=None,
        help="Do not verify TLS certificates of scanned instances.",
    )

    configure_parser = sub.add_parser(
        "configure",
        help="Ask for the settings interactively and save them as JSON.",
    )
    configure_parser.add_argument(
        "--all",
        dest="include_optional",
        action="store_true",
        default=None,
        help="Go through the optional settings without asking first.",
    )
    configure_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing file without confirming.",
    )
    configure_parser.add_argument(
        "--no-test-scan",
        dest="verify",
        action="store_false",
        default=None,
        help="Do not offer a test scan of the host before saving.",
    )
    refresh_parser = sub.add_parser(
        "refresh-data",
        help="Fetch validated release and advisory data for a monitoring host.",
    )
    refresh_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("~/.cache/check-opencloud-security").expanduser(),
        help="Directory for the two JSON cache files.",
    )
    refresh_parser.add_argument(
        "--schedule-url",
        help=(
            "Lifecycle page or mirror URL. Without it, the reviewed schedule "
            "is read from this project's repository and its signature "
            "verified; an explicit URL is fetched live and unverified."
        ),
    )
    refresh_parser.add_argument(
        "--advisory-url",
        help=(
            "OSV query endpoint or mirror URL. Without it, the reviewed "
            "advisory database is read from this project's repository and "
            "its signature verified; an explicit URL is fetched live and "
            "unverified."
        ),
    )
    refresh_parser.add_argument("--timeout", type=int, default=30)

    diff_parser = sub.add_parser(
        "diff",
        help="Say what changed between two saved result documents.",
        description=(
            "Compare two result documents written by `scan` and report what "
            "changed: findings that appeared, findings that were resolved, and "
            "any movement in the rating, the version and the support horizon. "
            "Reads files only - it never scans anything."
        ),
    )
    diff_parser.add_argument(
        "before", type=Path, help="The earlier result document (JSON)."
    )
    diff_parser.add_argument(
        "after", type=Path, help="The later result document (JSON)."
    )
    diff_parser.add_argument(
        "--format",
        dest="diff_format",
        choices=("text", "markdown", "json", "slack"),
        default="text",
        help=(
            "How to render the comparison: readable lines, a Markdown table, "
            "the structured document the webhook carries, or Slack Block Kit. "
            "Default: text."
        ),
    )
    diff_parser.add_argument(
        "--allow-different-hosts",
        action="store_true",
        help=(
            "Compare documents from two different instances. Off by default: "
            "'did the fix work' is a question about one instance, and two "
            "hosts silently compared is a wrong answer nobody notices."
        ),
    )
    diff_parser.add_argument(
        "--exit-zero",
        action="store_true",
        help=(
            "Always exit 0. Without it, a comparison that got worse exits 1 so "
            "a pipeline can gate on it."
        ),
    )

    enable_completion(parser)
    return parser


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _run_scan(args: argparse.Namespace, scanner_settings, release_settings) -> int:
    exit_code = 0
    documents = []
    for host in args.hosts:
        try:
            documents.append(
                scan(host, settings=scanner_settings, release_settings=release_settings)
            )
        except ScanError as exc:
            LOGGER.error("Scan of %s failed: %s", host, exc)
            documents.append({"host": host, "error": str(exc)})
            exit_code = 1

    payload = documents[0] if len(documents) == 1 else documents
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=False))
    return exit_code


class DiffError(Exception):
    """Raised when two documents cannot honestly be compared."""


def _load_result_document(path: Path) -> dict[str, Any]:
    """
    Read one archived result document.

    ``scan`` prints an array when it was given several hosts, so a
    single-element array is accepted as the document it contains. Anything
    longer is refused rather than guessed at: picking the first of four hosts
    would produce a confident comparison of the wrong instance.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DiffError(f"Cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DiffError(f"{path} is not valid JSON: {exc}") from exc

    if isinstance(payload, list):
        if len(payload) != 1:
            raise DiffError(
                f"{path} holds {len(payload)} result documents. Compare one "
                "instance at a time; split the file first."
            )
        payload = payload[0]
    if not isinstance(payload, dict):
        raise DiffError(f"{path} does not contain a result document.")
    if payload.get("error"):
        raise DiffError(
            f"{path} records a scan that failed ({payload['error']}), so there "
            "is nothing in it to compare."
        )
    if "rating" not in payload:
        raise DiffError(
            f"{path} has no rating, so it is not a result document from "
            "`check-opencloud-scanner scan`."
        )
    return payload


def _document_host(document: dict[str, Any]) -> str:
    """The instance a document describes, however that document names it."""
    return str(document.get("domain") or document.get("host") or "unknown")


def _archived_snapshot(document: dict[str, Any]) -> Snapshot:
    """
    One document as the baseline sees it, but timestamped when it was scanned.

    ``snapshot_of`` stamps the current time, which is right when it is
    recording a run that just happened and wrong here: these two documents were
    written weeks ago, and when they were written is half of what the reader
    wants to know.
    """
    snapshot = snapshot_of(document, waived=document.get("ignored") or ())
    scanned_at = document.get("scannedAt")
    if isinstance(scanned_at, dict) and scanned_at.get("date"):
        return replace(snapshot, recorded_at=str(scanned_at["date"]))
    return snapshot


def _compare_documents(
    before: dict[str, Any], after: dict[str, Any]
) -> Comparison:
    """
    Compare two archived documents with the baseline's own arithmetic.

    Deliberately routed through :class:`Baseline` rather than reimplemented:
    what counts as a new finding here and what counts as one during monitoring
    must be the same question, or the diff would tell an operator something
    their alerts never will.
    """
    baseline = Baseline(path=Path(os.devnull))
    host = _document_host(after)
    baseline.record(host, _archived_snapshot(before))
    return baseline.compare(host, _archived_snapshot(after))


def _run_diff(args: argparse.Namespace) -> int:
    """Report what changed between two saved result documents."""
    try:
        before = _load_result_document(args.before)
        after = _load_result_document(args.after)
    except DiffError as exc:
        LOGGER.error("%s", exc)
        return 2

    if (
        _document_host(before) != _document_host(after)
        and not args.allow_different_hosts
    ):
        LOGGER.error(
            "%s describes %s and %s describes %s. Pass "
            "--allow-different-hosts if comparing two instances is what you "
            "meant.",
            args.before,
            _document_host(before),
            args.after,
            _document_host(after),
        )
        return 2

    comparison = _compare_documents(before, after)

    if args.diff_format == "json":
        print(json.dumps(comparison.as_dict(), indent=2))
    elif args.diff_format == "slack":
        print(json.dumps(comparison.slack_blocks(), indent=2))
    else:
        previous = comparison.previous
        assert previous is not None  # a diff always has both sides
        print(
            f"{_document_host(after)}: {previous.recorded_at or 'unknown'} -> "
            f"{comparison.current.recorded_at or 'unknown'}"
        )
        print(comparison.summary())
        changes = comparison.render(args.diff_format)
        if changes:
            print(changes)

    if args.exit_zero:
        return 0
    return 1 if comparison.regressed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of ``check-opencloud-scanner``."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "diff":
        return _run_diff(args)
    if args.command == "configure":
        return run_setup(
            path=args.config,
            include_optional=args.include_optional,
            force=args.force,
            verify=args.verify,
        )
    if args.command == "refresh-data":
        try:
            paths = refresh_data(
                args.output_dir,
                schedule_url=args.schedule_url,
                advisory_url=args.advisory_url,
                timeout=args.timeout,
            )
        except RefreshError as exc:
            LOGGER.error("%s", exc)
            return 1
        for path in paths:
            print(path)
        return 0

    try:
        config = load_configuration(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
        return 2

    scanner_settings = scanner_settings_from_config(
        config,
        timeout=getattr(args, "timeout", None),
        verify_tls=getattr(args, "verify_tls", None),
        tls_ca_file=getattr(args, "ca_file", None),
        extra_checks=getattr(args, "extra_checks", None),
        check_debug_ports=getattr(args, "check_debug_ports", None),
        port=getattr(args, "port", None) if args.command == "scan" else None,
        scheme=getattr(args, "scheme", None),
        concurrency=getattr(args, "concurrency", None),
    )
    release_settings = release_settings_from_config(config)
    if getattr(args, "no_update_check", False):
        release_settings = release_settings.__class__(
            **{**release_settings.__dict__, "mode": "off"}
        )

    if args.command == "scan":
        return _run_scan(args, scanner_settings, release_settings)

    store = ScanStore(
        scanner_settings=scanner_settings,
        release_settings=release_settings,
        cache_ttl=args.cache_ttl
        or config.get_int("SERVICE_CACHE_TTL", DEFAULT_CACHE_TTL_SECONDS),
    )
    serve(
        store,
        listen=args.listen or config.get("SERVICE_LISTEN") or DEFAULT_LISTEN,
        port=args.port or config.get_int("SERVICE_PORT", DEFAULT_PORT),
        auth_token=args.token or config.get("SERVICE_TOKEN"),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
