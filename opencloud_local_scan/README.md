# `opencloud_local_scan`

The scan engine behind `check-opencloud-security` and the
`check-opencloud-scanner` service.

This package **is** the built-in scanner. It talks to an instance over HTTP(S), reads what OpenCloud exposes without
authentication, probes for the misconfigurations that actually occur in
OpenCloud deployments, and returns a single result document with a `0`-`5`
rating.

The rating scale follows the ratings of the Nextcloud scan API, so that
existing thresholds, performance data, webhooks and dashboards keep their
meaning.

| Module | Purpose |
|:-------|:--------|
| `scanner.py` | The scan engine; produces the result document |
| `releases.py` | Update check against the OpenCloud release feed |
| `vulndb.py`, `data/` | Advisory database and version-range matching |
| `versions.py` | Version parsing, comparison and the supported-release window |
| `config.py`, `secrets.py` | YAML / environment / secret-provider configuration |
| `service.py`, `cli.py` | The HTTP scan service and the `check-opencloud-scanner` command |
| `factory.py` | Builds settings objects from a `Configuration` |

## What it reads from the instance

Two endpoints are unauthenticated in OpenCloud, and both are needed:

- **`/status.php`** - product, edition, `productversion`, `maintenance`,
  `needsDbUpgrade`
- **`/ocs/v1.php/cloud/capabilities`** - the feature flags the hardening
  section below is derived from

Everything else is inferred from response headers, status codes and TCP
connects.

`/status.php` is not proof of OpenCloud, though: ownCloud and Nextcloud serve
the same endpoint, which OpenCloud inherited from them. A status document
whose product name carries either of those names is refused with `ScanError`
rather than scanned - their releases, advisories and defaults are not
OpenCloud's, and a verdict here would be a confident answer about the wrong
software.

### The version trap

`/status.php` reports three version fields:

```json
{"version": "0.1.0.0", "versionstring": "0.1.0", "productversion": "7.4.0"}
```

`version` and `versionstring` are **hardcoded constants** (`pkg/version` in the
OpenCloud source). They exist so old sync clients that expect an ownCloud-style
version string keep working, and they are identical on every instance ever
shipped. Only `productversion` is the actual release.

`versions.select_version()` therefore prefers `productversion`, falls back to
the capabilities endpoint, and treats the known placeholders as unusable. When
an instance offers nothing but the placeholder, the result document carries
`legacyVersion` and the EOL, update and advisory checks are skipped rather than
run against `0.1.0`.

If you are already parsing `/status.php` in another script, this is the field
to check.

## Rating algorithm

Evaluated in this order:

| Rating | Grade | Condition |
|:------:|:-----:|:----------|
| 0 | F | End of life |
| 1 | E | Vulnerability with severity critical or high |
| 2 | D | Any other known vulnerability |
| 3 | C | A whole release line behind |
| 4 | A | Update available within the release line |
| 5 | A+ | Up to date |

then **capped** by the worst failed additional check: `critical` -> at most `2`
(D), `high` -> `3` (C), `medium` -> `4` (A), `low` -> `5` (A+).

Capping rather than assigning is a deliberate choice. One exposed path is a
real problem, but it is not the same problem as running a release that receives
no security fixes at all, and a monitoring system that cannot tell them apart
is not useful. The consequence to be aware of: a single critical finding lands
at `D`, which the plugin's default `--critical 1` reports as WARNING. Run with
`--critical 2` if such a finding should page.

To report the findings without touching the rating at all:

```yaml
scanner:
  extra_checks_rating: false
```

Or drop the additional checks entirely with `--no-extra-checks`.

Every scan records how it arrived at its rating in `ratingExplanation`:

```json
{
  "rating": 4,
  "base": {"rating": 5, "reason": "the installed release is current and no advisory matches this version"},
  "caps": [
    {"check": "basicAuthDisabled", "severity": "medium", "cap": 4,
     "detail": "PROXY_ENABLE_BASIC_AUTH is on", "applied": true}
  ]
}
```

`base` is the rating the version and the advisory database alone produced;
`caps` lists every failed additional check with the ceiling its severity
imposes. A check that failed without deciding the outcome is kept with
`applied: false`, so a finding is never silently absent from the reasoning.
The list is sorted by severity, which makes the explanation independent of the
order the checks happened to run in.

## The single-page-application problem

OpenCloud is one Go binary that serves an embedded single-page frontend. That
frontend answers **unknown paths with HTTP 200 and the app shell** - so the
naive exposed-path check ("does `/opencloud.yaml` return 200?") reports a
handful of phantom exposures on every healthy instance.

Before probing anything, the scanner requests a path that cannot exist
(`/check-opencloud-security-probe-404`) and records the answer. A path is only
reported as exposed when its response actually differs from that catch-all
baseline. The same guard covers reverse proxies configured with a blanket
fallback.

## End-of-life detection

OpenCloud maintains three kinds of releases at the same time, and each has its
own support window:

| Track | Cadence | Supported until |
|:------|:--------|:----------------|
| `rolling` | about every 3 weeks | its successor is released |
| `production` | about every 6 months | the next production release |
| `lts` | a production line | 2 years after the line opened |

So a version number alone does not answer "is this still supported?". `7.2.3`
is the current production release while the rolling track is already at
`7.4.0`, and `7.3.0` - a *higher* version - stopped receiving fixes the day
`7.4.0` appeared.

The unit of support is the **release line** (`MAJOR.MINOR`), because that is
what OpenCloud maintains: `7.2.3` is a patch of the `7.2` line. A line can be
published on several tracks, and is judged by whichever supports it longest:

- `7.2` shipped as a rolling release and was then promoted to production. As a
  rolling release it is dead (7.3 exists); as the production release it is
  current. **Current** is the answer that matters.
- `4.0` is the previous production line *and* the current LTS line. Its
  production window closed when `7.2` arrived, but its LTS backports run until
  two years after `4.0.0`.

`scripts/update_release_schedule.py` scrapes the release dates from the
[OpenCloud admin documentation][lifecycle] - the only source that states the
release *type*; the GitHub release list cannot tell a rolling release from a
production one - and writes `data/release_schedule.json`:

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

```json
{
  "lifetime_days": {"rolling": 21, "production": 183, "lts": 730},
  "latest_release": {"production": "7.2.3", "rolling": "7.4.0"},
  "lines": [
    {"line": "7.4", "tracks": ["rolling"], "released": "2026-08-03", "latest": "7.4.0"},
    {"line": "7.2", "tracks": ["production", "rolling"], "released": "2026-06-25", "latest": "7.2.3"},
    {"line": "4.0", "tracks": ["lts", "production"], "released": "2025-12-01", "latest": "4.0.8"}
  ]
}
```

Rolling and production lines end when their successor on the same track is
released; `lifetime_days` bounds the newest line of a track and gives LTS the
two-year window the documentation promises. A line that is out of support gets
`EOL: true` and rating `F`.

Two cases are deliberately *not* end of life:

- a version newer than everything in the schedule, because the bundled file
  ages between updates and a fresh release must not trip the alarm;
- the newest line of a track, which has nothing to upgrade to.

```yaml
scanner:
  use_release_schedule: true       # false skips the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/release_schedule.json
```

The full verdict appears as `lifecycle` in the result document - line, track,
release date, end of support, days remaining, and the release to upgrade to -
so a stale or overridden schedule is visible rather than silent.

## Update check

An OpenCloud instance does not report pending updates: there is no `occ`
command and no updater endpoint. The newest release is therefore looked up
externally and compared against `productversion`.

The recommendation is **track aware**. A feed only knows the newest release
overall, which is always a rolling one, so offering it to a production or LTS
instance would move it onto a three-week support window. Those instances are
offered the newest release of their own track instead, and the newest release
overall is reported separately as `newestRelease`.

| Mode | Behaviour |
|:-----|:----------|
| `auto` | Try the feed; on any failure use `latest_release` from the bundled data |
| `feed` | Only the feed; a failure is reported as unknown |
| `pinned` | Use the configured `latest_version`; no network access |
| `bundled` | Use the shipped `latest_release`; no network access |
| `off` | Skip the update check |

`auto` is the default and never fails a check: a rate-limited or unreachable
GitHub degrades to the bundled release, which is as new as the installed
package. `feed` is the mode to pick when a silent fallback would be worse than
an explicit unknown.

The feed is the GitHub releases API by default. `parse_release_feed()` also
understands a plain `{"tag_name": ...}` document and a list of releases, so an
internal mirror needs no special format. Drafts and prereleases are skipped.

## Vulnerabilities

`data/vulnerabilities.json` **ships empty on purpose** - and in OpenCloud's
case unusually literally so: at the time of writing no CVE or GHSA has been
published for the product at all. The single entry in the file is disabled and
exists only to document the format.

`vulnerabilities: []` from a scan therefore means *"nothing in the database you
configured matched"*, not *"this instance has no known vulnerabilities"*. The
rating you get is driven almost entirely by the configuration checks. Point it
at a real source before relying on that part:

```yaml
scanner:
  vulnerability_db: /etc/check-opencloud-security/advisories.json
  vulnerability_feed: https://api.osv.dev/v1/query
```

Three input formats are accepted - the native one
(`{"advisories": [{"id": ..., "introduced": ..., "fixed": ...}]}`), the GitHub
Advisory API format and OSV documents - so an air-gapped setup can mirror a
feed to a file without conversion. Entries match on the half-open version range
`[introduced, fixed)` and are de-duplicated by id across sources. The sources
that were actually loaded appear as `advisorySources` in the result document,
so a misconfigured path is visible rather than silent.

## Hardenings

This package has **no hardening matrix**. It does not infer "this version
supports feature X, therefore X is enabled" - it reports only what the
instance actually said:

| Hardening | Evidence |
|:----------|:---------|
| `hstsLongMaxAge` | `Strict-Transport-Security` with `max-age` >= one year |
| `hstsPreload` | The same header carrying `preload` |
| `cspWithoutUnsafeInline` | A `Content-Security-Policy` without `'unsafe-inline'` |
| `basicAuthDisabled` | `WWW-Authenticate` on a protected endpoint not offering `Basic` |
| `publicLinkPasswordEnforced` | Capabilities: password required for public links |
| `publicLinkExpirationEnforced` | Capabilities: enforced expiry on public links |
| `userEnumerationRestricted` | Capabilities: user search restricted |
| `passwordPolicyEnforced` | Capabilities: minimum password length >= 8 |

A key is omitted entirely when the corresponding evidence is unavailable - a
missing header or an instance whose capabilities endpoint does not report that
feature. An older release therefore does not accumulate phantom findings, and
`capabilitiesAvailable` in the result document says whether the second half of
the table could be evaluated at all.

Some of these are worth knowing about before you enable `--check-hardening`:

- **`cspWithoutUnsafeInline` fails on a stock OpenCloud.** The default
  `csp.yaml` contains `'unsafe-inline'` in `script-src` and `style-src`. It is
  reported rather than excused, but fixing it means shipping your own CSP, and
  the web frontend currently depends on inline scripts and styles.
- **`basicAuthDisabled` is genuinely remotely observable.** With
  `PROXY_ENABLE_BASIC_AUTH=true` the proxy adds `Basic realm="<host>"` to its
  `WWW-Authenticate` challenge alongside `Bearer`. It is rated `medium`, and
  `low` when `identityProvider.external` is true: CalDAV, CardDAV and WebDAV
  clients cannot speak OpenID Connect, so an instance that wants them has to
  leave basic authentication on, and rating that as a serious failure told
  operators something they were right to disbelieve.
- **`publicLinkExpirationEnforced` and `userEnumerationRestricted` are not
  settings.** OpenCloud writes both capabilities as hardcoded constants, so the
  first fails on every instance and the second passes on every instance. They
  are marked `actionable=False` in the catalogue below, which keeps them out of
  alerts and counts while leaving them in the result document.

### Observations that are not findings

`scan()` also reports two integrations that are visible without logging in.
They live under `integrations`, produce no entry in `extraChecks`, and cannot
move the rating:

| Key | Evidence |
|:----|:---------|
| `integrations.office.detected` | `/app/list` - unprotected by OpenCloud's proxy policy - names at least one registered app provider |
| `integrations.office.apps` | The provider names it returned, e.g. `Collabora` |
| `integrations.office.groupware` | The `groupware.enabled` capability |
| `integrations.calendar.detected` | `/.well-known/caldav` answers with a redirect or a challenge rather than 404 |
| `integrations.calendar.advertised` | The `core.support_radicale` capability, which defaults to `true` and is therefore only corroborating |

The `files.app_providers` capability is a hardcoded constant and is ignored.

### What the scanner cannot measure

Two questions come up often enough to be worth stating as non-goals:

- **Audit logging cannot be checked.** OpenCloud's audit service consumes the
  internal event bus and exposes no HTTP surface; no capability, header or
  unauthenticated document reveals whether it is running. There is no signal to
  read, so no check exists and none can be added without credentials.
- **"Configured correctly" is out of scope for the integrations above.** That a
  provider is registered says nothing about WOPI secrets, share permissions or
  the second service's own configuration, all of which sit behind a login.

Everything the scanner does is a read. It never submits a form, never sends an
`Authorization` header and never tries a credential, so no result here can be
taken as evidence that authentication works - only that it is offered.

### Explaining the flags

`hardening.py` is the catalogue that turns these identifiers into something an
operator can act on. For each flag it holds a plain-language meaning, the
OpenCloud environment variable that governs it, and a link to the official
documentation:

```python
from opencloud_local_scan import describe_hardening

print(describe_hardening("basicAuthDisabled").describe())
```

```text
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so ...
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default). ...
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
```

The catalogue also covers the security headers from `setup.headers` and
`httpsEnforced`, and returns a named placeholder for an identifier it does not
know, so a future check can never crash a report. A test scans the fake
instance and asserts that every flag it produces has an entry, so adding a
hardening without documenting it fails the suite.

## Debug ports

Every OpenCloud service runs a debug listener serving `/healthz`, `/readyz`,
`/metrics`, `/config` and `/debug/pprof`. `/metrics` exposes the exact version
via `opencloud_proxy_build_info`, `/config` dumps the effective service
configuration, and `/debug/pprof` lets anyone trigger profiling.

They bind to loopback unless `<SERVICE>_DEBUG_ADDR` says otherwise, so one
answering from a monitoring host is a real finding - most often a container
that published a port range wholesale. Five are probed by default:

| Port | Service |
|:-----|:--------|
| 9205 | proxy |
| 9141 | frontend |
| 9124 | graph |
| 9134 | idp |
| 9239 | idm |

Each probe is one TCP connect with a three second timeout, so a firewalled host
costs up to fifteen seconds per scan. `check_debug_ports: false`,
`debug_port_timeout`, a shorter `debug_ports` list and `concurrency` are all
available.

The same handlers are also probed on the main address, where they must never
appear at all (`debugEndpoint:` findings).

## Concurrency

A scan is dominated by waiting: around twenty HTTP requests plus the debug-port
connects, issued one after the other. `concurrency` runs the independent ones
in parallel:

```python
result = scan("opencloud.example.com", settings=ScannerSettings(concurrency=8))
```

The default is `1`, which uses no threads at all, and values above `32` are
clamped. Each worker gets its own `requests.Session`, since a session is not
safe to share across threads.

The setting affects timing only. Results are collected back in the order the
probes were issued, so a parallel scan reports exactly the same findings, in
exactly the same order, as a sequential one.

## TLS

OpenCloud's proxy terminates TLS itself on port 9200, and `opencloud init`
generates a self-signed certificate. The scanner degrades in three steps rather
than failing on the first one:

1. HTTPS with certificate verification.
2. HTTPS without verification - the scan proceeds and `tlsTrusted` is reported
   as failed.
3. Plain HTTP - reported as `httpsAvailable` (critical).

`verify_tls: false` (or `--insecure`) starts at step 2. The untrusted chain
still shows up in the findings; it just stops counting against the rating, so
a self-signed instance can be monitored without a permanently degraded grade
while a genuinely broken certificate elsewhere still stands out.

## What this package does not do

- **No backend choice.** There is no remote scanner to select, so there is no
  `--scan-backend`, `--scan-url` or `--scan-token`, and nothing to force a
  rescan of, because nothing is ever cached.
- **No audit-log check.** The audit service has no HTTP surface and no
  capability of its own, so there is nothing to observe. See [What the scanner
  cannot measure](#what-the-scanner-cannot-measure).
- **No hardening matrix.** Hardenings are observed, not derived from the
  version (see above).
- **No credentials on the instance.** Every check works with what an
  unauthenticated client can see. The update check reads a public feed.
- **No PHP-era assumptions.** OpenCloud is a single Go binary with embedded
  assets: there is no `config/config.php`, no `/data/` and no `/3rdparty/`.
  The findings target what OpenCloud actually exposes - Graph API and OCS
  authentication, debug ports, `opencloud.yaml`, `proxy/server.key` and the
  idm boltdb.

## Using it directly

```python
from opencloud_local_scan import ScannerSettings, scan

result = scan("opencloud.example.com", settings=ScannerSettings(timeout=10))
print(result["rating"], result["version"], result["extraChecks"])
```

`scan()` raises `ScanError` when the instance cannot be identified as an
OpenCloud - an unreachable `/status.php`, a non-JSON response, a JSON document
without any recognisable version field, or one naming ownCloud or Nextcloud as
the product.

Every setting in `ScannerSettings` and `ReleaseSettings` can also come from a
configuration file (YAML, or JSON when the name ends in `.json`), an
environment variable or a secret provider - see
[`config/check-opencloud-security.example.yml`](../config/check-opencloud-security.example.yml)
and the [Configuration file and secrets](../README.md#configuration-file-and-secrets)
section of the main README. `check-opencloud-scanner configure` writes such a
file interactively.

For a scan that must not touch the network beyond the instance itself:

```python
from opencloud_local_scan import ReleaseSettings, ScannerSettings, scan

result = scan(
    "opencloud.example.com",
    settings=ScannerSettings(verify_tls=False, vulnerability_feed=None),
    release_settings=ReleaseSettings(mode="bundled"),
)
```

## Comparing a scan with the last one

`opencloud_local_scan.baseline` reduces a result document to the findings that
are worth comparing - vulnerabilities, missing hardening measures that are
actionable and not waived, failed additional checks and a pending update - and
remembers them per host. It is what `--baseline` / `--warn-on-new` are built
on.

```python
from opencloud_local_scan import load_baseline, scan, snapshot_of

result = scan("opencloud.example.com")
store = load_baseline("/var/lib/check_opencloud/baseline.json")
comparison = store.compare("opencloud.example.com", snapshot_of(result))

if comparison.regressed:
    print(comparison.summary())

store.record("opencloud.example.com", snapshot_of(result))
store.save()
```

`Comparison.regressed` is true on the first run (there is nothing to compare
against, so staying quiet would hide a real problem), when a finding is new,
when the rating has dropped, and whenever the release is past its end of life -
that last one however long it has been true, because a release that receives
no security fixes gets worse every day it stays in production.

The scan timestamp, the duration and the version string are deliberately not
part of a snapshot: they change on their own and would make every run look
new. Writing is atomic and owner-only, and a corrupt or future-format file is
read as "no baseline yet" rather than raising - degrading to the normal check
is never worse than refusing to run.

## Trademarks and affiliation

This is an independent community project. It is **not** affiliated with,
endorsed by, sponsored by or supported by OpenCloud GmbH, and nothing it
reports is an official statement about OpenCloud software.

"OpenCloud", the OpenCloud logo and all related names and marks are the
property of their respective owners. They appear here only to identify the
software this tool checks, which is nominative use and implies no
relationship. All rights in OpenCloud remain with OpenCloud GmbH.
