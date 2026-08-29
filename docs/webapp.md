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

The HTML interface is available in English, German, Spanish and French. It
uses the browser's weighted language preference on a first visit and provides
an accessible switcher on every page; a chosen language is remembered in an
`HttpOnly`, `SameSite=Lax` cookie. Generated operator-guide bodies remain
English and are labelled as such, while their navigation and page chrome are
translated. JSON APIs, agent contracts, exports and scan evidence are never
translated.

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

The service is three containers - the pages, the worker that runs the scans,
and the Redis between them - and the shortest honest way to get all three is
to let the setup wizard write them. It is one Python file, uses the standard
library alone, and needs no checkout:

```bash
mkdir opencloud-scanner && cd opencloud-scanner

curl -fsSLO https://raw.githubusercontent.com/sowoi/check-opencloud-security/main/docker/setup-wizard.py
chmod +x setup-wizard.py
./setup-wizard.py

docker compose up -d
# http://127.0.0.1:8811
```

It asks one question at a time and writes a commented compose file with the
non-secret answers inline, plus a `.env` created owner-readable only holding
every credential that file refers to as `${NAME}` - the Redis password, the
erasure token, the signing key, the audit salt and the encryption key.
[A deployment of your own](#a-deployment-of-your-own) has the flags.

### Or the compose files this project ships

Two shapes, both ready to `up`. The published image:

```bash
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security/docker

printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" > .env
chmod 600 .env

docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8811
```

Or the same stack built from the checkout, with `docker compose up --build -d`
and no `-f`.

Three settings decide whether that stack is fit to be reached by anybody else,
and all three live in `.env` beside the compose file:

| Setting | Why it matters |
|:--------|:---------------|
| `COS_WEB_PUBLIC_BASE_URL` | Canonical URLs, the sitemap and the discovery document are built from it rather than from an incoming `Host` header. It defaults to `http://localhost:8811` so a first `up` works; anything a stranger reaches must set it |
| `COS_REDIS_PASSWORD` | Redis holds every live scan and every result still inside its TTL. Unset, it asks for nothing. See [Redis](redis.md) |
| `COS_WEB_TRUST_FORWARDED_FOR` | `true` only behind a proxy that **overwrites** `X-Forwarded-For`, otherwise every client can forge its own rate-limit identity |

The published image is on Docker Hub as **`okxo/opencloud-scanner`**, so a
deployment does not have to build one. `latest` and `MAJOR.MINOR.PATCH` follow
the released version, `MAJOR.MINOR` follows the line, and `edge` is the current
`main`. It carries `linux/amd64` and `linux/arm64`, and the same image runs
both the web service and the worker - they differ only in the command, which is
why the code that describes a result and the code that produces it cannot drift
apart between deployments.

Running one container by hand needs a Redis the worker shares and the public
address, since neither has a useful default outside a compose file:

```bash
docker run --rm -p 8811:8811 \
    -e COS_WEB_REDIS_URL="redis://:PASSWORD@redis:6379/0" \
    -e COS_WEB_PUBLIC_BASE_URL=http://127.0.0.1:8811 \
    okxo/opencloud-scanner:latest
```

[`docker/README.md`](../docker/README.md) covers the stacks in full, including
the Authentik one, and the Docker Hub description carries a plain `docker run`
recipe for all three containers.

### Without containers

From a checkout, with three terminals or three `&`:

```bash
pip install ".[web,mcp]"    # the mcp extra is optional; it serves /mcp
redis-server &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 python -m webapp.tasks &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 \
    uvicorn webapp.app:app --host 127.0.0.1 --port 8811
```

Building the release archive yourself:

```bash
python scripts/build_web_bundle.py
# dist/check_opencloud_security_web.tar.gz  (+ .sha256)
```

### A deployment of your own

The two compose files are the two usual shapes. For anything else - a
different port, an on-premise instance the SSRF guard would otherwise refuse,
encryption at rest, a sign-in on `/mcp` - the wizard is the answer rather than
editing one of them into place, either from a checkout or downloaded on its
own:

```bash
cd docker
./setup-wizard.py --output-dir ~/opencloud-scanner
```

It explains each setting, shows an example answer, and writes a commented
compose file with the non-secret answers inline plus a `.env`, owner-readable
only, holding the credentials that file refers to as `${NAME}`. Answer
`generate` and it creates the erasure token, the signing key, the audit salt
and the encryption key for you. `--preset private` starts from what an estate
scanning its own instances wants, and `--non-interactive` takes every default
for an unattended install.

`--sign-in` requires a token on `/mcp` and asks for the issuer, the audience
and the keys of the provider you already run. `--with-authentik` provisions
one instead - Authentik and its database join the generated stack, those three
values are derived from the answers, and the blueprint is written beside the
compose file that mounts it. The two are independent: provisioning a provider
does not close the endpoint, so the ordinary way in is to bring Authentik up
with `/mcp` still open, get a token, and turn the guard on once it works.
Neither is a default, and nothing of Authentik is written into a deployment
that did not ask for it. When it is asked for, so are its mail settings
(`--smtp-host`, `--smtp-from`, `--smtp-security` and the rest), since an
identity provider that cannot send a password recovery locks out the one
account it starts with; the password comes from `AUTHENTIK_EMAIL_PASSWORD` in
the environment rather than from a flag.
[`docker/README.md`](../docker/README.md#the-setup-wizard) has the flags. It
is unrelated to `check-opencloud-security --configure`, which sets up a
monitoring check rather than a container deployment.

## What a visitor can ask for

Four things, and the list is closed:

| Field | Meaning |
|:------|:--------|
| `target_url` | The main address of the instance: hostname, optional `http://` or `https://`, and optional port. No path, query, fragment or credentials. Required |
| `ignore_hardenings` | Checks to waive, from a fixed allow-list. Optional, repeatable |
| `release_track` | `rolling`, `production`, `lts` or `auto`. Optional, defaults to `auto` |
| `output_format` | `dashboard`, `json`, `csv`, `sarif` or `pdf`. Optional, affects presentation only |

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

The target is an address, never a request template. A path such as
`/apps/files`, a query string, a fragment, embedded credentials, whitespace
or request-control characters are refused rather than silently discarded.
The scanner chooses the OpenCloud paths it knows itself; nothing appended by
a visitor can become a path, parameter or payload in an outgoing request.

Waivers are checked against an allow-list built from the hardening catalogue,
so `*` and `debugPort:*` are dropped rather than honoured. A wildcard waiver
on a public service would be a blindfold with a nice name. Flags OpenCloud
hardcodes are not offered either: waiving a finding nobody can fix would imply
somebody could.

## Configuration

Every setting is an environment variable, read once at startup.

| Variable | Default | What it does |
|:---------|:--------|:-------------|
| `COS_WEB_REDIS_URL` | `redis://127.0.0.1:6379/0` | Where ephemeral state lives. `memory://` runs without Redis, for a single-process evaluation. Include the password when Redis requires one: `redis://:PASSWORD@redis:6379/0` |
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
| `COS_WEB_MAX_BATCH_TARGETS` | `10` | Targets one `POST /api/scans/batch` may carry. Each still counts against every limit |
| `COS_WEB_TRUST_FORWARDED_FOR` | `false` | Read the client address from `X-Forwarded-For` |
| `COS_WEB_PUBLIC_BASE_URL` | *(required)* | The stable origin this service is reached at, used for canonical links, `sitemap.xml`, and machine discovery. An unset value refuses startup so an incoming `Host` header cannot publish attacker-controlled URLs |
| `COS_WEB_INDEX_META_TAG` | *(empty)* | Up to 10 optional `name=content` metadata pairs on the landing page, separated by `;`. Names and content are escaped separately; raw HTML, duplicate or reserved names, and prohibited platform metadata are refused |
| `COS_WEB_ALLOW_INDEXING` | `true` | Let search engines index the landing page and its explanation pages. Result pages are never indexable whatever this says |
| `COS_WEB_RELEASES_MODE` | `off` | Update check against the OpenCloud release feed: `off`, `auto`, `feed`, `bundled` |
| `COS_WEB_RELEASES_TOKEN` | *(none)* | GitHub token raising the feed's rate limit |
| `COS_WEB_SCHEDULE_REFRESH` | `true` | Re-read the OpenCloud release lifecycle page once a day and rate scans against what it says. One request a day for the whole deployment, not one per visitor |
| `COS_WEB_SCHEDULE_REFRESH_URL` | *(the OpenCloud lifecycle page)* | Where that schedule is read from. Operator configuration, so it may point at a mirror; never a request field |
| `COS_WEB_SCHEDULE_REFRESH_HOUR` | `4` | The hour (UTC) of the daily read. Worth varying between deployments so they do not all arrive at once |
| `COS_WEB_ADVISORY_REFRESH` | `true` | Ask the advisory feed once a day which vulnerabilities affect OpenCloud and rate scans against the answer. A refresh only ever adds an advisory, and never believes one with no version bounds |
| `COS_WEB_ADVISORY_REFRESH_URL` | `https://api.osv.dev/v1/query` | Where the advisories are read from. Operator configuration, so it may point at a mirror; never a request field |
| `COS_WEB_FRONTEND_DIR` | *next to `webapp/`* | Where templates and static assets live |
| `COS_WEB_ENABLE_DOCS` | `false` | Serve the browsable `/docs` and `/redoc` pages. The machine-readable documents are public whatever this says |
| `COS_WEB_ENABLE_MCP` | `true` | Serve the MCP endpoint at `/mcp` and register browser WebMCP tools. Ignored when the optional `mcp` extra is not installed |
| `COS_WEB_MCP_ALLOWED_HOSTS` | *(empty)* | `Host` values the MCP endpoint accepts, separated by `;`. Empty turns the DNS-rebinding check off, which is right when a proxy already fixes the host |
| `COS_WEB_MCP_MAX_CONCURRENT_WAITS` | `8` | How many MCP tool calls may sit waiting for a scan at once. Reaching the ceiling refuses nothing: the scan is submitted and the uuid comes back to be polled |
| `COS_WEB_MCP_AUTH_ENABLED` | `false` | Require a bearer token on `/mcp`. Off, because the service is meant to answer anybody; a deployment that wants the opposite turns it on and names an issuer. See [a sign-in on the MCP endpoint](authentik.md) |
| `COS_WEB_MCP_AUTH_ISSUER` | *(empty)* | The OIDC issuer whose tokens are accepted, exactly as its discovery document spells it. A trailing slash is accepted either way |
| `COS_WEB_MCP_AUTH_AUDIENCE` | *(empty)* | What a token's `aud` claim must contain, normally the client ID agents authenticate as. **Required** when the sign-in is on: empty refuses to start, because a token minted for another application behind the same provider would otherwise open this one |
| `COS_WEB_MCP_AUTH_JWKS_URL` | *(derived)* | Where the signing keys are published. Defaults to `<issuer>/jwks/`, which is what a provider following the discovery specification answers with |
| `COS_WEB_MCP_AUTH_RESOURCE_URL` | *(derived)* | The URL this endpoint claims as its protected resource. Defaults to `<COS_WEB_PUBLIC_BASE_URL>/mcp`; a token's audience is checked against it |
| `COS_WEB_MCP_AUTH_SCOPES` | *(empty)* | Scopes a token must carry, separated by `;`. Empty means any valid token from the issuer is enough |
| `COS_WEB_AUDIT_LOG` | `false` | Write an audit record for every scan request, rejection and triggered limit |
| `COS_WEB_AUDIT_LOG_TARGETS` | `false` | Record the target hostname in the clear instead of as a fingerprint. On-premise deployments only |
| `COS_WEB_AUDIT_SALT` | *(random per process)* | Salt for the audit fingerprints. Setting one lets records correlate across a restart; rotating it ends that |
| `COS_WEB_PURGE_TOKEN` | *(none)* | Enables `DELETE /api/purge` and is the secret it requires. Unset means the endpoint answers 404 like any other path that is not there |
| `COS_WEB_PURGE_SIGNING_KEY` | *(none)* | Signs the proof of deletion. Unset still erases, but the receipt cannot be verified afterwards |
| `COS_WEB_EXPORT_SIGNING_KEY` | *(none)* | Adds an `X-COS-Signature` HMAC-SHA256 header to every JSON, CSV, SARIF and PDF export |
| `COS_WEB_ENCRYPT_RESULTS` | `false` | Encrypt the stored result document with AES-256-GCM. Requires a key; a process asked to encrypt without one refuses to start |
| `COS_WEB_ENCRYPTION_KEY_<n>` | *(none)* | A 32-byte key as 64 hex characters. The highest `<n>` encrypts, lower ones still decrypt, which is how a key is rotated |

`COS_WEB_RELEASES_MODE` is `off` by default on purpose: a public deployment
that queries the release feed once per visitor gets rate limited, and then
every visitor's update check fails at once. The release schedule still decides
end of life without it.

`COS_WEB_SCHEDULE_REFRESH` is the opposite case, and is on by default. The
schedule that ships in the image is written by CI, so a service that has been
up for six weeks rates instances against a six-week-old picture of the world:
it calls last week's release "ahead of the schedule" and a line that expired
since the build "still supported". The worker therefore re-reads the published
lifecycle page once a day - at startup as well, so a fresh deployment does not
wait for the small hours - and keeps the result in Redis, where the scan jobs
pick it up.

A refresh can only ever add knowledge. A document that has lost a line the
bundled schedule knows about is refused, because a missing line turns an
end-of-life instance into an unknown one; an unreachable page, a redesigned
page or a truncated table all leave the previous schedule exactly as it was;
and a newer bundled file after a redeployment wins over whatever is left in
Redis. Nothing is written to the repository - `README.md` and the bundled
JSON stay CI's business. Turn the refresh off for a deployment with no
outbound access, which then behaves exactly as it did before. `/healthz`
reports the schedule's date and the time of the last successful read, and
[ADR 0016](../adr/0016-the-release-schedule-refreshes-itself.md) holds the
reasoning.

`COS_WEB_ADVISORY_REFRESH` does the same for the other half of what a rating
is made of, and it matters more. The advisory database decides whether an
instance is *reported as vulnerable*, so a database that has not heard of last
month's advisory does not merely grade an instance generously - it tells the
visitor a vulnerable instance is fine, and they have no way to tell that
answer apart from a real one. The worker therefore asks the feed once a day,
at startup as well, and the scan jobs rate against what it last accepted.

The rules are the mirror image of the schedule's, because this can fail in
both directions. A refresh **only ever adds**: the answer is merged into the
database the deployment already has, so a feed returning an empty list changes
nothing and a hand-written entry survives. Nothing **unbounded** is ever
believed - an advisory that names no versions would match every release there
has ever been, and public feeds do publish that shape - and an answer with
absurdly many advisories in it is refused whole. Any failure leaves the
database exactly as it was. Nothing is written to disk; the bundled JSON stays
CI's business, refreshed by `.github/workflows/vulnerability-db.yml`. Turn it
off for a deployment with no outbound access, which then rates against the
bundled file exactly as the plugin does on a monitoring host. `/healthz`
reports how many advisories it would rate against and when it last asked -
counts and dates, never a finding - and
[ADR 0017](../adr/0017-the-advisory-database-refreshes-itself.md) holds the
reasoning.

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
- the submission may include a plain base path for an instance installed in a
  subfolder, but not a query string, fragment, credentials, path parameters,
  escapes or traversal segments. Redirects sent by the instance may contain
  ordinary paths, but they are revalidated independently before being followed;
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

**What a rejection tells a stranger.** The target cooldown is shared, so its
429 says an instance was scanned recently - by anyone. That is inherent to a
per-target cooldown rather than a leak in the implementation, and it is
bounded by what it costs: every probe, including one inside a batch, spends a
scan from the prober's own client window, and a target that answers "not
recently" has just been claimed by them. A deployment that does not want the
question answerable at all sets `COS_WEB_TARGET_COOLDOWN=0` and relies on the
client limit alone. Nothing anywhere says *who* scanned it.

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

### The optional audit trail

An operator running this for other people eventually has to answer questions
the lines above cannot: was one network submitting scans all night, did the
limits hold, is somebody probing the endpoint with fields it does not accept.
`COS_WEB_AUDIT_LOG=true` turns on a second, separate log for exactly that -
the `check_opencloud.web.audit` logger, one JSON object per line, so it can be
routed and retained on its own:

```json
{"client": "9f2c1b7d4e6a0c58", "event": "scan_requested", "outputFormat": "dashboard", "releaseTrack": "production", "target": "1a4b9e0f7c23d865", "timestamp": "2026-08-19T10:14:02+00:00", "uuid": "0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa", "waivers": 0}
{"client": "9f2c1b7d4e6a0c58", "event": "rate_limited", "retryAfter": 42, "scope": "rate_limit_client", "timestamp": "2026-08-19T10:14:44+00:00"}
{"client": "3c80d5f21ab94e77", "event": "submission_rejected", "fields": ["workers"], "reason": "unsupported_fields", "status": 422, "timestamp": "2026-08-19T10:15:09+00:00"}
```

Three events: `scan_requested` for an accepted submission, `rate_limited` for
a client limit or target cooldown that actually triggered, and
`submission_rejected` for one that never became a scan - `unsupported_fields`,
`target_rejected`.

The point of the design is what it still does not write down:

- **A client address is always a fingerprint**, a truncated HMAC under the
  audit salt, and no setting changes that. Two requests from the same network
  share a fingerprint, which is what an audit needs; nothing maps one back.
- **The target is a fingerprint too**, unless `COS_WEB_AUDIT_LOG_TARGETS=true`
  says the deployment is scanning its own estate and wants the hostname.
- **The salt is random per process** unless `COS_WEB_AUDIT_SALT` is set.
  Correlating across a restart is a deliberate choice, and rotating the salt
  undoes it. **Treat a salt you set as a secret**, with the same care as
  `COS_WEB_PURGE_TOKEN`: a fingerprint is only a pseudonym while the salt is
  unknown, and anybody who learns it can re-derive the client addresses in a
  log by hashing the address space. A random per-process salt has no such
  property, which is why it is the default.
- **A submitted field name is recorded, not obeyed**: shortened, stripped of
  control characters and JSON-escaped, so a newline in a request body cannot
  forge a second record.

Leaving it off changes nothing: the ordinary lifecycle log is exactly as
above.

## Putting it behind a reverse proxy

Worked configuration for nginx, Apache httpd, Caddy, Traefik and HAProxy -
including the streaming the MCP endpoint needs and the paths a proxy must not
rewrite - is in [Reverse proxies](reverse-proxy.md). The short version:

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
curl -sS -X POST http://127.0.0.1:8811/api/scans \
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

### `POST /api/scans/batch`

For a caller with an estate to check rather than one instance:

```bash
curl -sS -X POST http://127.0.0.1:8811/api/scans/batch \
  -H 'Content-Type: application/json' \
  -d '{"targets": ["https://one.example.com", "https://two.example.com"]}'
```

```json
{
  "accepted": [
    {"uuid": "0f4a1f22-...", "target": "https://one.example.com",
     "state": "queued", "url": "/scan/0f4a1f22-..."}
  ],
  "rejected": [
    {"target": "https://two.example.com", "status": 429,
     "detail": "That instance was scanned very recently...", "retryAfter": 284}
  ],
  "counts": {"submitted": 2, "accepted": 1, "rejected": 1}
}
```

**A batch is a convenience, never a discount.** Every target is put through
exactly the pipeline a single submission goes through, in the order it was
written: it counts against the client rate limit, it claims its own target
cooldown, and it is validated by the same SSRF guard. Ten targets spend ten
scans from the window, which is why the answer is two lists rather than one
status - some can start while others wait.

The same four fields are accepted, with `targets` in place of `target_url`,
and anything else is a **422** naming it. `COS_WEB_MAX_BATCH_TARGETS` caps the
list; a longer one is refused as a whole, before anything is queued, so no
target pays a cooldown for a batch that never ran.

**202** when at least one target started. When nothing started, the status is
the reason the first target was refused - **429** with `Retry-After` and the
self-hosting hint if it was a limit, **400** or **422** otherwise.

### `GET /api/scans/{uuid}/export/{format}`

A finished scan as a file: `json`, `csv`, `sarif` or `pdf`.

```bash
curl -sS -OJ http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
```

All four carry the remediation plan - the ordered fix list with the grade each
step reaches - as summary and step rows in the CSV,
`runs[0].properties.remediation` in the SARIF, a "What gets you to A+" section
in the PDF and `remediationPlan` in the JSON.

They carry the transport-security detail in the same places: the header block
in the CSV, `runs[0].properties.tls` in the SARIF, a "Transport security"
section in the PDF and the `tls` block in the JSON - protocol, cipher,
certificate validity and remaining days, chain completeness and OCSP stapling.
A measurement that could not be taken is `null`, meaning "not determined"
rather than "fine".

All four are renderings of the same finished result, produced on request and
gone when the scan expires. The PDF is written by this service rather than by
a reporting library, for the same reason the frontend loads nothing from a
CDN. The finished `GET /api/scans/{uuid}` response advertises the four URLs
under `exports`, and the result page offers them as download buttons.

**200** with a `Content-Disposition` naming the uuid, **409** while the scan
has not finished - it exists, so 404 would send a caller into a retry loop
against the wrong endpoint - and **404** for an unknown uuid or an unknown
format.

### `DELETE /api/purge`

Erasure on request - the operator's side of a GDPR Article 17 message - plus a
receipt to put in the file afterwards.

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer $COS_WEB_PURGE_TOKEN" \
  "http://127.0.0.1:8811/api/purge?target=opencloud.example.com"
```

```json
{
  "receiptId": "8f14e45f-...",
  "issuedAt": "2025-01-30T11:04:07+00:00",
  "target": "opencloud.example.com",
  "targetFingerprint": "6c1f...",
  "deleted": {"scans": 2, "keys": 5, "queueEntries": 1, "rateLimitKeys": 1},
  "remaining": 0,
  "complete": true,
  "statement": "All scan records held for this target were deleted ...",
  "notes": ["..."],
  "signature": {"algorithm": "HMAC-SHA256", "value": "b91c..."}
}
```

It deletes every `scan:{uuid}:*` namespace whose own metadata names that
hostname, the target's entries in the queue, and the cooldown key derived from
it. `target` accepts a bare hostname or a full URL, in any case, with or
without a port.

`targetFingerprint` is present only when `COS_WEB_PURGE_SIGNING_KEY` is set,
and is `null` otherwise: an unkeyed hash of a hostname is not a pseudonym,
because the space of hostnames is small enough to enumerate.

**The receipt is the compliance artefact**, because by the time it is written
the data it describes is gone. `deleted` counts what was removed, and
`remaining` is a **second walk over the store after the deletion** - the only
honest evidence available, and `complete` is simply `remaining == 0`. `notes`
names what the service cannot reach: a result somebody already downloaded, and
the audit trail if one is being kept. Verify a receipt months later with

```python
from webapp.purge import verify
verify(receipt, key)      # the value of COS_WEB_PURGE_SIGNING_KEY
```

**It is authorised, and off until it is configured.** This is the one call that
walks the keyspace and the one that destroys results belonging to whoever is
reading them, so an unauthenticated version would be a denial-of-service tool
with a friendly name. A data subject writes to the operator; the operator - the
controller - runs the purge and passes the receipt back. **200** with the
receipt, **401** for a wrong secret, **422** for a target that is not a
hostname, and **404** whenever `COS_WEB_PURGE_TOKEN` is unset.

An instance with nothing stored answers 200 with zero counts, which is a proof
in its own right: no data was held.

### `GET /llms.txt`, `GET /openapi.json`, `GET /arazzo.json`, `GET /.well-known/ai.json`

**Always public, and never behind a switch.** A description nobody can fetch
describes nothing, and an agent that must be told to turn a document on has
already failed to discover it. `COS_WEB_ENABLE_DOCS` now governs only the
browsable `/docs` and `/redoc` pages.

The [OpenAPI](https://spec.openapis.org/oas/latest.html) document says what
each endpoint accepts and returns, down to the shape of every response; the
[Arazzo](https://spec.openapis.org/arazzo/latest.html) document beside it says
how those operations are used together - submit and poll until `done`, walk a
batch's accepted uuids, wait out a 409 before downloading a file, and erase an
instance against a receipt. Both are built from the same application, and a
test fails if a workflow describes an operation that no longer exists.

`/.well-known/ai.json` is the entry point: name, description, the two
specification URLs, the MCP endpoint, the usage limits an agent should respect
and the self-hosting link. It is an **application-level convention**, not a
registered standard - it exists so that an agent starting from nothing but the
origin can find the rest in one request.

`/llms.txt` is the shorter Markdown map. It lists the public contracts, main
operations, WebMCP tools, and the rules around asynchronous scans and UUIDs.
It contains no scan data and no listing mechanism.

### `POST /mcp`

The [Model Context Protocol](https://modelcontextprotocol.io) endpoint, over
streamable HTTP, stateless, with JSON responses. It is the agent-facing
execution layer, not a second implementation: every tool calls this
application's own HTTP API in process, so an agent meets exactly the rate
limits, the SSRF guard and the purge authorisation a browser meets.

Six tools, one per user-level task rather than one per endpoint:
`scan_instance`, `scan_instances`, `get_scan_result`, `plan_remediation`,
`export_scan` and `erase_instance_data`. Six prompts name the tasks people ask
for - `audit_instance`, `audit_estate`, `explain_scan_result`,
`triage_findings`, `review_transport_security` and `check_release_support` -
so a client can offer "audit this instance and write a remediation plan" as
one thing to pick. Five resources are published under `spec://` URIs: the
OpenAPI, Arazzo and discovery documents, and two that are a knowledge base
rather than a contract - `catalogue`, every hardening flag and extra check
the scanner runs explained, with the OpenCloud setting behind it, the fix and
the official documentation; and `advisories`, the whole advisory database a
scan is rated against. Both are built from the same functions the
`/catalogue` page renders from, so an agent can explain a finding, or see
what the scanner would catch, without ever submitting a target - and without
a resource ever disagreeing with the page about what a check means. The
polling, retry and error semantics come from `webapp/workflows.py`, which is
also what the Arazzo document is generated from, so the two cannot drift
apart.

`erase_instance_data` is marked destructive and needs the same
`Authorization: Bearer` credential the HTTP endpoint does. The credential is
read from the agent's request headers and never from a tool argument, so it is
never a value the model has seen. Where the endpoint itself requires a sign-in
it moves to `X-Purge-Authorization`, because `Authorization` then carries the
agent's identity token and reading one as the other is a confusion worth
refusing.

**The endpoint is open unless an operator says otherwise.** Set
`COS_WEB_MCP_AUTH_ENABLED` and an issuer and it becomes an OAuth 2.0 resource
server: a token is verified offline against the provider's published keys -
signature, issuer, audience, expiry, scopes - and a request without one gets a
401 whose `WWW-Authenticate` names
`/.well-known/oauth-protected-resource/mcp`, the public RFC 9728 document
saying which provider to ask. `/.well-known/ai.json` says the same before the
first request, under `mcp.authentication`.

This service issues nothing, stores nothing and holds no account: it checks a
token somebody else signed. And it buys an agent nothing else - the client
rate limit, the target cooldown, the SSRF guard and the queue are identical
signed in. A misconfiguration that would leave the endpoint open while the
operator believes it is protected refuses to start. [Authentik in front of
the MCP endpoint](authentik.md) is the worked setup.

Configuring a client against it - Claude Code, Claude Desktop, GitHub Copilot
in VS Code and the CLI, Cursor, Zed, Windsurf - is in [Using the scanner from
an AI agent](mcp.md), which also covers turning the endpoint off.

### `GET /scan/{uuid}`, `GET /`, `GET /healthz`

The result page, the landing page, and a Redis-backed health probe that says
nothing about any scan. The explanations the landing page used to carry sit on
their own pages - `GET /how-it-works`, `GET /grades`, `GET /documentation`,
`GET /search`, `GET /api`, `GET /ai`, `GET /cli`, `GET /privacy` and
`GET /about` - which
are HTML only and stay out of the OpenAPI schema. `/grades` explains the
plugin's real 0-5 map and its remediation ceilings; `/documentation` is the
local CLI quick reference and guide index. `GET /cli` is the one that points
away from this service: the
Docker one-liner that runs the same scan on the visitor's own machine, linked
from the primary navigation and documented in
[Scanning from the command line, in one line](docker-oneliner.md). `GET /healthz` returns 200 only after the configured
backend answers `PING`, its queue depth can be read, and a worker's short-lived
heartbeat is present. Its success body carries only the aggregate `queueDepth`
and `worker: "ok"`; it returns a detail-free 503 while any dependency is
unavailable.

Every `/documentation/{slug}` below the index is generated at build time from
the Markdown operator guides. The checked-in HTML is verified in CI and ships
inside `frontend/`; the running service neither parses Markdown nor needs the
source files. ADR 0018 records the boundary.

`/search` filters a checked-in, same-origin JSON index in the browser. Its
manifest names public templates explicitly and cannot see Redis, the API,
result pages, exports, UUIDs or submitted addresses. The release workflow
rebuilds that file when a new version is published; ordinary CI deliberately
does not, so one deployed release has one immutable search index. ADR 0019
records the boundary.

When `COS_WEB_ENABLE_MCP` is on, the landing and result pages also expose
their existing actions to supporting browsers through the
[WebMCP draft](https://webmachinelearning.github.io/webmcp/). The landing
page registers `scan_opencloud_security`; a result page registers
`get_scan_result` and `export_scan_report` for the displayed UUID. Their
schemas are rendered from the same catalogues as the page controls. Execution
uses the public API with `Accept: application/json`, so WebMCP does not bypass
the SSRF guard, rate limits, cooldown, queue, or capability checks.

`POST /` and `GET /scan/{uuid}` negotiate JSON for browser-side tools and
other clients. `Accept: application/json` requests a structured response, and
`output_format=json` does the same. HTML remains the default for ordinary
browser navigation.

The optional `COS_WEB_INDEX_META_TAG=name=content;name=content` setting adds
up to ten `<meta name="..." content="...">` elements to the landing page.
Docker Compose passes it from the deployment environment. The application
parses and escapes every pair instead of accepting raw HTML, and refuses
duplicate names, names already owned by the page, or prohibited platform
metadata. A literal semicolon is not supported in a value.

### `GET /robots.txt`, `GET /agents.txt`, `GET /sitemap.xml`

All three are generated, never files on disk. The sitemap lists the landing
page, the nine explanation/index pages and every generated CLI document, and
takes each `lastmod` from the template that renders it, so it cannot drift
from the pages that actually exist. None of them ever mentions a result: the
uuid is the whole of the authorisation, and a listing is exactly what this
service does not have. `robots.txt` disallows `/scan/`, `/api/`, the schema
and the health probe, and points at the sitemap.

`agents.txt` follows the [agents-txt.com](https://agents-txt.com) convention
instead: capability blocks of `Key: value` directives rather than
`robots.txt`'s allow-list, so a parser built against that convention reads
this deployment's tools directly. It declares `MCP: <url>` and
`WebMCP: <url>` when this deployment serves them, `Authorization: oauth2` and
`Identity: required` only when the MCP endpoint itself asks for a bearer
token, and nothing for `Protocols`/`Payments`/`A2A`/`Skills`/`UCP`, since none
of those apply here. Like `/.well-known/ai.json`, it is an informal
convention rather than a registered standard, and the OpenAPI, Arazzo and MCP
contracts remain authoritative over anything it says.

`GET /agents.json` is the structured sibling the convention recommends
alongside the plain-text file - the same document `/.well-known/ai.json`
serves, published again under the name `agents.txt` points at.

`COS_WEB_PUBLIC_BASE_URL` decides the origin in all three, together with the
canonical link on every page. Behind a proxy the service only sees its own
internal address, and without that setting it would publish URLs nobody
outside can reach.

`COS_WEB_ALLOW_INDEXING=false` turns the lot off: `robots.txt` becomes a flat
refusal, `agents.txt` becomes the convention's own minimal file with no
capability declared, `sitemap.xml` answers 404 and every page carries
`noindex`. A result page carries `noindex` and an `X-Robots-Tag` either way.

## Layout

```text
webapp/                 the service
├── app.py              routes, security headers, request validation
├── settings.py         every COS_WEB_* variable
├── ssrf.py             the target guard
├── ratelimit.py        the two limits
├── audit.py            the optional audit trail, pseudonymised
├── store.py            the per-scan Redis namespace
├── queue.py            handing a scan to the worker pool
├── tasks.py            the ARQ worker
├── runner.py           the seam where a request becomes ScannerSettings
├── redis_backend.py    Redis, and the in-process stand-in for tests
├── reports.py          the CSV, SARIF and PDF exports
├── arazzo.py           the API described as executable workflows
├── documentation.py    the manifest for the generated browser documentation
├── purge.py            erasure on request, and the signed receipt for it
├── seo.py              the public page list, robots.txt, agents.txt and sitemap.xml
└── catalog.py          the waiver allow-list and the dashboard grouping

frontend/
├── static/{css,js,img} vanilla CSS, small scripts, hand-drawn SVG
└── templates/          base, index, scan, 404, and the content pages

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
