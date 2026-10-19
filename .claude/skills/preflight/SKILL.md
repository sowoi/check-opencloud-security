---
name: preflight
description: Run locally everything CI checks on a check-opencloud-security pull request - ruff, mypy, Bandit, the generator --check modes, the advisory and pull request guards, Biome, zizmor, ansible-lint, actionlint, shellcheck, hadolint and the test suite - and report one pass/fail/skipped summary. Use before opening or updating a pull request, or when asked to check the branch.
argument-hint: "[quick]"
context: fork
agent: preflight-runner
background: false
---

# Preflight

Arguments: $ARGUMENTS (`quick` skips the full test suite and runs only the test
files related to the changed code).

This skill runs in the read-only `preflight-runner` agent
(`.claude/agents/preflight-runner.md`), so the long output stays out of the
main conversation and nothing is fixed while the checks run. Run from the
repository root. Do not run `ruff format` or reformat the tree. Run
independent checks in parallel where possible; the test suite takes about
75 seconds, so start it in the background first.

## 1. Context

```bash
git fetch origin main
git diff --stat origin/main...HEAD
git status --porcelain
```

## 2. Checks

A tool that is not installed is reported as **skipped**, never as passed. Use
`command -v <tool>` to decide.

| # | Check | Command |
|:--|:--|:--|
| 1 | Tests | `uv run --group test --extra signing pytest -q` (web tests use `COS_WEB_REDIS_URL=memory://` automatically via fixtures; set it if they complain) |
| 1a | Browser tests | `uv run pytest tests/test_webapp_browser_ux.py tests/test_webapp_browser_e2e.py -q` (part of check 1; report them separately, and as **skipped** - not passed - when WebKit is not installed: `uv run playwright install webkit`) |
| 2 | Ruff | `uvx ruff@0.17.1 check .` |
| 3 | mypy | `uv run --group test mypy --config-file mypy.ini` |
| 4 | Bandit | `uvx bandit --recursive . --severity-level medium --confidence-level medium --exclude ./tests,./secrets,./.venv -q` (advisory in CI - report findings, do not fail) |
| 5 | Frontend documentation | `uv run python scripts/build_frontend_documentation.py --check` |
| 6 | Search index | `python scripts/build_search_index.py --check` (CI rebuilds it on the PR, so stale is a warning) |
| 7 | Release schedule block | `uv run pytest tests/test_update_script.py -q` |
| 8 | Architecture diagrams | `uv run python scripts/render_architecture_diagrams.py --check` |
| 9 | Wizard blueprints | `python scripts/embed_wizard_blueprints.py --check` |
| 10 | Security advisories | `python scripts/security_advisories.py --check` |
| 11 | Changelog and version guard | `python scripts/check_pull_request.py --base origin/main` |
| 11a | Dependency policy | `uv run python scripts/check_dependencies.py --check --base origin/main` (a `proposed` record is a **warning** - it awaits the maintainer's approval - anything else fails) |
| 12 | Biome | `npx --yes @biomejs/biome@2.5.13 lint --error-on-warnings` (needs Node) |
| 13 | zizmor | `uvx zizmor@1.30.1 .github/workflows` |
| 14 | ansible-lint | `cd ansible && uvx ansible-lint` (**only** from inside `ansible/`; skip unless `ansible/` changed) |
| 15 | actionlint | `actionlint -color` (skip unless `.github/workflows/` changed) |
| 16 | shellcheck | `git ls-files '*.sh' \| xargs shellcheck` |
| 17 | hadolint | `hadolint docker/Dockerfile docker/Dockerfile.web` (skip unless `docker/` changed) |
| 18 | Compose files | `for f in docker/docker-compose*.yml; do docker compose -f "$f" config -q; done` (needs Docker; skip unless `docker/` changed) |
| 19 | Web bundle | `python scripts/build_web_bundle.py` (only if `webapp/`, `frontend/` or `scripts/build_web_bundle.py` changed; build into a scratch location or delete the tarball afterwards) |

With `quick`, replace check 1 with the test files that match the changed
modules (`tests/test_<module>.py`, `tests/test_webapp_*.py` for `webapp/`), and
skip 18 and 19.

Also scan the diff for the project's hard rules and report violations:

- a real hostname instead of `opencloud.example.com`;
- a literal `__version__ = "..."`, or a `version` change in `pyproject.toml`
  that the user did not ask for;
- any Twitter/X, Google or Meta reference in frontend, docs or workflows;
- `style=`, `<style>`, `onclick` or inline `<script>` in `frontend/templates/`;
- an edit to `RELEASE.md`, or a hand edit inside the
  `<!-- release-schedule:start -->` block of `README.md`;
- a new `checkout` step without `persist-credentials: false` in a job that
  does not push.

## 3. Report

One table: check, result (pass / fail / warning / skipped + reason), and for
each failure the first relevant lines of output. End with the list of
concrete fixes needed. The main conversation relays the report and asks the
user whether to apply them.
