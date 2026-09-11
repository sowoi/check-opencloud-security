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
