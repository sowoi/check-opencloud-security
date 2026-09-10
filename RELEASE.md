## check-opencloud-security 1.21.1

### Fixed

- **Drafting advisories after a release no longer fails the workflow asking
  for a permission that does not exist.** The `draft` job ran
  `security_advisories.py --sync` with the built-in `GITHUB_TOKEN` and stopped
  at `Resource not accessible by integration (HTTP 403)`. The job had asked
  for `security-events: write`, which sounds like the right thing and is not:
  it grants code scanning alerts, while creating a repository advisory is the
  Security tab, and *no* `permissions:` line grants a workflow token that —
  the advisories API is outside what an installation token may reach at all.
  So the job could not have worked as written, and the advisories drafted so
  far were all made by hand.

  Drafting now runs on a `SECURITY_ADVISORY_TOKEN` secret — a fine-grained
  token with *Security advisories: Read and write* — and where none is
  configured, it and the commit that records the new ids are skipped, with the
  reason and the command to run by hand written to the step summary. A release
  is no longer reported as failed over an advisory nobody could have drafted,
  and the records still waiting are listed either way.

  The script now recognises that 403 as well, rather than passing GitHub's
  sentence through unexplained: it names the token that would work and the
  near-miss permission that would not, so the next person to meet it does not
  go looking for a missing line in `permissions:`.
