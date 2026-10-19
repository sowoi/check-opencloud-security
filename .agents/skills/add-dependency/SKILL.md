---
name: add-dependency
description: Add a new Python dependency to check-opencloud-security under the dependency policy (ADR 0060) - justify it, check the standard library and existing packages first, security-review it, write the tests that exercise it, and draft the proposed security/dependencies/<name>.yml record for a maintainer to approve. Never approves a record. Use when asked to add a package to pyproject.toml, an extra or dependency group, a build requirement, or a uvx tool in a workflow, or when check_dependencies.py --check fails.
---

# Add a Python dependency

Request: $ARGUMENTS

Policy: [ADR 0060](../../../adr/0060-a-new-dependency-is-justified-tested-and-reviewed-first.md),
record format: `security/dependencies/README.md`. A package is used only after
a maintainer approves its record. **You never set `status: approved` or
`approved_by`, and never add a name to `security/dependencies/grandfathered.txt`.**

## 0. Should it be added at all?

Before anything else, check whether the need can be met without a new package:

- the standard library (`requires-python = ">=3.11"`, so `tomllib` is there);
- a package already declared (`python scripts/check_dependencies.py --list`);
- a few dozen lines of our own code.

If one of those does the job, say so and stop. Otherwise continue and write
down what you looked at - it becomes `alternatives_considered`.

## 1. Review the package (read-only, before touching the manifest)

Pick the exact version you intend to lock. For each question, write the
finding and how you got it:

| Field | How to find out |
|:--|:--|
| `known_vulnerabilities` | `uvx pip-audit --requirement <(echo "<name>==<version>")`; the project's GitHub security advisories; OSV (`https://osv.dev/list?ecosystem=PyPI&q=<name>`) |
| `maintenance` | PyPI release history, number of maintainers, open security issues, whether a `SECURITY.md` exists |
| `provenance` | PyPI "Verified details" / trusted publishing / attestations; the source repository matches the release |
| `install_time` | Wheels for every Python 3.11-3.15 and platform we ship? sdist-only means code runs at install time - read its build backend |
| `runtime_network` | Grep the package source for `requests`, `urllib`, `http`, `socket`, telemetry, update checks. Anything that contacts a third party is a blocker under AGENTS.md "Third parties" |
| `native_code` | Compiled extensions, `subprocess`, `eval`/`exec`, `pickle`/`marshal` on untrusted input |
| `transitive_dependencies` | Add it in a scratch environment (`uv add --dry-run` or `uv pip compile`) and list the new packages; glance at each the same way |
| `license` | Must be compatible with this project's `LICENSE` |

Downloading a package to read it is fine. Do not run its code outside a
throwaway environment, and do not send repository content anywhere.

Stop and report to the user instead of continuing if the review finds a
blocker: a known unfixed vulnerability, a third-party network call, an
unmaintained project, or an incompatible license.

## 2. Declare it and use it

- Add it to the narrowest scope that works: a dependency group for tests and
  tooling, an extra for the web app (`web`, `mcp`), `[project] dependencies`
  only when the plugin itself cannot run without it. Explain the scope in a
  comment above the entry, like the existing ones.
- `uv lock` to update `uv.lock`.
- A package the web app needs goes in an extra, never in `dependencies`; the
  wheel must stay small (see AGENTS.md).
- A `uvx` tool in a workflow is pinned to a version (`tool@x.y.z`).

## 3. Test it

Write or extend tests that exercise the code path using the package - and
assert the negative case too (see `tests/CLAUDE.md`). At least one listed test
file must mention the package's `import_name`. For a `ci` tool, list the
workflow that runs it.

## 4. Draft the record

Create `security/dependencies/<normalised-name>.yml` from the template in
`security/dependencies/README.md`:

- `status: proposed`, `approved_by: ""`;
- `scopes` exactly as `python scripts/check_dependencies.py --list` prints them;
- `review.reviewer`: who did the review (say it was drafted by an agent);
- `review.reviewed_on`: today.

## 5. Verify and hand over

```bash
python scripts/check_dependencies.py --check --base origin/main   # fails only on "proposed"
uv run pytest tests/test_dependency_policy.py <the tests you listed> -q
```

The check **must** fail with exactly one problem: the record is `proposed`.
Any other problem is yours to fix.

Add a `CHANGELOG.md` entry under `## [Unreleased]` naming the new dependency
and why. Then tell the user, in this order:

1. the package, version and scope, and why nothing existing does the job;
2. the review findings, with anything uncertain called out;
3. that the record is `proposed` and CI fails until they review it and set
   `status: approved` and `approved_by` themselves.
