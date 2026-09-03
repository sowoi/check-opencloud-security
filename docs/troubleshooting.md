# Troubleshooting

**`UNKNOWN: ... /status.php is unreachable`**
The plugin scans the instance itself with its built-in scanner, so the
monitoring host needs to reach it directly. Check that it can connect, and
remember that OpenCloud's own proxy listens on **9200**, not 443:
`--host opencloud.example.com:9200` or `--port 9200`.

**`UNKNOWN: No OpenCloud instance found at ...`**
`/status.php` did not answer with an OpenCloud status document. Either
something other than OpenCloud is on that address, or a reverse proxy in front
of it does not forward `/status.php`. Run with `--debug` to see the response.

**`UNKNOWN: ... is not an OpenCloud instance: /status.php reports ownCloud`**
ownCloud and Nextcloud serve the same `/status.php` - OpenCloud inherited the
endpoint from them - so the address answered, just not for OpenCloud. Their
releases, advisories and hardening defaults are different, and rating them
against the OpenCloud release schedule would produce a confident answer about
the wrong software, so the scan stops instead of guessing. See [What OpenCloud
is, and how it differs from ownCloud and
Nextcloud](what-is-opencloud.md#why-this-matters-for-a-security-scan) for why
the three are close enough to share an endpoint but not close enough to share
a rating.

**Certificate errors on a fresh instance**
`opencloud init` creates a self-signed certificate. Pass `--insecure` (the
untrusted chain is still reported, it just stops counting against the rating),
or put a reverse proxy with a real certificate in front of the instance.

**The version looks wrong (`0.1.0`)**
That is the hardcoded legacy field, not the release - see
[Reading the version correctly](scanner-checks.md#reading-the-version-correctly). The plugin
reports `legacyVersion` when the instance offered nothing better; upgrading the
instance or letting the plugin reach
`/ocs/v1.php/cloud/capabilities` resolves it.

**Every path is reported as exposed**
Something in front of the instance answers `200` for everything, including the
path the scanner probes to detect exactly that. Check the reverse proxy's
fallback rule.

**Security headers are reported missing, and OpenCloud sends them**
A proxy in front of the instance is stripping them, or answering before
OpenCloud does. [Reverse proxies](reverse-proxy.md) has the header set this
check looks for, written out for nginx, Apache, Caddy, Traefik and HAProxy.

**The check is slow**
Debug-port probing costs up to `debug_port_timeout` seconds per port on a
firewalled host. Use `--no-debug-ports`, lower
`COS_SCANNER_DEBUG_PORT_TIMEOUT`, shorten the port list, or scan in parallel
with `--concurrency` (see [Speeding the scan up](scanner-checks.md#speeding-the-scan-up)).

**`UNKNOWN` on the update check / GitHub rate limit**
Sixty anonymous API requests per hour and IP address are shared with everything
else on that address. Supply `--release-token`, or use `--update-source
bundled` / `pinned` to avoid the network entirely.

**Docker: `permission denied while trying to connect to the Docker socket`**
The user running Icinga2/cron/systemd needs permission to talk to the Docker
daemon - either add it to the `docker` group, or run the check via `sudo`,
depending on your security policy.

**Nothing happens / no output from cron or systemd**
- Cron and systemd units don't have a login shell's `PATH` or environment by
  default - use the full path to `check-opencloud-security` and set
  `COS_HOST` explicitly (see [Scheduling](scheduling.md)).
- Check logs with `journalctl -u check-opencloud-security.service` (systemd)
  or your configured log file (cron, see the example cron file).

**`--warn-on-new` reports OK while something is clearly wrong**
That is what it is for: with a baseline, only findings that are new or worse
than the last run change the status. The full state is still printed, and the
line starting `Suppressed by --warn-on-new:` names the status the run would
otherwise have had. Delete the baseline file to start again, or drop the flag
to see the real state on every run. End of life is the one thing it never
suppresses. See [Reporting only what changed](../README.md#reporting-only-what-changed).

**`--warn-on-new needs --baseline PATH`**
Without a file to remember the last run in, the flag would report "nothing
new" forever. Give it a path the monitoring user can write, e.g.
`/var/lib/check_opencloud/baseline.json`.

**`Baseline could not be written`**
The directory does not exist and cannot be created, or the monitoring user
cannot write there. The verdict on the instance is unaffected - this line is
the whole consequence - but until it is fixed nothing is being remembered, so
`--warn-on-new` will treat every run as the first.

**No note from `--self-update-check`**
It is cached for a day: delete
`${XDG_CACHE_HOME:-~/.cache}/check-opencloud-security/pypi-version.json` to ask
again. It also stays silent when PyPI is unreachable, when a proxy blocks it,
and when the installed version is newer than the published one - which is the
normal state of a source checkout. It never changes the exit code.

**Exit code reference**

| Exit code | Meaning    |
|:----------|:-----------|
| `0`       | OK         |
| `1`       | WARNING    |
| `2`       | CRITICAL   |
| `3`       | UNKNOWN    |

**Still stuck?** Open an issue with the output of `--debug` (tokens are
redacted from it), using the
[wrong finding](https://github.com/sowoi/check-opencloud-security/issues/new?template=wrong_finding.yml)
template if the check reported something you believe is incorrect. Never paste
a production hostname or a credential into a public thread - see
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
