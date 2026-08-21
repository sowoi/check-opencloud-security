#!/usr/bin/env python3
"""Verify a result export signed by the web application."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from webapp.export_signing import verify_bytes


def main() -> int:
    """Verify one file against an HMAC value copied from the response header."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("signature", help="The X-COS-Signature response header.")
    parser.add_argument(
        "--key-env",
        default="COS_WEB_EXPORT_SIGNING_KEY",
        help="Environment variable containing the signing key.",
    )
    args = parser.parse_args()
    key = os.environ.get(args.key_env)
    if not key:
        parser.error(f"{args.key_env} is not set")
    if not verify_bytes(args.file.read_bytes(), args.signature, key):
        print("signature verification failed", file=sys.stderr)
        return 1
    print("signature verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
