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

### Changed

- **On a phone, the address field is the first thing on the page.** Stacked
  into one column, the eyebrow, the two-line headline and the lede filled
  most of the screen before the form, so a visitor had to scroll to find the
  one field the service exists for. Below 640px the form is now painted at
  the top, with the headline and introduction, the artwork and the promises
  following it. Only the painting order changes: the markup still puts the
  heading first, so screen readers and the tab order are unaffected, and
  wider screens look exactly as before.

### Fixed

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
