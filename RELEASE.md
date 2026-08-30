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
