# The public scan service

A web application that runs the built-in scanner for anyone who visits it,
grades the instance from **A+** to **F**, and forgets the whole thing an hour
later. It is the same scanner the plugin uses; the web layer only serves.

**A running instance is at [scan.okxo.de](https://scan.okxo.de)** - try it
there before deploying one, or use it for a one-off scan. Everything below
describes how to run your own, which has no rate limit and can reach instances
a public service cannot.

It is **not** on PyPI. `pip install check-opencloud-security` gets the plugin
and the scanner library, deliberately without FastAPI, Redis or a single
template. The web application ships as a GitHub release asset,
`check_opencloud_security_web.tar.gz`, or you build it from a checkout.

| | |
|:--|:--|
| **Runs** | FastAPI + an ARQ worker + Redis |
| **Stores** | Nothing on disk. Redis only, every key with a TTL |
| **Needs** | No database, no account, no API key |
| **Concurrency** | Fixed by the operator, never by a request |

## Contents

- [Starting it](#starting-it)
- [What a visitor can ask for](#what-a-visitor-can-ask-for)
- [Configuration](#configuration)
- [How a scan flows through it](#how-a-scan-flows-through-it)
- [Queueing rather than refusing](#queueing-rather-than-refusing)
- [Isolation between scans](#isolation-between-scans)
- [The SSRF guard](#the-ssrf-guard)
- [Rate limiting](#rate-limiting)
- [What gets logged](#what-gets-logged)
- [Putting it behind a reverse proxy](#putting-it-behind-a-reverse-proxy)
- [The HTTP API](#the-http-api)
- [Layout](#layout)
- [Trademarks and affiliation](#trademarks-and-affiliation)

## Starting it

With Docker, which brings its own Redis:

```bash
cd docker
docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8080
```

The published image is on Docker Hub as **`okxo/opencloud-scanner`**, so a
deployment does not have to build one. `latest` and `MAJOR.MINOR.PATCH` follow
the released version, `MAJOR.MINOR` follows the line, and `edge` is the current
`main`. It carries `linux/amd64` and `linux/arm64`, and the same image runs
both the web service and the worker - they differ only in the command:

```bash
docker run --rm -p 8080:8080 \
    -e COS_WEB_REDIS_URL=redis://redis:6379/0 \
    okxo/opencloud-scanner:latest
```

Point `COS_WEB_REDIS_URL` at a Redis the worker shares, or use
[`docker/docker-compose.dockerhub.yml`](../docker/docker-compose.dockerhub.yml),
which pulls the image and wires all three together. The existing
[`docker/docker-compose.yml`](../docker/docker-compose.yml) still builds the
same stack from a checkout.

From a checkout, with three terminals or three `&`:

```bash
pip install ".[web]"
redis-server &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 python -m webapp.tasks &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 \
    uvicorn webapp.app:app --host 127.0.0.1 --port 8080
```

Building the release archive yourself:

```bash
python scripts/build_web_bundle.py
# dist/check_opencloud_security_web.tar.gz  (+ .sha256)
```

## What a visitor can ask for

Four things, and the list is closed:

| Field | Meaning |
|:------|:--------|
| `target_url` | The instance to scan. Required |
| `ignore_hardenings` | Checks to waive, from a fixed allow-list. Optional, repeatable |
| `release_track` | `rolling`, `production`, `lts` or `auto`. Optional, defaults to `auto` |
| `output_format` | `dashboard` or `json`. Optional, affects presentation only |

`release_track` is the same idea as the plugin's `--release-track`: it decides
how long the instance's release is supported and which release it is told to
upgrade to. It defaults to `auto`, which asks the release schedule which track
the installed release belongs to - the right answer for a stranger's server,
where any fixed guess is wrong for somebody: assuming `production` calls a
current rolling instance out of date, and assuming `rolling` reports an end of
life a production instance has not reached. An unknown value falls back to the
default instead of failing the scan.

Anything else is refused with **422**, by name, rather than ignored - a caller
who sends `concurrency=50` should be told it did nothing, not left believing
it worked. Concurrency, thread counts, timeouts and TLS verification are
operator settings and have no request-side equivalent at all.

Waivers are checked against an allow-list built from the hardening catalogue,
so `*` and `debugPort:*` are dropped rather than honoured. A wildcard waiver
on a public service would be a blindfold with a nice name. Flags OpenCloud
hardcodes are not offered either: waiving a finding nobody can fix would imply
somebody could.

## Configuration

Every setting is an environment variable, read once at startup.

| Variable | Default | What it does |
|:---------|:--------|:-------------|
| `COS_WEB_REDIS_URL` | `redis://127.0.0.1:6379/0` | Where ephemeral state lives. `memory://` runs without Redis, for a single-process evaluation |
| `COS_WEB_RESULT_TTL` | `3600` | Seconds a scan stays readable. Also the TTL on every key |
| `COS_WEB_MAX_WORKERS` | `5` | Scans running at once |
| `COS_WEB_SCAN_CONCURRENCY` | `4` | Probes in flight within one scan |
| `COS_WEB_SCAN_TIMEOUT` | `15` | Seconds one HTTP probe may take |
| `COS_WEB_JOB_TIMEOUT` | `180` | Seconds a whole scan may take |
| `COS_WEB_VERIFY_TLS` | `true` | Verify the target's certificate. An untrusted chain becomes a finding either way |
| `COS_WEB_ALLOW_PRIVATE_TARGETS` | `false` | Allow private, loopback and link-local targets. On-premise deployments only |
| `COS_WEB_ALLOWED_HOSTS` | *(empty)* | Hostnames exempt from the SSRF guard, separated by `;` |
| `COS_WEB_CHECK_DEBUG_PORTS` | `false` | Probe extra ports. Off in public: it is a port scan of somebody else's host |
| `COS_WEB_IP_RATE_LIMIT` | `10` | Scans per client address per window. `0` disables |
| `COS_WEB_IP_RATE_WINDOW` | `60` | The window, in seconds |
| `COS_WEB_TARGET_COOLDOWN` | `300` | Seconds before the same instance may be scanned again. `0` disables |
| `COS_WEB_TRUST_FORWARDED_FOR` | `false` | Read the client address from `X-Forwarded-For` |
| `COS_WEB_RELEASES_MODE` | `off` | Update check against the OpenCloud release feed: `off`, `auto`, `feed`, `bundled` |
| `COS_WEB_RELEASES_TOKEN` | *(none)* | GitHub token raising the feed's rate limit |
| `COS_WEB_FRONTEND_DIR` | *next to `webapp/`* | Where templates and static assets live |
| `COS_WEB_ENABLE_DOCS` | `false` | Serve `/openapi.json`, `/docs` and `/redoc`. Swagger UI loads its bundle from jsDelivr, so leave it off in public |

`COS_WEB_RELEASES_MODE` is `off` by default on purpose: a public deployment
that queries the release feed once per visitor gets rate limited, and then
every visitor's update check fails at once. The bundled release schedule still
decides end of life without any network access.

## How a scan flows through it

```text
POST /api/scans ──► client rate limit ──► SSRF guard ──► waiver allow-list
                                                              │
                          target cooldown ◄────────────────────┘
                                 │
                                 ▼
                    uuid4 ──► Redis (queued) ──► ARQ ──► 303 /scan/{uuid}
                                                          │
   worker: re-resolve ──► scan() ──► Redis (completed) ◄───┘
```

The client limit runs first because it is one `INCR` and it stops the resolver
behind the SSRF guard from being used as an amplifier. The cooldown runs last,
so a request that was going to be refused anyway does not consume the slot for
a target it never scanned.

## Queueing rather than refusing

More visitors than workers is a queue, not an outage. Every request that
passes validation gets a uuid and a **202** (or a **303** from the form), and
waits in a FIFO. The scan page shows the position - *"Scan queued. Position in
line: #2 of 7"* - and the polling script updates it every two seconds until a
worker picks the job up.

Nothing in the request can jump the queue or widen it. `COS_WEB_MAX_WORKERS`
is the only thing that decides how many scans run at once, and it is read from
the environment at worker startup.

## Isolation between scans

Each scan gets a `uuid4` and three keys of its own:

```text
scan:{uuid}:status      queued | running | completed | failed
scan:{uuid}:result      the result document
scan:{uuid}:metadata    target, waivers, timestamps
```

The uuid is a capability: knowing it is the only way to reach the scan.

- there is **no** listing endpoint, and there never will be; one request
  would undo the whole design. `GET /api/scans` only sends a browser back to
  the form, and carries nothing with it;
- an unknown, invalid or expired uuid is a **404** with an identical body in
  all three cases, so a stranger cannot learn that a uuid was once real;
- every key carries the TTL, including the one written while the scan is still
  queued. Nothing outlives the promise on the landing page.

## The SSRF guard

A public scan service forwards requests by definition, so the target is
checked before anything connects:

- the scheme must be `http` or `https`;
- the hostname must resolve, and **every** address it resolves to must be
  public unicast. One private answer among several rejects the target, which
  is what makes a multi-record trick pointless;
- `localhost`, `*.internal`, `*.local` and the cloud metadata names are
  refused by name as well, because a resolver answering those with a public
  address is either broken or lying;
- `169.254.169.254`, `100.100.100.200` and `fd00:ec2::254` are refused
  explicitly. Link-local already covers the first, but naming them keeps the
  refusal readable and survives a future carve-out.

**DNS rebinding** is answered by resolving twice: once when the request is
accepted and again in the worker immediately before the scan. The window an
attacker can aim at is then a single lookup wide, and nothing in the request
can widen it, because nothing in the request influences when a worker becomes
free.

`COS_WEB_ALLOW_PRIVATE_TARGETS=true` turns all of this off. It exists for an
on-premise deployment scanning its own estate. Do not set it on anything a
stranger can reach.

## Rate limiting

Two independent limits, both in Redis, both expiring on their own:

- **per client address** - `COS_WEB_IP_RATE_LIMIT` scans per
  `COS_WEB_IP_RATE_WINDOW`. Protects the service from one visitor;
- **per target** - one scan per `COS_WEB_TARGET_COOLDOWN`. Protects an
  OpenCloud instance from the service. Claimed with `SET NX`, so two
  simultaneous requests for the same instance cannot both win.

Both answer **429** with a `Retry-After`. The client address is never stored:
the key holds a truncated HMAC under a pepper generated at startup, which is
enough to count and useless afterwards.

## What gets logged

Lifecycle markers and a uuid:

```text
scan_created 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_started 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_completed 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
```

No target URL, no client address, no result. A log that records what everybody
scanned *is* a database of what everybody scanned, however short its
retention.

## Putting it behind a reverse proxy

Terminate TLS in front, pass `X-Forwarded-For`, and only then set
`COS_WEB_TRUST_FORWARDED_FOR=true`. The proxy must **overwrite** the header
rather than append to it - trusting a header a client can send makes the
client rate limit decorative.

The application sends its own security headers, including
`Content-Security-Policy: default-src 'self'` with no `unsafe-inline`
anywhere. Everything the pages load - CSS, JavaScript, icons, the type stack -
is served from `/static`, so there is nothing to relax. If your proxy adds a
policy of its own, make sure it does not loosen this one.

## The HTTP API

### `POST /api/scans`

```bash
curl -sS -X POST http://127.0.0.1:8080/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"target_url": "https://opencloud.example.com",
       "ignore_hardenings": ["cspWithoutUnsafeInline"]}'
```

```json
{"uuid": "0f4a1f22-...", "state": "queued", "url": "/scan/0f4a1f22-..."}
```

`target_url` may be a bare hostname; `https://` is assumed when no scheme is
given.

**202** on success, **400** for a target that cannot be scanned, **422** for a
field the service does not accept, **429** when a rate limit applies.

The browser form posts to `/` rather than here, and gets **303** to
`/scan/{uuid}`. Both paths are the same handler: a rejected submission is
re-rendered where it was posted, and `/` is a URL a reload can survive.
`Accept: text/html` selects the HTML behaviour on either path.

### `GET /api/scans/{uuid}`

```json
{
  "uuid": "0f4a1f22-...",
  "state": "queued",
  "target": "https://opencloud.example.com",
  "expiresIn": 3574,
  "queue": {"position": 2, "length": 7}
}
```

Once complete, the same endpoint carries `result` - the scanner's document,
unchanged - and `summary`, the same data regrouped for the dashboard. **404**
when the uuid is unknown or expired.

### `GET /scan/{uuid}`, `GET /`, `GET /healthz`

The result page, the landing page, and a Redis-backed health probe that says
nothing about any scan. `GET /healthz` returns 200 only after the configured
backend answers `PING`, its queue depth can be read, and a worker's short-lived
heartbeat is present. Its success body carries only the aggregate `queueDepth`
and `worker: "ok"`; it returns a detail-free 503 while any dependency is
unavailable.

## Layout

```text
webapp/                 the service
├── app.py              routes, security headers, request validation
├── settings.py         every COS_WEB_* variable
├── ssrf.py             the target guard
├── ratelimit.py        the two limits
├── store.py            the per-scan Redis namespace
├── queue.py            handing a scan to the worker pool
├── tasks.py            the ARQ worker
├── runner.py           the seam where a request becomes ScannerSettings
├── redis_backend.py    Redis, and the in-process stand-in for tests
└── catalog.py          the waiver allow-list and the dashboard grouping

frontend/
├── static/{css,js,img} vanilla CSS, two small scripts, hand-drawn SVG
└── templates/          base, index, scan, 404

docker/
├── Dockerfile.web      the image both web_app and arq_worker run
├── docker-compose.yml            locally built frontend, worker and Redis
├── docker-compose.dockerhub.yml  published-image frontend, worker and Redis
├── Dockerfile                    the plugin image, unrelated to the web application
└── docker-compose.monitoring.yml the plugin's own stack, also unrelated
```

[`webapp/README.md`](../webapp/README.md) covers the same ground from the
other side: the API surface, how to reach Swagger, what a request may not ask
for and how to run a frontend of your own.

The boundary the rest of the project keeps applies here too:
`opencloud_local_scan` measures, the plugin judges, and `webapp` serves. If a
change makes the web layer decide whether a finding is acceptable, it belongs
in the scanner or in the plugin instead.

## Trademarks and affiliation

This is an independent community project. It is **not** affiliated with,
endorsed by, sponsored by or supported by OpenCloud GmbH, and nothing it
reports is an official statement about OpenCloud software.

"OpenCloud", the OpenCloud logo and all related names and marks are the
property of their respective owners. They appear here only to identify the
software this tool checks, which is nominative use and implies no
relationship. All rights in OpenCloud remain with OpenCloud GmbH.
