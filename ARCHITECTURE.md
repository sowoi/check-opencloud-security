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
* [How settings reach the scanner](#how-settings-reach-the-scanner)
* [How a scan flows through the web application](#how-a-scan-flows-through-the-web-application)
* [Concurrency](#concurrency)
* [State and its lifetime](#state-and-its-lifetime)
* [The rating](#the-rating)
* [The release lifecycle](#the-release-lifecycle)
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
| `reports.py` | CSV, SARIF and the hand-written PDF |
| `arazzo.py` | The API described as executable workflows |
| `purge.py` | Erasure on request, and the receipt that proves it happened |
| `encryption.py` | Optional AES-256-GCM for results at rest |

`frontend/` holds every template and asset and no logic; `webapp/` holds no
markup. Nothing the browser loads comes from anywhere but `/static`, and the
CSP has no `unsafe-inline`, so there is no inline style, script or handler
anywhere.

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

## What ships where

| Artefact | Contents | Built by |
|:---------|:---------|:---------|
| PyPI wheel and sdist | The plugin and `opencloud_local_scan/` | `hatch`, excluding `webapp/` and `frontend/` |
| `check_opencloud_security_web.tar.gz` | The web application and its frontend | `scripts/build_web_bundle.py` |
| `docker/Dockerfile` | The plugin and the scanner service | The release workflow |
| `docker/Dockerfile.web` | The wheel plus the `web` extra, `webapp/`, `frontend/` | The release workflow |

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

**A new API endpoint** needs a workflow or a step in `webapp/arazzo.py` if it
changes how the API is used, and a row in the API table in `webapp/README.md`
and `docs/webapp.md`.

**A durable decision** about a layer boundary, a public interface, the security
or deployment model, data lifecycle or a long-lived dependency needs an ADR.
Use the next never-reused number; supersede rather than rewrite.

## Trademarks and affiliation

This project is independent. It is **not** affiliated with, endorsed by,
sponsored by or supported by OpenCloud GmbH, and nothing it reports is an
official statement about OpenCloud software. "OpenCloud" and all related names
and marks belong to their respective owners and are used only to identify the
software being checked.
