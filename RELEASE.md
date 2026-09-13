## check-opencloud-security 1.22.0

### Added

- **The browser can ask whether the fixes worked.** Three surfaces already
  answered it - `--baseline` between two monitoring runs,
  `check-opencloud-scanner diff` between two archived documents, and the
  `compare_scans` tool for an agent - and the person who ran both scans in a
  browser was the only one who could not. `GET /compare` takes the two uuids
  they already hold and shows what was resolved, what is new, what is still
  open and how the grade moved; a finished result page links to it with its
  own uuid already filled in, so only the earlier one has to be pasted.

  **It is the same arithmetic, not a fourth opinion.** The comparison in
  `webapp/workflows.py` was split into the part that reads two documents and
  the part that compares them, and the page calls the second directly. A
  reader, an agent and an operator's own alerting are therefore told the same
  thing about the same pair - the failure mode a second implementation in the
  page would eventually produce, and the one
  [ADR 0029](adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md)
  exists to prevent.

  **Nothing is stored, and nothing is listed.** Both uuids have to be
  presented, both results have to still exist, and the answer is written
  nowhere. An unknown uuid is a 404 that names *which* of the two is gone, a
  scan still running is a 409 rather than a 404, and the same uuid twice is
  refused with 422 - an empty diff of a scan against itself reads as "nothing
  is wrong". Two documents describing different instances are compared and
  said so. Like every page that renders a result, it is never indexed.

- **Checkmk runs this check from either side now.** Checkmk speaks Nagios, so
  a Checkmk server has always been able to run the plugin as an active check
  and read its line - but that route needs the server to reach the instance,
  and the deployments where it cannot are exactly the ones an agent already
  sits inside. The agent's own protocol is not the Nagios line: metrics are
  separated by `|` rather than spaces, every value has to parse as a number
  (the `s` on `time=4.120s` does not), the service name is quoted, and the
  detail follows the summary as a literal `\n`, because a real newline starts
  another service. `--format checkmk` writes that line - one per host in
  `--host`, since one line is one service - and
  `contrib/checkmk/opencloud_security` is it as a script ready to install.

  **The scanned instance names the service**, not the host the agent runs on:
  this plugin probes an instance from outside, so the natural place to run it
  is a monitoring host watching several instances, each of which needs a
  service of its own.

  **The state stays the plugin's.** A local check's thresholds are only
  evaluated when the state field is `P`, which hands the verdict to Checkmk,
  and deciding is this plugin's whole job - thresholds, waivers, the rules
  end of life and a baseline add on top. So the line carries the state it
  already reached and the metrics carry values alone, with no second opinion
  for Checkmk to disagree with. A measurement that was not taken is left out
  rather than sent as a zero: without `--check-hardening` there is no
  `hardenings_missing`, because an empty list of missing measures would
  otherwise be indistinguishable from a perfect one.

  [`docs/checkmk.md`](docs/checkmk.md) has both routes, the metric table, and
  why the local check is installed in a `local/3600/` subdirectory rather than
  in `local/` itself - a script in the directory proper runs on every agent
  call, once a minute, which is a full scan a minute against somebody's
  production instance.

- **The web pages keep track of a scan while the reader is elsewhere.** Four
  small things for the moments nobody is looking at the page, each running
  entirely in the browser and each leaving the page exactly as it was without
  scripting:

  - **The tab title follows the scan.** `Queued: host`, `#2 in line: host`,
    `Scanning: host`, and on a finished report `Grade B: host`, so a reader
    who switched tabs sees the result from the tab strip. The server writes
    the first reading and a finished page names its grade with no script at
    all. The title never carries the uuid, and the grade goes into the tab
    alone: the `title` block that also feeds `og:title` and the structured
    data stays generic, through a new `tab_title` block in `base.html`, so a
    link preview in a chat channel does not print somebody's grade.
  - **A rescan offers the comparison with the scan before it.** A finished
    report now says "You scanned this instance earlier in this tab, at 14:02 -
    see what changed since then", linking `/compare` with both uuids filled
    in. The earlier uuids are kept in the tab's `sessionStorage` only: never
    sent to the server, gone when the tab closes, and dropped once their
    result has expired rather than offered as a link to a 404.
  - **A report warns before it disappears.** In its last five minutes a
    finished report shows a warning near the top with a link to the
    downloads, keeps the minutes current, and says so once the result has
    gone. The server renders the warning already visible when a page is
    loaded inside that window, so a reader without scripting is warned too,
    and a failed scan, which has nothing to export, is offered no download.
  - **The form offers back the last settings used.** After a scan, the next
    visit to the form offers the release track, output format and waivers
    that scan used - "use them again" or "forget them" - instead of applying
    them unasked. They are kept in `localStorage`; the address is not, since
    the browser's own autocomplete already remembers it on the visitor's
    terms. A waiver or track the catalogue no longer lists is simply not
    applied.

- **An operator can name the addresses this deployment will not scan.** Every
  rule in the SSRF guard so far was a property of the address - private,
  link-local, a metadata endpoint. None of them could express the request that
  actually arrives: an instance owner asking to be left alone, a host somebody
  keeps submitting so the service hammers it, a range that is not a scanning
  target here however public it looks. `COS_WEB_BLOCKED_TARGETS` is that list -
  hostnames, `.suffix` domains (`*.example.org` is accepted as the same thing)
  and CIDR ranges, separated by `;`.

  **It outranks every setting that loosens the guard**, `COS_WEB_ALLOWED_HOSTS`
  and `COS_WEB_ALLOW_PRIVATE_TARGETS` included. Those answer whether a request
  could be an attack, and an operator may reasonably say "not on my own
  network"; an exclusion answers whether this service scans that address at
  all, which is a promise made to somebody outside the deployment. See
  [ADR 0043](adr/0043-an-operators-exclusion-outranks-every-allowance.md).

  **A name is matched by name, a range against every address the name resolves
  to**, so a second DNS record pointing at the same machine does not buy a
  scan. It is checked at submission, again in the worker immediately before
  the scan - a target excluded while its job waited in the queue is refused
  rather than scanned - and on every redirect hop, so a scanned host cannot
  name an excluded one in a `Location` header. Agents inherit it by calling
  the same API.

  **An entry that does not parse refuses startup**, in the web process and in
  the worker alike, because a typo here is otherwise invisible: the service
  comes up, answers normally, and scans exactly what it was told to leave
  alone. The refusal a visitor sees says only that the service has been asked
  not to scan that address; which entry matched is the operator's business.

- **A name behind several addresses can be checked on every one of them.** A
  scan dials the name once and sees whichever node the resolver put first, so
  in a pool where one node missed a configuration rollout - no HSTS, demo
  accounts still signing in, an older release - that node served some of the
  visitors and none of the scans. `tlsAddressParity` could not catch it: it
  compares only the TLS identity of the two address families, and nodes behind
  one certificate share it whatever they serve. `--all-addresses`
  (`COS_ALL_ADDRESSES`, `scanner.check_all_addresses`, and the same flag on
  `check-opencloud-scanner scan`) repeats the version, header, hardening and
  demo-account checks against each resolved address and reports
  `addressParity` when they disagree; the result document lists what each
  address served under `addressObservations`.

  **It stays aimed where the scan was pointed.** Every request keeps the
  hostname in `Host` and SNI, and the addresses are the resolver's answer for
  that name - or the caller's pin, which a pinned scan never widens. The
  finding is as severe as the worst difference, because the rating was built
  from whichever node answered first: a demo sign-in on another node counts
  like `demoUsersDisabled`, another release is `high`, other drift `medium`,
  and an address that resolves but does not answer fails too. Waived names are
  not compared.

  **Off by default, and never in the web service.** It costs about a dozen
  requests per address and a single-address name has nothing to compare; the
  web application sets it off explicitly and offers no field for it, since a
  request there chooses what to scan and never how hard. See
  [ADR 0042](adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

- **The exclusions can be changed without a deployment window.** The request
  that produces most of them - somebody writing to ask not to be scanned -
  rarely arrives at a convenient moment, and an environment variable read at
  startup answers it with "after the next restart". The operator's area now
  has an *Exclusions* card that adds and withdraws entries, and a change takes
  effect **from the next request, in every process**: the API reads the list
  on each submission and the worker when each job starts, so a scan already
  waiting in the queue is refused rather than run.

  **It is the one control in that area that writes**, and deliberately the
  safest shape of one. It can only ever *refuse* a scan, so a stolen operator
  session cannot point this service at anything. `COS_WEB_BLOCKED_TARGETS` is
  a floor the page cannot withdraw - those entries are listed with no control
  beside them, and an attempt to remove one is refused with a pointer to the
  environment, so a compose file stays the truth about what it declares. And a
  store that cannot be read refuses the scan rather than proceeding without
  the list, which is the opposite of how this service treats every other piece
  of runtime state and the right way round for a list whose absence means
  scanning somebody who asked not to be. See
  [ADR 0044](adr/0044-the-operator-area-may-write-the-exclusions.md).

  **That refusal is an answer, not a stack trace**: HTTP 503 with a sentence
  in the visitor's own language saying the service cannot reach its own
  configuration, and - because there is nothing they can change to get past it
  - the same pointer at running the scanner themselves that a rate limit
  carries. The audit trail records it as `exclusions_unreadable` rather than
  as a rejected target, so an operator reading the trail is not sent looking
  for a bad address that was never the problem.

  **The two halves are one list, however each is spelled.** An entry written
  in the area is normalised; one from the environment is shown exactly as the
  compose file spells it, so that card and file can be read side by side.
  Comparing those two as text made `Example.COM` and `example.com` two
  exclusions where the guard, which parses both, only ever saw one - so they
  are now compared parsed: the area declines to store what the environment
  already holds, and refuses to withdraw it under any spelling.

  Entries added there live in Redis and are as durable as it is; the card says
  so, and points at the environment variable for anything that must outlive a
  flush. An entry is capped at 253 characters, the longest a hostname can be,
  in the area and in `COS_WEB_BLOCKED_TARGETS` alike - anything longer could
  never match a target this service would accept, so it is a typo, and the
  ceiling on the number of entries bounds nothing without it. `/admin/state` -
  the document an operator copies into an issue report - carries how many
  exclusions are in force and never which.

### Changed

- **The architecture decision records have an index.** `adr/README.md` now
  lists every record with its number, decision and status, so the one that
  governs an area can be found without opening forty-odd files by name.

- **On a phone, the address field is the first thing on the page.** Stacked
  into one column, the eyebrow, the two-line headline and the lede filled
  most of the screen before the form, so a visitor had to scroll to find the
  one field the service exists for. Below 640px the form is now painted at
  the top, with the headline and introduction, the artwork and the promises
  following it. Only the painting order changes: the markup still puts the
  heading first, so screen readers and the tab order are unaffected, and
  wider screens look exactly as before.

### Fixed

- **A name pinned to several addresses no longer fails on the first one
  alone.** The web service resolves a submitted name, vets every address and
  pins the scan to them - and then only ever dialled the first. A dual-stack
  instance whose AAAA record points at nothing, or a scan from a host without
  an IPv6 route, answered "unreachable" where a visitor's browser simply used
  IPv4. A connection now tries the vetted addresses in order and the one that
  accepts is dialled first from then on; the TLS inspection and the debug-port
  probes use that address too, so a dead first address no longer reports a
  handshake failure or closed ports the instance does not have. Nothing
  outside the pinned list is ever dialled, only a failure to connect moves on,
  a single pinned address - the per-address comparison - is never widened, and
  the result document still lists the addresses in the order they resolved.
  The plugin, which does not pin, was not affected.

- **A comparison shows when each scan ran, instead of calling both times
  "unparsable".** `scannedAt` is written by the scanner from its own clock and
  is not one of the fields a scanned host has any say in, but it was being run
  through the allow-list meant for a version string a stranger chose - and
  that list has no `:` in it. Every comparison reported both timestamps as
  `unparsable`, to an agent as well as on the new page.

## check-opencloud-security 1.21.3

### Fixed

- **A storage directory nobody named no longer writes a compose file Docker
  refuses to parse.** Answering `filesystem` to the Redis persistence or audit
  trail question and then leaving the path empty produced `- :/data` - an
  empty mount source, a colon, and a stack that will not start, over a
  question that was never answered. The empty answer now falls back to the
  named volume, which needs nothing from anybody and keeps the data, and the
  wizard says that it did.

  **The directory is asked for properly, and it has a default**: `./data` for
  Redis and `./audit` for the trail, beside the generated compose file. The
  leading `./` is the whole point - Compose reads `data:/data` as a *named
  volume* called data and `./data:/data` as the directory next to the file, so
  a bare name is refused with that explanation rather than silently mounting
  something else. An absolute path still works.

- **The wizard asks the questions an answer opens, instead of only the first
  one.** Each section's question list was filtered once, before the section
  began, and the re-check inside the loop could only ever remove a question -
  never add the ones a fresh answer had just made relevant. The visible result
  was a mail server configured with nothing but a host name: the port, the
  transport security, the credentials and the From address all hung off
  `smtp_host` being set, and by the time it was, the list they would have been
  in had already been decided. Relevance is now decided one question at a time
  as the answers arrive.

  The same fault hid every Authentik question behind `--with-authentik`.
  Answering *yes* to "add Authentik to this stack" at the prompt asked for
  neither its address, nor its slug, nor **its ports**, and then generated a
  stack pinned to 9000 and 9443.

- **The release tarball carries the blueprint that provisions `/admin`.** It
  shipped `opencloud-scanner.yaml` and not `opencloud-admin.yaml`, so a
  deployment set up from the download could turn the operator's area on and
  get no proxy provider to reach it with.

### Added

- **The wizard's questions can be moved around in, and its summary can be
  worked in.** Forty-odd questions with no way back, no way to skip ahead and
  no way to fix one from the summary meant that noticing a typo one question
  too late left two options: abandon the run, or answer the rest of it knowing
  the compose file would need editing anyway. Now, at any question: `b` goes
  back to the one actually asked before it, a numbered choice can be answered
  with its number, `-` empties a text setting where an empty line only ever
  kept the default, and `rest` takes every remaining default and jumps to the
  summary. Section headings carry their position - *(7 of 12)* - because a
  long walk that says nothing about how much is left is one people abandon
  halfway.

  **The summary is the last place a mistake is caught, and it used to be a
  dead end.** It is now grouped under the headings the questions were asked
  under, with what was derived or generated listed apart from what somebody
  decided, and it asks *"Write it all out now? [Y/n], or name a setting to
  change"*. Naming one - `host_port`, or enough of it to be unambiguous -
  re-asks that question and comes straight back, so the express path through
  the whole thing is `rest` and then the three settings that matter.

- **Running the wizard again edits the deployment rather than re-describing
  it.** It always promised that, and delivered half: `.env` was read back so
  no credential was regenerated, and every *other* answer - the ports, the
  limits, the paths, the proxy, the sign-in - was gone. It now writes
  `.<compose-file>.answers.json` beside the compose file, its own notebook of
  every non-secret answer, and offers those back as the defaults on the next
  run. Changing a port on a live deployment is a re-run, `rest`, one setting,
  done. The notebook holds no credentials - those stay in the owner-readable
  `.env` they are already read back from - and is safe to delete. A preset
  named on the command line now overrides what it remembers, which is why
  `--preset public` sets the answers the private preset moves rather than
  doing nothing.

- **Turning the operator's area on ends the wizard with the walkthrough for
  opening it.** `/admin` refuses rather than asks - no login page to arrive
  at, no password prompt to get wrong - so every missing piece of the
  arrangement produces the same 404 as any unknown path: the right answer to
  give a stranger, and a miserable one to debug against. The steps are now
  printed in order with this deployment's own addresses in them: set the first
  Authentik password, put that account in the `opencloud-scanner-operators`
  group the blueprint binds the application to, install the generated proxy
  configuration, give Caddy or Traefik the shared secret in its own
  environment - it reads the value at run time rather than carrying it, so an
  installed, correct-looking file is not the last step - check that
  `COS_WEB_ADMIN_USERS` names the same person, and open the area. Then what
  each failure means: a bare 404 is the header that never arrived, a 404 after
  signing in is the second guest list, and a looping sign-in is a provider
  whose public address is not the one the browser used. Against somebody
  else's provider it names the header contract instead, and the sign-out URL
  the bundled stack sets for itself.

- **The wizard writes the reverse proxy configuration too.** The stack
  publishes a plain HTTP port on the loopback address and nothing else, so
  something in front has to terminate TLS - and the notes for doing that lived
  only in `docs/reverse-proxy.md`, to be copied by hand. Name what you run -
  nginx, Apache httpd, Caddy or Traefik - and the file is written beside the
  compose file, with the install commands in its header and in the wizard's
  next steps: TLS with a redirect from port 80 that leaves the ACME challenge
  alone, an `X-Forwarded-For` that is *set* rather than appended so a client
  cannot choose the address its rate limit is counted against, and a `/mcp`
  that is never buffered, because a buffered event stream is an agent session
  that waits for ever. Each of the four was checked against the server itself.

  **Where the stack can provide it, the file carries the forward auth in front
  of `/admin`**: the request is shown to the authentik outpost first and only
  what it accepts is passed on, carrying the identity the outpost established
  and the shared secret that makes those headers worth believing. Apache is
  the exception and says so in the file - it has no forward auth of its own,
  so the area is proxied by the catch-all without that header and the service
  answers 404, which is the right failure rather than an unauthenticated
  console.

  **The secret is not in the file you would commit.** A proxy configuration is
  pasted into tickets and copied between hosts exactly like a compose file, so
  nginx gets a one-line `include` of an owner-readable snippet - deliberately
  not named `.conf`, since everything called that under `conf.d` is included
  into the `http` block and this belongs to one location - while Caddy and
  Traefik read the value from their own environment.

### Changed

- **An identity provider can now be asked for by the operator's area alone.**
  `/admin` has no other way in - the service authenticates nobody and refuses
  a request that did not arrive through an outpost - but every Authentik
  question hung off the MCP endpoint being enabled, so a deployment that
  wanted the area and not the agent endpoint could not be offered one. The
  provider is its own section now, asked for by either consumer, and a
  deployment with an area gets the second blueprint,
  `authentik/blueprints/opencloud-admin.yaml`, copied beside the compose file
  that mounts it, with `COS_WEB_ADMIN_URL` set to the origin it protects. A
  provider with nothing to guard is still not deployed.

- **The mail questions cover the whole session.** Beyond the server name:
  the port, STARTTLS or implicit TLS or neither, whether the server wants an
  account at all, the username, the password and the From address. Saying it
  wants no account stops the credential questions and drops any answer left
  over from before, because Authentik reads an empty username as *do not
  authenticate* and half a credential fails at the first message rather than
  at the first mistake. A username with no password, and a password with no
  username, are each pointed out before anything is written.

- The guest list and the shared secret for the operator's area are no longer
  asked for when the area is off - an unused credential in `.env` is an
  invitation to turn the area on without one.
