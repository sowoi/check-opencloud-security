# ADR 0039: The plugin ships as a distribution package built from the wheel

- Status: Accepted
- Date: 2026-09-04

## Context

This plugin is installed on monitoring hosts. That is a narrower kind of
machine than "a computer with Python on it": it is configuration-managed, it
has an inventory somebody audits, and software on it arrives through `apt
install` and `dnf install` because that is the only channel the rest of the
estate uses. Until now the only supported routes were pipx, uv, pip and a
container image - four ways of saying "install a Python package", on hosts
where installing a Python package outside the distribution is often the thing
the operator is not allowed to do.

The gap is not convenience. A pip install on a monitoring host has no entry in
the package database, so it does not appear in the estate's inventory, is not
covered by the unattended-upgrade job that patches everything else, and leaves
whoever inherits the host unable to answer where the check came from.

`webapp/` has an established answer for an artifact that cannot go to PyPI:
`scripts/build_web_bundle.py` assembles a release archive from the tree and the
release workflow attaches it beside the wheel. This is the same shape of
problem - a second artifact, built from what the release already produces - so
it takes the same shape of answer.

## Decision

**The release builds a `.deb` and an `.rpm` from the wheel it already built,
with [nfpm](https://nfpm.goreleaser.com/), and attaches both to the GitHub
release.**

nfpm rather than `dpkg-deb` and `rpmbuild`: it produces both formats from one
recipe on any machine, so the two packages cannot drift apart by being
maintained separately, and the release job does not need a Debian runner and a
RHEL runner to build for Debian and RHEL. `packaging/nfpm.yaml` is that recipe;
`scripts/build_distro_packages.py` assembles the staging tree it reads.

Four choices inside that, each of which could reasonably have gone the other
way:

**The payload is the wheel unpacked into `/usr/lib/check-opencloud-security`,
not files in the system's `site-packages`.** A distribution package that writes
into `site-packages` collides with a `pip install check-opencloud-security` on
the same host, and each would silently half-overwrite the other. A private
directory cannot collide with anything, survives the distribution moving to a
new Python minor version without a rebuild, and lets one `noarch`/`all` package
serve every supported release. The `.dist-info` is kept with it, because that
is what `importlib.metadata` reads for `--version`.

**The two commands on `PATH` are shell launchers that search for an
interpreter.** `python3` is 3.9 on RHEL 9, which packages 3.11 and 3.12 beside
it under their own names, so a hardcoded `#!/usr/bin/python3` would fail on a
host that can run this perfectly well. The launchers try `$COS_PYTHON`, then
`python3`, then `python3.14` down to `python3.10`, version-checking each rather
than trusting the name. When none is usable they exit **3** - Nagios UNKNOWN -
because a plugin that could not run has measured nothing, and must never be
read as an instance that passed.

They run the entry point as a *file* rather than with `python -m`, because
`-m` puts the caller's working directory first on `sys.path` before 3.11. A
check runs from wherever cron happened to be, and a `requests.py` sitting there
must not become the requests a security scan trusts.

**The package configures nothing and enables nothing.** It creates
`/etc/check-opencloud-security/` and leaves it empty; the example
configuration ships as documentation. `config/check-opencloud-security.example.yml`
contains a live `host:` key, and installing it at
`/etc/check-opencloud-security/config.yml` - a path the plugin genuinely reads
- would give every invocation on that host a default target nobody chose. The
four systemd units install disabled for the same reason.

**`--upgrade-self` refuses.** The `.deb` and the `.rpm` drop a `distro-package`
marker beside the payload, and `selfupdate.plan_upgrade` raises before it
reaches the pip fallback, naming `apt` or `dnf`. This is not politeness: pip
would *appear* to succeed. It installs into the user's `site-packages`, which
the launcher never consults, so the operator is told the upgrade worked, has
two versions on the host, and is still running the old one. The marker is a
file rather than a path prefix so that the packaging declares what it is
instead of this module inferring it from where it happens to sit.

## Consequences

A monitoring host can install the check the same way it installs everything
else, and `apt list --installed` answers where it came from. The bundled
release schedule and advisory database - which ship *inside* the package and go
stale - are then refreshed by the same unattended-upgrade job that patches the
rest of the estate, which is a better story than the one pip could tell.

Two packages now have to be built before a release is complete, and the release
job gained a third-party build tool. nfpm is pinned by version and verified
against the digest published with that release; it is a build-time tool that
touches no code and produces archives whose contents are asserted by
`tests/test_distro_packaging.py`.

Neither package is in any distribution's archive, and this record does not
propose putting them there. They are release assets, downloaded and installed
by hand or by a configuration-management run. Getting into Debian proper means
a maintainer, a `debian/` directory built to policy and a release cycle this
project does not follow; that is a different decision, and this one does not
foreclose it.

The plugin directory is the one place the two packages genuinely differ:
Debian's monitoring plugins live under `/usr/lib/nagios/plugins`, the RPM
world's under `%{_libdir}`, which is `/usr/lib64` on every 64-bit build. Each
package ships the symlink its own ecosystem looks for.

## Alternatives considered

**Vendor a virtualenv into the package.** Self-contained, and immune to the
distribution's Python moving. But it makes the package architecture- and
interpreter-specific, so one `all`/`noarch` build becomes a matrix; it ships
copies of `requests` and `certifi` that the distribution's security team does
not patch; and a CA bundle nobody updates is a poor thing to put on a host
whose job is checking TLS. Depending on `python3-requests` and
`python3-certifi` means the distribution patches them.

**Hardcode `#!/usr/bin/python3` and depend on `python3 >= 3.10`.** Simpler, and
correct on Debian and Ubuntu. It makes the RPM uninstallable on RHEL 9, whose
`python3` is 3.9 and which is exactly the kind of long-lived host that runs a
monitoring daemon.

**Generate `debian/` and a `.spec` and build natively.** What a distribution
maintainer would do, and the right answer if these were going into an archive.
Here it doubles the packaging to maintain, needs two build environments, and
buys correctness against policies nothing in this release path checks.

**Leave it at pipx, uv, pip and the container.** The status quo, and the reason
this record exists. It serves everyone whose host policy allows a Python
install outside the distribution, and nobody else.
