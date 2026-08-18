# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes are collected under **[Unreleased]** as they are made. The version in
`pyproject.toml` is bumped by hand; when that bump lands on `main`, the release
workflow renames the [Unreleased] heading to that version, writes the same
entry to `RELEASE.md` and uses it as the body of the GitHub release.

## [Unreleased]

## [1.5.5] - 2026-08-17

### Added

- Live screenshots of the hosted scanner and a completed scan of the OpenCloud
  demonstration instance in `img/`, shown in the main and Docker Hub READMEs.

### Fixed

- `ProductName: Infinite Scale` now identifies ownCloud's renamed product and
  stops the scanner before it rates a non-OpenCloud instance against OpenCloud
  lifecycle data, advisories and hardening defaults.
- The Prometheus exporter now binds to `127.0.0.1` by default rather than all
  network interfaces. Remote scrapes require an explicit listen address.

## [1.5.4] - 2026-08-17

### Added

- `adr/`, with a decision-record template and lifecycle guidance. Future
  durable architecture changes now require an ADR, and agent guidance directs
  contributors to read and maintain the relevant records.

### Changed

- The Docker Hub README now includes complete `docker run` and standalone
  Docker Compose examples, so the frontend scanner can run without cloning the
  repository.

## [1.5.3] - 2026-08-17

### Changed

- Bump version 1.5.3
- Docker Hub publication now documents that `DOCKERHUB_TOKEN` needs read,
  write and delete scopes and that its account needs Admin repository access,
  so image descriptions remain a required part of a successful publish.

## [1.5.2] - 2026-08-17

### Added

- `docker/dockerhub-readme.md`, the Docker Hub description for the web image.
  The publish workflow submits it after every image push, so release
  instructions for GitHub, Docker Compose and `docker pull` stay with the
  image.

### Changed

- The Docker Hub publishing workflow now uses the Node 24 Docker actions.
  Buildx publishes the existing max-level provenance and SBOM directly to
  Docker Hub, avoiding a second GitHub attestation request that could fail
  after the image was already published during a GitHub service outage.

## [1.5.1] - 2026-08-17

### Added

- `docker/docker-compose.dockerhub.yml`, a self-contained frontend scanner
  deployment that pulls `okxo/opencloud-scanner:latest` for the web service and
  ARQ worker while retaining the queued worker, hardened runtime and ephemeral
  Redis configuration. The existing local-build Compose files remain unchanged.

## [1.5.0] - 2026-08-17

### Added

- **A hosted instance to try, at <https://scan.okxo.de>.** The web application
  from this repository, running: paste an address, read the grade, install
  nothing. It is now the first thing the README offers, linked from
  `docs/README.md`, `docs/webapp.md` and `webapp/README.md`, and listed on PyPI
  as the project's "Live demo". The README says plainly what using it means -
  the scan runs from that server, so it sees only what the public internet
  sees, and anything private still wants the plugin or your own deployment.
- **`--release-track auto`**, and `auto` as a value of
  `scanner.release_track`, `COS_SCANNER_RELEASE_TRACK` and the web form. It
  asks the release schedule which track the installed release belongs to,
  which is the same answer as leaving the track unset - said out loud, so one
  configuration can cover instances on different tracks without declaring a
  track that is wrong for half of them.
- A workflow that re-checks the OpenCloud links this project documents after
  every merge into `main`, and once a week.
  `scripts/check_documentation_links.py` collects every link to
  `opencloud.eu`, `docs.opencloud.eu` and the OpenCloud repositories from the
  documentation, the code and the configuration and requests it. A dead link
  fails the run; a redirect is reported but does not, because `opencloud.eu`
  redirects to a language version and a job that always fails is a job nobody
  reads. A finding that explains itself with a link nobody can follow is a
  finding nobody can act on.
- The web application is published to Docker Hub as **`opencloud-scanner`**,
  built for `linux/amd64` and `linux/arm64` from `docker/Dockerfile.web` with
  provenance and an SBOM attached. `edge` follows `main`; `latest` and the
  version tags only move when the version in `pyproject.toml` names an image
  that does not exist yet, so a documentation commit cannot republish
  `latest` from a tree that is not the released one. The account, the token
  and the optional namespace come from repository secrets - nothing in the
  repository names an account, and the job skips itself rather than failing
  when they are absent, so a fork does not go red over a credential it was
  never given.

### Changed

- **`auto` is now the default release track**, on the command line, in the
  configuration file and on the web form. It is the verdict an undeclared
  track always received, so nothing is rated differently - it is now recorded
  as `auto` rather than left blank, which is the difference between a result
  that says "the schedule worked this out" and one that says nothing. The web
  form previously defaulted to `production`, where any fixed guess is wrong
  for somebody: `production` calls a current rolling instance out of date and
  `rolling` reports an end of life a production instance has not reached.
  Naming a track still overrides it everywhere.
- **The setup wizard asks for the release track on its own**, with a note on
  what auto-detection does. It used to sit inside the update check group, so
  an operator who declined that group - reasonably, having no interest in
  where the newest release is looked up - was never asked about the setting
  that decides every lifecycle verdict.
- **The palette is brighter, and now readable where it was not.** Each status
  colour became three tokens instead of one: `--x` paints the dial, the rules
  and the borders, `--x-soft` is the tint behind them, and the new `--x-ink`
  is the tone that carries text on that tint. The single tone had to be both
  at once, which is why the amber and green tags sat at 2.9:1 - below WCAG AA,
  on the two labels that say a check passed or nearly did. Every text pair in
  both light and dark mode now clears 4.5:1 and every graphic tone 3:1, while
  the surfaces, the brand blue and the teal accent all moved lighter. The
  hard-coded glows and the white button label became tokens as well
  (`--brand-glow`, `--accent-wash`, `--on-brand`), so the palette has one
  source again - the button label is dark in dark mode, where its gradient is
  the light brand tone.
- The header says what the page is rather than what the package is called:
  the brand line is now just *Security scan for OpenCloud instances*. The
  package name sat above that same sentence in smaller type, so a first-time
  visitor read a repository name before they read what the site does. It is
  still named in the footer and linked from the source line.
- **A release ahead of its declared track is no longer end of life.** Running
  the current rolling release while declaring the production track rated the
  instance `F` and alerted `CRITICAL` - about a machine running the newest
  OpenCloud there is, with everything the production track ships and more. Such
  an instance is now reported as *ahead of* its track, with the current release
  of that track named. The `F` is kept for what it was meant for: a release
  *behind* the current one of the declared track, which really is missing
  fixes. The upgrade recommendation still never points backwards.

### Fixed

- The test suite no longer reads the configuration of the machine it runs on.
  A developer who had run `--configure` for a real instance had
  `~/.config/check-opencloud-security/.env.json`, and the tests that ask "what
  does the plugin see when nothing is configured?" saw their host, their track
  and their waivers instead of nothing - four failures locally, none in CI, and
  a real hostname printed into the failure output. Discovery is now pointed at
  an empty home and an empty working directory, created per test.
- The web application tests no longer warn on every run. Starlette 1.6
  deprecated driving `TestClient` with `httpx`, so the test group asks for
  `httpx2` instead. A warning that is printed on every green run is a warning
  nobody reads when it finally matters.

### Security

- **A server that reports ownCloud or Nextcloud in `status.php` is no longer
  scanned as OpenCloud.** All three serve the same endpoint - OpenCloud
  inherited it from them - so the document alone never said what was running,
  and the scan happily rated an ownCloud instance against OpenCloud's release
  schedule, advisories and hardening defaults. That is a confident answer about
  the wrong software, which is worse than no answer: the scan now stops with an
  error naming the product it found.

## [1.4.0] - 2026-08-15

### Added

- **A reverse proxy check, and one for the identity provider.**
  `reverseProxyDetected` records whether anything answers in front of the
  instance - a `Server` header naming Nginx, Caddy, Cloudflare and the like, or
  a forwarder-only header such as `Via` - and `identityProviderDetected`
  records whether the sign-in issuer could be established at all. Both are
  severity `low` and cost the rating nothing by design: Traefik and HAProxy
  announce nothing by default, so their absence is weak evidence and must not
  become a grade. When no provider is found, the explanation points at
  OpenCloud's own documentation, because the usual cause is a proxy that does
  not forward `/.well-known/`.
- The landing page of the web application now credits OpenCloud and links to
  the project and its documentation, alongside the notice that this scanner is
  independent of OpenCloud GmbH. The result page links to the same
  documentation when no identity provider was found, and shows the reverse
  proxy when one was.
- **The scan now works out who signs users in.** It reads
  `/.well-known/openid-configuration`, or the redirect the instance answers it
  with, and records the issuer in `identityProvider`: whether one was found,
  whether it is external to the instance, and which product it looks like -
  Keycloak, Authentik, Authelia, Zitadel, Entra ID and a few more are
  recognised by their issuer URL. Nothing is submitted to the instance to
  establish this: the discovery document and the `Location` header are read,
  and no login form is ever filled in. It is context rather than a verdict -
  the built-in provider fails nothing - and the result page shows it.
- The release track on the web form. `release_track` joins `target_url`,
  `ignore_hardenings` and `output_format` as the fourth - and last - thing a
  request may choose: `rolling`, `production` or `lts`, defaulting to
  `production`. It is the web equivalent of the plugin's `--release-track`, so
  it changes how a version is rated, never how hard the instance is probed,
  and an unknown value falls back to the default rather than failing the scan.
  The result page shows which track it was rated against.
- `COS_WEB_ENABLE_DOCS`, which serves the OpenAPI schema, Swagger UI and
  ReDoc at `/openapi.json`, `/docs` and `/redoc`. Off by default, because
  Swagger UI is the only page in this service that loads a script from another
  origin: enabling it relaxes the policy on those two pages and nowhere else,
  and logs `api_docs_enabled` at startup so a deployment says so.
- The backend version in the footer of every page of the web application, as a
  badge linking to the releases, matching what `/healthz` reports. A result is
  only as trustworthy as the build that produced it, and a bug report needs
  that number.
- The release refresh now also updates the README. `scripts/update_release_schedule.py`
  rewrites the generated table between the `release-schedule` markers with the
  current release of each track, so the documentation cannot go on quoting a
  version that has already been superseded. `--no-readme` refreshes only the
  data file, and `--check` now fails when the table has drifted from the
  schedule.
- A friendly way out of a rate limit in the web application: a 429 now says so
  casually and points at the project on GitHub, so whoever hit the limit can
  run exactly the same check themselves without one. The pointer is in the
  page and in the JSON response alike.
- A trademark and affiliation notice in the README, the documentation index,
  the library README, the web application guide, the footer of every page of
  the web application and the bundled quick start: this project is independent
  of OpenCloud GmbH, and all rights in OpenCloud remain with them.
- A self-hosted public scan service: a FastAPI web application with a
  hand-written frontend, an ARQ worker and Redis for ephemeral state. A
  visitor submits a URL and gets the same rating the plugin produces, with no
  account, no database and nothing kept beyond the result TTL.
- Graceful queueing for the web application. Requests beyond the configured
  worker count are accepted and queued in FIFO order rather than refused, and
  the page shows the position in line while the scan waits.
- Per-scan isolation in the web application: every submission gets a `uuid4`
  capability and its own `scan:{uuid}:*` Redis namespace, every key carries a
  TTL, there is no scan listing endpoint, and an unknown or expired scan is a
  404 that reveals nothing.
- An SSRF guard and two independent rate limits for the web application.
  Targets must resolve exclusively to public unicast addresses and are
  re-resolved in the worker against DNS rebinding; client and target limits
  answer 429 with `Retry-After`, and client addresses are only ever kept as a
  peppered HMAC.
- `docker/Dockerfile.web` and `docker/docker-compose.yml`, orchestrating the
  web application, the worker and Redis with concurrency fixed server-side.
- `scripts/build_web_bundle.py` and a release workflow step that publish
  `check_opencloud_security_web.tar.gz`, the complete web application with a
  SHA-256 checksum, as a GitHub release asset.
- [The public scan service](docs/webapp.md): deployment guide covering every
  `COS_WEB_*` setting, the request pipeline, the isolation model and the HTTP
  API.
- **Office and calendar integrations are reported as observations.** The
  result document gains an `integrations` block: `office` says whether
  `/app/list` names a registered app provider such as Collabora, `calendar`
  says whether anything answers `/.well-known/caldav`. Neither becomes a check
  and neither can move the rating - a registered provider says nothing about
  whether it is configured well. Audit logging is deliberately **not** checked:
  the audit service consumes the internal event bus and exposes no HTTP surface
  or capability, so there is nothing an unauthenticated client can read.

### Changed

- **`basicAuthDisabled` no longer costs two grades.** It is a `medium`
  finding, capping the rating at 4 rather than 3, and a `low` one when an
  external identity provider handles the interactive login. CalDAV, CardDAV
  and WebDAV clients cannot speak OpenID Connect and have nothing but basic
  authentication to use, so an instance that wants a calendar has to leave it
  on; rating that as a serious failure told operators something they were
  right to disbelieve. It stays a finding - a password does work on every
  request - and the remediation now says to hand those clients app tokens
  rather than account passwords.
- **Every Dockerfile and compose file now lives in `docker/`**, and the build
  context of each is the repository root. `docker/docker-compose.yml` is the
  complete web application - frontend, backend worker and Redis - so
  `cd docker && docker compose up --build -d` is a working deployment with no
  further arguments. The plugin's own scan service moved to
  `docker/docker-compose.monitoring.yml`, and building the plugin image is now
  `docker build -f docker/Dockerfile .`. `.dockerignore` stays in the root,
  which is where the daemon reads it from.
- CI actions moved off the deprecated Node 20 runtime: `actions/checkout@v7`,
  `astral-sh/setup-uv@v10.0.0`, `actions/dependency-review-action@v5.0.0`,
  `actions/attest-build-provenance@v4`, `peter-evans/create-pull-request@v8`,
  and `actions/attest-sbom` replaced by `actions/attest@v4`, which it now only
  wraps. The Bandit scan no longer uses an unversioned third-party action: it
  installs Bandit and uploads the SARIF itself, with the same thresholds and
  exclusions. Dependabot now watches GitHub Actions and the container images
  as well, so this does not have to be noticed by hand again.
- The PyPI wheel and sdist now explicitly exclude `frontend/` and `webapp/`.
  Installing the plugin on a monitoring host must not bring in FastAPI, Redis
  or ARQ; the web application ships as a release asset instead.

### Fixed

- Removed stale root-level `Dockerfile` and `docker-compose.yml` copies so CI
  and contributors use the canonical container definitions in `docker/`.

### Security

- Response bodies are read up to `max_response_bytes` (8 MiB) and no further,
  so a target answering with an endless body cannot hold a worker forever.
- Advisory links are rendered only when they are `http://` or `https://`,
  `peter-evans/create-pull-request` is pinned to a commit rather than a
  mutable tag, the plugin logs a webhook URL as scheme and host only because
  the rest of it is usually the credential, and the scan service compares its
  auth token as bytes so that a non-ASCII header is a 401 rather than a dead
  handler thread.

### Documentation

- The landing page explains how to drive the API from a script - the two curl
  calls, the four accepted fields, the actual rate limits and where to get the
  code when they bite - and links to Swagger, ReDoc and the schema when the
  documentation is enabled. `frontend/static/vendor/README.md` names the
  vendored packages, versions and licences.
- `README.md` and `opencloud_local_scan/README.md` document the `integrations`
  block and, as explicitly as it deserves, what the scan does not answer:
  audit logging, whether an integration is configured correctly, and anything
  needing credentials.
- [`docker/README.md`](docker/README.md) and
  [`frontend/README.md`](frontend/README.md): what each container file builds
  and why the build context is the repository root, and the frontend's rules,
  design tokens, template contract and how to run one of your own.
- [`webapp/README.md`](webapp/README.md): the web application and its frontend
  for whoever changes them or writes a client - every route and its
  status codes, how to reach Swagger, the four fields a request may send and
  why nothing else is accepted, every setting worth knowing on day one, and
  the template contract for running a frontend of your own.
- The issue templates ask where a problem happened - plugin, scanner library,
  web backend or page - and the pull request template has a checklist for a
  change to the web application or the frontend.

## [1.3.0] - 2026-08-13

### Added

- Itemized baseline diffs in text, Markdown, and Slack Block Kit JSON,
  covering CVEs, hardening and check changes, rating/lifecycle trends, and
  installed/update-version shifts. Webhooks now carry the structured diff.
- Native Prometheus text output and a lightweight `/metrics` exporter for
  Kubernetes and cloud-native monitoring. The exporter refreshes scans on
  demand with a configurable cache interval and requires no extra dependency.

### Changed

- Multi-host checks now run one worker per target, up to the configurable
  default ceiling of five. A single-host check remains single-threaded, and
  result blocks and Nagios perfdata remain isolated and ordered by input host.

## [1.2.3] - 2026-08-13

### Security

- Block webhook notifications to private, loopback, and link-local addresses
  by default to prevent server-side request forgery. Internal receivers require
  the explicit `--allow-private-webhooks` / `COS_ALLOW_PRIVATE_WEBHOOKS` opt-out.

## [1.2.2] - 2026-08-13

### Documentation

- Clarified that the built-in scanner is not exhaustive and that its rating
  does not guarantee an OpenCloud instance is completely secure.

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
