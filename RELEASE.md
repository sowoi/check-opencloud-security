## check-opencloud-security 1.31.3

### Security

- **The container images ship urllib3 2.8.0.** `uv.lock` pinned urllib3
  2.7.0 (PYSEC-2026-4175, -4176, -4177), and since 1.31.1 the container
  images install exactly what `uv.lock` pins. The PyPI package does not pin
  urllib3 and picks up the fixed release on its own. The lock also moves
  virtualenv from 21.7.7 to 21.14.11 (PYSEC-2026-4011 to -4014); it is a
  development dependency that no image or package contains.

### Changed

- **Every locked dependency is on its newest release.** `uv lock --upgrade`
  moved the whole set in `uv.lock`, which the container images install and
  CI tests against - among them mcp 2.3.0, pydantic 2.14.1, starlette 1.7.0
  (1.9.0 on newer Pythons), uvicorn 0.54.0, idna 3.20, pyjwt 2.15.1 and mypy
  2.4.0. The runtime ranges in `pyproject.toml` are unchanged, so a
  `pip install` accepts the same versions as before. `pip-audit` finds no
  known vulnerability in the new set. Only the test dependency playwright is
  held below 1.64, in `pyproject.toml` and for Dependabot: the WebKit it
  ships reports a Content-Security-Policy violation for the browser's own
  stylesheet of every `<select>`, so every browser test of a page with a
  language picker failed.
- **The signed-in stack runs authentik 2026.8.4.** The setup wizard and
  `docker/docker-compose.authentik.yml` pinned 2026.8.2; `AUTHENTIK_TAG`
  still overrides it. Redis 8.10 and Postgres 18.6 were already current.
- **Every GitHub Action is on its newest release, still pinned by commit.**
  setup-uv 10.3.0, setup-node 7.1.0, upload-artifact 7.0.2,
  download-artifact 8.0.2, setup-buildx-action 4.4.1 and codeql-action
  4.39.0; the diagram workflow renders with mermaid-cli 12.0.0.

### Fixed

- **An automated release-schedule pull request no longer fails CI.** The
  weekly refresh rewrote the release table in `README.md` but not the
  `/documentation` page generated from it, so the unit tests and every nox
  session failed on a stale `reference.html`. The workflow now regenerates
  that page and its sitemap revision and commits them with the refresh; the
  architecture-diagram refresh likewise updates the copy the frontend serves.
- **CI no longer breaks when a new ruff is released.** The workflow ran
  whatever ruff was newest, and 0.17 flagged two `noqa` comments for a rule
  the project never enables. The comments are gone and the workflow pins
  `ruff@0.17.1`, like zizmor and Biome already are.
- **A waiver test no longer expires with the calendar.** It built its waivers
  from a fixed date but scanned with the real clock, so from 4 October 2026
  one of them was already expired in the scan and the test failed on every
  run.
