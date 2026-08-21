## check-opencloud-security unreleased

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

## check-opencloud-security 1.8.0

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
