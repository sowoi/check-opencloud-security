# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

New entries are added on top by the release workflow whenever the version in
`pyproject.toml` changes; the same entry is written to `RELEASE.md` and used as
the body of the GitHub release.

## [1.0.1] - 2026-08-12

### Changed

- Bumped version to 1.0.1
- Version 1.0.0 commit
- Initial commit

### Documentation

- Release notes for v1.0.0 [skip ci]

## [1.0.0] - 2026-08-12

First release. A Nagios/Icinga plugin that checks an OpenCloud instance for
known vulnerabilities and misconfiguration. OpenCloud has no public scan API,
so the plugin scans entirely on its own. The ratings follow the scale of the
Nextcloud scan API, so that existing thresholds and dashboards keep their
meaning.

### Added

- **Built-in scanner** (`opencloud_local_scan`). Reads `/status.php` and the
  unauthenticated capabilities endpoint, evaluates security headers, and rates
  the instance on a `0`-`5` scale. No data about the instance leaves the
  network; hostnames, IP addresses, IPv6 and custom ports are all accepted.
- **OpenCloud-specific checks**: unauthenticated WebDAV, Graph and OCS
  endpoints; exposed `opencloud.yaml`, `proxy/server.key`, the idm boltdb,
  `.env` and `.git/config`; reachable service debug ports and `/metrics`,
  `/config`, `/debug/pprof` handlers; enabled HTTP basic authentication;
  version disclosure via response headers and WebFinger; directory listings;
  maintenance mode and pending database upgrades.
- **Catch-all detection.** OpenCloud's single-page frontend answers unknown
  paths with HTTP 200, so the scanner learns what a nonexistent path looks
  like before reporting any path as exposed.
- **TLS inspection** with graceful degradation: verified HTTPS, then
  unverified HTTPS with a `tlsTrusted` finding, then plain HTTP with a
  critical `httpsAvailable` finding. Covers handshake, protocol version and
  certificate expiry.
- **Correct version handling.** `/status.php` reports hardcoded legacy
  `version`/`versionstring` fields for old sync clients; only `productversion`
  is the real release. Instances that offer nothing else are reported as
  `legacyVersion` instead of being rated against a version that means nothing.
- **Hardening reporting** derived from what the instance actually reports -
  HSTS strength, CSP quality, basic auth, public-link password and expiry
  enforcement, user enumeration and password policy - rather than inferred
  from the version number.
- **Update check** against the OpenCloud release feed on GitHub, with `auto`,
  `feed`, `pinned`, `bundled` and `off` modes. The offline modes and the
  automatic fallback in `auto` keep an air-gapped or rate-limited setup
  working.
- **Lifecycle-aware end-of-life detection.** OpenCloud maintains three kinds
  of releases side by side, and each has its own support window: *rolling*
  (a release roughly every three weeks, only the newest one receives fixes),
  *production* (roughly every six months, kept alive with patch releases until
  the next production release takes over) and *LTS* (a production line with
  two years of backports). The verdict follows the published release schedule
  in `opencloud_local_scan/data/release_schedule.json`, refreshed on release
  and monthly by a scheduled workflow, because a flat list of major releases
  cannot express three overlapping support windows.
- **`releaseType` and `lifecycle` in the result document**, reporting the
  release line, its track, its release date, when support ends, how many days
  are left and which release to upgrade to. The plugin prints a
  `Release lifecycle:` line and a `support_days_left` performance value, and
  the webhook payload carries both fields.
- **The update check is track aware.** A release feed only knows the newest
  release overall, and on OpenCloud that is always a rolling one. Offering it
  to a production or LTS instance would silently move it onto a track with a
  three-week support window, so those instances are offered the newest release
  of their own track instead. `UpdateInfo` carries `track` and
  `newestRelease`, so the newest release overall is reported but not presented
  as the thing to install.
- **`--release-track` declares which track an instance follows** (`rolling`,
  `production` or `lts`). Without it a version is judged as generously as is
  true, which is right when nobody has said otherwise but wrong for anyone
  deliberately on the rolling track, where `7.2.3` went out of support the day
  `7.4.0` shipped. With a declared track the version is judged on that track
  alone, the update recommendation follows it, and the output marks the track
  as declared rather than inferred. A version that was never published on its
  declared track is reported with the reason rather than an empty support
  date, and is never told to "upgrade" to an older release.
- **`--ignore-hardening` accepts a finding you are not going to fix.** Some
  findings are real but not actionable in a given environment - a CSP that
  cannot be tightened without breaking the web UI, an HSTS header owned by a
  reverse proxy. The rating is recalculated without the waived finding, so
  accepting one genuinely changes the grade instead of leaving the check
  permanently yellow. The option is repeatable, takes a comma-separated list,
  understands shell-style wildcards (`debugPort:*`), and matches hardening
  measures, security headers, `httpsEnforced` and additional-check ids alike -
  one option for all of them, because `basicAuthDisabled` is both a hardening
  measure and an additional check. A waiver hides an alert, not the evidence:
  waived findings drop out of the alert lines, the `hardenings_missing` and
  `extra_checks_failed` metrics and the webhook payload, but stay in the
  result document flagged with `"ignored": true` and are listed as
  `Ignored by configuration (n): ...` in the output. Only a finding that
  actually failed can be waived, and no waiver can clear an end-of-life
  release.
- **`--debug` explains the rating.** A grade on its own is a verdict without
  an argument, so the check can show its reasoning: where the rating started
  (version and advisory database), which failed check capped it and by how
  much, the final value, and the thresholds that turned it into a WARNING or
  CRITICAL. A failed check that did *not* decide the outcome is listed too,
  marked as such, so nothing looks quietly dropped. The same breakdown is
  available as structured data in `ratingExplanation`, sorted by severity so
  it does not depend on the order the checks happened to run in.
- **Every hardening identifier is explained.** `basicAuthDisabled` and
  `cspWithoutUnsafeInline` say nothing to someone who has to fix them, so the
  `opencloud_local_scan.hardening` catalogue pairs each flag with a
  plain-language meaning, the OpenCloud environment variable that governs it
  (`PROXY_ENABLE_BASIC_AUTH`,
  `OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD`,
  `PROXY_CSP_CONFIG_FILE_LOCATION`, ...) and a link to the documentation.
- **Findings that no setting can clear are recorded but never alerted on.**
  Public-link expiry is hardcoded in OpenCloud, so `publicLinkExpirationEnforced`
  fails on every instance and no operator can fix it; alerting on it trains
  people to ignore the hardening line altogether. Such flags stay in the
  result document and in `--debug`, but are kept out of the alert line, the
  `hardenings_missing` metric and the webhook.
- **Advisory database** matching on the half-open range
  `[introduced, fixed)`, accepting the native, GitHub Advisory and OSV
  formats from the bundled file, extra files and a remote feed.
- **`check-opencloud-scanner`** with `scan` (one-shot JSON) and `serve`
  (HTTP service with `/api/queue`, `/api/result/<uuid>`, `/api/requeue`,
  `/api/scan` and `/healthz`, optional token auth and a per-host result
  cache).
- **Configuration** from a YAML file, `COS_`-prefixed environment variables or
  a secret provider (`secret://`, `file://`, `env://`, opt-in `exec://`),
  with command line > environment > file > default precedence. This includes
  `scanner.release_schedule` for sites with vendor support commitments that
  differ from the public ones, `scanner.release_track` and
  `scanner.ignore_hardenings`.
- **Monitoring integration**: Nagios/Icinga exit codes, performance data
  (`rating`, `vulnerabilities`, `time`, `hardenings_missing`,
  `extra_checks_failed`, `update_available`, `support_days_left`),
  configurable WARNING/CRITICAL thresholds, optional hardening evaluation,
  multi-host runs reporting the worst state, retries with exponential backoff,
  and optional webhook notifications that never change the reported state.
- **Deployment**: a Docker image and `docker-compose.yml`, an Ansible role,
  systemd service/timer and cron examples, Icinga2 and Icinga Director command
  definitions.
- Documentation, a test suite covering the scanner, service, configuration,
  release lookup, thresholds, webhooks, multi-host handling and the plugin
  end to end as a real subprocess, and CI workflows for tests, ruff, mypy,
  bandit, dependency review, multi-version nox runs, PyPI publishing and the
  monthly release-schedule refresh.
