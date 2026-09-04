#!/bin/sh
# Runs after the .deb or .rpm is unpacked.
#
# It enables nothing and starts nothing. The units this package ships need
# /etc/check-opencloud-security/env before they can do anything useful, and a
# monitoring check that begins scanning a host nobody named is not a favour.
# All this does is make the unit files visible, so that a `systemctl enable`
# typed straight after the install does not answer "unit not found".

set -e

if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload >/dev/null 2>&1 || :
fi

exit 0
