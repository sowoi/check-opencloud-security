# ADR 0045: A release is rehearsed on the pull request and publishes last

- Status: Accepted
- Date: 2026-09-13

## Context

A version bump that lands on `main` is the only release trigger there is:
`publish-pypi.yml` writes the notes, builds the wheel, the `.deb`, the `.rpm`
and the web bundle, uploads to PyPI, tags, and opens the GitHub release. Two
things about that were true and neither was visible in a green pipeline.

**Most of those artifacts were built for the first time on `main`.** The pull
request ran the tests, but nothing on it ran `uv build`, nfpm, the web bundle,
the release-notes script or either Dockerfile. A broken `packaging/nfpm.yaml`
or a file missing from the bundle manifest surfaced only after the merge,
inside the release.

**PyPI was uploaded to before those builds ran.** The upload came directly
after the wheel was built; the distribution packages, the web bundle and the
tag followed it. A failure in any later step left a version on PyPI with no
tag and no GitHub release. The next push to `main` found no tag, ran again,
and failed on PyPI's "File already exists" - and PyPI never takes a version
back, so there was no way to redo that release under its own number.

Separately, the rules that decide whether a pull request may release at all
were checkboxes: every change documented in `CHANGELOG.md` and `RELEASE.md`,
and the version bumped only deliberately. A mistaken bump publishes as surely
as an intended one, and the history already carries a bump commit whose
subject names a different version from the one it set.

## Decision

**The release publishes last.** In `publish-pypi.yml`, every build and
attestation step runs before `uv publish`, and only the tag and the GitHub
release come after it. `uv publish --check-url https://pypi.org/simple/`
skips files PyPI already holds with the same digest, so a run repeated after
a failed tag step completes the release instead of failing on the upload.

**The pull request rehearses it.** `release-dry-run.yml` runs on every pull
request to `main` and builds what the release builds: the release notes with
`--require-unreleased`, the wheel and the sdist checked by
`twine check --strict`, the `.deb` and the `.rpm` with the same pinned nfpm,
the web bundle, and both Dockerfiles for `linux/amd64` without pushing. It
holds a read-only token and has no publishing, pushing or attesting step.

**The pull request rules are checked, not ticked.** `pull-request-policy.yml`
runs `scripts/check_pull_request.py`, which refuses a pull request that

- changes anything without a new entry in `CHANGELOG.md` under
  `## [Unreleased]` or the declared version, and a change to `RELEASE.md`
  whose heading names that version - unless it carries `skip-changelog` or
  was opened by `github-actions[bot]` or `dependabot[bot]`;
- changes the version without the `release` label, or to a number that is not
  newer than `main` and every tag, or that a tag already names;
- contains a commit that changes the version line while its subject names a
  different version.

`tests/test_release_dry_run.py` holds the publish order, the `--check-url`,
the matching nfpm pin and the dry run's inability to publish; the script's own
behaviour is in `tests/test_check_pull_request.py`.

## Consequences

- A packaging break is a red pull request, not a half-published release.
- A failed release is repaired by pushing to `main` again; nothing has to be
  uploaded or tagged by hand.
- Every pull request to `main` spends a few more minutes of runner time on
  the rehearsal, most of it in the two image builds.
- The maintainer labels a bump `release`. That label is the whole cost of the
  version guard, and it is deliberately a step nobody takes by accident.
- An external contributor now has to touch `RELEASE.md` as well as
  `CHANGELOG.md`, as `AGENTS.md` already required.
- The rehearsal does not rebuild the search index: only the release workflow
  may, so the published indexes do not drift between versions.
- arm64 images are still built for the first time on `main`; the rehearsal
  answers whether the Dockerfile builds, not whether QEMU does.

## Alternatives considered

- **Tag first, then publish.** A tag without a PyPI upload is recoverable, but
  the tag is also what `publish-pypi.yml` reads to decide a release already
  happened, so a failed upload would never be retried.
- **Publish from a separate workflow triggered by the tag.** Events raised by
  the built-in `GITHUB_TOKEN` start no further workflows, so the tag push
  would not trigger it without a personal token held in the repository.
- **Upload to TestPyPI on every pull request.** It proves the upload, which
  has not been what breaks, and needs a credential on pull request runs.
- **Keep the checkboxes.** They were already there when a bump commit went out
  naming the wrong version.
