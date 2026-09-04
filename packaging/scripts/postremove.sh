#!/bin/sh
# Runs after the package is removed, for the same one reason postinstall runs:
# systemd should stop offering units whose files have gone.
#
# Nothing here deletes /etc/check-opencloud-security. Whatever an operator put
# in there is theirs, and a removal that takes the configuration with it makes
# a reinstall a surprise.

set -e

if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload >/dev/null 2>&1 || :
fi

exit 0
