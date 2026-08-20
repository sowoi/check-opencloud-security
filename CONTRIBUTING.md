<!-- TOC -->
* [CONTRIBUTING](#contributing)
  * [Guidelines](#guidelines)
  * [Local setup](#local-setup)
    * [1. Install `uv`](#1-install-uv)
  * [Install Dependencies](#install-dependencies)
    * [Exporting a requirements.txt](#exporting-a-requirementstxt)
  * [Running Tests](#running-tests)
    * [End-to-end tests](#end-to-end-tests)
  * [Linting](#linting)
  * [Changelog entries](#changelog-entries)
  * [Releasing](#releasing)
<!-- TOC -->

# CONTRIBUTING
We welcome and appreciate all contributions to this project! Before submitting a Pull Request (PR), please take a moment to review this guide.

By taking part you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md). The short version: review the change
rather than the person, and never post a token, a password or the hostname of
a real instance - in an issue, a pull request, a test or a commit message. Use
`opencloud.example.com`.

A vulnerability **in this plugin** is reported privately and never as a public
issue or pull request - see [SECURITY.md](SECURITY.md).

---

## Guidelines

* Ensure your code adheres to the existing coding style.
* Write clear and concise commit messages.
* **Always** run the tests and linting before submitting a PR.
* Keep PRs focused on a single feature or fix.

---

## Local setup

We recommend using **`uv`** for managing dependencies and running development tasks.

### 1. Install `uv`

If you haven't already, install the `uv` package manager (or your preferred installation method):

```
pipx install uv
```

## Install Dependencies

`uv` is the only dependency manager this project uses. Every dependency is
declared in `pyproject.toml` and pinned in `uv.lock` - there is no
`requirements.txt`, and none should be added.

Install the runtime dependencies together with the development dependencies
from the `test` group:

```
uv sync --group test
```

Add or change a dependency by editing `pyproject.toml` (or with
`uv add <package>` / `uv add --group test <package>`) and committing the
updated `uv.lock`.

### Exporting a requirements.txt

Some deployment tools still expect a `requirements.txt`. Generate it from the
lock file rather than maintaining it by hand, and treat it as a build artefact
that is never committed:

```
uv export --no-dev --no-emit-project --format requirements.txt -o requirements.txt

# without hashes, if the consuming tool cannot handle them:
uv export --no-dev --no-emit-project --no-hashes --format requirements.txt -o requirements.txt
```

## Running Tests
Tests are managed using pytest, and the required packages are defined in the test dependency group.

To run the complete test suite:
```
uv run --group test pytest
```

### End-to-end tests

`tests/test_e2e_cli.py` runs the plugin as a real subprocess against
`tests/fake_opencloud.py`, an in-process HTTP server that answers like an
OpenCloud instance. No OpenCloud installation, Docker container or internet
access is required, and no test ever talks to a real host.

To run only the end-to-end tests:
```
uv run --group test pytest tests/test_e2e_cli.py
```

`InstanceBehaviour` in `tests/fake_opencloud.py` is the switchboard for
everything the fake instance can do: which version it reports, which headers
it sets, which paths it exposes, whether it demands authentication. To cover a
new scanner behaviour, add a field there rather than writing another server.

Two details of that fake are load-bearing. It overrides `version_string()`,
because Python's `BaseHTTPRequestHandler` otherwise leaks
`Server: BaseHTTP/0.6 Python/3.13` and trips the version-disclosure check in
every unrelated test. And it answers unknown paths the way OpenCloud's
single-page frontend does, which is exactly what the catch-all detection in
the scanner exists to survive.

Multi-host changes also need coverage for worker sizing, result ordering and
the aggregate Nagios exit-code priority. Use `tests/test_multi_host.py` for
those cases; workers must keep per-host output and perfdata isolated until the
coordinator renders the final blocks.

### The bundled release schedule

`opencloud_local_scan/data/release_schedule.json` is generated, not written by
hand. `scripts/update_release_schedule.py` scrapes it from the release dates
in the [OpenCloud admin documentation][lifecycle], which is the only source
that states whether a release is rolling, production or LTS - the GitHub
release list cannot tell them apart. `tests/test_update_script.py` covers the
parser offline against a sample of the page, and also asserts that the file
currently checked in has the shape the script produces. Refresh it with:

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

```shell
python scripts/update_release_schedule.py            # rewrite the file
python scripts/update_release_schedule.py --check    # exit 1 if outdated
```

A scheduled workflow does the same thing weekly and opens a pull request.

Because the schedule is scraped from rendered HTML, it is worth checking the
diff of an automated refresh: a redesign of the documentation page shows up as
lines disappearing rather than as an error. The script refuses to write an
implausibly short schedule or one without a rolling and a production table,
which catches the worst of it.

## The documented OpenCloud links

Almost everything this project explains about OpenCloud is anchored in a link
it does not own: the lifecycle page the schedule is scraped from, the
configuration references a finding points an operator at, the advisories.
Those links rot when OpenCloud reorganises its documentation, without a single
commit landing here, and a finding that explains itself with a dead link is a
finding nobody can act on.

`scripts/check_documentation_links.py` collects every OpenCloud link the
repository documents and requests it. Two sources feed it: the text of every
file, and `opencloud_local_scan/hardening.py` imported rather than grepped -
a reference long enough to be split across two string literals is invisible
to a regular expression, and hardening references are exactly the long,
deeply nested URLs most likely to move. A workflow runs it after every merge
into `main` and once a week; `tests/test_documentation_links.py` covers which
links are collected, offline.

```shell
python scripts/check_documentation_links.py           # check, fail on rot
python scripts/check_documentation_links.py --list    # what would be checked
python scripts/check_documentation_links.py --strict  # redirects count too
```

A broken link fails the run. A redirect, and an answer that says "not to you"
rather than "not here" (`401`, `403`, `429` - the anonymous GitHub API is rate
limited), are only reported: `opencloud.eu` redirects to a language version,
and a job that fails every week is a job everybody learns to ignore. The
report is still worth reading, since a moved documentation page looks exactly
like that on its way to a 404. Fixtures under `tests/` are not documentation
and are skipped.

**A status code is not enough for `docs.opencloud.eu`.** It is a single-page
application: an address that no longer exists answers HTTP 200 with the
application shell and renders "Page not found" once the browser gets to it.
Every dead documentation link this project has had looked perfectly healthy
to a status check - the same trap the scanner guards against when it probes an
instance for exposed paths. So links there are checked against the site's own
`sitemap.xml` as well, and a `/docs/` address it does not list fails the run.
A sitemap that cannot be read condemns nothing, and only `/docs/` paths are
held to it: a sitemap lists pages, so an image missing from one proves
nothing.

## Linting
We use Ruff for linting and code formatting checks.

To run the linting check:
```
uvx ruff check
```

## Changelog entries
Describe your change under the `## [Unreleased]` heading at the top of
[`CHANGELOG.md`](CHANGELOG.md), in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) section it belongs to
(`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`,
`Documentation`). Create the heading if the previous release has just consumed
it:

```markdown
## [Unreleased]

### Added

- What you added, and why it matters to an operator.
```

Do not write a `## [x.y.z]` heading and do not bump the version - the release
picks your entry up under whichever number the maintainer chooses.

## Releasing
**The version in `pyproject.toml` is bumped by hand, by a maintainer, and
nobody else.** It is the only trigger there is: once the bump lands on `main`,
the [publish workflow](.github/workflows/publish-pypi.yml) publishes to PyPI.
It is also the only place the number is written: `opencloud_local_scan`
derives `__version__` from it - from the installed package metadata, or from
the file itself when running out of a checkout - and the plugin imports that.
Nothing else needs editing.

The workflow then:

1. `scripts/release_notes.py` renames `## [Unreleased]` in
   [`CHANGELOG.md`](CHANGELOG.md) to `## [<version>] - <date>`, writes the same
   body to `RELEASE.md` (overwritten on every release) and leaves a fresh empty
   `## [Unreleased]` behind.
2. Both files are committed back to `main` with `[skip ci]`.
3. The package is built and published to PyPI.
4. The tag `v<version>` is created and a GitHub release is opened with
   `RELEASE.md` as its body, followed by GitHub's generated
   "What's Changed" section.

A `## [<version>]` section that already exists wins over `## [Unreleased]`. If
neither has any content, the notes fall back to the commit subjects since the
previous tag, grouped by their
[Conventional Commit](https://www.conventionalcommits.org/) type (`feat` ->
Added, `fix` -> Fixed, `security` -> Security, ...; `chore`, `ci`, `build`,
`test` and `style` are skipped); `--require-unreleased` turns that fallback
into an error instead. Preview the result locally - it rewrites both files, so
revert afterwards:

```shell
python scripts/release_notes.py --version 0.0.0 --date 2000-01-01
git checkout CHANGELOG.md RELEASE.md
```
