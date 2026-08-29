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

## Severity and rating impact

Every check in this group is an `extraChecks` entry, reported and
rating-capped whenever the scan runs at all - critical findings cap the
rating at `D`, high at `C` - see the extra-checks table in [the main
README](../README.md#what-the-scanner-checks). None of them are hardening
flags, and none require `--check-hardening`: an exposed configuration file
or an open debug port is a finding on every scan, not an opt-in one.
