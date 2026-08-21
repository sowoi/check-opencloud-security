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
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

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
    refresh_parser.add_argument("--schedule-url", help="Lifecycle page or mirror URL.")
    refresh_parser.add_argument("--advisory-url", help="OSV query endpoint or mirror URL.")
    refresh_parser.add_argument("--timeout", type=int, default=30)

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


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of ``check-opencloud-scanner``."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

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
