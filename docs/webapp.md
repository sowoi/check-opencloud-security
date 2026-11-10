# The public scan service

The web application runs the built-in scanner and presents its findings with a grade
from **A+** to **F**. Results remain available in Redis for one hour by default. The web
layer presents the scanner’s result without defining a separate rating.

Try the public service at [scan.okxo.de](https://scan.okxo.de) for a one-off scan. The
instructions below cover hosting your own service, including network access, retention
and usage limits.

The PyPI package contains only the plugin and scanner library. The web
application is distributed separately as the GitHub release asset
`check_opencloud_security_web.tar.gz`, or you can build it from a checkout.

| | |
|:--|:--|
| **Runs** | FastAPI + an ARQ worker + Redis |
| **Stores** | Nothing on disk. Redis only, every key with a TTL |
| **Needs** | No database, no account, no API key |
| **Concurrency** | Fixed by the operator, never by a request |

The interface supports English, German, French and Spanish. It initially follows the
browser’s language preference; a choice made with the language switcher is remembered in
an `HttpOnly`, `SameSite=Lax` cookie. Guide bodies are available in all four
languages. API contracts, exports and measured evidence retain their original technical
values.

## Contents

- [Starting it](#starting-it)
- [What a visitor can ask for](#what-a-visitor-can-ask-for)
- [Configuration](#configuration)
- [How a scan flows through it](#how-a-scan-flows-through-it)
- [Queueing rather than refusing](#queueing-rather-than-refusing)
- [Isolation between scans](#isolation-between-scans)
- [Comparing two scans](#comparing-two-scans)
- [The SSRF guard](#the-ssrf-guard)
- [Rate limiting](#rate-limiting)
- [What gets logged](#what-gets-logged)
- [Putting it behind a reverse proxy](#putting-it-behind-a-reverse-proxy)
- [The HTTP API](#the-http-api)
- [Layout](#layout)
- [Trademarks and affiliation](#trademarks-and-affiliation)

## Starting it

The setup wizard creates the three required services: the web application, the scan
worker and Redis. It is a standalone Python script using the standard library and needs
no repository checkout:

```bash
mkdir opencloud-scanner && cd opencloud-scanner

base=https://github.com/sowoi/check-opencloud-security/releases/latest/download
curl -fsSLO "$base/setup-wizard.py" -O "$base/setup-wizard.py.sha256"
sha256sum --check setup-wizard.py.sha256    # macOS: shasum -a 256 --check
chmod +x setup-wizard.py
./setup-wizard.py --version
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

To use the published image:

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

Before making the stack publicly accessible, review these three settings in
the `.env` file beside the compose file:

| Setting | Why it matters |
|:--------|:---------------|
| `COS_WEB_PUBLIC_BASE_URL` | Canonical URLs, the sitemap and the discovery document are built from it rather than from an incoming `Host` header. It defaults to `http://localhost:8811` so a first `up` works; anything a stranger reaches must set it |
| `COS_REDIS_PASSWORD` | Redis holds every live scan and every result still inside its TTL. Unset, it asks for nothing. See [Redis](redis.md) |
| `COS_WEB_TRUST_FORWARDED_FOR` | `true` only behind a proxy of your own, otherwise every client can forge its own rate-limit identity. Set `COS_WEB_TRUSTED_PROXY_HOPS` to how many proxies there are |

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
valkey-server &
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

Use the wizard to configure a different port, internal targets, result encryption or MCP
authentication. It can run from a checkout or as a standalone download:

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
Neither flag implies the other, and nothing of Authentik is written into a
deployment that did not ask for it. Asked interactively, though, switching on
`/admin` or the sign-in on `/mcp` makes *yes* the default at the provider
question that follows, since most deployments asking for either have no
provider yet. When it is asked for, so are its mail settings
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
| `output_format` | `dashboard`, `json`, `csv`, `sarif` or `pdf`. Optional, affects presentation only. The export-only formats (`html`, `remediation-md`, `remediation-html`) are fetched from the export endpoint instead |

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
on a public service would hide every finding at once. Flags OpenCloud
hardcodes are not offered either, because nobody can fix those findings and
a waiver would suggest otherwise.

## Configuration

Every setting is an environment variable, read once at startup.

| Variable | Default | What it does |
|:---------|:--------|:-------------|
| `COS_WEB_REDIS_URL` | `redis://127.0.0.1:6379/0` | Where ephemeral state lives. `memory://` runs without Redis, for a single-process evaluation. Include the password when Redis requires one: `redis://:PASSWORD@redis:6379/0` |
| `COS_WEB_RESULT_TTL` | `3600` | Seconds a scan stays readable. Also the TTL on every key |
| `COS_WEB_COMPARISON_TTL` | `300` | Seconds a comparison against an uploaded report stays readable. Clamped to 300; shorter is honoured |
| `COS_WEB_MAX_WORKERS` | `5` | Scans running at once |
| `COS_WEB_SCAN_CONCURRENCY` | `4` | Probes in flight within one scan |
| `COS_WEB_SCAN_TIMEOUT` | `15` | Seconds one HTTP probe may take |
| `COS_WEB_JOB_TIMEOUT` | `180` | Seconds a whole scan may take |
| `COS_WEB_VERIFY_TLS` | `true` | Verify the target's certificate. An untrusted chain becomes a finding either way |
| `COS_WEB_ALLOW_PRIVATE_TARGETS` | `false` | Allow private, loopback and link-local targets. On-premise deployments only |
| `COS_WEB_ALLOWED_HOSTS` | *(empty)* | Hostnames exempt from the SSRF guard, separated by `;` |
| `COS_WEB_BLOCKED_TARGETS` | *(empty)* | Addresses this deployment will not scan, separated by `;`. Hostnames, `.suffix` domains and CIDR ranges. Outranks both settings above; an entry that does not parse refuses startup |
| `COS_WEB_CHECK_DEBUG_PORTS` | `false` | Probe extra ports. Off in public: it is a port scan of somebody else's host |
| `COS_WEB_IPV6_ENABLED` | `false` | Whether this service has outbound IPv6 of its own. Off, IPv6 addresses are never dialled and the IPv4/IPv6 TLS comparison is skipped, so a missing route on the scanning host is not reported as a fault of the instance |
| `COS_WEB_IP_RATE_LIMIT` | `10` | Scans per client address per window. `0` disables |
| `COS_WEB_IP_RATE_WINDOW` | `60` | The window, in seconds |
| `COS_WEB_TARGET_COOLDOWN` | `300` | Seconds before the same instance may be scanned again. `0` disables |
| `COS_WEB_PROBE_LIMIT` | `5` | Scans from one client address that may find no OpenCloud within `COS_WEB_PROBE_WINDOW` before that address is blocked. The same host scanned again counts again. Set on the web service **and** the worker. `0` disables |
| `COS_WEB_PROBE_WINDOW` | `300` | The window those scans are counted in, in seconds |
| `COS_WEB_PROBE_BLOCK` | `3600` | How long the first block lasts, in seconds |
| `COS_WEB_PROBE_BLOCK_MAX` | `86400` | The longest a repeated block grows to; each block inside the repeat window lasts six times the one before |
| `COS_WEB_PROBE_REPEAT_WINDOW` | `86400` | How long after a block ends the next one escalates, in seconds. `0` never escalates |
| `COS_WEB_PROBE_IPV4_PREFIX` | `24` | The IPv4 network the probe block counts as one client. `32` counts single addresses |
| `COS_WEB_CLIENT_IPV6_PREFIX` | `64` | The IPv6 network every client limit counts as one client |
| `COS_WEB_DAILY_SCAN_LIMIT` | `50` | Scans per client per day, on top of the per-minute limit. `0` disables |
| `COS_WEB_DNS_CONSISTENCY_CHECK` | `true` | Resolve a submitted name twice and refuse it when the answers share no address |
| `COS_WEB_REQUIRE_APPROVAL` | `false` | Scan approved instances only; see [Approval mode](#approval-mode) |
| `COS_WEB_APPROVED_TARGETS` | *(empty)* | Approved hostnames, `.suffix` domains, addresses and CIDR ranges, separated by `;`. An entry that does not parse refuses startup |
| `COS_WEB_APPROVAL_DNS` | `true` | In approval mode, accept a `_check-opencloud-security` TXT record naming this service's hostname |
| `COS_WEB_MAX_BATCH_TARGETS` | `10` | Targets one `POST /api/scans/batch` may carry. Each still counts against every limit |
| `COS_WEB_TRUST_FORWARDED_FOR` | `false` | Read the client address from `X-Forwarded-For` |
| `COS_WEB_TRUSTED_PROXY_HOPS` | `1` | How many proxies of your own sit in front. The header is read from the **right**, this many entries in, because that end is the only part a proxy writes |
| `COS_WEB_RATE_LIMIT_SALT` | *(random per process)* | Salt for the rate-limit and cooldown keys. Required to be the **same value in every web process** of a deployment that runs more than one: without it each derives its own keys, and a client gets one allowance per process |
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
| `COS_WEB_ADVISORY_REPOSITORY_URL` | `https://api.github.com/repos/opencloud-eu/opencloud/security-advisories` | OpenCloud's repository advisories, read with every refresh to add the ones OSV never received ([ADR 0071](../adr/0071-repository-advisories-are-a-second-advisory-source.md)). `off` skips them; a failure to read them keeps OSV's answer |
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
| `COS_WEB_ADMIN_ENABLED` | `false` | Serve the operator's area at `/admin`. Off means the routes are not registered at all, so the path 404s like any other unknown one |
| `COS_WEB_ADMIN_PROXY_SECRET` | *(unset)* | The secret the authentik outpost adds as `X-COS-Admin-Proxy`, and the only reason the identity headers are believed. Required when the area is on, at least 32 characters, or startup refuses |
| `COS_WEB_ADMIN_USERS` | *(empty)* | Who may use the area, by authentik username, `;`-separated. Empty with the area on refuses to start rather than meaning "everybody" |
| `COS_WEB_ADMIN_SIGN_OUT_URL` | *(unset)* | Where the area's sign-out link goes. This service holds no session to end, so the exit belongs to the provider in front - for the bundled stack, `/outpost.goauthentik.io/sign_out`. Unset, the band names the operator and offers no way out. Only a local path or an `http(s)` URL is accepted; anything else refuses to start, because the value is rendered as an `href` on a page whose content policy forbids script |
| `COS_WEB_ADMIN_AUDIT_BUFFER` | `200` | Recent audit records kept in memory for the live view, for a deployment that logs to stdout. `0` keeps none |
| `COS_WEB_ADMIN_REFRESH_COOLDOWN` | `60` | Shortest gap between two operator-triggered refreshes of the same reference data. The area's dry run - which reads both sources and applies nothing - is held back for the same interval under a key of its own, so it stays available in the moment after a refresh reported a failure |
| `COS_WEB_UPDATE_CHECK` | `true` | Ask GitHub whether a newer release of this service exists, for the operator's area only and at most every six hours. Set `false` with no outbound access |
| `COS_WEB_ADMIN_UPDATE_DIR` | *(unset)* | A writable tmpfs (the compose files mount one at `/var/lib/opencloud-scan/update`). Set, the operator's area can install a newer release: the web bundle is downloaded from GitHub, verified against its build attestation, unpacked here, and the web and worker processes restart on it - a short downtime, lasting until the containers restart. Unset, the area only says an update exists |
| `COS_WEB_AUDIT_LOG` | `false` | Write an audit record for every scan request, rejection and triggered limit |
| `COS_WEB_AUDIT_LOG_TARGETS` | `false` | Record the target hostname in the clear instead of as a fingerprint. On-premise deployments only |
| `COS_WEB_AUDIT_SALT` | *(random per process)* | Salt for the audit fingerprints. Setting one lets records correlate across a restart; rotating it ends that |
| `COS_WEB_AUDIT_LOG_FILE` | *(the process output)* | Write the audit records to this file instead, on a mount that outlives the container. Owner-readable only, and the ordinary log then carries no copy. A path that cannot be written refuses to start |
| `COS_WEB_AUDIT_LOG_MAX_BYTES` | `10000000` | Size at which that file is rotated. `0` never rotates |
| `COS_WEB_AUDIT_LOG_BACKUPS` | `5` | Rotated generations kept beside it. With the size above, the most the trail can occupy |
| `COS_WEB_AUDIT_LOG_ROTATION` | `service` | Who rotates that file: `service` (this process, by size) or `external` (logrotate on the host; this process only reopens the file it replaces). An unrecognised value refuses to start |
| `COS_WEB_PURGE_TOKEN` | *(none)* | Enables `DELETE /api/purge` and is the secret it requires. Unset means the endpoint answers 404 like any other path that is not there. At least 32 characters, or startup refuses: it is the whole authorisation for the one call that deletes other people's results. Five wrong answers from one address (one /64 for IPv6) in five minutes are followed by `429` |
| `COS_WEB_PURGE_SIGNING_KEY` | *(none)* | Signs the proof of deletion. Unset still erases, but the receipt cannot be verified afterwards |
| `COS_WEB_EXPORT_SIGNING_KEY` | *(none)* | Adds an `X-COS-Signature` HMAC-SHA256 header to every JSON, CSV, SARIF and PDF export |
| `COS_WEB_ENCRYPT_RESULTS` | `false` | Encrypt the stored result document with AES-256-GCM. Requires a key; a process asked to encrypt without one refuses to start |
| `COS_WEB_WEBHOOK_SECRET` | *(none)* | Read at startup but not used by the web service, which sends no webhooks; signed webhooks are the plugin's `--webhook-secret`. Listed so that setting it is not mistaken for a typo |
| `COS_WEB_ENCRYPTION_KEY_<n>` | *(none)* | A 32-byte key as 64 hex characters. The highest `<n>` encrypts, lower ones still decrypt, which is how a key is rotated |

`COS_WEB_RELEASES_MODE` is `off` by default: a public deployment
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

When there are more visitors than workers, requests queue. Every request that
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
  queued. The data expires after the retention period shown on the landing page.

## Comparing two scans

`GET /compare` answers the question that follows a remediation plan: *did it
help?* It takes two uuids the reader already has - `?baseline=` for the
earlier scan, `?current=` for the later one - and shows what was resolved,
what is new, what is still open, and how the grade moved. A finished result
page links to it with its own uuid already filled in, so only the earlier one
has to be pasted.

Comparisons use `opencloud_local_scan.baseline` through `workflows.compare_documents`,
the same calculation used by the CLI and the `compare_scans` MCP tool. See [ADR
0029](../adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md).

**Nothing is stored.** The comparison is worked out from two results that both
still exist and is written nowhere: this service keeps no scan history
([ADR 0002](../adr/0002-no-scan-result-caching.md)) and a uuid is a capability
with a TTL ([ADR 0007](../adr/0007-erasure-on-request.md)). A stored
comparison would be a scan result under another name, outliving the results it
describes and exempt from their erasure. The one case where a comparison *is*
held - because the file it was drawn from is gone and nothing could recompute
it - is [below](#comparing-against-a-report-you-uploaded), and it is held for
five minutes, under a capability, and inside the erasure it would otherwise be
exempt from.

The answers it can give:

| Situation | Answer |
|:----------|:-------|
| Both uuids resolve to finished scans | **200**, the comparison |
| Either uuid is unknown or expired | **404**, naming *which* of the two is gone - "one of them has expired" sends somebody looking through both |
| Either scan has not finished | **409**: there is nothing to compare yet, and 404 would send a reader to scan again while their scan is still running |
| The same uuid twice | **422**. An empty diff of a scan against itself reads as "nothing is wrong" |
| The two scans describe different instances | **422**, not compared. "Did the fix work" is a question about one instance, and an accidental comparison of two hosts would give a wrong answer that is easy to miss - `check-opencloud-scanner diff` refuses them too. See [ADR 0059](../adr/0059-a-comparison-refuses-two-different-instances.md) |

Like `/scan/{uuid}` and for the same reason, the page renders results and is
therefore never indexed and never in the OpenAPI schema, and each uuid remains
the whole of the authorisation for the result behind it.

## Comparing against a report you uploaded

The comparison above needs both scans to still exist, and the interesting
baseline is usually older than the hour a result lives. `POST /compare` takes
the earlier side as a **file** instead: the JSON or the CSV from the downloads
on a result page, uploaded from the reader's own disk, compared against a scan
of this service that has not expired. Same page, same arithmetic, same
verdicts - only where the earlier document came from changes. See
[ADR 0057](../adr/0057-an-uploaded-report-is-evidence-not-a-scan.md).
A report of a different instance than the scan it is compared with, or one
that names no instance, is refused with 422 the same way.

It is a browser feature and stays one: HTML only, never in the OpenAPI schema,
and there is no MCP tool for it. An agent already has `compare_scans`, which
takes two uuids - the shape an agent is in a position to supply.

**The file is the only untrusted structure this service parses.** Everything
else it compares came out of its own scanner minutes earlier, where the
untrusted part is a *string inside* a document this service built. So an
upload crosses one boundary, `webapp/imports.py`, and what comes out of it is
not what went in: a result document rebuilt key by key from an allow-list -
the fields `baseline.snapshot_of` reads, each type-checked, length-capped and
shape-checked. A key nobody named there reaches nothing downstream.

| Guard | Value |
|:------|:------|
| Largest file read | 256 KB, well below the 1 MB body limit that has already refused anything bigger |
| Encoding | strict UTF-8; a NUL byte or an invalid sequence is refused rather than repaired |
| Format | decided by looking at the bytes, never at the file name - which is read by nothing and never reflected into a page |
| CSV rows | 2 000 |
| JSON nesting | 20 levels |
| Entries per block, characters per string | 500 and 300; a block carrying more entries than that is refused rather than read in part |
| Finding identifiers | dropped unless spelled the way this scanner spells its own, and the count of everything that could not be read is shown |
| Rate limit | its own bucket, with the client limit's numbers - a parse costs this service work and costs nobody else's instance anything |
| Cross-site POST | refused before the limiter and before the parse |
| A network serving a probe block | refused before both, and before the file is read: the block is a judgement about the client, not about one endpoint |

**A fact the format never recorded is removed from both sides rather than
guessed at.** The CSV is a flat table of findings; whether an update was
pending and whether HTTPS was enforced live outside that table. Both are
written as rows now, but a file downloaded before that was true is silent
about them - and silence is not the answer "no". Those measurements are
neutralised on *both* documents before the comparison, and the page names what
it left out. JSON is the lossless round trip; CSV is a spreadsheet that
happens to be readable back.

**The file is never stored. The comparison is, for five minutes.** The upload
is read once into memory and written nowhere. What survives is the comparison
drawn from it, held under a fresh uuid4 in its own `compare:{token}:*`
namespace so a reload and a shared link keep working - the one thing here that
cannot be recomputed, because the file it came from is gone. The token behaves
like a scan uuid: unknown, malformed and expired are one 404, nothing lists
them, and results encryption applies where it is configured.
`COS_WEB_COMPARISON_TTL` can shorten that window and cannot widen it.

**An erasure request reaches it.** `DELETE /api/purge` walks the comparison
namespace as well as the scan one and deletes every cached comparison naming
that instance on either side, counting the keys into the same receipt so
`remaining: 0` keeps meaning what it says. A five-minute TTL is not a reason to
leave something out of an erasure - that is the argument
[ADR 0007](../adr/0007-erasure-on-request.md) refuses for the result itself.

| Situation | Answer |
|:----------|:-------|
| A readable report and a finished scan | **303** to `/compare/{token}` |
| No file, or no uuid | **422**, saying which half is missing |
| The later uuid is unknown or expired | **404** |
| The later scan has not finished | **409** |
| The file is empty, too large, not UTF-8, or not JSON or CSV | **422**, or **413** for size, in this service's own words - a rejected upload is never quoted back |
| The file parses but is not a scan report | **422** |
| Too many uploads from one network | **429** with `Retry-After` |
| The network is serving a probe block | **429** with `Retry-After`, for as long as the block has left to run |
| `GET /compare/{token}` after five minutes | **404**, exactly as for a token that never existed |

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
  refusal readable and survives a future carve-out;
- names under wildcard and rebinding DNS services - `nip.io`, `sslip.io`,
  `xip.io`, `traefik.me`, `localtest.me`, `lvh.me`, `vcap.me`,
  `lacolhost.com`, `localhost.direct`, `local.gd`, `rbndr.us`, `1u.ms` - are
  refused by name. They exist to point a name somewhere its reader did not
  expect; the public address behind one can still be scanned by typing it;
- a submitted name is resolved twice at once, and refused when the two answers
  share no address (`COS_WEB_DNS_CONSISTENCY_CHECK`). Every address from both
  answers is held to the rules above.

**DNS rebinding** is answered by resolving twice: once when the request is
accepted and again in the worker immediately before the scan. The window an
attacker can aim at is then a single lookup wide, and nothing in the request
can widen it, because nothing in the request influences when a worker becomes
free.

`COS_WEB_ALLOW_PRIVATE_TARGETS=true` turns all of this off. It exists for an
on-premise deployment scanning its own estate. Do not set it on anything a
stranger can reach.

### Addresses this deployment will not scan

Everything above is a property of the address. `COS_WEB_BLOCKED_TARGETS` is a
decision somebody made - an instance owner who asked to be left alone, a host
somebody keeps submitting so the service hammers it, a range that is not a
scanning target here however public it looks:

```bash
COS_WEB_BLOCKED_TARGETS="opencloud.example.com;.example.org;203.0.113.0/24"
```

- an entry is a **hostname**, a **domain suffix** written with a leading dot
  (`.example.org`, or `*.example.org` - both mean the domain *and* everything
  under it, and neither matches `notexample.org`), an **address**, or a
  **CIDR range**;
- hostnames are matched on the name, ranges on **every address the name
  resolves to**. A hostname entry therefore refuses that name and not a second
  name pointing at the same machine - exclude the range when the promise has
  to hold whatever the instance is called;
- it is checked at submission, again in the worker before the scan, and on
  every redirect hop, so a target excluded while its job sat in the queue is
  refused rather than scanned;
- it **outranks `COS_WEB_ALLOWED_HOSTS` and `COS_WEB_ALLOW_PRIVATE_TARGETS`**.
  Those exist to loosen the guard; this one answers whether the service scans
  that address at all, and loosening must not reopen it. See
  [ADR 0043](../adr/0043-an-operators-exclusion-outranks-every-allowance.md);
- an entry that is none of those four shapes **refuses startup**, in the web
  process and in the worker alike. A typo here is otherwise invisible: the
  service comes up, answers normally, and scans the addresses it was told not
  to.

The refusal a visitor sees says only that the service has been asked not to
scan that address. Which entry matched is operator configuration, and echoing
it would make every refusal a read of the list.

**The list has a second half that can be changed while the service runs.** The
request that produces most exclusions - somebody writing to ask not to be
scanned - rarely arrives at a convenient moment, and "after the next
deployment window" is not an answer to it. So the operator's area at `/admin`
has an *Exclusions* card that adds and withdraws entries, and:

- an entry takes effect **from the next request, in every process**, with
  nothing restarted: the API reads the list on each submission and the worker
  when each job starts, so a scan already waiting in the queue is refused
  rather than run;
- what `COS_WEB_BLOCKED_TARGETS` declares **cannot be withdrawn there**. Those
  entries are shown with no control beside them, and an attempt to remove one
  is refused with a pointer to the environment - your compose file stays the
  truth about what it declares;
- entries added in the area live in **Redis**, so they are as durable as your
  Redis is. Anything that must outlive a flush belongs in the environment
  variable;
- an entry is at most **253 characters**, the longest a hostname can be, here
  and in `COS_WEB_BLOCKED_TARGETS` alike. Anything longer could never match a
  target the service accepts, so it is refused as the typo it is;
- the two halves are compared **parsed, not as text**, so `Example.COM` in the
  environment and `example.com` in the area are one exclusion rather than two:
  the area declines to store what the environment already holds, and refuses
  to withdraw it under any spelling;
- if the store cannot be read, a submission is **refused rather than scanned**
  without the list - `503`, with the reason in the visitor's language and the
  pointer at self-hosting, and an `exclusions_unreadable` line in the audit
  trail rather than a rejected target.

The card is the one thing in that area that writes; see
[ADR 0044](../adr/0044-the-operator-area-may-write-the-exclusions.md) for the
four properties that made it acceptable there, and
[ADMIN.md](../ADMIN.md#the-operators-area-at-admin) for the area itself.

## Rate limiting

Every limit lives in Redis and expires on its own:

- **per client** - `COS_WEB_IP_RATE_LIMIT` scans per `COS_WEB_IP_RATE_WINDOW`,
  and at most `COS_WEB_DAILY_SCAN_LIMIT` a day. Protects the service from one
  visitor, and the daily cap from the patient version of a burst that stays
  just under the per-minute limit all night;
- **per target** - one scan per `COS_WEB_TARGET_COOLDOWN`. Protects an
  OpenCloud instance from the service. Claimed with `SET NX`, so two
  simultaneous requests for the same instance cannot both win;
- **the probe block** - `COS_WEB_PROBE_LIMIT` strikes within
  `COS_WEB_PROBE_WINDOW` block the client's network for `COS_WEB_PROBE_BLOCK`.
  Protects everybody else's hosts from this service being used to find out
  what answers where.

All of them answer **429** with a `Retry-After`. The client address is never
stored: a key holds a truncated HMAC under a pepper, which is enough to count
and useless afterwards.

**What counts as one client.** A single IPv4 address for the per-minute and
daily limits, because strangers behind one /24 should not share an allowance;
an IPv6 /64 (`COS_WEB_CLIENT_IPV6_PREFIX`) for every limit, because one
subscriber is handed a whole /64 and could otherwise rotate through it for
free. The probe block counts the IPv4 network `COS_WEB_PROBE_IPV4_PREFIX`
(`/24` by default) too, so a block cannot be stepped around by moving to the
next address along.

**What is a strike.** A scan that ends with the scanner's own verdict of *no
OpenCloud here* - `status.php` unreachable, not JSON, or another product - or
that runs out of time; and a submission the guard refuses for what it points
at: a private or internal address, an operator's exclusion, a wildcard or
rebinding DNS name, a name whose lookups disagree, or - in approval mode - an
instance nobody approved. The same host again is another strike, because
asking one address over and over whether it answers yet is probing too. A
finished scan never counts, whatever its grade, and neither does a typo, a
name that does not resolve or an unsupported scheme.

**Blocks grow when they are earned again.** A network blocked again within
`COS_WEB_PROBE_REPEAT_WINDOW` after its last block ended waits six times
longer - an hour, six hours, a day - up to `COS_WEB_PROBE_BLOCK_MAX`. Strikes
from scans that finish during a block change nothing, and a network that
stays away for the repeat window starts again at an hour.

**The block is decided after the fact.** Only the worker learns whether a host
was OpenCloud, so the submission hands it the network's fingerprint - never
the address - under `scan:{uuid}:prober`, which the worker reads and deletes
the moment the scan starts. The worker counts those strikes, the API counts
refused targets, and both impose the block through the same keys; the API
reads it before the client limit, so refusals during a block do not also spend
the allowance the visitor comes back to. MCP and the workflows wait out a
`Retry-After` of up to five minutes by themselves and hand anything longer - a
block or a spent daily cap - back to the caller.

**A host that is not OpenCloud is asked once.** The scanner reads `status.php`
before anything else, and the web service sets
`ScannerSettings.stop_when_not_opencloud`: an HTTPS answer that is not
OpenCloud ends the scan there, instead of being asked again without
certificate verification and then on port 80 as the plugin does for an
operator looking for the endpoint that works. Silence is still retried, since
that may only be an untrusted certificate.

A legitimate operator whose own instance is down can meet the block too,
after five attempts. The message says why, and points at
running the scanner locally, which has no such limit.

**The operator's area shows the guard working** - networks blocked right now,
and blocks, strikes and spent daily caps today and over seven days - as
counts. The block keys are counted, never read or listed.

### Approval mode

`COS_WEB_REQUIRE_APPROVAL=true` turns the public scanner into one that scans
approved instances only, and refuses the rest with **403**. An instance is
approved when it matches `COS_WEB_APPROVED_TARGETS` - hostnames, `.suffix`
domains, addresses and CIDR ranges, the same shapes as the exclusions - or,
with `COS_WEB_APPROVAL_DNS` (on by default), when its own zone publishes

```text
_check-opencloud-security.opencloud.example.com. TXT "check-opencloud-security=scan.example.net"
```

naming this service's hostname from `COS_WEB_PUBLIC_BASE_URL`. The record
approves one deployment, not every copy of the project, and needs no secret:
whoever can publish a TXT record under a name controls the name, which is the
claim approval asks for. The lookup goes to the system resolver only, like the
scanner's CAA check (ADR 0024), and a lookup that fails is a refusal. Approval
is checked at submission. A deployment that requires approval with an empty
list and the DNS proof off, or with an entry that does not parse, refuses to
start.

**A report page counts the wait down.** A finished report carries a **Scan
again** button, and beside it the time before that is allowed. Every limit in
the way is read - `RateLimiter.peek_client`, `peek_daily`, `peek_target` and
the probe block, which are the ordinary checks with the counting left out - and
the longest is what is shown, because a countdown that expired into a refusal
from *another* limit would be worse than none at all. Reading a limit must never spend it, or
showing somebody their wait would be the request that caused it.

The hostname comes from the record the uuid already unlocked, so this asks
nothing the caller did not bring with them: there is no way to enquire about a
target you do not hold a uuid for, and the uuid is still the whole of the
authorisation. The button itself is an ordinary form posting to `/` carrying
the first scan's target, waivers, release track and output format - so the
cross-site check, both limits, the SSRF guard and the audit trail apply to it
exactly as they do to any other submission, and the second result is rated on
the same terms as the first.

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
a client limit, target cooldown, daily cap (`rate_limit_daily`), probe block
(`rate_limit_probe`) or report upload (`rate_limit_upload`) that actually
triggered, and `submission_rejected` for one that never became a scan -
`unsupported_fields`, `target_rejected`, `target_not_approved` - or for an
uploaded report the parser would not read (`report_rejected`, carrying the key
of this service's own refusal in `fields` and no part of the file).

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

#### Keeping the trail past the container

By default those records go to the process output, which for a container means
`docker logs` — and a `docker compose down` takes them with it. An audit
question arrives months after the fact, so a deployment that wants an answer
then has to put the trail somewhere that outlives the stack:

```yaml
services:
  web_app:
    environment:
      COS_WEB_AUDIT_LOG: "true"
      COS_WEB_AUDIT_LOG_FILE: "/var/log/opencloud-scan/audit.log"
      # Rotated at this size, keeping this many generations. Together they are
      # the most the trail can ever occupy: an audit log nobody rotates fills
      # the volume it sits on and takes the service down with it.
      COS_WEB_AUDIT_LOG_MAX_BYTES: "10000000"
      COS_WEB_AUDIT_LOG_BACKUPS: "5"
    volumes:
      - audit_log:/var/log/opencloud-scan

volumes:
  audit_log:
```

Three things follow from that:

- **The records go to the file instead of, not as well as, the output.** The
  ordinary log is the one place this service keeps free of targets and client
  fingerprints, and a deployment shipping it somewhere central should not find
  the audit trail riding along.
- **The file is owner-readable only**, rotated generations included. A mounted
  volume is readable by whoever reaches the host it sits on.
- **A file that cannot be written stops the process**, with the path in the
  message. Otherwise the service would report an audit trail that is not being
  written. The same reasoning is in
  [ADR 0008](../adr/0008-refuse-to-start-without-the-encryption-key.md).

A named volume is the simplest answer and the one
[`docker/setup-wizard.py`](../docker/setup-wizard.py) offers first. A bind
mount to a host directory works identically — for existing log shipping or
backups — but the directory has to exist and be owned by uid `10001`, the
unprivileged user the image runs as, before the stack starts:

```bash
mkdir -p /srv/opencloud-scan/audit
sudo chown 10001 /srv/opencloud-scan/audit
```

On a **rootless** Docker, uid 10001 in the container is a subordinate uid on the
host, so run the `chown` inside a container instead - as the user namespace's
root, which is you, and without sudo:

```bash
docker run --rm --user 0 --entrypoint chown \
  -v /srv/opencloud-scan/audit:/target valkey/valkey:9.1-alpine 10001 /target
```

Keep it apart from a Redis data directory: Redis writes as uid 999, and one
directory can only belong to one of them.

#### Letting the host's logrotate keep it

A file on the host's filesystem is something the host already knows how to
look after, and an estate with a retention policy would rather express it
where every other log's is. `COS_WEB_AUDIT_LOG_ROTATION=external` hands the
job over: the service stops rotating by size and instead notices that the file
it holds has been moved aside and reopens the replacement.

That is the half that lives in this process. The other half is a policy the
host installs — `docker/setup-wizard.py` writes one beside the compose file
when you choose it, and it looks like this:

```
/srv/opencloud-scan/audit/audit.log {
    daily
    rotate 30
    dateext
    missingok
    notifempty
    compress
    delaycompress
    create 0600 10001 10001
}
```

```bash
sudo install -m 0644 -o root -g root opencloud-scan-audit.logrotate \
    /etc/logrotate.d/opencloud-scan-audit
sudo logrotate --debug /etc/logrotate.d/opencloud-scan-audit   # changes nothing
```

Two lines in that policy are load-bearing:

- **`create 0600 10001 10001`.** logrotate renames the file and makes the
  replacement itself, so the replacement has to be writable by the
  container's unprivileged user and readable by nobody else.
- **No `copytruncate`.** Truncating the file underneath a running writer loses
  whatever was written between the copy and the truncation. Reopening on a
  changed inode loses nothing, and this is a file whose entire purpose is to
  be complete.

**Exactly one thing may rotate the file.** Leaving
`COS_WEB_AUDIT_LOG_ROTATION` at `service` and installing a policy as well
gives you two, which is how a trail loses records; setting it to `external`
and installing nothing gives you none, and the file grows until the disk is
full. An unrecognised value refuses to start rather than guessing which you
meant.

Request bodies are limited to **1 MiB** and **30 seconds** before form, JSON
or MCP parsing. Oversized bodies return 413; incomplete bodies time out with
408. These fixed service-side limits do not change the scan queue or its
overload behaviour. Apply connection and bandwidth limits at the reverse
proxy too.

Each running scan uses a child process. A job timeout or cancellation stops
and reaps that process and its probe threads before the worker takes another
job. The worker therefore needs permission to spawn processes; allow for one
additional Python process per active scan when sizing memory and PID limits.
See [ADR 0053](../adr/0053-a-scan-timeout-ends-its-process.md).

## Putting it behind a reverse proxy

Worked configuration for nginx, Apache httpd, Caddy, Traefik and HAProxy -
including the streaming the MCP endpoint needs and the paths a proxy must not
rewrite - is in [Reverse proxies](reverse-proxy.md).

[`docker/setup-wizard.py`](../docker/setup-wizard.py) will write that file for
you for the first four: answer its reverse proxy question and the
configuration lands beside the generated compose file, with TLS, the
unbuffered `/mcp` stream, an `X-Forwarded-For` a client cannot choose, and -
where this stack provides the outpost - the forward auth in front of `/admin`.
See [the wizard's own notes](../docker/README.md#the-reverse-proxy).

The short version:

Terminate TLS in front, pass `X-Forwarded-For`, and only then set
`COS_WEB_TRUST_FORWARDED_FOR=true`.

The header is read from the **right**, `COS_WEB_TRUSTED_PROXY_HOPS` entries in
(`1` by default, which is one reverse proxy). That end is the only part a
proxy writes: nginx's `proxy_add_x_forwarded_for`, Traefik and most content
delivery networks *append*, so everything to the left of the last entry is
whatever the client sent. A CDN in front of an ingress is two hops and needs
`COS_WEB_TRUSTED_PROXY_HOPS=2`.

Counting too few is safe - the address recorded is a proxy's rather than the
visitor's. Counting more hops than there really are is what to avoid: it walks
the reader back into the part of the header a client controls, and so
allows the forgery the setting exists to prevent. When in doubt, count the
proxies you operate and no others.

An entry that is not an IP address is ignored rather than counted, so an
obfuscated identifier cannot become somebody's rate-limit bucket.

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

**202** on success, **400** for a target that cannot be scanned, **403** for an
instance a deployment in approval mode has not approved, **422** for a field
the service does not accept, **429** when a rate limit or the probe block
applies.

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

Each target in a batch passes through the same validation, client limit and target
cooldown as a single submission, in input order. Ten targets consume ten scan
allowances. The response separates accepted and rejected targets because some may be
queued while others are refused.

The same four fields are accepted, with `targets` in place of `target_url`,
and anything else is a **422** naming it. `COS_WEB_MAX_BATCH_TARGETS` caps the
list; a longer one is refused as a whole, before anything is queued, so no
target pays a cooldown for a batch that never ran.

**202** when at least one target started. When nothing started, the status is
the reason the first target was refused - **429** with `Retry-After` and the
self-hosting hint if it was a limit, **400** or **422** otherwise.

### `GET /api/scans/{uuid}/export/{format}`

A completed scan can be downloaded as `json`, `csv`, `sarif`, `pdf` or
`html`. The `remediation-md` and `remediation-html` bundles contain only
open, actionable findings and suggested nginx, Caddy, Traefik, Compose and
`.env` configuration snippets. Use a full report for the grade, passed checks
and security advisories.

```bash
curl -sS -OJ http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
```

The `html` report is **one standalone file** with its styling included.
Opening it makes no network requests; it has no scripts, images, external
fonts or stylesheets. Documentation links open only when you follow them.
It includes findings, waived findings and their reasons, the remediation
plan, coverage gaps and the reference data used to assess the scan. It has
no forms, rescan controls, polling or erasure token.

Full reports include the remediation plan: summary and step rows in CSV,
`runs[0].properties.remediation` in SARIF, a plan section in PDF and HTML,
and `remediationPlan` in JSON. Transport details appear in the CSV header
block, `runs[0].properties.tls` in SARIF, the transport sections in PDF and
HTML, and `tls` in JSON. These cover the protocol, cipher, certificate
validity and remaining days, chain completeness and OCSP stapling. A value
of `null` means the measurement could not be established, not that the check
passed.

The result page and the two remediation bundles also group the open findings
by where the change is made - reverse proxy, identity provider, OpenCloud,
DNS zone - and name the changes that resolve several findings at once
(`remediationPlan.groups` in JSON).

Downloads are generated from the stored result on request. Their links stop
working when the scan expires. Files already saved remain available, do not
update and are not removed when the scan is erased. The completed
`GET /api/scans/{uuid}` response lists the download URLs under `exports`;
the result page offers the same formats as download buttons.

#### Signed exports

With `COS_WEB_EXPORT_SIGNING_KEY` set, every export response carries a
signature of its exact bytes:

```text
X-COS-Signature: HMAC-SHA256=d68d9da7f04a4dcf38de5c64545141dc02c50c7476e76687e74c015383f34258
```

It is an HMAC-SHA256 over the body as sent, computed with the key's text as
UTF-8. PDF and CSV are covered the same way as JSON and SARIF. It lets a CI
job or an archive show later that a file is the one this service produced,
and that nobody edited it since.

**It is a shared secret, not a public signature.** Verifying needs the same
key, so only someone who holds it can check a file: the operator, or a
pipeline given the key through its secret store. A visitor cannot verify a
download on their own, and must never be sent the key to do so. Treat it like
a password, and generate a long random one:

```bash
openssl rand -hex 32
```

Save the header together with the file, because the signature is not
embedded in the file itself:

```bash
curl -sS -D headers.txt -o result.pdf \
  http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
grep -i '^x-cos-signature' headers.txt
```

Verify the **downloaded bytes**, never a parsed or re-serialised copy.
Reformatting the JSON changes the bytes and breaks the signature. From a
checkout of this repository:

```bash
COS_WEB_EXPORT_SIGNING_KEY='<key-from-secret-store>' \
  uv run python scripts/verify_export.py result.pdf 'HMAC-SHA256=<hex-from-header>'
```

It prints `signature verified` and exits `0`, or prints `signature
verification failed` and exits `1`. `--key-env NAME` reads the key from a
different environment variable. Without a checkout, `openssl` computes the
same digest, to compare with the hex after `HMAC-SHA256=`:

```bash
openssl dgst -sha256 -hmac "$COS_WEB_EXPORT_SIGNING_KEY" -r result.pdf
```

Rotating the key invalidates every signature made with the old one, since
there is no key versioning as there is for
`COS_WEB_ENCRYPTION_KEY_<n>`. Keep the old key wherever old files may still
need checking. Without the variable, exports are sent unsigned and carry no
header.

**200** with a `Content-Disposition` naming the uuid, **409** while the scan
has not finished - it exists, so 404 would send a caller into a retry loop
against the wrong endpoint - and **404** for an unknown uuid or an unknown
format.

### `GET /api/scans/{uuid}/badge.svg`

The grade as a small SVG, for pasting somewhere a picture says it faster than
a link.

```bash
curl -sS http://127.0.0.1:8811/api/scans/0f4a1f22-.../badge.svg
```

```markdown
![OpenCloud security](https://scan.example.com/api/scans/0f4a1f22-.../badge.svg)
```

It is written by `webapp/badge.py` the way the PDF is written by
`reports.py` - no badge service, no external font, no script. An `<img>`
pointing at somebody else's server would hand them the result URL in a
referrer on every view, and that URL's uuid is the whole of the authorisation
for the full result.

The badge carries the letter and nothing the scanned instance chose: no
hostname, no product string, no version. The colour is the dashboard's own
tone for that rating, so a badge and the page it links to cannot disagree.

**It lasts as long as the scan does.** With the default
`COS_WEB_RESULT_TTL` of one hour, an image embedded somewhere permanent stops
resolving within the hour and answers **404** like any other expired uuid.
That makes it right for a ticket, a chat message or a status dashboard while a
result is current, and wrong for a README - unless the deployment serving it
keeps results far longer, which is a decision with its own consequences for
everybody whose scans it stores. No endpoint
renders a badge for a *hostname*: that would be a permanent, guessable handle
on somebody's instance, which this service does not offer.

**200** with `image/svg+xml` and `Cache-Control: no-store`, **409** while the
scan has not finished, **404** for an unknown or expired uuid. The `no-store`
is the service-wide default it never opts out of: every route that is publicly
cacheable publishes metadata about *this service*
([ADR 0031](../adr/0031-a-response-is-uncacheable-until-a-route-opts-in.md)),
and a badge is a statement about somebody's instance.

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

The receipt records what the deletion found and removed. `deleted` counts removed keys;
`remaining` comes from a second inspection afterward, and `complete` means `remaining ==
0`. `notes` identifies data outside the operation’s reach, including downloaded reports
and any retained audit trail. Verify a signed receipt with:

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

If no matching data is found, the endpoint returns 200 with zero counts. The receipt
describes the store at the time of that inspection.

### `GET /llms.txt`, `GET /openapi.json`, `GET /arazzo.json`, `GET /.well-known/ai.json`

These discovery and contract documents are always public. `COS_WEB_ENABLE_DOCS` controls
only the interactive `/docs` and `/redoc` views.

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
execution layer and does not reimplement the service: every tool calls this
application's own HTTP API in process, so an agent meets the same rate
limits, SSRF guard and purge authorisation as a browser.

Seven tools, one per user-level task rather than one per endpoint:
`scan_instance`, `scan_instances`, `get_scan_result`, `plan_remediation`,
`compare_scans`, `export_scan` and `erase_instance_data`. Seven prompts name
the tasks people ask for - `audit_instance`, `audit_estate`,
`explain_scan_result`, `triage_findings`, `review_transport_security`,
`check_release_support` and `verify_remediation` - so a client can offer
"audit this instance and write a remediation plan" as one thing to pick. Five resources are published under `spec://` URIs: the
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
nothing about any scan.

A finished result page also offers to **scan again** - the same target on the
same terms, with the wait counted down beside it (see [Rate
limiting](#rate-limiting)) - and renders the findings it just listed **as
configuration**: a Compose, `.env`, nginx, Caddy or Traefik fragment built by
`opencloud_local_scan.snippets` from the catalogue's own `env_fix` and
`header_fix` pairs, with the chosen flavour remembered in the browser. All
five are rendered server-side and a script collapses them into a picker, so a
reader without scripting gets every fragment rather than one visible block and
four dead buttons. Nothing is generated in the browser: the fragments come
from the module the library tests cover, and a second implementation of that
in JavaScript is the one thing on the page that must not exist. The explanations the landing page used to carry sit on
their own pages - `GET /how-it-works`, `GET /grades`, `GET /documentation`,
`GET /search`, `GET /api`, `GET /privacy` and `GET /about` - which
are HTML only and stay out of the OpenAPI schema. So does `GET /compare`,
for a second reason: it renders two results and is therefore never
indexable, exactly as `/scan/{uuid}` is not. `/grades` explains the
plugin's real 0-5 map and its remediation ceilings; `/documentation` is the
local CLI quick reference and guide index, and it is also the page that points
away from this service: the Docker one-liners that run the same scan on the
visitor's own machine sit directly under its quick start, documented at length
in [Scanning from the command line, in one line](docker-oneliner.md). They used
to be a `/cli` tab of their own; that path is now a permanent redirect to
`/documentation#oneliner`. `GET /healthz` returns 200 only after the configured
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
result pages, exports, UUIDs or submitted addresses. Every pull request to
`main` rebuilds that file and commits it to the branch, and the release
workflow rebuilds it again before building artefacts, so one deployed release
has one immutable search index. ADR 0019 records the boundary and ADR 0050
when it is rebuilt.

When `COS_WEB_ENABLE_MCP` is on, the landing and result pages also expose
their existing actions to supporting browsers through the
[WebMCP draft](https://webmachinelearning.github.io/webmcp/). The landing
page registers `scan_opencloud_security`; a result page registers
`get_scan_result` and `export_scan_report` for the displayed UUID. Their
schemas are rendered from the same catalogues as the page controls. Execution
uses the public API with `Accept: application/json`, so WebMCP does not bypass
the SSRF guard, rate limits, cooldown, queue, or capability checks.

A browser tool answers a failure rather than throwing one: `ok: false` with
`status`, `error` and `retryable`, plus `retryAfter` in seconds where the
service sent one. This is the contract the `/mcp` tools already used, and the
statuses behind it are rendered into the page from `webapp/workflows.py`
rather than written into the script. See
[ADR 0041](../adr/0041-a-browser-tool-answers-a-failure-rather-than-throwing.md).

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

### `GET /advisories.atom`, `GET /release-schedule.atom`

The two documents that refresh themselves daily, as Atom 1.0 feeds.

```bash
curl -sS http://127.0.0.1:8811/advisories.atom
```

`/advisories.atom` is the advisory database a scan is rated against - one
entry per advisory, with its severity, the affected version ranges in the
half-open form the scanner matches on, and a link to the published advisory.
`/release-schedule.atom` is one entry per OpenCloud release line, dated by its
release date, saying which tracks it was published on and when it stops
receiving fixes.

Both are built from the same functions the pages use, so a feed cannot
describe an advisory differently from `/catalogue`. They are the reason a scan
run today can grade an instance more harshly than the same scan last month,
which is worth being told about: a subscriber hears that the database changed
without re-scanning to find out.

Advisory titles and descriptions come from a public feed this project does not
control. They are carried as escaped `type="text"`, never as markup, so a
reader cannot be made to render somebody else's HTML.

These are the only reference-data routes that opt into a public cache
(`max-age=3600`). They name no instance, carry no uuid and take no parameter -
the test [ADR 0031](../adr/0031-a-response-is-uncacheable-until-a-route-opts-in.md)
sets for being cacheable at all - and they must never learn to take one: a
feed filtered by hostname would be a question about somebody's instance.
Entry ids are URNs of the advisory or release line rather than URLs of this
deployment, so a reader's history survives the service moving host.

### `GET /robots.txt`, `GET /agents.txt`, `GET /sitemap.xml`

All three are generated, never files on disk. The sitemap lists the landing
page, the nine explanation/index pages and every generated CLI document, and
takes each `lastmod` from the template that renders it, so it cannot drift
from the pages that actually exist. None of them ever mentions a result: the
uuid is the only authorisation, and this service has no listing of results. `robots.txt` disallows `/scan/`, `/api/`, the schema
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
