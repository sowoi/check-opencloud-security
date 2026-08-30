# Exposed paths and debug endpoints: what this scanner checks, and why

OpenCloud is a single Go binary that serves its web frontend from assets
embedded in that binary. It never generates a directory listing and it never
serves its own configuration files, key material or database over HTTP - so
every check in this group is really the same question asked of a different
path: **is something in front of OpenCloud publishing more of the filesystem
than the reverse proxy was supposed to?**

Before any of these run, the scan first requests a path that cannot possibly
exist and remembers what comes back. OpenCloud's web frontend is a
single-page application, and unknown paths return the app shell with HTTP
`200` rather than a `404` - a naive "does this path return `200`?" check
would flag every healthy instance. Only a response that actually differs from
that catch-all baseline counts as a hit, on every check below.

<!-- TOC -->
* [Exposed paths and debug endpoints: what this scanner checks, and why](#exposed-paths-and-debug-endpoints-what-this-scanner-checks-and-why)
  * [1. Is a directory index being served: `directoryListing`](#1-is-a-directory-index-being-served-directorylisting)
  * [2. Is a specific deployment file readable: `exposed:<path>`](#2-is-a-specific-deployment-file-readable-exposedpath)
  * [3. Is a debug endpoint publicly readable: `debugEndpoint:<path>`](#3-is-a-debug-endpoint-publicly-readable-debugendpointpath)
  * [4. Is a service debug port reachable: `debugPort:<port>`](#4-is-a-service-debug-port-reachable-debugportport)
  * [5. Is the backend reachable directly, bypassing the proxy: `backendPortClosed`](#5-is-the-backend-reachable-directly-bypassing-the-proxy-backendportclosed)
  * [6. Who may read a response cross-origin: `corsOriginRestricted`](#6-who-may-read-a-response-cross-origin-corsoriginrestricted)
  * [7. Is the request echoed back: `traceMethodDisabled`](#7-is-the-request-echoed-back-tracemethoddisabled)
  * [Severity and rating impact](#severity-and-rating-impact)
<!-- TOC -->


## 1. Is a directory index being served: `directoryListing`

An `Index of /`-style page was returned. OpenCloud never generates one, so
this can only come from a plain web server pointed directly at the
deployment directory - the same misconfiguration that, left unnoticed, also
serves everything the next check looks for by name.

**Fix:** stop serving the deployment directory as static files. Point the
web server at OpenCloud's own address as a reverse proxy instead of at a
filesystem path, and switch directory indexing off explicitly (Nginx
`autoindex off`, Apache `Options -Indexes`) as a second layer - see [Reverse
proxies](reverse-proxy.md).

## 2. Is a specific deployment file readable: `exposed:<path>`

A fixed list of paths that must never answer over HTTP is requested by name:

| Path                                  | Severity |
|:---------------------------------------|:---------|
| `/opencloud.yaml`                      | critical |
| `/config/opencloud.yaml`               | critical |
| `/.opencloud/config/opencloud.yaml`    | critical |
| `/proxy/server.key`                    | critical |
| `/idm/opencloud.boltdb`                | critical |
| `/.env`                                 | critical |
| `/docker-compose.yml`                  | high     |
| `/storage/users/`                       | high     |
| `/.git/config`                          | high     |

These are configuration, key material and a database, in roughly that order
of what reading them hands over: `opencloud.yaml` and `.env` carry secrets
and settings, `proxy/server.key` is TLS private key material, and
`idm/opencloud.boltdb` is the identity store. A hit on any of them means the
deployment directory (or a git checkout of it) is reachable, exactly as with
`directoryListing` above.

**Fix:** stop serving the deployment directory - proxy to OpenCloud's own
address rather than exposing the filesystem it runs from - and confirm every
reported path answers `404` afterwards. Treat anything that *was* readable
as disclosed: rotate the TLS key, any credential in `opencloud.yaml` or
`.env`, and review the identity store for accounts created while it was
exposed.

## 3. Is a debug endpoint publicly readable: `debugEndpoint:<path>`

`/metrics`, `/config` and `/debug/pprof/` are checked on the public address.
These belong on OpenCloud's loopback-only debug listener, never in front of
a reverse proxy: `/metrics` and `/config` hand an outsider the running
configuration and internal state, and `/debug/pprof/` - when enabled - lets
the process be told to profile itself, which is both an information leak and
a way to make it do expensive work on request.

**Fix:** do not proxy `/debug` paths to the public address, and leave the
debug listeners bound to `127.0.0.1` as they are by default
(`OC_DEBUG_ADDR` and the per-service `*_DEBUG_ADDR` variables). If a metrics
scraper genuinely needs these, reach them over the internal network rather
than routing them through the same address the public internet uses.

## 4. Is a service debug port reachable: `debugPort:<port>`

Beyond the HTTP paths above, each OpenCloud service also listens on its own
debug **port**, bound to `127.0.0.1` by default. This check connects to the
default ports directly (or the ports configured in `scanner.debug_ports`) -
reaching one at all means it was published, almost always by a container
port mapping rather than a deliberate OpenCloud setting.

**Fix:** remove the port mapping that publishes it and leave the debug
listeners on `127.0.0.1`. As with the HTTP debug endpoints above, reach them
over the internal network if something needs to.

## 5. Is the backend reachable directly, bypassing the proxy: `backendPortClosed`

Port `9200` serves the same OpenCloud instance as the public address, but
without whatever a reverse proxy adds in front of it. When a proxy fronts
OpenCloud - for TLS termination, security headers, rate limiting, or all
three - a client that reaches `9200` directly gets none of that: no TLS
policy, no header hardening, none of the checks the rest of this scanner
reports as passing actually apply to a request that arrives this way.

**Fix:** remove the public port mapping for `9200` and bind the backend to
loopback or the private container network, so only the reverse proxy can
reach it.

## 6. Who may read a response cross-origin: `corsOriginRestricted`

The other checks on this page ask whether something is reachable. This one
asks who is allowed to *read the answer* once it is, which is a different
question and, on a stock instance, the more alarming one.

The browser's same-origin policy is what normally stops a page on
`attacker.example` from reading a response your OpenCloud sent. Cross-Origin
Resource Sharing is how a server switches that protection off for named
origins. OpenCloud ships with it switched off for *all* of them:
[`OC_CORS_ALLOW_ORIGINS` defaults to `*` and `OC_CORS_ALLOW_CREDENTIALS` to
`true`](https://docs.opencloud.eu/docs/dev/server/services/graph/environment-variables),
and a middleware given both commonly reflects whatever `Origin` it was sent
rather than the literal `*` - which is precisely the arrangement browsers
refuse to allow when they can see it coming.

The scan sends a request to `/graph/v1.0/me` carrying an `Origin` that cannot
belong to anybody (`https://cors-probe.check-opencloud-security.invalid` -
`.invalid` is reserved by RFC 2606 and resolves nowhere) and reads what comes
back:

| What the instance answers | Verdict |
|:--------------------------|:--------|
| The probe origin reflected, **with** `Access-Control-Allow-Credentials: true` | **critical** - any site can have a visitor's browser attach its OpenCloud session and hand the reply back |
| `Access-Control-Allow-Origin: null`, with credentials | **critical** - `null` is what a sandboxed iframe sends, and any page can put itself in one |
| The probe origin reflected, without credentials | **medium** - exposes what an unauthenticated caller could already fetch |
| A literal `*`, with or without credentials | **medium** - browsers refuse the pair with credentials, so the request fails rather than succeeding dangerously |
| A different, specific origin | **pass** - this is the configuration the check asks for |
| No `Access-Control-Allow-Origin` at all | **pass** |

**Fix:** set `OC_CORS_ALLOW_ORIGINS` to the exact origins that must reach the
API - the web interface's own origin, plus any office or client application
deliberately hosted elsewhere - and set `OC_CORS_ALLOW_CREDENTIALS=false`
unless one of them genuinely needs to send the session. The per-service forms
(`GRAPH_CORS_ALLOW_ORIGINS`, `OCS_CORS_ALLOW_ORIGINS` and so on) override the
shared name where one service needs a wider list.

## 7. Is the request echoed back: `traceMethodDisabled`

`TRACE` asks the server to send the request back as the response body,
headers included. Anything the browser attached on the way - the session
cookie, an `Authorization` header, a header the reverse proxy added - then
arrives as ordinary text, readable by a script that could never have read
those headers directly.

OpenCloud does not implement `TRACE`, so an instance answering it has a
reverse proxy or an application server in front that does. As with every
check on this page, a `200` alone proves nothing on a single-page
application: the answer only counts as an echo when the body actually looks
like the request that was sent (`Content-Type: message/http`, or the echoed
request line).

Probing for it is free in the sense that matters: `TRACE` is defined as a
safe method by RFC 9110 - it echoes and changes nothing - which is why a
plugin that may run every minute can ask.

**Fix:** refuse `TRACE` in whatever fronts the instance. Apache needs
`TraceEnable off`; nginx already returns `405` unless a location was written
to pass every method upstream; Traefik and Caddy need a rule limiting the
methods forwarded.

## Severity and rating impact

Every check in this group is an `extraChecks` entry, reported and
rating-capped whenever the scan runs at all - critical findings cap the
rating at `D`, high at `C` - see the extra-checks table in [the main
README](../README.md#what-the-scanner-checks). None of them are hardening
flags, and none require `--check-hardening`: an exposed configuration file
or an open debug port is a finding on every scan, not an opt-in one.
