## check-opencloud-security (unreleased)

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

## check-opencloud-security 1.7.0

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
