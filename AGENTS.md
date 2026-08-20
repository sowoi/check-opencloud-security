# AGENTS.md

Guidance for AI coding agents working on **check-opencloud-security**
(version **1.0.0**).

## What this project is

A Nagios/Icinga plugin that checks an OpenCloud instance for known
vulnerabilities and misconfiguration, plus the scanner library it is built on.

The single most important fact about it: **the plugin uses a built-in
scanner.** It never asks a remote service for a verdict - everything it
reports it works out itself by talking to the instance over HTTP. The ratings
follow the `0`-`5` scale of the Nextcloud scan API purely so that existing
thresholds, graphs and alert rules keep their meaning - that is the only place
Nextcloud may be mentioned. Do not introduce API clients, tokens or endpoints
for a remote scan service.

## Layout

| Path | What lives there |
|:-----|:-----------------|
| `check_opencloud_security.py` | The plugin: CLI, output, exit codes, perfdata, webhook |
| `opencloud_local_scan/scanner.py` | The scan pipeline, findings, waivers and the rating |
| `opencloud_local_scan/versions.py` | The release lifecycle model (tracks, lines, end of life) |
| `opencloud_local_scan/releases.py` | The update check and its track-aware recommendation |
| `opencloud_local_scan/tls.py` | Transport security: protocol, certificate, chain, stapling |
| `opencloud_local_scan/hardening.py` | Catalogue explaining every hardening identifier |
| `opencloud_local_scan/config.py`, `factory.py` | Configuration, secrets, settings construction |
| `opencloud_local_scan/wizard.py` | The interactive setup behind `--configure` |
| `opencloud_local_scan/selfupdate.py` | `--upgrade-self`, via pipx, uv or pip |
| `opencloud_local_scan/data/release_schedule.json` | Bundled release schedule |
| `scripts/update_release_schedule.py` | Regenerates that file from the published documentation |
| `scripts/release_notes.py` | Turns `## [Unreleased]` into the notes of a release |
| `scripts/check_documentation_links.py` | Re-checks every documented OpenCloud link after a merge into `main` |
| `adr/` | Durable architectural decision records |
| `webapp/` | The public scan service: FastAPI, the ARQ worker, SSRF and rate limits |
| `webapp/workflows.py` | What a *task* means: submit, poll, wait, complete, export |
| `webapp/openapi.py`, `arazzo.py`, `discovery.py` | The written contracts and `/.well-known/ai.json` |
| `webapp/mcp_server.py` | The MCP endpoint: those workflows, executed for an agent |
| `frontend/` | Everything the browser sees: templates, CSS, JavaScript, SVG |
| `scripts/build_web_bundle.py` | Builds the GitHub release tarball of the web application |
| `tests/` | Test suite, including `tests/fake_opencloud.py` |
| `docker/` | Every Dockerfile and compose file; the build context is the repository root |
| `ansible/`, `contrib/`, `config/` | Deployment role, Icinga definitions, example config |
| `docs/` | Deployment guides and worked examples, indexed by `docs/README.md` |

## Ground rules

- **Do not reference any real instance.** The project is tested against a live
  server, but its hostname must never appear in code, tests, documentation or
  commit messages. Use `opencloud.example.com` in examples.
- **Do not add a remote scan API.** See above. The web application in
  `webapp/` is a *service that runs the local scanner*, not a verdict the
  plugin asks somebody else for - the plugin must never call it.
- **The web application never ships to PyPI.** `webapp/` and `frontend/` are
  excluded from the wheel and the sdist, and a test enforces it.
- **Never bump the version.** See [Versioning and
  releases](#versioning-and-releases) - that is the user's decision alone.
- **`pyproject.toml` is the only place the version is written.**
  `opencloud_local_scan.__version__` derives it from there (package metadata
  when installed, the file itself in a checkout) and the plugin imports that.
  Never reintroduce a literal - that is how the numbers drifted apart before.
- **Never connect this project to Twitter/X, Google or Meta.** No script, no
  stylesheet, no font, no iframe, no image, no API, no SDK, no analytics, no
  tag manager, no CAPTCHA, no sign-in, no share button, no embed, and no
  card metadata naming any of them. This holds for the web application, the
  frontend, the plugin, the scanner, the container images, the CI workflows
  and the documentation alike. A visitor here is handing over the address of
  a system they are responsible for; a request to one of those platforms
  turns that into a record somebody else keeps. Platform-neutral, request-free
  metadata such as OpenGraph `og:` tags is fine, because nothing fetches it.
  See [Third parties](#third-parties).
- Comment only what needs clarification. Explain *why*, not *what*.

## Versioning and releases

**The version is bumped manually by the user, never by an agent.** Do not edit
the `version` in `pyproject.toml` - it is the *only* place the number is
written. `opencloud_local_scan.__version__` derives it from there and
`check_opencloud_security.py` imports that, so there is nothing to keep in
sync. Do not create tags or releases either. Deciding that a set of changes is
a patch, a minor or a major release is a judgement call about the project, not
a mechanical step - and a bump that lands on `main` publishes to PyPI
immediately.

**Every change must be documented in both `CHANGELOG.md` and `RELEASE.md`
under the version currently declared in `pyproject.toml`.** Read that version
before editing either file, add the entry to the matching Keep a Changelog
section (`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, or
`Documentation`), and keep the two release notes consistent. Never invent or
bump a version heading yourself.

When the user bumps the version, `scripts/release_notes.py` prepares the notes
for that `pyproject.toml` version and writes `RELEASE.md` for the GitHub
release. Keep the release documents synchronized before that workflow runs.

Preview what the next release would look like. It rewrites `CHANGELOG.md` and
`RELEASE.md`, so do it on a scratch copy or revert afterwards:

```bash
python scripts/release_notes.py --version 0.0.0 --date 2000-01-01
git checkout CHANGELOG.md RELEASE.md
```

`--require-unreleased` makes the script fail rather than fall back to
generating notes from commit subjects.

## Architectural decision records

[`adr/README.md`](adr/README.md) defines the format and lifecycle for
architectural decision records. Read the accepted ADRs relevant to an area
before changing it. Add an ADR for a durable change to a layer boundary, public
interface, security or deployment model, data lifecycle, or long-lived
dependency. Do not create one for routine implementation details or temporary
tasks.

Use the next zero-padded, never-reused number. Accepted ADRs are historical
records: do not rewrite their decision. When one changes, add a new ADR and
mark the older record as superseded.

## Working on the rating

The rating starts from the version and advisory database, then failed checks
cap it (`SEVERITY_RATING_CAP`: critical 2, high 3, medium 4, low 5). Two
invariants are load-bearing and have tests to match:

- **The explanation must not depend on iteration order.** A cap counts as
  *applied* when it equals the final rating, never "whichever came first".
- **End of life overrides everything**, including a wildcard waiver. A release
  that receives no security fixes is an F.

## The generated release table in the README

`scripts/update_release_schedule.py` writes
`opencloud_local_scan/data/release_schedule.json` **and** the block between
`<!-- release-schedule:start -->` and `<!-- release-schedule:end -->` in
`README.md`, which names the current release of each track. Both the release
workflow and the weekly schedule workflow commit the two together.

- **Do not edit that block by hand** - the next refresh overwrites it, and
  `tests/test_update_script.py` fails if it does not match the schedule that
  ships beside it.
- Removing the markers is an error, not a no-op: a README that quietly stops
  being updated is worse than one that never was.
- Change the rendering in `render_readme_block()`, then run
  `python scripts/update_release_schedule.py` to regenerate.
- The prose and the worked examples around the block are hand-written and
  deliberately name older releases; leave them alone.

## Working on the lifecycle

OpenCloud ships rolling (~3 weeks), production (~6 months) and LTS (2 years)
releases side by side. Releases group into **lines** (`MAJOR.MINOR`), and one
line can belong to several tracks.

- rolling and production expire when the next release on the same track ships;
  LTS expires on the clock.
- A **newer version can be less supported than an older one**. This is not a
  bug to fix.
- **Ahead of your track is not end of life.** A release newer than the current
  release of the declared track is reported as ahead of it and stays out of the
  `F` verdict; only a release *behind* it is unsupported. `auto` is a fourth
  accepted value of `--release-track` and means "infer it", exactly as leaving
  it unset does.
- An upgrade recommendation must only ever point *forwards*, and must never
  move a production or LTS instance onto the rolling track.

## Working on waivers

`--ignore-hardening` / `scanner.ignore_hardenings` suppresses an alert, not the
evidence. A waived finding stays in the result document with
`"ignored": true` and is still explained by `--debug`. Only a finding that
**actually failed** may be waived, so that a waiver cannot silently become a
blind spot when a measure regresses.

## Some findings can never be fixed

Several flags OpenCloud hardcodes in `services/frontend/pkg/revaconfig/config.go`
are not settings at all - `publicLinkExpirationEnforced` fails on every
instance in existence. These are marked `actionable=False` in
`hardening.py` and stay out of the alert line, the `hardenings_missing` metric
and the webhook, while remaining in the result document. Before adding a
hardening check, verify against the OpenCloud source that an operator can
actually change it.

## Working on the web application

`webapp/` is a third layer, and it *serves*. `opencloud_local_scan` measures,
`check_opencloud_security.py` judges, and the web application takes a URL from
a stranger, hands it to the scanner and renders the answer. A check
reimplemented in `webapp/`, or a rating decided there, is in the wrong layer -
grades come from the plugin's `RATE_MAP` and `catalog.summarise()` only
regroups the document the scanner already produced.

**It is not on PyPI, and that is a packaging rule with a test.** The wheel and
the sdist exclude `webapp/` and `frontend/`; the web application ships as
`check_opencloud_security_web.tar.gz`, built by
`scripts/build_web_bundle.py`. Somebody installing a monitoring plugin must
not receive FastAPI, Redis and ARQ. `tests/test_webapp_packaging.py` builds
the real artefacts and fails if that ever changes.

**A request may choose what to scan, never how hard.** The only accepted
fields are `target_url`, `ignore_hardenings`, `release_track` and
`output_format`; anything else is a **422** naming the field. Each of them is
a fact about the instance or about presentation, never about load: the track
changes how a version is *rated*, not how hard it is *probed*, and it falls
back to `production` when it is missing or unknown. Concurrency, worker counts, timeouts and
TLS verification come from `COS_WEB_*` environment variables and have no
request-side equivalent. Adding one would make a public service into an
amplifier.

**Overload is a queue, not an error.** A submission past the worker count is
accepted, gets a uuid and waits in FIFO order with its position shown. Never
answer a valid submission with a 503.

**The uuid is a capability.** Every scan gets its own `scan:{uuid}:*` Redis
namespace, every key carries the TTL, and unknown, invalid and expired all
return the same **404**. Never add a listing endpoint, never make a uuid
guessable, and never let one scan read another's keys.

**Log lifecycle markers and a uuid, nothing else.** No target URLs, no client
addresses, no results. A log of what everybody scanned is a database of what
everybody scanned.

**A rate limit is not a rejection - it is an invitation.** Whoever hits one
gets a friendly, casual message and a pointer to
<https://github.com/sowoi/check-opencloud-security>, because the whole check
is open source and runs on their own machine without any limit at all. Keep
that tone: apologetic rather than officious, and keep the link, in the HTML
response (`error_self_host`) as well as the JSON one (`hint`,
`selfHostUrl`).

## Working on the agent-facing surfaces

`/openapi.json` says which operations exist, `/arazzo.json` how they combine
into a task, `/mcp` lets an agent perform it, and `/.well-known/ai.json` is
how anything finds the other three. `ARCHITECTURE.md` draws the shape;
[ADR 0010](adr/0010-machine-readable-descriptions-are-always-public.md) and
[ADR 0011](adr/0011-mcp-is-an-execution-layer-not-a-second-implementation.md)
hold the decisions.

**There is one workflow layer and it is `webapp/workflows.py`.** The status a
submission answers with, the poll interval, the attempt ceiling, that a `404`
is final and a `409` means *not yet* - all of it lives there once. The Arazzo
document reads those constants and the MCP tools call those functions; a test
fails if either writes its own number. Change the behaviour there, not in a
description of it.

**MCP executes by calling this service's own HTTP API in-process.** Never the
internals, never a second path. That is what makes the SSRF guard, the client
rate limit, the target cooldown, the queue and the authorisation on erasure
the real ones. An agent must not be able to reach a code path a browser could
not, nor be rationed more generously than a browser is - a tool that skips a
limit has turned the endpoint into a way around it.

**Tools are user-level tasks, not endpoints.** `scan_instance`,
`scan_instances`, `get_scan_result`, `plan_remediation`, `export_scan`,
`erase_instance_data`. Do not add a tool per route: an agent asked to scan an
instance should call one tool, not orchestrate a submission and thirty polls.
Write the description *for an agent* - inputs, outputs, how long it takes,
what is retryable, when to stop, when to ask the user - and mark a destructive
one as destructive.

**A scanned host is not to be trusted with the model's attention.** A version
string, a product name and an error message are chosen by somebody else's
server. They stay collapsed, stripped and truncated, and the answer keeps its
`untrusted` block saying those fields are to be reported and never obeyed.

**Never hold, log or return a credential.** `erase_instance_data` requires the
same authorisation `DELETE /api/purge` does, supplied by the caller; the MCP
layer passes it and forgets it. Validate a uuid as a uuid before it reaches a
request path, and percent-encode anything that goes into a query.

**The four documents are public and unauthenticated**, at stable paths.
`COS_WEB_ENABLE_DOCS` governs only `/docs` and `/redoc`; `COS_WEB_ENABLE_MCP`
turns the endpoint off for a deployment that wants none, and the discovery
document then stops advertising it. A new tool needs a row in `docs/mcp.md`,
`webapp/README.md` and `docs/webapp.md`, and a test in
`tests/test_webapp_mcp.py`.

## Working on the frontend

`frontend/` holds every template and asset; `webapp/` holds no markup and
`frontend/` holds no logic. Jinja2 renders from `frontend/templates/`, and
`frontend/static/` is mounted at `/static`.

- **Nothing comes from a third party.** No Bootstrap, no Tailwind, no CDN, no
  font service, no analytics, no external script or stylesheet of any kind.
  Every byte the browser fetches is served from this origin under `/static/`,
  and a test asserts it. "Air-gapped" has to survive somebody opening the
  network tab.
- **Twitter/X, Google and Meta are excluded by name**, and not only as
  requests. No `twitter:` card metadata, no `fb:` properties, no
  `google-site-verification`, no Google Fonts, Analytics, Tag Manager,
  reCAPTCHA or Maps, no Facebook or Instagram pixel, embed or share button.
  `tests/test_webapp_seo.py` fails on any of them. See
  [Third parties](#third-parties).
- **The CSP has no `unsafe-inline`.** No `style=` attributes, no `<style>`
  blocks, no `onclick`, no inline `<script>`. A one-off style becomes a
  utility class or a `[data-...]` rule in `app.css`; there are already
  `[data-rating="0"]` through `[data-rating="5"]` doing exactly that.
- **Reference assets by relative path** - `/static/css/app.css`, not
  `url_for('static', ...)`, which emits an absolute URL and hands the page's
  own host name back to it.
- **The design system lives in `app.css`**, driven by custom properties at the
  top. Change a token rather than adding a colour, honour the existing dark
  mode, and respect `prefers-reduced-motion` for anything that moves.
- **Write semantic, accessible markup.** Landmarks, real labels, a visible
  focus ring, `aria-live` for the progress region, and text that stands on its
  own when the icon does not load. Progress and results must remain readable
  without JavaScript having succeeded.
- **No stock photography or generic illustration.** The SVGs in
  `static/img/` are hand-written and small; keep new ones the same way.
- **Never put a real hostname in a mockup either.** `opencloud.example.com`,
  in placeholders, screenshots and examples alike.
- Starlette needs `TemplateResponse(request, name, context, status_code=...)`;
  the two-argument form was removed.

Every page carries the trademark notice in the footer of `base.html`. See
[Trademarks and affiliation](#trademarks-and-affiliation) - do not remove it
from a template, and add it to any new surface that stands on its own.

## Third parties

**Nothing in this project may talk to Twitter/X, Google or Meta**, and nothing
may be built so that a deployment ends up doing it. Not a font, not a script,
not an analytics beacon, not a CAPTCHA, not a share button, not a login, not a
map, not an embedded video, not an SDK, and not a piece of metadata addressed
to one of them.

The reason is the same one behind everything else here. Somebody who uses this
service tells it the address of a system they are responsible for securing. A
single request to a platform whose business is building profiles turns that
into a record held by a company with no relationship to the visitor, no reason
to keep it and no obligation to delete it. The referrer alone would carry a
result URL whose uuid is the entire authorisation.

Concretely, and by name:

- **Google** - Fonts, Analytics, Tag Manager, reCAPTCHA, Maps, AdSense,
  Firebase, hosted libraries, `google-site-verification` meta tags, and
  "Sign in with Google".
- **Meta** - the Facebook pixel, SDK, like or share buttons, comment embeds,
  Instagram embeds or oEmbed, WhatsApp click-to-chat, `fb:` meta properties,
  and "Log in with Facebook".
- **Twitter/X** - `twitter:` card metadata, the widget script, embedded
  tweets, and share intents.

What is allowed: a plain link a person clicks, and platform-neutral metadata
that no browser fetches, such as OpenGraph `og:` tags. Both are inert. The
line is whether *this* page causes a request the visitor did not ask for.

This is not only a frontend rule. It covers the scanner, the plugin, the
container images, the CI workflows and the documentation. A dependency that
phones one of them home is the same leak with more steps, so check what a new
package fetches at install time and at runtime before adding it.

`tests/test_webapp_seo.py` asserts no page carries such metadata, and the
third-party test in `tests/test_webapp_api.py` walks the rendered HTML for any
foreign origin at all. The Content-Security-Policy has no allowance for one,
so a violation fails in a browser as well as in the suite.

## Trademarks and affiliation

This project is independent. It is **not** affiliated with, endorsed by,
sponsored by or supported by OpenCloud GmbH, and nothing it reports is an
official statement about OpenCloud software. "OpenCloud" and all related names
and marks belong to their respective owners and are used only to identify the
software being checked. All rights in OpenCloud remain with OpenCloud GmbH.

Where the notice belongs, and must stay: `README.md`, `docs/README.md`,
`docs/webapp.md`, `opencloud_local_scan/README.md`, the footer in
`frontend/templates/base.html`, and the `QUICKSTART.md` generated by
`scripts/build_web_bundle.py`. A new README, guide or user-facing page needs
it too. Do not write it in a way that claims a partnership, and do not use the
OpenCloud logo as this project's own.

### The container files

Everything Docker lives in `docker/`, and every build context is the
repository root, because an image needs files from outside that directory:

| File | What it builds |
|:-----|:---------------|
| `docker/Dockerfile` | The plugin and the scanner service - the PyPI wheel, nothing web |
| `docker/Dockerfile.web` | The web image: the wheel plus the `web` extra, `webapp/` and `frontend/` |
| `docker/docker-compose.yml` | The default stack - `web_app`, `arq_worker` and `redis`, ready to `up` |
| `docker/docker-compose.monitoring.yml` | The plugin's own scan service, unrelated to the web application |

- Build by hand with `docker build -f docker/Dockerfile.web .`, never with
  `-f` alone from inside `docker/` - the context would be wrong.
- `.dockerignore` stays in the repository root. That is the context root, and
  the daemon reads it from nowhere else.
- Compose is run from `docker/`, so paths inside those files point one level
  up (`../config`, `../secrets`).

## Validation

```bash
uv run pytest                          # full suite
uv run pytest tests/test_waivers.py    # one file
uv run pytest tests/test_webapp_api.py # the web application
uvx ruff check .                       # linting, as CI runs it
uv run mypy --config-file mypy.ini     # type checking
cd ansible && ansible-lint             # must be run from ansible/
```

Notes that will otherwise cost you time:

- Only `ruff check` is enforced, **not** `ruff format`. Do not reformat the
  tree.
- `ansible-lint` is clean only from inside `ansible/`; from the repository root
  it reports dozens of false positives.
- `pytest` exists only under `uv run`.
- The web tests need the `web` extra and the `test` group, and run without a
  Redis server: `COS_WEB_REDIS_URL=memory://` selects an in-process stand-in.
- `python scripts/build_web_bundle.py` builds the release tarball, and
  `cd docker && docker compose up --build` runs the whole stack
  locally. Neither is part of `pytest`, so run them after touching either.

## Tests

Tests are named as sentences describing the behaviour they protect
(`test_a_waived_check_no_longer_caps_the_rating`), and each carries a one-line
docstring explaining why the behaviour matters. Prefer deriving expectations
from a real scan of `tests/fake_opencloud.py` over duplicating hardcoded
lists, which go stale. An assertion that would still pass if the feature were
removed is worse than no assertion at all - assert the negative *and* the
positive case.

The web tests follow the same rule and live in `tests/test_webapp_*.py`, with
their fixtures in `tests/webapp_support.py`: an isolated in-process Redis per
test and an offline resolver, because `example.com` names do not resolve.
Anything asserting a security property - isolation, SSRF, rate limits,
expiry, the packaging exclusion - belongs there and must keep failing if the
protection is removed.

## Documentation

`README.md` is the reference for operators and carries a table of contents that
must be kept in sync with its headings. `opencloud_local_scan/README.md`
documents the library and service, and `webapp/README.md` the web application
and its frontend - the API, Swagger, the input restrictions and the template
contract. `docs/webapp.md` is the operator's view of the same service; keep
the two from contradicting each other. Every new option needs a row in the CLI
option table, an entry in `config/check-opencloud-security.example.yml`, and
matching entries in `CHANGELOG.md` and `RELEASE.md` under the version in
`pyproject.toml`; see [Versioning and releases](#versioning-and-releases).

The web application is documented in [`docs/webapp.md`](docs/webapp.md):
every `COS_WEB_*` setting, the request pipeline, the isolation model and the
HTTP API. A new setting needs a row in that table as well as in
`docker/docker-compose.yml`.

`docs/` holds the deployment guides and the worked examples, indexed by
`docs/README.md`. Long, platform-specific material belongs there rather than
in `README.md`; a new page needs a row in the guide table under
`# Deployment guides` and a row in the `docs/README.md` index. Relative links
in `docs/` point one level up (`../README.md#anchor`), so moving a section
means fixing the links that reached it by anchor.

`.github/copilot-instructions.md` is the same guidance in the form GitHub
Copilot reads automatically. This file stays the authoritative one; keep the
two consistent when a rule here changes.
