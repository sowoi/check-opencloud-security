# Specification

The normative contract of check-opencloud-security: what the software must
do, stated so that a test can be pointed at each clause.

The rest of the documentation explains, teaches and persuades.
[`README.md`](README.md) is the operator's reference,
[`ARCHITECTURE.md`](ARCHITECTURE.md) says how the repository fits together,
[`AGENTS.md`](AGENTS.md) is the rule set for anyone changing it, and `adr/`
records why each boundary is where it is. None of them is written to be
checked clause by clause. This file is - it exists so that a behaviour can be
cited rather than reconstructed from the code every time somebody asks whether
a change broke a promise.

<!-- TOC -->
* [Specification](#specification)
  * [1. Scope, conformance and precedence](#1-scope-conformance-and-precedence)
  * [2. Layers (`L`)](#2-layers-l)
  * [3. The scan result document (`D`)](#3-the-scan-result-document-d)
  * [4. Findings (`F`)](#4-findings-f)
  * [5. Waivers (`W`)](#5-waivers-w)
  * [6. The rating (`R`)](#6-the-rating-r)
  * [7. The release lifecycle (`V`)](#7-the-release-lifecycle-v)
  * [8. The verdict and the exit code (`E`)](#8-the-verdict-and-the-exit-code-e)
  * [9. Output (`O`)](#9-output-o)
  * [10. The webhook (`H`)](#10-the-webhook-h)
  * [11. Configuration (`C`)](#11-configuration-c)
  * [12. Conduct of a scan (`P`)](#12-conduct-of-a-scan-p)
  * [13. The web application (`X`)](#13-the-web-application-x)
  * [14. Prohibitions (`N`)](#14-prohibitions-n)
  * [Trademarks and affiliation](#trademarks-and-affiliation)
<!-- TOC -->


## 1. Scope, conformance and precedence

**Terminology.** MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. A
clause without one of those words is background, not a requirement.

**Scope.** This document governs observable behaviour: what goes in, what
comes out, and which of the two an input is allowed to change. It does not
govern implementation - the module a rule lives in, the shape of a function,
or the wording of a message are free to change while every clause below still
holds. Where a clause names a symbol, it names the thing that currently
enforces the rule, so the rule can be found; the symbol is not itself the
requirement.

**Precedence.** Where this file and another document disagree, the order is:
the code and its tests, then `AGENTS.md`, then this file, then everything
else. A disagreement between this file and the code is a bug in one of them
and MUST be resolved rather than left standing - if the code is right, correct
the clause in the same pull request.

**Conformance.** An implementation conforms when every MUST clause holds. The
test suite is the reference check; a clause that no test asserts is a gap in
the suite, not a weaker requirement.

**Versioning of this document.** Clause identifiers (`R-4`, `E-2`) are stable.
A clause that is withdrawn keeps its number, marked *withdrawn*, rather than
being reused - a citation in a commit message or an ADR must not silently come
to mean something else.


## 2. Layers (`L`)

Three layers, and the boundaries between them are the point.

- **L-1** `opencloud_local_scan/` MUST measure only. `scan()` returns a result
  document; it MUST NOT return, contain or imply a monitoring state.
- **L-2** The library MUST NOT be aware of `OK`, `WARNING`, `CRITICAL` or
  `UNKNOWN`, and MUST NOT know the thresholds that produce them.
- **L-3** `check_opencloud_security.py` MUST be the only place a result
  document becomes a verdict: thresholds, exit codes, the alert line,
  performance data and the webhook.
- **L-4** The plugin MUST NOT issue HTTP probes of its own against the scanned
  instance. Every observation in its output MUST come from the library.
- **L-5** `webapp/` MUST NOT decide whether a finding is acceptable. It runs
  the scanner and renders what came back; grades shown to a visitor MUST come
  from the plugin's `RATE_MAP`, and `webapp/catalog.py` MUST only regroup what
  the scanner already produced.
- **L-6** The plugin MUST NOT call the web application, or any other remote
  service, for a verdict. See [N-1](#14-prohibitions-n).


## 3. The scan result document (`D`)

`scan(host, settings, release_settings, database)` returns one JSON-shaped
`dict`. It is the only interface between the measuring layer and everything
else.

- **D-1** Keys of the result document MUST be camelCase, with the single
  shouted exception `EOL`. The plugin's own output - performance data, the
  webhook payload, the machine-readable formats - MUST be snake_case. The two
  vocabularies are deliberately different so that a key makes it obvious which
  side of the boundary it came from.
- **D-2** A successful scan MUST populate at least: `domain`, `addresses`,
  `ipv6Enabled`, `url`, `product`, `version`, `legacyVersion`, `edition`,
  `scannedAt`, `rating`, `ratingExplanation`, `EOL`, `releaseType`,
  `lifecycle`, `ignored`, `latestVersionInBranch`, `vulnerabilities`,
  `hardenings`, `setup`, `tls`, `tlsByAddress`, `identityProvider`,
  `reverseProxy`, `integrations`, `scanner`, `updates`, `extraChecks`,
  `advisorySources`, `capabilitiesAvailable` and `remediationPlan`.
- **D-3** `setup` MUST carry exactly the four sub-documents `https`, `headers`,
  `advisoryHeaders` and `advisoryChecks`.
- **D-4** `ratingExplanation` MUST record how the rating was reached:
  `rating`, a `base` object of `{rating, reason}`, and a `caps` list. A rating
  MUST NOT be reported without the argument behind it.
- **D-5** `remediationPlan` MUST be derived from the document that carries it
  and stored nowhere else - it is the rating's own arithmetic replayed with
  one finding removed at a time (ADR 0012).
- **D-6** A measurement that could not be taken MUST be absent or explicitly
  null, and MUST NOT be reported as a pass. A question nobody could answer is
  not a finding (ADR 0038).
- **D-7** A failed scan MUST raise `ScanError` rather than return a document
  with a guessed rating.


## 4. Findings (`F`)

A finding is `{id, severity, passed, detail, ignored}` in `extraChecks`.

- **F-1** `severity` MUST be one of `critical`, `high`, `medium`, `low`.
- **F-2** A finding counts towards the verdict when, and only when, it did not
  pass and was not waived (`Finding.counts`).
- **F-3** A check MUST be omitted from `extraChecks` when it could not be
  measured. It MUST NOT be recorded as passing to fill the gap.
- **F-4** A hardening measure an operator cannot influence MUST be marked
  `actionable=False` in `hardening.py`, and such a finding MUST stay out of
  the alert line, the `hardenings_missing` metric and the webhook while
  remaining in the result document.
- **F-5** `setup.advisoryHeaders` and `setup.advisoryChecks` grade behaviour of
  OpenCloud itself rather than of one deployment. They MUST be measured,
  explained by `--debug` and listed in the web catalogue, and they MUST NOT
  reach `_collect_missing_hardenings`, the alert line, the
  `hardenings_missing` metric, the webhook or any exit code, and MUST NOT be
  offered as waivers (ADR 0028, ADR 0034).
- **F-6** `failed_extra_checks(result)` MUST return failing, non-waived
  finding ids ordered worst severity first, and MUST be stable for a given
  document.
- **F-7** `companionAdminConsole` and `companionEditorHttps` MUST be absent -
  never passing - unless the companion service is published on the scanned
  instance's own origin (ADR 0036).


## 5. Waivers (`W`)

`--ignore-hardening` / `scanner.ignore_hardenings`.

- **W-1** A waiver MUST suppress an alert, never the evidence. A waived
  finding MUST remain in the result document with `"ignored": true` and MUST
  still be explained by `--debug`.
- **W-2** Only a check that **actually failed** may be waived. A waiver MUST
  NOT attach to a passing check, so that it cannot silently become a blind
  spot the day that check regresses.
- **W-3** Matching MUST be case-insensitive and MUST accept shell-style
  wildcards, so that generated families (`exposed:/some/path`,
  `debugPort:9205`) can be waived as `debugPort:*`.
- **W-4** Every waived identifier MUST appear in the document's `ignored`
  list, sorted and deduplicated.
- **W-5** A waiver MUST NOT lift the end-of-life verdict, including a wildcard
  waiver. See [R-7](#6-the-rating-r).


## 6. The rating (`R`)

An integer `0`-`5`. The letters belong to the plugin.

- **R-1** The base rating MUST be derived from the version and the advisory
  database alone, as follows, first match winning:

  | Base | Condition |
  |:-----|:----------|
  | `0` | the installed release line is out of support |
  | `1` | an advisory matches the installed version and at least one is critical or high |
  | `2` | an advisory matches the installed version |
  | `3` | the instance is a whole release line behind |
  | `4` | an update is pending on the same release line |
  | `5` | the installed release is current and no advisory matches it |

- **R-2** Failed extra checks MUST then cap the base rating by severity:
  critical `2`, high `3`, medium `4`, low `5` (`SEVERITY_RATING_CAP`). The
  final rating is the lowest applicable value, floored at `0`.
- **R-3** Caps MUST apply only when extra checks are enabled *and*
  `extra_checks_affect_rating` is set. When checks run but do not affect the
  rating, the explanation MUST say so rather than omit them.
- **R-4** A waived finding MUST NOT cap the rating ([F-2](#4-findings-f)).
- **R-5** Every failed check MUST be listed in `caps`, including one that
  changed nothing - a cap that would have landed above the final rating is
  kept and marked as not applied. Hiding it invites the suspicion that a
  finding was silently dropped.
- **R-6** A cap MUST be marked `applied` when, and only when, it equals the
  final rating - never "whichever ran first". **The explanation MUST NOT
  depend on iteration order.** A cap that merely matches a rating the base
  signals had already reached is still applied: it is a reason the instance
  sits where it does, and reporting the only critical finding in a report as
  "already lower" says something untrue about it.
- **R-7** End of life MUST override every other signal. An out-of-support
  release line is `0`, whatever else was measured and whatever was waived.
- **R-8** The `0`-`5` scale MUST keep the meaning it has in the Nextcloud scan
  API, so that thresholds, graphs and alert rules that predate this plugin
  keep theirs. This is the only place that project may be named.
- **R-9** `RATE_MAP` MUST be `{5: "A+", 4: "A", 3: "C", 2: "D", 1: "E",
  0: "F"}`. There is no `B`; the gap is inherited with the scale and MUST NOT
  be closed.


## 7. The release lifecycle (`V`)

OpenCloud ships rolling (~3 weeks), production (~6 months) and LTS (2 years)
releases side by side. Releases group into **lines** (`MAJOR.MINOR`), and one
line MAY belong to several tracks.

- **V-1** Rolling and production releases MUST expire when the next release on
  the same track ships; LTS releases MUST expire on the clock.
- **V-2** A newer version MAY be less supported than an older one. This is a
  property of the schedule, not a defect to correct.
- **V-3** A release newer than the current release of the declared track MUST
  be reported as ahead of that track and MUST stay out of the `F` verdict.
  Only a release *behind* the track is unsupported.
- **V-4** `--release-track` MUST accept `auto` as a fourth value, meaning
  "infer it", identically to leaving it unset.
- **V-5** An upgrade recommendation MUST point forwards only, and MUST NOT
  move a production or LTS instance onto the rolling track.
- **V-6** The bundled schedule (`opencloud_local_scan/data/release_schedule.json`)
  and the README block between `<!-- release-schedule:start -->` and
  `<!-- release-schedule:end -->` MUST be generated together by
  `scripts/update_release_schedule.py`, and MUST NOT be edited by hand.
- **V-7** Removing those markers MUST be treated as an error, not a no-op.


## 8. The verdict and the exit code (`E`)

- **E-1** Exit codes MUST follow Nagios: `OK` 0, `WARNING` 1, `CRITICAL` 2,
  `UNKNOWN` 3. A usage error MUST exit `2`, argparse's own code, so that a
  rejected flag looks the same however it was rejected.
- **E-2** Rating thresholds MUST be inclusive: a rating **at or below**
  `--warning` / `--critical` triggers that state. Defaults MUST be `3` (`C`)
  and `1` (`E`).
- **E-3** End of life MUST produce `CRITICAL`, ahead of both thresholds, and
  the message MUST name the release line and the upgrade target when the
  lifecycle knows them.
- **E-4** A matching advisory MUST raise the state to at least `WARNING`, even
  when the rating alone would still be acceptable.
- **E-5** A rating outside `RATE_MAP` MUST produce `UNKNOWN`, never a guessed
  state.
- **E-6** The exit code MUST keep its Nagios meaning under every value of
  `--format`.
- **E-7** A retired flag MUST be rejected with the name of its replacement.
  Silently ignoring one is worse than not recognising it (`RETIRED_FLAGS`).


## 9. Output (`O`)

- **O-1** `--format` MUST accept `nagios`, `prometheus`, `json`, `sarif` and
  `junit`, defaulting to `nagios`.
- **O-2** Performance data MUST always carry `rating` with its warning and
  critical thresholds and the range `0;5`, and `vulnerabilities` with a
  minimum of `0`. `hardenings_missing` MUST be emitted only when hardening
  checks ran, and `extra_checks_failed` only when extra checks ran.
- **O-3** The alert line MUST count only actionable, non-waived findings
  ([F-4](#4-findings-f), [F-5](#4-findings-f), [W-1](#5-waivers-w)).
- **O-4** `--debug` MUST explain every measured check, waived and advisory
  ones included.
- **O-5** Machine-readable formats MUST combine every host of a multi-host run
  into one document, and MUST preserve the order the hosts were given.
- **O-6** `--baseline` MUST NOT be able to hide a finding that is worse than
  the recorded one; a diff reports regressions, it does not suppress them.


## 10. The webhook (`H`)

- **H-1** The payload MUST be flat, self-describing and consumable without
  parsing the human-readable output.
- **H-2** Every payload MUST carry `plugin`, `plugin_version`, `timestamp`,
  `host`, `status`, `exit_code` and `message`; a scan payload MUST add at
  least `rating`, `rating_label`, `product`, `product_version`, `domain`,
  `scanned_at`, `eol`, `release_type`, `lifecycle`, `vulnerability_count`,
  `vulnerabilities`, `missing_hardenings`, `failed_extra_checks`,
  `scan_backend`, `scan_uuid`, `update` and `duration_seconds`.
- **H-3** `missing_hardenings` MUST be empty when hardening checks were not
  requested, and MUST otherwise list only actionable, non-waived measures -
  the same set the alert line and the `hardenings_missing` metric use.
- **H-4** `--webhook-on` MUST include every state at least as severe as the
  one named. The default MUST be `critical`.
- **H-5** A webhook failure MUST NOT change the exit code. The verdict is
  about the instance, not about the notification.
- **H-6** A push format MAY rewrite the request path, and MUST NOT rewrite the
  host (ADR 0040).


## 11. Configuration (`C`)

- **C-1** Precedence MUST be **CLI flag > environment variable > file >
  default**.
- **C-2** Nested file keys MUST flatten one-to-one onto flat names:
  `scanner.target_port` becomes `SCANNER_TARGET_PORT`, read from the
  environment as `COS_SCANNER_TARGET_PORT`. Lists MUST join with `;`.
- **C-3** Every environment variable this project reads MUST carry the `COS_`
  prefix.
- **C-4** A configuration file ending in `.json` MUST be parsed as JSON and
  anything else as YAML. The format follows the suffix, not the content.
- **C-5** `factory.py` MUST be the only place configuration becomes
  `ScannerSettings` or `ReleaseSettings`, and those MUST be frozen
  dataclasses.
- **C-6** A value MAY be given indirectly as `secret://`, `file://`, `env://`
  or `exec://`, or through a `_FILE`-suffixed name, so that no credential need
  be written into the configuration file.
- **C-7** The version MUST have exactly one source, the `version` field of
  `pyproject.toml`. A literal `__version__` assignment MUST NOT be
  reintroduced.
- **C-8** Adding one setting MUST touch all of: `factory.py`, the plugin flag,
  the `cli.py` subcommand, the `wizard.py` question, the README option table,
  `config/check-opencloud-security.example.yml`, and entries in `CHANGELOG.md`
  and `RELEASE.md` under the version in `pyproject.toml`.


## 12. Conduct of a scan (`P`)

What the scanner is allowed to do to somebody else's machine.

- **P-1** Every request the scan makes MUST use `GET`, `HEAD`, `PROPFIND` or
  `TRACE` - safe methods by RFC 9110, none able to change the instance. The
  set MUST NOT be widened.
- **P-2** No probe may send a credential, with one exception: the documented
  demo passwords, to the instance's own identity provider.
- **P-3** Every HTTP request MUST go to the base URL the caller gave, and no
  other. A probe MUST NOT take its address from the target's own response.
- **P-4** DNS lookups MUST use only the resolver in `/etc/resolv.conf`, never
  a public one - a scan that asked a third party would hand it the hostname
  being scanned (ADR 0024).
- **P-5** When no resolver is available, or the one found cannot answer, the
  finding MUST be left out rather than guessed at (ADR 0038).
- **P-6** Concurrency MUST be per call site and MUST NOT nest. `_run_all`
  creates its own pool and MUST preserve submission order.
- **P-7** A `requests.Session` MUST NOT be shared across threads. `_Probe`
  keeps one per worker; a second base URL MUST be reached through
  `_Probe.derive(url)`.
- **P-8** The default worker count MUST be `1`, i.e. sequential.
- **P-9** Transport security MUST be rated from measured parameters, never
  assumed from a version string or a vendor default (ADR 0013, ADR 0023).


## 13. The web application (`X`)

`webapp/` runs the same local scanner for a URL a stranger submits.

- **X-1** A request MUST choose **what** to scan, never **how hard**. The
  accepted fields are exactly `target_url`, `ignore_hardenings`,
  `release_track` and `output_format` (batch: `targets` in place of
  `target_url`); anything else MUST be rejected with `422`.
- **X-2** Concurrency, timeouts and TLS policy MUST be `COS_WEB_*` environment
  settings with no request-side equivalent.
- **X-3** Overload MUST queue, never `503`. A submission past the worker count
  MUST receive a uuid and wait FIFO.
- **X-4** A uuid MUST be a capability: its own `scan:{uuid}:*` Redis namespace
  with a TTL. Unknown, invalid and expired identifiers MUST all answer `404`,
  and there MUST be no endpoint that lists scans.
- **X-5** A scan MUST be in exactly one of `queued`, `running`, `completed`,
  `failed`; the last two are terminal.
- **X-6** Results MUST NOT be cached (ADR 0002), and a response MUST be
  uncacheable until its route opts in (ADR 0031).
- **X-7** The SSRF guard MUST resolve and pin the one submitted target. Every
  probe MUST go to that pinned address ([P-3](#12-conduct-of-a-scan-p)).
- **X-8** MCP MUST call this service's own HTTP API in-process, never the
  internals, so that the SSRF guard, the rate limit, the cooldown and the
  queue apply to an agent exactly as to a browser (ADR 0011).
- **X-9** A batch MUST count every target exactly as if it had been submitted
  on its own. It is a convenience, never a discount on the limits.
- **X-10** Reading a limit MUST NOT spend it, and a rescan MUST be an ordinary
  submission (ADR 0032).
- **X-11** Public pages MAY be indexable; results MUST NOT be (ADR 0009).
  Machine-readable descriptions MUST always be public (ADR 0010).
- **X-12** The release schedule and the advisory database MUST refresh
  themselves daily from published sources, and MUST only ever *gain*
  knowledge - a failed or truncated fetch MUST NOT remove what is already
  known (ADR 0016, ADR 0017). Refreshed data MUST be attested, not merely
  fetched (ADR 0027).
- **X-13** The service MUST refuse to start without its encryption key
  (ADR 0008).
- **X-14** A listener MUST bind loopback by default, and a wider bind MUST
  require a credential (ADR 0030).
- **X-15** Exports MUST be dependency-free (ADR 0006) and MUST offer `json`,
  `csv`, `sarif` and `pdf`.
- **X-16** The frontend MUST be fully self-hosted - no CDN, no framework
  bundle, no font service - and the CSP MUST NOT contain `unsafe-inline`: no
  `style=`, no `<style>`, no `onclick`, no inline `<script>`.
- **X-17** `webapp/` MUST hold no markup; everything the browser sees lives in
  `frontend/`.
- **X-18** `webapp/` and `frontend/` MUST NOT ship to PyPI. They ship as
  `check_opencloud_security_web.tar.gz`.
- **X-19** Erasure on request MUST be honoured (ADR 0007).


## 14. Prohibitions (`N`)

Rules whose whole content is that something must never exist.

- **N-1** There MUST NOT be a remote scan API. The plugin works out everything
  it reports by talking to the instance itself, and MUST NOT acquire a client,
  token or endpoint for a service that returns a verdict.
- **N-2** No real instance may be referenced. A hostname the project is tested
  against MUST NOT appear in code, tests, documentation or commit messages;
  examples use `opencloud.example.com`.
- **N-3** Nothing in this repository may connect to Twitter/X, Google or Meta -
  no script, stylesheet, font, iframe, image, API, SDK, analytics, tag
  manager, CAPTCHA, sign-in, share button, embed, or card metadata naming any
  of them. This holds for the plugin, the scanner, the web application, the
  frontend, the container images, the CI workflows and the documentation
  alike. A visitor is handing over the address of a system they are
  responsible for; a request to one of those platforms turns that into a
  record somebody else keeps. Platform-neutral, request-free metadata such as
  OpenGraph `og:` tags is permitted, because nothing fetches it.
- **N-4** The version MUST NOT be bumped by anyone but the user, and tags and
  releases MUST NOT be created on their behalf. A bump landing on `main`
  publishes to PyPI immediately.
- **N-5** A security advisory MUST NOT be published on the user's behalf. The
  record is written and left `draft`; publishing raises Dependabot alerts for
  every affected installation and cannot be undone.
- **N-6** A `### Security` entry in `CHANGELOG.md` MUST have a matching record
  in `security/advisories/`, written in the same pull request.
  `scripts/security_advisories.py --check` enforces it. Declining an advisory
  is a normal outcome; leaving the question undecided is not.


## Trademarks and affiliation

This project is independent. It is **not** affiliated with, endorsed by,
sponsored by or supported by OpenCloud GmbH, and nothing it reports is an
official statement about OpenCloud software. "OpenCloud" and all related names
and marks belong to their respective owners and are used only to identify the
software being checked.
