# AGENTS.md

Guidance for AI coding agents working on **check-opencloud-security**
(version **1.0.0**).

## What this project is

A Nagios/Icinga plugin that checks an OpenCloud instance for known
vulnerabilities and misconfiguration, plus the scanner library it is built on.

The single most important fact about it: **OpenCloud has no public scan API.**
There is no remote service to ask for a verdict, so everything the plugin
reports it works out itself by talking to the instance over HTTP. The ratings
follow the `0`-`5` scale of the Nextcloud scan API purely so that existing
thresholds, graphs and alert rules keep their meaning - that is the only place
Nextcloud may be mentioned. Do not introduce API clients, tokens or endpoints
for a scan service that does not exist.

## Layout

| Path | What lives there |
|:-----|:-----------------|
| `check_opencloud_security.py` | The plugin: CLI, output, exit codes, perfdata, webhook |
| `opencloud_local_scan/scanner.py` | The scan pipeline, findings, waivers and the rating |
| `opencloud_local_scan/versions.py` | The release lifecycle model (tracks, lines, end of life) |
| `opencloud_local_scan/releases.py` | The update check and its track-aware recommendation |
| `opencloud_local_scan/hardening.py` | Catalogue explaining every hardening identifier |
| `opencloud_local_scan/config.py`, `factory.py` | Configuration, secrets, settings construction |
| `opencloud_local_scan/data/release_schedule.json` | Bundled release schedule |
| `scripts/update_release_schedule.py` | Regenerates that file from the published documentation |
| `tests/` | Test suite, including `tests/fake_opencloud.py` |
| `ansible/`, `contrib/`, `config/` | Deployment role, Icinga definitions, example config |

## Ground rules

- **Never modify `check-nextcloud-security`.** It is a sibling repository used
  only as a reference. `git status` in it must stay empty.
- **Do not reference any real instance.** The project is tested against a live
  server, but its hostname must never appear in code, tests, documentation or
  commit messages. Use `opencloud.example.com` in examples.
- **Do not add a scan API.** See above.
- Keep the version in `pyproject.toml`, `check_opencloud_security.py` and
  `opencloud_local_scan/__init__.py` **identical**. They have drifted before.
- Comment only what needs clarification. Explain *why*, not *what*.

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
line in `CHANGELOG.md`.
