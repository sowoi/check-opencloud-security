# Security advisory records

One record per bullet under a `### Security` heading in
[`CHANGELOG.md`](../../CHANGELOG.md). Each answers a question the changelog
prose cannot, and preserves the evidence it was answered with.

## Why this exists

A `### Security` heading says something about this project's security changed.
It does not say whether anybody was ever at risk, and those come apart far more
often than the wording suggests. In this repository's own history, of nineteen
security entries only seven described a defect that a released version actually
carried. The rest were:

- **Never shipped** - introduced and fixed inside a single development cycle.
  An advisory would tell operators to upgrade away from versions that were
  never affected. (`catalogue-advisory-url-xss`, the three `mcp-*` records.)
- **Hardening** - narrowing a residual risk an ADR already named and accepted,
  rather than closing an exploitable gap. (`refresh-data-attestation`.)
- **Failing closed** - the defect cost availability, not security.
  (`webhook-hmac-unverifiable`: the signature never verified, so receivers
  correctly rejected every notification.)

Read from the prose alone, all nineteen look identical. The difference is only
visible in the git tags, and once somebody has looked it should not have to be
looked up again - which is what `verified:` is for.

## The rule

`scripts/security_advisories.py --check` fails when a Security entry from
1.14.0 onwards has no record, and CI runs it on every pull request. Write the
record in the same pull request as the fix.

Determine `shipped` from the release *before* the fix, never from memory:

```bash
git show v1.16.0:opencloud_local_scan/service.py | grep DEFAULT_LISTEN
git ls-tree -r --name-only v1.13.0 | grep catalogue   # absent = never shipped
```

## Fields

| Field | |
|:--|:--|
| `slug` | Matches the filename. `--publish` addresses a record by it. |
| `state` | `published`, `draft`, or `declined`. |
| `ghsa` | The GitHub advisory id, written back by `--sync`. |
| `changelog_version` | The release the entry appears under. |
| `changelog_entry` | The bullet's opening phrase, so the check can find it. |
| `shipped` | Did a released version carry it. `false` forbids an advisory. |
| `verified` | The command that established `shipped`, and what it showed. |
| `summary` | One line, becoming the advisory title. |
| `declined_because` | Required when `state: declined`. Which of the cases above. |
| `severity` | `low`, `medium`, `high`, `critical`. GitHub does not accept "moderate". |
| `cwe_ids` | e.g. `CWE-918`. |
| `package` | `plugin` or `web`. |
| `introduced` / `fixed` | Becomes `>= introduced, < fixed`. |
| `description` | The advisory body: Impact, Patches, Workarounds. |

### `package` is not cosmetic

`plugin` files against **pip / `check-opencloud-security`**, which raises
Dependabot alerts for PyPI installations. `web` files against ecosystem
`other`, because `webapp/` and `frontend/` are excluded from the wheel and the
sdist and ship as `check_opencloud_security_web.tar.gz`. Filing a web-only
defect as `plugin` alerts every PyPI user about code they do not have.

## Publishing

```bash
python scripts/security_advisories.py --list
python scripts/security_advisories.py --sync            # create drafts
python scripts/security_advisories.py --publish <slug>  # make one public
```

`--sync` runs automatically after a release
([`security-advisories.yml`](../../.github/workflows/security-advisories.yml)).
Publishing does not, and never will: a published advisory enters the GitHub
Advisory Database and raises Dependabot alerts for everyone on the affected
range, which cannot be undone. That is a maintainer's decision, in the same
class as the version bump.

Declining is a normal outcome and a record that says why is worth as much as an
advisory. Leaving an entry undecided is the only failure.
