## check-opencloud-security 1.32.1

### Security

- **The web container image no longer ships pyasn1 0.6.4.** sigstore, which
  the `signing` extra installs in `docker/Dockerfile.web`, pulled in pyasn1
  0.6.4 (CVE-2026-119194 to -119197) through `uv.lock` since 1.31.1. sigstore
  4.5.1 no longer depends on pyasn1, so the lock no longer contains it. The
  PyPI package never pinned pyasn1, and the plugin image does not install the
  `signing` extra.

### Changed

- **Dependabot updates every `github/codeql-action` step in one pull
  request.** The `init`, `analyze` and `upload-sarif` steps must run the same
  version; bumped one at a time, each pull request failed CodeQL until the
  other two were merged too.

### Documentation

- **`GUIDELINE.md` collects the rules behind this repository's agent setup.**
  Fifty-one tool-agnostic best practices for repositories where AI coding
  agents do much of the work: one authoritative rule file, hooks that enforce
  the hard rules, skills for many-file changes, read-only checking agents,
  generator `--check` modes, records for decisions, security fixes and
  dependencies, and tests that keep the instruction files in agreement.
