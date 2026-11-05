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
| [0019](0019-search-indexes-public-release-content-only.md) | Search indexes public release content only | Accepted; its release-only refresh superseded by ADR 0050 |
| [0020](0020-frontend-language-is-request-scoped.md) | Frontend language is request scoped | Accepted; English-only guide bodies superseded by ADR 0058 |
| [0021](0021-webmcp-is-a-page-scoped-api-client.md) | WebMCP is a page-scoped API client | Accepted |
| [0022](0022-identity-provider-versions-require-public-evidence.md) | Identity provider versions require public evidence | Accepted |
| [0023](0023-tls-policy-rates-measured-parameters.md) | TLS policy rates only the cipher and certificate parameters measured | Accepted |
| [0024](0024-caa-record-uses-the-systems-own-resolver.md) | The CAA record check uses only the system's own resolver | Accepted |
| [0025](0025-webhook-can-post-a-preformatted-chat-payload.md) | The webhook can post a pre-formatted chat payload | Accepted |
| [0026](0026-cli-plugin-gets-its-own-sarif-and-junit-export.md) | The CLI plugin gets its own SARIF/JUnit export, independent of the webapp's | Accepted |
| [0027](0027-refreshed-reference-data-is-attested-not-merely-fetched.md) | Refreshed reference data is attested, not merely fetched | Accepted |
| [0028](0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md) | Headers no OpenCloud sends are reported but never alerted on | Accepted |
| [0029](0029-a-comparison-is-two-live-results-and-one-arithmetic.md) | A comparison is two live results, judged by the plugin's own arithmetic | Accepted; comparing different instances superseded by ADR 0059 |
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
| [0045](0045-a-release-is-rehearsed-on-the-pull-request-and-publishes-last.md) | A release is rehearsed on the pull request and publishes last | Accepted; its pull request policy superseded by ADR 0046, its `RELEASE.md` requirement by ADR 0048 |
| [0046](0046-a-release-needs-no-label-and-the-pull-request-policy-is-local.md) | A release needs no label, and the pull request policy is local | Accepted; its `RELEASE.md` requirement superseded by ADR 0048 |
| [0047](0047-the-bundled-provider-requires-a-second-factor-and-provisions-its-accounts.md) | The bundled provider requires a second factor and provisions its accounts | Accepted |
| [0048](0048-release-md-is-written-by-the-release-not-by-a-pull-request.md) | RELEASE.md is written by the release, not by a pull request | Accepted |
| [0049](0049-the-docker-wizard-is-downloaded-from-a-release-and-knows-its-version.md) | The Docker wizard is downloaded from a release, and knows its version | Accepted |
| [0050](0050-every-pull-request-to-main-rebuilds-the-search-index.md) | Every pull request to main rebuilds the search index | Accepted |
| [0051](0051-a-client-that-keeps-scanning-hosts-that-are-not-opencloud-is-blocked.md) | A client that keeps scanning hosts that are not OpenCloud is blocked | Accepted |
| [0052](0052-the-probe-guard-counts-networks-and-a-deployment-may-scan-approved-instances-only.md) | The probe guard counts networks, and a deployment may scan approved instances only | Accepted |
| [0053](0053-a-scan-timeout-ends-its-process.md) | A scan timeout ends its process | Accepted |
| [0054](0054-metrics-are-collected-once-and-rendered-twice.md) | Metrics are collected once and rendered twice | Accepted |
| [0055](0055-a-badge-is-a-rendering-of-one-scan-not-a-handle-on-an-instance.md) | A badge is a rendering of one scan, not a handle on an instance | Accepted |
| [0056](0056-the-reference-data-is-subscribable.md) | The reference data is subscribable | Accepted |
| [0057](0057-an-uploaded-report-is-evidence-not-a-scan.md) | An uploaded report is evidence, not a scan | Accepted |
| [0058](0058-public-guides-have-reviewed-german-sources.md) | Public guides have reviewed German sources | Accepted |
| [0059](0059-a-comparison-refuses-two-different-instances.md) | A comparison refuses two different instances | Accepted |
| [0060](0060-a-new-dependency-is-justified-tested-and-reviewed-first.md) | A new dependency is justified, tested and reviewed first | Accepted |
| [0061](0061-the-frontend-is-tested-in-real-browsers-that-cannot-leave-loopback.md) | The frontend is tested in real browsers that cannot leave loopback | Accepted; engine choice superseded by [0068](0068-chromium-is-a-third-browser-test-engine-behind-the-dead-proxy.md) |
| [0062](0062-public-guides-have-reviewed-french-sources.md) | Public guides have French source pages | Accepted; its Spanish English-fallback statement superseded by ADR 0063 |
| [0063](0063-public-guides-have-spanish-sources.md) | Public guides have Spanish sources | Accepted |
| [0064](0064-a-scan-records-what-it-did-not-measure.md) | A scan records what it did not measure | Accepted |
| [0065](0065-a-waiver-may-carry-a-reason-and-a-deadline.md) | A waiver may carry a reason and a deadline | Accepted |
| [0066](0066-a-result-records-the-conditions-it-was-produced-under.md) | A result records the conditions it was produced under | Accepted |
| [0067](0067-a-release-ends-with-its-github-release-not-its-tag.md) | A release ends with its GitHub release, not its tag | Accepted |
| [0068](0068-chromium-is-a-third-browser-test-engine-behind-the-dead-proxy.md) | Chromium is a third browser test engine, behind the dead proxy | Accepted |
| [0069](0069-login-throttling-is-observed-only-when-the-operator-asks.md) | Login throttling is observed only when the operator asks | Accepted |
| [0070](0070-the-operator-area-installs-attested-releases-in-place.md) | The operator area installs attested releases in place | Accepted |
| [0071](0071-repository-advisories-are-a-second-advisory-source.md) | OpenCloud's repository advisories are a second advisory source | Accepted |
| [0072](0072-remediation-verification-re-measures-named-findings-without-a-full-scan.md) | Remediation verification re-measures named findings without a full scan | Accepted |
| [0073](0073-a-result-fingerprints-the-configuration-it-measured.md) | A result fingerprints the configuration it measured | Accepted |
| [0074](0074-a-lost-measurement-warns-through-the-baseline-not-the-rating.md) | A lost measurement warns through the baseline, not the rating | Accepted |
| [0075](0075-the-remediation-plan-groups-changes-by-where-they-are-made.md) | The remediation plan groups changes by where they are made | Accepted |
| [0076](0076-a-fleet-summary-is-read-from-saved-reports-and-stores-nothing.md) | A fleet summary is read from saved reports and stores nothing | Accepted |
| [0077](0077-decision-records-are-never-translated.md) | Decision records are never translated | Accepted |
| [0078](0078-changelogs-and-release-notes-are-never-translated.md) | Changelogs and release notes are never translated | Accepted |
| [0079](0079-a-finding-is-new-only-if-the-earlier-scan-could-have-reported-it.md) | A finding is new only if the earlier scan could have reported it | Accepted |
| [0080](0080-a-version-bump-is-the-whole-release-pull-request.md) | A version bump is the whole release pull request | Accepted |

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
