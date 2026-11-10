# The `check-opencloud-scanner` command

The package installs two commands.

- **`check-opencloud-security`** is the monitoring plugin. It scans an
  instance, *judges* the result against thresholds and exits `0`-`3` for
  Nagios or Icinga. Its flags are in the [CLI option reference](cli-reference.md).
- **`check-opencloud-scanner`** is everything else. It gives you the raw
  result document, compares two of them, summarises a fleet of them,
  explains a finding, reviews the
  configured waivers, refreshes the reference data, and runs the scan service. It never applies a warning or
  critical threshold.

This page is the reference for the second one.

<!-- TOC -->
* [The `check-opencloud-scanner` command](#the-check-opencloud-scanner-command)
  * [Global options](#global-options)
  * [`scan` - print the result document](#scan---print-the-result-document)
  * [`diff` - what changed between two saved results](#diff---what-changed-between-two-saved-results)
  * [`fleet` - a dashboard from saved results](#fleet---a-dashboard-from-saved-results)
  * [`explain` - what a finding means and how to fix it](#explain---what-a-finding-means-and-how-to-fix-it)
  * [`review-waivers` - waivers that need attention](#review-waivers---waivers-that-need-attention)
  * [`refresh-data` - update the release schedule and advisories](#refresh-data---update-the-release-schedule-and-advisories)
  * [`serve` - the scan service](#serve---the-scan-service)
  * [`configure` - write a configuration file](#configure---write-a-configuration-file)
  * [Exit codes](#exit-codes)
<!-- TOC -->


## Global options

These go **before** the subcommand:

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml -v scan opencloud.example.com
```

| Option | What it does |
|:--|:--|
| `-c, --config` | Configuration file. `.json` is read as JSON, anything else as YAML |
| `-v, --verbose` | More log output on stderr: `-v` for info, `-vv` for debug |

Without `-c`, the first file that exists is used, in this order:

1. `./.env.json`
2. `./check-opencloud-security.yml`
3. `./check-opencloud-security.yaml`
4. `~/.config/check-opencloud-security/.env.json`
5. `/etc/check-opencloud-security/.env.json`
6. `/etc/check-opencloud-security/config.yml`
7. `/etc/check-opencloud-security/config.yaml`

This is the same search the plugin does. `COS_` environment variables apply
on top of the file, and flags on top of both. See
[Secrets in the configuration](configuration.md).

## `scan` - print the result document

```bash
check-opencloud-scanner scan opencloud.example.com
check-opencloud-scanner scan --compact opencloud.example.com > result.json
check-opencloud-scanner scan cloud1.example.com cloud2.example.com | jq '.[].rating'
```

It prints the scanner's JSON result document: the rating and its
explanation, the lifecycle, every check, TLS and advisory matches, all with
camelCase keys. It prints no verdict. One host prints one object. Several
hosts print an array, in the order given.

| Option | What it does |
|:--|:--|
| `--compact` | Print the document on one line instead of indented |
| `--scheme {https,http}` | How to reach the instance |
| `--port` | Override the port |
| `--timeout` | Seconds allowed for each request |
| `--insecure` | Do not verify the instance's TLS certificate |
| `--ca-file` | PEM CA bundle to verify an internal certificate with |
| `--no-extra-checks` | Only product, version and headers |
| `--no-debug-ports` | Skip probing OpenCloud's debug ports |
| `--all-addresses` | Repeat the key checks on every address the name resolves to |
| `--concurrency` | Probes run in parallel within one scan. Default `1` |
| `--no-update-check` | Do not look up the newest OpenCloud release |

Waivers, the release track and the advisory sources come from the
configuration file or environment, exactly as for the plugin.

An instance that cannot be scanned does not abort the run. Its entry becomes
`{"host": ..., "error": ...}`, the other hosts are still scanned, and the
command exits `1`:

```json
{
  "host": "opencloud.example.com",
  "error": "https://opencloud.example.com/status.php is unreachable"
}
```

The document is what [CI pipelines](ci.md) and [Prometheus](prometheus.md)
consume, and what `diff` below compares. The
[scanner library README](../opencloud_local_scan/README.md) describes its
fields.

## `diff` - what changed between two saved results

```bash
check-opencloud-scanner scan opencloud.example.com > before.json
# ... change something on the instance ...
check-opencloud-scanner scan opencloud.example.com > after.json
check-opencloud-scanner diff before.json after.json
```

```text
opencloud.example.com: 2026-09-15 17:42:21.524291 -> 2026-09-15 17:42:22.737103
New since last run (15): check:debugEndpoint:/config, check:debugEndpoint:/debug/pprof/, check:debugEndpoint:/metrics, check:demoUsersDisabled, check:directoryListing (+10 more)
Security check: + debugEndpoint:/config
Security check: + demoUsersDisabled
...
Hardening: + Content-Security-Policy
...
Rating: A+ (5) -> D (2)
```

It reads two files and scans nothing. `+` marks a finding that appeared, `-`
one that was resolved, and `~` one that is still open but is now weighted
differently. It also reports any movement in the rating, the version and the
support horizon. It answers "did the fix work?" and "what did the upgrade
change?" without keeping a baseline file. For a check that remembers its last
run by itself, see [Reporting only what changed](baseline.md).

| Option | What it does |
|:--|:--|
| `--format text` | Readable lines, as above. The default |
| `--format markdown` | A Markdown table, for a ticket or a pull request comment |
| `--format side-by-side` | Both scans as two columns, one finding per row |
| `--format json` | The structured comparison the plugin's webhook carries |
| `--format slack` | Slack Block Kit JSON |
| `--category NAME` | Show one area only. Repeatable |
| `--all-findings` | List every finding measured, not only the ones that moved |
| `--exit-zero` | Always exit `0` |
| `--allow-different-hosts` | Compare results from two different instances |

### Severity, finding by finding

Every comparison ends with the failing findings counted by severity:

```text
~ exposed:/config/opencloud.yaml [exposure]: severity high -> critical
Failing by severity: critical 0 -> 1, high 1 -> 1, medium 0 -> 1, low 1 -> 0
```

The `~` line is the one a comparison of two lists of names cannot produce. A
check that was failing at `high` and is failing at `critical` never entered or
left the set of failing checks, so [the baseline](baseline.md) is silent about
it - correctly, because by its definition nothing regressed - while the
rating it caps has dropped a grade. The severity on each side comes from the
documents themselves, never from today's catalogue: a scan archived last
month is evidence about last month.

A waived finding is counted here and rendered as `waived`, because a waiver is
a decision to not be alerted and not a claim the finding is gone.

### Side by side

```bash
check-opencloud-scanner diff before.json after.json --format side-by-side
```

```text
opencloud.example.com
Rating: A+ (5) -> C (3)
Lifecycle: EOL: False -> True
Version: 3.4.0 -> 3.3.0

Finding                           2026-09-15T17:42:21+00:00  2026-09-22T09:03:11+00:00
--------------------------------  -------------------------  -------------------------
+ CVE-2026-0001                   not listed                 FAIL high
+ cspWithoutUnsafeInline          ok                         FAIL medium
~ exposed:/config/opencloud.yaml  FAIL high                  FAIL critical
- Referrer-Policy                 FAIL low                   ok
```

Each row states both sides, so a reader does not have to rebuild them from a
list of changes. `--all-findings` adds the findings that did not move, which
turns the view from "what changed" into "what the two scans found".

`not measured` and `not listed` are different answers and are never merged: a
check absent from a document was not performed ([ADR
0064](../adr/0064-a-scan-records-what-it-did-not-measure.md)), while an
advisory absent from one did not match that version. Neither is a pass.

### One area at a time

`--category` narrows the comparison, and takes a value from either of two
namespaces:

- **a finding category** - `cookies`, `authentication`, `sharing`, `exposure`,
  `embedding`, `lifecycle`, `proxy`, `headers`, `transport`, `advisory` -
  keeps only the findings about that area of the instance.
- **a change category** - `instance`, `referenceData`, `scanner`, `policy`,
  `unknown` - keeps only the explanation of *why* the two scans differ. See
  [Reference data](reference-data.md) for why a grade can move without the
  instance changing at all.

```bash
check-opencloud-scanner diff before.json after.json --category transport
check-opencloud-scanner diff before.json after.json --category instance
```

Each namespace is filtered only when a value for it is given, so
`--category transport` leaves the explanation intact and `--category instance`
leaves the findings intact. The flag is repeatable, and an unknown value is
refused with exit `2` rather than silently showing nothing - a typo that
printed an empty comparison would read as "nothing changed".

A filtered explanation omits the `[limitation]` lines, because those qualify
the whole comparison rather than one category of it.

**It exits `1` when the second result is worse**, so a pipeline can gate on
it. It exits `0` when nothing got worse, including when findings were only
resolved. `--exit-zero` turns the gate off.

It exits `2` without comparing results in either of these cases:

- **the two files describe different instances.** To check whether a fix
  worked, compare scans of the same instance. Pass `--allow-different-hosts`
  if you intend to compare different hosts.
- **a file is not a result document** from `scan`. For example, it has no
  rating, or it is the error entry of an instance that could not be scanned.

## `fleet` - a dashboard from saved results

```bash
today="/var/lib/opencloud-reports/$(date +%F)"
mkdir -p "$today"
for host in cloud1.example.com cloud2.example.com cloud3.example.com; do
  check-opencloud-scanner scan "$host" > "$today/$host.json"
done
check-opencloud-scanner fleet /var/lib/opencloud-reports
check-opencloud-scanner fleet /var/lib/opencloud-reports --format html > fleet.html
```

```text
Fleet summary, 2026-09-24 06:15:02 UTC
42 reports read, 3 hosts, 39 older superseded
Hosts: 3 | Unsupported releases: 1 | Waivers ending: 1 | Not covered: 1
Ratings: 4/5 x1, 2/5 x1

== Unsupported releases
Host                Version  Line              End of life  Upgrade to  Note
------------------  -------  ----------------  -----------  ----------  --------------
cloud2.example.com  2.0.0    2.0 (production)  2025-12-01   7.2.4       since the scan

== Waiver deadlines (next 30 days)
Host                Ends                  When        Checks         Waiver     Reason
------------------  --------------------  ----------  -------------  ---------  ----------------------
cloud2.example.com  2026-10-05 00:00 UTC  in 10 days  exposed:/.env  exposed:*  migration ticket OPS-1

== Common findings
Finding               Severity  Hosts  Waived  What it is
--------------------  --------  -----  ------  ----------------------------------------------
exposed:/.env         critical  2/2    1       A deployment file is publicly readable (/.env)
...

== Missing coverage
Host                Gap               Detail
------------------  ----------------  ----------------------------------------------------
cloud3.example.com  last scan failed  https://cloud3.example.com/status.php is unreachable
```

It reads result documents written by `scan` - files, or directories searched
recursively for `*.json` - and summarises the **newest report of each host**.
It scans nothing and stores nothing: collecting the reports, with a cron job,
a CI artefact store or a shared directory, stays with whatever you already use.

| Section | What it shows |
|:--|:--|
| Hosts | One row per host: version, rating, release line, failing and waived findings, coverage gaps and the age of the report |
| Unsupported releases | End-of-life releases, releases whose support ends within the window, and versions the schedule does not know |
| Waiver deadlines | Temporary waivers that let a failing check alert again within the window, or already have |
| Common findings | The failing findings shared by the most hosts, worst severity first |
| Missing coverage | Expected hosts without a report, hosts whose newest scan failed, stale reports, and reports older than the coverage block |
| Checks not evaluated | Checks the scans skipped or could not decide, and on how many hosts |

A report describes the day it was written, so two things are
re-measured against **today** rather than read back:

- **The release.** The recorded version is placed again in the release
  schedule this installation uses - the bundled one, or the file the
  configuration names, as for the plugin. A line that closed after the report
  was written is listed with the note `since the scan`. End of life is
  permanent, so a report that already said so is always listed.
- **The waiver deadline.** A waiver the report recorded as active may have
  run out since. Only a deadline after which a check really alerts again is
  listed, by the same rule as the plugin's `--waiver-warning`: a check that a
  permanent waiver also covers, and a flag OpenCloud hardcodes, never alert.

Common findings leave out what no operator can change - the flags OpenCloud
hardcodes and the headers no OpenCloud sends - because they fail on every
instance and would top the list of every fleet. A waived finding is still
counted, and the `Waived` column says on how many hosts.

| Option | What it does |
|:--|:--|
| `--format text` | Aligned tables, as above. The default |
| `--format markdown` | Markdown tables, for a ticket or a wiki page |
| `--format html` | One self-contained page: no script, no font, nothing fetched, light and dark mode |
| `--format json` | The structured summary, camelCase like the result document |
| `--window DAYS` | Show waivers and support windows ending within `DAYS` days. Default `30` |
| `--stale-after DAYS` | Count a host as not covered when its newest report is older. Default `7`, `0` turns it off |
| `--top N` | List the `N` most common findings. Default `10`, `0` lists all |
| `--expect HOST` | A host that should have a report. Repeatable, or comma separated |
| `--inventory FILE` | Expected hosts from a file, one per line, `#` starting a comment |

A host is matched by name and port, so `https://opencloud.example.com/` and
`opencloud.example.com` are the same host, while `opencloud.example.com:9200`
is another one. Write the port in `--expect` when the instance is scanned on
one.

It exits `0` whenever it printed a summary, however bad the fleet looks:
like `scan`, it measures and does not judge. It exits `2` when it found no
result document and no host was expected. A file that is not a result
document is not an error; it is named under *Files skipped*.

## `explain` - what a finding means and how to fix it

```bash
check-opencloud-scanner explain basicAuthDisabled
```

```text
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so usernames and passwords can be replayed on every request without going through the identity provider, ...
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs it. ...
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
```

It looks identifiers up in the catalogue built into the package. That is the
same text the plugin's `--debug` output, the scan result and the web
application show. It reads no configuration, needs no network and scans
nothing, so it works on any host where the package is installed.

```bash
check-opencloud-scanner explain cspWithoutUnsafeInline Referrer-Policy   # several at once
check-opencloud-scanner explain exposed:/config/opencloud.yaml          # parameterised ids too
check-opencloud-scanner explain --list                                  # every identifier, one per line
check-opencloud-scanner explain --list --category cookies               # one category
check-opencloud-scanner explain --format json cookieSecure              # for a script
check-opencloud-scanner explain                                         # the whole catalogue
```

| Option | What it does |
|:--|:--|
| `--list` | Print bare identifiers instead of explanations |
| `--category` | Only one category: `cookies`, `authentication`, `sharing`, `exposure`, `embedding`, `lifecycle`, `proxy`, `headers` or `transport` |
| `--format {text,json}` | JSON gives `id`, `category`, `title`, `meaning`, `remediation`, `reference`, `setting` and `actionable` for each entry |

An identifier the catalogue does not know exits `1` and suggests the nearest
ones:

```text
ERROR check_opencloud.cli: No catalogue entry for 'cookieSecur'. Did you mean: cookieSecure, cookieSameSite, cookiePrefix? Run `explain --list` for every identifier this build knows.
```

The identifiers are the ones findings carry in the alert line, in
`extraChecks[].id` and in `hardenings`, and the ones a waiver names. For the
longer, page-by-page treatment, see
[Hardening measures, one by one](hardening.md) and
[What the scanner reads](scanner-checks.md).

## `review-waivers` - waivers that need attention

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml review-waivers
```

```text
Reviewed 2 waiver(s) as of 2026-09-24 12:00 UTC without a scan result (pass --result for usage).

Expired (1):
  * exposed:/.env - Proxy rule pending
      Expired 2026-09-01 00:00 UTC (23 days ago); it suppresses nothing any more.
      Suggestion: Remove it from temporary_waivers / --waive-until. If the failure is still accepted, write a new record with a new deadline and a reason that is true today.

Unused (1):
  * debugPrt:*
      It matches no identifier this build knows.
      Suggestion: A check that was renamed or removed leaves its waiver behind; remove it if so. Check the spelling - did you mean debugPort?

Permanent (1):
  * debugPrt:*
      No reason and no deadline: it lasts until someone remembers it.
      Suggestion: Move it from ignore_hardenings / --ignore-hardening to a temporary waiver, e.g. --waive-until 'debugPrt:*|2026-12-23T00:00:00Z|<why this is accepted>'

Nothing was changed; edit the configuration to apply a suggestion.
```

It reads the waivers the plugin would use - `scanner.ignore_hardenings` and
`scanner.temporary_waivers` from the configuration file or their `COS_`
environment variables - and lists the ones that need a person, each with a
suggested cleanup. **It never changes the configuration.** Whether a failure
is still acceptable is for whoever accepted it to decide.

| Kind | What it means |
|:--|:--|
| Expired | A temporary waiver whose deadline has passed. It says whether the check alerts again or a broader waiver still hides it. |
| Expiring soon | A temporary waiver that runs out within `--expiring-within` days. This is the plugin's `--waiver-warning` for every record at once, not only the next one. |
| Unused | Matches no check that fails in the `--result` document. Without `--result`: matches no identifier this build knows, usually a typo or a renamed check. A waiver for a flag OpenCloud hardcodes counts as unused, because that flag never alerts. |
| Overlapping | Covered by another active waiver: a duplicate, a narrower pattern under a wider one, or - with `--result` - two patterns that waive the same failing check. A temporary waiver under a permanent one is flagged because its deadline changes nothing. |
| Permanent | A bare pattern with no reason and no deadline, with a `--waive-until` record to copy in its place. |

```bash
check-opencloud-scanner scan opencloud.example.com > result.json
check-opencloud-scanner review-waivers --result result.json          # tell used from unused
check-opencloud-scanner review-waivers --at 2026-12-01T00:00:00Z     # what will have expired by then
check-opencloud-scanner review-waivers --format json --exit-zero     # for a script
```

| Option | What it does |
|:--|:--|
| `--result FILE` | A result document from `scan`, to judge which waivers cover a failing check. With it the review also names the next expiry that makes a check alert, as `--waiver-warning` computes it |
| `--ignore-hardening`, `--waive-until` | Review these instead of the configured values, as the plugin flags of the same name would replace them |
| `--expiring-within DAYS` | The window for *Expiring soon*. Default: the `waiver_warning` setting, or `14` when that is off; `0` turns the section off |
| `--at TIMESTAMP` | Review as of another moment. It needs a timezone, like an expiry |
| `--format {text,json}` | JSON gives `counts` per kind and one entry per item, with `kind`, `pattern`, `reason`, `expiresAt`, `detail`, `suggestion` and `related` |
| `--exit-zero` | Always exit `0` |

One waiver can appear under several kinds. A misspelled permanent pattern,
for example, is both *Unused* and *Permanent*.

## `refresh-data` - update the release schedule and advisories

```bash
check-opencloud-scanner refresh-data --output-dir /var/lib/check-opencloud-security
```

It fetches the reviewed release schedule and advisory database from this
project's repository, verifies their signature, and writes them to
`--output-dir`. It prints the two paths and exits `0`. On any failure it
writes nothing and exits `1`.

| Option | Default | What it does |
|:--|:--|:--|
| `--output-dir` | `~/.cache/check-opencloud-security` | Where the two files go |
| `--timeout` | `30` | Seconds allowed for each request |
| `--schedule-url` | *(none)* | A lifecycle page or mirror, fetched unverified |
| `--advisory-url` | *(none)* | An OSV endpoint or mirror, fetched unverified |

The files have no effect until the configuration points at them. The
signature check needs the `signing` extra. One pitfall is easy to miss: a
schedule file the check cannot read turns the end-of-life check off. All of
this is covered in
[Keeping the release schedule and advisories current](reference-data.md).

## `serve` - the scan service

```bash
check-opencloud-scanner serve
check-opencloud-scanner serve --listen 0.0.0.0 --token "$(cat /run/secrets/scanner_token)"
```

It runs the scanner as a small HTTP service, so that several consumers share
one cached result per instance instead of each scanning it again.

| Option | Default | Setting |
|:--|:--|:--|
| `--listen` | `127.0.0.1` | `service.listen` / `COS_SERVICE_LISTEN` |
| `--port` | `8811` | `service.port` / `COS_SERVICE_PORT` |
| `--cache-ttl` | `900` seconds | `service.cache_ttl` / `COS_SERVICE_CACHE_TTL` |
| `--token` | *(none)* | `service.token` / `COS_SERVICE_TOKEN` |
| `--concurrency` | `1` | Probes in parallel within one scan |
| `--insecure` | off | Do not verify scanned instances' certificates |

**Binding anything but loopback without a token refuses to start.** It
prints `UNKNOWN: ...` on stderr and exits `3`, a code a supervisor will not
keep restarting through. The endpoints are listed in the
[main README](../README.md#running-the-scanner-as-a-service), and running it
in a container is covered in
[Running the scanner as a service](scan-service.md).

On such a bind the token must be at least 32 characters and not the
placeholder from `secrets/scanner_token.example`: nothing limits how often it
can be guessed, so its length is its only protection. `openssl rand -hex
32` gives one.

This is not the public web application. That one is
[the public scan service](webapp.md).

## `configure` - write a configuration file

```bash
check-opencloud-scanner configure
check-opencloud-scanner -c /etc/check-opencloud-security/.env.json configure
```

It asks for the settings interactively, explains each one, and saves them as
JSON, readable by the owner only. It offers `./.env.json`,
`~/.config/check-opencloud-security/.env.json` and
`/etc/check-opencloud-security/.env.json`, all places the search above finds
automatically. `-c` names the path instead. It is the same wizard as
`check-opencloud-security --configure`.

| Option | What it does |
|:--|:--|
| `--all` | Go through the optional settings without asking first |
| `--force` | Replace an existing file without confirming |
| `--no-test-scan` | Do not offer a test scan of the host before saving |
| `--export-monitoring` | Also write the scheduled check: `icinga`, `systemd`, `both` or `none` |

It then offers to write the scheduled check as well, next to the
configuration it just saved:

```text
Also write a monitoring configuration (Icinga service, systemd timer)? [y/N]
```

`--export-monitoring` answers that question up front, which is what a
provisioning script wants. The files carry the thresholds, the release track
and every other answer just given, so the check that runs every day is the
check that was configured rather than an example adjusted from memory:

```bash
check-opencloud-scanner configure --export-monitoring both
```

| File | What it is |
|:--|:--|
| `opencloud-security-<host>.conf` | An Icinga 2 `Service` object. It needs the `CheckCommand` from [`contrib/icinga2/`](../contrib/icinga2/check_opencloud_security.conf) as well - the service sets variables, the command turns them into flags |
| `check-opencloud-security.service` | A `oneshot` unit, with the same hardening directives as the one in [`contrib/systemd/`](../contrib/systemd/check-opencloud-security.service) |
| `check-opencloud-security.timer` | `OnCalendar=daily`, with a randomised delay so many hosts behind one address do not hit the release feed's rate limit at the same second |
| `check-opencloud-security.env` | The `COS_` variables for the unit, written owner-only |

Two limits apply. **Nothing is installed**: the files are written
where the configuration went and the commands that would install them are
printed, so what reaches `/etc` is something you read first. And **no
credential is written into them**: a webhook URL or a release token stays in
the configuration file, which is owner-only, while an Icinga object and a unit
file are not. Both artefacts point at that file instead - `vars.opencloud_config`
and `COS_CONFIG_FILE` - and name the settings they withheld, so a configured
webhook is never silently missing.

## Exit codes

These are **not** the plugin's Nagios codes. A `scan` that finds an F-rated
instance still exits `0`, because judging the result is the plugin's job.

| Subcommand | `0` | `1` | `2` | `3` |
|:--|:--|:--|:--|:--|
| `scan` | Every host was scanned | At least one host could not be scanned | Invalid configuration | - |
| `diff` | Nothing got worse | The later result is worse | The files cannot be compared | - |
| `fleet` | Summary printed | - | No result document found, or an unreadable inventory | - |
| `explain` | Printed | Unknown identifier or empty category | - | - |
| `review-waivers` | Nothing to clean up | At least one waiver is listed | Invalid waiver, timestamp or `--result` file | - |
| `refresh-data` | Both files written | Nothing written, see stderr | - | - |
| `serve` | Stopped normally | - | Invalid configuration | Refused to start, e.g. a wide bind without a token |

Invalid command-line arguments exit `2` for every subcommand, as usual for
argparse.
