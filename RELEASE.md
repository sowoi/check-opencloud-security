## check-opencloud-security 1.18.0

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
