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
