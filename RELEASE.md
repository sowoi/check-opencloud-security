## check-opencloud-security 1.6.1

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
  `eraseInstanceData` workflow in `/arazzo.json`.
- Batch scanning in the web application. `POST /api/scans/batch` accepts a
  `targets` list and answers with what started and what did not. A batch is a
  convenience, never a discount: every target runs the whole single-submission
  pipeline in order, counting against the client rate limit, passing the SSRF
  guard and claiming its own target cooldown, so ten targets spend ten scans
  from the window. `COS_WEB_MAX_BATCH_TARGETS` (default 10) caps the list and
  refuses a longer one before anything is queued.
- PDF, CSV and SARIF exports for the web application, offered as download
  buttons on the result page and served by
  `GET /api/scans/{uuid}/export/{format}` alongside `json`. All four are
  renderings of the same finished result, produced on request and gone when
  the scan expires; a scan that has not finished answers 409 rather than 404.
  The PDF is written by `webapp/reports.py` itself, so the web image gains no
  reporting dependency, and the SARIF report now names the running version and
  carries a rule with the catalogue's explanation for every result.
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
  and uuids only.

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

### Fixed

- The ARQ worker Compose health check now verifies its process and Redis
  connection instead of probing the web server endpoint it does not run.
- The web application's `/healthz` probe now checks Redis and returns 503
  while its required state store is unavailable.
- The web application's `/healthz` probe now also reports aggregate queue
  depth and requires a short-lived Redis worker heartbeat.
