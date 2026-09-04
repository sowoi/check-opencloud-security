#!/bin/sh
# /usr/bin/check-opencloud-scanner, as installed by the .deb and the .rpm.
#
# The companion to check-opencloud-security.sh - see the comment there for why
# the interpreter is searched for and why the entry point is a script rather
# than `python -m`. The scanner's real entry point is a module inside the
# package, so the payload carries a one-line script that imports it; running
# `opencloud_local_scan/cli.py` directly would break its relative imports.

set -eu

PAYLOAD="/usr/lib/check-opencloud-security"
ENTRYPOINT="$PAYLOAD/check-opencloud-scanner.py"

for candidate in ${COS_PYTHON:-} python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1 || continue
    exec "$candidate" "$ENTRYPOINT" "$@"
done

echo "check-opencloud-scanner: no Python 3.10 or newer found on PATH." >&2
echo "Install one (python3.12 on RHEL 9, python3 elsewhere), or point COS_PYTHON at it." >&2
exit 3
