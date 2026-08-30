## check-opencloud-security 1.16.0

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
