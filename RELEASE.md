## check-opencloud-security 1.32.2

### Changed

- **A failed browser test leaves a Playwright trace.** In CI a Firefox
  run once timed out loading `/api`, a page the same run had just loaded
  cleanly, and the log could not say which request hung. With
  `PLAYWRIGHT_TRACE_DIR` set, the `page` fixture in
  `tests/browser_support.py` records each test and keeps the trace only
  when the test fails. `browser-tests.yml` sets it and uploads the traces as
  `playwright-traces-<browser>` for seven days. Open one with
  `uv run playwright show-trace`. Locally nothing is recorded unless the
  variable is set; with it, the browser suite took 66 s instead of 64 s.
- **A version bump is the whole release pull request.** Releasing 1.32.1
  took three extra commits and two red CI runs. Three changes remove that
  (ADR 0080):
  - An advisory record for an entry under `## [Unreleased]` now says
    `changelog_version: unreleased` (and `fixed: unreleased`) instead of
    guessing a number. `scripts/release_notes.py` writes the version in when
    it renames the heading, the release commit carries the records, and the
    release dry run checks them. Before, the record had to name the version
    in `pyproject.toml`, which is the release already out until the bump, so
    every security entry broke the check on the bump.
  - `scripts/check_pull_request.py` refuses a version change that does not
    bring the regenerated Releases page and search indexes with it, and names
    the commands. A bot commit that regenerated them afterwards would run no
    checks. The edit hook's prompt for a version change names them too.
  - A pull request that changes only the version (the version lines in
    `pyproject.toml` and `uv.lock`, and those regenerated files) counts as a
    release and needs no changelog entry of its own.
- **The browser tests cache the Playwright browser build.** One 1.32.1 run
  hung downloading WebKit until the job timed out. The download is now
  cached, keyed on the locked Playwright version, and the install step has
  its own 10-minute limit. The system libraries are still installed through
  apt on every run.
- **A test takes the release through every step on a copy of the
  repository.** `tests/test_release_flow.py` copies the tracked files, adds
  an `[Unreleased]` security entry with its `unreleased` record, and bumps
  the version. It runs the real generators and `check_pull_request.py`,
  then does what `publish-pypi.yml` does: `release_notes.py`, both
  generators again, the advisory check and the `--check` modes. It also
  fails if the release rewrites a file that the workflow's release commit
  does not stage. Each script already had its own tests; this one catches
  the steps drifting apart.
- **Bandit is pinned, and `/preflight` scans what CI scans.** The workflow
  runs `bandit@1.9.4` with `bandit-sarif-formatter==1.1.1` instead of
  whatever is newest. The preflight skill used `--recursive .` on the
  working tree, which also took in `.nox/` and `mutants/` (about 3.3 million
  lines and hundreds of findings in third-party code). It now passes the
  tracked Python files, which is what CI's checkout holds.
- **CI runs a pinned uv.** Every job logged "Could not determine uv version
  … Falling back to latest", so a new uv release could change what
  `uv sync --locked` does without a commit in this repository.
  `pyproject.toml` now sets `required-version = ">=0.13.1"` under
  `[tool.uv]`, and every `setup-uv` step takes the lowest match, so CI
  installs exactly 0.13.1, the uv the Docker images copy in. It is a floor
  and not an exact pin, so a newer local uv still runs. Nothing raises it
  automatically; a test fails if a `setup-uv` step floats or a Docker image
  falls below it.
- **A weekly report names the CI tool pins that fell behind.** Dependabot
  updates actions, locked packages and Docker images. It does not update
  the `uvx`/`npx` versions (ruff, zizmor, Bandit, Biome), the binaries
  downloaded against a SHA-256 (shellcheck, hadolint, actionlint, nfpm),
  mermaid-cli or uv's `required-version`. On its first run six of them were
  behind. `scripts/check_tool_pins.py` finds them in the workflows and
  compares each with its latest release, and `tool-pins.yml` keeps one issue
  open while any is behind. It only reports: a new binary needs its SHA-256
  checked by hand. A new `*_VERSION` variable without a known release source
  fails the script, so a pin added later is watched from the start.
- **CI runs the test suite in slices.** The coverage run took 19 minutes
  and each nox interpreter 15, almost all of it pytest on a single runner.
  `pytest --shard INDEX/COUNT` (`tests/sharding.py`) runs one slice. A test's
  slice is a stable SHA-256 of its node id, because the slowest test takes 7
  of 507 seconds and no weights file would stay current. The coverage run
  is now four jobs (`python 1/4` to `python 4/4`). A `python` job combines
  their data and applies `fail_under` to the whole suite, after checking
  that the slices ran every test exactly once. nox runs three slices per
  interpreter. A failing slice reproduces locally with the same `--shard`.
  The generated-file checks moved into their own `generated files` job.

### Fixed

- **A browser test no longer fails because it moved on while a font was
  loading.** A web font is fetched when text first needs it, which can be
  after the load event. When a test reloaded in that moment, Firefox aborted
  the download and logged `downloadable font: download failed …
  status=2152398850` (`NS_BINDING_ABORTED`) as a console error, and the
  page watch failed the test. The first CI trace showed this for
  `test_garbage_in_storage_is_ignored`. The watch now ignores exactly that
  status. A font that fails for any other reason is still an error, and
  `tests/test_browser_support.py` checks both cases.
- **The browser tests cache their system packages too.** Today the
  runners' Ubuntu mirror served packages at a few hundred kB/s, and
  `playwright install-deps` timed out for WebKit (114 MB) and Firefox
  (49 MB) on almost every run; only Chromium (21 MB) got through. The
  downloaded `.deb` files are now cached per browser, Playwright version and
  runner image, and saved right after the install, so a failing test does
  not discard them. apt checks each cached package against the fresh index
  and downloads only what changed. The install has 20 minutes, enough to
  fill the cache once over a slow mirror, and the job limit rose from 20 to
  35 minutes.
- **The CI tool downloads retry a passing server error.** A `504` from
  GitHub's release downloads failed the hadolint install on main. The same
  single attempt fetched shellcheck, actionlint and nfpm, and nfpm is
  installed inside the release in `publish-pypi.yml`. Every `curl` download
  now retries up to five times (`--retry 5 --retry-delay 5`), and the digest
  check after it still decides what is installed.
  `tests/test_workflow_hardening.py` now refuses a download without
  `--retry`, and a pin comment that names only a major tag.
- **The test suite no longer leaks HTTP error answers.** In
  `tests/test_service.py`, each `HTTPError` a test caught kept its response
  open until the garbage collector closed it. That close came after the
  socket was gone and sometimes ended a full run with two
  `PytestUnraisableExceptionWarning`s (`ValueError: I/O operation on closed
  file`), reported in whatever test happened to be running. A helper now
  reads the status and body and closes the answer. The fake OpenCloud also
  stops printing a traceback when the scanner deliberately hangs up at its
  response cap, and the webhook test in `tests/test_output_formats.py`
  closes its listening socket.
- **Every pinned action names its exact release.** Several actions were
  pinned to a commit hash but commented only with the major tag
  (`actions/checkout # v7`, `actions/attest-build-provenance # v4`,
  `actions/attest # v4`, `docker/login-action # v4`). zizmor, running
  online in the workflow lint, compares that comment with where the tag
  points now. When `docker/login-action` v4.8.0 moved `v4`, every pull
  request failed on a file it never touched. The comments now name the tag
  each hash is (`v7.0.1`, `v4.2.2`, `v4.2.2`, `v4.7.0`); the hashes are
  unchanged.
- **A failed advisory or release-schedule refresh no longer leaks its
  connection.** When the OSV feed, the GitHub advisory API or the lifecycle
  page answered with an HTTP error status, the fetch wrapped the
  `HTTPError` in its own error and never closed the response it holds. Each
  failed daily refresh in the web service kept a socket open until the
  garbage collector reached it. `opencloud_local_scan/fetch.py` now opens
  all three through one helper, `open_document`, which closes an error
  answer before passing it on. Its status and reason stay readable.
- **A deliberate hook refusal no longer also says the hook "could not run".**
  The wrappers in `.claude/settings.json` printed that message on every exit
  that was not 0, including the deliberate exit 2, so a decision read like a
  broken hook. Only an unexpected exit code prints it now; both still refuse.
- **The release-notes preview in `AGENTS.md` and `CONTRIBUTING.md` reverts
  with `git restore`.** The branch guard read the documented
  `git checkout CHANGELOG.md RELEASE.md` as a switch to a branch called
  `CHANGELOG.md` and refused it.

### Documentation

- **The documented test suite runtime is accurate.** `CLAUDE.md`,
  `.github/copilot-instructions.md` and the preflight skill and agent said
  about 75 seconds. The suite takes about 8 minutes locally and about
  15 minutes per Python version in CI.
