# Scanning from the command line, in one line

If you would rather not paste your address into a website, you do not have to.
The same check the [public scan service](webapp.md) runs is in a published
container image, and one command runs it against your own instance - nothing
installed, nothing signed up for, no rate limit, and no third party learning
which instance you are responsible for.

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

That is the whole thing. It prints the same line a monitoring system would
get:

```text
OK: Server is up to date. No known vulnerabilities.
OpenCloud 7.2.3 on opencloud.example.com, rating: A+, last scanned: 2026-08-25 09:41:12
Release lifecycle: 7.2 (production, track detected), current release
```

The exit code is the Nagios one - `0` OK, `1` WARNING, `2` CRITICAL, `3`
UNKNOWN - so the same line works in a script, a pipeline or a cron job without
anything else around it.

> **Trademark notice.** This project is independent. It is not affiliated
> with, endorsed by or supported by OpenCloud GmbH. "OpenCloud" and all
> related marks belong to their respective owners and are used here only to
> identify the software being checked.

<!-- TOC -->
* [Scanning from the command line, in one line](#scanning-from-the-command-line-in-one-line)
  * [What the image is](#what-the-image-is)
  * [The same scan, as JSON](#the-same-scan-as-json)
  * [Useful variations](#useful-variations)
  * [Make it shorter](#make-it-shorter)
  * [Without Docker](#without-docker)
  * [Where to go next](#where-to-go-next)
<!-- TOC -->


## What the image is

[`okxo/opencloud-scanner`](https://hub.docker.com/r/okxo/opencloud-scanner) is
built from this repository and carries both entry points:

| Entry point | What it does |
|:------------|:-------------|
| `check-opencloud-security` | The Nagios/Icinga plugin: one status line, perfdata, an exit code |
| `check-opencloud-scanner` | The scanner on its own: the whole result document as JSON, or an HTTP service |

The image's default command starts the web application, which is why every
line here passes `--entrypoint`. Pin a version instead of `latest`
(`okxo/opencloud-scanner:1.9`) if you want the command to keep behaving the
same next month.

## The same scan, as JSON

Everything the web interface draws comes from this document - the rating, the
release lifecycle, the advisories, every check and the remediation plan:

```shell
docker run --rm --entrypoint check-opencloud-scanner \
  okxo/opencloud-scanner:latest scan opencloud.example.com
```

Pipe it into `jq` for the parts you care about:

```shell
docker run --rm --entrypoint check-opencloud-scanner \
  okxo/opencloud-scanner:latest scan opencloud.example.com \
  | jq '{rating, version, addresses, failed: [.extraChecks[] | select(.passed | not) | .id]}'
```

`addresses` is the IPv4 and IPv6 the name resolved to when the scan ran - the
same pair the result page shows under **Resolved to**, and worth a second look
when a scan reports something you did not expect: a name pointing at an old
address explains a surprising number of surprising results.

## Useful variations

Explain every finding rather than only naming it:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com --debug
```

Accept a finding you have decided to live with, exactly as the tick boxes on
the website do:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com \
  --ignore-hardening basicAuthDisabled
```

Rate the version against a particular release track rather than the one the
scan infers:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com \
  --release-track lts
```

Scan an instance that is not on the internet - a staging box on your own
network, or one behind a name only your resolver knows:

```shell
docker run --rm --network host --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.internal.example.com
```

The hosted service refuses a private address on purpose; your own machine has
no reason to.

Configure it with environment variables instead of flags, which is easier to
template over a list of hosts - every option has a `COS_` variable, listed in
the [main README](../README.md#environment-variables):

```shell
docker run --rm -e COS_HOST=opencloud.example.com \
  --entrypoint check-opencloud-security okxo/opencloud-scanner:latest
```

Skip the update check when the machine has no internet access, or when you do
not want the release feed contacted at all:

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com --no-update-check
```

## Make it shorter

If you run this often, a shell function turns it into one word:

```shell
# ~/.bashrc or ~/.zshrc
opencloud-scan() {
  docker run --rm --entrypoint check-opencloud-security \
    okxo/opencloud-scanner:latest --host "$1" "${@:2}"
}
```

```shell
opencloud-scan opencloud.example.com --debug
```

## Without Docker

The check is on PyPI and is a normal Python program, so
[`uv`](https://docs.astral.sh/uv/) or `pipx` will run it with no container at
all:

```shell
uvx --from check-opencloud-security check-opencloud-security \
  --host opencloud.example.com
```

```shell
pipx run --spec check-opencloud-security check-opencloud-security \
  --host opencloud.example.com
```

## Where to go next

- [The main README](../README.md) - every option, and what each check means.
- [Scheduling](scheduling.md) - the same command on a timer, with a systemd
  unit or a cron entry.
- [Running the check from CI](ci.md) - gating a pipeline on a field of the
  result document.
- [Checking a fleet of instances](many-instances.md) - one file per instance,
  and alerting only on what changed.
- [The public scan service](webapp.md) - running the web interface yourself,
  if you would like the pages as well as the command.
