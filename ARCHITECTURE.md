# Architecture

How this repository is put together, and why the seams are where they are.
[`AGENTS.md`](AGENTS.md) holds the rules; this document holds the shape they
follow from. For a decision and the alternatives that lost, read the record in
[`adr/`](adr/README.md).

<!-- TOC -->
* [The one-sentence version](#the-one-sentence-version)
* [Three layers](#three-layers)
  * [Measure: `opencloud_local_scan/`](#measure-opencloud_local_scan)
  * [Judge: `check_opencloud_security.py`](#judge-check_opencloud_securitypy)
  * [Serve: `webapp/` and `frontend/`](#serve-webapp-and-frontend)
  * [Frontend localization](#frontend-localization)
* [How settings reach the scanner](#how-settings-reach-the-scanner)
* [How a scan flows through the web application](#how-a-scan-flows-through-the-web-application)
* [The agent-facing surfaces](#the-agent-facing-surfaces)
  * [One workflow layer, three descriptions](#one-workflow-layer-three-descriptions)
  * [Browser WebMCP](#browser-webmcp)
  * [Discovery](#discovery)
  * [What MCP may not do](#what-mcp-may-not-do)
* [Concurrency](#concurrency)
* [State and its lifetime](#state-and-its-lifetime)
* [The rating](#the-rating)
* [The release lifecycle](#the-release-lifecycle)
  * [Updating for a new OpenCloud release](#updating-for-a-new-opencloud-release)
* [What ships where](#what-ships-where)
* [Testing strategy](#testing-strategy)
* [Where to add things](#where-to-add-things)
* [Trademarks and affiliation](#trademarks-and-affiliation)
<!-- TOC -->

## The one-sentence version

A monitoring plugin that talks to an OpenCloud instance itself, works out a
`0`-`5` rating from what it reads, and exits with a Nagios status - plus a
library it is built on and a web service that runs the same library for
somebody who does not want to install anything.

There is no remote scan API. Nothing here asks another service for a verdict,
and nothing here should ever start to. The `0`-`5` scale matches the Nextcloud
scan API only so that existing thresholds, graphs and alert rules keep their
meaning.

## Three layers

The boundaries between them are the design. A change that blurs one is in the
wrong file, however small it looks.

```text
                 ┌────────────────────────────────────────┐
   HTTP probes   │  opencloud_local_scan/   MEASURES      │
   to the ───────┤  scan() → result document              │
   instance      │  never decides what is acceptable      │
                 └───────────────┬────────────────────────┘
                                 │  result document
              ┌──────────────────┴───────────────────┐
              ▼                                      ▼
┌────────────────────────────────┐   ┌────────────────────────────────┐
│ check_opencloud_security.py    │   │ webapp/ + frontend/            │
│ JUDGES                         │   │ SERVES                         │
│ thresholds, exit code, alert   │   │ takes a URL from a stranger,   │
│ line, perfdata, webhook        │   │ queues it, renders the answer  │
└────────────────────────────────┘   └────────────────────────────────┘
                                                  │
                                       grades come from the plugin's
                                       RATE_MAP - never decided here
```

### Measure: `opencloud_local_scan/`

The scanner library. `scan()` probes an instance over HTTP and returns a
result document; it has no notion of WARNING or CRITICAL and never gains one.

| Module | Responsibility |
|:-------|:---------------|
| `scanner.py` | The scan pipeline, findings, waivers and the rating |
| `versions.py` | The lifecycle model: tracks, lines, end of life |
| `releases.py` | The update check and its track-aware recommendation |
| `hardening.py` | The catalogue explaining every hardening identifier |
| `tls.py` | Transport security: protocol, certificate, chain, stapling |
| `remediation.py` | The ordered fix list, replayed from the rating's own caps |
| `config.py`, `factory.py` | Configuration, secrets, settings construction |
| `wizard.py`, `selfupdate.py` | `--configure` and `--upgrade-self` |
| `data/release_schedule.json` | The bundled release schedule |

Result-document keys are camelCase - `extraChecks`, `ratingExplanation`,
`latestVersionInBranch`, and the shouted `EOL`.

### Judge: `check_opencloud_security.py`

The plugin. It owns every threshold, the exit code, the alert line, the
perfdata and the webhook, and its own output is snake_case:
`failed_extra_checks`, `plugin_version`, `rating_label`.

Startup order matters and is load-bearing: `_run_early_commands()` →
`_preparse_config()` → `_set_configuration()` → `build_arg_parser()` →
`parse_args()`. `--host` is required unless the environment supplies it, so any
mode that does not scan has to be intercepted in `_run_early_commands()`,
before a parser that insists on a host is ever built.

### Serve: `webapp/` and `frontend/`

The public service. It takes a URL from a stranger, hands it to the scanner and
renders what comes back. It reimplements no check and decides no grade -
`catalog.summarise()` regroups the document the scanner already produced, and
the letters come from the plugin's `RATE_MAP`.

| Module | Responsibility |
|:-------|:---------------|
| `app.py` | Routes, security headers, request validation |
| `settings.py` | Every `COS_WEB_*` variable, read once at startup |
| `ssrf.py` | What may be connected to, checked twice |
| `ratelimit.py` | The client limit and the per-target cooldown |
| `audit.py` | The optional, pseudonymised audit trail |
| `store.py` | One Redis namespace per scan, a TTL on every key |
| `queue.py`, `tasks.py` | Handing a scan to the ARQ worker, and running it |
| `runner.py` | Where a request becomes `ScannerSettings` |
| `catalog.py` | The waiver allow-list and the dashboard grouping |
| `documentation.py`, `search.py` | Public guide and release-search manifests |
| `i18n.py`, `locales/` | Request locale selection and the four string catalogues |
| `reports.py` | CSV, SARIF and the hand-written PDF |
| `redis_backend.py` | The Redis client, and the in-process stand-in the tests use |
| `workflows.py` | What a *task* means: submit, poll, wait, complete, export |
| `openapi.py` | The OpenAPI 3.1 document, written rather than inferred |
| `arazzo.py` | Those workflows described as Arazzo 1.0.1 |
| `mcp_server.py` | The MCP endpoint: the same workflows, executed for an agent |
| `prompts.py` | The prompts an agent is offered: the tasks people ask for, written once |
| `mcp_auth.py` | The optional sign-in on `/mcp`: a token verified, never issued |
| `discovery.py` | `/.well-known/ai.json`, which names all of the above |
| `seo.py` | Canonical URLs, `robots.txt` and the generated sitemap |
| `purge.py` | Erasure on request, and the receipt that proves it happened |
| `encryption.py` | Optional AES-256-GCM for results at rest |

The same service also describes itself and lets an agent drive it -
`/openapi.json`, `/arazzo.json`, `/mcp` and `/.well-known/ai.json`. That is
still the *serve* layer and nothing else: see
[The agent-facing surfaces](#the-agent-facing-surfaces).

`frontend/` holds every template and asset and no logic; `webapp/` holds no
markup. Nothing the browser loads comes from anywhere but `/static`, and the
CSP has no `unsafe-inline`, so there is no inline style, script or handler
anywhere.

### Frontend localization

One set of templates renders in English, German, Spanish and French. English
is the source catalogue; the other three catalogues have identical keys,
format placeholders and inline markup. `app.py` binds one translator to each
HTML request:

```text
validated cos_locale cookie
          │
          ├── absent ──► weighted Accept-Language
          │
          └── unsupported/absent ──► English
                                      │
                                      ▼
                         shared Jinja templates + <html lang>
```

The `/language` POST stores an `HttpOnly`, `SameSite=Lax` cookie and redirects
only to a validated local path. Pages vary on both `Cookie` and
`Accept-Language`; no locale appears in a URL, so a result UUID remains one
capability with one address.

Only application-authored HTML is translated. OpenAPI, Arazzo, MCP, discovery
documents and exports stay stable English contracts, while values and errors
measured from a remote instance remain verbatim. Browser JavaScript receives
its phrases through translated `data-*` attributes, never a second catalogue.
Generated operator-guide bodies remain English under `lang="en"` and have
localized chrome and a localized notice.

Search follows the same boundary at release time:
`scripts/build_search_index.py` writes one English index plus German, Spanish
and French overlays from the catalogues. The public manifest remains its only
input, so translation does not create a path from result data into search.
ADR 0020 records the language decision; ADR 0019 records the search boundary.

## How settings reach the scanner

One direction, four sources, one precedence:

```text
YAML/JSON file ─┐
environment  ───┼─→ config.Configuration ─→ factory.py ─→ frozen *Settings ─→ scanner
CLI flags    ───┘        (flat COS_ names)     (builds)       (dataclasses)
```

- `config.py` flattens nested keys: `scanner.target_port` in a file becomes
  `SCANNER_TARGET_PORT`, read from the environment as
  `COS_SCANNER_TARGET_PORT`. Lists join with `;`.
- Precedence is **CLI flag > environment variable > file > default**, and both
  CLIs implement it by passing `None` for "not specified" into `factory.py`.
- `factory.py` is the only place that builds `ScannerSettings` and
  `ReleaseSettings`, both frozen.
- A file ending in `.json` is parsed as JSON, anything else as YAML. The
  suffix decides, not the content.

The web application does not participate in that chain at all. Its settings are
`COS_WEB_*` environment variables read once at startup, because a request may
choose *what* to scan and never *how hard*.

## How a scan flows through the web application

```text
POST /api/scans ──► client rate limit ──► SSRF guard ──► waiver allow-list
POST /api/scans/batch  (per target, in order)                 │
                                                              ▼
                                                       target cooldown
                                                              │
                                                    uuid + Redis namespace
                                                              │
                                                          ARQ queue
                                                              │
                                                     worker: validate the
                                                     target again, scan,
                                                     store the result
                                                              │
                          GET /scan/{uuid} ◄───────────────────┤
                          GET /api/scans/{uuid}                │
                          GET /api/scans/{uuid}/export/{fmt} ◄─┘
```

The order is deliberate. The client limit comes first because it is one Redis
`INCR` and it protects the resolver behind the SSRF guard from being used as an
amplifier. The cooldown is claimed with `SET NX`, so two simultaneous requests
for the same instance cannot both win. Only then does a uuid exist.

A batch is the same pipeline run once per target, in the order they were
written: no target skips a limit by arriving with company, and the response
carries what started and what did not.

Overload queues rather than refusing. A submission past the worker count is
accepted, gets a uuid and waits in FIFO order with its position on screen; a
valid submission never receives a 503.

## The agent-facing surfaces

An AI agent that knows only `https://scan.okxo.de` has to be able to find out
what this service does and then do it, without a copy of this repository, this
document or `AGENTS.md`. Four things make that possible, and **none of them
contains a check, a limit or a verdict of its own.**

### One workflow layer, three descriptions

```text
                    webapp/workflows.py
             the semantics: submit -> poll -> wait ->
             complete -> export, and the rules for each
                            |
        +-------------------+-------------------+
        v                   v                   v
   openapi.py           arazzo.py          mcp_server.py
   what operations      how they combine   an agent performs
   exist                into a task        the task
        |                   |                   |
   /openapi.json       /arazzo.json           /mcp
```

`workflows.py` holds the numbers and the decisions once - the `202` a
submission answers with, the poll interval, the attempt ceiling, that a `404`
is final because an unknown uuid never becomes known, that a `409` on an
export means *not yet* rather than *never*. The Arazzo document reads those
constants, the MCP tools call those functions, and a test fails if either
hardcodes a different number. If a description and the API disagree, the API
wins and the description is the bug.

`mcp_server.py` executes by calling **this service's own HTTP API in-process**,
through the ordinary ASGI stack. That is the whole design: the SSRF guard, the
client rate limit, the target cooldown, the queue and the authorisation on
erasure are the real ones, because there is no second path to them. An agent
cannot reach a code path a browser could not, and cannot be rationed more
generously than a browser is. See
[ADR 0011](adr/0011-mcp-is-an-execution-layer-not-a-second-implementation.md).

Six tools, and they are **tasks rather than endpoints**: `scan_instance`,
`scan_instances`, `get_scan_result`, `plan_remediation`, `export_scan` and
`erase_instance_data`. An agent asked to scan an instance calls one tool once;
it does not orchestrate a submission and thirty polls, because the polling is
in `workflows.py`. Three resources - `spec://check-opencloud-security/...` for
the OpenAPI, Arazzo and discovery documents - let an agent read the contracts
it is working against. A specification is a document an agent reads, not a
call it makes, so it gets a resource URI rather than a link.

Six **prompts** name the tasks a person asks for - `audit_instance`,
`audit_estate`, `explain_scan_result`, `triage_findings`,
`review_transport_security` and `check_release_support` - so a client offers
the job rather than a menu of verbs. Their wording lives once in
`prompts.py`, composed from the notes and constants in `workflows.py`, and a
prompt names tools rather than endpoints because the tools are what carry the
limits. See
[ADR 0014](adr/0014-prompts-are-tasks-and-their-text-lives-beside-the-workflows.md).

The endpoint is **open unless an operator says otherwise**, which is what the
public deployment wants and what the default is. An estate running it for
itself sets `COS_WEB_MCP_AUTH_ENABLED` and an issuer, and `mcp_auth.py` makes
it an OAuth 2.0 resource server: a bearer token verified offline against the
provider's published keys - signature, issuer, audience, expiry, scopes,
asymmetric algorithms only - with a `401` naming the RFC 9728 metadata
document, which names the provider. This service issues nothing, stores
nothing and holds no account; `docker/docker-compose.authentik.yml` is a
complete alternative stack for operators who want a provider to hand, and
nothing in the code knows its name.

Two properties hold that layer in place. **Authentication decides who may
ask, never how hard**: every rate limit, cooldown and guard is identical for
an authenticated agent, because a sign-in that raised a limit would have
become the way around it. And a deployment that **asked for a sign-in it
cannot enforce refuses to start**, exactly as one asked to encrypt without a
key does - an operator who believes the endpoint is protected while it is
served open is the worst outcome available. See
[ADR 0015](adr/0015-the-mcp-endpoint-may-require-a-sign-in.md).

### Browser WebMCP

When MCP is enabled, the landing and result pages expose their current actions through the
[WebMCP draft](https://webmachinelearning.github.io/webmcp/). This is a
client-side adapter, not another workflow implementation:

```text
Jinja context -> _webmcp.html -> /static/js/webmcp.js
                                      |
                                      v
                         fetch with Accept: application/json
                                      |
                    +-----------------+------------------+
                    v                 v                  v
             POST /api/scans   GET /api/scans/{uuid}   export route
```

Jinja builds each JSON Schema from the options used by the rendered page.
Release tracks, output formats, waiver identifiers, and export formats
therefore cannot drift into a second browser-side catalogue. The external
script registers tools after `DOMContentLoaded` and checks for WebMCP before
using it. It accepts the earlier `navigator.modelContext` implementation and
the current `document.modelContext` draft.

The landing page offers `scan_opencloud_security`. A result page offers
`get_scan_result` and `export_scan_report`, bound to the UUID already in that
page. Other views have no useful page-specific action and register nothing.
Every execution calls the ordinary HTTP API with `Accept: application/json`,
so the SSRF guard, rate limits, cooldown, queue, and capability checks remain
the only implementation. `COS_WEB_ENABLE_MCP=false` removes both these
registrations and the server-side `/mcp` endpoint. ADR 0021 records this
boundary.

### Discovery

Naming a file after a specification is not a discovery mechanism. Nothing will
guess `/arazzo.json`, so one document names all of them:

```text
https://scan.okxo.de
        |
        +--> /llms.txt             short agent-readable map
        |
        v
/.well-known/ai.json --+--> /openapi.json   operations
                       +--> /arazzo.json    workflows
                       +--> /mcp            server-side tools
                       +--> /ai             the same thing, for a human
```

`/llms.txt` is the short starting point for clients that look for that file.
It names the contracts and interaction rules without containing a result,
UUID, or credential. `/.well-known/ai.json` is *this application's* detailed
discovery document and not a registered standard,
which is why the code says so and the documentation does too. It lives under
`/.well-known/` because that is where a well-behaved client looks, and it is
deliberately small: a name, a description and absolute URLs. `base.html`
carries `service-desc` and `arazzo` link relations as hints, and the `/ai`
page says the same in prose with ordinary clickable links - for the visitor
who is a person, and for the crawler that only reads HTML.

All four URLs are public and unauthenticated at stable paths.
`COS_WEB_ENABLE_DOCS` governs only the browsable `/docs` and `/redoc` pages,
never the JSON: a description nobody can fetch describes nothing
([ADR 0010](adr/0010-machine-readable-descriptions-are-always-public.md)).
`COS_WEB_ENABLE_MCP` turns the MCP endpoint off for a deployment that does not
want one, and the discovery document then stops advertising it.

### What MCP may not do

The endpoint is a way in, and it is treated as one.

- **It is not a second implementation.** A check reimplemented, a limit
  loosened or a grade decided in `mcp_server.py` is in the wrong file, exactly
  as it would be in `webapp/`.
- **It is not a way around a rate limit.** Every tool call is rationed against
  the address it actually came from; the transport's loopback default would
  otherwise have put every agent in the world in one bucket.
  `COS_WEB_MCP_MAX_CONCURRENT_WAITS` caps how many calls may sit waiting on a
  scan at once, and reaching it refuses nothing: the scan is submitted and the
  uuid comes back with a note to poll.
- **It is not a channel from a scanned host to the model.** A version string,
  a product name and an error message are chosen by somebody else's server and
  land in a language model's context, so each is collapsed, stripped and
  truncated, and the answer carries an `untrusted` block naming those fields
  and saying they are to be reported, never obeyed.
- **It does not hold credentials.** `erase_instance_data` is marked
  destructive and requires the same authorisation the API does; the MCP layer
  never supplies it, logs it or hands it back.
- **A uuid is validated as a uuid** before it reaches a request path, because
  an HTTP client resolves `..`, and `../../healthz` is not a scan.

## Concurrency

Per call site, and it must never nest.

- `_run_all(settings, tasks)` in the scanner creates its own
  `ThreadPoolExecutor` and preserves submission order via `pool.map`. That
  ordering is load-bearing and has tests.
- Group-level parallelism in `_collect_extra_findings` was deliberately left
  out: it would multiply the worker count.
- The default is `1`, which means genuinely sequential.
- `requests.Session` is not thread-safe, so `_Probe` keeps a `threading.local`
  session per worker and records an `_owner` thread id. Use `_Probe.derive(url)`
  for a second base URL; never share a session by hand.
- In the web application, concurrency is `COS_WEB_MAX_WORKERS` (scans at once)
  and `COS_WEB_SCAN_CONCURRENCY` (probes within one scan). Neither is reachable
  from a request.

## State and its lifetime

The plugin holds no state. The web application holds as little as it can:

- Three Redis keys per scan - `scan:{uuid}:status|result|metadata` - each with
  a TTL, plus one shared list of pending uuids for the queue position.
- **The uuid is a capability.** There is no listing endpoint, no guessable
  identifier, and no way for one scan to read another's keys. Unknown, invalid
  and expired all answer the same 404.
- Logs carry lifecycle markers and a uuid. The audit trail in `audit.py` is the
  one exception, is off by default, and records fingerprints rather than
  addresses ([ADR 0004](adr/0004-webapp-audit-logging.md)).
- Results are never cached ([ADR 0002](adr/0002-no-scan-result-caching.md)),
  and a worker heartbeat, not a process check, decides readiness
  ([ADR 0003](adr/0003-worker-health-heartbeat.md)).
- Everything expires on its own, and `DELETE /api/purge` erases it sooner on
  request. Because nothing maps a target back to its scans - such a map would
  be the very record this service refuses to keep - the purge walks the
  keyspace once, and returns a receipt whose `remaining` count comes from a
  second walk after the deletion
  ([ADR 0007](adr/0007-erasure-on-request.md)).
- `COS_WEB_ENCRYPT_RESULTS` encrypts the stored result with AES-256-GCM, and a
  process asked to encrypt without a usable key refuses to start rather than
  write cleartext while claiming otherwise
  ([ADR 0008](adr/0008-refuse-to-start-without-the-encryption-key.md)).

## The rating

The rating starts from the version and the advisory database, then failed
checks cap it (`SEVERITY_RATING_CAP`: critical 2, high 3, medium 4, low 5).
Two invariants have tests:

- **The explanation must not depend on iteration order.** A cap counts as
  *applied* when it equals the final rating, never "whichever came first".
- **End of life overrides everything**, including a wildcard waiver. A release
  that receives no security fixes is an F.

`remediation.py` answers the question that follows - *which of these do I fix,
and where does it get me?* - by replaying that same arithmetic with one finding
removed at a time. It is derived from the result document and stored nowhere
new, and it carries numbers only: the letters are still applied by the layer
that judges ([ADR 0012](adr/0012-the-remediation-plan-is-derived-not-stored.md)).

A waiver suppresses an alert, not the evidence: a waived finding stays in the
result document with `"ignored": true`, and only a finding that actually failed
may be waived, so a waiver cannot silently become a blind spot when a measure
regresses.

Some findings can never be fixed. Flags OpenCloud hardcodes are marked
`actionable=False` in `hardening.py`: they stay in the result document but out
of the alert line, the `hardenings_missing` metric and the webhook.

## The release lifecycle

OpenCloud ships rolling (~3 weeks), production (~6 months) and LTS (2 years)
releases side by side. Releases group into **lines** (`MAJOR.MINOR`), and one
line can belong to several tracks.

- rolling and production expire when the next release on the same track ships;
  LTS expires on the clock.
- **A newer version can be less supported than an older one.** That is the
  model, not a bug.
- **Ahead of your track is not end of life.** Only a release *behind* the
  current release of the declared track is unsupported.
- An upgrade recommendation only ever points forwards, and never moves a
  production or LTS instance onto the rolling track.

`scripts/update_release_schedule.py` regenerates
`opencloud_local_scan/data/release_schedule.json` and the block between the
`release-schedule` markers in `README.md`. Both are committed together, and
neither is edited by hand.

### Updating for a new OpenCloud release

The repository learns release facts automatically, but it never declares a
new OpenCloud release scanner-compatible without review. Follow this sequence
for a rolling, production, or LTS release:

1. **Start with evidence.** Let the scheduled
   `release-schedule.yml` workflow, or a local
   `uv run python scripts/update_release_schedule.py`, read the authoritative
   lifecycle page. It opens a PR containing only the schedule and generated
   README table. Do not edit either by hand and do not infer a track from a
   version number: the lifecycle source is what says whether a line is rolling,
   production, LTS, or several of them.
2. **Review the track-specific lifecycle change.** For a rolling or production
   line, verify that its successor makes the previous line unsupported. For an
   LTS line, verify the opening date and the calculated two-year support
   window. Existing lines may gain a newer patch, but their known tracks and
   opening dates must not disappear. A rejected runtime refresh is a safety
   signal, not a reason to relax that rule.
3. **Evaluate the vendor image separately.** Dispatch the `real OpenCloud
   container` workflow with `candidate_image` set to the immutable candidate
   digest. It initializes the vendor image and scans its public status
   endpoint. Record the reported OpenCloud version and inspect failures in
   version detection, TLS, headers, authentication redirects, exposed
   endpoints, hardening evidence, and the rating.
4. **Map any changed behaviour to the scanner.** Compare the candidate result
   with `tests/fake_opencloud.py`, `tests/test_local_scanner.py`, TLS and
   hardening tests. Change a fixture or expectation only with release evidence
   explaining the former behaviour, the new behaviour, the affected version,
   and the scanner rule. Never remove an assertion, weaken a grade, or widen a
   tolerance merely to make the candidate pass.
5. **Add a check only when it is externally observable and actionable.** Put
   new measurement in `opencloud_local_scan/`; keep rating decisions in the
   plugin. Confirm in OpenCloud source that an operator can change a proposed
   hardening setting before adding it. Add positive and negative unit coverage,
   update operator and machine-readable documentation, and add an ADR only if
   the change alters a durable boundary.
6. **Review advisory evidence too.** Run or wait for
   `vulnerability-db.yml`. Its PR may add affected ranges but must never
   remove an advisory or an already-known range. Check every new range against
   the advisory source before merge.
7. **Promote deliberately.** Once lifecycle, advisory, scanner, and full-suite
   evidence are reviewed, update the integration workflow's reviewed digest in
   a normal PR. Run `uv run pytest`, `uvx ruff check .`, `uv run mypy
   --config-file mypy.ini`, generated-document validation, and the candidate
   container test. The resulting diff is the compatibility record; no release
   data, fixture, or version number is changed directly in production.

## What ships where

| Artefact | Contents | Built by |
|:---------|:---------|:---------|
| PyPI wheel and sdist | The plugin and `opencloud_local_scan/` | `hatch`, excluding `webapp/` and `frontend/` |
| `check_opencloud_security_web.tar.gz` | The web application and its frontend | `scripts/build_web_bundle.py` |
| `docker/Dockerfile` | The plugin and the scanner service | The release workflow |
| `docker/Dockerfile.web` | The wheel plus the `web` and `mcp` extras, `webapp/`, `frontend/` | The release workflow |

Somebody installing a monitoring plugin must not receive FastAPI, Redis and
ARQ, and `tests/test_webapp_packaging.py` builds the real artefacts to prove
they do not.

The version has exactly one source, `pyproject.toml`.
`opencloud_local_scan.__version__` derives it and the plugin imports that.
Never write the number anywhere else.

Every Docker file lives in `docker/` and every build context is the repository
root, because an image needs files from outside that directory. `.dockerignore`
stays in the root, where the daemon reads it from.

## Testing strategy

- `tests/fake_opencloud.py` is a real HTTP server driven by an
  `InstanceBehaviour` dataclass. Expectations come from an actual scan of it,
  because hardcoded lists go stale.
- `tests/test_e2e_cli.py` runs the plugin as a subprocess with a scrubbed
  environment, the way a monitoring daemon would.
- `tests/webapp_support.py` provides an isolated in-process Redis per test and
  an offline resolver; `COS_WEB_REDIS_URL=memory://` means the web tests need
  no Redis server.
- `tests/test_webapp_mcp.py`, `test_webapp_workflows.py`,
  `test_webapp_openapi.py`, `test_webapp_arazzo.py` and
  `test_webapp_discovery.py` hold the agent-facing surfaces to the API: that
  every `operationPath` resolves, that the documents agree with
  `workflows.py` rather than carrying their own numbers, and that a tool call
  is limited exactly as the equivalent request is.
- Tests are named as sentences describing the behaviour they protect, and
  assert the negative case as well as the positive one. An assertion that would
  still pass with the feature removed is worse than none.

## Where to add things

**A new scanner check** belongs in `opencloud_local_scan/`, with an entry in
`hardening.py` explaining it - and only after verifying against the OpenCloud
source that an operator can actually change the setting.

**A new plugin setting** touches seven places, all of them or it half-works:
`config.py` (only for a new default path), `factory.py`, the flag in
`check_opencloud_security.py`, the subcommand in `opencloud_local_scan/cli.py`,
the question in `wizard.py`, the option table in `README.md`,
`config/check-opencloud-security.example.yml`, plus `CHANGELOG.md` and
`RELEASE.md` under the version in `pyproject.toml`.

**A new `COS_WEB_*` setting** needs a field on `WebSettings` with a docstring
saying why it is not client-configurable, a line in `from_env`, a row in the
table in `docs/webapp.md`, an entry in `docker/docker-compose.yml`, and the
same changelog entries.

**A new API endpoint** needs its operation in `webapp/openapi.py`, a workflow
or a step in `webapp/arazzo.py` if it changes how the API is *used*, and a row
in the API table in `webapp/README.md` and `docs/webapp.md`.

**A new MCP tool** starts in `webapp/workflows.py`, where the task and its
rules belong, and `webapp/mcp_server.py` only exposes it - calling the HTTP API
in-process, never the internals. The description is written for an agent:
what it does, what it needs, how long it takes, what is retryable, and whether
it destroys anything. It needs a row in the tool tables in `docs/mcp.md`,
`webapp/README.md` and `docs/webapp.md`, and a test in
`tests/test_webapp_mcp.py` asserting it cannot outrun a limit the API applies.

**A new WebMCP tool** must represent an action already available on that
page. Build its schema from the same server-side catalogue as the controls,
register it through `_webmcp.html`, and execute through the public JSON API.
It needs a test that proves no server-only setting entered its schema.

**A durable decision** about a layer boundary, a public interface, the security
or deployment model, data lifecycle or a long-lived dependency needs an ADR.
Use the next never-reused number; supersede rather than rewrite.

## Trademarks and affiliation

This project is independent. It is **not** affiliated with, endorsed by,
sponsored by or supported by OpenCloud GmbH, and nothing it reports is an
official statement about OpenCloud software. "OpenCloud" and all related names
and marks belong to their respective owners and are used only to identify the
software being checked.
