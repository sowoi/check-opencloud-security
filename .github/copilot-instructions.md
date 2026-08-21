# Copilot instructions for check-opencloud-security

A Nagios/Icinga plugin that rates the security of an OpenCloud instance, plus
the scanner library it is built on.

[`AGENTS.md`](../AGENTS.md) in the repository root is the authoritative rule
set - **read it before making changes.** It covers the ground rules, the
rating and lifecycle invariants, waivers, and the release process in more
depth than this file. What follows is the working context and the parts that
only become visible after reading several files.

## Commands

```bash
uv run pytest                                       # full suite (~75s)
uv run pytest tests/test_waivers.py                 # one file
uv run pytest tests/test_waivers.py::test_name      # one test
uv run pytest -k "waiver and not rating"            # by expression
uvx ruff check .                                    # linting, as CI runs it
uv run mypy --config-file mypy.ini                  # type checking
cd ansible && ansible-lint                          # must be run from ansible/
uv run nox                                          # the suite on 3.10 - 3.14
uv run pytest tests/test_webapp_api.py              # the web application
python scripts/build_web_bundle.py                  # the release tarball
python scripts/check_documentation_links.py         # the documented OpenCloud links
cd docker && docker compose up --build              # web + worker + redis
```

- `pytest` exists **only** under `uv run`.
- Only `ruff check` is enforced, **never `ruff format`**. Do not reformat the
  tree; a formatting-only diff will be rejected.
- `ansible-lint` is clean only from inside `ansible/`. From the repository root
  it reports dozens of false positives.
- `requires-python = ">=3.10"`. No `tomllib`, no 3.11+ syntax, and no
  backslashes inside f-string expressions.
- Bandit runs in CI. `subprocess` use carries `# nosec B404/B603` comments -
  follow the existing style in `secrets.py`, `selfupdate.py` and
  `scripts/release_notes.py`.
- The web tests need no Redis server: `COS_WEB_REDIS_URL=memory://` selects an
  in-process stand-in, and the fixtures in `tests/webapp_support.py` set it.

## Architecture

**Three layers, and the boundaries between them are the point.**

`opencloud_local_scan/` **measures**. `scan()` returns a result document and
never decides whether that is acceptable. `check_opencloud_security.py`
**judges**: thresholds, exit codes, the alert line, perfdata and the webhook.
`webapp/` **serves**: it takes a URL from a stranger, hands it to the scanner
and renders what comes back. A change that makes the library aware of
WARNING/CRITICAL, the plugin issue its own HTTP probes, or the web application
decide whether a finding is acceptable, is in the wrong layer. Grades in the
web UI come from the plugin's `RATE_MAP`; `webapp/catalog.py` only regroups
the document the scanner already produced.

**Settings flow in one direction:**

```
YAML/JSON file ─┐
environment  ───┼─→ config.Configuration ─→ factory.py ─→ frozen *Settings ─→ scanner
CLI flags    ───┘        (flat COS_ names)     (builds)       (dataclasses)
```

- `config.py` flattens nested keys into flat `COS_`-style names:
  `scanner.target_port` in the file becomes `SCANNER_TARGET_PORT`, read from
  the environment as `COS_SCANNER_TARGET_PORT`. Lists are joined with `;`.
- Precedence is **CLI flag > environment variable > file > default**, and both
  CLIs implement it by passing `None` for "not specified" into `factory.py`.
- `factory.py` is the only place that turns configuration into
  `ScannerSettings` / `ReleaseSettings`. Both are frozen dataclasses.
- A file ending in `.json` is parsed as JSON, anything else as YAML. Format
  follows the **suffix**, not the content.

**Adding one setting touches seven places.** All of them, or it half-works:
`config.py` (only if a new default path), `factory.py`, the plugin flag in
`check_opencloud_security.py`, the subcommand in `opencloud_local_scan/cli.py`,
the question in `wizard.py`, the CLI option table in `README.md`,
`config/check-opencloud-security.example.yml`, plus matching entries in
`CHANGELOG.md` and `RELEASE.md` under the version declared in `pyproject.toml`.

**Plugin startup order** in `check_opencloud_security.py`:
`_run_early_commands()` → `_preparse_config()` → `_set_configuration()` →
`build_arg_parser()` → `parse_args()`. `--host` is
`required=_env("HOST") is None`, so any mode that does not scan (`--configure`,
`--upgrade-self`) must be intercepted in `_run_early_commands()`, before the
parser that insists on a host is ever built.

## Architectural decision records

[`adr/README.md`](../adr/README.md) defines the format and lifecycle for
architectural decision records. Read accepted ADRs relevant to an area before
changing it. Add one for a durable change to a layer boundary, public
interface, security or deployment model, data lifecycle, or long-lived
dependency - not for routine implementation details or temporary tasks.

Use the next zero-padded, never-reused number. Accepted ADRs are historical
records: supersede a decision with a new ADR rather than rewriting it.

## Conventions that are not obvious from one file

**Result document keys are camelCase, the plugin's own output is snake_case.**
`extraChecks`, `ratingExplanation`, `latestVersionInBranch`, `productname` and
the shouted `EOL` in the scan result; `failed_extra_checks`, `plugin_version`,
`rating_label` in the webhook payload. Guessing wrong here costs a test round
trip.

**Concurrency is per call site and must never nest.** `_run_all(settings,
tasks)` creates its own `ThreadPoolExecutor` and preserves submission order via
`pool.map` - order preservation is load-bearing and has tests. Group-level
parallelism in `_collect_extra_findings` was deliberately left out because it
would multiply the worker count. Default is `1`, meaning genuinely sequential.

**`requests.Session` is not thread-safe.** `_Probe` keeps a `threading.local`
session per worker and records an `_owner` thread id. Use `_Probe.derive(url)`
to probe a second base URL; never share a session across probes by hand.

**The release table in `README.md` is generated.** Everything between
`<!-- release-schedule:start -->` and `<!-- release-schedule:end -->` is
written by `scripts/update_release_schedule.py` from the release schedule, by
the release workflow and by the weekly refresh, which commit both files
together. Never edit it by hand, never remove the markers (that is a hard
error), and regenerate after changing `render_readme_block()`. The prose
around it is hand-written and names older releases on purpose.

**The version has exactly one source: `pyproject.toml`.**
`opencloud_local_scan.__version__` derives it (package metadata when installed,
the file itself in a checkout) and the plugin imports that. Never write a
`__version__ = "x.y.z"` literal - `tests/test_version.py` fails if you do. And
never bump the number: a bump landing on `main` publishes to PyPI.

**Document every change in both `CHANGELOG.md` and `RELEASE.md` under the
version declared in `pyproject.toml`.** Never invent or bump a version number;
the user decides that number.

**Some hardening findings can never be fixed.** Flags OpenCloud hardcodes are
marked `actionable=False` in `hardening.py`: they stay in the result document
but out of the alert line, the `hardenings_missing` metric and the webhook.
Verify against the OpenCloud source that an operator can change a setting
before adding a check for it.

**Never write a real hostname, IP address or token** into code, tests, fixtures,
documentation or a commit message. `opencloud.example.com` is the placeholder
used throughout.

## The web application and the frontend

**`webapp/` and `frontend/` never reach PyPI.** The wheel and the sdist
exclude both, and `tests/test_webapp_packaging.py` builds the real artefacts to
prove it. The service ships as `check_opencloud_security_web.tar.gz`, built by
`scripts/build_web_bundle.py` and attached to the GitHub release. A monitoring
host installing the plugin must not receive FastAPI, Redis or ARQ.

**Every container file lives in `docker/`, and every build context is the
repository root.** `docker/Dockerfile` is the plugin, `docker/Dockerfile.web`
is the web image, `docker/docker-compose.yml` is the ready-to-run stack
(`web_app`, `arq_worker`, `redis`), `docker/docker-compose.authentik.yml` the
same stack plus Authentik for a sign-in on `/mcp`, and
`docker/docker-compose.monitoring.yml` is the plugin's unrelated scan service. Build with
`docker build -f docker/Dockerfile.web .` from the root; run compose from
inside `docker/`, where the paths point one level up. `.dockerignore` stays in
the root - the daemon reads it from the context, not from next to the
Dockerfile.

**`docker/setup-wizard.py` generates a deployment, it does not configure the
plugin.** It is standalone and stdlib-only, asks question by question with an
explanation and an example, and writes a commented compose file plus a `.env`
holding every credential the compose file refers to as `${NAME}` - a secret
never lands in the compose file, and `.env` is created `0600`. It refuses to
overwrite the compose files that ship in `docker/`. Keep it independent of
`opencloud_local_scan.wizard`, which sets up a monitoring check;
`tests/test_docker_wizard.py` asserts both the split and the independence.

**A request chooses what to scan, never how hard.** `target_url`,
`ignore_hardenings`, `release_track`, `output_format` - and nothing else,
which is a **422** naming the field. `release_track` rates the version against
`rolling`, `production` or `lts` and defaults to `production`; an unknown
value falls back rather than failing. Concurrency, worker counts, timeouts and TLS verification
are `COS_WEB_*` environment variables with no request-side equivalent.

**Overload queues, it does not fail.** Submissions past the worker count are
accepted, get a uuid and wait in FIFO order with the position on screen. A
valid submission never gets a 503.

**The release schedule refreshes itself, and may only gain knowledge.** The
schedule CI commits is frozen the moment an image is built, so the worker
re-reads the published lifecycle page once a day (`webapp/schedule.py`,
`COS_WEB_SCHEDULE_REFRESH`, on by default) and keeps it in Redis, where each
scan picks it up. There is one parser -
`opencloud_local_scan/schedule_source.py`, which `scripts/` also uses - and a
candidate document is accepted only when it still knows every line the bundled
file knows, because losing a line turns an end-of-life instance into an
unknown one. A failed, redesigned or truncated page changes nothing, a newer
bundled file wins after a redeployment, and nothing is ever written back to
`README.md` or the bundled JSON: those stay CI's. The plugin does not do this
- a check running every few minutes must not become a documentation fetch.
See [ADR 0016](../adr/0016-the-release-schedule-refreshes-itself.md).

**The advisory database refreshes itself, and may only gain advisories.**
Same reason, higher stakes: a database that has not heard of last month's
advisory does not grade an instance generously, it tells a visitor a
vulnerable instance is fine. The worker asks the advisory feed once a day
(`webapp/advisories.py`, `COS_WEB_ADVISORY_REFRESH`, on by default) and the
scan jobs rate against the answer. One reader again -
`opencloud_local_scan/advisory_source.py`, which `scripts/` and CI also use -
and the acceptance rules are the mirror image, because this can fail by
*gaining* an advisory as well as by losing one: a refresh only ever adds, so a
feed answering with an empty list changes nothing; **nothing unbounded is ever
believed**, because an advisory naming no versions matches every release there
has ever been and public feeds do publish that shape; an absurd number of
advisories is refused whole; and any failure leaves the database as it was.
One advisory can affect several release lines patched separately, so every
range is kept and the fix reported is the one for the line the instance is
actually on. Nothing is written to disk. See
[ADR 0017](../adr/0017-the-advisory-database-refreshes-itself.md).

**A uuid is a capability.** Own `scan:{uuid}:status|result|metadata`
namespace, TTL on every key, no listing endpoint ever, and unknown, invalid
and expired all answer the same **404**. Logs carry lifecycle markers and the
uuid only - never a target URL, a client address or a result.

**A rate limit is a friendly nudge, not a door slammed.** The 429 apologises
casually and points at
<https://github.com/sowoi/check-opencloud-security> so the visitor can run the
same check themselves with no limits. Keep both channels working: the template
branch behind `error_self_host` and the JSON `hint` / `selfHostUrl` fields.

**Never wire anything to Twitter/X, Google or Meta.** No script, stylesheet,
font, iframe, image, API, SDK, analytics, tag manager, CAPTCHA, sign-in, share
button or embed, and no card metadata naming them - no `twitter:`, no `fb:`,
no `google-site-verification`. This covers the web application, the frontend,
the scanner, the plugin, the container images, the CI workflows and the
documentation, and it covers dependencies that would phone one of them home. A
visitor hands this service the address of a system they are responsible for,
and the referrer on a result page carries a uuid that is the whole of the
authorisation. Plain links a person clicks are fine, and so is
platform-neutral metadata nothing fetches, such as OpenGraph `og:` tags.
`tests/test_webapp_seo.py` fails on the metadata; the third-party test in
`tests/test_webapp_api.py` fails on any foreign origin at all. `AGENTS.md`
lists the named services under **Third parties**.

**The frontend is hand-written and self-hosted, without exception.** No
Bootstrap, no Tailwind, no CDN, no font service, no analytics - every byte
comes from `/static/`, and a test asserts it. The CSP has no `unsafe-inline`,
so there are no `style=` attributes, no `<style>` blocks, no `onclick` and no
inline `<script>`; one-off styles become utility classes or `[data-...]` rules
in `app.css`. Reference assets as `/static/...` rather than `url_for`, which
emits an absolute URL. Keep the markup semantic and accessible - landmarks,
real labels, `aria-live` on the progress region, `prefers-reduced-motion`
honoured - and keep the SVGs hand-drawn rather than stock. Starlette needs
`TemplateResponse(request, name, context, status_code=...)`.

**Every user-facing surface carries the trademark notice.** This project is
independent: not affiliated with, endorsed by or supported by OpenCloud GmbH,
and "OpenCloud" and its marks belong to their owners, used only to identify the
software being checked. The notice lives in `README.md`, `docs/README.md`,
`docs/webapp.md`, `opencloud_local_scan/README.md`, the footer of
`frontend/templates/base.html` and the generated `QUICKSTART.md`. Do not
remove it, do not imply a partnership, and add it to any new user-facing page.

## The agent-facing surfaces

**One workflow layer, three descriptions.** `/openapi.json` says which
operations exist, `/arazzo.json` how they combine into a task, `/mcp` executes
it, and `/.well-known/ai.json` is how anything finds the other three. The
semantics live once in `webapp/workflows.py` - the submission status, the poll
interval, the attempt ceiling, that a `404` is final and a `409` means *not
yet*. `webapp/arazzo.py` reads those constants and `webapp/mcp_server.py`
calls those functions; a test fails if either invents its own number. See
[ADR 0011](../adr/0011-mcp-is-an-execution-layer-not-a-second-implementation.md).

**MCP calls this service's own HTTP API in-process**, never the internals, so
the SSRF guard, the client rate limit, the target cooldown, the queue and the
authorisation on erasure are the real ones. An agent must not reach a code
path a browser could not, nor be rationed more generously.
`COS_WEB_MCP_MAX_CONCURRENT_WAITS` bounds waiting calls and refuses nothing:
the uuid comes back with a note to poll.

**Six tools, and they are tasks rather than endpoints**: `scan_instance`,
`scan_instances`, `get_scan_result`, `plan_remediation`, `export_scan`,
`erase_instance_data`, plus three `spec://` resources for the OpenAPI, Arazzo
and discovery documents. Descriptions are written for an agent - inputs,
outputs, duration, retryability, when to stop - and a destructive tool says so.
Never hold, log or return a credential; validate a uuid as a uuid before it
reaches a request path. A scanned host's version, product name and error text
stay collapsed, stripped, truncated and inside the `untrusted` block.

**Prompts are tasks a person asks for**, and their wording lives once in
`webapp/prompts.py`, composed from the notes and constants in
`webapp/workflows.py`. A prompt names tools rather than endpoints - the tools
carry the limits - and it decides nothing: it quotes the workflow layer's
numbers, the scanner's ordering and the plugin's grades. The catalogue is
published in the `mcp.prompts` block of `/.well-known/ai.json`. A new one
needs a row in `docs/mcp.md`, `webapp/README.md` and `docs/webapp.md` and a
test in `tests/test_webapp_mcp.py`. See
[ADR 0014](../adr/0014-prompts-are-tasks-and-their-text-lives-beside-the-workflows.md).

**`/mcp` is open unless an operator says otherwise.** `webapp/mcp_auth.py`
makes it an OAuth 2.0 *resource server* when `COS_WEB_MCP_AUTH_ENABLED` and an
issuer are set: a bearer token verified offline against the provider's
published JWKS, asymmetric algorithms only, RFC 9728 metadata at
`/.well-known/oauth-protected-resource/mcp` and a `401` naming it. Issue,
store or accept nothing of your own, and never let a sign-in change a limit -
**authentication decides who may ask, never how hard**. A deployment that
cannot enforce the sign-in it asked for refuses to start; one that asked with
`/mcp` switched off does not. With a sign-in on, the purge credential moves to
`X-Purge-Authorization` with no fallback. `docs/authentik.md` and
[ADR 0015](../adr/0015-the-mcp-endpoint-may-require-a-sign-in.md).

**The four documents are public and unauthenticated.** `COS_WEB_ENABLE_DOCS`
governs only `/docs` and `/redoc`; `COS_WEB_ENABLE_MCP` turns the endpoint off
and the discovery document then stops naming it. A new tool needs a row in
`docs/mcp.md`, `webapp/README.md` and `docs/webapp.md` and a test in
`tests/test_webapp_mcp.py`.

## Tests

- `tests/fake_opencloud.py` is a real HTTP server driven by an
  `InstanceBehaviour` dataclass. Use it rather than mocking `requests`, and
  derive expectations from an actual scan of it - hardcoded lists go stale.
- `tests/conftest.py` has two autouse fixtures: one strips every `COS_`
  variable so a developer's environment cannot change argparse defaults, and
  one stubs `time.sleep` so retry/backoff tests do not really wait.
- `tests/test_e2e_cli.py` runs the plugin as a subprocess with a scrubbed
  environment, the way a monitoring daemon would.
- `tests/webapp_support.py` holds the web fixtures: an isolated in-process
  Redis per test and an offline resolver, since `example.com` names do not
  resolve. Do not reach for a mock of `requests` in either suite.
- Name a test as a sentence describing the behaviour it protects
  (`test_a_waived_check_no_longer_caps_the_rating`) with a one-line docstring
  saying why that behaviour matters. **Assert the negative case as well as the
  positive one** - an assertion that would still pass with the feature removed
  is worse than none.

## Documentation

`README.md` is the operator reference and carries a table of contents that must
stay in sync with its headings. `opencloud_local_scan/README.md` documents the
library and the HTTP service, and `webapp/README.md` the web application and
its frontend (API, Swagger, input restrictions, template contract) while
`docs/webapp.md` is the operator's view of it. `docs/` holds the deployment guides and worked
examples; a new page there needs a row in the README's guide table and one in
`docs/README.md`. Links inside `docs/` reach the README one level up
(`../README.md#anchor`).
