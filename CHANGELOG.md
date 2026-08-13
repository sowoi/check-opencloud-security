# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes are collected under **[Unreleased]** as they are made. The version in
`pyproject.toml` is bumped by hand; when that bump lands on `main`, the release
workflow renames the [Unreleased] heading to that version, writes the same
entry to `RELEASE.md` and uses it as the body of the GitHub release.

## [Unreleased]

## [1.2.1] - 2026-08-13

### Documentation

- Documented shell-completion installation with uv and added an acknowledgment
  of the OpenCloud project to the README.

## [1.2.0] - 2026-08-13

### Added

- **`--baseline PATH` and `--warn-on-new`**, for operators who do not want the
  full state of every instance on every run. The baseline records the findings
  of each run, one entry per host, and `--warn-on-new` then reports `OK` while
  the picture is unchanged and the normal status as soon as anything is new or
  worse. The evidence is never suppressed - only the alert - and three things
  always escalate: a new finding, a lower rating, and a release past its end of
  life, which receives no security fixes and therefore cannot be grandfathered
  in. The first run has nothing to compare against, so it reports normally and
  becomes the baseline; `--warn-on-new` without `--baseline` is rejected rather
  than quietly reporting "nothing new" forever; and a baseline that cannot be
  written is a line of output, never a change of verdict. See
  [Reporting only what changed](README.md#reporting-only-what-changed).
- **`--self-update-check`**, which asks PyPI once a day whether a newer version
  of the plugin has been published and appends a note. Off by default, cached
  under `${XDG_CACHE_HOME:-~/.cache}/check-opencloud-security/`, silent on
  every failure, and it never changes the exit code - whether PyPI answered
  says nothing about the instance being monitored.
- **`--upgrade-self --check-only`** as a second spelling of
  `--upgrade-self check`, because that is the pairing people reach for first.
  Used without `--upgrade-self` it is rejected with a usage error instead of
  being silently ignored.
- **Shell completion** via [argcomplete](https://github.com/kislyuk/argcomplete)
  for both `check-opencloud-security` and `check-opencloud-scanner`. It
  completes option names, the values of the options that take a fixed set, and
  the hardening identifiers of `--ignore-hardening`, which are long enough to
  be worth not typing. Install it with the new `completion` extra
  (`pipx install 'check-opencloud-security[completion]'`); without it nothing
  is registered and the plugin behaves as before. See
  [Shell completion](README.md#shell-completion).
- **A `HEALTHCHECK` in the Dockerfile** that verifies the image rather than an
  instance: the package imports and the two data files it rates against - the
  release schedule and the bundled advisory database - parse. It needs no
  network, so it stays honest on an air-gapped host. Containers running the
  scan service keep using the HTTP `/healthz` probe that `docker-compose.yml`
  already overrides it with.
- **An SBOM and Sigstore build attestations** for every release. The publish
  workflow generates a CycloneDX SBOM from the resolved runtime environment,
  attaches it to the GitHub release, and signs provenance for the wheel and
  sdist with a short-lived Sigstore certificate - so there is no signing key
  for this project to leak. Verify a downloaded artifact with
  `gh attestation verify <file> --repo sowoi/check-opencloud-security`.
- **`.github/copilot-instructions.md`**, so GitHub Copilot picks up the same
  rules `AGENTS.md` already states - the layer boundary between the plugin and
  the scanner library, how a setting travels from the file to
  `ScannerSettings`, and the conventions that are invisible in any single file.
- **A [`docs/`](docs/README.md) folder**, with the deployment walk-throughs
  that were crowding the README - [Icinga Director](docs/icinga-director.md),
  [Ansible](docs/ansible.md), [scheduling](docs/scheduling.md) and
  [troubleshooting](docs/troubleshooting.md) - and worked examples for the
  places this check tends to end up: [Kubernetes](docs/kubernetes.md),
  [CI pipelines](docs/ci.md), [Prometheus and Grafana](docs/prometheus.md),
  [webhook adapters](docs/webhook-recipes.md) for Slack, ntfy and
  Alertmanager, and [fleets of instances](docs/many-instances.md). The README
  keeps a guide table and links into each of them.

### Changed

- **`--configure` now edits the configuration instead of starting from
  scratch.** The file already on disk is loaded and every stored value is
  offered as the default for its question, so Enter keeps it and only what
  needs changing has to be typed; `-` removes a configured value, and keys the
  wizard has no question for survive untouched instead of being silently
  dropped. Before saving it offers a test scan of the host with the answers
  just given, and diagnoses the usual failures (certificate, unreachable, not
  an OpenCloud) rather than only reporting them. A failing scan does not block
  saving - the file may well be written somewhere that cannot reach the
  instance. `check-opencloud-scanner configure --no-test-scan` skips the offer.

- **`--dry-run` is gone; use `--upgrade-self=check` instead.** The flag only
  ever meant anything together with `--upgrade-self`, and on its own it was
  accepted and silently ignored - a dangerous thing for a flag whose whole
  promise is "this changes nothing". `--upgrade-self` now takes an optional
  value, `run` (the default when given without one) or `check`, and a bare
  `--dry-run` is rejected rather than obeyed halfway.

## [1.1.0] - 2026-08-13

### Added

- **`--configure`**. An interactive setup that asks for the settings the check
  needs, explains what each one is for and shows an example, then saves them as
  JSON with mode `0600`. Only the host is required; the optional settings are
  offered group by group and skipped unless you ask for them. The file is found
  automatically from then on, so the check runs with no arguments at all.
  `check-opencloud-scanner configure` does the same for the scanner.
- **JSON configuration files.** A configuration file whose name ends in
  `.json` is read as JSON; anything else is still YAML. `./.env.json` and
  `~/.config/check-opencloud-security/.env.json` were added to the paths
  searched automatically.
- **`--upgrade-self`**. Works out whether the plugin was installed with pipx,
  uv or pip and runs the matching upgrade command. `--dry-run` prints the
  command instead. A git checkout is refused, since installing over a working
  copy would leave you editing files that are no longer executed.
- **`SECURITY.md`**, describing what is in scope, how to report a
  vulnerability privately, and what the plugin does with your data.
- **`CODE_OF_CONDUCT.md`**, including the rule this project cares about most:
  no credentials and no production hostnames in a public thread.
- Issue forms for a bug, a wrong finding or rating, and a feature request,
  plus a pull request template. The finding form asks for the `--debug` output
  and for whether the setting is one an operator can actually change, which is
  what deciding a hardening report usually turns on.
- README: how to feed the webhook into an Uptime Kuma Push monitor.
- **`--concurrency` / `COS_SCANNER_CONCURRENCY`**. Runs the scanner's probes in
  parallel instead of one after the other, which shortens a scan considerably -
  most of all when debug-port probing runs into a firewall. Defaults to `1`,
  meaning no multithreading and exactly the previous sequential behaviour;
  values above `32` are clamped. The setting changes only the timing: findings
  and their order are identical whatever it is set to.

### Changed

- **The version is now declared once, in `pyproject.toml`.**
  `opencloud_local_scan.__version__` derives it from the installed package
  metadata, or from `pyproject.toml` itself when running out of a checkout, and
  `check_opencloud_security.py` imports that instead of carrying its own
  literal. A release is still cut by editing `pyproject.toml` by hand, but the
  three numbers can no longer drift apart.
- Documentation now describes the scan backend simply as the built-in scanner.
- **Release notes are collected under `## [Unreleased]`.** Changes are written
  down as they are made; `scripts/release_notes.py` renames that heading to the
  version from `pyproject.toml` when a release is cut, writes the same body to
  `RELEASE.md` and leaves a fresh empty `## [Unreleased]` behind. The version
  itself is bumped by hand and is still the only thing that triggers a release.
  `--require-unreleased` refuses to fall back to generated commit-subject notes.

## [1.0.0] - 2026-08-12

First release. A Nagios/Icinga plugin that checks an OpenCloud instance for
known vulnerabilities and misconfiguration. The plugin scans entirely on its
own, using a built-in scanner. The ratings follow the scale of the
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
