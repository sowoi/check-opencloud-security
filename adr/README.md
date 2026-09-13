# Architecture decision records

This directory preserves the durable architectural decisions behind this
project. Read the accepted records that affect an area before changing it.

## Index

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-prometheus-exporter-loopback-default.md) | Bind the Prometheus exporter to loopback by default | Accepted |
| [0002](0002-no-scan-result-caching.md) | No cross-request scan result caching | Accepted |
| [0003](0003-worker-health-heartbeat.md) | Redis worker health heartbeat | Accepted |
| [0004](0004-webapp-audit-logging.md) | Pseudonymised, opt-in audit logging in the web application | Accepted |
| [0005](0005-batch-scan-submission.md) | Batch submission without a batch exemption | Accepted |
| [0006](0006-dependency-free-exports.md) | Exports rendered without a reporting dependency | Accepted |
| [0007](0007-erasure-on-request.md) | Erasure on request, proved by a second look | Accepted |
| [0008](0008-refuse-to-start-without-the-encryption-key.md) | A process asked to encrypt refuses to start without the key | Accepted |
| [0009](0009-public-pages-indexable-results-never.md) | The public pages are indexable, a result never is | Accepted |
| [0010](0010-machine-readable-descriptions-are-always-public.md) | The machine-readable descriptions are always public | Accepted |
| [0011](0011-mcp-is-an-execution-layer-not-a-second-implementation.md) | MCP is an execution layer over the same API, not a second one | Accepted |
| [0012](0012-the-remediation-plan-is-derived-not-stored.md) | The remediation plan is derived from the rating, not a second model of it | Accepted |
| [0013](0013-transport-security-is-measured-not-assumed.md) | Transport security is measured, and what cannot be measured is absent | Accepted |
| [0014](0014-prompts-are-tasks-and-their-text-lives-beside-the-workflows.md) | Prompts are tasks, and their text lives beside the workflows | Accepted |
| [0015](0015-the-mcp-endpoint-may-require-a-sign-in.md) | The MCP endpoint may require a sign-in, and this service is only ever a resource server | Accepted |
| [0016](0016-the-release-schedule-refreshes-itself.md) | The release schedule refreshes itself, and only ever gains knowledge | Accepted |
| [0017](0017-the-advisory-database-refreshes-itself.md) | The advisory database refreshes itself, and only ever gains advisories | Accepted |
| [0018](0018-cli-documentation-is-generated-at-build-time.md) | CLI documentation is generated at build time | Accepted |
| [0019](0019-search-indexes-public-release-content-only.md) | Search indexes public release content only | Accepted |
| [0020](0020-frontend-language-is-request-scoped.md) | Frontend language is request scoped | Accepted |
| [0021](0021-webmcp-is-a-page-scoped-api-client.md) | WebMCP is a page-scoped API client | Accepted |
| [0022](0022-identity-provider-versions-require-public-evidence.md) | Identity provider versions require public evidence | Accepted |
| [0023](0023-tls-policy-rates-measured-parameters.md) | TLS policy rates only the cipher and certificate parameters measured | Accepted |
| [0024](0024-caa-record-uses-the-systems-own-resolver.md) | The CAA record check uses only the system's own resolver | Accepted |
| [0025](0025-webhook-can-post-a-preformatted-chat-payload.md) | The webhook can post a pre-formatted chat payload | Accepted |
| [0026](0026-cli-plugin-gets-its-own-sarif-and-junit-export.md) | The CLI plugin gets its own SARIF/JUnit export, independent of the webapp's | Accepted |
| [0027](0027-refreshed-reference-data-is-attested-not-merely-fetched.md) | Refreshed reference data is attested, not merely fetched | Accepted |
| [0028](0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md) | Headers no OpenCloud sends are reported but never alerted on | Accepted |
| [0029](0029-a-comparison-is-two-live-results-and-one-arithmetic.md) | A comparison is two live results, judged by the plugin's own arithmetic | Accepted |
| [0030](0030-a-listener-binds-loopback-and-a-wide-bind-needs-a-credential.md) | A listener binds loopback, and a wide bind needs a credential | Accepted |
| [0031](0031-a-response-is-uncacheable-until-a-route-opts-in.md) | A response is uncacheable until a route opts in | Accepted |
| [0032](0032-a-rescan-is-an-ordinary-submission-and-reading-a-limit-never-spends-it.md) | A rescan is an ordinary submission, and reading a limit never spends it | Accepted |
| [0033](0033-a-generated-configuration-fragment-is-complete-or-it-says-so.md) | A generated configuration fragment is complete, or it says so | Accepted |
| [0034](0034-an-advisory-observation-need-not-be-a-header.md) | An advisory observation need not be a header | Accepted |
| [0035](0035-the-operator-area-is-guarded-by-a-proxy-and-authenticates-nobody.md) | The operator's area is guarded by a proxy and authenticates nobody | Accepted |
| [0036](0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md) | A companion service is probed only where the scan was pointed | Accepted |
| [0037](0037-preload-eligibility-is-measured-list-membership-is-not.md) | Preload eligibility is measured, list membership is not | Accepted |
| [0038](0038-a-dnssec-answer-nobody-could-have-given-is-not-a-finding.md) | A DNSSEC answer nobody could have given is not a finding | Accepted |
| [0039](0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md) | The plugin ships as a distribution package built from the wheel | Accepted |
| [0040](0040-a-push-format-may-rewrite-the-path-never-the-host.md) | A push format may rewrite the path, never the host | Accepted |
| [0041](0041-a-browser-tool-answers-a-failure-rather-than-throwing.md) | A browser tool answers a failure rather than throwing | Accepted |
| [0042](0042-every-resolved-address-is-compared-only-when-the-operator-asks.md) | Every resolved address is compared only when the operator asks | Accepted |
| [0043](0043-an-operators-exclusion-outranks-every-allowance.md) | An operator's exclusion outranks every allowance | Accepted |
| [0044](0044-the-operator-area-may-write-the-exclusions.md) | The operator's area may write the exclusions, and nothing else | Accepted |
| [0045](0045-a-release-is-rehearsed-on-the-pull-request-and-publishes-last.md) | A release is rehearsed on the pull request and publishes last | Accepted |

## Writing a new record

Create an ADR for a decision that changes a layer boundary, public interface,
security or deployment model, data lifecycle, or a long-lived dependency. Do
not create one for routine implementation details or temporary tasks.

Use zero-padded, never-reused filenames:

```text
0001-short-decision-title.md
```

Use this template:

```markdown
# ADR 0001: Short decision title

- Status: Proposed | Accepted | Superseded by ADR NNNN
- Date: YYYY-MM-DD

## Context

What problem requires a durable decision?

## Decision

What is the chosen approach?

## Consequences

What becomes easier, harder, required or deliberately out of scope?

## Alternatives considered

What credible alternatives were rejected, and why?
```

Accepted ADRs are historical records: do not rewrite their decision. When a
decision changes, add a new ADR and mark the older record as superseded.

Add every new record to the index above in the same change, with its title
and status as they appear in the record itself.
