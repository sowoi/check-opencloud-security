# `opencloud_local_scan`

The scan engine behind `check-opencloud-security` and the
`check-opencloud-scanner` service.

The scanner connects directly to the instance over HTTP(S), checks publicly observable
settings and returns one result document with a rating from `0` to `5`. It also tests
the documented demo credentials against the instance’s own identity provider.

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
| `tls.py` | Transport security: handshake, protocol, certificate, chain, stapling |

## What it reads from the instance

Two endpoints are unauthenticated in OpenCloud, and both are needed:

- **`/status.php`** - product, edition, `productversion`. It also carries
  `maintenance`, `installed` and `needsDbUpgrade`, but OpenCloud's own handler
  hardcodes all three rather than reading real state, so this package does not
  check them - see [`docs/status-php.md`](../docs/status-php.md).
- **`/ocs/v1.php/cloud/capabilities`** - the feature flags the hardening
  section below is derived from

Everything else is inferred from response headers, status codes and TCP
connects.

A `/status.php` response alone does not identify OpenCloud. The scanner checks the
reported product and raises `ScanError` for another product, whose releases, advisories
and defaults would not match this database. See [What OpenCloud
is](../docs/what-is-opencloud.md).

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

A cap can only lower the starting rating, so a configuration finding cannot improve an
end-of-life result. Note the monitoring consequence: a critical finding caps the score
at `2` (`D`), which the default `--critical 1` reports as WARNING. Use `--critical 2` to
make it CRITICAL.

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

## What would raise the rating

The same result carries a `remediationPlan`, built by `remediation.py` from
the caps above: an ordered fix list with the rating each step would reach.

```json
{
  "currentRating": 3,
  "achievableRating": 5,
  "summary": "Two fixes would raise this instance from 3/5 to 5/5.",
  "steps": [
    {"order": 1, "id": "exposed:/opencloud.yaml", "kind": "finding",
     "severity": "high", "title": "A deployment file is publicly readable",
     "action": "Stop serving the deployment directory ...",
     "ratingBefore": 3, "ratingAfter": 4, "ratingGain": 1}
  ],
  "blocked": [],
  "waived": []
}
```

It is a replay of `_compute_rating` with one finding removed at a time, not a
second model of the rating, so a predicted grade cannot disagree with the real
one. Nothing new is stored: the plan is derived from the document it sits in.

`groups` regroups the open findings - including ones that cap nothing, such
as a missing header - by where the change is made (`reverseProxy`,
`identityProvider`, `opencloud`, `dnsZone`), built by `remediation_groups.py`.
Findings one edit resolves together are one change, with the `findings` it
resolves, the plan `steps` among them, `resolvesSeveral`, and the
`ratingAfter` that change alone gives, replayed through the same arithmetic.
`groupSummary` is one sentence naming the changes that resolve several.

Three properties are load-bearing and have tests:

- The **order** is by cap, then severity, then identifier, so it does not
  depend on the order the checks ran in. A step that gains nothing on its own -
  the first of several findings sharing one ceiling - stays in the list with
  `ratingGain: 0` rather than being hidden.
- An **update is a step too**, inserted at the first position where it starts
  to gain something. Fixing findings cannot lift a rating above what the
  installed version allows, so a plan that put the upgrade first would promise
  a gain it could not deliver.
- **Findings that cannot be fixed** - `actionable: false`, the flags OpenCloud
  hardcodes - go to `blocked` and stay in every simulated remainder, which is
  what bounds `achievableRating` correctly.

An end-of-life release short-circuits the rating to `0` without recording any
caps, so the plan rebuilds them from `extraChecks` in that one case. Otherwise
it would promise a perfect score after an upgrade with a critical finding
still open.

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

`schedule_source.py` reads the release dates off the
[OpenCloud admin documentation][lifecycle] - the only source that states the
release *type*; the GitHub release list cannot tell a rolling release from a
production one. `scripts/update_release_schedule.py` runs it in CI and writes
the result to `data/release_schedule.json`, which is the file that ships:

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

When the instance is newer than the schedule, the result includes `scheduleStale`,
`scheduleUpdated`, `scheduleSource` and a `scheduleNote` linking to the [lifecycle
page][lifecycle]. These describe the reference data without changing the rating or
update recommendation. `ReleaseSchedule.is_behind()` exposes the same comparison.

The plugin keeps the schedule that shipped with it: a monitoring host runs the
check every few minutes and must not turn that into a documentation fetch, so
the file is refreshed by upgrading. The web application is the other case - a
process that stays up for months - and re-reads the same page once a day
through `schedule_source.fetch_schedule_document()`, handing the result to
`ScannerSettings.release_schedule`. Either way the scanner is *given* a
schedule and decides nothing new about where it came from.

```yaml
scanner:
  use_release_schedule: true       # false skips the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/release_schedule.json
```

The full verdict appears as `lifecycle` in the result document - line, track,
release date, end of support, days remaining, the release to upgrade to, and
how old the schedule that decided all of it is - so a stale or overridden
schedule is visible rather than silent.

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

Beside `vulnerabilities`, a result carries `upgradePath` when the installed
release has known advisories and a newer release is recommended: the
`target`, the advisories it `fixes`, the ones it is `stillAffected` by, and
`safeVersion`, the lowest release past every missing fix (`null` when one has
none yet). It is `null` otherwise. See
[Does the upgrade clear the advisories?](../docs/release-lifecycle.md#does-the-upgrade-clear-the-advisories)

`upgradeRehearsal` goes one step further: for every candidate release (the
newest patch of the installed line and the newest release of each later line,
restricted to the declared track) it lists what the release `fixes`, leaves
`stillAffected` and `introduces`, whether it is `endOfLife`, and the 0-5
`rating` the scan would give it - the version rules replayed, still capped by
the instance's failed checks. An empty list when nothing newer is known. See
[Rehearse every upgrade](../docs/release-lifecycle.md#rehearse-every-upgrade).

`alternativeServices` records the instance's `Alt-Svc` header - whether it
advertises HTTP/3 over UDP - as an observation that is never graded. See
[Alternative services](../docs/scanner-checks.md#alternative-services-http3).

`loginThrottling` is `null` unless `check_login_throttling` is set; then it
records whether six failed sign-ins for a non-existent account were slowed
down. Never graded. See
[Failed sign-ins](../docs/scanner-checks.md#failed-sign-ins-opt-in).

### Refreshing reference data on a monitoring host

The package includes a separate `refresh-data` command for installations that
cannot wait for a package upgrade:

```console
$ check-opencloud-scanner refresh-data \
    --output-dir /var/lib/check-opencloud-security
/var/lib/check-opencloud-security/release_schedule.json
/var/lib/check-opencloud-security/vulnerabilities.json
```

It reads both documents from this project's own repository - the reviewed
files a maintainer merged, not a live third-party query - and **verifies a
Sigstore attestation** over them before believing any of it. It then rejects
a lifecycle document that loses a bundled release line, refuses unbounded
advisories, and replaces each file atomically. It never writes into the
installed package. Point `scanner.release_schedule` and
`scanner.vulnerability_db` at the two generated files, then run the supplied
[`check-opencloud-security-refresh.timer`](../contrib/systemd/check-opencloud-security-refresh.timer)
daily. A network failure leaves the previous files untouched.

Signature verification needs the `signing` extra:

```console
$ pip install 'check-opencloud-security[signing]'
```

Without it the refresh still runs - it falls back to the structural guards
alone and logs a warning saying so. Note what that means: a host without the
extra is not checking provenance at all, so install it wherever the refresh
actually matters.

With the extra installed, there are three outcomes. A
verified document is written. A signature that could not be *checked* - the
attestation is not published yet, GitHub is unreachable, the trust root
would not load - warns and falls back to the structural guards. A signature
that is present and *wrong* stops the refresh outright and leaves the
previous files exactly where they were.

Passing `--schedule-url` or `--advisory-url` queries that source live and
unverified, for an air-gapped mirror or a fork, and says so in the log. See
[ADR 0027](../adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

`data/vulnerabilities.json` carries the advisories published against
OpenCloud, and is regenerated daily by
`.github/workflows/vulnerability-db.yml`, which runs
`scripts/update_vulnerability_db.py` against the OSV query API and opens a
pull request when the answer has changed. The refresh **only ever adds**: an
advisory the feed has forgotten stays in the file, and a hand-written entry
survives. An entry is only removed by hand.

It is still only as complete as the feeds it is built from.
`vulnerabilities: []` from a scan means *"nothing in the database you
configured matched"*, not *"this instance has no known vulnerabilities"*, and
a large part of the rating comes from the configuration checks either way.
Add your own source if you have one:

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

One advisory can affect several release lines that were patched separately.
`GHSA-vf5j-r2hw-2hrw` was fixed in both `4.0.3` and `5.0.2`, and that is one
advisory with two disjoint ranges rather than two advisories, so an entry may
carry a `ranges` list:

```json
{
  "id": "GHSA-vf5j-r2hw-2hrw",
  "severity": "high",
  "ranges": [
    {"introduced": "4.0.0", "fixed": "4.0.3"},
    {"introduced": "5.0.0", "fixed": "5.0.2"}
  ]
}
```

A match reports the fix belonging to the line the scanned instance is on, so a
`5.0.1` instance is told to upgrade to `5.0.2` rather than to a release that
fixes nothing for it. `introduced` and `fixed` stay beside it as the first
range, which is what a single-range advisory has always been.

**An advisory with no version bounds at all is dropped**, wherever it comes
from. A range that is open at both ends matches every release there has ever
been, and public feeds do publish that shape - the Go vulnerability database
records this very advisory as `introduced: "0"` with no fix. Believing one
would report every OpenCloud instance in the world as vulnerable, so the
parser refuses it rather than trusting the feed to be sensible.

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
| `passwordPolicyEnforced` | Capabilities: policy enabled and minimum password length >= 8 |
| `passwordPolicyComplexity` | Capabilities: the policy still requires a lowercase letter, an uppercase letter, a digit and a special character |
| `oidcPkceSupported` | Discovery document: `code_challenge_methods_supported` contains `S256` |
| `oidcImplicitFlowDisabled` | Discovery document: `response_types_supported` returns no token from the authorization endpoint (external providers only) |
| `oidcSigningAlgorithmStrong` | Discovery document: `id_token_signing_alg_values_supported` has neither `none` nor an `HS` algorithm |
| `oidcEndpointsUseHttps` | Discovery document: every published endpoint is `https://` (only measured when the instance itself answered over HTTPS) |

A key is omitted entirely when the corresponding evidence is unavailable - a
missing header or an instance whose capabilities endpoint does not report that
feature. An older release therefore does not accumulate phantom findings, and
`capabilitiesAvailable` in the result document says whether the second half of
the table could be evaluated at all.

Which of them was omitted, and why, is recorded in `coverage` - see
[What the scan covered](#what-the-scan-covered).

The additional probes also read the public web configuration: wildcard embed
message origins fail `webEmbedMessageOriginRestricted`, delegated iframe
authentication without an explicit origin fails
`webEmbedDelegatedAuthenticationRestricted`, and a matching OpenCloud listener
on the direct backend port fails `backendPortClosed`.

Note the following before you enable `--check-hardening`:

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

`setup.advisoryChecks` is the other block that cannot move the rating, and for
a different reason: not that the observation is neutral, but that OpenCloud
satisfies it on no instance, so counting it would report the shipped state of
the software as a fault in this deployment. It holds two entries:

- `securityTxtPublished` - whether `/.well-known/security.txt` carries the
  `Contact` field RFC 9116 requires, so that somebody who finds a flaw knows
  where to send it. The body is what is read, not the status code: an
  instance whose frontend answers every unknown path with its own shell
  returns 200 for that path too.
- `hstsPreloadEligible` - whether the `Strict-Transport-Security` header
  would actually be accepted for browser preloading, which needs a max-age of
  at least a year, `includeSubDomains` and `preload` together. `hstsPreload`
  in the `hardenings` block answers the narrower question of whether the
  directive is present at all; OpenCloud's proxy sends it alongside ten years
  and no `includeSubDomains`, so the header on every stock instance asks for
  something the preload list refuses. Whether the domain is *on* the list is
  deliberately not measured - see
  [ADR 0037](../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md).

The block is `{}` rather than a dictionary of `false` when the extra checks
are off, because an observation nobody made is not one that failed. See
[ADR 0034](../adr/0034-an-advisory-observation-need-not-be-a-header.md).

The `identityProvider` observation names an external provider when its OIDC
issuer identifies one. For Keycloak, Authelia and Authentik it also includes
`advisoryUrl`, which points to the provider's official GitHub Security
Advisories page. `version` is present but empty because none of these providers
exposes its product version through an unauthenticated, default-enabled
endpoint. The scanner does not guess from URL paths, assets or proxy headers;
if trustworthy public version evidence becomes available, that field can carry
it without changing the result shape.

### What the scanner cannot measure

Two questions come up often and are out of scope:

- **Audit logging cannot be checked.** OpenCloud's audit service consumes the
  internal event bus and exposes no HTTP surface; no capability, header or
  unauthenticated document reveals whether it is running. Without a
  signal to read, no check exists and none can be added without credentials.
- **"Configured correctly" is out of scope for the integrations above.** That a
  provider is registered says nothing about WOPI secrets, share permissions or
  the second service's own configuration, all of which sit behind a login.

The scanner does not use ordinary user credentials. The documented exception is
`_demo_user_finding`: with the built-in provider, it tests the published demo accounts
through `/ocs/v1.php/cloud/user`. A successful login produces the critical
`demoUsersDisabled` finding. No credentials go to an external provider. Rejection
confirms only that those demo credentials failed, not that authentication is secure in
every respect.

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

The catalogue also covers the security headers from `setup.headers`, the
advisory observations from `setup.advisoryHeaders` and
`setup.advisoryChecks`, and `httpsEnforced`, and returns a named placeholder
for an identifier it does not know, so a future check can never crash a
report. A test scans the fake instance and asserts that every flag it produces
has an entry, so adding a hardening without documenting it fails the suite.

The same catalogue is a command, for the far more common case of having an
identifier and no Python prompt:

```shell
$ check-opencloud-scanner explain basicAuthDisabled
$ check-opencloud-scanner explain exposed:/config/opencloud.yaml
$ check-opencloud-scanner explain --category transport
$ check-opencloud-scanner explain --list
$ check-opencloud-scanner explain --format json cookieSecure
```

The command works offline and reads only the installed catalogue. It accepts header
names and path-specific identifiers such as `exposed:/config/opencloud.yaml`. With no
identifier it prints the whole catalogue. An unknown identifier returns exit code 1 and
suggests nearby names.

### The same fix, as configuration

`snippets.py` turns the catalogue’s `env_fix` and `header_fix` entries into
configuration snippets:

```python
from opencloud_local_scan import configuration_fragment

print(configuration_fragment(["basicAuthDisabled", "demoUsersDisabled"], "compose").text)
```

```yaml
services:
  opencloud:
    environment:
      PROXY_ENABLE_BASIC_AUTH: "false"
      IDM_CREATE_DEMO_USERS: "false"
```

Five flavours: `compose`, `env`, `nginx`, `caddy`, `traefik`. Each expresses
one kind of fix, because the two kinds live in different files on usually
different machines - environment assignments go on the OpenCloud instance,
response headers on whatever terminates TLS in front of it. Rendering a header
into a Compose environment block would produce a line that does nothing, so a
flavour reports what it cannot express in `Fragment.elsewhere` instead, and
`flavours_for` names the flavours that can.

All configuration names and values come from the catalogue. Settings that depend on the
deployment, such as a CORS origin or CSP file path, appear in `Fragment.undecided`. They
require an operator’s choice before a usable snippet can be generated.

## What the scan covered

Neither a passed check nor a check that never ran leaves a trace in this
document. `coverage` records which of the two it was. See
[ADR 0064](../adr/0064-a-scan-records-what-it-did-not-measure.md).

```json
{
  "coverage": {
    "schema": 1,
    "counts": {"passed": 49, "failed": 10, "not_checked": 12, "inconclusive": 0, "total": 71},
    "checks": [
      {"id": "Content-Security-Policy", "group": "header", "state": "passed"},
      {"id": "directoryListing", "group": "extraCheck", "state": "failed"},
      {"id": "tlsInspection", "group": "tls", "state": "not_checked",
       "reason": "not_applicable", "detail": "The instance answered over plain HTTP."}
    ]
  }
}
```

Every check the scan considered appears exactly once, in one of four states:

| State | Meaning |
|:--|:--|
| `passed` | The check ran and the instance satisfied it |
| `failed` | The check ran and the instance did not satisfy it |
| `not_checked` | The scanner did not run the check |
| `inconclusive` | The scanner ran the check and could not decide |

`passed` and `failed` carry no reason - a measurement that ran needs no
excuse. The other two always carry one, from a closed set:

| Reason | Meaning |
|:--|:--|
| `not_applicable` | The check cannot apply to this deployment - no certificate on a plain-HTTP instance, no second address to compare |
| `probe_disabled` | A setting turned the probe off for this scan |
| `prerequisite_missing` | The instance did not publish what the check reads |
| `timeout` | Nothing answered in time |
| `unreadable` | Something answered and could not be understood |
| `no_route` | There is no route to that address family from where the scan ran |

Two properties matter here:

- **The total is what this scan considered**, not a constant. The checks are
  dynamic - which paths are probed, which debug ports are dialled, which
  addresses are compared depend on the instance and the settings - so there is
  no fixed denominator.
- **Coverage never changes a grade.** Nothing in the block reaches the rating,
  the severities, the alert line or the exit code. The webhook payload carries
  the counts, but only as a report of what was measured - no receiver has to
  read them to know the verdict. A waived failure stays `failed` here; the
  acceptance is in `extraChecks[].ignored`, because a waiver is a decision
  about alerting and not about evidence.

A document written before this block existed has no `coverage` key,
which is a report that does not say what it covered - not a scan without
gaps. Read it with `coverage.coverage_of(result)`, which returns `None` for
both a missing and a malformed block.

### The one-line summary

`coverage.summary(result)` reduces the block to the four numbers a reader
needs, and `coverage.summary_line(result)` writes them as one English
sentence:

```
84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited
```

Every check is in exactly one of the four. `evaluated` is a conclusion, pass
or fail; `skipped` is a check the scanner decided not to run; `indeterminate`
is one that ran and could not tell; `networkLimited` is split out of the last
two because a timeout or a missing route is the one gap another vantage point
might close - DNSSEC from a resolver that validates, an external identity
provider that is reachable from elsewhere. Zero counts are left out of the
sentence, but the number evaluated is always named. Both functions return
`None` / `""` for a document that has no coverage block, so "nothing was
missed" and "this report does not say" never read alike.

The plugin prints the sentence as a `Coverage:` detail line, the webhook
payload carries the same numbers under `coverage` (snake_case, as the payload
is), and the web application shows them under *What this scan did not
measure*.

## The conditions a scan ran under

Two scans of the same instance can disagree without the instance having
changed: the advisory database learned a CVE, a support window closed, the
scanner was upgraded, a waiver expired. `provenance` records what was known
at the time, so a comparison can tell those apart from a real regression. See
[ADR 0066](../adr/0066-a-result-records-the-conditions-it-was-produced-under.md).

```json
{
  "provenance": {
    "schema": 1,
    "scannerVersion": "1.25.0",
    "scannedAt": "2026-09-17T19:56:35.852320+00:00",
    "releaseTrack": "auto",
    "advisoryData": {"digest": "7ffa242f...", "count": 1},
    "scheduleData": {"digest": "6e9468bf...", "updated": "2026-09-15"},
    "waivers": {"active": [], "expired": []},
    "coverage": {"measured": 59, "total": 71}
  }
}
```

`digest` is a SHA-256 over the reference data's own identifying fields in
canonical form, so the same advisories hash the same however they were
serialised, merged or ordered. It is a digest rather than a copy - embedding
the database would put megabytes of other people's advisories in every report -
and rather than a file path, which would publish where the machine keeps its
files. `scheduleData.updated` is when the schedule was *generated*, which is
not when it was read; `scannedAt` is the scan.

`waivers` records patterns and states, never the reason text: a reason is
prose written for a person, and a comparison that diffed it would report a
corrected typo as a change of policy.

### Comparing two results

`check-opencloud-scanner diff` prints the contributing changes under the
existing summary, and `--format json` carries them as `explanation`:

| Category | What changed |
|:--|:--|
| `instance` | The version, a check that started or stopped failing, or a configuration group whose fingerprint moved |
| `referenceData` | The advisories, the release schedule, the release track, or a support window that simply elapsed |
| `scanner` | The scanner's version, or how many checks reached a conclusion |
| `policy` | A waiver expired, was added or was removed |
| `unknown` | Something moved and nothing recorded accounts for it |

The wording is conservative. A changed digest establishes that
the reference data differed; it does not establish that it caused any
particular grade to move, and the sentence reflects that. Several changes may
contribute without one being chosen as *the* cause.

`--format json` also carries `findings`, one entry per finding in either
document, with the severity, the waiver state and the category on each side,
and `severityTotals`, the failing findings counted by severity before and
after. That is what `opencloud_local_scan.findings` computes and what the
`~` lines and `--format side-by-side` render. It keeps what the set of
failing names throws away: a finding that stayed open and moved from `high`
to `critical` is not a change to that set, and is a change to the rating it
caps.

A side is `null` where the document did not record that finding at all, and
the status says `appeared` or `disappeared` rather than `introduced` or
`resolved` - absent is not passing ([ADR
0064](../adr/0064-a-scan-records-what-it-did-not-measure.md)). Severities are
read from the documents and held to `critical`, `high`, `medium`, `low`,
`unknown`; an archived report is evidence about when it was written, so the
current catalogue never overrides it.

`limitations` lists what the comparison could not establish - most often that
one of the two reports predates these blocks, and so cannot say what it was
judged against or how much of it ran. That is reported rather than assumed.

## Has the deployment changed?

A grade says whether an instance is in good shape. It does not say whether it
is still the same instance as last week. A policy rewritten without gaining
`unsafe-inline`, a proxy replaced with a different product that sets the same
headers, public links that stopped requiring a password and require one again,
a certificate moved to another issuer - none of that has to move a grade, and
an operator watching only the grade sees none of it.

`configuration` is a **fingerprint**: grouped digests of how the deployment is
configured, and nothing it is configured to. See
[ADR 0073](../adr/0073-a-result-fingerprints-the-configuration-it-measured.md).

```json
{
  "configuration": {
    "schema": 1,
    "digest": "9e3c4428...",
    "groups": {
      "tls": {"digest": "89a97538...", "scope": "1d0f4b77...", "facts": 12},
      "headers": {"digest": "cb25144c...", "scope": "b8e1a930...", "facts": 13},
      "sharing": {"digest": "7b8a1ced...", "scope": "44c0ae51...", "facts": 3},
      "authentication": {"digest": "588d045f...", "scope": "0a7be2cc...", "facts": 6},
      "proxy": {"digest": "b7db6daf...", "scope": "ff31c084...", "facts": 5}
    }
  }
}
```

Two scans with the same group digest were looking at the same configuration
for that group; two that differ were not. That is the entire claim, and these
rules are what make it worth reading:

- **Digests only, never the configuration.** A content security policy names
  the origins a deployment trusts, a discovery document can name a tenant, a
  server banner names an internal build. Every fact is hashed into its group
  and discarded; a reader learns *that* sharing changed, never *what* it is
  set to. The block is safe on a public page for the same reason it is safe in
  a ticket.
- **Groups are the questions an operator asks.** "Did TLS change?" is useful;
  "did fact 37 change?" is not.
- **Only what the deployment decides.** The transport group hashes the issuer,
  the key, the signature algorithm and the negotiated protocols - not the
  serial number, the dates or the certificate fingerprint, because a renewal
  is routine. The proxy group hashes the vendor, not the banner, whose build
  number moves with every patch.
- **A scan's own settings are never a fact.** `scope` is a digest of *which*
  facts a group looked at, without their values. Two groups are compared only
  when their scopes match, so a run that stopped inspecting TLS reports "not
  comparable" instead of drift. A group with nothing to hash at all is `none`.
- **It never changes a grade.** Nothing here reaches the rating, the
  severities, the alert line or the exit code.

Read it with `fingerprint.fingerprint_of(result)`, which returns `None` for
both a missing and a malformed block - a report that cannot say is not a
deployment that did not change. `fingerprint.digests(result)` reduces it to
one opaque `scope:digest` string per group, which is what a baseline file, a
webhook receiver and a comparison all store, and
`fingerprint.drift(before, after)` names the groups that differ:

```python
from opencloud_local_scan.fingerprint import digests, drift

changed = drift(digests(last_week), digests(today))  # ('headers',)
```

The plugin prints `Configuration fingerprint: 9e3c4428` with each scan, and
`--baseline` turns the same digests into `No new findings, but the
configuration changed (headers)`.

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

## Every resolved address

`check_all_addresses=True` (`--all-addresses` on `scan`) repeats the
node-dependent part of a scan - `status.php`, the root page's graded headers,
capabilities, the authentication challenge, the identity provider and the demo
accounts - against each address the name resolved to, one after another, and
emits `addressParity`. Each request keeps the hostname in `Host` and SNI and is
pinned to one address through its own session. The addresses are the
resolver's answer, or `pinned_addresses` when given, so a pinned scan never
widens past what the caller vetted; IPv6 is skipped when `ipv6_enabled` is
false. What each address served is listed under `addressObservations`:

```json
{"addressObservations": [
  {"address": "198.51.100.1", "reachable": true, "version": "7.2.3",
   "headers": {"Strict-Transport-Security": true}, "hardenings": {},
   "demoUsersDisabled": true, "error": ""}
]}
```

The first address is the reference; severity follows the worst difference
(demo accounts as `demoUsersDisabled`, another release `high`, anything else
`medium`); waived names are not compared. With one address, or with the
setting off (the default), there is no finding and the list is empty. See
[ADR 0042](../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

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

For an internal CA, keep verification on and set `scanner.tls_ca_file` (or
`COS_SCANNER_TLS_CA_FILE`) to its PEM bundle; `check-opencloud-scanner scan`
also accepts `--ca-file`. This trusts that CA without turning verification off.

### What is measured

`tls.py` does the inspecting and hands `scanner.py` a list of checks; it knows
nothing about ratings. Beyond the handshake and trust it reports:

| Finding | What it asks |
|:--------|:-------------|
| `tlsProtocol` | Is the negotiated version at least TLS 1.2? |
| `tlsDeprecatedProtocol` | Does the server *still accept* TLS 1.0 or 1.1, having negotiated something newer with us? |
| `tlsHostname` | Does the certificate cover the name it was asked for, wildcards and IP addresses included? |
| `tlsChain` | Does the server send its intermediates, or only a leaf that validates by luck? |
| `tlsCertificate` | Does it expire within `tls_min_days`, or has it already? |
| `tlsCertificateLifetime` | Is it valid for longer than the scanner’s 398-day threshold? |
| `tlsCipherSuite` | Is the cipher suite negotiated by this scan modern and forward-secret? |
| `tlsCertificatePolicy` | Does the certificate use an adequately sized key and a modern signature? |
| `tlsAddressParity` | Do the published IPv4 and IPv6 endpoints present the same usable TLS identity? |
| `tlsCaaRecord` | Does the name have a DNS CAA record naming at least one authorized issuer? |
| `tlsDnssec` | Is the zone signed, so that the address every check above rests on can be trusted? Absent rather than failed when the resolver in use does not speak DNSSEC |
| `cookieSecure`, `cookieHttpOnly`, `cookieSameSite` | Do cookies actually observed on the public response carry these attributes? |
| `tlsOcspStapling` | Is a revocation response stapled to the handshake? |

The measurements behind them are in a `tls` block in the result document: the
protocol and cipher, the certificate's subject, issuer, validity window,
remaining days and names, the chain length, and what the deprecated-protocol
and stapling probes found.

```json
{
  "host": "opencloud.example.com",
  "port": 443,
  "reachable": true,
  "protocol": "TLSv1.3",
  "cipher": "TLS_AES_256_GCM_SHA384",
  "cipherBits": 256,
  "trusted": true,
  "hostnameMatch": true,
  "chainComplete": true,
  "chainLength": 2,
  "deprecatedProtocolsProbed": ["TLSv1", "TLSv1.1"],
  "deprecatedProtocolsAccepted": [],
  "ocspStapled": false,
  "ocspNote": "the certificate names no OCSP responder",
  "certificate": {
    "subject": "opencloud.example.com",
    "issuer": "Example CA R3",
    "serialNumber": "03A1...",
    "notBefore": "2026-06-01T00:00:00+00:00",
    "notAfter": "2026-08-30T00:00:00+00:00",
    "daysRemaining": 9,
    "lifetimeDays": 90,
    "altNames": ["opencloud.example.com"],
    "ocspResponders": [],
    "selfSigned": false,
    "keyType": "RSA",
    "keyBits": 2048,
    "signatureAlgorithm": "sha256WithRSAEncryption"
  }
}
```

**`null` means "not determined", never "fine".** A check that could not be
performed - `get_unverified_chain()` needs Python 3.13, the deprecated-protocol
probe needs a build that still speaks one, stapling needs the `openssl`
command and a certificate that names a responder - is left out of the findings
entirely rather than recorded as passed. See
[ADR 0013](../adr/0013-transport-security-is-measured-not-assumed.md).

The certificate is decoded from what the server presented whether or not it
verified, so an instance with the self-signed certificate `opencloud init`
generates still gets its expiry, names and lifetime checked. Two probes are
optional at the call: `probe_deprecated` opens one extra handshake per old
protocol, and `check_stapling` runs one `openssl s_client` with a fixed
argument list and no shell.

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

`scan()` raises `ScanError` when it cannot identify OpenCloud: the endpoint is
unreachable, its response is not suitable JSON, version fields are missing or the
product is different. Cases where a service answered raise `NotOpenCloud`. By default
the scanner retries an unsuitable HTTPS response without certificate verification and
then over HTTP. `ScannerSettings(stop_when_not_opencloud=True)` stops after the first
such response; the public web application enables it.

The document also carries `addresses`, the IPv4 and IPv6 the hostname resolved
to while the scan ran:

```json
{"addresses": {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7"]}}
```

It is context rather than a finding, and never moves the rating. Addresses
pinned through `ScannerSettings.pinned_addresses` are reported as they are:
the web application validates a name before it lets a scan start and dials
exactly those, so resolving a second time here could name an address the scan
never connected to.

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

## Verifying a fix without a full scan

`opencloud_local_scan.verification.verify` re-measures only the findings it is
given, by running the scanner's own probes for them and nothing else. It is
what `--verify-remediation` is built on (see
[ADR 0072](../adr/0072-remediation-verification-re-measures-named-findings-without-a-full-scan.md)).

```python
from opencloud_local_scan.verification import verify

document = verify(
    "opencloud.example.com",
    ["Strict-Transport-Security", "exposed"],
)
for entry in document["results"]:
    print(entry["id"], entry["passed"], entry["reason"])
```

The document has `domain`, `url`, `verifiedAt`, `probeGroups` (the groups
that actually ran) and `results`, one entry per requested id in the order
given:

| Key | Meaning |
|:----|:--------|
| `id` | The requested id; a family root such as `exposed` covers every `exposed:...` member |
| `verifiable` | False for an id only a full scan can settle (`eol`, `vulnerability:...`, `httpsAvailable`, the address-parity checks) or that this build does not know |
| `passed` | True or false when measured, `None` when nothing was |
| `group` | The probe group that measured it |
| `checks` | The measured findings, in the same shape as `extraChecks` entries |
| `reason` | Why `passed` is `None`, otherwise empty |

Like `scan()`, it measures and never judges: no rating, no waivers, no
remediation plan. `probe_group(id)` tells you in advance which group, if any,
an id maps to. It raises `ScanError` when the instance cannot be reached.

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
