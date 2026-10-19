# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes are collected under **[Unreleased]** as they are made. The version in
`pyproject.toml` is bumped by hand; when that bump lands on `main`, the release
workflow renames the [Unreleased] heading to that version, writes the same
entry to `RELEASE.md` and uses it as the body of the GitHub release.

## [Unreleased]

### Security

- **The container images ship urllib3 2.8.0.** `uv.lock` pinned urllib3
  2.7.0 (PYSEC-2026-4175, -4176, -4177), and since 1.31.1 the container
  images install exactly what `uv.lock` pins. The PyPI package does not pin
  urllib3 and picks up the fixed release on its own. The lock also moves
  virtualenv from 21.7.7 to 21.14.11 (PYSEC-2026-4011 to -4014); it is a
  development dependency that no image or package contains.

### Changed

- **Every locked dependency is on its newest release.** `uv lock --upgrade`
  moved the whole set in `uv.lock`, which the container images install and
  CI tests against - among them mcp 2.3.0, pydantic 2.14.1, starlette 1.7.0
  (1.9.0 on newer Pythons), uvicorn 0.54.0, idna 3.20, pyjwt 2.15.1, mypy
  2.4.0 and playwright 1.64.0. `pyproject.toml` is unchanged, so the ranges a
  `pip install` accepts are the same as before. `pip-audit` finds no known
  vulnerability in the new set.
- **The signed-in stack runs authentik 2026.8.4.** The setup wizard and
  `docker/docker-compose.authentik.yml` pinned 2026.8.2; `AUTHENTIK_TAG`
  still overrides it. Redis 8.10 and Postgres 18.6 were already current.
- **Every GitHub Action is on its newest release, still pinned by commit.**
  setup-uv 10.3.0, setup-node 7.1.0, upload-artifact 7.0.2,
  download-artifact 8.0.2, setup-buildx-action 4.4.1 and codeql-action
  4.39.0; the diagram workflow renders with mermaid-cli 12.0.0.

### Fixed

- **An automated release-schedule pull request no longer fails CI.** The
  weekly refresh rewrote the release table in `README.md` but not the
  `/documentation` page generated from it, so the unit tests and every nox
  session failed on a stale `reference.html`. The workflow now regenerates
  that page and its sitemap revision and commits them with the refresh; the
  architecture-diagram refresh likewise updates the copy the frontend serves.
- **CI no longer breaks when a new ruff is released.** The workflow ran
  whatever ruff was newest, and 0.17 flagged two `noqa` comments for a rule
  the project never enables. The comments are gone and the workflow pins
  `ruff@0.17.1`, like zizmor and Biome already are.
- **A waiver test no longer expires with the calendar.** It built its waivers
  from a fixed date but scanned with the real clock, so from 4 October 2026
  one of them was already expired in the scan and the test failed on every
  run.

## [1.31.2] - 2026-09-25

### Security

- **The erasure credential throttle counts an IPv6 client by its /64.** Failed
  guesses at the `DELETE /api/purge` token were counted per single address,
  while every other limit counts an IPv6 client by the /64 it is handed - so
  rotating the interface identifier bought five fresh guesses each time. The
  32-character minimum on the token kept guessing impractical regardless.
- **The scan service refuses a guessable token on a wide bind.** Serving
  anywhere but loopback required a token but accepted any non-empty one -
  `--token a`, or the placeholder `secrets/scanner_token.example` ships with -
  and nothing counts failed attempts, so a short token let anybody who reached
  the port make it scan whatever they named. Such a bind now needs a token of
  at least 32 characters that is not that placeholder, or it refuses to start.
  `openssl rand -hex 32`, which every guide already uses, is unaffected.

### Fixed

- **A check only one of two scans made is no longer called new or resolved.**
  Comparisons read a finding missing from the earlier scan as passing, so a
  check added by a newer scanner - or by turning the extra checks on - was
  reported as a regression of the instance, and a check the later scan no
  longer made as fixed. The baseline, `check-opencloud-scanner diff`, the web
  comparison and `compare_scans` now list these as newly measured or no
  longer measured, based on each scan's coverage block, and the explanation
  files them as scanner changes. A newly measured failure still alerts, and
  `--warn-on-new` still does not suppress it. A report or baseline that does
  not list its checks is compared as before. See ADR 0079.
- Aligned the report expiry footer, warning and live countdown to round remaining
  minutes up consistently in every language.
- **A comparison page rounds its expiry up too.** It rounded the minutes
  left down, so it announced one minute fewer than the result page would.

### Documentation

- Added German, Spanish and French operator architecture and operations documentation, including
  localized document navigation and operator search. Section anchors and commands
  remain aligned with English; ADRs and release-note bodies remain English.

- Clarified grouped remediation, upgrade estimates, report expiry and operator
  messages in English, German, Spanish and French. A simulated upgrade whose
  grade is limited by findings no longer implies that the grade cannot improve.
  Count labels also read correctly for a single finding.
- Expanded all-language tests for remediation groups, upgrade estimates,
  escaped version strings, singular and plural expiry warnings, and the
  translated decision-record interface around English source documents.
- **Decision records are never translated.** ADR 0077 records that every
  record in `adr/` exists in English only, and once: the operator area shows
  it untranslated in every locale, and translation work leaves `adr/` alone.
- **Changelogs and release notes are never translated.** ADR 0078 records
  that `CHANGELOG.md`, `RELEASE.md` and the GitHub release body exist in
  English only, and that the operator area's Releases tab shows them
  untranslated in every locale.

## [1.31.1] - 2026-09-24

### Changed

- **The coverage warning's alert line is now covered by mutation testing.**
  `tests/test_coverage_regression.py` drives `_apply_baseline` in process but
  was missing from the mutmut selection, so eleven mutants of the branch that
  lifts an OK to WARNING when a measured check turns inconclusive survived.
  It is now listed, and its test asserts the whole alert line: three of those
  mutants left `OK: ` inside the WARNING message without a test noticing.

### Fixed

- **The web report no longer offers "What gets you to A+" under an A+.** When
  no step in the remediation plan raises the grade, because the instance
  already has the top grade or something no setting can change holds it down,
  the plan is headed "Still worth fixing, the grade stays A+" (or whichever
  grade it holds) instead.
  This applies to the dashboard, its contents list, and the PDF and HTML
  exports, in all four languages.
- **`check-opencloud-scanner fleet` lists waiver deadlines in the order they
  end.** Deadlines were sorted by their text, so a waiver written with a
  `+02:00` offset could be listed after one that ends later in UTC.
- **The fleet summary's "Not covered" count counts each host once.** A host
  whose last scan failed long enough ago to be stale was counted twice.
- **The remediation plan no longer fails on a result document whose
  `ratingExplanation.base` is `null`.** The update step's detail is then left
  empty, instead of `remediation_plan()` raising.

### Security

- **An empty listen address no longer counts as loopback for the scan
  service.** Binding `""` listens on every interface, but the check that
  demands a token for anything but loopback let it through. The command line,
  `COS_SERVICE_LISTEN` and the configuration file all fall back to
  `127.0.0.1` when empty, so only a program calling `build_server()` or
  `serve()` with `listen=""` could reach it.
- **The container images install the dependencies `uv.lock` pins, with their
  hashes.** Both `docker/Dockerfile` and `docker/Dockerfile.web` resolved
  their dependencies from PyPI at build time, so an image could ship versions
  that CI, `pip-audit` and the SBOM never saw.

## [1.31.0] - 2026-09-24

### Documentation

- Polished scan progress, errors, downloads and sharing text in English,
  German, Spanish and French. Corrected informal Spanish instructions and
  clarified that saved downloads remain available after a scan expires.
- Updated all four web-service guides to describe every export format,
  including offline HTML reports and remediation bundles. Expanded tests for
  translated error pages, email drafts, link-free summaries and download links.
- Translation checks now catch additional Spanish forms of informal address
  and report broken guide links at their original line numbers, ignoring
  links shown only in code examples. Added regression tests for both cases.

### Added

- **Coverage regression alerts.** With `--baseline`, a check that an earlier
  run reached a conclusion on and that is `inconclusive` now raises an `OK` to
  `WARNING`, even when the grade has not moved. The rating, its perfdata and
  the findings are untouched: the scan saw less, the instance did not change.
  The warning lasts until the check is measured again, `--warn-on-new` does
  not suppress it, the webhook's `baseline_diff` carries the lost checks as
  `coverage_regressed`, and the two-document comparison reports a
  `coverageRegressed` scanner change. See ADR 0074 and
  [Reporting only what changed](docs/baseline.md#coverage-regressions).
- **Grouped remediation plans.** `remediationPlan.groups` places every open
  finding in the system its fix is made in - the reverse proxy, the identity
  provider, OpenCloud or the DNS zone - and merges the findings one edit
  resolves into a single change: every missing header is one header block,
  every exposed path one proxy rule, and the update closes every matching
  advisory. Each change carries the rating it alone would give, replayed
  through the rating function, and `groupSummary` names the changes that
  resolve several findings at once. Shown by `--debug`, on the web dashboard
  ("What to change where"), in the remediation bundle, and returned by the
  `plan_remediation` MCP tool. See ADR 0075 and
  [What would raise the rating](README.md#grouped-by-where-the-change-is-made).
- **Architecture decisions in the operator area.** A new Decisions tab at
  `/admin/decisions` lists every architecture decision record with its
  status, and a filter narrows the list by number, title or status. Each
  record opens as its own page in English, and links between records, or from
  the Architecture tab, stay inside the area. The area's search now indexes
  every record's full text. Like the rest of the area, the records are never
  public: a stranger gets a 404, and they are absent from the public search,
  the sitemap and `/documentation`.
- **`check-opencloud-scanner review-waivers`.** It reads the configured
  waivers (`ignore_hardenings` and `temporary_waivers`, or the
  `--ignore-hardening` and `--waive-until` values given to it) and lists five
  kinds that need attention. *Expired* waivers no longer suppress anything.
  *Expiring soon* ones run out within the `waiver_warning` window. *Unused*
  ones match no failing check in a `--result` document, or with no document,
  no identifier the scanner knows. *Overlapping* ones are already covered by
  another waiver, such as a deadline hidden under a permanent `*`.
  *Permanent* ones have no reason and no deadline. Each item has a suggested
  cleanup, for a permanent waiver a `--waive-until` record to copy. The
  command never changes the configuration. It exits `1` when it lists
  anything, unless given `--exit-zero`, and `--format json` suits scripts. See
  [the scanner command](docs/scanner-cli.md#review-waivers---waivers-that-need-attention).
- **`check-opencloud-scanner fleet`.** It turns saved `scan` result
  documents into one summary of a fleet. Give it files, or directories that
  it searches for `*.json`, and it keeps the newest report of each host. It
  lists end-of-life releases and releases whose support ends soon. The
  recorded version is placed in today's release schedule again, so a line
  that closed after the report was written is listed too. It lists waivers
  that let a failing check alert again within `--window` days (default
  `30`), measured against today. It counts the failing findings that most
  hosts share, and leaves out the ones no operator can change. Under missing
  coverage it lists stale reports (`--stale-after`, default `7` days), failed
  scans, checks the scans could not evaluate, and hosts named by `--expect`
  or `--inventory` that have no report. The output is text, Markdown, JSON,
  or one self-contained HTML page that fetches nothing. It never scans,
  stores nothing and applies no threshold, so it exits `0` whenever it
  printed a summary. See
  [the scanner command](docs/scanner-cli.md#fleet---a-dashboard-from-saved-results).

### Fixed

- **The `.deb` install smoke test survives a mirror caught mid-sync.** When
  the Ubuntu or Debian mirror lists a dependency it no longer serves (a
  404), `packaging/tests/install-smoke.sh` refreshes the package index and
  tries the install once more before the release dry run fails.

## [1.30.2] - 2026-09-24

### Changed

- **Tests now cover code that no test reached before.** The advisory refresh
  script `scripts/update_vulnerability_db.py` has tests. They prove that it
  writes new advisories and that `--check` writes nothing. If the feed is
  down, the script keeps the file. `scripts/verify_export.py` has tests too. They
  prove that it refuses edited bytes, the wrong key and a missing key. The scan
  child process in `webapp/scan_process.py` has tests for a rejected target, a
  failed scan and a crash. A rejected target stays a rejection in the worker,
  and a crash sends no exception text. The approval mode in
  `webapp/approval.py` has tests that prove DNS never approves an address
  target, and that a failed TXT lookup is a refusal.
  `tests/test_verify_remediation.py` now makes sure that every extra check and
  hardening flag of a full scan verifies to the same answer, not only three of
  them.

### Documentation

- Clarified operator status, comparison results, monitoring instructions and
  TLS explanations in English, German, Spanish and French. Corrected Spanish
  forms of address and translated two overlooked deployment settings rows.
- Expanded translation tests to cover copied English table descriptions,
  duplicate catalogue keys, repeated placeholders, and formatting and HTML
  escaping across every language, including messages on conditional pages.

### Fixed

- `--waiver-warning` and `waiver_days_left` no longer count a waiver that
  only covers a flag OpenCloud hardcodes, such as
  `publicLinkExpirationEnforced`. That flag never alerts, so the end of its
  waiver changes nothing. Before this fix, such a waiver raised a WARNING.
- The plugin output now says "1 day left" instead of "1 days left" in the
  end-of-life warning, the lifecycle line and the waiver warning. If one
  waiver covers several checks, the waiver warning now says that they
  "alert again".
- If two waivers end at the same moment, the waiver warning now names both.
  Before this fix, it named only one waiver but listed the checks of both.

## [1.30.1] - 2026-09-23

### Added

- `--waiver-warning DAYS` (`COS_WAIVER_WARNING`, YAML `waiver_warning`)
  sets a warning window for `--waive-until` waivers. If a waiver that hides
  a failing check ends within `DAYS` days, an otherwise OK result becomes
  WARNING. Before this, a waiver gave no lead time. The check was silent
  until the deadline and alerted on the next run after it. The long output
  also names the next waiver to end. The default `0` turns the warning off.
- The `waiver_days_left` performance value counts the days until that
  waiver ends. With `--waiver-warning` it carries the window as its warning
  range. Checkmk reports it under the same name, and Prometheus and OTLP as
  `opencloud_security_waiver_days_remaining`. The webhook payload adds
  `waiver_days_left`, `waiver_warning_days` and `waiver_warning`, and
  `contrib/prometheus/alerts.yml` adds an `OpenCloudWaiverExpiring` rule.
- The `coverage_inconclusive` and `coverage_not_checked` performance values
  put the coverage block on a graph. A graph now shows the day that checks
  become unreadable. Checkmk uses the same names, and Prometheus and OTLP use
  `opencloud_security_coverage_inconclusive_total` and
  `opencloud_security_coverage_not_checked_total`. The grade does not change.

### Documentation

- Replaced vague and literal wording in the interface, scanner guides and
  README. Aligned English, German, Spanish and French explanations and
  corrected inconsistent forms of address.
- Completed the remaining French guide translations while preserving commands,
  technical values and section links.
- Expanded wording checks to current repository documentation and Python
  product strings, including phrases split across lines. Added regression
  cases and a translation review checklist. Corrected inconsistent exemption
  terminology and Spanish plural recognition in the glossary check. Recorded
  reviewed plain-language alternatives so they no longer produce warnings.

## [1.30.0] - 2026-09-22

### Documentation

- Listed `tests/test_monitoring_export.py` in the test index, so the
  scheduler-export tests can be found by purpose.

- Clarified German operator messages about wildcard DNS and temporary
  application updates, and replaced the literal TLS introduction with a
  description of the measured values. Added three wording regression cases.

- Clarified configuration-drift explanations in the English, German, Spanish
  and French baseline guides. Older baselines lack fingerprints, so an absent
  drift report does not establish that the configuration is unchanged.
  Added regression cases for vague and anthropomorphic wording in all four
  languages. Fixed four French guide links to the documentation index found
  by the translation tests.
- Reworded literal German and Spanish translations in the baseline and scanner CLI
  guides, including severity comparisons and missing measurements. Added
  regression cases for the awkward phrases found during review.

### Added

- **The setup wizard exports the scheduled check, not just the configuration.**
  `check-opencloud-scanner configure` now offers to write the monitoring
  configuration next to the file it saved, and `--export-monitoring`
  (`icinga`, `systemd`, `both`, `none`) answers that question up front for a
  provisioning script. It produces an Icinga 2 `Service` object, and a systemd
  `oneshot` service, `daily` timer and `COS_` environment file, each carrying
  the thresholds, the release track and every other answer just given - so the
  check that runs every day is the one that was configured rather than an
  example adjusted from memory. Two rules shape the output: **nothing is
  installed** (the files are written for review and the install commands are
  printed, never run), and **no credential is written into them** - a webhook
  URL or release token stays in the owner-only configuration file, which both
  artefacts point at with `vars.opencloud_config` and `COS_CONFIG_FILE`, and
  the settings withheld are named rather than silently dropped. The generated
  unit carries the same hardening directives as the one in `contrib/systemd/`,
  asserted by a test so it cannot quietly become a weaker copy.

- **`check-opencloud-scanner diff` compares two results finding by finding.**
  A new `--format side-by-side` states both scans as two columns, one finding
  per row, so a reader does not have to rebuild each side from a list of
  changes; `--all-findings` adds the findings that did not move. Every
  comparison now reports per-finding severity movement - a `~` line and a
  `Failing by severity:` tally - which the baseline's comparison of two sets
  of names cannot express: a check that stayed open and moved from `high` to
  `critical` never enters or leaves that set, and caps the rating a grade
  lower. `--category` narrows the comparison to one area, taking a value
  either from the finding categories (`exposure`, `headers`, `transport`,
  `advisory`, ...) or from the change categories (`instance`,
  `referenceData`, `scanner`, `policy`, `unknown`); an unknown value is
  refused rather than silently showing nothing. `--format json` carries the
  same as `findings` and `severityTotals`. A side that was never measured is
  reported as such and never as a pass, and a waived finding is still counted.

- **A finished scan downloads as a remediation bundle: only the work that is
  left, with the configuration that closes it.** The result page and
  `GET /api/scans/{uuid}/export/{format}` gained `remediation-md` and
  `remediation-html`. A bundle carries **only** the open, actionable findings
  - waived entries and the flags OpenCloud hardcodes are left out - each with
  what the scanner observed, what it means and what to change, followed by the
  nginx, Caddy, Traefik, Docker Compose and `.env` fragments that satisfy
  them, rendered from the hardening catalogue's own `env_fix` and
  `header_fix` entries. Every flavour is written out rather than one, each
  naming which findings it covers and which belong in the other kind of file,
  and a finding whose right value is a decision about the deployment is listed
  as having no mechanical fix rather than given a placeholder to edit. The
  grade, the passed checks and the advisory list stay in the full report:
  repeating them here would bury the one thing the file is for.

- **SARIF output now carries what a code-scanning dashboard needs to act on a
  finding.** `--format sarif` previously named a rule and a level and left the
  rest to a reader's own research. Each rule now carries the hardening
  catalogue's remediation sentence, the official documentation link
  (`helpUri`), the catalogue entry that explains a per-path finding
  (`catalogueId` - `exposed` for `exposed:/opencloud.yaml`), the setting
  behind it, and the `security-severity`, `problem.severity` and `tags`
  properties GitHub code scanning sorts and filters alerts on. Each result
  carries the severity, category, remediation and reference beside the host,
  and a `partialFingerprints` entry stable across runs, so a finding that has
  been open for a month stays one alert with a history rather than a new one
  every night. An advisory additionally names `fixedIn` and the release
  window it covers (`affectedRanges`, e.g. `>= 1.0.0, < 4.0.8`), and the run
  reports the rating, version and end-of-life state per scanned host. The web
  application's own SARIF export gained the same properties and fingerprints,
  keeping the two renderers in convention-sync as ADR 0026 requires.

- **A scan result's `vulnerabilities` entries name the release range they
  apply to.** `affectedRanges` (and `introduced`) join `fixedIn`, so a reader
  can tell whether an older release was ever affected rather than only which
  release ends the window.

### Fixed

- **The French scanner CLI guide no longer ships the newly added comparison
  sections in English.** Its `diff` explanation, severity view, side-by-side
  output and category filtering are now translated, and regression tests catch
  those copied-English phrases in future guide updates.

- **The German operator area no longer leaves avoidable English labels in
  place.** Advisory status is shown as Sicherheitsmeldungen, update controls
  as Aktualisierungen, and the audit section consistently names its log.

## [1.29.3] - 2026-09-22

### Fixed

- **Sloppy generated wording was removed from the English, German and French<
  documentation.** Replaced vague promotional phrases and awkward literal
  translations in the Kubernetes, scanner and reference-data guides, rebuilt
  their frontend pages, and expanded the translation-quality tests with
  regression cases for these patterns.

## [1.29.2] - 2026-09-22

### Fixed

- **`/llms.txt` and `/llms-full.txt` described an older version of the
  service.** They are the map an agent reads before deciding what this
  service can do, and four of their facts had fallen behind the code:
  `/mcp` was described as six tools and six prompts where it registers seven
  of each, `compare_scans` was missing from the tool list in the long form,
  the export formats omitted `html`, and the endpoint summary never mentioned
  `GET /api/scans/{uuid}/badge.svg`. An agent that trusts the map would have
  concluded the badge and the HTML export do not exist. All four now match
  what `webapp/mcp_server.py`, `wf.EXPORT_FORMATS` and `webapp/openapi.py`
  actually serve.

- **A page's `<lastmod>` in `sitemap.xml` now moves only when the page really
  changed.** The date came from the modification time of the template that
  renders the page, and a checkout, a container build and an unpacked release
  tarball all write every template at once - so every public page claimed to
  have changed on release day, and a crawler told that everything changed
  learns nothing from the file. Each public page's date is now recorded next
  to a digest of its template in `webapp/data/page-revisions.json`, and
  `scripts/update_page_revisions.py` moves a date only when that digest does.
  A page the record has never seen, or one edited since it was written, still
  falls back to the modification time rather than publishing a date that is
  no longer true. CI checks the record with `--check`, as it does for the
  generated documentation.

- **The German, Spanish and French pages no longer drop names the English
  text uses to say what this is.** The translated "About" paragraph called the
  plugin a generic monitoring plugin, so a reader of those pages never learned
  it plugs into Nagios and Icinga, and it also lost the English sentence's
  point that running it yourself has no rate limit or queue. The German and
  French descriptions of the method page said "what the scanner checks"
  without naming an OpenCloud instance, and the Spanish search summary for the
  API page dropped OpenAPI, Arazzo and MCP - the three things somebody
  searching for that page is searching for. All four strings now carry the
  names again; the search index is rebuilt with them.

## [1.29.1] - 2026-09-21

### Changed

- **The `--policy` deployment gate is now covered by tests mutation testing
  can run.** Its behaviour was only ever exercised through the real CLI, which
  runs the plugin as a subprocess, so mutation testing could delete the scan
  document, the rating or the vulnerability list that `_apply_policy` is
  handed - and drop the policy verdict from the webhook payload - without a
  single test noticing. A violation that should fail a pipeline could have
  stopped failing it silently. `tests/test_policy_gate.py` now drives the same
  gate in process and is listed in the mutmut selection; the five surviving
  mutants it was written for are killed.

- **A result list that no longer lines up with the checks that produced it is
  now an error rather than a shorter report.** Every place the scanner and the
  plugin pair a list of checks with the results `_run_all` returned for them -
  the exposed paths, the protected endpoints, the debug endpoints and ports,
  the demo accounts, and the per-host rows of the `checkmk` and `summary`
  output formats - zipped the two without asserting they were the same length.
  The lengths match by construction today, so nothing changes for any scan that
  runs; what changes is the failure mode if a later edit breaks that pairing.
  Silently dropping the tail would have meant a report that omits checks
  without saying so, which reads as an instance that passed them. The one
  pairing deliberately left lenient is the lifecycle page parser, where the two
  lists come from somebody else's HTML and a tab without a panel must be
  dropped rather than raise.

### Fixed

- The browser test for the severity filter no longer drops its own press in
  WebKit on CI. Pressing a counter hides most of the list and reveals the
  status line above it, so the page it leaves behind is a different height
  from the one that was pressed; the test read the new count back with a
  single sample and pressed *clear* straight away, on a control that was
  still settling. WebKit dropped that press rather than delivering it, the
  filter stayed on, and the run failed counting a list nobody had asked for.
  Each press is now waited out for the count it asked for before the next one
  is aimed, which still fails - loudly - if a press is ever genuinely lost.

## [1.29.0] - 2026-09-21

### Added

- **A scan fingerprints the configuration it measured, so drift is visible
  without the grade moving.** A rewritten content security policy, a replaced
  reverse proxy, public links that stopped requiring a password, a certificate
  at a different issuer - none of that has to change a grade, and an operator
  watching only the grade saw none of it. The result document now carries a
  `configuration` block: grouped digests for transport, headers, sharing,
  authentication and proxy, plus one over all five. **Digests only, never the
  configuration** - a policy, an issuer and a server banner go in and a hash
  comes out, so the block is safe on a public page, in a webhook and in an
  uploaded report. The plugin prints `Configuration fingerprint: 9e3c4428`,
  `--baseline` reports `No new findings, but the configuration changed
  (headers)`, `check-opencloud-scanner diff` adds a `configurationChanged`
  change, and the web application shows the groups under *Has this deployment
  changed?*. Routine churn is deliberately excluded: a renewed certificate and
  a proxy's new build number are not drift, and a group the two scans looked
  at differently is reported as not comparable rather than as a change.
  Nothing in it touches a rating, an exit code or an alert line. See
  [ADR 0073](adr/0073-a-result-fingerprints-the-configuration-it-measured.md).
- **`--policy` fails a deployment on explicit requirements, not on a grade.**
  `-w`/`-c` and `--profile` judge an instance by its rating, which is the
  wrong shape for a CI gate: a team that requires HTTPS enforcement and no
  demo accounts cannot express that as a number. A policy file states it
  directly - `minimum_rating`, `required_hardenings` and `forbidden` (a
  missing measure, a failed check or a vulnerability id) - and anything it
  asks for that an instance does not meet ends the run CRITICAL. A policy
  only ever makes a verdict worse, a waiver does not excuse a requirement,
  and an unknown key or measure is a usage error rather than a rule that
  quietly requires nothing. `--format json` and the webhook payload carry the
  verdict under `policy`. See [CI policy mode](README.md#ci-policy-mode) and
  [`config/policy.example.yml`](config/policy.example.yml).
- **`--format summary` reads a whole fleet in one table.** Checking a dozen
  instances printed a dozen result blocks written for a monitoring system,
  which is a lot to read when the question is just "which of these needs me
  today". The new format prints one aligned row per host instead - host,
  grade, version, end-of-life state, how many advisories apply, and how much
  moved since `--baseline` - followed by the same tally the Nagios output
  starts with. Rows keep the order the hosts were given and the exit code is
  unchanged, so it works from a cron job that mails its output. The `NEW`
  column distinguishes "no baseline given" (`-`) from "no new findings" (`0`),
  and a host whose scan failed shows its Nagios status where the grade would
  be. See [Reading a fleet in one table](README.md#reading-a-fleet-in-one-table).
- **The output says how much it could actually measure.** A check that
  passed and one that never ran left the same trace in the plugin's output -
  nothing - so the plugin now prints a `Coverage:` line such as `84 checks
  evaluated, 6 skipped, 2 indeterminate, 1 network-limited`, and the webhook
  payload and `--format json` carry the same counts under `coverage`. The web
  application's *What this scan did not measure* section shows the same four
  numbers. `network_limited` is split out of the skipped and indeterminate
  counts because a timeout or a missing route - DNSSEC, an external identity
  provider, an optional endpoint - is the gap another vantage point might
  close. Nothing in it changes a grade, an exit code or an alert line.

## [1.28.1] - 2026-09-21

### Added

- **`--profile` judges a scan by a named threshold set.** `strict`, `ops` and
  `lenient` each decide the five settings a team otherwise writes out by hand
  - `--warning`, `--critical`, `--check-hardening`, `--update-warning` and
  `--eol-warning` - so a monitoring definition can adopt a stance without
  twelve flags. A profile decides **how the same measurements are judged,
  never how hard the instance is probed**: there is no profile that scans
  more or less. It is also the weakest source of a value, so an explicit
  flag, an environment variable or a configuration key still wins, and the
  `--debug` explanation names the profile a rating was judged by. Leaving it
  unset keeps every default exactly as it was. See
  [Threshold profiles](README.md#threshold-profiles).

- **The web application renders the upgrade rehearsal.** The result page
  gains a *What upgrading would buy you* panel: one row per candidate
  release, with the advisories it clears, the ones it leaves, any it newly
  brings in, whether it is already end of life, and the grade it would reach.
  Where the version alone would rate better than the row shows, the panel
  says so - the difference is this instance's own findings, which an upgrade
  does not touch. Every number comes from the scanner's `upgradeRehearsal`;
  the web layer only picks the letter and the tone, as it does for every
  other grade on the page. A result stored before the rehearsal existed
  renders without the panel rather than as an instance with nothing to
  upgrade to.

- **A golden corpus of frozen verdicts.** `tests/golden/` records the whole
  judgement a handful of known instances earn - rating, grade, failed checks,
  missing measures, the caps that produced the rating and the exit code under
  the plugin's defaults and under every profile - and `tests/test_golden_corpus.py`
  replays them. It is the assertion no single test makes: that a severity
  raised or a measure added to the catalogue cannot silently re-grade every
  instance that looks like one of these. The reference data is pinned in
  `tests/golden_corpus.py`, so a published release or advisory does not move
  the corpus; `python scripts/update_golden_corpus.py` rewrites it when the
  new verdict is the intended one.

### Changed

- **The Icinga check commands offer `--profile`.** The three CheckCommand
  definitions - `contrib/icinga2/check_opencloud_security.conf` and the
  `opencloud_check_native` / `opencloud_check_docker` role templates - carry
  the new option as `$opencloud_profile$`, next to `--warning` and
  `--critical`. Without it an Icinga user could not reach a profile at all,
  which is what `tests/test_monitoring_parity.py` is there to notice.

- **The upgrade rehearsal's reporting is pinned by tests.** Mutation testing
  found the two plugin helpers behind it under-covered: an end-of-life
  candidate, a malformed entry, a rating outside the 0-5 range and seven of
  the webhook payload's ten keys were asserted by nothing. The gaps are
  closed, and `tests/test_verify_remediation.py` and
  `tests/test_threshold_profiles.py` are now part of the mutmut test
  selection, which reported "no tests" for `verification.py` before.

### Security

- **The web application sends `Strict-Transport-Security` over HTTPS.** The
  generated reverse-proxy configuration deliberately adds no security headers
  - "the application sends its own, and an `add_header` here would be one
  more place they can disagree" - and HSTS was the one the application did
  not send, so no deployment built by `docker/setup-wizard.py` had it. A
  service whose subject is HTTPS enforcement now asks of itself what
  `hstsLongMaxAge` and `hstsIncludeSubdomains` ask of the instances it
  scans: `max-age=63072000; includeSubDomains`. Not `preload`, which is an
  effectively irreversible submission to a list browsers ship and belongs to
  whoever owns the domain. Sent only over TLS, because RFC 6797 forbids a
  browser to record it from a cleartext hop - and the scheme is read from
  `X-Forwarded-Proto` only where `COS_WEB_TRUST_FORWARDED_FOR` says a proxy
  writes it, which is the same trust decision `client_address` makes.

- **A tampered erasure receipt verifies as false rather than raising.**
  `webapp.purge.verify` compared the expected digest with the receipt's
  signature as `str`, and `hmac.compare_digest` raises `TypeError` on a
  string outside ASCII - so a receipt edited to carry one answered an auditor
  with a traceback instead of the `False` the function is read for. Both
  sides are encoded now, exactly as the purge endpoint has always compared
  its token. The endpoint itself was never affected.

## [1.28.0] - 2026-09-20

### Added

- **Upgrade rehearsal: what each candidate release would fix, leave and
  rate.** The scan result gains `upgradeRehearsal`, which simulates every
  release worth moving to (the newest patch of the installed line and the
  newest release of each later line, only on the declared track) against the
  advisory database and the release schedule. The plugin prints it as one
  detail line, for example "Upgrade rehearsal: 7.2.4 fixes 3 findings,
  leaves 1, reaches rating C", and the webhook payload carries it as
  `upgrade_rehearsal`. The rating replays the scanner's own version rules and
  keeps the instance's failed checks as caps, because an upgrade does not
  change the proxy. See
  [Rehearse every upgrade](docs/release-lifecycle.md#rehearse-every-upgrade).

- **A scan the target cooldown refuses now opens your earlier result.** When
  an instance was scanned too recently and this browser tab has already shown
  a finished scan of it, the web application opens that result instead of
  only refusing, says it is the earlier result, and counts down to when a new
  scan is possible. The earlier result comes from the tab's own scan history
  (the one the comparison offer keeps in `sessionStorage`); the server never
  hands one visitor a scan somebody else started, as
  [ADR 0002](adr/0002-no-scan-result-caching.md) requires. Without such a
  scan the refusal is unchanged.

- **`--verify-remediation` re-checks one finding without a full scan.**
  After changing a single reverse-proxy setting, pass the finding ids the
  full output reported (repeatable or comma-separated, a family root such as
  `exposed` covers every member) and only the probes that measure them run.
  The plugin answers `OK` when every one now passes, `WARNING`/`CRITICAL`
  while one still fails, and `UNKNOWN` for an id only a full scan can settle
  (`eol`, a vulnerability, address parity). No rating, baseline or webhook.
  The measurement is `opencloud_local_scan.verification.verify`, which reuses
  the scanner's own probes so its answer matches the next full scan. See
  ADR 0072.

### Documentation

- **Translated release-lifecycle guides now include the upgrade-rehearsal
  section.** Their section anchors stay aligned with the English guide.

### Fixed

- **A gateway answer no longer fails the documented link check.** An HTTP
  408, 502, 503 or 504 comes from the machinery in front of a site, not from
  the page, so it is now retried like a transport error and - when the whole
  run is unlucky - reported without failing the workflow. A link that rotted
  answers 404; a merge that fails because GitHub was briefly slow is exactly
  the noise this check is meant to avoid.
- **Pytest no longer collects mutmut's generated working copy.** This avoids
  an `ImportPathMismatchError` between the real and mutated test suites.

## [1.27.2] - 2026-09-19

### Added

- **Property-based tests for the parsers that read outside text.**
  `tests/test_properties.py` uses Hypothesis, a new test-only dependency
  (reviewed in `security/dependencies/hypothesis.yml`), to generate inputs
  for version parsing and comparison, advisory ranges, the
  Strict-Transport-Security and Content-Security-Policy readers, the web
  application's SSRF guard (private literals, IPv4-mapped and 6to4
  addresses, arbitrary input) and the `;`-joined configuration lists.
- **The output documents' key names are pinned.**
  `tests/test_output_shape.py` fails when a top-level key of the scan result
  or of the plugin's `--format json` / webhook payload is renamed, added or
  dropped, or when a key breaks the camelCase (result) / snake_case (plugin)
  convention, so a breaking rename cannot land unnoticed.
- **The advisory database also reads OpenCloud's repository advisories.**
  OpenCloud publishes some advisories only on its GitHub repository, where
  OSV never sees them. The daily refresh (`scripts/update_vulnerability_db.py`,
  new `--repository-url`) and the web application's refresh (new
  `COS_WEB_ADVISORY_REPOSITORY_URL`, `off` to skip) now add those
  advisories. Their version ranges are read strictly: an advisory fixed on two
  release lines becomes one range per line, and prose ranges are never
  guessed at. OSV stays the primary source, and if the repository feed can't
  be read, OSV's answer is kept.
  [ADR 0071](adr/0071-repository-advisories-are-a-second-advisory-source.md).

### Changed

- **Polished recent German, Spanish and French web translations.** Fixed mixed
  forms of address and several literal or awkward phrases in the operator
  update messages, scan facts and coverage explanations.

### Security

- **GHSA-gf4p-7p27-26w7 (CVE-2026-57500, "Access to internal metadata") is
  now reported.** OpenCloud published it only as a repository advisory, which
  never reaches OSV, the one feed the advisory database was refreshed from - so
  every release before 4.0.8, and 5.0.0 up to 7.2.0, was rated as free of
  known advisories. The bundled database now carries it, affecting releases
  from 1.0.0 up to 4.0.8 and from 4.1.0 up to (but not including) 7.2.0.

## [1.27.1] - 2026-09-19

### Added

- Codex can use the repository's Claude Code skills, hooks, subagent roles and
  Playwright MCP configuration through portable `.agents/` and `.codex/`
  compatibility files. The original `.claude/` setup remains unchanged.

- The operator's area shows the running release and whether a newer one is
  published on GitHub (cached six hours, `COS_WEB_UPDATE_CHECK`), and a button
  installs it: the release's web bundle is verified against its Sigstore build
  attestation from this repository's release workflow, unpacked on a tmpfs
  (`COS_WEB_ADMIN_UPDATE_DIR`, mounted by every compose file) and the web and
  worker processes restart on it - a short downtime, lasting until the
  containers restart. The Docker setup wizard sets it up whenever it enables
  the operator's area. The web image now installs the `signing` extra
  ([ADR 0070](adr/0070-the-operator-area-installs-attested-releases-in-place.md)).

### Changed

- mypy now also checks the bodies of functions without annotations
  (`check_untyped_defs` in `mypy.ini`), so CI type-checks the test suite
  too. The 98 errors that surfaced - all in `tests/` - are fixed.

### Fixed

- The Codex scan driver no longer prints the raw scanner document, which could
  expose TLS inspection data in its JSON output; `scan --json` now emits only
  the version, verdict and failed checks.

- The operator area's **Releases** tab never listed the release it was running
  on: the image is built from the version-bump commit, before the release
  workflow renames `[Unreleased]`. The page is now generated with that section
  under the `pyproject.toml` version when the changelog has no heading for it.

## [1.27.0] - 2026-09-19

### Added

- The web report lists an advertised HTTP/3 listener (with its UDP ports) and
  the upgrade path - what the recommended release fixes, what it leaves open
  and which release clears everything - in all four languages.

- `upgrade_path_complete` performance data (`1` when the recommended upgrade
  clears every known advisory, `0` when it does not), and with
  `--eol-warning` the `support_days_left` metric carries that window as its
  warning range and the end of life as critical. The webhook payload gains
  `eol_warning_days`, `eol_warning` and `upgrade_path`.

- `--login-throttling` (`COS_LOGIN_THROTTLING`, YAML
  `scanner.check_login_throttling`, also on `scan` and in the setup wizard)
  sends six failed sign-ins for a random, non-existent account to the
  built-in identity provider and records `loginThrottling` - whether an HTTP
  429 or `Retry-After` slowed them down. Off by default, never graded, run
  after every other probe, and never sent by the web service
  ([ADR 0069](adr/0069-login-throttling-is-observed-only-when-the-operator-asks.md)).

## [1.26.1] - 2026-09-19

### Added

- The operator's area has a **Releases** tab at `/admin/docs/releases`: the
  ten newest released sections of `CHANGELOG.md`, newest first, so an
  operator can read what the running release changed without leaving the
  area. The publish workflow regenerates it together with the release notes.

## [1.26.0] - 2026-09-19

### Added

- `--eol-warning DAYS` (`COS_EOL_WARNING`, YAML `eol_warning`, and a setup
  wizard question) turns an otherwise `OK` result into `WARNING` once the
  running release line has `DAYS` or fewer days of support left, naming the
  end-of-life date and the upgrade target. Off (`0`) by default; past end of
  life stays `CRITICAL` as before.

- The scan result records `upgradePath` when the installed release carries
  known advisories: which of them the recommended release fixes, which it is
  still affected by, and `safeVersion`, the lowest release past every missing
  fix. The plugin prints it as a detail line, so an update that would leave an
  advisory open no longer reads as the whole answer.

- The scan result records `alternativeServices`, what the instance advertises
  in its `Alt-Svc` header, and the plugin prints a detail line when it
  advertises HTTP/3 - a UDP listener a firewall written for TCP 443 may not
  cover. It is an observation, never graded, and the advertised address is
  never probed.

### Changed

- The "On this page" contents list of a scan report groups its up to twelve
  entries into three labelled columns - *Fix*, *Details* and *Keep* - instead
  of one long row of links, so the sections worth acting on stand apart from
  the reference material and the export and share cards.

- The Docker setup wizard opens each section with a two-column card: the step
  counter, progress and the section's purpose on the left, and every section
  of the walk on the right, marked done, skipped or still ahead, with the
  current one highlighted. A terminal narrower than the card, a pipe or
  `NO_COLOR` keeps the plain heading lines.

## [1.25.3] - 2026-09-18

### Added

- The `/check-changelog-docs` skill checks that every new `Added` or
  `Changed` entry under `[Unreleased]` is documented where AGENTS.md requires
  it - the README option table, the example YAML, the `docs/` guides in all
  four languages, `docs/webapp.md`, the guide index and the generated
  `/documentation` pages - and reports each gap as a concrete action. A new
  Claude Code hook stops the first `git commit` that adds such entries and
  asks for the check; retrying the same commit goes through.

- Manual mutation testing for contributors: the `/mutation-test` skill runs
  mutmut through the read-only `mutation-tester` agent on chosen plugin or
  scanner functions and sorts every surviving mutant into a real test gap,
  unreachable code or noise. mutmut 3.8.0 is a new dependency in its own
  `mutation` group - never installed by CI or a plain `uv sync`, never run in
  CI - reviewed and approved in `security/dependencies/mutmut.yml`.

- The browser tests now also run in Chromium, the engine behind Chrome,
  Edge and most Android browsers, as a third job in the browser-tests
  workflow ([ADR 0068](adr/0068-chromium-is-a-third-browser-test-engine-behind-the-dead-proxy.md),
  superseding ADR 0061's WebKit-and-Firefox-only rule). Chromium is
  Playwright's build, which is Google's, and runs behind the same dead proxy
  and request watch as the other engines; WebKit stays the default. The
  workflow now runs every `tests/test_webapp_browser_*.py` file, including
  the enhancements, phone and operator tests it had been leaving out.
  Chromium's first run showed ReDoc asking for Redocly's logo from its CDN;
  the `/redoc` page's policy already blocks it, and a test now keeps it that
  way.

### Fixed

- The end-of-life alert no longer shows a double space ("The 2.x  release
  line") when the scan result names a release line but no release type.
- `--baseline` and `--warn-on-new` are now tested in-process: suppressing an
  unchanged problem, keeping new findings, worse ratings and OK runs as they
  are, leaving waived measures out of the baseline, and a baseline that
  cannot be written. The rating messages (end of life, thresholds, OK and
  UNKNOWN) are pinned exactly. A mutation-testing trial run found both gaps.
- `check_vulnerabilities` is now tested as a whole, in-process: a scan with
  known vulnerabilities and a good rating, the exact hardening and update
  alert lines, what the baseline records with and without
  `--check-hardening`, perfdata, the self-update note, extra-check
  truncation and the payload behind `--format` and the webhook. A
  `/mutation-test` run of the rating, baseline and check functions now
  leaves only 3 equivalent mutants alive (was 108).
- The browser tests for the below-the-fold reveal no longer time out in
  Firefox on CI. They ran the longest page with the blurred fade switched
  on, which starved headless Firefox until even the next page load timed
  out; they now use reduced motion like every other browser test, which
  still exercises the same hiding and revealing, and the motion itself
  stays covered on the landing page.

### Documentation

- Polished awkward German guide wording and corrected inconsistent address forms.

- `docker/docker-compose.yml` now shows every web setting it had left out:
  the operator's area (`COS_WEB_ADMIN_*`), `COS_WEB_AUDIT_LOG_ROTATION` and
  `COS_WEB_RATE_LIMIT_SALT` as commented examples, and why
  `COS_WEB_FRONTEND_DIR` stays unset. The example configuration shows
  `scanner.proxy` and `releases.proxy`, which override the top-level `proxy`.

### Security

- **Scan targets and redirect hops in deprecated IPv6 site-local space are refused.**
  The web service's SSRF guard let the deprecated site-local range (RFC 3879) through because no
  `ipaddress` private flag covers it, so a name resolving there - or a redirect
  to it - could reach a network that still routes site-local addresses.

- **Webhooks to deprecated IPv6 site-local addresses are refused.** The
  plugin's webhook guard had the same site-local gap as the web service.

## [1.25.2] - 2026-09-18

### Added

- The Docker setup wizard moves while it works, in the four places where
  motion tells the operator something the static page could not. Section
  headings sweep into view, the step counter is a single-line gauge redrawn
  in place rather than a new bar per section, the wait for the started stack
  to answer spins and then morphs into a tick or a cross, and the summary is
  drawn as one bordered card per group. The look is borrowed from
  [ratatui](https://ratatui.rs)'s throbber, LineGauge and Block widgets; the
  wizard still depends on nothing but the standard library.

  All of it is gated on the same check that gates colour - no terminal,
  `NO_COLOR`, `FORCE_COLOR`, `TERM=dumb` or a captured run prints exactly the
  plain text it printed before, with no escape and no carriage return. A card
  narrows its label column to fit an eighty column terminal and falls back to
  the plain list in a pane too narrow for one.

### Changed

- `specs.md` states the no-JavaScript promise as clause X-20: a page read
  without a script works with plain forms and links, and a control only a
  script can make work stays hidden until the script reveals it. Clause C-8
  no longer asks for a `RELEASE.md` entry when a setting is added - the
  release workflow writes that file (ADR 0048).

### Security

- **The Docker setup wizard no longer writes credentials through a symbolic
  link.** A link left where `.env` belongs - even a dangling one, which did
  not count as an existing file and so raised no overwrite question - made
  the wizard create the link's target and write every generated secret into
  it. The wizard now refuses to write when the compose file or `.env` is a
  link, whatever `--force` says, and opens every owner-only file (`.env`,
  the nginx admin secret header, credential backups) with `O_NOFOLLOW`.
  Affected anyone who ran `setup-wizard.py` from 1.9.0 to 1.25.1 in a
  directory somebody else could write to.

### Fixed

- A report page read without JavaScript no longer shows controls that only
  a script can make work: the configuration-fragment picker and the copy
  buttons were rendered `hidden`, but their `display` rules outranked the
  attribute. New browser tests (`tests/test_webapp_browser_enhancements.py`)
  now drive the remembered form settings, the fragment picker, the share
  buttons, the rescan countdown and the expiry warning.
- The below-the-fold reveal and the site's own 404 page now have browser
  tests too (`tests/test_webapp_browser_ux.py`): blocks arrive as a reader
  scrolls, a jump to the end sweeps up every block it carried past, a page
  read without JavaScript hides nothing, and a mistyped address gets a 404
  page that runs clean under the CSP with a way home.
- The waiver search on the landing page no longer makes iOS Safari zoom the
  page when it is tapped: on a phone it is now set at 16 pixels, the size
  below which Safari zooms into a focused field. New phone tests
  (`tests/test_webapp_browser_mobile.py`) drive the menu, a scan, target
  sizes and field sizes by touch on a 390-pixel screen.
- The operator's area and the API documentation pages now have browser
  tests (`tests/test_webapp_browser_operator.py`): the admin pages run clean
  under their CSP, `admin.js` fills every tile from `/admin/state`, a
  request without the outpost's headers gets the ordinary 404, and Swagger
  UI and ReDoc render from the vendored bundles with nothing fetched from
  outside.
- The security headers are now tested on every kind of response a stranger
  can reach (`tests/test_webapp_security_headers.py`), not only the landing
  page: errors, the JSON API, every export, the badge, static files,
  redirects and the operator's area. Nothing tied to a scan's uuid may be
  stored by a cache, and the documentation pages' relaxed policy applies to
  exactly `/docs` and `/redoc`, never a neighbouring address.
- `opencloud_local_scan.scan()` raises `ScanError` for an address it cannot
  parse - an unclosed IPv6 bracket or a port outside 0-65535 - instead of
  letting urllib's `ValueError` escape. The plugin already reported these as
  UNKNOWN; a direct caller of the library now gets the exception it is
  promised. New robustness tests (`tests/test_scanner_robustness.py`) cover
  malformed, empty, binary and failing status answers, an oversized body,
  capabilities of the wrong shape, a target that never answers and a
  redirect loop.
- The Docker setup wizard checks the answers it reads back from its
  answers file the way it checks a typed answer: a value outside a
  question's choices, one its validation refuses, or one carrying a control
  character is dropped. A newline in an edited file could otherwise rewrite
  `docker-compose.yml` around it. A `.env` that is not UTF-8 now stops the
  run with a sentence instead of a traceback, and without regenerating the
  credentials a running deployment depends on. New tests
  (`tests/test_docker_wizard_hardening.py`) cover links, edited and
  unreadable files, input that ends mid-walk, refused answers and masked
  credentials.

## [1.25.1] - 2026-09-18

### Fixed

- **A release that stopped after its tag is finished by the next run.** The
  release workflow skipped any version whose tag existed, so when v1.25.0 was
  tagged and GitHub then answered an asset upload with HTTP 500, it reached
  PyPI and Docker Hub but never got a GitHub release, and every re-run stayed
  green without doing anything. The workflow now treats a published GitHub
  release as the end of a version: a tagged version without one is rebuilt
  from its tag and released, the release stays a draft until every asset has
  been uploaded (each upload is retried), and the workflow can be started by
  hand. See ADR 0067.
- **A semicolon in a waiver's reason no longer creates a permanent waiver.**
  `temporary_waivers` is a list, and a list in the environment or a
  configuration file is split on `;`, so the reason
  `Firewall change; debugPort:9206 stays open` left a second entry behind,
  which was read as a bare pattern and became a waiver with no deadline and
  no reason. `temporary_waivers` and `--waive-until` now refuse an entry
  without an expiry and a reason instead; a permanent waiver still belongs in
  `--ignore-hardening`.
- **A malformed waiver in the configuration is UNKNOWN, not WARNING.** A
  `temporary_waivers` entry that could not be read ended the plugin in a
  traceback with exit status 1, which a monitoring system reports as WARNING.
  It now answers UNKNOWN with the reason, on every output path - several
  hosts, `--format json` and the other machine formats included, which also
  let a configuration error such as an unreadable secret escape the same way.
  `check-opencloud-scanner` reports it as a usage error.
- **`check-opencloud-scanner diff` explains a hand-edited report instead of
  crashing.** A provenance, coverage or waiver block of the wrong shape - a
  string where an object belongs, a count that is not a number - ended the
  comparison in a traceback. It is now read as missing, the same as in a
  report that predates the block.
- **The browser tests declare the web server they start.** `uvicorn` is
  imported by `tests/browser_support.py` but reached the `test` dependency
  group only as a dependency of `mcp`; it is now listed there itself.

## [1.25.0] - 2026-09-17

### Added

- **The comparison journeys are covered in a real browser.** The Playwright
  suite now downloads a scan report and uploads it as the baseline for a later
  scan, follows the same-tab comparison offer through to its result, and
  verifies that the capability-bearing scan history does not cross into
  another tab.
- **Translation quality checks.** `scripts/check_translations.py` compares the
  four frontend catalogues and the translated guides against their English
  source and separates what a machine can decide from what it cannot.
  Structural differences - a missing or unknown key, changed `{placeholders}`,
  a string `str.format` would refuse, changed or disallowed inline markup, a
  translated `href`, a relative guide link that resolves to no file - are
  errors and fail CI. Prose heuristics - the form of address a language uses,
  a string left in English, a dropped product name, a glossary term rendered
  two ways - are warnings that name a key for a reviewer, and `--strict` fails
  on those too. Decisions about a warning are recorded in the script's
  `ACCEPTED` table rather than by removing the check.
- **[`TRANSLATING.md`](TRANSLATING.md), the style guide behind those checks.**
  It records the register each language uses - German informal "du", French
  polite "vous", Spanish polite "usted" - the agreed terminology, what happens
  to example hostnames and placeholders, and the review workflow.

- **A scan now records what it did not measure.** The result document gains an
  additive `coverage` block: every check the scan considered, in one of four
  states - `passed`, `failed`, `not_checked` or `inconclusive` - and, whenever
  there is no measurement, a machine-readable reason from a closed set
  (`not_applicable`, `probe_disabled`, `prerequisite_missing`, `timeout`,
  `unreadable`, `no_route`) with a sentence of detail. A passed check and a
  check that never ran no longer look identical. The reason is what separates
  a property of the deployment - no certificate to inspect on a plain-HTTP
  instance - from a probe somebody turned off. The total is what that scan
  considered rather than a fixed denominator, because the checks are dynamic.
  Coverage explains a grade and never changes one: nothing in the block reaches
  the rating, the severities, the alert line, the exit code or the webhook
  payload, and a waived failure stays a failed measurement with its acceptance
  recorded separately. A report written before this existed has no block, which
  every reader treats as "does not say" rather than "nothing was missed". The
  result page shows the gaps beside the grade in all four languages. See
  [ADR 0064](adr/0064-a-scan-records-what-it-did-not-measure.md).

- **A waiver can now carry a reason and a deadline.** `--waive-until
  'debugPort:9205|2026-12-31T00:00:00Z|Firewall change, OPS-412'` accepts a
  failing check until a stated moment, after which it alerts again with no
  configuration change - the fix for a waiver added "for two weeks" that is
  still suppressing an alert a year later. The expiry must carry a timezone and
  the reason may not be empty; a record missing either is refused rather than
  quietly becoming permanent, because failing open is how a typo outlives
  everybody who knew about it. The boundary is `now >= expires_at`, decided
  once per scan against one UTC clock. A bare pattern in `--ignore-hardening`
  is still a permanent waiver and is unchanged. Any active record suppresses,
  and the result document's new `waivers` block lists every record that applies
  to a check - active, expired, and the ones that matched nothing - so a
  permanent wildcard cannot silently absorb an expiry underneath it. Waivers
  still only apply to failing checks, still never remove evidence, and end of
  life is still an F. Configurable as `COS_SCANNER_TEMPORARY_WAIVERS` and
  `scanner.temporary_waivers`. See
  [ADR 0065](adr/0065-a-waiver-may-carry-a-reason-and-a-deadline.md).
- **A comparison now explains why a result changed, not only that it did.**
  Every scan records a `provenance` block built from the data it was actually
  given while it ran: the scanner version, the scan time, the release track,
  the waivers in force, how much was measured, and a stable digest of the exact
  advisory database and release schedule it judged against - a digest rather
  than a copy or a file path, and one that is independent of serialisation
  order. `check-opencloud-scanner diff` and the web comparison then share one
  explanation model that groups contributing changes as `instance`,
  `referenceData`, `scanner`, `policy` or `unknown`, so an upgrade, a newly
  recorded advisory, a support window that simply elapsed, a scanner upgrade
  and an expired waiver are told apart instead of all reading as a regression.
  It claims only what the evidence supports: a changed digest establishes that
  the reference data differed and explicitly not that it caused any particular
  grade to move, several changes may contribute without one being elected the
  cause, and a difference nothing accounts for is reported as unexplained
  rather than dropped. An older report that records neither block still
  compares; what cannot be established is reported as a limitation instead of
  guessed. Uploaded reports pass both blocks through the same bounded
  allow-list (ADR 0057). No new scan history is stored. See
  [ADR 0066](adr/0066-a-result-records-the-conditions-it-was-produced-under.md).
- **A scan can be downloaded as one standalone HTML report.** A result link
  is a capability with a time limit, which is right for a page a stranger can
  reach and wrong for the evidence somebody needs at the end of the quarter.
  `GET /api/scans/{uuid}/export/html` is the same report without the service
  under it: the styling travels inside the document, and there is no script, no
  image, no font service and no stylesheet to fetch, so opening the file makes
  no network request at all - the documentation links are the only addresses in
  it and are followed only if the reader chooses to. It carries the findings,
  the ignored ones with their waiver reasons, the remediation plan, the
  coverage gaps and the reference data the scan was judged against, marking
  what an older report does not record rather than leaving it blank. It says
  plainly that it is a copy that outlives the link, does not update, and is not
  erased when the scan is. There is nothing to operate in it: no form, no
  rescan control, no polling, no erasure token. Every string in it comes from
  the scanned instance or from an operator's waiver, so all of it is escaped
  and a `javascript:` reference renders as text rather than as a link. The
  download sits beside the existing exports on the result page in all four
  languages; the report itself is English, as every export is.

### Security

- **An uploaded report that carries more findings than a report can is now
  refused rather than read in part.** `webapp/imports.py` capped every block
  of a report to its first 500 entries and read the rest of the file as if
  they had never been written. That is the one kind of hole the page cannot
  name: everything past the cut reads as resolved on the earlier side and as
  introduced on the later one, in a comparison that otherwise looks complete.
  A block longer than the cap is now the same 422 as any other file that is
  not a report this service wrote - the answer the CSV row limit already gave
  a file that was too long. What is still read in part is still counted: an
  entry that is not the shape its block is written in, and a waiver that is
  not an identifier this scanner writes, now reach the count the page shows
  beside the comparison instead of disappearing. The grade is read through the
  same length cap as every other string in the file, so a quarter of a
  megabyte of digits is not handed to `int` on the strength of an interpreter
  default an operator can turn off. See
  [ADR 0057](adr/0057-an-uploaded-report-is-evidence-not-a-scan.md).
- **A network serving a probe block can no longer upload a report either.**
  The block ADR 0051 imposes on a client whose recent scans kept turning out
  not to be OpenCloud was asked about on the submission path only, so the same
  network could still hand `POST /compare` a file to parse - the one parser
  here fed from outside, and work this service does whether or not a scan
  follows. It is now asked before the upload's own bucket, as the submission
  path asks it before the client limit, so a blocked client's refusals do not
  run down an allowance it will want back when the block ends. The answer is
  the 429 with `Retry-After` the block gives everywhere else, in its own
  sentence in all four languages.
- **The report upload now reaches the audit trail.** It is the only structure
  this service parses that it did not write, and it was the one refusal an
  operator with `COS_WEB_AUDIT_LOG` on could not see: a spent upload limit and
  a file the parser would not read are now `rate_limited` with the scope
  `rate_limit_upload` and `submission_rejected` with the reason
  `report_rejected`. The record carries the key of this service's own refusal
  and no part of the file, because an audit trail is as attractive a place for
  a hostile upload to be quoted as an error page is.

### Fixed

- **Two sentences about a refused upload printed their own placeholder.** The
  page that says a file is too large, and the one that says a comparison has
  expired, are catalogue strings with a number in them, and both were rendered
  without it - so a reader was told their file exceeded the "{kilobytes} KB"
  limit. Every sentence on that path is now given the size limit and the
  window a comparison lives for, from the settings that enforce them.

- **101 dead links in the French guides.** A guide under `docs/<language>/`
  sits one directory deeper than its English source, so every path out of
  `docs/` needed `../../` and had `../`. The generated French pages carried
  the same mistake into the public documentation, where links to ADRs and
  repository files pointed at GitHub addresses that did not exist. The
  English guide index also linked to a German index that was never written;
  it now points at the three translated guide directories.

## [1.24.2] - 2026-09-17

### Changed

- **The German interface and guides now address the reader as "du"
  throughout.** The remaining formal strings in the German catalogue and the
  last formal sentences in `docs/de/` are rewritten, and the test that
  tolerated a list of older formal strings now fails on any formal German
  string, in the catalogue and in the German guides alike.
- **Spanish guide sources are now available in the frontend.** Every public
  guide has a matching `docs/es/` source, generated Spanish template and
  search index entry, so a Spanish visitor no longer gets the English guide
  under a notice. The languages with guide sources are listed once, in
  `GUIDE_LANGUAGES`, for the generator, the route and the search index. See
  [ADR 0063](adr/0063-public-guides-have-spanish-sources.md).

### Fixed

- **The browser tests pass in Firefox again.** Playwright's Firefox drops an
  emulated colour scheme once a page sends
  `Cross-Origin-Opener-Policy: same-origin`, so the dark-theme test now gives
  Firefox a browser whose system theme is dark instead; and waiting for a
  finished scan tolerates the moment during the result page's reload when the
  new document has no body yet.
- **The MCP sign-in no longer warns about `validate_token_resource` at
  startup.** The token verifier already checks a token's audience against
  `COS_WEB_MCP_AUTH_AUDIENCE`, so the MCP SDK is now told explicitly not to
  also require the token's resource to equal the resource URL, which would
  have refused valid tokens once SDK 3.0 turns that check on by default.
- **The grade page test matches the reworded English copy again.** It now
  looks for "Explanations for failed checks", the heading the copy polish
  gave that item.

## [1.24.1] - 2026-09-16

### Added

- **The frontend is tested in a real browser.** `tests/test_webapp_browser_ux.py`
  and `tests/test_webapp_browser_e2e.py` drive the web application in WebKit
  (and Firefox in CI, `.github/workflows/browser-tests.yml`) through
  Playwright: every public page runs clean under its Content-Security-Policy,
  fits a phone screen and hides what is marked hidden; navigation, theme,
  language, form validation, waiver search, site search and back-to-top
  behave; and a visitor's journeys work from the form to the report - the
  waiting page's hand-over, severity filters, all four exports, waivers,
  keyboard only, without JavaScript and in German. No browser can reach
  anything but loopback, and Chromium is never used because its builds are
  Google's. New test dependency `playwright` has an approved review in
  `security/dependencies/playwright.yml`; see
  [ADR 0061](adr/0061-the-frontend-is-tested-in-real-browsers-that-cannot-leave-loopback.md).
- **Agents can drive the running app through the Playwright MCP server.**
  `.mcp.json` starts the server bundled with the same `playwright` package,
  configured in `.claude/playwright-mcp.json` for WebKit, an isolated
  headless profile and loopback only - no Node.js installation needed.

### Fixed

- **The scan form validates the address in the browser again.** Browsers
  compile the field's `pattern` with the `v` flag, under which the unescaped
  `-` in `[A-Za-z0-9._~-]` is an error, so WebKit and Chromium silently
  skipped client-side validation and sent malformed addresses to the server.
- **The catalogue and reports no longer scroll sideways on phones.** A
  remediation naming a long environment variable had no break opportunity,
  and the findings list grew to fit it - 319 pixels past a 390-pixel screen on
  `/catalogue`.
- **The findings filter note is hidden until a filter is chosen.** A
  `display: flex` rule outranked the `hidden` attribute, so every report showed
  an empty "showing only" line with a "show all" link.

### Changed

- **A new Python dependency needs an approved review first.** Every package in
  `pyproject.toml` and every `uvx` tool in a workflow needs a record in
  `security/dependencies/` that says why it is needed, which tests exercise
  it, what a security review found, and which maintainer approved it.
  `scripts/check_dependencies.py`, run by a new `dependency-policy` job in the
  supply-chain workflow, fails without one. The 33 dependencies already in use
  are listed in `security/dependencies/grandfathered.txt`, which may only
  shrink. The dependency-review action now fails a pull request that
  introduces a known-vulnerable package instead of only commenting, and the
  supply-chain workflow grants its attestation permissions to the one job that
  attests. See
  [ADR 0060](adr/0060-a-new-dependency-is-justified-tested-and-reviewed-first.md).
- **Routine dependency updates get a seven-day stabilization window.**
  Dependabot still raises security updates immediately, while monthly version
  updates wait long enough for a compromised or broken release to be noticed.
  The composite action also invokes its private scanner environment directly
  instead of adding that directory to the rest of the job's executable path.

- **Comparing two scans of different instances is refused.** The `/compare`
  page, the report upload and the MCP tool `compare_scans` used to compare a
  scan of one host with a scan of another and only show a warning. They now
  answer 422 and compare nothing, matching the default of
  `check-opencloud-scanner diff`. A report that names no instance is refused
  the same way. `sameTarget` stays in the answer and is always `true`. See
  [ADR 0059](adr/0059-a-comparison-refuses-two-different-instances.md), which
  supersedes this part of ADR 0029.
### Documentation

- **New German text addresses the reader as "du".** New and reworded strings
  in the German web interface and guides use the informal form instead of
  "Sie". Existing formal strings are listed in `tests/test_webapp_i18n.py`,
  which fails on any other formal string; the list only shrinks as strings
  are converted. The "Die beiden Scans betreffen unterschiedliche Instanzen"
  message already uses the new form.
- **The release skills build a release skeleton and never write a changelog
  entry.** `/patch-release`, `/minor-release` and `/major-release` now make
  exactly the version bump in `pyproject.toml`, a new `uv.lock` and the
  refreshed generated files (release schedule, advisory database, frontend
  documentation, search indexes), and leave `CHANGELOG.md` and `RELEASE.md`
  alone: the release notes are the `[Unreleased]` entries the merged pull
  requests wrote. A new OpenCloud release or advisory found by the refresh is
  reported to the user instead of written down. The version guard now runs
  after the commit, because it reads the committed version, with
  `--labels skip-changelog` so that only its version check applies.
- **`/open-release-pr` checks the changelog before it opens anything.** It
  stops when the `[Unreleased]` section is empty, when the release branch
  changes `RELEASE.md`, or when it changes a released section of
  `CHANGELOG.md`. Entries the release branch adds under `[Unreleased]` are
  allowed and become part of the pull request body, which uses the
  `[Unreleased]` entries verbatim; the skill never edits either file.
- **Claude Code hooks enforce the project's hard rules.** `.claude/settings.json`
  refuses publishing or syncing advisories, merging pull requests, creating
  tags and releases, force-pushing, pushing to `main`, `git reset --hard`,
  aborting a merge and `ruff format`; refuses hand edits to `RELEASE.md`, the
  generated documentation, search indexes, bundled data, the README
  release-schedule block and the embedded wizard blueprints; asks before a
  version change or a literal `__version__`; and refuses inline styles and
  scripts in templates. When the session ends, it runs the fast generator
  `--check` guards for changed sources.
- **A privacy guard keeps real instances, scan output and personal data out
  of commits.** `.claude/hooks/privacy_guard.py` checks staged changes and
  commit messages before `git commit`, the commits a `git push` would send,
  pull request bodies, and, when the session ends, everything staged or not
  yet pushed. It refuses hostnames that look like an instance or scan target,
  public IP addresses, personal e-mail addresses, credentials and scanner or
  plugin output in any format, and asks about any other new hostname. Values
  already on `main` and public references in
  `.claude/hooks/privacy_allowlist.txt` pass.
- **The hooks refuse when they cannot run, and have tests.** A guard that is
  missing, crashes or cannot read its input now refuses the command or edit
  instead of letting it through; the generator checks at the end of a
  session run in the project's environment and report a missing dependency
  as skipped rather than as a stale file; the privacy guard only starts for
  `git` and `gh` commands. `tests/test_claude_hooks.py` covers all of it.
- **The hooks close the gaps a review found.** The Bash guard now applies the
  Edit guard's rules to shell writes (redirects, `tee`, `sed -i`, `cp`, `mv`,
  `rm`), sees commands inside `$(...)`, backticks, `bash -c`, `eval`, braces,
  background jobs and `xargs`, ignores quoted text, heredoc bodies and
  comments, lets `ruff format --check`/`--diff` and redirected `git tag`
  listings through, and reads `git push -o` values correctly. Pushes using
  `--repo` are checked against both the main-branch guard and the privacy
  guard. The privacy
  guard matches values already on `main` as whole tokens only, reads diffs
  without mistaking an added `++ ` line for a file header, checks merge
  commits, checks the branch a push actually sends, reads `git commit -F`
  message files and `gh` `-F`/`--body-file=` bodies (issues too), only widens
  a commit check to the working tree for a real `git add`, `-a`/`-i`/`-o` or
  pathspec, and asks when it cannot read the commits of a push. The session-end
  generator checks treat only a traceback ending in an import error as a
  missing dependency.
- **`/preflight` runs in a read-only `preflight-runner` agent**, so its output
  stays out of the conversation and nothing is changed while it checks.
- **`/patch-release`, `/minor-release` and `/major-release` are now one
  `/release <patch|minor|major>` skill.**
- **German guide pages no longer repeat their title inside the article.** The
  frontend generator removes the source and translated Markdown title before
  rendering the page header; German sources keep their headings and key
  external references in German, and the Spanish agent-client guidance uses
  the formal form of address consistently.
- **French guide sources are now available in the frontend.** Every public
  guide has a matching `docs/fr/` source, generated French template and search
  index entry. Spanish guide pages continue to use the explicit English
  fallback until their own source set is reviewed. See
  [ADR 0062](adr/0062-public-guides-have-french-sources.md).

## [1.24.0] - 2026-09-16

### Documentation

- Rewrite frontend explanations and operator documentation for clearer,
  consistent wording in English, German, French and Spanish. Clarify scan
  coverage, temporary storage, alert timing and configuration instructions.
- Add German versions of all public guides under `docs/de/`, generated German
  frontend pages and German guide search content. Preserve section links across
  languages; French and Spanish continue to use English guide bodies.

### Added

- **The comparison page takes the earlier scan as an uploaded report.**
  `/compare` needed both scans to still exist, and the baseline worth
  comparing against is usually older than the hour a result lives. It now also
  accepts the JSON or CSV file from a result page's downloads: upload the
  report you kept, name a scan that has not expired, and the page answers the
  same question with the same arithmetic - `workflows.compare_documents`, which
  is the plugin's own `--baseline` comparison, so a reader, an agent and an
  operator's alerting still cannot disagree about one pair. The file is the
  only structure this service parses that it did not write, so it crosses one
  boundary: `webapp/imports.py` does not hand back what it was given but a
  result document rebuilt key by key from an allow-list, capped at 256 KB,
  strict UTF-8, with identifiers dropped and counted unless they are spelled
  the way this scanner spells its own. The file is read once in memory and
  written nowhere - not its contents, not its name, which nothing reads. What
  survives is the comparison, under a fresh uuid4 for at most five minutes so
  a reload and a shared link keep working; `COS_WEB_COMPARISON_TTL` can
  shorten that window and cannot widen it. Unknown, malformed and expired
  tokens are one 404, and nothing lists them, and `DELETE /api/purge` erases a
  cached comparison along with the scans of the instance it names rather than
  leaving it to its own clock. A browser feature only: no MCP
  tool and not in the OpenAPI schema, because an agent already has
  `compare_scans` and two uuids. See
  [ADR 0057](adr/0057-an-uploaded-report-is-evidence-not-a-scan.md).

- **`--format otlp` hands the scan's metrics to an OpenTelemetry collector.**
  The eight metrics the Prometheus exporter publishes, rendered as one
  OTLP/JSON `ExportMetricsServiceRequest` covering every scanned host - the
  body a collector accepts at `/v1/metrics`. Pipe it at `curl` from the timer
  that already runs the check: the plugin prints the document and never dials
  the collector itself, so where the metrics go and which credential reaches
  them stay out of a scan. Like `--format prometheus` it exits `0` whatever
  the instance scored and reports an unreachable one as
  `opencloud_security_scrape_success 0`, because a metrics pipeline has no
  other way to tell that apart from a scan that stopped running. The names,
  labels and values are the exporter's: both formats now render one reading of
  the scan rather than each deciding for itself what a waived measure counts
  as - see
  [ADR 0054](adr/0054-metrics-are-collected-once-and-rendered-twice.md).

- **A Helm chart installs the Kubernetes deployment this project documents.**
  [`contrib/helm/check-opencloud-security`](contrib/helm/check-opencloud-security)
  renders the scheduled scan as a `CronJob` and, when asked for, the shared
  scan service with a `NetworkPolicy` naming the instances it may reach.
  Four values have no default and an install that omits one is refused rather
  than rendered: the image tag, because the release schedule ships inside the
  image and `latest` would move the verdict under a running alert; the hosts,
  because a Job with no host scans nothing daily while looking like
  monitoring; the scan service's token, because an untokened one scans any
  host its callers name; and that policy's allowlist, because a policy with no
  egress rule is a different policy rather than an unfinished one. The chart
  writes no `Secret` and carries no version of its own - every credential is
  read from one you created and named. `tests/test_helm_chart.py` holds every
  flag it can emit against the plugin's own argument parser.

- **A finished scan can be shown as a grade badge.**
  `GET /api/scans/{uuid}/badge.svg` renders the letter as a small SVG this
  service draws itself - no badge service, no external font, no script,
  because an image fetched from somebody else's server would hand them the
  result URL in a referrer on every view, and that URL's uuid is the whole of
  the authorisation. It carries nothing the scanned instance chose: no
  hostname, no product, no version. It answers 404 for an unknown or expired
  uuid and 409 while the scan is running, like every other reading of one, and
  keeps the service-wide `no-store`. A badge therefore lives exactly as long
  as its scan - an hour by default - which makes it right for a ticket or a
  chat message and wrong for a README; there is deliberately no badge for a
  hostname, because that would be a permanent handle on somebody's instance.
  See [ADR 0055](adr/0055-a-badge-is-a-rendering-of-one-scan-not-a-handle-on-an-instance.md).

- **The reference data can be subscribed to.** `/advisories.atom` and
  `/release-schedule.atom` publish the advisory database and the release
  lifecycle as Atom feeds, built from the same functions `/catalogue` and the
  scan pipeline use. Both documents refresh themselves daily and may only gain
  knowledge, and until now noticing a new advisory meant reopening a page and
  remembering what had been there. The feeds name no instance, carry no uuid
  and take no parameter, which is what lets them be publicly cacheable under
  [ADR 0031](adr/0031-a-response-is-uncacheable-until-a-route-opts-in.md);
  advisory titles and descriptions come from a feed this project does not
  control and are carried as escaped text rather than markup. See
  [ADR 0056](adr/0056-the-reference-data-is-subscribable.md).

### Changed

- **The CSV export records two facts the findings table cannot carry.** A
  `Update available` row and an `HTTPS enforced` row now sit with the header
  block, because both are single measurements that live outside the per-finding
  table and a report read back without them cannot tell "no" from "never
  recorded". A file downloaded before this is still readable: the comparison
  leaves those two measurements out of *both* sides rather than guessing at
  them, and says on the page that it did. Anything parsing that CSV by row
  position rather than by label will need adjusting.

- **The bundled release schedule and advisory database were re-checked against
  their published sources.** Neither moved: the schedule still names OpenCloud
  7.2.4 as production and 8.0.0 as rolling, and the advisory database still
  holds the same two records. The generated frontend documentation and the
  public and operator search indexes were rebuilt so that the version they
  carry is this release's.

## [1.23.3] - 2026-09-16

### Added

- **An operator can search the operator area.** While the sign-in lasts,
  `/search` also answers from the area's own pages - the overview, the
  configuration and rules tabs and the two operator documents - and marks
  those results as the operator area's. The index behind them is built into
  the package rather than `frontend/static`, is served only by an authorised
  route under `/admin`, and is sent `no-store` so that signing out ends
  access to it immediately. Everybody else gets the public index alone and no
  indication that another one exists.

### Fixed

- **The operator documents no longer carry broken images.** The repository's
  Markdown points at files beside it, which resolve to nothing once a page is
  served from `/admin/docs/`. The architecture diagram is now served from this
  origin, as `img-src 'self'` requires; the two interface screenshots are
  megabytes each and show the page the reader is already on, so they become
  links to the repository rather than weight in the bundle.
- **The two generated operator documents now look like the rest of the area.**
  `Architecture` and `Operations` never loaded `admin.css`, so the tab strip
  above them rendered as bare links and neither page carried the signed-in
  band or the ruled heading the other tabs have.

### Changed

- **The operator index is chosen from a table rather than named by a request.**
  The file each language's operator search index lives in is now a fixed entry
  in one table in `webapp/search.py`, which both the build script and the
  request path read. The language a request asks for could already only be one
  of the four this frontend has - a cookie or `Accept-Language` is reduced to a
  supported code or to nothing before anything else sees it - so no traversal
  was reachable, but the name was still assembled from that value, which is a
  shape static analysis rightly objects to and one refactor away from being
  true. A cookie the visitor wrote by hand now selects an entry or misses the
  table and gets English.

- **The agent guide is now part of the API page.** `/ai` was a tab of its own
  next to `/api`, which asked a reader wiring up software to guess whether a
  curl call and an MCP endpoint were documented in the same place. Discovery,
  WebMCP, client configuration and the rules for agents are now sections of
  `/api`, which keeps its name. `/ai` redirects there permanently, and the
  discovery document's `documentation` key follows it.

- **Reference data re-read and the generated documentation rebuilt.** The
  OpenCloud release schedule is unchanged (production 7.2.4, rolling 8.0.0)
  and the advisory database brought no new entries, so this release carries
  the same ratings as the last one. The bundled documentation pages and the
  four search indexes are regenerated against the new version.

## [1.23.2] - 2026-09-15

### Fixed

- **Parallel scanner tests no longer overflow the fake server's backlog.**
  The fixture accepts a full burst of probes, so dropped local connections
  do not turn a reachable test finding into an intermittent pass.

### Security

- **Anonymous scans no longer inherit local credentials.** Scanner sessions, including
  parallel sessions, disable ambient Requests configuration. Explicit demo
  authentication remains intact. Webhook sessions also disable ambient credentials.
- **Pinned scans cannot be redirected through ambient proxies.** Scans ignore
  environment proxies. A pinned scan with an explicit resolving proxy is rejected.
  Unpinned CLI scans still support the explicitly configured proxy.
- **Workers cannot resurrect erased or expired scan results.** Worker transitions
  require the original metadata and status keys to exist, and check and write atomically
  in Redis. MemoryRedis follows the same contract. Deletion between reading metadata and
  committing completion cannot revive the UUID.
- **Browser-origin fallback checks validate the complete origin.** Opaque and
  malformed origins are rejected; comparison includes scheme, normalized hostname and
  effective port. The configured public origin is authoritative, not the request's
  internal Host header.
- **Webhook delivery dials only the addresses that passed validation.** Delivery pins
  the validated address set while preserving Host, TLS SNI and certificate hostname
  verification. Restricted delivery refuses an explicit resolving proxy and ignores
  ambient proxies. Redirects remain disabled and response bodies are not downloaded.
- **Redirect responses obey the scanner response-size limit.** Scanner sessions leave
  all redirect handling to the capped manual redirect loop, including the normally
  implicit Response.next preparation. Explicit request Authorization headers are not
  propagated to redirect targets.
- **A web scan timeout now stops its probes.** Each web scan runs in a spawned child
  process. Timeout and cancellation kill and reap it, including its probe threads,
  before the slot is released. Unexpected child failures return a generic
  classification; worker logs no longer include exception traces that may contain scan
  data.
- **Authentication-key fetches stay bounded during outages.** Only one key lookup may
  be in progress per verifier; concurrent attempts fail closed without queuing another
  blocking fetch. Failed fetches impose a 60-second retry floor, including initial
  fetches. Valid cached-key verification and key rotation retain their existing
  behavior.
- **Web request bodies are bounded before parsing.** An ASGI guard bounds mutation
  request bodies to 1 MiB and a 30-second total receive deadline before downstream
  parsing. Chunked bodies are counted as well. Oversized bodies return 413 and
  incomplete bodies return 408.
- **Unrelated browser pages cannot trigger loopback-service scans.** Scan-triggering
  GET and POST routes reject cross-site/same-site Fetch Metadata and foreign or opaque
  fallback Origins. Ordinary non-browser monitoring clients remain supported. Malformed
  Host values are refused instead of raising.
- **Existing wizard secret files are private before new secrets are written.** The
  wizard applies fchmod(0600) to the open descriptor before writing any secret data,
  including existing .env files, nginx admin-header files and secret backups.

### Documentation

- **Repository-wide security audit.** `security/audit-2026-09-16.md` records
  the review scope, eleven fixes, validation results and remaining deployment
  checks. Advisory records are drafts; nothing was published by the audit.
- **German, French and Spanish frontend wording and terminology have been
  polished.** The translated catalogues now use more natural phrasing and
  established technical terms across the public and operator-facing pages,
  without changing any scan behaviour or API contract.
- **Keeping the release schedule and advisories current.**
  `docs/reference-data.md` documents `check-opencloud-scanner refresh-data`:
  - the reviewed, Sigstore-attested files it fetches, and the three
    verification outcomes;
  - the structural checks that apply either way;
  - pointing `scanner.release_schedule` and `scanner.vulnerability_db` at the
    result;
  - the daily systemd timer;
  - mirrors for hosts without internet access.

  It also warns that a schedule file the check cannot read turns the
  end-of-life check off rather than falling back to the bundled schedule.
- **A reference for `check-opencloud-scanner`.** `docs/scanner-cli.md` covers
  the global options and configuration search, `scan`, `diff`, `explain`,
  `refresh-data`, `serve` and `configure`, with options and exit codes for
  each. It explains how they differ from the plugin's Nagios codes.
- **Signed exports are documented in `docs/webapp.md`.** A new section
  explains what `X-COS-Signature` covers and that it is a shared-secret HMAC
  rather than a public signature. It shows how to keep the header with the
  file, and how to verify it with `scripts/verify_export.py` or `openssl`.
- **The README no longer says the bundled advisory database is empty.** It
  names the advisory it carries and points to the refresh guide.
- Both new pages are listed in `docs/README.md` and published under
  `/documentation`. The frontend documentation and search indexes are rebuilt.

## [1.23.1] - 2026-09-15

### Changed

- **The bundled release schedule knows OpenCloud 8.0.** Regenerated from the
  published lifecycle page: the 8.0 line is the current rolling release
  (8.0.0), so 7.5 is now behind the rolling track. Production (7.2.4) and LTS
  (4.0.8) are unchanged, and the README release table follows. The advisory
  database was re-read from OSV and has nothing new. The frontend
  documentation and the search indexes are rebuilt to match.

### Documentation

- **Claude Code skills for the repetitive maintenance tasks.** `.claude/skills/`
  now carries step-by-step skills for patch, minor and major releases, opening
  the release pull request, refreshing the bundled data, adding a setting, a
  hardening check or a translated string, writing a security advisory record or
  an ADR, a local run of the pull request checks, fixing OpenCloud
  documentation links, and resolving conflicts in generated files. They follow
  `AGENTS.md`: none of them publishes an advisory, merges to `main` or bumps a
  version unless the maintainer invokes a release skill.
- **A skill to run and drive the project locally.**
  `.claude/skills/run-check-opencloud-security/` runs the scanner library,
  the plugin or the web app against the fake OpenCloud from the tests, with no
  Redis, Docker or real instance. The web app gets an in-process worker, so a
  submitted scan completes. Headless Chromium submits the form and takes
  screenshots.
- **`.claude/` stays out of images and source archives.** It is listed in
  `.dockerignore` and marked `export-ignore` in `.gitattributes`, like
  `.github/`.

## [1.23.0] - 2026-09-14

### Added

- **The operator area has a Rules tab.** `/admin/rules` documents how a grade
  is decided - the scale, the scanner's severity ceilings, the end-of-life and
  track overrides, whether extra checks count, the waivers a visitor may
  choose, and the advisory database and release schedule rated against - and
  every rule enforced against a request: the per-client, daily and per-target
  limits, the probe block with its strikes, network scope and escalation, the
  SSRF guard's refused ranges, names and wildcard DNS services, approval mode,
  the flags every scan runs with, and the credential and refresh limits. Each
  rule is marked enforced or off and names its `COS_WEB_*` variables. Nothing
  is restated: every number and list is read from the running settings and
  the constants of the code that enforces it, and the page names no target,
  uuid or client.
- **The operator area has a Configuration tab.** `/admin/configuration`
  lists every `COS_WEB_*` variable the web service reads, grouped, with the
  value in effect after parsing, whether the environment set it or the default
  applies, and the documented default and description from `docs/webapp.md`.
  Credentials - tokens, signing keys, salts, the admin proxy secret and the
  password in `COS_WEB_REDIS_URL` - are shown only as set or not set; for
  `COS_WEB_ENCRYPTION_KEY_<n>` only the versions present are named. `COS_WEB_*`
  names the service does not recognise are listed without their values, so a
  misspelt variable is noticed instead of silently leaving the default in
  force. `scripts/build_frontend_documentation.py` now also generates
  `webapp/environment_reference.py` from the documentation table, and
  `COS_WEB_IPV6_ENABLED` and `COS_WEB_WEBHOOK_SECRET` are documented there for
  the first time.
- **The web service blocks a client that keeps scanning hosts that are not
  OpenCloud.** Five scans from one client address that find no OpenCloud -
  nothing answering on `status.php`, something that is not JSON, another
  product, or no answer in time - within five minutes block that address for
  an hour; the same host scanned again counts again. A blocked submission
  answers 429 with a `Retry-After` of the rest of the block, the usual pointer
  to running the scanner locally, and `rate_limit_probe` in the audit trail.
  Only the worker learns the outcome, so a submission hands it the client's
  rate-limit fingerprint, never the address, under `scan:{uuid}:prober`, and
  the worker deletes it as soon as it starts the scan. Tuned with
  `COS_WEB_PROBE_LIMIT`, `COS_WEB_PROBE_WINDOW` and `COS_WEB_PROBE_BLOCK`,
  which the web service and the worker both read; `COS_WEB_PROBE_LIMIT=0`
  turns it off. MCP and the workflows now wait out a `Retry-After` of at most
  five minutes by themselves and hand a longer one back to the caller instead
  of sleeping through it. See ADR 0051.
- **The probe block counts networks, grows when it is earned again, and counts
  refused targets.** An IPv6 client is one /64 for every limit
  (`COS_WEB_CLIENT_IPV6_PREFIX`), so rotating through a subscriber's own
  addresses no longer resets anything, and the probe block covers an IPv4 /24
  (`COS_WEB_PROBE_IPV4_PREFIX`) so the next address along cannot step around
  it; the per-minute limit still counts single IPv4 addresses. A block earned
  again within `COS_WEB_PROBE_REPEAT_WINDOW` of the last one lasts six times
  longer - an hour, six hours, a day - up to `COS_WEB_PROBE_BLOCK_MAX`. A
  submission the guard refuses for what it points at - a private or internal
  address, an exclusion, a misleading DNS name, an unapproved instance - is a
  strike too; a typo or an unresolvable name is not. See ADR 0052.
- **A daily cap per client.** `COS_WEB_DAILY_SCAN_LIMIT` (default 50) refuses
  the patient version of a burst with 429, `rate_limit_daily` in the audit
  trail and the usual self-host pointer.
- **Wildcard and rebinding DNS names are refused, and a name must resolve the
  same way twice.** Names under `nip.io`, `sslip.io`, `xip.io`, `traefik.me`,
  `localtest.me`, `lvh.me`, `vcap.me`, `lacolhost.com`, `localhost.direct`,
  `local.gd`, `rbndr.us` and `1u.ms` are refused by name wherever the SSRF
  guard applies. A submitted name is looked up twice and refused when the
  answers share no address, with every address from both held to the guard
  (`COS_WEB_DNS_CONSISTENCY_CHECK`).
- **Approval mode.** `COS_WEB_REQUIRE_APPROVAL=true` scans only instances in
  `COS_WEB_APPROVED_TARGETS` or, with `COS_WEB_APPROVAL_DNS`, instances whose
  zone publishes `_check-opencloud-security.<host> TXT
  "check-opencloud-security=<this service's hostname>"`; anything else is a
  403 and `target_not_approved` in the audit trail. A mode that could approve
  nothing, or a list entry that does not parse, refuses startup.
- **The operator's area has an Abuse guard tile**: networks blocked now, and
  blocks, strikes and daily caps reached over seven days, as counts only.
- **The Docker setup wizard asks for every abuse limit** in a new *Abuse
  protection* section and writes them to both containers.
- **`ScannerSettings.stop_when_not_opencloud` and `NotOpenCloud`.** A
  `status.php` answer that is not OpenCloud now raises `NotOpenCloud`, a
  subclass of `ScanError`. With the setting on, the scan stops there rather
  than asking again without certificate verification and over plain HTTP;
  the web service turns it on, and the plugin's default is unchanged.

### Security

- **The scan service refuses a request not addressed to loopback when it has
  no token.** `check-opencloud-scanner serve` on its default `127.0.0.1` bind
  with no token answered any `Host`, so a web page open in a browser on the
  same machine could point a hostname of its own at `127.0.0.1` (DNS
  rebinding), read every answer as same-origin, and use `/api/scan` - which
  has no target guard - to scan and report back what the operator's network
  holds. Without a token a request must now name `localhost`, a `127.0.0.0/8`
  address or `::1`, or it is answered 403; a service with a token is
  unaffected, since a page cannot know it.
- **`POST /api/scans/batch` refuses a cross-site submission like the single
  one does.** It was the one public POST without the `Sec-Fetch-Site`/`Origin`
  check, and it parses its body as JSON whatever the `Content-Type` says, so a
  foreign page's `text/plain` form - which needs no preflight - could queue a
  batch of scans from a borrowed browser, spending that visitor's allowance
  and, with the probe guard, earning their address a block.
- **The operator area accepts a write only from its own origin.** Its three
  POSTs took the public pages' check, which lets `same-site` through, and a
  sign-in cookie is sent on a same-site request - so a page on any sibling
  subdomain, the identity provider's or an OpenCloud instance's among them,
  could add or withdraw exclusions and press the refreshes with the
  operator's session. `/admin` now requires `Sec-Fetch-Site: same-origin`
  (or `none`), or an `Origin` of this service where that header is absent.
- **A non-ASCII `X-COS-Admin-Proxy` header is refused with 404 instead of
  crashing with 500.** The secret was compared as `str`, which raises on
  characters outside ASCII; the 500 differed from the 404 an area that is off
  answers, and told a prober from outside that `/admin` was switched on. It is
  now compared as bytes, as the erasure token already was.

## [1.22.7] - 2026-09-14

### Fixed

- **The two refresh buttons in the operator area work again.** Each of those
  forms carries a hidden `action` field naming the source to refresh, and a
  control of that name is reachable as `form.action` - so the script read the
  input element instead of the path and posted to
  `/[object HTMLInputElement]`, which answered 404 and left the page saying
  nothing. It now reads the form's `action` attribute. The dry-run probe
  beside them, which has no such field, was unaffected.
- **The light/dark switch keeps switching in a browser that refuses to
  remember it.** A press wrote the scheme to the document and to
  localStorage, and where the write was refused - a private window, blocked
  site data - the next press asked storage what was on screen, got nothing,
  fell back to the operating system's scheme and so computed the scheme the
  page had just left. The button changed nothing from the second press on.
  It now reads the scheme the document is actually in first, which a press
  writes whether or not anything can be stored.

### Changed

- **The operator area's forms no longer name a field `action`.** A refresh
  now posts `source=schedule|advisories` to `/admin/refresh`, and an exclusion
  posts `operation=add|remove` to `/admin/exclusions`; the old `action` field
  is refused with 422. Only a script posting to these routes by hand needs
  the new names - the JSON answers still carry `action`. A test now keeps
  every template from naming a control after a form property it would shadow
  (`action`, `method`, `submit`, ...), and the button test posts each form's
  own fields to its own path instead of reading the script's text.
- **Every pull request to `main` rebuilds the search index.** A new
  `search-index.yml` workflow runs `scripts/build_search_index.py` on every
  pull request, whether or not a template changed, and commits the result to
  the branch when it differs - so a page edited in a pull request no longer
  merges with search describing it as it read one release ago. A fork's pull
  request gets a read-only token, so there a stale index is reported as a
  warning instead. The release workflow still rebuilds it before building
  artefacts. ADR 0050 records the change and supersedes the release-only
  refresh in ADR 0019.
- **The operator area's search index card says how to fix a stale index.**
  It lists every reason the index is out of date rather than only the first,
  and, unless the index is current, shows the command that regenerates it
  and the rebuild that follows. There is still no button: the index stays
  generated by CI, never by the running service (ADR 0035).
- **Code scanning no longer mistakes a file path in the Docker setup wizard
  for a credential.** The path of the nginx admin-proxy header file was held
  in a variable called `secret`, and because the wizard prints that path in
  its list of written files, CodeQL reported clear-text logging of sensitive
  data. Only the name changed: the wizard never printed the value, and the
  file is still written owner-readable only.

## [1.22.6] - 2026-09-13

### Security

- **The Docker setup wizard no longer shows a stored credential when it is
  run again.** A re-run reads `.env` back so that its credentials survive, and
  every question then offered the value in brackets as the default - the SMTP
  password, the erasure token, the signing keys, the audit salt, the
  encryption key, the `/admin` proxy secret and the releases token, in plain
  text on the screen and in the scrollback. Those prompts now say `[set,
  hidden - Enter keeps it]` instead, Enter still keeps the stored value, and
  what is typed at them is read without an echo when the wizard runs in a
  terminal. Settings kept in `.env` that are not credentials - the issuer, the
  audience, the key set and resource URLs - are still shown, so they can be
  checked.
- **The scan service no longer lets a submitted host write its own log
  lines.** `opencloud-local-scan serve` logged a failed scan with the host
  exactly as the request body held it, so a newline in `url=` started a new
  line in the service log that looked like any other. The host and the error
  are now logged in quoted, escaped form. Found by CodeQL.

### Added

- **The Docker setup wizard is downloaded from a release, checksummed, and
  knows its version.** Every release now attaches `setup-wizard.py` with a
  `setup-wizard.py.sha256` beside it, built and attested by the release
  workflow, and the guides download that copy instead of whatever `main` held.
  `setup-wizard.py --version` names the release it came from: stamped into the
  download, and read from `pyproject.toml` in a checkout or the web bundle.
  See ADR 0049. The release asset first exists with the next release.
- **The Docker setup wizard asks how much to ask.** `quick`, the default on a
  first run, asks only the image, the port and public address, `/mcp` and its
  sign-in, `/admin`, the identity provider and its mail, and the reverse proxy;
  `private` asks the same from the private preset; `full` asks everything and
  is the default when editing an existing deployment. `--mode` answers it in
  advance, and a section passed over is now named as skipped so the step
  counter adds up.
- **The Docker setup wizard shows what a re-run would change, and keeps what
  it replaces.** Before asking to overwrite, it prints a diff of the compose
  file and the proxy and logrotate files - never of `.env` - and every replaced
  file is kept as `<name>.<UTC time>.bak`, the `.env` copy owner-readable only.
- **The Docker setup wizard checks the host and can start the stack.** The
  summary points out Docker or the Compose plugin missing, the host port
  already in use, and a certificate the proxy configuration names that does
  not exist. After writing it offers `docker compose config`, then
  `docker compose up -d` and a wait for `/healthz` - each only when asked, and
  `up` only when nothing has to be done as root first.
- **Answers can travel between hosts.** `--print-answers` prints every
  non-credential answer as JSON and writes nothing; `--answers FILE` starts a
  run from such a file, read as untrusted, and refuses one with nothing usable
  in it.

### Changed

- **The Docker setup wizard no longer binds every interface to check a
  port.** When `bind_address` publishes on all interfaces (`0.0.0.0`, `::` or
  empty), the check that the host port is free now probes loopback - a port
  taken on every interface is taken there too - instead of briefly binding the
  wildcard address itself.

- **Web: page titles no longer repeat the site name.** A title that already
  says "OpenCloud Security Scanner" - most documentation guides - is no longer
  followed by `· OpenCloud Security Scan`, so a search result shows the part
  that tells the pages apart. Every page also declares its language as
  `og:locale`, and the `/ai` description is short enough not to be cut off.
  An address with a trailing slash (`/about/`) now redirects permanently
  (308) instead of temporarily (307), so a crawler keeps one address per
  page, and `/favicon.ico` redirects to the site icon instead of answering 404.

- **The Docker setup wizard is easier to read.** A question opens with its
  first sentence, and `?` shows the rest with a link to the page documenting
  the setting, at the release the wizard came from. Text wraps to the width of
  the terminal. The summary labels each answer with its question, gives the
  name to type in brackets and marks every answer that differs from the
  default, and the enrollment link block uses the same rules as the rest of
  the output.
- **The Docker setup wizard offers the bundled Authentik once a sign-in is
  wanted.** Switching on the operator's area at `/admin` or the sign-in on
  `/mcp` now makes *yes* the default at the identity provider question, because
  nearly every deployment asking for either has no provider of its own and was
  otherwise sent on to issuer, audience and key questions it could not answer.
  Answering `no` still checks tokens against a provider you run. The default
  moves only when a sign-in is switched on, so re-running over a deployment
  that already declined Authentik keeps it out, and `--sign-in` on its own
  still adds no provider.
- **The Docker setup wizard is easier to follow.** It opens with a framed
  title, the list of steps ahead and a table of what can be typed at a
  question; every section heading shows `Step N of 12` with a progress bar;
  the question, its current value and a refused answer stand out from the
  explanation; and the summary and closing screens are grouped under rules.
  The styling is plain ANSI from the standard library - Rich, questionary and
  InquirerPy were considered and would each need installing on a host that
  has only Docker - and it is left out entirely when the output is not a
  terminal, `NO_COLOR` is set or `TERM=dumb`, so piped and logged runs print
  exactly the plain text they did before.

### Documentation

- **`tests/README.md` indexes the test suite.** Every test module is listed by
  area with a line on what it protects, alongside the shared fixtures, how to
  run the suite and its conventions. `tests/test_documentation_indexes.py`
  fails when a test module is added, renamed or removed without the index
  following.

## [1.22.5] - 2026-09-13

### Changed

- **The Docker setup wizard sets the enrollment link apart.** It was one
  paragraph among the proxy commands and the `/admin` steps at the end of a
  long run, and easy to scroll past - leaving an operator to create accounts
  and group memberships by hand in Authentik that the link would have made.
  It now closes under its own `ENROLLMENT LINK` heading, with the command that
  builds the link from `.env` first, and says "Send it to scanokko. It asks for
  that username" for one name rather than "Send that link to each of
  scanokko".

### Documentation

- **Setting up an operator for `/admin`, by the wizard or by hand.**
  `docs/authentik.md` has a new section on the two places an operator has to
  be named - `COS_WEB_ADMIN_USERS` and Authentik's
  `opencloud-scanner-operators` group - and reaches it both ways: through the
  wizard's enrollment link, and in the Authentik interface or from a shell,
  including getting into `akadmin` with `ak create_recovery_key` when
  `AUTHENTIK_BOOTSTRAP_PASSWORD` is refused by a database older than `.env`.
  The second-factor section now says what a person sees when enrolling an
  authenticator app, a security key or recovery codes. The troubleshooting
  table gains the refused bootstrap password, a sign-in Authentik stops
  because the account is not in the group, and `password authentication
  failed for user "authentik"` from a database volume created under another
  `AUTHENTIK_PG_PASS`. `ADMIN.md` points there.

## [1.22.4] - 2026-09-13

### Changed

- **A pull request documents itself in `CHANGELOG.md` alone.**
  `scripts/check_pull_request.py` no longer requires `RELEASE.md` to change or
  its heading to name the version in `pyproject.toml`, and the test that
  compared the two in the repository is gone. The release workflow writes
  `RELEASE.md` from `## [Unreleased]` and overwrites it, so an entry copied
  there by hand was discarded, and between a bump and its release the file
  rightly still names the last release - which failed the suite on a branch
  with nothing wrong in it. `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md` and the
  pull request template now say to leave it to the release. See ADR 0048.

### Fixed

- **A Docker setup wizard downloaded on its own writes the Authentik
  blueprints.** `docker/README.md` says to `curl` just `setup-wizard.py`, but
  the wizard copied the blueprints from a checkout beside it and skipped any
  it could not find without a word. The generated stack mounted
  `./authentik/blueprints` anyway, Docker created it empty, and Authentik
  started with no provider: `/mcp` refused every token, and the forward auth
  in front of `/admin` answered 404, which nginx turns into a 500. The wizard
  now carries the four blueprints itself, generated into it from
  `authentik/blueprints/` by `scripts/embed_wizard_blueprints.py`, and a test
  fails when the embedded copies differ from those files. A deployment set up
  with an earlier download gets them by re-running the wizard.
- Fixed version bump.

## [1.22.2] - 2026-09-13

### Added

- **The bundled Authentik requires a second factor at every sign-in.**
  `authentik/blueprints/opencloud-mfa.yaml` sets Authentik's own
  `default-authentication-mfa-validation` stage to enrol an account that has
  no authenticator - TOTP or WebAuthn - before the sign-in completes, instead
  of skipping it, and is re-applied so the requirement stays on. It is mounted
  by `docker-compose.authentik.yml` and copied by the Docker setup wizard.
  Agents using `client_credentials` run no flow and are unaffected.
- **The Docker setup wizard configures Authentik without its admin interface.**
  It asks who signs in, by username (the operator guest list is always
  included), and prints one enrollment link. Each person named chooses a
  password and enrols a second factor there; an operator joins
  `opencloud-scanner-operators` on the way. The link is an invitation keyed by
  a generated `AUTHENTIK_ENROLLMENT_TOKEN` in `.env` - the wizard prints the
  link with a placeholder and a command that fills the token in from `.env`,
  never the token itself, so it stays out of scrollback and CI logs
  (`authentik/blueprints/opencloud-enrollment.yaml`), admits only the listed
  names, each once, and creates nothing without the token. `akadmin` gets a
  generated `AUTHENTIK_BOOTSTRAP_PASSWORD` for recovery, which also closes the
  initial-setup flow that would otherwise make whoever reached it first the
  administrator. See ADR 0047.

### Changed

- **The Authentik stack runs Authentik 2026.8.2.** `docker-compose.authentik.yml`
  and the image the Docker setup wizard writes move from 2026.8.0 together, so
  a generated stack and the file next to the wizard still pin the same version.
- **`forwardedHostIgnored` names a missing default server on the reverse proxy
  as a cause.** The explanation used to trace every failure to an instance
  that was never told its address, so an operator with `OC_URL` set correctly
  was sent back to it. A proxy with no default server answers a `Host` it has
  no site for from whichever site it loaded first for that port - often
  another application on the same machine - and a redirect there built from
  `$host` repeats the probe host without OpenCloud ever seeing the request.
  The explanation now says so when only `Host` comes back as a redirect, the
  remediation gives an explicit nginx default server that refuses unknown names
  (and the Apache equivalent) plus how to tell which server answered, and
  `docs/reverse-proxy.md` and `docs/scanner-checks.md` describe the same.
- **`forwardedHostIgnored` names a missing default server on the reverse proxy
  as a cause.** The explanation used to trace every failure to an instance
  that was never told its address, so an operator with `OC_URL` set correctly
  was sent back to it. A proxy with no default server answers a `Host` it has
  no site for from whichever site it loaded first for that port - often
  another application on the same machine - and a redirect there built from
  `$host` repeats the probe host without OpenCloud ever seeing the request.
  The explanation now says so when only `Host` comes back as a redirect, the
  remediation gives an explicit nginx default server that refuses unknown names
  (and the Apache equivalent) plus how to tell which server answered, and
  `docs/reverse-proxy.md` and `docs/scanner-checks.md` describe the same.

### Fixed

- **Signing in to `/admin` through Authentik works.** The operator-area
  blueprint created a proxy outpost of its own, but named no configuration for
  it, so Authentik refused the entry - and, a blueprint being applied as a
  whole, rolled back the provider, application and binding with it. Nothing in
  the stack ran that outpost either, so the forward-auth path answered 404,
  which nginx turns into a 500 for every request to `/admin`. The provider is
  now assigned to Authentik's embedded outpost, which the server already serves
  on port 9000, and the old outpost is removed where an earlier version did
  create it. The embedded outpost is re-applied every hour with exactly the
  providers the blueprint lists, so a provider assigned to it by hand is taken
  off again.
- **The embedded outpost sends a browser to Authentik's public address.** Left
  unconfigured it redirects to `http://localhost/application/o/authorize/`,
  which no visitor can reach. The blueprint now sets it from
  `COS_AUTHENTIK_URL`, which `docker-compose.authentik.yml` passes to the
  server and worker from `AUTHENTIK_URL`, and which the Docker setup wizard
  writes into the compose file it generates.

- **Re-running the Docker setup wizard moves Authentik to its newer patch
  release.** The image tag is remembered with every other answer, so a newer
  wizard run against an existing deployment kept writing the release that
  deployment was first set up with - which is how a stack stayed on 2026.8.0
  after the wizard moved to 2026.8.2. A remembered pin in the same `YYYY.M`
  series is now moved up and the wizard says so; a pin in an older series is
  left alone with a warning, because an upgrade across series can carry
  migrations worth reading first.
- **The generated nginx configuration gives the forward auth room for
  Authentik's headers.** The `/admin` and `/outpost.goauthentik.io` locations
  now set `proxy_buffers 8 16k` and `proxy_buffer_size 32k`, as Authentik's own
  nginx example does: its session cookie and identity headers outgrow nginx's
  defaults and fail as "upstream sent too big header", a 502 for a sign-in that
  worked.
- **Verified end to end.** A generated stack with Authentik 2026.8.2 and the
  generated nginx configuration signs an operator in and serves `/admin`, and
  keeps an account outside the operator group out. A test now fails if the
  blueprint creates an outpost of its own again or stops setting the embedded
  outpost's address.

## [1.22.1] - 2026-09-13

### Added

- **The Docker setup wizard generates for rootless Docker too.** Under a
  rootless daemon, uid 10001 in a container is the user's subordinate uid at
  that offset on the host, so the `sudo chown 10001` the wizard printed for a
  bind-mounted audit or Redis directory handed it to an account the container
  never runs as, and the container could not write to it. The wizard now asks
  whether the daemon is rootful or rootless - detected from the socket, which a
  rootless daemon serves under `/run/user/<uid>` - and for a rootless one
  prints a `chown` that runs inside a container instead and needs no sudo. A
  logrotate policy names the mapped host ids from `/etc/subuid` and
  `/etc/subgid`, and the wizard says so when there is no range to read. It
  also points out that the default rootless port driver hides the client
  address from a port published beyond `127.0.0.1`. Verified end to end on
  `docker:dind-rootless`: both containers write to their directories.

- **The Docker setup wizard writes Authentik's site into the proxy
  configuration too.** `docker/setup-wizard.py` already wrote nginx, Apache,
  Caddy or Traefik for the scan service, including the forward auth in front
  of `/admin` - but a stack that brought Authentik still left its sign-in page
  to be proxied by hand, and every sign-in redirects a browser there. When the
  stack brings Authentik, the same file now carries a second server block,
  virtual host or router answering to the host name of Authentik's public
  address and proxying to its published port, with the WebSocket its
  interface keeps open and `X-Forwarded-For` set rather than appended. nginx
  and Apache are asked for a certificate for that name, since it is not the
  scanner's; Caddy and Traefik fetch their own. An address that is
  `localhost`, a bare IP or the scanner's own host name gets no site, and the
  warning that used to cover only `/admin` now says so for any stack with
  Authentik behind a generated proxy.

### Changed

- **The Docker setup wizard pulls the published image by default.** It is one
  file meant to be downloaded onto a host with nothing but Docker, and the
  former default, `build`, needed a checkout of this repository such a host
  does not have. `dockerhub` is now the default and listed first; answer
  `build`, or pass the new `--image-source build`, to build the code in a
  checkout instead - the local-testing recipe in `ADMIN.md` now does.
- **`--force` lets the Docker setup wizard replace a shipped compose file in
  place.** `docker/docker-compose.yml` and the other compose files in
  `docker/` were refused as targets even with `--force`, so reconfiguring the
  stack a checkout already runs meant moving it to a directory of its own.
  They are still refused without the flag, and the refusal now names it; with
  it they are overwritten, and the wizard says on stderr - where an unattended
  run shows it too - that the checkout now carries a modified tracked file and
  how to put the shipped one back.

### Fixed

- **Automatic updates work on Docker 29 again.** The Watchtower the Docker
  setup wizard adds with `--auto-updates` was `containrrr/watchtower`, which
  was archived in December 2025 and always speaks Docker API 1.25. Docker 29.0
  raised the daemon's minimum to 1.44 and 29.3 to 1.40, so the container
  panicked on start with `client version 1.25 is too old` unless
  `DOCKER_API_VERSION` was pinned by hand. The wizard now writes
  `nickfedor/watchtower`, the maintained fork, which negotiates the API
  version with the daemon and reads the same variables and enable label - so
  no version is pinned, and none goes stale when a daemon raises its minimum
  again. Reproduced and verified against Docker 29.6.

- **The Docker setup wizard no longer lets the audit trail and Redis share a
  host directory.** The web image writes as uid 10001 and Redis as uid 999,
  and a directory has one owner, so whichever was chowned last kept the other
  container from writing. The same directory - however it is spelled - or one
  inside the other is now refused at the question, blocks the summary, and
  makes an unattended run write nothing.
- **A generated logrotate policy names the audit file by its absolute path.**
  The default `./audit` was written into the policy as it was, and logrotate
  resolves a relative path against wherever cron runs it from rather than
  against the compose file, so the policy rotated nothing.

## [1.22.0] - 2026-09-13

### Added

- **The browser can ask whether the fixes worked.** Three surfaces already
  answered it - `--baseline` between two monitoring runs,
  `check-opencloud-scanner diff` between two archived documents, and the
  `compare_scans` tool for an agent - and the person who ran both scans in a
  browser was the only one who could not. `GET /compare` takes the two uuids
  they already hold and shows what was resolved, what is new, what is still
  open and how the grade moved; a finished result page links to it with its
  own uuid already filled in, so only the earlier one has to be pasted.

  **It is the same arithmetic, not a fourth opinion.** The comparison in
  `webapp/workflows.py` was split into the part that reads two documents and
  the part that compares them, and the page calls the second directly. A
  reader, an agent and an operator's own alerting are therefore told the same
  thing about the same pair - the failure mode a second implementation in the
  page would eventually produce, and the one
  [ADR 0029](adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md)
  exists to prevent.

  **Nothing is stored, and nothing is listed.** Both uuids have to be
  presented, both results have to still exist, and the answer is written
  nowhere. An unknown uuid is a 404 that names *which* of the two is gone, a
  scan still running is a 409 rather than a 404, and the same uuid twice is
  refused with 422 - an empty diff of a scan against itself reads as "nothing
  is wrong". Two documents describing different instances are compared and
  said so. Like every page that renders a result, it is never indexed.

- **Checkmk runs this check from either side now.** Checkmk speaks Nagios, so
  a Checkmk server has always been able to run the plugin as an active check
  and read its line - but that route needs the server to reach the instance,
  and the deployments where it cannot are exactly the ones an agent already
  sits inside. The agent's own protocol is not the Nagios line: metrics are
  separated by `|` rather than spaces, every value has to parse as a number
  (the `s` on `time=4.120s` does not), the service name is quoted, and the
  detail follows the summary as a literal `\n`, because a real newline starts
  another service. `--format checkmk` writes that line - one per host in
  `--host`, since one line is one service - and
  `contrib/checkmk/opencloud_security` is it as a script ready to install.

  **The scanned instance names the service**, not the host the agent runs on:
  this plugin probes an instance from outside, so the natural place to run it
  is a monitoring host watching several instances, each of which needs a
  service of its own.

  **The state stays the plugin's.** A local check's thresholds are only
  evaluated when the state field is `P`, which hands the verdict to Checkmk,
  and deciding is this plugin's whole job - thresholds, waivers, the rules
  end of life and a baseline add on top. So the line carries the state it
  already reached and the metrics carry values alone, with no second opinion
  for Checkmk to disagree with. A measurement that was not taken is left out
  rather than sent as a zero: without `--check-hardening` there is no
  `hardenings_missing`, because an empty list of missing measures would
  otherwise be indistinguishable from a perfect one.

  [`docs/checkmk.md`](docs/checkmk.md) has both routes, the metric table, and
  why the local check is installed in a `local/3600/` subdirectory rather than
  in `local/` itself - a script in the directory proper runs on every agent
  call, once a minute, which is a full scan a minute against somebody's
  production instance.

- **The web pages keep track of a scan while the reader is elsewhere.** Four
  small things for the moments nobody is looking at the page, each running
  entirely in the browser and each leaving the page exactly as it was without
  scripting:

  - **The tab title follows the scan.** `Queued: host`, `#2 in line: host`,
    `Scanning: host`, and on a finished report `Grade B: host`, so a reader
    who switched tabs sees the result from the tab strip. The server writes
    the first reading and a finished page names its grade with no script at
    all. The title never carries the uuid, and the grade goes into the tab
    alone: the `title` block that also feeds `og:title` and the structured
    data stays generic, through a new `tab_title` block in `base.html`, so a
    link preview in a chat channel does not print somebody's grade.
  - **A rescan offers the comparison with the scan before it.** A finished
    report now says "You scanned this instance earlier in this tab, at 14:02 -
    see what changed since then", linking `/compare` with both uuids filled
    in. The earlier uuids are kept in the tab's `sessionStorage` only: never
    sent to the server, gone when the tab closes, and dropped once their
    result has expired rather than offered as a link to a 404.
  - **A report warns before it disappears.** In its last five minutes a
    finished report shows a warning near the top with a link to the
    downloads, keeps the minutes current, and says so once the result has
    gone. The server renders the warning already visible when a page is
    loaded inside that window, so a reader without scripting is warned too,
    and a failed scan, which has nothing to export, is offered no download.
  - **The form offers back the last settings used.** After a scan, the next
    visit to the form offers the release track, output format and waivers
    that scan used - "use them again" or "forget them" - instead of applying
    them unasked. They are kept in `localStorage`; the address is not, since
    the browser's own autocomplete already remembers it on the visitor's
    terms. A waiver or track the catalogue no longer lists is simply not
    applied.

- **An operator can name the addresses this deployment will not scan.** Every
  rule in the SSRF guard so far was a property of the address - private,
  link-local, a metadata endpoint. None of them could express the request that
  actually arrives: an instance owner asking to be left alone, a host somebody
  keeps submitting so the service hammers it, a range that is not a scanning
  target here however public it looks. `COS_WEB_BLOCKED_TARGETS` is that list -
  hostnames, `.suffix` domains (`*.example.org` is accepted as the same thing)
  and CIDR ranges, separated by `;`.

  **It outranks every setting that loosens the guard**, `COS_WEB_ALLOWED_HOSTS`
  and `COS_WEB_ALLOW_PRIVATE_TARGETS` included. Those answer whether a request
  could be an attack, and an operator may reasonably say "not on my own
  network"; an exclusion answers whether this service scans that address at
  all, which is a promise made to somebody outside the deployment. See
  [ADR 0043](adr/0043-an-operators-exclusion-outranks-every-allowance.md).

  **A name is matched by name, a range against every address the name resolves
  to**, so a second DNS record pointing at the same machine does not buy a
  scan. It is checked at submission, again in the worker immediately before
  the scan - a target excluded while its job waited in the queue is refused
  rather than scanned - and on every redirect hop, so a scanned host cannot
  name an excluded one in a `Location` header. Agents inherit it by calling
  the same API.

  **An entry that does not parse refuses startup**, in the web process and in
  the worker alike, because a typo here is otherwise invisible: the service
  comes up, answers normally, and scans exactly what it was told to leave
  alone. The refusal a visitor sees says only that the service has been asked
  not to scan that address; which entry matched is the operator's business.

- **A name behind several addresses can be checked on every one of them.** A
  scan dials the name once and sees whichever node the resolver put first, so
  in a pool where one node missed a configuration rollout - no HSTS, demo
  accounts still signing in, an older release - that node served some of the
  visitors and none of the scans. `tlsAddressParity` could not catch it: it
  compares only the TLS identity of the two address families, and nodes behind
  one certificate share it whatever they serve. `--all-addresses`
  (`COS_ALL_ADDRESSES`, `scanner.check_all_addresses`, and the same flag on
  `check-opencloud-scanner scan`) repeats the version, header, hardening and
  demo-account checks against each resolved address and reports
  `addressParity` when they disagree; the result document lists what each
  address served under `addressObservations`.

  **It stays aimed where the scan was pointed.** Every request keeps the
  hostname in `Host` and SNI, and the addresses are the resolver's answer for
  that name - or the caller's pin, which a pinned scan never widens. The
  finding is as severe as the worst difference, because the rating was built
  from whichever node answered first: a demo sign-in on another node counts
  like `demoUsersDisabled`, another release is `high`, other drift `medium`,
  and an address that resolves but does not answer fails too. Waived names are
  not compared.

  **Off by default, and never in the web service.** It costs about a dozen
  requests per address and a single-address name has nothing to compare; the
  web application sets it off explicitly and offers no field for it, since a
  request there chooses what to scan and never how hard. See
  [ADR 0042](adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

- **The exclusions can be changed without a deployment window.** The request
  that produces most of them - somebody writing to ask not to be scanned -
  rarely arrives at a convenient moment, and an environment variable read at
  startup answers it with "after the next restart". The operator's area now
  has an *Exclusions* card that adds and withdraws entries, and a change takes
  effect **from the next request, in every process**: the API reads the list
  on each submission and the worker when each job starts, so a scan already
  waiting in the queue is refused rather than run.

  **It is the one control in that area that writes**, and deliberately the
  safest shape of one. It can only ever *refuse* a scan, so a stolen operator
  session cannot point this service at anything. `COS_WEB_BLOCKED_TARGETS` is
  a floor the page cannot withdraw - those entries are listed with no control
  beside them, and an attempt to remove one is refused with a pointer to the
  environment, so a compose file stays the truth about what it declares. And a
  store that cannot be read refuses the scan rather than proceeding without
  the list, which is the opposite of how this service treats every other piece
  of runtime state and the right way round for a list whose absence means
  scanning somebody who asked not to be. See
  [ADR 0044](adr/0044-the-operator-area-may-write-the-exclusions.md).

  **That refusal is an answer, not a stack trace**: HTTP 503 with a sentence
  in the visitor's own language saying the service cannot reach its own
  configuration, and - because there is nothing they can change to get past it
  - the same pointer at running the scanner themselves that a rate limit
  carries. The audit trail records it as `exclusions_unreadable` rather than
  as a rejected target, so an operator reading the trail is not sent looking
  for a bad address that was never the problem.

  **The two halves are one list, however each is spelled.** An entry written
  in the area is normalised; one from the environment is shown exactly as the
  compose file spells it, so that card and file can be read side by side.
  Comparing those two as text made `Example.COM` and `example.com` two
  exclusions where the guard, which parses both, only ever saw one - so they
  are now compared parsed: the area declines to store what the environment
  already holds, and refuses to withdraw it under any spelling.

  Entries added there live in Redis and are as durable as it is; the card says
  so, and points at the environment variable for anything that must outlive a
  flush. An entry is capped at 253 characters, the longest a hostname can be,
  in the area and in `COS_WEB_BLOCKED_TARGETS` alike - anything longer could
  never match a target this service would accept, so it is a typo, and the
  ceiling on the number of entries bounds nothing without it. `/admin/state` -
  the document an operator copies into an issue report - carries how many
  exclusions are in force and never which.

### Changed

- **The workflows, shell scripts, Dockerfiles, compose files and frontend
  scripts are linted.** `workflow-lint.yml` runs actionlint and zizmor over
  `.github/workflows`; `static-analysis.yml` runs shellcheck on every tracked
  shell script, hadolint on both Dockerfiles, `docker compose config` on every
  compose file and Biome on `frontend/static/js` (rules in `biome.jsonc`);
  `codeql.yml` adds CodeQL for Python, JavaScript and the workflows. Every tool
  is pinned by version, and the downloaded binaries by digest. What they found
  is fixed: checkouts no longer leave the job token in `.git/config` unless the
  job pushes, the release workflow reads its version from the environment
  instead of pasting an expression into shell, the SBOM is generated from the
  locked environment, a Docker Hub pin carried the wrong version comment, and
  the plugin image runs as the numeric `USER 1000` - the uid it already had, so
  mounted files keep their owner.

- **The .deb and the .rpm are installed on every pull request.** The release
  dry run now installs both packages in Debian 12, Ubuntu 24.04 and Fedora 43
  with the distribution's own package manager, runs both commands and the
  Nagios plugin path, and removes them again (`packaging/tests/install-smoke.sh`).

- **A missed Homebrew formula regeneration opens a pull request.**
  `homebrew-formula.yml` runs `build_homebrew_formula.py --check` daily and,
  when the formula no longer pins the newest release on PyPI, regenerates it
  and opens a pull request. The architecture diagram's image references are
  checked on every pull request, and so are the documented OpenCloud links.

- **CI is locked, cached and cancels what is superseded.** Every `uv sync` is
  `--locked`; workflows that publish nothing cache uv's downloads, while those
  that push, publish or sign never restore a cache; pull request runs cancel
  the run they replace; and the nox suite runs as a five-job matrix, one per
  Python. `tests/test_workflow_hardening.py` holds each of these.

- **A release is built on the pull request, and publishes to PyPI last.** The
  release workflow uploaded to PyPI straight after building the wheel, and
  only then built the `.deb`, the `.rpm` and the web bundle - so a broken
  packaging recipe left a version on PyPI with no tag and no GitHub release,
  and the retry failed on "File already exists". Every artifact is now built
  and attested before the upload, `uv publish --check-url` lets a repeated run
  finish the release, and the new `release-dry-run.yml` builds the release
  notes, the wheel (checked by `twine check --strict`), both distribution
  packages, the web bundle and both images on every pull request, publishing
  nothing. See
  [ADR 0045](adr/0045-a-release-is-rehearsed-on-the-pull-request-and-publishes-last.md).

- **The pull request checklist's two release rules can be checked locally.**
  `python scripts/check_pull_request.py --base origin/main` refuses a change
  without a new `CHANGELOG.md` entry and a `RELEASE.md` under the declared
  version, and a version change that does not move past every tag or whose
  bump commit names a different version. It is a local check, not a CI gate,
  and a release needs no label. The README table of contents, the `docs/` index and the
  `/documentation` manifest are held to their contents by
  `tests/test_documentation_indexes.py`.

- **The architecture decision records have an index.** `adr/README.md` now
  lists every record with its number, decision and status, so the one that
  governs an area can be found without opening forty-odd files by name.

- **On a phone, the address field is the first thing on the page.** Stacked
  into one column, the eyebrow, the two-line headline and the lede filled
  most of the screen before the form, so a visitor had to scroll to find the
  one field the service exists for. Below 640px the form is now painted at
  the top, with the headline and introduction, the artwork and the promises
  following it. Only the painting order changes: the markup still puts the
  heading first, so screen readers and the tab order are unaffected, and
  wider screens look exactly as before.

### Fixed

- **A name pinned to several addresses no longer fails on the first one
  alone.** The web service resolves a submitted name, vets every address and
  pins the scan to them - and then only ever dialled the first. A dual-stack
  instance whose AAAA record points at nothing, or a scan from a host without
  an IPv6 route, answered "unreachable" where a visitor's browser simply used
  IPv4. A connection now tries the vetted addresses in order and the one that
  accepts is dialled first from then on; the TLS inspection and the debug-port
  probes use that address too, so a dead first address no longer reports a
  handshake failure or closed ports the instance does not have. Nothing
  outside the pinned list is ever dialled, only a failure to connect moves on,
  a single pinned address - the per-address comparison - is never widened, and
  the result document still lists the addresses in the order they resolved.
  The plugin, which does not pin, was not affected.

- **A comparison shows when each scan ran, instead of calling both times
  "unparsable".** `scannedAt` is written by the scanner from its own clock and
  is not one of the fields a scanned host has any say in, but it was being run
  through the allow-list meant for a version string a stranger chose - and
  that list has no `:` in it. Every comparison reported both timestamps as
  `unparsable`, to an agent as well as on the new page.

## [1.21.3] - 2026-09-11

### Fixed

- **A storage directory nobody named no longer writes a compose file Docker
  refuses to parse.** Answering `filesystem` to the Redis persistence or audit
  trail question and then leaving the path empty produced `- :/data` - an
  empty mount source, a colon, and a stack that will not start, over a
  question that was never answered. The empty answer now falls back to the
  named volume, which needs nothing from anybody and keeps the data, and the
  wizard says that it did.

  **The directory is asked for properly, and it has a default**: `./data` for
  Redis and `./audit` for the trail, beside the generated compose file. The
  leading `./` is the whole point - Compose reads `data:/data` as a *named
  volume* called data and `./data:/data` as the directory next to the file, so
  a bare name is refused with that explanation rather than silently mounting
  something else. An absolute path still works.

- **The wizard asks the questions an answer opens, instead of only the first
  one.** Each section's question list was filtered once, before the section
  began, and the re-check inside the loop could only ever remove a question -
  never add the ones a fresh answer had just made relevant. The visible result
  was a mail server configured with nothing but a host name: the port, the
  transport security, the credentials and the From address all hung off
  `smtp_host` being set, and by the time it was, the list they would have been
  in had already been decided. Relevance is now decided one question at a time
  as the answers arrive.

  The same fault hid every Authentik question behind `--with-authentik`.
  Answering *yes* to "add Authentik to this stack" at the prompt asked for
  neither its address, nor its slug, nor **its ports**, and then generated a
  stack pinned to 9000 and 9443.

- **The release tarball carries the blueprint that provisions `/admin`.** It
  shipped `opencloud-scanner.yaml` and not `opencloud-admin.yaml`, so a
  deployment set up from the download could turn the operator's area on and
  get no proxy provider to reach it with.

### Added

- **The wizard's questions can be moved around in, and its summary can be
  worked in.** Forty-odd questions with no way back, no way to skip ahead and
  no way to fix one from the summary meant that noticing a typo one question
  too late left two options: abandon the run, or answer the rest of it knowing
  the compose file would need editing anyway. Now, at any question: `b` goes
  back to the one actually asked before it, a numbered choice can be answered
  with its number, `-` empties a text setting where an empty line only ever
  kept the default, and `rest` takes every remaining default and jumps to the
  summary. Section headings carry their position - *(7 of 12)* - because a
  long walk that says nothing about how much is left is one people abandon
  halfway.

  **The summary is the last place a mistake is caught, and it used to be a
  dead end.** It is now grouped under the headings the questions were asked
  under, with what was derived or generated listed apart from what somebody
  decided, and it asks *"Write it all out now? [Y/n], or name a setting to
  change"*. Naming one - `host_port`, or enough of it to be unambiguous -
  re-asks that question and comes straight back, so the express path through
  the whole thing is `rest` and then the three settings that matter.

- **Running the wizard again edits the deployment rather than re-describing
  it.** It always promised that, and delivered half: `.env` was read back so
  no credential was regenerated, and every *other* answer - the ports, the
  limits, the paths, the proxy, the sign-in - was gone. It now writes
  `.<compose-file>.answers.json` beside the compose file, its own notebook of
  every non-secret answer, and offers those back as the defaults on the next
  run. Changing a port on a live deployment is a re-run, `rest`, one setting,
  done. The notebook holds no credentials - those stay in the owner-readable
  `.env` they are already read back from - and is safe to delete. A preset
  named on the command line now overrides what it remembers, which is why
  `--preset public` sets the answers the private preset moves rather than
  doing nothing.

- **Turning the operator's area on ends the wizard with the walkthrough for
  opening it.** `/admin` refuses rather than asks - no login page to arrive
  at, no password prompt to get wrong - so every missing piece of the
  arrangement produces the same 404 as any unknown path: the right answer to
  give a stranger, and a miserable one to debug against. The steps are now
  printed in order with this deployment's own addresses in them: set the first
  Authentik password, put that account in the `opencloud-scanner-operators`
  group the blueprint binds the application to, install the generated proxy
  configuration, give Caddy or Traefik the shared secret in its own
  environment - it reads the value at run time rather than carrying it, so an
  installed, correct-looking file is not the last step - check that
  `COS_WEB_ADMIN_USERS` names the same person, and open the area. Then what
  each failure means: a bare 404 is the header that never arrived, a 404 after
  signing in is the second guest list, and a looping sign-in is a provider
  whose public address is not the one the browser used. Against somebody
  else's provider it names the header contract instead, and the sign-out URL
  the bundled stack sets for itself.

- **The wizard writes the reverse proxy configuration too.** The stack
  publishes a plain HTTP port on the loopback address and nothing else, so
  something in front has to terminate TLS - and the notes for doing that lived
  only in `docs/reverse-proxy.md`, to be copied by hand. Name what you run -
  nginx, Apache httpd, Caddy or Traefik - and the file is written beside the
  compose file, with the install commands in its header and in the wizard's
  next steps: TLS with a redirect from port 80 that leaves the ACME challenge
  alone, an `X-Forwarded-For` that is *set* rather than appended so a client
  cannot choose the address its rate limit is counted against, and a `/mcp`
  that is never buffered, because a buffered event stream is an agent session
  that waits for ever. Each of the four was checked against the server itself.

  **Where the stack can provide it, the file carries the forward auth in front
  of `/admin`**: the request is shown to the authentik outpost first and only
  what it accepts is passed on, carrying the identity the outpost established
  and the shared secret that makes those headers worth believing. Apache is
  the exception and says so in the file - it has no forward auth of its own,
  so the area is proxied by the catch-all without that header and the service
  answers 404, which is the right failure rather than an unauthenticated
  console.

  **The secret is not in the file you would commit.** A proxy configuration is
  pasted into tickets and copied between hosts exactly like a compose file, so
  nginx gets a one-line `include` of an owner-readable snippet - deliberately
  not named `.conf`, since everything called that under `conf.d` is included
  into the `http` block and this belongs to one location - while Caddy and
  Traefik read the value from their own environment.

### Changed

- **An identity provider can now be asked for by the operator's area alone.**
  `/admin` has no other way in - the service authenticates nobody and refuses
  a request that did not arrive through an outpost - but every Authentik
  question hung off the MCP endpoint being enabled, so a deployment that
  wanted the area and not the agent endpoint could not be offered one. The
  provider is its own section now, asked for by either consumer, and a
  deployment with an area gets the second blueprint,
  `authentik/blueprints/opencloud-admin.yaml`, copied beside the compose file
  that mounts it, with `COS_WEB_ADMIN_URL` set to the origin it protects. A
  provider with nothing to guard is still not deployed.

- **The mail questions cover the whole session.** Beyond the server name:
  the port, STARTTLS or implicit TLS or neither, whether the server wants an
  account at all, the username, the password and the From address. Saying it
  wants no account stops the credential questions and drops any answer left
  over from before, because Authentik reads an empty username as *do not
  authenticate* and half a credential fails at the first message rather than
  at the first mistake. A username with no password, and a password with no
  username, are each pointed out before anything is written.

- The guest list and the shared secret for the operator's area are no longer
  asked for when the area is off - an unused credential in `.env` is an
  invitation to turn the area on without one.

## [1.21.2] - 2026-09-10

### Changed

- **A WebMCP tool in the browser now answers a failure instead of throwing
  one.** The two agent surfaces disagreed about the same service. Every
  server-side `/mcp` tool returns `ok: false` with a status and a `retryable`
  flag, and says so in its own description — *retryable false means stop; do
  not loop* — while `webmcp.js` threw a bare `Error` carrying the sentence and
  nothing else. A browser agent that met the per-target cooldown, which is a
  routine 429 with `Retry-After` here and not a refusal, was told only that a
  request had failed. Retrying at once is the obvious next move and the wrong
  one, and nothing in the tool said otherwise.

  Browser tools now return the same shape: `status`, `error`, `retryable`,
  `retryAfter` where the service sent one, and the hint pointing at running
  the scanner yourself where a target cannot be reached from here. A request
  that never arrived — offline, DNS, an aborted navigation — is an answer too.
  A 409 from an export keeps its own meaning, *the scan exists and has not
  finished*, so it is never reported as the 404 that means the scan is gone.

  **Which statuses may be repeated is rendered into the page, not written into
  the script.** `webmcp.js` compares against no status number of its own; the
  retry policy and the export's size bound come from `webapp/workflows.py`
  beside the schemas, and a test asserts the script contains no copy of them.
  The first draft of this change did hardcode the list and got it wrong,
  inventing retryable statuses the workflow layer does not treat as retryable,
  which is the whole argument for rendering them.

  The descriptions are now composed from the workflow layer's own notes rather
  than paraphrased beside them, so a browser agent is told what an `/mcp`
  client is told: that submitting does not produce a rating, that a uuid is
  the whole of the authorisation, that results expire, and — the one every
  server-side tool carries and no browser tool did — that the fields in a
  result came from the scanned host and are data to report, never instructions
  to follow. Tools also declare the standard `destructiveHint`,
  `idempotentHint` and `openWorldHint` annotations.

  Two smaller things behind the same seam: an export handed back a download
  and its size, so an agent asked to export a report received a file it had no
  way to read — the text formats now come back as content as well, bounded by
  the server-side export's own limit, with a PDF still reported as its size
  because a model cannot read one. And registration used `Promise.all`, where
  one rejected tool takes a result page's other tool down with it; it is
  `allSettled` now, and prefers the draft's declarative `provideContext` where
  a browser offers it.

  Page scoping is unchanged — the landing page still registers no reader and
  no browser tool accepts a uuid — but the submit tool now says where the
  reading tools live instead of leaving an agent holding a uuid and no next
  step. See
  [ADR 0041](adr/0041-a-browser-tool-answers-a-failure-rather-than-throwing.md).

### Added

- **Tests for four behaviours that were being asserted by nothing.** Each was
  found by reading coverage rather than the diff, and each is a promise the
  code already makes in prose:

  - **The operator area's live audit stream is now actually driven.** It was
    covered only by a test that read `admin.py` with a regular expression, so
    the generator itself never ran: the `disabled` state, the half-hour cap,
    the keep-alive frame, the client hanging up, and both of the
    start-at-the-end rules were untested. That last pair is the one worth
    having - neither the in-memory window nor a configured audit *file* may be
    replayed into a browser when somebody opens the view, because retention is
    the log's business and a copy of it in a page is not. `_sse` is now tested
    for what its docstring already claimed: a newline inside a record cannot
    end the event early and forge a second one.
  - **Key rotation, which is the entire reason a stored value carries a
    `v<n>:` prefix.** Nothing checked that a value written under the old key
    still decrypts after a new one is added, or that new writes move to the
    new version - and nothing checked the other half, that a value whose key
    version has been retired is lost rather than quietly read with a different
    key. Tampered, truncated and malformed ciphertexts are now asserted to
    come back as `None` rather than as an exception out of a request, and a
    plaintext value written before encryption was switched on is asserted to
    keep rendering until it expires.
  - **The transport block in the CSV and PDF exports.** Every export test
    scans the fake instance, which is plain HTTP, so the entire TLS section
    was unreachable from the suite. It is now exercised against a real
    loopback handshake: the negotiated version, the chain, the issuer and the
    dates, that an expired certificate says *expired 30 day(s) ago* rather
    than printing a date somebody has to subtract, that "not trusted" and "no
    path to a public root" stay two different problems, and that a deprecated
    version still accepted does not read like one that was refused.
  - **`SecretProvider.resolve_tree`, and the refusals around it.** The
    recursion that resolves every `secret://` in a nested configuration had no
    test at all, nor did a reference naming nothing, an unset environment
    variable, or a command that exits non-zero - the last of which would
    otherwise hand the caller an empty credential. Two boundaries are now
    written down: only the four listed schemes are references, so a
    `redis://` URL in a setting is a value and not a lookup; and `exec://`
    runs its argv directly, so a `;` in a reference is part of an argument
    rather than a second command.

### Fixed

- **A certificate that expired today no longer passes the expiry check.**
  `days_remaining` truncates towards zero, so the first day of expiry counts
  as `0` rather than `-1` - and both the wording and the verdict were read
  from the sign of that number. A certificate that had gone out of date hours
  earlier was therefore reported as expiring "in 0 day(s)" and *passed*
  `--tls-min-days 0`, on precisely the day the distinction matters most.
  `Certificate` now carries an `expired` flag read from `notAfter` against
  the clock, and the check consults that instead of the sign. The flag is
  deliberately kept out of `as_dict()`: `notAfter` and `daysRemaining` are
  both already in the result document, and its shape is a contract.

- **A zone that publishes only an `iodef` CAA record is no longer told it has
  none.** `iodef` names where a CA should report a violation; it authorizes
  nobody, so the issuance risk is real and the finding was right to fail. The
  wording was not: an operator who had published a CAA record was sent looking
  for one they already had. The detail now names the tags actually present and
  says that they authorize no issuer, which is a different thing to fix.

- **A rating cap is reported as applied even when the base rating had already
  reached it.** A cap counted only when it *lowered* the rating, so a critical
  finding capping at `2` on an instance the advisories had already put at `2`
  was rendered as "would cap at 2/5, already lower" - which says something
  untrue about the only critical finding in the report. A cap is now applied
  when it equals the final rating, which is what makes the explanation
  independent of the order the checks ran in.

- **A clean instance is no longer told its failed extra checks are being
  disregarded.** With `extra_checks_affect_rating` off, the explanation
  appended "failed extra checks are reported but do not affect the rating"
  whenever `findings` was non-empty - and `findings` holds the passes too, so
  an instance with nothing wrong got the note as well. It is now added only
  when a finding actually counts.

- **`derive()` no longer discards the redirect pins on the session it shares.**
  It re-runs `__post_init__` on a probe holding an existing session, and
  mounting unconditionally replaced a pinning adapter already in use: the pins
  added to it were silently dropped, and the pool holding its open connections
  was no longer reachable from `session.adapters` for `close()` to shut down.
  Mounting is now skipped where a pinning adapter is already mounted.

- **Probes abandoned while opening an instance are closed.** Only the probe
  `_open_instance` returns was ever closed by its caller, while each fallback
  attempt - HTTPS without verification, then plain HTTP - opened another. An
  abandoned probe still owns the sockets its session pooled, which is the
  whole reason `_Probe.close` exists; all three paths now close what they
  are not returning.

- **An advisory that only the running image knows about is no longer missing
  from every scan.** The stored advisory document carries no TTL - reference
  data is superseded, never expired - and the bundled file was folded in only
  when nothing was stored yet. A deployment upgraded to an image whose wheel
  ships a hand-curated advisory therefore merged into whatever an older image
  had left in Redis, and unless the feed happened to mention that advisory it
  stayed absent for the life of the deployment. The bundled file is now folded
  in on every read as well as every refresh, so the floor holds on the read
  path and an upgraded deployment is right immediately rather than after its
  next daily fetch.

- **Only the canonical spelling of a uuid is treated as one of ours.**
  `is_scan_uuid` asked `uuid.UUID()` whether it could parse the value, and it
  parses rather more than the form this service hands out: braces, a
  `urn:uuid:` prefix, upper case, and no hyphens at all. Every one of those
  interpolates into a *different* Redis key for the same scan, which is the
  opposite of what the function exists to guarantee — and the urn form puts
  colons into a key name, where `_identifiers_for` splits on them and would
  stop recognising the scan as one of its own to erase. Nothing could reach
  that today, because a key is only ever written under a server-generated
  uuid4 and every other spelling simply missed and answered 404; the check now
  holds the value to the spelling it claims to accept.

- **A rate-limit counter that lost its window no longer refuses that client for
  ever.** `INCR` and `EXPIRE` are two round trips, and a counter created by the
  first without reaching the second has no window to fall out of: the count
  never resets, so the client stays refused indefinitely with nothing in the
  log to say why. A counter already over its limit is the one place this can be
  observed, so it is also where it is now put right — the window is re-applied
  and the client waits one of them rather than for somebody to notice a key in
  Redis. A counter that still has its window keeps the one it has, so a refusal
  cannot push the client's own deadline further away.

### Documentation

- **`specs.md`: the normative contract, stated clause by clause.** Everything
  this project promises was already written down somewhere - the rating
  invariants in `AGENTS.md`, the layer boundaries in `ARCHITECTURE.md`, the
  thresholds in `README.md`, the reasoning in forty ADRs - but all of it in
  prose written to explain rather than to be checked. Asking "is this
  behaviour a promise or an accident?" meant reading the code and guessing at
  the intent behind it.

  The new file answers that question directly: numbered MUST/MUST NOT clauses
  grouped by subject - layers, the result document, findings, waivers, the
  rating, the lifecycle, exit codes, output, the webhook, configuration, how a
  scan is allowed to behave towards somebody else's machine, the web
  application, and the prohibitions - each one small enough that a test can be
  pointed at it and a commit message can cite it. Clause numbers are stable,
  and a withdrawn one keeps its number rather than being reused, so a citation
  cannot quietly come to mean something else.

  It is deliberately not a fourth explanation of the same material. Where a
  clause needs a reason, it links the ADR that argues it; where it needs a
  mechanism, it names the symbol that enforces it. And it says what to do when
  it is wrong: the code and its tests win, and the clause gets corrected in the
  same pull request.

## [1.21.1] - 2026-09-06

### Fixed

- **On a phone, the four promises no longer open the landing page.** Below
  640px `.hero` becomes a flex column so that the artwork can move underneath
  the form, and the reordering names `.hero-copy`, `.scan-form` and
  `.hero-art` - but the assurance strip is a child of `.hero` as well, and
  nothing gave it an order. Its default `0` sorted it ahead of all three, so
  the first thing a visitor met was *100% air-gapped · No data stored · No
  registration needed · Ephemeral results*, four answers to questions the page
  had not asked yet, with the headline and the address field below them. The
  strip is now ordered last, where it reads as a footnote to the instrument it
  follows. Desktop is untouched: `.hero` is a grid there and `order` never
  applied.

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

## [1.21.0] - 2026-09-06

### Added

- **Three step-by-step identity-provider tutorials, in
  [`docs/identity-providers.md`](docs/identity-providers.md).** Putting
  Keycloak, Authentik or Authelia in front of an instance was one section of
  [Running OpenCloud in a secure
  infrastructure](docs/secure-deployment.md#1-put-a-real-identity-provider-in-front),
  which argued the case and then summarised each provider in a screenful.
  This is the other half: installing each one, the provider configuration in
  full, verifying it worked, and moving an instance that already has accounts
  without stranding anybody's files in an account they can no longer reach.

  The part worth having is the section none of the three vendors can write,
  because it is not about them: **the four clients, their redirect URIs and
  their scopes are properties of OpenCloud's own applications** and are
  identical whichever provider you pick. The web client needs
  `oidc-silent-redirect.html` registered or sessions start dying at an
  interval nobody can reproduce; only the non-browser clients get
  `offline_access`, because a refresh token in a browser tab is a credential
  in a place that cannot protect it; and all four are public clients with
  PKCE, because everything OpenCloud ships runs on somebody else's machine
  and cannot keep a secret. Each provider tutorial is then only what that
  provider calls those things.

  The troubleshooting table is the failures in order of how often they are
  the answer, and the verification section ends where this repository begins:
  a scan, and the four OpenID Connect properties it reads from the discovery
  document - plus a note on the two things it deliberately cannot tell you,
  which are your group mapping and whether your second factor is enforced.

- **The operator's area has a Documentation tab.** `/admin` gained a tab
  strip, and beside the overview it now renders the two repository documents
  somebody running this service actually needs while running it:
  `ARCHITECTURE.md` at `/admin/docs/architecture`, and the operations notes in
  `ADMIN.md` at `/admin/docs/operations`. Reaching for either used to mean
  leaving the service and finding the repository.

  They are generated at build time into `frontend/templates/admin-docs/` by
  the same pipeline the public guides use ([ADR
  0018](adr/0018-cli-documentation-is-generated-at-build-time.md)), so nothing
  parses Markdown at runtime and the web application still has no Markdown
  dependency. English only, with a line above each saying which repository
  file it came from - a half-translated operations note is worse than an
  English one that says so.

  **They come from a manifest of their own**, `OPERATOR_DOCUMENTATION_PAGES`,
  deliberately separate from the one that feeds `/documentation`. That is what
  keeps `ADMIN.md`'s own promise about itself intact: the pages are absent
  from the public documentation index, the sitemap, `robots.txt` and the
  search index, they answer **404** to anybody the outpost did not authorise,
  and `tests/test_webapp_admin.py` holds them to every one of those. The one
  thing that did change is recorded in `ADMIN.md` itself: the rendered page
  travels inside the web bundle and the container image, which is acceptable
  only because that file is already world-readable in the public repository
  and contains operations notes rather than credentials.

### Fixed

- **The hero instrument follows the scheme a visitor chose, not only the one
  their operating system reports.** It was `<img src="hero.svg">`, and an
  `<img>` is a separate document: it can read `prefers-color-scheme` but never
  the `data-theme` this page writes on the root element when somebody presses
  the header switch. So the drawing answered the system while everything
  around it answered the toggle, and pressing the switch left a daylight
  instrument on a midnight page - or a midnight one on a daylight page, which
  is the same bug from the other side.

  It is now inline in `index.html`, with its styles in `app.css` under all
  three of the states the rest of the page already handles. That ends the
  second palette it was carrying: the markers are the page's own `--good`,
  `--fair`, `--info` and `--bad` rather than a hand-copy that had already
  drifted in the light scheme, and only the three colours genuinely its own -
  the sweep's magenta, the lit top of the shield, the static - are still
  written down. `hero.svg` is gone rather than left unreferenced beside it.

  The `<style>` block could not come along: `style-src 'self'` carries no
  `unsafe-inline`, so a `<style>` element in the markup is dropped by the
  browser and caught by `tests/test_webapp_api.py`. The drawing is also
  explicitly decorative now - inline, its `<title>` *would* be announced, and
  what it would announce is the headline directly above it, a second time.

- **On a phone the hero puts the field before the picture.** Stacked into one
  column, a full-width 480×300 illustration sat between the headline and the
  one field this service exists for, so the first gesture on a small screen
  was a scroll looking for something the page had just promised. The column is
  reordered rather than the artwork dropped: the wrapper dissolves with
  `display: contents` so copy, form and instrument become siblings in one
  flex column, and the drawing keeps its place underneath at a size that looks
  deliberate. The markup is untouched, so a reader without CSS still meets
  them in the order it states.

- **The lock file no longer pins a package its own maintainers withdrew.**
  `securesystemslib` 1.5.0 was yanked from PyPI as incompatible with sigstore,
  which is the only reason it is here at all: the `signing` extra pulls
  sigstore, sigstore pulls tuf, and tuf pulls securesystemslib. A resolve from
  scratch would have skipped a yanked release, but the version was already
  written down, so every `uv lock` re-pinned it and said so in a warning. The
  pin moves to 1.5.1, the release that restores the compatibility, and no
  constraint is left behind to remove later.

### Security

- **`--configure` no longer writes the configuration world-readable before
  narrowing it.** The file it saves may hold a release token, a service token
  or a webhook URL with a credential in it - the wizard says so - and it was
  written with `write_text` and only then `chmod`ed to `0600`. On a monitoring
  host with more than one account, any local user could read the token in the
  window between the two, and a descriptor opened in that window stays
  readable after the `chmod`.

  The window was not the whole of it. Where the destination **already existed**
  at `0644` - an earlier run, an editor, `touch` - the write went through that
  same inode, so the token sat world-readable for the entire write rather than
  for an instant. Re-running `--configure` to *rotate* a token is exactly that
  path.

  The configuration is now written to a `mkstemp` file, which is owner-only
  from the moment it exists, and moved into place. The secret is therefore
  never on disk under a wider mode, and the move being atomic means a save
  that fails leaves the previous configuration intact instead of a truncated
  one. This is the rule `docker/setup-wizard.py` already held its `.env` to and
  `baseline.py` already held its state file to; the plugin's own wizard was the
  one place that did not.

## [1.20.0] - 2026-09-04

### Added

- **`cert_days_left`: the certificate's remaining life is now a metric, not
  only a finding.** The scan has always measured it and the rating has always
  judged it, but the number reached an operator only as `tlsCertificate` - a
  state, on the day the margin had already run out. A monitoring system wants
  the number *before* that day, to graph and to alert on, which is exactly
  what `support_days_left` already does for the release line beside it.

  It carries the scan's own thresholds rather than a second opinion invented
  for the graph: warning at or below `scanner.tls_min_days`, the margin the
  finding itself fires at, and critical once the certificate has expired. Both
  are open at the bottom (`@~:30`), and the value keeps counting past zero
  into negative days, because "expired nine days ago" is the reading somebody
  needs to see.

  **An unmeasured certificate is absent rather than zero.** A scan over plain
  HTTP, a host that refused the handshake and a certificate whose dates would
  not parse all measured nothing, and reporting nothing as `0` would page
  somebody about an expiry that was never observed.

- **The webhook can post to ntfy and Gotify directly**, with
  `--webhook-format ntfy` and `--webhook-format gotify`. Both were previously
  a shell wrapper around `curl` - the one in
  [Webhook recipes](docs/webhook-recipes.md) is still there for anyone who
  wants the plugin's full text or a priority scheme of their own. Priorities
  follow the state, matching what that wrapper did: CRITICAL arrives at ntfy's
  `urgent` and Gotify's 8, WARNING at `default` and 5, UNKNOWN at `high` and
  5. An OK - which only `--webhook-on always` ever sends - arrives at the
  quietest value each service has, so a dead man's switch does not buzz
  somebody nightly to say nothing is wrong.

  `--webhook-digest` renders too, rather than falling back to the flat
  document neither service can read. Same selection as the chat digests: only
  the hosts that are not OK, capped, with the healthy ones counted.

  **With `ntfy`, point `--webhook-url` at the topic URL.** ntfy reads a JSON
  publication only at its server root, taking the topic from the document
  rather than the path, so the plugin reads the topic off the configured URL
  and posts to the root of that same server. Scheme, host and port are
  untouched, so the address the SSRF guard checked is the address posted to. A
  URL naming no topic is refused when the check starts, rather than answering
  400 on every notification for the life of the configuration. See
  [ADR 0040](adr/0040-a-push-format-may-rewrite-the-path-never-the-host.md).

  There is still no `matrix` format, for the reason there was not one before:
  matrix-hookshot's outbound webhook connector accepts the `slack` shape, and
  a second name for the same document would only suggest they differ.

- **The plugin installs with Homebrew**, as
  `brew install sowoi/tap/check-opencloud-security`. This is the workstation
  half of the argument the `.deb` and the `.rpm` make for monitoring hosts: on
  macOS and on the Linux laptops that use it, `brew` is the package database,
  and a `pip install --user` is absent from it, invisible to `brew outdated`
  and unanswerable to whoever inherits the machine.

  The formula is generated by `scripts/build_homebrew_formula.py` from what
  PyPI published, so every URL and `sha256` in it names an artifact the index
  already serves. It therefore describes a *released* version and defaults to
  the newest one published rather than the one in `pyproject.toml` - a formula
  for a version that has not gone out yet would pin a URL answering 404.
  `--check` asks only whether a release was missed, deliberately not whether a
  regeneration would reproduce the file byte for byte: that second question
  answers no whenever an unrelated dependency publishes.

  It lives in a tap rather than in Homebrew core, which has notability
  requirements this project does not claim to meet. Nothing here pushes to
  that tap; a release workflow writing to a second repository is a decision
  about credentials rather than about packaging.

  **`--upgrade-self` refuses on a Homebrew installation** and names
  `brew upgrade`, exactly as it already does for `apt` and `dnf`. The failure
  it avoids is quieter than the distribution one: Homebrew's formula is a
  virtualenv under the Cellar, so pip finds it writable and appears to
  succeed - and the next `brew` operation relinks the Cellar and puts the old
  version back, leaving no record that pip was ever there.

- **The collaboration backend beside an instance is now looked at, not just
  counted.** The scanner has always reported *that* an office integration
  exists, because the instance names its own app providers. It never asked
  what that second service publishes - and a document editor is a second HTTP
  server, with an administration console listing every open document session
  and a transport of its own. Where a reverse proxy serves that backend on the
  instance's own origin, two findings now follow: `companionAdminConsole`
  (high) when the editor's console answers from the internet, and
  `companionEditorHttps` (high) when the WOPI discovery document advertises
  editor addresses over plain HTTP, which sends the document and the token
  authorising the session unencrypted.

  The backend is detected by the `wopi-discovery` root element the WOPI
  protocol specifies rather than by a status code, because OpenCloud answers
  unknown paths with its own HTML shell and a check that trusted the code
  would find an editor on every instance in existence.

  **The scan asks the origin it was pointed at and nothing else.** It
  deliberately does not follow the editor host named inside the discovery
  document: that would let a scanned instance choose the next address the
  scanner connects to, walking straight past the SSRF pinning the public
  service depends on. A deployment serving its editor from a host of its own
  therefore gets neither finding rather than a pass, because nothing was
  measured - point a second scan at that host. See
  [ADR 0036](adr/0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md).

- **`tlsDnssec`: whether the zone answering for this name is signed.**
  Everything else the scan concludes about the transport starts from an
  address a resolver handed over. In an unsigned zone that answer carries no
  signature, so one forged on the way to the resolver cannot be told apart
  from the real one - and the CAA record restricting who may issue a
  certificate for the name arrives over the same channel and can be forged
  along with the address it protects.

  The check queries the resolver this machine already uses, read from
  `/etc/resolv.conf` and never a public one, for the same reason the CAA
  lookup does: asking 1.1.1.1 would hand a third party the hostname being
  scanned. It is a low finding, and a zone that is signed but read through a
  non-validating resolver passes - whether the operator signed their zone is
  the part this scan is entitled to judge.

  **A resolver that does not speak DNSSEC leaves the finding out of the result
  entirely**, rather than reporting the zone as unsigned. The two produce
  identical silence, and treating the second as the first would fail every
  scan run from behind such a resolver for a reason that has nothing to do
  with the instance being scanned. See
  [ADR 0038](adr/0038-a-dnssec-answer-nobody-could-have-given-is-not-a-finding.md).

- **`hstsPreloadEligible`: whether the `preload` directive would actually be
  honoured**, under `setup.advisoryChecks`. `hstsPreload` reports whether the
  header *asks* to be preloaded, which is an intention rather than a state - a
  host is protected before its first request only if it is really in the
  browser preload list, and the list only accepts a header carrying a max-age
  of at least a year, `includeSubDomains` and `preload` together.

  OpenCloud's own proxy sends ten years and `preload` but no
  `includeSubDomains`, so the header on every stock instance asks for
  something the list refuses. That makes the shortfall a fact about OpenCloud
  rather than about any one deployment, which is why it is an advisory
  observation - measured, explained by `--debug` and catalogued, never
  counted, never alerted on and never offered as a waiver.

  Membership of the list itself is deliberately not measured: the only ways to
  know are to ask a third party, which would leak the scanned hostname, or to
  ship tens of megabytes of the list in a plugin meant to stay small on a
  monitoring host. See
  [ADR 0037](adr/0037-preload-eligibility-is-measured-list-membership-is-not.md).

- **The plugin now ships as a `.deb` and an `.rpm`, built from the same wheel
  and attached to every release.** Its audience is monitoring hosts, and on
  those `apt install` and `dnf install` are how software arrives - a pip
  install has no entry in the package database, so it is absent from the
  inventory, missed by the unattended-upgrade job that patches everything else
  and unanswerable to whoever inherits the host. Both packages are
  architecture-independent, so one file fits every release of a distribution.

  The check lands on `PATH` and in the monitoring plugin directory
  (`/usr/lib/nagios/plugins` on Debian, `/usr/lib64/...` on RPM systems), so an
  Icinga2 `CheckCommand` built on `PluginDir` needs no path configuration.

  **The package configures nothing and enables nothing.** It creates
  `/etc/check-opencloud-security/` and leaves it empty, and the example
  configuration ships as documentation: that example names a host that is not
  yours, and the path it would occupy is one the plugin genuinely reads, so
  installing it would give every invocation on that host a default target
  nobody chose. The four systemd units install disabled for the same reason.

  The payload is the wheel unpacked into one private directory rather than
  files in the system's `site-packages`, which cannot then collide with a pip
  install of the same name on the same host. The two commands are small
  launchers that find a Python 3.10 or newer for themselves - RHEL 9 answers
  3.9 to `python3` and carries 3.11 and 3.12 beside it under their own names -
  and exit **3 (UNKNOWN)** rather than a verdict when none is usable, because
  a check that could not run has measured nothing.

  `--upgrade-self` now refuses on such an installation and names `apt` or
  `dnf`. That is not politeness: pip would appear to succeed, installing into
  a `site-packages` the launcher never reads, leaving two versions on the host
  and the old one still running. See
  [ADR 0039](adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md)
  and [Installing the plugin](docs/installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm).

### Changed

- The DNS wire format the CAA lookup speaks now lives in
  `opencloud_local_scan/dns.py`, where the DNSSEC lookup shares it rather than
  carrying a second copy of it. `caa.py` keeps its behaviour, its identifier
  and its refusal to query any resolver the operator did not already choose.

### Fixed

- **An advisory patched on two release lines is now matched on both of them,
  whichever format it arrives in.** The GitHub Advisory API writes one
  `vulnerabilities` entry per affected range, so an issue fixed in *both*
  `4.0.3` and `5.0.2` arrives as two entries for the same package. The
  converter stopped at the first one, which cleared every instance on the other
  line: a `5.0.1` server was told no advisory matched it, and the instances
  that *were* flagged were pointed at the fix for a line they are not on. Every
  bounded range is now kept, exactly as the OSV converter beside it already
  did, and `for_version` reports the fix belonging to the installed line. The
  bundled database is generated from OSV and is unaffected; this is the path an
  operator takes with `--vulnerability-db` or `--vulnerability-feed` pointed at
  a GitHub-format document.

- **An advisory whose lower bound is exclusive no longer reports the one release
  it excludes.** `>= 7.0.0` and `> 7.0.0` were read alike, so an advisory that
  went out of its way to say `7.0.0` is not affected produced a finding on
  exactly that release - one no upgrade can clear, because the installed
  version is already the one the advisory considers safe. The bound now moves
  just past the named release, the way an inclusive upper bound already moved
  just past its own.

- **An upgrade recommendation cannot point backwards.** A release line the
  schedule has no record of - dropped from the lifecycle page as it aged, or
  never published there - is judged end of life, and the release to move to was
  read off the declared track alone. The newest release recorded for a track can
  be *older* than a version that is not in the schedule at all, so an LTS
  instance on `5.0.0` was told to "upgrade" to `4.0.8`: advice that removes
  fixes rather than adding them. The verdict now names the newest release that
  is genuinely ahead of the installed one, and no arrow at all when there is
  none. Where the arrow already pointed forwards nothing changes.

- **A `q=nan` in `Accept-Language` no longer decides which language a page is
  written in.** It parses as a float and then compares false against every
  other weight, so the sort that orders a browser's language list - and with it
  the language served - followed whichever comparisons Python happened to make
  rather than the header. A weight that is not a weight is now dropped like an
  unparsable one, while a client that overshoots the range with `q=1.5` is
  still understood as meaning "this one first".

- **A `--webhook-url` the plugin cannot parse is refused instead of raising.**
  An unclosed IPv6 literal is a URL `urlsplit` rejects, and the rejection
  happened inside the log call that was explaining why the webhook had been
  blocked - so a typo in the flag replaced the check's own result with a
  traceback, which for a monitoring plugin is the one output that says nothing.
  Redaction now answers `<redacted>` for a URL it cannot read, the delivery
  fails as a delivery failure, and the scan result is still reported.

## [1.19.0] - 2026-09-03

### Added

- **An optional operator's area at `/admin`, off unless a deployment asks for
  it.** It refreshes the release schedule and the advisory database on a
  press, follows the audit trail as it is written, and shows what the service
  is doing: the worker and its queue depth, every configured limit, when each
  piece of reference data was last updated, and whether the shipped search
  index still describes this build.

  It authenticates nobody. An authentik proxy provider stands in front of it
  and forwards the identity it established, and this service believes those
  headers only because the outpost adds a shared secret alongside them,
  compared in constant time - the same shape `/mcp` already uses. Three
  refusals hold it together: a deployment that enables the area without
  `COS_WEB_ADMIN_PROXY_SECRET` does not start, one whose
  `COS_WEB_ADMIN_USERS` names nobody does not start, and every failure to
  authorise answers **404** rather than 401, because whoever is asking
  without the secret is finding out whether the area exists. With the area
  off the routes are never registered, so the path is as absent as any other
  unknown one.

  Nothing about an operator is stored - the identity names the actor in an
  audit record and is then gone. The readings are counts and settings only:
  no address anybody scanned reaches them. The audit view starts at the end
  of the trail rather than replaying what was retained, and a client in it is
  a truncated HMAC under a salt this process holds, which nothing here can
  resolve. The page is `noindex, nofollow, noarchive` and deliberately absent
  from `robots.txt`, where a `Disallow` line would advertise it, and it is
  not linked from the documentation.

  `docker/setup-wizard.py` asks whether to serve it - answering no by
  default - and configures the authentik user who may use it.

  **The area says what it does not know.** Its readings are polled, and a
  poll that stops answering used to look exactly like a service with nothing
  happening on it: the numbers simply stopped moving. So the age of the last
  answer is on the page and counts up between polls, a reading older than a
  few of them says the service has not answered and that what is on screen
  is the last thing it said, a tile lights when its value moves, and the
  band's dot pulses while a fetch is actually in flight. The audit view now
  reads the account of the connection the server was already sending: the
  stream ending at its half-hour cap and a deployment that keeps no trail at
  all are each said in a sentence, instead of arriving as the silence a
  dropped connection produces - and a capped stream is let go rather than
  reopened, which the browser would otherwise do for ever. Where the records
  come from a ring in one process's memory rather than a file, the page says
  so, because behind more than one replica that is a part of the trail and
  not all of it. And the page stops polling while nobody is looking at it: a
  tab left open overnight was asking for the state every ten seconds until
  morning.

  The search-index card answers with three verdicts rather than two, and its
  sentence can account for all of them. An index that does not say which
  release it was built for reads *Cannot tell* rather than *Current*: its
  pages and its languages were compared, its copy could not be, and only the
  stamp says what the copy was extracted from. A page the index holds that
  this build no longer serves is named under the verdict instead of leaving
  "out of date" standing over "every page and language is indexed" - two
  lines written in two places, one of which was being read with no way to
  tell which.

  **Three controls that change nothing were added, and one that reaches
  upstream.** The readings can be re-read on demand and copied as the
  service's own JSON for an issue report, the audit list on screen can be
  emptied, and *Test the sources* runs both refreshes as a dry run: the same
  fetch, the same guards, and then the answer is thrown away. It exists
  because a refresh reporting `failed` and one reporting `rejected` both
  leave the data exactly as it was, and only one of them is a network to go
  and look at. It reaches somebody else's server, so it is held back by
  `COS_WEB_ADMIN_REFRESH_COOLDOWN` like the buttons that apply what they
  fetch - under a key of its own, so it is available in the moment after a
  refresh has failed, which is the only moment anybody wants it.

  **The reference data ages the way the poll does.** The two tiles printed
  the stamp they had - `checked 2026-09-02 04:17`, flat grey - so a daily
  refresh that had been failing for a week looked exactly like one that ran
  this morning, and the reader had to notice the date and subtract. They now
  say how long ago, keep the exact moment on a `<time>` where whoever wants
  it can get at it, and turn the accent past two daily cycles: one missed run
  is a source having a bad morning, two is a pattern, and by then the
  schedule and the advisory database are deciding what visitors are told from
  a picture of the world nobody has checked since the day before yesterday.

  And the note says *which* failure has been stopping it. Both refreshes
  leave their data exactly as it was whenever they do not succeed, so the
  checked stamp cannot distinguish a source nobody can reach from a document
  these guards are right to refuse - the difference `ADMIN.md` calls the
  interesting one, and the only way to see it was to press *Test the
  sources*, which fetches from somebody else's server to answer a question
  the last refresh already knew the answer to. Every attempt now records what
  it made of the source, beside the stamp rather than instead of it, and the
  tile reads *the last attempt could not be fetched* or *was refused by the
  guards*. A refresh that was never run records nothing, and a deployment
  that turned the refresh off is not reported as overdue.

  **"Redis is gone" and "the worker died" are no longer the same picture.**
  The heartbeat the worker tile reads is a key in the store, so a store that
  is unreachable took the answer with it - and the tile said *Not answering*
  either way, which is an area that sends an operator to restart a container
  that may be perfectly healthy. It is the failure they are most likely to be
  reading the page during. The tile now has a third answer, *Cannot tell*,
  the state document reports `store.reachable` beside a worker liveness that
  is `null` rather than `false` when nothing was learned, and `ADMIN.md`'s
  troubleshooting table no longer has to draw the distinction in prose that
  the page can draw itself.

  **It says what this deployment is exposing.** The state document already
  carried it - `/mcp` and whether a token is required, `/docs`, indexing,
  private-network targets, encryption at rest, and what the audit trail keeps
  and where - and the page showed none of it, so the question an operator
  opens this area with could only be answered by reading the compose file. A
  card of on/off pills now answers it, from the same two functions that
  answer `/admin/state`, so the card and the diagnostics an operator copies
  cannot disagree. They are settings rather than readings: the card is
  rendered by the server, needs no scripting, and is never repolled, because
  a value that changed did so in a process the open page is no longer talking
  to. Two combinations carry the marked accent and only two - an agent
  endpoint with no sign-in on it, and private-network targets on a deployment
  that asks to be indexed, which is a scanner strangers can find pointed at
  the network it stands in. Neither is refused: each is the right setting for
  some deployment, and the area's job is to say which one this is.

  **And a way out of it.** The band said who was signed in and offered no way
  to stop being, which for a console left open on a shared screen is the one
  control it was missing. This service has no session to end, so it cannot
  invent one: `COS_WEB_ADMIN_SIGN_OUT_URL` names the exit of the provider
  that did the signing in - `/outpost.goauthentik.io/sign_out` for the
  bundled stack, which the wizard now writes - and the link appears only
  where a deployment named one, because a *Sign out* that leaves somebody
  signed in is worse than no control at all. Only a local path or an
  `http(s)` URL is accepted and startup refuses anything else: the value is
  rendered into an `href` on a page whose content policy exists to keep
  script off it, and `javascript:` in a link is script by another name.

- **A report prints as a document.** It gets printed for a change record and
  saved to PDF for somebody who was not at the screen, and until now that
  sheet carried the aurora, a menu, a scheme switch and a row of export
  buttons nobody can press. Print now forces the tokens back to daylight -
  which is a correctness fix, not a preference: the dark scheme's ink is
  near-white, so a reader who chose dark and pressed print was handed a blank
  page - drops the chrome and the controls, keeps the grade, the facts, the
  findings, the plan and the trademark notice every standing surface carries,
  stops a finding being split across a fold, and prints the address behind
  each documentation and advisory reference, which on paper is the only way a
  link says anything. No second template and no new markup beyond a marker on
  the two cards that are entirely controls.

- **A new check, `forwardedHostIgnored`: whether the instance lets the caller
  decide what its own address is.** Every other check reads what an instance
  volunteers. This one asks a question it cannot answer by accident - it
  requests `/.well-known/openid-configuration` twice claiming to have arrived
  at a host that does not exist, once as the request's own `Host` and once as
  `X-Forwarded-Host` - and looks for that host coming back. An instance that
  was never told its public address derives one from each request, and the
  discovery document is where that costs something: the `issuer` and the
  endpoints are where a client sends the next sign-in, so whoever picks the
  host has picked where an authentication request goes. It is `medium`
  because on its own it misleads only whoever sent the header; behind a cache
  it becomes the answer everybody gets, and behind a proxy that forwards a
  client's own `X-Forwarded-Host` it is a stranger who chooses. The fix is
  `OC_URL` plus a forwarded header set from the proxy's own configuration
  rather than passed through, and `docs/reverse-proxy.md` now says so beside
  the `X-Forwarded-For` advice it already gave.

  **Only a URL a client would be *sent* to counts**, which is the whole
  design: the redirect target, or one of five named fields of the document,
  compared as the host of a parsed URL. A default virtual host refusing a
  name it does not recognise usually prints that name in its error page, and
  a check that searched the body would report correct behaviour as the
  finding. An instance publishing no discovery document is not judged either
  way - two errors are the scan learning nothing, not a pass - and the two
  probes share the batch that already ran the CORS and TRACE questions, so
  the scan gains two requests and no round of waiting.

- **A test that fails when a setting is only added in some of the places a
  setting lives.** Adding one tunable touches the settings dataclass,
  `factory.py`, the example configuration file and the flag that overrides
  it, and missing one of those fails silently in both directions: a field
  nothing builds keeps its default for ever and reads as a setting that does
  not work, and a key the example file documents that nothing reads is advice
  an operator follows and then wonders about. Neither shows up in a test of
  the scanner, which is perfectly happy either way.
  `tests/test_settings_completeness.py` derives all three lists instead of
  keeping one - the dataclass fields, the configuration names the code parses
  out to read, and every key the example file documents including the
  commented-out ones - and checks them against each other in both directions. The five
  fields that are genuinely not settings are named with the reason each one
  is set in this process rather than by anybody's configuration, and a second
  test makes that list shrink again when a field stops belonging on it.

### Documentation

- **`README.md` describes the GitHub Action.** `action.yml` has existed since
  1.16.0 and the README never mentioned it: the only `uses:` line in the
  project was in [`docs/ci.md`](docs/ci.md), which is one link away from the
  file people open first and, more to the point, is not the page GitHub
  renders for a Marketplace listing - that is `README.md` on the default
  branch. The new section is the whole step in one workflow, both tables
  (thirteen inputs, six outputs), why the tag has to be pinned - the release
  schedule and the newest known OpenCloud version ship inside the package, so
  which version runs is part of the verdict - and what `fail-on` decides.
  `docs/ci.md` keeps everything that is longer than a paragraph: SARIF into
  the code-scanning dashboard, reporting without failing the job, GitLab CI.

- **`README.md` is half its length, and the material it lost is now findable.**
  It had reached 2,348 lines, which meant the file people open first answered
  every question at the same volume: how to install the plugin, what each
  hardening identifier means, which OpenCloud service listens on port 9134 and
  how to write an Icinga2 `CheckCommand` all stood in one column with nothing
  to skip. Eight sections that had become reference works of their own now
  have pages of their own - [Installing the plugin](docs/installation.md),
  [What the scanner reads, and what it deliberately does
  not](docs/scanner-checks.md), [Release tracks, end of life and the update
  recommendation](docs/release-lifecycle.md), [Hardening measures, one by
  one](docs/hardening.md), [Secrets in the configuration](docs/configuration.md),
  [Reporting only what changed](docs/baseline.md), [Running the scanner as a
  service](docs/scan-service.md) and [Worked examples](docs/examples.md) - and
  the example webhook payload and the Uptime Kuma walk-through joined [the
  webhook recipes](docs/webhook-recipes.md), where every other receiver
  already was.

  What stayed behind is a summary and a link rather than a stub: the README
  still says what the scanner reads, what a waiver does, how a track is
  declared and what the service refuses to do without a token - it just stops
  before the tables. Nothing was deleted, every paragraph is either still in
  `README.md` or on one of those pages, and the anchors other documents
  reached them by were followed to their new homes rather than left dangling.
  The eight pages are in the `docs/README.md` index and in
  `webapp/documentation.py`, so each is a page under `/documentation` and a
  row in the search index - which is where somebody looking for "shell
  completion" or "demo users" actually starts.

### Removed

- **Two encryption helpers nothing called.** `encrypt_result_dict` and
  `decrypt_result_dict` read like the path a scan record takes to Redis, and
  no caller has ever existed: `webapp/store.py` uses `encrypt_value` and
  `decrypt_value` directly. Thirty lines of untested code around key material
  that a reader had every reason to believe was load-bearing, and which any
  future change would have had to keep working for nobody. Deleting them is
  the whole change - the encryption an operator turns on is exactly what it
  was, and `tests/test_webapp_encryption.py` still describes it.

### Fixed

- **A server still offering TLS 1.0 is now caught by a scan of one, not by an
  inspection written out by hand.** How the rating treats a populated
  `deprecated_accepted` was covered; whether the probe can populate it was
  not. `_accepts` - the function that decides whether the server said yes -
  had never once returned `True` in this suite, so a bug in it would have
  cleared every server on the internet with every test still passing. The
  check now stands up a loopback server pinned to those versions and reads the
  finding back off a real handshake. Because Python's default client starts at
  TLS 1.2 and will not speak to such a server at all, this is also the first
  test to exercise the fallback handshake that reaches one; and because a
  server offering a single version answers every other question with a
  refusal, one case offers both, which is the only way the probe is ever told
  yes. A build of OpenSSL that will not serve them skips rather than fails.

- **The two Redis backends are held to the same contract.** The suite runs
  against `memory://`, the in-process stand-in, because a test that needs a
  server is a test a contributor cannot run - which left the `redis.asyncio`
  client every deployment actually uses executing nowhere, and nothing at all
  checking that the two agree. That is a test double free to drift away from
  the thing it stands in for: `SET NX` reporting whether it stored, `TTL`
  answering -2 for a key that is gone and -1 for one that never expires,
  `LPOS` counting from zero, `LREM` returning how many it removed, `INCR`
  leaving an existing expiry alone. Any of those diverging passes the whole
  suite and then loses a scan, or serves one that should have expired, on a
  real server. `tests/test_redis_contract.py` asks both backends the same
  questions, and CI now starts a Redis service for the half that needs one;
  without `TEST_REDIS_URL` that half skips, so nothing new is needed to run
  the suite locally. Every call runs on one event loop rather than a fresh one
  per call: a `redis.asyncio` pool binds its sockets to the loop that opened
  them, so a per-call `asyncio.run` - which the in-process backend never
  notices - leaves the real client's second command reaching for a connection
  attached to a loop that is already closed, exactly as a deployment would
  never do. The queue is covered the same way - `memory://` must keep
  selecting the queue that runs nothing, a real URL must produce an ARQ queue
  a job actually reaches, and the URL a deployment configures must survive the
  translation into ARQ's own connection settings. That job is read back with
  ARQ's own reader, because ARQ's queue is a sorted set of job ids rather than
  the list the store's own queue is, and it goes onto a queue name this run
  invented so that a worker watching a shared server cannot take it.

- **Coverage was blind to both entry points, and had been all along.** The
  plugin and the scanner CLI are tested the way a monitoring system runs
  them - as a subprocess with a deliberately scrubbed environment - and
  nothing that happened inside one was ever measured. The plugin reported 78%
  however thorough the suite got; it is really at
  92%, and the entire SARIF, JUnit, Prometheus and multi-host surface was
  being counted as untested while `test_output_formats.py` exercised every
  line of it.

  That is worse than an inaccurate number. For the largest file in the
  project, a branch nobody had tested and a branch covered only by a
  subprocess looked exactly alike, so the floor could not tell them apart -
  which is the one distinction it exists to draw. It was met by the library
  while the plugin contributed noise.

  `coverage` already starts itself in any process where
  `COVERAGE_PROCESS_START` is set, so the fix is to let that variable and an
  absolute `COVERAGE_FILE` survive the scrub, and to run in parallel mode so
  each process writes its own data file. `tests/conftest.coverage_environment`
  hands them over and returns nothing at all unless this process is genuinely
  measuring, so a plain `pytest` run still spawns the same clean environment
  and leaves no data files behind. Two settings had to stop being paths
  relative to a working directory the subprocess does not share: the plugin is
  named as a module rather than a file, and `wizard.py` is omitted by a
  wildcard, or it reappears at 29% once the subprocess runs are combined in.
  The floor moves 85 → 87 against a real 89%.

- **A test compared a countdown against itself and failed once a run crossed a
  second.** `expiresIn` is the scan key's remaining TTL, read at the moment
  each request is served, so the three answers
  `test_a_result_page_negotiates_the_same_scan_record_as_the_api` collects -
  the API record, the page negotiated with `Accept`, and the same page asked
  with `output_format=json` - are entitled to differ by a second, and on one
  Python 3.13 nox run they did: `3600` against `3599`. The test now compares
  the record without that field and asserts the countdown separately, as a
  retention window present in all three answers rather than an integer that
  must match. Nothing about the service changed: a live TTL is what the field
  is for, and the ten fields that actually make up the record are still
  compared whole.

### Security

- **The CAA lookup accepts an answer only from the resolver it asked.** The
  query went out from an unconnected UDP socket and the reply was read with
  `recvfrom`, so the kernel handed over a datagram from *any* address: a
  forged answer had only to reach the ephemeral port before the resolver's and
  carry the matching request id, rather than also come from the resolver.
  Anybody able to send UDP to the scanning host could therefore decide the
  `tlsCaaRecord` finding - assert a restriction on an instance that has none,
  or hide one that exists. The socket is now connected before the query is
  sent, which is what every resolver library does and what makes the request
  id a second check rather than the only one. The reach was one informational
  finding: nothing else reads the answer, and neither the rating nor any other
  check moves with it.

- **A token naming a signing key nobody published can no longer order a key
  fetch per request.** Only deployments with `COS_WEB_MCP_AUTH_ENABLED` were
  affected. A bearer token is checked against the provider's published keys,
  looked up by the `kid` in its header, and the client refetches the key set
  whenever that name is not in the set - which is how a rotated key works
  without a restart. Nothing bounded how often an unknown name could provoke
  that. A `kid` needs no signature that verifies, no audience and no issuer,
  and is read before any of them are checked, so an unauthenticated caller
  could turn each of its requests into one outbound request to the operator's
  identity provider, each blocking the event loop while it ran. A miss may now
  provoke a fetch at most once a minute, and verification runs off the event
  loop. No token was ever accepted that should not have been: the key name only
  selects which published key the signature is checked against.

- **The operator area's sign-out address is held to the same shape as every
  other local path.** `COS_WEB_ADMIN_SIGN_OUT_URL` is rendered into an `href`
  and checked at startup so it cannot be a scheme this page's content policy
  exists to forbid. Anything starting with a single `/` counted as local - but
  a backslash is a slash to a browser, so `/\host` resolves exactly as
  `//host` does, off-site, while being spelled like a path. It is now held to
  the character class `webapp.i18n.safe_next_path` holds the language switch
  to, which has no backslash in it. Never released: the area, the setting and
  the check were all written in this cycle.

## [1.18.2] - 2026-09-01

### Added

- **The severity counters on a report are the filter for its findings.**
  Pressing `Critical`, `Warning` or `Info` narrows the list below to that
  severity, pressing it again gives the whole list back, and a sentence
  beside the heading says which filter is on with a way out of it. The
  counters already counted exactly those entries, so the shortest way to ask
  "show me only those" is the number itself. A counter standing at zero is
  disabled - there is nothing behind it - and the advisories and passed
  counts stay readings, because neither has a list on this page to narrow.
  Nothing is fetched and no count is ever rewritten: every entry is already
  on the page tagged with the severity the server gave it, so the filter only
  sets `hidden`. Without scripting the counters are five readings, which is
  what they were.
- **A switch between the light and dark themes, in the header.** The
  operating system still decides on a first visit and on every visit after
  it; only pressing the switch writes anything down, and it is remembered in
  that browser alone. `theme.js` applies a stored choice before the first
  paint - the one script on the site that is not deferred - so an override
  never opens with a flash of the other scheme, and the `theme-color` meta
  tags are re-pointed so the browser's own chrome does not frame a dark page
  in a light bar. Which icon the button shows is decided in CSS from the same
  two questions the colour tokens ask, so it is never briefly wrong, and the
  control is hidden until scripting marks the document rather than being
  offered to a reader who cannot use it.
- **The waiver picker can be searched.** The catalogue lists every check the
  scanner runs, which is thorough and, past a screenful, hard to read;
  somebody who came to waive one identifier can now type it instead of
  hunting for it. Matching is against the identifier and the title the server
  already wrote into each row, a group whose entries have all gone is hidden
  with them, and a box that was typed in and emptied leaves the list exactly
  as it found it - including anything already ticked, because filtering only
  ever sets `hidden`. The field is revealed by its script, so a reader
  without one gets the full list rather than a search box that does nothing.
- **An address that will not do says so before the form is submitted.** The
  sentence under the field appears on `:user-invalid` - once the visitor has
  typed and left, never while they are still typing - so the red bar stops
  being a colour that carries a meaning nothing spells out. It is CSS that
  reveals it, so a browser without scripting corrects a typo just as readily.

### Changed

- **The progress card says how long the wait has run, and how long it usually
  takes.** The estimate is the server's sentence and is there without
  scripting; the clock beside it is measured against a wall-clock instant
  rather than counted up, so a laptop that sleeps wakes with the right answer
  instead of a tally of missed ticks. It starts when the page did, which is
  the wait the reader is actually sitting through, and it is `aria-live="off"`
  inside a card that is otherwise polite - a reading that changed every second
  would be announced every second, which is the difference between telling
  somebody where they are and talking over them.

### Documentation

- **`ADMIN.md` collects the operational knowledge a system administrator
  needs and a developer document never states.** How to refresh the
  vulnerability database and the release schedule by hand and what the
  guards refuse; how a monitoring host pulls the reviewed, attested data with
  `check-opencloud-scanner refresh-data` and which configuration keys make it
  count; how to regenerate `/documentation`, the search index and the web
  bundle; how to raise a disposable local stack from the working tree with
  `docker/setup-wizard.py` to look at the frontend in a browser, why
  `--preset private` is the one that lets a scan of a local instance complete
  at all, and the bind mount that turns a CSS change into a page reload
  rather than an image rebuild; what the daily runtime refresh keeps in Redis
  and how `/healthz`
  shows whether it happened; every logger name and log marker worth grepping
  for, and what the logs deliberately never contain; what to do when
  OpenCloud moves a documented link, including why a status code alone is not
  enough for a single-page documentation site. It stays internal: it is
  absent from the wheel, the sdist, the web bundle, `webapp/documentation.py`
  and `webapp/search.py`, so nothing publishes it.

### Fixed

- **The reference-data test fixture no longer leaves its own request body
  unread.** `fetch_records` POSTs a small JSON query; the fake HTTP server in
  `tests/test_reference_data_limits.py` answered without ever reading that
  body off the socket, then closed the connection (it runs HTTP/1.0, so it
  closes after every request). Closing a socket with an unread request body
  still sitting in the kernel's receive buffer makes it send a reset instead
  of a clean close, and that reset could land on the client mid-read of the
  *response* - intermittently surfacing as a `ConnectionResetError` in
  `test_an_oversized_advisory_answer_is_refused_before_it_is_parsed` instead
  of the `AdvisoryFetchError` the test asserts on, regardless of how large the
  response body was. Only the advisory test could ever hit this: the
  schedule/lifecycle fetch this fixture also serves is a plain GET with no
  request body to leave unread. The handler now drains `Content-Length` bytes
  of the request before replying.

- **The self-hosting note under a rescan lost its breathing room when the
  rescan card merged into the report's head.** `section-gap` moved from the
  self-host paragraph onto the rescan status line above it instead of
  staying on both, so the two unrelated sentences - "ready to scan again" and
  "you can self-host this" - sat almost flush against each other (.4rem
  apart instead of the 1.25rem every other section boundary on the page
  uses). `frontend/templates/scan.html` now keeps `section-gap` on the
  self-host paragraph as well.

## [1.18.1] - 2026-08-31

### Changed

- The rescan button sits next to "scan another instance" in the report's
  head, rather than in a card of its own further down the page - the two
  actions a reader reaches for once a result is in, grouped together.
- The documentation and advisory links inside a finding's fix line now read
  as a small chip, in the same shape as the severity and category tags above
  them, instead of as a sentence of body text that happened to be blue.
  Shared by `scan.html` and `catalogue.html`, so both pages pick it up.

### Fixed

- **`tests/test_data_signing.py`'s tests against a real Sigstore bundle now
  actually run in CI.** `sigstore` is an optional extra kept out of the
  `test` dependency group on purpose, so the two tests that exercise
  `_verify_one_bundle` - a malformed bundle skipped in favour of the next,
  and a readable bundle that fails the identity pin raising
  `SignatureInvalid` - marked themselves `@needs_sigstore` and quietly
  skipped whenever it was missing. No workflow ever installed both the
  `test` group and the `signing` extra together: `run-tests.yml` synced only
  `--group test`, and `supply-chain.yml` installed `--all-extras` but never
  ran pytest. The verification logic that decides whether a fetched
  vulnerability database or release schedule really carries this project's
  own attestation had therefore never executed in automation, only ever on a
  developer's own machine with `sigstore` installed by hand.
  `run-tests.yml` now syncs and runs with `--extra signing` alongside
  `--group test`, so both tests run on every push and pull request.

- **A flaky advisory-feed test no longer races a real socket close against a
  megabyte of unread data.** `read_capped` reads at most `MAX_DOCUMENT_BYTES
  + 1` bytes and the response is closed right after; the test built a body
  roughly twice that size to prove the size guard fires before the
  `MAX_ADVISORIES` count guard even gets a chance to. Closing a socket with
  over a megabyte still incoming makes the kernel send a reset instead of a
  clean close, which occasionally raced the fake server's single write and
  surfaced as a `ConnectionResetError` where the test expected the guard's
  own `AdvisoryFetchError`. The body is now padded to just past the cap, the
  same way the sibling schedule-page test already did, leaving nothing sized
  enough to race over.

## [1.18.0] - 2026-08-31

### Added

- **`check-opencloud-scanner explain` looks a finding up without scanning
  anything.** A monitoring system prints `cspWithoutUnsafeInline` and stops
  there. Until now the three ways to find out what that meant were to run a
  scan that fails the same check, open the web application, or read
  `hardening.py` - none of which is available to the person the alert woke up.

  `explain <id>` prints the same paragraph `--debug` and the web catalogue
  print, from the same catalogue, and it reads nothing else: no configuration
  file, no network, no instance. It takes header names (`Referrer-Policy`) and
  per-path findings (`exposed:/config/opencloud.yaml`, which resolves to the
  family the catalogue actually lists) as readily as hardening flags, so
  whatever the alert said can be pasted in as it stands. With no identifier it
  prints the whole catalogue; `--category transport` narrows it, `--list`
  gives bare identifiers for a pipeline, and `--format json` gives the entry
  with its category, setting and reference. A typo exits 1 and suggests the
  nearest identifiers rather than printing a confident placeholder.

- **The scan reports whether a `security.txt` says how to report a
  vulnerability**, as `securityTxtPublished` under the new
  `setup.advisoryChecks`. Somebody who finds a flaw and cannot find an address
  for it falls back to a public issue tracker or to nothing, and a report that
  never arrives looks from the outside exactly like a flaw nobody found.

  It is reported and never counted, on the reasoning
  [ADR 0028](adr/0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md)
  applied to the modern response headers: no OpenCloud publishes one on any
  instance, so an absence describes the software rather than this deployment,
  and counting it would hand every `--check-hardening` user a WARNING about
  the shipped state of OpenCloud.
  [ADR 0034](adr/0034-an-advisory-observation-need-not-be-a-header.md)
  generalises that block to what is not a header. It reaches neither the alert
  line, the rating, the metrics, the webhook nor the exit code, and it is not
  offered as a waiver; `--debug` and the web catalogue explain it like any
  other check.

  The check reads the body rather than the status code. OpenCloud's frontend
  answers unknown paths with its own single-page shell, so a 200 at
  `/.well-known/security.txt` is the normal case and means nothing - the file
  has to carry the `Contact` field RFC 9116 makes mandatory, and must not be
  served as markup. The block is `{}` rather than a dictionary of `false`
  under `--no-extra-checks`: an observation nobody made is not one that
  failed.

- **`Cross-Origin-Embedder-Policy` joins the advisory headers.** It is the
  missing half of `Cross-Origin-Opener-Policy`, which was already reported:
  only both together give the browser grounds to isolate the origin against
  the Spectre-family side channels either one alone leaves open. Like the
  other three it is measured, explained and never counted, and
  `unsafe-none` - the browser default written out - is not credited as
  protection. The remediation says plainly that `require-corp` will stop a
  Collabora or WOPI embed loading unless that origin sends a
  `Cross-Origin-Resource-Policy` of its own, because a header that breaks the
  office integration is not one to roll out unrehearsed.

- **A `### Security` changelog entry now has to say whether anybody was ever at
  risk.** The heading records that something about this project's security
  changed; it never said whether a released version actually carried the
  defect, and reviewing the whole changelog showed how far those two come
  apart. Of nineteen security entries, seven described something a release
  shipped. The rest were defects introduced and fixed inside one development
  cycle - the `/catalogue` XSS, and all three MCP entries, whose templates and
  modules first appear in the very release said to fix them - plus hardening
  that closed no exploitable gap, and one bug that failed closed. Read as
  prose all nineteen look the same; the difference is only visible in the git
  tags.

  `security/advisories/<slug>.yml` now records one decision per entry, with the
  `git show` output it rests on in `verified:`.
  `scripts/security_advisories.py --check` fails when an entry from `1.14.0`
  onwards has no record, and runs on every pull request, so the question is
  answered by whoever fixed the defect rather than by somebody reconstructing
  it at release time. Declining is a normal answer - a record saying *never
  shipped, and here is the command that shows it* is worth as much as an
  advisory. Leaving the entry undecided is the only outcome the check refuses.

  After a release, `--sync` creates a GitHub **draft** advisory for each record
  that asked for one and commits the new identifiers back. Publishing stays
  manual and always will: it enters the GitHub Advisory Database and raises
  Dependabot alerts for every affected installation, which cannot be undone. A
  web-application record files against ecosystem `other` rather than `pip`,
  because `webapp/` never ships to PyPI and an alert there would be about code
  the installation does not have.

  Seven advisories were published from this review, covering `1.2.3` through
  `1.17.0`: the open scan-service bind, three webhook SSRF defects, the
  unpinned web-scan connection, results that were never encrypted at rest
  despite the setting, and CSV export formula injection.

- **A report page can rescan the instance, and says how long that has to
  wait.** The loop somebody actually runs is scan, fix, scan again - and the
  second half of it meant going back to the front page and retyping the
  address, with the waivers and the release track re-picked from memory or
  quietly forgotten. A result that was rated on different terms from the one
  before it is not a comparison, it is two unrelated reports.

  A finished report now carries **Scan again**, which resubmits the same
  target with the same waivers, the same release track and the same output
  format. It is an ordinary form posting to `/`, which is the point: the
  cross-site check, both rate limits, the SSRF guard and the audit trail are
  the ones every other submission already goes through, and there is no
  second write path to keep in step with them.

  Beside it is the wait. Both limits are read - the instance's cooldown and
  the visitor's own allowance - and the longer of the two is counted down in
  the page, because a countdown that expired into a refusal from the *other*
  limit would be worse than none. `RateLimiter` gains `peek_client` and
  `peek_target` for this: reading a limit must not spend it, or showing
  somebody their wait would be the request that caused it. The hostname comes
  from the record the uuid already unlocked, so nothing here can be asked
  about a target the caller does not hold a uuid for.

  The button is rendered enabled and the script disables it, rather than the
  other way round. A reader without scripting is never left holding a control
  that nothing on the page can release, and the 429 they may meet instead is
  the friendly one that points at self-hosting.
  [ADR 0032](adr/0032-a-rescan-is-an-ordinary-submission-and-reading-a-limit-never-spends-it.md)
  records the boundary.

- **The fixes a report names, in the syntax of the file that has to change.**
  Every finding already carried a sentence - *Set PROXY_ENABLE_BASIC_AUTH=false*
  - and an operator with eleven of them translated eleven sentences into one
  Compose file by hand. The translation is where the mistakes were.

  A report now renders that step: `opencloud_local_scan/snippets.py` turns the
  identifiers a scan reported into a fragment, in **Docker Compose**, **.env**,
  **nginx**, **Caddy** or **Traefik**, with the chosen one remembered in the
  browser. It renders, it does not decide - every name and value comes from
  the new `env_fix` and `header_fix` fields on the catalogue entries, so the
  fragment and the sentence above it cannot come to say different things, and
  a test asserts each header value still appears in its own Fix line.

  A fragment is complete or it says so. A check whose right value is a
  decision about the deployment - a CORS origin, a path to a CSP file - is
  named as having nothing to paste rather than given a placeholder: a fragment
  that has to be edited first is worse than the sentence it replaced, because
  it looks finished. Environment assignments and response headers are never
  mixed, either, since they are set in different files on usually different
  machines; what the chosen flavour cannot express is named, with the flavours
  that can.
  [ADR 0033](adr/0033-a-generated-configuration-fragment-is-complete-or-it-says-so.md)
  records the boundary.

### Changed

- **`--help` is grouped rather than a flat list of forty-five options.** The
  plugin's options were printed in one run, in the order they happened to be
  defined, and the flag somebody needed was always in the middle of it. They
  now sit under nine headings - which instance to check, what to probe, how
  the result is judged, version and update information, comparing against an
  earlier run, how the scan runs, what is printed, posting the result
  elsewhere, and the program itself - in the order a first run needs them.
  No flag, default, environment variable or behaviour changed.

### Documentation

- `AGENTS.md` gains **Security advisories**, and `SECURITY.md` explains how the
  advisory a reporter is promised actually gets published - including that the
  records for entries decided *against* are public too, so the reasoning can be
  read either way. `CONTRIBUTING.md` shows the two record shapes a contributor
  writes, the pull request template asks for one, and
  [`security/advisories/README.md`](security/advisories/README.md) documents
  the fields and why `package` is not cosmetic.

## [1.17.0] - 2026-08-31

### Security

- **The scan service binds loopback, and binding anything else now requires a
  token.** `check-opencloud-scanner serve` defaulted to `0.0.0.0` with no
  credential, and `GET /api/scan?url=<host>` hands the hostname a request
  names straight to the scanner - which, by design, validates nothing: the
  SSRF guard lives in `webapp/ssrf.py` and that path never reaches it. On a
  network with no token in front, that is an open request forwarder into
  whatever the monitoring host can reach - the cloud metadata endpoint, a
  container runtime socket, an internal admin panel - each answered back to
  the caller as scan evidence.

  `COS_SERVICE_LISTEN` now defaults to `127.0.0.1`, and any other address
  without `--token`/`COS_SERVICE_TOKEN` refuses to start rather than serving
  open. An operator who published the port meant to publish the service, and
  would otherwise have learned what they published from somebody else.

  **This is a breaking change** for a container that published the port
  without a token: it now needs `COS_SERVICE_LISTEN=0.0.0.0` *and*
  `COS_SERVICE_TOKEN`. The failure names both.
  `docker/docker-compose.monitoring.yml` already set both and is unchanged;
  local use needs neither. ADR 0001 made this argument for the Prometheus
  exporter and stopped there, so
  [ADR 0030](adr/0030-a-listener-binds-loopback-and-a-wide-bind-needs-a-credential.md)
  generalises it: a listener binds loopback, and a wide bind needs a
  credential.

- **`X-Forwarded-For` is read from the right rather than the left.** The
  leftmost entry is only the client behind a proxy that *overwrites* the
  header; nginx's `proxy_add_x_forwarded_for`, Traefik and most content
  delivery networks *append*, and there the leftmost entry is whatever the
  client sent. A caller could therefore mint a fresh rate-limit bucket, a
  fresh audit identity and a fresh allowance of `DELETE /api/purge` attempts
  per request, by adding one header.

  The header is now read from the end only a proxy writes,
  `COS_WEB_TRUSTED_PROXY_HOPS` entries in. An entry that is not an IP address
  is ignored rather than counted, so an obfuscated identifier cannot become
  somebody's bucket either, and an entry that *is* one is reduced to its
  canonical form before anything keys on it - `[2001:db8::1]`, `2001:db8::1`
  and `2001:0DB8:0000::1` are one host written three ways, and would otherwise
  have been three buckets, three audit identities and three allowances of
  purge attempts. `docs/reverse-proxy.md` said the opposite for Traefik - that
  the first entry is the client - and now says what happens.

- **The two daily reference-data fetches cap what they will read.** The
  release lifecycle page and the OSV advisory feed were both read into memory
  in full before anything looked at them, and both URLs are operator
  configuration that may name a mirror. The advisory feed's `MAX_ADVISORIES`
  guard could not help: reaching it already meant paying for the whole answer.
  Because both jobs run `run_at_startup`, an oversized answer was a worker
  that crashed, restarted, asked again and crashed again.

  Both now read at most one megabyte and treat more as a failed fetch, which
  every caller already degrades from by keeping the document it had. The
  ceiling lives in one place, `opencloud_local_scan/fetch.py`, so the two
  cannot drift - the same rule `ScannerSettings.max_response_bytes` has always
  applied to the instances being scanned, now applied to the documents they
  are rated against.

- **A submission from another site is refused before it is counted.** `POST /`
  and `POST /language` took a plain form body with no check on where it came
  from, so a page anywhere could queue a scan against a target of its choosing
  and have it attributed to whichever browser it borrowed - spending that
  visitor's rate-limit allowance and making their network the apparent origin
  of a scan they never asked for.

  Both now refuse a cross-site submission, using the `Sec-Fetch-Site` and
  `Origin` headers a browser attaches by itself rather than a token, since
  this service has no session to hang one on. The check runs before the rate
  limiter, so a refused submission costs the borrowed visitor nothing. A
  caller that is not a browser - curl, an agent, the in-process MCP client -
  sends neither header and is refused nothing; a page cannot make a browser
  omit them.

### Fixed

- **An advisory that names no version range is dropped instead of matching
  every release.** `is_in_range(version, None, None)` is true of every version
  there has ever been, so one such record reported *every* instance scanned
  with that database as critically vulnerable - a fleet-wide false CRITICAL
  that looks exactly like a real one, on the check whose exit code drives the
  alerting.

  `_from_osv` already refused these and said why; the other two parsers did
  not. The native format is the one an operator writes by hand and points
  `--vulnerability-feed` at, where a forgotten bound is a typo rather than
  somebody else's feed quirk, and the GitHub parser stopped at the first
  OpenCloud entry - which proves an advisory is *about* OpenCloud and nothing
  about which releases it affects, so an unparseable
  `vulnerable_version_range` with no patched version left it unbounded. All
  three now refuse alike and log which advisory was dropped.

  A single open bound is untouched: no fix yet is the normal shape of a fresh
  advisory, and no introduced version means everything up to the fix. Only
  *both* ends open is meaningless. A disabled placeholder such as the bundled
  `OC-EOL` is not judged at all - it never becomes an advisory, and it
  documents the end-of-life finding the scanner raises by itself.

  The web application keeps refusing such a *document* wholesale rather than
  quietly dropping the entry from it, which is what
  [ADR 0017](adr/0017-the-advisory-database-refreshes-itself.md) asks for: a
  feed emitting an advisory that affects every version has gone wrong, and
  yesterday's database is the better answer than the rest of today's.

- **A rating threshold outside 0-5 no longer crashes the plugin into a
  WARNING.** `-w`/`-c` are plain integers and the environment feeds the same
  values, so nothing stopped `-c 6`. The evaluation then looked the threshold
  up in `RATE_MAP` to name it in the alert line and raised `KeyError`; with no
  handler above `main()`, Python exited 1, which Nagios reads as WARNING. A
  typo in a check command became a warning state on the monitored host with a
  traceback as its status text. The thresholds are now validated before any
  scan starts, and the two alert-line lookups no longer index `RATE_MAP`
  directly.

### Added

- **Every finding on a report links to the catalogue entry that explains it,
  and the report has a contents list.** A result named identifiers -
  `basicAuthDisabled`, `exposed:/config/opencloud.yaml` - and left the reader
  to search for what they mean. The category badge already led to the
  catalogue, but only as far as the category: a reader who wanted the
  paragraph about *their* finding still had to find it among sixty entries.

  Each catalogue entry now carries its own anchor, and every finding, missing
  hardening, missing header, plan step, waived check and unfixable flag on a
  report links straight to it. Both sides are built from one function,
  `hardening.catalogue_id`, so a report cannot offer a fragment the catalogue
  does not publish - asserted in both directions by a test. The per-path and
  per-port findings resolve to the family the catalogue actually lists, so
  `exposed:/config/opencloud.yaml` lands on `exposed`; an identifier this
  build cannot explain is rendered as plain text rather than as a link
  promising an explanation that is not there. The entry a reader arrives at
  highlights itself.

  The report also gets the contents list the documentation pages have, built
  from the same `_toc.html`. Every entry is conditional on the section it
  names being rendered, so a clean instance is not offered a jump to an
  advisories card it does not have.

- **A report can be shared by email or from the clipboard, and by nothing
  else.** A finished report had no way out of the browser except the exports,
  so the address got copied out of the URL bar - and that address is the whole
  of the authorisation for the page ([ADR 0007](adr/0007-erasure-on-request.md)).
  The page now says so, and offers three ways to act on it.

  The email link is a plain `mailto:`, which the browser hands to whatever
  mail client the reader already has; nothing is posted through this service
  and no third party is asked to help. **There is deliberately no Slack,
  Teams or social share button**, and not only for the reason in `AGENTS.md`:
  those services fetch a link server-side to build a preview of it, so a share
  button would hand a company a working credential for somebody's security
  report and have it fetch the report to make a thumbnail.

  That is also why *copy summary* exists beside *copy link*. Pasting findings
  into a chat channel is a reasonable thing to want; handing everyone in that
  channel a live capability usually is not, so the summary carries the grade
  and the counts as text with no link in it - asserted by a test, because that
  is the property worth keeping. Both buttons are rendered hidden and shown
  only where a clipboard is actually reachable, so a reader on plain http gets
  the address in selectable text rather than a button that cannot work.

- `COS_WEB_TRUSTED_PROXY_HOPS` (default `1`): how many proxies of a
  deployment's own sit in front of the service, which is how far in from the
  right of `X-Forwarded-For` the client address is read. One reverse proxy is
  `1`; a content delivery network in front of an ingress is `2`. Counting too
  few names a proxy instead of the visitor and is harmless. **Counting more
  than there are is not, and nothing can make it safe**: with `2` behind a
  single proxy, `X-Forwarded-For: spoofed` arrives as `spoofed, <real>` and
  the second entry from the right is the one the client wrote. The count is
  clamped to the number of entries present, but that only prevents a read past
  the end - nothing in the header distinguishes an entry a proxy appended from
  one a client sent. Set it to the number of proxies you operate.

## [1.16.0] - 2026-08-30

### Added

- **The Docker setup wizard can hand the audit file to the host's logrotate**,
  for a trail kept in a directory on the host. It asks who rotates it -
  `service`, by size, from inside the container and needing nothing installed,
  or `logrotate`, which is where an estate's retention policy, compression and
  backups already live - and how many days to keep. Choosing logrotate writes
  a third file beside the compose file, `<project>-audit.logrotate`, with the
  install command in its header and in the wizard's next steps.

  `COS_WEB_AUDIT_LOG_ROTATION` is the setting behind it. `external` turns the
  service's own size-based rotation off and switches the handler to one that
  notices its file was moved aside and reopens the replacement, so the policy
  needs no `copytruncate` - which would truncate the file underneath a running
  writer and lose whatever fell between the copy and the truncation - and its
  `create 0600 10001 10001` line is what keeps the new file writable by the
  container and readable by nobody else. Exactly one thing may rotate the
  file, so an unrecognised value refuses to start rather than leaving a
  deployment with two rotators or none, and the wizard warns that a policy
  nobody installs rotates nothing.

- **The Docker setup wizard asks where a deployment keeps its audit trail and
  whether Redis survives a restart**, and either can go to a named Docker
  volume or to a directory on the host. Both default to `none`, which is what
  the shipped stack already does; the point is that keeping something is now
  an answer rather than a hand-edited compose file.

  The audit trail needed somewhere to go first, so `COS_WEB_AUDIT_LOG_FILE`
  is new: it writes the records to a file instead of the process output,
  owner-readable, rotated at `COS_WEB_AUDIT_LOG_MAX_BYTES` with
  `COS_WEB_AUDIT_LOG_BACKUPS` generations kept, so the trail cannot fill the
  volume it sits on. The records go there *instead of*, not as well as, the
  ordinary log - which is the one place this service keeps free of targets and
  client fingerprints. A path the process cannot write refuses to start, for
  the reason [ADR 0008](adr/0008-refuse-to-start-without-the-encryption-key.md)
  gives about encryption: reporting an audit trail that silently goes nowhere
  is worse than keeping none. `Dockerfile.web` creates
  `/var/log/opencloud-scan` owned by the unprivileged uid, so a fresh named
  volume inherits an ownership the container can write to.

  Persisting Redis is the one answer here that takes something away from what
  the service can promise - a copy of every result still inside its TTL then
  exists as a file - so the wizard warns when it is chosen, suggests
  `COS_WEB_ENCRYPT_RESULTS` alongside it, and rewrites the comment above the
  `redis` service rather than leaving a compose file claiming it writes
  nothing to disk. The `private` preset now keeps the audit trail it already
  turned on.

- **Four hardening flags read from the OpenID Connect discovery document the
  scan already fetches**, at the cost of no additional HTTP request. Finding
  out who signs users in has always meant reading
  `/.well-known/openid-configuration`; until now only `issuer` was kept and
  the rest was thrown away, which left
  [Securing a deployment](docs/secure-deployment.md) telling operators to
  require PKCE with nothing able to check whether they had.

  | Flag                         | Fails when                                                                   |
  |:-----------------------------|:-----------------------------------------------------------------------------|
  | `oidcPkceSupported`          | `code_challenge_methods_supported` does not offer `S256`                     |
  | `oidcImplicitFlowDisabled`   | `response_types_supported` returns a token from the authorization endpoint   |
  | `oidcSigningAlgorithmStrong` | `id_token_signing_alg_values_supported` contains `none` or an `HS` algorithm |
  | `oidcEndpointsUseHttps`      | a published endpoint is an `http://` address                                 |

  **Every one is skipped where the evidence is not published**, the same rule
  `passwordPolicyComplexity` follows. That matters more here than usual:
  OpenCloud's built-in provider ([libregraph/lico](https://github.com/libregraph/lico)) omits
  `code_challenge_methods_supported` entirely, so reading its absence as "no
  PKCE" would fail every stock instance for something its operator cannot
  change. For the same reason `oidcImplicitFlowDisabled` is reported for an
  **external** provider only - lico publishes `id_token token` and `id_token`
  among its response types and cannot be reconfigured, and a finding an
  operator cannot act on is worse than none. `oidcEndpointsUseHttps` is
  measured only when the instance itself answered over HTTPS, so it reports
  the disagreement worth reporting - a TLS instance whose provider still
  advertises `http://` - rather than restating `httpsEnforced`.

  [Authentication](docs/authentication.md) explains all four, and records
  what else that document publishes and why none of the rest is checked -
  including `token_endpoint_auth_methods_supported`, the obvious fifth
  candidate, which is not a finding in either direction.

  The result document's `identityProvider` block gains a `metadata` key
  carrying the fields these flags were read from, so a reader can see the
  evidence rather than only the verdict. `derive_hardenings()` takes the
  identity-provider block as a fourth, optional argument; a caller that does
  not pass one still gets every other flag.

- **`passwordPolicyComplexity`: whether the link password policy still asks
  for more than a length.** OpenCloud's default policy requires one lowercase
  letter, one uppercase letter, one digit and one special character, and each
  of those four minimums is a setting somebody can lower to zero. A
  twelve-character policy with all four at zero accepts `aaaaaaaaaaaa`, which
  satisfies `passwordPolicyEnforced` and nothing else. Deliberately a second
  flag rather than a stricter `passwordPolicyEnforced`: folding them together
  would change what an existing alert means without changing its name.
  Reported only when the instance publishes all four minimums - a policy that
  is switched off publishes none of them, and that case is
  `passwordPolicyEnforced` failing rather than this one. See
  [Authentication and account exposure](docs/authentication.md).

- **`check-opencloud-scanner diff`**: compare two archived result documents
  and say what changed - findings that appeared, findings that were resolved,
  and any movement in the rating, the version and the support horizon. Renders
  as `text`, `markdown`, `json` (the document the webhook carries) or `slack`
  (Block Kit). It reads files and never scans anything. Two different hosts
  are refused unless `--allow-different-hosts` is given, because "did the fix
  work" is a question about one instance and two hosts silently compared is a
  wrong answer nobody notices; a comparison that got worse exits 1 so a
  pipeline can gate on it, unless `--exit-zero` says otherwise. The judgement
  is the plugin's own `--baseline` arithmetic, not a second implementation of
  it.

- **`compare_scans`, an MCP tool, and `verify_remediation`, a prompt**, so the
  question an agent is asked a week after handing over a remediation plan -
  *did any of that help?* - has an answer. Two finished scans of one instance
  are compared into what was fixed, what is still open and what is new; both
  uuids must still be here, since this service stores no scan history and a
  uuid remains a capability with a TTL. The comparison is the same
  `--baseline` arithmetic the plugin uses rather than a set difference of its
  own, so an agent cannot call "improved" something the plugin would not. Also
  reachable as the `compareScans` Arazzo workflow and listed in
  `/.well-known/ai.json`. See
  [ADR 0029](adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md)
  for why neither a history table nor workflow-layer arithmetic was acceptable.

- **A GitHub Action** ([`action.yml`](action.yml)): `uses: sowoi/check-opencloud-security@v1`
  with a `target`, and the scan runs. Writes `json`, `sarif` (2.1.0, for the
  code-scanning dashboard), `junit` or `nagios` to `output-file`, and exposes
  `exit-code`, `status`, `rating`, `rating-label`, `message` and `result-file`
  as step outputs. `fail-on` chooses whether a `warning` fails the step, only
  a `critical` does, or `never` does and a later step decides; `UNKNOWN` fails
  under both of the first two, because a scan that did not run is not a pass.
  Pin the version: the release schedule and the newest known OpenCloud version
  ship *inside* the package, so which version runs is part of the verdict. See
  [Running the check from CI](docs/ci.md).

- **`opencloud_security_end_of_life`**, a Prometheus metric of its own rather
  than a negative `support_days_remaining`. A rolling or production release
  whose end of life has not been dated yet publishes no day count at all, and
  "unknown" must not read as "expiring today" in the one alert nobody may
  miss. Labelled with `host` and `release_type`.

- **Prometheus alerting rules and a Grafana dashboard as files**
  ([`contrib/prometheus/alerts.yml`](contrib/prometheus/alerts.yml),
  [`contrib/grafana/dashboard.json`](contrib/grafana/dashboard.json)) - nobody
  retypes a dashboard. Both read the metric names the **native** exporter
  publishes, not the shorter ones the textfile-collector and Pushgateway
  recipes shape with `jq`. `tests/test_contrib_assets.py` derives the names
  from the exporter itself, so a rename fails the suite rather than quietly
  emptying a panel. The dashboard carries an `Instance` selector, so one copy
  serves every host.

- **A contents list on every page the menu bar reaches** that has more than
  one section. `/how-it-works`, `/grades`, `/catalogue`, `/api`, `/ai` and
  `/about` now open with the same jump list `/documentation` already had, and
  that list is one template
  ([`frontend/templates/_toc.html`](frontend/templates/_toc.html)) rather than
  six copies. Every entry reuses the section's own heading string, so a
  heading rewritten in one of the four languages cannot leave the contents
  list behind saying the old thing. A page with a single section
  (`/privacy`) includes nothing: a contents list of one entry is a link to the
  top of the page the reader is already on.

### Changed

- **Breaking: `COS_WEB_PURGE_TOKEN` must now be at least 32 characters, and a
  deployment whose token is shorter refuses to start.** That token is the
  entire authorisation for `DELETE /api/purge`, the one route that walks the
  keyspace and deletes results belonging to whoever is currently reading them,
  so a memorable one is worse than no endpoint at all. Startup fails with a
  message naming the variable rather than serving the endpoint behind a
  guessable secret - the stance
  [ADR 0008](adr/0008-refuse-to-start-without-the-encryption-key.md) takes for
  the encryption key, for the same reason: a deployment whose operator
  believes something is protected must not come up when it is not.

  **What to do.** Nothing, unless `COS_WEB_PURGE_TOKEN` is set *and* shorter
  than 32 characters - leaving it unset is unaffected and still answers 404 to
  every erasure request, which is the default and the safe state. If it is
  set, generate a replacement and update whoever holds it:

  ```bash
  python -c 'import secrets; print(secrets.token_hex(32))'
  ```

  Tokens written by the Docker setup wizard have always been 64 hex
  characters and need no change.

- **The Docker setup wizard's yes/no questions say that `true` and `false` are
  accepted too**, and a confirmation prompt that does not understand an answer
  now says so instead of silently asking again. Both words were always
  accepted; nothing on screen admitted it.

- **The Docker tab is now the first half of `/documentation`.** Somebody
  looking for how to run the check had to guess which of two menu entries
  answered that; the one-liners - the plain `docker run`, the JSON result
  document, `--network host` for an instance this site will not scan, and the
  `uvx` form for machines without Docker - now sit directly under the quick
  start on the documentation page. `/cli` answers **301** to
  `/documentation#oneliner`, because that path is printed in released
  documentation and indexed; it is out of `sitemap.xml` and out of the search
  index, whose `/documentation` entry now covers the same text. The "every
  variation, written down" section it used to close with is not repeated: the
  guide it pointed at,
  [Scanning from the command line, in one line](docs/docker-oneliner.md), is
  already listed in the guide grid further down the same page.

### Fixed

- **`DELETE /api/purge` now counts wrong credentials, and refuses to start
  behind one short enough to guess.** It is the only destructive route here -
  it walks the keyspace and deletes results belonging to whoever is currently
  reading them - and the token is the whole of its authorisation. The
  comparison was already constant time, which stops a token leaking a
  character at a time and does nothing about simply trying: the route called
  no limiter, so attempts were free. Five failures from one address inside
  five minutes are now answered `429` without a comparison. Only failures
  count, so an operator working through a list of erasure requests never meets
  it. The minimum length now required of that token is a breaking change and
  is described under **Changed** above.

- **The client rate limit can now be made to hold across more than one web
  process.** The pepper the limit keys are derived from is generated per
  process, which is correct for the single-process stack this ships and
  silently wrong for anything scaled: each process derives a different Redis
  key for the same address, so a client quietly gets one allowance per process
  and nothing in any log says so. `COS_WEB_RATE_LIMIT_SALT`, set to the same
  value everywhere, makes them count together. Unset keeps exactly the
  previous behaviour, so a single-process deployment needs no change.

- **`COS_WEB_ENABLE_DOCS` in the three published compose files now matches the
  comment above it.** `docker-compose.yml` explained that the browsable
  `/docs` and `/redoc` pages are "off in public: enabling them relaxes the
  content policy on those two paths", and then set the value to `"true"`;
  the other two stacks enabled them with no comment at all. All three are now
  `"false"`, which is also the application's own default, and the comment says
  how to turn them on. `/openapi.json`, `/arazzo.json` and
  `/.well-known/ai.json` are public whatever this says, as they always were.

- **A scanned instance can no longer forge the GitHub Action's step outputs.**
  The action writes `status`, `rating`, `rating-label` and `message` to
  `$GITHUB_OUTPUT` as heredoc blocks, and the delimiter closing them was the
  fixed string `COS_EOF`. Half of what reaches those values is a string the
  *scanned host* chose - its product name, a `WWW-Authenticate` challenge, the
  message built around them - so the one party with an interest in guessing
  the delimiter already knew it. A host answering with a message containing a
  line reading `COS_EOF` closed the block early and had everything after it
  parsed as further assignments: arbitrary step outputs in whatever workflow
  consumes them, from a host that only had to answer an HTTP request. The
  delimiter is now `secrets.token_hex(16)` per run, as GitHub's own
  documentation specifies, and a value that manages to contain it anyway is
  dropped rather than written.

- **A webhook is no longer delivered to wherever the receiver redirects it.**
  `--webhook-url` is checked against private, loopback and link-local
  addresses, and re-resolved immediately before delivery to close the
  rebinding window - but the POST itself left `allow_redirects` at its
  default, so a receiver answering `302 Location: http://169.254.169.254/`
  had the payload delivered one hop past the guard, to an address nothing
  checked. What travelled with it was not only the result: `X-COS-Signature`
  and every `--webhook-header` went too, and `requests` drops `Authorization`
  across hosts but keeps the rest, so a receiver's own API key was handed to
  whatever it pointed at. The scanner has refused unvalidated redirects since
  the SSRF guard was written; the webhook path simply never asked. Redirects
  are now never followed, and a 3xx is reported as a delivery failure rather
  than passing `raise_for_status()` as a notification that never arrived.

- **The Redis service in all three published compose files now starts with the
  arguments it was meant to have.** `command: >` is a *folded* scalar, so a
  `#` inside the block is literal text rather than a comment - the four lines
  of prose explaining `COS_REDIS_PASSWORD` were folded into the command line
  between `--maxmemory-policy` and `--requirepass`, handing `redis-server`
  fifty words of English as arguments. Either the server refuses the directive
  and never starts - taking the whole stack with it, since the other services
  wait on its health check - or it comes up with no password at all on a store
  holding every live scan and every result still inside its TTL. The wizard's
  generated compose kept its comments outside the block and was unaffected;
  the checked-in files had diverged from it since 1.12.0. The comments now sit
  above `command:` in `docker-compose.yml`, `docker-compose.dockerhub.yml` and
  `docker-compose.authentik.yml`, and two tests split each compose file's
  commands the way Compose does and assert that no folded-in prose reached
  them.

- **Every workflow now declares the token scope it needs, and pins every
  action to a digest.** Ten of the sixteen already did both; the six that ran
  the suite, ruff, mypy, nox, ansible-lint and Bandit declared no
  `permissions:` block at all, so `GITHUB_TOKEN` arrived with whatever the
  repository default grants - frequently write across every scope - in jobs
  that install and execute the whole dependency tree on a push. They now
  declare `contents: read`. Bandit keeps its job-level
  `security-events: write` for the SARIF upload, which a job-level block
  grants without widening the others. The same seven files referenced
  `actions/checkout@v7`, `astral-sh/setup-uv@v10.0.0` and
  `github/codeql-action/upload-sarif@v4` by mutable tag rather than by digest,
  against the convention the rest of the directory follows; all three are now
  pinned to the commit their tag resolved to, with the version in a trailing
  comment. Two tests read the workflow directory rather than a list, so a
  workflow added later is covered the moment it exists.

- **The Bandit workflow's SARIF upload now names the ref and commit it is
  reporting on**, so a pull request's code scanning check can find it. Left to
  itself the upload action resolves the merge commit from the checkout, and
  GitHub may recompute `refs/pull/N/merge` between the event firing and the
  job running - the analysis then landed on a commit the pull request's check
  was not looking at, and every pull request drew "Code scanning cannot
  determine the alerts introduced by this pull request, because 1
  configuration present on `refs/heads/main` was not found" even though the
  job had succeeded and uploaded its report. Passing `ref` and `sha` from the
  event pins the analysis to the commit the check expects; on `push` and
  `schedule` they are the values the action would have derived anyway.

- **The Docker setup wizard's generated compose file now actually enables
  IPv6 when an operator confirms the container can reach one.** Answering
  yes to "Does this container have outbound IPv6 connectivity?" only ever
  turned on `COS_WEB_IPV6_ENABLED` - it left both networks the stack uses,
  `default` and `scanner_internal`, without `enable_ipv6`, which Compose does
  not set for a network just because the daemon supports it. An operator who
  had genuinely verified IPv6 still got a container that could not dial one,
  making the confirmed "yes" indistinguishable from a wrong one.
  `render_compose_file` now writes `enable_ipv6: true` on both networks
  whenever `ipv6_enabled` is set.

- **A scan now closes the connections it opened.** `_Probe` pools its
  HTTP connections in a `requests.Session` - one for the calling thread and
  one per worker - and none of them were ever closed, so every scan left its
  sockets held until the garbage collector happened to run. Over a fleet that
  is one socket per host for no reason, and where the instance has gone away
  in the meantime the response still sitting in the pool is finalised against
  a socket somebody else already closed. On Python 3.14 that surfaces as
  `ValueError: I/O operation on closed file` ignored in a destructor, blamed
  on whatever unrelated code was running when the collector fired - in this
  repository, a `PytestUnraisableExceptionWarning` pinned to an innocent test
  in `tests/test_webapp_api.py`. `_Probe.close()` closes every session the
  probe opened, including the ones worker threads made, and `scan()` calls it
  in a `finally` so an exception partway through does not leak them either.

- **A CSP directive separated from its sources by a tab or a newline is now
  read.** `_csp_directive` split the name from the source list on a literal
  `" "`, but CSP separates the two with any run of ASCII whitespace, and a
  policy indented across several lines uses a tab. Such a directive was
  invisible: `script-src\t'self' 'unsafe-inline'` left
  `cspWithoutUnsafeInline` passing, which is a green tick for a policy that
  really does let injected markup execute - the one direction this check must
  not fail in. The same blindness ran the other way for
  `frame-ancestors`, where a tab produced a false clickjacking alarm against
  an instance whose CSP did restrict framing.

- **A CAA record whose property tag is not spelled in lower case now counts.**
  RFC 8659 section 4.1 makes the tag case insensitive, so
  `Issue "letsencrypt.org"` restricts certificate issuance exactly as much as
  `issue` does. Matching the spelling literally reported such a zone as having
  no CAA record at all - a `tlsCaaRecord` finding against a domain that had
  done the right thing. Tags are folded to lower case as they are parsed, so
  `iodef` is still not mistaken for a property that authorizes an issuer.

- **The Prometheus exporter no longer counts measures the operator waived.**
  `opencloud_security_hardenings_missing_total` and
  `opencloud_security_failed_extra_checks_total` were computed straight from
  the result document, ignoring `ignored` - so the same instance reported zero
  to Icinga, whose perfdata has always dropped waived entries, and non-zero to
  Prometheus. An alert rule built on either gauge fired for exactly the
  measures its operator had switched off, which is the noise a waiver exists
  to remove. Both now follow the rule `failed_extra_checks()` already
  documents: a waiver hides an alert, not the evidence.

- **A pinned IPv6 literal is no longer looked up a second time.** The scan
  carries an IPv6 host bracketed so it can go back into a URL, while the web
  application pins the bare address it validated. `_resolved_addresses`
  compared the two without stripping the brackets, so every IPv6 literal
  target missed its pin and fell through to the DNS lookup the pin exists to
  avoid - leaving `addresses` empty, and the IPv4/IPv6 TLS parity check
  skipped, for precisely the targets that had been pinned. It now normalises
  the key the way the debug-port and TLS lookups beside it already did.

- **The webhook guard now refuses carrier-grade NAT, as the scan-target guard
  always has.** `_webhook_address_is_public` leaned on `ipaddress` to say what
  is private, and `ipaddress` does not classify `100.64.0.0/10` as anything -
  not private, not reserved, not link-local. A webhook URL resolving into that
  range was therefore delivered to, including to `100.100.100.200`, a cloud
  metadata endpoint where a single successful request is already a breach.
  `webapp/ssrf.py` has refused the range for a scan target since it was
  written; the two guards answer the same question about different callers and
  are now kept in step, with the NAT64 prefixes folded into the same table so
  there is one list to read instead of two.

  The webhook URL is operator configuration rather than a stranger's input, so
  this was defence in depth rather than an open door - but it was the one
  range where the two guards disagreed.

### Removed

- **`_base_of()` in the scanner**, which was dead code and wrong. It tried to
  recover the pre-cap rating from the cap list by taking the lowest cap that
  was not applied, which returns 4 rather than 5 for the ordinary case of a
  clean instance with one medium finding. Nothing called it - `RatingExplanation`
  has carried `base_rating` outright for several releases - so no output
  changes.

### Documentation

- **[Running the check from CI](docs/ci.md) now leads with the action**
  rather than with a hand-rolled install: the workflow to copy, how to feed
  the SARIF into GitHub's code-scanning dashboard, and the manual installation
  kept below for whoever wants it.

- **[Prometheus and Grafana](docs/prometheus.md) gains the two files to copy
  and a table of everything the exporter publishes** - every metric, its
  labels and its meaning - including which two are the only ones a failed scan
  emits, so a broken scan reads as no verdict rather than a stale one.

- **[Public link sharing](docs/sharing.md) writes down what is *not* checked
  and why.** The capabilities document says a great deal more about sharing
  than the two flags read; the new table records which of it is a hardcoded
  constant (so a check would say nothing about the deployment), which is
  configurable but explicitly unsupported to change, and which is a genuine
  judgement call deliberately not made yet - verified against OpenCloud's own
  `services/frontend/pkg/revaconfig/config.go`, so nobody re-derives it in a
  year.

- **[`contrib/README.md`](contrib/README.md)** is no longer only about
  scheduling; it now covers all four things it ships and how to install each.

## [1.15.0] - 2026-08-30

### Added

- **`corsOriginRestricted`: the scan now asks who may read the API's
  responses.** A request to `/graph/v1.0/me` carrying an `Origin` that cannot
  belong to anybody (`.invalid`, reserved by RFC 2606) reveals what the
  instance grants a foreign site. OpenCloud ships
  [`OC_CORS_ALLOW_ORIGINS='*'` with
  `OC_CORS_ALLOW_CREDENTIALS=true`](https://docs.opencloud.eu/docs/dev/server/services/graph/environment-variables),
  and a middleware given both commonly reflects the requesting origin - so any
  page a signed-in user opens can have their browser attach its OpenCloud
  session and read the reply. **Critical** when credentials are allowed with a
  reflected or `null` origin, **medium** for a reflected origin without them
  or a literal `*` (which browsers refuse to act on), and a pass for a
  specific named origin. See
  [Exposed paths and debug endpoints](docs/exposure.md).

- **`traceMethodDisabled`**: whether the server answers `TRACE` by echoing the
  request back, headers included, where a script can read the session cookie
  it could never read directly. OpenCloud does not implement `TRACE`, so a
  hit means something in front of it does. `TRACE` is a safe method by RFC
  9110 - it echoes and changes nothing - and a `200` only counts when the body
  actually looks like the request, so a single-page application's catch-all
  shell is not mistaken for an echo.

- **`cookiePrefix`**: the `__Host-` and `__Secure-` name prefixes, which are
  the only cookie protection a browser enforces on the name rather than the
  attributes - and therefore the only one that stops a sibling subdomain or
  plain HTTP on the same host from *overwriting* a session cookie, which
  `Secure` and `HttpOnly` do nothing about. Reports both a cookie that claims
  a prefix without honouring its rules (rejected outright by every browser, so
  the session silently does not work) and the ordinary case of no prefix at
  all. See [Cookie attributes](docs/cookies.md).

- **`tlsCertificateTransparency`**: counts the signed certificate timestamps
  embedded in the certificate, from the `openssl x509 -text` call that already
  reads the key and signature algorithm - no extra connection. A publicly
  trusted certificate without them is refused outright by Chrome and Safari.
  Deliberately withheld for a self-signed or privately issued certificate,
  which cannot be logged and where the question is not a fair one -
  OpenCloud's own `opencloud init` produces exactly that.

- **`tlsEarlyData`**: reads the `Max Early Data` limit the server's session
  tickets advertise, from the same `openssl s_client` handshake that answers
  the stapling question. A TLS 1.3 0-RTT flight has no replay protection by
  design; for a file service that is a move, copy or delete replayed at
  somebody else's choosing. Low severity, and reported as unknown rather than
  as accepted when the server never states a limit. See
  [TLS and certificates](docs/tls.md).

- **`setup.advisoryHeaders`**: `Permissions-Policy`,
  `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy`, measured
  and explained but **never counted**. No OpenCloud sends any of them, so
  their absence describes the software rather than the deployment; putting
  them in `setup.headers` would give every existing `--check-hardening` user a
  permanent WARNING no configuration change could clear. They are explained by
  `--debug` under a heading that says so, listed in the web catalogue, and
  kept out of the alert line, the `hardenings_missing` metric, the webhook and
  the exit code. A value that restricts nothing (`unsafe-none`,
  `cross-origin`) does not count as present. See
  [ADR 0028](adr/0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md).

- **[Running OpenCloud in a secure infrastructure](docs/secure-deployment.md)**,
  served at `/documentation/secure-deployment`: the part a scan cannot see.
  Putting Keycloak, Authentik or Authelia in front of the instance with the
  exact `OC_OIDC_*`/`PROXY_*` variables and the two settings that are usually
  got wrong; turning the audit service on (it is not in the default run set,
  and `AUDIT_LOG_LEVEL` defaults to `error`) and getting its log off the host;
  firewalling the ports Docker publishes behind UFW's back; what the people
  using the instance should be told; and where scheduled scanning with this
  plugin fits, including an explicit list of what it will not tell you.

- **Test coverage is now measured and enforced in CI.** `pytest --cov` runs in
  the unit-test workflow with a floor of 85% (the suite sits at 87%). A plugin
  whose whole value is that its verdicts are trustworthy should not have
  untested branches in `scanner.py` or `tls.py`.

### Changed

- **[The CLI option reference moved to its own page](docs/cli-reference.md)**,
  served at `/documentation/cli-reference`. The fifty-row table was 10% of
  `README.md` by weight and pushed everything after it halfway down the file;
  the README keeps the handful of options people actually type most days and
  links to the full table. The two inbound links from
  [`docs/ansible.md`](docs/ansible.md) and
  [`ansible/README.md`](ansible/README.md) now point at the new page.

- **The `tls` block of the result document** gains `certificate.sctCount` and
  `maxEarlyData`, both `null` when nothing looked - an absent measurement
  stays an unknown rather than becoming a pass, as everywhere else in that
  module.

## [1.14.2] - 2026-08-30

### Added

- **A "What OpenCloud is" background page**
  ([`docs/what-is-opencloud.md`](docs/what-is-opencloud.md), served at
  `/documentation/what-is-opencloud`): the fork history behind OpenCloud,
  ownCloud and Nextcloud, and the architecture, storage and release
  differences that follow from it. This is the background for why the
  scanner reads the `product`/`productname` field from `/status.php` and
  refuses to rate an instance that identifies as ownCloud or Nextcloud
  rather than OpenCloud, instead of guessing.

- **`--webhook-digest`**: with `--host` given several targets, send one
  combined webhook for the whole run instead of one per host that meets
  `--webhook-on`. Only combines what happens inside one process - see
  [Checking a fleet of instances](docs/many-instances.md) for how this
  relates to the config-file-per-instance and cron/systemd-loop patterns,
  where each instance is a separate process with nothing to combine across.

### Changed

- **`contrib/systemd/*.service` now carry hardening directives**
  (`ProtectSystem=strict`, `NoNewPrivileges=yes`, `PrivateTmp=yes`, a
  restricted `RestrictAddressFamilies=`, an empty `CapabilityBoundingSet=`,
  and more) instead of relying solely on `DynamicUser=`/`StateDirectory=`.
  Run `systemd-analyze security <unit>` after deploying to see the effect.
  The main scan unit also gains `StateDirectory=check-opencloud-security` so
  the `COS_BASELINE` path now demonstrated in
  `check-opencloud-security.env.example` composes with the hardening rather
  than needing a manually added `ReadWritePaths=`.

- **A table of contents on every documentation guide long enough to need
  one.** 19 pages under [`docs/`](docs/) - everything from
  [`authentication.md`](docs/authentication.md) to
  [`webhook-recipes.md`](docs/webhook-recipes.md), plus the docs index and the
  new [`what-is-opencloud.md`](docs/what-is-opencloud.md) - were missing the
  `<!-- TOC -->` jump list that `mcp.md`, `authentik.md`, `reverse-proxy.md`
  and `redis.md` already had. Pages with only a title and no sub-sections
  ([`icinga-director.md`](docs/icinga-director.md),
  [`troubleshooting.md`](docs/troubleshooting.md)) and
  [`webapp.md`](docs/webapp.md) (already has its own "Contents" list) were
  left alone.

- **The three-layer diagram in [`ARCHITECTURE.md`](ARCHITECTURE.md)** is now
  a Mermaid flowchart instead of an ASCII box diagram, so it renders as an
  actual diagram on GitHub rather than relying on a monospace font to line
  the boxes up. Same content: `opencloud_local_scan/` measures, its result
  document feeds both `check_opencloud_security.py` (judges) and `webapp/` +
  `frontend/` (serves), and grades come from the plugin's `RATE_MAP`, never
  decided in `serve`.

- **That diagram now renders to a checked-in PNG**
  ([`img/architecture-three-layers.png`](img/architecture-three-layers.png)),
  because GitHub is the only place that renders Mermaid - `git show`, an
  editor preview and a plain read of the file all show source otherwise.
  [`scripts/render_architecture_diagrams.py`](scripts/render_architecture_diagrams.py)
  finds every `` ```mermaid `` fence in `ARCHITECTURE.md` and makes sure a
  Markdown image line for its rendered PNG follows it (`--check` for CI); the
  new [`render-architecture-diagram.yml`](.github/workflows/render-architecture-diagram.yml)
  workflow runs it and `mmdc` (`@mermaid-js/mermaid-cli`, under Node 24 - not
  the Node 20 GitHub Actions runners are deprecating) on every push to `main`
  that touches `ARCHITECTURE.md`, and opens a pull request when the rendered
  PNG no longer matches the Mermaid source.

### Security

- **The webhook HMAC signature could never be verified by any receiver.**
  `--webhook-secret` signed a canonical serialisation of the payload
  (`sort_keys=True`, compact separators) but then handed the *object* to
  `requests.post(json=...)`, which re-serialised it with its own separators
  and insertion order. The bytes that went out were therefore never the bytes
  that were signed, so a receiver hashing the body it received - the only
  thing it can hash - always computed a different digest and correctly
  rejected every notification. The body is now serialised exactly once and
  posted verbatim as `data=`, so the signed bytes and the sent bytes are the
  same bytes. Anyone who had given up on `X-COS-Signature` and stopped
  checking it should turn verification back on.

  `tests/test_webhook.py` asserted the header against a re-serialisation of
  `kwargs["json"]` - the parsed document, never the transmitted body - so it
  passed throughout and would have kept passing with the feature entirely
  broken. It now verifies over the bytes actually sent, and a second test
  asserts a signature does *not* verify against a modified body.

- **`refresh-data` now verifies where its data came from.** The refresh a
  monitoring host runs used to query OSV and the OpenCloud lifecycle page
  live and believe the answer on the strength of TLS and a few structural
  guards - the residual risk [ADR 0016](adr/0016-the-release-schedule-refreshes-itself.md)
  and [ADR 0017](adr/0017-the-advisory-database-refreshes-itself.md) both
  name outright, since a compromised or spoofed upstream page could inject
  false advisory data and nothing would notice. It now reads both documents
  from this project's own repository - the reviewed files a maintainer
  merged - and verifies a Sigstore attestation over the exact bytes,
  pinned to this repository's own signing workflow, before writing
  anything. There is no signing key to leak: the new
  `attest-security-data.yml` workflow signs with a short-lived certificate
  bound to its own identity, the same way `publish-pypi.yml` already
  attests the wheel. A signature that is present and wrong stops the
  refresh and leaves the previous files untouched; one that merely cannot
  be checked warns and falls back to the previous behaviour. Verification
  needs the new `signing` extra (`pip install
  check-opencloud-security[signing]`) - without it the refresh works as
  before, and says so. See
  [ADR 0027](adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

- **The webhook notifier's SSRF guard only checked IPv4 addresses.**
  `_resolve_webhook_address` resolved a webhook hostname with
  `socket.gethostbyname`, which only returns `A` records, while the actual
  delivery in `requests.post` resolves dual-stack. A hostname with a public
  `A` record and a private, loopback or link-local `AAAA` record therefore
  passed validation and could still be connected to over IPv6, and the
  DNS-rebinding recheck immediately before delivery had the same blind spot.
  Resolution now uses `socket.getaddrinfo` and validates every address a
  hostname answers with, IPv4 and IPv6 alike, and also unwraps IPv4-mapped,
  6to4 and NAT64-encoded IPv6 literals so a private IPv4 address cannot hide
  inside an IPv6 one either.

### Fixed

- **The "back to top" link never appeared on mobile browsers.**
  `back-to-top.js` read `window.innerHeight` live inside its scroll handler
  as the reveal threshold, but scrolling on a phone collapses the browser's
  own address bar mid-gesture, growing `innerHeight` at the same time as
  `scrollY`. That moving target could keep the link hidden well past the
  intended one screen of scrolling. The threshold is now measured once (and
  only re-measured on a genuine `resize`, such as an orientation change)
  instead of being read live on every scroll.

- **`publish-dockerhub.yml` pinned its actions to floating version tags**
  (`actions/checkout`, `astral-sh/setup-uv`, `docker/setup-qemu-action`,
  `docker/setup-buildx-action`, `docker/login-action`,
  `docker/build-push-action`) while every other workflow that handles
  secrets already pins to a commit SHA. This is the workflow that
  authenticates to Docker Hub, so it is now pinned the same way as the rest.

### Documentation

- **Verifying the webhook signature** now has a section in
  [`webhook-recipes.md`](docs/webhook-recipes.md): what `X-COS-Signature`
  contains, a receiver that verifies it, and why it has to hash the raw
  request body rather than a re-encoding of the parsed document. Notes that
  `hmac.compare_digest` belongs there instead of `==`, where to get the raw
  body in Flask and FastAPI, that the signature also covers the `slack` and
  `discord` bodies, and that a missing header on a receiver expecting one is
  a rejection rather than a pass.

- **`--webhook-secret` and `--ca-file` were missing from the CLI option
  table** in [`README.md`](README.md) despite both being implemented, and
  neither appeared in
  [`config/check-opencloud-security.example.yml`](config/check-opencloud-security.example.yml).
  Both now have a row and a commented example (`webhook.secret`,
  `scanner.tls_ca_file`).

- **Three hardening flags the guides never named.** Naming a check by its
  identifier is the convention every in-depth page follows, but
  `httpsEnforced`, `reverseProxyDetected` and `identityProviderDetected`
  appeared in no page under [`docs/`](docs/) at all, so an operator reading a
  result had nowhere to look them up.
  [`reverse-proxy.md`](docs/reverse-proxy.md) gains a section covering the
  first two - what each has to see to pass, why a closed port 80 counts as
  enforcing HTTPS, and why a well-run Traefik or HAProxy deployment can fail
  proxy detection with nothing wrong - and [`tls.md`](docs/tls.md) points at
  it, since `httpsEnforced` sits beside `httpsAvailable` conceptually but is
  decided at the proxy rather than in the TLS layer.
  [`authentication.md`](docs/authentication.md) gains
  `identityProviderDetected` as a sixth check: how the issuer is read from
  `/.well-known/openid-configuration` (including the redirect case), that
  nothing is ever submitted to find it, and that a failure is far more often
  a proxy not forwarding the well-known path than an instance with no
  sign-in.

- **Cross-links to [`what-is-opencloud.md`](docs/what-is-opencloud.md).** The
  new page was reachable only from the docs index and
  [`troubleshooting.md`](docs/troubleshooting.md), leaving it the one guide
  with no inbound link from [`README.md`](README.md). The sentence in the
  README explaining that an ownCloud or Nextcloud product name is refused
  rather than rated now links to it, as does the matching passage in
  [`opencloud_local_scan/README.md`](opencloud_local_scan/README.md), and
  [`status-php.md`](docs/status-php.md) links back to the page that tells the
  fork lineage in full.

## [1.14.1] - 2026-08-29

### Changed

- **Check catalogue order**: The catalogue page now lists OpenCloud's own
  hardening categories first, security headers (including CSP) after, and
  transport/TLS last.

### Removed

- **`installed`, `maintenanceMode` and `databaseUpgrade` checks**: Dropped
  the findings derived from `/status.php`'s `installed`, `maintenance` and
  `needsDbUpgrade` fields. OpenCloud's handler for that endpoint returns
  those three fields as hardcoded `true`/`false`/`false` literals rather than
  reading any live state, so none of the checks could ever fire - see [Why
  OpenCloud still answers `/status.php`](docs/status-php.md).

### Fixed

- **`actions/upload-artifact` in `supply-chain.yml`** was still pinned to
  v4.6.2, the last release built on GitHub's now-deprecated Node 20 runtime.
  Bumped to v7.0.1 (Node 24), pinned to its commit the same way every other
  action in the workflows already is. Every other pinned action was already
  on a Node 24 release.

## [1.14.0] - 2026-08-29

### Added

- **CAA record check (`tlsCaaRecord`)**: The built-in scanner now reports
  whether the scanned name has a DNS CAA record restricting which
  certificate authorities may issue for it. The lookup is dependency-free
  and only ever queries the system's own configured resolver - never a
  public one - so nothing new is sent to a third party.
- **Native Slack and Discord webhook formats**: `--webhook-format slack`
  (also accepted by Mattermost and the common Matrix webhook bridges) or
  `--webhook-format discord` posts the result already shaped for that
  receiver, so the adapter script in `docs/webhook-recipes.md` is no longer
  required for the common case. The default is unchanged.
- **`--format json`/`sarif`/`junit`**: one combined machine-readable document
  for every scanned host, for CI pipelines - a JSON array of the existing
  webhook payload shape, SARIF 2.1.0 for a code-scanning dashboard, or JUnit
  XML with one testsuite per host. The exit code keeps its Nagios meaning
  under every format.
- **IPv6 connectivity in the Docker setup wizard**: `docker/setup-wizard.py`
  now asks whether the deployment's containers have outbound IPv6
  connectivity (`COS_WEB_IPV6_ENABLED`, off by default, since Docker's
  default network has none). Left off, the built-in scanner still lists an
  instance's IPv6 addresses but skips dialling them for the IPv4/IPv6
  TLS-parity check, and the dashboard notes why instead of reporting the
  instance's IPv6 side as unreachable for a limitation of the deployment
  rather than of the instance.
- **The MCP endpoint is now a knowledge base as well as an execution layer**:
  two new resources, `catalogue` and `advisories`, publish the same
  hardening/check explanations and advisory database the `/catalogue` page
  renders - built from the same functions, so a resource can never disagree
  with the page about what a check id means. An agent can now explain a
  finding, or see what the scanner would catch, without submitting a scan.
- **`GET /agents.txt`**: a capability declaration in the
  [agents-txt.com](https://agents-txt.com) format, published under the
  filename some agent frameworks look for by convention. It names the MCP
  and WebMCP endpoints, declares `Authorization`/`Identity` only when the
  MCP endpoint itself requires a bearer token, and points at the discovery
  document and the OpenAPI/Arazzo contracts.
- **`GET /agents.json`**: the structured sibling the agents-txt.com
  convention recommends alongside `agents.txt` - the same document
  `/.well-known/ai.json` already serves, published again under the name the
  convention looks for.
- **`SearchAction` structured data on the homepage**: names the existing
  `/search` form so Google can offer a sitelinks search box, and
  **`BreadcrumbList` structured data on every `/documentation/{slug}` page**:
  draws the real home / documentation / guide trail those pages already sit
  in.
- **A short FAQ on `/how-it-works`**, in all four languages, with matching
  `FAQPage` structured data generated from the same catalogue keys the
  visible answers render from, so the two can never disagree.
- **`max-image-preview:large, max-snippet:-1`** added to the `robots` meta
  tag on every indexable page, opting back into the full-size thumbnail and
  snippet length Google has capped by default since 2019.

### Security

- **Stored XSS on the public `/catalogue` page via a feed-supplied advisory
  URL.** `catalogue.html` rendered `advisory.url` as an `href` with only a
  truthiness check, while the sibling `scan.html` template already guarded
  the same field with the `is safe_link` scheme check added when the daily
  OSV advisory refresh was wired in. A `javascript:` URL from a malicious or
  malformed upstream advisory entry could therefore execute in the page's
  own origin for any unauthenticated visitor who clicked the advisory link.
  `catalogue.html` now applies the same `is safe_link` guard.

### Fixed

- **`cspWithoutUnsafeInline` now also catches `unsafe-eval`**, and no longer
  mistakes a `style-src 'unsafe-inline'` for a script-execution weakness. The
  check used to fall back to a substring search over the *entire*
  `Content-Security-Policy` header when no `script-src` directive was
  present, so a policy with only `style-src 'unsafe-inline'` was wrongly
  flagged; it now reads `default-src` specifically, per CSP's own fallback
  rule, and also flags `'unsafe-eval'` in `script-src`/`default-src`, which
  undermines a CSP's XSS protection just as much as `'unsafe-inline'` does.
- **The `X-Frame-Options` check now accepts a CSP `frame-ancestors`
  directive as the alternative it already claimed to be**: the hardening
  catalogue's remediation text has always said "Send 'X-Frame-Options:
  SAMEORIGIN', or a CSP 'frame-ancestors' directive", but the scanner only
  ever checked the header, so an instance protected purely through
  `frame-ancestors` (the modern, browser-preferred mechanism) was reported
  as vulnerable to clickjacking. A wildcard `frame-ancestors *` still fails
  the check, since it does not restrict framing at all.
- **`cspWithoutUnsafeInline` no longer flags the standard `strict-dynamic`
  rollout pattern.** A `script-src` that pairs `'unsafe-inline'` with a nonce
  or a hash (e.g. `script-src 'nonce-xyz' 'strict-dynamic' 'unsafe-inline'
  https:;`) was reported as unsafe, but every browser that understands
  nonces ignores `'unsafe-inline'` in that case per the CSP spec - the
  keyword is only a fallback for browsers too old to understand the nonce.
  `'unsafe-eval'` gets no such exemption, since nothing about a nonce or hash
  makes `eval()` safe again.

## [1.13.0] - 2026-08-28

### Added

- **TLS cipher and certificate-policy findings**: The built-in scanner now
  flags a weak negotiated cipher suite and certificates with undersized RSA or
  EC keys or MD5/SHA-1 signatures. It records the measured key type, size and
  signature in the result while leaving either check absent when it cannot
  measure the necessary evidence.
- **Automatic updates in the Docker setup wizard**: `docker/setup-wizard.py`
  now asks whether the deployment's pulled images should update themselves
  (or takes `--auto-updates`) and adds a Watchtower service to the generated
  stack when they should - scoped by label to this stack's own containers,
  and pointed at the Docker socket detected for the user running the wizard,
  including the rootless socket under `/run/user/<uid>`.
- **The Docker setup wizard reuses an existing `.env`**: re-running it
  against a directory that already holds one reads the file back and offers
  every value as the default of its question instead of regenerating the
  deployment's credentials.

## [1.12.1] - 2026-08-27

## Fixed

- Fix YAML syntax error in Github actions workflow

## [1.12.0] - 2026-08-27

### Changed

- **Security and release-data safeguards**: Kept advisory ranges and release
  support facts monotonic during refreshes, and validate refresh pull requests
  against their relevant regression tests before review.
- **Search and agent discovery**: Kept query pages out of the sitemap and
  index, emitted valid localized JSON-LD only on public pages, and aligned the
  extended agent guide and discovery capabilities with the implemented API.
- **Documentation search intent**: Made generated OpenCloud Security Scanner
  guide titles and descriptions self-describing when reached directly.
- **Deployment and compatibility evidence**: Require an explicit public origin,
  pin the scheduled OpenCloud integration baseline by digest, and document
  candidate-image review rules.
- **Release operations and metadata**: Added the architecture runbook for
  rolling, production, and LTS releases; `COS_WEB_INDEX_META_TAG` now accepts
  a bounded, validated list of landing-page metadata pairs.
- **Configuration and Authentik guides**: Added directory references for the
  example scanner configuration and the MCP Authentik blueprint.
- **Docker setup documentation**: The setup wizard now leads the Docker Hub
  description, `docker/README.md`, `docs/webapp.md` and `webapp/README.md`, and
  every documented stack recipe carries the now-required
  `COS_WEB_PUBLIC_BASE_URL`, the Redis password and the internal network.
- **Redis hardening**: The Docker setup wizard and every shipped compose stack
  now support `COS_REDIS_PASSWORD` and keep Redis on an internal network with
  no published port, answering the "Redis does not require authentication and
  is not protected by network restriction" finding.

### Added

- **Redis operator guide**: `docs/redis.md` and `/documentation/redis` cover
  what the scan service keeps in Redis and for how long, authentication,
  network isolation, memory and eviction, health signals and troubleshooting.
- **`/.well-known/security.txt`**: An RFC 9116 document with a computed
  `Expires`, naming the project's security policy everywhere and an operator
  address only on the deployment the legal notice belongs to.

### Fixed

- **The Python version matrix actually tested one version**: `nox` installed
  no test dependencies and ran the outer environment's `pytest`, so every
  session reported the same interpreter. Each session now syncs into its own
  environment and asserts the interpreter before running the suite.
- **Python 3.10 compatibility**: `scripts/release_notes.py` and its test
  imported `tomllib`, which does not exist before 3.11. Both now read the
  project version without it.

## [1.11.4] - 2026-08-26

## Added
- **Legal Notice Badge**: Added an explicit Legal Notice link to the footer, 
  displayed exclusively when accessing the site via scan.okxo.de.

## [1.11.3] - 2026-08-26

## Changed
- **Documentation layout**: Removed redundant H1 tags.
- **Release versions**: Updated OpenCloud release versions to current

## [1.11.2] - 2026-08-26

### Added
- **WebMCP Protocol Support**: Added tooldescription and optional toolautosubmit
  declarative attributes to HTML forms, enabling AI agents to auto-discover and 
  interface directly with site features.
- **Input Parameters Context**: Added descriptive description attributes to all 
  security scanner form controls (target_url, release_track, output_format) for 
  richer AI agent understanding.
- **Structured Data (Schema.org)**: Implemented JSON-LD WebApplication schema 
  metadata within the main template <head> to improve search engine rich snippets 
  and AI crawler categorization.

## [1.11.1] - 2026-08-26

### Added

- **llms-full.txt Documentation**: Introduced a comprehensive, self-contained 
  Markdown documentation file designed for Large Language Models (LLMs) with  
  extended context windows.

### Changed

- **Updated /llms.txt layout**: follow standard Markdown guidelines, including 
  blockquote summaries, explicit link structures, and references to full 
  documentation.

## [1.11.0] - 2026-08-26

### Added

- **Browser agents can use the page already in front of them.** The landing
  page registers a WebMCP scan tool, result pages register status and export
  tools for their current UUID, and `/llms.txt` maps the API, workflow, MCP,
  and WebMCP surfaces. Tool schemas come from the same server-side catalogues
  as the rendered controls, every execution uses the existing JSON API, and
  the front end's AI page documents the tools and their security boundary.
- **Deployments can add one optional landing-page meta tag.**
  `COS_WEB_INDEX_META_TAG=name=content` is passed through both Docker Compose
  stacks and rendered as escaped `name` and `content` attributes. Raw HTML,
  reserved page metadata, and named surveillance-platform tags are refused.
- **False results have a direct reporting path.** Completed result pages link
  to the repository issue tracker for false positives and false negatives,
  without putting the scan UUID or target into the URL.
- **Recognised identity providers link to their advisory database.** Scan
  overviews for Keycloak, Authelia and Authentik point to the provider's
  official GitHub Security Advisories page. The result reserves a version
  field but reports that it is unavailable rather than guessing, because none
  of the three exposes a product version without authentication.

### Changed

- **HTML action routes now negotiate structured responses.** A request for
  `application/json`, or a form choosing `output_format=json`, receives the
  same scan record or acceptance payload as the JSON API. The frontend CSS
  also drops selectors that no template or script can reach.
- **The MCP switch governs both browser and server tools.** Turning
  `COS_WEB_ENABLE_MCP` off now removes WebMCP registration from the landing
  and result pages as well as disabling `/mcp`.

### Security

- **Translated HTML now has an explicit trusted boundary.** Only
  source-controlled catalogue markup is treated as renderable HTML, while
  every interpolated placeholder is converted to text and escaped.

## [1.10.0] - 2026-08-25

### Added

- **The resolved addresses are part of the result.** Every scan now records
  the IPv4 and IPv6 the instance's name pointed at while it ran, as
  `addresses` in the result document, and a web result page prints them under
  **Resolved to** in the overview. A name that does not resolve, or a scan of
  a bare address, reports empty lists rather than an error, and the block
  never moves the rating - it is there because "it answers on the address you
  retired last month" explains a surprising number of surprising results. The
  addresses the web application already validated are reported unchanged, so
  the document names what the scan actually dialled rather than a second
  lookup's answer.
- **A one-liner for whoever would rather not use the website.** The published
  image `okxo/opencloud-scanner` carries both entry points, so
  `docker run --rm --entrypoint check-opencloud-security
  okxo/opencloud-scanner:latest --host opencloud.example.com` runs the same
  check on your own machine, with no rate limit, no queue and nobody else
  learning which instance you look after.
  [`docs/docker-oneliner.md`](docs/docker-oneliner.md) collects the JSON
  variant, waivers, release tracks, private networks, a shell function and
  the container-free `uvx` form.
- **A "Docker" tab in the web interface.** The new page at `/cli` shows that
  one-liner where the hesitation actually happens - in the primary
  navigation, on the site being asked for an address - and links the full
  documentation. It is a public, indexable page like the other explanations.
- **A "Grades" tab explains the real rating scale.** The new `/grades` page
  takes its letters from the plugin's `RATE_MAP` and its finding ceilings
  from the scanner, explains why the 0-5 scale has no `B`, and shows what
  `A+`, `A`, `C`, `D`, `E` and `F` mean, what holds each one down and how the
  ordered remediation plan helps move an instance upward.
- **A local "Docs" tab for the CLI.** `/documentation` collects the quick
  start, the two entry points, everyday flags, configuration precedence and
  monitoring patterns in the web interface. Every full operator guide below
  it is a separate local HTML page generated from `README.md`,
  `opencloud_local_scan/README.md` or `docs/`; CI rejects stale generated
  pages, while production serves plain checked-in templates and carries no
  Markdown parser.
- **A small static search now reaches all public guidance.** The header field
  opens `/search`, where a same-origin release index is filtered in the
  browser. The manifest can read public templates only, and the release
  workflow is the sole automatic writer, so result pages, UUIDs, submitted
  addresses and exports have no path into the index.
- **The complete web interface now speaks four languages.** Stable string
  catalogues cover English, German, Spanish and French across navigation,
  forms, progress, results, grades, search and page metadata. The browser's
  weighted language preference is selected automatically, while an accessible
  switcher stores an explicit choice in an `HttpOnly`, `SameSite=Lax` cookie
  and works without JavaScript. Generated guide bodies remain English with a
  localized notice; their chrome and release-built search indexes follow the
  selected language. API, MCP and export contracts remain English, and remote
  scan evidence remains verbatim.

### Changed

- **The frontend header stays on one line.** Its brand is now the shorter
  *Security scan for OpenCloud*, controls and links do not wrap, and the
  compact menu takes over at tablet and narrower desktop widths before the
  translated navigation can split across lines. The landing-page and
  completed-result screenshots now show this header and the language switcher.
- **The web interface now uses the Halo design system.** Space Grotesk,
  Inter and JetBrains Mono are self-hosted with their licences; cold frosted
  panes float over an iris-and-magenta aurora, the target address is a
  full-width command bar, and every transition has a reduced-motion answer.
  Light and dark schemes use separate contrast-checked tokens, the artwork
  and OpenGraph image match them, and `DESIGN.md` explains how to extend the
  system without turning it into a collection of one-off styles.
- **Build contexts and source archives carry less development material.**
  Docker now excludes ADRs, guides, screenshots, deployment sources and
  maintainer-only files that neither image copies or runs; Git archives omit
  ADRs, screenshots and agent/design guidance as well. Both Dockerfiles still
  use explicit `COPY` lists, and the web release bundle remains an explicit
  allow-list, so runtime templates, generated Docs pages and licences stay in
  their intended artefacts.

### Security

- **A scan submission is now a constrained instance base address.** The
  browser gives immediate feedback and the server enforces the boundary: a
  target may have an `http` or `https` scheme, a hostname, an optional port
  and a plain subfolder path, but no query string, fragment, credentials,
  path parameters, escapes, traversal, whitespace or request-control
  characters. The scanner chooses every OpenCloud endpoint itself, so
  nothing appended by a visitor can become an
  outgoing payload or parameter. Redirects sent by the instance remain
  usable and are independently revalidated before they are followed.
- **The documented demo accounts are now a critical finding.**
  `IDM_CREATE_DEMO_USERS` fills OpenCloud's built-in identity management with
  five accounts - `dennis`, `margaret`, `alan`, `lynn`, `mary` - whose
  passwords are printed in OpenCloud's own documentation, and `dennis` is an
  administrator. When the instance signs users in with its *own* provider, the
  scan now asks `/ocs/v1.php/cloud/user` with each documented pair;
  `demoUsersDisabled` fails at severity `critical` when one is accepted, which
  caps the rating at `D` and puts the account names in the alert line.
  Nothing is guessed - only the published defaults are sent, and only to the
  instance's own provider, never to an external Keycloak or Authentik - and an
  endpoint answering unauthenticated requests reports nothing rather than
  inventing a demo user. `--debug` and `describe_hardening()` explain the
  finding and name `IDM_CREATE_DEMO_USERS=false`, along with the fact that
  turning it off does not delete accounts that already exist.
- **The admin documentation now drives three more remote checks and closes a
  password-policy blind spot.** Wildcard iframe message origins are `high`,
  delegated authentication without a trusted origin is `critical`, and a
  matching OpenCloud listener exposed directly on port 9200 is `high`.
  Capabilities that explicitly show a disabled password policy now fail
  `passwordPolicyEnforced` instead of silently omitting it. A Let's Encrypt
  staging issuer also names the exact production-certificate fix in the
  existing `tlsTrusted` finding. The audit deliberately does not guess admin
  passwords, probe sibling products or penalise OpenCloud endpoints that are
  public by design.

### Fixed

- **Signed reports are deployable from every supported setup path.** The
  Docker stacks and setup wizard now expose `COS_WEB_EXPORT_SIGNING_KEY`, the
  unattended wizard generates it, PDF/SARIF/JSON signatures are each tested
  against their exact downloaded bytes, MCP export results retain the
  signature header, and the release bundle now includes
  `scripts/verify_export.py`.

## [1.9.3] - 2026-08-24

### Added

- **A real OpenGraph share image.** `og:image` now points at a hand-drawn
  1200x630 PNG (`frontend/static/img/og-image.png`, rendered from the
  `og-image.svg` beside it) with `og:image:type`, `og:image:width` and
  `og:image:height` metadata, because most crawlers and chat clients will not
  draw the SVG the pages previously shared.

### Changed

- **Body type is now Inter, self-hosted.** The web application serves the
  five weights it uses from `/static/fonts/` (SIL OFL 1.1, license beside the
  files) with the system sans as the fallback while the file arrives. The
  serif display face and the monospace dossier labels still come from the
  reader's own system stack, and nothing is fetched from a font service.
- **The accent colour is a warm ember in daylight.** The teal accent became a
  deep orange in the light scheme (`#c2410c`) and now carries the primary
  action button as well as the live marker and the assurance row, so the one
  thing a page wants done is the first thing the eye finds; the dark scheme
  keeps the clear teal (`#5eead4`) it always had. The logo, hero and expired
  artwork and the backdrop aurora were re-tinted to match.

## [1.9.2] - 2026-08-21

### Fixed

- **Grid height fixed. **

## [1.9.1] - 2026-08-21

### Changed

- **The web application has a new frontend design.** The whole design system
  in `frontend/static/css/app.css` was rebuilt as a field report: serif
  display type against warm bone paper, monospace dossier labels with a drawn
  leading rule, hairline rules instead of filled chrome, frosted-glass cards
  that diffuse the backdrop they float over, and a reticle motif that frames
  the scan form with registration brackets. The backdrop is a faint
  engineering grid over a quiet aurora with a grain of baked-in noise, the
  landing page states its promises as a ruled specification row, and a tiny
  `reveal.js` arrives blocks as they scroll into view - decoration only, so
  the page reads complete with scripting blocked. Waiting is theatre now
  too: a beam travels the progress card while a scan runs, and when the
  result is in, the page settles, announces the report and falls away before
  the rendered answer arrives. The automatic light and dark modes stay,
  driven as before by one token list and its `prefers-color-scheme: dark`
  counterpart, reduced motion still turns every animation off (and skips the
  hand-off entirely), and the artwork was redrawn to match: the hero is a
  technical instrument drawing with the same hand-drawn, two-scheme
  discipline as before.


## [1.9.0] - 2026-08-21

### Added

- **Monitoring hosts can refresh reference data without upgrading the plugin.**
  `check-opencloud-scanner refresh-data` validates and atomically writes the
  release schedule and advisory database to an operator-selected cache
  directory. A systemd service and daily timer are included; failed or unsafe
  downloads leave the previous files untouched.

- **Result exports can be signed.** When `COS_WEB_EXPORT_SIGNING_KEY` is set,
  JSON, CSV, SARIF and PDF downloads carry an `X-COS-Signature` HMAC-SHA256
  header. `scripts/verify_export.py` verifies the exact downloaded bytes.

- **Supply-chain checks in GitHub Actions.** Pull requests, pushes to `main`
  and a weekly run now audit every locked core, web and MCP dependency with
  `pip-audit`, publish a CycloneDX SBOM and attest that SBOM with GitHub's
  short-lived Sigstore identity. Release artifacts and the web bundle use
  pinned attestation actions as well, and dependency-review now pins its
  action commit instead of a mutable tag. See [CI documentation](docs/ci.md).

- **A real-container integration test now exercises the scanner against an
  initialized OpenCloud image.** It is opt-in locally, runs weekly in CI,
  cleans up its disposable Docker resources, and skips clearly when Docker or
  the selected image/version is unavailable.

- **The advisory database is refreshed daily, in CI and at runtime.** Until
  now nothing wrote `opencloud_local_scan/data/vulnerabilities.json`: it
  shipped with no active advisory in it, there was no script to regenerate it
  and no workflow to run one, so every advisory published against OpenCloud
  since the file was written was invisible to every deployment - and a visitor
  scanning an affected instance was told it was fine. Two things now keep it
  current. `.github/workflows/vulnerability-db.yml` runs
  `scripts/update_vulnerability_db.py` against the OSV query API every day and
  opens a pull request when the answer has changed, and the web application's
  worker asks the same feed once a day (and at startup) and rates queued scans
  against what it last accepted, so an advisory published after an image was
  built still reaches the people scanning with it. Both use one reader,
  `opencloud_local_scan/advisory_source.py`. A refresh only ever adds an
  advisory, so a feed answering with an empty list changes nothing and a
  hand-written entry survives; an advisory with no version bounds is never
  believed, because it would match every release there has ever been; an
  answer with an absurd number of advisories is refused whole; and any failure
  leaves the database exactly as it was. Nothing is written to disk at
  runtime. `COS_WEB_ADVISORY_REFRESH=false` turns it off for a deployment with
  no outbound access, `COS_WEB_ADVISORY_REFRESH_URL` points it at a mirror,
  and `/healthz` reports how many advisories the deployment would rate against
  and when it last asked. See
  [ADR 0017](adr/0017-the-advisory-database-refreshes-itself.md).

- **The web application refreshes the OpenCloud release schedule itself, once
  a day.** The schedule that decides whether a line is still supported is
  written by CI and frozen into the image, so a service that has been up for
  six weeks rates instances against a six-week-old picture of the world: it
  calls last week's release "ahead of the schedule" and a line that expired
  since the build "still supported". The worker now re-reads the published
  lifecycle page once a day - and at startup, so a fresh deployment does not
  wait for the small hours - and keeps the result in Redis, where every queued
  scan picks it up. A refresh can only add knowledge: a page that has lost a
  release line is refused, because a missing line would turn an end-of-life
  instance into an unknown one; an unreachable, redesigned or truncated page
  leaves the previous schedule exactly as it was; and a newer bundled file
  after a redeployment wins over whatever is in Redis. Nothing is written back
  to the repository. `COS_WEB_SCHEDULE_REFRESH=false` turns it off for a
  deployment with no outbound access, `COS_WEB_SCHEDULE_REFRESH_URL` points it
  at a mirror and `COS_WEB_SCHEDULE_REFRESH_HOUR` moves the daily read;
  `/healthz` reports the schedule's date and the last successful read. The
  plugin is unchanged - a check running every few minutes must not become a
  documentation fetch. See
  [ADR 0016](adr/0016-the-release-schedule-refreshes-itself.md).

- **A setup wizard for the Docker deployment**, `docker/setup-wizard.py`. It
  asks, one question at a time, for the settings a deployment of the web
  application actually has to decide - what it is reachable at, how hard it
  may scan, what it may reach, who may erase a result, whether an agent may
  use `/mcp` - explains each one and shows an example answer, and then writes
  a commented compose file with the non-secret answers inline and a `.env`,
  created owner-readable only, holding the credentials that file refers to as
  `${NAME}`. That split is the point of it: a compose file is something an
  operator commits and pastes into a ticket, and a purge token is not. It
  generates the credentials nobody should invent by hand, warns about the
  combinations the service itself refuses to start on, offers a `private`
  preset for an estate scanning its own instances, runs on the standard
  library alone so it works on a host that has Docker and nothing else, and
  refuses to write over the compose files that ship with the project. It is
  separate from `check-opencloud-security --configure`, which configures a
  monitoring check rather than a container, and shares no code with it. It
  travels in the web application's release tarball, because whoever unpacks
  that is setting up exactly the deployment it asks about.

- **The setup wizard can provision Authentik**, rather than handing back a
  form of OAuth homework, and `--with-authentik` is how it is asked to. That
  adds Authentik and its database to the generated stack, derives the issuer,
  the JWKS URL and the audience from the answers, generates the credentials
  into `.env`, writes the provisioning blueprint beside the compose file that
  mounts it. It is a separate answer from `--sign-in`, which turns the guard
  on and asks for the issuer, the audience and the keys of whatever the estate
  already runs - the usual case, and the one that adds no containers. Neither
  flag implies the other, deliberately: provisioning a provider leaves `/mcp`
  open, so an operator can bring Authentik up, log in and mint a token before
  anything starts being refused, and `--sign-in` is what closes it. Nothing of
  Authentik reaches a deployment that did not ask for it.

- **Mail settings for Authentik**, in the wizard and in the stack that ships
  here. `docker-compose.authentik.yml` now carries `AUTHENTIK_EMAIL__*` on
  both Authentik services - the server sends the test message, the worker
  sends everything else, so configuring one and not the other works until the
  moment it matters - and `authentik-env.sh` writes the names into `.env`
  commented out. The wizard asks for them (`--smtp-host`, `--smtp-port`,
  `--smtp-username`, `--smtp-from`, `--smtp-security`, `--smtp-timeout`) and
  models STARTTLS and implicit TLS as one choice, because `USE_TLS` and
  `USE_SSL` both true is a session that negotiates neither. There is
  deliberately no `--smtp-password`: the wizard reads it from
  `AUTHENTIK_EMAIL_PASSWORD` in the environment or asks for it, and writes it
  into `.env` alone. An identity provider that cannot send a password recovery
  locks out the one account it starts with, and the way back in is a database
  edit. `docs/authentik.md` documents every variable.

- **MCP prompts**, so a client can offer the job rather than a menu of verbs.
  Six of them, each the task somebody actually asks for: `audit_instance`
  ("audit this instance and write a remediation plan"), `audit_estate`,
  `explain_scan_result`, `triage_findings`, `review_transport_security` and
  `check_release_support`. They are advertised as an MCP capability, listed
  over `prompts/list` and named in the `mcp.prompts` block of
  `/.well-known/ai.json` so an agent can see the tasks before it connects.
  New module `webapp/prompts.py` holds the wording and composes it from the
  notes and constants in `webapp/workflows.py`, so a prompt cannot quote a
  poll interval or a timeout the workflow layer does not have; the prompts
  name tools rather than endpoints, because the tools are what carry the
  limits. ADR 0014 records the decision and why a prompt decides nothing.
- **Transport security beside the grade.** The result page now shows the
  negotiated TLS version, the certificate's expiry date with the days left or
  gone, and whether the chain is complete and trusted, in the overview next to
  the score - the questions somebody scanning their own instance most often
  came for, previously answered only at the bottom of the page. Each fact
  takes its colour from the pass or fail the scanner already recorded for that
  check, so the page cannot disagree with the alert the same scan produced,
  and an instance that answered no handshake shows nothing rather than a row
  of dashes.
- **An optional sign-in in front of the MCP endpoint.** `/mcp` is open unless
  an operator says otherwise, which is what the public service wants; a
  deployment running this for its own estate can now set
  `COS_WEB_MCP_AUTH_ENABLED` and an issuer and have it become an OAuth 2.0
  resource server. A bearer token is verified offline against the provider's
  published keys - signature, issuer, audience, expiry and any required
  scopes, asymmetric algorithms only - and a request without one gets a 401
  whose `WWW-Authenticate` names the RFC 9728 metadata document at
  `/.well-known/oauth-protected-resource/mcp`, which names the provider.
  `/.well-known/ai.json` reports the same under `mcp.authentication`, so an
  agent knows before it connects. This service issues no token, stores none
  and holds no account, and a sign-in buys an agent nothing else: the client
  rate limit, the target cooldown, the SSRF guard and the queue are identical
  signed in. A deployment that asked for a sign-in it cannot enforce refuses
  to start rather than serve the endpoint open. New settings
  `COS_WEB_MCP_AUTH_ENABLED`, `COS_WEB_MCP_AUTH_ISSUER`,
  `COS_WEB_MCP_AUTH_AUDIENCE`, `COS_WEB_MCP_AUTH_JWKS_URL`,
  `COS_WEB_MCP_AUTH_RESOURCE_URL` and `COS_WEB_MCP_AUTH_SCOPES`, and a new
  module `webapp/mcp_auth.py`. ADR 0015 records the decision.
- **A complete signed-in stack**, in `docker/docker-compose.authentik.yml`:
  the web application, the worker, Redis, Authentik and Authentik's own
  PostgreSQL (`postgres:18.6-alpine`), in one file and one command. It is a
  stack of its own rather than a Compose profile, because Compose validates a
  required variable in every file it reads and a profile would break
  `docker compose up` for everybody who never wanted it. **The sign-in follows
  the endpoint**: `COS_WEB_MCP_AUTH_ENABLED` is `${COS_WEB_ENABLE_MCP:-true}`,
  so bringing this stack up means `/mcp` requires a token and turning the
  endpoint off turns the sign-in off with it, with no combination that leaves
  the endpoint open by accident. `docker/authentik-env.sh` writes the five
  secrets it needs into `docker/.env`, once and without overwriting.
  Authentik itself has no Alpine image and is published Debian-based only.
  It needs no Redis, and does not get the Docker socket the upstream compose
  file hands its worker. Nothing in the code knows the name: any provider
  publishing signed JWTs and a JWKS works.
- **The OAuth2 provider provisions itself**, from
  `authentik/blueprints/opencloud-scanner.yaml`, which Authentik's worker
  applies on the first start: the provider, its signing key, the four scopes
  and the application whose slug becomes the issuer. Every entry is
  `state: created`, so it provisions once and leaves later operator edits
  alone. The client ID and secret come from `docker/.env`, which is also where
  the web application reads the audience - so both sides agree without
  anything being copied between them.
- **New guide `docs/authentik.md`** covering the one-command stack, what the
  blueprint created and how to change it, getting a token, the reverse-proxy
  trap where a rewritten `Host` gives every token an issuer nobody accepts,
  and the backup and restore - which are the operator's to run, because
  Authentik has no built-in backup.

### Changed

- **The lifecycle page has one parser, and it ships in the wheel.** The
  scraping that lived in `scripts/update_release_schedule.py` moved to
  `opencloud_local_scan/schedule_source.py` so that CI and the web
  application's daily refresh cannot drift apart about what the documentation
  says. The script keeps everything that is about the repository: the
  checked-in `release_schedule.json`, the generated README block and the CLI.

- **The purge credential moves out of `Authorization` when the MCP endpoint
  requires a sign-in.** `erase_instance_data` reads it from
  `X-Purge-Authorization` instead, with no fallback: with authentication on,
  `Authorization` carries the agent's identity token, and reading one as the
  other would compare a credential against a credential and answer 401 for a
  reason nobody could see. Unchanged on a deployment without a sign-in, which
  is every deployment until an operator turns one on.

- **A release newer than the bundled schedule now says so, and still costs
  nothing.** The release schedule that ships inside the package is a snapshot
  of a page that keeps moving, so an instance patched the week after a release
  of this project is routinely newer than the file being used to judge it.
  That was already never held against it - no `F`, no upgrade pointing
  backwards - but it was also never mentioned, which left an operator reading
  a support window worked out from data older than their own instance with no
  way to tell. A version ahead of the newest release recorded for its line, or
  on a line newer than every line on record, now sets `scheduleStale` in the
  `lifecycle` block along with `scheduleUpdated`, `scheduleSource` and a
  `scheduleNote` that says plainly that the schedule is probably out of date,
  that this is not counted against the instance, and where the authoritative
  page is. The plugin prints it as a `Release schedule:` line, the result page
  shows it beside the release track with a link, and an MCP tool passes it on
  as `scheduleNote` so an agent does not present a stale verdict as settled.
  Regenerating the schedule, or upgrading the package, clears it. A line that
  genuinely expired stays expired: patching inside a dead line does not reopen
  it, and the note explains the data rather than overturning the verdict.

### Security

- **DNS rebinding protection now pins validated scan connections.** Web scans
  dial the addresses accepted by the SSRF resolver while preserving the
  original hostname for HTTP Host and TLS certificate validation. Redirects
  are validated and pinned before each hop as well.

- **MCP OAuth now requires secure provider transport.** When authentication is
  enabled, issuer and JWKS URLs must use HTTPS; only explicit loopback URLs
  remain available over HTTP for local development.

- **An advisory affecting several release lines no longer passes half of
  them.** `GHSA-vf5j-r2hw-2hrw` - a path traversal through public links,
  rated high - was fixed in `4.0.3` **and** in `5.0.2`, published as one
  record with two disjoint affected ranges. The OSV parser read the first
  range and stopped, so an instance on `5.0.0` or `5.0.1` was reported as
  unaffected: a false pass on a live vulnerability. An advisory now carries
  every range it affects, and a match reports the fix belonging to the line
  the scanned instance is actually on, so a `5.0.1` instance is told to
  upgrade to `5.0.2` rather than to a release that fixes nothing for it.

- **An advisory with no version bounds is refused rather than believed.** A
  range that is open at both ends matches every version there has ever been,
  and public feeds do publish that shape - the Go vulnerability database
  records the advisory above as `introduced: "0"` with no fix. Ingesting one
  would have reported every OpenCloud instance in the world as vulnerable,
  which is how a security check loses the trust that makes anybody act on it.
  Such an entry is now dropped where a feed is parsed, so the guard covers
  `--vulnerability-feed` and a mirrored file as much as the web application,
  and a stored document that slipped one through is refused when it is read
  back.

- **A sign-in on `/mcp` with no audience now refuses to start.** An `aud`
  claim that is never compared is not a weaker check than one that is: on a
  provider that serves more than this service - which is what an identity
  provider is for - every application behind it is issued tokens by the same
  issuer and signed with the same key, so an unchecked audience made any one
  of those tokens a key to this endpoint. `COS_WEB_MCP_AUTH_AUDIENCE` is
  therefore required whenever `COS_WEB_MCP_AUTH_ENABLED` is on, alongside the
  issuer, the resource URL and HTTPS, and a token carrying no `aud` at all is
  refused rather than waved through. The verifier fails closed as well as the
  startup check, so one built without an audience accepts nothing. The stack
  in `docker-compose.authentik.yml` already set the value and is unaffected;
  a deployment that left it empty has to name the client ID its agents
  authenticate as. The setup wizard asks for it as a required answer.

- **`export_scan` says whose words it is carrying.** Every other MCP tool
  passes the scanned instance's strings through a sanitiser and returns an
  `untrusted` block naming them; an export returned the rendered document
  untouched and unlabelled, so a hostile instance's prose reached a model as
  ordinary tool output, in a session that also has a destructive tool in it.
  An export cannot be flattened the way a summary field is without ceasing to
  be the file it claims to be, so it is labelled instead: the answer carries
  the same `untrusted` block, and one too large to hand back inline comes with
  `truncated: true` and the URL to fetch rather than a context window's worth
  of somebody else's text. A structured export past the bound is withheld
  whole, because half of a JSON document is not JSON.

- **The action that publishes the Docker Hub description is pinned to a
  commit.** `peter-evans/dockerhub-description` was used at a mutable `v5`
  tag while holding `DOCKERHUB_TOKEN`, so whoever could move that tag could
  have had the credential. It now names a full SHA with the version in a
  comment beside it, the way the release workflow already pins its own
  third-party action.

### Documentation

- **How to let somebody use the MCP endpoint, and how they sign in.**
  `docs/authentik.md` gains two sections and the point of the first one is a
  default worth knowing: an application with no bindings in Authentik is one
  every account in the directory can use, so the page now walks through the
  group, the binding, the user, the password recovery and the service account
  an agent gets instead of a person's credentials - and says plainly that the
  scan service reads none of it. The second replaces a single `curl` with the
  three ways a caller actually gets a token, including the one that surprises
  everybody who has used another provider first: Authentik does machine-to-
  machine by *username and app password*, not by client ID and client secret.
  It ends where it should, calling `/mcp` with the token and reading the
  claims when it is refused, and the troubleshooting table gained the failures
  that go with all of it.

## [1.8.0] - 2026-08-20

### Added

- **A remediation planner**, answering "what gets you to A+" rather than only
  "what is wrong". The rating already records which finding held it down and
  by how much, so replaying that arithmetic with one finding removed at a time
  gives an ordered fix list with the grade each step would reach - including
  the update step, because fixing findings can never lift a rating above what
  the installed version allows. It is derived from the result document and
  stored nowhere new. New module `opencloud_local_scan/remediation.py`, a
  `remediationPlan` key in every scan result, a section on the dashboard, the
  plan in the CSV, SARIF and PDF exports, a `--debug` block in the plugin, a
  `planRemediation` Arazzo workflow and a `plan_remediation` MCP tool.
- ADR 0012 records why the plan is derived from the rating rather than
  modelled beside it, and why it is stored nowhere.
- Remediation text for every finding the extra-check pass can report -
  `tlsTrusted`, `directoryListing`, `maintenanceMode`, the `exposed:`,
  `authentication:`, `debugEndpoint:`, `debugPort:` and `versionDisclosure:`
  families and the rest. Until now `describe_hardening()` explained the
  hardening flags and the headers but answered "No description is available"
  for exactly the checks that cap a rating, which left the one part of a
  report an operator has to act on as the one part that said nothing.
- A Model Context Protocol endpoint at `POST /mcp`, so an AI agent can run the
  same checks a browser can. Six tools, one per user-level task -
  `scan_instance`, `scan_instances`, `get_scan_result`, `plan_remediation`,
  `export_scan` and `erase_instance_data` - and three resources exposing the
  OpenAPI, Arazzo and discovery documents. The tools call this application's own HTTP API in
  process, so an agent meets exactly the same SSRF guard, rate limits and
  purge authorisation; `erase_instance_data` is marked destructive and takes
  its credential from the request headers, never from a tool argument. Needs
  the new optional `mcp` extra, and is off when it is not installed. See
  [ADR 0011](adr/0011-mcp-is-an-execution-layer-not-a-second-implementation.md).
- `GET /.well-known/ai.json`, a discovery document naming the OpenAPI schema,
  the Arazzo workflows, the MCP endpoint, the usage limits worth respecting
  and the link to self-hosting. It is an application-level convention rather
  than a registered standard, and it exists so that an agent starting from
  nothing but the origin needs one request to find everything else.
- `webapp/workflows.py`, the single place the workflow semantics live: the
  poll interval and attempt ceiling, the submit retry count, which statuses
  are terminal, and the prose explaining each of them. The Arazzo document is
  rendered from it and the MCP tools execute it, so the described behaviour
  and the executed behaviour are the same code.
- Discovery hints in the head of every page - `rel="service-desc"`,
  `rel="arazzo"` and `rel="ai-discovery"` - and a **For AI agents** section on
  `/api` linking the same four addresses as ordinary clickable links.
- `COS_WEB_ENABLE_MCP` (default `true`) and `COS_WEB_MCP_ALLOWED_HOSTS` for
  the `Host` values the MCP endpoint accepts.
- `GET /sitemap.xml` and `GET /robots.txt` in the web application, both
  generated rather than kept as files. The sitemap lists the landing page and
  the four explanations, and takes each `lastmod` from the template that
  renders the page, so it cannot drift from the routes that exist. Neither
  mentions a result: `robots.txt` disallows `/scan/`, `/api/`, `/mcp` and the
  health probe, while explicitly allowing the machine-readable documents.
- `COS_WEB_PUBLIC_BASE_URL` sets the origin used in the canonical links and
  the sitemap. Behind a proxy the service only sees its own internal address
  and would otherwise publish URLs nobody outside can reach.
- `COS_WEB_ALLOW_INDEXING` (default `true`) decides whether search engines may
  index the five public pages. Turning it off restores the previous behaviour
  in full: a flat `robots.txt`, a 404 for the sitemap and `noindex` everywhere.
- Every page now carries a canonical URL, platform-neutral OpenGraph metadata
  and a title that names the service. See
  [ADR 0009](adr/0009-public-pages-indexable-results-never.md).

- **Transport security is now inspected in detail**, in a new module
  `opencloud_local_scan/tls.py`. The check used to end at "the handshake
  worked, the certificate is trusted, it expires on this date"; it now also
  reports the negotiated protocol and cipher, whether the server still accepts
  a deprecated one, whether the certificate actually covers the name it was
  asked for, whether the chain it presents is complete, whether its lifetime
  stays inside the 398 days browsers accept, and whether an OCSP response is
  stapled to the handshake. Five new findings - `tlsDeprecatedProtocol`,
  `tlsHostname`, `tlsChain`, `tlsCertificateLifetime` and `tlsOcspStapling` -
  are explained in the hardening catalogue like every other one.
- A `tls` block in the result document carries the measurements behind those
  findings: the protocol and cipher, the certificate's subject, issuer,
  validity window and remaining days, its names, the chain length, and what
  the deprecated-protocol and stapling probes found. It is on the dashboard as
  a **Transport security** card, in the JSON, CSV, SARIF and PDF exports, in
  the `TlsDetail` schema in `/openapi.json` and in the MCP result view.
  **A measurement that could not be taken is absent, never a pass**: `null`
  means "not determined", so a check the platform or the server made
  impossible is left out rather than quietly counted in the instance's favour.
  See [ADR 0013](adr/0013-transport-security-is-measured-not-assumed.md).

### Changed

- `/openapi.json` and `/arazzo.json` are now always public, at stable paths
  and without authentication. `COS_WEB_ENABLE_DOCS` governs only the browsable
  `/docs` and `/redoc` pages, which is what it was really protecting: those
  relax the content policy to render, while a JSON document does not. A
  description nobody can fetch describes nothing. See
  [ADR 0010](adr/0010-machine-readable-descriptions-are-always-public.md).
- The OpenAPI document is now written rather than inferred, and describes the
  API as it actually behaves. The generated one declared a form body where
  scan creation takes JSON, `200` where it answers `202 Accepted`, and empty
  schemas where a client needed the shape of a result. Every response now has
  a named schema mirroring the implementation field for field - the uuid a
  caller needs, the scan record with its state, `done`, summary and available
  exports, the batch's accepted and rejected lists, the purge receipt and the
  health body - and every description says what an agent should do with a
  status: `409` on an export means *not yet*, `404` means *never*.
- The Arazzo workflows now describe the real lifecycle. `awaitScanResult` is a
  new shared workflow that polls until `done`, stops immediately on a 404
  because an unknown or expired uuid never becomes known, and gives up after a
  bounded number of attempts. `scanManyInstances` no longer passes batch uuids
  into a workflow expecting a `target_url`; it waits on the accepted uuids and
  does not retry a target the backend rejected. `eraseInstanceData` documents
  the authorisation, the receipt, the counts and the signature.
- The header navigation collapses behind a menu button on narrow screens. Six
  links and the brand line did not fit across a phone, so the last entries
  could only be reached by scrolling the page sideways. The collapsed layout
  is switched on by `nav.js` itself, so with scripting blocked the links stay
  on the page and wrap onto a second row.
- `scripts/check_documentation_links.py` no longer trusts a status code on
  `docs.opencloud.eu`. It is a single-page application, so an address that no
  longer exists answers `200` with the application shell and only renders
  "Page not found" once a browser gets to it - which is why three dead links
  sat in the catalogue with the checker reporting everything healthy. A
  `/docs/` address is now checked against the site's own `sitemap.xml` as
  well. The checker also imports the hardening catalogue instead of only
  reading source text, because a URL long enough to be split across two string
  literals is invisible to a regular expression, and those are the longest
  links this project documents.
- The landing page, the form, the progress track and the result dashboard now
  hold their shape below 640px: full-width buttons, a smaller dial, a stacked
  footer and no element wider than the viewport.
- The landing page and the four explanations are now indexable; a result page
  is not, and never can be. It carries `noindex` in the markup and an
  `X-Robots-Tag` on the response, as does every export and API reply.

### Fixed

- An untrusted certificate no longer hides its own expiry date. `getpeercert()`
  returns nothing at all when verification is off, so on an instance with a
  self-signed certificate - the default OpenCloud ships - the certificate
  expiry check produced no finding whatsoever, and an expired certificate went
  unreported on exactly the instances most likely to have one. The certificate
  is now decoded from the presented chain regardless of whether it verified.
- A server offering only TLS 1.0 is reported as speaking an obsolete protocol
  rather than as unreachable. Python's client refuses such a handshake outright,
  which read as "no TLS here" instead of the finding it should have been.
- Three documentation links pointed at pages that no longer exist: the update
  guide, the external identity provider reference and the reverse proxy setup.
  All three are reachable again, in the hardening catalogue and in the README.

### Security

- The MCP tools no longer hand a scanned host a channel to the model. A
  version string, a product name, an explanation and an error message are all
  chosen by somebody else's server, and they land in a language model's
  context: each is now collapsed, stripped of non-printable characters and
  truncated, a version that does not parse becomes `unparsable`, and the
  answer carries an `untrusted` block naming those fields and stating that
  they are to be reported and never obeyed. The same warning is in the server
  instructions and the tool descriptions.
- A `uuid` given to an MCP tool is validated as a UUID before it reaches a
  request path. An HTTP client resolves `..` in a path, so `../../healthz`
  previously addressed the application rather than a scan; an identifier that
  does not parse now gets the same 404 unknown and expired do, without a
  request being made. The purge target is percent-encoded for the same reason,
  so a `&` in it can no longer add a second query parameter.
- Every MCP tool call is now rate limited against the address it actually came
  from. The in-process transport reported a hardcoded `127.0.0.1`, so in the
  default configuration every agent in the world shared one bucket and one
  audit identity - rationing strangers by each other, and letting one busy
  client lock the rest out.
- `COS_WEB_MCP_MAX_CONCURRENT_WAITS` (default `8`) caps how many tool calls
  may sit waiting on a scan at once, so a handful of calls cannot pin the
  process open for the minutes a scan may take. Nothing is refused when the
  ceiling is reached: the scan is submitted as usual and the uuid comes back
  with a note to poll `get_scan_result`, exactly as `wait: false` answers.

### Documentation

- Every page now says in its footer that this check is **not exhaustive and a
  good grade is not a certificate**: it reads what a publicly reachable
  instance shows an anonymous visitor, so an "A" means nothing checked went
  wrong, not that the instance is secure. A result page repeats it next to the
  grade and links to a fuller "what this scan cannot see", which now names the
  categories an unauthenticated scan cannot reach at all - the host and its
  packages, the container runtime, the proxy's own configuration, backups,
  storage, secrets, accounts and sign-in, existing shares, the supply chain,
  and anything only a logged-in user sees. `tests/test_webapp_api.py` fails if
  a page loses the caveat.
- [`docs/reverse-proxy.md`](docs/reverse-proxy.md), a guide to reverse proxies
  in both directions: the header set this check grades, written out for nginx,
  Apache httpd, Caddy, Traefik and HAProxy, together with the mistakes that
  cost an instance a grade; and what the scan service needs from a proxy - a
  client address it can rate limit, timeouts longer than a scan, an unbuffered
  `/mcp` event stream, and the discovery paths left unrewritten. Linked from
  the README guide table, the docs index, `docs/webapp.md` and
  `docs/troubleshooting.md`.
- `ARCHITECTURE.md` gains **The agent-facing surfaces**, which was missing
  entirely: how `webapp/workflows.py` holds the semantics once and
  `/openapi.json`, `/arazzo.json` and `/mcp` are three descriptions of it, how
  `/.well-known/ai.json` leads to all three, and what the MCP endpoint may not
  do - be a second implementation, a way around a rate limit, a channel from a
  scanned host to the model, or a place a credential lives. Its module tables
  now name `tls.py`, `remediation.py` and the seven web modules added since
  they were written. `AGENTS.md` and `.github/copilot-instructions.md` gain
  the same rules in short, so an agent working on a tool has them without
  reading the code.
- `AGENTS.md` gains a **Third parties** section, and
  `.github/copilot-instructions.md` and `frontend/README.md` the same rule in
  short: nothing in this project may connect to Twitter/X, Google or Meta -
  no script, font, embed, SDK, analytics, CAPTCHA, sign-in or share button,
  and no metadata addressed to one of them. A visitor hands this service the
  address of a system they are responsible for, and a result URL's uuid is the
  whole of its authorisation; neither belongs in a third party's logs. Plain
  links and platform-neutral OpenGraph tags stay, because nothing fetches
  them, and `tests/test_webapp_seo.py` fails if a page starts carrying such
  metadata.

## [1.7.0] - 2026-08-19

### Security

- Results are now actually encrypted at rest when `COS_WEB_ENCRYPT_RESULTS` is
  on. The ARQ worker - the process that writes the result document - built its
  store without the encryption configuration, so the setting encrypted nothing
  while appearing to work, and scan results sat in Redis in the clear. The
  worker now receives the configuration, and any process that is asked to
  encrypt without a usable `COS_WEB_ENCRYPTION_KEY_<version>` refuses to start
  rather than silently storing plaintext.
- CSV exports no longer allow spreadsheet formula injection. Cells are built
  from strings the *scanned* instance chooses - its product name, a
  `WWW-Authenticate` challenge - so an instance naming itself `=cmd|...` could
  run code on the machine of whoever opened the download. Every cell is now
  prefixed when it starts with `=`, `+`, `-`, `@`, a tab or a carriage return,
  stripped of newlines so a value cannot forge a row, and capped in length.
- A malformed `COS_WEB_ENCRYPTION_KEY_<version>` no longer puts the key
  material into the exception message, and from there into a worker log or an
  issue report. The message names the key version only.
- The purge receipt omits `targetFingerprint` unless `COS_WEB_PURGE_SIGNING_KEY`
  is set. An unkeyed hash of a hostname is not a pseudonym, and a receipt filed
  for compliance should not carry one that claims to be. The fingerprint and
  the receipt signature are now computed over domain-separated inputs.
- `DELETE /api/purge` compares the presented credential as bytes, so a header
  carrying non-ASCII characters is answered with 401 rather than raising out of
  the authorisation check.

### Added

- A right-to-be-forgotten endpoint for the web application.
  `DELETE /api/purge?target=opencloud.example.com` erases every scan held for
  one instance - status, result and metadata keys, the queue entries and the
  cooldown key derived from the target - and answers with a proof of deletion:
  the counts removed, a `remaining` count taken from a **second walk over the
  store after the deletion**, the version that issued it and an HMAC signature
  when `COS_WEB_PURGE_SIGNING_KEY` is set, verifiable later with
  `webapp.purge.verify()`. Because nothing maps a target back to its scans -
  such an index would be the record of who scanned what that this service
  refuses to keep - the purge walks the keyspace instead, on a call that never
  happens on the request path. It is authorised and absent until configured:
  without `COS_WEB_PURGE_TOKEN` the endpoint answers 404, since the call
  destroys results belonging to whoever is currently reading them. An erasure
  is recorded in the audit trail when one is kept, and described by the
  `eraseInstanceData` workflow in `/arazzo.json`. See
  [ADR 0007](adr/0007-erasure-on-request.md).
- Batch scanning in the web application. `POST /api/scans/batch` accepts a
  `targets` list and answers with what started and what did not. A batch is a
  convenience, never a discount: every target runs the whole single-submission
  pipeline in order, counting against the client rate limit, passing the SSRF
  guard and claiming its own target cooldown, so ten targets spend ten scans
  from the window. `COS_WEB_MAX_BATCH_TARGETS` (default 10) caps the list and
  refuses a longer one before anything is queued. See
  [ADR 0005](adr/0005-batch-scan-submission.md).
- PDF, CSV and SARIF exports for the web application, offered as download
  buttons on the result page and served by
  `GET /api/scans/{uuid}/export/{format}` alongside `json`. All four are
  renderings of the same finished result, produced on request and gone when
  the scan expires; a scan that has not finished answers 409 rather than 404.
  The PDF is written by `webapp/reports.py` itself, so the web image gains no
  reporting dependency, and the SARIF report now names the running version and
  carries a rule with the catalogue's explanation for every result. See
  [ADR 0006](adr/0006-dependency-free-exports.md).
- An [Arazzo 1.0.1](https://spec.openapis.org/arazzo/latest.html) description
  of the HTTP API at `/arazzo.json`, beside the OpenAPI schema and behind the
  same `COS_WEB_ENABLE_DOCS` switch. Three workflows - `scanOneInstance`,
  `scanManyInstances` and `exportFinishedScan` - describe the parts a schema
  cannot: submitting and polling until `done`, walking a batch's accepted
  uuids, and waiting out a 409 before downloading a file.
- `ARCHITECTURE.md`, describing the three layers and the boundaries between
  them, how settings reach the scanner, the request pipeline, the concurrency
  and state rules, what ships in which artefact, and where a new check,
  setting or endpoint belongs.
- Optional audit logging for the web application. `COS_WEB_AUDIT_LOG=true`
  writes one JSON record per line on the `check_opencloud.web.audit` logger
  for every accepted scan request, every rejected submission and every
  triggered rate limit or target cooldown, each with a UTC timestamp.
  Requester addresses are always recorded as a truncated HMAC fingerprint and
  never in the clear; the target is a fingerprint too unless
  `COS_WEB_AUDIT_LOG_TARGETS=true`. `COS_WEB_AUDIT_SALT` pins the fingerprint
  salt so records correlate across a restart, and leaving it unset means they
  do not. Off by default, so the ordinary log still carries lifecycle markers
  and uuids only. See [ADR 0004](adr/0004-webapp-audit-logging.md).

### Changed

- The landing page is now about scanning again. The explanations that grew
  under the form - what gets tested and what happens after the button, the
  JSON API and its fair use limits, what the server keeps, and who OpenCloud
  is - moved to `/how-it-works`, `/api`, `/privacy` and `/about`. The header
  and footer navigation reach all four, every content page ends with links to
  the others but never to itself, and the pages stay out of the OpenAPI schema
  so a generated client does not grow methods for HTML.

- The web interface has a new theme, in two halves of the same day. Light is a
  sunrise over a breakfast table: warm paper, a low sun behind the shield and
  one orange the page is led by. Dark is the night before it: a deep sky, a
  moon, and a faint field of stars behind the page. Both are entirely token
  driven at the top of `app.css`, every ink-on-tint pair still clears WCAG AA,
  and the three hand-drawn SVGs now carry both schemes internally rather than
  one hardcoded blue.

## [1.6.1] - 2026-08-18

### Fixed

- The ARQ worker Compose health check now verifies its process and Redis
  connection instead of probing the web server endpoint it does not run.
- The web application's `/healthz` probe now checks Redis and returns 503
  while its required state store is unavailable.
- The web application's `/healthz` probe now also reports aggregate queue
  depth and requires a short-lived Redis worker heartbeat.

## [1.6.0] - 2026-08-18

### Added

- Webhook signature verification using HMAC-SHA256. When configured with
  `--webhook-secret` or `COS_WEB_WEBHOOK_SECRET` (for the web application),
  webhook payloads are signed with an `X-COS-Signature` header (format:
  `sha256=<hex>`). Receivers must share the same secret to verify signatures.
- Redis encryption with key rotation support (web application). When
  `COS_WEB_ENCRYPT_RESULTS=true` is set, scan results are encrypted at rest
  using AES-256-GCM. Encryption keys are configured via
  `COS_WEB_ENCRYPTION_KEY_<VERSION>` env vars (hex-encoded 256-bit keys).
  Key rotation is transparent: new encryptions use the highest version,
  old keys still decrypt existing data. Encryption defaults to off to maintain
  backward compatibility.
- Multiple report formats for web application scan results (API):
  - **CSV format**: Export findings as CSV with scan metadata headers
  - **SARIF format**: Security Results Interchange Format for integration with
    security dashboards and tools
  - Formats are selected via `output_format` query parameter in POST requests
  - Existing dashboard and JSON formats remain unchanged

### Fixed

- A time-of-check-time-of-use vulnerability in webhook URL validation
  allowed DNS rebinding attacks to bypass SSRF protection and target private
  addresses. Webhook DNS resolution is now re-validated immediately before
  delivery and blocked if the address has changed since submission.

### Documentation

- Added `adr/0002-no-scan-result-caching.md` explaining why scan results are
  not cached across requests and the data protection and security
  considerations behind that decision.

## [1.5.5] - 2026-08-17

### Added

- Live screenshots of the hosted scanner and a completed scan of the OpenCloud
  demonstration instance in `img/`, shown in the main and Docker Hub READMEs.

### Fixed

- `ProductName: Infinite Scale` now identifies ownCloud's renamed product and
  stops the scanner before it rates a non-OpenCloud instance against OpenCloud
  lifecycle data, advisories and hardening defaults.
- The Prometheus exporter now binds to `127.0.0.1` by default rather than all
  network interfaces. Remote scrapes require an explicit listen address.

## [1.5.4] - 2026-08-17

### Added

- `adr/`, with a decision-record template and lifecycle guidance. Future
  durable architecture changes now require an ADR, and agent guidance directs
  contributors to read and maintain the relevant records.

### Changed

- The Docker Hub README now includes complete `docker run` and standalone
  Docker Compose examples, so the frontend scanner can run without cloning the
  repository.

## [1.5.3] - 2026-08-17

### Changed

- Bump version 1.5.3
- Docker Hub publication now documents that `DOCKERHUB_TOKEN` needs read,
  write and delete scopes and that its account needs Admin repository access,
  so image descriptions remain a required part of a successful publish.

## [1.5.2] - 2026-08-17

### Added

- `docker/dockerhub-readme.md`, the Docker Hub description for the web image.
  The publish workflow submits it after every image push, so release
  instructions for GitHub, Docker Compose and `docker pull` stay with the
  image.

### Changed

- The Docker Hub publishing workflow now uses the Node 24 Docker actions.
  Buildx publishes the existing max-level provenance and SBOM directly to
  Docker Hub, avoiding a second GitHub attestation request that could fail
  after the image was already published during a GitHub service outage.

## [1.5.1] - 2026-08-17

### Added

- `docker/docker-compose.dockerhub.yml`, a self-contained frontend scanner
  deployment that pulls `okxo/opencloud-scanner:latest` for the web service and
  ARQ worker while retaining the queued worker, hardened runtime and ephemeral
  Redis configuration. The existing local-build Compose files remain unchanged.

## [1.5.0] - 2026-08-17

### Added

- **A hosted instance to try, at <https://scan.okxo.de>.** The web application
  from this repository, running: paste an address, read the grade, install
  nothing. It is now the first thing the README offers, linked from
  `docs/README.md`, `docs/webapp.md` and `webapp/README.md`, and listed on PyPI
  as the project's "Live demo". The README says plainly what using it means -
  the scan runs from that server, so it sees only what the public internet
  sees, and anything private still wants the plugin or your own deployment.
- **`--release-track auto`**, and `auto` as a value of
  `scanner.release_track`, `COS_SCANNER_RELEASE_TRACK` and the web form. It
  asks the release schedule which track the installed release belongs to,
  which is the same answer as leaving the track unset - said out loud, so one
  configuration can cover instances on different tracks without declaring a
  track that is wrong for half of them.
- A workflow that re-checks the OpenCloud links this project documents after
  every merge into `main`, and once a week.
  `scripts/check_documentation_links.py` collects every link to
  `opencloud.eu`, `docs.opencloud.eu` and the OpenCloud repositories from the
  documentation, the code and the configuration and requests it. A dead link
  fails the run; a redirect is reported but does not, because `opencloud.eu`
  redirects to a language version and a job that always fails is a job nobody
  reads. A finding that explains itself with a link nobody can follow is a
  finding nobody can act on.
- The web application is published to Docker Hub as **`opencloud-scanner`**,
  built for `linux/amd64` and `linux/arm64` from `docker/Dockerfile.web` with
  provenance and an SBOM attached. `edge` follows `main`; `latest` and the
  version tags only move when the version in `pyproject.toml` names an image
  that does not exist yet, so a documentation commit cannot republish
  `latest` from a tree that is not the released one. The account, the token
  and the optional namespace come from repository secrets - nothing in the
  repository names an account, and the job skips itself rather than failing
  when they are absent, so a fork does not go red over a credential it was
  never given.

### Changed

- **`auto` is now the default release track**, on the command line, in the
  configuration file and on the web form. It is the verdict an undeclared
  track always received, so nothing is rated differently - it is now recorded
  as `auto` rather than left blank, which is the difference between a result
  that says "the schedule worked this out" and one that says nothing. The web
  form previously defaulted to `production`, where any fixed guess is wrong
  for somebody: `production` calls a current rolling instance out of date and
  `rolling` reports an end of life a production instance has not reached.
  Naming a track still overrides it everywhere.
- **The setup wizard asks for the release track on its own**, with a note on
  what auto-detection does. It used to sit inside the update check group, so
  an operator who declined that group - reasonably, having no interest in
  where the newest release is looked up - was never asked about the setting
  that decides every lifecycle verdict.
- **The palette is brighter, and now readable where it was not.** Each status
  colour became three tokens instead of one: `--x` paints the dial, the rules
  and the borders, `--x-soft` is the tint behind them, and the new `--x-ink`
  is the tone that carries text on that tint. The single tone had to be both
  at once, which is why the amber and green tags sat at 2.9:1 - below WCAG AA,
  on the two labels that say a check passed or nearly did. Every text pair in
  both light and dark mode now clears 4.5:1 and every graphic tone 3:1, while
  the surfaces, the brand blue and the teal accent all moved lighter. The
  hard-coded glows and the white button label became tokens as well
  (`--brand-glow`, `--accent-wash`, `--on-brand`), so the palette has one
  source again - the button label is dark in dark mode, where its gradient is
  the light brand tone.
- The header says what the page is rather than what the package is called:
  the brand line is now just *Security scan for OpenCloud instances*. The
  package name sat above that same sentence in smaller type, so a first-time
  visitor read a repository name before they read what the site does. It is
  still named in the footer and linked from the source line.
- **A release ahead of its declared track is no longer end of life.** Running
  the current rolling release while declaring the production track rated the
  instance `F` and alerted `CRITICAL` - about a machine running the newest
  OpenCloud there is, with everything the production track ships and more. Such
  an instance is now reported as *ahead of* its track, with the current release
  of that track named. The `F` is kept for what it was meant for: a release
  *behind* the current one of the declared track, which really is missing
  fixes. The upgrade recommendation still never points backwards.

### Fixed

- The test suite no longer reads the configuration of the machine it runs on.
  A developer who had run `--configure` for a real instance had
  `~/.config/check-opencloud-security/.env.json`, and the tests that ask "what
  does the plugin see when nothing is configured?" saw their host, their track
  and their waivers instead of nothing - four failures locally, none in CI, and
  a real hostname printed into the failure output. Discovery is now pointed at
  an empty home and an empty working directory, created per test.
- The web application tests no longer warn on every run. Starlette 1.6
  deprecated driving `TestClient` with `httpx`, so the test group asks for
  `httpx2` instead. A warning that is printed on every green run is a warning
  nobody reads when it finally matters.

### Security

- **A server that reports ownCloud or Nextcloud in `status.php` is no longer
  scanned as OpenCloud.** All three serve the same endpoint - OpenCloud
  inherited it from them - so the document alone never said what was running,
  and the scan happily rated an ownCloud instance against OpenCloud's release
  schedule, advisories and hardening defaults. That is a confident answer about
  the wrong software, which is worse than no answer: the scan now stops with an
  error naming the product it found.

## [1.4.0] - 2026-08-15

### Added

- **A reverse proxy check, and one for the identity provider.**
  `reverseProxyDetected` records whether anything answers in front of the
  instance - a `Server` header naming Nginx, Caddy, Cloudflare and the like, or
  a forwarder-only header such as `Via` - and `identityProviderDetected`
  records whether the sign-in issuer could be established at all. Both are
  severity `low` and cost the rating nothing by design: Traefik and HAProxy
  announce nothing by default, so their absence is weak evidence and must not
  become a grade. When no provider is found, the explanation points at
  OpenCloud's own documentation, because the usual cause is a proxy that does
  not forward `/.well-known/`.
- The landing page of the web application now credits OpenCloud and links to
  the project and its documentation, alongside the notice that this scanner is
  independent of OpenCloud GmbH. The result page links to the same
  documentation when no identity provider was found, and shows the reverse
  proxy when one was.
- **The scan now works out who signs users in.** It reads
  `/.well-known/openid-configuration`, or the redirect the instance answers it
  with, and records the issuer in `identityProvider`: whether one was found,
  whether it is external to the instance, and which product it looks like -
  Keycloak, Authentik, Authelia, Zitadel, Entra ID and a few more are
  recognised by their issuer URL. Nothing is submitted to the instance to
  establish this: the discovery document and the `Location` header are read,
  and no login form is ever filled in. It is context rather than a verdict -
  the built-in provider fails nothing - and the result page shows it.
- The release track on the web form. `release_track` joins `target_url`,
  `ignore_hardenings` and `output_format` as the fourth - and last - thing a
  request may choose: `rolling`, `production` or `lts`, defaulting to
  `production`. It is the web equivalent of the plugin's `--release-track`, so
  it changes how a version is rated, never how hard the instance is probed,
  and an unknown value falls back to the default rather than failing the scan.
  The result page shows which track it was rated against.
- `COS_WEB_ENABLE_DOCS`, which serves the OpenAPI schema, Swagger UI and
  ReDoc at `/openapi.json`, `/docs` and `/redoc`. Off by default, because
  Swagger UI is the only page in this service that loads a script from another
  origin: enabling it relaxes the policy on those two pages and nowhere else,
  and logs `api_docs_enabled` at startup so a deployment says so.
- The backend version in the footer of every page of the web application, as a
  badge linking to the releases, matching what `/healthz` reports. A result is
  only as trustworthy as the build that produced it, and a bug report needs
  that number.
- The release refresh now also updates the README. `scripts/update_release_schedule.py`
  rewrites the generated table between the `release-schedule` markers with the
  current release of each track, so the documentation cannot go on quoting a
  version that has already been superseded. `--no-readme` refreshes only the
  data file, and `--check` now fails when the table has drifted from the
  schedule.
- A friendly way out of a rate limit in the web application: a 429 now says so
  casually and points at the project on GitHub, so whoever hit the limit can
  run exactly the same check themselves without one. The pointer is in the
  page and in the JSON response alike.
- A trademark and affiliation notice in the README, the documentation index,
  the library README, the web application guide, the footer of every page of
  the web application and the bundled quick start: this project is independent
  of OpenCloud GmbH, and all rights in OpenCloud remain with them.
- A self-hosted public scan service: a FastAPI web application with a
  hand-written frontend, an ARQ worker and Redis for ephemeral state. A
  visitor submits a URL and gets the same rating the plugin produces, with no
  account, no database and nothing kept beyond the result TTL.
- Graceful queueing for the web application. Requests beyond the configured
  worker count are accepted and queued in FIFO order rather than refused, and
  the page shows the position in line while the scan waits.
- Per-scan isolation in the web application: every submission gets a `uuid4`
  capability and its own `scan:{uuid}:*` Redis namespace, every key carries a
  TTL, there is no scan listing endpoint, and an unknown or expired scan is a
  404 that reveals nothing.
- An SSRF guard and two independent rate limits for the web application.
  Targets must resolve exclusively to public unicast addresses and are
  re-resolved in the worker against DNS rebinding; client and target limits
  answer 429 with `Retry-After`, and client addresses are only ever kept as a
  peppered HMAC.
- `docker/Dockerfile.web` and `docker/docker-compose.yml`, orchestrating the
  web application, the worker and Redis with concurrency fixed server-side.
- `scripts/build_web_bundle.py` and a release workflow step that publish
  `check_opencloud_security_web.tar.gz`, the complete web application with a
  SHA-256 checksum, as a GitHub release asset.
- [The public scan service](docs/webapp.md): deployment guide covering every
  `COS_WEB_*` setting, the request pipeline, the isolation model and the HTTP
  API.
- **Office and calendar integrations are reported as observations.** The
  result document gains an `integrations` block: `office` says whether
  `/app/list` names a registered app provider such as Collabora, `calendar`
  says whether anything answers `/.well-known/caldav`. Neither becomes a check
  and neither can move the rating - a registered provider says nothing about
  whether it is configured well. Audit logging is deliberately **not** checked:
  the audit service consumes the internal event bus and exposes no HTTP surface
  or capability, so there is nothing an unauthenticated client can read.

### Changed

- **`basicAuthDisabled` no longer costs two grades.** It is a `medium`
  finding, capping the rating at 4 rather than 3, and a `low` one when an
  external identity provider handles the interactive login. CalDAV, CardDAV
  and WebDAV clients cannot speak OpenID Connect and have nothing but basic
  authentication to use, so an instance that wants a calendar has to leave it
  on; rating that as a serious failure told operators something they were
  right to disbelieve. It stays a finding - a password does work on every
  request - and the remediation now says to hand those clients app tokens
  rather than account passwords.
- **Every Dockerfile and compose file now lives in `docker/`**, and the build
  context of each is the repository root. `docker/docker-compose.yml` is the
  complete web application - frontend, backend worker and Redis - so
  `cd docker && docker compose up --build -d` is a working deployment with no
  further arguments. The plugin's own scan service moved to
  `docker/docker-compose.monitoring.yml`, and building the plugin image is now
  `docker build -f docker/Dockerfile .`. `.dockerignore` stays in the root,
  which is where the daemon reads it from.
- CI actions moved off the deprecated Node 20 runtime: `actions/checkout@v7`,
  `astral-sh/setup-uv@v10.0.0`, `actions/dependency-review-action@v5.0.0`,
  `actions/attest-build-provenance@v4`, `peter-evans/create-pull-request@v8`,
  and `actions/attest-sbom` replaced by `actions/attest@v4`, which it now only
  wraps. The Bandit scan no longer uses an unversioned third-party action: it
  installs Bandit and uploads the SARIF itself, with the same thresholds and
  exclusions. Dependabot now watches GitHub Actions and the container images
  as well, so this does not have to be noticed by hand again.
- The PyPI wheel and sdist now explicitly exclude `frontend/` and `webapp/`.
  Installing the plugin on a monitoring host must not bring in FastAPI, Redis
  or ARQ; the web application ships as a release asset instead.

### Fixed

- Removed stale root-level `Dockerfile` and `docker-compose.yml` copies so CI
  and contributors use the canonical container definitions in `docker/`.

### Security

- Response bodies are read up to `max_response_bytes` (8 MiB) and no further,
  so a target answering with an endless body cannot hold a worker forever.
- Advisory links are rendered only when they are `http://` or `https://`,
  `peter-evans/create-pull-request` is pinned to a commit rather than a
  mutable tag, the plugin logs a webhook URL as scheme and host only because
  the rest of it is usually the credential, and the scan service compares its
  auth token as bytes so that a non-ASCII header is a 401 rather than a dead
  handler thread.

### Documentation

- The landing page explains how to drive the API from a script - the two curl
  calls, the four accepted fields, the actual rate limits and where to get the
  code when they bite - and links to Swagger, ReDoc and the schema when the
  documentation is enabled. `frontend/static/vendor/README.md` names the
  vendored packages, versions and licences.
- `README.md` and `opencloud_local_scan/README.md` document the `integrations`
  block and, as explicitly as it deserves, what the scan does not answer:
  audit logging, whether an integration is configured correctly, and anything
  needing credentials.
- [`docker/README.md`](docker/README.md) and
  [`frontend/README.md`](frontend/README.md): what each container file builds
  and why the build context is the repository root, and the frontend's rules,
  design tokens, template contract and how to run one of your own.
- [`webapp/README.md`](webapp/README.md): the web application and its frontend
  for whoever changes them or writes a client - every route and its
  status codes, how to reach Swagger, the four fields a request may send and
  why nothing else is accepted, every setting worth knowing on day one, and
  the template contract for running a frontend of your own.
- The issue templates ask where a problem happened - plugin, scanner library,
  web backend or page - and the pull request template has a checklist for a
  change to the web application or the frontend.

## [1.3.0] - 2026-08-13

### Added

- Itemized baseline diffs in text, Markdown, and Slack Block Kit JSON,
  covering CVEs, hardening and check changes, rating/lifecycle trends, and
  installed/update-version shifts. Webhooks now carry the structured diff.
- Native Prometheus text output and a lightweight `/metrics` exporter for
  Kubernetes and cloud-native monitoring. The exporter refreshes scans on
  demand with a configurable cache interval and requires no extra dependency.

### Changed

- Multi-host checks now run one worker per target, up to the configurable
  default ceiling of five. A single-host check remains single-threaded, and
  result blocks and Nagios perfdata remain isolated and ordered by input host.

## [1.2.3] - 2026-08-13

### Security

- Block webhook notifications to private, loopback, and link-local addresses
  by default to prevent server-side request forgery. Internal receivers require
  the explicit `--allow-private-webhooks` / `COS_ALLOW_PRIVATE_WEBHOOKS` opt-out.

## [1.2.2] - 2026-08-13

### Documentation

- Clarified that the built-in scanner is not exhaustive and that its rating
  does not guarantee an OpenCloud instance is completely secure.

## [1.2.1] - 2026-08-13

### Documentation

- Documented shell-completion installation with uv and added an acknowledgment
  of the OpenCloud project to the README.

## [1.2.0] - 2026-08-13

### Added

- **`--baseline PATH` and `--warn-on-new`**, for operators who do not want the
  full state of every instance on every run. The baseline records the findings
  of each run, one entry per host, and `--warn-on-new` then reports `OK` while
  the picture is unchanged and the normal status as soon as anything is new or
  worse. The evidence is never suppressed - only the alert - and three things
  always escalate: a new finding, a lower rating, and a release past its end of
  life, which receives no security fixes and therefore cannot be grandfathered
  in. The first run has nothing to compare against, so it reports normally and
  becomes the baseline; `--warn-on-new` without `--baseline` is rejected rather
  than quietly reporting "nothing new" forever; and a baseline that cannot be
  written is a line of output, never a change of verdict. See
  [Reporting only what changed](README.md#reporting-only-what-changed).
- **`--self-update-check`**, which asks PyPI once a day whether a newer version
  of the plugin has been published and appends a note. Off by default, cached
  under `${XDG_CACHE_HOME:-~/.cache}/check-opencloud-security/`, silent on
  every failure, and it never changes the exit code - whether PyPI answered
  says nothing about the instance being monitored.
- **`--upgrade-self --check-only`** as a second spelling of
  `--upgrade-self check`, because that is the pairing people reach for first.
  Used without `--upgrade-self` it is rejected with a usage error instead of
  being silently ignored.
- **Shell completion** via [argcomplete](https://github.com/kislyuk/argcomplete)
  for both `check-opencloud-security` and `check-opencloud-scanner`. It
  completes option names, the values of the options that take a fixed set, and
  the hardening identifiers of `--ignore-hardening`, which are long enough to
  be worth not typing. Install it with the new `completion` extra
  (`pipx install 'check-opencloud-security[completion]'`); without it nothing
  is registered and the plugin behaves as before. See
  [Shell completion](docs/installation.md#shell-completion).
- **A `HEALTHCHECK` in the Dockerfile** that verifies the image rather than an
  instance: the package imports and the two data files it rates against - the
  release schedule and the bundled advisory database - parse. It needs no
  network, so it stays honest on an air-gapped host. Containers running the
  scan service keep using the HTTP `/healthz` probe that `docker-compose.yml`
  already overrides it with.
- **An SBOM and Sigstore build attestations** for every release. The publish
  workflow generates a CycloneDX SBOM from the resolved runtime environment,
  attaches it to the GitHub release, and signs provenance for the wheel and
  sdist with a short-lived Sigstore certificate - so there is no signing key
  for this project to leak. Verify a downloaded artifact with
  `gh attestation verify <file> --repo sowoi/check-opencloud-security`.
- **`.github/copilot-instructions.md`**, so GitHub Copilot picks up the same
  rules `AGENTS.md` already states - the layer boundary between the plugin and
  the scanner library, how a setting travels from the file to
  `ScannerSettings`, and the conventions that are invisible in any single file.
- **A [`docs/`](docs/README.md) folder**, with the deployment walk-throughs
  that were crowding the README - [Icinga Director](docs/icinga-director.md),
  [Ansible](docs/ansible.md), [scheduling](docs/scheduling.md) and
  [troubleshooting](docs/troubleshooting.md) - and worked examples for the
  places this check tends to end up: [Kubernetes](docs/kubernetes.md),
  [CI pipelines](docs/ci.md), [Prometheus and Grafana](docs/prometheus.md),
  [webhook adapters](docs/webhook-recipes.md) for Slack, ntfy and
  Alertmanager, and [fleets of instances](docs/many-instances.md). The README
  keeps a guide table and links into each of them.

### Changed

- **`--configure` now edits the configuration instead of starting from
  scratch.** The file already on disk is loaded and every stored value is
  offered as the default for its question, so Enter keeps it and only what
  needs changing has to be typed; `-` removes a configured value, and keys the
  wizard has no question for survive untouched instead of being silently
  dropped. Before saving it offers a test scan of the host with the answers
  just given, and diagnoses the usual failures (certificate, unreachable, not
  an OpenCloud) rather than only reporting them. A failing scan does not block
  saving - the file may well be written somewhere that cannot reach the
  instance. `check-opencloud-scanner configure --no-test-scan` skips the offer.

- **`--dry-run` is gone; use `--upgrade-self=check` instead.** The flag only
  ever meant anything together with `--upgrade-self`, and on its own it was
  accepted and silently ignored - a dangerous thing for a flag whose whole
  promise is "this changes nothing". `--upgrade-self` now takes an optional
  value, `run` (the default when given without one) or `check`, and a bare
  `--dry-run` is rejected rather than obeyed halfway.

## [1.1.0] - 2026-08-13

### Added

- **`--configure`**. An interactive setup that asks for the settings the check
  needs, explains what each one is for and shows an example, then saves them as
  JSON with mode `0600`. Only the host is required; the optional settings are
  offered group by group and skipped unless you ask for them. The file is found
  automatically from then on, so the check runs with no arguments at all.
  `check-opencloud-scanner configure` does the same for the scanner.
- **JSON configuration files.** A configuration file whose name ends in
  `.json` is read as JSON; anything else is still YAML. `./.env.json` and
  `~/.config/check-opencloud-security/.env.json` were added to the paths
  searched automatically.
- **`--upgrade-self`**. Works out whether the plugin was installed with pipx,
  uv or pip and runs the matching upgrade command. `--dry-run` prints the
  command instead. A git checkout is refused, since installing over a working
  copy would leave you editing files that are no longer executed.
- **`SECURITY.md`**, describing what is in scope, how to report a
  vulnerability privately, and what the plugin does with your data.
- **`CODE_OF_CONDUCT.md`**, including the rule this project cares about most:
  no credentials and no production hostnames in a public thread.
- Issue forms for a bug, a wrong finding or rating, and a feature request,
  plus a pull request template. The finding form asks for the `--debug` output
  and for whether the setting is one an operator can actually change, which is
  what deciding a hardening report usually turns on.
- README: how to feed the webhook into an Uptime Kuma Push monitor.
- **`--concurrency` / `COS_SCANNER_CONCURRENCY`**. Runs the scanner's probes in
  parallel instead of one after the other, which shortens a scan considerably -
  most of all when debug-port probing runs into a firewall. Defaults to `1`,
  meaning no multithreading and exactly the previous sequential behaviour;
  values above `32` are clamped. The setting changes only the timing: findings
  and their order are identical whatever it is set to.

### Changed

- **The version is now declared once, in `pyproject.toml`.**
  `opencloud_local_scan.__version__` derives it from the installed package
  metadata, or from `pyproject.toml` itself when running out of a checkout, and
  `check_opencloud_security.py` imports that instead of carrying its own
  literal. A release is still cut by editing `pyproject.toml` by hand, but the
  three numbers can no longer drift apart.
- Documentation now describes the scan backend simply as the built-in scanner.
- **Release notes are collected under `## [Unreleased]`.** Changes are written
  down as they are made; `scripts/release_notes.py` renames that heading to the
  version from `pyproject.toml` when a release is cut, writes the same body to
  `RELEASE.md` and leaves a fresh empty `## [Unreleased]` behind. The version
  itself is bumped by hand and is still the only thing that triggers a release.
  `--require-unreleased` refuses to fall back to generated commit-subject notes.

## [1.0.0] - 2026-08-12

First release. A Nagios/Icinga plugin that checks an OpenCloud instance for
known vulnerabilities and misconfiguration. The plugin scans entirely on its
own, using a built-in scanner. The ratings follow the scale of the
Nextcloud scan API, so that existing thresholds and dashboards keep their
meaning.

### Added

- **Built-in scanner** (`opencloud_local_scan`). Reads `/status.php` and the
  unauthenticated capabilities endpoint, evaluates security headers, and rates
  the instance on a `0`-`5` scale. No data about the instance leaves the
  network; hostnames, IP addresses, IPv6 and custom ports are all accepted.
- **OpenCloud-specific checks**: unauthenticated WebDAV, Graph and OCS
  endpoints; exposed `opencloud.yaml`, `proxy/server.key`, the idm boltdb,
  `.env` and `.git/config`; reachable service debug ports and `/metrics`,
  `/config`, `/debug/pprof` handlers; enabled HTTP basic authentication;
  version disclosure via response headers and WebFinger; directory listings;
  maintenance mode and pending database upgrades.
- **Catch-all detection.** OpenCloud's single-page frontend answers unknown
  paths with HTTP 200, so the scanner learns what a nonexistent path looks
  like before reporting any path as exposed.
- **TLS inspection** with graceful degradation: verified HTTPS, then
  unverified HTTPS with a `tlsTrusted` finding, then plain HTTP with a
  critical `httpsAvailable` finding. Covers handshake, protocol version and
  certificate expiry.
- **Correct version handling.** `/status.php` reports hardcoded legacy
  `version`/`versionstring` fields for old sync clients; only `productversion`
  is the real release. Instances that offer nothing else are reported as
  `legacyVersion` instead of being rated against a version that means nothing.
- **Hardening reporting** derived from what the instance actually reports -
  HSTS strength, CSP quality, basic auth, public-link password and expiry
  enforcement, user enumeration and password policy - rather than inferred
  from the version number.
- **Update check** against the OpenCloud release feed on GitHub, with `auto`,
  `feed`, `pinned`, `bundled` and `off` modes. The offline modes and the
  automatic fallback in `auto` keep an air-gapped or rate-limited setup
  working.
- **Lifecycle-aware end-of-life detection.** OpenCloud maintains three kinds
  of releases side by side, and each has its own support window: *rolling*
  (a release roughly every three weeks, only the newest one receives fixes),
  *production* (roughly every six months, kept alive with patch releases until
  the next production release takes over) and *LTS* (a production line with
  two years of backports). The verdict follows the published release schedule
  in `opencloud_local_scan/data/release_schedule.json`, refreshed on release
  and monthly by a scheduled workflow, because a flat list of major releases
  cannot express three overlapping support windows.
- **`releaseType` and `lifecycle` in the result document**, reporting the
  release line, its track, its release date, when support ends, how many days
  are left and which release to upgrade to. The plugin prints a
  `Release lifecycle:` line and a `support_days_left` performance value, and
  the webhook payload carries both fields.
- **The update check is track aware.** A release feed only knows the newest
  release overall, and on OpenCloud that is always a rolling one. Offering it
  to a production or LTS instance would silently move it onto a track with a
  three-week support window, so those instances are offered the newest release
  of their own track instead. `UpdateInfo` carries `track` and
  `newestRelease`, so the newest release overall is reported but not presented
  as the thing to install.
- **`--release-track` declares which track an instance follows** (`rolling`,
  `production` or `lts`). Without it a version is judged as generously as is
  true, which is right when nobody has said otherwise but wrong for anyone
  deliberately on the rolling track, where `7.2.3` went out of support the day
  `7.4.0` shipped. With a declared track the version is judged on that track
  alone, the update recommendation follows it, and the output marks the track
  as declared rather than inferred. A version that was never published on its
  declared track is reported with the reason rather than an empty support
  date, and is never told to "upgrade" to an older release.
- **`--ignore-hardening` accepts a finding you are not going to fix.** Some
  findings are real but not actionable in a given environment - a CSP that
  cannot be tightened without breaking the web UI, an HSTS header owned by a
  reverse proxy. The rating is recalculated without the waived finding, so
  accepting one genuinely changes the grade instead of leaving the check
  permanently yellow. The option is repeatable, takes a comma-separated list,
  understands shell-style wildcards (`debugPort:*`), and matches hardening
  measures, security headers, `httpsEnforced` and additional-check ids alike -
  one option for all of them, because `basicAuthDisabled` is both a hardening
  measure and an additional check. A waiver hides an alert, not the evidence:
  waived findings drop out of the alert lines, the `hardenings_missing` and
  `extra_checks_failed` metrics and the webhook payload, but stay in the
  result document flagged with `"ignored": true` and are listed as
  `Ignored by configuration (n): ...` in the output. Only a finding that
  actually failed can be waived, and no waiver can clear an end-of-life
  release.
- **`--debug` explains the rating.** A grade on its own is a verdict without
  an argument, so the check can show its reasoning: where the rating started
  (version and advisory database), which failed check capped it and by how
  much, the final value, and the thresholds that turned it into a WARNING or
  CRITICAL. A failed check that did *not* decide the outcome is listed too,
  marked as such, so nothing looks quietly dropped. The same breakdown is
  available as structured data in `ratingExplanation`, sorted by severity so
  it does not depend on the order the checks happened to run in.
- **Every hardening identifier is explained.** `basicAuthDisabled` and
  `cspWithoutUnsafeInline` say nothing to someone who has to fix them, so the
  `opencloud_local_scan.hardening` catalogue pairs each flag with a
  plain-language meaning, the OpenCloud environment variable that governs it
  (`PROXY_ENABLE_BASIC_AUTH`,
  `OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD`,
  `PROXY_CSP_CONFIG_FILE_LOCATION`, ...) and a link to the documentation.
- **Findings that no setting can clear are recorded but never alerted on.**
  Public-link expiry is hardcoded in OpenCloud, so `publicLinkExpirationEnforced`
  fails on every instance and no operator can fix it; alerting on it trains
  people to ignore the hardening line altogether. Such flags stay in the
  result document and in `--debug`, but are kept out of the alert line, the
  `hardenings_missing` metric and the webhook.
- **Advisory database** matching on the half-open range
  `[introduced, fixed)`, accepting the native, GitHub Advisory and OSV
  formats from the bundled file, extra files and a remote feed.
- **`check-opencloud-scanner`** with `scan` (one-shot JSON) and `serve`
  (HTTP service with `/api/queue`, `/api/result/<uuid>`, `/api/requeue`,
  `/api/scan` and `/healthz`, optional token auth and a per-host result
  cache).
- **Configuration** from a YAML file, `COS_`-prefixed environment variables or
  a secret provider (`secret://`, `file://`, `env://`, opt-in `exec://`),
  with command line > environment > file > default precedence. This includes
  `scanner.release_schedule` for sites with vendor support commitments that
  differ from the public ones, `scanner.release_track` and
  `scanner.ignore_hardenings`.
- **Monitoring integration**: Nagios/Icinga exit codes, performance data
  (`rating`, `vulnerabilities`, `time`, `hardenings_missing`,
  `extra_checks_failed`, `update_available`, `support_days_left`),
  configurable WARNING/CRITICAL thresholds, optional hardening evaluation,
  multi-host runs reporting the worst state, retries with exponential backoff,
  and optional webhook notifications that never change the reported state.
- **Deployment**: a Docker image and `docker-compose.yml`, an Ansible role,
  systemd service/timer and cron examples, Icinga2 and Icinga Director command
  definitions.
- Documentation, a test suite covering the scanner, service, configuration,
  release lookup, thresholds, webhooks, multi-host handling and the plugin
  end to end as a real subprocess, and CI workflows for tests, ruff, mypy,
  bandit, dependency review, multi-version nox runs, PyPI publishing and the
  monthly release-schedule refresh.
