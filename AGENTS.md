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
| `opencloud_local_scan/hardening.py` | Catalogue explaining every hardening identifier |
| `opencloud_local_scan/config.py`, `factory.py` | Configuration, secrets, settings construction |
| `opencloud_local_scan/wizard.py` | The interactive setup behind `--configure` |
| `opencloud_local_scan/selfupdate.py` | `--upgrade-self`, via pipx, uv or pip |
| `opencloud_local_scan/data/release_schedule.json` | Bundled release schedule |
| `scripts/update_release_schedule.py` | Regenerates that file from the published documentation |
| `scripts/release_notes.py` | Turns `## [Unreleased]` into the notes of a release |
| `tests/` | Test suite, including `tests/fake_opencloud.py` |
| `ansible/`, `contrib/`, `config/` | Deployment role, Icinga definitions, example config |
| `docs/` | Deployment guides and worked examples, indexed by `docs/README.md` |

## Ground rules

- **Do not reference any real instance.** The project is tested against a live
  server, but its hostname must never appear in code, tests, documentation or
  commit messages. Use `opencloud.example.com` in examples.
- **Do not add a remote scan API.** See above.
- **Never bump the version.** See [Versioning and
  releases](#versioning-and-releases) - that is the user's decision alone.
- **`pyproject.toml` is the only place the version is written.**
  `opencloud_local_scan.__version__` derives it from there (package metadata
  when installed, the file itself in a checkout) and the plugin imports that.
  Never reintroduce a literal - that is how the numbers drifted apart before.
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

Write what you changed under the **`## [Unreleased]`** heading at the top of
`CHANGELOG.md` instead, in the [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) sections (`Added`, `Changed`,
`Deprecated`, `Removed`, `Fixed`, `Security`, `Documentation`). Create the
heading if a release has just consumed it. Never write a `## [x.y.z]` heading
yourself.

When the user bumps the version, `scripts/release_notes.py` renames
`## [Unreleased]` to `## [<version from pyproject.toml>] - <date>`, copies that
body into `RELEASE.md` for the GitHub release, and leaves a fresh empty
`## [Unreleased]` behind. So an entry only needs writing once, and everything
collected since the last release ships under the version the user chose.

Preview what the next release would look like. It rewrites `CHANGELOG.md` and
`RELEASE.md`, so do it on a scratch copy or revert afterwards:

```bash
python scripts/release_notes.py --version 0.0.0 --date 2000-01-01
git checkout CHANGELOG.md RELEASE.md
```

`--require-unreleased` makes the script fail rather than fall back to
generating notes from commit subjects.

## Working on the rating

The rating starts from the version and advisory database, then failed checks
cap it (`SEVERITY_RATING_CAP`: critical 2, high 3, medium 4, low 5). Two
invariants are load-bearing and have tests to match:

- **The explanation must not depend on iteration order.** A cap counts as
  *applied* when it equals the final rating, never "whichever came first".
- **End of life overrides everything**, including a wildcard waiver. A release
  that receives no security fixes is an F.

## Working on the lifecycle

OpenCloud ships rolling (~3 weeks), production (~6 months) and LTS (2 years)
releases side by side. Releases group into **lines** (`MAJOR.MINOR`), and one
line can belong to several tracks.

- rolling and production expire when the next release on the same track ships;
  LTS expires on the clock.
- A **newer version can be less supported than an older one**. This is not a
  bug to fix.
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

## Validation

```bash
uv run pytest                          # full suite
uv run pytest tests/test_waivers.py    # one file
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

## Tests

Tests are named as sentences describing the behaviour they protect
(`test_a_waived_check_no_longer_caps_the_rating`), and each carries a one-line
docstring explaining why the behaviour matters. Prefer deriving expectations
from a real scan of `tests/fake_opencloud.py` over duplicating hardcoded
lists, which go stale. An assertion that would still pass if the feature were
removed is worse than no assertion at all - assert the negative *and* the
positive case.

## Documentation

`README.md` is the reference for operators and carries a table of contents that
must be kept in sync with its headings. `opencloud_local_scan/README.md`
documents the library and service. Every new option needs a row in the CLI
option table, an entry in `config/check-opencloud-security.example.yml` and a
line under `## [Unreleased]` in `CHANGELOG.md` - never under a version
heading, see [Versioning and releases](#versioning-and-releases).

`docs/` holds the deployment guides and the worked examples, indexed by
`docs/README.md`. Long, platform-specific material belongs there rather than
in `README.md`; a new page needs a row in the guide table under
`# Deployment guides` and a row in the `docs/README.md` index. Relative links
in `docs/` point one level up (`../README.md#anchor`), so moving a section
means fixing the links that reached it by anchor.

`.github/copilot-instructions.md` is the same guidance in the form GitHub
Copilot reads automatically. This file stays the authoritative one; keep the
two consistent when a rule here changes.
