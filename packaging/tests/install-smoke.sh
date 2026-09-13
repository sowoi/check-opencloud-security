#!/bin/sh
# Install the .deb or the .rpm the way a monitoring host would, run it, and
# remove it again. Run inside a clean distribution container, from the
# directory holding the packages:
#
#   docker run --rm -v "$PWD/distro-packages:/pkgs" -w /pkgs debian:12 \
#       sh install-smoke.sh deb
#
# A package that builds can still fail here: a dependency name the
# distribution does not carry, a launcher that cannot find its payload, a
# maintainer script that exits non-zero as root, or a removal that leaves the
# payload behind. release-dry-run.yml runs this on every pull request.

set -eu

packager="${1:?usage: install-smoke.sh deb|rpm}"

case "$packager" in
    deb)
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq ./check-opencloud-security_*_all.deb >/dev/null
        plugin=/usr/lib/nagios/plugins/check_opencloud_security
        ;;
    rpm)
        dnf install -y -q ./check-opencloud-security-*.noarch.rpm >/dev/null
        plugin=/usr/lib64/nagios/plugins/check_opencloud_security
        ;;
    *)
        echo "unknown packager: $packager" >&2
        exit 2
        ;;
esac

# Both commands on PATH, and the path Icinga and Nagios are configured with.
check-opencloud-security --version
"$plugin" --version
check-opencloud-scanner --help >/dev/null
echo "installed and runs"

case "$packager" in
    deb) apt-get remove -y -qq check-opencloud-security >/dev/null ;;
    rpm) dnf remove -y -q check-opencloud-security >/dev/null ;;
esac

test ! -e /usr/bin/check-opencloud-security
test ! -e /usr/lib/check-opencloud-security/check_opencloud_security.py
echo "removed cleanly"
