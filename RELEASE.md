## check-opencloud-security 1.15.0

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

## check-opencloud-security 1.14.2

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
