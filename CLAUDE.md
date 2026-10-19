# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

**`AGENTS.md` in the repository root is the authoritative rule set for this
project — read it before making non-trivial changes.** It covers ground rules
(no remote scan API, no real hostnames, never bump the version, no
Twitter/X/Google/Meta integrations), the rating and lifecycle invariants,
waivers, ADR policy, and the release process in depth. This file only adds
what's needed to get productive quickly; it does not restate AGENTS.md.

Project hooks in `.claude/settings.json` (scripts in `.claude/hooks/`) refuse
the irreversible commands and hand edits to generated files that AGENTS.md
forbids. **All work happens on the checked-out `release/` branch** - never
create or switch to a `feature/`, `fix/`, `chore/` or `docs/` branch;
`guard_branch.py` refuses it, and asks before a switch to `main`.
A refusal is final: report it to the user, never work around it.
The hooks match text, so a heredoc line that starts with such a command also
trips them - write that content with the Write tool instead. The privacy
guard (`privacy_guard.py`) refuses commits and pushes that carry a real
host, scan output or personal data; replace the value with
`opencloud.example.com` or a 192.0.2.x address, and never extend
`.claude/hooks/privacy_allowlist.txt` yourself - ask the user.

## What this project is

A Nagios/Icinga plugin (`check_opencloud_security.py`) that rates the security
of an OpenCloud instance using a **built-in scanner** — it never asks a remote
service for a verdict. `webapp/` is a separate public web service that runs
that same local scanner for a URL a stranger submits.

## Commands

```bash
uv run pytest                                       # full suite (~75s)
uv run pytest tests/test_webapp_api.py              # the web application (no Redis needed)
uv run playwright install webkit                    # once: the browser for the tests below and the MCP server
uv run pytest tests/test_webapp_browser_*.py        # the frontend in a real browser (ADR 0061)
uvx ruff@0.17.1 check .                             # linting, as CI runs it
uv run mypy --config-file mypy.ini                  # type checking
cd ansible && ansible-lint                          # must be run from ansible/
uv run nox                                          # full suite on Python 3.10-3.14
python scripts/build_web_bundle.py                  # builds the web release tarball
python scripts/build_wizard_release.py              # builds the stamped setup-wizard.py a release attaches
uv build && python scripts/build_distro_packages.py # builds the .deb and .rpm (needs nfpm)
python scripts/embed_wizard_blueprints.py           # after editing authentik/blueprints/ (--check verifies)
python scripts/update_golden_corpus.py --check      # the frozen verdicts still match
python scripts/check_documentation_links.py         # re-checks documented OpenCloud links
python scripts/security_advisories.py --check       # every ### Security entry is decided
python scripts/check_pull_request.py --base origin/main  # changelog entries and the version guard (local only)
npx @biomejs/biome@2.5.13 lint                     # frontend scripts (biome.jsonc)
uvx zizmor@1.30.1 .github/workflows                 # workflow security audit
cd docker && docker compose up --build              # web + worker + redis, locally
```

Notes that will otherwise cost you time:
- `pytest` exists **only** under `uv run`.
- Browsers are **WebKit (default), Firefox or Playwright's Chromium** - the
  last is Google's build, allowed for Blink coverage by
  [ADR 0068](adr/0068-chromium-is-a-third-browser-test-engine-behind-the-dead-proxy.md) -
  and always behind the dead proxy in `tests/browser_support.py`. The `playwright`
  MCP server in `.mcp.json` is the same reviewed package, loopback only.
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
- **Adding a setting touches many places** — use `/add-setting`, which lists
  them all.

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
- Every change needs an entry under `## [Unreleased]` in `CHANGELOG.md`. Never
  edit `RELEASE.md` — the release workflow writes it from that section, so it
  names the last release until the next one (ADR 0048).
- **A `### Security` changelog entry also needs a record in
  `security/advisories/`** in the same pull request — use
  `/security-fix-record`. **Never publish an advisory yourself.**
- **A new Python dependency** (in `pyproject.toml` or a workflow's `uvx`)
  needs a justified, tested, security-reviewed record in
  `security/dependencies/` first — use `/add-dependency` (ADR 0060). Draft it
  `proposed`; **only the maintainer approves it**, and
  `grandfathered.txt` never gains a name.

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
- **German text uses the informal "du"**, never `Sie`/`Ihr`/`Ihnen` —
  in `webapp/locales/de.py` and `docs/de/` alike; `tests/test_webapp_i18n.py`
  fails on a formal string in either.
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

## Documentation map

- `README.md` — operator reference (keep its table of contents in sync).
- `/documentation` (browser-facing CLI reference) is generated from
  `README.md` / `opencloud_local_scan/README.md` / `docs/` by
  `scripts/build_frontend_documentation.py` at build time — regenerate after
  changing a source; CI runs it with `--check`.
- `adr/` — architectural decision records; read ones relevant to an area
  before changing it, add a new one (never rewrite an accepted one) for a
  durable change to a layer boundary, public interface, security model, or
  long-lived dependency.
