# Installing the plugin

Every way of getting `check-opencloud-security` onto a host, and the
monitoring objects that call it once it is there. The
[main README](../README.md#installation) carries the two commands that cover
the common case; this page is everything else - keeping the package current,
shell completion, installing from a checkout, building the image yourself,
and the Icinga2 and Nagios object definitions.

<!-- TOC -->
* [Installing the plugin](#installing-the-plugin)
  * [Using pipx / uv / pip (recommended)](#using-pipx--uv--pip-recommended)
  * [Debian, Ubuntu, RHEL, Fedora (.deb and .rpm)](#debian-ubuntu-rhel-fedora-deb-and-rpm)
  * [Docker](#docker)
  * [Icinga2 / Nagios](#icinga2--nagios)
<!-- TOC -->


## Using pipx / uv / pip (recommended)
The package is published on
[PyPI](https://pypi.org/project/check-opencloud-security/) and installs two
commands onto your `PATH`: `check-opencloud-security` (the check itself) and
`check-opencloud-scanner` (the same scanner as a one-shot JSON tool or a
long-running service).

**[pipx](https://pipx.pypa.io/) - recommended for CLI tools**, keeps the plugin
in its own virtualenv:
```shell
pipx install check-opencloud-security
```

**[uv](https://docs.astral.sh/uv/)** - same idea, faster:
```shell
uv tool install check-opencloud-security
```

**pip** - into the system or an existing virtualenv:
```shell
pip install check-opencloud-security
```

Every release ships a CycloneDX SBOM and a Sigstore provenance attestation;
see [Verifying what you downloaded](../SECURITY.md#verifying-what-you-downloaded)
if you would rather not take the artifact on trust.

To install the latest unreleased changes, point any of them at the repository
instead: `pipx install git+https://github.com/sowoi/check-opencloud-security.git`
(likewise `uv tool install git+https://...` and `pip install git+https://...`).

### Updating
```shell
check-opencloud-security --upgrade-self
```

That works out how the plugin was installed and runs the right command for it.
Use `--upgrade-self=check` to see what it would run without running it. A git
checkout is refused - update that with `git pull`.

The commands it picks between, if you would rather run them yourself:

```shell
pipx upgrade check-opencloud-security          # pipx
pipx upgrade-all                               # ... or every pipx tool at once

uv tool upgrade check-opencloud-security       # uv
uv tool upgrade --all                          # ... or every uv tool at once

pip install --upgrade check-opencloud-security # pip
```

Check what you are running with `check-opencloud-security --version`, and see
[CHANGELOG.md](../CHANGELOG.md) for what changed. A git installation is updated by
re-running the same `install` command with `--force` (pipx/uv) or
`--upgrade --force-reinstall` (pip).

Keeping the package current matters more here than for a plugin that asks a
hosted service: the OpenCloud release schedule and the newest known release
ship *inside* the package (see
[End-of-life detection](../README.md#end-of-life-detection)).

To remove the plugin again: `pipx uninstall check-opencloud-security`,
`uv tool uninstall check-opencloud-security` or
`pip uninstall check-opencloud-security`.

**From a checkout (development or air-gapped install):**

The project uses [uv](https://docs.astral.sh/uv/) as its dependency manager;
`uv.lock` pins every dependency, so an install is reproducible:

```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security

uv sync                                       # create .venv from uv.lock
uv run check-opencloud-security --host opencloud.example.com
```

Without `uv`, install the checkout with pip - the dependencies are declared in
`pyproject.toml`, no separate requirements file is needed:

```shell
pip install .
# or, without installing, run the script in place:
pip install requests PyYAML
python3 check_opencloud_security.py --host opencloud.example.com
```

If some deployment tool of yours insists on a `requirements.txt`, generate one
from the lock file instead of maintaining it by hand:

```shell
uv export --no-dev --no-emit-project --format requirements.txt -o requirements.txt

# without the hashes, if your tooling cannot handle them:
uv export --no-dev --no-emit-project --no-hashes --format requirements.txt -o requirements.txt

# including the development and test dependencies:
uv export --no-emit-project --format requirements.txt -o requirements-dev.txt
```

Such a file is a build artefact - do not commit it, it goes stale the moment
`uv.lock` changes.

### Shell completion
Completion is optional and off by default; it needs one extra dependency:

```shell
pipx install 'check-opencloud-security[completion]'
uv tool install 'check-opencloud-security[completion]'
# or, into an existing install:
pipx inject check-opencloud-security argcomplete
uv tool install --with argcomplete check-opencloud-security --force
```

Then register the two commands with your shell. For **bash**, in `~/.bashrc`:

```shell
eval "$(register-python-argcomplete check-opencloud-security)"
eval "$(register-python-argcomplete check-opencloud-scanner)"
```

For **zsh**, the same two lines in `~/.zshrc`, preceded once by
`autoload -U bashcompinit && bashcompinit`. For **fish**, write the output to a
completion file instead:

```shell
register-python-argcomplete --shell fish check-opencloud-security \
  > ~/.config/fish/completions/check-opencloud-security.fish
```

Completion knows the option names, the values of the options that take a fixed
set (`--webhook-on`, `--release-track`, `--update-source`, `--upgrade-self`),
and - the one that saves real typing - the hardening identifiers accepted by
`--ignore-hardening` and their long, camel-cased names.

Without `argcomplete` installed, nothing is registered and the plugin behaves
exactly as before; it is never a hard dependency of a monitoring plugin.

## Debian, Ubuntu, RHEL, Fedora (.deb and .rpm)

Use this on a monitoring host, where the point is that the check appears in the
package database like everything else on the machine: in the inventory, in the
unattended-upgrade job, and answerable to `apt list --installed`. Every release
carries both packages as assets. They are architecture-independent (`all` /
`noarch`), so one file fits every host.

```shell
VERSION=$(curl -fsSL https://api.github.com/repos/sowoi/check-opencloud-security/releases/latest \
          | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')
BASE=https://github.com/sowoi/check-opencloud-security/releases/download/v$VERSION

# Debian, Ubuntu
curl -fsSLO "$BASE/check-opencloud-security_${VERSION}_all.deb"
sudo apt install "./check-opencloud-security_${VERSION}_all.deb"

# RHEL, Rocky, Alma, Fedora, openSUSE
curl -fsSLO "$BASE/check-opencloud-security-${VERSION}-1.noarch.rpm"
sudo dnf install "./check-opencloud-security-${VERSION}-1.noarch.rpm"
```

Each package has a `.sha256` beside it, and both are covered by the same
Sigstore provenance attestation as the wheel - see
[Verifying what you downloaded](../SECURITY.md#verifying-what-you-downloaded).

### What it installs

| Path | |
|:--|:--|
| `/usr/bin/check-opencloud-security` | the check |
| `/usr/bin/check-opencloud-scanner` | the same scanner as a JSON tool |
| `/usr/lib/nagios/plugins/check_opencloud_security` | symlink to the check (`/usr/lib64/...` on RPM systems) |
| `/usr/lib/check-opencloud-security/` | the code |
| `/etc/check-opencloud-security/` | created empty, and searched for `config.yml` |
| `/usr/lib/systemd/system/` | four units, none of them enabled |
| `/usr/share/doc/check-opencloud-security/` | the example configuration, env file and cron entry |

Because the plugin directory is already populated, an Icinga2 or Nagios
`CheckCommand` using `PluginDir + "/check_opencloud_security"` works with no
further path configuration - see [Icinga2 / Nagios](#icinga2--nagios) below.

### Configuring it

**The package configures nothing on purpose.** The example configuration names
a host that is not yours, and `/etc/check-opencloud-security/config.yml` is a
path the plugin genuinely reads, so installing the example there would give
every invocation on the host a default target nobody chose. Copy what you want:

```shell
sudo cp /usr/share/doc/check-opencloud-security/config.example.yml \
        /etc/check-opencloud-security/config.yml

sudo cp /usr/share/doc/check-opencloud-security/env.example \
        /etc/check-opencloud-security/env      # for the systemd units
```

`check-opencloud-security --configure` asks the same questions interactively.

The units ship disabled and need that `env` file first:

```shell
sudo systemctl enable --now check-opencloud-security.timer
sudo systemctl enable --now check-opencloud-security-refresh.timer
```

The second one keeps the bundled release schedule and advisory database
current, which matters more here than it looks: both ship *inside* the package
(see [End-of-life detection](../README.md#end-of-life-detection)).

### Updating and removing it

Through `apt` and `dnf`, like anything else on the host. `--upgrade-self`
detects a distribution package and refuses rather than letting pip install a
second copy beside it - a copy the installed commands would never run.

```shell
sudo apt install --only-upgrade check-opencloud-security   # or: dnf upgrade
sudo apt remove check-opencloud-security                   # or: dnf remove
```

Removal leaves `/etc/check-opencloud-security/` alone: whatever you put there
is yours.

### The interpreter it uses

The installed commands are small shell launchers that find a Python 3.10 or
newer for themselves - `$COS_PYTHON` first, then `python3`, then `python3.14`
down to `python3.10`, checking the version of each rather than trusting the
name. This is why the RPM does not demand `python3 >= 3.10`: RHEL 9 answers 3.9
to `python3` and packages 3.11 and 3.12 beside it, and a versioned dependency
would refuse to install on a host that runs this perfectly well.

If nothing suitable is found, the check exits **3 (UNKNOWN)** rather than
reporting a verdict it never measured. Point `COS_PYTHON` at an interpreter to
settle it:

```shell
sudo dnf install python3.12
COS_PYTHON=/usr/bin/python3.12 check-opencloud-security --host opencloud.example.com
```

### Building the packages yourself

They are built from the wheel, so a checkout produces the same thing a release
does. It needs [nfpm](https://nfpm.goreleaser.com/install/) on `PATH`:

```shell
uv build                                        # the wheel first
python scripts/build_distro_packages.py         # both, into distro-packages/
python scripts/build_distro_packages.py --packager deb
```

The layout, the dependencies and everything else the packages declare live in
[`packaging/nfpm.yaml`](../packaging/nfpm.yaml). Why they are built this way is
[ADR 0039](../adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md).

## macOS and Linux workstations (Homebrew)

Use this on a laptop rather than on a monitoring host - somebody trying an
instance by hand before wiring the check into Icinga. The argument is the one
the `.deb` and the `.rpm` make one platform over: `brew` is the package
database on these machines, and a `pip install --user` is absent from it and
invisible to `brew outdated`.

```shell
brew install sowoi/tap/check-opencloud-security
check-opencloud-security --host opencloud.example.com
```

The formula lives in a tap rather than in Homebrew core, which has notability
requirements this project does not claim to meet. `brew upgrade` keeps it
current; `--upgrade-self` deliberately refuses on a Homebrew installation and
says so, because pip would write into the Cellar and the next `brew`
operation would quietly undo it.

The formula itself is generated from what PyPI published, by
[`scripts/build_homebrew_formula.py`](../scripts/build_homebrew_formula.py) -
see [`packaging/README.md`](../packaging/README.md#homebrew) if you are
maintaining the tap rather than installing from it.

## Docker
Use this if you would rather not install anything on the host. The image also
ships the scan service (see
[Running the scanner as a service](../README.md#running-the-scanner-as-a-service)).

The published image carries both entry points, so a check is one command with
nothing built and nothing installed:
```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

That one line, its JSON variant and the useful flags around it are collected in
[Scanning from the command line, in one line](docker-oneliner.md). The
image's default command starts the web application, which is why the plugin is
selected with `--entrypoint`.

Build the image yourself instead when you want to run your own checkout.
Everything Docker-related lives in [`docker/`](../docker/), and the build context
is the repository root:
```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security
docker build -f docker/Dockerfile -t check-opencloud-security .
```

Run a check:
```shell
docker run --rm check-opencloud-security --host opencloud.example.com
```

Or configure it entirely through [environment variables](../README.md#environment-variables)
(handy since you don't need to edit the `docker run` command per host):
```shell
docker run --rm -e COS_HOST=opencloud.example.com check-opencloud-security
```

The image carries a `HEALTHCHECK` that verifies the image rather than any
instance: that the package imports and that the release schedule and bundled
advisory database parse. It needs no network, so it also passes on an
air-gapped host. It is there for the long-running scan service; a one-shot
check container exits before Docker gets round to running it. The service in
`docker/docker-compose.monitoring.yml` overrides it with the HTTP `/healthz`
probe, which is the
more useful check once something is actually listening.

The check container needs no network ports, but it does need to reach the
OpenCloud instance itself. If the
instance is only reachable on the Docker host's own network, add
`--network host` or the appropriate `--add-host`. It runs as an unprivileged
`nagios` user and exits with the same Nagios-style codes (`0`/`1`/`2`/`3`) as
the native script, so it can be dropped straight into any monitoring pipeline
that already understands `docker run` as a check command (see
[Icinga2 / Nagios](#icinga2--nagios) and [Icinga Director](icinga-director.md)
below).

If you'd rather not build locally, push the built image to your own registry
(e.g. `docker tag check-opencloud-security registry.example.com/check-opencloud-security`
followed by `docker push ...`) and reference that image on your monitoring
host(s) instead.

## Icinga2 / Nagios
- If you installed the package with pipx/uv/pip, locate the installed `check-opencloud-security` executable (e.g. `which check-opencloud-security`) and reference that path in `PluginDir`, or copy/symlink it into your plugin folder (usually `/usr/lib/nagios/plugins/`).
- If you're running the script manually, put `check_opencloud_security.py` into your plugin folder instead.
- Create a new custom command:

```
object CheckCommand "check_opencloud_security" {
    import "plugin-check-command"
    command = [ PluginDir + "/check-opencloud-security" ]

    arguments += {
        "--host" = {
            description = "OpenCloud hostname, IP or URL"
            required = true
            value = "$address$"
        }

        "--port" = {
            description = "Port the instance listens on, e.g. 9200 (optional)"
            value = "$opencloud_port$"
        }

        "--proxy" = {
            description = "HTTP/HTTPS proxy (optional)"
            required = false
        }

        "--insecure" = {
            description = "Do not verify the instance's TLS certificate (optional)"
            set_if = "$opencloud_insecure$"
        }

        "--no-debug-ports" = {
            description = "Skip probing the OpenCloud debug ports (optional)"
            set_if = "$opencloud_no_debug_ports$"
        }

        "--debug" = {
            description = "Enable debugging output (optional)"
            set_if = "$opencloud_debug$"
        }

        "--warning" = {
            description = "Rating (0-5) at or below which the check warns (optional)"
            value = "$opencloud_warning$"
        }

        "--critical" = {
            description = "Rating (0-5) at or below which the check is critical (optional)"
            value = "$opencloud_critical$"
        }

        "--check-hardening" = {
            description = "Also check hardening measures and security headers (optional)"
            set_if = "$opencloud_check_hardening$"
        }

        "--update-source" = {
            description = "Where the newest release is looked up: auto, feed, pinned, bundled, off"
            value = "$opencloud_update_source$"
        }
    }
}
```

- Create a new Service object.

```
object Service "Service: OpenCloud Security Scan" {
   import               "generic-service"
   host_name =          "YOUR OPENCLOUD HOST"
   check_command =      "check_opencloud_security"
   check_interval = 24h
}
```

The scan only talks to your own instance, so there is no external rate limit to
respect and a shorter interval than 24h is technically fine. A full scan does
issue a few dozen requests plus the debug-port probes, though, so an hourly
check is a sensible floor - and if the [update check](../README.md#update-check) uses the
GitHub feed, keep it at a few times a day or supply a token.

### Using the Docker image instead

If you installed via [Docker](#docker), point the `CheckCommand` at `docker`
and let it run the container on demand instead of a local binary:

```
object CheckCommand "check_opencloud_security_docker" {
    import "plugin-check-command"
    command = [ "/usr/bin/docker" ]

    arguments += {
        "run" = {
            order = -5
            value = "run"
        }
        "--rm" = {
            order = -4
            value = "--rm"
        }
        "image" = {
            order = -3
            skip_key = true
            value = "check-opencloud-security"
        }
        "--host" = {
            description = "OpenCloud hostname, IP or URL"
            required = true
            value = "$address$"
        }
        "--port" = {
            description = "Port the instance listens on, e.g. 9200 (optional)"
            value = "$opencloud_port$"
        }
        "--proxy" = {
            description = "HTTP/HTTPS proxy (optional)"
            required = false
        }
        "--insecure" = {
            description = "Do not verify the instance's TLS certificate (optional)"
            set_if = "$opencloud_insecure$"
        }
        "--debug" = {
            description = "Enable debugging output (optional)"
            set_if = "$opencloud_debug$"
        }
        "--warning" = {
            description = "Rating (0-5) at or below which the check warns (optional)"
            value = "$opencloud_warning$"
        }
        "--critical" = {
            description = "Rating (0-5) at or below which the check is critical (optional)"
            value = "$opencloud_critical$"
        }
        "--check-hardening" = {
            description = "Also check hardening measures and security headers (optional)"
            set_if = "$opencloud_check_hardening$"
        }
    }
}
```

This assumes the `check-opencloud-security` image has already been built (or
pulled) on the Icinga2 host, that the user running the Icinga2 daemon has
permission to talk to the Docker socket, and that the container can reach the
OpenCloud instance.
