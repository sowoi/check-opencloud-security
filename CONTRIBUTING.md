<!-- TOC -->
* [CONTRIBUTING](#contributing)
  * [Guidelines](#guidelines)
  * [Local setup](#local-setup)
    * [1. Install `uv`](#1-install-uv)
    * [2. Register the merge drivers](#2-register-the-merge-drivers)
  * [Generated files and merge conflicts](#generated-files-and-merge-conflicts)
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

### 2. Register the merge drivers

Once per clone:

```
python scripts/setup_git_merge_drivers.py
```

See below for what it prevents. Skipping it costs you nothing but the
occasional conflict you would have had anyway.

## Generated files and merge conflicts

`frontend/static/search-index.json` and its three locale overlays are
**generated** — a pure function of the templates, the catalogues and the
version — and they are also checked in, because the frontend serves them and
`tests/test_webapp_search.py` reads them. That combination conflicts on merge
for a reason no person can settle: two branches that touch a template, a
string or `pyproject.toml` produce different bytes on the same lines, and
neither side was written by hand. Resolving one by picking a side means
choosing between two stale answers.

So the resolution is always the same — rebuild — and
`scripts/setup_git_merge_drivers.py` teaches git to do it for you.
`.gitattributes` points those four files at a `search-index` merge driver, and
the setup script registers what that driver *is* in your `.git/config`. Git
splits it that way on purpose: a driver is an arbitrary command, and a
repository able to hand one to everyone who clones it would be a repository
that runs code on clone. That is why this cannot be automatic.

Rebuilding is the correct resolution and not merely the convenient one: the
index is authoritative exactly once, in the release workflow, and
`test_only_the_release_workflow_refreshes_the_index` forbids any other
workflow from touching it — so a rebuild produces what the next release would
produce anyway.

Without the setup step you get the ordinary conflict, exactly as before.
Resolve it by hand with:

```
python scripts/build_search_index.py && git add frontend/static/search-index*.json
```

If git says `fatal: custom merge driver search-index lacks command line`, the
config is half-written — re-run the setup script.

**The data files are not covered, deliberately.**
`opencloud_local_scan/data/release_schedule.json` and `vulnerabilities.json`
are generated too, but from the network rather than from this tree, and they
ship in the wheel. A conflict there is a real question about which fetch is
newer, so it stays a conflict for a person to answer — re-run
`scripts/update_release_schedule.py` or `scripts/update_vulnerability_db.py`.

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

Add the same entry to [`RELEASE.md`](RELEASE.md), under its
`## check-opencloud-security <version>` heading - the version currently in
`pyproject.toml`.

Do not write a `## [x.y.z]` heading and do not bump the version - the release
picks your entry up under whichever number the maintainer chooses.

CI checks both with `scripts/check_pull_request.py`. A pull request that
genuinely needs no notes - a typo, a test-only change - is labelled
`skip-changelog` by a maintainer; run the check locally with
`python scripts/check_pull_request.py --base origin/main`.

### If your entry goes under `### Security`

Add a record to [`security/advisories/`](security/advisories/) in the same pull
request, named after your change. CI runs
`python scripts/security_advisories.py --check` and fails without one.

The record answers a question the changelog prose cannot: **did a released
version actually carry this defect?** A bug introduced and fixed inside one
development cycle never reached anybody, and an advisory for it would tell
operators to upgrade away from versions that were never affected. Work it out
from the tags rather than from memory - the release before your fix is the
evidence - and put the command and its result in `verified:`:

```bash
git show v1.16.0:opencloud_local_scan/service.py | grep DEFAULT_LISTEN
git ls-tree -r --name-only v1.13.0 | grep catalogue   # absent = never shipped
```

Then say what follows:

```yaml
state: draft          # this shipped and needs a GitHub Security Advisory
shipped: true
severity: high        # low | medium | high | critical
package: plugin       # plugin (on PyPI) or web (the release tarball)
introduced: "1.0.0"
fixed: "1.17.0"
```

or, just as valid an answer:

```yaml
state: declined
shipped: false
declined_because: |
  Never shipped. Introduced and fixed inside the 1.14.0 cycle.
```

Copy the shape from any existing file in that directory. **Do not publish the
advisory** - a maintainer does that after the release, because it raises
Dependabot alerts for every affected installation and cannot be undone.

## Releasing
**The version in `pyproject.toml` is bumped by hand, by a maintainer, and
nobody else.** It is the only trigger there is: once the bump lands on `main`,
the [publish workflow](.github/workflows/publish-pypi.yml) publishes to PyPI.
It is also the only place the number is written: `opencloud_local_scan`
derives `__version__` from it - from the installed package metadata, or from
the file itself when running out of a checkout - and the plugin imports that.
Nothing else needs editing.

The pull request carrying the bump needs the `release` label - the
[pull request policy](.github/workflows/pull-request-policy.yml) refuses a
version change without it, and one that does not move past every tag. The
[release dry run](.github/workflows/release-dry-run.yml) has by then built the
notes, the wheel, the `.deb`, the `.rpm`, the web bundle and both images on
that pull request.

The workflow then:

1. `scripts/release_notes.py` renames `## [Unreleased]` in
   [`CHANGELOG.md`](CHANGELOG.md) to `## [<version>] - <date>`, writes the same
   body to `RELEASE.md` (overwritten on every release) and leaves a fresh empty
   `## [Unreleased]` behind.
2. Both files are committed back to `main` with `[skip ci]`.
3. The wheel, the SBOM, the `.deb`, the `.rpm` and the web bundle are built and
   attested, and only then is the package published to PyPI - so a failed
   build never leaves a version on PyPI without a release. If a later step
   fails, the next push to `main` finishes the release; files PyPI already
   holds are skipped.
4. The tag `v<version>` is created and a GitHub release is opened with
   `RELEASE.md` as its body, followed by GitHub's generated
   "What's Changed" section.
5. [`security-advisories.yml`](.github/workflows/security-advisories.yml) then
   runs `scripts/security_advisories.py --sync`, which creates a GitHub **draft**
   advisory for every record marked `state: draft` and commits the new GHSA ids
   back. The job summary lists what is waiting.

Publishing those drafts is the one manual step left, and deliberately so:

```bash
python scripts/security_advisories.py --list
python scripts/security_advisories.py --publish <slug>
```

A published advisory enters the GitHub Advisory Database and raises Dependabot
alerts for everyone on the affected range. Review the severity, the version
range and the wording in the Security tab first.

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
