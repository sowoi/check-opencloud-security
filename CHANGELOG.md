# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes are collected under **[Unreleased]** as they are made. The version in
`pyproject.toml` is bumped by hand; when that bump lands on `main`, the release
workflow renames the [Unreleased] heading to that version, writes the same
entry to `RELEASE.md` and uses it as the body of the GitHub release.

## [Unreleased]

### Added

- **CAA record check (`tlsCaaRecord`)**: The built-in scanner now reports
  whether the scanned name has a DNS CAA record restricting which
  certificate authorities may issue for it. The lookup is dependency-free
  and only ever queries the system's own configured resolver - never a
  public one - so nothing new is sent to a third party.
- **Native Slack and Discord webhook formats**: `--webhook-format slack`
  (also accepted by Mattermost and the common Matrix webhook bridges) or
  `--webhook-format discord` posts the result already shaped for that
  receiver, so the adapter script in `docs/webhook-recipes.md` is no longer
  required for the common case. The default is unchanged.

## [1.13.0] - 2026-08-28

### Added

- **TLS cipher and certificate-policy findings**: The built-in scanner now
  flags a weak negotiated cipher suite and certificates with undersized RSA or
  EC keys or MD5/SHA-1 signatures. It records the measured key type, size and
  signature in the result while leaving either check absent when it cannot
  measure the necessary evidence.
- **Automatic updates in the Docker setup wizard**: `docker/setup-wizard.py`
  now asks whether the deployment's pulled images should update themselves
  (or takes `--auto-updates`) and adds a Watchtower service to the generated
  stack when they should - scoped by label to this stack's own containers,
  and pointed at the Docker socket detected for the user running the wizard,
  including the rootless socket under `/run/user/<uid>`.
- **The Docker setup wizard reuses an existing `.env`**: re-running it
  against a directory that already holds one reads the file back and offers
  every value as the default of its question instead of regenerating the
  deployment's credentials.

## [1.12.1] - 2026-08-27

## Fixed

- Fix YAML syntax error in Github actions workflow

## [1.12.0] - 2026-08-27

### Changed

- **Security and release-data safeguards**: Kept advisory ranges and release
  support facts monotonic during refreshes, and validate refresh pull requests
  against their relevant regression tests before review.
- **Search and agent discovery**: Kept query pages out of the sitemap and
  index, emitted valid localized JSON-LD only on public pages, and aligned the
  extended agent guide and discovery capabilities with the implemented API.
- **Documentation search intent**: Made generated OpenCloud Security Scanner
  guide titles and descriptions self-describing when reached directly.
- **Deployment and compatibility evidence**: Require an explicit public origin,
  pin the scheduled OpenCloud integration baseline by digest, and document
  candidate-image review rules.
- **Release operations and metadata**: Added the architecture runbook for
  rolling, production, and LTS releases; `COS_WEB_INDEX_META_TAG` now accepts
  a bounded, validated list of landing-page metadata pairs.
- **Configuration and Authentik guides**: Added directory references for the
  example scanner configuration and the MCP Authentik blueprint.
- **Docker setup documentation**: The setup wizard now leads the Docker Hub
  description, `docker/README.md`, `docs/webapp.md` and `webapp/README.md`, and
  every documented stack recipe carries the now-required
  `COS_WEB_PUBLIC_BASE_URL`, the Redis password and the internal network.
- **Redis hardening**: The Docker setup wizard and every shipped compose stack
  now support `COS_REDIS_PASSWORD` and keep Redis on an internal network with
  no published port, answering the "Redis does not require authentication and
  is not protected by network restriction" finding.

### Added

- **Redis operator guide**: `docs/redis.md` and `/documentation/redis` cover
  what the scan service keeps in Redis and for how long, authentication,
  network isolation, memory and eviction, health signals and troubleshooting.
- **`/.well-known/security.txt`**: An RFC 9116 document with a computed
  `Expires`, naming the project's security policy everywhere and an operator
  address only on the deployment the legal notice belongs to.

### Fixed

- **The Python version matrix actually tested one version**: `nox` installed
  no test dependencies and ran the outer environment's `pytest`, so every
  session reported the same interpreter. Each session now syncs into its own
  environment and asserts the interpreter before running the suite.
- **Python 3.10 compatibility**: `scripts/release_notes.py` and its test
  imported `tomllib`, which does not exist before 3.11. Both now read the
  project version without it.

## [1.11.4] - 2026-08-26

## Added
- **Legal Notice Badge**: Added an explicit Legal Notice link to the footer, 
  displayed exclusively when accessing the site via scan.okxo.de.

## [1.11.3] - 2026-08-26

## Changed
- **Documentation layout**: Removed redundant H1 tags.
- **Release versions**: Updated OpenCloud release versions to current

## [1.11.2] - 2026-08-26

### Added
- **WebMCP Protocol Support**: Added tooldescription and optional toolautosubmit
  declarative attributes to HTML forms, enabling AI agents to auto-discover and 
  interface directly with site features.
- **Input Parameters Context**: Added descriptive description attributes to all 
  security scanner form controls (target_url, release_track, output_format) for 
  richer AI agent understanding.
- **Structured Data (Schema.org)**: Implemented JSON-LD WebApplication schema 
  metadata within the main template <head> to improve search engine rich snippets 
  and AI crawler categorization.

## [1.11.1] - 2026-08-26

### Added

- **llms-full.txt Documentation**: Introduced a comprehensive, self-contained 
  Markdown documentation file designed for Large Language Models (LLMs) with  
  extended context windows.

### Changed

- **Updated /llms.txt layout**: follow standard Markdown guidelines, including 
  blockquote summaries, explicit link structures, and references to full 
  documentation.

## [1.11.0] - 2026-08-26

### Added

- **Browser agents can use the page already in front of them.** The landing
  page registers a WebMCP scan tool, result pages register status and export
  tools for their current UUID, and `/llms.txt` maps the API, workflow, MCP,
  and WebMCP surfaces. Tool schemas come from the same server-side catalogues
  as the rendered controls, every execution uses the existing JSON API, and
  the front end's AI page documents the tools and their security boundary.
- **Deployments can add one optional landing-page meta tag.**
  `COS_WEB_INDEX_META_TAG=name=content` is passed through both Docker Compose
  stacks and rendered as escaped `name` and `content` attributes. Raw HTML,
  reserved page metadata, and named surveillance-platform tags are refused.
- **False results have a direct reporting path.** Completed result pages link
  to the repository issue tracker for false positives and false negatives,
  without putting the scan UUID or target into the URL.
- **Recognised identity providers link to their advisory database.** Scan
  overviews for Keycloak, Authelia and Authentik point to the provider's
  official GitHub Security Advisories page. The result reserves a version
  field but reports that it is unavailable rather than guessing, because none
  of the three exposes a product version without authentication.

### Changed

- **HTML action routes now negotiate structured responses.** A request for
  `application/json`, or a form choosing `output_format=json`, receives the
  same scan record or acceptance payload as the JSON API. The frontend CSS
  also drops selectors that no template or script can reach.
- **The MCP switch governs both browser and server tools.** Turning
  `COS_WEB_ENABLE_MCP` off now removes WebMCP registration from the landing
  and result pages as well as disabling `/mcp`.

### Security

- **Translated HTML now has an explicit trusted boundary.** Only
  source-controlled catalogue markup is treated as renderable HTML, while
  every interpolated placeholder is converted to text and escaped.

## [1.10.0] - 2026-08-25

### Added

- **The resolved addresses are part of the result.** Every scan now records
  the IPv4 and IPv6 the instance's name pointed at while it ran, as
  `addresses` in the result document, and a web result page prints them under
  **Resolved to** in the overview. A name that does not resolve, or a scan of
  a bare address, reports empty lists rather than an error, and the block
  never moves the rating - it is there because "it answers on the address you
  retired last month" explains a surprising number of surprising results. The
  addresses the web application already validated are reported unchanged, so
  the document names what the scan actually dialled rather than a second
  lookup's answer.
- **A one-liner for whoever would rather not use the website.** The published
  image `okxo/opencloud-scanner` carries both entry points, so
  `docker run --rm --entrypoint check-opencloud-security
  okxo/opencloud-scanner:latest --host opencloud.example.com` runs the same
  check on your own machine, with no rate limit, no queue and nobody else
  learning which instance you look after.
  [`docs/docker-oneliner.md`](docs/docker-oneliner.md) collects the JSON
  variant, waivers, release tracks, private networks, a shell function and
  the container-free `uvx` form.
- **A "Docker" tab in the web interface.** The new page at `/cli` shows that
  one-liner where the hesitation actually happens - in the primary
  navigation, on the site being asked for an address - and links the full
  documentation. It is a public, indexable page like the other explanations.
- **A "Grades" tab explains the real rating scale.** The new `/grades` page
  takes its letters from the plugin's `RATE_MAP` and its finding ceilings
  from the scanner, explains why the 0-5 scale has no `B`, and shows what
  `A+`, `A`, `C`, `D`, `E` and `F` mean, what holds each one down and how the
  ordered remediation plan helps move an instance upward.
- **A local "Docs" tab for the CLI.** `/documentation` collects the quick
  start, the two entry points, everyday flags, configuration precedence and
  monitoring patterns in the web interface. Every full operator guide below
  it is a separate local HTML page generated from `README.md`,
  `opencloud_local_scan/README.md` or `docs/`; CI rejects stale generated
  pages, while production serves plain checked-in templates and carries no
  Markdown parser.
- **A small static search now reaches all public guidance.** The header field
  opens `/search`, where a same-origin release index is filtered in the
  browser. The manifest can read public templates only, and the release
  workflow is the sole automatic writer, so result pages, UUIDs, submitted
  addresses and exports have no path into the index.
- **The complete web interface now speaks four languages.** Stable string
  catalogues cover English, German, Spanish and French across navigation,
  forms, progress, results, grades, search and page metadata. The browser's
  weighted language preference is selected automatically, while an accessible
  switcher stores an explicit choice in an `HttpOnly`, `SameSite=Lax` cookie
  and works without JavaScript. Generated guide bodies remain English with a
  localized notice; their chrome and release-built search indexes follow the
  selected language. API, MCP and export contracts remain English, and remote
  scan evidence remains verbatim.

### Changed

- **The frontend header stays on one line.** Its brand is now the shorter
  *Security scan for OpenCloud*, controls and links do not wrap, and the
  compact menu takes over at tablet and narrower desktop widths before the
  translated navigation can split across lines. The landing-page and
  completed-result screenshots now show this header and the language switcher.
- **The web interface now uses the Halo design system.** Space Grotesk,
  Inter and JetBrains Mono are self-hosted with their licences; cold frosted
  panes float over an iris-and-magenta aurora, the target address is a
  full-width command bar, and every transition has a reduced-motion answer.
  Light and dark schemes use separate contrast-checked tokens, the artwork
  and OpenGraph image match them, and `DESIGN.md` explains how to extend the
  system without turning it into a collection of one-off styles.
- **Build contexts and source archives carry less development material.**
  Docker now excludes ADRs, guides, screenshots, deployment sources and
  maintainer-only files that neither image copies or runs; Git archives omit
  ADRs, screenshots and agent/design guidance as well. Both Dockerfiles still
  use explicit `COPY` lists, and the web release bundle remains an explicit
  allow-list, so runtime templates, generated Docs pages and licences stay in
  their intended artefacts.

### Security

- **A scan submission is now a constrained instance base address.** The
  browser gives immediate feedback and the server enforces the boundary: a
  target may have an `http` or `https` scheme, a hostname, an optional port
  and a plain subfolder path, but no query string, fragment, credentials,
  path parameters, escapes, traversal, whitespace or request-control
  characters. The scanner chooses every OpenCloud endpoint itself, so
  nothing appended by a visitor can become an
  outgoing payload or parameter. Redirects sent by the instance remain
  usable and are independently revalidated before they are followed.
- **The documented demo accounts are now a critical finding.**
  `IDM_CREATE_DEMO_USERS` fills OpenCloud's built-in identity management with
  five accounts - `dennis`, `margaret`, `alan`, `lynn`, `mary` - whose
  passwords are printed in OpenCloud's own documentation, and `dennis` is an
  administrator. When the instance signs users in with its *own* provider, the
  scan now asks `/ocs/v1.php/cloud/user` with each documented pair;
  `demoUsersDisabled` fails at severity `critical` when one is accepted, which
  caps the rating at `D` and puts the account names in the alert line.
  Nothing is guessed - only the published defaults are sent, and only to the
  instance's own provider, never to an external Keycloak or Authentik - and an
  endpoint answering unauthenticated requests reports nothing rather than
  inventing a demo user. `--debug` and `describe_hardening()` explain the
  finding and name `IDM_CREATE_DEMO_USERS=false`, along with the fact that
  turning it off does not delete accounts that already exist.
- **The admin documentation now drives three more remote checks and closes a
  password-policy blind spot.** Wildcard iframe message origins are `high`,
  delegated authentication without a trusted origin is `critical`, and a
  matching OpenCloud listener exposed directly on port 9200 is `high`.
  Capabilities that explicitly show a disabled password policy now fail
  `passwordPolicyEnforced` instead of silently omitting it. A Let's Encrypt
  staging issuer also names the exact production-certificate fix in the
  existing `tlsTrusted` finding. The audit deliberately does not guess admin
  passwords, probe sibling products or penalise OpenCloud endpoints that are
  public by design.

### Fixed

- **Signed reports are deployable from every supported setup path.** The
  Docker stacks and setup wizard now expose `COS_WEB_EXPORT_SIGNING_KEY`, the
  unattended wizard generates it, PDF/SARIF/JSON signatures are each tested
  against their exact downloaded bytes, MCP export results retain the
  signature header, and the release bundle now includes
  `scripts/verify_export.py`.

## [1.9.3] - 2026-08-24

### Added

- **A real OpenGraph share image.** `og:image` now points at a hand-drawn
  1200x630 PNG (`frontend/static/img/og-image.png`, rendered from the
  `og-image.svg` beside it) with `og:image:type`, `og:image:width` and
  `og:image:height` metadata, because most crawlers and chat clients will not
  draw the SVG the pages previously shared.

### Changed

- **Body type is now Inter, self-hosted.** The web application serves the
  five weights it uses from `/static/fonts/` (SIL OFL 1.1, license beside the
  files) with the system sans as the fallback while the file arrives. The
  serif display face and the monospace dossier labels still come from the
  reader's own system stack, and nothing is fetched from a font service.
- **The accent colour is a warm ember in daylight.** The teal accent became a
  deep orange in the light scheme (`#c2410c`) and now carries the primary
  action button as well as the live marker and the assurance row, so the one
  thing a page wants done is the first thing the eye finds; the dark scheme
  keeps the clear teal (`#5eead4`) it always had. The logo, hero and expired
  artwork and the backdrop aurora were re-tinted to match.

## [1.9.2] - 2026-08-21

### Fixed

- **Grid height fixed. **

## [1.9.1] - 2026-08-21

### Changed

- **The web application has a new frontend design.** The whole design system
  in `frontend/static/css/app.css` was rebuilt as a field report: serif
  display type against warm bone paper, monospace dossier labels with a drawn
  leading rule, hairline rules instead of filled chrome, frosted-glass cards
  that diffuse the backdrop they float over, and a reticle motif that frames
  the scan form with registration brackets. The backdrop is a faint
  engineering grid over a quiet aurora with a grain of baked-in noise, the
  landing page states its promises as a ruled specification row, and a tiny
  `reveal.js` arrives blocks as they scroll into view - decoration only, so
  the page reads complete with scripting blocked. Waiting is theatre now
  too: a beam travels the progress card while a scan runs, and when the
  result is in, the page settles, announces the report and falls away before
  the rendered answer arrives. The automatic light and dark modes stay,
  driven as before by one token list and its `prefers-color-scheme: dark`
  counterpart, reduced motion still turns every animation off (and skips the
  hand-off entirely), and the artwork was redrawn to match: the hero is a
  technical instrument drawing with the same hand-drawn, two-scheme
  discipline as before.


## [1.9.0] - 2026-08-21

### Added

- **Monitoring hosts can refresh reference data without upgrading the plugin.**
  `check-opencloud-scanner refresh-data` validates and atomically writes the
  release schedule and advisory database to an operator-selected cache
  directory. A systemd service and daily timer are included; failed or unsafe
  downloads leave the previous files untouched.

- **Result exports can be signed.** When `COS_WEB_EXPORT_SIGNING_KEY` is set,
  JSON, CSV, SARIF and PDF downloads carry an `X-COS-Signature` HMAC-SHA256
  header. `scripts/verify_export.py` verifies the exact downloaded bytes.

- **Supply-chain checks in GitHub Actions.** Pull requests, pushes to `main`
  and a weekly run now audit every locked core, web and MCP dependency with
  `pip-audit`, publish a CycloneDX SBOM and attest that SBOM with GitHub's
  short-lived Sigstore identity. Release artifacts and the web bundle use
  pinned attestation actions as well, and dependency-review now pins its
  action commit instead of a mutable tag. See [CI documentation](docs/ci.md).

- **A real-container integration test now exercises the scanner against an
  initialized OpenCloud image.** It is opt-in locally, runs weekly in CI,
  cleans up its disposable Docker resources, and skips clearly when Docker or
  the selected image/version is unavailable.

- **The advisory database is refreshed daily, in CI and at runtime.** Until
  now nothing wrote `opencloud_local_scan/data/vulnerabilities.json`: it
  shipped with no active advisory in it, there was no script to regenerate it
  and no workflow to run one, so every advisory published against OpenCloud
  since the file was written was invisible to every deployment - and a visitor
  scanning an affected instance was told it was fine. Two things now keep it
  current. `.github/workflows/vulnerability-db.yml` runs
  `scripts/update_vulnerability_db.py` against the OSV query API every day and
  opens a pull request when the answer has changed, and the web application's
  worker asks the same feed once a day (and at startup) and rates queued scans
  against what it last accepted, so an advisory published after an image was
  built still reaches the people scanning with it. Both use one reader,
  `opencloud_local_scan/advisory_source.py`. A refresh only ever adds an
  advisory, so a feed answering with an empty list changes nothing and a
  hand-written entry survives; an advisory with no version bounds is never
  believed, because it would match every release there has ever been; an
  answer with an absurd number of advisories is refused whole; and any failure
  leaves the database exactly as it was. Nothing is written to disk at
  runtime. `COS_WEB_ADVISORY_REFRESH=false` turns it off for a deployment with
  no outbound access, `COS_WEB_ADVISORY_REFRESH_URL` points it at a mirror,
  and `/healthz` reports how many advisories the deployment would rate against
  and when it last asked. See
  [ADR 0017](adr/0017-the-advisory-database-refreshes-itself.md).

- **The web application refreshes the OpenCloud release schedule itself, once
  a day.** The schedule that decides whether a line is still supported is
  written by CI and frozen into the image, so a service that has been up for
  six weeks rates instances against a six-week-old picture of the world: it
  calls last week's release "ahead of the schedule" and a line that expired
  since the build "still supported". The worker now re-reads the published
  lifecycle page once a day - and at startup, so a fresh deployment does not
  wait for the small hours - and keeps the result in Redis, where every queued
  scan picks it up. A refresh can only add knowledge: a page that has lost a
  release line is refused, because a missing line would turn an end-of-life
  instance into an unknown one; an unreachable, redesigned or truncated page
  leaves the previous schedule exactly as it was; and a newer bundled file
  after a redeployment wins over whatever is in Redis. Nothing is written back
  to the repository. `COS_WEB_SCHEDULE_REFRESH=false` turns it off for a
  deployment with no outbound access, `COS_WEB_SCHEDULE_REFRESH_URL` points it
  at a mirror and `COS_WEB_SCHEDULE_REFRESH_HOUR` moves the daily read;
  `/healthz` reports the schedule's date and the last successful read. The
  plugin is unchanged - a check running every few minutes must not become a
  documentation fetch. See
  [ADR 0016](adr/0016-the-release-schedule-refreshes-itself.md).

- **A setup wizard for the Docker deployment**, `docker/setup-wizard.py`. It
  asks, one question at a time, for the settings a deployment of the web
  application actually has to decide - what it is reachable at, how hard it
  may scan, what it may reach, who may erase a result, whether an agent may
  use `/mcp` - explains each one and shows an example answer, and then writes
  a commented compose file with the non-secret answers inline and a `.env`,
  created owner-readable only, holding the credentials that file refers to as
  `${NAME}`. That split is the point of it: a compose file is something an
  operator commits and pastes into a ticket, and a purge token is not. It
  generates the credentials nobody should invent by hand, warns about the
  combinations the service itself refuses to start on, offers a `private`
  preset for an estate scanning its own instances, runs on the standard
  library alone so it works on a host that has Docker and nothing else, and
  refuses to write over the compose files that ship with the project. It is
  separate from `check-opencloud-security --configure`, which configures a
  monitoring check rather than a container, and shares no code with it. It
  travels in the web application's release tarball, because whoever unpacks
  that is setting up exactly the deployment it asks about.

- **The setup wizard can provision Authentik**, rather than handing back a
  form of OAuth homework, and `--with-authentik` is how it is asked to. That
  adds Authentik and its database to the generated stack, derives the issuer,
  the JWKS URL and the audience from the answers, generates the credentials
  into `.env`, writes the provisioning blueprint beside the compose file that
  mounts it. It is a separate answer from `--sign-in`, which turns the guard
  on and asks for the issuer, the audience and the keys of whatever the estate
  already runs - the usual case, and the one that adds no containers. Neither
  flag implies the other, deliberately: provisioning a provider leaves `/mcp`
  open, so an operator can bring Authentik up, log in and mint a token before
  anything starts being refused, and `--sign-in` is what closes it. Nothing of
  Authentik reaches a deployment that did not ask for it.

- **Mail settings for Authentik**, in the wizard and in the stack that ships
  here. `docker-compose.authentik.yml` now carries `AUTHENTIK_EMAIL__*` on
  both Authentik services - the server sends the test message, the worker
  sends everything else, so configuring one and not the other works until the
  moment it matters - and `authentik-env.sh` writes the names into `.env`
  commented out. The wizard asks for them (`--smtp-host`, `--smtp-port`,
  `--smtp-username`, `--smtp-from`, `--smtp-security`, `--smtp-timeout`) and
  models STARTTLS and implicit TLS as one choice, because `USE_TLS` and
  `USE_SSL` both true is a session that negotiates neither. There is
  deliberately no `--smtp-password`: the wizard reads it from
  `AUTHENTIK_EMAIL_PASSWORD` in the environment or asks for it, and writes it
  into `.env` alone. An identity provider that cannot send a password recovery
  locks out the one account it starts with, and the way back in is a database
  edit. `docs/authentik.md` documents every variable.

- **MCP prompts**, so a client can offer the job rather than a menu of verbs.
  Six of them, each the task somebody actually asks for: `audit_instance`
  ("audit this instance and write a remediation plan"), `audit_estate`,
  `explain_scan_result`, `triage_findings`, `review_transport_security` and
  `check_release_support`. They are advertised as an MCP capability, listed
  over `prompts/list` and named in the `mcp.prompts` block of
  `/.well-known/ai.json` so an agent can see the tasks before it connects.
  New module `webapp/prompts.py` holds the wording and composes it from the
  notes and constants in `webapp/workflows.py`, so a prompt cannot quote a
  poll interval or a timeout the workflow layer does not have; the prompts
  name tools rather than endpoints, because the tools are what carry the
  limits. ADR 0014 records the decision and why a prompt decides nothing.
- **Transport security beside the grade.** The result page now shows the
  negotiated TLS version, the certificate's expiry date with the days left or
  gone, and whether the chain is complete and trusted, in the overview next to
  the score - the questions somebody scanning their own instance most often
  came for, previously answered only at the bottom of the page. Each fact
  takes its colour from the pass or fail the scanner already recorded for that
  check, so the page cannot disagree with the alert the same scan produced,
  and an instance that answered no handshake shows nothing rather than a row
  of dashes.
- **An optional sign-in in front of the MCP endpoint.** `/mcp` is open unless
  an operator says otherwise, which is what the public service wants; a
  deployment running this for its own estate can now set
  `COS_WEB_MCP_AUTH_ENABLED` and an issuer and have it become an OAuth 2.0
  resource server. A bearer token is verified offline against the provider's
  published keys - signature, issuer, audience, expiry and any required
  scopes, asymmetric algorithms only - and a request without one gets a 401
  whose `WWW-Authenticate` names the RFC 9728 metadata document at
  `/.well-known/oauth-protected-resource/mcp`, which names the provider.
  `/.well-known/ai.json` reports the same under `mcp.authentication`, so an
  agent knows before it connects. This service issues no token, stores none
  and holds no account, and a sign-in buys an agent nothing else: the client
  rate limit, the target cooldown, the SSRF guard and the queue are identical
  signed in. A deployment that asked for a sign-in it cannot enforce refuses
  to start rather than serve the endpoint open. New settings
  `COS_WEB_MCP_AUTH_ENABLED`, `COS_WEB_MCP_AUTH_ISSUER`,
  `COS_WEB_MCP_AUTH_AUDIENCE`, `COS_WEB_MCP_AUTH_JWKS_URL`,
  `COS_WEB_MCP_AUTH_RESOURCE_URL` and `COS_WEB_MCP_AUTH_SCOPES`, and a new
  module `webapp/mcp_auth.py`. ADR 0015 records the decision.
- **A complete signed-in stack**, in `docker/docker-compose.authentik.yml`:
  the web application, the worker, Redis, Authentik and Authentik's own
  PostgreSQL (`postgres:18.6-alpine`), in one file and one command. It is a
  stack of its own rather than a Compose profile, because Compose validates a
  required variable in every file it reads and a profile would break
  `docker compose up` for everybody who never wanted it. **The sign-in follows
  the endpoint**: `COS_WEB_MCP_AUTH_ENABLED` is `${COS_WEB_ENABLE_MCP:-true}`,
  so bringing this stack up means `/mcp` requires a token and turning the
  endpoint off turns the sign-in off with it, with no combination that leaves
  the endpoint open by accident. `docker/authentik-env.sh` writes the five
  secrets it needs into `docker/.env`, once and without overwriting.
  Authentik itself has no Alpine image and is published Debian-based only.
  It needs no Redis, and does not get the Docker socket the upstream compose
  file hands its worker. Nothing in the code knows the name: any provider
  publishing signed JWTs and a JWKS works.
- **The OAuth2 provider provisions itself**, from
  `authentik/blueprints/opencloud-scanner.yaml`, which Authentik's worker
  applies on the first start: the provider, its signing key, the four scopes
  and the application whose slug becomes the issuer. Every entry is
  `state: created`, so it provisions once and leaves later operator edits
  alone. The client ID and secret come from `docker/.env`, which is also where
  the web application reads the audience - so both sides agree without
  anything being copied between them.
- **New guide `docs/authentik.md`** covering the one-command stack, what the
  blueprint created and how to change it, getting a token, the reverse-proxy
  trap where a rewritten `Host` gives every token an issuer nobody accepts,
  and the backup and restore - which are the operator's to run, because
  Authentik has no built-in backup.

### Changed

- **The lifecycle page has one parser, and it ships in the wheel.** The
  scraping that lived in `scripts/update_release_schedule.py` moved to
  `opencloud_local_scan/schedule_source.py` so that CI and the web
  application's daily refresh cannot drift apart about what the documentation
  says. The script keeps everything that is about the repository: the
  checked-in `release_schedule.json`, the generated README block and the CLI.

- **The purge credential moves out of `Authorization` when the MCP endpoint
  requires a sign-in.** `erase_instance_data` reads it from
  `X-Purge-Authorization` instead, with no fallback: with authentication on,
  `Authorization` carries the agent's identity token, and reading one as the
  other would compare a credential against a credential and answer 401 for a
  reason nobody could see. Unchanged on a deployment without a sign-in, which
  is every deployment until an operator turns one on.

- **A release newer than the bundled schedule now says so, and still costs
  nothing.** The release schedule that ships inside the package is a snapshot
  of a page that keeps moving, so an instance patched the week after a release
  of this project is routinely newer than the file being used to judge it.
  That was already never held against it - no `F`, no upgrade pointing
  backwards - but it was also never mentioned, which left an operator reading
  a support window worked out from data older than their own instance with no
  way to tell. A version ahead of the newest release recorded for its line, or
  on a line newer than every line on record, now sets `scheduleStale` in the
  `lifecycle` block along with `scheduleUpdated`, `scheduleSource` and a
  `scheduleNote` that says plainly that the schedule is probably out of date,
  that this is not counted against the instance, and where the authoritative
  page is. The plugin prints it as a `Release schedule:` line, the result page
  shows it beside the release track with a link, and an MCP tool passes it on
  as `scheduleNote` so an agent does not present a stale verdict as settled.
  Regenerating the schedule, or upgrading the package, clears it. A line that
  genuinely expired stays expired: patching inside a dead line does not reopen
  it, and the note explains the data rather than overturning the verdict.

### Security

- **DNS rebinding protection now pins validated scan connections.** Web scans
  dial the addresses accepted by the SSRF resolver while preserving the
  original hostname for HTTP Host and TLS certificate validation. Redirects
  are validated and pinned before each hop as well.

- **MCP OAuth now requires secure provider transport.** When authentication is
  enabled, issuer and JWKS URLs must use HTTPS; only explicit loopback URLs
  remain available over HTTP for local development.

- **An advisory affecting several release lines no longer passes half of
  them.** `GHSA-vf5j-r2hw-2hrw` - a path traversal through public links,
  rated high - was fixed in `4.0.3` **and** in `5.0.2`, published as one
  record with two disjoint affected ranges. The OSV parser read the first
  range and stopped, so an instance on `5.0.0` or `5.0.1` was reported as
  unaffected: a false pass on a live vulnerability. An advisory now carries
  every range it affects, and a match reports the fix belonging to the line
  the scanned instance is actually on, so a `5.0.1` instance is told to
  upgrade to `5.0.2` rather than to a release that fixes nothing for it.

- **An advisory with no version bounds is refused rather than believed.** A
  range that is open at both ends matches every version there has ever been,
  and public feeds do publish that shape - the Go vulnerability database
  records the advisory above as `introduced: "0"` with no fix. Ingesting one
  would have reported every OpenCloud instance in the world as vulnerable,
  which is how a security check loses the trust that makes anybody act on it.
  Such an entry is now dropped where a feed is parsed, so the guard covers
  `--vulnerability-feed` and a mirrored file as much as the web application,
  and a stored document that slipped one through is refused when it is read
  back.

- **A sign-in on `/mcp` with no audience now refuses to start.** An `aud`
  claim that is never compared is not a weaker check than one that is: on a
  provider that serves more than this service - which is what an identity
  provider is for - every application behind it is issued tokens by the same
  issuer and signed with the same key, so an unchecked audience made any one
  of those tokens a key to this endpoint. `COS_WEB_MCP_AUTH_AUDIENCE` is
  therefore required whenever `COS_WEB_MCP_AUTH_ENABLED` is on, alongside the
  issuer, the resource URL and HTTPS, and a token carrying no `aud` at all is
  refused rather than waved through. The verifier fails closed as well as the
  startup check, so one built without an audience accepts nothing. The stack
  in `docker-compose.authentik.yml` already set the value and is unaffected;
  a deployment that left it empty has to name the client ID its agents
  authenticate as. The setup wizard asks for it as a required answer.

- **`export_scan` says whose words it is carrying.** Every other MCP tool
  passes the scanned instance's strings through a sanitiser and returns an
  `untrusted` block naming them; an export returned the rendered document
  untouched and unlabelled, so a hostile instance's prose reached a model as
  ordinary tool output, in a session that also has a destructive tool in it.
  An export cannot be flattened the way a summary field is without ceasing to
  be the file it claims to be, so it is labelled instead: the answer carries
  the same `untrusted` block, and one too large to hand back inline comes with
  `truncated: true` and the URL to fetch rather than a context window's worth
  of somebody else's text. A structured export past the bound is withheld
  whole, because half of a JSON document is not JSON.

- **The action that publishes the Docker Hub description is pinned to a
  commit.** `peter-evans/dockerhub-description` was used at a mutable `v5`
  tag while holding `DOCKERHUB_TOKEN`, so whoever could move that tag could
  have had the credential. It now names a full SHA with the version in a
  comment beside it, the way the release workflow already pins its own
  third-party action.

### Documentation

- **How to let somebody use the MCP endpoint, and how they sign in.**
  `docs/authentik.md` gains two sections and the point of the first one is a
  default worth knowing: an application with no bindings in Authentik is one
  every account in the directory can use, so the page now walks through the
  group, the binding, the user, the password recovery and the service account
  an agent gets instead of a person's credentials - and says plainly that the
  scan service reads none of it. The second replaces a single `curl` with the
  three ways a caller actually gets a token, including the one that surprises
  everybody who has used another provider first: Authentik does machine-to-
  machine by *username and app password*, not by client ID and client secret.
  It ends where it should, calling `/mcp` with the token and reading the
  claims when it is refused, and the troubleshooting table gained the failures
  that go with all of it.

## [1.8.0] - 2026-08-20

### Added

- **A remediation planner**, answering "what gets you to A+" rather than only
  "what is wrong". The rating already records which finding held it down and
  by how much, so replaying that arithmetic with one finding removed at a time
  gives an ordered fix list with the grade each step would reach - including
  the update step, because fixing findings can never lift a rating above what
  the installed version allows. It is derived from the result document and
  stored nowhere new. New module `opencloud_local_scan/remediation.py`, a
  `remediationPlan` key in every scan result, a section on the dashboard, the
  plan in the CSV, SARIF and PDF exports, a `--debug` block in the plugin, a
  `planRemediation` Arazzo workflow and a `plan_remediation` MCP tool.
- ADR 0012 records why the plan is derived from the rating rather than
  modelled beside it, and why it is stored nowhere.
- Remediation text for every finding the extra-check pass can report -
  `tlsTrusted`, `directoryListing`, `maintenanceMode`, the `exposed:`,
  `authentication:`, `debugEndpoint:`, `debugPort:` and `versionDisclosure:`
  families and the rest. Until now `describe_hardening()` explained the
  hardening flags and the headers but answered "No description is available"
  for exactly the checks that cap a rating, which left the one part of a
  report an operator has to act on as the one part that said nothing.
- A Model Context Protocol endpoint at `POST /mcp`, so an AI agent can run the
  same checks a browser can. Six tools, one per user-level task -
  `scan_instance`, `scan_instances`, `get_scan_result`, `plan_remediation`,
  `export_scan` and `erase_instance_data` - and three resources exposing the
  OpenAPI, Arazzo and discovery documents. The tools call this application's own HTTP API in
  process, so an agent meets exactly the same SSRF guard, rate limits and
  purge authorisation; `erase_instance_data` is marked destructive and takes
  its credential from the request headers, never from a tool argument. Needs
  the new optional `mcp` extra, and is off when it is not installed. See
  [ADR 0011](adr/0011-mcp-is-an-execution-layer-not-a-second-implementation.md).
- `GET /.well-known/ai.json`, a discovery document naming the OpenAPI schema,
  the Arazzo workflows, the MCP endpoint, the usage limits worth respecting
  and the link to self-hosting. It is an application-level convention rather
  than a registered standard, and it exists so that an agent starting from
  nothing but the origin needs one request to find everything else.
- `webapp/workflows.py`, the single place the workflow semantics live: the
  poll interval and attempt ceiling, the submit retry count, which statuses
  are terminal, and the prose explaining each of them. The Arazzo document is
  rendered from it and the MCP tools execute it, so the described behaviour
  and the executed behaviour are the same code.
- Discovery hints in the head of every page - `rel="service-desc"`,
  `rel="arazzo"` and `rel="ai-discovery"` - and a **For AI agents** section on
  `/api` linking the same four addresses as ordinary clickable links.
- `COS_WEB_ENABLE_MCP` (default `true`) and `COS_WEB_MCP_ALLOWED_HOSTS` for
  the `Host` values the MCP endpoint accepts.
- `GET /sitemap.xml` and `GET /robots.txt` in the web application, both
  generated rather than kept as files. The sitemap lists the landing page and
  the four explanations, and takes each `lastmod` from the template that
  renders the page, so it cannot drift from the routes that exist. Neither
  mentions a result: `robots.txt` disallows `/scan/`, `/api/`, `/mcp` and the
  health probe, while explicitly allowing the machine-readable documents.
- `COS_WEB_PUBLIC_BASE_URL` sets the origin used in the canonical links and
  the sitemap. Behind a proxy the service only sees its own internal address
  and would otherwise publish URLs nobody outside can reach.
- `COS_WEB_ALLOW_INDEXING` (default `true`) decides whether search engines may
  index the five public pages. Turning it off restores the previous behaviour
  in full: a flat `robots.txt`, a 404 for the sitemap and `noindex` everywhere.
- Every page now carries a canonical URL, platform-neutral OpenGraph metadata
  and a title that names the service. See
  [ADR 0009](adr/0009-public-pages-indexable-results-never.md).

- **Transport security is now inspected in detail**, in a new module
  `opencloud_local_scan/tls.py`. The check used to end at "the handshake
  worked, the certificate is trusted, it expires on this date"; it now also
  reports the negotiated protocol and cipher, whether the server still accepts
  a deprecated one, whether the certificate actually covers the name it was
  asked for, whether the chain it presents is complete, whether its lifetime
  stays inside the 398 days browsers accept, and whether an OCSP response is
  stapled to the handshake. Five new findings - `tlsDeprecatedProtocol`,
  `tlsHostname`, `tlsChain`, `tlsCertificateLifetime` and `tlsOcspStapling` -
  are explained in the hardening catalogue like every other one.
- A `tls` block in the result document carries the measurements behind those
  findings: the protocol and cipher, the certificate's subject, issuer,
  validity window and remaining days, its names, the chain length, and what
  the deprecated-protocol and stapling probes found. It is on the dashboard as
  a **Transport security** card, in the JSON, CSV, SARIF and PDF exports, in
  the `TlsDetail` schema in `/openapi.json` and in the MCP result view.
  **A measurement that could not be taken is absent, never a pass**: `null`
  means "not determined", so a check the platform or the server made
  impossible is left out rather than quietly counted in the instance's favour.
  See [ADR 0013](adr/0013-transport-security-is-measured-not-assumed.md).

### Changed

- `/openapi.json` and `/arazzo.json` are now always public, at stable paths
  and without authentication. `COS_WEB_ENABLE_DOCS` governs only the browsable
  `/docs` and `/redoc` pages, which is what it was really protecting: those
  relax the content policy to render, while a JSON document does not. A
  description nobody can fetch describes nothing. See
  [ADR 0010](adr/0010-machine-readable-descriptions-are-always-public.md).
- The OpenAPI document is now written rather than inferred, and describes the
  API as it actually behaves. The generated one declared a form body where
  scan creation takes JSON, `200` where it answers `202 Accepted`, and empty
  schemas where a client needed the shape of a result. Every response now has
  a named schema mirroring the implementation field for field - the uuid a
  caller needs, the scan record with its state, `done`, summary and available
  exports, the batch's accepted and rejected lists, the purge receipt and the
  health body - and every description says what an agent should do with a
  status: `409` on an export means *not yet*, `404` means *never*.
- The Arazzo workflows now describe the real lifecycle. `awaitScanResult` is a
  new shared workflow that polls until `done`, stops immediately on a 404
  because an unknown or expired uuid never becomes known, and gives up after a
  bounded number of attempts. `scanManyInstances` no longer passes batch uuids
  into a workflow expecting a `target_url`; it waits on the accepted uuids and
  does not retry a target the backend rejected. `eraseInstanceData` documents
  the authorisation, the receipt, the counts and the signature.
- The header navigation collapses behind a menu button on narrow screens. Six
  links and the brand line did not fit across a phone, so the last entries
  could only be reached by scrolling the page sideways. The collapsed layout
  is switched on by `nav.js` itself, so with scripting blocked the links stay
  on the page and wrap onto a second row.
- `scripts/check_documentation_links.py` no longer trusts a status code on
  `docs.opencloud.eu`. It is a single-page application, so an address that no
  longer exists answers `200` with the application shell and only renders
  "Page not found" once a browser gets to it - which is why three dead links
  sat in the catalogue with the checker reporting everything healthy. A
  `/docs/` address is now checked against the site's own `sitemap.xml` as
  well. The checker also imports the hardening catalogue instead of only
  reading source text, because a URL long enough to be split across two string
  literals is invisible to a regular expression, and those are the longest
  links this project documents.
- The landing page, the form, the progress track and the result dashboard now
  hold their shape below 640px: full-width buttons, a smaller dial, a stacked
  footer and no element wider than the viewport.
- The landing page and the four explanations are now indexable; a result page
  is not, and never can be. It carries `noindex` in the markup and an
  `X-Robots-Tag` on the response, as does every export and API reply.

### Fixed

- An untrusted certificate no longer hides its own expiry date. `getpeercert()`
  returns nothing at all when verification is off, so on an instance with a
  self-signed certificate - the default OpenCloud ships - the certificate
  expiry check produced no finding whatsoever, and an expired certificate went
  unreported on exactly the instances most likely to have one. The certificate
  is now decoded from the presented chain regardless of whether it verified.
- A server offering only TLS 1.0 is reported as speaking an obsolete protocol
  rather than as unreachable. Python's client refuses such a handshake outright,
  which read as "no TLS here" instead of the finding it should have been.
- Three documentation links pointed at pages that no longer exist: the update
  guide, the external identity provider reference and the reverse proxy setup.
  All three are reachable again, in the hardening catalogue and in the README.

### Security

- The MCP tools no longer hand a scanned host a channel to the model. A
  version string, a product name, an explanation and an error message are all
  chosen by somebody else's server, and they land in a language model's
  context: each is now collapsed, stripped of non-printable characters and
  truncated, a version that does not parse becomes `unparsable`, and the
  answer carries an `untrusted` block naming those fields and stating that
  they are to be reported and never obeyed. The same warning is in the server
  instructions and the tool descriptions.
- A `uuid` given to an MCP tool is validated as a UUID before it reaches a
  request path. An HTTP client resolves `..` in a path, so `../../healthz`
  previously addressed the application rather than a scan; an identifier that
  does not parse now gets the same 404 unknown and expired do, without a
  request being made. The purge target is percent-encoded for the same reason,
  so a `&` in it can no longer add a second query parameter.
- Every MCP tool call is now rate limited against the address it actually came
  from. The in-process transport reported a hardcoded `127.0.0.1`, so in the
  default configuration every agent in the world shared one bucket and one
  audit identity - rationing strangers by each other, and letting one busy
  client lock the rest out.
- `COS_WEB_MCP_MAX_CONCURRENT_WAITS` (default `8`) caps how many tool calls
  may sit waiting on a scan at once, so a handful of calls cannot pin the
  process open for the minutes a scan may take. Nothing is refused when the
  ceiling is reached: the scan is submitted as usual and the uuid comes back
  with a note to poll `get_scan_result`, exactly as `wait: false` answers.

### Documentation

- Every page now says in its footer that this check is **not exhaustive and a
  good grade is not a certificate**: it reads what a publicly reachable
  instance shows an anonymous visitor, so an "A" means nothing checked went
  wrong, not that the instance is secure. A result page repeats it next to the
  grade and links to a fuller "what this scan cannot see", which now names the
  categories an unauthenticated scan cannot reach at all - the host and its
  packages, the container runtime, the proxy's own configuration, backups,
  storage, secrets, accounts and sign-in, existing shares, the supply chain,
  and anything only a logged-in user sees. `tests/test_webapp_api.py` fails if
  a page loses the caveat.
- [`docs/reverse-proxy.md`](docs/reverse-proxy.md), a guide to reverse proxies
  in both directions: the header set this check grades, written out for nginx,
  Apache httpd, Caddy, Traefik and HAProxy, together with the mistakes that
  cost an instance a grade; and what the scan service needs from a proxy - a
  client address it can rate limit, timeouts longer than a scan, an unbuffered
  `/mcp` event stream, and the discovery paths left unrewritten. Linked from
  the README guide table, the docs index, `docs/webapp.md` and
  `docs/troubleshooting.md`.
- `ARCHITECTURE.md` gains **The agent-facing surfaces**, which was missing
  entirely: how `webapp/workflows.py` holds the semantics once and
  `/openapi.json`, `/arazzo.json` and `/mcp` are three descriptions of it, how
  `/.well-known/ai.json` leads to all three, and what the MCP endpoint may not
  do - be a second implementation, a way around a rate limit, a channel from a
  scanned host to the model, or a place a credential lives. Its module tables
  now name `tls.py`, `remediation.py` and the seven web modules added since
  they were written. `AGENTS.md` and `.github/copilot-instructions.md` gain
  the same rules in short, so an agent working on a tool has them without
  reading the code.
- `AGENTS.md` gains a **Third parties** section, and
  `.github/copilot-instructions.md` and `frontend/README.md` the same rule in
  short: nothing in this project may connect to Twitter/X, Google or Meta -
  no script, font, embed, SDK, analytics, CAPTCHA, sign-in or share button,
  and no metadata addressed to one of them. A visitor hands this service the
  address of a system they are responsible for, and a result URL's uuid is the
  whole of its authorisation; neither belongs in a third party's logs. Plain
  links and platform-neutral OpenGraph tags stay, because nothing fetches
  them, and `tests/test_webapp_seo.py` fails if a page starts carrying such
  metadata.

## [1.7.0] - 2026-08-19

### Security

- Results are now actually encrypted at rest when `COS_WEB_ENCRYPT_RESULTS` is
  on. The ARQ worker - the process that writes the result document - built its
  store without the encryption configuration, so the setting encrypted nothing
  while appearing to work, and scan results sat in Redis in the clear. The
  worker now receives the configuration, and any process that is asked to
  encrypt without a usable `COS_WEB_ENCRYPTION_KEY_<version>` refuses to start
  rather than silently storing plaintext.
- CSV exports no longer allow spreadsheet formula injection. Cells are built
  from strings the *scanned* instance chooses - its product name, a
  `WWW-Authenticate` challenge - so an instance naming itself `=cmd|...` could
  run code on the machine of whoever opened the download. Every cell is now
  prefixed when it starts with `=`, `+`, `-`, `@`, a tab or a carriage return,
  stripped of newlines so a value cannot forge a row, and capped in length.
- A malformed `COS_WEB_ENCRYPTION_KEY_<version>` no longer puts the key
  material into the exception message, and from there into a worker log or an
  issue report. The message names the key version only.
- The purge receipt omits `targetFingerprint` unless `COS_WEB_PURGE_SIGNING_KEY`
  is set. An unkeyed hash of a hostname is not a pseudonym, and a receipt filed
  for compliance should not carry one that claims to be. The fingerprint and
  the receipt signature are now computed over domain-separated inputs.
- `DELETE /api/purge` compares the presented credential as bytes, so a header
  carrying non-ASCII characters is answered with 401 rather than raising out of
  the authorisation check.

### Added

- A right-to-be-forgotten endpoint for the web application.
  `DELETE /api/purge?target=opencloud.example.com` erases every scan held for
  one instance - status, result and metadata keys, the queue entries and the
  cooldown key derived from the target - and answers with a proof of deletion:
  the counts removed, a `remaining` count taken from a **second walk over the
  store after the deletion**, the version that issued it and an HMAC signature
  when `COS_WEB_PURGE_SIGNING_KEY` is set, verifiable later with
  `webapp.purge.verify()`. Because nothing maps a target back to its scans -
  such an index would be the record of who scanned what that this service
  refuses to keep - the purge walks the keyspace instead, on a call that never
  happens on the request path. It is authorised and absent until configured:
  without `COS_WEB_PURGE_TOKEN` the endpoint answers 404, since the call
  destroys results belonging to whoever is currently reading them. An erasure
  is recorded in the audit trail when one is kept, and described by the
  `eraseInstanceData` workflow in `/arazzo.json`. See
  [ADR 0007](adr/0007-erasure-on-request.md).
- Batch scanning in the web application. `POST /api/scans/batch` accepts a
  `targets` list and answers with what started and what did not. A batch is a
  convenience, never a discount: every target runs the whole single-submission
  pipeline in order, counting against the client rate limit, passing the SSRF
  guard and claiming its own target cooldown, so ten targets spend ten scans
  from the window. `COS_WEB_MAX_BATCH_TARGETS` (default 10) caps the list and
  refuses a longer one before anything is queued. See
  [ADR 0005](adr/0005-batch-scan-submission.md).
- PDF, CSV and SARIF exports for the web application, offered as download
  buttons on the result page and served by
  `GET /api/scans/{uuid}/export/{format}` alongside `json`. All four are
  renderings of the same finished result, produced on request and gone when
  the scan expires; a scan that has not finished answers 409 rather than 404.
  The PDF is written by `webapp/reports.py` itself, so the web image gains no
  reporting dependency, and the SARIF report now names the running version and
  carries a rule with the catalogue's explanation for every result. See
  [ADR 0006](adr/0006-dependency-free-exports.md).
- An [Arazzo 1.0.1](https://spec.openapis.org/arazzo/latest.html) description
  of the HTTP API at `/arazzo.json`, beside the OpenAPI schema and behind the
  same `COS_WEB_ENABLE_DOCS` switch. Three workflows - `scanOneInstance`,
  `scanManyInstances` and `exportFinishedScan` - describe the parts a schema
  cannot: submitting and polling until `done`, walking a batch's accepted
  uuids, and waiting out a 409 before downloading a file.
- `ARCHITECTURE.md`, describing the three layers and the boundaries between
  them, how settings reach the scanner, the request pipeline, the concurrency
  and state rules, what ships in which artefact, and where a new check,
  setting or endpoint belongs.
- Optional audit logging for the web application. `COS_WEB_AUDIT_LOG=true`
  writes one JSON record per line on the `check_opencloud.web.audit` logger
  for every accepted scan request, every rejected submission and every
  triggered rate limit or target cooldown, each with a UTC timestamp.
  Requester addresses are always recorded as a truncated HMAC fingerprint and
  never in the clear; the target is a fingerprint too unless
  `COS_WEB_AUDIT_LOG_TARGETS=true`. `COS_WEB_AUDIT_SALT` pins the fingerprint
  salt so records correlate across a restart, and leaving it unset means they
  do not. Off by default, so the ordinary log still carries lifecycle markers
  and uuids only. See [ADR 0004](adr/0004-webapp-audit-logging.md).

### Changed

- The landing page is now about scanning again. The explanations that grew
  under the form - what gets tested and what happens after the button, the
  JSON API and its fair use limits, what the server keeps, and who OpenCloud
  is - moved to `/how-it-works`, `/api`, `/privacy` and `/about`. The header
  and footer navigation reach all four, every content page ends with links to
  the others but never to itself, and the pages stay out of the OpenAPI schema
  so a generated client does not grow methods for HTML.

- The web interface has a new theme, in two halves of the same day. Light is a
  sunrise over a breakfast table: warm paper, a low sun behind the shield and
  one orange the page is led by. Dark is the night before it: a deep sky, a
  moon, and a faint field of stars behind the page. Both are entirely token
  driven at the top of `app.css`, every ink-on-tint pair still clears WCAG AA,
  and the three hand-drawn SVGs now carry both schemes internally rather than
  one hardcoded blue.

## [1.6.1] - 2026-08-18

### Fixed

- The ARQ worker Compose health check now verifies its process and Redis
  connection instead of probing the web server endpoint it does not run.
- The web application's `/healthz` probe now checks Redis and returns 503
  while its required state store is unavailable.
- The web application's `/healthz` probe now also reports aggregate queue
  depth and requires a short-lived Redis worker heartbeat.

## [1.6.0] - 2026-08-18

### Added

- Webhook signature verification using HMAC-SHA256. When configured with
  `--webhook-secret` or `COS_WEB_WEBHOOK_SECRET` (for the web application),
  webhook payloads are signed with an `X-COS-Signature` header (format:
  `sha256=<hex>`). Receivers must share the same secret to verify signatures.
- Redis encryption with key rotation support (web application). When
  `COS_WEB_ENCRYPT_RESULTS=true` is set, scan results are encrypted at rest
  using AES-256-GCM. Encryption keys are configured via
  `COS_WEB_ENCRYPTION_KEY_<VERSION>` env vars (hex-encoded 256-bit keys).
  Key rotation is transparent: new encryptions use the highest version,
  old keys still decrypt existing data. Encryption defaults to off to maintain
  backward compatibility.
- Multiple report formats for web application scan results (API):
  - **CSV format**: Export findings as CSV with scan metadata headers
  - **SARIF format**: Security Results Interchange Format for integration with
    security dashboards and tools
  - Formats are selected via `output_format` query parameter in POST requests
  - Existing dashboard and JSON formats remain unchanged

### Fixed

- A time-of-check-time-of-use vulnerability in webhook URL validation
  allowed DNS rebinding attacks to bypass SSRF protection and target private
  addresses. Webhook DNS resolution is now re-validated immediately before
  delivery and blocked if the address has changed since submission.

### Documentation

- Added `adr/0002-no-scan-result-caching.md` explaining why scan results are
  not cached across requests and the data protection and security
  considerations behind that decision.

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
