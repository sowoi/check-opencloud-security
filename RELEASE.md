## check-opencloud-security 1.17.0

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
