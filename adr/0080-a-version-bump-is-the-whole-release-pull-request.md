# ADR 0080: A version bump is the whole release pull request

- Status: Accepted
- Date: 2026-11-05
- Extends: ADR 0045, ADR 0046, ADR 0050

## Context

Releasing 1.32.1 was meant to be one changed line in `pyproject.toml`. It took
three more commits and two red CI runs:

- **An advisory record named the wrong section.** `security_advisories.py`
  read `## [Unreleased]` under the version in `pyproject.toml`. Between a
  release and the next bump that number is the release already out, so the
  record for the pyasn1 entry said `changelog_version: "1.32.0"` - correct
  when it was written, and failing the check the moment the version moved to
  1.32.1. Every release carrying a `### Security` entry would meet this.
- **The bump left generated files stale.** The operator area's Releases page
  (`frontend/templates/admin-docs/releases.html`) and all eight search
  indexes render the version. The unit tests and the documentation check
  failed on every Python version. The search-index workflow (ADR 0050)
  rebuilt only the public indexes, and its commit - made with `GITHUB_TOKEN` -
  starts no workflow, so even a complete bot rebuild would have left the
  pull request on the red checks of the commit before it.
- **The pull request guard asked a release for notes.** `check_pull_request.py`
  wanted a new changelog entry, although a release's notes are, by
  definition, the `## [Unreleased]` section it publishes.

## Decision

**A record claims an unreleased entry with `unreleased`, not a number.**
`changelog_version` - and `fixed`, while the fix is unreleased - say
`unreleased` (any case). `security_advisories.py` matches such a record
against the `## [Unreleased]` heading itself and never against the version in
`pyproject.toml`; a record that guesses a number for an unreleased entry fails
the check. `--sync` drafts no advisory for it, because a range needs a fixed
version.

**The release writes the number in.** `scripts/release_notes.py`, in the step
that renames `## [Unreleased]` to the version, replaces the marker in every
record under `security/advisories/` - only a field whose whole value is the
marker. `publish-pypi.yml` adds `security/advisories/` to the release commit,
so the heading and the records that claim it change together, and
`release-dry-run.yml` runs `security_advisories.py --check` after rehearsing
that step.

**A bump brings its regenerated files in the same push.** After the version
changes, `uv lock`, `build_frontend_documentation.py` and then
`build_search_index.py` run, and the result is committed with the bump.
`check_pull_request.py` lists the files that render the version
(`VERSION_EMBEDDING`) and refuses a version change whose diff lacks any of
them. The edit hook's prompt for a version change names the same commands.
The search-index workflow keeps rebuilding the public indexes on every pull
request (ADR 0050); it is not extended to the Releases page, because its
commit would still run no checks.

**A pull request that only bumps is a release and needs no entry.** When the
version changed and the diff holds nothing but `pyproject.toml`, `uv.lock`
and `VERSION_EMBEDDING` - and both files differ only in the project's own
version line - `check_pull_request.py` does not ask for a changelog entry. A
dependency change in the lock, or any other file, makes it an ordinary pull
request again.

## Consequences

A release is one edit and three generator commands, and its pull request goes
green on the first push. A security record written mid-cycle stays valid
across the bump and the release without anybody remembering it.

Records already released keep their numbers; only new records use the
marker. A record for an `[Unreleased]` entry that was written with the old
convention fails the check with the usual "no record claims" message.

The guard sees only which files changed, not whether they are current; the
generators' `--check` modes in CI still decide that.

## Alternatives considered

- **Keep reading `[Unreleased]` under the `pyproject.toml` version.** That is
  what broke: the number is only right after the bump, and the record is
  written before it.
- **Resolve `unreleased` to the `pyproject.toml` version without rewriting.**
  It would match until the next bump, then fail the same way one release
  later.
- **Extend the search-index bot to the Releases page.** Its commit runs no
  checks; the pull request would show red checks on the commit before and
  none on its head. A token that does start workflows is a credential this
  repository does not hold.
- **Make the Releases page ignore the bumped version.** The page shows the
  running release from what `[Unreleased]` collected on purpose (see
  `test_the_release_notes_are_readable_from_the_area`), and the search
  indexes embed the version regardless.
