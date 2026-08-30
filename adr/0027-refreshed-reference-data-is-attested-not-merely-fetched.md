# ADR 0027: Refreshed reference data is attested, not merely fetched

- Status: Accepted
- Date: 2026-08-30

## Context

ADR 0016 and ADR 0017 gave the release schedule and the advisory database a
refresh that a monitoring host can run on its own, so an instance is not
rated against whatever data happened to ship in the installed wheel. Both
ADRs also name, in their own words, what that refresh cannot do:

> A compromised or badly edited lifecycle page could add lines that do not
> exist, and would then be believed - as CI would believe it today.
> — ADR 0016

> The feed is a third party this project depends on being honest about
> OpenCloud. — ADR 0017

`refresh_data()` fetched from `https://api.osv.dev/v1/query` and
`https://docs.opencloud.eu/.../lifecycle/` over TLS and checked the answers
structurally: the schedule may not lose a bundled release line, an advisory
must carry a bounded range, a query may not return hundreds of records.
Those guards catch a page that changed shape. They do not catch a page that
is the right shape and says the wrong thing, and a security tool that
believes a false "not affected" is worse than one that never refreshed.

Signing the upstream answers is not available to this project: OSV and the
OpenCloud documentation site are third parties, and neither will sign
anything on this project's behalf. What *can* be attested is what this
project itself publishes.

That publication already exists and is already reviewed.
`scripts/update_vulnerability_db.py` and `scripts/update_release_schedule.py`
run in CI, query those same upstreams, and open a pull request - the
advisory one saying "Review the ranges before merging" in its own body. A
human merges it. The merged file on `main` is therefore strictly better
evidence than the live query a monitoring host was making instead: same
source, plus review.

## Decision

`refresh-data` reads both documents from this repository's own `main`
branch by default, and verifies a Sigstore attestation over the exact bytes
it read before writing anything.

`.github/workflows/attest-security-data.yml` runs
`actions/attest-build-provenance` on every push to `main` that changes
either file. There is no signing key: the certificate is short-lived and
bound to the workflow's own OIDC identity, exactly as `publish-pypi.yml`
already attests the wheel, the SBOM and the web bundle - and for the reason
stated in that workflow, that there is then no signing key for this project
to leak.

`opencloud_local_scan/data_signing.py` verifies. GitHub publishes the
attestation under a public API keyed by the content's SHA-256 digest;
verification fetches it back and checks it with `sigstore`, pinning the
certificate identity to *this* repository's own signing workflow on
`refs/heads/main`. Pinning is the part that matters: without it, any valid
GitHub Actions signature from any workflow in any repository on the platform
would satisfy the check. The attestation is a DSSE-wrapped in-toto
statement, so `verify_dsse` proves who signed the envelope and the
statement's own subject digest is then compared against the fetched bytes -
querying by digest alone would only prove GitHub's index agrees, not that
the signed statement is about this content.

Three outcomes, deliberately different:

**Verified.** The document is written. The advisory database replaces the
local file wholesale rather than going through `merge_document`: the
attested file is the complete reviewed database, not a feed answer to fold
into the local one. The merge-only rule that stops a live OSV query from
losing an advisory still applies - upstream, in the pull request that
produced the file, where a person can see what changed.

**Verification could not be attempted.** The `signing` extra is not
installed, the trust root or the attestation could not be fetched, or
nothing has been published for that content yet - a real case, since a
merged commit is readable from `raw.githubusercontent.com` before its
attestation finishes publishing. This logs a warning naming the reason and
falls back to exactly the behaviour that existed before this ADR:
structural guards, and nothing else. It is a reduced-assurance refresh, not
a broken one.

**Verified as wrong.** An attestation exists for this content and does not
verify against the pinned identity. This is the only outcome that stops the
refresh, and it stops it the way ADR 0016 and ADR 0017 already require every
failure to behave: `RefreshError`, previous files untouched, reason in the
log.

`--schedule-url` and `--advisory-url` still query an arbitrary source live,
unverified, warned about. An air-gapped mirror and a fork both need that,
and nothing this project controls signs a third party's URL.

The structural guards run on the verified path too. Provenance says who
published a document; it does not say the document is sane, and ADR 0016's
rule that a refresh may never lose a known release line is cheap enough to
keep enforcing either way.

## Consequences

`sigstore` is a new optional extra (`pip install
check-opencloud-security[signing]`), not a dependency. It pulls in a dozen
transitive packages, and the plugin's whole packaging premise - ADR 0026
restates it - is that a monitoring host installs something small. A host
without the extra refreshes exactly as it did before, with a warning saying
what it is not getting. This is a real gap: the default install does not
verify, and an operator who never reads a warning never learns that.

The default source of reference data moves from a third party to this
repository. A monitoring host now depends on `raw.githubusercontent.com` and
`api.github.com` being reachable for a refresh, where it previously depended
on `api.osv.dev` and `docs.opencloud.eu`. This is a different dependency,
not a smaller one - but it is one whose contents this project reviews.

Data freshness is now bounded by how often the advisory and schedule PRs are
merged, rather than by how often a monitoring host asks OSV. That is the
point - review is what is being added - but a merge that sits unattended is
now a refresh that sits still, where before it would have gone straight
through unreviewed.

The verifier is pinned to one workflow path on one ref. Renaming
`attest-security-data.yml`, or moving the default branch, breaks
verification for every already-installed copy until they upgrade - the
failure is a warning and a fallback rather than an outage, but it is silent
in exactly the way this ADR otherwise argues against.

## Alternatives considered

**A static Ed25519 keypair, private half in a GitHub Actions secret, public
half baked into the package.** The obvious design, and the one this project
already declined elsewhere: `publish-pypi.yml`'s own comment says Sigstore
was chosen so "there is no signing key for this project to leak." A key in a
repository secret is a key that can be exfiltrated by any workflow change
that gets merged, and rotating it means every installed copy verifies
against a public key it no longer has.

**Attest at release time, in `publish-pypi.yml`.** Simpler - the workflow
already attests three other artifacts - but `publish-pypi.yml` only runs
when a maintainer hand-bumps the version. Advisory data would then be no
fresher than the last release, which is the staleness ADR 0017 was written
to fix.

**Verify only the file bundled in the installed wheel, and leave the live
refresh alone.** A much smaller change, and it would detect a tampered
package. It does nothing about the case this ADR is about, which is the
unreviewed live fetch, and it duplicates what `gh attestation verify`
already does for the wheel.

**Keep fetching from OSV and the lifecycle page, and sign that.** Not
available: there is nothing to sign with, because the answers come from
third parties who do not sign them for this project.
