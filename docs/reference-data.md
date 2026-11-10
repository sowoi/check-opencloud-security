# Keeping the release schedule and advisories current

The scanner uses a release schedule to determine support status and an advisory database
to identify known vulnerabilities. Both are bundled with the package and can become
outdated between package upgrades. Refreshing them separately lets the scanner recognise
newer releases and advisories.

`check-opencloud-scanner refresh-data` closes that gap without a package
upgrade. This page covers what it fetches and how it checks the data, how to
run it daily, and how to point the check at the result.

<!-- TOC -->
* [Keeping the release schedule and advisories current](#keeping-the-release-schedule-and-advisories-current)
  * [When you need it](#when-you-need-it)
  * [Running a refresh](#running-a-refresh)
  * [Where the data comes from, and how it is checked](#where-the-data-comes-from-and-how-it-is-checked)
    * [Signature verification](#signature-verification)
    * [The checks that apply either way](#the-checks-that-apply-either-way)
  * [Using the refreshed files](#using-the-refreshed-files)
  * [Running it daily with systemd](#running-it-daily-with-systemd)
  * [Mirrors and hosts without internet access](#mirrors-and-hosts-without-internet-access)
  * [Your own advisories](#your-own-advisories)
  * [Points worth knowing](#points-worth-knowing)
<!-- TOC -->


## When you need it

- **A scan names a version the schedule does not know.** The lifecycle line
  then says the release is newer than anything in the bundled release
  schedule, and the result document carries `"scheduleStale": true`. See
  [Release tracks, end of life and the update recommendation](release-lifecycle.md).
- **An advisory was published after your package was built.** The bundled
  database cannot match it, so the scan reports no known vulnerabilities for
  a version that has one.
- **You pin the package** and upgrade it on your own schedule rather than
  whenever a release appears.

A host that upgrades the package promptly gets the same data that way, and
needs none of this. The [public scan service](webapp.md) refreshes its own
copy at runtime and needs none of it either.

## Running a refresh

```bash
check-opencloud-scanner refresh-data --output-dir /var/lib/check-opencloud-security
```

On success it prints the two files it wrote and exits `0`:

```text
/var/lib/check-opencloud-security/release_schedule.json
/var/lib/check-opencloud-security/vulnerabilities.json
```

| Option | Default | What it does |
|:--|:--|:--|
| `--output-dir` | `~/.cache/check-opencloud-security` | Directory the two files are written to. Created if missing |
| `--timeout` | `30` | Seconds allowed for each request |
| `--schedule-url` | *(none)* | Read the release schedule from this lifecycle page or mirror instead, **unverified**. See [Mirrors](#mirrors-and-hosts-without-internet-access) |
| `--advisory-url` | *(none)* | Query this OSV endpoint or mirror instead, **unverified** |

Any failure exits `1` with the reason on stderr: a network error, a document
that fails a check, or a signature that does not match. Nothing is written
unless both documents pass, so the previous files stay exactly where they
were. A cron job or timer can therefore run it blindly. A bad day upstream
never replaces good data with worse.

Add `-vv` to see each signature being verified:

```bash
check-opencloud-scanner -vv refresh-data --output-dir /var/lib/check-opencloud-security
```

## Where the data comes from, and how it is checked

By default the refresh does **not** query OSV or the OpenCloud lifecycle
page live. It reads `release_schedule.json` and `vulnerabilities.json` from
the `main` branch of this project's repository. Those are the files a
maintainer already reviewed and merged, in the pull requests the project's
daily data workflows open. Nothing reaches your host that a person has not
looked at. See
[ADR 0027](../adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

### Signature verification

Every change to those two files on `main` is attested with
[Sigstore](https://www.sigstore.dev/) by this repository's
`attest-security-data.yml` workflow. The refresh fetches that attestation and
checks that it was signed by that one workflow, on `main`, in this
repository. A signature from any other GitHub Actions run does not count.

Verification needs the `signing` extra, which is optional because it pulls in
about a dozen further packages:

```bash
pipx install 'check-opencloud-security[signing]'
```

To add the extra to an existing pipx installation, re-run that command with
`--force`. [Installing the plugin](installation.md) has the uv and pip
equivalents.

There are three outcomes:

| Outcome | What happens |
|:--|:--|
| The signature verifies | The document is used |
| The signature could not be *checked* | A warning, then the structural checks below only. Causes: the extra is not installed, GitHub or the Sigstore trust root is unreachable, or no attestation is published yet for that content |
| A signature is present and **wrong** | The refresh stops, exits `1`, and writes nothing |

Without the extra, every run logs this for each file and still succeeds:

```text
WARNING check_opencloud.refresh_data: Refreshing the release schedule without verifying its signature: the 'signing' extra (sigstore) is not installed. Install the 'signing' extra (pip install check-opencloud-security[signing]) to verify it.
```

A host that shows this warning is not checking where its data came from.
Install the extra wherever the refresh matters.

### The checks that apply either way

A verified signature proves where a document came from, not that it makes
sense. So these checks run on every refresh, signed or not:

- **The release schedule may not lose a release line.** Every line in the
  schedule bundled with the installed package must still be present. A
  truncated or rewritten lifecycle page cannot make an old release
  look supported.
- **The advisory database must have usable entries.** It must contain at
  least one advisory, and every advisory needs a version bound. An advisory
  open at both ends would match every OpenCloud release there has ever been.
- **Each file is replaced atomically.** A reader never sees half a file.

## Using the refreshed files

The refresh only writes files. It never writes into the installed package, so
nothing changes until the check is told where to look:

```yaml
scanner:
  release_schedule: /var/lib/check-opencloud-security/release_schedule.json
  vulnerability_db:
    - /var/lib/check-opencloud-security/vulnerabilities.json
```

Or through the environment:

```bash
COS_SCANNER_RELEASE_SCHEDULE=/var/lib/check-opencloud-security/release_schedule.json
COS_SCANNER_VULNERABILITY_DB=/var/lib/check-opencloud-security/vulnerabilities.json
```

The two settings behave differently:

- `release_schedule` **replaces** the bundled schedule.
- `vulnerability_db` **adds to** the bundled database. Entries are
  de-duplicated by id, so listing the refreshed file alongside the bundled one
  is safe.

Both the plugin and `check-opencloud-scanner scan` read the same settings.
Confirm it took effect with the scanner's JSON output:

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml \
    scan opencloud.example.com | jq '.advisorySources, .lifecycle.scheduleUpdated'
```

`scheduleUpdated` should be the date of the refreshed schedule, and
`advisorySources` should list the refreshed file.

**Check both after any change of path or user, because neither failure is
loud:**

- **A schedule file that is missing or unreadable turns the end-of-life check
  off.** The check does not fall back to the bundled schedule. The lifecycle
  line reads `Release lifecycle: unknown (no release schedule available)`,
  `scheduleUpdated` is `null`, and nothing is logged below `-vv`. An
  end-of-life release is then rated on its configuration alone. In testing, a
  2.3.0 instance that is otherwise CRITICAL came out as `OK` and `A+`.
- **An advisory file that is missing or unreadable is skipped with a
  warning** on stderr (`Advisory file ... does not exist`, or `Ignoring
  advisory file ...: Permission denied`). An unreadable file still appears
  in `advisorySources`, so read the warning rather than the list.

## Running it daily with systemd

[`contrib/systemd/`](../contrib/systemd/) has a hardened oneshot service and a
timer for it:
[`check-opencloud-security-refresh.service`](../contrib/systemd/check-opencloud-security-refresh.service)
and
[`check-opencloud-security-refresh.timer`](../contrib/systemd/check-opencloud-security-refresh.timer).
The service writes to `/var/lib/check-opencloud-security` through
`StateDirectory=` and may write nowhere else. The timer runs it daily,
randomised within an hour, and catches up after downtime.

```bash
sudo cp contrib/systemd/check-opencloud-security-refresh.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now check-opencloud-security-refresh.timer
sudo systemctl start check-opencloud-security-refresh.service   # a first run now
journalctl -u check-opencloud-security-refresh.service
```

**Run it as the user the check runs as.** Both files are written readable by
their owner only (mode `0600`). The unit ships with
`User=check-opencloud-security`, so a check running as `nagios` or `icinga`
cannot read what it wrote. That silently turns the end-of-life check off. See
[Using the refreshed files](#using-the-refreshed-files). Either run the check
as that user, or change the refresh user with a drop-in:

```bash
sudo systemctl edit check-opencloud-security-refresh.service
# [Service]
# User=nagios
```

`ExecStart=` expects `/usr/bin/check-opencloud-scanner`, which is where the
`.deb` and `.rpm` packages install it. Adjust the path for a pipx or pip
installation. Without systemd, a daily cron line does the same job. See
[Scheduling](scheduling.md).

## Mirrors and hosts without internet access

A default refresh needs HTTPS access to `raw.githubusercontent.com`, and,
for verification, to GitHub's attestation API and the Sigstore trust root.
There are two ways to serve a host that has none of that.

**Refresh elsewhere and copy the files.** Run the verified refresh on a
connected machine with the `signing` extra, then copy the two files to the
same paths on the isolated host. The files are self-contained, and the copy
keeps the verification you did.

**Point the refresh at a mirror.** `--schedule-url` takes a copy of the
OpenCloud lifecycle page. `--advisory-url` takes an OSV-compatible query
endpoint, whose answer is merged into the bundled database:

```bash
check-opencloud-scanner refresh-data \
    --output-dir /var/lib/check-opencloud-security \
    --schedule-url https://mirror.example.com/opencloud/lifecycle/ \
    --advisory-url https://mirror.example.com/osv/v1/query
```

Nothing signs a mirror, so both options skip signature verification and say
so on every run. The structural checks above still apply. Use this for an
internal mirror you control, not as a way around a signature failure.

## Your own advisories

`scanner.vulnerability_db` takes a list, so a file of your own sits beside the
refreshed one. Three formats are understood without conversion: the native
`{"advisories": [...]}` document, the GitHub Advisory API format, and OSV
documents. The [main README](../README.md#advisory-database) describes the
formats and how entries match a version. `scanner.vulnerability_feed` queries
a feed live on every scan instead of reading a file.

## Points worth knowing

- **A refresh only ever changes data, never code.** No new check, finding or
  rating rule arrives this way. Those still need a package upgrade.
- **An empty `vulnerabilities` list is not a clean bill of health.** It means
  nothing in the databases you configured matched this version. The
  configuration checks carry most of the rating either way.
- **Refresh the files the check actually reads.** The default output
  directory is under the home directory of whoever runs the refresh, so a
  refresh run as root does nothing for a check running as `nagios`.
- **The web application does not use this command.** It refreshes its schedule
  and advisory database at runtime, and may only ever gain knowledge. See
  [the public scan service](webapp.md).
