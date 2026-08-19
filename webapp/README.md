# The web application and its frontend

This directory is the public scan service: a small FastAPI application, an ARQ
worker, and Redis holding nothing for longer than an hour. The pages it serves
live one directory up in [`frontend/`](../frontend). Neither is on PyPI - the
wheel is the plugin and the scanner, and a monitoring host has no use for
FastAPI.

- **Operators** want [`docs/webapp.md`](../docs/webapp.md): deployment, the
  reverse proxy, every setting and the threat model behind it.
- **Anyone who just wants a scan** wants
  [scan.okxo.de](https://scan.okxo.de), where this service is already running.
- **This file** is for whoever is changing the service or writing a client
  against it.

* [What is where](#what-is-where)
* [Running it](#running-it)
* [The HTTP API](#the-http-api)
* [Scanning several instances at once](#scanning-several-instances-at-once)
* [Taking a result away](#taking-a-result-away)
* [Erasing an instance on request](#erasing-an-instance-on-request)
* [Swagger and the OpenAPI schema](#swagger-and-the-openapi-schema)
* [What a request may not ask for](#what-a-request-may-not-ask-for)
* [Configuration](#configuration)
* [Customising the frontend](#customising-the-frontend)
* [Tests](#tests)
* [Trademarks and affiliation](#trademarks-and-affiliation)

## What is where

```text
webapp/
├── app.py            routes, security headers, request validation
├── settings.py       every COS_WEB_* variable, read once at startup
├── ssrf.py           the target guard: what may be connected to
├── ratelimit.py      the client limit and the per-target cooldown
├── audit.py          the optional audit trail, pseudonymised
├── store.py          one Redis namespace per scan, TTL on every key
├── queue.py          handing a scan to the worker pool
├── tasks.py          the ARQ worker; `python -m webapp.tasks`
├── runner.py         where a request becomes ScannerSettings
├── redis_backend.py  Redis, and the in-process stand-in for tests
├── reports.py        the CSV, SARIF and PDF exports
├── arazzo.py         the API described as executable workflows
├── purge.py          erasure on request, and the signed receipt for it
└── catalog.py        the waiver allow-list and the dashboard grouping

frontend/
├── templates/        base.html, index.html, scan.html, 404.html,
│                     how-it-works.html, api.html, privacy.html, about.html,
│                     _page-nav.html (the cross-links between them)
└── static/
    ├── css/app.css   the whole design system, hand-written
    ├── js/app.js     landing page niceties; the form works without it
    ├── js/scan.js    polls /api/scans/{uuid} until the scan settles
    └── img/*.svg     drawn for this project
```

Three layers, and the boundary between them is the point:
`opencloud_local_scan` **measures**, the plugin **judges**, and `webapp`
**serves**. If a change here starts deciding whether a finding is acceptable,
it belongs in the scanner or the plugin instead.

## Running it

With Docker, which brings its own Redis:

```bash
cd docker && docker compose -f docker-compose.dockerhub.yml up
# http://127.0.0.1:8080
```

The released image is on Docker Hub as `okxo/opencloud-scanner`
(`latest`, `MAJOR.MINOR.PATCH`, `MAJOR.MINOR` and `edge`, for `linux/amd64`
and `linux/arm64`), built from
[`docker/Dockerfile.web`](../docker/Dockerfile.web) by
[`.github/workflows/publish-dockerhub.yml`](../.github/workflows/publish-dockerhub.yml).
The new Compose file pulls it for both frontend and worker services without
altering the existing local-build Compose file. See
[`docs/webapp.md`](../docs/webapp.md#starting-it) for deployment details.

From a checkout:

```bash
pip install ".[web]"
redis-server &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 python -m webapp.tasks &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 \
    uvicorn webapp.app:app --host 127.0.0.1 --port 8080 --reload
```

`COS_WEB_REDIS_URL=memory://` runs the API with an in-process stand-in and no
Redis at all. Handy for looking at the pages; scans stay `queued`, because
nothing is listening on the other end of the queue.

## The HTTP API

A small surface, and this is all of it.

| Method | Path | What it does |
|:-------|:-----|:-------------|
| `GET` | `/` | The landing page and the form |
| `GET` | `/how-it-works`, `/api`, `/privacy`, `/about` | The content pages the landing page links to; HTML only, never in the schema |
| `POST` | `/` | The form submission; **303** to `/scan/{uuid}` |
| `POST` | `/api/scans` | The same handler for API clients; **202** with the uuid |
| `POST` | `/api/scans/batch` | Several targets at once; **202** with what started and what did not |
| `GET` | `/api/scans` | Redirects to `/`. It lists nothing - there is no listing |
| `GET` | `/scan/{uuid}` | The progress and result page |
| `GET` | `/api/scans/{uuid}` | The state, and the result once there is one |
| `GET` | `/api/scans/{uuid}/export/{format}` | The finished scan as `json`, `csv`, `sarif` or `pdf` |
| `DELETE` | `/api/purge` | Erases everything held for one instance and returns a signed receipt; **404** until a token is configured |
| `GET` | `/arazzo.json` | The API as Arazzo workflows, beside the schema and behind the same switch |
| `GET` | `/healthz` | Pings Redis, reads queue depth, and requires a live worker heartbeat; returns the aggregate depth or a 503 when unavailable |

### Starting a scan

```bash
curl -sS -X POST http://127.0.0.1:8080/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"target_url": "opencloud.example.com",
       "ignore_hardenings": ["cspWithoutUnsafeInline"],
       "release_track": "production",
       "output_format": "dashboard"}'
```

```json
{"uuid": "0f4a1f22-...", "state": "queued", "url": "/scan/0f4a1f22-..."}
```

`target_url` may be a bare hostname - `https://` is assumed when no scheme is
given, which is why the form's input field is not `type="url"`.

| Status | When |
|:-------|:-----|
| **202** | Accepted and queued, even when every worker is busy |
| **303** | The same, for a browser: `Location: /scan/{uuid}` |
| **400** | A target that cannot be scanned: private, loopback, unresolvable, malformed |
| **422** | A field the service does not accept, named in the message |
| **429** | A rate limit, with `Retry-After` and a pointer to running it yourself |

An overloaded service still answers **202**. Submissions past the worker count
wait in FIFO order and the position is shown on the page; a valid submission
never gets a **503**.

### Polling a scan

```bash
curl -sS http://127.0.0.1:8080/api/scans/0f4a1f22-...
```

```json
{
  "uuid": "0f4a1f22-...",
  "state": "queued",
  "target": "https://opencloud.example.com",
  "expiresIn": 3574,
  "queue": {"position": 2, "length": 7}
}
```

`state` moves `queued` → `running` → `completed` or `failed`. A completed scan
carries `result`, the scanner's document unchanged, and `summary`, the same
data regrouped for the dashboard. `scan.js` polls this endpoint with a backoff
and stops as soon as the state settles.

The uuid is a capability token. Unknown, invalid and expired all answer the
same **404** with the same body, so nobody can learn that a uuid was once
real, and there is no endpoint that enumerates scans.

## Scanning several instances at once

`POST /api/scans/batch` takes `targets` in place of `target_url` and is
otherwise the same request:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/scans/batch \
  -H 'Content-Type: application/json' \
  -d '{"targets": ["one.example.com", "two.example.com"],
       "release_track": "production"}'
```

```json
{
  "accepted": [{"uuid": "0f4a1f22-...", "target": "https://one.example.com",
                "state": "queued", "url": "/scan/0f4a1f22-..."}],
  "rejected": [{"target": "https://two.example.com", "status": 429,
                "detail": "That instance was scanned very recently...",
                "retryAfter": 284}],
  "counts": {"submitted": 2, "accepted": 1, "rejected": 1}
}
```

**A batch buys convenience, not capacity.** Each target runs the whole
single-submission pipeline in the order it was written: the client rate limit
counts it, the SSRF guard validates it, and it claims its own target cooldown.
Ten targets spend ten scans from the window. That is why the answer is two
lists - a batch where the third instance is in cooldown and the fourth is a
typo should still scan the other eight.

`COS_WEB_MAX_BATCH_TARGETS` (default 10) caps the list, and a longer one is
refused as a whole before anything is queued, so nothing pays a cooldown for a
batch that never ran. **202** when at least one target started; when none did,
the status is the reason the first was refused, with `Retry-After` and the
self-hosting pointer if that reason was a limit.

Each uuid is polled exactly as a single scan, and reaches nothing but its own
scan - batching creates no handle over the group.

## Taking a result away

`GET /api/scans/{uuid}/export/{format}` renders a finished scan as `json`,
`csv`, `sarif` or `pdf`:

```bash
curl -sS -OJ http://127.0.0.1:8080/api/scans/0f4a1f22-.../export/pdf
```

| Format | For |
|:-------|:----|
| `pdf` | A ticket, a review, a printout. Written by `reports.py` itself - no reporting library, for the same reason the frontend loads nothing from a CDN |
| `csv` | A spreadsheet: a header block, then one row per finding with a section column |
| `sarif` | A code-scanning dashboard: SARIF 2.1.0, every result carrying a rule with the catalogue's own explanation |
| `json` | The scanner's document, unchanged |

All four are renderings of one finished result and are produced on request, so
none of them outlives the scan. A finished `GET /api/scans/{uuid}` advertises
the URLs under `exports`, and the result page offers them as download buttons -
plain links, because the policy forbids an inline handler.

**409** while the scan has not finished: it exists, and answering 404 would
send a caller into a retry loop against the wrong endpoint. **404** for an
unknown uuid or an unknown format, with the same body as everywhere else.

## Erasing an instance on request

`DELETE /api/purge?target=opencloud.example.com` removes every scan this
service holds for one instance, along with the queue entries and the cooldown
key derived from it:

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer $COS_WEB_PURGE_TOKEN" \
  "http://127.0.0.1:8080/api/purge?target=opencloud.example.com"
```

Everything here expires on its own already; this is for the person who wants
it gone now, and for the operator who has to show that it went. The response is
a receipt: what was deleted, a `remaining` count from a **second walk over the
store afterwards**, and an HMAC signature when `COS_WEB_PURGE_SIGNING_KEY` is
set. `webapp.purge.verify()` checks one later, when the data it describes no
longer exists to be compared against.

Two design consequences worth knowing:

- **There is no target index, so a purge walks the keyspace** and reads each
  scan's own metadata. Keeping an index would mean keeping a record of who
  scanned what, which is the thing this service refuses to have. The walk is
  the price, paid by a rare authenticated call and by nothing on the request
  path.
- **It is authorised and off by default.** The call deletes results belonging
  to whoever is reading them, so without `COS_WEB_PURGE_TOKEN` the endpoint
  answers 404 like any other path that does not exist. The realistic workflow
  is a message to the operator, who runs it and returns the receipt.

## Swagger and the OpenAPI schema

Both are **off by default** - they describe endpoints already documented in
prose, and a public deployment has no reason to advertise them.

They are, however, served entirely from this origin: Swagger UI and ReDoc are
rendered with the copies in
[`frontend/static/vendor/`](../frontend/static/vendor/) rather than FastAPI's
own pages, which fetch their JavaScript from jsDelivr. Those default pages
render blank wherever that CDN is unreachable - a network-restricted host, a
browser blocking third-party requests - which is precisely the sort of place
this service runs. The Swagger page is markup of our own for the same reason:
FastAPI's version mounts the UI from an inline `<script>`, and the policy
below refuses to run inline script, so the one call that starts it lives in
`/static/js/docs.js`.

Turn it on for development:

```bash
COS_WEB_ENABLE_DOCS=true \
COS_WEB_REDIS_URL=memory:// \
  uvicorn webapp.app:app --port 8080
```

- Swagger UI: <http://127.0.0.1:8080/docs>
- ReDoc: <http://127.0.0.1:8080/redoc>
- The schema itself: <http://127.0.0.1:8080/openapi.json>
- The workflows: <http://127.0.0.1:8080/arazzo.json>

In Docker, set `COS_WEB_ENABLE_DOCS: "true"` on the `web_app` service in
[`docker/docker-compose.yml`](../docker/docker-compose.yml).

When it is on, the landing page links to all three. Enabling it relaxes the
Content-Security-Policy on `/docs` and `/redoc` and **nowhere else**, and only
by allowing inline styles and a blob worker - both pages need them to render,
and no foreign origin is allowed even there. The landing page, the result page
and the schema keep the strict policy, and a test fails if that ever leaks.
The service also logs `api_docs_enabled` at startup, so a deployment that
turned it on by accident says so.

Prefer not to serve it at all? The schema is static, so write it to a file and
open it in your own viewer:

```bash
COS_WEB_ENABLE_DOCS=true COS_WEB_REDIS_URL=memory:// python -c \
  "import json;from webapp.app import create_app;print(json.dumps(create_app().openapi()))" \
  > openapi.json
```

### The workflows, in Arazzo

The schema says what each endpoint accepts. It cannot say that a scan is
asynchronous, that the uuid from the first call is the only way back to the
second, that a batch answers with two lists, or that a 409 on an export means
*not yet* rather than *no*. Those are the parts a client gets wrong, so they
are written down as [Arazzo 1.0.1](https://spec.openapis.org/arazzo/latest.html)
workflows at `/arazzo.json`: `scanOneInstance`, `scanManyInstances` and
`exportFinishedScan`.

[`arazzo.py`](arazzo.py) builds the document from this application rather than
shipping a static copy, so it names this build's version, and
`tests/test_webapp_arazzo.py` checks every step against the served OpenAPI
paths - a workflow describing an endpoint that moved fails the suite instead
of misleading somebody. Write it to a file the same way as the schema:

```bash
COS_WEB_REDIS_URL=memory:// python -c \
  "import json;from webapp.arazzo import arazzo_document;print(json.dumps(arazzo_document()))" \
  > scan-workflows.arazzo.json
```

## What a request may not ask for

A request chooses **what** to scan, never **how hard**:

| Accepted | Meaning |
|:---------|:--------|
| `target_url` | Required. Hostname or URL of the instance |
| `ignore_hardenings` | Optional. Identifiers to waive, checked against an allow-list; unknown ones are dropped |
| `release_track` | Optional. `rolling`, `production`, `lts` or `auto`; defaults to `auto`, and an unknown value falls back to it |
| `output_format` | Optional. `dashboard`, `json`, `csv`, `sarif` or `pdf` |

`release_track` is the web equivalent of the plugin's `--release-track`. It
decides how long the instance's release is supported and which release it is
told to upgrade to - so it changes how a version is *rated*, never how hard it
is *probed*. The default is `auto`: the release schedule works the track out
from the release the instance reports, which is the honest answer when the
visitor does not know, and the only one that is not wrong for somebody -
assuming `production` calls a current rolling instance out of date, assuming
`rolling` reports an end of life that has not happened.

Anything else is a **422** naming the field. `concurrency`, `threads`,
`workers`, `timeout` and `verify_tls` are not near-misses to be forgiven -
they are the settings that decide how much load this service puts on someone
else's server, and they live in the environment only. The refusal is tested
for each of them, from a form body and a JSON body alike.

The other standing restrictions:

- **Public targets only.** Private, loopback, link-local and cloud metadata
  addresses are refused, hostnames are resolved and every address checked, and
  the target is validated again in the worker so a DNS answer that changed in
  between is caught rather than trusted.
- **One scan per target per cooldown**, and a per-client limit on top.
- **No port scanning.** `COS_WEB_CHECK_DEBUG_PORTS` is off; connecting to
  extra ports on a host a stranger named is not something to do uninvited.
- **Nothing is stored.** Every key has a TTL, Redis persists nothing, and the
  log carries lifecycle markers and uuids - never a target, a client address
  or a result. An operator who needs an audit trail can turn one on with
  `COS_WEB_AUDIT_LOG`; addresses stay fingerprints there too. See
  [What gets logged](../docs/webapp.md#what-gets-logged).

## Configuration

Everything is a `COS_WEB_*` environment variable read once at startup; there
is no configuration file and nothing is reachable from a request. The full
table with defaults is in
[`docs/webapp.md`](../docs/webapp.md#configuration), and the dataclass in
[`settings.py`](settings.py) is the source of truth. The ones worth knowing
before the first deployment:

| Variable | Default | Why it matters |
|:---------|:--------|:---------------|
| `COS_WEB_REDIS_URL` | `redis://127.0.0.1:6379/0` | `memory://` runs without Redis, for a single process |
| `COS_WEB_RESULT_TTL` | `3600` | How long a result lives, and the TTL on every key |
| `COS_WEB_MAX_WORKERS` | `5` | Scans at once. The whole of this service's load on the outside world |
| `COS_WEB_SCAN_CONCURRENCY` | `4` | Probes in flight within one scan |
| `COS_WEB_IP_RATE_LIMIT` / `_WINDOW` | `10` / `60` | The client limit. `0` disables |
| `COS_WEB_TARGET_COOLDOWN` | `300` | Seconds before the same instance may be scanned again |
| `COS_WEB_MAX_BATCH_TARGETS` | `10` | Targets one batch may carry; each still spends a scan from every limit |
| `COS_WEB_TRUST_FORWARDED_FOR` | `false` | Only behind a proxy that **overwrites** the header, or the limit is decorative |
| `COS_WEB_ALLOW_PRIVATE_TARGETS` | `false` | On-premise deployments scanning their own network |
| `COS_WEB_ENABLE_DOCS` | `false` | Swagger UI, ReDoc and the schema |
| `COS_WEB_AUDIT_LOG` | `false` | An audit record per request, rejection and triggered limit, with fingerprints rather than addresses |
| `COS_WEB_PURGE_TOKEN` | *(none)* | Enables `DELETE /api/purge`. Unset means the endpoint is not there at all |
| `COS_WEB_PURGE_SIGNING_KEY` | *(none)* | Signs the proof of deletion, so a receipt can be checked long after the data went |
| `COS_WEB_ENCRYPT_RESULTS` | `false` | AES-256-GCM on the stored result. The web process and the worker need the same `COS_WEB_ENCRYPTION_KEY_<n>`, and one asked to encrypt without a key refuses to start |
| `COS_WEB_FRONTEND_DIR` | *next to `webapp/`* | Serve a different `templates/` and `static/` |

Adding a setting means: a field on `WebSettings` with a docstring saying why
it is not client-configurable, a line in `from_env`, a row in the table in
`docs/webapp.md`, an entry in `docker/docker-compose.yml`, and a row here if
it is one somebody meets on day one.

## Customising the frontend

The rules are short, and they are the product:

- **No third-party anything.** No CDN, no font service, no analytics, no
  tracking pixel. Everything the browser loads comes from `/static`, and a
  test walks the rendered HTML asserting exactly that.
- **No inline styles or scripts.** The policy has no `unsafe-inline`, so an
  inline `style=` or `<script>` does not fail the test - it fails in the
  browser.
- **The form works with JavaScript blocked.** `app.js` is decoration.
  `scan.js` is the only script that is load-bearing, and only for live
  progress; the page it polls renders the same result on a reload.
- **Nothing generic.** The CSS is a small design-token system at the top of
  `app.css`; the SVGs were drawn for this project. No stock art, no framework.
- **Two schemes, one day.** Light is a sunrise over breakfast - warm paper, a
  low sun, a single orange to follow. Dark is the night before it: a deep sky,
  a moon and a faint field of stars. Both live entirely in the tokens at the
  top of `app.css` and its `prefers-color-scheme: dark` block, so no rule
  further down names a colour, and every ink-on-tint pair clears WCAG AA in
  both. The three SVGs carry the same pair internally: they are loaded with
  `<img>`, so they are documents of their own that the page's stylesheet
  cannot reach and the page's CSP does not govern.

To run with your own branding, point `COS_WEB_FRONTEND_DIR` at a copy of
`frontend/`:

```bash
cp -r frontend /srv/my-frontend
COS_WEB_FRONTEND_DIR=/srv/my-frontend uvicorn webapp.app:app
```

The template contract is small: `base.html` receives `version`, `project_url`
and `result_ttl_minutes` on every page; `index.html` also gets `waivers`,
`tracks`, `release_track`, `error`, `error_self_host` and `target_url`;
`scan.html` gets the record and its `summary`. The content pages -
`/how-it-works`, `/api`, `/privacy` and `/about` - need nothing beyond the
base variables and `limits`. Keep the trademark notice and the "run it yourself" pointer -
they are the reason a rate limit reads as a nudge rather than a door.

## Tests

```bash
uv run pytest tests/test_webapp_api.py        # the API and its refusals
uv run pytest tests/test_webapp_worker.py     # the worker and the queue
uv run pytest tests/test_webapp_packaging.py  # what ships, and what must not
```

They need the `web` extra and run without a Redis server: the fixtures in
`tests/webapp_support.py` give each test an empty `memory://` backend with
real TTL semantics and a clock they can move, plus an offline resolver,
because documentation addresses do not resolve.

Anything asserting a security property - isolation, the SSRF guard, the rate
limits, expiry, the packaging exclusion - belongs there, and must keep failing
if the protection is removed.

## Trademarks and affiliation

This is an independent community project. It is not affiliated with OpenCloud
GmbH and is neither recommended nor supported by the company. "OpenCloud", the
OpenCloud logo and all associated trademarks are the property of their
respective owners and are used here solely to indicate which software this
tool checks.
