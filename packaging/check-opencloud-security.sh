#!/bin/sh
# /usr/bin/check-opencloud-security, as installed by the .deb and the .rpm.
#
# The package is the PyPI wheel unpacked into one private directory rather than
# a virtualenv or a copy in the system site-packages: there is nothing to
# rebuild when the distribution's interpreter moves, and nothing that collides
# with a `pip install check-opencloud-security` on the same host.
#
# The plugin module is run as a script rather than with `python -m`, because
# `-m` puts the *caller's* working directory first on `sys.path` before 3.11.
# A check runs from wherever cron or the monitoring daemon happened to be, and
# a `requests.py` sitting there must not become the requests this scan trusts.
# Running the file puts its own directory first instead.
#
# The interpreter is searched for rather than hardcoded, because the one that
# answers to `python3` is not always new enough: Debian 12 and Ubuntu 22.04
# are fine, while RHEL 9 answers 3.9 and carries 3.11 and 3.12 beside it under
# their own names. COS_PYTHON overrides the search.

set -eu

PAYLOAD="/usr/lib/check-opencloud-security"
ENTRYPOINT="$PAYLOAD/check_opencloud_security.py"

for candidate in ${COS_PYTHON:-} python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1 || continue
    exec "$candidate" "$ENTRYPOINT" "$@"
done

# Exit 3 is Nagios UNKNOWN. A plugin that could not run has measured nothing,
# and must never be read as an instance that passed or failed.
echo "check-opencloud-security: no Python 3.10 or newer found on PATH." >&2
echo "Install one (python3.12 on RHEL 9, python3 elsewhere), or point COS_PYTHON at it." >&2
exit 3
