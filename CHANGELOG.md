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

- **An optional operator's area at `/admin`, off unless a deployment asks for
  it.** It refreshes the release schedule and the advisory database on a
  press, follows the audit trail as it is written, and shows what the service
  is doing: the worker and its queue depth, every configured limit, when each
  piece of reference data was last updated, and whether the shipped search
  index still describes this build.

  It authenticates nobody. An authentik proxy provider stands in front of it
  and forwards the identity it established, and this service believes those
  headers only because the outpost adds a shared secret alongside them,
  compared in constant time - the same shape `/mcp` already uses. Three
  refusals hold it together: a deployment that enables the area without
  `COS_WEB_ADMIN_PROXY_SECRET` does not start, one whose
  `COS_WEB_ADMIN_USERS` names nobody does not start, and every failure to
  authorise answers **404** rather than 401, because whoever is asking
  without the secret is finding out whether the area exists. With the area
  off the routes are never registered, so the path is as absent as any other
  unknown one.

  Nothing about an operator is stored - the identity names the actor in an
  audit record and is then gone. The readings are counts and settings only:
  no address anybody scanned reaches them. The audit view starts at the end
  of the trail rather than replaying what was retained, and a client in it is
  a truncated HMAC under a salt this process holds, which nothing here can
  resolve. The page is `noindex, nofollow, noarchive` and deliberately absent
  from `robots.txt`, where a `Disallow` line would advertise it, and it is
  not linked from the documentation.

  `docker/setup-wizard.py` asks whether to serve it - answering no by
  default - and configures the authentik user who may use it.

  **The area says what it does not know.** Its readings are polled, and a
  poll that stops answering used to look exactly like a service with nothing
  happening on it: the numbers simply stopped moving. So the age of the last
  answer is on the page and counts up between polls, a reading older than a
  few of them says the service has not answered and that what is on screen
  is the last thing it said, a tile lights when its value moves, and the
  band's dot pulses while a fetch is actually in flight. The audit view now
  reads the account of the connection the server was already sending: the
  stream ending at its half-hour cap and a deployment that keeps no trail at
  all are each said in a sentence, instead of arriving as the silence a
  dropped connection produces - and a capped stream is let go rather than
  reopened, which the browser would otherwise do for ever. Where the records
  come from a ring in one process's memory rather than a file, the page says
  so, because behind more than one replica that is a part of the trail and
  not all of it. And the page stops polling while nobody is looking at it: a
  tab left open overnight was asking for the state every ten seconds until
  morning.

  **Three controls that change nothing were added, and one that reaches
  upstream.** The readings can be re-read on demand and copied as the
  service's own JSON for an issue report, the audit list on screen can be
  emptied, and *Test the sources* runs both refreshes as a dry run: the same
  fetch, the same guards, and then the answer is thrown away. It exists
  because a refresh reporting `failed` and one reporting `rejected` both
  leave the data exactly as it was, and only one of them is a network to go
  and look at. It reaches somebody else's server, so it is held back by
  `COS_WEB_ADMIN_REFRESH_COOLDOWN` like the buttons that apply what they
  fetch - under a key of its own, so it is available in the moment after a
  refresh has failed, which is the only moment anybody wants it.

  **"Redis is gone" and "the worker died" are no longer the same picture.**
  The heartbeat the worker tile reads is a key in the store, so a store that
  is unreachable took the answer with it - and the tile said *Not answering*
  either way, which is an area that sends an operator to restart a container
  that may be perfectly healthy. It is the failure they are most likely to be
  reading the page during. The tile now has a third answer, *Cannot tell*,
  the state document reports `store.reachable` beside a worker liveness that
  is `null` rather than `false` when nothing was learned, and `ADMIN.md`'s
  troubleshooting table no longer has to draw the distinction in prose that
  the page can draw itself.

  **It says what this deployment is exposing.** The state document already
  carried it - `/mcp` and whether a token is required, `/docs`, indexing,
  private-network targets, encryption at rest, and what the audit trail keeps
  and where - and the page showed none of it, so the question an operator
  opens this area with could only be answered by reading the compose file. A
  card of on/off pills now answers it, from the same two functions that
  answer `/admin/state`, so the card and the diagnostics an operator copies
  cannot disagree. They are settings rather than readings: the card is
  rendered by the server, needs no scripting, and is never repolled, because
  a value that changed did so in a process the open page is no longer talking
  to. Two combinations carry the marked accent and only two - an agent
  endpoint with no sign-in on it, and private-network targets on a deployment
  that asks to be indexed, which is a scanner strangers can find pointed at
  the network it stands in. Neither is refused: each is the right setting for
  some deployment, and the area's job is to say which one this is.

  **And a way out of it.** The band said who was signed in and offered no way
  to stop being, which for a console left open on a shared screen is the one
  control it was missing. This service has no session to end, so it cannot
  invent one: `COS_WEB_ADMIN_SIGN_OUT_URL` names the exit of the provider
  that did the signing in - `/outpost.goauthentik.io/sign_out` for the
  bundled stack, which the wizard now writes - and the link appears only
  where a deployment named one, because a *Sign out* that leaves somebody
  signed in is worse than no control at all. Only a local path or an
  `http(s)` URL is accepted and startup refuses anything else: the value is
  rendered into an `href` on a page whose content policy exists to keep
  script off it, and `javascript:` in a link is script by another name.

- **A report prints as a document.** It gets printed for a change record and
  saved to PDF for somebody who was not at the screen, and until now that
  sheet carried the aurora, a menu, a scheme switch and a row of export
  buttons nobody can press. Print now forces the tokens back to daylight -
  which is a correctness fix, not a preference: the dark scheme's ink is
  near-white, so a reader who chose dark and pressed print was handed a blank
  page - drops the chrome and the controls, keeps the grade, the facts, the
  findings, the plan and the trademark notice every standing surface carries,
  stops a finding being split across a fold, and prints the address behind
  each documentation and advisory reference, which on paper is the only way a
  link says anything. No second template and no new markup beyond a marker on
  the two cards that are entirely controls.

## [1.18.2] - 2026-09-01

### Added

- **The severity counters on a report are the filter for its findings.**
  Pressing `Critical`, `Warning` or `Info` narrows the list below to that
  severity, pressing it again gives the whole list back, and a sentence
  beside the heading says which filter is on with a way out of it. The
  counters already counted exactly those entries, so the shortest way to ask
  "show me only those" is the number itself. A counter standing at zero is
  disabled - there is nothing behind it - and the advisories and passed
  counts stay readings, because neither has a list on this page to narrow.
  Nothing is fetched and no count is ever rewritten: every entry is already
  on the page tagged with the severity the server gave it, so the filter only
  sets `hidden`. Without scripting the counters are five readings, which is
  what they were.
- **A switch between the light and dark themes, in the header.** The
  operating system still decides on a first visit and on every visit after
  it; only pressing the switch writes anything down, and it is remembered in
  that browser alone. `theme.js` applies a stored choice before the first
  paint - the one script on the site that is not deferred - so an override
  never opens with a flash of the other scheme, and the `theme-color` meta
  tags are re-pointed so the browser's own chrome does not frame a dark page
  in a light bar. Which icon the button shows is decided in CSS from the same
  two questions the colour tokens ask, so it is never briefly wrong, and the
  control is hidden until scripting marks the document rather than being
  offered to a reader who cannot use it.
- **The waiver picker can be searched.** The catalogue lists every check the
  scanner runs, which is thorough and, past a screenful, hard to read;
  somebody who came to waive one identifier can now type it instead of
  hunting for it. Matching is against the identifier and the title the server
  already wrote into each row, a group whose entries have all gone is hidden
  with them, and a box that was typed in and emptied leaves the list exactly
  as it found it - including anything already ticked, because filtering only
  ever sets `hidden`. The field is revealed by its script, so a reader
  without one gets the full list rather than a search box that does nothing.
- **An address that will not do says so before the form is submitted.** The
  sentence under the field appears on `:user-invalid` - once the visitor has
  typed and left, never while they are still typing - so the red bar stops
  being a colour that carries a meaning nothing spells out. It is CSS that
  reveals it, so a browser without scripting corrects a typo just as readily.

### Changed

- **The progress card says how long the wait has run, and how long it usually
  takes.** The estimate is the server's sentence and is there without
  scripting; the clock beside it is measured against a wall-clock instant
  rather than counted up, so a laptop that sleeps wakes with the right answer
  instead of a tally of missed ticks. It starts when the page did, which is
  the wait the reader is actually sitting through, and it is `aria-live="off"`
  inside a card that is otherwise polite - a reading that changed every second
  would be announced every second, which is the difference between telling
  somebody where they are and talking over them.

### Documentation

- **`ADMIN.md` collects the operational knowledge a system administrator
  needs and a developer document never states.** How to refresh the
  vulnerability database and the release schedule by hand and what the
  guards refuse; how a monitoring host pulls the reviewed, attested data with
  `check-opencloud-scanner refresh-data` and which configuration keys make it
  count; how to regenerate `/documentation`, the search index and the web
  bundle; how to raise a disposable local stack from the working tree with
  `docker/setup-wizard.py` to look at the frontend in a browser, why
  `--preset private` is the one that lets a scan of a local instance complete
  at all, and the bind mount that turns a CSS change into a page reload
  rather than an image rebuild; what the daily runtime refresh keeps in Redis
  and how `/healthz`
  shows whether it happened; every logger name and log marker worth grepping
  for, and what the logs deliberately never contain; what to do when
  OpenCloud moves a documented link, including why a status code alone is not
  enough for a single-page documentation site. It stays internal: it is
  absent from the wheel, the sdist, the web bundle, `webapp/documentation.py`
  and `webapp/search.py`, so nothing publishes it.

### Fixed

- **The reference-data test fixture no longer leaves its own request body
  unread.** `fetch_records` POSTs a small JSON query; the fake HTTP server in
  `tests/test_reference_data_limits.py` answered without ever reading that
  body off the socket, then closed the connection (it runs HTTP/1.0, so it
  closes after every request). Closing a socket with an unread request body
  still sitting in the kernel's receive buffer makes it send a reset instead
  of a clean close, and that reset could land on the client mid-read of the
  *response* - intermittently surfacing as a `ConnectionResetError` in
  `test_an_oversized_advisory_answer_is_refused_before_it_is_parsed` instead
  of the `AdvisoryFetchError` the test asserts on, regardless of how large the
  response body was. Only the advisory test could ever hit this: the
  schedule/lifecycle fetch this fixture also serves is a plain GET with no
  request body to leave unread. The handler now drains `Content-Length` bytes
  of the request before replying.

- **The self-hosting note under a rescan lost its breathing room when the
  rescan card merged into the report's head.** `section-gap` moved from the
  self-host paragraph onto the rescan status line above it instead of
  staying on both, so the two unrelated sentences - "ready to scan again" and
  "you can self-host this" - sat almost flush against each other (.4rem
  apart instead of the 1.25rem every other section boundary on the page
  uses). `frontend/templates/scan.html` now keeps `section-gap` on the
  self-host paragraph as well.

## [1.18.1] - 2026-08-31

### Changed

- The rescan button sits next to "scan another instance" in the report's
  head, rather than in a card of its own further down the page - the two
  actions a reader reaches for once a result is in, grouped together.
- The documentation and advisory links inside a finding's fix line now read
  as a small chip, in the same shape as the severity and category tags above
  them, instead of as a sentence of body text that happened to be blue.
  Shared by `scan.html` and `catalogue.html`, so both pages pick it up.

### Fixed

- **`tests/test_data_signing.py`'s tests against a real Sigstore bundle now
  actually run in CI.** `sigstore` is an optional extra kept out of the
  `test` dependency group on purpose, so the two tests that exercise
  `_verify_one_bundle` - a malformed bundle skipped in favour of the next,
  and a readable bundle that fails the identity pin raising
  `SignatureInvalid` - marked themselves `@needs_sigstore` and quietly
  skipped whenever it was missing. No workflow ever installed both the
  `test` group and the `signing` extra together: `run-tests.yml` synced only
  `--group test`, and `supply-chain.yml` installed `--all-extras` but never
  ran pytest. The verification logic that decides whether a fetched
  vulnerability database or release schedule really carries this project's
  own attestation had therefore never executed in automation, only ever on a
  developer's own machine with `sigstore` installed by hand.
  `run-tests.yml` now syncs and runs with `--extra signing` alongside
  `--group test`, so both tests run on every push and pull request.

- **A flaky advisory-feed test no longer races a real socket close against a
  megabyte of unread data.** `read_capped` reads at most `MAX_DOCUMENT_BYTES
  + 1` bytes and the response is closed right after; the test built a body
  roughly twice that size to prove the size guard fires before the
  `MAX_ADVISORIES` count guard even gets a chance to. Closing a socket with
  over a megabyte still incoming makes the kernel send a reset instead of a
  clean close, which occasionally raced the fake server's single write and
  surfaced as a `ConnectionResetError` where the test expected the guard's
  own `AdvisoryFetchError`. The body is now padded to just past the cap, the
  same way the sibling schedule-page test already did, leaving nothing sized
  enough to race over.

## [1.18.0] - 2026-08-31

### Added

- **`check-opencloud-scanner explain` looks a finding up without scanning
  anything.** A monitoring system prints `cspWithoutUnsafeInline` and stops
  there. Until now the three ways to find out what that meant were to run a
  scan that fails the same check, open the web application, or read
  `hardening.py` - none of which is available to the person the alert woke up.

  `explain <id>` prints the same paragraph `--debug` and the web catalogue
  print, from the same catalogue, and it reads nothing else: no configuration
  file, no network, no instance. It takes header names (`Referrer-Policy`) and
  per-path findings (`exposed:/config/opencloud.yaml`, which resolves to the
  family the catalogue actually lists) as readily as hardening flags, so
  whatever the alert said can be pasted in as it stands. With no identifier it
  prints the whole catalogue; `--category transport` narrows it, `--list`
  gives bare identifiers for a pipeline, and `--format json` gives the entry
  with its category, setting and reference. A typo exits 1 and suggests the
  nearest identifiers rather than printing a confident placeholder.

- **The scan reports whether a `security.txt` says how to report a
  vulnerability**, as `securityTxtPublished` under the new
  `setup.advisoryChecks`. Somebody who finds a flaw and cannot find an address
  for it falls back to a public issue tracker or to nothing, and a report that
  never arrives looks from the outside exactly like a flaw nobody found.

  It is reported and never counted, on the reasoning
  [ADR 0028](adr/0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md)
  applied to the modern response headers: no OpenCloud publishes one on any
  instance, so an absence describes the software rather than this deployment,
  and counting it would hand every `--check-hardening` user a WARNING about
  the shipped state of OpenCloud.
  [ADR 0034](adr/0034-an-advisory-observation-need-not-be-a-header.md)
  generalises that block to what is not a header. It reaches neither the alert
  line, the rating, the metrics, the webhook nor the exit code, and it is not
  offered as a waiver; `--debug` and the web catalogue explain it like any
  other check.

  The check reads the body rather than the status code. OpenCloud's frontend
  answers unknown paths with its own single-page shell, so a 200 at
  `/.well-known/security.txt` is the normal case and means nothing - the file
  has to carry the `Contact` field RFC 9116 makes mandatory, and must not be
  served as markup. The block is `{}` rather than a dictionary of `false`
  under `--no-extra-checks`: an observation nobody made is not one that
  failed.

- **`Cross-Origin-Embedder-Policy` joins the advisory headers.** It is the
  missing half of `Cross-Origin-Opener-Policy`, which was already reported:
  only both together give the browser grounds to isolate the origin against
  the Spectre-family side channels either one alone leaves open. Like the
  other three it is measured, explained and never counted, and
  `unsafe-none` - the browser default written out - is not credited as
  protection. The remediation says plainly that `require-corp` will stop a
  Collabora or WOPI embed loading unless that origin sends a
  `Cross-Origin-Resource-Policy` of its own, because a header that breaks the
  office integration is not one to roll out unrehearsed.

- **A `### Security` changelog entry now has to say whether anybody was ever at
  risk.** The heading records that something about this project's security
  changed; it never said whether a released version actually carried the
  defect, and reviewing the whole changelog showed how far those two come
  apart. Of nineteen security entries, seven described something a release
  shipped. The rest were defects introduced and fixed inside one development
  cycle - the `/catalogue` XSS, and all three MCP entries, whose templates and
  modules first appear in the very release said to fix them - plus hardening
  that closed no exploitable gap, and one bug that failed closed. Read as
  prose all nineteen look the same; the difference is only visible in the git
  tags.

  `security/advisories/<slug>.yml` now records one decision per entry, with the
  `git show` output it rests on in `verified:`.
  `scripts/security_advisories.py --check` fails when an entry from `1.14.0`
  onwards has no record, and runs on every pull request, so the question is
  answered by whoever fixed the defect rather than by somebody reconstructing
  it at release time. Declining is a normal answer - a record saying *never
  shipped, and here is the command that shows it* is worth as much as an
  advisory. Leaving the entry undecided is the only outcome the check refuses.

  After a release, `--sync` creates a GitHub **draft** advisory for each record
  that asked for one and commits the new identifiers back. Publishing stays
  manual and always will: it enters the GitHub Advisory Database and raises
  Dependabot alerts for every affected installation, which cannot be undone. A
  web-application record files against ecosystem `other` rather than `pip`,
  because `webapp/` never ships to PyPI and an alert there would be about code
  the installation does not have.

  Seven advisories were published from this review, covering `1.2.3` through
  `1.17.0`: the open scan-service bind, three webhook SSRF defects, the
  unpinned web-scan connection, results that were never encrypted at rest
  despite the setting, and CSV export formula injection.

- **A report page can rescan the instance, and says how long that has to
  wait.** The loop somebody actually runs is scan, fix, scan again - and the
  second half of it meant going back to the front page and retyping the
  address, with the waivers and the release track re-picked from memory or
  quietly forgotten. A result that was rated on different terms from the one
  before it is not a comparison, it is two unrelated reports.

  A finished report now carries **Scan again**, which resubmits the same
  target with the same waivers, the same release track and the same output
  format. It is an ordinary form posting to `/`, which is the point: the
  cross-site check, both rate limits, the SSRF guard and the audit trail are
  the ones every other submission already goes through, and there is no
  second write path to keep in step with them.

  Beside it is the wait. Both limits are read - the instance's cooldown and
  the visitor's own allowance - and the longer of the two is counted down in
  the page, because a countdown that expired into a refusal from the *other*
  limit would be worse than none. `RateLimiter` gains `peek_client` and
  `peek_target` for this: reading a limit must not spend it, or showing
  somebody their wait would be the request that caused it. The hostname comes
  from the record the uuid already unlocked, so nothing here can be asked
  about a target the caller does not hold a uuid for.

  The button is rendered enabled and the script disables it, rather than the
  other way round. A reader without scripting is never left holding a control
  that nothing on the page can release, and the 429 they may meet instead is
  the friendly one that points at self-hosting.
  [ADR 0032](adr/0032-a-rescan-is-an-ordinary-submission-and-reading-a-limit-never-spends-it.md)
  records the boundary.

- **The fixes a report names, in the syntax of the file that has to change.**
  Every finding already carried a sentence - *Set PROXY_ENABLE_BASIC_AUTH=false*
  - and an operator with eleven of them translated eleven sentences into one
  Compose file by hand. The translation is where the mistakes were.

  A report now renders that step: `opencloud_local_scan/snippets.py` turns the
  identifiers a scan reported into a fragment, in **Docker Compose**, **.env**,
  **nginx**, **Caddy** or **Traefik**, with the chosen one remembered in the
  browser. It renders, it does not decide - every name and value comes from
  the new `env_fix` and `header_fix` fields on the catalogue entries, so the
  fragment and the sentence above it cannot come to say different things, and
  a test asserts each header value still appears in its own Fix line.

  A fragment is complete or it says so. A check whose right value is a
  decision about the deployment - a CORS origin, a path to a CSP file - is
  named as having nothing to paste rather than given a placeholder: a fragment
  that has to be edited first is worse than the sentence it replaced, because
  it looks finished. Environment assignments and response headers are never
  mixed, either, since they are set in different files on usually different
  machines; what the chosen flavour cannot express is named, with the flavours
  that can.
  [ADR 0033](adr/0033-a-generated-configuration-fragment-is-complete-or-it-says-so.md)
  records the boundary.

### Changed

- **`--help` is grouped rather than a flat list of forty-five options.** The
  plugin's options were printed in one run, in the order they happened to be
  defined, and the flag somebody needed was always in the middle of it. They
  now sit under nine headings - which instance to check, what to probe, how
  the result is judged, version and update information, comparing against an
  earlier run, how the scan runs, what is printed, posting the result
  elsewhere, and the program itself - in the order a first run needs them.
  No flag, default, environment variable or behaviour changed.

### Documentation

- `AGENTS.md` gains **Security advisories**, and `SECURITY.md` explains how the
  advisory a reporter is promised actually gets published - including that the
  records for entries decided *against* are public too, so the reasoning can be
  read either way. `CONTRIBUTING.md` shows the two record shapes a contributor
  writes, the pull request template asks for one, and
  [`security/advisories/README.md`](security/advisories/README.md) documents
  the fields and why `package` is not cosmetic.

## [1.17.0] - 2026-08-31

### Security

- **The scan service binds loopback, and binding anything else now requires a
  token.** `check-opencloud-scanner serve` defaulted to `0.0.0.0` with no
  credential, and `GET /api/scan?url=<host>` hands the hostname a request
  names straight to the scanner - which, by design, validates nothing: the
  SSRF guard lives in `webapp/ssrf.py` and that path never reaches it. On a
  network with no token in front, that is an open request forwarder into
  whatever the monitoring host can reach - the cloud metadata endpoint, a
  container runtime socket, an internal admin panel - each answered back to
  the caller as scan evidence.

  `COS_SERVICE_LISTEN` now defaults to `127.0.0.1`, and any other address
  without `--token`/`COS_SERVICE_TOKEN` refuses to start rather than serving
  open. An operator who published the port meant to publish the service, and
  would otherwise have learned what they published from somebody else.

  **This is a breaking change** for a container that published the port
  without a token: it now needs `COS_SERVICE_LISTEN=0.0.0.0` *and*
  `COS_SERVICE_TOKEN`. The failure names both.
  `docker/docker-compose.monitoring.yml` already set both and is unchanged;
  local use needs neither. ADR 0001 made this argument for the Prometheus
  exporter and stopped there, so
  [ADR 0030](adr/0030-a-listener-binds-loopback-and-a-wide-bind-needs-a-credential.md)
  generalises it: a listener binds loopback, and a wide bind needs a
  credential.

- **`X-Forwarded-For` is read from the right rather than the left.** The
  leftmost entry is only the client behind a proxy that *overwrites* the
  header; nginx's `proxy_add_x_forwarded_for`, Traefik and most content
  delivery networks *append*, and there the leftmost entry is whatever the
  client sent. A caller could therefore mint a fresh rate-limit bucket, a
  fresh audit identity and a fresh allowance of `DELETE /api/purge` attempts
  per request, by adding one header.

  The header is now read from the end only a proxy writes,
  `COS_WEB_TRUSTED_PROXY_HOPS` entries in. An entry that is not an IP address
  is ignored rather than counted, so an obfuscated identifier cannot become
  somebody's bucket either, and an entry that *is* one is reduced to its
  canonical form before anything keys on it - `[2001:db8::1]`, `2001:db8::1`
  and `2001:0DB8:0000::1` are one host written three ways, and would otherwise
  have been three buckets, three audit identities and three allowances of
  purge attempts. `docs/reverse-proxy.md` said the opposite for Traefik - that
  the first entry is the client - and now says what happens.

- **The two daily reference-data fetches cap what they will read.** The
  release lifecycle page and the OSV advisory feed were both read into memory
  in full before anything looked at them, and both URLs are operator
  configuration that may name a mirror. The advisory feed's `MAX_ADVISORIES`
  guard could not help: reaching it already meant paying for the whole answer.
  Because both jobs run `run_at_startup`, an oversized answer was a worker
  that crashed, restarted, asked again and crashed again.

  Both now read at most one megabyte and treat more as a failed fetch, which
  every caller already degrades from by keeping the document it had. The
  ceiling lives in one place, `opencloud_local_scan/fetch.py`, so the two
  cannot drift - the same rule `ScannerSettings.max_response_bytes` has always
  applied to the instances being scanned, now applied to the documents they
  are rated against.

- **A submission from another site is refused before it is counted.** `POST /`
  and `POST /language` took a plain form body with no check on where it came
  from, so a page anywhere could queue a scan against a target of its choosing
  and have it attributed to whichever browser it borrowed - spending that
  visitor's rate-limit allowance and making their network the apparent origin
  of a scan they never asked for.

  Both now refuse a cross-site submission, using the `Sec-Fetch-Site` and
  `Origin` headers a browser attaches by itself rather than a token, since
  this service has no session to hang one on. The check runs before the rate
  limiter, so a refused submission costs the borrowed visitor nothing. A
  caller that is not a browser - curl, an agent, the in-process MCP client -
  sends neither header and is refused nothing; a page cannot make a browser
  omit them.

### Fixed

- **An advisory that names no version range is dropped instead of matching
  every release.** `is_in_range(version, None, None)` is true of every version
  there has ever been, so one such record reported *every* instance scanned
  with that database as critically vulnerable - a fleet-wide false CRITICAL
  that looks exactly like a real one, on the check whose exit code drives the
  alerting.

  `_from_osv` already refused these and said why; the other two parsers did
  not. The native format is the one an operator writes by hand and points
  `--vulnerability-feed` at, where a forgotten bound is a typo rather than
  somebody else's feed quirk, and the GitHub parser stopped at the first
  OpenCloud entry - which proves an advisory is *about* OpenCloud and nothing
  about which releases it affects, so an unparseable
  `vulnerable_version_range` with no patched version left it unbounded. All
  three now refuse alike and log which advisory was dropped.

  A single open bound is untouched: no fix yet is the normal shape of a fresh
  advisory, and no introduced version means everything up to the fix. Only
  *both* ends open is meaningless. A disabled placeholder such as the bundled
  `OC-EOL` is not judged at all - it never becomes an advisory, and it
  documents the end-of-life finding the scanner raises by itself.

  The web application keeps refusing such a *document* wholesale rather than
  quietly dropping the entry from it, which is what
  [ADR 0017](adr/0017-the-advisory-database-refreshes-itself.md) asks for: a
  feed emitting an advisory that affects every version has gone wrong, and
  yesterday's database is the better answer than the rest of today's.

- **A rating threshold outside 0-5 no longer crashes the plugin into a
  WARNING.** `-w`/`-c` are plain integers and the environment feeds the same
  values, so nothing stopped `-c 6`. The evaluation then looked the threshold
  up in `RATE_MAP` to name it in the alert line and raised `KeyError`; with no
  handler above `main()`, Python exited 1, which Nagios reads as WARNING. A
  typo in a check command became a warning state on the monitored host with a
  traceback as its status text. The thresholds are now validated before any
  scan starts, and the two alert-line lookups no longer index `RATE_MAP`
  directly.

### Added

- **Every finding on a report links to the catalogue entry that explains it,
  and the report has a contents list.** A result named identifiers -
  `basicAuthDisabled`, `exposed:/config/opencloud.yaml` - and left the reader
  to search for what they mean. The category badge already led to the
  catalogue, but only as far as the category: a reader who wanted the
  paragraph about *their* finding still had to find it among sixty entries.

  Each catalogue entry now carries its own anchor, and every finding, missing
  hardening, missing header, plan step, waived check and unfixable flag on a
  report links straight to it. Both sides are built from one function,
  `hardening.catalogue_id`, so a report cannot offer a fragment the catalogue
  does not publish - asserted in both directions by a test. The per-path and
  per-port findings resolve to the family the catalogue actually lists, so
  `exposed:/config/opencloud.yaml` lands on `exposed`; an identifier this
  build cannot explain is rendered as plain text rather than as a link
  promising an explanation that is not there. The entry a reader arrives at
  highlights itself.

  The report also gets the contents list the documentation pages have, built
  from the same `_toc.html`. Every entry is conditional on the section it
  names being rendered, so a clean instance is not offered a jump to an
  advisories card it does not have.

- **A report can be shared by email or from the clipboard, and by nothing
  else.** A finished report had no way out of the browser except the exports,
  so the address got copied out of the URL bar - and that address is the whole
  of the authorisation for the page ([ADR 0007](adr/0007-erasure-on-request.md)).
  The page now says so, and offers three ways to act on it.

  The email link is a plain `mailto:`, which the browser hands to whatever
  mail client the reader already has; nothing is posted through this service
  and no third party is asked to help. **There is deliberately no Slack,
  Teams or social share button**, and not only for the reason in `AGENTS.md`:
  those services fetch a link server-side to build a preview of it, so a share
  button would hand a company a working credential for somebody's security
  report and have it fetch the report to make a thumbnail.

  That is also why *copy summary* exists beside *copy link*. Pasting findings
  into a chat channel is a reasonable thing to want; handing everyone in that
  channel a live capability usually is not, so the summary carries the grade
  and the counts as text with no link in it - asserted by a test, because that
  is the property worth keeping. Both buttons are rendered hidden and shown
  only where a clipboard is actually reachable, so a reader on plain http gets
  the address in selectable text rather than a button that cannot work.

- `COS_WEB_TRUSTED_PROXY_HOPS` (default `1`): how many proxies of a
  deployment's own sit in front of the service, which is how far in from the
  right of `X-Forwarded-For` the client address is read. One reverse proxy is
  `1`; a content delivery network in front of an ingress is `2`. Counting too
  few names a proxy instead of the visitor and is harmless. **Counting more
  than there are is not, and nothing can make it safe**: with `2` behind a
  single proxy, `X-Forwarded-For: spoofed` arrives as `spoofed, <real>` and
  the second entry from the right is the one the client wrote. The count is
  clamped to the number of entries present, but that only prevents a read past
  the end - nothing in the header distinguishes an entry a proxy appended from
  one a client sent. Set it to the number of proxies you operate.

## [1.16.0] - 2026-08-30

### Added

- **The Docker setup wizard can hand the audit file to the host's logrotate**,
  for a trail kept in a directory on the host. It asks who rotates it -
  `service`, by size, from inside the container and needing nothing installed,
  or `logrotate`, which is where an estate's retention policy, compression and
  backups already live - and how many days to keep. Choosing logrotate writes
  a third file beside the compose file, `<project>-audit.logrotate`, with the
  install command in its header and in the wizard's next steps.

  `COS_WEB_AUDIT_LOG_ROTATION` is the setting behind it. `external` turns the
  service's own size-based rotation off and switches the handler to one that
  notices its file was moved aside and reopens the replacement, so the policy
  needs no `copytruncate` - which would truncate the file underneath a running
  writer and lose whatever fell between the copy and the truncation - and its
  `create 0600 10001 10001` line is what keeps the new file writable by the
  container and readable by nobody else. Exactly one thing may rotate the
  file, so an unrecognised value refuses to start rather than leaving a
  deployment with two rotators or none, and the wizard warns that a policy
  nobody installs rotates nothing.

- **The Docker setup wizard asks where a deployment keeps its audit trail and
  whether Redis survives a restart**, and either can go to a named Docker
  volume or to a directory on the host. Both default to `none`, which is what
  the shipped stack already does; the point is that keeping something is now
  an answer rather than a hand-edited compose file.

  The audit trail needed somewhere to go first, so `COS_WEB_AUDIT_LOG_FILE`
  is new: it writes the records to a file instead of the process output,
  owner-readable, rotated at `COS_WEB_AUDIT_LOG_MAX_BYTES` with
  `COS_WEB_AUDIT_LOG_BACKUPS` generations kept, so the trail cannot fill the
  volume it sits on. The records go there *instead of*, not as well as, the
  ordinary log - which is the one place this service keeps free of targets and
  client fingerprints. A path the process cannot write refuses to start, for
  the reason [ADR 0008](adr/0008-refuse-to-start-without-the-encryption-key.md)
  gives about encryption: reporting an audit trail that silently goes nowhere
  is worse than keeping none. `Dockerfile.web` creates
  `/var/log/opencloud-scan` owned by the unprivileged uid, so a fresh named
  volume inherits an ownership the container can write to.

  Persisting Redis is the one answer here that takes something away from what
  the service can promise - a copy of every result still inside its TTL then
  exists as a file - so the wizard warns when it is chosen, suggests
  `COS_WEB_ENCRYPT_RESULTS` alongside it, and rewrites the comment above the
  `redis` service rather than leaving a compose file claiming it writes
  nothing to disk. The `private` preset now keeps the audit trail it already
  turned on.

- **Four hardening flags read from the OpenID Connect discovery document the
  scan already fetches**, at the cost of no additional HTTP request. Finding
  out who signs users in has always meant reading
  `/.well-known/openid-configuration`; until now only `issuer` was kept and
  the rest was thrown away, which left
  [Securing a deployment](docs/secure-deployment.md) telling operators to
  require PKCE with nothing able to check whether they had.

  | Flag                         | Fails when                                                                   |
  |:-----------------------------|:-----------------------------------------------------------------------------|
  | `oidcPkceSupported`          | `code_challenge_methods_supported` does not offer `S256`                     |
  | `oidcImplicitFlowDisabled`   | `response_types_supported` returns a token from the authorization endpoint   |
  | `oidcSigningAlgorithmStrong` | `id_token_signing_alg_values_supported` contains `none` or an `HS` algorithm |
  | `oidcEndpointsUseHttps`      | a published endpoint is an `http://` address                                 |

  **Every one is skipped where the evidence is not published**, the same rule
  `passwordPolicyComplexity` follows. That matters more here than usual:
  OpenCloud's built-in provider ([libregraph/lico](https://github.com/libregraph/lico)) omits
  `code_challenge_methods_supported` entirely, so reading its absence as "no
  PKCE" would fail every stock instance for something its operator cannot
  change. For the same reason `oidcImplicitFlowDisabled` is reported for an
  **external** provider only - lico publishes `id_token token` and `id_token`
  among its response types and cannot be reconfigured, and a finding an
  operator cannot act on is worse than none. `oidcEndpointsUseHttps` is
  measured only when the instance itself answered over HTTPS, so it reports
  the disagreement worth reporting - a TLS instance whose provider still
  advertises `http://` - rather than restating `httpsEnforced`.

  [Authentication](docs/authentication.md) explains all four, and records
  what else that document publishes and why none of the rest is checked -
  including `token_endpoint_auth_methods_supported`, the obvious fifth
  candidate, which is not a finding in either direction.

  The result document's `identityProvider` block gains a `metadata` key
  carrying the fields these flags were read from, so a reader can see the
  evidence rather than only the verdict. `derive_hardenings()` takes the
  identity-provider block as a fourth, optional argument; a caller that does
  not pass one still gets every other flag.

- **`passwordPolicyComplexity`: whether the link password policy still asks
  for more than a length.** OpenCloud's default policy requires one lowercase
  letter, one uppercase letter, one digit and one special character, and each
  of those four minimums is a setting somebody can lower to zero. A
  twelve-character policy with all four at zero accepts `aaaaaaaaaaaa`, which
  satisfies `passwordPolicyEnforced` and nothing else. Deliberately a second
  flag rather than a stricter `passwordPolicyEnforced`: folding them together
  would change what an existing alert means without changing its name.
  Reported only when the instance publishes all four minimums - a policy that
  is switched off publishes none of them, and that case is
  `passwordPolicyEnforced` failing rather than this one. See
  [Authentication and account exposure](docs/authentication.md).

- **`check-opencloud-scanner diff`**: compare two archived result documents
  and say what changed - findings that appeared, findings that were resolved,
  and any movement in the rating, the version and the support horizon. Renders
  as `text`, `markdown`, `json` (the document the webhook carries) or `slack`
  (Block Kit). It reads files and never scans anything. Two different hosts
  are refused unless `--allow-different-hosts` is given, because "did the fix
  work" is a question about one instance and two hosts silently compared is a
  wrong answer nobody notices; a comparison that got worse exits 1 so a
  pipeline can gate on it, unless `--exit-zero` says otherwise. The judgement
  is the plugin's own `--baseline` arithmetic, not a second implementation of
  it.

- **`compare_scans`, an MCP tool, and `verify_remediation`, a prompt**, so the
  question an agent is asked a week after handing over a remediation plan -
  *did any of that help?* - has an answer. Two finished scans of one instance
  are compared into what was fixed, what is still open and what is new; both
  uuids must still be here, since this service stores no scan history and a
  uuid remains a capability with a TTL. The comparison is the same
  `--baseline` arithmetic the plugin uses rather than a set difference of its
  own, so an agent cannot call "improved" something the plugin would not. Also
  reachable as the `compareScans` Arazzo workflow and listed in
  `/.well-known/ai.json`. See
  [ADR 0029](adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md)
  for why neither a history table nor workflow-layer arithmetic was acceptable.

- **A GitHub Action** ([`action.yml`](action.yml)): `uses: sowoi/check-opencloud-security@v1`
  with a `target`, and the scan runs. Writes `json`, `sarif` (2.1.0, for the
  code-scanning dashboard), `junit` or `nagios` to `output-file`, and exposes
  `exit-code`, `status`, `rating`, `rating-label`, `message` and `result-file`
  as step outputs. `fail-on` chooses whether a `warning` fails the step, only
  a `critical` does, or `never` does and a later step decides; `UNKNOWN` fails
  under both of the first two, because a scan that did not run is not a pass.
  Pin the version: the release schedule and the newest known OpenCloud version
  ship *inside* the package, so which version runs is part of the verdict. See
  [Running the check from CI](docs/ci.md).

- **`opencloud_security_end_of_life`**, a Prometheus metric of its own rather
  than a negative `support_days_remaining`. A rolling or production release
  whose end of life has not been dated yet publishes no day count at all, and
  "unknown" must not read as "expiring today" in the one alert nobody may
  miss. Labelled with `host` and `release_type`.

- **Prometheus alerting rules and a Grafana dashboard as files**
  ([`contrib/prometheus/alerts.yml`](contrib/prometheus/alerts.yml),
  [`contrib/grafana/dashboard.json`](contrib/grafana/dashboard.json)) - nobody
  retypes a dashboard. Both read the metric names the **native** exporter
  publishes, not the shorter ones the textfile-collector and Pushgateway
  recipes shape with `jq`. `tests/test_contrib_assets.py` derives the names
  from the exporter itself, so a rename fails the suite rather than quietly
  emptying a panel. The dashboard carries an `Instance` selector, so one copy
  serves every host.

- **A contents list on every page the menu bar reaches** that has more than
  one section. `/how-it-works`, `/grades`, `/catalogue`, `/api`, `/ai` and
  `/about` now open with the same jump list `/documentation` already had, and
  that list is one template
  ([`frontend/templates/_toc.html`](frontend/templates/_toc.html)) rather than
  six copies. Every entry reuses the section's own heading string, so a
  heading rewritten in one of the four languages cannot leave the contents
  list behind saying the old thing. A page with a single section
  (`/privacy`) includes nothing: a contents list of one entry is a link to the
  top of the page the reader is already on.

### Changed

- **Breaking: `COS_WEB_PURGE_TOKEN` must now be at least 32 characters, and a
  deployment whose token is shorter refuses to start.** That token is the
  entire authorisation for `DELETE /api/purge`, the one route that walks the
  keyspace and deletes results belonging to whoever is currently reading them,
  so a memorable one is worse than no endpoint at all. Startup fails with a
  message naming the variable rather than serving the endpoint behind a
  guessable secret - the stance
  [ADR 0008](adr/0008-refuse-to-start-without-the-encryption-key.md) takes for
  the encryption key, for the same reason: a deployment whose operator
  believes something is protected must not come up when it is not.

  **What to do.** Nothing, unless `COS_WEB_PURGE_TOKEN` is set *and* shorter
  than 32 characters - leaving it unset is unaffected and still answers 404 to
  every erasure request, which is the default and the safe state. If it is
  set, generate a replacement and update whoever holds it:

  ```bash
  python -c 'import secrets; print(secrets.token_hex(32))'
  ```

  Tokens written by the Docker setup wizard have always been 64 hex
  characters and need no change.

- **The Docker setup wizard's yes/no questions say that `true` and `false` are
  accepted too**, and a confirmation prompt that does not understand an answer
  now says so instead of silently asking again. Both words were always
  accepted; nothing on screen admitted it.

- **The Docker tab is now the first half of `/documentation`.** Somebody
  looking for how to run the check had to guess which of two menu entries
  answered that; the one-liners - the plain `docker run`, the JSON result
  document, `--network host` for an instance this site will not scan, and the
  `uvx` form for machines without Docker - now sit directly under the quick
  start on the documentation page. `/cli` answers **301** to
  `/documentation#oneliner`, because that path is printed in released
  documentation and indexed; it is out of `sitemap.xml` and out of the search
  index, whose `/documentation` entry now covers the same text. The "every
  variation, written down" section it used to close with is not repeated: the
  guide it pointed at,
  [Scanning from the command line, in one line](docs/docker-oneliner.md), is
  already listed in the guide grid further down the same page.

### Fixed

- **`DELETE /api/purge` now counts wrong credentials, and refuses to start
  behind one short enough to guess.** It is the only destructive route here -
  it walks the keyspace and deletes results belonging to whoever is currently
  reading them - and the token is the whole of its authorisation. The
  comparison was already constant time, which stops a token leaking a
  character at a time and does nothing about simply trying: the route called
  no limiter, so attempts were free. Five failures from one address inside
  five minutes are now answered `429` without a comparison. Only failures
  count, so an operator working through a list of erasure requests never meets
  it. The minimum length now required of that token is a breaking change and
  is described under **Changed** above.

- **The client rate limit can now be made to hold across more than one web
  process.** The pepper the limit keys are derived from is generated per
  process, which is correct for the single-process stack this ships and
  silently wrong for anything scaled: each process derives a different Redis
  key for the same address, so a client quietly gets one allowance per process
  and nothing in any log says so. `COS_WEB_RATE_LIMIT_SALT`, set to the same
  value everywhere, makes them count together. Unset keeps exactly the
  previous behaviour, so a single-process deployment needs no change.

- **`COS_WEB_ENABLE_DOCS` in the three published compose files now matches the
  comment above it.** `docker-compose.yml` explained that the browsable
  `/docs` and `/redoc` pages are "off in public: enabling them relaxes the
  content policy on those two paths", and then set the value to `"true"`;
  the other two stacks enabled them with no comment at all. All three are now
  `"false"`, which is also the application's own default, and the comment says
  how to turn them on. `/openapi.json`, `/arazzo.json` and
  `/.well-known/ai.json` are public whatever this says, as they always were.

- **A scanned instance can no longer forge the GitHub Action's step outputs.**
  The action writes `status`, `rating`, `rating-label` and `message` to
  `$GITHUB_OUTPUT` as heredoc blocks, and the delimiter closing them was the
  fixed string `COS_EOF`. Half of what reaches those values is a string the
  *scanned host* chose - its product name, a `WWW-Authenticate` challenge, the
  message built around them - so the one party with an interest in guessing
  the delimiter already knew it. A host answering with a message containing a
  line reading `COS_EOF` closed the block early and had everything after it
  parsed as further assignments: arbitrary step outputs in whatever workflow
  consumes them, from a host that only had to answer an HTTP request. The
  delimiter is now `secrets.token_hex(16)` per run, as GitHub's own
  documentation specifies, and a value that manages to contain it anyway is
  dropped rather than written.

- **A webhook is no longer delivered to wherever the receiver redirects it.**
  `--webhook-url` is checked against private, loopback and link-local
  addresses, and re-resolved immediately before delivery to close the
  rebinding window - but the POST itself left `allow_redirects` at its
  default, so a receiver answering `302 Location: http://169.254.169.254/`
  had the payload delivered one hop past the guard, to an address nothing
  checked. What travelled with it was not only the result: `X-COS-Signature`
  and every `--webhook-header` went too, and `requests` drops `Authorization`
  across hosts but keeps the rest, so a receiver's own API key was handed to
  whatever it pointed at. The scanner has refused unvalidated redirects since
  the SSRF guard was written; the webhook path simply never asked. Redirects
  are now never followed, and a 3xx is reported as a delivery failure rather
  than passing `raise_for_status()` as a notification that never arrived.

- **The Redis service in all three published compose files now starts with the
  arguments it was meant to have.** `command: >` is a *folded* scalar, so a
  `#` inside the block is literal text rather than a comment - the four lines
  of prose explaining `COS_REDIS_PASSWORD` were folded into the command line
  between `--maxmemory-policy` and `--requirepass`, handing `redis-server`
  fifty words of English as arguments. Either the server refuses the directive
  and never starts - taking the whole stack with it, since the other services
  wait on its health check - or it comes up with no password at all on a store
  holding every live scan and every result still inside its TTL. The wizard's
  generated compose kept its comments outside the block and was unaffected;
  the checked-in files had diverged from it since 1.12.0. The comments now sit
  above `command:` in `docker-compose.yml`, `docker-compose.dockerhub.yml` and
  `docker-compose.authentik.yml`, and two tests split each compose file's
  commands the way Compose does and assert that no folded-in prose reached
  them.

- **Every workflow now declares the token scope it needs, and pins every
  action to a digest.** Ten of the sixteen already did both; the six that ran
  the suite, ruff, mypy, nox, ansible-lint and Bandit declared no
  `permissions:` block at all, so `GITHUB_TOKEN` arrived with whatever the
  repository default grants - frequently write across every scope - in jobs
  that install and execute the whole dependency tree on a push. They now
  declare `contents: read`. Bandit keeps its job-level
  `security-events: write` for the SARIF upload, which a job-level block
  grants without widening the others. The same seven files referenced
  `actions/checkout@v7`, `astral-sh/setup-uv@v10.0.0` and
  `github/codeql-action/upload-sarif@v4` by mutable tag rather than by digest,
  against the convention the rest of the directory follows; all three are now
  pinned to the commit their tag resolved to, with the version in a trailing
  comment. Two tests read the workflow directory rather than a list, so a
  workflow added later is covered the moment it exists.

- **The Bandit workflow's SARIF upload now names the ref and commit it is
  reporting on**, so a pull request's code scanning check can find it. Left to
  itself the upload action resolves the merge commit from the checkout, and
  GitHub may recompute `refs/pull/N/merge` between the event firing and the
  job running - the analysis then landed on a commit the pull request's check
  was not looking at, and every pull request drew "Code scanning cannot
  determine the alerts introduced by this pull request, because 1
  configuration present on `refs/heads/main` was not found" even though the
  job had succeeded and uploaded its report. Passing `ref` and `sha` from the
  event pins the analysis to the commit the check expects; on `push` and
  `schedule` they are the values the action would have derived anyway.

- **The Docker setup wizard's generated compose file now actually enables
  IPv6 when an operator confirms the container can reach one.** Answering
  yes to "Does this container have outbound IPv6 connectivity?" only ever
  turned on `COS_WEB_IPV6_ENABLED` - it left both networks the stack uses,
  `default` and `scanner_internal`, without `enable_ipv6`, which Compose does
  not set for a network just because the daemon supports it. An operator who
  had genuinely verified IPv6 still got a container that could not dial one,
  making the confirmed "yes" indistinguishable from a wrong one.
  `render_compose_file` now writes `enable_ipv6: true` on both networks
  whenever `ipv6_enabled` is set.

- **A scan now closes the connections it opened.** `_Probe` pools its
  HTTP connections in a `requests.Session` - one for the calling thread and
  one per worker - and none of them were ever closed, so every scan left its
  sockets held until the garbage collector happened to run. Over a fleet that
  is one socket per host for no reason, and where the instance has gone away
  in the meantime the response still sitting in the pool is finalised against
  a socket somebody else already closed. On Python 3.14 that surfaces as
  `ValueError: I/O operation on closed file` ignored in a destructor, blamed
  on whatever unrelated code was running when the collector fired - in this
  repository, a `PytestUnraisableExceptionWarning` pinned to an innocent test
  in `tests/test_webapp_api.py`. `_Probe.close()` closes every session the
  probe opened, including the ones worker threads made, and `scan()` calls it
  in a `finally` so an exception partway through does not leak them either.

- **A CSP directive separated from its sources by a tab or a newline is now
  read.** `_csp_directive` split the name from the source list on a literal
  `" "`, but CSP separates the two with any run of ASCII whitespace, and a
  policy indented across several lines uses a tab. Such a directive was
  invisible: `script-src\t'self' 'unsafe-inline'` left
  `cspWithoutUnsafeInline` passing, which is a green tick for a policy that
  really does let injected markup execute - the one direction this check must
  not fail in. The same blindness ran the other way for
  `frame-ancestors`, where a tab produced a false clickjacking alarm against
  an instance whose CSP did restrict framing.

- **A CAA record whose property tag is not spelled in lower case now counts.**
  RFC 8659 section 4.1 makes the tag case insensitive, so
  `Issue "letsencrypt.org"` restricts certificate issuance exactly as much as
  `issue` does. Matching the spelling literally reported such a zone as having
  no CAA record at all - a `tlsCaaRecord` finding against a domain that had
  done the right thing. Tags are folded to lower case as they are parsed, so
  `iodef` is still not mistaken for a property that authorizes an issuer.

- **The Prometheus exporter no longer counts measures the operator waived.**
  `opencloud_security_hardenings_missing_total` and
  `opencloud_security_failed_extra_checks_total` were computed straight from
  the result document, ignoring `ignored` - so the same instance reported zero
  to Icinga, whose perfdata has always dropped waived entries, and non-zero to
  Prometheus. An alert rule built on either gauge fired for exactly the
  measures its operator had switched off, which is the noise a waiver exists
  to remove. Both now follow the rule `failed_extra_checks()` already
  documents: a waiver hides an alert, not the evidence.

- **A pinned IPv6 literal is no longer looked up a second time.** The scan
  carries an IPv6 host bracketed so it can go back into a URL, while the web
  application pins the bare address it validated. `_resolved_addresses`
  compared the two without stripping the brackets, so every IPv6 literal
  target missed its pin and fell through to the DNS lookup the pin exists to
  avoid - leaving `addresses` empty, and the IPv4/IPv6 TLS parity check
  skipped, for precisely the targets that had been pinned. It now normalises
  the key the way the debug-port and TLS lookups beside it already did.

- **The webhook guard now refuses carrier-grade NAT, as the scan-target guard
  always has.** `_webhook_address_is_public` leaned on `ipaddress` to say what
  is private, and `ipaddress` does not classify `100.64.0.0/10` as anything -
  not private, not reserved, not link-local. A webhook URL resolving into that
  range was therefore delivered to, including to `100.100.100.200`, a cloud
  metadata endpoint where a single successful request is already a breach.
  `webapp/ssrf.py` has refused the range for a scan target since it was
  written; the two guards answer the same question about different callers and
  are now kept in step, with the NAT64 prefixes folded into the same table so
  there is one list to read instead of two.

  The webhook URL is operator configuration rather than a stranger's input, so
  this was defence in depth rather than an open door - but it was the one
  range where the two guards disagreed.

### Removed

- **`_base_of()` in the scanner**, which was dead code and wrong. It tried to
  recover the pre-cap rating from the cap list by taking the lowest cap that
  was not applied, which returns 4 rather than 5 for the ordinary case of a
  clean instance with one medium finding. Nothing called it - `RatingExplanation`
  has carried `base_rating` outright for several releases - so no output
  changes.

### Documentation

- **[Running the check from CI](docs/ci.md) now leads with the action**
  rather than with a hand-rolled install: the workflow to copy, how to feed
  the SARIF into GitHub's code-scanning dashboard, and the manual installation
  kept below for whoever wants it.

- **[Prometheus and Grafana](docs/prometheus.md) gains the two files to copy
  and a table of everything the exporter publishes** - every metric, its
  labels and its meaning - including which two are the only ones a failed scan
  emits, so a broken scan reads as no verdict rather than a stale one.

- **[Public link sharing](docs/sharing.md) writes down what is *not* checked
  and why.** The capabilities document says a great deal more about sharing
  than the two flags read; the new table records which of it is a hardcoded
  constant (so a check would say nothing about the deployment), which is
  configurable but explicitly unsupported to change, and which is a genuine
  judgement call deliberately not made yet - verified against OpenCloud's own
  `services/frontend/pkg/revaconfig/config.go`, so nobody re-derives it in a
  year.

- **[`contrib/README.md`](contrib/README.md)** is no longer only about
  scheduling; it now covers all four things it ships and how to install each.

## [1.15.0] - 2026-08-30

### Added

- **`corsOriginRestricted`: the scan now asks who may read the API's
  responses.** A request to `/graph/v1.0/me` carrying an `Origin` that cannot
  belong to anybody (`.invalid`, reserved by RFC 2606) reveals what the
  instance grants a foreign site. OpenCloud ships
  [`OC_CORS_ALLOW_ORIGINS='*'` with
  `OC_CORS_ALLOW_CREDENTIALS=true`](https://docs.opencloud.eu/docs/dev/server/services/graph/environment-variables),
  and a middleware given both commonly reflects the requesting origin - so any
  page a signed-in user opens can have their browser attach its OpenCloud
  session and read the reply. **Critical** when credentials are allowed with a
  reflected or `null` origin, **medium** for a reflected origin without them
  or a literal `*` (which browsers refuse to act on), and a pass for a
  specific named origin. See
  [Exposed paths and debug endpoints](docs/exposure.md).

- **`traceMethodDisabled`**: whether the server answers `TRACE` by echoing the
  request back, headers included, where a script can read the session cookie
  it could never read directly. OpenCloud does not implement `TRACE`, so a
  hit means something in front of it does. `TRACE` is a safe method by RFC
  9110 - it echoes and changes nothing - and a `200` only counts when the body
  actually looks like the request, so a single-page application's catch-all
  shell is not mistaken for an echo.

- **`cookiePrefix`**: the `__Host-` and `__Secure-` name prefixes, which are
  the only cookie protection a browser enforces on the name rather than the
  attributes - and therefore the only one that stops a sibling subdomain or
  plain HTTP on the same host from *overwriting* a session cookie, which
  `Secure` and `HttpOnly` do nothing about. Reports both a cookie that claims
  a prefix without honouring its rules (rejected outright by every browser, so
  the session silently does not work) and the ordinary case of no prefix at
  all. See [Cookie attributes](docs/cookies.md).

- **`tlsCertificateTransparency`**: counts the signed certificate timestamps
  embedded in the certificate, from the `openssl x509 -text` call that already
  reads the key and signature algorithm - no extra connection. A publicly
  trusted certificate without them is refused outright by Chrome and Safari.
  Deliberately withheld for a self-signed or privately issued certificate,
  which cannot be logged and where the question is not a fair one -
  OpenCloud's own `opencloud init` produces exactly that.

- **`tlsEarlyData`**: reads the `Max Early Data` limit the server's session
  tickets advertise, from the same `openssl s_client` handshake that answers
  the stapling question. A TLS 1.3 0-RTT flight has no replay protection by
  design; for a file service that is a move, copy or delete replayed at
  somebody else's choosing. Low severity, and reported as unknown rather than
  as accepted when the server never states a limit. See
  [TLS and certificates](docs/tls.md).

- **`setup.advisoryHeaders`**: `Permissions-Policy`,
  `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy`, measured
  and explained but **never counted**. No OpenCloud sends any of them, so
  their absence describes the software rather than the deployment; putting
  them in `setup.headers` would give every existing `--check-hardening` user a
  permanent WARNING no configuration change could clear. They are explained by
  `--debug` under a heading that says so, listed in the web catalogue, and
  kept out of the alert line, the `hardenings_missing` metric, the webhook and
  the exit code. A value that restricts nothing (`unsafe-none`,
  `cross-origin`) does not count as present. See
  [ADR 0028](adr/0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md).

- **[Running OpenCloud in a secure infrastructure](docs/secure-deployment.md)**,
  served at `/documentation/secure-deployment`: the part a scan cannot see.
  Putting Keycloak, Authentik or Authelia in front of the instance with the
  exact `OC_OIDC_*`/`PROXY_*` variables and the two settings that are usually
  got wrong; turning the audit service on (it is not in the default run set,
  and `AUDIT_LOG_LEVEL` defaults to `error`) and getting its log off the host;
  firewalling the ports Docker publishes behind UFW's back; what the people
  using the instance should be told; and where scheduled scanning with this
  plugin fits, including an explicit list of what it will not tell you.

- **Test coverage is now measured and enforced in CI.** `pytest --cov` runs in
  the unit-test workflow with a floor of 85% (the suite sits at 87%). A plugin
  whose whole value is that its verdicts are trustworthy should not have
  untested branches in `scanner.py` or `tls.py`.

### Changed

- **[The CLI option reference moved to its own page](docs/cli-reference.md)**,
  served at `/documentation/cli-reference`. The fifty-row table was 10% of
  `README.md` by weight and pushed everything after it halfway down the file;
  the README keeps the handful of options people actually type most days and
  links to the full table. The two inbound links from
  [`docs/ansible.md`](docs/ansible.md) and
  [`ansible/README.md`](ansible/README.md) now point at the new page.

- **The `tls` block of the result document** gains `certificate.sctCount` and
  `maxEarlyData`, both `null` when nothing looked - an absent measurement
  stays an unknown rather than becoming a pass, as everywhere else in that
  module.

## [1.14.2] - 2026-08-30

### Added

- **A "What OpenCloud is" background page**
  ([`docs/what-is-opencloud.md`](docs/what-is-opencloud.md), served at
  `/documentation/what-is-opencloud`): the fork history behind OpenCloud,
  ownCloud and Nextcloud, and the architecture, storage and release
  differences that follow from it. This is the background for why the
  scanner reads the `product`/`productname` field from `/status.php` and
  refuses to rate an instance that identifies as ownCloud or Nextcloud
  rather than OpenCloud, instead of guessing.

- **`--webhook-digest`**: with `--host` given several targets, send one
  combined webhook for the whole run instead of one per host that meets
  `--webhook-on`. Only combines what happens inside one process - see
  [Checking a fleet of instances](docs/many-instances.md) for how this
  relates to the config-file-per-instance and cron/systemd-loop patterns,
  where each instance is a separate process with nothing to combine across.

### Changed

- **`contrib/systemd/*.service` now carry hardening directives**
  (`ProtectSystem=strict`, `NoNewPrivileges=yes`, `PrivateTmp=yes`, a
  restricted `RestrictAddressFamilies=`, an empty `CapabilityBoundingSet=`,
  and more) instead of relying solely on `DynamicUser=`/`StateDirectory=`.
  Run `systemd-analyze security <unit>` after deploying to see the effect.
  The main scan unit also gains `StateDirectory=check-opencloud-security` so
  the `COS_BASELINE` path now demonstrated in
  `check-opencloud-security.env.example` composes with the hardening rather
  than needing a manually added `ReadWritePaths=`.

- **A table of contents on every documentation guide long enough to need
  one.** 19 pages under [`docs/`](docs/) - everything from
  [`authentication.md`](docs/authentication.md) to
  [`webhook-recipes.md`](docs/webhook-recipes.md), plus the docs index and the
  new [`what-is-opencloud.md`](docs/what-is-opencloud.md) - were missing the
  `<!-- TOC -->` jump list that `mcp.md`, `authentik.md`, `reverse-proxy.md`
  and `redis.md` already had. Pages with only a title and no sub-sections
  ([`icinga-director.md`](docs/icinga-director.md),
  [`troubleshooting.md`](docs/troubleshooting.md)) and
  [`webapp.md`](docs/webapp.md) (already has its own "Contents" list) were
  left alone.

- **The three-layer diagram in [`ARCHITECTURE.md`](ARCHITECTURE.md)** is now
  a Mermaid flowchart instead of an ASCII box diagram, so it renders as an
  actual diagram on GitHub rather than relying on a monospace font to line
  the boxes up. Same content: `opencloud_local_scan/` measures, its result
  document feeds both `check_opencloud_security.py` (judges) and `webapp/` +
  `frontend/` (serves), and grades come from the plugin's `RATE_MAP`, never
  decided in `serve`.

- **That diagram now renders to a checked-in PNG**
  ([`img/architecture-three-layers.png`](img/architecture-three-layers.png)),
  because GitHub is the only place that renders Mermaid - `git show`, an
  editor preview and a plain read of the file all show source otherwise.
  [`scripts/render_architecture_diagrams.py`](scripts/render_architecture_diagrams.py)
  finds every `` ```mermaid `` fence in `ARCHITECTURE.md` and makes sure a
  Markdown image line for its rendered PNG follows it (`--check` for CI); the
  new [`render-architecture-diagram.yml`](.github/workflows/render-architecture-diagram.yml)
  workflow runs it and `mmdc` (`@mermaid-js/mermaid-cli`, under Node 24 - not
  the Node 20 GitHub Actions runners are deprecating) on every push to `main`
  that touches `ARCHITECTURE.md`, and opens a pull request when the rendered
  PNG no longer matches the Mermaid source.

### Security

- **The webhook HMAC signature could never be verified by any receiver.**
  `--webhook-secret` signed a canonical serialisation of the payload
  (`sort_keys=True`, compact separators) but then handed the *object* to
  `requests.post(json=...)`, which re-serialised it with its own separators
  and insertion order. The bytes that went out were therefore never the bytes
  that were signed, so a receiver hashing the body it received - the only
  thing it can hash - always computed a different digest and correctly
  rejected every notification. The body is now serialised exactly once and
  posted verbatim as `data=`, so the signed bytes and the sent bytes are the
  same bytes. Anyone who had given up on `X-COS-Signature` and stopped
  checking it should turn verification back on.

  `tests/test_webhook.py` asserted the header against a re-serialisation of
  `kwargs["json"]` - the parsed document, never the transmitted body - so it
  passed throughout and would have kept passing with the feature entirely
  broken. It now verifies over the bytes actually sent, and a second test
  asserts a signature does *not* verify against a modified body.

- **`refresh-data` now verifies where its data came from.** The refresh a
  monitoring host runs used to query OSV and the OpenCloud lifecycle page
  live and believe the answer on the strength of TLS and a few structural
  guards - the residual risk [ADR 0016](adr/0016-the-release-schedule-refreshes-itself.md)
  and [ADR 0017](adr/0017-the-advisory-database-refreshes-itself.md) both
  name outright, since a compromised or spoofed upstream page could inject
  false advisory data and nothing would notice. It now reads both documents
  from this project's own repository - the reviewed files a maintainer
  merged - and verifies a Sigstore attestation over the exact bytes,
  pinned to this repository's own signing workflow, before writing
  anything. There is no signing key to leak: the new
  `attest-security-data.yml` workflow signs with a short-lived certificate
  bound to its own identity, the same way `publish-pypi.yml` already
  attests the wheel. A signature that is present and wrong stops the
  refresh and leaves the previous files untouched; one that merely cannot
  be checked warns and falls back to the previous behaviour. Verification
  needs the new `signing` extra (`pip install
  check-opencloud-security[signing]`) - without it the refresh works as
  before, and says so. See
  [ADR 0027](adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

- **The webhook notifier's SSRF guard only checked IPv4 addresses.**
  `_resolve_webhook_address` resolved a webhook hostname with
  `socket.gethostbyname`, which only returns `A` records, while the actual
  delivery in `requests.post` resolves dual-stack. A hostname with a public
  `A` record and a private, loopback or link-local `AAAA` record therefore
  passed validation and could still be connected to over IPv6, and the
  DNS-rebinding recheck immediately before delivery had the same blind spot.
  Resolution now uses `socket.getaddrinfo` and validates every address a
  hostname answers with, IPv4 and IPv6 alike, and also unwraps IPv4-mapped,
  6to4 and NAT64-encoded IPv6 literals so a private IPv4 address cannot hide
  inside an IPv6 one either.

### Fixed

- **The "back to top" link never appeared on mobile browsers.**
  `back-to-top.js` read `window.innerHeight` live inside its scroll handler
  as the reveal threshold, but scrolling on a phone collapses the browser's
  own address bar mid-gesture, growing `innerHeight` at the same time as
  `scrollY`. That moving target could keep the link hidden well past the
  intended one screen of scrolling. The threshold is now measured once (and
  only re-measured on a genuine `resize`, such as an orientation change)
  instead of being read live on every scroll.

- **`publish-dockerhub.yml` pinned its actions to floating version tags**
  (`actions/checkout`, `astral-sh/setup-uv`, `docker/setup-qemu-action`,
  `docker/setup-buildx-action`, `docker/login-action`,
  `docker/build-push-action`) while every other workflow that handles
  secrets already pins to a commit SHA. This is the workflow that
  authenticates to Docker Hub, so it is now pinned the same way as the rest.

### Documentation

- **Verifying the webhook signature** now has a section in
  [`webhook-recipes.md`](docs/webhook-recipes.md): what `X-COS-Signature`
  contains, a receiver that verifies it, and why it has to hash the raw
  request body rather than a re-encoding of the parsed document. Notes that
  `hmac.compare_digest` belongs there instead of `==`, where to get the raw
  body in Flask and FastAPI, that the signature also covers the `slack` and
  `discord` bodies, and that a missing header on a receiver expecting one is
  a rejection rather than a pass.

- **`--webhook-secret` and `--ca-file` were missing from the CLI option
  table** in [`README.md`](README.md) despite both being implemented, and
  neither appeared in
  [`config/check-opencloud-security.example.yml`](config/check-opencloud-security.example.yml).
  Both now have a row and a commented example (`webhook.secret`,
  `scanner.tls_ca_file`).

- **Three hardening flags the guides never named.** Naming a check by its
  identifier is the convention every in-depth page follows, but
  `httpsEnforced`, `reverseProxyDetected` and `identityProviderDetected`
  appeared in no page under [`docs/`](docs/) at all, so an operator reading a
  result had nowhere to look them up.
  [`reverse-proxy.md`](docs/reverse-proxy.md) gains a section covering the
  first two - what each has to see to pass, why a closed port 80 counts as
  enforcing HTTPS, and why a well-run Traefik or HAProxy deployment can fail
  proxy detection with nothing wrong - and [`tls.md`](docs/tls.md) points at
  it, since `httpsEnforced` sits beside `httpsAvailable` conceptually but is
  decided at the proxy rather than in the TLS layer.
  [`authentication.md`](docs/authentication.md) gains
  `identityProviderDetected` as a sixth check: how the issuer is read from
  `/.well-known/openid-configuration` (including the redirect case), that
  nothing is ever submitted to find it, and that a failure is far more often
  a proxy not forwarding the well-known path than an instance with no
  sign-in.

- **Cross-links to [`what-is-opencloud.md`](docs/what-is-opencloud.md).** The
  new page was reachable only from the docs index and
  [`troubleshooting.md`](docs/troubleshooting.md), leaving it the one guide
  with no inbound link from [`README.md`](README.md). The sentence in the
  README explaining that an ownCloud or Nextcloud product name is refused
  rather than rated now links to it, as does the matching passage in
  [`opencloud_local_scan/README.md`](opencloud_local_scan/README.md), and
  [`status-php.md`](docs/status-php.md) links back to the page that tells the
  fork lineage in full.

## [1.14.1] - 2026-08-29

### Changed

- **Check catalogue order**: The catalogue page now lists OpenCloud's own
  hardening categories first, security headers (including CSP) after, and
  transport/TLS last.

### Removed

- **`installed`, `maintenanceMode` and `databaseUpgrade` checks**: Dropped
  the findings derived from `/status.php`'s `installed`, `maintenance` and
  `needsDbUpgrade` fields. OpenCloud's handler for that endpoint returns
  those three fields as hardcoded `true`/`false`/`false` literals rather than
  reading any live state, so none of the checks could ever fire - see [Why
  OpenCloud still answers `/status.php`](docs/status-php.md).

### Fixed

- **`actions/upload-artifact` in `supply-chain.yml`** was still pinned to
  v4.6.2, the last release built on GitHub's now-deprecated Node 20 runtime.
  Bumped to v7.0.1 (Node 24), pinned to its commit the same way every other
  action in the workflows already is. Every other pinned action was already
  on a Node 24 release.

## [1.14.0] - 2026-08-29

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
- **`--format json`/`sarif`/`junit`**: one combined machine-readable document
  for every scanned host, for CI pipelines - a JSON array of the existing
  webhook payload shape, SARIF 2.1.0 for a code-scanning dashboard, or JUnit
  XML with one testsuite per host. The exit code keeps its Nagios meaning
  under every format.
- **IPv6 connectivity in the Docker setup wizard**: `docker/setup-wizard.py`
  now asks whether the deployment's containers have outbound IPv6
  connectivity (`COS_WEB_IPV6_ENABLED`, off by default, since Docker's
  default network has none). Left off, the built-in scanner still lists an
  instance's IPv6 addresses but skips dialling them for the IPv4/IPv6
  TLS-parity check, and the dashboard notes why instead of reporting the
  instance's IPv6 side as unreachable for a limitation of the deployment
  rather than of the instance.
- **The MCP endpoint is now a knowledge base as well as an execution layer**:
  two new resources, `catalogue` and `advisories`, publish the same
  hardening/check explanations and advisory database the `/catalogue` page
  renders - built from the same functions, so a resource can never disagree
  with the page about what a check id means. An agent can now explain a
  finding, or see what the scanner would catch, without submitting a scan.
- **`GET /agents.txt`**: a capability declaration in the
  [agents-txt.com](https://agents-txt.com) format, published under the
  filename some agent frameworks look for by convention. It names the MCP
  and WebMCP endpoints, declares `Authorization`/`Identity` only when the
  MCP endpoint itself requires a bearer token, and points at the discovery
  document and the OpenAPI/Arazzo contracts.
- **`GET /agents.json`**: the structured sibling the agents-txt.com
  convention recommends alongside `agents.txt` - the same document
  `/.well-known/ai.json` already serves, published again under the name the
  convention looks for.
- **`SearchAction` structured data on the homepage**: names the existing
  `/search` form so Google can offer a sitelinks search box, and
  **`BreadcrumbList` structured data on every `/documentation/{slug}` page**:
  draws the real home / documentation / guide trail those pages already sit
  in.
- **A short FAQ on `/how-it-works`**, in all four languages, with matching
  `FAQPage` structured data generated from the same catalogue keys the
  visible answers render from, so the two can never disagree.
- **`max-image-preview:large, max-snippet:-1`** added to the `robots` meta
  tag on every indexable page, opting back into the full-size thumbnail and
  snippet length Google has capped by default since 2019.

### Security

- **Stored XSS on the public `/catalogue` page via a feed-supplied advisory
  URL.** `catalogue.html` rendered `advisory.url` as an `href` with only a
  truthiness check, while the sibling `scan.html` template already guarded
  the same field with the `is safe_link` scheme check added when the daily
  OSV advisory refresh was wired in. A `javascript:` URL from a malicious or
  malformed upstream advisory entry could therefore execute in the page's
  own origin for any unauthenticated visitor who clicked the advisory link.
  `catalogue.html` now applies the same `is safe_link` guard.

### Fixed

- **`cspWithoutUnsafeInline` now also catches `unsafe-eval`**, and no longer
  mistakes a `style-src 'unsafe-inline'` for a script-execution weakness. The
  check used to fall back to a substring search over the *entire*
  `Content-Security-Policy` header when no `script-src` directive was
  present, so a policy with only `style-src 'unsafe-inline'` was wrongly
  flagged; it now reads `default-src` specifically, per CSP's own fallback
  rule, and also flags `'unsafe-eval'` in `script-src`/`default-src`, which
  undermines a CSP's XSS protection just as much as `'unsafe-inline'` does.
- **The `X-Frame-Options` check now accepts a CSP `frame-ancestors`
  directive as the alternative it already claimed to be**: the hardening
  catalogue's remediation text has always said "Send 'X-Frame-Options:
  SAMEORIGIN', or a CSP 'frame-ancestors' directive", but the scanner only
  ever checked the header, so an instance protected purely through
  `frame-ancestors` (the modern, browser-preferred mechanism) was reported
  as vulnerable to clickjacking. A wildcard `frame-ancestors *` still fails
  the check, since it does not restrict framing at all.
- **`cspWithoutUnsafeInline` no longer flags the standard `strict-dynamic`
  rollout pattern.** A `script-src` that pairs `'unsafe-inline'` with a nonce
  or a hash (e.g. `script-src 'nonce-xyz' 'strict-dynamic' 'unsafe-inline'
  https:;`) was reported as unsafe, but every browser that understands
  nonces ignores `'unsafe-inline'` in that case per the CSP spec - the
  keyword is only a fallback for browsers too old to understand the nonce.
  `'unsafe-eval'` gets no such exemption, since nothing about a nonce or hash
  makes `eval()` safe again.

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
