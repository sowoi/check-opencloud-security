# What the scanner reads, and what it deliberately does not

The complete inventory of what a scan takes from an instance: the endpoints
it reads, every additional check it runs and what each one is worth, which
observations are recorded but never graded, and the questions a scan from
outside cannot answer at all.

The [main README](../README.md#the-built-in-scanner) summarises this in a
paragraph; the individual checks are explained one group at a time in
[TLS](tls.md), [CSP](csp.md), [cookies](cookies.md),
[authentication](authentication.md), [sharing](sharing.md),
[exposure](exposure.md), [embedding](embedding.md) and
[lifecycle](lifecycle.md).

<!-- TOC -->
* [What the scanner reads, and what it deliberately does not](#what-the-scanner-reads-and-what-it-deliberately-does-not)
  * [What the scanner checks](#what-the-scanner-checks)
  * [Reading the version correctly](#reading-the-version-correctly)
  * [Debug ports](#debug-ports)
<!-- TOC -->


## What the scanner checks

Read from the instance itself:

- product, `productversion` and edition from `/status.php`; a server whose
  product name says ownCloud or Nextcloud is refused rather than rated,
  because it serves the same endpoint but is not the same software - see
  [`docs/what-is-opencloud.md`](what-is-opencloud.md) for where the three
  projects came from and how they diverged. `/status.php`
  also carries `maintenance`, `installed` and `needsDbUpgrade`, but OpenCloud's
  own handler for it hardcodes all three (`false`, `true`, `false`) rather than
  reading real state, so this scanner does not check them - see
  [`docs/status-php.md`](status-php.md).
- the IPv4 and IPv6 addresses the name resolved to while the scan ran,
  reported as `addresses` in the result document and shown as **Resolved to**
  on a web result page - context, never a finding, and empty when a name
  does not resolve or an address was scanned directly
- capabilities from `/ocs/v1.php/cloud/capabilities` (both endpoints are
  unauthenticated in OpenCloud)
- the security headers `Strict-Transport-Security`, `Content-Security-Policy`,
  `X-Content-Type-Options`, `X-Frame-Options`,
  `X-Permitted-Cross-Domain-Policies`, `X-Robots-Tag`, `X-XSS-Protection` and
  `Referrer-Policy`, reported as `setup.headers` - see
  [`docs/csp.md`](csp.md) for what the `Content-Security-Policy` checks
  look for and why
- four further headers that **no** OpenCloud sends - `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` and
  `Cross-Origin-Embedder-Policy` - reported separately as
  `setup.advisoryHeaders`. A reverse proxy can add all four and the instance
  is better for it, but their absence is the shipped state of every OpenCloud
  rather than a fact about this deployment, so they are explained by `--debug`
  and never counted as a missing hardening, never alerted on and never allowed
  to change an exit code. See
  [ADR 0028](../adr/0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md).
  Rehearse `Cross-Origin-Embedder-Policy: require-corp` before rolling it
  out - an office integration that embeds Collabora or a WOPI host stops
  loading unless that origin sends a `Cross-Origin-Resource-Policy` of its own
- whether `/.well-known/security.txt` tells somebody who finds a flaw where to
  report it, as `securityTxtPublished` under `setup.advisoryChecks`. The same
  bargain as the headers above, for what is not a header: OpenCloud publishes
  none on any instance, so it is explained and never counted. The file has to
  carry the `Contact` field RFC 9116 requires - a 200 alone means nothing on
  an instance whose frontend answers every unknown path with its own shell.
  See [ADR 0034](../adr/0034-an-advisory-observation-need-not-be-a-header.md)
- `hardenings` derived from those headers and capabilities
- known vulnerabilities from the [advisory database](../README.md#advisory-database) and
  the resulting rating (`0`-`5`)

Plus the additional checks (`extraChecks` in the JSON, disable with
`--no-extra-checks`):

| Check                                                                                                                                      | Severity      | Purpose                                                                                                     |
|:-------------------------------------------------------------------------------------------------------------------------------------------|:--------------|:------------------------------------------------------------------------------------------------------------|
| `httpsAvailable`, `tlsHandshake`, `tlsProtocol`                                                                                            | critical/high | Instance only reachable over HTTP, broken TLS, or a protocol older than TLS 1.2                             |
| `tlsCertificate`, `tlsTrusted`                                                                                                             | high/medium   | Certificate expired, expiring within `scanner.tls_min_days`, or not trusted                                 |
| `tlsDeprecatedProtocol`                                                                                                                    | high          | The server still accepts TLS 1.0 or 1.1 even though it negotiated something newer with us                   |
| `tlsHostname`                                                                                                                              | high          | The certificate does not cover the name it was asked for                                                    |
| `tlsChain`                                                                                                                                 | medium        | The chain is missing an intermediate, so it validates only for clients that happen to have one cached       |
| `tlsCertificateLifetime`                                                                                                                   | low           | The certificate is valid for longer than the 398 days browsers accept                                       |
| `tlsCipherSuite`                                                                                                                           | medium        | The cipher suite negotiated by this scan is weak or lacks forward secrecy                                   |
| `tlsCertificatePolicy`                                                                                                                     | medium        | The certificate has a weak key or an MD5/SHA-1 signature                                                    |
| `tlsAddressParity`                                                                                                                          | medium        | IPv4 and IPv6 present different TLS services, or one is unreachable                                          |
| `tlsCaaRecord`                                                                                                                             | low           | No DNS CAA record restricts which certificate authorities may issue for this name                            |
| `cookieSecure`, `cookieHttpOnly`, `cookieSameSite`                                                                                        | high - low    | An observed cookie lacks Secure, HttpOnly or SameSite                                                        |
| `cookiePrefix`                                                                                                                             | low           | No observed cookie uses the `__Host-`/`__Secure-` name prefix, or one claims a prefix it does not honour     |
| `tlsOcspStapling`                                                                                                                          | low           | No OCSP response stapled to the handshake, although the certificate names a responder                       |
| `tlsCertificateTransparency`                                                                                                               | medium        | A publicly trusted certificate carries no signed certificate timestamps, so Chrome and Safari will refuse it |
| `tlsEarlyData`                                                                                                                             | low           | The server's session tickets invite a TLS 1.3 0-RTT flight, which has no replay protection                  |
| `corsOriginRestricted`                                                                                                                     | critical/medium | Any origin may read the API's responses; critical when credentials are allowed with it                     |
| `traceMethodDisabled`                                                                                                                      | medium        | The server answers `TRACE` by echoing the request, session cookie included                                  |
| `forwardedHostIgnored`                                                                                                                     | medium        | A host name the caller supplied comes back in the discovery document, so a caller chooses where a sign-in goes |
| `header:<name>`                                                                                                                            | high - low    | One of the headers above missing or too weak                                                                |
| `authentication:/remote.php/dav/files/`, `/graph/v1.0/users`, `/ocs/v1.php/cloud/user`                                                     | critical/high | An endpoint that must demand authentication answered anyway                                                 |
| `exposed:/opencloud.yaml`, `/proxy/server.key`, `/idm/opencloud.boltdb`, `/.env`, `/docker-compose.yml`, `/storage/users/`, `/.git/config` | critical/high | Deployment internals published by a misconfigured reverse proxy                                             |
| `directoryListing`                                                                                                                         | critical      | A directory index served instead of the web frontend                                                        |
| `demoUsersDisabled`                                                                                                                        | critical      | The built-in identity provider still accepts the documented demo accounts, one of which is an administrator |
| `debugEndpoint:/metrics`, `/config`, `/debug/pprof/`                                                                                       | critical/high | Debug handlers reachable on the public address                                                              |
| `debugPort:<port>`                                                                                                                         | high          | A service debug port answering from the outside                                                             |
| `backendPortClosed`                                                                                                                        | high          | The same OpenCloud instance is reachable directly on backend port 9200, bypassing its reverse proxy         |
| `webEmbedDelegatedAuthenticationRestricted`                                                                                                | critical      | Delegated iframe authentication accepts messages without an explicit trusted origin                         |
| `webEmbedMessageOriginRestricted`                                                                                                          | high          | The web client's embed messages trust every parent origin                                                   |
| `basicAuthDisabled`                                                                                                                        | medium        | The proxy still offers HTTP basic authentication                                                            |
| `identityProviderDetected`                                                                                                                 | low           | No OpenID Connect discovery document and no redirect from it, so who signs users in cannot be established   |
| `reverseProxyDetected`                                                                                                                     | low           | Nothing suggests a reverse proxy in front of the instance                                                   |
| `versionDisclosure:Server`, `webfingerVersionDisclosure`                                                                                   | low           | Exact versions leaked to unauthenticated callers                                                            |

A failed additional check caps the rating (critical -> `D`, high -> `C`, medium
-> `A`, low -> `A+`); set `scanner.extra_checks_rating: false` to report them
without touching the rating. For the reasoning behind each group of checks
above, see [`docs/cookies.md`](cookies.md),
[`docs/authentication.md`](authentication.md),
[`docs/sharing.md`](sharing.md), [`docs/exposure.md`](exposure.md),
[`docs/embedding.md`](embedding.md) and
[`docs/lifecycle.md`](lifecycle.md), alongside
[`docs/csp.md`](csp.md) and [`docs/tls.md`](tls.md) above.

OpenCloud is a single Go binary that serves its web frontend from embedded
assets, and its frontend is a single-page application: unknown paths return the
app shell with HTTP 200 rather than a 404. A naive "does `/opencloud.yaml`
return 200?" check would therefore flag every healthy instance. The scanner
first probes a path that cannot exist, learns what the catch-all response looks
like, and only reports an exposed path whose response actually differs from it.

### Who signs users in

The scan also reads `/.well-known/openid-configuration` - the OpenID Connect
discovery document, or the redirect the instance answers it with - to find out
which identity provider issues its tokens. An issuer on a different host means
an external provider such as Keycloak, Authentik or Authelia is in front of the
instance, and the result document records it:

```json
{"identityProvider": {"detected": true, "external": true,
                      "issuer": "https://id.example.com", "vendor": "Keycloak"}}
```

This is context, never a verdict: using the built-in provider fails nothing,
and no check requires an external one. It only softens `basicAuthDisabled`,
which is `medium` normally and `low` when the interactive login goes through an
external provider.

Nothing is submitted to the instance to establish this. The discovery document
and the `Location` header are read, and no login form is ever filled in - a
scanner that guesses credentials against somebody's instance is a scanner
nobody should point at their server, and an identity provider is the worst
place to start.

When no provider can be found at all, `identityProviderDetected` fails at
severity `low` and `--debug` points at [OpenCloud's own
documentation][opencloud-idp] - the usual cause is a reverse proxy that does
not forward `/.well-known/`.

### The demo accounts

When the discovery document names the instance's *own* provider - the built-in
identity management rather than a Keycloak or Authentik in front of it - the
scan additionally checks whether the demo users are still on.
`IDM_CREATE_DEMO_USERS=true` creates five accounts whose names and passwords
are printed in [OpenCloud's documentation][opencloud-demo-users], and `dennis`
is an administrator. Left enabled on a reachable instance, that is an admin
account whose password everybody already knows, so `demoUsersDisabled` is a
`critical` finding: it fails the check and caps the rating at `D`.

This is the one place the scan sends a credential, and it does so because
there is no other way to see those accounts from outside - nothing OpenCloud
exposes unauthenticated lists its users. What is sent is a published default
rather than a guess at anybody's password, only the documented pairs are
tried, and they go only to the instance's own provider: with an external
identity provider the accounts come from there, the check does not apply, and
no login is ever pushed at a third party. Switching the setting off does not
delete accounts that already exist, so a failing instance needs them removed
as well.

### What is in front of the instance

`reverseProxy` records whether anything answers before OpenCloud does: a
`Server` header naming Nginx, Caddy, Cloudflare or another proxy, or a header
only a forwarder adds such as `Via`.

```json
{"reverseProxy": {"detected": true, "vendor": "Nginx", "evidence": "Server: nginx"}}
```

`reverseProxyDetected` fails when nothing was found, and does so at severity
`low` **on purpose**: Traefik and HAProxy announce nothing by default, and
stripping the `Server` header is itself good practice, so a well-run
deployment can look bare from outside. The finding is worth showing and is
never worth a grade.

`forwardedHostIgnored` asks the other question about the same boundary: not
whether something is in front, but whether the instance lets whoever is
calling decide what it thinks its own address is. The scan requests
`/.well-known/openid-configuration` twice with a host that does not exist -
once as the request's own `Host`, once as `X-Forwarded-Host` - and looks for
that host coming back in the `Location` it redirects to or in the `issuer`,
`authorization_endpoint`, `token_endpoint`, `end_session_endpoint` or
`jwks_uri` the document publishes.

```json
{"id": "forwardedHostIgnored", "severity": "medium", "passed": false,
 "detail": "A host name the caller supplied is published back: X-Forwarded-Host comes back as the issuer it publishes"}
```

Those URLs are where a client sends the next sign-in, so a caller who picks
the host has picked where an authentication request goes. On its own it
misleads only whoever sent the header, which is why it is `medium` rather
than higher; behind a cache it becomes the answer everybody gets, and behind
a proxy that forwards a client's own `X-Forwarded-Host` it is a stranger who
chooses. It means the instance was never told its public address and derives
one from each request - set `OC_URL`, and set the forwarded headers from the
proxy's configuration rather than passing the client's through.

Only a URL a client would be *sent* to counts. A default virtual host that
refuses an unrecognised name commonly prints that name in its error page, and
reading the body for it would report the correct behaviour as the finding.
An instance that publishes no discovery document at all is not judged either
way: two errors are the scan learning nothing, not a pass.

### Office and calendar integrations

Two integrations are visible without logging in, and both are reported as
observations rather than verdicts:

- `/app/list` is unprotected by OpenCloud's own proxy policy and names the app
  providers actually registered with the app registry - Collabora, OnlyOffice
  and the like. The `app_providers` block in the capabilities document is
  hardcoded and says nothing, so it is not used.
- `/.well-known/caldav` answers with a redirect or an authentication challenge
  only when something is wired to it, which is how a proxied Radicale shows up.
  A stock instance answers 404.

```json
{"integrations": {"office": {"detected": true, "apps": ["Collabora"], "groupware": false},
                  "calendar": {"detected": true, "advertised": true}}}
```

Neither becomes a check and neither can move the rating.

### What the scan deliberately does not answer

- **Audit logging.** OpenCloud's audit service only consumes the internal
  event bus. It publishes no endpoint, and no unauthenticated document
  mentions it, so whether it is enabled cannot be established from outside at
  all. **It is not checked**, and a clean report says nothing about it.
- **Whether an integration is configured *correctly*.** The scan reports that
  an app provider is registered, or that something answers the CalDAV path.
  WOPI secrets, share permissions and the other service's own configuration
  live behind a login and are not checked.
- **Anything requiring credentials.** No login form is ever submitted and no
  password is ever guessed. The single exception is the demo accounts above:
  the passwords OpenCloud publishes are sent, as published, to the instance's
  own identity provider, because that is the only way to see from outside
  whether those accounts still exist.
- **Your firewall, your identity provider's policy, your backups.** All of it
  matters more than several of the things above, and none of it is visible
  over HTTP.

Everything in that list still has to be got right, so
**[Running OpenCloud in a secure infrastructure](secure-deployment.md)**
covers the part a scan cannot see: putting Keycloak, Authentik or Authelia in
front of the instance, turning the audit service on and getting its log off
the host, firewalling the ports Docker publishes behind your back, what the
people using the instance should be told, and where scheduled scanning with
this plugin fits alongside all of it.

[opencloud-idp]: https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp
[opencloud-demo-users]: https://docs.opencloud.eu/docs/admin/resources/demo-user/

## Reading the version correctly

`/status.php` reports three version fields, and two of them are traps:

```json
{"version":"0.1.0.0","versionstring":"0.1.0","productversion":"7.4.0"}
```

`version` and `versionstring` are hardcoded constants OpenCloud sends to keep
old sync clients happy - they are the same on every instance and say nothing
about the release. The real release is **`productversion`** only. The scanner
uses `productversion`, falls back to the capabilities endpoint, and reports
`legacyVersion: true` in the result document when an instance offers nothing
but the placeholder. Anything comparing versions from `/status.php` by hand
(including other monitoring scripts you may already run) is almost certainly
reading the wrong field.

## Debug ports

Every OpenCloud service has a debug listener that serves `/healthz`,
`/readyz`, `/metrics`, `/config` and `/debug/pprof`. `/metrics` includes
`opencloud_proxy_build_info` (exact version), `/config` dumps the effective
service configuration, and `/debug/pprof` allows anyone to trigger profiling.

These listeners bind to loopback by default, so a debug port that answers from
your monitoring host is a genuine finding - usually a container that published
the whole port range. The scanner probes the five most informative ones:

| Port | Service  |
|:-----|:---------|
| 9205 | proxy    |
| 9141 | frontend |
| 9124 | graph    |
| 9134 | idp      |
| 9239 | idm      |

Each probe is a single TCP connect with a three second timeout, so a firewalled
host costs up to 15 seconds. Turn the probes off with `--no-debug-ports`, run
them in parallel with [`--concurrency`](#speeding-the-scan-up), or tune them:

```yaml
scanner:
  check_debug_ports: true
  debug_ports: [9205, 9141]
  debug_port_timeout: 1
```

### Speeding the scan up

A scan spends nearly all of its time waiting for the instance to answer: around
twenty HTTP requests and five TCP connects, one after the other.
`scanner.concurrency` runs those probes in parallel for a single-host scan;
raising it shortens a run considerably, at the price of a burst of parallel
requests against the instance, and is most noticeable when debug-port probing
runs into a firewall that swallows the connections. `--concurrency` instead
controls the outer host-worker ceiling described in
[Checking multiple hosts](../README.md#checking-multiple-hosts).

The setting changes only the timing, never the verdict: the result document
lists the same findings in the same order whatever the value is. Values above
`32` are clamped. It can also be set once for every host:

```yaml
scanner:
  concurrency: 8
```
