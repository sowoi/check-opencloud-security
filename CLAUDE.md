# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

**`AGENTS.md` in the repository root is the authoritative rule set for this
project — read it before making non-trivial changes.** It covers ground rules
(no remote scan API, no real hostnames, never bump the version, no
Twitter/X/Google/Meta integrations), the rating and lifecycle invariants,
waivers, ADR policy, and the release process in depth. This file only adds
what's needed to get productive quickly; it does not restate AGENTS.md.

## What this project is

A Nagios/Icinga plugin (`check_opencloud_security.py`) that rates the security
of an OpenCloud instance using a **built-in scanner** — it never asks a remote
service for a verdict. `webapp/` is a separate public web service that runs
that same local scanner for a URL a stranger submits.

## Commands

```bash
uv run pytest                                       # full suite (~75s)
uv run pytest tests/test_waivers.py                 # one file
uv run pytest tests/test_waivers.py::test_name      # one test
uv run pytest -k "waiver and not rating"            # by expression
uv run pytest tests/test_webapp_api.py              # the web application (no Redis needed)
uvx ruff check .                                    # linting, as CI runs it
uv run mypy --config-file mypy.ini                  # type checking
cd ansible && ansible-lint                          # must be run from ansible/
uv run nox                                          # full suite on Python 3.10-3.14
python scripts/build_web_bundle.py                  # builds the web release tarball
python scripts/check_documentation_links.py         # re-checks documented OpenCloud links
cd docker && docker compose up --build              # web + worker + redis, locally
```

Notes that will otherwise cost you time:
- `pytest` exists **only** under `uv run`.
- Only `ruff check` is enforced, **never `ruff format`** — do not reformat the tree.
- `ansible-lint` is clean only from inside `ansible/`; from the repo root it reports false positives.
- `requires-python = ">=3.10"`: no `tomllib`, no 3.11+ syntax, no backslashes inside f-string expressions.
- Web tests need the `web` extra and the `test` dependency group, and run with `COS_WEB_REDIS_URL=memory://` (an in-process Redis stand-in) — no real Redis server needed.
- `subprocess` calls carry `# nosec B404/B603` comments for Bandit (CI runs it) — follow the existing style in `secrets.py`, `selfupdate.py`, `scripts/release_notes.py`.

## Architecture: three layers, boundaries are the point

```
opencloud_local_scan/  →  measures.  scan() returns a result document, never a verdict.
check_opencloud_security.py  →  judges.  Thresholds, exit codes, alert line, perfdata, webhook.
webapp/  →  serves.  Takes a URL from a stranger, hands it to the scanner, renders the answer.
```

A change that makes the library aware of WARNING/CRITICAL, has the plugin
issue its own HTTP probes, or has `webapp/` decide whether a finding is
acceptable, is in the wrong layer. Grades in the web UI come from the
plugin's `RATE_MAP`; `webapp/catalog.py` only regroups what the scanner
already produced.

Key modules (see `AGENTS.md` for the full table):
- `opencloud_local_scan/scanner.py` — the scan pipeline, findings, waivers, rating
- `opencloud_local_scan/versions.py` / `releases.py` — release lifecycle, update recommendations
- `opencloud_local_scan/tls.py` — transport security checks
- `opencloud_local_scan/hardening.py` — catalogue of every hardening identifier
- `opencloud_local_scan/config.py`, `factory.py` — configuration → frozen settings
- `webapp/workflows.py` — the one workflow layer (submit/poll/wait/complete/export semantics)
- `webapp/mcp_server.py`, `mcp_auth.py`, `prompts.py` — the MCP agent-facing layer
- `frontend/` — templates/CSS/JS the browser sees; `webapp/` holds no markup

### Settings flow in one direction

```
YAML/JSON file ─┐
environment  ───┼─→ config.Configuration ─→ factory.py ─→ frozen *Settings ─→ scanner
CLI flags    ───┘        (flat COS_ names)     (builds)       (dataclasses)
```

- `config.py` flattens nested keys into flat names: `scanner.target_port` in
  the file becomes `SCANNER_TARGET_PORT`, read from the environment as
  `COS_SCANNER_TARGET_PORT`. Lists are joined with `;`.
- Precedence is **CLI flag > environment variable > file > default**.
- `factory.py` is the only place configuration becomes `ScannerSettings` /
  `ReleaseSettings` (frozen dataclasses).
- A file ending in `.json` is parsed as JSON, anything else as YAML — format
  follows the suffix, not the content.
- **Adding one setting touches seven places**: `config.py` (only if a new
  default path), `factory.py`, the plugin flag in
  `check_opencloud_security.py`, the subcommand in
  `opencloud_local_scan/cli.py`, the question in `wizard.py`, the CLI option
  table in `README.md`, `config/check-opencloud-security.example.yml`, plus
  matching entries in `CHANGELOG.md` and `RELEASE.md` under the version in
  `pyproject.toml`.

### Conventions easy to get wrong

- **Result document keys are camelCase**, the plugin's own output is
  **snake_case**: `extraChecks`, `ratingExplanation`, `latestVersionInBranch`,
  the shouted `EOL` in the scan result vs. `failed_extra_checks`,
  `plugin_version`, `rating_label` in the webhook payload.
- **Concurrency is per call site and must never nest.** `_run_all(settings,
  tasks)` creates its own `ThreadPoolExecutor` and preserves submission order
  via `pool.map` (order preservation is load-bearing, has tests). Default
  worker count is `1` (sequential).
- **`requests.Session` is not thread-safe.** `_Probe` keeps a
  `threading.local` session per worker; use `_Probe.derive(url)` to probe a
  second base URL rather than sharing a session by hand.
- **The version has exactly one source: `pyproject.toml`.**
  `opencloud_local_scan.__version__` derives it; never write a literal
  `__version__ = "x.y.z"`, and never bump the number yourself — that is the
  user's decision and a bump landing on `main` publishes to PyPI immediately.
- **The release schedule table in `README.md` is generated** between
  `<!-- release-schedule:start -->` / `<!-- release-schedule:end -->` by
  `scripts/update_release_schedule.py` — never edit it by hand.
- Every change needs entries in both `CHANGELOG.md` and `RELEASE.md` under the
  version currently in `pyproject.toml`.

## The web application (`webapp/` + `frontend/`)

- **Never ships to PyPI.** The wheel/sdist exclude `webapp/` and `frontend/`;
  it ships as `check_opencloud_security_web.tar.gz` via
  `scripts/build_web_bundle.py`. Enforced by `tests/test_webapp_packaging.py`.
- **A request chooses what to scan, never how hard.** Only `target_url`,
  `ignore_hardenings`, `release_track`, `output_format` are accepted fields;
  anything else is a 422. Concurrency/timeouts/TLS policy are `COS_WEB_*` env
  vars with no request-side equivalent.
- **Overload queues, never 503s.** Submissions past the worker count get a
  uuid and wait FIFO.
- **A uuid is a capability**: own `scan:{uuid}:*` Redis namespace with a TTL;
  unknown/invalid/expired all answer 404; there is no listing endpoint.
- **No Twitter/X, Google, or Meta integrations anywhere** — no fonts,
  analytics, CDNs, sign-in, share buttons, or card metadata naming them.
  Enforced by `tests/test_webapp_seo.py` and the third-party check in
  `tests/test_webapp_api.py`.
- **The frontend is fully self-hosted**, no CDN/Bootstrap/Tailwind/font
  service. CSP has no `unsafe-inline` — no `style=`, `<style>`, `onclick`, or
  inline `<script>`; use utility classes / `[data-...]` rules in `app.css`
  instead.
- **The release schedule and advisory database refresh themselves daily**
  from published sources (`webapp/schedule.py`, `webapp/advisories.py`) and
  may only *gain* knowledge, never lose it on a bad fetch. See
  [ADR 0016](adr/0016-the-release-schedule-refreshes-itself.md) and
  [ADR 0017](adr/0017-the-advisory-database-refreshes-itself.md).
- **MCP (`webapp/mcp_server.py`) calls this service's own HTTP API
  in-process**, never internals directly — that's what makes the SSRF guard,
  rate limit, cooldown, and queue apply to agents the same as browsers. See
  [ADR 0011](adr/0011-mcp-is-an-execution-layer-not-a-second-implementation.md).

## Tests

- `tests/fake_opencloud.py` is a real HTTP server driven by an
  `InstanceBehaviour` dataclass — use it rather than mocking `requests`, and
  derive expectations from an actual scan of it (hardcoded lists go stale).
- `tests/conftest.py` has two autouse fixtures: one strips every `COS_`
  environment variable, one stubs `time.sleep` for retry/backoff tests.
- `tests/webapp_support.py` holds web fixtures: an isolated in-process Redis
  per test and an offline resolver (`example.com` doesn't resolve).
- Name tests as sentences describing the behaviour they protect (e.g.
  `test_a_waived_check_no_longer_caps_the_rating`) with a one-line docstring
  explaining why it matters. **Assert the negative case as well as the
  positive one.**

## Documentation map

- `README.md` — operator reference (keep its table of contents in sync).
- `opencloud_local_scan/README.md` — the scanner library/service.
- `webapp/README.md` and `docs/webapp.md` — the web application (API,
  Swagger, input restrictions, template contract vs. operator's view).
- `docs/` — deployment guides, indexed by `docs/README.md`.
- `/documentation` (browser-facing CLI reference) is generated from
  `README.md` / `opencloud_local_scan/README.md` / `docs/` by
  `scripts/build_frontend_documentation.py` at build time — regenerate after
  changing a source; CI runs it with `--check`.
- `adr/` — architectural decision records; read ones relevant to an area
  before changing it, add a new one (never rewrite an accepted one) for a
  durable change to a layer boundary, public interface, security model, or
  long-lived dependency.
