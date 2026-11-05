---
name: security-fix-record
description: "Write the security/advisories/<slug>.yml record for a ### Security changelog entry in check-opencloud-security - determine from git tags whether a released version carried the defect, choose draft or declined, fill every field, and run the coverage check. Never publishes an advisory. Use whenever a ### Security entry is added or security_advisories.py --check fails."
argument-hint: <changelog entry phrase or description of the fix>
---

# Security fix record

Request: $ARGUMENTS

Every bullet under `### Security` in `CHANGELOG.md` needs a record in
`security/advisories/<slug>.yml` **in the same pull request**. The record
answers what the prose cannot: *did a released version carry this defect, and
does the person running it need to be told?*

**Never run `python scripts/security_advisories.py --publish` or `--sync`, and
never request a CVE.** Publishing raises Dependabot alerts for everyone and
cannot be undone - it is the user's decision alone.

## 1. Find the entry

```bash
python scripts/security_advisories.py --check    # which entries lack a record
sed -n '/^## \[Unreleased\]/,/^## \[/p' CHANGELOG.md
```

If there is no `### Security` bullet yet, write it first (a bold opening
phrase, then what changed and who was affected). `changelog_entry` must match
that opening phrase.

## 2. Establish `shipped` from the tags - never from the prose

1. Find where the defect was introduced:
   ```bash
   git log --oneline -S '<vulnerable code snippet>' -- <file>
   git tag --contains <introducing commit> --sort=v:refname | head -3
   ```
2. Look at the last release **before** the fix and confirm the defect is there:
   ```bash
   git tag --sort=-v:refname | head -5
   git show v<last release>:<file> | grep -n '<pattern>'
   git ls-tree -r --name-only v<release> | grep <file>   # absent = never shipped
   ```
3. Record the command and what it showed; that is `verified:`.

Then decide:

| Finding | `state` | `shipped` |
|:--|:--|:--|
| A released version carried an exploitable defect | `draft` | `true` |
| Introduced and fixed within the unreleased cycle | `declined` | `false` - *never shipped* |
| Narrows a residual risk an ADR accepted | `declined` | per the tags - *hardening* |
| The defect failed closed (availability only) | `declined` | per the tags - *fails closed* |

Declining is a normal outcome. Never write `published` - only the user does
that. If the case is not clear-cut, present the evidence and ask the user.

## 3. Write the record

Use an existing record as the template (`security/advisories/csv-export-formula-injection.yml`
for a shipped one; the `mcp-*` or `catalogue-advisory-url-xss` records for
never shipped; `refresh-data-attestation` for hardening;
`webhook-hmac-unverifiable` for fails closed). Fields:

- `slug` - matches the filename, kebab-case.
- `state` - `draft` or `declined`.
- `changelog_version` - `unreleased` for an entry under `[Unreleased]`,
  never a guessed number: `pyproject.toml` still names the last release until
  the bump. The release writes the version in (ADR 0080).
- `changelog_entry` - the bullet's opening phrase, verbatim.
- `shipped`, `verified` - from step 2.
- `declined_because` - required when declined; name the case.
- `package` - `plugin` for anything in the PyPI wheel; **`web`** for
  `webapp/` or `frontend/`. Filing a web defect as `plugin` alerts every PyPI
  user about code they do not have.
- `severity` - `low`, `medium`, `high` or `critical` (never "moderate").
- `cwe_ids` - e.g. `CWE-918`.
- `introduced`, `fixed` - becomes `>= introduced, < fixed`; `fixed` is
  `unreleased` too while the fix is.
- `summary` - one line, the advisory title.
- `description` - `### Impact`, `### Patches`, `### Workarounds`, and for `web`
  the note that PyPI installations are unaffected.

Never put a real hostname in the record - use `opencloud.example.com`.

## 4. Verify

```bash
python scripts/security_advisories.py --check
python scripts/security_advisories.py --list
```

Report the decision, the evidence, and remind the user that a `draft` becomes
a GitHub draft advisory only after release (or their own `--sync`), and
publishing stays with them.
