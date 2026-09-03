## check-opencloud-security 1.19.0

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

  The search-index card answers with three verdicts rather than two, and its
  sentence can account for all of them. An index that does not say which
  release it was built for reads *Cannot tell* rather than *Current*: its
  pages and its languages were compared, its copy could not be, and only the
  stamp says what the copy was extracted from. A page the index holds that
  this build no longer serves is named under the verdict instead of leaving
  "out of date" standing over "every page and language is indexed" - two
  lines written in two places, one of which was being read with no way to
  tell which.

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

  **The reference data ages the way the poll does.** The two tiles printed
  the stamp they had - `checked 2026-09-02 04:17`, flat grey - so a daily
  refresh that had been failing for a week looked exactly like one that ran
  this morning, and the reader had to notice the date and subtract. They now
  say how long ago, keep the exact moment on a `<time>` where whoever wants
  it can get at it, and turn the accent past two daily cycles: one missed run
  is a source having a bad morning, two is a pattern, and by then the
  schedule and the advisory database are deciding what visitors are told from
  a picture of the world nobody has checked since the day before yesterday.

  And the note says *which* failure has been stopping it. Both refreshes
  leave their data exactly as it was whenever they do not succeed, so the
  checked stamp cannot distinguish a source nobody can reach from a document
  these guards are right to refuse - the difference `ADMIN.md` calls the
  interesting one, and the only way to see it was to press *Test the
  sources*, which fetches from somebody else's server to answer a question
  the last refresh already knew the answer to. Every attempt now records what
  it made of the source, beside the stamp rather than instead of it, and the
  tile reads *the last attempt could not be fetched* or *was refused by the
  guards*. A refresh that was never run records nothing, and a deployment
  that turned the refresh off is not reported as overdue.

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

- **A new check, `forwardedHostIgnored`: whether the instance lets the caller
  decide what its own address is.** Every other check reads what an instance
  volunteers. This one asks a question it cannot answer by accident - it
  requests `/.well-known/openid-configuration` twice claiming to have arrived
  at a host that does not exist, once as the request's own `Host` and once as
  `X-Forwarded-Host` - and looks for that host coming back. An instance that
  was never told its public address derives one from each request, and the
  discovery document is where that costs something: the `issuer` and the
  endpoints are where a client sends the next sign-in, so whoever picks the
  host has picked where an authentication request goes. It is `medium`
  because on its own it misleads only whoever sent the header; behind a cache
  it becomes the answer everybody gets, and behind a proxy that forwards a
  client's own `X-Forwarded-Host` it is a stranger who chooses. The fix is
  `OC_URL` plus a forwarded header set from the proxy's own configuration
  rather than passed through, and `docs/reverse-proxy.md` now says so beside
  the `X-Forwarded-For` advice it already gave.

  **Only a URL a client would be *sent* to counts**, which is the whole
  design: the redirect target, or one of five named fields of the document,
  compared as the host of a parsed URL. A default virtual host refusing a
  name it does not recognise usually prints that name in its error page, and
  a check that searched the body would report correct behaviour as the
  finding. An instance publishing no discovery document is not judged either
  way - two errors are the scan learning nothing, not a pass - and the two
  probes share the batch that already ran the CORS and TRACE questions, so
  the scan gains two requests and no round of waiting.

- **A test that fails when a setting is only added in some of the places a
  setting lives.** Adding one tunable touches the settings dataclass,
  `factory.py`, the example configuration file and the flag that overrides
  it, and missing one of those fails silently in both directions: a field
  nothing builds keeps its default for ever and reads as a setting that does
  not work, and a key the example file documents that nothing reads is advice
  an operator follows and then wonders about. Neither shows up in a test of
  the scanner, which is perfectly happy either way.
  `tests/test_settings_completeness.py` derives all three lists instead of
  keeping one - the dataclass fields, the configuration names the code parses
  out to read, and every key the example file documents including the
  commented-out ones - and checks them against each other in both directions. The five
  fields that are genuinely not settings are named with the reason each one
  is set in this process rather than by anybody's configuration, and a second
  test makes that list shrink again when a field stops belonging on it.

### Documentation

- **`README.md` describes the GitHub Action.** `action.yml` has existed since
  1.16.0 and the README never mentioned it: the only `uses:` line in the
  project was in [`docs/ci.md`](docs/ci.md), which is one link away from the
  file people open first and, more to the point, is not the page GitHub
  renders for a Marketplace listing - that is `README.md` on the default
  branch. The new section is the whole step in one workflow, both tables
  (thirteen inputs, six outputs), why the tag has to be pinned - the release
  schedule and the newest known OpenCloud version ship inside the package, so
  which version runs is part of the verdict - and what `fail-on` decides.
  `docs/ci.md` keeps everything that is longer than a paragraph: SARIF into
  the code-scanning dashboard, reporting without failing the job, GitLab CI.

- **`README.md` is half its length, and the material it lost is now findable.**
  It had reached 2,348 lines, which meant the file people open first answered
  every question at the same volume: how to install the plugin, what each
  hardening identifier means, which OpenCloud service listens on port 9134 and
  how to write an Icinga2 `CheckCommand` all stood in one column with nothing
  to skip. Eight sections that had become reference works of their own now
  have pages of their own - [Installing the plugin](docs/installation.md),
  [What the scanner reads, and what it deliberately does
  not](docs/scanner-checks.md), [Release tracks, end of life and the update
  recommendation](docs/release-lifecycle.md), [Hardening measures, one by
  one](docs/hardening.md), [Secrets in the configuration](docs/configuration.md),
  [Reporting only what changed](docs/baseline.md), [Running the scanner as a
  service](docs/scan-service.md) and [Worked examples](docs/examples.md) - and
  the example webhook payload and the Uptime Kuma walk-through joined [the
  webhook recipes](docs/webhook-recipes.md), where every other receiver
  already was.

  What stayed behind is a summary and a link rather than a stub: the README
  still says what the scanner reads, what a waiver does, how a track is
  declared and what the service refuses to do without a token - it just stops
  before the tables. Nothing was deleted, every paragraph is either still in
  `README.md` or on one of those pages, and the anchors other documents
  reached them by were followed to their new homes rather than left dangling.
  The eight pages are in the `docs/README.md` index and in
  `webapp/documentation.py`, so each is a page under `/documentation` and a
  row in the search index - which is where somebody looking for "shell
  completion" or "demo users" actually starts.

### Removed

- **Two encryption helpers nothing called.** `encrypt_result_dict` and
  `decrypt_result_dict` read like the path a scan record takes to Redis, and
  no caller has ever existed: `webapp/store.py` uses `encrypt_value` and
  `decrypt_value` directly. Thirty lines of untested code around key material
  that a reader had every reason to believe was load-bearing, and which any
  future change would have had to keep working for nobody. Deleting them is
  the whole change - the encryption an operator turns on is exactly what it
  was, and `tests/test_webapp_encryption.py` still describes it.

### Fixed

- **A server still offering TLS 1.0 is now caught by a scan of one, not by an
  inspection written out by hand.** How the rating treats a populated
  `deprecated_accepted` was covered; whether the probe can populate it was
  not. `_accepts` - the function that decides whether the server said yes -
  had never once returned `True` in this suite, so a bug in it would have
  cleared every server on the internet with every test still passing. The
  check now stands up a loopback server pinned to those versions and reads the
  finding back off a real handshake. Because Python's default client starts at
  TLS 1.2 and will not speak to such a server at all, this is also the first
  test to exercise the fallback handshake that reaches one; and because a
  server offering a single version answers every other question with a
  refusal, one case offers both, which is the only way the probe is ever told
  yes. A build of OpenSSL that will not serve them skips rather than fails.

- **The two Redis backends are held to the same contract.** The suite runs
  against `memory://`, the in-process stand-in, because a test that needs a
  server is a test a contributor cannot run - which left the `redis.asyncio`
  client every deployment actually uses executing nowhere, and nothing at all
  checking that the two agree. That is a test double free to drift away from
  the thing it stands in for: `SET NX` reporting whether it stored, `TTL`
  answering -2 for a key that is gone and -1 for one that never expires,
  `LPOS` counting from zero, `LREM` returning how many it removed, `INCR`
  leaving an existing expiry alone. Any of those diverging passes the whole
  suite and then loses a scan, or serves one that should have expired, on a
  real server. `tests/test_redis_contract.py` asks both backends the same
  questions, and CI now starts a Redis service for the half that needs one;
  without `TEST_REDIS_URL` that half skips, so nothing new is needed to run
  the suite locally. Every call runs on one event loop rather than a fresh one
  per call: a `redis.asyncio` pool binds its sockets to the loop that opened
  them, so a per-call `asyncio.run` - which the in-process backend never
  notices - leaves the real client's second command reaching for a connection
  attached to a loop that is already closed, exactly as a deployment would
  never do. The queue is covered the same way - `memory://` must keep
  selecting the queue that runs nothing, a real URL must produce an ARQ queue
  a job actually reaches, and the URL a deployment configures must survive the
  translation into ARQ's own connection settings. That job is read back with
  ARQ's own reader, because ARQ's queue is a sorted set of job ids rather than
  the list the store's own queue is, and it goes onto a queue name this run
  invented so that a worker watching a shared server cannot take it.

- **Coverage was blind to both entry points, and had been all along.** The
  plugin and the scanner CLI are tested the way a monitoring system runs
  them - as a subprocess with a deliberately scrubbed environment - and
  nothing that happened inside one was ever measured. The plugin reported 78%
  however thorough the suite got; it is really at
  92%, and the entire SARIF, JUnit, Prometheus and multi-host surface was
  being counted as untested while `test_output_formats.py` exercised every
  line of it.

  That is worse than an inaccurate number. For the largest file in the
  project, a branch nobody had tested and a branch covered only by a
  subprocess looked exactly alike, so the floor could not tell them apart -
  which is the one distinction it exists to draw. It was met by the library
  while the plugin contributed noise.

  `coverage` already starts itself in any process where
  `COVERAGE_PROCESS_START` is set, so the fix is to let that variable and an
  absolute `COVERAGE_FILE` survive the scrub, and to run in parallel mode so
  each process writes its own data file. `tests/conftest.coverage_environment`
  hands them over and returns nothing at all unless this process is genuinely
  measuring, so a plain `pytest` run still spawns the same clean environment
  and leaves no data files behind. Two settings had to stop being paths
  relative to a working directory the subprocess does not share: the plugin is
  named as a module rather than a file, and `wizard.py` is omitted by a
  wildcard, or it reappears at 29% once the subprocess runs are combined in.
  The floor moves 85 → 87 against a real 89%.

- **A test compared a countdown against itself and failed once a run crossed a
  second.** `expiresIn` is the scan key's remaining TTL, read at the moment
  each request is served, so the three answers
  `test_a_result_page_negotiates_the_same_scan_record_as_the_api` collects -
  the API record, the page negotiated with `Accept`, and the same page asked
  with `output_format=json` - are entitled to differ by a second, and on one
  Python 3.13 nox run they did: `3600` against `3599`. The test now compares
  the record without that field and asserts the countdown separately, as a
  retention window present in all three answers rather than an integer that
  must match. Nothing about the service changed: a live TTL is what the field
  is for, and the ten fields that actually make up the record are still
  compared whole.

### Security

- **The CAA lookup accepts an answer only from the resolver it asked.** The
  query went out from an unconnected UDP socket and the reply was read with
  `recvfrom`, so the kernel handed over a datagram from *any* address: a
  forged answer had only to reach the ephemeral port before the resolver's and
  carry the matching request id, rather than also come from the resolver.
  Anybody able to send UDP to the scanning host could therefore decide the
  `tlsCaaRecord` finding - assert a restriction on an instance that has none,
  or hide one that exists. The socket is now connected before the query is
  sent, which is what every resolver library does and what makes the request
  id a second check rather than the only one. The reach was one informational
  finding: nothing else reads the answer, and neither the rating nor any other
  check moves with it.

- **A token naming a signing key nobody published can no longer order a key
  fetch per request.** Only deployments with `COS_WEB_MCP_AUTH_ENABLED` were
  affected. A bearer token is checked against the provider's published keys,
  looked up by the `kid` in its header, and the client refetches the key set
  whenever that name is not in the set - which is how a rotated key works
  without a restart. Nothing bounded how often an unknown name could provoke
  that. A `kid` needs no signature that verifies, no audience and no issuer,
  and is read before any of them are checked, so an unauthenticated caller
  could turn each of its requests into one outbound request to the operator's
  identity provider, each blocking the event loop while it ran. A miss may now
  provoke a fetch at most once a minute, and verification runs off the event
  loop. No token was ever accepted that should not have been: the key name only
  selects which published key the signature is checked against.

- **The operator area's sign-out address is held to the same shape as every
  other local path.** `COS_WEB_ADMIN_SIGN_OUT_URL` is rendered into an `href`
  and checked at startup so it cannot be a scheme this page's content policy
  exists to forbid. Anything starting with a single `/` counted as local - but
  a backslash is a slash to a browser, so `/\host` resolves exactly as
  `//host` does, off-site, while being spelled like a path. It is now held to
  the character class `webapp.i18n.safe_next_path` holds the language switch
  to, which has no backslash in it. Never released: the area, the setting and
  the check were all written in this cycle.
