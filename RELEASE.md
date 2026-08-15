## check-opencloud-security 1.4.0

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

- The web stack now runs Redis 8.10; Redis 7 is end of life.
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

